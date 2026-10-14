# -*- coding: utf-8 -*-
"""Fabrica de repositorios de persistencia (README §2.5, AGENTS §5.5).

Seleciona e instancia os repositorios FAKE ou ORACLE conforme configuracao.
Garante singletons por processo e aplica a trava de ambiente para o backend FAKE.
"""
import os
import threading


from repo_fake.agendamentos import RepoAgendamentosFake
from repo_fake.agentes import RepoAgentesFake
from repo_fake.auditoria import RepoAuditoriaFake
from repo_fake.catalogo import RepoCatalogoFake
from repo_fake.rbac import RepoRbacFake
from repo_fake.seed import carregar_seed
from repo_fake.store import FakeDataStore
from repo_fake.tickets import RepoTicketsFake
from repo_fake.usuarios import RepoUsuariosFake

_lock_fabrica = threading.RLock()
_singletons = {}
_fake_store = None
_config_override = None


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
        _fake_store = None


def _resolver_config(config_param=None):
    """Resolve tupla (data_backend, sss_env) a partir dos parametros, override ou current."""
    cfg = config_param
    if cfg is None:
        cfg = _config_override
    if cfg is None:
        try:
            from gluon import current
            cfg = getattr(current, "sss_cfg", None) or getattr(current, "sss_config", None)
        except ImportError:
            pass

    backend = None
    env = None

    if cfg is not None:
        if hasattr(cfg, "__getitem__"):
            try:
                backend = cfg["app"]["data_backend"]
            except (KeyError, TypeError):
                pass
            try:
                env = cfg["app"]["sss_env"]
            except (KeyError, TypeError):
                pass

    if not backend:
        backend = os.environ.get("SSS_DATA_BACKEND", "FAKE")
    if not env:
        env = os.environ.get("SSS_ENV", "DEV")

    return str(backend).upper(), str(env).upper()


def obter(nome, config=None):
    """Retorna a instancia singleton do repositorio solicitado.

    Lanca RuntimeError se backend FAKE for utilizado fora de sss_env=DEV.
    Lanca NotImplementedError se backend ORACLE for solicitado antes da sua implementacao.
    """
    global _fake_store

    backend, env = _resolver_config(config)

    # Trava de ambiente estrita (README §2.5 e AGENTS §5.5)
    if backend == "FAKE" and env != "DEV":
        raise RuntimeError("data_backend FAKE e proibido fora de DEV (sss_env=%s)" % env)

    if backend == "ORACLE":
        raise NotImplementedError("Backend ORACLE ainda nao implementado")

    if backend != "FAKE":
        raise ValueError("Backend de persistencia desconhecido: %s" % backend)

    nome_norm = str(nome).lower().replace("repo_", "")

    with _lock_fabrica:
        if _fake_store is None:
            _fake_store = FakeDataStore()
            carregar_seed(_fake_store)

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
