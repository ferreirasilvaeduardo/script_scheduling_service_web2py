# -*- coding: utf-8 -*-
"""Montagem do servidor web (CR-021e): configuracao, controllers, views e o Application.

Era o models/00_config.py mais o despacho do web2py. Os controllers ficam num registro de imports
explicitos (o projeto proibe import dinamico); o ``dev`` so entra com ``sss_env = DEV`` e se o
arquivo existir, porque nao vai no pacote (um DEV instalado pelo pacote roda sem ele, como no
web2py). Action e toda funcao definida no proprio modulo do controller, sem '_' no inicio e sem
parametro obrigatorio (como no web2py): nomes importados, como ``redirect``, nunca viram rota.
"""
import inspect
import os
from types import ModuleType
from typing import Any, Callable, Dict, Mapping, Optional

from sss.config import app_context
from sss.core import masking
from sss.config import sss_config
from sss.web.framework import Application, Context, Route, SessionCodec, Settings, Templates

from . import context, errors, security
from .context import APPLICATION, URL

# src/sss/web/ (CR-022b7): templates, estaticos e controllers ficam no pacote da camada web.
WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWS_DIR = os.path.join(WEB_DIR, "templates")
STATIC_DIR = os.path.join(WEB_DIR, "static")
DEV_CONTROLLER = os.path.join(WEB_DIR, "controllers", "dev.py")
_TEMPLATES = Templates(VIEWS_DIR)


def load_config(path: Optional[str] = None) -> Any:
    """Configuracao do papel web, gravada no app_context; aborta sem UTF-8 (README §12.2)."""
    cfg = sss_config.get_config("sss_web", path)
    app_context.set_config(cfg)
    # Sem UTF-8 no sistema de arquivos, nomes e valores com acento quebram (CR-007 R-17).
    sss_config.check_encoding("sss_web", cfg.logging.log_dir)
    masking.install_filter_on_handlers()
    return cfg


def controllers(cfg: Any) -> Dict[str, ModuleType]:
    """Registro dos controllers, por import explicito."""
    # pylint: disable=import-outside-toplevel
    from sss.web.controllers import (admin_environments, admin_parameters, admin_profiles,
                                     admin_scripts, admin_users, audit, default, inputs, logs,
                                     outputs, schedules, tickets)
    registry = {module.__name__.rsplit(".", 1)[1]: module for module in (
        admin_environments, admin_parameters, admin_profiles, admin_scripts, admin_users, audit,
        default, inputs, logs, outputs, schedules, tickets)}
    if cfg.app.sss_env == "DEV" and os.path.isfile(DEV_CONTROLLER):
        # Fora do pacote de implantacao (README §12.2): so em DEV e so se estiver presente (achado
        # no ensaio do pacote do CR-021f3: sem o arquivo, o servidor nao subia).
        from sss.web.controllers import dev
        registry["dev"] = dev
    return registry


def _without_required_parameters(function: Callable[..., Any]) -> bool:
    return all(p.default is not p.empty or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
               for p in inspect.signature(function).parameters.values())


def actions(module: ModuleType) -> Dict[str, Callable[[], Any]]:
    """Actions de um controller: funcoes do proprio modulo, publicas, sem parametro obrigatorio."""
    return {name: value for name, value in vars(module).items()
            if inspect.isfunction(value) and value.__module__ == module.__name__
            and not name.startswith("_") and _without_required_parameters(value)}


def make_resolver(registry: Mapping[str, ModuleType]
                  ) -> Callable[[Route], Optional[Callable[[Context], Any]]]:
    """Resolvedor do Application: rota -> action chamada sem argumentos (D3)."""
    table = {name: actions(module) for name, module in registry.items()}

    def resolve(route: Route) -> Optional[Callable[[Context], Any]]:
        function = table.get(route.controller, {}).get(route.function)
        if function is None:
            return None
        return lambda ctx: function()
    return resolve


def view_namespace(ctx: Context) -> Dict[str, Any]:
    """Nomes que toda view enxerga, alem das variaveis devolvidas pela action."""
    return {"request": ctx.request, "response": ctx.response, "session": ctx.session, "URL": URL,
            "csrf_field": security.csrf_field, "sss_ctx": context.user()}


def render_view(ctx: Context, name: str, data: Mapping[str, Any]) -> str:
    """HTML da view ``name`` com as variaveis da action."""
    namespace = view_namespace(ctx)
    namespace.update(data)
    return _TEMPLATES.render(name, namespace)


def render(ctx: Context, data: Mapping[str, Any]) -> str:
    """View da action: ``response.view`` ou ``<controller>/<funcao>.<extensao>``, como no web2py.

    O ``response.view`` permite a action escolher outra view (ex.: o formulario de inclusao).
    """
    route = ctx.route
    name = ctx.response.view or f"{route.controller}/{route.function}.{route.extension}"
    return render_view(ctx, name, data)


def make_app(cfg: Any) -> Application:
    """O Application do SSS: sessao assinada, hooks de seguranca, views e pagina de erro."""
    secrets = sss_config.get_secrets("sss_web")
    settings = Settings(APPLICATION, STATIC_DIR, security.max_body_bytes(),
                        SessionCodec(secrets.cookie_key), security.secure_cookie)
    return Application(settings, make_resolver(controllers(cfg)), security.log(),
                       before=[security.before_request], after=[security.after_request],
                       renderer=render, error_page=errors.make_error_page(render_view))
