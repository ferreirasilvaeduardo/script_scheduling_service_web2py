# -*- coding: utf-8 -*-
"""Carga e validacao tipada da configuracao do SSS e de segredos.

Compativel estritamente com Python 3.6. Sem dependencias externas.
Valida todas as secoes e chaves do README §12.1 e §4.1 de forma declarativa e fail-fast.
"""
import collections
import configparser
import logging
import os
import re
import sys


# Variaveis que nunca passam do daemon para o script (README §8.6, CR-007 R-32).
BLOCKED_ENV_VARS = frozenset([
    "LD_PRELOAD", "LD_AUDIT", "PYTHONPATH", "PYTHONHOME",
    "PYTHONSTARTUP", "PYTHONINSPECT", "BASH_ENV", "ENV",
    "SHELLOPTS", "BASHOPTS", "IFS", "PERL5LIB", "PERL5OPT",
    "GCONV_PATH", "LOCPATH", "NLSPATH", "HOSTALIASES", "GLIBC_TUNABLES",
    "PS4", "PROMPT_COMMAND", "CDPATH", "GLOBIGNORE",
])
# Prefixos bloqueados: LD_* (exceto LD_LIBRARY_PATH), BASH_FUNC_* e MALLOC_*.
_BLOCKED_PREFIXES = ("LD_", "BASH_FUNC_", "MALLOC_")
_ALLOWED_LD = "LD_LIBRARY_PATH"
# Chaves que o agente define e que o env_passthrough nao pode sobrescrever (README §8.6).
_FIXED_KEYS = frozenset(["PATH", "HOME", "TMPDIR", "LANG", "TZ", "PADRAO_VALOR_RUN_CONEXAO_BD"])
_FIXED_PREFIXES = ("LC_", "SSS_", "PYTHON")

# Versao do SSS: unico lugar (tbsss_agentes.versao e SSS_VERSION do script, CR-010). Trocada a cada release.
SSS_VERSION = "1.0.0-dev"

# Chaves que existiram e foram retiradas: recusadas com orientacao, para nao serem ignoradas em silencio.
REMOVED_KEYS = {
    ("app", "data_backend"): "a aplicacao usa sempre o Oracle do [oracle] (owner e table_prefix) (F7.3)",
    ("agent", "script_owner_uids"): "o SSS nao confere mais o dono dos scripts; o ambiente controla o conteudo (CR-011)",
    ("agent", "ambientes_exigem_hash"): "o SSS nao confere mais o hash dos scripts (CR-011)",
}

# Chaves com nome novo (CR-015a): o config.ini antigo e recusado com o nome a usar, sem aceitar o antigo.
RENAMED_KEYS = {
    ("agent", "saida_dir"): "output_dir",
    ("agent", "saida_max_bytes"): "output_max_bytes",
    ("agent", "saida_max_arquivos"): "output_max_files",
    ("agent", "entrada_dir"): "input_dir",
    ("logging", "saida_retention_days"): "output_retention_days",
    # CR-016b: configuracao e operacao em ingles
    ("oracle", "modo_driver"): "driver_mode",
    ("agent", "ambientes_atendidos"): "environments",
    ("agent", "usuarios_execucao"): "exec_users",
    ("agent", "interpretadores"): "interpreters",
    ("agent", "fila_envelhecimento_min"): "queue_aging_min",
    ("agent", "log_dir_min_livre_mb"): "log_dir_min_free_mb",
    ("web", "sessao_max_horas"): "session_max_hours",
    ("web", "login_max_tentativas"): "login_max_attempts",
    ("web", "login_bloqueio_s"): "login_lockout_s",
}

# Secoes com nome novo (CR-016b), no config.ini e no secrets.cfg ([ambiente:X] -> [environment:X]).
RENAMED_SECTIONS = {"retencao": "retention", "ambiente:": "environment:"}

# Atores do sistema que nao podem ser agent_id (README §4.4 e §8.12).
RESERVED_AGENT_IDS = ("init_db", "seed", "purge")
_RE_EXEC_USER = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_ENVIRONMENTS_MAX = 1000
ROLES = ("web", "agent", "monitor")

_log = logging.getLogger("sss_config")


def is_blocked_variable(name):
    """Verdadeiro se a variavel nao pode ir para o ambiente do script (lista de bloqueio ou chave fixa)."""
    high = name.upper()
    if high in BLOCKED_ENV_VARS:
        return True
    if high.startswith(_BLOCKED_PREFIXES) and high != _ALLOWED_LD:
        return True
    return high in _FIXED_KEYS or high.startswith(_FIXED_PREFIXES)


class ConfigError(Exception):
    """Excecao para falhas de configuracao e validacao tipada."""

    def __init__(self, section=None, key=None, reason=None):
        if key is None and reason is None and section is not None:
            self.reason = str(section)
            self.section = None
            self.key = None
        else:
            self.section = section
            self.key = key
            self.reason = reason

        parts = []
        if self.section:
            parts.append("[%s]" % self.section)
        if self.key:
            parts.append(self.key)
        if self.reason:
            parts.append(str(self.reason))
        msg = ": ".join(parts) if parts else "Erro de configuracao"
        super(ConfigError, self).__init__(msg)


class FieldDef(object):
    """Definicao declarativa de um campo de configuracao."""

    __slots__ = (
        "kind", "required", "min_val", "max_val",
        "allowed_values", "regex", "default"
    )

    def __init__(self, kind, required=True, min_val=None, max_val=None,
                 allowed_values=None, regex=None, default=None):
        self.kind = kind  # 'str', 'int', 'bool', 'enum', 'list_csv', 'path'
        self.required = required
        self.min_val = min_val
        self.max_val = max_val
        self.allowed_values = tuple(allowed_values) if allowed_values else None
        self.regex = regex
        self.default = default


