# -*- coding: utf-8 -*-
"""Fabrica de repositorios de persistencia (README §2.5, AGENTS §5.5).

A aplicacao usa sempre o Oracle do [oracle] do config.ini (owner e table_prefix). O FAKE so existe
quando um teste o injeta explicitamente por configurar({"app": {"data_backend": "FAKE", ...}}), e so
onde a pasta dev/ existe (o repositorio; CR-032, D11). Garante singletons por processo.
"""
from typing import Any
import logging
import os
import threading

from sss.config import app_context
from sss.core import masking
from sss.core import security

# O repo_fake nao vai no pacote de implantacao (README §12.2): e importado so no ramo FAKE, que so um teste
# liga (F9.1d), e so onde existe a pasta dev/ da raiz (src/sss/persistence/ -> raiz).
_APP_DEV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "dev")

_factory_lock = threading.RLock()
_singletons = {}
_singletons_oracle = {}
_fake_store = None
_config_override = None

ENV_DEV_PASSWORD = "SSS_DEV_SEED_PASSWORD"


def configure(cfg):
    """Permite injetar uma configuracao explicita (usado em testes ou bootstrap)."""
    global _config_override
    with _factory_lock:
        _config_override = cfg


def reset_singletons():
    """Reseta instancias singleton e estado de seed (usado em testes)."""
    global _fake_store
    with _factory_lock:
        _singletons.clear()
        _singletons_oracle.clear()
        _fake_store = None


def _resolve_config(config_param=None):
    """Resolve o backend do parametro, do override ou do app_context.

    O config.ini nao tem mais data_backend: sem a chave, o backend e ORACLE. So o dict de teste
    passado a configurar() pode pedir FAKE. Sem configuracao, falha.
    """
    cfg = config_param
    if cfg is None:
        cfg = _config_override
    if cfg is None:
        cfg = app_context.get_config()
    if cfg is None:
        raise RuntimeError("Configuracao ausente: informe config ou carregue models/00_config.py (app_context)")

    app = cfg["app"]
    backend = app.get("data_backend", "ORACLE") if isinstance(app, dict) else "ORACLE"
    return str(backend).upper()


def _dev_seed_password():
    """Senha DEV do seed FAKE, lida do ambiente; ausente ou fora da politica deixa os logins impossiveis."""
    log = logging.getLogger("sss_web")
    password = os.environ.get(ENV_DEV_PASSWORD)
    if not password:
        log.warning("%s ausente: usuarios do seed FAKE sem senha utilizavel (logins DEV impossiveis)",
                    ENV_DEV_PASSWORD, extra={"action": "SEED"})
        return None
    masking.register_secret(password)
    if security.validate_password_policy(password):
        log.warning("%s fora da politica de senha: usuarios do seed FAKE sem senha utilizavel",
                    ENV_DEV_PASSWORD, extra={"action": "SEED"})
        return None
    return password


def _oracle_class(normalized_name):
    """Classe Oracle do agregado (import tardio: o driver so e carregado quando usado)."""
    if normalized_name == "catalog":
        from sss.persistence.oracle.catalog import RepoCatalogOracle
        return RepoCatalogOracle
    if normalized_name == "tickets":
        from sss.persistence.oracle.tickets import RepoTicketsOracle
        return RepoTicketsOracle
    if normalized_name == "schedules":
        from sss.persistence.oracle.schedules import RepoSchedulesOracle
        return RepoSchedulesOracle
    if normalized_name == "audit":
        from sss.persistence.oracle.audit import RepoAuditOracle
        return RepoAuditOracle
    if normalized_name == "agents":
        from sss.persistence.oracle.agents import RepoAgentsOracle
        return RepoAgentsOracle
    if normalized_name == "inputs":
        from sss.persistence.oracle.inputs import RepoInputsOracle
        return RepoInputsOracle
    return None


def get(name: str, config: Any = None) -> Any:
    """Retorna a instancia singleton do repositorio solicitado.

    Lanca RuntimeError se o FAKE (so de teste) for pedido onde nao ha a pasta dev/ e ValueError para
    um repositorio desconhecido.
    """
    global _fake_store

    backend = _resolve_config(config)

    # Trava estrita (README §2.5 e AGENTS §5.5; CR-032, D11): o FAKE so existe onde ha a pasta dev/.
    if backend == "FAKE" and not os.path.isdir(_APP_DEV_DIR):
        raise RuntimeError("FAKE (so de teste) e proibido fora do repositorio (sem a pasta dev/)")

    name_norm = str(name).lower().replace("repo_", "")

    if backend == "ORACLE":
        with _factory_lock:
            if name_norm in ("users", "rbac") and name_norm not in _singletons_oracle:
                # RBAC_USUARIOS: os dois repositorios compartilham o agregado.
                from sss.persistence.oracle.users import RepoUsersOracle
                from sss.persistence.oracle.rbac import RepoRbacOracle
                _singletons_oracle["users"] = RepoUsersOracle()
                _singletons_oracle["rbac"] = RepoRbacOracle()
            elif name_norm not in _singletons_oracle:
                cls_name = _oracle_class(name_norm)
                if cls_name is None:
                    raise ValueError("Repositorio desconhecido: %s" % name)
                _singletons_oracle[name_norm] = cls_name()
            return _singletons_oracle[name_norm]

    if backend != "FAKE":
        raise ValueError("Backend de persistencia desconhecido: %s" % backend)

    with _factory_lock:
        if _fake_store is None:
            from sss.persistence.fake.schedules import RepoSchedulesFake
            from sss.persistence.fake.agents import RepoAgentsFake
            from sss.persistence.fake.audit import RepoAuditFake
            from sss.persistence.fake.catalog import RepoCatalogFake
            from sss.persistence.fake.inputs import RepoInputsFake
            from sss.persistence.fake.rbac import RepoRbacFake
            from sss.persistence.fake.seed import load_seed
            from sss.persistence.fake.store import FakeDataStore
            from sss.persistence.fake.tickets import RepoTicketsFake
            from sss.persistence.fake.users import RepoUsersFake
            _fake_store = FakeDataStore()
            load_seed(_fake_store, dev_password=_dev_seed_password())

            _singletons["users"] = RepoUsersFake(_fake_store)
            _singletons["rbac"] = RepoRbacFake(_fake_store)
            _singletons["catalog"] = RepoCatalogFake(_fake_store)
            _singletons["tickets"] = RepoTicketsFake(_fake_store)
            _singletons["schedules"] = RepoSchedulesFake(_fake_store)
            _singletons["audit"] = RepoAuditFake(_fake_store)
            _singletons["agents"] = RepoAgentsFake(_fake_store)
            _singletons["inputs"] = RepoInputsFake(_fake_store)

        if name_norm not in _singletons:
            raise ValueError("Repositorio desconhecido: %s" % name)

        return _singletons[name_norm]
