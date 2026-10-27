# -*- coding: utf-8 -*-
"""Pacote de implantacao (README §12.2; F9.1c; CR-005; CR-003 P10). Biblioteca padrao apenas.

Uso: python tools/package.py [--source <raiz do repositorio>] [--out-dir <pasta>]

Ferramenta de build (CR-022b2): fica em tools/, fora do pacote que ela mesma gera.

Gera <saida>/sss-<versao>.tar.gz (tudo sob sss-<versao>/, com um SHA256SUMS de cada arquivo) e <saida>/SHA256SUMS
com o hash do tar.gz. A versao e sss_config.SSS_VERSION. O tar e deterministico (ordem, dono, data e modos fixos).

Entram: os launchers de producao e o helper do bin/ e a aplicacao (APP_DIRS e APP_FILES da raiz, que e a propria
aplicacao desde o CR-022a) sem codigo de DEV, sem testes e sem pastas de runtime. Desde o CR-021f nao ha web2py: o servidor web e o scripts/run_web.py da propria aplicacao.
Falha (codigo 1, sem gravar nada) se o pacote tiver secrets.cfg real, *.pyc, __pycache__, controllers/dev.py,
o FAKE (src/sss/persistence/fake), /admin/, resto do web2py (gluon/, web2py.py, anyserver.py, routes.py ou pasta de runtime dele), link
simbolico ou credencial que nao seja o CHANGE_ME de um */secrets.cfg.example (instance/exemplos/). A mensagem cita o arquivo e a
linha, nunca o valor.
"""
import argparse
import gzip
import hashlib
import io
import os
import re
import sys
import tarfile

_TOOLS = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_TOOLS)
sys.path.insert(0, os.path.join(_APP_DIR, "src"))
# Rodando de dentro da copia limpa que vai empacotar, o import abaixo gravaria src/sss/config/__pycache__ nela
# e o proprio pacote seria recusado por bytecode (achado no ensaio do CR-021f3).
sys.dont_write_bytecode = True

from sss.config import sss_config  # noqa: E402

DEFAULT_ROOT = _APP_DIR  # CR-022a: a aplicacao e a raiz do repositorio
BIN = ("sss-web.sh", "sss-scheduler.sh", "sss-stop.sh", "sss-update.sh", "sss-keepalive.sh", "sss-helper")
# Da raiz so entram estas pastas e arquivos da aplicacao (lista de permissao, CR-022a): o resto da raiz
# (.git, Makefile, CLAUDE.md, input/, output/, logs/...) e da maquina de desenvolvimento.
APP_DIRS = ("docs", "instance", "scripts", "src")
APP_FILES = ("AGENTS.md", "README.md")
# Restos do web2py (CR-021f): na raiz, recusados; na aplicacao, as pastas de runtime que ele criava.
WEB2PY_ROOT_LEFTOVERS = ("gluon", "web2py.py", "anyserver.py", "routes.py", "applications")
WEB2PY_APP_DIRS = ("sessions", "errors", "cache", "databases", "uploads", "private", "cron",
                   "applications", "deposit", "site-packages", "scripts/applications",
                   "scripts/deposit", "scripts/site-packages")
# Relativos a aplicacao: nunca entram (codigo de DEV, configuracao local, dados e pastas de execucao).
EXCLUDE_APP = (
    "src/sss/web/controllers/dev.py", "src/sss/web/templates/dev", "dev", "src/sss/persistence/fake", "modules/repo_fake", "instance/config.ini", "instance/web.env",
    "log", "logs", "work", "exec", "dist", "scripts/logs",
) + WEB2PY_APP_DIRS
# Os testes ficam em tests/, fora da lista de permissao (CR-022b1); um test_*.py perdido em scripts/ tambem fica fora.
_RE_TEST = re.compile(r"^scripts/test_[^/]*\.py$")
_RE_CREDENTIAL = re.compile(r"^\s*(password|cookie_key)\s*[=:]\s*(.*?)\s*$", re.IGNORECASE)
_SECRETS_EXAMPLE = "instance/secrets.cfg.example"
_PLACEHOLDER = "CHANGE_ME"
MTIME = 1767225600  # 2026-01-01 00:00:00 UTC: tar reprodutivel


