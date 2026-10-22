# -*- coding: utf-8 -*-
"""Ponto unico de conexao e selecao de driver Oracle (CR-002, AGENTS §2.2, F7.2).

Responsavel pela selecao adaptativa (Thin -> Thick -> cx_Oracle) via sondagem isolada em
subprocesso, pela inicializacao do driver vencedor, conexao tipada por papel, pool,
gerenciamento transacional, binds neutros, classificacao de erros e reconexao resiliente.
Nenhum outro modulo da aplicacao importa oracledb ou cx_Oracle.
"""
import collections
import contextlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time

import sss_config
import sss_logging
try:
    import os_platform
except ImportError:
    from modules import os_platform
try:
    import sql_ident
except ImportError:
    from modules import sql_ident

logger = logging.getLogger("sss_db_conn")

_SELECTION_LOCK = threading.Lock()
_DRIVER_SELECTION = None
_DRIVER_INITIALIZED = None
_BUDGET_WARNING_EMITTED = False

CANDIDATOS_VALIDOS = ("thin", "thick", "cx_oracle")

# Tipos neutros de bind para isolar diferencas entre oracledb e cx_Oracle (F7.2)
TIPO_DATE = "TIPO_DATE"
TIPO_CLOB = "TIPO_CLOB"
TIPO_BLOB = "TIPO_BLOB"  # zip da saida do ticket (CR-012)
TIPO_NUMBER = "TIPO_NUMBER"
TIPO_VARCHAR = "TIPO_VARCHAR"
TIPOS_NEUTROS = (TIPO_DATE, TIPO_CLOB, TIPO_BLOB, TIPO_NUMBER, TIPO_VARCHAR)

DriverSelection = collections.namedtuple("DriverSelection", [
    "candidate", "server_version", "driver_version", "client_version"
])


class SchemaVersionError(Exception):
    """Lancado quando a versao de esquema no banco difere da esperada pela aplicacao."""
    pass


def _get_password(segredos):
    """Extrai a senha Oracle de Segredos, dict ou mock."""
    if segredos is None:
        return ""
    if hasattr(segredos, "oracle") and segredos.oracle:
        return getattr(segredos.oracle, "password", "") or ""
    if hasattr(segredos, "oracle_password"):
        return getattr(segredos, "oracle_password", "") or ""
    if hasattr(segredos, "password"):
        return getattr(segredos, "password", "") or ""
    if isinstance(segredos, dict):
        oracle_dict = segredos.get("oracle")
        if isinstance(oracle_dict, dict):
            return oracle_dict.get("password") or ""
        return segredos.get("password") or ""
    return ""


def _log_critical(msg, cfg=None):
    """Registra falha fatal em CRITICAL conforme README §13 e AGENTS §2.2."""
    log_dir = None
    if cfg and hasattr(cfg, "logging") and hasattr(cfg.logging, "log_dir"):
        log_dir = cfg.logging.log_dir
    elif hasattr(cfg, "log_dir"):
        log_dir = getattr(cfg, "log_dir")

    # Garante que o logger do modulo emita no nivel CRITICAL (capturavel por assertLogs)
    logger.critical(msg, extra={"agent": "-", "ticket": "-", "action": "SELECAO_DRIVER"})

    # Se nao houver handlers configurados na hierarquia, envia para arquivo/stderr via sss_logging
    if not logger.handlers and not logging.getLogger().handlers:
        sss_logging.log_initial_critical("sss_db_conn", msg, log_dir)


