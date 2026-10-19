# SSS — Explain Plan: Agregado CATALOGO (F7.3)

Consultas SQL estáticas do `RepoCatalogoOracle` (`modules/repo_oracle/catalogo.py`) no Oracle 11gR2, com o acesso esperado de cada uma.

> **Identificadores dinâmicos (README §9.1, §12.1):** `{owner}` vem de `[oracle] owner` e `{prefixo}` de `[oracle] table_prefix` (padrão `tbsss_`). Os dois são validados por `sql_ident` e qualificados **uma vez**, na criação do repositório. Todo valor entra por bind.
>
> **Escopo do critério "sem `TABLE ACCESS FULL`":** o critério vale para `{prefixo}tickets` e `{prefixo}auditoria` (AGENTS §4.12). O catálogo não lê nenhuma das duas, salvo a gravação da auditoria pela PK. As listagens de cadastro (ambientes, scripts e parâmetros) são tabelas pequenas, de administração. Nelas, `TABLE ACCESS FULL` com `COUNT STOPKEY` é aceitável e esperado.
>
> **Ordenação:** a ordem é `NLSSORT(<coluna>, 'NLS_SORT=BINARY')` seguida do desempate por `id`. Assim, a ordem fica igual à do FAKE (ordem de código Unicode do Python), seja qual for o `NLS_SORT` da sessão.

---

## 1. Listagens paginadas (AGENTS §4.4; CR-007, R-29)

O padrão é o mesmo nas três listagens: um `COUNT` que para em 10.001 e a página pela subquery de `ROWNUM`, na mesma conexão de leitura. Os filtros de trecho usam `LIKE … ESCAPE '\'`, com `%` e `_` escapados no bind; os de igualdade vêm de uma allowlist fixa.

### 1.1 `ambientes_listar`
```sql
SELECT COUNT(*) FROM (SELECT id FROM {owner}.{prefixo}ambientes
                       WHERE UPPER(nome) LIKE :nome_f ESCAPE '\' AND ativo = :ativo_f AND ROWNUM <= 10001);

SELECT * FROM (SELECT a.*, ROWNUM rn FROM (
  SELECT id, nome, descricao, conexao, ativo, created_at, created_by, updated_at, updated_by
    FROM {owner}.{prefixo}ambientes
   WHERE UPPER(nome) LIKE :nome_f ESCAPE '\' AND ativo = :ativo_f
   ORDER BY NLSSORT(nome, 'NLS_SORT=BINARY'), id
) a WHERE ROWNUM <= :fim) WHERE rn > :inicio
```
* **Esperado:** `COUNT STOPKEY` + `TABLE ACCESS FULL` em `{prefixo}ambientes` (tabela de cadastro); `SORT ORDER BY STOPKEY`.

### 1.2 `scripts_listar`
```sql
SELECT * FROM (SELECT a.*, ROWNUM rn FROM (
  SELECT s.id, s.nome, s.descricao, s.grupo, s.categoria, s.etapa, s.interpretador, s.path_file,
         s.tipo_param, s.max_qtd_parallel_env, s.timeout_seg, s.ativo, s.sha256_homologado,
         s.created_at, s.created_by, s.updated_at, s.updated_by,
         (SELECT COUNT(*) FROM {owner}.{prefixo}script_param sp WHERE sp.script_id = s.id) qtd_parametros
    FROM {owner}.{prefixo}scripts s
   WHERE LOWER(s.nome) LIKE :nome_f ESCAPE '\' AND s.grupo = :grupo_f   -- só os filtros informados
   ORDER BY NLSSORT(s.nome, 'NLS_SORT=BINARY'), s.id
) a WHERE ROWNUM <= :fim) WHERE rn > :inicio;

-- Ambientes homologados só da página (IN por contagem controlada, em lotes de até 500):
SELECT sa.script_id, a.nome
  FROM {owner}.{prefixo}script_amb sa JOIN {owner}.{prefixo}ambientes a ON a.id = sa.ambiente_id
 WHERE sa.script_id IN (:s0, :s1, ...)
```
* **Esperado:**
  * `qtd_parametros`: `INDEX RANGE SCAN` em `uk_{prefixo}sprm_scr_prm` (coluna líder `script_id`);
  * homologados: `INDEX RANGE SCAN` em `uk_{prefixo}samb_scr_amb` (líder `script_id`) e `INDEX UNIQUE SCAN` na PK de `{prefixo}ambientes`.
