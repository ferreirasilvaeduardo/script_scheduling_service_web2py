# -*- coding: utf-8 -*-
"""Verificador de ambiente e pre-requisitos do SSS.

CLI de verificacao de ambiente sem efeitos colaterais (somente leitura).
Executa fail-fast caso a versao do Python seja anterior a 3.6.0 ou caso algum
recurso obrigatorio esteja ausente ou invalido (AGENTS §2.1: sintaxe 3.6, execucao em >= 3.6.0).
"""
import argparse
import os
import sys

# 1. Verificacao de runtime: Python 3.6.0 ou superior
if sys.version_info[:3] < (3, 6, 0):
    sys.stderr.write(
        "FALHA: Python 3.6.0 ou superior e obrigatorio. Versao detectada: %d.%d.%d\n"
        % (sys.version_info[0], sys.version_info[1], sys.version_info[2])
    )
    sys.exit(2)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verificador de ambiente do SSS")
    parser.add_argument("--config", default=None, help="config.ini (ou --name)")
    parser.add_argument("--name", default=None, help="processo: instance/<nome>/config.ini (CR-029)")
    args = parser.parse_args(argv)
    # src/sss/cli/ -> raiz da aplicacao (CR-022b8); o comando continua sendo scripts/<nome>.py
    app_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
    # Servidor web proprio (CR-021e); o web2py saiu do repositorio no CR-021f.
    web_server = os.path.join(app_dir, "scripts", "run_web.py")
    bootstrap_css = os.path.join(app_dir, "src", "sss", "web", "static", "bootstrap", "bootstrap.min.css")
    bootstrap_js = os.path.join(app_dir, "src", "sss", "web", "static", "bootstrap", "bootstrap.bundle.min.js")

    results = []

    # Item 1: Versao do Python
    results.append((
        "Versao do Python (>= 3.6.0)",
        "OK",
        "%d.%d.%d" % sys.version_info[:3],
    ))

    # Item 2: servidor web (scripts/run_web.py)
    if os.path.isfile(web_server):
        results.append(("scripts/run_web.py", "OK", "Presente"))
    else:
        results.append(("scripts/run_web.py", "FALHA", "Arquivo nao encontrado"))

    # Item 3: bootstrap.min.css
    if os.path.isfile(bootstrap_css) and os.path.getsize(bootstrap_css) > 0:
        results.append(("bootstrap.min.css", "OK", "%d bytes" % os.path.getsize(bootstrap_css)))
    else:
        results.append(("bootstrap.min.css", "FALHA", "Arquivo inexistente ou vazio"))

    # Item 4: bootstrap.bundle.min.js
    if os.path.isfile(bootstrap_js) and os.path.getsize(bootstrap_js) > 0:
        results.append(("bootstrap.bundle.min.js", "OK", "%d bytes" % os.path.getsize(bootstrap_js)))
    else:
        results.append(("bootstrap.bundle.min.js", "FALHA", "Arquivo inexistente ou vazio"))

    # Item 5: Driver Oracle (driver_mode e cadeia adaptativa)
    try:
        from sss.config import sss_config
        cfg = sss_config.get_config(path=sss_config.config_path(args.config, args.name))
        mode = getattr(cfg.oracle, "driver_mode", "auto")
        chain_desc = "auto (Thin -> Thick -> cx_Oracle)" if mode == "auto" else mode

        sel_desc = None
        status = "OK"
        # Sondagem real do driver so com os testes Oracle ligados (SSS_TEST_ORACLE=1, README §2.5).
        if os.environ.get("SSS_TEST_ORACLE") == "1":
            try:
                from sss.persistence import db_conn
                # CR-031: os segredos do papel do proprio processo (o agente nao tem [web]).
                role = "agent" if getattr(cfg.app, "role", "all") == "agent" else "web"
                secrets_value = sss_config.get_secrets(role=role)
                sel = db_conn.select_driver(cfg, secrets_value)
                sel_desc = "modo=%s (servidor=%s driver=%s cliente=%s)" % (
                    sel.candidate, sel.server_version or "-", sel.driver_version or "-", sel.client_version or "-"
                )
            except Exception as and_probe:
                sel_desc = "sondagem falhou: %s" % and_probe
                status = "FALHA"

        detail_driver = chain_desc
        if sel_desc:
            detail_driver = "%s | Selecionado: %s" % (chain_desc, sel_desc)
        results.append(("Driver Oracle (driver_mode)", status, detail_driver))
    except Exception as exc:
        results.append(("Driver Oracle (driver_mode)", "FALHA", "Erro ao carregar configuracao: %s" % exc))

    # Renderizacao da tabela OK/FALHA
    col1_w = max([len(r[0]) for r in results] + [4]) + 2
    col2_w = 8
    col3_w = max([len(r[2]) for r in results] + [7]) + 2

    sep = "+%s+%s+%s+" % ("-" * col1_w, "-" * col2_w, "-" * col3_w)
    header = "| %-*s | %-*s | %-*s |" % (
        col1_w - 2, "Item",
        col2_w - 2, "Status",
        col3_w - 2, "Detalhe",
    )

    print(sep)
    print(header)
    print(sep)
    all_ok = True
    for item, status, detail in results:
        if status != "OK":
            all_ok = False
        print("| %-*s | %-*s | %-*s |" % (
            col1_w - 2, item,
            col2_w - 2, status,
            col3_w - 2, detail,
        ))
    print(sep)

    if all_ok:
        print("\nResultado: Todos os pre-requisitos foram atendidos com sucesso.")
        sys.exit(0)
    else:
        print("\nResultado: Um ou mais pre-requisitos falharam.")
        sys.exit(1)


if __name__ == "__main__":
    main()
