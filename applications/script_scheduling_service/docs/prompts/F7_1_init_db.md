# SSS — Prompt F7.1: Bootstrap de DDL e seed (`init_db.py`)

## Leitura obrigatória antes de planejar
- `AGENTS.md` §4 (inteiro)
- `README.md` §9, §10 (inteiro), §11.1, §11.2, §4.3.D (seed de funcionalidades)
- Arquivo: `modules/sql_ident.py` (fonte única do modelo)

## Objetivo
Gerar e aplicar o DDL Oracle 11gR2 de forma idempotente e auditável, **a partir do registro `sql_ident`**, sem nenhum nome escrito à mão.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/ddl_builder.py`** (puro, sem driver), que gera as instruções a partir do registro, por fase (README §11.1):
  1. `CREATE SEQUENCE ... START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE`;
  2. `CREATE TABLE` com colunas, `DEFAULT` e `NOT NULL` (sem constraints nomeadas além do `NOT NULL`), com a cláusula LOB `SECUREFILE (CACHE)` ou `BASICFILE` conforme a opção;
  3. `ALTER TABLE ... ADD CONSTRAINT` para PK, UK e CK;
  4. `ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY ... [ON DELETE CASCADE|SET NULL]`;
  5. `CREATE INDEX`, incluindo os FBI com as expressões **literais** do registro. **Não** crie índice separado se a PK ou UK já cobre a coluna líder;
  6. triggers `_bi` no template literal do AGENTS §4.2 e triggers `_bu` de imutabilidade (`IF :NEW.<col> <> :OLD.<col> THEN RAISE_APPLICATION_ERROR(-20001, '<col> é imutável'); END IF;`).

  Cada instrução vem acompanhada do tipo e do nome do objeto, para a checagem de existência.
- **`applications/script_scheduling_service/scripts/init_db.py`** (CLI, `print` permitido), com as opções `--config`, `--dry-run`, `--lob-basicfile`, `--admin-login <login>`, `--admin-nome <nome>`, `--recreate` (só com `SSS_ENV=DEV` e confirmação digitada "RECRIAR <owner>") e `--stats` (padrão ligado):
  - **Checagem de existência** em `ALL_OBJECTS`, `ALL_CONSTRAINTS` e `ALL_INDEXES`, com `owner` e nome como **binds** (`UPPER`). O que já existe é marcado `SKIP`.
  - **Execução fase a fase:** o DDL faz commit implícito no Oracle. A primeira falha **aborta**, com fase, objeto, ORA- e o SQL (sem segredos) no log e código de saída 1.
  - **Seed via `MERGE`** (idempotente): o catálogo de funcionalidades do README §4.3.D e o perfil `ADMINISTRADOR` (`is_admin = 'S'`) com todas as funcionalidades.
  - **Administrador inicial:** criado só se `--admin-login` for informado e o login não existir. A senha vem de `SSS_BOOTSTRAP_ADMIN_PASSWORD` ou de `getpass` com confirmação, passa pela `validar_politica_senha` e é gravada com `hash_senha`. Nunca há senha em argumento de linha de comando.
  - **Estatísticas:** `DBMS_STATS.GATHER_TABLE_STATS(ownname => :o, tabname => :t, cascade => TRUE)` por tabela.
  - **Usuário de aplicação diferente do owner:** com `--grants-para <usuario>`, imprime (sem executar) os `GRANT SELECT, INSERT, UPDATE, DELETE` necessários e o `GRANT SELECT` nas sequences, para o DBA aplicar.
  - O `--dry-run` imprime **todo** o DDL, em ordem, e não conecta. Quando não houver config de banco, usa o `owner` e o prefixo do config.
- **`applications/script_scheduling_service/scripts/test_db_schema.py` (ampliar)** e **`applications/script_scheduling_service/scripts/test_ddl_builder.py`:**
  - o DDL gerado contém todos os nomes do registro;
  - nenhuma ocorrência de `IDENTITY`, `FETCH FIRST`, `OFFSET`, `JSON_` ou `VARCHAR2(n)` sem `CHAR`;
  - toda trigger `_bi` igual ao template literal;
  - a ordem das fases está correta (FK depois de PK/UK; índice FBI depois da tabela);
  - `--dry-run` executável sem driver.

**OUT**
- Sem DROP em HML/PROD e sem migração de versões futuras (fora do escopo).

## Requisitos
1. Valores sempre como binds. Identificadores apenas via `sql_ident.qualificar` (AGENTS §3.1).
2. O script é **reexecutável**: a segunda execução sobre a base pronta resulta em 100% `SKIP` e sem erro.
3. A conexão é feita via `oracle_conn`. Se o F7.2 ainda não existir, isole a conexão numa função `_conectar(cfg)` com import tardio. O F7.2 vai substituí-la e o relatório deve registrar essa dependência.

## Critérios de aceite
- [ ] `python scripts/init_db.py --dry-run` gera um DDL completo e revisável. Salve-o como `docs/ddl_gerado.sql`.
- [ ] Os testes passam.
- [ ] Com `SSS_TEST_DSN`: a primeira execução cria tudo e a segunda resulta em 100% SKIP. Sem `SSS_TEST_DSN`, o veredito dessa parte é `NÃO TESTADO`.

## Verificação
- `python scripts/init_db.py --dry-run > ../../docs/ddl_gerado.sql`
- `python -m unittest discover -s scripts -p "test_d*.py"`
- **Revisão humana sua (DBA):** leia o `docs/ddl_gerado.sql` antes de executar em qualquer base.

## Saída
Relatório AGENTS.md §9.
