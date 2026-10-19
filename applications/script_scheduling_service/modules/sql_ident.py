# -*- coding: utf-8 -*-
"""Registro declarativo e geracao de identificadores Oracle para o SSS.

Fonte unica de verdade para nomes de tabelas, sequences, triggers, PK, UK, FK,
CK e indices (Oracle 11gR2 limitados a 30 caracteres).
Consumido por init_db.py, repo_oracle e testes de conformidade.
Nao gera DDL e nao importa drivers nem gluon.
"""
import copy
import re
from collections import OrderedDict

# Regex oficiais de validacao (AGENTS.md §3.1)
PADRAO_OWNER = r"^[A-Za-z][A-Za-z0-9_]{0,29}$"
PADRAO_PREFIXO = r"^[a-z][a-z0-9_]{0,7}$"
PADRAO_IDENTIFICADOR = r"^[a-zA-Z][a-zA-Z0-9_]{0,29}$"
PADRAO_IDENT_ASCII_LOWER = r"^[a-z][a-z0-9_]*$"

_RE_OWNER = re.compile(PADRAO_OWNER)
_RE_PREFIXO = re.compile(PADRAO_PREFIXO)
_RE_IDENT = re.compile(PADRAO_IDENTIFICADOR)
_RE_IDENT_ASCII_LOWER = re.compile(PADRAO_IDENT_ASCII_LOWER)

# Expressoes literais de indices baseados em funcao (FBI) - README §10.13 e AGENTS §4.8
FBI_TCK_FILA_EXPR = (
    "((CASE WHEN status = 'PENDING' THEN prioridade END), "
    "(CASE WHEN status = 'PENDING' THEN scheduled_at END))"
)
FBI_TCK_RUN_EXPR = "((CASE WHEN status = 'RUNNING' THEN agente_id END))"

# Cláusulas CASE individuais para composicao identica em queries (README §10.13, AGENTS §4.8)
FBI_TCK_FILA_PRIO_CASE = "CASE WHEN status = 'PENDING' THEN prioridade END"
FBI_TCK_FILA_SCHED_CASE = "CASE WHEN status = 'PENDING' THEN scheduled_at END"
FBI_TCK_RUN_AGENTE_CASE = "CASE WHEN status = 'RUNNING' THEN agente_id END"

# Indice unico da ocorrencia de agendamento (CR-007, R-27): so tickets de agendamento entram no indice.
FBI_TCK_OCOR_EXPR = (
    "((CASE WHEN agendamento_id IS NOT NULL THEN agendamento_id END), "
    "(CASE WHEN agendamento_id IS NOT NULL THEN scheduled_at END))"
)

# Versao do esquema que o codigo espera em tbsss_controle (CR-007, D4). Toda mudanca de esquema a
# incrementa e traz a migracao scripts/migracoes/m<NNNN>_*.py no mesmo pacote (AGENTS §4.16).
VERSAO_ESQUEMA = 1

# Colunas de registro (CR-006, README §10): todas as tabelas, exceto as listadas em TABELAS_SEM_REGISTRO.
COLUNAS_REGISTRO = ("created_at", "created_by", "updated_at", "updated_by")
TABELAS_SEM_REGISTRO = ("auditoria", "controle")
ATOR_MAX = 40
CK_REGISTRO_EXPR = (
    "(updated_at IS NULL AND updated_by IS NULL) OR "
    "(updated_at IS NOT NULL AND updated_by IS NOT NULL)"
)


def _eco_seguro(valor):
    """Retorna representacao segura do valor sem expor dados que excedam 64 caracteres."""
    if valor is None:
        return "None"
    if not isinstance(valor, str):
        return "tipo invalido ({})".format(type(valor).__name__)
    if len(valor) > 64:
        return "<valor com {} caracteres excede limite de 64>".format(len(valor))
    return "'{}'".format(valor)


def validar_owner(owner):
    """Valida o nome do owner/schema Oracle conforme AGENTS §3.1.

    Aceita ^[A-Za-z][A-Za-z0-9_]{0,29}$ com comprimento maximo de 30 caracteres.
    Lanca ValueError se invalido, sem ecoar o valor se tiver mais de 64 caracteres.
    """
    if not isinstance(owner, str) or not _RE_OWNER.fullmatch(owner):
        raise ValueError("Owner invalido: {}".format(_eco_seguro(owner)))
    return owner


def validar_prefixo(prefixo):
    """Valida o prefixo de tabela conforme AGENTS §3.1.

    Aceita ^[A-Za-z][A-Za-z0-9_]{0,7}$: comeca com letra (nome Oracle valido), ate 8 caracteres.
    Lanca ValueError se invalido, sem ecoar o valor se tiver mais de 64 caracteres.
    """
    if not isinstance(prefixo, str) or not _RE_PREFIXO.fullmatch(prefixo):
        raise ValueError("Prefixo invalido: {}".format(_eco_seguro(prefixo)))
    return prefixo


def validar_nome(nome, prefixo=None):
    """Valida sintaxe e tamanho de um identificador Oracle (<= 30 caracteres).

    Se prefixo for informado, verifica tambem presenca no catalogo de identificadores.
    Lanca ValueError se invalido, sem ecoar o valor se tiver mais de 64 caracteres.
    """
    if not isinstance(nome, str) or len(nome) > 30 or not _RE_IDENT.fullmatch(nome):
        raise ValueError("Nome de objeto invalido: {}".format(_eco_seguro(nome)))
    if prefixo is not None:
        validar_prefixo(prefixo)
        catalogo = todos_identificadores(prefixo)
        if nome.lower() not in catalogo:
            raise ValueError(
                "Nome de objeto nao registrado no catalogo: {}".format(_eco_seguro(nome))
            )
    return nome


def qualificar(owner, nome, prefixo=None):
    """Valida e retorna OWNER.NOME qualificado para uso em SQL (AGENTS §3.1)."""
    v_owner = validar_owner(owner)
    v_nome = validar_nome(nome, prefixo=prefixo)
    return "{}.{}".format(v_owner, v_nome)


# ---------------------------------------------------------------------------
# Registro Declarativo das 17 Tabelas (README §10)
# ---------------------------------------------------------------------------

