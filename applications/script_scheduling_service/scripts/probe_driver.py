# -*- coding: utf-8 -*-
"""Sondador isolado de driver Oracle (Thin, Thick, cx_Oracle).

Executado em subprocesso isolado (sys.executable -I) para testar uma unica combinacao
de driver sem contaminar o processo principal e sem vazar credenciais (CR-002, AGENTS §2.2).
"""
import argparse
import json
import os
import re
import sys

# Ajusta sys.path para carregar modulos do SSS sem depender do ambiente global
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.dirname(_scripts_dir)
_modules_dir = os.path.join(_app_dir, "modules")
for _p in (_app_dir, _modules_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import sss_config  # noqa: E402
import plataforma  # noqa: E402


_RE_CODIGO_ERRO = re.compile(r"\b([A-Z]{3,4}-\d{4,5})\b")

_ERROS_AUTENTICACAO = {
    "ORA-01017", "ORA-28000", "ORA-28001", "ORA-28002",
    "ORA-28003", "ORA-28007", "ORA-28014",
}

_ERROS_REDE = {
    "ORA-12154", "ORA-12170", "ORA-12514", "ORA-12541", "ORA-12543",
    "ORA-12545", "ORA-12560", "ORA-03113", "ORA-03114", "ORA-03156",
    "DPY-4011", "DPY-4024", "DPI-1067", "DPY-6005",
}


def _classificar_erro(exc):
    """Extrai codigo e categoria do erro sem expor dados sensiveis."""
    if isinstance(exc, ImportError):
        return "IMPORT_ERROR", "BIBLIOTECA"

    msg = str(exc)
    match = _RE_CODIGO_ERRO.search(msg)
    codigo = match.group(1) if match else None

    if codigo in _ERROS_AUTENTICACAO or "logon denied" in msg.lower() or "account is locked" in msg.lower():
        return codigo or "AUTH_ERROR", "AUTENTICACAO"
    if codigo == "DPY-3010" or "in thin mode" in msg.lower():
        return codigo or "DPY-3010", "INCOMPATIVEL"
    if codigo == "DPI-1047" or "oracle client library" in msg.lower():
        return codigo or "DPI-1047", "BIBLIOTECA"
    if codigo in _ERROS_REDE or "timed out" in msg.lower() or "timeout" in msg.lower():
        return codigo or "NET_ERROR", "REDE"
    return codigo or "ERR_OUTRO", "OUTRO"


def _formatar_versao_cliente(val):
    if val is None:
        return None
    if isinstance(val, (tuple, list)):
        return ".".join(str(x) for x in val)
    return str(val)


def sondar(candidato, cfg, senha, usuario=None):
    """Executa a tentativa de conexao para o candidato especificado, com a conta do papel (usuario) ou, sem ela,
    [oracle] user."""
    usuario = usuario or cfg.oracle.user
    driver = None
    versao_servidor = None
    versao_driver = None
    versao_cliente = None

    try:
        if candidato == "thin":
            import oracledb
            driver = oracledb
            timeout_s = float(cfg.oracle.call_timeout_ms) / 1000.0 if cfg.oracle.call_timeout_ms else 30.0
            conn = oracledb.connect(
                user=usuario,
                password=senha,
                dsn=cfg.oracle.dsn,
                tcp_connect_timeout=timeout_s,
            )
        elif candidato == "thick":
            import oracledb
            driver = oracledb
            lib_dir = plataforma.obter_lib_dir_oracle(cfg)
            try:
                if lib_dir:
                    oracledb.init_oracle_client(lib_dir=lib_dir)
                else:
                    oracledb.init_oracle_client()
            except Exception as e_init:
                if "already been initialized" not in str(e_init):
                    raise
            conn = oracledb.connect(
                user=usuario,
                password=senha,
                dsn=cfg.oracle.dsn,
            )
        elif candidato == "cx_oracle":
            import cx_Oracle
            driver = cx_Oracle
            lib_dir = plataforma.obter_lib_dir_oracle(cfg)
            try:
                if lib_dir:
                    cx_Oracle.init_oracle_client(lib_dir=lib_dir)
            except Exception as e_init:
                if "already been initialized" not in str(e_init):
                    pass
            conn = cx_Oracle.connect(
                user=usuario,
                password=senha,
                dsn=cfg.oracle.dsn,
            )
        else:
            return {
                "candidato": candidato,
                "ok": False,
                "versao_servidor": None,
                "versao_driver": None,
                "versao_cliente": None,
                "codigo_erro": "CANDIDATO_INVALIDO",
                "category": "OUTRO",
            }

        cur = conn.cursor()
        cur.execute("SELECT SYSDATE FROM DUAL")
        cur.fetchone()

        versao_servidor = str(getattr(conn, "version", None) or "")
        versao_driver = str(getattr(driver, "__version__", None) or "")
        if candidato in ("thick", "cx_oracle") and hasattr(driver, "clientversion"):
            try:
                versao_cliente = _formatar_versao_cliente(driver.clientversion())
            except Exception:
                versao_cliente = None

        cur.close()
        conn.close()

        return {
            "candidato": candidato,
            "ok": True,
            "versao_servidor": versao_servidor,
            "versao_driver": versao_driver,
            "versao_cliente": versao_cliente,
            "codigo_erro": None,
            "category": None,
        }

    except Exception as exc:
        codigo, categoria = _classificar_erro(exc)
        return {
            "candidato": candidato,
            "ok": False,
            "versao_servidor": None,
            "versao_driver": getattr(driver, "__version__", None) if driver else None,
            "versao_cliente": None,
            "codigo_erro": codigo,
            "category": categoria,
        }


def main():
    parser = argparse.ArgumentParser(description="Sondador isolado de driver Oracle")
    parser.add_argument("candidato", choices=["thin", "thick", "cx_oracle"])
    parser.add_argument("--config", dest="config", default=None)
    parser.add_argument("--user", dest="usuario", default=None, help="conta do papel (padrao: [oracle] user)")
    args = parser.parse_args()

    # Senha estritamente pela entrada padrao (stdin)
    senha = sys.stdin.read()
    if senha.endswith("\r\n"):
        senha = senha[:-2]
    elif senha.endswith("\n") or senha.endswith("\r"):
        senha = senha[:-1]

    if args.config:
        cfg = sss_config.carregar(args.config)
    else:
        cfg = sss_config.obter_config()

    resultado = sondar(args.candidato, cfg, senha, usuario=args.usuario)
    sys.stdout.write(json.dumps(resultado) + "\n")
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    main()