* **Sem `LISTAGG`:** de propósito. Com muitos ambientes, ele estouraria os 4.000 bytes (ORA-01489).

### 1.3 `parametros_listar`
```sql
SELECT p.id, p.codigo, ..., p.updated_by,
       (SELECT COUNT(*) FROM {owner}.{prefixo}script_param sp WHERE sp.parametro_id = p.id) qtd_scripts
  FROM {owner}.{prefixo}parametros p
 WHERE LOWER(p.codigo) LIKE :codigo_f ESCAPE '\'                        -- só os filtros informados
 ORDER BY NLSSORT(p.codigo, 'NLS_SORT=BINARY'), p.id                    -- dentro do padrão ROWNUM
```
* **Esperado:** `qtd_scripts` faz `INDEX RANGE SCAN` em `ix_{prefixo}sprm_prm` (`parametro_id`).

---

## 2. `scripts_executaveis` (README §4.3.A)

Uma única consulta. A matriz é lida pelo `perfil_id` do contexto, com `EXISTS` (decisão registrada no README §4.3.A).

```sql
-- Não administrador (o EXEC_SCRIPT é conferido antes, no contexto):
SELECT s.id, s.nome, ..., s.updated_by
  FROM {owner}.{prefixo}scripts s
 WHERE s.ativo = 'S'
   AND EXISTS (SELECT 1 FROM {owner}.{prefixo}perfil_scr ps
                WHERE ps.perfil_id = :perfil_id AND ps.script_id = s.id)
   AND EXISTS (SELECT 1 FROM {owner}.{prefixo}script_amb sa
                 JOIN {owner}.{prefixo}ambientes a ON a.id = sa.ambiente_id
                 JOIN {owner}.{prefixo}perfil_amb pa ON pa.ambiente_id = sa.ambiente_id AND pa.perfil_id = :perfil_id
                WHERE sa.script_id = s.id AND a.ativo = 'S')
 ORDER BY NLSSORT(s.nome, 'NLS_SORT=BINARY'), s.id

-- Administrador: dispensa perfil_scr/perfil_amb; não dispensa a homologação em ambiente ativo.
SELECT s.id, ... FROM {owner}.{prefixo}scripts s
 WHERE s.ativo = 'S'
   AND EXISTS (SELECT 1 FROM {owner}.{prefixo}script_amb sa JOIN {owner}.{prefixo}ambientes a ON a.id = sa.ambiente_id
                WHERE sa.script_id = s.id AND a.ativo = 'S')
 ORDER BY NLSSORT(s.nome, 'NLS_SORT=BINARY'), s.id
```
* **Esperado:**
  * o `EXISTS` vira semi-join (`NESTED LOOPS SEMI` ou `HASH JOIN SEMI`);
  * `perfil_scr` e `perfil_amb` por `INDEX RANGE SCAN` nas UKs de líder `perfil_id`;
  * `script_amb` por `uk_{prefixo}samb_scr_amb` (líder `script_id`).

---

## 3. Transições e gravações

Toda gravação roda numa só transação (`db_conn.transacao`), com o `id` obtido por `seq.NEXTVAL` (`db_conn.proximo_id`) antes do `INSERT`.

| Operação | Lock | DML | Acesso esperado |
|---|---|---|---|
| `ambientes_alterar` | `SELECT … FROM {prefixo}ambientes WHERE id = :id FOR UPDATE WAIT 5` | `UPDATE … SET descricao, conexao, ativo, updated_at = SYSDATE, updated_by = :ator WHERE id = :id` (`rowcount = 1` conferido) | `INDEX UNIQUE SCAN` na PK |
| `scripts_alterar` | `SELECT … FROM {prefixo}scripts WHERE id = :id FOR UPDATE WAIT 5`; ao trocar `tipo_param`, trava os parâmetros vinculados (`scripts → parametros`) | `UPDATE` de todas as colunas de negócio + `updated_*` pela PK | PK; UK do nome por `INDEX UNIQUE SCAN` (`nome = :nome AND id <> :id`, sem `UPPER`) |
| `homologacao_salvar` | `SELECT id FROM {prefixo}scripts WHERE id = :id FOR UPDATE WAIT 5` | `executemany DELETE … WHERE id = :id` (removidos), `executemany INSERT` (novos, `created_*`), `UPDATE {prefixo}scripts SET updated_*` se houve mudança | `uk_{prefixo}samb_scr_amb` (líder `script_id`) |
| `parametros_alterar` | `SELECT … FROM {prefixo}parametros WHERE id = :id FOR UPDATE WAIT 5` | `UPDATE` pela PK; dependências por `SELECT s.tipo_param, s.ativo FROM {prefixo}script_param sp JOIN {prefixo}scripts s …` | `ix_{prefixo}sprm_prm` + PK de scripts |
| `script_params_salvar` | script `FOR UPDATE WAIT 5`, depois cada parâmetro `FOR UPDATE WAIT 5` em ordem de `id` | `DELETE … WHERE script_id = :script_id` e `executemany INSERT`: novos com `SYSDATE`/ator; mantidos com o `created_*`/`updated_*` lidos (bind `TIPO_DATE`); alterados com o `created_*` lido e `updated_* = SYSDATE`/ator | `uk_{prefixo}sprm_scr_prm` (líder `script_id`) |

