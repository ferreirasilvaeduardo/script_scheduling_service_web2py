# -*- coding: utf-8 -*-
"""Contrato de persistencia para catalogo (ambientes, scripts, homologacoes, parametros e vinculos)."""


class RepoCatalog(object):
    """Contrato abstrato para gestao de environments, scripts e parametros.

    Colunas de registro (CR-006, README §10): toda gravacao de negocio exige o actor, por
    auditoria['actor'] ou pelo parametro actor=; o INSERT grava created_*, a alteracao grava updated_*.
    Sem actor, RepoViolation sem gravar nada.
    """

    def environments_list(self, filtros=None, pagina=1, tamanho=20):
        """Lista ambientes paginados com formato {'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}."""
        raise NotImplementedError

    def environments_get(self, id):
        """Retorna dict com dados do ambiente ou lanca RepoNotFound."""
        raise NotImplementedError

    def environments_insert(self, dados, auditoria=None, ator=None):
        """Insere novo ambiente e retorna dict com o registro criado.

        auditoria: opcional, {'actor', 'ip', 'action', 'detail'}; gravada na mesma transacao
        (entidade tbsss_environments, entidade_id = novo id).
        """
        raise NotImplementedError

    def environments_update(self, id, dados, esperado=None, auditoria=None, ator=None):
        """Atualiza dados do environment e retorna o registro alterado. Nome e imutavel.

        esperado: opcional, dict campo -> valor lido pelo chamador; o UPDATE e condicional a esses
        valores (concorrencia otimista) e, se algum divergir, lanca RepoConflict sem alterar nada.
        auditoria: opcional, como em ambientes_inserir, gravada na mesma transacao do UPDATE.
        """
        raise NotImplementedError

    def scripts_list(self, filtros=None, pagina=1, tamanho=20):
        """Lista scripts paginados com formato {'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}.

        Ordem: nome ASC, id ASC. Filtros: nome (trecho), grupo, categoria, interpretador (logico) e ativo.
        Cada item traz 'ambientes_homologados' (nomes, ordem alfabetica) e 'qtd_parametros'.
        """
        raise NotImplementedError

    def scripts_get(self, id):
        """Retorna dict com dados do script ou lanca RepoNotFound."""
        raise NotImplementedError

    def scripts_insert(self, dados, auditoria=None, ator=None):
        """Insere novo script e retorna dict com o registro criado (auditoria opcional na mesma transacao)."""
        raise NotImplementedError

    def scripts_update(self, id, dados, esperado=None, auditoria=None, ator=None):
        """Atualiza o script e retorna o registro; esperado divergente lanca RepoConflict.

        Trocar tipo_param revalida os vinculos na mesma operacao: NENHUM com vinculo lanca
        RepoViolation('sss_scr_nenhum_vinculado'); NOMEADO com parametro sem flag lanca
        RepoViolation('sss_scr_nomeado_sem_flag'). auditoria: opcional, na mesma transacao.
        """
        raise NotImplementedError

    def homologation_get(self, script_id):
        """Retorna lista de ambiente_id homologados para o script."""
        raise NotImplementedError

    def homologation_save(self, script_id, ambiente_ids, esperado=None, auditoria=None, ator=None):
        """Substitui os ambientes homologados do script e retorna a lista resultante.

        esperado: opcional, lista de ambiente_id lida; divergencia lanca RepoConflict.
        auditoria: opcional (entidade tbsss_scripts), na mesma transacao.
        """
        raise NotImplementedError

    def parameters_list(self, filtros=None, pagina=1, tamanho=20):
        """Lista parametros paginados com formato {'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}.

        Ordem: codigo ASC, id ASC. Cada item traz 'qtd_scripts' (vinculos em tbsss_script_param, de
        scripts ativos ou nao), calculado na mesma consulta.
        """
        raise NotImplementedError

    def parameters_get(self, id):
        """Retorna dict com dados do parametro ou lanca RepoNotFound."""
        raise NotImplementedError

    def parameters_insert(self, dados, auditoria=None, ator=None):
        """Insere novo parametro e retorna dict com o registro criado.

        auditoria: opcional, {'actor', 'ip', 'action', 'detail'}; gravada na mesma transacao
        (entidade tbsss_parameters, entidade_id = novo id).
        """
        raise NotImplementedError

    def parameters_update(self, id, dados, esperado=None, auditoria=None, ator=None):
        """Atualiza o parametro e retorna o registro, com as regras de dependencia na mesma operacao.

        Lanca RepoViolation com constraint de aplicacao, sem alterar nada, quando:
        sss_prm_tipo_vinculado (tipo_componente muda e ha qualquer vinculo), sss_prm_flag_nomeado
        (param_nomeado muda e ha vinculo com script NOMEADO) ou sss_prm_vinculo_ativo (desativacao com
        vinculo a script ativo). esperado: opcional, divergencia lanca RepoConflict.
        auditoria: opcional, na mesma transacao.
        """
        raise NotImplementedError

    def parameter_links(self, parametro_id):
        """Retorna lista de scripts vinculados ao parametro para verificacao de desativacao."""
        raise NotImplementedError

    def script_params_get(self, script_id):
        """Retorna lista de vinculos ordenados por ordem com dados completos do parametro."""
        raise NotImplementedError

    def script_params_save(self, script_id, vinculos, esperado=None, auditoria=None, ator=None):
        """Substitui os vinculos do script ({parametro_id, ordem, obrigatorio, valor_padrao_sub}).

        Regras na mesma operacao: script NENHUM nao aceita vinculo ('sss_scr_nenhum_vinculado');
        script NOMEADO exige param_nomeado em todo parametro ('sss_scr_nomeado_sem_flag').
        esperado: opcional, lista lida de (parametro_id, ordem, obrigatorio, valor_padrao_sub);
        divergencia lanca RepoConflict. auditoria: opcional (entidade tbsss_scripts).
        """
        raise NotImplementedError

    def executable_scripts(self, usuario_ctx):
        """Retorna lista de scripts executaveis autorizados para o contexto de usuario (README §4.3.A)."""
        raise NotImplementedError
