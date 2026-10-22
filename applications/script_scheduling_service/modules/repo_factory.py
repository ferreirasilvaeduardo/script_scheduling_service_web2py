# -*- coding: utf-8 -*-
"""Fabrica de repositorios de persistencia (README §2.5, AGENTS §5.5).

A aplicacao usa sempre o Oracle do [oracle] do config.ini (owner e table_prefix). O FAKE so existe
quando um teste o injeta explicitamente por configurar({"app": {"data_backend": "FAKE", ...}}), e so
com sss_env = DEV. Garante singletons por processo.
"""
import logging
import os
import threading

from gluon import current

import masking
import security

# O repo_fake nao vai no pacote de implantacao (README §12.2): e importado so no ramo FAKE, que so um teste
# em DEV liga (F9.1d).

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
    """Resolve (backend, sss_env) do parametro, do override ou de current.sss_cfg.

    O config.ini nao tem mais data_backend: sem a chave, o backend e ORACLE. So o dict de teste
    passado a configurar() pode pedir FAKE. Sem configuracao, ou sem [app] sss_env, falha.
    """
    cfg = config_param
    if cfg is None:
        cfg = _config_override
    if cfg is None:
        cfg = getattr(current, "sss_cfg", None)
    if cfg is None:
        raise RuntimeError("Configuracao ausente: informe config ou carregue models/00_config.py (current.sss_cfg)")

    app = cfg["app"]
    backend = app.get("data_backend", "ORACLE") if isinstance(app, dict) else "ORACLE"
    return str(backend).upper(), str(app["sss_env"]).upper()


def _dev_seed_password():
    """Senha DEV do seed FAKE, lida do ambiente; ausente ou fora da politica deixa os logins impossiveis."""
    log = logging.getLogger("sss_web")
    senha = os.environ.get(ENV_DEV_PASSWORD)
    if not senha:
        log.warning("%s ausente: usuarios do seed FAKE sem senha utilizavel (logins DEV impossiveis)",
                    ENV_DEV_PASSWORD, extra={"action": "SEED"})
        return None
    masking.register_secret(senha)
    if security.validate_password_policy(senha):
        log.warning("%s fora da politica de senha: usuarios do seed FAKE sem senha utilizavel",
                    ENV_DEV_PASSWORD, extra={"action": "SEED"})
        return None
    return senha


def _oracle_class(normalized_name):
    """Classe Oracle do agregado (import tardio: o driver so e carregado quando usado)."""
    if normalized_name == "catalog":
        from repo_oracle.catalog import RepoCatalogOracle
        return RepoCatalogOracle
    if normalized_name == "tickets":
        from repo_oracle.tickets import RepoTicketsOracle
        return RepoTicketsOracle
    if normalized_name == "schedules":
        from repo_oracle.schedules import RepoSchedulesOracle
        return RepoSchedulesOracle
    if normalized_name == "audit":
        from repo_oracle.audit import RepoAuditOracle
        return RepoAuditOracle
    if normalized_name == "agents":
        from repo_oracle.agents import RepoAgentsOracle
        return RepoAgentsOracle
    return None


def get(name, config=None):
    """Retorna a instancia singleton do repositorio solicitado.

    Lanca RuntimeError se o FAKE (so de teste) for pedido fora de sss_env=DEV e ValueError para
    um repositorio desconhecido.
    """
    global _fake_store

    backend, env = _resolve_config(config)

    # Trava de ambiente estrita (README §2.5 e AGENTS §5.5)
    if backend == "FAKE" and env != "DEV":
        raise RuntimeError("FAKE (so de teste) e proibido fora de DEV (sss_env=%s)" % env)

    nome_norm = str(name).lower().replace("repo_", "")

    if backend == "ORACLE":
        with _factory_lock:
            if nome_norm in ("users", "rbac") and nome_norm not in _singletons_oracle:
                # RBAC_USUARIOS: os dois repositorios compartilham o agregado.
                from repo_oracle.users import RepoUsersOracle
                from repo_oracle.rbac import RepoRbacOracle
                _singletons_oracle["users"] = RepoUsersOracle()
                _singletons_oracle["rbac"] = RepoRbacOracle()
            elif nome_norm not in _singletons_oracle:
                classe = _oracle_class(nome_norm)
                if classe is None:
                    raise ValueError("Repositorio desconhecido: %s" % name)
                _singletons_oracle[nome_norm] = classe()
            return _singletons_oracle[nome_norm]

    if backend != "FAKE":
        raise ValueError("Backend de persistencia desconhecido: %s" % backend)

    with _factory_lock:
        if _fake_store is None:
            from repo_fake.schedules import RepoSchedulesFake
            from repo_fake.agents import RepoAgentsFake
            from repo_fake.audit import RepoAuditFake
            from repo_fake.catalog import RepoCatalogFake
            from repo_fake.rbac import RepoRbacFake
            from repo_fake.seed import load_seed
            from repo_fake.store import FakeDataStore
            from repo_fake.tickets import RepoTicketsFake
            from repo_fake.users import RepoUsersFake
            _fake_store = FakeDataStore()
            load_seed(_fake_store, dev_password=_dev_seed_password())

            _singletons["users"] = RepoUsersFake(_fake_store)
            _singletons["rbac"] = RepoRbacFake(_fake_store)
            _singletons["catalog"] = RepoCatalogFake(_fake_store)
            _singletons["tickets"] = RepoTicketsFake(_fake_store)
            _singletons["schedules"] = RepoSchedulesFake(_fake_store)
            _singletons["audit"] = RepoAuditFake(_fake_store)
            _singletons["agents"] = RepoAgentsFake(_fake_store)

        if nome_norm not in _singletons:
            raise ValueError("Repositorio desconhecido: %s" % name)

        return _singletons[nome_norm]
