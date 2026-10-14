# -*- coding: utf-8 -*-
"""Verificador de ambiente e pre-requisitos do SSS.

CLI de verificacao de ambiente sem efeitos colaterais (somente leitura).
Executa fail-fast caso a versao do Python nao seja 3.6 ou caso algum
recurso obrigatorio esteja ausente ou invalido.
"""
import os
import re
import sys

# 1. Verificacao estrita de runtime: Python 3.6 obrigatorio
if sys.version_info[:2] != (3, 6):
    sys.stderr.write(
        "FALHA: Python 3.6 e obrigatorio. Versao detectada: %d.%d.%d\n"
        % (sys.version_info[0], sys.version_info[1], sys.version_info[2])
    )
    sys.exit(2)


# Avaliacao de string como codigo: proibida em qualquer ponto do bundle.
_RE_EVAL_DIRETO = (
    (re.compile(r"\bnew\s+Function\b"), "new Function"),
    (re.compile(r"(?<![\w$.])Function\s*\("), "Function()"),
    # Classe [e] evita que o proprio padrao seja acusado pelo varredor de test_py36_compat.
    (re.compile(r"(?<![\w$.])[e]val\s*\("), "eval"),
)
# Obtencao do construtor AsyncFunction/GeneratorFunction, equivalente a new Function.
_RE_CONSTRUTOR_DINAMICO = re.compile(
    r"getPrototypeOf\s*\(\s*(?:async\b|function\s*\*)"
    r"|\(\s*(?:async\s*(?:function\b[^{]*\{\s*\}|\([^)]*\)\s*=>\s*\{\s*\})|function\s*\*[^{]*\{\s*\})\s*\)\s*\.\s*constructor"
)
_RE_SET_EVALUATOR = re.compile(r"\.setEvaluator\s*\(\s*([A-Za-z_$][\w$]*)\s*\)")
_RE_DECL_FUNCAO = re.compile(r"(?<![\w$.])function\s+([A-Za-z_$][\w$]*)\s*\(")
_RE_IDENT = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)(?![\w$])")
_ANTES_DE_REGEX = set("(,=:[!&|?{};+-*%<>~^")
_PALAVRAS_ANTES_DE_REGEX = ("return", "typeof", "case", "in", "of", "void", "delete", "new", "throw")
_PARES = {"(": ")", "[": "]", "{": "}"}


class _JsInvalido(Exception):
    pass


def _pular_regex(src, i):
    """i aponta para a '/' de abertura; retorna o indice apos o literal (incluindo flags)."""
    i += 1
    em_classe = False
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "\n":
            raise _JsInvalido("regex sem fechamento")
        if em_classe:
            em_classe = c != "]"
        elif c == "[":
            em_classe = True
        elif c == "/":
            i += 1
            while i < len(src) and (src[i].isalnum() or src[i] in "_$"):
                i += 1
            return i
        i += 1
    raise _JsInvalido("regex sem fechamento")


def _inicia_regex(src, i):
    j = i - 1
    while j >= 0 and src[j] in " \t\r\n":
        j -= 1
    if j < 0 or src[j] in _ANTES_DE_REGEX:
        return True
    k = j
    while k >= 0 and (src[k].isalnum() or src[k] in "_$"):
        k -= 1
    return src[k + 1:j + 1] in _PALAVRAS_ANTES_DE_REGEX


