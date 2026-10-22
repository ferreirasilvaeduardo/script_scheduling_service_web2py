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
OWNER_PATTERN = r"^[A-Za-z][A-Za-z0-9_]{0,29}$"
PREFIX_PATTERN = r"^[a-z][a-z0-9_]{0,7}$"
IDENTIFIER_PATTERN = r"^[a-zA-Z][a-zA-Z0-9_]{0,29}$"
IDENT_ASCII_LOWER_PATTERN = r"^[a-z][a-z0-9_]*$"

_RE_OWNER = re.compile(OWNER_PATTERN)
_RE_PREFIXO = re.compile(PREFIX_PATTERN)
_RE_IDENT = re.compile(IDENTIFIER_PATTERN)
_RE_IDENT_ASCII_LOWER = re.compile(IDENT_ASCII_LOWER_PATTERN)

# Expressoes literais de indices baseados em funcao (FBI) - README §10.13 e AGENTS §4.8
# Fila (CR-013): colunas simples na frente e o inicio da espera, para a janela por ambiente e prioridade
# ler o indice ja na ordem da fila e parar no lote (INDEX RANGE SCAN sem sort, sem acesso a tabela).
# Com CASE em todas as colunas (indice so dos PENDING) o Oracle nunca elimina o sort (medido no GFPR 19c).
FBI_TCK_QUEUE_START = "GREATEST(scheduled_at, created_at)"
FBI_TCK_QUEUE_EXPR = "(status, environment, priority, " + FBI_TCK_QUEUE_START + ", id, script_id)"
FBI_TCK_RUN_EXPR = "((CASE WHEN status = 'RUNNING' THEN agent_id END))"

# Cláusulas CASE individuais para composicao identica em queries (README §10.13, AGENTS §4.8)
FBI_TCK_RUN_AGENT_CASE = "CASE WHEN status = 'RUNNING' THEN agent_id END"

# Saidas ainda em gravacao, por agente (CR-012): o startup check acha so as linhas GRAVANDO dele.
FBI_TOUT_WRITE_EXPR = "((CASE WHEN state = 'WRITING' THEN agent_id END))"
FBI_TOUT_WRITE_CASE = "CASE WHEN state = 'WRITING' THEN agent_id END"

# Indice unico da ocorrencia de agendamento (CR-007, R-27): so tickets de agendamento entram no indice.
FBI_TCK_OCCUR_EXPR = (
    "((CASE WHEN schedule_id IS NOT NULL THEN schedule_id END), "
    "(CASE WHEN schedule_id IS NOT NULL THEN scheduled_at END))"
)

# Versao do esquema que o codigo espera em tbsss_control (CR-007, D4). Toda mudanca de esquema a
# incrementa e traz a migracao scripts/migrations/m<NNNN>_*.py no mesmo pacote (AGENTS §4.16).
SCHEMA_VERSION = 1  # aberta ate a primeira producao (AGENTS §4.16): o CR-016a entra direto nela

# Colunas de registro (CR-006, README §10): todas as tabelas, exceto as listadas em TABELAS_SEM_REGISTRO.
RECORD_COLUMNS = ("created_at", "created_by", "updated_at", "updated_by")
TABLES_WITHOUT_RECORD = ("audit", "control")
ACTOR_MAX = 40
CK_RECORD_EXPR = (
    "(updated_at IS NULL AND updated_by IS NULL) OR "
    "(updated_at IS NOT NULL AND updated_by IS NOT NULL)"
)


def _safe_echo(value):
    """Retorna representacao segura do valor sem expor dados que excedam 64 caracteres."""
    if value is None:
        return "None"
    if not isinstance(value, str):
        return "tipo invalido ({})".format(type(value).__name__)
    if len(value) > 64:
        return "<valor com {} caracteres excede limite de 64>".format(len(value))
    return "'{}'".format(value)


def validate_owner(owner):
    """Valida o nome do owner/schema Oracle conforme AGENTS §3.1.

    Aceita ^[A-Za-z][A-Za-z0-9_]{0,29}$ com comprimento maximo de 30 caracteres.
    Lanca ValueError se invalido, sem ecoar o valor se tiver mais de 64 caracteres.
    """
    if not isinstance(owner, str) or not _RE_OWNER.fullmatch(owner):
        raise ValueError("Owner invalido: {}".format(_safe_echo(owner)))
    return owner


def validate_prefix(prefix):
    """Valida o prefixo de tabela conforme AGENTS §3.1.

    Aceita ^[A-Za-z][A-Za-z0-9_]{0,7}$: comeca com letra (nome Oracle valido), ate 8 caracteres.
    Lanca ValueError se invalido, sem ecoar o valor se tiver mais de 64 caracteres.
    """
    if not isinstance(prefix, str) or not _RE_PREFIXO.fullmatch(prefix):
        raise ValueError("Prefixo invalido: {}".format(_safe_echo(prefix)))
    return prefix


def validate_name(name, prefix=None):
    """Valida sintaxe e tamanho de um identificador Oracle (<= 30 caracteres).

    Se prefixo for informado, verifica tambem presenca no catalogo de identificadores.
    Lanca ValueError se invalido, sem ecoar o valor se tiver mais de 64 caracteres.
    """
    if not isinstance(name, str) or len(name) > 30 or not _RE_IDENT.fullmatch(name):
        raise ValueError("Nome de objeto invalido: {}".format(_safe_echo(name)))
    if prefix is not None:
        validate_prefix(prefix)
        catalog = all_identifiers(prefix)
        if name.lower() not in catalog:
            raise ValueError(
                "Nome de objeto nao registrado no catalogo: {}".format(_safe_echo(name))
            )
    return name


# Tabela de controle do esquema anterior ao CR-016a (nomes em portugues): o init_db recusa criar o novo com ela.
LEGACY_CONTROL_TABLE = "controle"


def physical(entity):
    """Nome fisico da tabela, sem o prefixo, da entidade logica (CR-016a; a chave logica muda no CR-016c)."""
    return TABLES[entity]['fisico']


def qualify(owner, name, prefix=None):
    """Valida e retorna OWNER.NOME qualificado para uso em SQL (AGENTS §3.1)."""
    v_owner = validate_owner(owner)
    v_name = validate_name(name, prefix=prefix)
    return "{}.{}".format(v_owner, v_name)


def table(owner, prefix, entity):
    """OWNER.<prefixo><nome fisico> da entidade logica, validado (CR-016a)."""
    return qualify(owner, prefix + physical(entity), prefix=prefix)


def sequence(owner, prefix, entity):
    """OWNER.sq_<prefixo><nome fisico> da entidade logica, validado (CR-016a)."""
    return qualify(owner, "sq_" + prefix + physical(entity), prefix=prefix)


