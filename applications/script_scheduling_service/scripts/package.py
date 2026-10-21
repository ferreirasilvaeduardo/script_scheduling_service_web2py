# -*- coding: utf-8 -*-
"""Pacote de implantacao (README §12.2; F9.1c; CR-005; CR-003 P10). Biblioteca padrao apenas.

Uso: python scripts/package.py [--source <raiz do web2py>] [--out-dir <pasta>]

Gera <saida>/sss-<versao>.tar.gz (tudo sob sss-<versao>/, com um SHA256SUMS de cada arquivo) e <saida>/SHA256SUMS
com o hash do tar.gz. A versao e sss_config.VERSAO_SSS. O tar e deterministico (ordem, dono, data e modos fixos).

Entram: web2py.py, anyserver.py, gluon/ (sem os testes do upstream), um routes.py gerado com a aplicacao padrao unica, os launchers de
producao e o helper do bin/, e a aplicacao sem codigo de DEV, sem testes e sem pastas de runtime (que vao vazias).
Falha (codigo 1, sem gravar nada) se o pacote tiver secrets.cfg real, *.pyc, __pycache__, controllers/dev.py,
repo_fake, /admin/, pasta de runtime, link simbolico ou credencial que nao seja o CHANGE_ME de
instance/secrets.cfg.example. A mensagem cita o arquivo e a linha, nunca o valor.
"""
import argparse
import gzip
import hashlib
import io
import os
import re
import sys
import tarfile

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_SCRIPTS)
sys.path.insert(0, os.path.join(_APP_DIR, "modules"))

import sss_config  # noqa: E402

APP = "applications/script_scheduling_service"
RAIZ_PADRAO = os.path.dirname(os.path.dirname(_APP_DIR))
ARQUIVOS_RAIZ = ("web2py.py", "anyserver.py")
PASTAS_RAIZ = ("gluon",)
BIN = ("sss-web.sh", "sss-scheduler.sh", "sss-stop.sh", "sss-helper")
# Pastas de runtime do web2py: entram vazias (o web2py as usa), nunca com conteudo.
RUNTIME_VAZIAS = ("sessions", "errors", "cache", "databases", "uploads", "private", "cron")
# Relativos a aplicacao: nunca entram (codigo de DEV, configuracao local, pastas que o web2py cria fora da raiz).
EXCLUIR_APP = (
    "controllers/dev.py", "views/dev", "dev", "modules/repo_fake", "instance/config.ini", "instance/web.env",
    "log", "logs", "work", "exec", "dist", "applications", "deposit", "site-packages",
    "scripts/applications", "scripts/deposit", "scripts/logs", "scripts/site-packages",
    "scripts/_testenv.py", "scripts/_oracle_test_support.py", "scripts/_saida_memoria.py",
) + RUNTIME_VAZIAS
_RE_TESTE = re.compile(r"^scripts/test_[^/]*\.py$")
# Do gluon/ (upstream) saem os testes e o ambiente virtual de teste versionado do pydal, em qualquer nivel.
EXCLUIR_GLUON = ("tests", "test-venv", ".pytest_cache", "ci")
_RE_CREDENCIAL = re.compile(r"^\s*(password|cookie_key)\s*[=:]\s*(.*?)\s*$", re.IGNORECASE)
_EXEMPLO_SEGREDOS = APP + "/instance/secrets.cfg.example"
_PLACEHOLDER = "CHANGE_ME"
MTIME = 1767225600  # 2026-01-01 00:00:00 UTC: tar reprodutivel

ROUTES = '''# -*- coding: utf-8 -*-
# Gerado por scripts/package.py (README §12.2): script_scheduling_service e a aplicacao padrao e unica.
default_application = "script_scheduling_service"
default_controller = "default"
default_function = "index"

routes_onerror = [
    ("script_scheduling_service/*", "/script_scheduling_service/erro/index"),
]
'''


class ErroPacote(Exception):
    """Pacote recusado; problemas e a lista de motivos (sem valores de credencial)."""

    def __init__(self, problemas):
        Exception.__init__(self, "pacote recusado: %d problema(s)" % len(problemas))
        self.problemas = problemas


