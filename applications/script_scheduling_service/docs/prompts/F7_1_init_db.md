# SSS — Prompt F7.1: Bootstrap de DDL e seed (`init_db.py`)

## Leitura obrigatória antes de planejar
- `AGENTS.md` §4 (inteiro)
- `docs/arquitetura/CR-007-robustez-do-scheduler.md` (D1b: contas e GRANTs por papel; D4: versão do esquema e migrações; R-27: índice único da ocorrência; R-29: LOBs e estatísticas; R-32: `--recreate`)
- `docs/arquitetura/CR-006-colunas-de-registro.md` (R-a: colunas de registro e CKs `_upd`; R-b: atores `SYSTEM:init_db`)
- `docs/arquitetura/CR-003-correcoes-pos-analise.md` (D5 e C4: colunas e CKs novas, `table_prefix`, CRITICAL em configuração inválida; a D16, várias pastas base, foi revogada pelo CR-005)
- `README.md` §9, §10 (inteiro; em especial as tabelas 6 `tbsss_scripts`, 9 `tbsss_usuarios`, 15 `tbsss_agentes` e 16 `tbsss_auditoria`), §11.1, §11.2, §4.3.D (seed de funcionalidades), §8.5 ("CKs de banco"), §12.1 (tabela de faixas e "Falha de configuração"), §13
- Arquivos: `modules/sql_ident.py` (fonte única do modelo; já contém as colunas e CKs do CR-003), `modules/sss_config.py` (`obter_config`/`carregar`, regex de `owner` e `table_prefix`)

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

  **Modelo do CR-007 (já no registro `sql_ident`):** a 17ª tabela `tbsss_controle` (linha única, `ck_tbsss_ctl_id (id = 1)`, sem colunas de registro); `tbsss_scripts.sha256_homologado` e `tbsss_tickets.arquivo_sha256` com as CKs `_sha`; `tbsss_agentes.config_criticos`, `hostname VARCHAR2(255 CHAR)` e `ambientes VARCHAR2(1000 CHAR)`; `tbsss_tickets.process_id NUMBER(10)`; `ix_tbsss_agd_prox (ativo, proxima_execucao, id)`; `ix_tbsss_tck_hist (script_id, created_at)`; o índice **único** baseado em função `ix_tbsss_tck_ocor` (o registro marca `unico`, e o DDL usa `CREATE UNIQUE INDEX`); `ERRO_INTERNO` na `ck_tbsss_agd_pausa`. Cláusula LOB explícita para **todos** os CLOBs, inclusive `tbsss_agendamentos.parametros_json` (README §10).

  Cada instrução vem acompanhada do tipo e do nome do objeto, para a checagem de existência.

  **Modelo do CR-005 (já no registro `sql_ident`; gerar a partir dele, nunca escrever à mão):**
  - `tbsss_scripts.path_file VARCHAR2(500 CHAR) NOT NULL` (caminho absoluto livre, README §8.5 e §10 tabela 6; sem `pasta_base`);
  - `ck_tbsss_scr_path` (CR-005, R-g): `SUBSTR(path_file, 1, 1) = '/' AND INSTR(path_file, '..') = 0 AND INSTR(path_file, '//') = 0 AND INSTR(path_file, '\') = 0`. A barra invertida sai **literal** no DDL (`'\'`, um único caractere; no Oracle, `\` não é caractere de escape);
  - `tbsss_agentes`: sem `pastas_base`; `plataforma` com `ck_tbsss_agt_plat (plataforma IS NULL OR plataforma IN ('LINUX','UNIX'))` (CR-005, R-h);
  - `tbsss_usuarios.tentativas_falha NUMBER(2)` (por isso `login_max_tentativas` vai de 1 a 99, README §12.1).

  **Modelo do CR-006 (já no registro `sql_ident`):** as tabelas, exceto `tbsss_auditoria` e `tbsss_controle` (CR-007), terminam com `created_at DATE DEFAULT SYSDATE NOT NULL`, `created_by VARCHAR2(40 CHAR) NOT NULL` (sem `DEFAULT`), `updated_at DATE` e `updated_by VARCHAR2(40 CHAR)`, e têm a CK `ck_<prefixo><abrev>_upd` (`updated_at` e `updated_by` nulos juntos ou preenchidos juntos). Sem FK nem índice nessas colunas (README §10, "Colunas de registro").

  O banco ainda não existe, então não há migração (CR-003, "Modelo de dados"): as colunas entram no `CREATE TABLE` e as CKs na fase 3.
- **`applications/script_scheduling_service/scripts/init_db.py`** (CLI, `print` permitido), com as opções `--config`, `--dry-run`, `--lob-basicfile`, `--admin-login <login>`, `--admin-nome <nome>`, `--recreate` (só com `SSS_ENV=DEV` e confirmação digitada "RECRIAR <owner>") e `--stats` (padrão ligado). **`--recreate` (CR-007, R-32):** exige `[app] sss_env = DEV` **e** `SSS_ENV=DEV`, a confirmação digitada e nenhuma linha em `tbsss_tickets` nem `tbsss_agentes`. **Códigos de saída:** 0 sucesso, 1 falha de fase, 2 configuração inválida, 3 divergência de esquema ou versão:
  - **Checagem de existência** em `ALL_OBJECTS`, `ALL_CONSTRAINTS` e `ALL_INDEXES`, com `owner` e nome como **binds** (`UPPER`). O que já existe é marcado `SKIP`.
  - **Execução fase a fase:** o DDL faz commit implícito no Oracle. A primeira falha **aborta**, com fase, objeto, ORA- e o SQL (sem segredos) no log e código de saída 1.
  - **Conexão como dono do esquema (CR-007, D1b):** `--usuario-dono` (padrão o `owner`), senha por `getpass` ou `SSS_INIT_DB_PASSWORD`, nunca de arquivo nem argumento (README §11.1).
  - **Versão do esquema e migrações (CR-007, D4, README §11.1):** base vazia grava `tbsss_controle` com `sql_ident.VERSAO_ESQUEMA`; base com versão menor aplica, em ordem, as migrações de `scripts/migracoes/m<NNNN>_<descricao>.py` (crie a pasta com um `__init__.py` e o contrato `VERSAO` + `aplicar(conn, nomes, log)`; ainda não há migração, porque esta é a versão 1), auditando `ESQUEMA_MIGRAR`; versão maior que a do código aborta com código 3.
  - **Conferência do esquema real contra o registro, depois das fases:** `ALL_TAB_COLUMNS` (tipo, tamanho, `NULLABLE`, `DATA_DEFAULT`), `SEARCH_CONDITION` das CKs, colunas e expressões dos índices e objetos inválidos (`ALL_OBJECTS.STATUS = 'INVALID'` e `ALL_ERRORS`; no modo Thin, "sucesso com erro de compilação" é só aviso e precisa desta conferência). Divergência aborta com a lista e código 3; nunca corrige sozinho.
  - **Seed via `MERGE`** (idempotente): o catálogo de funcionalidades do README §4.3.D e o perfil `ADMINISTRADOR` (`is_admin = 'S'`) com todas as funcionalidades. Ator `SYSTEM:init_db` (CR-006): `WHEN NOT MATCHED` grava `created_at = SYSDATE` e `created_by = 'SYSTEM:init_db'`; `WHEN MATCHED` só atualiza a linha que difere do seed (cláusula `WHERE` do `UPDATE` do `MERGE`), gravando `updated_at = SYSDATE` e `updated_by = 'SYSTEM:init_db'`. Uma linha igual ao seed não é tocada, então a segunda execução não muda `updated_*`.
  - **Administrador inicial:** criado só se `--admin-login` for informado e o login não existir, com `created_by = 'SYSTEM:init_db'`. A senha vem de `SSS_BOOTSTRAP_ADMIN_PASSWORD` ou de `getpass` com confirmação, passa pela `validar_politica_senha` e é gravada com `hash_senha`. Nunca há senha em argumento de linha de comando.
  - **Estatísticas:** `DBMS_STATS.GATHER_TABLE_STATS(ownname => :o, tabname => :t, cascade => TRUE)` só em tabela com linhas (CR-007, R-29: estatística de tabela vazia fixa planos ruins); o relatório lembra o job automático de estatísticas.
  - **GRANTs por papel (CR-007, D1b):** `--grants-para web=<usuario>,agente=<usuario>,purge=<usuario>` imprime (sem executar) os GRANTs da tabela do README §11.1, objeto a objeto, para o DBA aplicar. Nenhum papel de aplicação recebe `UPDATE` ou `DELETE` em `tbsss_auditoria`.
  - O `--dry-run` imprime **todo** o DDL, em ordem, e não conecta. Quando não houver config de banco, usa o `owner` e o prefixo do config.
  - **Configuração:** o `owner` segue `^[A-Za-z][A-Za-z0-9_]{0,29}$` e o `table_prefix` segue `^[A-Za-z][A-Za-z0-9_]{0,7}$` (começa com letra, até 8 caracteres; README §12.1, D5), validados por `sss_config`/`sql_ident` antes de gerar qualquer DDL. Configuração inválida aborta com um registro **CRITICAL** com a seção, a chave e o motivo (nunca o valor de um segredo), no formato do README §13, e código de saída diferente de zero, como na "Falha de configuração" do §12.1 (reaproveite o caminho de `sss_config.obter_config(nome_log=...)`; sem `log_dir` utilizável, o CRITICAL vai para o stderr). O `--dry-run` também aborta. O log do CLI segue o README §13, com `<nome_log>` `init_db`: `log_dir/app/AAAA/MM/DD/HH/MI/init_db_<PID>.log`, via `sss_logging.configurar('init_db', cfg)`.
- **`applications/script_scheduling_service/scripts/test_db_schema.py` (ampliar)** e **`applications/script_scheduling_service/scripts/test_ddl_builder.py`:**
  - o DDL gerado contém todos os nomes do registro;
  - nenhuma ocorrência de `IDENTITY`, `FETCH FIRST`, `OFFSET`, `JSON_` ou `VARCHAR2(n)` sem `CHAR`;
  - toda trigger `_bi` igual ao template literal;
  - a ordem das fases está correta (FK depois de PK/UK; índice FBI depois da tabela);
  - **CR-005:** o DDL contém `path_file VARCHAR2(500 CHAR) NOT NULL` em `tbsss_scripts`, a `ck_tbsss_scr_path` absoluta (R-g) e `ck_tbsss_agt_plat` (R-h) em `tbsss_agentes` (sem `pasta_base` nem `pastas_base`);
  - **CR-006:** as tabelas (todas menos `tbsss_auditoria` e `tbsss_controle`) têm as quatro colunas de registro e a `ck_..._upd`; `created_by` sai sem `DEFAULT`; o seed gerado usa `SYSTEM:init_db`;
  - `table_prefix` começando por dígito ou com mais de 8 caracteres é recusado antes de gerar DDL, com CRITICAL (`assertLogs`);
  - `--dry-run` executável sem driver;
  - **CR-007:** o DDL contém `tbsss_controle` com as duas CKs e a linha de seed; `CREATE UNIQUE INDEX` para `ix_tbsss_tck_ocor`; as CKs `_sha`; a cláusula LOB de `parametros_json`; os GRANTs gerados por papel não dão `UPDATE`/`DELETE` em `tbsss_auditoria` a web nem agente; a conferência de esquema detecta coluna faltando, tamanho divergente, CK com texto diferente e trigger inválida (com conexão mock).

**OUT**
- Sem DROP em HML/PROD e sem migração de versões futuras (fora do escopo).

## Requisitos
1. Valores sempre como binds. Identificadores apenas via `sql_ident.qualificar` (AGENTS §3.1).
2. O script é **reexecutável**: a segunda execução sobre a base pronta resulta em 100% `SKIP` e sem erro.
3. A conexão é feita via `db_conn`. Se o F7.2 ainda não existir, isole a conexão numa função `_conectar(cfg)` com import tardio. O F7.2 vai substituí-la e o relatório deve registrar essa dependência.

## Critérios de aceite
- [ ] `python scripts/init_db.py --dry-run` gera um DDL completo e revisável. Salve-o como `docs/ddl_gerado.sql`.
- [ ] Os testes passam.
- [ ] O `docs/ddl_gerado.sql` contém `path_file VARCHAR2(500 CHAR)` e as CKs `ck_tbsss_scr_path` absoluta e `ck_tbsss_agt_plat` (CR-005).
- [ ] O `docs/ddl_gerado.sql` contém as colunas de registro e as CKs `_upd` (CR-006); a segunda execução do seed não altera `updated_*`.
- [ ] O `docs/ddl_gerado.sql` contém os objetos do CR-007 (`tbsss_controle`, índice único da ocorrência, CKs `_sha`, LOB de `parametros_json`); com `SSS_TEST_DSN`, a segunda execução sai com 0 e a conferência de esquema passa.
- [ ] Com `SSS_TEST_DSN`: a primeira execução cria tudo e a segunda resulta em 100% SKIP. Sem `SSS_TEST_DSN`, o veredito dessa parte é `NÃO TESTADO`.

## Verificação
- `python scripts/init_db.py --dry-run > ../../docs/ddl_gerado.sql`
- `python -m unittest discover -s scripts -p "test_d*.py"`
- **Revisão humana sua (DBA):** leia o `docs/ddl_gerado.sql` antes de executar em qualquer base.

## Saída
Relatório AGENTS.md §9.