# Esquema declarativo completo de todas as secoes e chaves (README §12.1)
SCHEMA = collections.OrderedDict([
    ("app", collections.OrderedDict([
        ("sss_env", FieldDef("enum", required=True, allowed_values=("DEV", "HML", "PROD"))),
    ])),
    ("oracle", collections.OrderedDict([
        ("user", FieldDef("str", required=True)),
        ("dsn", FieldDef("str", required=True)),
        ("owner", FieldDef("str", required=True, regex=r"^[A-Za-z][A-Za-z0-9_]{0,29}$")),
        # So minusculas: o registro de identificadores so aceita nomes em minusculas (CR-007, R-31).
        ("table_prefix", FieldDef("str", required=True, regex=r"^[a-z][a-z0-9_]{0,7}$")),
        ("driver_mode", FieldDef("enum", required=False, allowed_values=("auto", "thin", "thick", "cx_oracle"), default="auto")),
        ("oracle_client_lib_dir", FieldDef("path", required=False, default=None)),
        ("call_timeout_ms", FieldDef("int", required=True, min_val=1, max_val=3600000)),
        ("pool_min", FieldDef("int", required=True, min_val=1, max_val=1000)),
        ("pool_max", FieldDef("int", required=True, min_val=1, max_val=1000)),
    ])),
    ("secrets", collections.OrderedDict([
        ("secrets_file", FieldDef("path", required=True)),
    ])),
    ("agent", collections.OrderedDict([
        # init_db, seed e purge sao atores reservados do sistema (README §4.4 e §8.12).
        ("agent_id", FieldDef("str", required=True, regex=r"^(?!(?:init_db|seed|purge)$)[A-Za-z0-9._-]{1,30}$")),
        ("environments", FieldDef("list_csv", required=True)),
        ("work_dir", FieldDef("path", required=True)),
        # Usuario do SO por ambiente e pasta base dos diretorios de trabalho dos scripts (CR-007, D1):
        # obrigatorios fora de DEV (validacao cruzada em carregar()).
        ("exec_users", FieldDef("map_csv", required=False, default=())),
        ("interpreters", FieldDef("map_csv", required=False, default=())),
        ("exec_work_dir", FieldDef("path", required=False, default=None)),
        ("max_parallel_jobs", FieldDef("int", required=True, min_val=1, max_val=999)),
        ("max_parallel_hard_limit", FieldDef("int", required=True, min_val=1, max_val=999)),
        ("claim_batch_size", FieldDef("int", required=True, min_val=1, max_val=1000)),
        ("schedule_batch_size", FieldDef("int", required=True, min_val=1, max_val=1000)),
        ("orchestrator_interval_s", FieldDef("int", required=True, min_val=1, max_val=3600)),
        ("cancel_poll_interval_s", FieldDef("int", required=True, min_val=1, max_val=3600)),
        ("heartbeat_interval_s", FieldDef("int", required=True, min_val=1, max_val=3600)),
        ("fence_timeout_s", FieldDef("int", required=True, min_val=1, max_val=86400)),
        ("node_offline_timeout_s", FieldDef("int", required=True, min_val=1, max_val=86400)),
        ("kill_grace_s", FieldDef("int", required=True, min_val=1, max_val=300)),
        ("script_timeout_s", FieldDef("int", required=True, min_val=1, max_val=86400)),
        ("shutdown_mode", FieldDef("enum", required=True, allowed_values=("TERMINATE", "DRAIN"))),
        ("shutdown_grace_s", FieldDef("int", required=True, min_val=1, max_val=3600)),
        ("misfire_policy", FieldDef("enum", required=True, allowed_values=("RUN_ONCE", "SKIP"))),
        ("misfire_tolerance_s", FieldDef("int", required=True, min_val=1, max_val=86400)),
        # Minimo 1461 (4 anos): cobre o 29/02 de regras CRON anuais (CR-008, R-32).
        ("cron_horizon_days", FieldDef("int", required=True, min_val=1461, max_val=36500)),
        ("queue_aging_min", FieldDef("int", required=False, min_val=0, max_val=1440, default=60)),
        # CR-008, R-25: espaco minimo do log_dir.
        ("log_dir_min_free_mb", FieldDef("int", required=False, min_val=0, max_val=1048576, default=1024)),
        # CR-012: pasta de saida dos scripts (vazio desliga) e limites do zip (README §8.13).
        ("output_dir", FieldDef("path", required=False, default=None)),
        ("output_max_bytes", FieldDef("int", required=False, min_val=1048576, max_val=209715200, default=20971520)),
        ("output_max_files", FieldDef("int", required=False, min_val=1, max_val=10000, default=1000)),
        # CR-014: pasta de entrada dos scripts, permanente, uma por ambiente e script (vazio desliga; README §8.14).
        ("input_dir", FieldDef("path", required=False, default=None)),
        # CR-019: pasta de trabalho dos scripts, por ticket, com as partes da pasta de saida (vazio desliga; README §8.15).
        ("script_work_dir", FieldDef("path", required=False, default=None)),
        ("child_locale", FieldDef("str", required=True)),
        ("env_passthrough", FieldDef("list_csv", required=False, default=())),
    ])),
    ("logging", collections.OrderedDict([
        ("log_dir", FieldDef("path", required=True)),
        ("level", FieldDef("enum", required=True, allowed_values=("DEBUG", "INFO", "WARN", "ERROR"))),
        ("app_log_max_bytes", FieldDef("int", required=True, min_val=1024, max_val=1073741824)),
        ("app_log_retention_days", FieldDef("int", required=True, min_val=1, max_val=3650)),
        ("max_log_size_bytes", FieldDef("int", required=True, min_val=1024, max_val=67108864)),
        ("max_local_log_size_bytes", FieldDef("int", required=True, min_val=1024, max_val=10737418240)),
        ("local_log_retention_days", FieldDef("int", required=True, min_val=1, max_val=3650)),
        # CR-012: pastas de saida que ficaram no disco (excesso ou falha).
        ("output_retention_days", FieldDef("int", required=False, min_val=1, max_val=365, default=7)),
        # CR-019: pastas de trabalho dos scripts, que ficam no disco depois do ticket.
        ("script_work_retention_days", FieldDef("int", required=False, min_val=1, max_val=365, default=7)),
    ])),
    ("web", collections.OrderedDict([
        ("session_idle_timeout_s", FieldDef("int", required=True, min_val=1, max_val=86400)),
        ("session_max_hours", FieldDef("int", required=False, min_val=1, max_val=168, default=12)),
        ("login_max_attempts", FieldDef("int", required=True, min_val=1, max_val=99)),
        ("login_lockout_s", FieldDef("int", required=True, min_val=1, max_val=86400)),
        ("log_poll_interval_s", FieldDef("int", required=True, min_val=1, max_val=3600)),
        ("trusted_proxies", FieldDef("list_csv", required=False, default=())),
        ("allowed_origins", FieldDef("list_csv", required=True)),
        # CR-020d: tamanho maximo do arquivo enviado pela tela de Entrada (o POST maior e recusado antes de ser lido).
        ("input_upload_max_bytes", FieldDef("int", required=False, min_val=1048576, max_val=209715200,
                                            default=52428800)),
    ])),
    ("retention", collections.OrderedDict([
        ("ticket_retention_days", FieldDef("int", required=True, min_val=1, max_val=3650)),
        ("audit_retention_days", FieldDef("int", required=True, min_val=365, max_val=3650)),
        ("purge_batch_size", FieldDef("int", required=True, min_val=1, max_val=100000)),
        # CR-020e: envios da tela de Entrada apagados depois de N dias (o conteudo sai antes, apos as entregas).
        ("input_retention_days", FieldDef("int", required=False, min_val=1, max_val=3650, default=30)),
        ("purge_user", FieldDef("str", required=False, default=None, regex=r"^[A-Za-z][A-Za-z0-9_$#]{0,29}$")),
    ])),
])