def _run_probe_subprocess(candidato, cfg, senha, usuario=None):
    """Executa scripts/probe_driver.py em subprocesso isolado com sys.executable -I.

    usuario: a conta do papel que vai conectar (F9.1d; sem ele, [oracle] user). Nao e segredo e vai no argv; a
    senha vai so pela entrada padrao."""
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.dirname(scripts_dir)
    sondar_script = os.path.join(app_dir, "scripts", "probe_driver.py")

    cmd = [sys.executable, "-I", sondar_script, candidato]
    caminho_cfg = getattr(cfg, "caminho_arquivo", None)
    if caminho_cfg and os.path.isfile(caminho_cfg):
        cmd.extend(["--config", caminho_cfg])
    if usuario:
        cmd.extend(["--user", usuario])

    timeout_ms = getattr(cfg.oracle, "call_timeout_ms", 30000) if hasattr(cfg, "oracle") else 30000
    timeout_s = (2.0 * float(timeout_ms)) / 1000.0
    if timeout_s < 1.0:
        timeout_s = 1.0

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
        )
        stdout_bytes, _stderr = proc.communicate(
            input=(senha or "").encode("utf-8"),
            timeout=timeout_s,
        )
        if proc.returncode != 0:
            return {
                "candidate": candidato,
                "ok": False,
                "error_code": "EXIT_%d" % proc.returncode,
                "category": "OTHER",
            }

        linha = stdout_bytes.decode("utf-8", "replace").strip()
        if not linha:
            return {
                "candidate": candidato,
                "ok": False,
                "error_code": "SEM_SAIDA",
                "category": "OTHER",
            }
        return json.loads(linha)

    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.communicate()
        except Exception:
            pass
        return {
            "candidate": candidato,
            "ok": False,
            "error_code": "TIMEOUT",
            "category": "NETWORK",
        }
    except Exception as exc:
        return {
            "candidate": candidato,
            "ok": False,
            "error_code": "SUBPROCESS_ERROR: %s" % exc,
            "category": "OTHER",
        }


def select_driver(cfg, segredos, executor_sondagem=None, usuario=None, senha=None):
    """Sonda e seleciona a combinacao de driver Oracle apropriada.

    Em 'auto': Thin -> Thick -> cx_Oracle. usuario e senha: as credenciais do papel que vai conectar (F9.1d:
    o monitor e o purge nao usam a conta do [oracle]); sem eles, [oracle] user e password.
    Interrompe a cadeia imediatamente em falhas de AUTENTICACAO.
    Falhas fatais geram registro em CRITICAL e RuntimeError.
    """
    global _DRIVER_SELECTION
    with _SELECTION_LOCK:
        if _DRIVER_SELECTION is not None:
            return _DRIVER_SELECTION

        modo = getattr(cfg.oracle, "driver_mode", "auto") if hasattr(cfg, "oracle") else "auto"
        if modo not in ("auto", "thin", "thick", "cx_oracle"):
            msg = "Falha de configuracao: driver_mode '%s' invalido. Valores aceitos: auto, thin, thick, cx_oracle" % modo
            _log_critical(msg, cfg)
            raise RuntimeError(msg)

        if modo == "auto":
            candidatos = list(CANDIDATOS_VALIDOS)
        else:
            candidatos = [modo]

        if senha is None:
            senha = _get_password(segredos)
        tentativas = []
        sondador = executor_sondagem
        if sondador is None:
            def sondador(cand, cfg_sondagem, senha_sondagem):
                return _run_probe_subprocess(cand, cfg_sondagem, senha_sondagem, usuario=usuario)

        for cand in candidatos:
            res = sondador(cand, cfg, senha)
            if res.get("ok"):
                selecao = DriverSelection(
                    candidate=cand,
                    server_version=res.get("server_version"),
                    driver_version=res.get("driver_version"),
                    client_version=res.get("client_version"),
                )
                _DRIVER_SELECTION = selecao
                return selecao

            codigo = res.get("error_code") or "DESCONHECIDO"
            categoria = res.get("category") or "OTHER"
            tentativas.append((cand, codigo, categoria))

            logger.warning(
                "Sondagem do candidato Oracle '%s' falhou: codigo=%s categoria=%s",
                cand, codigo, categoria,
                extra={"agent": "-", "ticket": "-", "action": "SELECAO_DRIVER"},
            )

            # Falha de autenticacao interrompe imediatamente a cadeia (README §2.3)
            if categoria == "AUTHENTICATION":
                msg = (
                    "Falha fatal de autenticacao Oracle com candidato '%s' (codigo=%s). "
                    "Cadeia interrompida para proteger a conta."
                ) % (cand, codigo)
                _log_critical(msg, cfg)
                raise RuntimeError(msg)

        # Se chegou aqui, todos os candidatos falharam ou candidato forcado falhou
        detalhe_tentativas = "; ".join(["%s (%s: %s)" % (c, cat, cod) for c, cod, cat in tentativas])
        if modo != "auto":
            msg = "Falha fatal: candidato forçado '%s' falhou (%s)" % (modo, detalhe_tentativas)
        else:
            msg = "Falha fatal: todos os candidatos de driver Oracle falharam (%s)" % detalhe_tentativas

        _log_critical(msg, cfg)
        raise RuntimeError(msg)


