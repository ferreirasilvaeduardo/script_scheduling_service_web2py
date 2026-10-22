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

CHILD_PATH = "/usr/bin:/bin"
CONNECTION_VAR = "PADRAO_VALOR_RUN_CONEXAO_BD"
SSS_CONNECTION_VAR = "SSS_ENVIRONMENT_CONNECTION"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"
PLATFORMS = ("LINUX", "UNIX")


def exec_user(cfg, environment_name):
    """Usuario do SO do ambiente em [agent] exec_users, ou None (so DEV, validado no config)."""
    return dict(cfg.agent.exec_users or ()).get(environment_name) or None


def script_work_dir(ticket_id, user, exec_work_dir, work_dir_ticket):
    """cwd/HOME do script (README §8.4 passo 2): exec_work_dir/<usuario>/ticket_<id> com usuario de
    execucao (criado pelo helper); em DEV sem usuario, work_dir/ticket_<id>/exec."""
    if user:
        return os.path.join(exec_work_dir, user, "ticket_%d" % int(ticket_id))
    return os.path.join(work_dir_ticket, "exec")


def _passthrough(names, environ_daemon):
    env = {}
    for nome in names or ():
        if sss_config.is_blocked_variable(nome):
            # O config ja recusa na subida; aqui e defesa em profundidade (README §8.6).
            raise ValueError("Variavel bloqueada no env_passthrough: %s" % nome)
        if nome in environ_daemon:
            env[nome] = environ_daemon[nome]
    return env


def _connection(secrets, environment, ticket_id):
    """(usuario, connect string) do ambiente, ou (usuario ou None, None) sem DSN ou sem credencial."""
    nome = environment["name"]
    dsn = (environment.get("connection") or "").strip()
    cred = (getattr(secrets, "environments", None) or {}).get(nome)
    usuario = cred.user if cred is not None else None
    if not dsn or cred is None:
        _log.warning("%s omitida: ambiente %s sem %s", CONNECTION_VAR, nome,
                     "DSN" if not dsn else "credencial [environment:%s] no secrets.cfg" % nome,
                     extra={"ticket": ticket_id, "action": "SPAWN"})
        return usuario, None
    valor = "%s/%s@%s" % (cred.user, cred.password, dsn)
    masking.register_secret(cred.password)
    masking.register_secret(valor)
    return usuario, valor


def _date(value):
    if value is None:
        return None
    return value.strftime(_DATE_FMT) if hasattr(value, "strftime") else str(value)


def _set(env, name, value):
    """Define SSS_* so com valor (CR-010): None ou texto vazio deixam a variavel ausente."""
    if value is None:
        return
    texto = str(value)
    if texto.strip() and "\x00" not in texto:
        env[name] = texto