class _ItemAccessMixin(object):
    """Mixin para permitir acesso indexado por nome de atributo."""

    def __getitem__(self, item):
        if isinstance(item, str):
            try:
                return getattr(self, item)
            except AttributeError:
                raise KeyError(item)
        return super(_ItemAccessMixin, self).__getitem__(item)


class AppConfig(_ItemAccessMixin, collections.namedtuple("AppConfig", ["sss_env"])):
    __slots__ = ()


class OracleConfig(_ItemAccessMixin, collections.namedtuple("OracleConfig", [
    "user", "dsn", "owner", "table_prefix", "driver_mode",
    "oracle_client_lib_dir", "call_timeout_ms",
    "pool_min", "pool_max"
])):
    __slots__ = ()


class SecretsConfig(_ItemAccessMixin, collections.namedtuple("SecretsConfig", ["secrets_file"])):
    __slots__ = ()


class AgentConfig(_ItemAccessMixin, collections.namedtuple("AgentConfig", [
    "agent_id", "environments", "work_dir",
    "max_parallel_jobs", "max_parallel_hard_limit",
    "claim_batch_size", "schedule_batch_size", "orchestrator_interval_s",
    "cancel_poll_interval_s", "heartbeat_interval_s", "fence_timeout_s",
    "node_offline_timeout_s", "kill_grace_s", "script_timeout_s",
    "shutdown_mode", "shutdown_grace_s", "misfire_policy",
    "misfire_tolerance_s", "cron_horizon_days", "child_locale",
    "env_passthrough", "exec_users", "interpreters", "exec_work_dir", "queue_aging_min",
    "log_dir_min_free_mb", "output_dir", "output_max_bytes", "output_max_files", "input_dir",
    "script_work_dir"
])):
    __slots__ = ()


class LoggingConfig(_ItemAccessMixin, collections.namedtuple("LoggingConfig", [
    "log_dir", "level", "app_log_max_bytes", "app_log_retention_days",
    "max_log_size_bytes", "max_local_log_size_bytes", "local_log_retention_days", "output_retention_days",
    "script_work_retention_days"
])):
    __slots__ = ()


class WebConfig(_ItemAccessMixin, collections.namedtuple("WebConfig", [
    "session_idle_timeout_s", "session_max_hours", "login_max_attempts", "login_lockout_s",
    "log_poll_interval_s", "trusted_proxies", "allowed_origins", "input_upload_max_bytes"
])):
    __slots__ = ()


class RetentionConfig(_ItemAccessMixin, collections.namedtuple("RetentionConfig", [
    "ticket_retention_days", "audit_retention_days", "purge_batch_size", "purge_user", "input_retention_days"
])):
    __slots__ = ()


class Config(_ItemAccessMixin, collections.namedtuple("Config", [
    "app", "oracle", "secrets", "agent", "logging", "web", "retention"
])):
    __slots__ = ()