def _criar_registro_tabelas():
    """Constroi o registro declarativo ordenado das 17 tabelas do SSS."""
    r = OrderedDict()

    # 1. Ambientes
    r['ambientes'] = OrderedDict([
        ('entidade', 'ambientes'),
        ('abrev', 'amb'),
        ('rotulo', 'Ambientes'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('nome', {'nome': 'nome', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('descricao', {'nome': 'descricao', 'tipo': 'VARCHAR2(100 CHAR)', 'not_null': False, 'default': None}),
            ('conexao', {'nome': 'conexao', 'tipo': 'VARCHAR2(250 CHAR)', 'not_null': False, 'default': None}),
            ('ativo', {'nome': 'ativo', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'S'"}),
            ('created_at', {'nome': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('nome', {'sufixo': 'nome', 'colunas': ('nome',)}),
        ])),
        ('fks', OrderedDict()),
        ('cks', OrderedDict([
            ('ativo', {'sufixo': 'ativo', 'expr': "ativo IN ('S', 'N')"}),
            ('nome', {'sufixo': 'nome', 'expr': "REGEXP_LIKE(nome, '^[A-Z0-9_]{1,30}$')"}),
            ('conexao', {'sufixo': 'conexao', 'expr': "conexao IS NULL OR INSTR(conexao, '@') = 0"}),
        ])),
        ('indices', OrderedDict()),
        ('trigger_bu', {'sufixo': 'bu', 'coluna_imutavel': 'nome'}),
        ('colunas_lob', ()),
    ])

    # 2. Perfis
    r['perfis'] = OrderedDict([
        ('entidade', 'perfis'),
        ('abrev', 'per'),
        ('rotulo', 'Perfis'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('nome', {'nome': 'nome', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('descricao', {'nome': 'descricao', 'tipo': 'VARCHAR2(100 CHAR)', 'not_null': False, 'default': None}),
            ('is_admin', {'nome': 'is_admin', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'N'"}),
            ('perm_versao', {'nome': 'perm_versao', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': '1'}),
            ('ativo', {'nome': 'ativo', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'S'"}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('nome', {'sufixo': 'nome', 'colunas': ('nome',)}),
        ])),
        ('fks', OrderedDict()),
        ('cks', OrderedDict([
            ('adm', {'sufixo': 'adm', 'expr': "is_admin IN ('S', 'N')"}),
            ('ativo', {'sufixo': 'ativo', 'expr': "ativo IN ('S', 'N')"}),
            ('versao', {'sufixo': 'versao', 'expr': "perm_versao >= 1"}),
        ])),
        ('indices', OrderedDict()),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 3. Funcionalidades
    r['funcionalidades'] = OrderedDict([
        ('entidade', 'funcionalidades'),
        ('abrev', 'fnc'),
        ('rotulo', 'Funcionalidades'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('codigo', {'nome': 'codigo', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('nome', {'nome': 'nome', 'tipo': 'VARCHAR2(60 CHAR)', 'not_null': True, 'default': None}),
            ('modulo', {'nome': 'modulo', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('descricao', {'nome': 'descricao', 'tipo': 'VARCHAR2(150 CHAR)', 'not_null': False, 'default': None}),
            ('ativo', {'nome': 'ativo', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'S'"}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('codigo', {'sufixo': 'codigo', 'colunas': ('codigo',)}),
        ])),
        ('fks', OrderedDict()),
        ('cks', OrderedDict([
            ('ativo', {'sufixo': 'ativo', 'expr': "ativo IN ('S', 'N')"}),
        ])),
        ('indices', OrderedDict()),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 4. Perfil x Funcionalidade
    r['perfil_func'] = OrderedDict([
        ('entidade', 'perfil_func'),
        ('abrev', 'pfnc'),
        ('rotulo', 'Perfil x Funcionalidade'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('perfil_id', {'nome': 'perfil_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('funcionalidade_id', {'nome': 'funcionalidade_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('per_fnc', {'sufixo': 'per_fnc', 'colunas': ('perfil_id', 'funcionalidade_id')}),
        ])),
        ('fks', OrderedDict([
            ('per', {'sufixo': 'per', 'colunas': ('perfil_id',), 'ref_tabela': 'perfis', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
            ('fnc', {'sufixo': 'fnc', 'colunas': ('funcionalidade_id',), 'ref_tabela': 'funcionalidades', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
        ])),
        ('cks', OrderedDict()),
        ('indices', OrderedDict([
            ('fnc', {'sufixo': 'fnc', 'colunas': ('funcionalidade_id',), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 5. Perfil x Ambiente
    r['perfil_amb'] = OrderedDict([
        ('entidade', 'perfil_amb'),
        ('abrev', 'pamb'),
        ('rotulo', 'Perfil x Ambiente'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('perfil_id', {'nome': 'perfil_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('ambiente_id', {'nome': 'ambiente_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('per_amb', {'sufixo': 'per_amb', 'colunas': ('perfil_id', 'ambiente_id')}),
        ])),
        ('fks', OrderedDict([
            ('per', {'sufixo': 'per', 'colunas': ('perfil_id',), 'ref_tabela': 'perfis', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
            ('amb', {'sufixo': 'amb', 'colunas': ('ambiente_id',), 'ref_tabela': 'ambientes', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
        ])),
        ('cks', OrderedDict()),
        ('indices', OrderedDict([
            ('amb', {'sufixo': 'amb', 'colunas': ('ambiente_id',), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 6. Scripts
    r['scripts'] = OrderedDict([
        ('entidade', 'scripts'),
        ('abrev', 'scr'),
        ('rotulo', 'Scripts'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('nome', {'nome': 'nome', 'tipo': 'VARCHAR2(60 CHAR)', 'not_null': True, 'default': None}),
            ('descricao', {'nome': 'descricao', 'tipo': 'VARCHAR2(200 CHAR)', 'not_null': False, 'default': None}),
            ('grupo', {'nome': 'grupo', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': False, 'default': None}),
            ('categoria', {'nome': 'categoria', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': False, 'default': None}),
            ('etapa', {'nome': 'etapa', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': False, 'default': None}),
            ('interpretador', {'nome': 'interpretador', 'tipo': 'VARCHAR2(15 CHAR)', 'not_null': True, 'default': None}),
            ('path_file', {'nome': 'path_file', 'tipo': 'VARCHAR2(500 CHAR)', 'not_null': True, 'default': None}),
            ('tipo_param', {'nome': 'tipo_param', 'tipo': 'VARCHAR2(15 CHAR)', 'not_null': True, 'default': "'NOMEADO'"}),
            ('max_qtd_parallel_env', {'nome': 'max_qtd_parallel_env', 'tipo': 'NUMBER(3)', 'not_null': True, 'default': '1'}),
            ('timeout_seg', {'nome': 'timeout_seg', 'tipo': 'NUMBER(7)', 'not_null': False, 'default': None}),
            ('ativo', {'nome': 'ativo', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'S'"}),
            ('sha256_homologado', {'nome': 'sha256_homologado', 'tipo': 'VARCHAR2(64 CHAR)', 'not_null': False, 'default': None}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('nome', {'sufixo': 'nome', 'colunas': ('nome',)}),
        ])),
        ('fks', OrderedDict()),
        ('cks', OrderedDict([
            ('tparam', {'sufixo': 'tparam', 'expr': "tipo_param IN ('NOMEADO','SEQUENCIAL','NENHUM')"}),
            ('ativo', {'sufixo': 'ativo', 'expr': "ativo IN ('S', 'N')"}),
            ('paral', {'sufixo': 'paral', 'expr': "max_qtd_parallel_env BETWEEN 1 AND 999"}),
            ('int', {'sufixo': 'int', 'expr': "interpretador IN ('PYTHON3','BASH','SH')"}),
            ('path', {'sufixo': 'path', 'expr': "SUBSTR(path_file, 1, 1) = '/' AND INSTR(path_file, '..') = 0 AND INSTR(path_file, '//') = 0 AND INSTR(path_file, '\\') = 0"}),
            ('tmout', {'sufixo': 'tmout', 'expr': "timeout_seg IS NULL OR timeout_seg > 0"}),
            ('sha', {'sufixo': 'sha', 'expr': "sha256_homologado IS NULL OR REGEXP_LIKE(sha256_homologado, '^[0-9a-f]{64}$')"}),
        ])),
        ('indices', OrderedDict()),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 7. Perfil x Script
    r['perfil_scr'] = OrderedDict([
        ('entidade', 'perfil_scr'),
        ('abrev', 'pscr'),
        ('rotulo', 'Perfil x Script'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('perfil_id', {'nome': 'perfil_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('script_id', {'nome': 'script_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('per_scr', {'sufixo': 'per_scr', 'colunas': ('perfil_id', 'script_id')}),
        ])),
        ('fks', OrderedDict([
            ('per', {'sufixo': 'per', 'colunas': ('perfil_id',), 'ref_tabela': 'perfis', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
            ('scr', {'sufixo': 'scr', 'colunas': ('script_id',), 'ref_tabela': 'scripts', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
        ])),
        ('cks', OrderedDict()),
        ('indices', OrderedDict([
            ('scr', {'sufixo': 'scr', 'colunas': ('script_id',), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 8. Script x Ambiente
    r['script_amb'] = OrderedDict([
        ('entidade', 'script_amb'),
        ('abrev', 'samb'),
        ('rotulo', 'Script x Ambiente'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('script_id', {'nome': 'script_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('ambiente_id', {'nome': 'ambiente_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('scr_amb', {'sufixo': 'scr_amb', 'colunas': ('script_id', 'ambiente_id')}),
        ])),
        ('fks', OrderedDict([
            ('scr', {'sufixo': 'scr', 'colunas': ('script_id',), 'ref_tabela': 'scripts', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
            ('amb', {'sufixo': 'amb', 'colunas': ('ambiente_id',), 'ref_tabela': 'ambientes', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
        ])),
        ('cks', OrderedDict()),
        ('indices', OrderedDict([
            ('amb', {'sufixo': 'amb', 'colunas': ('ambiente_id',), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 9. Usuarios
    r['usuarios'] = OrderedDict([
        ('entidade', 'usuarios'),
        ('abrev', 'usr'),
        ('rotulo', 'Usuários'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('login', {'nome': 'login', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('nome', {'nome': 'nome', 'tipo': 'VARCHAR2(60 CHAR)', 'not_null': True, 'default': None}),
            ('senha_hash', {'nome': 'senha_hash', 'tipo': 'VARCHAR2(256 CHAR)', 'not_null': True, 'default': None}),
            ('perfil_id', {'nome': 'perfil_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('tentativas_falha', {'nome': 'tentativas_falha', 'tipo': 'NUMBER(2)', 'not_null': True, 'default': '0'}),
            ('bloqueado_ate', {'nome': 'bloqueado_ate', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('ultimo_login', {'nome': 'ultimo_login', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('senha_alterada_em', {'nome': 'senha_alterada_em', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('sessao_epoch', {'nome': 'sessao_epoch', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': '0'}),
            ('ativo', {'nome': 'ativo', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'S'"}),
            ('created_at', {'nome': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('login', {'sufixo': 'login', 'colunas': ('login',)}),
        ])),
        ('fks', OrderedDict([
            ('per', {'sufixo': 'per', 'colunas': ('perfil_id',), 'ref_tabela': 'perfis', 'ref_colunas': ('id',), 'on_delete': None}),
        ])),
        ('cks', OrderedDict([
            ('ativo', {'sufixo': 'ativo', 'expr': "ativo IN ('S', 'N')"}),
            ('login', {'sufixo': 'login', 'expr': "REGEXP_LIKE(login, '^[a-z0-9._-]{3,30}$')"}),
            ('tent', {'sufixo': 'tent', 'expr': "tentativas_falha >= 0"}),
            ('epoch', {'sufixo': 'epoch', 'expr': "sessao_epoch >= 0"}),
        ])),
        ('indices', OrderedDict([
            ('per', {'sufixo': 'per', 'colunas': ('perfil_id',), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', {'sufixo': 'bu', 'coluna_imutavel': 'login'}),
        ('colunas_lob', ()),
    ])

    # 10. Parametros
    r['parametros'] = OrderedDict([
        ('entidade', 'parametros'),
        ('abrev', 'prm'),
        ('rotulo', 'Parâmetros'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('codigo', {'nome': 'codigo', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('param_nomeado', {'nome': 'param_nomeado', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': False, 'default': None}),
            ('label', {'nome': 'label', 'tipo': 'VARCHAR2(60 CHAR)', 'not_null': True, 'default': None}),
            ('descricao', {'nome': 'descricao', 'tipo': 'VARCHAR2(150 CHAR)', 'not_null': False, 'default': None}),
            ('tipo_componente', {'nome': 'tipo_componente', 'tipo': 'VARCHAR2(20 CHAR)', 'not_null': True, 'default': None}),
            ('opcoes_json', {'nome': 'opcoes_json', 'tipo': 'VARCHAR2(500 CHAR)', 'not_null': False, 'default': None}),
            ('valor_padrao', {'nome': 'valor_padrao', 'tipo': 'VARCHAR2(100 CHAR)', 'not_null': False, 'default': None}),
            ('regex_validacao', {'nome': 'regex_validacao', 'tipo': 'VARCHAR2(150 CHAR)', 'not_null': False, 'default': None}),
            ('sensivel', {'nome': 'sensivel', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'N'"}),
            ('ativo', {'nome': 'ativo', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'S'"}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('codigo', {'sufixo': 'codigo', 'colunas': ('codigo',)}),
        ])),
        ('fks', OrderedDict()),
        ('cks', OrderedDict([
            ('tcomp', {'sufixo': 'tcomp', 'expr': "tipo_componente IN ('TEXT','NUMBER','DATE','SELECT','CHECKBOX')"}),
            ('ativo', {'sufixo': 'ativo', 'expr': "ativo IN ('S', 'N')"}),
            ('sens', {'sufixo': 'sens', 'expr': "sensivel IN ('S','N')"}),
            ('codigo', {'sufixo': 'codigo', 'expr': "REGEXP_LIKE(codigo, '^[a-z0-9_]{1,30}$')"}),
            ('flag', {'sufixo': 'flag', 'expr': "param_nomeado IS NULL OR REGEXP_LIKE(param_nomeado, '^-{1,2}[A-Za-z0-9][A-Za-z0-9_-]{0,27}$')"}),
        ])),
        ('indices', OrderedDict()),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 11. Script x Parametro
    r['script_param'] = OrderedDict([
        ('entidade', 'script_param'),
        ('abrev', 'sprm'),
        ('rotulo', 'Script x Parâmetro'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('script_id', {'nome': 'script_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('parametro_id', {'nome': 'parametro_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('ordem', {'nome': 'ordem', 'tipo': 'NUMBER(3)', 'not_null': True, 'default': None}),
            ('obrigatorio', {'nome': 'obrigatorio', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'S'"}),
            ('valor_padrao_sub', {'nome': 'valor_padrao_sub', 'tipo': 'VARCHAR2(100 CHAR)', 'not_null': False, 'default': None}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('scr_prm', {'sufixo': 'scr_prm', 'colunas': ('script_id', 'parametro_id')}),
            ('scr_ord', {'sufixo': 'scr_ord', 'colunas': ('script_id', 'ordem')}),
        ])),
        ('fks', OrderedDict([
            ('scr', {'sufixo': 'scr', 'colunas': ('script_id',), 'ref_tabela': 'scripts', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
            ('prm', {'sufixo': 'prm', 'colunas': ('parametro_id',), 'ref_tabela': 'parametros', 'ref_colunas': ('id',), 'on_delete': None}),
        ])),
        ('cks', OrderedDict([
            ('obrig', {'sufixo': 'obrig', 'expr': "obrigatorio IN ('S', 'N')"}),
            ('ordem', {'sufixo': 'ordem', 'expr': "ordem >= 1"}),
        ])),
        ('indices', OrderedDict([
            ('prm', {'sufixo': 'prm', 'colunas': ('parametro_id',), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 12. Agendamentos
    r['agendamentos'] = OrderedDict([
        ('entidade', 'agendamentos'),
        ('abrev', 'agd'),
        ('rotulo', 'Agendamentos'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('nome', {'nome': 'nome', 'tipo': 'VARCHAR2(60 CHAR)', 'not_null': True, 'default': None}),
            ('script_id', {'nome': 'script_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('ambiente', {'nome': 'ambiente', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('usuario_id', {'nome': 'usuario_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('prioridade', {'nome': 'prioridade', 'tipo': 'NUMBER(1)', 'not_null': True, 'default': '2'}),
            ('tipo_recorrencia', {'nome': 'tipo_recorrencia', 'tipo': 'VARCHAR2(15 CHAR)', 'not_null': True, 'default': None}),
            ('expressao_cron', {'nome': 'expressao_cron', 'tipo': 'VARCHAR2(60 CHAR)', 'not_null': False, 'default': None}),
            ('hora_execucao', {'nome': 'hora_execucao', 'tipo': 'VARCHAR2(5 CHAR)', 'not_null': False, 'default': None}),
            ('dias_semana', {'nome': 'dias_semana', 'tipo': 'VARCHAR2(20 CHAR)', 'not_null': False, 'default': None}),
            ('dia_mes', {'nome': 'dia_mes', 'tipo': 'NUMBER(2)', 'not_null': False, 'default': None}),
            ('parametros_json', {'nome': 'parametros_json', 'tipo': 'CLOB', 'not_null': False, 'default': None}),
            ('data_inicio', {'nome': 'data_inicio', 'tipo': 'DATE', 'not_null': True, 'default': None}),
            ('data_fim', {'nome': 'data_fim', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('proxima_execucao', {'nome': 'proxima_execucao', 'tipo': 'DATE', 'not_null': True, 'default': None}),
            ('ultima_execucao', {'nome': 'ultima_execucao', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('ultimo_ticket_id', {'nome': 'ultimo_ticket_id', 'tipo': 'NUMBER(10)', 'not_null': False, 'default': None}),
            ('pausa_motivo', {'nome': 'pausa_motivo', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': False, 'default': None}),
            ('ativo', {'nome': 'ativo', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'S'"}),
            ('created_at', {'nome': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict()),
        ('fks', OrderedDict([
            ('scr', {'sufixo': 'scr', 'colunas': ('script_id',), 'ref_tabela': 'scripts', 'ref_colunas': ('id',), 'on_delete': None}),
            ('usr', {'sufixo': 'usr', 'colunas': ('usuario_id',), 'ref_tabela': 'usuarios', 'ref_colunas': ('id',), 'on_delete': None}),
            ('amb', {'sufixo': 'amb', 'colunas': ('ambiente',), 'ref_tabela': 'ambientes', 'ref_colunas': ('nome',), 'on_delete': None}),
        ])),
        ('cks', OrderedDict([
            ('trec', {'sufixo': 'trec', 'expr': "tipo_recorrencia IN ('UNICA','DIARIA','SEMANAL','MENSAL','CRON')"}),
            ('prio', {'sufixo': 'prio', 'expr': "prioridade BETWEEN 1 AND 4"}),
            ('ativo', {'sufixo': 'ativo', 'expr': "ativo IN ('S', 'N')"}),
            ('dia', {'sufixo': 'dia', 'expr': "dia_mes IS NULL OR dia_mes BETWEEN 1 AND 31"}),
            ('hora', {'sufixo': 'hora', 'expr': "hora_execucao IS NULL OR REGEXP_LIKE(hora_execucao, '^([01][0-9]|2[0-3]):[0-5][0-9]$')"}),
            ('dsem', {'sufixo': 'dsem', 'expr': "dias_semana IS NULL OR REGEXP_LIKE(dias_semana, '^[1-7](,[1-7]){0,6}$')"}),
            ('fim', {'sufixo': 'fim', 'expr': "data_fim IS NULL OR data_fim >= data_inicio"}),
            ('pausa', {'sufixo': 'pausa', 'expr': "pausa_motivo IS NULL OR pausa_motivo IN ('USUARIO_INATIVO','SEM_PERMISSAO','SCRIPT_INATIVO','AMBIENTE_INATIVO','PARAM_INVALIDO','CRON_INVALIDO','CONCLUIDO','MANUAL','ERRO_INTERNO')"}),
            ('campos', {'sufixo': 'campos', 'expr': "(tipo_recorrencia = 'UNICA') OR (tipo_recorrencia = 'DIARIA' AND hora_execucao IS NOT NULL) OR (tipo_recorrencia = 'SEMANAL' AND hora_execucao IS NOT NULL AND dias_semana IS NOT NULL) OR (tipo_recorrencia = 'MENSAL' AND hora_execucao IS NOT NULL AND dia_mes IS NOT NULL) OR (tipo_recorrencia = 'CRON' AND expressao_cron IS NOT NULL)"}),
        ])),
        ('indices', OrderedDict([
            ('scr', {'sufixo': 'scr', 'colunas': ('script_id',), 'expr': None, 'fbi': False}),
            ('usr', {'sufixo': 'usr', 'colunas': ('usuario_id',), 'expr': None, 'fbi': False}),
            ('amb', {'sufixo': 'amb', 'colunas': ('ambiente',), 'expr': None, 'fbi': False}),
            ('prox', {'sufixo': 'prox', 'colunas': ('ativo', 'proxima_execucao', 'id'), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ('parametros_json',)),
    ])

    # 13. Tickets
    r['tickets'] = OrderedDict([
        ('entidade', 'tickets'),
        ('abrev', 'tck'),
        ('rotulo', 'Tickets'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('script_id', {'nome': 'script_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('ambiente', {'nome': 'ambiente', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('solicitante', {'nome': 'solicitante', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('ip_origem', {'nome': 'ip_origem', 'tipo': 'VARCHAR2(45 CHAR)', 'not_null': False, 'default': None}),
            ('agente_id', {'nome': 'agente_id', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': False, 'default': None}),
            ('process_id', {'nome': 'process_id', 'tipo': 'NUMBER(10)', 'not_null': False, 'default': None}),
            ('process_start', {'nome': 'process_start', 'tipo': 'NUMBER(20)', 'not_null': False, 'default': None}),
            ('status', {'nome': 'status', 'tipo': 'VARCHAR2(15 CHAR)', 'not_null': True, 'default': "'PENDING'"}),
            ('prioridade', {'nome': 'prioridade', 'tipo': 'NUMBER(1)', 'not_null': True, 'default': '2'}),
            ('cancel_requested', {'nome': 'cancel_requested', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'N'"}),
            ('status_motivo', {'nome': 'status_motivo', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': False, 'default': None}),
            ('parent_ticket_id', {'nome': 'parent_ticket_id', 'tipo': 'NUMBER(10)', 'not_null': False, 'default': None}),
            ('agendamento_id', {'nome': 'agendamento_id', 'tipo': 'NUMBER(10)', 'not_null': False, 'default': None}),
            ('parametros_enviados', {'nome': 'parametros_enviados', 'tipo': 'CLOB', 'not_null': True, 'default': None}),
            ('log_output', {'nome': 'log_output', 'tipo': 'CLOB', 'not_null': False, 'default': None}),
            ('log_offset_chars', {'nome': 'log_offset_chars', 'tipo': 'NUMBER(20)', 'not_null': True, 'default': '0'}),
            ('log_truncado', {'nome': 'log_truncado', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'N'"}),
            ('return_code', {'nome': 'return_code', 'tipo': 'NUMBER(6)', 'not_null': False, 'default': None}),
            ('arquivo_sha256', {'nome': 'arquivo_sha256', 'tipo': 'VARCHAR2(64 CHAR)', 'not_null': False, 'default': None}),
            ('scheduled_at', {'nome': 'scheduled_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
            ('started_at', {'nome': 'started_at', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('heartbeat_at', {'nome': 'heartbeat_at', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('finished_at', {'nome': 'finished_at', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('created_at', {'nome': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict()),
        ('fks', OrderedDict([
            ('scr', {'sufixo': 'scr', 'colunas': ('script_id',), 'ref_tabela': 'scripts', 'ref_colunas': ('id',), 'on_delete': None}),
            ('amb', {'sufixo': 'amb', 'colunas': ('ambiente',), 'ref_tabela': 'ambientes', 'ref_colunas': ('nome',), 'on_delete': None}),
            ('usr', {'sufixo': 'usr', 'colunas': ('solicitante',), 'ref_tabela': 'usuarios', 'ref_colunas': ('login',), 'on_delete': None}),
            ('parent', {'sufixo': 'parent', 'colunas': ('parent_ticket_id',), 'ref_tabela': 'tickets', 'ref_colunas': ('id',), 'on_delete': 'SET NULL'}),
            ('agd', {'sufixo': 'agd', 'colunas': ('agendamento_id',), 'ref_tabela': 'agendamentos', 'ref_colunas': ('id',), 'on_delete': 'SET NULL'}),
        ])),
        ('cks', OrderedDict([
            ('stat', {'sufixo': 'stat', 'expr': "status IN ('PENDING','RUNNING','SUCCESS','FAILED','CANCELLED')"}),
            ('prio', {'sufixo': 'prio', 'expr': "prioridade BETWEEN 1 AND 4"}),
            ('cancreq', {'sufixo': 'cancreq', 'expr': "cancel_requested IN ('S','N')"}),
            ('logtr', {'sufixo': 'logtr', 'expr': "log_truncado IN ('S','N')"}),
            ('logoff', {'sufixo': 'logoff', 'expr': 'log_offset_chars >= 0'}),
            ('motivo', {'sufixo': 'motivo', 'expr': "status_motivo IS NULL OR status_motivo IN ('EXIT_OK','EXIT_ERROR','KILLED_SIGNAL','TIMEOUT','NODE_OFFLINE','ORPHAN_PROCESS','FENCED','PRECHECK_FAILED','SPAWN_ERROR','LOG_LIMIT','SHUTDOWN','CANCEL_USER')"}),
            ('sha', {'sufixo': 'sha', 'expr': "arquivo_sha256 IS NULL OR REGEXP_LIKE(arquivo_sha256, '^[0-9a-f]{64}$')"}),
        ])),
        ('indices', OrderedDict([
            ('scr', {'sufixo': 'scr', 'colunas': ('script_id', 'ambiente', 'status'), 'expr': None, 'fbi': False}),
            ('amb', {'sufixo': 'amb', 'colunas': ('ambiente',), 'expr': None, 'fbi': False}),
            ('usr', {'sufixo': 'usr', 'colunas': ('solicitante',), 'expr': None, 'fbi': False}),
            ('par', {'sufixo': 'par', 'colunas': ('parent_ticket_id',), 'expr': None, 'fbi': False}),
            ('agd', {'sufixo': 'agd', 'colunas': ('agendamento_id',), 'expr': None, 'fbi': False}),
            # (created_at, id): retencao e a ordem da lista de tickets (created_at DESC, id DESC) sem SORT
            # da tabela inteira (F7.3, EXPLAIN com volume).
            ('crt', {'sufixo': 'crt', 'colunas': ('created_at', 'id'), 'expr': None, 'fbi': False}),
            ('hist', {'sufixo': 'hist', 'colunas': ('script_id', 'created_at'), 'expr': None, 'fbi': False}),
            ('fila', {'sufixo': 'fila', 'colunas': (), 'expr': FBI_TCK_FILA_EXPR, 'fbi': True}),
            ('run', {'sufixo': 'run', 'colunas': (), 'expr': FBI_TCK_RUN_EXPR, 'fbi': True}),
            ('ocor', {'sufixo': 'ocor', 'colunas': (), 'expr': FBI_TCK_OCOR_EXPR, 'fbi': True, 'unico': True}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ('parametros_enviados', 'log_output')),
    ])

    # 14. Ticket x Resposta
    r['ticket_resp'] = OrderedDict([
        ('entidade', 'ticket_resp'),
        ('abrev', 'trsp'),
        ('rotulo', 'Ticket x Resposta'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('ticket_id', {'nome': 'ticket_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('parametro_id', {'nome': 'parametro_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('valor_resposta', {'nome': 'valor_resposta', 'tipo': 'VARCHAR2(500 CHAR)', 'not_null': False, 'default': None}),
            ('created_at', {'nome': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('tck_prm', {'sufixo': 'tck_prm', 'colunas': ('ticket_id', 'parametro_id')}),
        ])),
        ('fks', OrderedDict([
            ('tck', {'sufixo': 'tck', 'colunas': ('ticket_id',), 'ref_tabela': 'tickets', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
            ('prm', {'sufixo': 'prm', 'colunas': ('parametro_id',), 'ref_tabela': 'parametros', 'ref_colunas': ('id',), 'on_delete': None}),
        ])),
        ('cks', OrderedDict()),
        ('indices', OrderedDict([
            ('prm', {'sufixo': 'prm', 'colunas': ('parametro_id',), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 15. Agentes
    r['agentes'] = OrderedDict([
        ('entidade', 'agentes'),
        ('abrev', 'agt'),
        ('rotulo', 'Agentes'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('codigo', {'nome': 'codigo', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('hostname', {'nome': 'hostname', 'tipo': 'VARCHAR2(255 CHAR)', 'not_null': True, 'default': None}),
            ('pid_daemon', {'nome': 'pid_daemon', 'tipo': 'NUMBER(10)', 'not_null': False, 'default': None}),
            ('versao', {'nome': 'versao', 'tipo': 'VARCHAR2(20 CHAR)', 'not_null': False, 'default': None}),
            ('ambientes', {'nome': 'ambientes', 'tipo': 'VARCHAR2(1000 CHAR)', 'not_null': False, 'default': None}),
            ('plataforma', {'nome': 'plataforma', 'tipo': 'VARCHAR2(10 CHAR)', 'not_null': False, 'default': None}),
            ('interpretadores', {'nome': 'interpretadores', 'tipo': 'VARCHAR2(100 CHAR)', 'not_null': False, 'default': None}),
            ('status', {'nome': 'status', 'tipo': 'VARCHAR2(10 CHAR)', 'not_null': True, 'default': "'ATIVO'"}),
            ('iniciado_em', {'nome': 'iniciado_em', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('heartbeat_at', {'nome': 'heartbeat_at', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('config_criticos', {'nome': 'config_criticos', 'tipo': 'VARCHAR2(400 CHAR)', 'not_null': False, 'default': None}),
            ('created_at', {'nome': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('codigo', {'sufixo': 'codigo', 'colunas': ('codigo',)}),
        ])),
        ('fks', OrderedDict()),
        ('cks', OrderedDict([
            ('stat', {'sufixo': 'stat', 'expr': "status IN ('ATIVO','PARADO')"}),
            ('plat', {'sufixo': 'plat', 'expr': "plataforma IS NULL OR plataforma IN ('LINUX','UNIX')"}),
        ])),
        ('indices', OrderedDict()),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 16. Auditoria
    r['auditoria'] = OrderedDict([
        ('entidade', 'auditoria'),
        ('abrev', 'aud'),
        ('rotulo', 'Auditoria'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('ator', {'nome': 'ator', 'tipo': 'VARCHAR2(40 CHAR)', 'not_null': True, 'default': None}),
            ('ip_origem', {'nome': 'ip_origem', 'tipo': 'VARCHAR2(45 CHAR)', 'not_null': False, 'default': None}),
            ('acao', {'nome': 'acao', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('entidade', {'nome': 'entidade', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('entidade_id', {'nome': 'entidade_id', 'tipo': 'NUMBER(10)', 'not_null': False, 'default': None}),
            ('detalhe', {'nome': 'detalhe', 'tipo': 'VARCHAR2(1000 CHAR)', 'not_null': False, 'default': None}),
            ('created_at', {'nome': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict()),
        ('fks', OrderedDict()),
        ('cks', OrderedDict()),
        ('indices', OrderedDict([
            ('crt', {'sufixo': 'crt', 'colunas': ('created_at',), 'expr': None, 'fbi': False}),
            ('ent', {'sufixo': 'ent', 'colunas': ('entidade', 'entidade_id'), 'expr': None, 'fbi': False}),
            ('ator', {'sufixo': 'ator', 'colunas': ('ator',), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 17. Controle (CR-007, D4): linha unica com a versao do esquema e a concessao do purge.
    r['controle'] = OrderedDict([
        ('entidade', 'controle'),
        ('abrev', 'ctl'),
        ('rotulo', 'Controle'),
        ('colunas', OrderedDict([
            ('id', {'nome': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('versao_esquema', {'nome': 'versao_esquema', 'tipo': 'NUMBER(6)', 'not_null': True, 'default': None}),
            ('versao_aplicada_em', {'nome': 'versao_aplicada_em', 'tipo': 'DATE', 'not_null': True, 'default': None}),
            ('versao_aplicada_por', {'nome': 'versao_aplicada_por', 'tipo': 'VARCHAR2(%d CHAR)' % ATOR_MAX, 'not_null': True, 'default': None}),
            ('purge_dono', {'nome': 'purge_dono', 'tipo': 'VARCHAR2(%d CHAR)' % ATOR_MAX, 'not_null': False, 'default': None}),
            ('purge_concessao_ate', {'nome': 'purge_concessao_ate', 'tipo': 'DATE', 'not_null': False, 'default': None}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict()),
        ('fks', OrderedDict()),
        ('cks', OrderedDict([
            ('id', {'sufixo': 'id', 'expr': "id = 1"}),
            ('versao', {'sufixo': 'versao', 'expr': "versao_esquema >= 1"}),
        ])),
        ('indices', OrderedDict()),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    for entidade, defn in r.items():
        if entidade not in TABELAS_SEM_REGISTRO:
            _aplicar_colunas_registro(defn)

    return r


def _aplicar_colunas_registro(defn):
    """Acrescenta as colunas de registro que faltam e a CK _upd (CR-006, README §10).

    created_at ja existe no fim de algumas tabelas; as demais colunas entram depois dela.
    """
    colunas = defn['colunas']
    novas = OrderedDict([
        ('created_at', {'nome': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ('created_by', {'nome': 'created_by', 'tipo': 'VARCHAR2(%d CHAR)' % ATOR_MAX, 'not_null': True, 'default': None}),
        ('updated_at', {'nome': 'updated_at', 'tipo': 'DATE', 'not_null': False, 'default': None}),
        ('updated_by', {'nome': 'updated_by', 'tipo': 'VARCHAR2(%d CHAR)' % ATOR_MAX, 'not_null': False, 'default': None}),
    ])
    for nome, coluna in novas.items():
        if nome not in colunas:
            colunas[nome] = coluna
    defn['cks']['upd'] = {'sufixo': 'upd', 'expr': CK_REGISTRO_EXPR}


# Instancia imutavel de referencia do catalogo
TABELAS = _criar_registro_tabelas()


class NomesEsquema(OrderedDict):
    """Container ordenado dos identificadores expandidos para um prefixo.

    Permite indexacao por entidade (ex: n['tickets']) e oferece metodo para
    extracao plana de todos os identificadores gerados no esquema.
    """

    def todos_identificadores(self, incluir_colunas=True):
        """Retorna o conjunto (set) de todos os identificadores expandidos."""
        ids = set()
        for entidade, t in self.items():
            ids.add(t['tabela'])
            ids.add(t['sequence'])
            ids.add(t['trigger_bi'])
            ids.add(t['trigger'])
            if t['trigger_bu']:
                ids.add(t['trigger_bu'])
            ids.add(t['pk'])
            for uk_nome in t['uks']:
                ids.add(uk_nome)
            for fk_nome in t['fks']:
                ids.add(fk_nome)
            for ck_nome in t['cks']:
                ids.add(ck_nome)
            for ix_nome in t['indices']:
                ids.add(ix_nome)
            if incluir_colunas:
                for col_nome in t['colunas']:
                    ids.add(col_nome)
        return ids

    def lista_identificadores(self, incluir_colunas=True):
        """Retorna lista ordenada de todos os identificadores expandidos."""
        return sorted(self.todos_identificadores(incluir_colunas=incluir_colunas))


def nomes(prefixo, tabelas=None):
    """Gera e retorna todos os identificadores expandidos a partir de table_prefix.

    Segue as regras do template README §9.1:
      tabela      = {prefixo}{entidade}
      sequence    = sq_{prefixo}{entidade}
      trigger PK  = tr_{prefixo}{abrev}_bi
      trigger UPD = tr_{prefixo}{abrev}_bu
      PK          = pk_{prefixo}{entidade}
      UK/FK/CK/IX = {uk|fk|ck|ix}_{prefixo}{abrev}_{sufixo}
    """
    validar_prefixo(prefixo)
    registro = TABELAS if tabelas is None else tabelas

    resultado = NomesEsquema()
    for entidade, defn in registro.items():
        abrev = defn['abrev']
        tabela_nome = "{}{}".format(prefixo, entidade)
        seq_nome = "sq_{}{}".format(prefixo, entidade)
        tr_bi_nome = "tr_{}{}_bi".format(prefixo, abrev)
        tr_bu_nome = "tr_{}{}_bu".format(prefixo, abrev) if defn.get('trigger_bu') else None
        pk_nome = "pk_{}{}".format(prefixo, entidade)

        uks = OrderedDict()
        for sufixo_key, uk_def in defn.get('uks', {}).items():
            suf = uk_def['sufixo']
            uk_nome = "uk_{}{}_{}".format(prefixo, abrev, suf)
            uks[uk_nome] = OrderedDict([
                ('nome', uk_nome),
                ('sufixo', suf),
                ('colunas', uk_def['colunas']),
            ])

        fks = OrderedDict()
        for sufixo_key, fk_def in defn.get('fks', {}).items():
            suf = fk_def['sufixo']
            fk_nome = "fk_{}{}_{}".format(prefixo, abrev, suf)
            ref_tabela_nome = "{}{}".format(prefixo, fk_def['ref_tabela'])
            fks[fk_nome] = OrderedDict([
                ('nome', fk_nome),
                ('sufixo', suf),
                ('colunas', fk_def['colunas']),
                ('ref_entidade', fk_def['ref_tabela']),
                ('ref_tabela', ref_tabela_nome),
                ('ref_colunas', fk_def['ref_colunas']),
                ('on_delete', fk_def.get('on_delete')),
            ])

        cks = OrderedDict()
        for sufixo_key, ck_def in defn.get('cks', {}).items():
            suf = ck_def['sufixo']
            ck_nome = "ck_{}{}_{}".format(prefixo, abrev, suf)
            cks[ck_nome] = OrderedDict([
                ('nome', ck_nome),
                ('sufixo', suf),
                ('expr', ck_def['expr']),
            ])

        indices = OrderedDict()
        for sufixo_key, ix_def in defn.get('indices', {}).items():
            suf = ix_def['sufixo']
            ix_nome = "ix_{}{}_{}".format(prefixo, abrev, suf)
            indices[ix_nome] = OrderedDict([
                ('nome', ix_nome),
                ('sufixo', suf),
                ('colunas', ix_def['colunas']),
                ('expr', ix_def.get('expr')),
                ('fbi', ix_def.get('fbi', False)),
                ('unico', ix_def.get('unico', False)),
            ])

        info = OrderedDict([
            ('entidade', entidade),
            ('abrev', abrev),
            ('rotulo', defn.get('rotulo', entidade)),
            ('tabela', tabela_nome),
            ('sequence', seq_nome),
            ('trigger', tr_bi_nome),
            ('trigger_bi', tr_bi_nome),
            ('trigger_bu', tr_bu_nome),
            ('pk', pk_nome),
            ('uks', uks),
            ('fks', fks),
            ('cks', cks),
            ('indices', indices),
            ('colunas', defn.get('colunas', OrderedDict())),
            ('colunas_lob', defn.get('colunas_lob', ())),
            ('trigger_extra', defn.get('trigger_bu')),
        ])
        resultado[entidade] = info

    return resultado


def todos_identificadores(prefixo, tabelas=None, incluir_colunas=True):
    """Retorna conjunto de todos os identificadores expandidos para o prefixo informado."""
    esquema = nomes(prefixo, tabelas=tabelas)
    return esquema.todos_identificadores(incluir_colunas=incluir_colunas)


def validar_registro(prefixo, tabelas=None):
    """Valida se todos os identificadores respeitam as restricoes do Oracle 11gR2.

    Garante:
      1. len <= 30 para todo identificador expandido (tabela, sequence, trigger, PK, UK, FK, CK, indice, coluna).
      2. Todos em ASCII lowercase casando com ^[a-z][a-z0-9_]*$.

    Lanca ValueError detalhando o identificador e tipo em caso de violacao.
    """
    validar_prefixo(prefixo)
    registro = TABELAS if tabelas is None else tabelas
    esquema = nomes(prefixo, tabelas=registro)

    for entidade, t in esquema.items():
        # Tabelas, sequences, triggers, PK
        itens_principais = [
            ("tabela", t['tabela']),
            ("sequence", t['sequence']),
            ("trigger_bi", t['trigger_bi']),
            ("pk", t['pk']),
        ]
        if t['trigger_bu']:
            itens_principais.append(("trigger_bu", t['trigger_bu']))

        for rotulo, ident in itens_principais:
            _checar_identificador(ident, rotulo, entidade)

        # UKs
        for uk_nome in t['uks']:
            _checar_identificador(uk_nome, "UK", entidade)

        # FKs
        for fk_nome in t['fks']:
            _checar_identificador(fk_nome, "FK", entidade)

        # CKs
        for ck_nome in t['cks']:
            _checar_identificador(ck_nome, "CK", entidade)

        # Indices
        for ix_nome in t['indices']:
            _checar_identificador(ix_nome, "Indice", entidade)

        # Colunas
        for col_nome in t['colunas']:
            _checar_identificador(col_nome, "Coluna", entidade)

    return True


def _checar_identificador(ident, tipo, entidade):
    """Verifica comprimento (<= 30) e formato ASCII minúsculo de um identificador."""
    if not isinstance(ident, str):
        raise ValueError(
            "Identificador do tipo {} na entidade '{}' nao e string: {}".format(
                tipo, entidade, _eco_seguro(ident)
            )
        )
    if len(ident) > 30:
        raise ValueError(
            "Identificador '{}' (tipo {}, entidade '{}') excede 30 caracteres (len={})".format(
                ident if len(ident) <= 64 else "<identificador excede 64 chars>",
                tipo,
                entidade,
                len(ident),
            )
        )
    if not _RE_IDENT_ASCII_LOWER.fullmatch(ident):
        raise ValueError(
            "Identificador '{}' (tipo {}, entidade '{}') nao atende ao padrao ASCII lowercase".format(
                ident if len(ident) <= 64 else "<identificador excede 64 chars>",
                tipo,
                entidade,
            )
        )


def normalizar_expressao(texto):
    """Normaliza expressoes SQL (CK, FBI, DATA_DEFAULT) para comparacao (CR-008, R-14).

    Regras:
      1. Remove aspas duplas (o Oracle devolve "STATUS", "PRIORIDADE").
      2. Converte para maiusculas fora de literais entre aspas simples.
      3. Colapsa sequencias de espacos, tabs e quebras de linha em um unico espaco.
      4. Remove espacos adjacentes a '(', ')' e ',' e operadores fora de literais.
      5. Remove espacos nas pontas (strip) e parenteses mais externos se envolverem a expressao inteira.
    """
    if texto is None:
        return ""
    if not isinstance(texto, str):
        texto = str(texto)

    # 1. Remove aspas duplas
    texto = texto.replace('"', '')

    # 2. Converte para maiusculas fora de literais entre aspas simples
    partes = []
    em_literal = False
    buffer = []
    i = 0
    n = len(texto)
    while i < n:
        c = texto[i]
        if c == "'":
            buffer.append(c)
            # Escape de aspas simples em SQL eh ''
            if em_literal and i + 1 < n and texto[i + 1] == "'":
                buffer.append(texto[i + 1])
                i += 2
                continue
            em_literal = not em_literal
            i += 1
        else:
            if em_literal:
                buffer.append(c)
            else:
                buffer.append(c.upper())
            i += 1

    texto_upper = "".join(buffer)

    # 3 e 4. Colapsa espacos e remove espacos ao redor de pontuacoes/operadores fora de literais
    tokens = []
    i = 0
    n = len(texto_upper)
    em_literal = False
    buf = []
    while i < n:
        c = texto_upper[i]
        if c == "'":
            if not em_literal:
                trecho = "".join(buf)
                trecho = re.sub(r"\s+", " ", trecho)
                trecho = re.sub(r"\s*([(),]|<=|>=|<>|=|<|>)\s*", r"\1", trecho)
                tokens.append(trecho)
                buf = [c]
                em_literal = True
                i += 1
            else:
                buf.append(c)
                if i + 1 < n and texto_upper[i + 1] == "'":
                    buf.append(texto_upper[i + 1])
                    i += 2
                    continue
                tokens.append("".join(buf))
                buf = []
                em_literal = False
                i += 1
        else:
            buf.append(c)
            i += 1

    if buf:
        trecho = "".join(buf)
        if not em_literal:
            trecho = re.sub(r"\s+", " ", trecho)
            trecho = re.sub(r"\s*([(),]|<=|>=|<>|=|<|>)\s*", r"\1", trecho)
        tokens.append(trecho)

    res = "".join(tokens).strip()

    # Desempacota parenteses externos se envolverem a expressao toda
    while res.startswith("(") and res.endswith(")"):
        nivel = 0
        fechou_antes = False
        for idx, ch in enumerate(res):
            if ch == "(":
                nivel += 1
            elif ch == ")":
                nivel -= 1
                if nivel == 0 and idx < len(res) - 1:
                    fechou_antes = True
                    break
        if not fechou_antes and nivel == 0:
            res = res[1:-1].strip()
        else:
            break

    return res


def eh_ck_not_null_sistema(nome_ck, condicao):
    """Indica se a CK eh uma constraint de sistema SYS_C% que apenas reforca NOT NULL."""
    if not nome_ck or not nome_ck.upper().startswith("SYS_C"):
        return False
    # Para checar se eh NOT NULL, normalizamos apenas tirando aspas e espacos externos
    c_limpa = condicao.replace('"', '').strip()
    return bool(re.fullmatch(r"^[A-Za-z0-9_]+\s+IS\s+NOT\s+NULL$", c_limpa, re.IGNORECASE))
