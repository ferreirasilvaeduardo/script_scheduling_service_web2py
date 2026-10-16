# -*- coding: utf-8 -*-
"""Pastas e caminhos dos logs (README §8.4, §13, CR-005 D5/D6/D7).

Modulo puro: nao importa gluon (AGENTS §7.1). E o unico lugar que monta caminho de log (AGENTS §6).
"""
import re
import unicodedata

# Pasta dos logs da aplicacao; nenhum script pode ter essa pasta de log (CR-005, D7).
PASTA_APP = 'app'
_RE_FORA = re.compile(r'[^a-z0-9._-]+')


def pasta_script(nome, script_id=None):
    """Forma segura do nome do script para a pasta do log de execucao (CR-005, R-a).

    Sem acento (NFKD -> ASCII), minusculo, cada sequencia fora de [a-z0-9._-] vira '_',
    sem '.' ou '_' nas pontas. Vazio vira 'script_<id>' (ou 'script').
    """
    texto = unicodedata.normalize('NFKD', nome or u'')
    texto = texto.encode('ascii', 'ignore').decode('ascii').lower()
    texto = _RE_FORA.sub('_', texto).strip('._')
    if not texto:
        return 'script_%s' % script_id if script_id is not None else 'script'
    return texto


def nome_reservado(nome):
    """True se o nome do script geraria a pasta reservada 'app' (CR-005, D7)."""
    return pasta_script(nome) == PASTA_APP