def initialize(selecao, cfg=None):
    """Importa o driver vencedor no processo principal e inicializa Thick/cx_Oracle se necessario."""
    global _DRIVER_INITIALIZED
    with _SELECTION_LOCK:
        if _DRIVER_INITIALIZED is not None:
            return _DRIVER_INITIALIZED

        if selecao is None:
            raise RuntimeError("selecao de driver nao fornecida para inicializar()")

        candidato = selecao.candidate
        driver = None

        if candidato in ("thin", "thick"):
            import oracledb
            # Validacao estrita: python-oracledb 2.x e proibido no Python 3.6 (README §2.3)
            versao_str = getattr(oracledb, "__version__", "")
            if sys.version_info < (3, 7) and versao_str.startswith("2."):
                msg = "Falha de configuracao: python-oracledb 2.x nao e compativel com Python 3.6; use versao 1.x ou cx_Oracle (README §2.3)"
                _log_critical(msg, cfg)
                raise RuntimeError(msg)

            driver = oracledb
            if candidato == "thick":
                lib_dir = os_platform.get_oracle_lib_dir(cfg)
                try:
                    if lib_dir:
                        oracledb.init_oracle_client(lib_dir=lib_dir)
                    else:
                        oracledb.init_oracle_client()
                except Exception as exc:
                    if "already been initialized" not in str(exc):
                        raise

                # Validacao de versao major do Instant Client 19 (README §2.3)
                if hasattr(driver, "clientversion"):
                    c_ver = driver.clientversion()
                    major = c_ver[0] if (isinstance(c_ver, (tuple, list)) and c_ver) else None
                    if major is not None and major != 19:
                        msg = "Falha de configuracao: Oracle Instant Client versao %s invalida. Exigido major 19 (README §2.3)" % (c_ver,)
                        _log_critical(msg, cfg)
                        raise RuntimeError(msg)

        elif candidato == "cx_oracle":
            import cx_Oracle
            driver = cx_Oracle
            lib_dir = os_platform.get_oracle_lib_dir(cfg)
            try:
                if lib_dir:
                    cx_Oracle.init_oracle_client(lib_dir=lib_dir)
                else:
                    cx_Oracle.init_oracle_client()
            except Exception as exc:
                if "already been initialized" not in str(exc):
                    pass

            # Validacao de versao major do Instant Client 19 (README §2.3)
            if hasattr(driver, "clientversion"):
                c_ver = driver.clientversion()
                major = c_ver[0] if (isinstance(c_ver, (tuple, list)) and c_ver) else None
                if major is not None and major != 19:
                    msg = "Falha de configuracao: Oracle Instant Client versao %s invalida. Exigido major 19 (README §2.3)" % (c_ver,)
                    _log_critical(msg, cfg)
                    raise RuntimeError(msg)
        else:
            raise RuntimeError("Candidato de driver desconhecido: %s" % candidato)

        nome_driver = "oracledb" if candidato in ("thin", "thick") else "cx_Oracle"
        logger.info(
            "driver=%s modo=%s servidor=%s cliente=%s",
            nome_driver,
            candidato,
            selecao.server_version or "-",
            selecao.client_version or "-",
            extra={"agent": "-", "ticket": "-", "action": "INICIO"},
        )

        _DRIVER_INITIALIZED = driver
        return driver