A ordem de locks é `{prefixo}scripts → {prefixo}parametros`. Ela nunca é invertida e não cruza com as ordens do README §8.3 (claim e desdobro): o catálogo não trava tickets nem agendamentos.

---

## 4. Avaliação de execução do plano

**Plano: TESTADO em 2026-10-19**, Oracle 19.24 (banco `GFPR`), owner `openrisow` em modo compartilhado (`SSS_TEST_SCHEMA_COMPARTILHADO=1`, README §2.5), driver Thin (python-oracledb 1.4.2). Os planos saíram de `EXPLAIN PLAN SET STATEMENT_ID … FOR <query>` + `DBMS_XPLAN.DISPLAY`, sem executar os comandos. O texto `{owner}` substitui `OPENRISOW`.

* **Sem `TABLE ACCESS FULL` em `tbsss_tickets` nem em `tbsss_auditoria`:** conforme: o agregado não lê essas tabelas.
* **`TABLE ACCESS FULL` aceitável:** aparece só no `COUNT` e na página das listagens de cadastro (`tbsss_ambientes`, `tbsss_scripts`, `tbsss_parametros`), com `COUNT STOPKEY`/`SORT ORDER BY STOPKEY`, e no ramo alternativo dos planos adaptativos (`STATISTICS COLLECTOR` + `HASH JOIN`), que o otimizador só usa se a cardinalidade real for maior.
* **Leituras por chave e transições:** lock e `UPDATE` pela PK (`INDEX UNIQUE SCAN`); UK do nome do script por `INDEX UNIQUE SCAN`; vínculos por `UK_…_SPRM_SCR_ORD`/`UK_…_SAMB_SCR_AMB` (líder `script_id`); `scripts_executaveis` com semi-join e `INDEX UNIQUE SCAN` em `UK_…_PSCR_PER_SCR` e `UK_…_PAMB_PER_AMB`. Nas consultas por `parametro_id`, o otimizador escolheu `INDEX SKIP SCAN` em `UK_…_SPRM_SCR_PRM`, por causa do volume pequeno de hoje; `IX_…_SPRM_PRM` continua disponível e é usado em `qtd_scripts`.

### Planos registrados

### ambientes_listar (nome, ativo) [1]
```text
 
--------------------------------------------------------
| Id  | Operation            | Name            | Rows  |
--------------------------------------------------------
|   0 | SELECT STATEMENT     |                 |     1 |
|   1 |  SORT AGGREGATE      |                 |     1 |
|   2 |   VIEW               |                 |     1 |
|   3 |    COUNT STOPKEY     |                 |       |
|   4 |     TABLE ACCESS FULL| TBSSS_AMBIENTES |     1 |
--------------------------------------------------------
```

### ambientes_listar (nome, ativo) [2]
```text
 
------------------------------------------------------------
| Id  | Operation                | Name            | Rows  |
------------------------------------------------------------
|   0 | SELECT STATEMENT         |                 |     1 |
|   1 |  VIEW                    |                 |     1 |
|   2 |   COUNT STOPKEY          |                 |       |
|   3 |    VIEW                  |                 |     1 |
|   4 |     SORT ORDER BY STOPKEY|                 |     1 |
|   5 |      TABLE ACCESS FULL   | TBSSS_AMBIENTES |     1 |
------------------------------------------------------------
```

### scripts_listar (nome, grupo) [1]
```text
 
------------------------------------------------------
| Id  | Operation            | Name          | Rows  |
------------------------------------------------------
|   0 | SELECT STATEMENT     |               |     1 |
|   1 |  SORT AGGREGATE      |               |     1 |
|   2 |   VIEW               |               |     1 |
|   3 |    COUNT STOPKEY     |               |       |
|   4 |     TABLE ACCESS FULL| TBSSS_SCRIPTS |     1 |
------------------------------------------------------
```

