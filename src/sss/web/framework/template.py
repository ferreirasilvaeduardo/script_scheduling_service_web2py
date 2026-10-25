# -*- coding: utf-8 -*-
"""Motor de templates das views (CR-021d2, D2), compativel com a sintaxe do web2py.

Gera o MESMO codigo Python que o parser do web2py (yatl, licenca BSD) a partir do mesmo arquivo,
com uma implementacao propria das mesmas regras: texto vira ``response.write(<repr>,
escape=False)``, ``{{=x}}`` vira ``response.write(x)``, codigo entra linha a linha e e reindentado
(':' abre, 'pass' fecha, 'elif'/'else'/'except'/'finally' voltam e reabrem,
'return'/'continue'/'break'/'raise' voltam na linha seguinte). A paridade e conferida em
test_web_template.py nas views reais.

Unica excecao a proibicao de exec do projeto (AGENTS §2.1): so codigo gerado de arquivos dentro
de ``templates/`` (caminho real conferido), com ``include``/``extend`` so por nome literal (o yatl
fazia eval da expressao; aqui expressao e recusada). ``block``, ``super`` e ``end`` nao sao usados
e sao recusados.
"""
import ast
import os
import re
import threading
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

WRITER = "response.write"

_RE_TAG = re.compile(r"(\{\{.*?\}\})", re.DOTALL)
_RE_MULTILINE = re.compile(r'(""".*?""")|(\'\'\'.*?\'\'\')', re.DOTALL)
_RE_BLOCK = re.compile(r"^(elif |else:|except:|except |finally:).*$", re.DOTALL)
_RE_UNBLOCK = re.compile(r"^(return|continue|break|raise)( .*)?$", re.DOTALL)
_RE_PASS = re.compile(r"^pass( .*)?$", re.DOTALL)
_RE_VIEW_NAME = re.compile(r"[a-z0-9_]+(?:/[a-z0-9_]+)*\.(?:html|load)")
_UNSUPPORTED = ("block", "end", "super")


class TemplateError(Exception):
    """View que nao pode ser compilada (arquivo e motivo na mensagem)."""


# Lugar do ``{{include}}`` vazio de ``owner``, preenchido pelo template que estende este.
_Slot = NamedTuple("_Slot", [("owner", str)])


# Fragmento de codigo, lugar de include vazio ou nos de um arquivo incluido.
_Node = Union[str, _Slot, list]


class _Fragment(str):
    """Fragmento de codigo com a marca de antes ou depois do ``{{extend}}``."""

    pre_extend = True


def _fragment(code: str, pre_extend: bool) -> _Fragment:
    item = _Fragment(code)
    item.pre_extend = pre_extend
    return item


class _Loader:
    """Leitura das views, sempre dentro da pasta (caminho real) e so por nome literal."""

    def __init__(self, views_dir: str) -> None:
        self.root = os.path.realpath(views_dir)
        self.dependencies: List[str] = []

    def path(self, name: str) -> str:
        """Caminho real de uma view pelo nome; fora de templates/ ou fora do formato e erro."""
        if not _RE_VIEW_NAME.fullmatch(name):
            raise TemplateError(f"nome de view fora do formato: {name!r}")
        real = os.path.realpath(os.path.join(self.root, *name.split("/")))
        if os.path.commonpath([self.root, real]) != self.root or not os.path.isfile(real):
            raise TemplateError(f"view inexistente ou fora de templates/: {name!r}")
        return real

    def read(self, name: str) -> str:
        """Texto da view, registrando o arquivo como dependencia do cache."""
        path = self.path(name)
        self.dependencies.append(path)
        with open(path, encoding="utf-8") as handle:
            return handle.read()


def _literal_name(value: str, where: str) -> str:
    """Nome de ``include``/``extend``: so literal de texto, nunca expressao."""
    try:
        name = ast.literal_eval(value.strip())
    except (ValueError, SyntaxError) as exc:
        raise TemplateError(f"{where}: include/extend aceita so nome literal: {value!r}") from exc
    if not isinstance(name, str):
        raise TemplateError(f"{where}: include/extend aceita so nome literal: {value!r}")
    return name


def _code_lines(line: str) -> str:
    """Bloco de codigo: cada linha sem a indentacao; linha com '=' vira escrita (como no yatl)."""
    tokens = line.split("\n")
    continuation = False
    for index, token in enumerate(tokens):
        token = tokens[index] = token.strip()
        if token.startswith("="):
            if token.endswith("\\"):
                continuation = True
                tokens[index] = f"\n{WRITER}({token[1:].strip()}"
            else:
                tokens[index] = f"\n{WRITER}({token[1:].strip()})"
        elif continuation:
            tokens[index] += ")"
            continuation = False
    return "\n" + "\n".join(tokens)


def _tag_node(line: str, name: str, loader: _Loader, pre_extend: bool) -> Optional[_Node]:
    """No de uma tag ``{{...}}`` ja sem os delimitadores (None para ``extend``, tratado fora)."""
    line = _RE_MULTILINE.sub(lambda m: m.group(0).replace("\n", "\\n"), line)
    if line.startswith("="):
        return _fragment(f"\n{WRITER}({line[1:].strip()})", pre_extend)
    word, _sep, value = line.partition(" ")
    if word in _UNSUPPORTED:
        raise TemplateError(f"{name}: '{word}' nao e suportado")
    if word == "include":
        if not value:
            return _Slot(name)
        return _parse(loader.read(_literal_name(value, name)), value, loader)
    if word == "extend":
        return None
    return _fragment(_code_lines(line), pre_extend)