def _convert_value(section_name, key_name, cdef, raw_val):
    """Converte e valida um valor individual com base em CampoDef."""
    if raw_val is None:
        if cdef.required:
            raise ConfigError(section_name, key_name, "Chave obrigatoria ausente")
        return cdef.default

    val_str = str(raw_val).strip()

    if cdef.kind == "str":
        if not val_str:
            if cdef.required:
                raise ConfigError(section_name, key_name, "Valor obrigatorio nao pode ser vazio")
            return cdef.default
        if cdef.regex and not re.fullmatch(cdef.regex, val_str):
            raise ConfigError(
                section_name, key_name,
                "Valor '%s' nao atende ao padrao exigido '%s'" % (val_str, cdef.regex)
            )
        return val_str

    elif cdef.kind == "path":
        if not val_str:
            if cdef.required:
                raise ConfigError(section_name, key_name, "Caminho obrigatorio nao pode ser vazio")
            return cdef.default
        return os.path.normpath(val_str)

    elif cdef.kind == "int":
        if not val_str:
            if cdef.required:
                raise ConfigError(section_name, key_name, "Valor inteiro obrigatorio ausente")
            return cdef.default
        try:
            val_int = int(val_str)
        except ValueError:
            raise ConfigError(section_name, key_name, "Valor inteiro invalido: '%s'" % val_str)

        if cdef.min_val is not None and val_int < cdef.min_val:
            raise ConfigError(
                section_name, key_name,
                "Valor %d abaixo do minimo permitido (%d)" % (val_int, cdef.min_val)
            )
        if cdef.max_val is not None and val_int > cdef.max_val:
            raise ConfigError(
                section_name, key_name,
                "Valor %d acima do maximo permitido (%d)" % (val_int, cdef.max_val)
            )
        return val_int

    elif cdef.kind == "bool":
        if not val_str:
            if cdef.required:
                raise ConfigError(section_name, key_name, "Valor booleano obrigatorio ausente")
            return cdef.default
        low = val_str.lower()
        if low in ("true", "1", "yes", "on"):
            return True
        elif low in ("false", "0", "no", "off"):
            return False
        raise ConfigError(section_name, key_name, "Valor booleano invalido: '%s'" % val_str)

    elif cdef.kind == "enum":
        if not val_str:
            if cdef.required:
                raise ConfigError(section_name, key_name, "Valor obrigatorio ausente")
            return cdef.default
        if cdef.allowed_values and val_str not in cdef.allowed_values:
            raise ConfigError(
                section_name, key_name,
                "Valor '%s' invalido. Permitidos: %s" % (
                    val_str, ", ".join(cdef.allowed_values)
                )
            )
        return val_str

    elif cdef.kind == "list_csv":
        if not val_str:
            if cdef.required:
                raise ConfigError(section_name, key_name, "Lista obrigatoria nao pode ser vazia")
            return cdef.default

        parts = [p.strip() for p in val_str.split(",") if p.strip()]
        if cdef.required and not parts:
            raise ConfigError(section_name, key_name, "Lista obrigatoria nao pode ser vazia")

        return tuple(parts)

    elif cdef.kind == "map_csv":
        # "CHAVE=valor,CHAVE=valor" -> tupla de pares, na ordem, sem chave repetida.
        if not val_str:
            if cdef.required:
                raise ConfigError(section_name, key_name, "Lista obrigatoria nao pode ser vazia")
            return cdef.default
        pairs = []
        seen = set()
        for item in [p.strip() for p in val_str.split(",") if p.strip()]:
            if item.count("=") != 1:
                raise ConfigError(section_name, key_name, "Item invalido (esperado CHAVE=valor): '%s'" % item)
            k, v = [x.strip() for x in item.split("=")]
            if not k or not v:
                raise ConfigError(section_name, key_name, "Item invalido (esperado CHAVE=valor): '%s'" % item)
            if k in seen:
                raise ConfigError(section_name, key_name, "Chave repetida: '%s'" % k)
            seen.add(k)
            pairs.append((k, v))
        return tuple(pairs)

    raise ConfigError(section_name, key_name, "Tipo de campo desconhecido no schema: '%s'" % cdef.kind)


def load(ini_path):
    """Carrega e valida o config.ini de forma declarativa e fail-fast.

    Retorna uma instancia imutavel de Config.
    """
    if not os.path.exists(ini_path):
        raise ConfigError(reason="Arquivo de configuracao nao encontrado: %s" % ini_path)

    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
    try:
        with open(ini_path, "r", encoding="utf-8") as f:
            cp.read_file(f)
    except Exception as e:
        raise ConfigError(reason="Erro ao ler arquivo de configuracao %s: %s" % (ini_path, e))

    # 1. Validar secoes desconhecidas
    for sec in cp.sections():
        if sec in RENAMED_SECTIONS:
            raise ConfigError(section=sec, key=None, reason="Secao renomeada: [%s] passou a se chamar [%s] (CR-016b)"
                             % (sec, RENAMED_SECTIONS[sec]))
        if sec not in SCHEMA:
            raise ConfigError(section=sec, key=None, reason="Secao desconhecida no config.ini: [%s]" % sec)

    # 2. Validar presenca e chaves de cada secao
    data_sections = {}
    for sec_name, sec_fields in SCHEMA.items():
        if sec_name not in cp.sections():
            raise ConfigError(section=sec_name, key=None, reason="Secao obrigatoria ausente: [%s]" % sec_name)

        cp_sec = cp[sec_name]

        # Chaves desconhecidas na secao
        for k in cp_sec:
            if (sec_name, k) in REMOVED_KEYS:
                raise ConfigError(section=sec_name, key=k, reason="Chave removida: %s; apague a linha %s" % (
                    REMOVED_KEYS[(sec_name, k)], k))
            if (sec_name, k) in RENAMED_KEYS:
                raise ConfigError(section=sec_name, key=k, reason="Chave renomeada: %s passou a se chamar %s (CR-015a)"
                                 % (k, RENAMED_KEYS[(sec_name, k)]))
            if k not in sec_fields:
                raise ConfigError(section=sec_name, key=k, reason="Chave desconhecida na secao [%s]: %s" % (sec_name, k))

        # Validar e converter cada chave esperada
        data_sec = {}
        for k, cdef in sec_fields.items():
            if k not in cp_sec:
                if cdef.required:
                    raise ConfigError(
                        section=sec_name, key=k,
                        reason="Chave obrigatoria ausente na secao [%s]: %s" % (sec_name, k)
                    )
                data_sec[k] = cdef.default
            else:
                raw = cp_sec[k]
                data_sec[k] = _convert_value(sec_name, k, cdef, raw)

        data_sections[sec_name] = data_sec

    # 3. Validacao de env_passthrough contra a lista de bloqueio e as chaves fixas (README §8.6)
    agent_dict = data_sections["agent"]
    for env_var in agent_dict["env_passthrough"]:
        if is_blocked_variable(env_var):
            raise ConfigError(
                section="agent", key="env_passthrough",
                reason="Variavel bloqueada nao permitida em env_passthrough: '%s'" % env_var
            )

    # 4. Invariantes
    app_dict = data_sections["app"]
    oracle_dict = data_sections["oracle"]
    if oracle_dict["pool_min"] > oracle_dict["pool_max"]:
        raise ConfigError(
            section="oracle", key="pool_min",
            reason="pool_min (%d) nao pode ser maior que pool_max (%d)" % (
                oracle_dict["pool_min"], oracle_dict["pool_max"]
            )
        )

    if agent_dict["max_parallel_jobs"] > agent_dict["max_parallel_hard_limit"]:
        raise ConfigError(
            section="agent", key="max_parallel_jobs",
            reason="max_parallel_jobs (%d) nao pode ser maior que max_parallel_hard_limit (%d)" % (
                agent_dict["max_parallel_jobs"], agent_dict["max_parallel_hard_limit"]
            )
        )

    if agent_dict["fence_timeout_s"] * 2 > agent_dict["node_offline_timeout_s"]:
        raise ConfigError(
            section="agent", key="fence_timeout_s",
            reason="Invariante violada: fence_timeout_s * 2 (%d) deve ser <= node_offline_timeout_s (%d)" % (
                agent_dict["fence_timeout_s"] * 2, agent_dict["node_offline_timeout_s"]
            )
        )

    if agent_dict["heartbeat_interval_s"] * 3 > agent_dict["fence_timeout_s"]:
        raise ConfigError(
            section="agent", key="heartbeat_interval_s",
            reason="Invariante violada: heartbeat_interval_s * 3 (%d) deve ser <= fence_timeout_s (%d)" % (
                agent_dict["heartbeat_interval_s"] * 3, agent_dict["fence_timeout_s"]
            )
        )

    _validate_cr007(app_dict, oracle_dict, agent_dict, data_sections["logging"], data_sections["retention"])

    # 5. Instanciar arvore de configuracao imutavel
    app_cfg = AppConfig(**app_dict)
    oracle_cfg = OracleConfig(**oracle_dict)
    secrets_cfg = SecretsConfig(**data_sections["secrets"])
    agent_cfg = AgentConfig(**agent_dict)
    logging_cfg = LoggingConfig(**data_sections["logging"])
    web_cfg = WebConfig(**data_sections["web"])
    retention_cfg = RetentionConfig(**data_sections["retention"])

    return Config(
        app=app_cfg,
        oracle=oracle_cfg,
        secrets=secrets_cfg,
        agent=agent_cfg,
        logging=logging_cfg,
        web=web_cfg,
        retention=retention_cfg
    )


