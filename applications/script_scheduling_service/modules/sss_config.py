# -*- coding: utf-8 -*-
"""Carga e validacao tipada da configuracao do SSS e de segredos.

Compativel estritamente com Python 3.6. Sem dependencias externas.
Valida todas as secoes e chaves do README §12.1 e §4.1 de forma declarativa e fail-fast.
"""
import collections
import configparser
import os
import re
import stat


BLOCKED_ENV_VARS = frozenset([
    "LD_PRELOAD", "LD_AUDIT", "PYTHONPATH", "PYTHONHOME",
    "PYTHONSTARTUP", "PYTHONINSPECT", "BASH_ENV", "ENV",
    "SHELLOPTS", "BASHOPTS", "IFS", "PERL5LIB", "PERL5OPT"
])


class ConfigErro(Exception):
    """Excecao para falhas de configuracao e validacao tipada."""

    def __init__(self, secao=None, chave=None, motivo=None):
        if chave is None and motivo is None and secao is not None:
            self.motivo = str(secao)
            self.secao = None
            self.chave = None
        else:
            self.secao = secao
            self.chave = chave
            self.motivo = motivo

        partes = []
        if self.secao:
            partes.append("[%s]" % self.secao)
        if self.chave:
            partes.append(self.chave)
        if self.motivo:
            partes.append(str(self.motivo))
        msg = ": ".join(partes) if partes else "Erro de configuracao"
        super(ConfigErro, self).__init__(msg)


class CampoDef(object):
    """Definicao declarativa de um campo de configuracao."""

    __slots__ = (
        "tipo", "obrigatorio", "min_val", "max_val",
        "allowed_values", "regex", "default"
    )

    def __init__(self, tipo, obrigatorio=True, min_val=None, max_val=None,
                 allowed_values=None, regex=None, default=None):
        self.tipo = tipo  # 'str', 'int', 'bool', 'enum', 'list_csv', 'path'
        self.obrigatorio = obrigatorio
        self.min_val = min_val
        self.max_val = max_val
        self.allowed_values = tuple(allowed_values) if allowed_values else None
        self.regex = regex
        self.default = default