def _parse(text: str, name: str, loader: _Loader) -> List[_Node]:
    """Nos de codigo de um template, ja com ``include`` e ``extend`` resolvidos."""
    nodes: List[_Node] = []
    extend: Optional[str] = None
    pre_extend = True
    for index, piece in enumerate(_RE_TAG.split(text)):
        if not piece:
            continue
        if index % 2 == 0:
            nodes.append(_fragment(f"\n{WRITER}({piece!r}, escape=False)", pre_extend))
            continue
        line = piece[2:-2].strip()
        if not line:
            continue
        if line.split(" ", 1)[0] == "extend":
            extend, pre_extend = line.partition(" ")[2], False
            continue
        nodes.append(_tag_node(line, name, loader, pre_extend))
    return nodes if extend is None else _extend(nodes, extend, name, loader)


def _extend(nodes: List[_Node], value: str, name: str, loader: _Loader) -> List[_Node]:
    """O pai recebe, no seu ``{{include}}``, o que veio depois do extend; o que veio antes vai
    para o inicio (como no yatl)."""
    parent = _parse(loader.read(_literal_name(value, name)), value, loader)
    before = [n for n in nodes if isinstance(n, _Fragment) and n.pre_extend]
    after = [n for n in nodes if not (isinstance(n, _Fragment) and n.pre_extend)]
    return before + _fill(parent, value, after)


def _fill(nodes: List[_Node], owner: str, body: List[_Node]) -> List[_Node]:
    """Troca o lugar ``{{include}}`` de ``owner`` (em qualquer nivel) por ``body``."""
    result: List[_Node] = []
    for node in nodes:
        if isinstance(node, _Slot) and node.owner == owner:
            result.append(body)
        elif isinstance(node, list):
            result.append(_fill(node, owner, body))
        else:
            result.append(node)
    return result


def _flatten(nodes: List[_Node]) -> str:
    """Codigo dos nos na ordem; lugar de include que ninguem preencheu fica vazio."""
    return "".join(_flatten(n) if isinstance(n, list) else ("" if isinstance(n, _Slot) else n)
                   for n in nodes)


def reindent(text: str, name: str = "view") -> str:
    """Reindenta o codigo gerado pelas regras do yatl (a indentacao do autor e ignorada)."""
    lines: List[str] = []
    credit = 0
    level = 0
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if _RE_BLOCK.match(line):
            level = level + credit - 1
        level = max(level, 0)
        lines.append(" " * (4 * level) + line)
        credit = 0
        if _RE_PASS.match(line):
            level -= 1
        if _RE_UNBLOCK.match(line):
            credit = 1
            level -= 1
        if line.endswith(":") and not line.startswith("#"):
            level += 1
    if level > 0:
        raise TemplateError(f"{name}: falta 'pass' na view")
    if level < 0:
        raise TemplateError(f"{name}: 'pass' demais na view")
    return "\n".join(lines)


def generate(text: str, name: str, views_dir: str) -> Tuple[str, List[str]]:
    """(codigo Python da view, arquivos de que ela depende)."""
    loader = _Loader(views_dir)
    code = reindent(_flatten(_parse(text, name, loader)), name)
    return code, loader.dependencies


# Um so metodo publico de proposito: o objeto e o cache das views compiladas.
class Templates:  # pylint: disable=too-few-public-methods
    """Views compiladas em cache, recompiladas quando um dos arquivos muda."""

    def __init__(self, views_dir: str) -> None:
        self.views_dir = views_dir
        self._loader = _Loader(views_dir)
        self._cache: Dict[str, Tuple[Tuple[Tuple[str, int], ...], Any]] = {}
        self._lock = threading.Lock()

    def _compiled(self, name: str) -> Any:
        path = self._loader.path(name)
        with self._lock:
            cached = self._cache.get(name)
            if cached is not None and all(os.stat(p).st_mtime_ns == m for p, m in cached[0]):
                return cached[1]
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            code, dependencies = generate(text, name, self.views_dir)
            try:
                compiled = compile(code, f"templates/{name}", "exec")
            except SyntaxError as exc:
                lines = code.split("\n")
                inside = bool(exc.lineno) and exc.lineno <= len(lines)
                text = lines[exc.lineno - 1].strip() if inside else ""
                raise TemplateError(f"{name}: erro de sintaxe no codigo gerado ({exc.msg}), linha "
                                    f"{exc.lineno}: {text}") from exc
            stamps = tuple((p, os.stat(p).st_mtime_ns) for p in [path] + dependencies)
            self._cache[name] = (stamps, compiled)
            return compiled

    def render(self, name: str, context: Dict[str, Any]) -> str:
        """HTML da view ``name`` com ``context`` (que traz o ``response`` com ``write``)."""
        compiled = self._compiled(name)
        response = context["response"]
        namespace = dict(context)
        # Unico exec do projeto (D2): codigo gerado so de arquivos de templates/, nunca de dado.
        exec(compiled, namespace)  # pylint: disable=exec-used
        return response.take_view_output()