def build(cfg, secrets, ticket, environment, script_real, work_dir_ticket, environ_daemon, platform_name,
              snapshot=None, schedule=None, log_path=None, timeout_sec=None, hostname=None, version=None,
              output_dir=None, input_dir=None):
    """Ambiente exato do filho (README §8.6, tabela POSIX; CR-010). Variavel bloqueada: ValueError.

    ticket: dict com id, ambiente e, quando houver, parent_ticket_id, agendamento_id, prioridade, started_at
    (relogio do banco, devolvido pelo claim) e scheduled_at; ambiente: dict com nome, descricao e conexao
    (tbsss_environments); script_real: o caminho resolvido pelo path_guard; environ_daemon: o ambiente do daemon
    (so para TZ e env_passthrough); snapshot: o snapshot v4 (script_id, script_nome, interpretador);
    agendamento: dict com nome e tipo_recorrencia da regra que gerou o ticket; log_path: o
    .log.parcial aberto por executor.open_log; timeout_seg: o prazo efetivo; hostname e versao: do agente;
    output_dir: a pasta de saida do ticket (CR-012), so quando o agente tem output_dir.
    input_dir: a pasta de entrada do script (CR-014), so quando o agente tem input_dir.
    """
    if platform_name not in PLATFORMS:
        raise ValueError("Plataforma nao suportada: %s" % platform_name)
    if not isinstance(script_real, str) or not script_real.startswith("/"):
        raise ValueError("script_real deve ser absoluto")
    ticket_id = int(ticket["id"])
    agente = cfg.agent
    usuario = exec_user(cfg, environment["name"])
    home = script_work_dir(ticket_id, usuario, agente.exec_work_dir, work_dir_ticket)
    snap = snapshot or {}

    env = _passthrough(agente.env_passthrough, environ_daemon)
    env.update({
        "PATH": CHILD_PATH,
        "HOME": home,
        "TMPDIR": os.path.join(home, "tmp"),
        "LANG": agente.child_locale,
        "LC_ALL": agente.child_locale,
        # Efeito so em BASH/SH chamando python sem -I; o PYTHON3 roda com -I (CR-007, R-17).
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "SSS_TICKET_ID": str(ticket_id),
        "SSS_ENVIRONMENT": environment["name"],
        "SSS_AGENT_ID": agente.agent_id,
        "SSS_SCRIPT_DIR": os.path.dirname(script_real),
        "SSS_SCRIPT_FILE": script_real,
        "SSS_PLATFORM": platform_name,
    })
    if environ_daemon.get("TZ"):
        env["TZ"] = environ_daemon["TZ"]

    # Execucao (CR-010).
    agendada = ticket.get("schedule_id") is not None
    env["SSS_EXECUTION_TYPE"] = "AGENDADA" if agendada else "MANUAL"
    _set(env, "SSS_PARENT_TICKET_ID", ticket.get("parent_ticket_id"))
    _set(env, "SSS_PRIORITY", ticket.get("priority"))
    _set(env, "SSS_STARTED_AT", _date(ticket.get("started_at")))
    _set(env, "SSS_SCHEDULED_AT", _date(ticket.get("scheduled_at")))
    _set(env, "SSS_TIMEOUT_SECONDS", timeout_sec)
    if agendada:
        _set(env, "SSS_SCHEDULE_ID", ticket.get("schedule_id"))
        _set(env, "SSS_SCHEDULE_NAME", (schedule or {}).get("name"))
        _set(env, "SSS_RECURRENCE", (schedule or {}).get("recurrence_type"))
    # Script, log e agente.
    # CR-011: com link simbolico no caminho, o cadastrado vai em SSS_SCRIPT_LINK; o real nos demais.
    if snap.get("path_file") and snap["path_file"] != script_real:
        _set(env, "SSS_SCRIPT_LINK", snap["path_file"])
    _set(env, "SSS_SCRIPT_ID", snap.get("script_id"))
    _set(env, "SSS_SCRIPT_NAME", snap.get("script_name"))
    _set(env, "SSS_INTERPRETER", snap.get("interpreter"))
    if log_path:
        _set(env, "SSS_LOG_DIR", os.path.dirname(log_path))
        _set(env, "SSS_LOG_FILE", os.path.basename(log_path))
    _set(env, "SSS_OUTPUT_DIR", output_dir)
    _set(env, "SSS_INPUT_DIR", input_dir)
    _set(env, "SSS_AGENT_HOST", hostname)
    _set(env, "SSS_VERSION", version)
    # Ambiente: descricao, DSN (sem credencial), usuario e a connect string (mascarada em todo log).
    _set(env, "SSS_ENVIRONMENT_DESCRIPTION", environment.get("description"))
    _set(env, "SSS_ENVIRONMENT_DSN", (environment.get("connection") or "").strip() or None)
    usuario_bd, conexao = _connection(secrets, environment, ticket_id)
    _set(env, "SSS_ENVIRONMENT_USER", usuario_bd)
    if conexao is not None:
        env[CONNECTION_VAR] = conexao
        env[SSS_CONNECTION_VAR] = conexao
    return env