def call_timeout_s(call_timeout_ms):
    """call_timeout_ms arredondado para cima em segundos (invariantes I3 e I4, README §8.9)."""
    return (int(call_timeout_ms) + 999) // 1000


def _inside(path, folder):
    path, folder = os.path.normpath(path), os.path.normpath(folder)
    return os.path.commonpath([path, folder]) == folder


def _validate_cr007(app, oracle, agent, logging_dict, retention):
    """Validacoes cruzadas do CR-007: invariantes I3/I4, execucao, retencao e purge."""
    call_s = call_timeout_s(oracle["call_timeout_ms"])
    i3 = agent["heartbeat_interval_s"] + 2 * call_s
    if i3 > agent["fence_timeout_s"]:
        raise ConfigError(
            section="agent", key="fence_timeout_s",
            reason="Invariante I3 violada: heartbeat_interval_s + 2 * call_timeout_s (%d) deve ser <= "
                   "fence_timeout_s (%d) (README §8.9)" % (i3, agent["fence_timeout_s"]))
    i4 = agent["fence_timeout_s"] + call_s + agent["kill_grace_s"] + 2
    if i4 > agent["node_offline_timeout_s"]:
        raise ConfigError(
            section="agent", key="node_offline_timeout_s",
            reason="Invariante I4 violada: fence_timeout_s + call_timeout_s + kill_grace_s + 2 (%d) deve ser <= "
                   "node_offline_timeout_s (%d) (README §8.9)" % (i4, agent["node_offline_timeout_s"]))

    if len(",".join(agent["environments"])) > _ENVIRONMENTS_MAX:
        raise ConfigError(section="agent", key="environments",
                         reason="Lista com mais de %d caracteres (coluna tbsss_agentes.ambientes)" % _ENVIRONMENTS_MAX)

    for logical, executable in agent["interpreters"]:
        # Allowlist do path_guard (README §6.4); o executavel e conferido pelo agente na subida (§8.5).
        if logical not in ("PYTHON3", "BASH", "SH"):
            raise ConfigError(section="agent", key="interpreters",
                             reason="Interpretador fora da allowlist (PYTHON3, BASH, SH): '%s'" % logical)
        if not executable.startswith("/") or os.path.normpath(executable) != executable:
            raise ConfigError(section="agent", key="interpreters",
                             reason="Executavel de %s deve ser caminho absoluto e normalizado" % logical)

    dev = app["sss_env"] == "DEV"
    users = dict(agent["exec_users"])
    for env, usr in agent["exec_users"]:
        if env not in agent["environments"]:
            raise ConfigError(section="agent", key="exec_users",
                             reason="Ambiente '%s' nao esta em environments" % env)
        if not _RE_EXEC_USER.match(usr) or usr == "root":
            raise ConfigError(section="agent", key="exec_users",
                             reason="Usuario de execucao invalido para '%s'" % env)
    if not dev:
        missing = [a for a in agent["environments"] if a not in users]
        if missing:
            raise ConfigError(section="agent", key="exec_users",
                             reason="Fora de DEV, todo ambiente atendido precisa de usuario de execucao: %s"
                                    % ", ".join(missing))
        if not agent["exec_work_dir"]:
            raise ConfigError(section="agent", key="exec_work_dir", reason="Obrigatorio fora de DEV (CR-007, D1)")
    if agent["exec_work_dir"]:
        for name, other in (("work_dir", agent["work_dir"]), ("log_dir", logging_dict["log_dir"])):
            if _inside(agent["exec_work_dir"], other) or _inside(other, agent["exec_work_dir"]):
                raise ConfigError(section="agent", key="exec_work_dir",
                                 reason="Nao pode ficar dentro de %s nem conte-lo" % name)
    if agent["output_dir"]:
        # CR-012: a pasta de saida nao se sobrepoe as pastas do SSS (README §8.13).
        if not os.path.isabs(agent["output_dir"]):
            raise ConfigError(section="agent", key="output_dir", reason="Deve ser um caminho absoluto")
        for name, other in (("work_dir", agent["work_dir"]), ("log_dir", logging_dict["log_dir"]),
                            ("exec_work_dir", agent["exec_work_dir"])):
            if other and (_inside(agent["output_dir"], other) or _inside(other, agent["output_dir"])):
                raise ConfigError(section="agent", key="output_dir",
                                 reason="Nao pode ficar dentro de %s nem conte-lo" % name)
    if agent["input_dir"]:
        # CR-014: a pasta de entrada nao se sobrepoe as pastas do SSS nem a de saida (README §8.14).
        if not os.path.isabs(agent["input_dir"]):
            raise ConfigError(section="agent", key="input_dir", reason="Deve ser um caminho absoluto")
        for name, other in (("work_dir", agent["work_dir"]), ("log_dir", logging_dict["log_dir"]),
                            ("exec_work_dir", agent["exec_work_dir"]), ("output_dir", agent["output_dir"])):
            if other and (_inside(agent["input_dir"], other) or _inside(other, agent["input_dir"])):
                raise ConfigError(section="agent", key="input_dir",
                                 reason="Nao pode ficar dentro de %s nem conte-lo" % name)
    if agent["script_work_dir"]:
        # CR-019: a pasta de trabalho nao se sobrepoe as pastas do SSS, a de saida nem a de entrada (README §8.15).
        if not os.path.isabs(agent["script_work_dir"]):
            raise ConfigError(section="agent", key="script_work_dir", reason="Deve ser um caminho absoluto")
        for name, other in (("work_dir", agent["work_dir"]), ("log_dir", logging_dict["log_dir"]),
                            ("exec_work_dir", agent["exec_work_dir"]), ("output_dir", agent["output_dir"]),
                            ("input_dir", agent["input_dir"])):
            if other and (_inside(agent["script_work_dir"], other) or _inside(other, agent["script_work_dir"])):
                raise ConfigError(section="agent", key="script_work_dir",
                                 reason="Nao pode ficar dentro de %s nem conte-lo" % name)

    if retention["audit_retention_days"] < retention["ticket_retention_days"]:
        raise ConfigError(section="retention", key="audit_retention_days",
                         reason="audit_retention_days (%d) deve ser >= ticket_retention_days (%d)" % (
                             retention["audit_retention_days"], retention["ticket_retention_days"]))
    if app["sss_env"] != "DEV" and oracle["user"].upper() == oracle["owner"].upper():
        # CR-008, R-29: a conta da aplicacao nunca e a dona do esquema fora de DEV (D1b do CR-007).
        raise ConfigError(section="oracle", key="user",
                         reason="Fora de DEV, a conta da aplicacao deve ser diferente do owner do esquema")
    purge = retention["purge_user"]
    if not purge:
        # Em DEV, purge_user vazio significa purge desligado (scripts/purge.py recusa rodar; README §12.1).
        if app["sss_env"] != "DEV":
            raise ConfigError(section="retention", key="purge_user", reason="Obrigatorio fora de DEV")
    elif purge.upper() in (oracle["user"].upper(), oracle["owner"].upper()):
            raise ConfigError(section="retention", key="purge_user",
                             reason="A conta de purge deve ser diferente da conta do processo e do owner")