# ---------------------------------------------------------------------------
# Registro Declarativo das 17 Tabelas (README §10)
# ---------------------------------------------------------------------------

def _build_table_registry():
    """Constroi o registro declarativo ordenado das 17 tabelas do SSS."""
    r = OrderedDict()

    # 1. Ambientes
    r['environments'] = OrderedDict([
        ('entity', 'environments'),
        ('fisico', 'environments'),
        ('abrev', 'env'),
        ('rotulo', 'Ambientes'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('name', {'name': 'name', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('description', {'name': 'description', 'tipo': 'VARCHAR2(100 CHAR)', 'not_null': False, 'default': None}),
            ('connection', {'name': 'connection', 'tipo': 'VARCHAR2(250 CHAR)', 'not_null': False, 'default': None}),
            ('active', {'name': 'active', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'Y'"}),
            ('created_at', {'name': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('name', {'sufixo': 'name', 'colunas': ('name',)}),
        ])),
        ('fks', OrderedDict()),
        ('cks', OrderedDict([
            ('active', {'sufixo': 'active', 'expr': "active IN ('Y', 'N')"}),
            ('name', {'sufixo': 'name', 'expr': "REGEXP_LIKE(name, '^[A-Z0-9_]{1,30}$')"}),
            ('connection', {'sufixo': 'connection', 'expr': "connection IS NULL OR INSTR(connection, '@') = 0"}),
        ])),
        ('indices', OrderedDict()),
        ('trigger_bu', {'sufixo': 'bu', 'coluna_imutavel': 'name'}),
        ('colunas_lob', ()),
    ])

    # 2. Perfis
    r['profiles'] = OrderedDict([
        ('entity', 'profiles'),
        ('fisico', 'profiles'),
        ('abrev', 'prf'),
        ('rotulo', 'Perfis'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('name', {'name': 'name', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('description', {'name': 'description', 'tipo': 'VARCHAR2(100 CHAR)', 'not_null': False, 'default': None}),
            ('is_admin', {'name': 'is_admin', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'N'"}),
            ('perm_version', {'name': 'perm_version', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': '1'}),
            ('active', {'name': 'active', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'Y'"}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('name', {'sufixo': 'name', 'colunas': ('name',)}),
        ])),
        ('fks', OrderedDict()),
        ('cks', OrderedDict([
            ('adm', {'sufixo': 'adm', 'expr': "is_admin IN ('Y', 'N')"}),
            ('active', {'sufixo': 'active', 'expr': "active IN ('Y', 'N')"}),
            ('version', {'sufixo': 'version', 'expr': "perm_version >= 1"}),
        ])),
        ('indices', OrderedDict()),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 3. Funcionalidades
    r['features'] = OrderedDict([
        ('entity', 'features'),
        ('fisico', 'features'),
        ('abrev', 'fea'),
        ('rotulo', 'Funcionalidades'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('code', {'name': 'code', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('name', {'name': 'name', 'tipo': 'VARCHAR2(60 CHAR)', 'not_null': True, 'default': None}),
            ('module', {'name': 'module', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('description', {'name': 'description', 'tipo': 'VARCHAR2(150 CHAR)', 'not_null': False, 'default': None}),
            ('active', {'name': 'active', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'Y'"}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('code', {'sufixo': 'code', 'colunas': ('code',)}),
        ])),
        ('fks', OrderedDict()),
        ('cks', OrderedDict([
            ('active', {'sufixo': 'active', 'expr': "active IN ('Y', 'N')"}),
        ])),
        ('indices', OrderedDict()),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 4. Perfil x Funcionalidade
    r['profile_feature'] = OrderedDict([
        ('entity', 'profile_feature'),
        ('fisico', 'profile_feature'),
        ('abrev', 'pfea'),
        ('rotulo', 'Perfil x Funcionalidade'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('profile_id', {'name': 'profile_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('feature_id', {'name': 'feature_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('prf_fea', {'sufixo': 'prf_fea', 'colunas': ('profile_id', 'feature_id')}),
        ])),
        ('fks', OrderedDict([
            ('prf', {'sufixo': 'prf', 'colunas': ('profile_id',), 'ref_tabela': 'profiles', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
            ('fea', {'sufixo': 'fea', 'colunas': ('feature_id',), 'ref_tabela': 'features', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
        ])),
        ('cks', OrderedDict()),
        ('indices', OrderedDict([
            ('fea', {'sufixo': 'fea', 'colunas': ('feature_id',), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 5. Perfil x Ambiente
    r['profile_env'] = OrderedDict([
        ('entity', 'profile_env'),
        ('fisico', 'profile_env'),
        ('abrev', 'penv'),
        ('rotulo', 'Perfil x Ambiente'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('profile_id', {'name': 'profile_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('environment_id', {'name': 'environment_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('prf_env', {'sufixo': 'prf_env', 'colunas': ('profile_id', 'environment_id')}),
        ])),
        ('fks', OrderedDict([
            ('prf', {'sufixo': 'prf', 'colunas': ('profile_id',), 'ref_tabela': 'profiles', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
            ('env', {'sufixo': 'env', 'colunas': ('environment_id',), 'ref_tabela': 'environments', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
        ])),
        ('cks', OrderedDict()),
        ('indices', OrderedDict([
            ('env', {'sufixo': 'env', 'colunas': ('environment_id',), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 6. Scripts
    r['scripts'] = OrderedDict([
        ('entity', 'scripts'),
        ('fisico', 'scripts'),
        ('abrev', 'scr'),
        ('rotulo', 'Scripts'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('name', {'name': 'name', 'tipo': 'VARCHAR2(60 CHAR)', 'not_null': True, 'default': None}),
            ('description', {'name': 'description', 'tipo': 'VARCHAR2(200 CHAR)', 'not_null': False, 'default': None}),
            ('script_group', {'name': 'script_group', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': False, 'default': None}),
            ('category', {'name': 'category', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': False, 'default': None}),
            ('stage', {'name': 'stage', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': False, 'default': None}),
            ('interpreter', {'name': 'interpreter', 'tipo': 'VARCHAR2(15 CHAR)', 'not_null': True, 'default': None}),
            ('path_file', {'name': 'path_file', 'tipo': 'VARCHAR2(500 CHAR)', 'not_null': True, 'default': None}),
            ('param_type', {'name': 'param_type', 'tipo': 'VARCHAR2(15 CHAR)', 'not_null': True, 'default': "'NAMED'"}),
            ('max_parallel_env', {'name': 'max_parallel_env', 'tipo': 'NUMBER(3)', 'not_null': True, 'default': '1'}),
            ('timeout_s', {'name': 'timeout_s', 'tipo': 'NUMBER(7)', 'not_null': False, 'default': None}),
            ('active', {'name': 'active', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'Y'"}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('name', {'sufixo': 'name', 'colunas': ('name',)}),
        ])),
        ('fks', OrderedDict()),
        ('cks', OrderedDict([
            ('ptype', {'sufixo': 'ptype', 'expr': "param_type IN ('NAMED','POSITIONAL','NONE')"}),
            ('active', {'sufixo': 'active', 'expr': "active IN ('Y', 'N')"}),
            ('paral', {'sufixo': 'paral', 'expr': "max_parallel_env BETWEEN 1 AND 999"}),
            ('int', {'sufixo': 'int', 'expr': "interpreter IN ('PYTHON3','BASH','SH')"}),
            ('path', {'sufixo': 'path', 'expr': "SUBSTR(path_file, 1, 1) = '/' AND INSTR(path_file, '..') = 0 AND INSTR(path_file, '//') = 0 AND INSTR(path_file, '\\') = 0"}),
            ('tmout', {'sufixo': 'tmout', 'expr': "timeout_s IS NULL OR timeout_s > 0"}),
        ])),
        ('indices', OrderedDict()),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 7. Perfil x Script
    r['profile_script'] = OrderedDict([
        ('entity', 'profile_script'),
        ('fisico', 'profile_script'),
        ('abrev', 'pscr'),
        ('rotulo', 'Perfil x Script'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('profile_id', {'name': 'profile_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('script_id', {'name': 'script_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('prf_scr', {'sufixo': 'prf_scr', 'colunas': ('profile_id', 'script_id')}),
        ])),
        ('fks', OrderedDict([
            ('prf', {'sufixo': 'prf', 'colunas': ('profile_id',), 'ref_tabela': 'profiles', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
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
    r['script_env'] = OrderedDict([
        ('entity', 'script_env'),
        ('fisico', 'script_env'),
        ('abrev', 'senv'),
        ('rotulo', 'Script x Ambiente'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('script_id', {'name': 'script_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('environment_id', {'name': 'environment_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('scr_env', {'sufixo': 'scr_env', 'colunas': ('script_id', 'environment_id')}),
        ])),
        ('fks', OrderedDict([
            ('scr', {'sufixo': 'scr', 'colunas': ('script_id',), 'ref_tabela': 'scripts', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
            ('env', {'sufixo': 'env', 'colunas': ('environment_id',), 'ref_tabela': 'environments', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
        ])),
        ('cks', OrderedDict()),
        ('indices', OrderedDict([
            ('env', {'sufixo': 'env', 'colunas': ('environment_id',), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 9. Usuarios
    r['users'] = OrderedDict([
        ('entity', 'users'),
        ('fisico', 'users'),
        ('abrev', 'usr'),
        ('rotulo', 'Usuários'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('login', {'name': 'login', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('name', {'name': 'name', 'tipo': 'VARCHAR2(60 CHAR)', 'not_null': True, 'default': None}),
            ('password_hash', {'name': 'password_hash', 'tipo': 'VARCHAR2(256 CHAR)', 'not_null': True, 'default': None}),
            ('profile_id', {'name': 'profile_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('failed_attempts', {'name': 'failed_attempts', 'tipo': 'NUMBER(2)', 'not_null': True, 'default': '0'}),
            ('locked_until', {'name': 'locked_until', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('last_login_at', {'name': 'last_login_at', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('password_changed_at', {'name': 'password_changed_at', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('session_epoch', {'name': 'session_epoch', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': '0'}),
            ('active', {'name': 'active', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'Y'"}),
            ('created_at', {'name': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('login', {'sufixo': 'login', 'colunas': ('login',)}),
        ])),
        ('fks', OrderedDict([
            ('prf', {'sufixo': 'prf', 'colunas': ('profile_id',), 'ref_tabela': 'profiles', 'ref_colunas': ('id',), 'on_delete': None}),
        ])),
        ('cks', OrderedDict([
            ('active', {'sufixo': 'active', 'expr': "active IN ('Y', 'N')"}),
            ('login', {'sufixo': 'login', 'expr': "REGEXP_LIKE(login, '^[a-z0-9._-]{3,30}$')"}),
            ('att', {'sufixo': 'att', 'expr': "failed_attempts >= 0"}),
            ('epoch', {'sufixo': 'epoch', 'expr': "session_epoch >= 0"}),
        ])),
        ('indices', OrderedDict([
            ('prf', {'sufixo': 'prf', 'colunas': ('profile_id',), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', {'sufixo': 'bu', 'coluna_imutavel': 'login'}),
        ('colunas_lob', ()),
    ])

    # 10. Parametros
    r['parameters'] = OrderedDict([
        ('entity', 'parameters'),
        ('fisico', 'parameters'),
        ('abrev', 'prm'),
        ('rotulo', 'Parâmetros'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('code', {'name': 'code', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('param_flag', {'name': 'param_flag', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': False, 'default': None}),
            ('label', {'name': 'label', 'tipo': 'VARCHAR2(60 CHAR)', 'not_null': True, 'default': None}),
            ('description', {'name': 'description', 'tipo': 'VARCHAR2(150 CHAR)', 'not_null': False, 'default': None}),
            ('component_type', {'name': 'component_type', 'tipo': 'VARCHAR2(20 CHAR)', 'not_null': True, 'default': None}),
            ('options_json', {'name': 'options_json', 'tipo': 'VARCHAR2(500 CHAR)', 'not_null': False, 'default': None}),
            ('default_value', {'name': 'default_value', 'tipo': 'VARCHAR2(100 CHAR)', 'not_null': False, 'default': None}),
            ('validation_regex', {'name': 'validation_regex', 'tipo': 'VARCHAR2(150 CHAR)', 'not_null': False, 'default': None}),
            ('sensitive', {'name': 'sensitive', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'N'"}),
            ('active', {'name': 'active', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'Y'"}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('code', {'sufixo': 'code', 'colunas': ('code',)}),
        ])),
        ('fks', OrderedDict()),
        ('cks', OrderedDict([
            ('ctype', {'sufixo': 'ctype', 'expr': "component_type IN ('TEXT','NUMBER','DATE','SELECT','CHECKBOX')"}),
            ('active', {'sufixo': 'active', 'expr': "active IN ('Y', 'N')"}),
            ('sens', {'sufixo': 'sens', 'expr': "sensitive IN ('Y','N')"}),
            ('code', {'sufixo': 'code', 'expr': "REGEXP_LIKE(code, '^[a-z0-9_]{1,30}$')"}),
            ('flag', {'sufixo': 'flag', 'expr': "param_flag IS NULL OR REGEXP_LIKE(param_flag, '^-{1,2}[A-Za-z0-9][A-Za-z0-9_-]{0,27}$')"}),
        ])),
        ('indices', OrderedDict()),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 11. Script x Parametro
    r['script_param'] = OrderedDict([
        ('entity', 'script_param'),
        ('fisico', 'script_param'),
        ('abrev', 'sprm'),
        ('rotulo', 'Script x Parâmetro'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('script_id', {'name': 'script_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('parameter_id', {'name': 'parameter_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('sort_order', {'name': 'sort_order', 'tipo': 'NUMBER(3)', 'not_null': True, 'default': None}),
            ('required', {'name': 'required', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'Y'"}),
            ('default_value_override', {'name': 'default_value_override', 'tipo': 'VARCHAR2(100 CHAR)', 'not_null': False, 'default': None}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('scr_prm', {'sufixo': 'scr_prm', 'colunas': ('script_id', 'parameter_id')}),
            ('scr_ord', {'sufixo': 'scr_ord', 'colunas': ('script_id', 'sort_order')}),
        ])),
        ('fks', OrderedDict([
            ('scr', {'sufixo': 'scr', 'colunas': ('script_id',), 'ref_tabela': 'scripts', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
            ('prm', {'sufixo': 'prm', 'colunas': ('parameter_id',), 'ref_tabela': 'parameters', 'ref_colunas': ('id',), 'on_delete': None}),
        ])),
        ('cks', OrderedDict([
            ('req', {'sufixo': 'req', 'expr': "required IN ('Y', 'N')"}),
            ('sort_order', {'sufixo': 'sort_order', 'expr': "sort_order >= 1"}),
        ])),
        ('indices', OrderedDict([
            ('prm', {'sufixo': 'prm', 'colunas': ('parameter_id',), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 12. Agendamentos
    r['schedules'] = OrderedDict([
        ('entity', 'schedules'),
        ('fisico', 'schedules'),
        ('abrev', 'sch'),
        ('rotulo', 'Agendamentos'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('name', {'name': 'name', 'tipo': 'VARCHAR2(60 CHAR)', 'not_null': True, 'default': None}),
            ('script_id', {'name': 'script_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('environment', {'name': 'environment', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('user_id', {'name': 'user_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('priority', {'name': 'priority', 'tipo': 'NUMBER(1)', 'not_null': True, 'default': '2'}),
            ('recurrence_type', {'name': 'recurrence_type', 'tipo': 'VARCHAR2(15 CHAR)', 'not_null': True, 'default': None}),
            ('cron_expression', {'name': 'cron_expression', 'tipo': 'VARCHAR2(60 CHAR)', 'not_null': False, 'default': None}),
            ('run_time', {'name': 'run_time', 'tipo': 'VARCHAR2(5 CHAR)', 'not_null': False, 'default': None}),
            ('week_days', {'name': 'week_days', 'tipo': 'VARCHAR2(20 CHAR)', 'not_null': False, 'default': None}),
            ('month_day', {'name': 'month_day', 'tipo': 'NUMBER(2)', 'not_null': False, 'default': None}),
            ('params_json', {'name': 'params_json', 'tipo': 'CLOB', 'not_null': False, 'default': None}),
            ('start_date', {'name': 'start_date', 'tipo': 'DATE', 'not_null': True, 'default': None}),
            ('end_date', {'name': 'end_date', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('next_run_at', {'name': 'next_run_at', 'tipo': 'DATE', 'not_null': True, 'default': None}),
            ('last_run_at', {'name': 'last_run_at', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('last_ticket_id', {'name': 'last_ticket_id', 'tipo': 'NUMBER(10)', 'not_null': False, 'default': None}),
            ('pause_reason', {'name': 'pause_reason', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': False, 'default': None}),
            ('active', {'name': 'active', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'Y'"}),
            ('created_at', {'name': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict()),
        ('fks', OrderedDict([
            ('scr', {'sufixo': 'scr', 'colunas': ('script_id',), 'ref_tabela': 'scripts', 'ref_colunas': ('id',), 'on_delete': None}),
            ('usr', {'sufixo': 'usr', 'colunas': ('user_id',), 'ref_tabela': 'users', 'ref_colunas': ('id',), 'on_delete': None}),
            ('env', {'sufixo': 'env', 'colunas': ('environment',), 'ref_tabela': 'environments', 'ref_colunas': ('name',), 'on_delete': None}),
        ])),
        ('cks', OrderedDict([
            ('rtype', {'sufixo': 'rtype', 'expr': "recurrence_type IN ('ONCE','DAILY','WEEKLY','MONTHLY','CRON')"}),
            ('prio', {'sufixo': 'prio', 'expr': "priority BETWEEN 1 AND 4"}),
            ('active', {'sufixo': 'active', 'expr': "active IN ('Y', 'N')"}),
            ('day', {'sufixo': 'day', 'expr': "month_day IS NULL OR month_day BETWEEN 1 AND 31"}),
            ('time', {'sufixo': 'time', 'expr': "run_time IS NULL OR REGEXP_LIKE(run_time, '^([01][0-9]|2[0-3]):[0-5][0-9]$')"}),
            ('wday', {'sufixo': 'wday', 'expr': "week_days IS NULL OR REGEXP_LIKE(week_days, '^[1-7](,[1-7]){0,6}$')"}),
            ('end', {'sufixo': 'end', 'expr': "end_date IS NULL OR end_date >= start_date"}),
            ('pause', {'sufixo': 'pause', 'expr': "pause_reason IS NULL OR pause_reason IN ('USER_INACTIVE','NO_PERMISSION','SCRIPT_INACTIVE','ENVIRONMENT_INACTIVE','INVALID_PARAM','INVALID_CRON','COMPLETED','MANUAL','INTERNAL_ERROR')"}),
            ('fields', {'sufixo': 'fields', 'expr': "(recurrence_type = 'ONCE') OR (recurrence_type = 'DAILY' AND run_time IS NOT NULL) OR (recurrence_type = 'WEEKLY' AND run_time IS NOT NULL AND week_days IS NOT NULL) OR (recurrence_type = 'MONTHLY' AND run_time IS NOT NULL AND month_day IS NOT NULL) OR (recurrence_type = 'CRON' AND cron_expression IS NOT NULL)"}),
        ])),
        ('indices', OrderedDict([
            ('scr', {'sufixo': 'scr', 'colunas': ('script_id',), 'expr': None, 'fbi': False}),
            ('usr', {'sufixo': 'usr', 'colunas': ('user_id',), 'expr': None, 'fbi': False}),
            ('env', {'sufixo': 'env', 'colunas': ('environment',), 'expr': None, 'fbi': False}),
            ('next', {'sufixo': 'next', 'colunas': ('active', 'next_run_at', 'id'), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ('params_json',)),
    ])

    # 13. Tickets
    r['tickets'] = OrderedDict([
        ('entity', 'tickets'),
        ('fisico', 'tickets'),
        ('abrev', 'tck'),
        ('rotulo', 'Tickets'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('script_id', {'name': 'script_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('environment', {'name': 'environment', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('requested_by', {'name': 'requested_by', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('source_ip', {'name': 'source_ip', 'tipo': 'VARCHAR2(45 CHAR)', 'not_null': False, 'default': None}),
            ('agent_id', {'name': 'agent_id', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': False, 'default': None}),
            ('process_id', {'name': 'process_id', 'tipo': 'NUMBER(10)', 'not_null': False, 'default': None}),
            ('process_start', {'name': 'process_start', 'tipo': 'NUMBER(20)', 'not_null': False, 'default': None}),
            ('status', {'name': 'status', 'tipo': 'VARCHAR2(15 CHAR)', 'not_null': True, 'default': "'PENDING'"}),
            ('priority', {'name': 'priority', 'tipo': 'NUMBER(1)', 'not_null': True, 'default': '2'}),
            ('cancel_requested', {'name': 'cancel_requested', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'N'"}),
            ('status_reason', {'name': 'status_reason', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': False, 'default': None}),
            ('parent_ticket_id', {'name': 'parent_ticket_id', 'tipo': 'NUMBER(10)', 'not_null': False, 'default': None}),
            ('schedule_id', {'name': 'schedule_id', 'tipo': 'NUMBER(10)', 'not_null': False, 'default': None}),
            ('submitted_params', {'name': 'submitted_params', 'tipo': 'CLOB', 'not_null': True, 'default': None}),
            ('log_output', {'name': 'log_output', 'tipo': 'CLOB', 'not_null': False, 'default': None}),
            ('log_offset_chars', {'name': 'log_offset_chars', 'tipo': 'NUMBER(20)', 'not_null': True, 'default': '0'}),
            ('log_truncated', {'name': 'log_truncated', 'tipo': 'CHAR(1)', 'not_null': True, 'default': "'N'"}),
            ('return_code', {'name': 'return_code', 'tipo': 'NUMBER(6)', 'not_null': False, 'default': None}),
            ('scheduled_at', {'name': 'scheduled_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
            ('started_at', {'name': 'started_at', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('heartbeat_at', {'name': 'heartbeat_at', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('finished_at', {'name': 'finished_at', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('created_at', {'name': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict()),
        ('fks', OrderedDict([
            ('scr', {'sufixo': 'scr', 'colunas': ('script_id',), 'ref_tabela': 'scripts', 'ref_colunas': ('id',), 'on_delete': None}),
            ('env', {'sufixo': 'env', 'colunas': ('environment',), 'ref_tabela': 'environments', 'ref_colunas': ('name',), 'on_delete': None}),
            ('usr', {'sufixo': 'usr', 'colunas': ('requested_by',), 'ref_tabela': 'users', 'ref_colunas': ('login',), 'on_delete': None}),
            ('parent', {'sufixo': 'parent', 'colunas': ('parent_ticket_id',), 'ref_tabela': 'tickets', 'ref_colunas': ('id',), 'on_delete': 'SET NULL'}),
            ('sch', {'sufixo': 'sch', 'colunas': ('schedule_id',), 'ref_tabela': 'schedules', 'ref_colunas': ('id',), 'on_delete': 'SET NULL'}),
        ])),
        ('cks', OrderedDict([
            ('stat', {'sufixo': 'stat', 'expr': "status IN ('PENDING','RUNNING','SUCCESS','FAILED','CANCELLED')"}),
            ('prio', {'sufixo': 'prio', 'expr': "priority BETWEEN 1 AND 4"}),
            ('cancreq', {'sufixo': 'cancreq', 'expr': "cancel_requested IN ('Y','N')"}),
            ('logtr', {'sufixo': 'logtr', 'expr': "log_truncated IN ('Y','N')"}),
            ('logoff', {'sufixo': 'logoff', 'expr': 'log_offset_chars >= 0'}),
            ('reason', {'sufixo': 'reason', 'expr': "status_reason IS NULL OR status_reason IN ('EXIT_OK','EXIT_ERROR','KILLED_SIGNAL','TIMEOUT','NODE_OFFLINE','ORPHAN_PROCESS','FENCED','PRECHECK_FAILED','SPAWN_ERROR','LOG_LIMIT','SHUTDOWN','CANCEL_USER')"}),
        ])),
        ('indices', OrderedDict([
            ('scr', {'sufixo': 'scr', 'colunas': ('script_id', 'environment', 'status'), 'expr': None, 'fbi': False}),
            ('env', {'sufixo': 'env', 'colunas': ('environment',), 'expr': None, 'fbi': False}),
            ('usr', {'sufixo': 'usr', 'colunas': ('requested_by',), 'expr': None, 'fbi': False}),
            ('par', {'sufixo': 'par', 'colunas': ('parent_ticket_id',), 'expr': None, 'fbi': False}),
            ('sch', {'sufixo': 'sch', 'colunas': ('schedule_id',), 'expr': None, 'fbi': False}),
            # (created_at, id): retencao e a ordem da lista de tickets (created_at DESC, id DESC) sem SORT
            # da tabela inteira (F7.3, EXPLAIN com volume).
            ('crt', {'sufixo': 'crt', 'colunas': ('created_at', 'id'), 'expr': None, 'fbi': False}),
            ('hist', {'sufixo': 'hist', 'colunas': ('script_id', 'created_at'), 'expr': None, 'fbi': False}),
            ('queue', {'sufixo': 'queue', 'colunas': (), 'expr': FBI_TCK_QUEUE_EXPR, 'fbi': True}),
            ('run', {'sufixo': 'run', 'colunas': (), 'expr': FBI_TCK_RUN_EXPR, 'fbi': True}),
            ('occur', {'sufixo': 'occur', 'colunas': (), 'expr': FBI_TCK_OCCUR_EXPR, 'fbi': True, 'unico': True}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ('submitted_params', 'log_output')),
    ])

    # 14. Ticket x Resposta
    r['ticket_answer'] = OrderedDict([
        ('entity', 'ticket_answer'),
        ('fisico', 'ticket_answer'),
        ('abrev', 'tans'),
        ('rotulo', 'Ticket x Resposta'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('ticket_id', {'name': 'ticket_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('parameter_id', {'name': 'parameter_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('answer_value', {'name': 'answer_value', 'tipo': 'VARCHAR2(500 CHAR)', 'not_null': False, 'default': None}),
            ('created_at', {'name': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('tck_prm', {'sufixo': 'tck_prm', 'colunas': ('ticket_id', 'parameter_id')}),
        ])),
        ('fks', OrderedDict([
            ('tck', {'sufixo': 'tck', 'colunas': ('ticket_id',), 'ref_tabela': 'tickets', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
            ('prm', {'sufixo': 'prm', 'colunas': ('parameter_id',), 'ref_tabela': 'parameters', 'ref_colunas': ('id',), 'on_delete': None}),
        ])),
        ('cks', OrderedDict()),
        ('indices', OrderedDict([
            ('prm', {'sufixo': 'prm', 'colunas': ('parameter_id',), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 15. Agentes
    r['agents'] = OrderedDict([
        ('entity', 'agents'),
        ('fisico', 'agents'),
        ('abrev', 'agt'),
        ('rotulo', 'Agentes'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('code', {'name': 'code', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('hostname', {'name': 'hostname', 'tipo': 'VARCHAR2(255 CHAR)', 'not_null': True, 'default': None}),
            ('daemon_pid', {'name': 'daemon_pid', 'tipo': 'NUMBER(10)', 'not_null': False, 'default': None}),
            ('version', {'name': 'version', 'tipo': 'VARCHAR2(20 CHAR)', 'not_null': False, 'default': None}),
            ('environments', {'name': 'environments', 'tipo': 'VARCHAR2(1000 CHAR)', 'not_null': False, 'default': None}),
            ('platform', {'name': 'platform', 'tipo': 'VARCHAR2(10 CHAR)', 'not_null': False, 'default': None}),
            ('interpreters', {'name': 'interpreters', 'tipo': 'VARCHAR2(100 CHAR)', 'not_null': False, 'default': None}),
            ('status', {'name': 'status', 'tipo': 'VARCHAR2(10 CHAR)', 'not_null': True, 'default': "'ACTIVE'"}),
            ('started_at', {'name': 'started_at', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('heartbeat_at', {'name': 'heartbeat_at', 'tipo': 'DATE', 'not_null': False, 'default': None}),
            ('critical_config', {'name': 'critical_config', 'tipo': 'VARCHAR2(400 CHAR)', 'not_null': False, 'default': None}),
            ('created_at', {'name': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('code', {'sufixo': 'code', 'colunas': ('code',)}),
        ])),
        ('fks', OrderedDict()),
        ('cks', OrderedDict([
            ('stat', {'sufixo': 'stat', 'expr': "status IN ('ACTIVE','STOPPED')"}),
            ('plat', {'sufixo': 'plat', 'expr': "platform IS NULL OR platform IN ('LINUX','UNIX')"}),
        ])),
        ('indices', OrderedDict()),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 16. Auditoria
    r['audit'] = OrderedDict([
        ('entity', 'audit'),
        ('fisico', 'audit'),
        ('abrev', 'aud'),
        ('rotulo', 'Auditoria'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('actor', {'name': 'actor', 'tipo': 'VARCHAR2(40 CHAR)', 'not_null': True, 'default': None}),
            ('source_ip', {'name': 'source_ip', 'tipo': 'VARCHAR2(45 CHAR)', 'not_null': False, 'default': None}),
            ('action', {'name': 'action', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('entity', {'name': 'entity', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('entity_id', {'name': 'entity_id', 'tipo': 'NUMBER(10)', 'not_null': False, 'default': None}),
            ('detail', {'name': 'detail', 'tipo': 'VARCHAR2(1000 CHAR)', 'not_null': False, 'default': None}),
            ('created_at', {'name': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict()),
        ('fks', OrderedDict()),
        ('cks', OrderedDict()),
        ('indices', OrderedDict([
            ('crt', {'sufixo': 'crt', 'colunas': ('created_at',), 'expr': None, 'fbi': False}),
            ('ent', {'sufixo': 'ent', 'colunas': ('entity', 'entity_id'), 'expr': None, 'fbi': False}),
            ('actor', {'sufixo': 'actor', 'colunas': ('actor',), 'expr': None, 'fbi': False}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 17. Controle (CR-007, D4): linha unica com a versao do esquema e a concessao do purge.
    r['control'] = OrderedDict([
        ('entity', 'control'),
        ('fisico', 'control'),
        ('abrev', 'ctl'),
        ('rotulo', 'Controle'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('schema_version', {'name': 'schema_version', 'tipo': 'NUMBER(6)', 'not_null': True, 'default': None}),
            ('version_applied_at', {'name': 'version_applied_at', 'tipo': 'DATE', 'not_null': True, 'default': None}),
            ('version_applied_by', {'name': 'version_applied_by', 'tipo': 'VARCHAR2(%d CHAR)' % ACTOR_MAX, 'not_null': True, 'default': None}),
            ('purge_owner', {'name': 'purge_owner', 'tipo': 'VARCHAR2(%d CHAR)' % ACTOR_MAX, 'not_null': False, 'default': None}),
            ('purge_lease_until', {'name': 'purge_lease_until', 'tipo': 'DATE', 'not_null': False, 'default': None}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict()),
        ('fks', OrderedDict()),
        ('cks', OrderedDict([
            ('id', {'sufixo': 'id', 'expr': "id = 1"}),
            ('version', {'sufixo': 'version', 'expr': "schema_version >= 1"}),
        ])),
        ('indices', OrderedDict()),
        ('trigger_bu', None),
        ('colunas_lob', ()),
    ])

    # 18. Saida do ticket (CR-012): zip da pasta de saida do script, uma linha por ticket.
    r['ticket_output'] = OrderedDict([
        ('entity', 'ticket_output'),
        ('fisico', 'ticket_output'),
        ('abrev', 'tout'),
        ('rotulo', 'Saida do ticket'),
        ('colunas', OrderedDict([
            ('id', {'name': 'id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('ticket_id', {'name': 'ticket_id', 'tipo': 'NUMBER(10)', 'not_null': True, 'default': None}),
            ('state', {'name': 'state', 'tipo': 'VARCHAR2(10 CHAR)', 'not_null': True, 'default': None}),
            ('reason', {'name': 'reason', 'tipo': 'VARCHAR2(10 CHAR)', 'not_null': False, 'default': None}),
            ('agent_id', {'name': 'agent_id', 'tipo': 'VARCHAR2(30 CHAR)', 'not_null': True, 'default': None}),
            ('file_count', {'name': 'file_count', 'tipo': 'NUMBER(10)', 'not_null': False, 'default': None}),
            ('size_bytes', {'name': 'size_bytes', 'tipo': 'NUMBER(12)', 'not_null': False, 'default': None}),
            ('content', {'name': 'content', 'tipo': 'BLOB', 'not_null': False, 'default': None}),
            ('created_at', {'name': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ])),
        ('pk', {'colunas': ('id',), 'sufixo': None}),
        ('uks', OrderedDict([
            ('tck', {'sufixo': 'tck', 'colunas': ('ticket_id',)}),
        ])),
        ('fks', OrderedDict([
            ('tck', {'sufixo': 'tck', 'colunas': ('ticket_id',), 'ref_tabela': 'tickets', 'ref_colunas': ('id',), 'on_delete': 'CASCADE'}),
        ])),
        ('cks', OrderedDict([
            ('state', {'sufixo': 'state', 'expr': "state IN ('WRITING','AVAILABLE','EXCEEDED','FAILED')"}),
            ('rsn', {'sufixo': 'rsn', 'expr': "reason IS NULL OR reason IN ('FILES','BYTES','DEADLINE','ERROR')"}),
            ('size', {'sufixo': 'size', 'expr': "(file_count IS NULL OR file_count >= 0) AND (size_bytes IS NULL OR size_bytes >= 0)"}),
        ])),
        ('indices', OrderedDict([
            ('write', {'sufixo': 'write', 'colunas': (), 'expr': FBI_TOUT_WRITE_EXPR, 'fbi': True}),
        ])),
        ('trigger_bu', None),
        ('colunas_lob', ('content',)),
    ])

    for entity, defn in r.items():
        if entity not in TABLES_WITHOUT_RECORD:
            _apply_record_columns(defn)

    return r


def _apply_record_columns(defn):
    """Acrescenta as colunas de registro que faltam e a CK _upd (CR-006, README §10).

    created_at ja existe no fim de algumas tabelas; as demais colunas entram depois dela.
    """
    columns = defn['colunas']
    new = OrderedDict([
        ('created_at', {'name': 'created_at', 'tipo': 'DATE', 'not_null': True, 'default': 'SYSDATE'}),
        ('created_by', {'name': 'created_by', 'tipo': 'VARCHAR2(%d CHAR)' % ACTOR_MAX, 'not_null': True, 'default': None}),
        ('updated_at', {'name': 'updated_at', 'tipo': 'DATE', 'not_null': False, 'default': None}),
        ('updated_by', {'name': 'updated_by', 'tipo': 'VARCHAR2(%d CHAR)' % ACTOR_MAX, 'not_null': False, 'default': None}),
    ])
    for name, column in new.items():
        if name not in columns:
            columns[name] = column
    defn['cks']['upd'] = {'sufixo': 'upd', 'expr': CK_RECORD_EXPR}


# Instancia imutavel de referencia do catalogo
TABLES = _build_table_registry()


class SchemaNames(OrderedDict):
    """Container ordenado dos identificadores expandidos para um prefixo.

    Permite indexacao por entidade (ex: n['tickets']) e oferece metodo para
    extracao plana de todos os identificadores gerados no esquema.
    """

    def all_identifiers(self, include_columns=True):
        """Retorna o conjunto (set) de todos os identificadores expandidos."""
        ids = set()
        for entity, t in self.items():
            ids.add(t['tabela'])
            ids.add(t['sequence'])
            ids.add(t['trigger_bi'])
            ids.add(t['trigger'])
            if t['trigger_bu']:
                ids.add(t['trigger_bu'])
            ids.add(t['pk'])
            for uk_name in t['uks']:
                ids.add(uk_name)
            for fk_name in t['fks']:
                ids.add(fk_name)
            for ck_name in t['cks']:
                ids.add(ck_name)
            for ix_name in t['indices']:
                ids.add(ix_name)
            if include_columns:
                for col_name in t['colunas']:
                    ids.add(col_name)
        return ids

    def list_identifiers(self, include_columns=True):
        """Retorna lista ordenada de todos os identificadores expandidos."""
        return sorted(self.all_identifiers(include_columns=include_columns))


def names(prefix, tables=None):
    """Gera e retorna todos os identificadores expandidos a partir de table_prefix.

    Segue as regras do template README §9.1:
      tabela      = {prefixo}{fisico}
      sequence    = sq_{prefixo}{fisico}
      trigger PK  = tr_{prefixo}{abrev}_bi
      trigger UPD = tr_{prefixo}{abrev}_bu
      PK          = pk_{prefixo}{fisico}
      UK/FK/CK/IX = {uk|fk|ck|ix}_{prefixo}{abrev}_{sufixo}
    """
    validate_prefix(prefix)
    record = TABLES if tables is None else tables

    result = SchemaNames()
    for entity, defn in record.items():
        abbr = defn['abrev']
        table_name = "{}{}".format(prefix, defn['fisico'])
        seq_name = "sq_{}{}".format(prefix, defn['fisico'])
        tr_bi_name = "tr_{}{}_bi".format(prefix, abbr)
        tr_bu_name = "tr_{}{}_bu".format(prefix, abbr) if defn.get('trigger_bu') else None
        pk_name = "pk_{}{}".format(prefix, defn['fisico'])

        uks = OrderedDict()
        for suffix_key, uk_def in defn.get('uks', {}).items():
            suf = uk_def['sufixo']
            uk_name = "uk_{}{}_{}".format(prefix, abbr, suf)
            uks[uk_name] = OrderedDict([
                ('name', uk_name),
                ('sufixo', suf),
                ('colunas', uk_def['colunas']),
            ])

        fks = OrderedDict()
        for suffix_key, fk_def in defn.get('fks', {}).items():
            suf = fk_def['sufixo']
            fk_name = "fk_{}{}_{}".format(prefix, abbr, suf)
            ref_table_name = "{}{}".format(prefix, record[fk_def['ref_tabela']]['fisico'])
            fks[fk_name] = OrderedDict([
                ('name', fk_name),
                ('sufixo', suf),
                ('colunas', fk_def['colunas']),
                ('ref_entidade', fk_def['ref_tabela']),
                ('ref_tabela', ref_table_name),
                ('ref_colunas', fk_def['ref_colunas']),
                ('on_delete', fk_def.get('on_delete')),
            ])

        cks = OrderedDict()
        for suffix_key, ck_def in defn.get('cks', {}).items():
            suf = ck_def['sufixo']
            ck_name = "ck_{}{}_{}".format(prefix, abbr, suf)
            cks[ck_name] = OrderedDict([
                ('name', ck_name),
                ('sufixo', suf),
                ('expr', ck_def['expr']),
            ])

        indexes = OrderedDict()
        for suffix_key, ix_def in defn.get('indices', {}).items():
            suf = ix_def['sufixo']
            ix_name = "ix_{}{}_{}".format(prefix, abbr, suf)
            indexes[ix_name] = OrderedDict([
                ('name', ix_name),
                ('sufixo', suf),
                ('colunas', ix_def['colunas']),
                ('expr', ix_def.get('expr')),
                ('fbi', ix_def.get('fbi', False)),
                ('unico', ix_def.get('unico', False)),
            ])

        info = OrderedDict([
            ('entity', entity),
            ('abrev', abbr),
            ('rotulo', defn.get('rotulo', entity)),
            ('tabela', table_name),
            ('sequence', seq_name),
            ('trigger', tr_bi_name),
            ('trigger_bi', tr_bi_name),
            ('trigger_bu', tr_bu_name),
            ('pk', pk_name),
            ('uks', uks),
            ('fks', fks),
            ('cks', cks),
            ('indices', indexes),
            ('colunas', defn.get('colunas', OrderedDict())),
            ('colunas_lob', defn.get('colunas_lob', ())),
            ('trigger_extra', defn.get('trigger_bu')),
        ])
        result[entity] = info

    return result


def all_identifiers(prefix, tables=None, include_columns=True):
    """Retorna conjunto de todos os identificadores expandidos para o prefixo informado."""
    schema = names(prefix, tables=tables)
    return schema.all_identifiers(include_columns=include_columns)


def validate_registry(prefix, tables=None):
    """Valida se todos os identificadores respeitam as restricoes do Oracle 11gR2.

    Garante:
      1. len <= 30 para todo identificador expandido (tabela, sequence, trigger, PK, UK, FK, CK, indice, coluna).
      2. Todos em ASCII lowercase casando com ^[a-z][a-z0-9_]*$.

    Lanca ValueError detalhando o identificador e tipo em caso de violacao.
    """
    validate_prefix(prefix)
    record = TABLES if tables is None else tables
    schema = names(prefix, tables=record)

    for entity, t in schema.items():
        # Tabelas, sequences, triggers, PK
        items_main = [
            ("tabela", t['tabela']),
            ("sequence", t['sequence']),
            ("trigger_bi", t['trigger_bi']),
            ("pk", t['pk']),
        ]
        if t['trigger_bu']:
            items_main.append(("trigger_bu", t['trigger_bu']))

        for label, ident in items_main:
            _check_identifier(ident, label, entity)

        # UKs
        for uk_name in t['uks']:
            _check_identifier(uk_name, "UK", entity)

        # FKs
        for fk_name in t['fks']:
            _check_identifier(fk_name, "FK", entity)

        # CKs
        for ck_name in t['cks']:
            _check_identifier(ck_name, "CK", entity)

        # Indices
        for ix_name in t['indices']:
            _check_identifier(ix_name, "Indice", entity)

        # Colunas
        for col_name in t['colunas']:
            _check_identifier(col_name, "Coluna", entity)

    return True


def _check_identifier(ident, kind, entity):
    """Verifica comprimento (<= 30) e formato ASCII minúsculo de um identificador."""
    if not isinstance(ident, str):
        raise ValueError(
            "Identificador do tipo {} na entidade '{}' nao e string: {}".format(
                kind, entity, _safe_echo(ident)
            )
        )
    if len(ident) > 30:
        raise ValueError(
            "Identificador '{}' (tipo {}, entidade '{}') excede 30 caracteres (len={})".format(
                ident if len(ident) <= 64 else "<identificador excede 64 chars>",
                kind,
                entity,
                len(ident),
            )
        )
    if not _RE_IDENT_ASCII_LOWER.fullmatch(ident):
        raise ValueError(
            "Identificador '{}' (tipo {}, entidade '{}') nao atende ao padrao ASCII lowercase".format(
                ident if len(ident) <= 64 else "<identificador excede 64 chars>",
                kind,
                entity,
            )
        )


def normalize_expression(text):
    """Normaliza expressoes SQL (CK, FBI, DATA_DEFAULT) para comparacao (CR-008, R-14).

    Regras:
      1. Remove aspas duplas (o Oracle devolve "STATUS", "PRIORITY").
      2. Converte para maiusculas fora de literais entre aspas simples.
      3. Colapsa sequencias de espacos, tabs e quebras de linha em um unico espaco.
      4. Remove espacos adjacentes a '(', ')' e ',' e operadores fora de literais.
      5. Remove espacos nas pontas (strip) e parenteses mais externos se envolverem a expressao inteira.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # 1. Remove aspas duplas
    text = text.replace('"', '')

    # 2. Converte para maiusculas fora de literais entre aspas simples
    parts = []
    in_literal = False
    buffer = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "'":
            buffer.append(c)
            # Escape de aspas simples em SQL eh ''
            if in_literal and i + 1 < n and text[i + 1] == "'":
                buffer.append(text[i + 1])
                i += 2
                continue
            in_literal = not in_literal
            i += 1
        else:
            if in_literal:
                buffer.append(c)
            else:
                buffer.append(c.upper())
            i += 1

    text_upper = "".join(buffer)

    # 3 e 4. Colapsa espacos e remove espacos ao redor de pontuacoes/operadores fora de literais
    tokens = []
    i = 0
    n = len(text_upper)
    in_literal = False
    buf = []
    while i < n:
        c = text_upper[i]
        if c == "'":
            if not in_literal:
                snippet = "".join(buf)
                snippet = re.sub(r"\s+", " ", snippet)
                snippet = re.sub(r"\s*([(),]|<=|>=|<>|=|<|>)\s*", r"\1", snippet)
                tokens.append(snippet)
                buf = [c]
                in_literal = True
                i += 1
            else:
                buf.append(c)
                if i + 1 < n and text_upper[i + 1] == "'":
                    buf.append(text_upper[i + 1])
                    i += 2
                    continue
                tokens.append("".join(buf))
                buf = []
                in_literal = False
                i += 1
        else:
            buf.append(c)
            i += 1

    if buf:
        snippet = "".join(buf)
        if not in_literal:
            snippet = re.sub(r"\s+", " ", snippet)
            snippet = re.sub(r"\s*([(),]|<=|>=|<>|=|<|>)\s*", r"\1", snippet)
        tokens.append(snippet)

    res = "".join(tokens).strip()

    # Desempacota parenteses externos se envolverem a expressao toda
    while res.startswith("(") and res.endswith(")"):
        level = 0
        closed_before = False
        for idx, ch in enumerate(res):
            if ch == "(":
                level += 1
            elif ch == ")":
                level -= 1
                if level == 0 and idx < len(res) - 1:
                    closed_before = True
                    break
        if not closed_before and level == 0:
            res = res[1:-1].strip()
        else:
            break

    return res


def is_system_not_null_ck(ck_name, condition):
    """Indica se a CK eh uma constraint de sistema SYS_C% que apenas reforca NOT NULL."""
    if not ck_name or not ck_name.upper().startswith("SYS_C"):
        return False
    # Para checar se eh NOT NULL, normalizamos apenas tirando aspas e espacos externos
    c_clean = condition.replace('"', '').strip()
    return bool(re.fullmatch(r"^[A-Za-z0-9_]+\s+IS\s+NOT\s+NULL$", c_clean, re.IGNORECASE))