def get_selection():
    """Retorna a selecao atual de driver em cache, ou None."""
    with _SELECTION_LOCK:
        return _DRIVER_SELECTION


def reset_selection():
    """Reseta o cache de selecao e driver inicializado (para uso em testes)."""
    global _DRIVER_SELECTION, _DRIVER_INITIALIZED, _BUDGET_WARNING_EMITTED
    with _SELECTION_LOCK:
        _DRIVER_SELECTION = None
        _DRIVER_INITIALIZED = None
        _BUDGET_WARNING_EMITTED = False


# ==============================================================================
# TIPOS NEUTROS, BINDS E SETINPUTSIZES (README §7.5, AGENTS §3.1)
# ==============================================================================

def get_driver_type(tipo_neutro, driver=None, candidato=None):
    """Mapeia uma constante de tipo neutro para o tipo nativo do driver ativo."""
    drv = driver or _DRIVER_INITIALIZED
    cand = candidato or (_DRIVER_SELECTION.candidate if _DRIVER_SELECTION else None)

    if drv is None:
        return tipo_neutro

    if tipo_neutro == TIPO_DATE:
        if cand == "cx_oracle" or (hasattr(drv, "__name__") and drv.__name__ == "cx_Oracle"):
            return getattr(drv, "DATETIME", None)
        return getattr(drv, "DB_TYPE_DATE", None)

    if tipo_neutro == TIPO_CLOB:
        if cand == "cx_oracle" or (hasattr(drv, "__name__") and drv.__name__ == "cx_Oracle"):
            return getattr(drv, "CLOB", None)
        return getattr(drv, "DB_TYPE_CLOB", None)

    if tipo_neutro == TIPO_BLOB:
        if cand == "cx_oracle" or (hasattr(drv, "__name__") and drv.__name__ == "cx_Oracle"):
            return getattr(drv, "BLOB", None)
        return getattr(drv, "DB_TYPE_BLOB", None)

    if tipo_neutro == TIPO_NUMBER:
        if cand == "cx_oracle" or (hasattr(drv, "__name__") and drv.__name__ == "cx_Oracle"):
            return getattr(drv, "NUMBER", None)
        return getattr(drv, "DB_TYPE_NUMBER", None)

    if tipo_neutro == TIPO_VARCHAR:
        if cand == "cx_oracle" or (hasattr(drv, "__name__") and drv.__name__ == "cx_Oracle"):
            return getattr(drv, "STRING", None)
        return getattr(drv, "DB_TYPE_VARCHAR", None)

    return tipo_neutro


def set_input_types(cursor, **mapa):
    """Aplica setinputsizes no cursor convertendo constantes neutras para tipos do driver ativo."""
    drv = _DRIVER_INITIALIZED
    cand = _DRIVER_SELECTION.candidate if _DRIVER_SELECTION else None

    # Se o cursor possui conexao mock ou associada, tenta inferir driver se ainda nulo
    if drv is None and hasattr(cursor, "connection") and hasattr(cursor.connection, "_driver"):
        drv = cursor.connection._driver

    mapa_driver = {}
    for param, tipo_neutro in mapa.items():
        tipo_concreto = get_driver_type(tipo_neutro, driver=drv, candidato=cand)
        mapa_driver[param] = tipo_concreto if tipo_concreto is not None else tipo_neutro

    cursor.setinputsizes(**mapa_driver)


def output_variable(cursor, tipo, tamanho=None):
    """Cria uma variavel de saida OUT bind PL/SQL sem expor cursor.var externamente."""
    drv = _DRIVER_INITIALIZED
    cand = _DRIVER_SELECTION.candidate if _DRIVER_SELECTION else None

    tipo_concreto = get_driver_type(tipo, driver=drv, candidato=cand)
    alvo = tipo_concreto if tipo_concreto is not None else tipo

    if tamanho is not None:
        return cursor.var(alvo, size=tamanho)
    return cursor.var(alvo)


