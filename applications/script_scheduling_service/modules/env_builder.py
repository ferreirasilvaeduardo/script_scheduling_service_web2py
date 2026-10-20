# -*- coding: utf-8 -*-
"""Ambiente do processo filho (README §8.6; CR-007 D1, R-17 e R-32; CR-008 R-36).

Modulo puro: nao importa gluon nem plataforma, nunca le o ambiente do processo (o do daemon chega por
parametro) e nao toca no sistema de arquivos. So monta caminhos e o dicionario do ambiente.
"""
import logging
import os

import masking
import sss_config

_log = logging.getLogger("sss_scheduler")

PATH_FILHO = "/usr/bin:/bin"
VAR_CONEXAO = "PADRAO_VALOR_RUN_CONEXAO_BD"
PLATAFORMAS = ("LINUX", "UNIX")


def usuario_execucao(cfg, ambiente_nome):
    """Usuario do SO do ambiente em [agent] usuarios_execucao, ou None (so DEV, validado no config)."""
    return dict(cfg.agent.usuarios_execucao or ()).get(ambiente_nome) or None


def dir_trabalho_script(ticket_id, usuario, exec_work_dir, work_dir_ticket):
    """cwd/HOME do script (README §8.4 passo 2): exec_work_dir/<usuario>/ticket_<id> com usuario de
    execucao (criado pelo helper); em DEV sem usuario, work_dir/ticket_<id>/exec."""
    if usuario:
        return os.path.join(exec_work_dir, usuario, "ticket_%d" % int(ticket_id))
    return os.path.join(work_dir_ticket, "exec")


def _passthrough(nomes, environ_daemon):
    env = {}
    for nome in nomes or ():
        if sss_config.variavel_bloqueada(nome):
            # O config ja recusa na subida; aqui e defesa em profundidade (README §8.6).
            raise ValueError("Variavel bloqueada no env_passthrough: %s" % nome)
        if nome in environ_daemon:
            env[nome] = environ_daemon[nome]
    return env


def _conexao(segredos, ambiente, ticket_id):
    nome = ambiente["nome"]
    dsn = (ambiente.get("conexao") or "").strip()
    cred = (getattr(segredos, "ambientes", None) or {}).get(nome)
    if not dsn or cred is None:
        _log.warning("%s omitida: ambiente %s sem %s", VAR_CONEXAO, nome,
                     "DSN" if not dsn else "credencial [ambiente:%s] no secrets.cfg" % nome,
                     extra={"ticket": ticket_id, "acao": "SPAWN"})
        return None
    valor = "%s/%s@%s" % (cred.user, cred.password, dsn)
    masking.registrar_segredo(cred.password)
    masking.registrar_segredo(valor)
    return valor


def construir(cfg, segredos, ticket, ambiente, script_real, work_dir_ticket, environ_daemon, plataforma_nome):
    """Ambiente exato do filho (README §8.6, tabela POSIX). Variavel bloqueada: ValueError.

    ticket: dict com id e ambiente; ambiente: dict com nome e conexao (tbsss_ambientes); script_real: o
    caminho resolvido pelo path_guard; environ_daemon: o ambiente do daemon (so para TZ e env_passthrough).
    """
    if plataforma_nome not in PLATAFORMAS:
        raise ValueError("Plataforma nao suportada: %s" % plataforma_nome)
    if not isinstance(script_real, str) or not script_real.startswith("/"):
        raise ValueError("script_real deve ser absoluto")
    ticket_id = int(ticket["id"])
    agente = cfg.agent
    usuario = usuario_execucao(cfg, ambiente["nome"])
    home = dir_trabalho_script(ticket_id, usuario, agente.exec_work_dir, work_dir_ticket)

    env = _passthrough(agente.env_passthrough, environ_daemon)
    env.update({
        "PATH": PATH_FILHO,
        "HOME": home,
        "TMPDIR": os.path.join(home, "tmp"),
        "LANG": agente.child_locale,
        "LC_ALL": agente.child_locale,
        # Efeito so em BASH/SH chamando python sem -I; o PYTHON3 roda com -I (CR-007, R-17).
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "SSS_TICKET_ID": str(ticket_id),
        "SSS_AMBIENTE": ambiente["nome"],
        "SSS_AGENTE_ID": agente.agent_id,
        "SSS_SCRIPT_DIR": os.path.dirname(script_real),
    })
    if environ_daemon.get("TZ"):
        env["TZ"] = environ_daemon["TZ"]
    conexao = _conexao(segredos, ambiente, ticket_id)
    if conexao is not None:
        env[VAR_CONEXAO] = conexao
    return env
