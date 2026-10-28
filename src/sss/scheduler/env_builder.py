# -*- coding: utf-8 -*-
"""Ambiente do processo filho (README §8.6; CR-007 D1, R-17 e R-32; CR-008 R-36; CR-010).

CR-010: o script recebe, em variaveis SSS_* (prefixo reservado, recusado no env_passthrough), os dados da
execucao, do ambiente, do script, do log e do agente. Variavel sem valor nao e definida.

Modulo puro: nao importa gluon nem plataforma, nunca le o ambiente do processo (o do daemon chega por
parametro) e nao toca no sistema de arquivos. So monta caminhos e o dicionario do ambiente.
"""
import logging
import os

from sss.core import masking, params_compiler
from sss.config import sss_config

_log = logging.getLogger("sss_scheduler")

CHILD_PATH = "/usr/bin:/bin"
CONNECTION_VAR = "PADRAO_VALOR_RUN_CONEXAO_BD"
SSS_CONNECTION_VAR = "SSS_ENVIRONMENT_CONNECTION"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"
PLATFORMS = ("LINUX", "UNIX")


def script_work_dir(work_dir_ticket):
    """cwd/HOME do script (README §8.4 passo 2): work_dir/ticket_<id>/exec, com a conta do agente (CR-032, D7)."""
    return os.path.join(work_dir_ticket, "exec")


def _passthrough(names, environ_daemon):
    env = {}
    for name in names or ():
        if sss_config.is_blocked_variable(name):
            # O config ja recusa na subida; aqui e defesa em profundidade (README §8.6).
            raise ValueError("Variavel bloqueada no env_passthrough: %s" % name)
        if name in environ_daemon:
            env[name] = environ_daemon[name]
    return env


def _connection(secrets, environment, ticket_id):
    """(usuario, connect string) do ambiente, ou (usuario ou None, None) sem DSN ou sem credencial."""
    name = environment["name"]
    dsn = (environment.get("connection") or "").strip()
    cred = (getattr(secrets, "environments", None) or {}).get(name)
    user = cred.user if cred is not None else None
    if not dsn or cred is None:
        _log.warning("%s omitida: ambiente %s sem %s", CONNECTION_VAR, name,
                     "DSN" if not dsn else "credencial [environment:%s] no secrets.cfg" % name,
                     extra={"ticket": ticket_id, "action": "SPAWN"})
        return user, None
    value = "%s/%s@%s" % (cred.user, cred.password, dsn)
    masking.register_secret(cred.password)
    masking.register_secret(value)
    return user, value


def _date(value):
    if value is None:
        return None
    return value.strftime(_DATE_FMT) if hasattr(value, "strftime") else str(value)


def _set(env, name, value):
    """Define SSS_* so com valor (CR-010): None ou texto vazio deixam a variavel ausente."""
    if value is None:
        return
    text = str(value)
    if text.strip() and "\x00" not in text:
        env[name] = text