def output_value(variavel):
    """Extrai e normaliza o valor Python de uma variavel de saida PL/SQL."""
    if variavel is None:
        return None
    val = variavel.getvalue()
    if hasattr(val, "read") and callable(val.read):
        return val.read()
    return val


# ==============================================================================
# CLASSIFICACAO E MAPEAMENTO DE ERROS (README §2.3, CR-007 R-12, AGENTS §4.10)
# ==============================================================================

_RE_ORACLE_COD = re.compile(r"\b(ORA|DPY|DPI)-0*(\d+)\b", re.IGNORECASE)

_NETWORK_ERRORS_ORA = {
    3113, 3114, 3135, 12541, 12170, 12514, 12528, 12537,
    1033, 1034, 1089, 28, 1012, 2396, 25408
}
_NETWORK_ERRORS_DPI = {1080}
_NETWORK_ERRORS_DPY = {4011, 6000, 6005}

_TIMEOUT_ERRORS_DPY = {4024}
_TIMEOUT_ERRORS_DPI = {1067}
_TIMEOUT_ERRORS_ORA = {3156}

_LOCK_ERRORS_ORA = {54, 30006, 60}
_VIOLATION_ERRORS_ORA = {1, 2290, 2291, 2292, 1400, 12899, 1438}


def classify_error(exc):
    """Extrai tupla (prefixo, numero) do erro (ORA-, DPY-, DPI-)."""
    if exc is None:
        return None, None

    # Tentativa 1: atributos code ou args do objeto de erro
    code_attr = getattr(exc, "code", None)
    if code_attr is None and hasattr(exc, "args") and exc.args:
        primeiro = exc.args[0]
        code_attr = getattr(primeiro, "code", None)

    if isinstance(code_attr, int) and code_attr > 0:
        return "ORA", code_attr

    # Tentativa 2: regex sobre a representacao em string
    m = _RE_ORACLE_COD.search(str(exc))
    if m:
        return m.group(1).upper(), int(m.group(2))

    return None, None


def is_network_error(exc):
    """Verdadeiro se o erro representa queda de rede, indisponibilidade ou failover."""
    pfx, num = classify_error(exc)
    if pfx == "ORA" and num in _NETWORK_ERRORS_ORA:
        return True
    if pfx == "DPI" and num in _NETWORK_ERRORS_DPI:
        return True
    if pfx == "DPY" and num in _NETWORK_ERRORS_DPY:
        return True
    return False


def is_timeout(exc):
    """Verdadeiro se o erro for call timeout (DPY-4024, DPI-1067, ORA-03156)."""
    pfx, num = classify_error(exc)
    if pfx == "DPY" and num in _TIMEOUT_ERRORS_DPY:
        return True
    if pfx == "DPI" and num in _TIMEOUT_ERRORS_DPI:
        return True
    if pfx == "ORA" and num in _TIMEOUT_ERRORS_ORA:
        return True
    return False


def is_lock(exc):
    """Verdadeiro se o erro for timeout de lock (ORA-00054, ORA-30006) ou deadlock (ORA-00060)."""
    pfx, num = classify_error(exc)
    return pfx == "ORA" and num in _LOCK_ERRORS_ORA


def is_violation(exc):
    """Verdadeiro se o erro for violacao de integridade/unicidade/CK/NOT NULL/tamanho."""
    pfx, num = classify_error(exc)
    return pfx == "ORA" and num in _VIOLATION_ERRORS_ORA


def translate_error(exc):
    """Traduz excecao Oracle para as excecoes da camada de repositorio."""
    try:
        import repo_errors
    except ImportError:
        from modules import repo_errors

    if is_violation(exc):
        return repo_errors.RepoViolation(str(exc))
    if is_lock(exc) or is_timeout(exc):
        return repo_errors.RepoConflict(str(exc))
    if is_network_error(exc):
        return repo_errors.RepoUnavailable(str(exc))
    return repo_errors.RepoError(str(exc))


# ==============================================================================
# ORCAMENTO DA ABERTURA DA CONEXAO (CR-008, R-17)
# ==============================================================================