### scripts_listar (nome, grupo) [2]
```text
 
------------------------------------------------------------------
| Id  | Operation                | Name                  | Rows  |
------------------------------------------------------------------
|   0 | SELECT STATEMENT         |                       |     1 |
|   1 |  SORT AGGREGATE          |                       |     1 |
|   2 |   INDEX RANGE SCAN       | UK_TBSSS_SPRM_SCR_ORD |     3 |
|   3 |  VIEW                    |                       |     1 |
|   4 |   COUNT STOPKEY          |                       |       |
|   5 |    VIEW                  |                       |     1 |
|   6 |     SORT ORDER BY STOPKEY|                       |     1 |
|   7 |      TABLE ACCESS FULL   | TBSSS_SCRIPTS         |     1 |
------------------------------------------------------------------
```

### parametros_listar (codigo) [1]
```text
 
----------------------------------------------------------
| Id  | Operation          | Name                | Rows  |
----------------------------------------------------------
|   0 | SELECT STATEMENT   |                     |     1 |
|   1 |  SORT AGGREGATE    |                     |     1 |
|   2 |   VIEW             |                     |     1 |
|   3 |    COUNT STOPKEY   |                     |       |
|   4 |     INDEX FULL SCAN| UK_TBSSS_PRM_CODIGO |     1 |
----------------------------------------------------------
```

### parametros_listar (codigo) [2]
```text
 
--------------------------------------------------------------
| Id  | Operation                | Name              | Rows  |
--------------------------------------------------------------
|   0 | SELECT STATEMENT         |                   |     1 |
|   1 |  SORT AGGREGATE          |                   |     1 |
|   2 |   INDEX RANGE SCAN       | IX_TBSSS_SPRM_PRM |     2 |
|   3 |  VIEW                    |                   |     1 |
|   4 |   COUNT STOPKEY          |                   |       |
|   5 |    VIEW                  |                   |     1 |
|   6 |     SORT ORDER BY STOPKEY|                   |     1 |
|   7 |      TABLE ACCESS FULL   | TBSSS_PARAMETROS  |     1 |
--------------------------------------------------------------
```

### scripts_executaveis (perfil) [1]
```text
 
----------------------------------------------------------------------------
| Id  | Operation                          | Name                  | Rows  |
----------------------------------------------------------------------------
|   0 | SELECT STATEMENT                   |                       |    10 |
|   1 |  SORT ORDER BY                     |                       |    10 |
|   2 |   NESTED LOOPS SEMI                |                       |    10 |
|   3 |    MERGE JOIN SEMI                 |                       |    14 |
|   4 |     TABLE ACCESS BY INDEX ROWID    | TBSSS_SCRIPTS         |    14 |
|   5 |      INDEX FULL SCAN               | PK_TBSSS_SCRIPTS      |    14 |
|   6 |     SORT UNIQUE                    |                       |    57 |
|   7 |      VIEW                          | VW_SQ_1               |    57 |
|   8 |       NESTED LOOPS SEMI            |                       |    57 |
|   9 |        MERGE JOIN                  |                       |    63 |
|  10 |         TABLE ACCESS BY INDEX ROWID| TBSSS_AMBIENTES       |     5 |
|  11 |          INDEX FULL SCAN           | PK_TBSSS_AMBIENTES    |     5 |
|  12 |         SORT JOIN                  |                       |    70 |
|  13 |          INDEX FULL SCAN           | UK_TBSSS_SAMB_SCR_AMB |    70 |
|  14 |        INDEX UNIQUE SCAN           | UK_TBSSS_PAMB_PER_AMB |     5 |
|  15 |    INDEX UNIQUE SCAN               | UK_TBSSS_PSCR_PER_SCR |    10 |
----------------------------------------------------------------------------
```

