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
from typing import List, Optional


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

# Chaves que existiram e foram retiradas: ignoradas com aviso "apague a linha", nunca em silencio.
# CR-036 (D6): as chaves retiradas antes do CR-032 tambem so geram aviso (antes recusavam a subida): uma regra
# so para chave que saiu. As renomeadas (RENAMED_KEYS) continuam recusadas, para o valor nao se perder.
_OLD_REMOVED = {
    ("app", "data_backend"): "a aplicacao usa sempre o Oracle do [oracle] (owner e table_prefix) (F7.3)",
    ("agent", "script_owner_uids"): "o SSS nao confere mais o dono dos scripts; o ambiente controla o conteudo (CR-011)",
    ("agent", "ambientes_exigem_hash"): "o SSS nao confere mais o hash dos scripts (CR-011)",
}

# Chaves que deixaram de existir e sao so ignoradas, com aviso (a subida segue).
_NO_PURGE = "o purge e a retencao automatica foram retirados; a limpeza e manual (README §11.3, CR-030)"
IGNORED_KEYS = dict(_OLD_REMOVED)
IGNORED_KEYS.update({
    ("agent", "interpreters"): "o interpretador vem do script (#!), do disparo ou do cadastro (CR-026)",
    ("agent", "interpretadores"): "o interpretador vem do script (#!), do disparo ou do cadastro (CR-026)",
    ("logging", "app_log_retention_days"): _NO_PURGE,
    ("logging", "local_log_retention_days"): _NO_PURGE,
    ("logging", "output_retention_days"): _NO_PURGE,
    ("logging", "script_work_retention_days"): _NO_PURGE,
    ("logging", "saida_retention_days"): _NO_PURGE,
})
# CR-032 (D2, D3, D9): ajustes finos com valor fixo no codigo. Continuam atributos do Config (quem le nao
# muda); a linha no config.ini so gera aviso. D1: chaves sem efeito, retiradas.
FIXED = {
    ("oracle", "pool_min"): 1, ("oracle", "pool_max"): 4,
    ("agent", "schedule_batch_size"): 50, ("agent", "orchestrator_interval_s"): 10,
    ("agent", "cancel_poll_interval_s"): 2, ("agent", "heartbeat_interval_s"): 10,
    ("agent", "fence_timeout_s"): 90, ("agent", "node_offline_timeout_s"): 180,
    ("agent", "kill_grace_s"): 5, ("agent", "shutdown_mode"): "TERMINATE",
    ("agent", "shutdown_grace_s"): 30, ("agent", "misfire_tolerance_s"): 300,
    ("agent", "cron_horizon_days"): 1461, ("agent", "queue_aging_min"): 60,
    ("agent", "child_locale"): "C.UTF-8",
    ("web", "log_poll_interval_s"): 3, ("web", "max_threads"): 16, ("web", "socket_timeout_s"): 30,
    # CR-036 (D3): sem limite de tamanho nem de quantidade na saida (0 = sem limite); todo zip vai ao banco.
    ("agent", "output_max_bytes"): 0, ("agent", "output_max_files"): 0,
}
_FIXED_REASON = "valor fixo no codigo desde o CR-032"
_REMOVED_REASON = "sem efeito, retirada no CR-032"
IGNORED_KEYS.update(dict((key, "%s (%s)" % (_FIXED_REASON, value)) for key, value in FIXED.items()))
_NO_OUTPUT_LIMIT = "a saida nao tem mais limite de tamanho nem de arquivos desde o CR-036 (todo zip vai ao banco)"
IGNORED_KEYS.update(dict((("agent", key), _NO_OUTPUT_LIMIT)
                         for key in ("output_max_bytes", "output_max_files", "saida_max_bytes", "saida_max_arquivos")))
# CR-032 (D4, D14): sempre do [app] name; o secrets.cfg e o unico da pasta de cima (instance/secrets.cfg).
_DERIVED_REASON = "derivada do [app] name desde o CR-032"
IGNORED_KEYS.update({("agent", "agent_id"): _DERIVED_REASON, ("agent", "work_dir"): _DERIVED_REASON,
                     ("logging", "log_dir"): _DERIVED_REASON,
                     ("secrets", "secrets_file"): "o secrets.cfg e o unico de instance/ desde o CR-032"})
IGNORED_KEYS.update({("agent", "claim_batch_size"): _REMOVED_REASON,
                     ("agent", "max_parallel_hard_limit"): _REMOVED_REASON,
                     ("oracle", "oracle_client_lib_dir"): _REMOVED_REASON})
# CR-032 (D11): DEV e PROD com o mesmo comportamento; o ambiente mostrado vem da pasta <TIPO>.
IGNORED_KEYS[("app", "sss_env")] = ("o comportamento e o mesmo em DEV e PROD desde o CR-032; o ambiente mostrado "
                                    "vem da pasta acima da raiz")
# CR-032 (D7): sem usuario de execucao, sudo nem helper; tudo roda com a conta do agente.
_NO_EXEC_USER = "sem usuario de execucao desde o CR-032; os scripts rodam com a conta do agente"
IGNORED_KEYS.update(dict((("agent", key), _NO_EXEC_USER)
                         for key in ("exec_users", "usuarios_execucao", "exec_work_dir", "helper_path")))

