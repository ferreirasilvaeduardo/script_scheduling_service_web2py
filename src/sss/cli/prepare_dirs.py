# -*- coding: utf-8 -*-
"""Cria as pastas do config.ini com o dono e o modo da implantacao (CR-026e; DEPLOYMENT §4, §8).

Uso (como root no servidor; no DEV, com o proprio usuario):
  python3 scripts/prepare_dirs.py [--config <config.ini>] [--service-user sss] [--dry-run]

O SSS nao cria as pastas configuradas na subida (README §12.1): este comando as cria antes.
  log_dir                                 sss          0750
  work_dir                                sss          0700
  exec_work_dir (com exec_users)          root         0755
  exec_work_dir/<usuario de execucao>     o usuario    0700
  output_dir, input_dir, script_work_dir  sss          0755
  <essas tres>/<ambiente>                 o usuario de execucao do ambiente  0700
  script_base_dir                         sss          0755
A pasta que ja existe tem o dono e o modo ajustados (nunca o conteudo); nada e apagado. Antes de
criar qualquer coisa, confere que os usuarios existem. Fora de DEV exige root; no DEV, sem root,
cria com o usuario atual (sem chown) e pula as pastas dos usuarios de execucao.

Saida: 0 ok; 1 falha ao criar ou ajustar; 2 configuracao ou usuario invalido;
3 fora de DEV sem root.
"""
import argparse
import os
import pwd
import sys
from typing import List, NamedTuple, Optional, Sequence

from sss.config import log_paths, sss_config

EXIT_OK, EXIT_FAILURE, EXIT_INVALID, EXIT_NOT_ROOT = 0, 1, 2, 3

Folder = NamedTuple("Folder", [("path", str), ("owner", str), ("mode", int), ("key", str)])


def plan(cfg: "sss_config.Config", service_user: str, as_root: bool) -> List[Folder]:
    """Pastas na ordem de criacao (a de cima antes das de baixo). Sem root (so no DEV), o dono e o
    usuario atual e as pastas dos usuarios de execucao ficam de fora."""
    agent = cfg.agent
    me = service_user if as_root else pwd.getpwuid(os.getuid()).pw_name
    users = dict(agent.exec_users) if as_root else {}
    folders = [Folder(cfg.logging.log_dir, me, 0o750, "log_dir"),
               Folder(agent.work_dir, me, 0o700, "work_dir")]
    if agent.exec_work_dir:
        top = "root" if as_root else me
        folders.append(Folder(agent.exec_work_dir, top, 0o755, "exec_work_dir"))
        for user in sorted(set(users.values())):
            path = os.path.join(agent.exec_work_dir, user)
            folders.append(Folder(path, user, 0o700, "exec_work_dir"))
    for key in ("output_dir", "input_dir", "script_work_dir"):
        base = getattr(agent, key)
        if not base:
            continue
        folders.append(Folder(base, me, 0o755, key))
        for env in agent.environments:
            if env in users:
                path = os.path.join(base, log_paths.environment_dir(env))
                folders.append(Folder(path, users[env], 0o700, key))
    if agent.script_base_dir:
        folders.append(Folder(agent.script_base_dir, me, 0o755, "script_base_dir"))
    return folders


def missing_users(folders: Sequence[Folder]) -> List[str]:
    missing = []
    for owner in sorted(set(f.owner for f in folders)):
        try:
            pwd.getpwnam(owner)
        except KeyError:
            missing.append(owner)
    return missing


def apply(folder: Folder, chown: bool) -> str:
    """Cria (com as de cima que faltarem) ou ajusta; devolve 'criada', 'ajustada' ou 'ok'."""
    entry = pwd.getpwnam(folder.owner)
    if os.path.islink(folder.path):
        raise OSError("e link simbolico; crie a pasta real e aponte o config.ini para ela")
    if os.path.lexists(folder.path) and not os.path.isdir(folder.path):
        raise OSError("existe e nao e pasta")
    state = "ok"
    if not os.path.isdir(folder.path):
        os.makedirs(folder.path, 0o755)
        state = "criada"
    st = os.stat(folder.path)
    if chown and (st.st_uid != entry.pw_uid or st.st_gid != entry.pw_gid):
        os.chown(folder.path, entry.pw_uid, entry.pw_gid)
        state = "ajustada" if state == "ok" else state
    if st.st_mode & 0o7777 != folder.mode:
        os.chmod(folder.path, folder.mode)
        state = "ajustada" if state == "ok" else state
    return state


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cria as pastas do config.ini do SSS com dono e modo (CR-026e)")
    parser.add_argument("--config", default=None, help="config.ini (padrao: instance/config.ini)")
    parser.add_argument("--service-user", default="sss", help="usuario do servico (padrao: sss)")
    parser.add_argument("--dry-run", action="store_true", help="so mostra o que faria")
    args = parser.parse_args(argv)
    try:
        cfg = sss_config.load(args.config or sss_config.default_config_path())
    except sss_config.ConfigError as exc:
        print("Configuracao invalida: %s" % exc, file=sys.stderr)
        return EXIT_INVALID
    as_root = os.geteuid() == 0
    if not as_root and cfg.app.sss_env != "DEV":
        print("Fora de DEV, rode como root: as pastas sao do usuario do servico e dos usuarios "
              "de execucao.", file=sys.stderr)
        return EXIT_NOT_ROOT
    for message in sss_config.pending_warnings():
        print(message, file=sys.stderr)
    folders = plan(cfg, args.service_user, as_root)
    missing = missing_users(folders)
    if missing:
        print("Usuario(s) inexistente(s): %s. Crie antes (DEPLOYMENT §4); nenhuma pasta foi "
              "criada." % ", ".join(missing), file=sys.stderr)
        return EXIT_INVALID
    if not as_root:
        print("DEV sem root: pastas do usuario atual, sem as dos usuarios de execucao.")
    failures = 0
    for f in folders:
        line = "%-16s %-10s %04o %s" % (f.key, f.owner, f.mode, f.path)
        if args.dry_run:
            print("faria: " + line)
            continue
        try:
            print("%-9s %s" % (apply(f, as_root), line))
        except OSError as exc:
            failures += 1
            reason = getattr(exc, "strerror", None) or exc
            print("FALHA     %s (%s)" % (line, reason), file=sys.stderr)
    return EXIT_FAILURE if failures else EXIT_OK
