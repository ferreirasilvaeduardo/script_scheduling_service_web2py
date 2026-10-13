# -*- coding: utf-8 -*-
"""Verificador de ambiente e pre-requisitos do SSS.

CLI de verificacao de ambiente sem efeitos colaterais (somente leitura).
Executa fail-fast caso a versao do Python nao seja 3.6 ou caso algum
recurso obrigatorio esteja ausente ou invalido.
"""
import os
import sys

# 1. Verificacao estrita de runtime: Python 3.6 obrigatorio
if sys.version_info[:2] != (3, 6):
    sys.stderr.write(
        "FALHA: Python 3.6 e obrigatorio. Versao detectada: %d.%d.%d\n"
        % (sys.version_info[0], sys.version_info[1], sys.version_info[2])
    )
    sys.exit(2)


def main():
    # Resolucao dinamica de caminhos a partir de __file__
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.dirname(scripts_dir)
    web2py_root = os.path.dirname(os.path.dirname(app_dir))

    web2py_file = os.path.join(web2py_root, "web2py.py")
    bootstrap_css = os.path.join(app_dir, "static", "bootstrap", "bootstrap.min.css")
    bootstrap_js = os.path.join(app_dir, "static", "bootstrap", "bootstrap.bundle.min.js")
    alpine_js = os.path.join(app_dir, "static", "js", "alpine.min.js")

    results = []

    # Item 1: Versao do Python
    results.append((
        "Versao do Python (3.6)",
        "OK",
        "%d.%d.%d" % sys.version_info[:3],
    ))

    # Item 2: web2py.py na raiz
    if os.path.isfile(web2py_file):
        results.append(("web2py.py na raiz", "OK", "Presente"))
    else:
        results.append(("web2py.py na raiz", "FALHA", "Arquivo nao encontrado na raiz do web2py"))

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

    # Item 5: alpine.min.js
    if os.path.isfile(alpine_js) and os.path.getsize(alpine_js) > 0:
        results.append(("alpine.min.js", "OK", "%d bytes" % os.path.getsize(alpine_js)))
    else:
        results.append(("alpine.min.js", "FALHA", "Arquivo inexistente ou vazio"))

    # Item 6: build CSP do Alpine.js
    if not os.path.isfile(alpine_js):
        results.append(("Build CSP do Alpine.js", "FALHA", "Arquivo alpine.min.js nao encontrado"))
    else:
        try:
            with open(alpine_js, "rb") as f:
                alpine_bytes = f.read()
            if b"new Function" in alpine_bytes:
                results.append(("Build CSP do Alpine.js", "FALHA", "Alpine não é a build CSP"))
            else:
                results.append(("Build CSP do Alpine.js", "OK", "Build CSP confirmada (sem 'new Function')"))
        except Exception as e:
            results.append(("Build CSP do Alpine.js", "FALHA", "Erro ao ler arquivo: %s" % str(e)))

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