class PackageError(Exception):
    """Pacote recusado; problemas e a lista de motivos (sem valores de credencial)."""

    def __init__(self, problems):
        Exception.__init__(self, "pacote recusado: %d problema(s)" % len(problems))
        self.problems = problems


def _excluded_from_app(rel):
    if _RE_TEST.match(rel):
        return True
    if rel.startswith("instance/"):
        # CR-028: de instance/ so vao os exemplos; instance/<nome>/ (config e segredos reais) fica no servidor.
        # O instance/secrets.cfg do formato unico anterior continua entrando, para o pacote ser recusado.
        if rel == "instance/secrets.cfg":
            return False
        return not (rel == "instance/exemplos" or rel.startswith("instance/exemplos/") or rel.endswith(".example"))
    return any(rel == p or rel.startswith(p + "/") for p in EXCLUDE_APP)


def _walk(source, base, problems, filter_value=None):
    """Arquivos de origem/base (relativos a origem), sem seguir links; links viram problema."""
    files = []
    for dir_value, subdirs, names in os.walk(os.path.join(source, base)):
        rel_dir = os.path.relpath(dir_value, source).replace(os.sep, "/")
        for name in sorted(subdirs):
            if os.path.islink(os.path.join(dir_value, name)):
                problems.append("%s/%s: link simbolico" % (rel_dir, name))
        keep = []
        for name in sorted(subdirs):
            rel = rel_dir + "/" + name
            if os.path.islink(os.path.join(dir_value, name)) or (filter_value and filter_value(rel)):
                continue
            keep.append(name)
        subdirs[:] = keep
        for name in sorted(names):
            rel = rel_dir + "/" + name
            if filter_value and filter_value(rel):
                continue
            if os.path.islink(os.path.join(dir_value, name)):
                problems.append("%s: link simbolico" % rel)
                continue
            files.append(rel)
    return files


def collect(source):
    """(arquivos relativos a origem, problemas de link/ausencia/resto do web2py na raiz)."""
    problems = [f"{name}: resto do web2py na raiz (CR-021f)" for name in WEB2PY_ROOT_LEFTOVERS
                if os.path.lexists(os.path.join(source, name))]
    files = []
    for name in BIN:
        rel = "bin/" + name
        if os.path.isfile(os.path.join(source, rel)) and not os.path.islink(os.path.join(source, rel)):
            files.append(rel)
        else:
            problems.append("%s: ausente" % rel)
    for name in APP_FILES:
        if os.path.isfile(os.path.join(source, name)) and not os.path.islink(os.path.join(source, name)):
            files.append(name)
        else:
            problems.append("%s: ausente" % name)
    for name in APP_DIRS:
        files.extend(_walk(source, name, problems, filter_value=_excluded_from_app))
    return sorted(files), problems


def _credentials(rel, content):
    name = rel.rsplit("/", 1)[-1]
    if not (name.endswith(".ini") or name.endswith(".cfg") or name.endswith(".cfg.example")
            or name.endswith(".ini.example")):
        return []
    problems = []
    for n, line in enumerate(content.decode("utf-8", "replace").splitlines(), 1):
        m = _RE_CREDENTIAL.match(line)
        if not m:
            continue
        value = re.split(r"\s+[;#]", m.group(2), 1)[0].strip()
        if not value or value in ("...",):
            continue
        # CR-028: os exemplos de instance/exemplos/<nome>/ tambem usam o placeholder.
        if (rel == _SECRETS_EXAMPLE or rel.endswith("/secrets.cfg.example")) and value == _PLACEHOLDER:
            continue
        problems.append("%s:%d: %s com valor que nao e o placeholder %s" % (rel, n, m.group(1).lower(), _PLACEHOLDER))
    return problems