def _excluido_da_app(rel):
    if _RE_TESTE.match(rel):
        return True
    return any(rel == p or rel.startswith(p + "/") for p in EXCLUIR_APP)


def _caminhar(origem, base, problemas, filtro=None):
    """Arquivos de origem/base (relativos a origem), sem seguir links; links viram problema."""
    arquivos = []
    for pasta, subpastas, nomes in os.walk(os.path.join(origem, base)):
        rel_pasta = os.path.relpath(pasta, origem).replace(os.sep, "/")
        for nome in sorted(subpastas):
            if os.path.islink(os.path.join(pasta, nome)):
                problemas.append("%s/%s: link simbolico" % (rel_pasta, nome))
        manter = []
        for nome in sorted(subpastas):
            rel = rel_pasta + "/" + nome
            if os.path.islink(os.path.join(pasta, nome)) or (filtro and filtro(rel)):
                continue
            manter.append(nome)
        subpastas[:] = manter
        for nome in sorted(nomes):
            rel = rel_pasta + "/" + nome
            if filtro and filtro(rel):
                continue
            if os.path.islink(os.path.join(pasta, nome)):
                problemas.append("%s: link simbolico" % rel)
                continue
            arquivos.append(rel)
    return arquivos


def coletar(origem):
    """(arquivos relativos a origem, problemas de link/ausencia). O routes.py e gerado, nao coletado."""
    problemas = []
    arquivos = []
    for nome in ARQUIVOS_RAIZ:
        if os.path.isfile(os.path.join(origem, nome)):
            arquivos.append(nome)
        else:
            problemas.append("%s: ausente" % nome)
    for nome in BIN:
        rel = "bin/" + nome
        if os.path.isfile(os.path.join(origem, rel)) and not os.path.islink(os.path.join(origem, rel)):
            arquivos.append(rel)
        else:
            problemas.append("%s: ausente" % rel)
    for pasta in PASTAS_RAIZ:
        arquivos.extend(_caminhar(origem, pasta, problemas,
                                  filtro=lambda rel: any(p in EXCLUIR_GLUON for p in rel.split("/"))))
    prefixo = APP + "/"
    arquivos.extend(_caminhar(origem, APP, problemas,
                              filtro=lambda rel: _excluido_da_app(rel[len(prefixo):])))
    return sorted(arquivos), problemas


def _credenciais(rel, conteudo):
    nome = rel.rsplit("/", 1)[-1]
    if not (nome.endswith(".ini") or nome.endswith(".cfg") or nome.endswith(".cfg.example")
            or nome.endswith(".ini.example")):
        return []
    problemas = []
    for n, linha in enumerate(conteudo.decode("utf-8", "replace").splitlines(), 1):
        m = _RE_CREDENCIAL.match(linha)
        if not m:
            continue
        valor = re.split(r"\s+[;#]", m.group(2), 1)[0].strip()
        if not valor or valor in ("...",):
            continue
        if rel == _EXEMPLO_SEGREDOS and valor == _PLACEHOLDER:
            continue
        problemas.append("%s:%d: %s com valor que nao e o placeholder %s" % (rel, n, m.group(1).lower(), _PLACEHOLDER))
    return problemas


def verificar(arquivos, ler):
    """Problemas do conteudo (sem valores). ler(rel) -> bytes."""
    problemas = []
    for rel in arquivos:
        partes = rel.split("/")
        nome = partes[-1]
        if nome == "secrets.cfg":
            problemas.append("%s: arquivo de segredos real" % rel)
        if nome.endswith(".pyc") or "__pycache__" in partes:
            problemas.append("%s: bytecode" % rel)
        if rel.endswith("controllers/dev.py") or "repo_fake" in partes:
            problemas.append("%s: codigo de DEV" % rel)
        if rel.startswith("applications/") and partes[1] != "script_scheduling_service":
            problemas.append("%s: aplicacao fora do SSS (/admin/, welcome, examples)" % rel)
        if rel.startswith(APP + "/"):
            resto = rel[len(APP) + 1:]
            if resto.split("/")[0] in ("applications", "deposit", "logs", "site-packages") or \
                    resto.split("/")[:2] in (["scripts", "applications"], ["scripts", "deposit"],
                                             ["scripts", "logs"], ["scripts", "site-packages"]):
                problemas.append("%s: pasta de runtime do web2py" % rel)
        problemas.extend(_credenciais(rel, ler(rel)))
    return problemas