def check_encoding(log_name=None, log_dir=None):
    """Aborta (ConfigErro) se a codificacao do sistema de arquivos nao for UTF-8 (CR-007, R-17)."""
    code = (sys.getfilesystemencoding() or "").lower().replace("-", "")
    if code != "utf8":
        exc = ConfigError(reason="Codificacao do sistema de arquivos '%s' nao e UTF-8: exporte LANG/LC_ALL "
                                "(por exemplo C.UTF-8) antes de iniciar (README §12.2)" % sys.getfilesystemencoding())
        if log_name:
            _abort(log_name, exc, log_dir)
        raise exc


class OracleSecret(object):
    """Representacao de credenciais Oracle, sem exibir senha no repr."""

    __slots__ = ("_password",)

    def __init__(self, password):
        self._password = password

    @property
    def password(self):
        return self._password

    def __repr__(self):
        return "<OracleSegredo: password=***>"

    def __str__(self):
        return "<OracleSegredo: ***redacted***>"


class WebSecret(object):
    """Representacao da chave de sessao web, sem exibir no repr."""

    __slots__ = ("_cookie_key",)

    def __init__(self, cookie_key):
        self._cookie_key = cookie_key

    @property
    def cookie_key(self):
        return self._cookie_key

    def __repr__(self):
        return "<WebSegredo: cookie_key=***>"

    def __str__(self):
        return "<WebSegredo: ***redacted***>"


class EnvironmentSecret(object):
    """Credenciais de acesso para um ambiente catalogado."""

    __slots__ = ("_user", "_password")

    def __init__(self, user, password):
        self._user = user
        self._password = password

    @property
    def user(self):
        return self._user

    @property
    def password(self):
        return self._password

    def __repr__(self):
        return "<AmbienteSegredo: user=%r, password=***>" % (self._user,)

    def __str__(self):
        return "<AmbienteSegredo: user=%r, password=***>" % (self._user,)


class Secrets(object):
    """Container seguro de segredos carregados do secrets.cfg."""

    __slots__ = ("_oracle", "_web", "_environments", "_purge", "_monitor")

    def __init__(self, oracle_password, cookie_key, environments, purge_password=None, monitor=None):
        self._oracle = OracleSecret(oracle_password) if oracle_password is not None else None
        self._web = WebSecret(cookie_key) if cookie_key is not None else None
        self._environments = dict(environments)
        self._purge = OracleSecret(purge_password) if purge_password is not None else None
        self._monitor = monitor  # EnvironmentSecret com user e password (CR-008, E3)

    @property
    def purge_password(self):
        return self._purge.password if self._purge else None

    @property
    def oracle(self):
        return self._oracle

    @property
    def oracle_password(self):
        return self._oracle.password if self._oracle else None

    @property
    def web(self):
        return self._web

    @property
    def cookie_key(self):
        return self._web.cookie_key if self._web else None

    @property
    def monitor(self):
        return self._monitor

    @property
    def monitor_password(self):
        return self._monitor.password if self._monitor else None

    @property
    def monitor_user(self):
        return self._monitor.user if self._monitor else None

    @property
    def environments(self):
        return self._environments

    def get_environment(self, name):
        return self._environments.get(name)

    def __getitem__(self, item):
        if item == "oracle":
            if self._oracle is None:
                raise KeyError(item)
            return {"password": self.oracle_password}
        elif item == "web":
            if self._web is None:
                raise KeyError(item)
            return {"cookie_key": self.cookie_key}
        elif item == "monitor":
            if self._monitor is None:
                raise KeyError(item)
            return {"user": self.monitor_user, "password": self.monitor_password}
        elif item.startswith("environment:"):
            name = item.split(":", 1)[1]
            env = self.get_environment(name)
            if env is None:
                raise KeyError(item)
            return {"user": env.user, "password": env.password}
        elif item in self._environments:
            env = self._environments[item]
            return {"user": env.user, "password": env.password}
        raise KeyError(item)

    def __repr__(self):
        return "<Segredos: oracle=%s, web=%s, monitor=%s, environments=%r>" % (
            "***" if self._oracle else "None", "***" if self._web else "None",
            "***" if self._monitor else "None",
            sorted(list(self._environments.keys()))
        )

    def __str__(self):
        return "<Segredos: ***redacted***>"


