# -*- coding: utf-8 -*-
"""Cadastro de perfis e matriz de permissoes (README §4.3, MANAGE_PROFILES). Padrao em docs/ADMIN_CRUD_PATTERN.md.

Regras ficam em modules/admin_profiles_service.py; CSRF e Origin de todo POST sao validados
em models/10_security.py. Nenhuma permissao e decidida no cliente: o POST da matriz e revalidado inteiro.
"""
import admin_crud
import admin_profiles_service as servico
import ui_helpers
from admin_crud import AccessDenied, OperationDenied
from repo_errors import RepoConflict, RepoError, RepoNotFound

_FUNC = "MANAGE_PROFILES"
_TAMANHOS = (20, 50, 100)
_MAX_IDS = 5000
_MSG_FALHA_LISTA = u"Não foi possível carregar os perfis. Tente novamente em instantes."
_MSG_FALHA_ALTERNAR = u"Não foi possível alterar a situação do perfil. Tente novamente em instantes."
_MSG_FALHA_MATRIZ = u"Não foi possível salvar a matriz. Tente novamente em instantes."
_JS_MATRIZ = "js/app/matriz.js"


def _exigir_metodo(*permitidos):
    if (request.env.request_method or "GET").upper() not in permitidos:
        raise HTTP(405, **response.headers)


def _negado():
    raise HTTP(403, u"Acesso negado.", **response.headers)


def _nao_encontrado():
    raise HTTP(404, u"Perfil não encontrado.", **response.headers)


def _texto(valor, limite):
    valor = valor[-1] if isinstance(valor, list) and valor else valor
    return valor[:limite] if isinstance(valor, str) else None


def _lista(nome):
    valor = request.post_vars.get(nome)
    if valor is None:
        return []
    valor = valor if isinstance(valor, list) else [valor]
    return [v[:11] if isinstance(v, str) else v for v in valor[:_MAX_IDS]]


def _pagina_form(ctx, dados, erros=None):
    response.title = (u"Perfil %s — SSS" % dados["name"]) if dados.get("id") else u"Novo perfil — SSS"
    response.view = "admin_perfis/form.html"
    erros = erros or {}
    campos = [{"name": n, "erro": erros.get(n)} for n in ("name", "description")]
    return dict(perfil=dados, erros=erros, erro_geral=erros.get(admin_crud.GENERAL_FIELD),
                foco_campo=ui_helpers.primeiro_campo_invalido(campos),
                aviso_desativacao=servico.DEACTIVATION_WARNING)


def lista():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    filtros = servico.normalize_filters(request.get_vars)
    pagina = ui_helpers.sanitizar_pagina(_texto(request.get_vars.get("pagina"), 9))
    tamanho = ui_helpers.sanitizar_tamanho(_texto(request.get_vars.get("tamanho"), 3), _TAMANHOS)
    erro = None
    try:
        resultado = servico.list_page(ctx, filtros, pagina, tamanho)
    except AccessDenied:
        _negado()
    except RepoError:
        _log.exception("falha ao listar perfis (login=%s)", ctx["login"], extra={"action": _FUNC})
        resultado = {"itens": [], "total": 0, "pagina": 1, "tamanho": tamanho}
        erro = _MSG_FALHA_LISTA
    response.title = u"Perfis — SSS"
    return dict(resultado=resultado, erro=erro, filtros_ativos=filtros, tamanho=tamanho,
                query_params=dict(filtros, tamanho=tamanho))


def form():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    try:
        dados = servico.form(ctx, _texto(request.args(0), 11))
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    return _pagina_form(ctx, dados)