def connection_budget_s(dsn, call_timeout_s):
    """Calcula CONNECT_TIMEOUT * (RETRY_COUNT + 1) * enderecos a partir do DSN descritor.

    Se ultrapassar call_timeout_s, emite WARN CONEXAO_ACIMA_DO_PRAZO uma vez por processo.
    """
    global _BUDGET_WARNING_EMITTED
    texto = (dsn or "").strip()
    timeout_padrao = int(call_timeout_s) if call_timeout_s else 30

    # Se for descritor TNS (contem '(')
    if "(" in texto:
        enderecos = len(re.findall(r"\(\s*ADDRESS\b", texto, re.IGNORECASE))
        if enderecos < 1:
            enderecos = 1

        m_timeout = re.search(r"CONNECT_TIMEOUT\s*=\s*(\d+)", texto, re.IGNORECASE)
        connect_timeout = int(m_timeout.group(1)) if m_timeout else timeout_padrao

        m_retry = re.search(r"RETRY_COUNT\s*=\s*(\d+)", texto, re.IGNORECASE)
        retry_count = int(m_retry.group(1)) if m_retry else 0

        orcamento = int(connect_timeout * (retry_count + 1) * enderecos)
    else:
        # Easy Connect: conta 1 endereco e usa o call_timeout_s
        orcamento = timeout_padrao

    if orcamento > timeout_padrao and not _BUDGET_WARNING_EMITTED:
        logger.warning(
            "CONEXAO_ACIMA_DO_PRAZO: orcamento da conexao %ds excede call_timeout_s %ds (CR-008, R-17)",
            orcamento, timeout_padrao,
            extra={"agent": "-", "ticket": "-", "action": "ORCAMENTO_CONEXAO"},
        )
        _BUDGET_WARNING_EMITTED = True

    return orcamento


# ==============================================================================
# CONEXAO E POOL (README §2.3, §4.1, CR-007 D1b, CR-008 E3)
# ==============================================================================

def connect(cfg, segredos, papel="web", user=None, password=None):
    """Abre conexao Oracle neutra para o papel especificado (web, agente, purge, monitor)."""
    # 1. Resolver credenciais conforme o papel
    if user is not None and password is not None:
        u = user
        p = password
    elif papel in ("web", "agent"):
        u = getattr(cfg.oracle, "user", None)
        p = _get_password(segredos)
    elif papel == "purge":
        u = getattr(getattr(cfg, "retention", None), "purge_user", None) or getattr(cfg.oracle, "user", None)
        p = getattr(segredos, "purge_password", None) or _get_password(segredos)
    elif papel == "monitor":
        mon = getattr(segredos, "monitor", None)
        u = getattr(mon, "user", None) if mon else getattr(getattr(cfg, "monitor", None), "user", None)
        p = getattr(mon, "password", None) if mon else None
    elif papel == "dono":
        u = user or getattr(cfg.oracle, "owner", None)
        p = password or _get_password(segredos)
    else:
        raise ValueError("Papel de conexao desconhecido: %s" % papel)

    dsn = getattr(cfg.oracle, "dsn", "") if hasattr(cfg, "oracle") else getattr(cfg, "dsn", "")
    timeout_ms = getattr(cfg.oracle, "call_timeout_ms", 30000) if hasattr(cfg, "oracle") else 30000
    try:
        timeout_s = float(timeout_ms) / 1000.0
    except (TypeError, ValueError):
        timeout_s = 30.0
        timeout_ms = 30000

    # Valida orcamento da conexao (CR-008, R-17)
    connection_budget_s(dsn, timeout_s)

    selecao = get_selection()
    if selecao is None:
        selecao = select_driver(cfg, segredos, usuario=u, senha=p)
    driver = initialize(selecao, cfg)

    candidato = selecao.candidate
    if candidato == "thin":
        conn = driver.connect(user=u, password=p, dsn=dsn, tcp_connect_timeout=timeout_s)
    else:
        conn = driver.connect(user=u, password=p, dsn=dsn)

    return configure_session(conn, cfg, papel, user=u)