### scripts_executaveis (admin) [1]
```text
 
--------------------------------------------------------------------------
| Id  | Operation                        | Name                  | Rows  |
--------------------------------------------------------------------------
|   0 | SELECT STATEMENT                 |                       |    14 |
|   1 |  SORT ORDER BY                   |                       |    14 |
|   2 |   MERGE JOIN SEMI                |                       |    14 |
|   3 |    TABLE ACCESS BY INDEX ROWID   | TBSSS_SCRIPTS         |    14 |
|   4 |     INDEX FULL SCAN              | PK_TBSSS_SCRIPTS      |    14 |
|   5 |    SORT UNIQUE                   |                       |    63 |
|   6 |     VIEW                         | VW_SQ_1               |    63 |
|   7 |      MERGE JOIN                  |                       |    63 |
|   8 |       TABLE ACCESS BY INDEX ROWID| TBSSS_AMBIENTES       |     5 |
|   9 |        INDEX FULL SCAN           | PK_TBSSS_AMBIENTES    |     5 |
|  10 |       SORT JOIN                  |                       |    70 |
|  11 |        INDEX FULL SCAN           | UK_TBSSS_SAMB_SCR_AMB |    70 |
--------------------------------------------------------------------------
```

### scripts_listar: homologados da pagina
```text
 
-------------------------------------------------------------------
| Id  | Operation                 | Name                  | Rows  |
-------------------------------------------------------------------
|   0 | SELECT STATEMENT          |                       |    10 |
|   1 |  HASH JOIN                |                       |    10 |
|   2 |   NESTED LOOPS            |                       |    10 |
|   3 |    STATISTICS COLLECTOR   |                       |       |
|   4 |     VIEW                  | index$_join$_002      |     5 |
|   5 |      HASH JOIN            |                       |       |
|   6 |       INDEX FAST FULL SCAN| PK_TBSSS_AMBIENTES    |     5 |
|   7 |       INDEX FAST FULL SCAN| UK_TBSSS_AMB_NOME     |     5 |
|   8 |    INLIST ITERATOR        |                       |       |
|   9 |     INDEX UNIQUE SCAN     | UK_TBSSS_SAMB_SCR_AMB |     2 |
|  10 |   INLIST ITERATOR         |                       |       |
|  11 |    INDEX RANGE SCAN       | UK_TBSSS_SAMB_SCR_AMB |    10 |
-------------------------------------------------------------------
```

### PRM_VINCULOS
```text
 
------------------------------------------------------------------------
| Id  | Operation                      | Name                  | Rows  |
------------------------------------------------------------------------
|   0 | SELECT STATEMENT               |                       |     2 |
|   1 |  SORT ORDER BY                 |                       |     2 |
|   2 |   HASH JOIN                    |                       |     2 |
|   3 |    NESTED LOOPS                |                       |     2 |
|   4 |     NESTED LOOPS               |                       |     2 |
|   5 |      STATISTICS COLLECTOR      |                       |       |
|   6 |       SORT UNIQUE              |                       |     2 |
|   7 |        INDEX SKIP SCAN         | UK_TBSSS_SPRM_SCR_PRM |     2 |
|   8 |      INDEX UNIQUE SCAN         | PK_TBSSS_SCRIPTS      |     1 |
|   9 |     TABLE ACCESS BY INDEX ROWID| TBSSS_SCRIPTS         |     1 |
|  10 |    TABLE ACCESS FULL           | TBSSS_SCRIPTS         |     1 |
------------------------------------------------------------------------
```

### SPRM_OBTER
```text
 
----------------------------------------------------------------------------------
| Id  | Operation                                | Name                  | Rows  |
----------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                       |     3 |
|   1 |  SORT ORDER BY                           |                       |     3 |
|   2 |   HASH JOIN                              |                       |     3 |
|   3 |    NESTED LOOPS                          |                       |     3 |
|   4 |     NESTED LOOPS                         |                       |     3 |
|   5 |      STATISTICS COLLECTOR                |                       |       |
|   6 |       TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_SCRIPT_PARAM    |     3 |
|   7 |        INDEX RANGE SCAN                  | UK_TBSSS_SPRM_SCR_ORD |     3 |
|   8 |      INDEX UNIQUE SCAN                   | PK_TBSSS_PARAMETROS   |     1 |
|   9 |     TABLE ACCESS BY INDEX ROWID          | TBSSS_PARAMETROS      |     1 |
|  10 |    TABLE ACCESS FULL                     | TBSSS_PARAMETROS      |     1 |
----------------------------------------------------------------------------------
```

### SPRM_DO_SCRIPT
```text
 
------------------------------------------------------------------------------
| Id  | Operation                            | Name                  | Rows  |
------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                     |                       |     3 |
|   1 |  SORT ORDER BY                       |                       |     3 |
|   2 |   TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_SCRIPT_PARAM    |     3 |
|   3 |    INDEX RANGE SCAN                  | UK_TBSSS_SPRM_SCR_ORD |     3 |
------------------------------------------------------------------------------
```