# Esquema declarativo completo de todas as secoes e chaves (README §12.1)
SCHEMA = collections.OrderedDict([
    ("app", collections.OrderedDict([
        ("sss_env", CampoDef("enum", obrigatorio=True, allowed_values=("DEV", "HML", "PROD"))),
        ("data_backend", CampoDef("enum", obrigatorio=True, allowed_values=("FAKE", "ORACLE"))),
    ])),
    ("oracle", collections.OrderedDict([
        ("user", CampoDef("str", obrigatorio=True)),
        ("dsn", CampoDef("str", obrigatorio=True)),
        ("owner", CampoDef("str", obrigatorio=True, regex=r"^[A-Za-z][A-Za-z0-9_]{0,29}$")),
        ("table_prefix", CampoDef("str", obrigatorio=True, regex=r"^[A-Za-z][A-Za-z0-9_]{0,7}$")),
        ("driver", CampoDef("enum", obrigatorio=True, allowed_values=("oracledb", "cx_Oracle"))),
        ("use_thick_mode", CampoDef("bool", obrigatorio=True)),
        ("oracle_client_lib_dir", CampoDef("path", obrigatorio=False, default=None)),
        ("call_timeout_ms", CampoDef("int", obrigatorio=True, min_val=1, max_val=3600000)),
        ("pool_min", CampoDef("int", obrigatorio=True, min_val=1, max_val=1000)),
        ("pool_max", CampoDef("int", obrigatorio=True, min_val=1, max_val=1000)),
    ])),
    ("secrets", collections.OrderedDict([
        ("secrets_file", CampoDef("path", obrigatorio=True)),
    ])),
    ("agent", collections.OrderedDict([
        ("agent_id", CampoDef("str", obrigatorio=True, regex=r"^[A-Za-z0-9._-]{1,30}$")),
        ("ambientes_atendidos", CampoDef("list_csv", obrigatorio=True)),
        ("work_dir", CampoDef("path", obrigatorio=True)),
        ("script_owner_uids", CampoDef("list_csv", obrigatorio=True)),
        ("max_parallel_jobs", CampoDef("int", obrigatorio=True, min_val=1, max_val=999)),
        ("max_parallel_hard_limit", CampoDef("int", obrigatorio=True, min_val=1, max_val=999)),
        ("claim_batch_size", CampoDef("int", obrigatorio=True, min_val=1, max_val=1000)),
        ("schedule_batch_size", CampoDef("int", obrigatorio=True, min_val=1, max_val=1000)),
        ("orchestrator_interval_s", CampoDef("int", obrigatorio=True, min_val=1, max_val=3600)),
        ("cancel_poll_interval_s", CampoDef("int", obrigatorio=True, min_val=1, max_val=3600)),
        ("heartbeat_interval_s", CampoDef("int", obrigatorio=True, min_val=1, max_val=3600)),
        ("fence_timeout_s", CampoDef("int", obrigatorio=True, min_val=1, max_val=86400)),
        ("node_offline_timeout_s", CampoDef("int", obrigatorio=True, min_val=1, max_val=86400)),
        ("kill_grace_s", CampoDef("int", obrigatorio=True, min_val=1, max_val=300)),
        ("script_timeout_s", CampoDef("int", obrigatorio=True, min_val=1, max_val=86400)),
        ("shutdown_mode", CampoDef("enum", obrigatorio=True, allowed_values=("TERMINATE", "DRAIN"))),
        ("shutdown_grace_s", CampoDef("int", obrigatorio=True, min_val=1, max_val=3600)),
        ("misfire_policy", CampoDef("enum", obrigatorio=True, allowed_values=("RUN_ONCE", "SKIP"))),
        ("misfire_tolerance_s", CampoDef("int", obrigatorio=True, min_val=1, max_val=86400)),
        ("cron_horizon_days", CampoDef("int", obrigatorio=True, min_val=1, max_val=36500)),
        ("child_locale", CampoDef("str", obrigatorio=True)),
        ("env_passthrough", CampoDef("list_csv", obrigatorio=False, default=())),
    ])),
    ("logging", collections.OrderedDict([
        ("log_dir", CampoDef("path", obrigatorio=True)),
        ("level", CampoDef("enum", obrigatorio=True, allowed_values=("DEBUG", "INFO", "WARN", "ERROR"))),
        ("app_log_max_bytes", CampoDef("int", obrigatorio=True, min_val=1024, max_val=1073741824)),
        ("app_log_retention_days", CampoDef("int", obrigatorio=True, min_val=1, max_val=3650)),
        ("max_log_size_bytes", CampoDef("int", obrigatorio=True, min_val=1024, max_val=1073741824)),
        ("max_local_log_size_bytes", CampoDef("int", obrigatorio=True, min_val=1024, max_val=10737418240)),
        ("local_log_retention_days", CampoDef("int", obrigatorio=True, min_val=1, max_val=3650)),
    ])),
    ("web", collections.OrderedDict([
        ("session_idle_timeout_s", CampoDef("int", obrigatorio=True, min_val=1, max_val=86400)),
        ("login_max_tentativas", CampoDef("int", obrigatorio=True, min_val=1, max_val=99)),
        ("login_bloqueio_s", CampoDef("int", obrigatorio=True, min_val=1, max_val=86400)),
        ("log_poll_interval_s", CampoDef("int", obrigatorio=True, min_val=1, max_val=3600)),
        ("trusted_proxies", CampoDef("list_csv", obrigatorio=False, default=())),
        ("allowed_origins", CampoDef("list_csv", obrigatorio=True)),
    ])),
    ("retencao", collections.OrderedDict([
        ("ticket_retention_days", CampoDef("int", obrigatorio=True, min_val=1, max_val=3650)),
        ("audit_retention_days", CampoDef("int", obrigatorio=True, min_val=1, max_val=3650)),
        ("purge_batch_size", CampoDef("int", obrigatorio=True, min_val=1, max_val=100000)),
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


class AppConfig(_ItemAccessMixin, collections.namedtuple("AppConfig", ["sss_env", "data_backend"])):
    __slots__ = ()


class OracleConfig(_ItemAccessMixin, collections.namedtuple("OracleConfig", [
    "user", "dsn", "owner", "table_prefix", "driver",
    "use_thick_mode", "oracle_client_lib_dir", "call_timeout_ms",
    "pool_min", "pool_max"
])):
    __slots__ = ()


class SecretsConfig(_ItemAccessMixin, collections.namedtuple("SecretsConfig", ["secrets_file"])):
    __slots__ = ()


class AgentConfig(_ItemAccessMixin, collections.namedtuple("AgentConfig", [
    "agent_id", "ambientes_atendidos", "work_dir",
    "script_owner_uids", "max_parallel_jobs", "max_parallel_hard_limit",
    "claim_batch_size", "schedule_batch_size", "orchestrator_interval_s",
    "cancel_poll_interval_s", "heartbeat_interval_s", "fence_timeout_s",
    "node_offline_timeout_s", "kill_grace_s", "script_timeout_s",
    "shutdown_mode", "shutdown_grace_s", "misfire_policy",
    "misfire_tolerance_s", "cron_horizon_days", "child_locale",
    "env_passthrough"
])):
    __slots__ = ()


class LoggingConfig(_ItemAccessMixin, collections.namedtuple("LoggingConfig", [
    "log_dir", "level", "app_log_max_bytes", "app_log_retention_days",
    "max_log_size_bytes", "max_local_log_size_bytes", "local_log_retention_days"
])):
    __slots__ = ()


class WebConfig(_ItemAccessMixin, collections.namedtuple("WebConfig", [
    "session_idle_timeout_s", "login_max_tentativas", "login_bloqueio_s",
    "log_poll_interval_s", "trusted_proxies", "allowed_origins"
])):
    __slots__ = ()


class RetencaoConfig(_ItemAccessMixin, collections.namedtuple("RetencaoConfig", [
    "ticket_retention_days", "audit_retention_days", "purge_batch_size"
])):
    __slots__ = ()


class Config(_ItemAccessMixin, collections.namedtuple("Config", [
    "app", "oracle", "secrets", "agent", "logging", "web", "retencao"
])):
    __slots__ = ()


def _converter_valor(secao, chave, cdef, raw_val):
    """Converte e valida um valor individual com base em CampoDef."""
    if raw_val is None:
        if cdef.obrigatorio:
            raise ConfigErro(secao, chave, "Chave obrigatoria ausente")
        return cdef.default

    val_str = str(raw_val).strip()

    if cdef.tipo == "str":
        if not val_str:
            if cdef.obrigatorio:
                raise ConfigErro(secao, chave, "Valor obrigatorio nao pode ser vazio")
            return cdef.default
        if cdef.regex and not re.fullmatch(cdef.regex, val_str):
            raise ConfigErro(
                secao, chave,
                "Valor '%s' nao atende ao padrao exigido '%s'" % (val_str, cdef.regex)
            )
        return val_str

    elif cdef.tipo == "path":
        if not val_str:
            if cdef.obrigatorio:
                raise ConfigErro(secao, chave, "Caminho obrigatorio nao pode ser vazio")
            return cdef.default
        return os.path.normpath(val_str)

    elif cdef.tipo == "int":
        if not val_str:
            if cdef.obrigatorio:
                raise ConfigErro(secao, chave, "Valor inteiro obrigatorio ausente")
            return cdef.default
        try:
            val_int = int(val_str)
        except ValueError:
            raise ConfigErro(secao, chave, "Valor inteiro invalido: '%s'" % val_str)

        if cdef.min_val is not None and val_int < cdef.min_val:
            raise ConfigErro(
                secao, chave,
                "Valor %d abaixo do minimo permitido (%d)" % (val_int, cdef.min_val)
            )
        if cdef.max_val is not None and val_int > cdef.max_val:
            raise ConfigErro(
                secao, chave,
                "Valor %d acima do maximo permitido (%d)" % (val_int, cdef.max_val)
            )
        return val_int

    elif cdef.tipo == "bool":
        if not val_str:
            if cdef.obrigatorio:
                raise ConfigErro(secao, chave, "Valor booleano obrigatorio ausente")
            return cdef.default
        low = val_str.lower()
        if low in ("true", "1", "yes", "on"):
            return True
        elif low in ("false", "0", "no", "off"):
            return False
        raise ConfigErro(secao, chave, "Valor booleano invalido: '%s'" % val_str)

    elif cdef.tipo == "enum":
        if not val_str:
            if cdef.obrigatorio:
                raise ConfigErro(secao, chave, "Valor obrigatorio ausente")
            return cdef.default
        if cdef.allowed_values and val_str not in cdef.allowed_values:
            raise ConfigErro(
                secao, chave,
                "Valor '%s' invalido. Permitidos: %s" % (
                    val_str, ", ".join(cdef.allowed_values)
                )
            )
        return val_str

    elif cdef.tipo == "list_csv":
        if not val_str:
            if cdef.obrigatorio:
                raise ConfigErro(secao, chave, "Lista obrigatoria nao pode ser vazia")
            return cdef.default

        partes = [p.strip() for p in val_str.split(",") if p.strip()]
        if cdef.obrigatorio and not partes:
            raise ConfigErro(secao, chave, "Lista obrigatoria nao pode ser vazia")

        if chave == "script_owner_uids":
            uids = []
            for item in partes:
                try:
                    uid = int(item)
                    if uid < 0:
                        raise ValueError()
                    uids.append(uid)
                except ValueError:
                    raise ConfigErro(
                        secao, chave,
                        "UID invalido na lista de donos: '%s'" % item
                    )
            return tuple(uids)

        return tuple(partes)

    raise ConfigErro(secao, chave, "Tipo de campo desconhecido no schema: '%s'" % cdef.tipo)


def carregar(caminho_ini):
    """Carrega e valida o config.ini de forma declarativa e fail-fast.

    Retorna uma instancia imutavel de Config.
    """
    if not os.path.exists(caminho_ini):
        raise ConfigErro(motivo="Arquivo de configuracao nao encontrado: %s" % caminho_ini)

    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
    try:
        with open(caminho_ini, "r", encoding="utf-8") as f:
            cp.read_file(f)
    except Exception as e:
        raise ConfigErro(motivo="Erro ao ler arquivo de configuracao %s: %s" % (caminho_ini, e))

    # 1. Validar secoes desconhecidas
    for sec in cp.sections():
        if sec not in SCHEMA:
            raise ConfigErro(secao=sec, chave=None, motivo="Secao desconhecida no config.ini: [%s]" % sec)

    # 2. Validar presenca e chaves de cada secao
    dados_secoes = {}
    for sec_nome, sec_campos in SCHEMA.items():
        if sec_nome not in cp.sections():
            raise ConfigErro(secao=sec_nome, chave=None, motivo="Secao obrigatoria ausente: [%s]" % sec_nome)

        cp_sec = cp[sec_nome]

        # Chaves desconhecidas na secao
        for k in cp_sec:
            if k not in sec_campos:
                raise ConfigErro(secao=sec_nome, chave=k, motivo="Chave desconhecida na secao [%s]: %s" % (sec_nome, k))

        # Validar e converter cada chave esperada
        dados_sec = {}
        for k, cdef in sec_campos.items():
            if k not in cp_sec:
                if cdef.obrigatorio:
                    raise ConfigErro(
                        secao=sec_nome, chave=k,
                        motivo="Chave obrigatoria ausente na secao [%s]: %s" % (sec_nome, k)
                    )
                dados_sec[k] = cdef.default
            else:
                raw = cp_sec[k]
                dados_sec[k] = _converter_valor(sec_nome, k, cdef, raw)

        dados_secoes[sec_nome] = dados_sec

    # 3. Validacao de env_passthrough contra allowlist/blocklist
    agent_dict = dados_secoes["agent"]
    for env_var in agent_dict["env_passthrough"]:
        if env_var.upper() in BLOCKED_ENV_VARS or env_var in BLOCKED_ENV_VARS:
            raise ConfigErro(
                secao="agent", chave="env_passthrough",
                motivo="Variavel bloqueada nao permitida em env_passthrough: '%s'" % env_var
            )

    # 4. Invariantes
    app_dict = dados_secoes["app"]
    if app_dict["data_backend"] == "FAKE" and app_dict["sss_env"] != "DEV":
        raise ConfigErro(
            secao="app", chave="data_backend",
            motivo="data_backend=FAKE exige sss_env=DEV (atual: %s)" % app_dict["sss_env"]
        )

    oracle_dict = dados_secoes["oracle"]
    if oracle_dict["pool_min"] > oracle_dict["pool_max"]:
        raise ConfigErro(
            secao="oracle", chave="pool_min",
            motivo="pool_min (%d) nao pode ser maior que pool_max (%d)" % (
                oracle_dict["pool_min"], oracle_dict["pool_max"]
            )
        )

    if agent_dict["max_parallel_jobs"] > agent_dict["max_parallel_hard_limit"]:
        raise ConfigErro(
            secao="agent", chave="max_parallel_jobs",
            motivo="max_parallel_jobs (%d) nao pode ser maior que max_parallel_hard_limit (%d)" % (
                agent_dict["max_parallel_jobs"], agent_dict["max_parallel_hard_limit"]
            )
        )

    if agent_dict["fence_timeout_s"] * 2 > agent_dict["node_offline_timeout_s"]:
        raise ConfigErro(
            secao="agent", chave="fence_timeout_s",
            motivo="Invariante violada: fence_timeout_s * 2 (%d) deve ser <= node_offline_timeout_s (%d)" % (
                agent_dict["fence_timeout_s"] * 2, agent_dict["node_offline_timeout_s"]
            )
        )

    if agent_dict["heartbeat_interval_s"] * 3 > agent_dict["fence_timeout_s"]:
        raise ConfigErro(
            secao="agent", chave="heartbeat_interval_s",
            motivo="Invariante violada: heartbeat_interval_s * 3 (%d) deve ser <= fence_timeout_s (%d)" % (
                agent_dict["heartbeat_interval_s"] * 3, agent_dict["fence_timeout_s"]
            )
        )

    # 5. Instanciar arvore de configuracao imutavel
    app_cfg = AppConfig(**app_dict)
    oracle_cfg = OracleConfig(**oracle_dict)
    secrets_cfg = SecretsConfig(**dados_secoes["secrets"])
    agent_cfg = AgentConfig(**agent_dict)
    logging_cfg = LoggingConfig(**dados_secoes["logging"])
    web_cfg = WebConfig(**dados_secoes["web"])
    retencao_cfg = RetencaoConfig(**dados_secoes["retencao"])

    return Config(
        app=app_cfg,
        oracle=oracle_cfg,
        secrets=secrets_cfg,
        agent=agent_cfg,
        logging=logging_cfg,
        web=web_cfg,
        retencao=retencao_cfg
    )


class OracleSegredo(object):
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


class WebSegredo(object):
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


class AmbienteSegredo(object):
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


class Segredos(object):
    """Container seguro de segredos carregados do secrets.cfg."""

    __slots__ = ("_oracle", "_web", "_ambientes")

    def __init__(self, oracle_password, cookie_key, ambientes):
        self._oracle = OracleSegredo(oracle_password) if oracle_password is not None else None
        self._web = WebSegredo(cookie_key)
        self._ambientes = dict(ambientes)

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
        return self._web.cookie_key

    @property
    def ambientes(self):
        return self._ambientes

    def get_ambiente(self, nome):
        return self._ambientes.get(nome)

    def __getitem__(self, item):
        if item == "oracle":
            if self._oracle is None:
                raise KeyError(item)
            return {"password": self.oracle_password}
        elif item == "web":
            return {"cookie_key": self.cookie_key}
        elif item.startswith("ambiente:"):
            nome = item.split(":", 1)[1]
            amb = self.get_ambiente(nome)
            if amb is None:
                raise KeyError(item)
            return {"user": amb.user, "password": amb.password}
        elif item in self._ambientes:
            amb = self._ambientes[item]
            return {"user": amb.user, "password": amb.password}
        raise KeyError(item)

    def __repr__(self):
        return "<Segredos: oracle=%s, web=***, ambientes=%r>" % (
            "***" if self._oracle else "None",
            sorted(list(self._ambientes.keys()))
        )

    def __str__(self):
        return "<Segredos: ***redacted***>"


def carregar_segredos(caminho, cfg=None, sss_env=None, data_backend=None):
    """Valida e carrega segredos de arquivo com modo 0600 e ownership restrito."""
    if not os.path.exists(caminho):
        raise ConfigErro(motivo="Arquivo de segredos nao encontrado: %s" % caminho)

    try:
        st = os.stat(caminho)
    except OSError as e:
        raise ConfigErro(motivo="Erro ao obter informacoes do arquivo de segredos %s: %s" % (caminho, e))

    if not stat.S_ISREG(st.st_mode):
        raise ConfigErro(motivo="Arquivo de segredos deve ser um arquivo regular: %s" % caminho)

    if st.st_uid != os.geteuid():
        raise ConfigErro(
            motivo="Arquivo de segredos deve pertencer ao usuario corrente (UID %d, atual %d)" % (
                os.geteuid(), st.st_uid
            )
        )

    if (st.st_mode & 0o077) != 0:
        raise ConfigErro(
            motivo="Arquivo de segredos possui permissoes inseguras (mode %o, esperado sem acesso grupo/outros)" % (
                st.st_mode & 0o777
            )
        )

    if cfg is not None:
        env = getattr(cfg.app, "sss_env", sss_env)
        backend = getattr(cfg.app, "data_backend", data_backend)
    else:
        env = sss_env
        backend = data_backend

    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            cp.read_file(f)
    except Exception as e:
        raise ConfigErro(motivo="Erro ao ler arquivo de segredos %s: %s" % (caminho, e))

    # [web] cookie_key e obrigatorio sempre
    if "web" not in cp.sections():
        raise ConfigErro(secao="web", chave=None, motivo="Secao [web] obrigatoria ausente em secrets.cfg")
    if "cookie_key" not in cp["web"]:
        raise ConfigErro(secao="web", chave="cookie_key", motivo="Chave cookie_key obrigatoria ausente em [web]")
    cookie_key = cp["web"]["cookie_key"].strip()
    if not cookie_key:
        raise ConfigErro(secao="web", chave="cookie_key", motivo="cookie_key nao pode ser vazio")

    # [oracle] password: em DEV e FAKE e opcional; caso contrario, obrigatorio
    oracle_password = None
    is_dev_fake = (env == "DEV" and backend == "FAKE")
    if "oracle" in cp.sections():
        if "password" not in cp["oracle"]:
            if not is_dev_fake:
                raise ConfigErro(secao="oracle", chave="password", motivo="Chave password obrigatoria ausente em [oracle]")
        else:
            pwd = cp["oracle"]["password"].strip()
            if not pwd and not is_dev_fake:
                raise ConfigErro(secao="oracle", chave="password", motivo="password do oracle nao pode ser vazio")
            oracle_password = pwd if pwd else None
    else:
        if not is_dev_fake:
            raise ConfigErro(secao="oracle", chave=None, motivo="Secao [oracle] obrigatoria ausente em secrets.cfg")

    # [ambiente:<NOME>]
    ambientes = {}
    for sec in cp.sections():
        if sec in ("oracle", "web"):
            continue
        if sec.startswith("ambiente:"):
            nome = sec.split(":", 1)[1].strip()
            if not nome:
                raise ConfigErro(secao=sec, chave=None, motivo="Nome de ambiente invalido na secao [%s]" % sec)
            if "user" not in cp[sec]:
                raise ConfigErro(secao=sec, chave="user", motivo="Chave user obrigatoria ausente em [%s]" % sec)
            if "password" not in cp[sec]:
                raise ConfigErro(secao=sec, chave="password", motivo="Chave password obrigatoria ausente em [%s]" % sec)
            u = cp[sec]["user"].strip()
            p = cp[sec]["password"].strip()
            if not u:
                raise ConfigErro(secao=sec, chave="user", motivo="user nao pode ser vazio em [%s]" % sec)
            if not p:
                raise ConfigErro(secao=sec, chave="password", motivo="password nao pode ser vazio em [%s]" % sec)
            ambientes[nome] = AmbienteSegredo(user=u, password=p)
        else:
            raise ConfigErro(secao=sec, chave=None, motivo="Secao desconhecida em secrets.cfg: [%s]" % sec)

    segredos = Segredos(oracle_password=oracle_password, cookie_key=cookie_key, ambientes=ambientes)

    # Import tardio para nao acoplar carregar() ao masking. Sem masking.py a carga de
    # segredos falha (ImportError): segredo sem mascaramento nunca chega aos logs (AGENTS §3.3).
    from masking import registrar_segredo

    if oracle_password:
        registrar_segredo(oracle_password)
    registrar_segredo(cookie_key)
    for amb in ambientes.values():
        registrar_segredo(amb.password)

    return segredos


_CONFIG_CACHE = None


def caminho_config_padrao():
    """Caminho canonico do config.ini da aplicacao (instance/config.ini)."""
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(app_dir, "instance", "config.ini")


def _log_dir_bruto(caminho_ini):
    """[logging] log_dir lido sem validacao, so para registrar o CRITICAL de uma configuracao invalida."""
    try:
        cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
        with open(caminho_ini, "r", encoding="utf-8") as f:
            cp.read_file(f)
        valor = cp.get("logging", "log_dir", fallback="").strip()
        return valor or None
    except (OSError, ValueError, configparser.Error):
        return None


def _abortar(nome_log, exc, log_dir):
    import sss_logging
    sss_logging.registrar_critico_inicial(nome_log, "Subida abortada: configuracao invalida: %s" % exc, log_dir)


def obter_config(nome_log=None):
    """Retorna a configuracao validada, carregada uma unica vez por processo.

    Com nome_log ('sss_web' ou 'sss_scheduler'), uma falha e registrada em CRITICAL antes de
    ser relancada (README §12.1, "Falha de configuracao").
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        caminho = caminho_config_padrao()
        try:
            # Corrida entre threads do servidor web apenas recarrega o mesmo arquivo imutavel.
            _CONFIG_CACHE = carregar(caminho)
        except ConfigErro as exc:
            if nome_log:
                _abortar(nome_log, exc, _log_dir_bruto(caminho))
            raise
    return _CONFIG_CACHE


def reset_config_cache():
    """Descarta a configuracao em cache (uso em testes)."""
    global _CONFIG_CACHE
    _CONFIG_CACHE = None


_SEGREDOS_CACHE = None


def obter_segredos(nome_log=None):
    """Retorna os segredos validados de [secrets] secrets_file, carregados uma unica vez por processo.

    Com nome_log, uma falha e registrada em CRITICAL (sem valores de segredo) antes de ser relancada.
    """
    global _SEGREDOS_CACHE
    if _SEGREDOS_CACHE is None:
        cfg = obter_config(nome_log)
        try:
            _SEGREDOS_CACHE = carregar_segredos(cfg.secrets.secrets_file, cfg=cfg)
        except ConfigErro as exc:
            if nome_log:
                _abortar(nome_log, exc, cfg.logging.log_dir)
            raise
    return _SEGREDOS_CACHE


def reset_segredos_cache():
    """Descarta os segredos em cache (uso em testes)."""
    global _SEGREDOS_CACHE
    _SEGREDOS_CACHE = None