def salvar():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    perfil_id = _texto(request.post_vars.get("id"), 11)
    enviados = dict((c, _texto(request.post_vars.get(c), 300)) for c in ("name", "description", "is_admin", "version"))
    try:
        salvo_id, erros = servico.save(ctx, _ip_origem(), perfil_id, enviados)
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    except RepoError:
        _log.exception("falha ao salvar perfil (login=%s id=%r)", ctx["login"], perfil_id, extra={"action": _FUNC})
        salvo_id, erros = None, {admin_crud.GENERAL_FIELD: admin_crud.MSG_FAILURE}
    if not erros:
        session.flash = {"tipo": "sucesso", "mensagem": u"Perfil salvo com sucesso."}
        redirect(URL(c="admin_perfis", f="lista"))
    try:
        dados = servico.form(ctx, perfil_id) if perfil_id else servico.form(ctx)
    except RepoError:
        dados = {"id": None, "name": "", "description": "", "is_admin": "N", "active": "Y", "version": "",
                 "usuarios_ativos": 0}
    if admin_crud.GENERAL_FIELD not in erros:
        dados = dict(dados, name=enviados["name"] or "", description=enviados["description"] or "",
                     is_admin="Y" if enviados["is_admin"] == "Y" else "N")
        if perfil_id:
            dados["version"] = enviados["version"] or ""
    # Status 200: um 4xx seria substituido pela pagina de erro do routes_onerror.
    response.flash = {"tipo": "erro", "mensagem": erros.get(admin_crud.GENERAL_FIELD)
                      or ui_helpers.mensagem("formulario")}
    return _pagina_form(ctx, dados, erros)


def alternar_ativo():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    perfil_id = _texto(request.post_vars.get("id"), 11)
    try:
        alterado = servico.toggle_active(ctx, _ip_origem(), perfil_id, _texto(request.post_vars.get("version"), 64))
        acao = u"desativado" if alterado["active"] == "N" else u"reativado"
        session.flash = {"tipo": "sucesso", "mensagem": u"Perfil %s %s." % (alterado["name"], acao)}
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    except OperationDenied as exc:
        session.flash = {"tipo": "erro", "mensagem": exc.mensagem}
    except RepoConflict:
        session.flash = {"tipo": "aviso", "mensagem": admin_crud.MSG_CONFLICT}
    except RepoError:
        _log.exception("falha ao alternar perfil (login=%s id=%r)", ctx["login"], perfil_id, extra={"action": _FUNC})
        session.flash = {"tipo": "erro", "mensagem": _MSG_FALHA_ALTERNAR}
    redirect(URL(c="admin_perfis", f="form", args=[perfil_id]))


def quem_pode():
    """Quem pode o que (README §4.3.B.2): so leitura, por script ou por ambiente."""
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    try:
        dados = servico.who_can(ctx, _texto(request.get_vars.get("script"), 11),
                                  _texto(request.get_vars.get("environment"), 11))
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    response.title = u"Quem pode o quê — SSS"
    return dict(q=dados)


def matriz():
    _exigir_metodo("GET", "HEAD")
    ctx = _exigir_func(_FUNC)
    try:
        dados = servico.matrix(ctx, _texto(request.args(0), 11))
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    response.title = u"Permissões de %s — SSS" % dados["perfil"]["name"]
    response.sss_scripts = [_JS_MATRIZ]
    return dict(matriz=dados)


def salvar_matriz():
    _exigir_metodo("POST")
    ctx = _exigir_func(_FUNC)
    perfil_id = _texto(request.post_vars.get("id"), 11)
    try:
        diff, erros = servico.save_matrix(ctx, _ip_origem(), perfil_id, _lista("funcs"), _lista("ambs"),
                                            _lista("scrs"), _texto(request.post_vars.get("perm_version"), 11))
    except RepoNotFound:
        _nao_encontrado()
    except AccessDenied:
        _negado()
    except RepoError:
        _log.exception("falha ao salvar matriz (login=%s id=%r)", ctx["login"], perfil_id, extra={"action": "PERM_UPDATE"})
        diff, erros = None, {admin_crud.GENERAL_FIELD: _MSG_FALHA_MATRIZ}
    if erros:
        session.flash = {"tipo": "erro", "mensagem": erros[admin_crud.GENERAL_FIELD]}
    elif diff:
        session.flash = {"tipo": "sucesso", "mensagem": u"Permissões salvas: %s" % diff}
    else:
        session.flash = {"tipo": "aviso", "mensagem": u"Nenhuma alteração para salvar."}
    redirect(URL(c="admin_perfis", f="matriz", args=[perfil_id]))