def check(files, read):
    """Problemas do conteudo (sem valores). ler(rel) -> bytes."""
    problems = []
    for rel in files:
        parts = rel.split("/")
        name = parts[-1]
        if name == "secrets.cfg":
            problems.append("%s: arquivo de segredos real" % rel)
        if name.endswith(".pyc") or "__pycache__" in parts:
            problems.append("%s: bytecode" % rel)
        if rel.endswith("controllers/dev.py") or "repo_fake" in parts or rel.startswith("src/sss/persistence/fake/"):
            problems.append("%s: codigo de DEV" % rel)
        if parts[0] in WEB2PY_ROOT_LEFTOVERS:
            problems.append(f"{rel}: resto do web2py (CR-021f)")
        elif any(rel == d or rel.startswith(d + "/") for d in WEB2PY_APP_DIRS):
            problems.append("%s: pasta de runtime do web2py" % rel)
        problems.extend(_credentials(rel, read(rel)))
    return problems


def _info(name, size, mode, kind=tarfile.REGTYPE):
    info = tarfile.TarInfo(name)
    info.size, info.mode, info.type, info.mtime = size, mode, kind, MTIME
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def build_package(source, output, version=None):
    """Gera o pacote e o SHA256SUMS; devolve (tar_gz, sha256sums). PackageError sem gravar nada."""
    version = version or sss_config.SSS_VERSION
    source = os.path.abspath(source)
    files, problems = collect(source)

    def ler(rel):
        with open(os.path.join(source, rel), "rb") as f:
            return f.read()
    problems.extend(check(files, ler))
    if problems:
        raise PackageError(problems)

    top = "sss-%s" % version
    content = [(rel, ler(rel)) for rel in files]
    content.sort()
    sums = "".join("%s  %s\n" % (hashlib.sha256(data).hexdigest(), rel) for rel, data in content)
    dirs = set()
    for rel, _d in content:
        parts = rel.split("/")[:-1]
        dirs.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))

    os.makedirs(output, exist_ok=True)
    destination = os.path.join(output, "%s.tar.gz" % top)
    temporary = destination + ".parcial"
    try:
        with open(temporary, "wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tar:
                    tar.addfile(_info(top, 0, 0o755, tarfile.DIRTYPE))
                    items = [(p, None) for p in dirs] + content + [("SHA256SUMS", sums.encode("utf-8"))]
                    for rel, data in sorted(items, key=lambda x: x[0]):
                        name = top + "/" + rel
                        if data is None:
                            tar.addfile(_info(name, 0, 0o755, tarfile.DIRTYPE))
                        else:
                            mode = 0o755 if rel.startswith("bin/") else 0o644
                            tar.addfile(_info(name, len(data), mode), io.BytesIO(data))
        os.replace(temporary, destination)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise
    with open(destination, "rb") as f:
        hash_package = hashlib.sha256(f.read()).hexdigest()
    sums_dist = os.path.join(output, "SHA256SUMS")
    with open(sums_dist, "w", encoding="utf-8") as f:
        f.write("%s  %s\n" % (hash_package, os.path.basename(destination)))
    return destination, sums_dist


def main(argv=None, output_text=None):
    output_text = output_text or sys.stdout
    parser = argparse.ArgumentParser(description="Pacote de implantacao do SSS (README §12.2)")
    parser.add_argument("--source", dest="origem", default=DEFAULT_ROOT, help="raiz do repositorio a empacotar (padrao: esta arvore)")
    parser.add_argument("--out-dir", dest="saida", default=None, help="pasta de saida (padrao: <origem>/dist)")
    args = parser.parse_args(argv)
    try:
        destination, sums = build_package(args.origem, args.saida or os.path.join(args.origem, "dist"))
    except PackageError as exc:
        output_text.write("Pacote recusado:\n")
        for problem in exc.problems:
            output_text.write("  - %s\n" % problem)
        return 1
    output_text.write("Pacote: %s\nSHA256SUMS: %s\n" % (destination, sums))
    return 0


if __name__ == "__main__":
    sys.exit(main())
