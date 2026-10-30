# -*- coding: utf-8 -*-
"""Verificador de ambiente e pre-requisitos do SSS.

CLI de verificacao de ambiente sem efeitos colaterais (somente leitura).
Confere os arquivos da aplicacao e sonda o banco do processo (--name ou --config) com a conta e os segredos
do papel dele (CR-033, D6: a sondagem sempre roda; antes, so com SSS_TEST_ORACLE=1). Sem processo, sai com 2.
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


def _agent_checks(cfg):
    """Linhas do agente: locale dos scripts (C.UTF-8 ou o substituto) e python/python3 do PATH."""
    from sss.platform import os_platform
    rows = []
    wanted = cfg.agent.child_locale
    chosen = os_platform.pick_child_locale(wanted)
    if not chosen:
        rows.append(("Locale dos scripts", "FALHA", "%s nao consta em locale -a e nao ha outro UTF-8" % wanted))
    elif chosen != wanted:
        rows.append(("Locale dos scripts", "AVISO", "%s nao consta em locale -a: os scripts usam %s" % (wanted, chosen)))
    else:
        rows.append(("Locale dos scripts", "OK", chosen))
    found = os_platform.interpreter_versions()
    detail = "; ".join("%s -> %s" % (name, "%s (%s)" % (path, version or "versao desconhecida") if path
                                     else "nao encontrado") for name, path, version in found)
    python2 = [version for name, _path, version in found
               if name == "python" and version and version.startswith("2.")]
    if python2:
        rows.append(("Interpretadores", "AVISO",
                     detail + "; python e o Python %s: cadastre scripts Python 3 como python3" % python2[0]))
    else:
        rows.append(("Interpretadores", "OK", detail))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verificador de ambiente do SSS")
    parser.add_argument("--config", default=None, help="config.ini (ou --name)")
    parser.add_argument("--name", default=None, help="processo: instance/<nome>/config.ini (CR-029)")
    args = parser.parse_args(argv)
    from sss.config import sss_config
    try:
        config_file = sss_config.config_path(args.config, args.name)
    except sss_config.ConfigError as exc:
        # README §12.1: sem processo (ou nome invalido), codigo 2 com a lista do instance/, como o run_web
        print("Configuracao invalida: %s" % exc, file=sys.stderr)
        sys.exit(2)
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
    cfg = None
    try:
        cfg = sss_config.get_config(path=config_file)
        mode = getattr(cfg.oracle, "driver_mode", "auto")
        chain_desc = "auto (Thin -> Thick -> cx_Oracle)" if mode == "auto" else mode

        status = "OK"
        # Sondagem real do driver e da conexao (CR-033, D6), com os segredos do papel do proprio processo
        # (CR-031: o agente nao tem [web]).
        try:
            from sss.persistence import db_conn
            role = "agent" if getattr(cfg.app, "role", "all") == "agent" else "web"
            secrets_value = sss_config.get_secrets(role=role)
            sel = db_conn.select_driver(cfg, secrets_value)
            sel_desc = "modo=%s (servidor=%s driver=%s cliente=%s)" % (
                sel.candidate, sel.server_version or "-", sel.driver_version or "-", sel.client_version or "-"
            )
        except Exception as and_probe:  # a falha vira a linha FALHA da tabela (sem valor de segredo)
            sel_desc = "sondagem falhou: %s" % and_probe
            status = "FALHA"

        detail_driver = chain_desc
        if sel_desc:
            detail_driver = "%s | Selecionado: %s" % (chain_desc, sel_desc)
        results.append(("Driver Oracle (driver_mode)", status, detail_driver))
        # Cliente fora do 19 recomendado: AVISO, como no processo (decisao 10 A), sem reprovar o ambiente.
        if status == "OK" and sel.client_version:
            parts = tuple(int(p) for p in str(sel.client_version).split(".") if p.isdigit())
            warning = db_conn.client_version_warning(parts)
            if warning:
                results.append(("Cliente Oracle", "AVISO", warning))
        # Item 6: orcamento da abertura da conexao (README §2.3, CR-008 R-17): acima do call_timeout_s e AVISO,
        # com o WARN CONEXAO_ACIMA_DO_PRAZO, sem reprovar o ambiente.
        from sss.persistence import db_conn
        call_s = sss_config.call_timeout_s(cfg.oracle.call_timeout_ms)
        budget = db_conn.connection_budget_s(cfg.oracle.dsn, call_s)
        results.append(("Orcamento da conexao", "OK" if budget <= call_s else "AVISO",
                        "%ds (call_timeout_s %ds)%s" % (budget, call_s,
                                                        "" if budget <= call_s else ": CONEXAO_ACIMA_DO_PRAZO")))
    except Exception as exc:
        results.append(("Driver Oracle (driver_mode)", "FALHA", "Erro ao carregar configuracao: %s" % exc))

    # Itens 7 e 8, so nos agentes (com a configuracao que o item 5 carregou): o que a subida do agente confere e
    # avisa (locale dos scripts e interpretadores), para o servidor se mostrar compativel antes de subir.
    if cfg is not None and getattr(cfg.app, "role", "all") == "agent":
        results.extend(_agent_checks(cfg))

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
        if status not in ("OK", "AVISO"):
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