_NO_MONITOR = "sem papel monitor desde o CR-032; o health.py usa a conta do proprio processo"
# CR-032 (D18): arquivo comum do servidor, ao lado do secrets.cfg, com o banco comum ao web e aos agentes.
COMMON_FILE = "common.ini"
COMMON_SECTIONS = ("oracle",)
# Secoes inteiras ignoradas com aviso (CR-030): o load() registra uma linha por chave.
IGNORED_SECTIONS = {"retention": _NO_PURGE, "retencao": _NO_PURGE,
                    "secrets": "o secrets.cfg e o unico de instance/ desde o CR-032"}

# Avisos do load() que esperam o log da aplicacao (CR-026f): o load() roda antes do sss_logging.configure().
_PENDING_WARNINGS = []  # type: List[str]


def pending_warnings() -> List[str]:
    """Devolve e esvazia os avisos guardados pelo load() (o configure() do log os grava)."""
    taken = list(_PENDING_WARNINGS)
    del _PENDING_WARNINGS[:]
    return taken


# Chaves com nome novo (CR-015a): o config.ini antigo e recusado com o nome a usar, sem aceitar o antigo.
RENAMED_KEYS = {
    ("agent", "saida_dir"): "output_dir",
    ("agent", "entrada_dir"): "input_dir",
    # CR-016b: configuracao e operacao em ingles
    ("oracle", "modo_driver"): "driver_mode",
    ("agent", "ambientes_atendidos"): "environments",
    ("agent", "fila_envelhecimento_min"): "queue_aging_min",
    ("agent", "log_dir_min_livre_mb"): "log_dir_min_free_mb",
    ("web", "sessao_max_horas"): "session_max_hours",
    ("web", "login_max_tentativas"): "login_max_attempts",
    ("web", "login_bloqueio_s"): "login_lockout_s",
}

# Secoes com nome novo (CR-016b), no config.ini e no secrets.cfg ([ambiente:X] -> [environment:X]).
RENAMED_SECTIONS = {"ambiente:": "environment:"}

