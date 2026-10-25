# -*- coding: utf-8 -*-
"""Gerador de scripts SQL de implantacao e rollback para o SSS no Oracle 11gR2+.

Gera scripts .sql autocontidos prontos para execucao direta por DBAs via SQL*Plus ou
SQL Developer em ambientes de homologacao e producao, sem depender de execucao Python
no servidor de banco de dados.

Produz:
  - 01_deploy_sss.sql : DDL (189 objetos), DML Seed (5 ambientes + controle + perfil admin), Estatisticas
  - 02_rollback_sss.sql  : Desinstalacao total e limpa (Drop triggers, tabelas CASCADE PURGE, sequences)
  - 03_grants_sss.sql    : Privilegios minimos por papel (web, agente, purge, monitor) [opcional]
"""
import argparse
import os
import sys

# Garante acesso aos modulos locais
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for _code_dir in (os.path.join(_BASE_DIR, "modules"), os.path.join(_BASE_DIR, "src")):
    if _code_dir not in sys.path:
        sys.path.insert(0, _code_dir)

import ddl_builder
from sss.core import sql_ident
from sss.config import sss_config


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        description="Gera scripts SQL (.sql) de implantacao e rollback Oracle para o SSS",
        add_help=True,
    )
    parser.add_argument("--config", dest="config", default=None, help="Caminho do config.ini (opcional)")
    parser.add_argument("--owner", dest="owner", default=None, help="Owner do esquema Oracle (ex: OPENRISOW)")
    parser.add_argument("--prefix", dest="prefixo", default=None, help="Prefixo de tabelas (ex: tbsss_)")
    parser.add_argument("--lob-basicfile", dest="lob_basicfile", action="store_true", help="Fallback LOB BASICFILE")
    parser.add_argument("--out-dir", dest="out_dir", default="docs/sql", help="Diretorio de destino dos arquivos .sql")
    parser.add_argument("--grants-to", dest="grants_para", default=None,
                        help="web=u1,agent=u2,purge=u3,monitor=u4 (padrao: contas do config.ini; nunca PUBLIC)")
    parser.add_argument("--admin-login", dest="admin_login", default=None, help="Login do administrador inicial no seed")
    parser.add_argument("--admin-name", dest="admin_nome", default=None, help="Nome do administrador inicial")
    parser.add_argument("--admin-password-hash", dest="admin_senha_hash", default=None, help="Hash PBKDF2 da senha admin")
    parser.add_argument("--stdout", dest="stdout", choices=["deploy", "rollback", "validate", "grants"], default=None, help="Imprime no stdout")

    args = parser.parse_args(argv)

    # 1. Carrega configuracoes de owner e prefixo
    owner = args.owner
    prefix = args.prefixo
    lob_storage = "BASICFILE" if args.lob_basicfile else "SECUREFILE"

    cfg = None
    # O config tambem fornece as contas dos papeis quando --grants-to nao e informado (README §11.1).
    if args.config or (not owner or not prefix) or not args.grants_para:
        path_cfg = args.config
        if not path_cfg:
            candidate = os.path.join(_BASE_DIR, "instance", "config.ini")
            if os.path.isfile(candidate):
                path_cfg = candidate
            else:
                candidate_ex = os.path.join(_BASE_DIR, "instance", "config.ini.example")
                if os.path.isfile(candidate_ex):
                    path_cfg = candidate_ex

        if path_cfg and os.path.isfile(path_cfg):
            try:
                cfg = sss_config.load(path_cfg)
                if hasattr(cfg, "oracle"):
                    if not owner:
                        owner = getattr(cfg.oracle, "owner", "OPENRISOW")
                    if not prefix:
                        prefix = getattr(cfg.oracle, "table_prefix", "tbsss_")
                    if not args.lob_basicfile:
                        lob_storage = getattr(cfg.oracle, "lob_storage", "SECUREFILE")
            except Exception as exc:
                print("Aviso ao ler config.ini: %s" % exc, file=sys.stderr)

    owner = owner or "OPENRISOW"
    prefix = prefix or "tbsss_"

    try:
        sql_ident.validate_owner(owner)
        sql_ident.validate_prefix(prefix)
        sql_ident.validate_registry(prefix)
    except Exception as exc:
        print("Erro de validacao em identificadores Oracle: %s" % exc, file=sys.stderr)
        return 2

    roles_grants = {}
    if args.grants_para:
        for p in args.grants_para.split(","):
            p = p.strip()
            if not p:
                continue
            if "=" not in p:
                print("Formato invalido em --grants-to: use papel=usuario", file=sys.stderr)
                return 2
            role, usr = p.split("=", 1)
            roles_grants[role.strip().lower()] = usr.strip()
    elif cfg is not None:
        # web e agente usam [oracle] user (cada no le o seu config.ini); purge, [retention] purge_user.
        # A conta do monitor fica no secrets.cfg: so por --grants-to.
        usr_app = getattr(getattr(cfg, "oracle", None), "user", None)
        roles_grants = {
            "web": usr_app,
            "agent": usr_app,
            "purge": getattr(getattr(cfg, "retention", None), "purge_user", None),
        }
    try:
        ddl_builder.build_grants_by_role(owner, prefix, roles_grants)
    except ValueError as exc:
        print("Erro nos GRANTs por papel: %s" % exc, file=sys.stderr)
        return 2

    # 2. Geracao dos scripts
    script_deploy = ddl_builder.build_full_deploy_script(
        owner=owner,
        prefix=prefix,
        lob_storage=lob_storage,
        admin_login=args.admin_login,
        admin_name=args.admin_nome,
        admin_password_hash=args.admin_senha_hash,
        user_roles=roles_grants,
    )

    script_rollback = ddl_builder.build_rollback_script(
        owner=owner,
        prefix=prefix,
    )

    script_validate = ddl_builder.build_validation_script(owner=owner, prefix=prefix)

    script_grants = ""
    if args.grants_para:
        grants = ddl_builder.build_grants_by_role(owner, prefix, roles_grants)
        script_grants = "\n".join([
            "-- ==============================================================================",
            "-- Script Scheduling Service (SSS) - Grants por Papel Oracle 11gR2+",
            "-- Owner: {}".format(owner),
            "-- Prefixo: {}".format(prefix),
            "-- ==============================================================================",
            "SET DEFINE OFF;",
            "",
        ] + grants + ["", "PROMPT Grants aplicados com sucesso.", ""])

    # 3. Saida stdout se solicitada
    if args.stdout == "deploy":
        print(script_deploy)
        return 0
    elif args.stdout == "rollback":
        print(script_rollback)
        return 0
    elif args.stdout == "validate":
        print(script_validate)
        return 0
    elif args.stdout == "grants":
        print(script_grants)
        return 0

    # 4. Gravacao dos arquivos
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    file_deploy = os.path.join(out_dir, "01_deploy_sss.sql")
    file_rollback = os.path.join(out_dir, "02_rollback_sss.sql")
    file_validate = os.path.join(out_dir, "99_validate_deploy.sql")

    with open(file_deploy, "w", encoding="utf-8") as f:
        f.write(script_deploy)

    with open(file_rollback, "w", encoding="utf-8") as f:
        f.write(script_rollback)

    with open(file_validate, "w", encoding="utf-8") as f:
        f.write(script_validate)

    print("Scripts SQL gerados com sucesso:")
    print("  - Implantacao : {}".format(file_deploy))
    print("  - Rollback    : {}".format(file_rollback))
    print("  - Validacao   : {}".format(file_validate))

    if script_grants:
        file_grants = os.path.join(out_dir, "03_grants_sss.sql")
        with open(file_grants, "w", encoding="utf-8") as f:
            f.write(script_grants)
        print("  - Grants      : {}".format(file_grants))

    return 0


if __name__ == "__main__":
    sys.exit(main())
