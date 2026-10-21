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

_lock_fabrica = threading.RLock()
_singletons = {}
_singletons_oracle = {}
_fake_store = None
_config_override = None

ENV_SENHA_DEV = "SSS_DEV_SEED_PASSWORD"


def configurar(cfg):
    """Permite injetar uma configuracao explicita (usado em testes ou bootstrap)."""
    global _config_override
    with _lock_fabrica:
        _config_override = cfg


def reset_singletons():
    """Reseta instancias singleton e estado de seed (usado em testes)."""
    global _fake_store
    with _lock_fabrica:
        _singletons.clear()
        _singletons_oracle.clear()
        _fake_store = None


def _resolver_config(config_param=None):
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


def _senha_dev_seed():
    """Senha DEV do seed FAKE, lida do ambiente; ausente ou fora da politica deixa os logins impossiveis."""
    log = logging.getLogger("sss_web")
    senha = os.environ.get(ENV_SENHA_DEV)
    if not senha:
        log.warning("%s ausente: usuarios do seed FAKE sem senha utilizavel (logins DEV impossiveis)",
                    ENV_SENHA_DEV, extra={"action": "SEED"})
        return None
    masking.registrar_segredo(senha)
    if security.validar_politica_senha(senha):
        log.warning("%s fora da politica de senha: usuarios do seed FAKE sem senha utilizavel",
                    ENV_SENHA_DEV, extra={"action": "SEED"})
        return None
    return senha


def _classe_oracle(nome_norm):
    """Classe Oracle do agregado (import tardio: o driver so e carregado quando usado)."""
    if nome_norm == "catalogo":
        from repo_oracle.catalog import RepoCatalogoOracle
        return RepoCatalogoOracle
    if nome_norm == "tickets":
        from repo_oracle.tickets import RepoTicketsOracle
        return RepoTicketsOracle
    if nome_norm == "agendamentos":
        from repo_oracle.schedules import RepoAgendamentosOracle
        return RepoAgendamentosOracle
    if nome_norm == "auditoria":
        from repo_oracle.audit import RepoAuditoriaOracle
        return RepoAuditoriaOracle
    if nome_norm == "agentes":
        from repo_oracle.agents import RepoAgentesOracle
        return RepoAgentesOracle
    return None


def obter(nome, config=None):
    """Retorna a instancia singleton do repositorio solicitado.

    Lanca RuntimeError se o FAKE (so de teste) for pedido fora de sss_env=DEV e ValueError para
    um repositorio desconhecido.
    """
    global _fake_store

    backend, env = _resolver_config(config)

    # Trava de ambiente estrita (README §2.5 e AGENTS §5.5)
    if backend == "FAKE" and env != "DEV":
        raise RuntimeError("FAKE (so de teste) e proibido fora de DEV (sss_env=%s)" % env)

    nome_norm = str(nome).lower().replace("repo_", "")

    if backend == "ORACLE":
        with _lock_fabrica:
            if nome_norm in ("usuarios", "rbac") and nome_norm not in _singletons_oracle:
                # RBAC_USUARIOS: os dois repositorios compartilham o agregado.
                from repo_oracle.users import RepoUsuariosOracle
                from repo_oracle.rbac import RepoRbacOracle
                _singletons_oracle["usuarios"] = RepoUsuariosOracle()
                _singletons_oracle["rbac"] = RepoRbacOracle()
            elif nome_norm not in _singletons_oracle:
                classe = _classe_oracle(nome_norm)
                if classe is None:
                    raise ValueError("Repositorio desconhecido: %s" % nome)
                _singletons_oracle[nome_norm] = classe()
            return _singletons_oracle[nome_norm]

    if backend != "FAKE":
        raise ValueError("Backend de persistencia desconhecido: %s" % backend)

    with _lock_fabrica:
        if _fake_store is None:
            from repo_fake.schedules import RepoAgendamentosFake
            from repo_fake.agents import RepoAgentesFake
            from repo_fake.audit import RepoAuditoriaFake
            from repo_fake.catalog import RepoCatalogoFake
            from repo_fake.rbac import RepoRbacFake
            from repo_fake.seed import carregar_seed
            from repo_fake.store import FakeDataStore
            from repo_fake.tickets import RepoTicketsFake
            from repo_fake.users import RepoUsuariosFake
            _fake_store = FakeDataStore()
            carregar_seed(_fake_store, senha_dev=_senha_dev_seed())

            _singletons["usuarios"] = RepoUsuariosFake(_fake_store)
            _singletons["rbac"] = RepoRbacFake(_fake_store)
            _singletons["catalogo"] = RepoCatalogoFake(_fake_store)
            _singletons["tickets"] = RepoTicketsFake(_fake_store)
            _singletons["agendamentos"] = RepoAgendamentosFake(_fake_store)
            _singletons["auditoria"] = RepoAuditoriaFake(_fake_store)
            _singletons["agentes"] = RepoAgentesFake(_fake_store)

        if nome_norm not in _singletons:
            raise ValueError("Repositorio desconhecido: %s" % nome)

        return _singletons[nome_norm]