def configure_session(conn, cfg, papel="web", user=None):
    """Configuracao obrigatoria de toda conexao (README §2.3), nova ou tirada do pool.

    autocommit desligado, call_timeout do config e module/action/client_identifier da sessao.
    """
    timeout_ms = getattr(cfg.oracle, "call_timeout_ms", 30000) if hasattr(cfg, "oracle") else 30000
    try:
        timeout_ms = int(timeout_ms)
    except (TypeError, ValueError):
        timeout_ms = 30000
    conn.autocommit = False
    if hasattr(conn, "call_timeout"):
        conn.call_timeout = timeout_ms

    conn.module = "SSS_%s" % papel.upper()
    conn.action = "INICIO"

    u = user or (getattr(cfg.oracle, "user", None) if hasattr(cfg, "oracle") else None)
    agent_id = getattr(getattr(cfg, "agent", None), "agent_id", None) or getattr(cfg, "agent_id", None)
    conn.client_identifier = str(agent_id or u or "-")
    return conn


def pool(cfg, segredos, papel="web"):
    """Cria pool de conexoes Oracle para o no web com ping_interval de 60s (CR-007, R-12)."""
    u = getattr(cfg.oracle, "user", None)
    p = _get_password(segredos)
    dsn = getattr(cfg.oracle, "dsn", "") if hasattr(cfg, "oracle") else getattr(cfg, "dsn", "")
    timeout_ms = getattr(cfg.oracle, "call_timeout_ms", 30000) if hasattr(cfg, "oracle") else 30000
    timeout_s = float(timeout_ms) / 1000.0
    p_min = int(getattr(cfg.oracle, "pool_min", 1))
    p_max = int(getattr(cfg.oracle, "pool_max", 4))

    connection_budget_s(dsn, timeout_s)

    selecao = get_selection()
    if selecao is None:
        selecao = select_driver(cfg, segredos)
    driver = initialize(selecao, cfg)

    candidato = selecao.candidate
    if candidato in ("thin", "thick"):
        return driver.create_pool(
            user=u, password=p, dsn=dsn,
            min=p_min, max=p_max, increment=1,
            ping_interval=60, tcp_connect_timeout=timeout_s,
        )
    return driver.SessionPool(
        user=u, password=p, dsn=dsn,
        min=p_min, max=p_max, increment=1,
        ping_interval=60,
    )


# ==============================================================================
# GERENCIADOR DE TRANSACAO (AGENTS §4.9, §4.10)
# ==============================================================================

@contextlib.contextmanager
def transaction(conn):
    """Context manager que faz COMMIT no sucesso e ROLLBACK em qualquer excecao.

    Classifica e registra timeout de lock, deadlock e call timeout como WARN,
    sem stack trace; demais erros sao registrados como ERROR com stack trace.
    A excecao original e sempre propagada.
    """
    try:
        yield conn
        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass

        if is_lock(exc) or is_timeout(exc):
            pfx, num = classify_error(exc)
            cod_str = "%s-%s" % (pfx or "ERR", num or 0)
            logger.warning(
                "Falha de concorrencia/lock/timeout na transacao Oracle: %s (codigo=%s)",
                exc, cod_str,
                extra={"agent": "-", "ticket": "-", "action": "TRANSACAO"},
            )
        else:
            logger.error(
                "Erro na transacao Oracle: %s", exc, exc_info=True,
                extra={"agent": "-", "ticket": "-", "action": "TRANSACAO"},
            )
        raise


# ==============================================================================
# RECURSOS AUXILIARES: RELOGIO, IDS E SAUDE
# ==============================================================================

def db_now(conn):
    """Retorna SYSDATE naive do banco truncado sem microssegundos (README §4.2, §7.1)."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT SYSDATE FROM DUAL")
        row = cur.fetchone()
        dt = row[0]
        return dt.replace(microsecond=0)
    finally:
        cur.close()


def health(conn):
    """Executa SELECT SYSDATE FROM DUAL para checagem de saude (README §2.3)."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT SYSDATE FROM DUAL")
        row = cur.fetchone()
        return row[0]
    finally:
        cur.close()