def _info(nome, tamanho, modo, tipo=tarfile.REGTYPE):
    info = tarfile.TarInfo(nome)
    info.size, info.mode, info.type, info.mtime = tamanho, modo, tipo, MTIME
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def empacotar(origem, saida, versao=None):
    """Gera o pacote e o SHA256SUMS; devolve (tar_gz, sha256sums). ErroPacote sem gravar nada."""
    versao = versao or sss_config.VERSAO_SSS
    origem = os.path.abspath(origem)
    arquivos, problemas = coletar(origem)

    def ler(rel):
        with open(os.path.join(origem, rel), "rb") as f:
            return f.read()
    problemas.extend(verificar(arquivos, ler))
    if problemas:
        raise ErroPacote(problemas)

    topo = "sss-%s" % versao
    conteudo = [(rel, ler(rel)) for rel in arquivos] + [("routes.py", ROUTES.encode("utf-8"))]
    conteudo.sort()
    somas = "".join("%s  %s\n" % (hashlib.sha256(dados).hexdigest(), rel) for rel, dados in conteudo)
    pastas = set()
    for rel, _d in conteudo:
        partes = rel.split("/")[:-1]
        pastas.update("/".join(partes[:i]) for i in range(1, len(partes) + 1))
    pastas.update(APP + "/" + p for p in RUNTIME_VAZIAS)

    os.makedirs(saida, exist_ok=True)
    destino = os.path.join(saida, "%s.tar.gz" % topo)
    temporario = destino + ".parcial"
    try:
        with open(temporario, "wb") as bruto:
            with gzip.GzipFile(filename="", mode="wb", fileobj=bruto, mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tar:
                    tar.addfile(_info(topo, 0, 0o755, tarfile.DIRTYPE))
                    itens = [(p, None) for p in pastas] + conteudo + [("SHA256SUMS", somas.encode("utf-8"))]
                    for rel, dados in sorted(itens, key=lambda x: x[0]):
                        nome = topo + "/" + rel
                        if dados is None:
                            tar.addfile(_info(nome, 0, 0o755, tarfile.DIRTYPE))
                        else:
                            modo = 0o755 if rel.startswith("bin/") else 0o644
                            tar.addfile(_info(nome, len(dados), modo), io.BytesIO(dados))
        os.replace(temporario, destino)
    except BaseException:
        if os.path.exists(temporario):
            os.remove(temporario)
        raise
    with open(destino, "rb") as f:
        hash_pacote = hashlib.sha256(f.read()).hexdigest()
    somas_dist = os.path.join(saida, "SHA256SUMS")
    with open(somas_dist, "w", encoding="utf-8") as f:
        f.write("%s  %s\n" % (hash_pacote, os.path.basename(destino)))
    return destino, somas_dist


def main(argv=None, saida_texto=None):
    saida_texto = saida_texto or sys.stdout
    parser = argparse.ArgumentParser(description="Pacote de implantacao do SSS (README §12.2)")
    parser.add_argument("--source", dest="origem", default=RAIZ_PADRAO, help="raiz do web2py a empacotar (padrao: esta arvore)")
    parser.add_argument("--out-dir", dest="saida", default=None, help="pasta de saida (padrao: <origem>/dist)")
    args = parser.parse_args(argv)
    try:
        destino, somas = empacotar(args.origem, args.saida or os.path.join(args.origem, "dist"))
    except ErroPacote as exc:
        saida_texto.write("Pacote recusado:\n")
        for problema in exc.problemas:
            saida_texto.write("  - %s\n" % problema)
        return 1
    saida_texto.write("Pacote: %s\nSHA256SUMS: %s\n" % (destino, somas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
