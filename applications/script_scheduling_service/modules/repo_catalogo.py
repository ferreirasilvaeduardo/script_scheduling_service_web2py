# -*- coding: utf-8 -*-
"""Contrato de persistencia para catalogo (ambientes, scripts, homologacoes, parametros e vinculos)."""


class RepoCatalogo(object):
    """Contrato abstrato para gestao de ambientes, scripts e parametros."""

    def ambientes_listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista ambientes paginados com formato {'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}."""
        raise NotImplementedError

    def ambientes_obter(self, id):
        """Retorna dict com dados do ambiente ou lanca RepoNaoEncontrado."""
        raise NotImplementedError

    def ambientes_inserir(self, dados, auditoria=None):
        """Insere novo ambiente e retorna dict com o registro criado.

        auditoria: opcional, {'ator', 'ip', 'acao', 'detalhe'}; gravada na mesma transacao
        (entidade tbsss_ambientes, entidade_id = novo id).
        """
        raise NotImplementedError

    def ambientes_alterar(self, id, dados, esperado=None, auditoria=None):
        """Atualiza dados do ambiente e retorna o registro alterado. Nome e imutavel.

        esperado: opcional, dict campo -> valor lido pelo chamador; o UPDATE e condicional a esses
        valores (concorrencia otimista) e, se algum divergir, lanca RepoConflito sem alterar nada.
        auditoria: opcional, como em ambientes_inserir, gravada na mesma transacao do UPDATE.
        """
        raise NotImplementedError

    def scripts_listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista scripts paginados com formato {'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}."""
        raise NotImplementedError

    def scripts_obter(self, id):
        """Retorna dict com dados do script ou lanca RepoNaoEncontrado."""
        raise NotImplementedError

    def scripts_inserir(self, dados):
        """Insere novo script e retorna dict com o registro criado."""
        raise NotImplementedError

    def scripts_alterar(self, id, dados):
        """Atualiza dados do script."""
        raise NotImplementedError

    def homologacao_obter(self, script_id):
        """Retorna lista de ambiente_id homologados para o script."""
        raise NotImplementedError

    def homologacao_salvar(self, script_id, ambiente_ids):
        """Atualiza os ambientes homologados para o script."""
        raise NotImplementedError

    def parametros_listar(self, filtros=None, pagina=1, tamanho=20):
        """Lista parametros paginados com formato {'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}."""
        raise NotImplementedError

    def parametros_obter(self, id):
        """Retorna dict com dados do parametro ou lanca RepoNaoEncontrado."""
        raise NotImplementedError

    def parametros_inserir(self, dados):
        """Insere novo parametro e retorna dict com o registro criado."""
        raise NotImplementedError

    def parametros_alterar(self, id, dados):
        """Atualiza dados do parametro."""
        raise NotImplementedError

    def parametro_vinculos(self, parametro_id):
        """Retorna lista de scripts vinculados ao parametro para verificacao de desativacao."""
        raise NotImplementedError

    def script_params_obter(self, script_id):
        """Retorna lista de vinculos ordenados por ordem com dados completos do parametro."""
        raise NotImplementedError

    def script_params_salvar(self, script_id, vinculos):
        """Atualiza vinculos de parametros para o script com lista de dicts."""
        raise NotImplementedError

    def scripts_executaveis(self, usuario_ctx):
        """Retorna lista de scripts executaveis autorizados para o contexto de usuario (README §4.3.A)."""
        raise NotImplementedError