def next_id(conn, sequence_qualificada):
    """Obtem o proximo id sequencial (SELECT {seq}.NEXTVAL FROM DUAL, README §2.7)."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT %s.NEXTVAL FROM DUAL" % sequence_qualificada)
        row = cur.fetchone()
        return int(row[0])
    finally:
        cur.close()


def check_schema_version(conn, owner=None, prefixo="tbsss_"):
    """Confere se versao_esquema em tbsss_control e igual a VERSAO_ESQUEMA (CR-007, D4)."""
    if owner:
        tabela = sql_ident.qualify(owner, prefixo + sql_ident.physical("control"))
    else:
        tabela = prefixo + sql_ident.physical("control")

    cur = conn.cursor()
    try:
        cur.execute("SELECT schema_version FROM %s WHERE id = 1" % tabela)
        row = cur.fetchone()
        if not row:
            msg = "Versao do esquema ausente na tabela de controle (id=1)"
            _log_critical(msg)
            raise SchemaVersionError(msg)

        v = int(row[0])
        if v != sql_ident.SCHEMA_VERSION:
            msg = "Versao do esquema incompativel: esperada %d, encontrada %d" % (sql_ident.SCHEMA_VERSION, v)
            _log_critical(msg)
            raise SchemaVersionError(msg)
        return v
    finally:
        cur.close()


# ==============================================================================
# RECONEXAO RESILIENTE PARA O DAEMON (CR-007, R-04, AGENTS §6)
# ==============================================================================

class ResilientConnection(object):
    """Gerencia conexao persistente com reconexao monotonica sem sleep (CR-007, R-04)."""

    def __init__(self, cfg, segredos, papel="agent"):
        self.cfg = cfg
        self.secrets = segredos
        self.role = papel
        self.conn = None
        self.backoff_s = 1.0
        self.next_attempt_monotonic = 0.0
        self.failing = False
        self._connected_once = False  # a primeira conexao nao e reconexao (F9.1d)

    def get_connection(self):
        """Retorna a conexao ativa ou None."""
        return self.conn

    def close(self):
        """Fecha e descarta a conexao atual."""
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
        self.failing = True

    def notify_error(self, exc):
        """Em erro de rede, descarta a conexao e calcula o proximo prazo do backoff."""
        if is_network_error(exc):
            self.close()
            self.next_attempt_monotonic = time.monotonic() + self.backoff_s
            self.backoff_s = min(60.0, self.backoff_s * 2.0)

    def ensure(self):
        """Tenta reconectar se desconectado e prazo vencido, no maximo UMA vez, SEM SLEEP."""
        if self.conn is not None:
            return True

        agora = time.monotonic()
        if agora < self.next_attempt_monotonic:
            return False

        primeira = not self._connected_once
        if primeira:
            logger.info("Conectando ao Oracle (papel=%s)...", self.role,
                        extra={"agent": "-", "ticket": "-", "action": "CONEXAO"})
        else:
            logger.warning(
                "Tentando reconexao com o Oracle (papel=%s)...", self.role,
                extra={"agent": "-", "ticket": "-", "action": "RECONEXAO"},
            )
        try:
            self.conn = connect(self.cfg, self.secrets, papel=self.role)
            self.backoff_s = 1.0
            self.failing = False
            self._connected_once = True
            logger.info(
                "Conexao estabelecida (papel=%s)" if primeira else "Reconexao bem-sucedida (papel=%s)", self.role,
                extra={"agent": "-", "ticket": "-", "action": "CONEXAO" if primeira else "RECONEXAO"},
            )
            return True
        except Exception as exc:
            logger.warning(
                "Falha na tentativa de %s: %s", "conexao" if primeira else "reconexao", exc,
                extra={"agent": "-", "ticket": "-", "action": "CONEXAO" if primeira else "RECONEXAO"},
            )
            self.next_attempt_monotonic = time.monotonic() + self.backoff_s
            self.backoff_s = min(60.0, self.backoff_s * 2.0)
            return False
