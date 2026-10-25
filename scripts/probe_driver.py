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
for _p in (_app_dir, _modules_dir, os.path.join(_app_dir, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sss.config import sss_config  # noqa: E402
import os_platform  # noqa: E402


_RE_ERROR_CODE = re.compile(r"\b([A-Z]{3,4}-\d{4,5})\b")

_AUTH_ERRORS = {
    "ORA-01017", "ORA-28000", "ORA-28001", "ORA-28002",
    "ORA-28003", "ORA-28007", "ORA-28014",
}

_NETWORK_ERRORS = {
    "ORA-12154", "ORA-12170", "ORA-12514", "ORA-12541", "ORA-12543",
    "ORA-12545", "ORA-12560", "ORA-03113", "ORA-03114", "ORA-03156",
    "DPY-4011", "DPY-4024", "DPI-1067", "DPY-6005",
}


def _classify_error(exc):
    """Extrai codigo e categoria do erro sem expor dados sensiveis."""
    if isinstance(exc, ImportError):
        return "IMPORT_ERROR", "LIBRARY"

    msg = str(exc)
    match = _RE_ERROR_CODE.search(msg)
    code = match.group(1) if match else None

    if code in _AUTH_ERRORS or "logon denied" in msg.lower() or "account is locked" in msg.lower():
        return code or "AUTH_ERROR", "AUTHENTICATION"
    if code == "DPY-3010" or "in thin mode" in msg.lower():
        return code or "DPY-3010", "INCOMPATIBLE"
    if code == "DPI-1047" or "oracle client library" in msg.lower():
        return code or "DPI-1047", "LIBRARY"
    if code in _NETWORK_ERRORS or "timed out" in msg.lower() or "timeout" in msg.lower():
        return code or "NET_ERROR", "NETWORK"
    return code or "ERR_OTHER", "OTHER"


def _format_client_version(val):
    if val is None:
        return None
    if isinstance(val, (tuple, list)):
        return ".".join(str(x) for x in val)
    return str(val)


def probe(candidate, cfg, password_value, user=None):
    """Executa a tentativa de conexao para o candidato especificado, com a conta do papel (usuario) ou, sem ela,
    [oracle] user."""
    user = user or cfg.oracle.user
    driver = None
    version_server = None
    version_driver = None
    version_client = None

    try:
        if candidate == "thin":
            import oracledb
            driver = oracledb
            timeout_s = float(cfg.oracle.call_timeout_ms) / 1000.0 if cfg.oracle.call_timeout_ms else 30.0
            conn = oracledb.connect(
                user=user,
                password=password_value,
                dsn=cfg.oracle.dsn,
                tcp_connect_timeout=timeout_s,
            )
        elif candidate == "thick":
            import oracledb
            driver = oracledb
            lib_dir = os_platform.get_oracle_lib_dir(cfg)
            try:
                if lib_dir:
                    oracledb.init_oracle_client(lib_dir=lib_dir)
                else:
                    oracledb.init_oracle_client()
            except Exception as and_init:
                if "already been initialized" not in str(and_init):
                    raise
            conn = oracledb.connect(
                user=user,
                password=password_value,
                dsn=cfg.oracle.dsn,
            )
        elif candidate == "cx_oracle":
            import cx_Oracle
            driver = cx_Oracle
            lib_dir = os_platform.get_oracle_lib_dir(cfg)
            try:
                if lib_dir:
                    cx_Oracle.init_oracle_client(lib_dir=lib_dir)
            except Exception as and_init:
                if "already been initialized" not in str(and_init):
                    pass
            conn = cx_Oracle.connect(
                user=user,
                password=password_value,
                dsn=cfg.oracle.dsn,
            )
        else:
            return {
                "candidate": candidate,
                "ok": False,
                "server_version": None,
                "driver_version": None,
                "client_version": None,
                "error_code": "INVALID_CANDIDATE",
                "category": "OTHER",
            }

        cur = conn.cursor()
        cur.execute("SELECT SYSDATE FROM DUAL")
        cur.fetchone()

        version_server = str(getattr(conn, "version", None) or "")
        version_driver = str(getattr(driver, "__version__", None) or "")
        if candidate in ("thick", "cx_oracle") and hasattr(driver, "clientversion"):
            try:
                version_client = _format_client_version(driver.clientversion())
            except Exception:
                version_client = None

        cur.close()
        conn.close()

        return {
            "candidate": candidate,
            "ok": True,
            "server_version": version_server,
            "driver_version": version_driver,
            "client_version": version_client,
            "error_code": None,
            "category": None,
        }

    except Exception as exc:
        code, category = _classify_error(exc)
        return {
            "candidate": candidate,
            "ok": False,
            "server_version": None,
            "driver_version": getattr(driver, "__version__", None) if driver else None,
            "client_version": None,
            "error_code": code,
            "category": category,
        }


def main():
    parser = argparse.ArgumentParser(description="Sondador isolado de driver Oracle")
    parser.add_argument("candidate", choices=["thin", "thick", "cx_oracle"])
    parser.add_argument("--config", dest="config", default=None)
    parser.add_argument("--user", dest="usuario", default=None, help="conta do papel (padrao: [oracle] user)")
    args = parser.parse_args()

    # Senha estritamente pela entrada padrao (stdin)
    password = sys.stdin.read()
    if password.endswith("\r\n"):
        password = password[:-2]
    elif password.endswith("\n") or password.endswith("\r"):
        password = password[:-1]

    if args.config:
        cfg = sss_config.load(args.config)
    else:
        cfg = sss_config.get_config()

    result = probe(args.candidate, cfg, password, user=args.usuario)
    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    main()