def _other_role_section(role, section_name, env):
    """Secao que pertence a outro papel (README §4.1, CR-007 D1b): erro em HML/PROD, WARN nos demais casos."""
    reason = "Secao [%s] nao pertence ao papel '%s' (README §4.1)" % (section_name, role)
    if env in ("HML", "PROD"):
        raise ConfigError(section=section_name, key=None, reason=reason)
    _log.warning("secrets.cfg: %s; ignorada fora de HML/PROD", reason)


def _monitor_secrets(cp, env):
    """Papel monitor (README §4.1; CR-008, E3; F9.1b): so [monitor]; [web] proibida; as demais secoes do arquivo
    do servidor sao ignoradas, sem validar nem registrar no masking os segredos de outros papeis."""
    if "web" in cp.sections():
        _other_role_section("monitor", "web", env)
    if "monitor" not in cp.sections():
        raise ConfigError(section="monitor", key=None, reason="Secao [monitor] obrigatoria ausente em secrets.cfg")
    values = {}
    for key in ("user", "password"):
        if key not in cp["monitor"]:
            raise ConfigError(section="monitor", key=key, reason="Chave %s obrigatoria ausente em [monitor]" % key)
        values[key] = cp["monitor"][key].strip()
        if not values[key]:
            raise ConfigError(section="monitor", key=key, reason="%s nao pode ser vazio em [monitor]" % key)
    from masking import register_secret
    register_secret(values["password"])
    return Secrets(oracle_password=None, cookie_key=None, environments={}, purge_password=None,
                    monitor=EnvironmentSecret(user=values["user"], password=values["password"]))


def load_secrets(path, cfg=None, sss_env=None, data_backend=None, role="web"):
    """Valida e carrega segredos de arquivo com modo 0600 e ownership restrito.

    papel ('web' ou 'agent', CR-007 D1b) define as secoes obrigatorias e as proibidas (README §4.1).
    A aplicacao usa sempre o Oracle, entao [oracle] password e obrigatoria para web e agente.
    data_backend='FAKE' so pode vir como parametro explicito de teste (DEV), nunca do config.ini.
    """
    if role not in ROLES:
        raise ConfigError(reason="Papel de segredos invalido: %r" % (role,))
    if not os.path.exists(path):
        raise ConfigError(reason="Arquivo de segredos nao encontrado: %s" % path)

    import os_platform
    try:
        code, st = os_platform.validate_restricted_file(path)
    except OSError as e:
        raise ConfigError(reason="Erro ao obter informacoes do arquivo de segredos %s: %s" % (path, e))

    if code == "NAO_REGULAR":
        raise ConfigError(reason="Arquivo de segredos deve ser um arquivo regular: %s" % path)

    if code == "DONO_INVALIDO":
        raise ConfigError(
            reason="Arquivo de segredos deve pertencer ao usuario corrente (UID %d, atual %d)" % (
                os.geteuid(), st.st_uid
            )
        )

    if code == "PERMISSAO_INSEGURA":
        raise ConfigError(
            reason="Arquivo de segredos possui permissoes inseguras (mode %o, esperado sem acesso grupo/outros)" % (
                st.st_mode & 0o777
            )
        )

    if cfg is not None:
        env = getattr(cfg.app, "sss_env", sss_env)
        backend = data_backend
    else:
        env = sss_env
        backend = data_backend

    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
    try:
        with open(path, "r", encoding="utf-8") as f:
            cp.read_file(f)
    except Exception as e:
        raise ConfigError(reason="Erro ao ler arquivo de segredos %s: %s" % (path, e))

    if role == "monitor":
        return _monitor_secrets(cp, env)

    # [web] cookie_key: obrigatorio no papel web e proibido no agente (README §4.1)
    cookie_key = None
    if role == "web":
        if "web" not in cp.sections():
            raise ConfigError(section="web", key=None, reason="Secao [web] obrigatoria ausente em secrets.cfg")
        if "cookie_key" not in cp["web"]:
            raise ConfigError(section="web", key="cookie_key", reason="Chave cookie_key obrigatoria ausente em [web]")
        cookie_key = cp["web"]["cookie_key"].strip()
        if not cookie_key:
            raise ConfigError(section="web", key="cookie_key", reason="cookie_key nao pode ser vazio")
    elif "web" in cp.sections():
        _other_role_section(role, "web", env)

    # [oracle] password: em DEV e FAKE e opcional; obrigatorio para web e agente
    oracle_password = None
    is_dev_fake = (env == "DEV" and backend == "FAKE")
    if "oracle" in cp.sections():
        if "password" not in cp["oracle"]:
            if not is_dev_fake:
                raise ConfigError(section="oracle", key="password", reason="Chave password obrigatoria ausente em [oracle]")
        else:
            pwd = cp["oracle"]["password"].strip()
            if not pwd and not is_dev_fake:
                raise ConfigError(section="oracle", key="password", reason="password do oracle nao pode ser vazio")
            oracle_password = pwd if pwd else None
    else:
        if not is_dev_fake:
            raise ConfigError(section="oracle", key=None, reason="Secao [oracle] obrigatoria ausente em secrets.cfg")

    # [purge] password: so no papel agente (o purge.py roda no servidor do agente)
    purge_password = None
    if "purge" in cp.sections():
        if role != "agent":
            _other_role_section(role, "purge", env)
        else:
            purge_password = (cp["purge"].get("password") or "").strip() or None
            if purge_password is None:
                raise ConfigError(section="purge", key="password", reason="password do purge nao pode ser vazio")

    # [monitor]: so no papel monitor (CR-008, E3), tratado em _segredos_monitor
    if "monitor" in cp.sections():
        _other_role_section(role, "monitor", env)

    # [environment:<NOME>]: so no papel agente
    environments = {}
    for sec in cp.sections():
        if sec in ("oracle", "web", "purge", "monitor"):
            continue
        if sec.startswith("environment:"):
            if role != "agent":
                _other_role_section(role, sec, env)
                if env in ("HML", "PROD"):
                    continue
            name = sec.split(":", 1)[1].strip()
            if not name:
                raise ConfigError(section=sec, key=None, reason="Nome de ambiente invalido na secao [%s]" % sec)
            if "user" not in cp[sec]:
                raise ConfigError(section=sec, key="user", reason="Chave user obrigatoria ausente em [%s]" % sec)
            if "password" not in cp[sec]:
                raise ConfigError(section=sec, key="password", reason="Chave password obrigatoria ausente em [%s]" % sec)
            u = cp[sec]["user"].strip()
            p = cp[sec]["password"].strip()
            if not u:
                raise ConfigError(section=sec, key="user", reason="user nao pode ser vazio em [%s]" % sec)
            if not p:
                raise ConfigError(section=sec, key="password", reason="password nao pode ser vazio em [%s]" % sec)
            environments[name] = EnvironmentSecret(user=u, password=p)
        elif sec.startswith("ambiente:"):
            raise ConfigError(section=sec, key=None, reason="Secao renomeada: [%s] passou a se chamar [environment:%s] "
                             "(CR-016b)" % (sec, sec.split(":", 1)[1]))
        else:
            raise ConfigError(section=sec, key=None, reason="Secao desconhecida em secrets.cfg: [%s]" % sec)

    if role == "agent" and cfg is not None and env != "DEV":
        missing = [a for a in cfg.agent.environments if a not in environments]
        if missing:
            raise ConfigError(section="ambiente", key=None,
                             reason="Ambientes atendidos sem credencial em secrets.cfg: %s" % ", ".join(missing))

    secrets_value = Secrets(oracle_password=oracle_password, cookie_key=cookie_key, environments=environments,
                        purge_password=purge_password, monitor=None)

    # Import tardio para nao acoplar carregar() ao masking. Sem masking.py a carga de
    # segredos falha (ImportError): segredo sem mascaramento nunca chega aos logs (AGENTS §3.3).
    from masking import register_secret

    if oracle_password:
        register_secret(oracle_password)
    if cookie_key:
        register_secret(cookie_key)
    if purge_password:
        register_secret(purge_password)
    for env_name in environments.values():
        register_secret(env_name.password)

    return secrets_value