def build(cfg, secrets, ticket, environment, script_real, work_dir_ticket, environ_daemon, platform_name,
              snapshot=None, schedule=None, log_path=None, timeout_sec=None, hostname=None, version=None,
              output_dir=None, input_dir=None, work_folder=None):
    """Ambiente exato do filho (README §8.6, tabela POSIX; CR-010). Variavel bloqueada: ValueError.

    ticket: dict com id, ambiente e, quando houver, parent_ticket_id, schedule_id, prioridade, started_at
    (relogio do banco, devolvido pelo claim) e scheduled_at; ambiente: dict com nome, descricao e conexao
    (tbsss_environments); script_real: o caminho resolvido pelo path_guard; environ_daemon: o ambiente do daemon
    (so para TZ e env_passthrough); snapshot: o snapshot v4 (script_id, script_name, interpretador);
    agendamento: dict com nome e tipo_recorrencia da regra que gerou o ticket; log_path: o
    .log.parcial aberto por executor.open_log; timeout_seg: o prazo efetivo; hostname e versao: do agente;
    output_dir: a pasta de saida do ticket (CR-012), so quando o agente tem output_dir.
    input_dir: a pasta de entrada do script (CR-014), so quando o agente tem input_dir.
    work_folder: a pasta de trabalho do ticket (CR-019), so quando o agente tem script_work_dir.
    """
    if platform_name not in PLATFORMS:
        raise ValueError("Plataforma nao suportada: %s" % platform_name)
    if not isinstance(script_real, str) or not script_real.startswith("/"):
        raise ValueError("script_real deve ser absoluto")
    ticket_id = int(ticket["id"])
    agent = cfg.agent
    home = script_work_dir(work_dir_ticket)
    snap = snapshot or {}

    env = _passthrough(agent.env_passthrough, environ_daemon)
    env.update({
        "PATH": CHILD_PATH,
        "HOME": home,
        "TMPDIR": os.path.join(home, "tmp"),
        "LANG": agent.child_locale,
        "LC_ALL": agent.child_locale,
        # Efeito so em BASH/SH chamando python sem -I; o PYTHON3 roda com -I (CR-007, R-17).
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "SSS_TICKET_ID": str(ticket_id),
        "SSS_ENVIRONMENT": environment["name"],
        "SSS_AGENT_ID": agent.agent_id,
        "SSS_SCRIPT_DIR": os.path.dirname(script_real),
        "SSS_SCRIPT_FILE": script_real,
        "SSS_PLATFORM": platform_name,
    })
    if environ_daemon.get("TZ"):
        env["TZ"] = environ_daemon["TZ"]

    # Execucao (CR-010).
    scheduled = ticket.get("schedule_id") is not None
    env["SSS_EXECUTION_TYPE"] = "AGENDADA" if scheduled else "MANUAL"
    _set(env, "SSS_PARENT_TICKET_ID", ticket.get("parent_ticket_id"))
    _set(env, "SSS_PRIORITY", ticket.get("priority"))
    _set(env, "SSS_STARTED_AT", _date(ticket.get("started_at")))
    _set(env, "SSS_SCHEDULED_AT", _date(ticket.get("scheduled_at")))
    _set(env, "SSS_TIMEOUT_SECONDS", timeout_sec)
    if scheduled:
        _set(env, "SSS_SCHEDULE_ID", ticket.get("schedule_id"))
        _set(env, "SSS_SCHEDULE_NAME", (schedule or {}).get("name"))
        _set(env, "SSS_RECURRENCE", (schedule or {}).get("recurrence_type"))
    # Script, log e agente.
    # CR-011: com link simbolico no caminho, o cadastrado vai em SSS_SCRIPT_LINK; o real nos demais.
    # CR-023: o cadastrado relativo entra ja junto da pasta base (nunca chega relativo ao script).
    if snap.get("path_file"):
        typed = snap["path_file"]
        base = getattr(cfg.agent, "script_base_dir", None)
        if typed[:1] != "/" and base:
            typed = os.path.join(base, typed)
        if typed != script_real:
            _set(env, "SSS_SCRIPT_LINK", typed)
    _set(env, "SSS_SCRIPT_ID", snap.get("script_id"))
    _set(env, "SSS_SCRIPT_NAME", snap.get("script_name"))
    # CR-026f: o nome do cadastro, inclusive nos tickets v5/v6 ainda na fila (PYTHON3 -> python3).
    _set(env, "SSS_INTERPRETER", params_compiler.interpreter_name(snap.get("interpreter")))
    if log_path:
        _set(env, "SSS_LOG_DIR", os.path.dirname(log_path))
        _set(env, "SSS_LOG_FILE", os.path.basename(log_path))
    _set(env, "SSS_OUTPUT_DIR", output_dir)
    _set(env, "SSS_INPUT_DIR", input_dir)
    _set(env, "SSS_WORK_DIR", work_folder)
    _set(env, "SSS_AGENT_HOST", hostname)
    _set(env, "SSS_VERSION", version)
    # Ambiente: descricao, DSN (sem credencial), usuario e a connect string (mascarada em todo log).
    _set(env, "SSS_ENVIRONMENT_DESCRIPTION", environment.get("description"))
    _set(env, "SSS_ENVIRONMENT_DSN", (environment.get("connection") or "").strip() or None)
    user_db, connection = _connection(secrets, environment, ticket_id)
    _set(env, "SSS_ENVIRONMENT_USER", user_db)
    if connection is not None:
        env[CONNECTION_VAR] = connection
        env[SSS_CONNECTION_VAR] = connection
    return env
