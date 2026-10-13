# SSS — Prompt F0.3: Registro de identificadores e testes de schema/compatibilidade

## Leitura obrigatória antes de planejar
- `AGENTS.md` §2.1, §3.1, §4 (inteiro), §7
- `README.md` §9 (inteiro), §10 (inteiro, as 16 tabelas)

## Objetivo
Criar a fonte única de verdade do modelo de dados (`sql_ident.py`), que será consumida mais tarde pelo `init_db.py`, pelo `repo_oracle` e pelos testes. Criar também as travas automáticas de 30 caracteres e de compatibilidade com Python 3.6.

## Escopo
**IN**
- `applications/script_scheduling_service/modules/sql_ident.py`:
  - **Registro declarativo** (`collections.OrderedDict`) das **16 tabelas** do README §10, cada uma com:
    - `entidade` e `abrev`;
    - colunas na ordem do README: nome, tipo Oracle literal (por exemplo, `VARCHAR2(30 CHAR)`), `NOT NULL`, `DEFAULT`;
    - PK;
    - UKs (nome e colunas);
    - FKs (nome, colunas, tabela e colunas referenciadas, `ON DELETE`);
    - CKs (nome e expressão literal do README);
    - índices (nome, colunas ou expressões; o FBI usa a expressão `CASE` literal do README);
    - triggers extras (`_bu`) com a coluna imutável;
    - colunas LOB.
  - **Geração de nomes** pelo template do README §9.1 a partir de `table_prefix`. A função `nomes(prefixo)` devolve todos os identificadores expandidos.
  - **Validação:** `validar_owner(s)`, `validar_prefixo(s)` e `qualificar(owner, nome)`, que valida e retorna `OWNER.NOME`. Valor inválido gera `ValueError`, sem eco do valor bruto se ele tiver mais de 64 caracteres.
  - O módulo **não** gera DDL (isso é o F7.1) e **não** importa driver nem `gluon`.
- `applications/script_scheduling_service/scripts/test_db_schema.py` (AGENTS §7.4). Testa:
  - todos os identificadores (tabelas, colunas, sequences, triggers, PK, UK, FK, CK, índices) com `len <= 30` usando o prefixo do `config.ini.example` **e** o prefixo `abcdefg_` (8 caracteres);
  - todos em ASCII, casando `^[a-z][a-z0-9_]*$`;
  - toda FK com um índice (ou UK/PK) cuja **coluna líder** seja a primeira coluna da FK;
  - toda tabela com sequence, trigger `_bi` e coluna `id NUMBER(10) NOT NULL`;
  - toda coluna `VARCHAR2` com `CHAR` explícito;
  - toda coluna de flag `CHAR(1)` com CK `IN ('S','N')`, exceto `status`/enum documentado;
  - 16 tabelas exatas, com nomes iguais aos do README §9.2.
- `applications/script_scheduling_service/scripts/test_py36_compat.py` (AGENTS §7.4):
  - percorre todos os `.py` de `APP` (exceto `dev/scripts/`) e de `bin/`;
  - compila com `ast.parse(src, feature_version=(3, 6))` quando o interpretador for >= 3.8; senão, com `compile()`;
  - procura tokens proibidos por regex (AGENTS §2.1 e §3.2), com lista de exceções **explícita** para o próprio arquivo de teste;
  - procura `http://` e `https://` em `applications/script_scheduling_service/static/js/app/`, `applications/script_scheduling_service/static/css/` e `applications/script_scheduling_service/views/`.

**OUT**
- Sem DDL, sem conexão e sem SQL de aplicação.

## Requisitos
1. O registro deve refletir **literalmente** o README §10. Qualquer divergência que você notar no README (nome, tipo, CK) **não** deve ser corrigida no código: liste-a em "Observações".
2. As expressões dos índices FBI ficam guardadas como string única. O F7.3 vai importá-las para garantir que as queries as repitam textualmente (AGENTS §4.8).

## Critérios de aceite
- [ ] `test_db_schema.py` e `test_py36_compat.py` passam.
- [ ] Um teste negativo prova a detecção: um registro temporário com nome de 31 caracteres, criado em memória dentro do teste, faz a checagem falhar.
- [ ] `nomes('tbsss_')` reproduz exatamente as tabelas de sequence/trigger/PK do README §9.2.

## Verificação
`python -m unittest discover -s scripts -p "test_db_schema.py"` e `... -p "test_py36_compat.py"`

## Regras de parada
Se faltar no README um nome de constraint ou índice que o template exija, **pare** e liste-o.

## Saída
Relatório AGENTS.md §9.