_CONFIG_CACHE = None


def default_config_path():
    """Caminho canonico do config.ini da aplicacao (instance/config.ini)."""
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(app_dir, "instance", "config.ini")


def _raw_log_dir(ini_path):
    """[logging] log_dir lido sem validacao, so para registrar o CRITICAL de uma configuracao invalida."""
    try:
        cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
        with open(ini_path, "r", encoding="utf-8") as f:
            cp.read_file(f)
        value = cp.get("logging", "log_dir", fallback="").strip()
        return value or None
    except (OSError, ValueError, configparser.Error):
        return None


def _abort(log_name, exc, log_dir):
    import sss_logging
    sss_logging.log_initial_critical(log_name, "Subida abortada: configuracao invalida: %s" % exc, log_dir)


def get_config(log_name=None, path=None):
    """Retorna a configuracao validada, carregada uma unica vez por processo.

    Com log_name ('sss_web' ou 'sss_scheduler'), uma falha e registrada em CRITICAL antes de
    ser relancada (README §12.1, "Falha de configuracao"). caminho: outro config.ini (so o
    agente, por --config do run_scheduler; README §12.2); sem ele, instance/config.ini.
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        path = path or default_config_path()
        try:
            # Corrida entre threads do servidor web apenas recarrega o mesmo arquivo imutavel.
            _CONFIG_CACHE = load(path)
        except ConfigError as exc:
            if log_name:
                _abort(log_name, exc, _raw_log_dir(path))
            raise
    return _CONFIG_CACHE


def reset_config_cache():
    """Descarta a configuracao em cache (uso em testes)."""
    global _CONFIG_CACHE
    _CONFIG_CACHE = None


_SECRETS_CACHE = None


def get_secrets(log_name=None, role="web"):
    """Retorna os segredos validados de [secrets] secrets_file, carregados uma unica vez por processo.

    papel: 'web' (nó web) ou 'agent' (daemon e purge), README §4.1.
    Com log_name, uma falha e registrada em CRITICAL (sem valores de segredo) antes de ser relancada.
    """
    global _SECRETS_CACHE
    if _SECRETS_CACHE is None:
        cfg = get_config(log_name)
        try:
            _SECRETS_CACHE = load_secrets(cfg.secrets.secrets_file, cfg=cfg, role=role)
        except ConfigError as exc:
            if log_name:
                _abort(log_name, exc, cfg.logging.log_dir)
            raise
    return _SECRETS_CACHE


def reset_secrets_cache():
    """Descarta os segredos em cache (uso em testes)."""
    global _SECRETS_CACHE
    _SECRETS_CACHE = None


def critical_config(cfg):
    """Texto canonico dos parametros que precisam coincidir nos nos (README §8.12)."""
    fields = (("hb", "heartbeat_interval_s"), ("fence", "fence_timeout_s"),
              ("offline", "node_offline_timeout_s"), ("call", None),
              ("kill", "kill_grace_s"), ("misfire", "misfire_policy"),
              ("tol", "misfire_tolerance_s"), ("horizonte", "cron_horizon_days"),
              ("envelhecimento", "queue_aging_min"))
    return ";".join("%s=%s" % (label, call_timeout_s(cfg.oracle.call_timeout_ms) if key is None
                               else getattr(cfg.agent, key))
                    for label, key in fields)
