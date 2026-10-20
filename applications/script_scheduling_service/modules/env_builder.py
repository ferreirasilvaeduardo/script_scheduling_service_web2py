# -*- coding: utf-8 -*-
"""Ambiente do processo filho (README §8.6; CR-007 D1, R-17 e R-32; CR-008 R-36; CR-010).

CR-010: o script recebe, em variaveis SSS_* (prefixo reservado, recusado no env_passthrough), os dados da
execucao, do ambiente, do script, do log e do agente. Variavel sem valor nao e definida.

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
VAR_CONEXAO_SSS = "SSS_AMBIENTE_CONEXAO"
_FMT_DATA = "%Y-%m-%d %H:%M:%S"
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
    """(usuario, connect string) do ambiente, ou (usuario ou None, None) sem DSN ou sem credencial."""
    nome = ambiente["nome"]
    dsn = (ambiente.get("conexao") or "").strip()
    cred = (getattr(segredos, "ambientes", None) or {}).get(nome)
    usuario = cred.user if cred is not None else None
    if not dsn or cred is None:
        _log.warning("%s omitida: ambiente %s sem %s", VAR_CONEXAO, nome,
                     "DSN" if not dsn else "credencial [ambiente:%s] no secrets.cfg" % nome,
                     extra={"ticket": ticket_id, "acao": "SPAWN"})
        return usuario, None
    valor = "%s/%s@%s" % (cred.user, cred.password, dsn)
    masking.registrar_segredo(cred.password)
    masking.registrar_segredo(valor)
    return usuario, valor


def _data(valor):
    if valor is None:
        return None
    return valor.strftime(_FMT_DATA) if hasattr(valor, "strftime") else str(valor)


def _definir(env, nome, valor):
    """Define SSS_* so com valor (CR-010): None ou texto vazio deixam a variavel ausente."""
    if valor is None:
        return
    texto = str(valor)
    if texto.strip() and "\x00" not in texto:
        env[nome] = texto


def construir(cfg, segredos, ticket, ambiente, script_real, work_dir_ticket, environ_daemon, plataforma_nome,
              snapshot=None, agendamento=None, caminho_log=None, timeout_seg=None, hostname=None, versao=None,
              pasta_saida=None):
    """Ambiente exato do filho (README §8.6, tabela POSIX; CR-010). Variavel bloqueada: ValueError.

    ticket: dict com id, ambiente e, quando houver, parent_ticket_id, agendamento_id, prioridade, started_at
    (relogio do banco, devolvido pelo claim) e scheduled_at; ambiente: dict com nome, descricao e conexao
    (tbsss_ambientes); script_real: o caminho resolvido pelo path_guard; environ_daemon: o ambiente do daemon
    (so para TZ e env_passthrough); snapshot: o snapshot v4 (script_id, script_nome, interpretador);
    agendamento: dict com nome e tipo_recorrencia da regra que gerou o ticket; caminho_log: o
    .log.parcial aberto por executor.abrir_log; timeout_seg: o prazo efetivo; hostname e versao: do agente;
    pasta_saida: a pasta de saida do ticket (CR-012), so quando o agente tem saida_dir.
    """
    if plataforma_nome not in PLATAFORMAS:
        raise ValueError("Plataforma nao suportada: %s" % plataforma_nome)
    if not isinstance(script_real, str) or not script_real.startswith("/"):
        raise ValueError("script_real deve ser absoluto")
    ticket_id = int(ticket["id"])
    agente = cfg.agent
    usuario = usuario_execucao(cfg, ambiente["nome"])
    home = dir_trabalho_script(ticket_id, usuario, agente.exec_work_dir, work_dir_ticket)
    snap = snapshot or {}

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
        "SSS_SCRIPT_ARQUIVO": script_real,
        "SSS_PLATAFORMA": plataforma_nome,
    })
    if environ_daemon.get("TZ"):
        env["TZ"] = environ_daemon["TZ"]

    # Execucao (CR-010).
    agendada = ticket.get("agendamento_id") is not None
    env["SSS_TIPO_EXECUCAO"] = "AGENDADA" if agendada else "MANUAL"
    _definir(env, "SSS_TICKET_PAI_ID", ticket.get("parent_ticket_id"))
    _definir(env, "SSS_PRIORIDADE", ticket.get("prioridade"))
    _definir(env, "SSS_DATA_EXECUCAO", _data(ticket.get("started_at")))
    _definir(env, "SSS_DATA_AGENDADA", _data(ticket.get("scheduled_at")))
    _definir(env, "SSS_TIMEOUT_SEG", timeout_seg)
    if agendada:
        _definir(env, "SSS_AGENDAMENTO_ID", ticket.get("agendamento_id"))
        _definir(env, "SSS_AGENDAMENTO_NOME", (agendamento or {}).get("nome"))
        _definir(env, "SSS_RECORRENCIA", (agendamento or {}).get("tipo_recorrencia"))
    # Script, log e agente.
    # CR-011: com link simbolico no caminho, o cadastrado vai em SSS_SCRIPT_LINK; o real nos demais.
    if snap.get("path_file") and snap["path_file"] != script_real:
        _definir(env, "SSS_SCRIPT_LINK", snap["path_file"])
    _definir(env, "SSS_SCRIPT_ID", snap.get("script_id"))
    _definir(env, "SSS_SCRIPT_NOME", snap.get("script_nome"))
    _definir(env, "SSS_INTERPRETADOR", snap.get("interpretador"))
    if caminho_log:
        _definir(env, "SSS_LOG_DIR", os.path.dirname(caminho_log))
        _definir(env, "SSS_LOG_ARQUIVO", os.path.basename(caminho_log))
    _definir(env, "SSS_SAIDA_DIR", pasta_saida)
    _definir(env, "SSS_AGENTE_HOST", hostname)
    _definir(env, "SSS_VERSAO", versao)
    # Ambiente: descricao, DSN (sem credencial), usuario e a connect string (mascarada em todo log).
    _definir(env, "SSS_AMBIENTE_DESCRICAO", ambiente.get("descricao"))
    _definir(env, "SSS_AMBIENTE_DSN", (ambiente.get("conexao") or "").strip() or None)
    usuario_bd, conexao = _conexao(segredos, ambiente, ticket_id)
    _definir(env, "SSS_AMBIENTE_USUARIO", usuario_bd)
    if conexao is not None:
        env[VAR_CONEXAO] = conexao
        env[VAR_CONEXAO_SSS] = conexao
    return env