# Atores do sistema que nao podem ser agent_id (README §4.4 e §8.12).
RESERVED_AGENT_IDS = ("init_db", "seed", "purge")
_ENVIRONMENTS_MAX = 1000
ROLES = ("web", "agent")

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
        # CR-028 (D5, D6): nome do processo (web0001, agente0001...); as pastas saem de var/<nome>/ e, no
        # agente, e o agent_id.
        ("name", FieldDef("str", required=True, regex=r"^[a-z][a-z0-9_-]{0,29}$")),
    ])),
    ("oracle", collections.OrderedDict([
        ("user", FieldDef("str", required=True)),
        ("dsn", FieldDef("str", required=True)),
        ("owner", FieldDef("str", required=True, regex=r"^[A-Za-z][A-Za-z0-9_]{0,29}$")),
        # So minusculas: o registro de identificadores so aceita nomes em minusculas (CR-007, R-31).
        ("table_prefix", FieldDef("str", required=True, regex=r"^[a-z][a-z0-9_]{0,7}$")),
        ("driver_mode", FieldDef("enum", required=False, allowed_values=("auto", "thin", "thick", "cx_oracle"), default="auto")),
        ("call_timeout_ms", FieldDef("int", required=False, min_val=1, max_val=3600000, default=30000)),
    ])),
    ("agent", collections.OrderedDict([
        ("environments", FieldDef("list_csv", required=True)),
        ("max_parallel_jobs", FieldDef("int", required=True, min_val=1, max_val=999)),
        # Pedido do responsavel pelo produto (2026-10-27): padrao de 168 h; maximo igual ao do cadastro do
        # script (tbsss_scripts.timeout_s, NUMBER(7)).
        ("script_timeout_s", FieldDef("int", required=False, min_val=1, max_val=9999999, default=604800)),
        ("misfire_policy", FieldDef("enum", required=False, allowed_values=("RUN_ONCE", "SKIP"), default="RUN_ONCE")),
        # CR-008, R-25: espaco minimo do log_dir.
        ("log_dir_min_free_mb", FieldDef("int", required=False, min_val=0, max_val=1048576, default=1024)),
        # CR-012: pasta de saida dos scripts (vazio desliga; o zip nao tem limite desde o CR-036, README §8.13).
        ("output_dir", FieldDef("path", required=False, default=None)),
        # CR-014: pasta de entrada dos scripts, permanente, uma por ambiente e script (vazio desliga; README §8.14).
        ("input_dir", FieldDef("path", required=False, default=None)),
        # CR-019: pasta de trabalho dos scripts, por ticket, com as partes da pasta de saida (vazio desliga; README §8.15).
        ("script_work_dir", FieldDef("path", required=False, default=None)),
        # CR-023: pasta base dos scripts cadastrados com caminho relativo (vazio desliga; README §8.5).
        ("script_base_dir", FieldDef("path", required=False, default=None)),
        ("env_passthrough", FieldDef("list_csv", required=False, default=())),
    ])),
    ("logging", collections.OrderedDict([
        ("level", FieldDef("enum", required=False, allowed_values=("DEBUG", "INFO", "WARN", "ERROR"), default="INFO")),
        ("app_log_max_bytes", FieldDef("int", required=False, min_val=1024, max_val=1073741824, default=10485760)),
        ("max_log_size_bytes", FieldDef("int", required=False, min_val=1024, max_val=67108864, default=5242880)),
        ("max_local_log_size_bytes", FieldDef("int", required=False, min_val=1024, max_val=10737418240, default=52428800)),
    ])),
    ("web", collections.OrderedDict([
        ("session_idle_timeout_s", FieldDef("int", required=False, min_val=1, max_val=86400, default=1800)),
        ("session_max_hours", FieldDef("int", required=False, min_val=1, max_val=168, default=12)),
        ("login_max_attempts", FieldDef("int", required=False, min_val=1, max_val=99, default=5)),
        ("login_lockout_s", FieldDef("int", required=False, min_val=1, max_val=86400, default=900)),
        ("trusted_proxies", FieldDef("list_csv", required=False, default=())),
        ("allowed_origins", FieldDef("list_csv", required=True)),
        # CR-020d: tamanho maximo do arquivo enviado pela tela de Entrada (o POST maior e recusado antes de ser lido).
        ("input_upload_max_bytes", FieldDef("int", required=False, min_val=1048576, max_val=209715200,
                                            default=52428800)),
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


class AppConfig(_ItemAccessMixin, collections.namedtuple("AppConfig",
                                                         ["name", "role", "config_path", "common_path"])):
    __slots__ = ()


# role, config_path e common_path sao opcionais na construcao direta (testes); o load() sempre os preenche
# (CR-028; CR-029: config_path e o arquivo lido, repassado a sondagem do driver; CR-032, D18: common_path e o
# instance/common.ini lido, ou None).
AppConfig.__new__.__defaults__ = ("all", None, None)


class OracleConfig(_ItemAccessMixin, collections.namedtuple("OracleConfig", [
    "user", "dsn", "owner", "table_prefix", "driver_mode",
    "call_timeout_ms",
    "pool_min", "pool_max"
])):
    __slots__ = ()


class SecretsConfig(_ItemAccessMixin, collections.namedtuple("SecretsConfig", ["secrets_file"])):
    __slots__ = ()


class AgentConfig(_ItemAccessMixin, collections.namedtuple("AgentConfig", [
    "agent_id", "environments", "work_dir",
    "max_parallel_jobs", "schedule_batch_size", "orchestrator_interval_s",
    "cancel_poll_interval_s", "heartbeat_interval_s", "fence_timeout_s",
    "node_offline_timeout_s", "kill_grace_s", "script_timeout_s",
    "shutdown_mode", "shutdown_grace_s", "misfire_policy",
    "misfire_tolerance_s", "cron_horizon_days", "child_locale",
    "env_passthrough", "queue_aging_min",
    "log_dir_min_free_mb", "output_dir", "output_max_bytes", "output_max_files", "input_dir",
    "script_work_dir", "script_base_dir"
])):
    __slots__ = ()


class LoggingConfig(_ItemAccessMixin, collections.namedtuple("LoggingConfig", [
    "log_dir", "level", "app_log_max_bytes", "max_log_size_bytes", "max_local_log_size_bytes"
])):
    __slots__ = ()


class WebConfig(_ItemAccessMixin, collections.namedtuple("WebConfig", [
    "session_idle_timeout_s", "session_max_hours", "login_max_attempts", "login_lockout_s",
    "log_poll_interval_s", "trusted_proxies", "allowed_origins", "input_upload_max_bytes",
    "max_threads", "socket_timeout_s"
])):
    __slots__ = ()


class Config(_ItemAccessMixin, collections.namedtuple("Config", [
    "app", "oracle", "secrets", "agent", "logging", "web"
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


# CR-028: estrutura por processo. A raiz da aplicacao (src/sss/config/ -> raiz) guarda instance/<nome>/,
# var/<nome>/ e scripts_ambiente/, iguais em DEV, HML e PROD.
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
VAR_DIR = os.path.join(APP_DIR, "var")
SCRIPTS_DIR = os.path.join(APP_DIR, "scripts_ambiente")
# Pasta <TIPO> acima da raiz (CR-028, D1): DEV ou PROD. CR-032 (D11): so o que se mostra na tela e no log de
# subida; o comportamento e o mesmo em todo <TIPO>.
INSTALL_TYPE = os.path.basename(os.path.dirname(APP_DIR)).upper()
# Pasta dev/ do repositorio (CR-032, D11): a tela /dev, o FAKE e os scripts em dev/ so valem onde ela existe; o
# pacote de implantacao nao a leva.
APP_DEV_DIR = os.path.join(APP_DIR, "dev")
# Secoes que cada papel nao usa (CR-028, D4): o papel vem do proprio arquivo.
_ROLE_SKIPPED = {"web": ("agent",), "agent": ("web",)}
# Chaves de [agent] que o web tambem usa (painel de saude, agendamentos, fila) e que precisam ser iguais as dos
# agentes (revisao do CR-028, A1): o config do web aceita um [agent] parcial so com elas, sem mudar o papel.
# CR-032 (D2, D3): os tempos de saude e os ajustes do desdobro ficaram fixos; sobra so a politica de misfire.
WEB_AGENT_KEYS = ("misfire_policy",)
# Chaves que so o agente tem: um [agent] com qualquer delas e o do formato unico, e nao o parcial do web.
_AGENT_ONLY_REQUIRED = ("environments", "max_parallel_jobs")


def env_label(install_type: Optional[str] = None) -> str:
    """Ambiente mostrado na tela e na linha de subida (CR-028, D12; CR-032, D11): o nome da pasta <TIPO>."""
    tipo = INSTALL_TYPE if install_type is None else install_type.upper()
    return tipo or "?"


def has_dev_dir() -> bool:
    """CR-032 (D11): a pasta dev/ existe (o repositorio); no pacote, nao."""
    return os.path.isdir(APP_DEV_DIR)


def role_of(sections):
    """Papel do config.ini pelas secoes (CR-028, D4): [web] sem [agent] e o web; [agent] sem [web] e o agente.
    Com as duas, ou nenhuma, "all": o formato unico, recusado desde o CR-032 (D4) pelo load()."""
    present = set(sections)
    if "web" in present and "agent" not in present:
        return "web"
    if "agent" in present and "web" not in present:
        return "agent"
    return "all"


# CR-032 (032e, D21): pastas do agente no plural. Nome novo -> nome anterior, renomeado na subida do agente quando a
# pasta derivada do nome ainda tem o nome anterior (scheduler_loop._rename_legacy_dirs).
LEGACY_DIR_NAMES = collections.OrderedDict([
    ("works", "work"), ("outputs", "output"), ("inputs", "input"), ("script_works", "script_work"),
])


def _derived_paths(name, role, present):
    """Pastas que saem do nome do processo quando a chave nao esta escrita (CR-028, D5). agent_id, work_dir e
    log_dir saem sempre do nome (CR-032, D4): nao sao mais chaves do config."""
    base = os.path.join(VAR_DIR, name)
    derived = {}
    if role != "web":
        derived.update({
            ("agent", "output_dir"): os.path.join(base, "outputs"),
            ("agent", "input_dir"): os.path.join(base, "inputs"),
            ("agent", "script_work_dir"): os.path.join(base, "script_works"),
            ("agent", "script_base_dir"): SCRIPTS_DIR,
        })
    return dict((key, value) for key, value in derived.items() if key not in present)


def common_path_for(ini_path: str) -> str:
    """CR-032 (D18): o instance/common.ini do servidor, na pasta de cima da do config (como o secrets.cfg)."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(ini_path))), COMMON_FILE)


def _merge_common(cp: configparser.ConfigParser, ini_path: str) -> Optional[str]:
    """CR-032 (D18): junta ao config do processo o [oracle] do common.ini, se existir. Uma chave escrita no
    config.ini do processo vale no lugar da comum. O common.ini so aceita [oracle]. Devolve o caminho lido."""
    path = common_path_for(ini_path)
    if not os.path.exists(path):
        return None
    common = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
    try:
        with open(path, "r", encoding="utf-8") as f:
            common.read_file(f)
    except Exception as e:
        raise ConfigError(reason="Erro ao ler %s: %s" % (path, e))
    for sec in common.sections():
        if sec not in COMMON_SECTIONS:
            raise ConfigError(section=sec, key=None,
                              reason="O %s so aceita %s (CR-032, D18)"
                                     % (COMMON_FILE, ", ".join("[%s]" % x for x in COMMON_SECTIONS)))
        if not cp.has_section(sec):
            cp.add_section(sec)
        for k, v in common[sec].items():
            # Revisao do CR-032 (achado 12): aviso e recusa citam o common.ini, nao o config.ini do processo.
            if (sec, k) in IGNORED_KEYS:
                _PENDING_WARNINGS.append("%s: chave [%s] %s ignorada: %s; apague a linha"
                                         % (COMMON_FILE, sec, k, IGNORED_KEYS[(sec, k)]))
                continue
            if k not in SCHEMA[sec]:
                raise ConfigError(section=sec, key=k, reason="Chave desconhecida no %s: %s" % (COMMON_FILE, k))
            if k not in cp[sec]:
                cp[sec][k] = v
    return path


def load(ini_path: str) -> "Config":
    """Carrega e valida o config.ini de forma declarativa e fail-fast.

    CR-028: o papel (web, agente ou o formato unico anterior) vem das secoes do arquivo; com [app] name, as
    pastas nao escritas saem de var/<nome>/. Retorna uma instancia imutavel de Config.
    """
    if not os.path.exists(ini_path):
        raise ConfigError(reason="Arquivo de configuracao nao encontrado: %s" % ini_path)

    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
    try:
        with open(ini_path, "r", encoding="utf-8") as f:
            cp.read_file(f)
    except Exception as e:
        raise ConfigError(reason="Erro ao ler arquivo de configuracao %s: %s" % (ini_path, e))
    common_path = _merge_common(cp, ini_path)

    # 1. Validar secoes desconhecidas
    for sec in cp.sections():
        if sec in IGNORED_SECTIONS:
            for k in cp[sec]:
                _PENDING_WARNINGS.append("config.ini: chave [%s] %s ignorada: %s; apague a linha"
                                         % (sec, k, IGNORED_SECTIONS[sec]))
            cp.remove_section(sec)
            continue
        if sec in RENAMED_SECTIONS:
            raise ConfigError(section=sec, key=None, reason="Secao renomeada: [%s] passou a se chamar [%s] (CR-016b)"
                             % (sec, RENAMED_SECTIONS[sec]))
        if sec not in SCHEMA:
            raise ConfigError(section=sec, key=None, reason="Secao desconhecida no config.ini: [%s]" % sec)

    # 2. Validar presenca e chaves de cada secao
    role = role_of(cp.sections())
    if role == "all" and "web" in cp and "agent" in cp and not any(k in cp["agent"] for k in _AGENT_ONLY_REQUIRED):
        # CR-028 (A1): [web] com um [agent] parcial e o web; o [agent] so leva as chaves de WEB_AGENT_KEYS.
        role = "web"
        for k in cp["agent"]:
            if k not in WEB_AGENT_KEYS and ("agent", k) not in IGNORED_KEYS:
                raise ConfigError(section="agent", key=k,
                                  reason="No config do web, [agent] so aceita: %s" % ", ".join(WEB_AGENT_KEYS))
    if role == "all":
        # CR-032 (D4): sem formato unico; um config.ini por processo, em instance/<nome>/.
        raise ConfigError(reason="O config.ini precisa ser de um processo: [web] (no web) ou [agent] (agente), "
                                 "nao os dois nem nenhum (CR-032; modelos em instance/exemplos/)")
    raw_name = cp["app"].get("name", "").strip() if cp.has_section("app") else ""
    present = set((sec, k) for sec in cp.sections() for k in cp[sec])
    derived = _derived_paths(raw_name, role, present) if raw_name else {}
    data_sections = {}
    for sec_name, sec_fields in SCHEMA.items():
        if sec_name in _ROLE_SKIPPED[role]:
            # CR-028 (D4): secao que o papel nao usa fica com os padroes (obrigatorias sem valor).
            data_sections[sec_name] = dict((k, cdef.default) for k, cdef in sec_fields.items())
            if sec_name in cp:
                for k in cp[sec_name]:
                    if (sec_name, k) in IGNORED_KEYS:
                        _PENDING_WARNINGS.append("config.ini: chave [%s] %s ignorada: %s; apague a linha"
                                                 % (sec_name, k, IGNORED_KEYS[(sec_name, k)]))
                        continue
                    data_sections[sec_name][k] = _convert_value(sec_name, k, sec_fields[k], cp[sec_name][k])
            continue
        if sec_name not in cp.sections():
            # CR-026: secao sem chave obrigatoria (ex.: [secrets]) pode faltar; vale o padrao de cada chave.
            if any(cdef.required and (sec_name, k) not in derived for k, cdef in sec_fields.items()):
                raise ConfigError(section=sec_name, key=None, reason="Secao obrigatoria ausente: [%s]" % sec_name)
            cp_sec = {}
        else:
            cp_sec = cp[sec_name]

        # Chaves desconhecidas na secao
        for k in cp_sec:
            if (sec_name, k) in IGNORED_KEYS:
                _PENDING_WARNINGS.append("config.ini: chave [%s] %s ignorada: %s; apague a linha"
                                         % (sec_name, k, IGNORED_KEYS[(sec_name, k)]))
                continue
            if (sec_name, k) in RENAMED_KEYS:
                raise ConfigError(section=sec_name, key=k, reason="Chave renomeada: %s passou a se chamar %s (CR-015a)"
                                 % (k, RENAMED_KEYS[(sec_name, k)]))
            if k not in sec_fields:
                raise ConfigError(section=sec_name, key=k, reason="Chave desconhecida na secao [%s]: %s" % (sec_name, k))

        # Validar e converter cada chave esperada
        data_sec = {}
        for k, cdef in sec_fields.items():
            if (sec_name, k) in derived:
                data_sec[k] = derived[(sec_name, k)]
                continue
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

    # CR-032: os ajustes finos fixos entram sempre com o valor do codigo.
    for (sec_name, k), value in FIXED.items():
        data_sections[sec_name][k] = value

    app_name = data_sections["app"]["name"]
    folder = os.path.dirname(os.path.realpath(ini_path))
    if (app_name and os.path.dirname(folder) == os.path.realpath(os.path.join(APP_DIR, "instance"))
            and os.path.basename(folder) != app_name):
        # Revisao do CR-028 (A2): pasta copiada sem trocar o name subiria (e pararia) outro processo.
        raise ConfigError(section="app", key="name",
                          reason="O name (%s) deve ser o nome da pasta instance/%s/ (CR-028)"
                                 % (app_name, os.path.basename(folder)))
    # CR-032 (D4): agent_id, work_dir e log_dir sempre do nome.
    base = os.path.join(VAR_DIR, app_name)
    data_sections["logging"]["log_dir"] = os.path.join(base, "logs")
    data_sections["agent"]["agent_id"] = app_name if role == "agent" else None
    data_sections["agent"]["work_dir"] = os.path.join(base, "works") if role == "agent" else None
    # CR-034 (D9): reservado em todo papel (antes so no agente, cujo nome vai ao banco como ator), como diz o
    # README §12.1: uma regra so para o nome do processo.
    if app_name in RESERVED_AGENT_IDS:
        raise ConfigError(section="app", key="name",
                          reason="Nome reservado do sistema: %s (README §4.4 e §8.12)" % app_name)
    data_sections["app"]["role"] = role
    data_sections["app"]["config_path"] = os.path.abspath(ini_path)
    data_sections["app"]["common_path"] = common_path

    # CR-032 (D14): um secrets.cfg por servidor, na pasta de cima da do config (instance/secrets.cfg). O antigo,
    # na pasta do processo, ainda e lido, com aviso para mover.
    shared = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(ini_path))), "secrets.cfg")
    old = os.path.join(os.path.dirname(os.path.abspath(ini_path)), "secrets.cfg")
    if not os.path.exists(shared) and os.path.exists(old):
        _PENDING_WARNINGS.append("secrets.cfg: lido de %s; mova-o para %s, unico do servidor (CR-032)" % (old, shared))
        shared = old
    data_sections["secrets"] = {"secrets_file": shared}

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
    # CR-032 (D3): os tempos de saude sao fixos (heartbeat 10, fence 90, offline 180); as invariantes I3/I4 so
    # limitam o call_timeout_ms (ate 40 s), em _validate_cr007.
    _validate_cr007(app_dict, oracle_dict, agent_dict, data_sections["logging"], role)

    # 5. Instanciar arvore de configuracao imutavel
    app_cfg = AppConfig(**app_dict)
    oracle_cfg = OracleConfig(**oracle_dict)
    secrets_cfg = SecretsConfig(**data_sections["secrets"])
    agent_cfg = AgentConfig(**agent_dict)
    logging_cfg = LoggingConfig(**data_sections["logging"])
    web_cfg = WebConfig(**data_sections["web"])

    return Config(
        app=app_cfg,
        oracle=oracle_cfg,
        secrets=secrets_cfg,
        agent=agent_cfg,
        logging=logging_cfg,
        web=web_cfg,
    )


def call_timeout_s(call_timeout_ms):
    """call_timeout_ms arredondado para cima em segundos (invariantes I3 e I4, README §8.9)."""
    return (int(call_timeout_ms) + 999) // 1000


def _inside(path, folder):
    path, folder = os.path.normpath(path), os.path.normpath(folder)
    return os.path.commonpath([path, folder]) == folder


def _validate_script_base_dir(agent: dict, log_dir: str) -> None:
    """CR-023 (D5): formato da pasta base; a existencia so e avisada na subida do agente (README §8.5)."""
    # pylint: disable=import-outside-toplevel
    from sss.platform import path_guard
    base = agent["script_base_dir"]
    if not os.path.isabs(base) or os.path.normpath(base) != base:
        raise ConfigError(section="agent", key="script_base_dir",
                          reason="Deve ser um caminho absoluto e normalizado")
    sss_dirs = (agent["work_dir"], log_dir, agent["output_dir"], agent["input_dir"], agent["script_work_dir"])
    try:
        path_guard.check_forbidden_dirs(base, sss_dirs)
    except path_guard.PathGuardError as exc:
        reasons = {"SYSTEM_DIR": "Nao pode ficar numa pasta do sistema",
                   "SSS_DIR": "Nao pode ficar dentro de uma pasta do SSS (log, trabalho, entrada, saida)",
                   "APP_DIR": "Nao pode ficar dentro da pasta da aplicacao (so em dev/, onde existe)"}
        raise ConfigError(section="agent", key="script_base_dir",
                          reason=reasons.get(exc.code, exc.code))


def _validate_cr007(app, oracle, agent, logging_dict, role="all"):
    """Validacoes cruzadas do CR-007: invariantes I3/I4, execucao e a conta Oracle. CR-028 (D4): no papel web,
    so as que valem para ele (invariantes e a conta Oracle); as do agente ficam de fora. CR-030: sem purge."""
    call_s = call_timeout_s(oracle["call_timeout_ms"])
    i3 = agent["heartbeat_interval_s"] + 2 * call_s
    i4 = agent["fence_timeout_s"] + call_s + agent["kill_grace_s"] + 2
    if i3 > agent["fence_timeout_s"] or i4 > agent["node_offline_timeout_s"]:
        # CR-032 (D3): com os tempos de saude fixos, I3 e I4 (README §8.9) so limitam o call_timeout_ms.
        raise ConfigError(
            section="oracle", key="call_timeout_ms",
            reason="call_timeout_ms (%d) acima do limite dos tempos de saude fixos: no maximo 40000 "
                   "(invariantes I3 e I4, README §8.9)" % oracle["call_timeout_ms"])

    if role != "web":
        _validate_agent_paths(app, agent, logging_dict)
    # CR-032 (D11): a conta igual ao owner do esquema e aceita (ambiente com um usuario de banco so).


def _validate_agent_paths(app, agent, logging_dict):
    """Validacoes do agente (CR-007, CR-012, CR-014, CR-019, CR-023): ambientes e pastas."""
    if len(",".join(agent["environments"])) > _ENVIRONMENTS_MAX:
        raise ConfigError(section="agent", key="environments",
                         reason="Lista com mais de %d caracteres (coluna tbsss_agentes.ambientes)" % _ENVIRONMENTS_MAX)

    if agent["output_dir"]:
        # CR-012: a pasta de saida nao se sobrepoe as pastas do SSS (README §8.13).
        if not os.path.isabs(agent["output_dir"]):
            raise ConfigError(section="agent", key="output_dir", reason="Deve ser um caminho absoluto")
        for name, other in (("work_dir", agent["work_dir"]), ("log_dir", logging_dict["log_dir"])):
            if other and (_inside(agent["output_dir"], other) or _inside(other, agent["output_dir"])):
                raise ConfigError(section="agent", key="output_dir",
                                 reason="Nao pode ficar dentro de %s nem conte-lo" % name)
    if agent["input_dir"]:
        # CR-014: a pasta de entrada nao se sobrepoe as pastas do SSS nem a de saida (README §8.14).
        if not os.path.isabs(agent["input_dir"]):
            raise ConfigError(section="agent", key="input_dir", reason="Deve ser um caminho absoluto")
        for name, other in (("work_dir", agent["work_dir"]), ("log_dir", logging_dict["log_dir"]),
                            ("output_dir", agent["output_dir"])):
            if other and (_inside(agent["input_dir"], other) or _inside(other, agent["input_dir"])):
                raise ConfigError(section="agent", key="input_dir",
                                 reason="Nao pode ficar dentro de %s nem conte-lo" % name)
    if agent["script_work_dir"]:
        # CR-019: a pasta de trabalho nao se sobrepoe as pastas do SSS, a de saida nem a de entrada (README §8.15).
        if not os.path.isabs(agent["script_work_dir"]):
            raise ConfigError(section="agent", key="script_work_dir", reason="Deve ser um caminho absoluto")
        for name, other in (("work_dir", agent["work_dir"]), ("log_dir", logging_dict["log_dir"]),
                            ("output_dir", agent["output_dir"]), ("input_dir", agent["input_dir"])):
            if other and (_inside(agent["script_work_dir"], other) or _inside(other, agent["script_work_dir"])):
                raise ConfigError(section="agent", key="script_work_dir",
                                 reason="Nao pode ficar dentro de %s nem conte-lo" % name)
    if agent["script_base_dir"]:
        _validate_script_base_dir(agent, logging_dict["log_dir"])


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

    __slots__ = ("_oracle", "_web", "_environments")

    def __init__(self, oracle_password, cookie_key, environments):
        self._oracle = OracleSecret(oracle_password) if oracle_password is not None else None
        self._web = WebSecret(cookie_key) if cookie_key is not None else None
        self._environments = dict(environments)

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
        return "<Segredos: oracle=%s, web=%s, environments=%r>" % (
            "***" if self._oracle else "None", "***" if self._web else "None",
            sorted(list(self._environments.keys()))
        )

    def __str__(self):
        return "<Segredos: ***redacted***>"


def load_secrets(path, cfg=None, data_backend=None, role="web"):
    """Valida e carrega segredos de arquivo com modo 0600 e ownership restrito.

    papel ('web' ou 'agent', CR-007 D1b) define as secoes lidas e exigidas; as do outro papel sao ignoradas, mas
    mascaradas (README §4.1; CR-032, D14).
    A aplicacao usa sempre o Oracle, entao [oracle] password e obrigatoria para web e agente.
    data_backend='FAKE' so pode vir como parametro explicito de teste (DEV), nunca do config.ini.
    """
    if role not in ROLES:
        raise ConfigError(reason="Papel de segredos invalido: %r" % (role,))
    if not os.path.exists(path):
        raise ConfigError(reason="Arquivo de segredos nao encontrado: %s" % path)

    from sss.platform import os_platform
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

    backend = data_backend

    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
    try:
        with open(path, "r", encoding="utf-8") as f:
            cp.read_file(f)
    except Exception as e:
        raise ConfigError(reason="Erro ao ler arquivo de segredos %s: %s" % (path, e))

    # [web] cookie_key: obrigatorio no papel web; o agente nao o le (README §4.1)
    cookie_key = None
    if role == "web":
        if "web" not in cp.sections():
            raise ConfigError(section="web", key=None, reason="Secao [web] obrigatoria ausente em secrets.cfg")
        if "cookie_key" not in cp["web"]:
            raise ConfigError(section="web", key="cookie_key", reason="Chave cookie_key obrigatoria ausente em [web]")
        cookie_key = cp["web"]["cookie_key"].strip()
        if not cookie_key:
            raise ConfigError(section="web", key="cookie_key", reason="cookie_key nao pode ser vazio")
    # CR-032 (D14): um secrets.cfg por servidor; as secoes dos outros processos sao ignoradas sem aviso (nao
    # validadas), mas os valores delas entram no masking (revisao do CR-032, achado 3): o script roda com a conta
    # do agente e pode ler o arquivo, e o cookie_key ou a senha de um ambiente nunca podem sair num log.
    other_values = []
    if role != "web" and "web" in cp.sections():
        other_values.append(cp["web"].get("cookie_key", "").strip())

    # [oracle] password: em DEV e FAKE e opcional; obrigatorio para web e agente
    oracle_password = None
    is_dev_fake = backend == "FAKE"
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

    # [purge]: o purge foi retirado (CR-030); a secao antiga so gera aviso, e o valor nunca e lido.
    if "purge" in cp.sections():
        _log.warning("secrets.cfg: secao [purge] ignorada: %s; apague a secao", _NO_PURGE)
    # [monitor]: o papel monitor foi retirado (CR-032, D8); o health.py usa a conta do proprio processo.
    if "monitor" in cp.sections():
        _log.warning("secrets.cfg: secao [monitor] ignorada: %s; apague a secao", _NO_MONITOR)

    # [environment:<NOME>]: so no papel agente
    environments = {}
    for sec in cp.sections():
        if sec in ("oracle", "web", "purge", "monitor"):
            continue
        if sec.startswith("environment:"):
            if role != "agent":
                other_values.append(cp[sec].get("password", "").strip())
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

    if role == "agent" and cfg is not None:
        missing = [a for a in cfg.agent.environments if a not in environments]
        if missing:
            raise ConfigError(section="ambiente", key=None,
                             reason="Ambientes atendidos sem credencial em secrets.cfg: %s" % ", ".join(missing))

    secrets_value = Secrets(oracle_password=oracle_password, cookie_key=cookie_key, environments=environments)

    # Import tardio para nao acoplar carregar() ao masking. Sem masking.py a carga de
    # segredos falha (ImportError): segredo sem mascaramento nunca chega aos logs (AGENTS §3.3).
    from sss.core.masking import register_secret

    if oracle_password:
        register_secret(oracle_password)
    if cookie_key:
        register_secret(cookie_key)
    for env_name in environments.values():
        register_secret(env_name.password)
    for value in other_values:
        if value:
            register_secret(value)

    return secrets_value


_CONFIG_CACHE = None


_RE_PROCESS_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,29}$")


def processes() -> List[str]:
    """Processos configurados: pastas de instance/ com config.ini (sem os modelos de exemplos/)."""
    base = os.path.join(APP_DIR, "instance")
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return []
    return [n for n in names if n != "exemplos" and os.path.isfile(os.path.join(base, n, "config.ini"))]


def missing_process_error() -> ConfigError:
    """CR-029 (D1, opcao A): sem --name nem --config nao ha config padrao; a mensagem lista os processos."""
    found = processes()
    return ConfigError(reason="Informe o processo: --name <nome> (em instance/: %s) ou --config <arquivo> (CR-029)"
                              % (", ".join(found) if found else "nenhum; veja instance/exemplos/"))


def config_path(config: "Optional[str]" = None, name: "Optional[str]" = None) -> str:
    """config.ini pedido na linha de comando (CR-028, D7): --config vence; --name <nome> e
    instance/<nome>/config.ini; sem os dois, ConfigError com a lista dos processos (CR-029)."""
    if config:
        return config
    if name:
        if not _RE_PROCESS_NAME.match(name):
            raise ConfigError(reason="Nome de processo invalido: '%s' (ex.: web0001, agente0001)" % name)
        return os.path.join(APP_DIR, "instance", name, "config.ini")
    raise missing_process_error()


def _raw_log_dir(ini_path):
    """var/<name>/logs pelo [app] name lido sem validacao (CR-032, D4), so para registrar o CRITICAL de uma
    configuracao invalida."""
    try:
        cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
        with open(ini_path, "r", encoding="utf-8") as f:
            cp.read_file(f)
        name = cp.get("app", "name", fallback="").strip()
        return os.path.join(VAR_DIR, name, "logs") if _RE_PROCESS_NAME.match(name) else None
    except (OSError, ValueError, configparser.Error):
        return None


def _abort(log_name, exc, log_dir):
    from sss.config import sss_logging
    sss_logging.log_initial_critical(log_name, "Subida abortada: configuracao invalida: %s" % exc, log_dir)


def get_config(log_name=None, path=None):
    """Retorna a configuracao validada, carregada uma unica vez por processo.

    Com log_name ('sss_web' ou 'sss_scheduler'), uma falha e registrada em CRITICAL antes de
    ser relancada (README §12.1, "Falha de configuracao"). caminho: outro config.ini (so o
    agente, por --config do run_scheduler; README §12.2). Sem ele e sem cache, ConfigError: nao ha
    config padrao (CR-029).
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        if not path:
            raise missing_process_error()
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

    papel: 'web' (nó web) ou 'agent' (daemon), README §4.1.
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
    """Texto canonico dos parametros que precisam coincidir nos nos (README §8.12). CR-032 (D16): os demais
    sao fixos no codigo; sobram o call_timeout_ms (em segundos) e a misfire_policy."""
    return "call=%s;misfire=%s" % (call_timeout_s(cfg.oracle.call_timeout_ms), cfg.agent.misfire_policy)
