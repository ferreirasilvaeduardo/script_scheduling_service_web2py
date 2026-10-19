# -*- coding: utf-8 -*-
"""Gerador de scripts SQL de implantacao e rollback para o SSS no Oracle 11gR2+.

Gera scripts .sql autocontidos prontos para execucao direta por DBAs via SQL*Plus ou
SQL Developer em ambientes de homologacao e producao, sem depender de execucao Python
no servidor de banco de dados.

Produz:
  - 01_implantar_sss.sql : DDL (189 objetos), DML Seed (5 ambientes + controle + perfil admin), Estatisticas
  - 02_rollback_sss.sql  : Desinstalacao total e limpa (Drop triggers, tabelas CASCADE PURGE, sequences)
  - 03_grants_sss.sql    : Privilegios minimos por papel (web, agente, purge, monitor) [opcional]
"""
import argparse
import os
import sys

# Garante acesso aos modulos locais
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_MODULES_DIR = os.path.join(_BASE_DIR, "modules")
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)

import ddl_builder
import sql_ident
import sss_config


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        description="Gera scripts SQL (.sql) de implantacao e rollback Oracle para o SSS",
        add_help=True,
    )
    parser.add_argument("--config", dest="config", default=None, help="Caminho do config.ini (opcional)")
    parser.add_argument("--owner", dest="owner", default=None, help="Owner do esquema Oracle (ex: OPENRISOW)")
    parser.add_argument("--prefixo", dest="prefixo", default=None, help="Prefixo de tabelas (ex: tbsss_)")
    parser.add_argument("--lob-basicfile", dest="lob_basicfile", action="store_true", help="Fallback LOB BASICFILE")
    parser.add_argument("--out-dir", dest="out_dir", default="docs/sql", help="Diretorio de destino dos arquivos .sql")
    parser.add_argument("--grants-para", dest="grants_para", default=None,
                        help="web=u1,agente=u2,purge=u3,monitor=u4 (padrao: contas do config.ini; nunca PUBLIC)")
    parser.add_argument("--admin-login", dest="admin_login", default=None, help="Login do administrador inicial no seed")
    parser.add_argument("--admin-nome", dest="admin_nome", default=None, help="Nome do administrador inicial")
    parser.add_argument("--admin-senha-hash", dest="admin_senha_hash", default=None, help="Hash PBKDF2 da senha admin")
    parser.add_argument("--stdout", dest="stdout", choices=["implantar", "rollback", "grants"], default=None, help="Imprime no stdout")

    args = parser.parse_args(argv)

    # 1. Carrega configuracoes de owner e prefixo
    owner = args.owner
    prefixo = args.prefixo
    lob_storage = "BASICFILE" if args.lob_basicfile else "SECUREFILE"

    cfg = None
    # O config tambem fornece as contas dos papeis quando --grants-para nao e informado (README §11.1).
    if args.config or (not owner or not prefixo) or not args.grants_para:
        caminho_cfg = args.config
        if not caminho_cfg:
            candidato = os.path.join(_BASE_DIR, "instance", "config.ini")
            if os.path.isfile(candidato):
                caminho_cfg = candidato
            else:
                candidato_ex = os.path.join(_BASE_DIR, "instance", "config.ini.example")
                if os.path.isfile(candidato_ex):
                    caminho_cfg = candidato_ex

        if caminho_cfg and os.path.isfile(caminho_cfg):
            try:
                cfg = sss_config.carregar(caminho_cfg)
                if hasattr(cfg, "oracle"):
                    if not owner:
                        owner = getattr(cfg.oracle, "owner", "OPENRISOW")
                    if not prefixo:
                        prefixo = getattr(cfg.oracle, "table_prefix", "tbsss_")
                    if not args.lob_basicfile:
                        lob_storage = getattr(cfg.oracle, "lob_storage", "SECUREFILE")
            except Exception as exc:
                print("Aviso ao ler config.ini: %s" % exc, file=sys.stderr)

    owner = owner or "OPENRISOW"
    prefixo = prefixo or "tbsss_"

    try:
        sql_ident.validar_owner(owner)
        sql_ident.validar_prefixo(prefixo)
        sql_ident.validar_registro(prefixo)
    except Exception as exc:
        print("Erro de validacao em identificadores Oracle: %s" % exc, file=sys.stderr)
        return 2

    papeis_grants = {}
    if args.grants_para:
        for p in args.grants_para.split(","):
            p = p.strip()
            if not p:
                continue
            if "=" not in p:
                print("Formato invalido em --grants-para: use papel=usuario", file=sys.stderr)
                return 2
            papel, usr = p.split("=", 1)
            papeis_grants[papel.strip().lower()] = usr.strip()
    elif cfg is not None:
        # web e agente usam [oracle] user (cada no le o seu config.ini); purge, [retencao] purge_user.
        # A conta do monitor fica no secrets.cfg: so por --grants-para.
        usr_app = getattr(getattr(cfg, "oracle", None), "user", None)
        papeis_grants = {
            "web": usr_app,
            "agente": usr_app,
            "purge": getattr(getattr(cfg, "retencao", None), "purge_user", None),
        }
    try:
        ddl_builder.gerar_grants_por_papel(owner, prefixo, papeis_grants)
    except ValueError as exc:
        print("Erro nos GRANTs por papel: %s" % exc, file=sys.stderr)
        return 2

    # 2. Geracao dos scripts
    script_implantar = ddl_builder.gerar_script_implantacao_completo(
        owner=owner,
        prefixo=prefixo,
        lob_storage=lob_storage,
        admin_login=args.admin_login,
        admin_nome=args.admin_nome,
        admin_senha_hash=args.admin_senha_hash,
        papeis_usuarios=papeis_grants,
    )

    script_rollback = ddl_builder.gerar_script_rollback(
        owner=owner,
        prefixo=prefixo,
    )

    script_grants = ""
    if args.grants_para:
        grants = ddl_builder.gerar_grants_por_papel(owner, prefixo, papeis_grants)
        script_grants = "\n".join([
            "-- ==============================================================================",
            "-- Script Scheduling Service (SSS) - Grants por Papel Oracle 11gR2+",
            "-- Owner: {}".format(owner),
            "-- Prefixo: {}".format(prefixo),
            "-- ==============================================================================",
            "SET DEFINE OFF;",
            "",
        ] + grants + ["", "PROMPT Grants aplicados com sucesso.", ""])

    # 3. Saida stdout se solicitada
    if args.stdout == "implantar":
        print(script_implantar)
        return 0
    elif args.stdout == "rollback":
        print(script_rollback)
        return 0
    elif args.stdout == "grants":
        print(script_grants)
        return 0

    # 4. Gravacao dos arquivos
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    arq_implantar = os.path.join(out_dir, "01_implantar_sss.sql")
    arq_rollback = os.path.join(out_dir, "02_rollback_sss.sql")

    with open(arq_implantar, "w", encoding="utf-8") as f:
        f.write(script_implantar)

    with open(arq_rollback, "w", encoding="utf-8") as f:
        f.write(script_rollback)

    print("Scripts SQL gerados com sucesso:")
    print("  - Implantacao : {}".format(arq_implantar))
    print("  - Rollback    : {}".format(arq_rollback))

    if script_grants:
        arq_grants = os.path.join(out_dir, "03_grants_sss.sql")
        with open(arq_grants, "w", encoding="utf-8") as f:
            f.write(script_grants)
        print("  - Grants      : {}".format(arq_grants))

    return 0


if __name__ == "__main__":
    sys.exit(main())