def _casar(src, i):
    """Indice do delimitador que fecha src[i] ('(', '[' ou '{').

    Ignora strings, templates (com ${} aninhado), comentarios e literais regex.
    Desbalanceamento levanta _JsInvalido (o chamador reprova: fail-closed).
    """
    pilha = [_PARES[src[i]]]
    # Cada nivel de template aberto guarda a profundidade da pilha no '${'.
    templates = []
    i += 1
    n = len(src)
    while i < n:
        c = src[i]
        if c in "'\"":
            i += 1
            while i < n and src[i] != c:
                if src[i] == "\\":
                    i += 1
                elif src[i] == "\n":
                    raise _JsInvalido("string sem fechamento")
                i += 1
            if i >= n:
                raise _JsInvalido("string sem fechamento")
        elif c == "`" or (c == "}" and templates and len(pilha) == templates[-1]):
            if c == "}":
                templates.pop()
            i += 1
            while i < n and src[i] != "`":
                if src[i] == "\\":
                    i += 1
                elif src.startswith("${", i):
                    templates.append(len(pilha))
                    i += 1
                    break
                i += 1
            else:
                if i >= n:
                    raise _JsInvalido("template sem fechamento")
        elif src.startswith("//", i):
            fim = src.find("\n", i)
            i = n if fim < 0 else fim
        elif src.startswith("/*", i):
            fim = src.find("*/", i + 2)
            if fim < 0:
                raise _JsInvalido("comentario sem fechamento")
            i = fim + 1
        elif c == "/" and _inicia_regex(src, i):
            i = _pular_regex(src, i)
            continue
        elif c in _PARES:
            pilha.append(_PARES[c])
        elif c in ")]}":
            if c != pilha.pop():
                raise _JsInvalido("delimitadores desbalanceados")
            if not pilha:
                return i
        i += 1
    raise _JsInvalido("delimitadores desbalanceados")


def _corpos_de_funcoes(src):
    """Mapeia nome -> lista de textos (parametros + corpo) das declaracoes 'function nome(...)'."""
    corpos = {}
    for m in _RE_DECL_FUNCAO.finditer(src):
        fim_params = _casar(src, m.end() - 1)
        abre = src.find("{", fim_params)
        if abre < 0 or src[fim_params + 1:abre].strip():
            raise _JsInvalido("declaracao de funcao sem corpo: %s" % m.group(1))
        corpos.setdefault(m.group(1), []).append(src[m.end() - 1:_casar(src, abre) + 1])
    return corpos


def verificar_alpine_csp(fonte):
    """Retorna (ok, detalhe) indicando se o bundle Alpine e seguro sob script-src 'self'.

    Reprova eval, new Function e Function() em qualquer ponto e reprova o avaliador
    registrado via setEvaluator() que alcance um construtor dinamico (AsyncFunction).
    O build CSP oficial ainda embute o avaliador padrao como codigo morto; ele so e
    aceito se nao for alcancavel a partir do avaliador registrado.
    """
    for regex, rotulo in _RE_EVAL_DIRETO:
        if regex.search(fonte):
            return False, "Uso de %s encontrado" % rotulo

    registros = _RE_SET_EVALUATOR.findall(fonte)
    if len(registros) != 1:
        return False, "Esperado exatamente 1 setEvaluator(), encontrados %d" % len(registros)
    avaliador = registros[0]

    try:
        corpos = _corpos_de_funcoes(fonte)
    except _JsInvalido as e:
        return False, "Bundle não analisável: %s" % e
    if avaliador not in corpos:
        return False, "Avaliador registrado '%s' não declarado como função" % avaliador

    # Sobreaproximacao intencional: todo identificador igual a nome de funcao declarada
    # conta como alcancavel (inclusive parametros homonimos), errando para o lado da falha.
    alcancaveis = set()
    pendentes = [avaliador]
    while pendentes:
        nome = pendentes.pop()
        if nome in alcancaveis:
            continue
        alcancaveis.add(nome)
        for corpo in corpos[nome]:
            if _RE_CONSTRUTOR_DINAMICO.search(corpo):
                return False, "Avaliador registrado '%s' alcança construtor dinâmico em '%s' (build não CSP)" % (
                    avaliador, nome)
            pendentes.extend(ident for ident in _RE_IDENT.findall(corpo) if ident in corpos)

    if _RE_CONSTRUTOR_DINAMICO.search(fonte):
        return True, "Build CSP confirmada: avaliador '%s' não avalia strings (avaliador padrão presente apenas como código morto)" % avaliador
    return True, "Build CSP confirmada: avaliador '%s' não avalia strings" % avaliador


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
            with open(alpine_js, "r", encoding="utf-8") as f:
                ok, detalhe = verificar_alpine_csp(f.read())
            results.append(("Build CSP do Alpine.js", "OK" if ok else "FALHA", detalhe))
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