### SAMB_DO_SCRIPT
```text
 
-----------------------------------------------------------------------------
| Id  | Operation                           | Name                  | Rows  |
-----------------------------------------------------------------------------
|   0 | SELECT STATEMENT                    |                       |     5 |
|   1 |  TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_SCRIPT_AMB      |     5 |
|   2 |   INDEX RANGE SCAN                  | UK_TBSSS_SAMB_SCR_AMB |     5 |
-----------------------------------------------------------------------------
```

### PRM_SCRIPTS_VINCULADOS
```text
 
-----------------------------------------------------------------------
| Id  | Operation                     | Name                  | Rows  |
-----------------------------------------------------------------------
|   0 | SELECT STATEMENT              |                       |     2 |
|   1 |  HASH JOIN                    |                       |     2 |
|   2 |   NESTED LOOPS                |                       |     2 |
|   3 |    NESTED LOOPS               |                       |     2 |
|   4 |     STATISTICS COLLECTOR      |                       |       |
|   5 |      INDEX SKIP SCAN          | UK_TBSSS_SPRM_SCR_PRM |     2 |
|   6 |     INDEX UNIQUE SCAN         | PK_TBSSS_SCRIPTS      |     1 |
|   7 |    TABLE ACCESS BY INDEX ROWID| TBSSS_SCRIPTS         |     1 |
|   8 |   TABLE ACCESS FULL           | TBSSS_SCRIPTS         |     1 |
-----------------------------------------------------------------------
```

### SCR_NOME_EM_USO
```text
 
-----------------------------------------------------------------
| Id  | Operation                   | Name              | Rows  |
-----------------------------------------------------------------
|   0 | SELECT STATEMENT            |                   |     1 |
|   1 |  TABLE ACCESS BY INDEX ROWID| TBSSS_SCRIPTS     |     1 |
|   2 |   INDEX UNIQUE SCAN         | UK_TBSSS_SCR_NOME |     1 |
-----------------------------------------------------------------
```

### SCR_OBTER_LOCK
```text
 
-----------------------------------------------------------------
| Id  | Operation                    | Name             | Rows  |
-----------------------------------------------------------------
|   0 | SELECT STATEMENT             |                  |     1 |
|   1 |  FOR UPDATE                  |                  |       |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_SCRIPTS    |     1 |
|   3 |    INDEX UNIQUE SCAN         | PK_TBSSS_SCRIPTS |     1 |
-----------------------------------------------------------------
```

### AMB_OBTER_LOCK
```text
 
-------------------------------------------------------------------
| Id  | Operation                    | Name               | Rows  |
-------------------------------------------------------------------
|   0 | SELECT STATEMENT             |                    |     1 |
|   1 |  FOR UPDATE                  |                    |       |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_AMBIENTES    |     1 |
|   3 |    INDEX UNIQUE SCAN         | PK_TBSSS_AMBIENTES |     1 |
-------------------------------------------------------------------
```

### PRM_OBTER_LOCK
```text
 
--------------------------------------------------------------------
| Id  | Operation                    | Name                | Rows  |
--------------------------------------------------------------------
|   0 | SELECT STATEMENT             |                     |     1 |
|   1 |  FOR UPDATE                  |                     |       |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_PARAMETROS    |     1 |
|   3 |    INDEX UNIQUE SCAN         | PK_TBSSS_PARAMETROS |     1 |
--------------------------------------------------------------------
```

### SCR_CARIMBAR
```text
 
-------------------------------------------------------
| Id  | Operation          | Name             | Rows  |
-------------------------------------------------------
|   0 | UPDATE STATEMENT   |                  |     1 |
|   1 |  UPDATE            | TBSSS_SCRIPTS    |       |
|   2 |   INDEX UNIQUE SCAN| PK_TBSSS_SCRIPTS |     1 |
-------------------------------------------------------
```

### SPRM_EXCLUIR_DO_SCRIPT
```text
 
-----------------------------------------------------------
| Id  | Operation         | Name                  | Rows  |
-----------------------------------------------------------
|   0 | DELETE STATEMENT  |                       |     3 |
|   1 |  DELETE           | TBSSS_SCRIPT_PARAM    |       |
|   2 |   INDEX RANGE SCAN| UK_TBSSS_SPRM_SCR_ORD |     3 |
-----------------------------------------------------------
```
