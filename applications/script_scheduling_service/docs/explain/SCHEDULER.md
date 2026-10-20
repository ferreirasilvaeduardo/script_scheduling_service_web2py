# SSS — Explain Plan: repositório do daemon (F8.3a)

Consultas do `RepoSchedulerFila` (`modules/repo_oracle/scheduler_fila.py`) no Oracle 11gR2+.

> **Identificadores dinâmicos (README §9.1, §12.1):** `{owner}` vem de `[oracle] owner` e `{prefixo}` de `[oracle] table_prefix`, validados por `sql_ident` e qualificados uma vez, na criação do repositório. As listas `IN` (`:amb0..`, `:int0..`) são geradas por contagem e todo valor entra por bind.
>
> **Expressões dos índices de função:** `candidatos` usa as expressões de `ix_{prefixo}tck_fila` e `varredura_propria`/`tickets_running_do_agente` a de `ix_{prefixo}tck_run`, textualmente iguais às do `sql_ident` e sem alias de tabela (CR-007, R-32).

---

## 1. Consultas

| Método | Consulta | Acesso esperado |
|---|---|---|
| `candidatos` | `PENDING` vencidos dos ambientes ativos atendidos e dos interpretadores do agente, sem os pares no teto, pela prioridade efetiva (README §8.2; CR-007 R-07; CR-008 R-20), `ROWNUM <= :lote` | `ix_{prefixo}tck_fila` (só os `PENDING`); teto por `ix_{prefixo}tck_scr`; scripts pela PK |
| `claim` (3 passos) | `SELECT … FOR UPDATE WAIT 5` do script; contagem de `RUNNING` do par; `UPDATE … RETURNING started_at` (README §8.3) | `pk_{prefixo}scripts`; `ix_{prefixo}tck_scr`; `pk_{prefixo}tickets` |
| `varredura_propria`, `tickets_running_do_agente` | `(CASE WHEN status = 'RUNNING' THEN agente_id END) = :agente_id` (README §8.7) | `ix_{prefixo}tck_run` |
| `heartbeat` | `executemany` do `UPDATE` por PK dos tickets e `UPDATE` do agente por `codigo` | `pk_{prefixo}tickets`; `uk_{prefixo}agt_codigo` |
| `registrar_pid`, `finalizar`, `devolver` | `UPDATE` pela PK com `agente_id` e `status` | `pk_{prefixo}tickets` |

---

## 2. Avaliação de execução do plano

**Plano: TESTADO em 2026-10-20**, Oracle 19.24 (banco `GFPR`), owner `openrisow` em modo compartilhado (README §2.5), driver Thin, com `EXPLAIN PLAN SET STATEMENT_ID … FOR <query>` + `DBMS_XPLAN.DISPLAY` (sem executar os comandos). O texto `{owner}` substitui `OPENRISOW`.

* **Volume simulado:** `tbsss_tickets` e `tbsss_agentes` estão vazias depois do ciclo 02 → 01 → 99. Só durante o `EXPLAIN`, as estatísticas foram trocadas por valores fictícios (`DBMS_STATS.SET_TABLE_STATS`/`SET_COLUMN_STATS`/`SET_INDEX_STATS`): 1 milhão de tickets, 2.000 deles nos índices de função `tck_fila` e `tck_run` (inclusive as colunas ocultas `SYS_NC` desses índices), e 50 agentes. Em seguida, as estatísticas das duas tabelas foram apagadas e as dos índices recoletadas (nenhuma das duas é coletada pelo `01_implantar`). O estado antes e depois foi conferido e é idêntico; nenhuma linha foi gravada.
* **Sem `TABLE ACCESS FULL` em `tbsss_tickets` em nenhuma consulta:** conforme.
* **`candidatos`:** os tickets vêm só de `INDEX FULL SCAN` em `ix_{prefixo}tck_fila`, que contém apenas os `PENDING` (as linhas dos outros status têm a expressão nula e não entram no índice); o teto usa `INDEX RANGE SCAN` em `ix_{prefixo}tck_scr`. O `TABLE ACCESS FULL` em `tbsss_scripts` é o ramo alternativo do plano **adaptativo** do Oracle 12c+ (`STATISTICS COLLECTOR` escolhe em execução entre nested loops pela PK e hash join); ele incide só sobre o catálogo de scripts. No 11gR2 não há plano adaptativo.
* **Claim:** os três passos são por PK ou por `ix_{prefixo}tck_scr`; a ordem de locks é `tbsss_scripts` → `tbsss_tickets` (README §8.3).

### Planos registrados (com volume simulado)

### candidatos

```text
-------------------------------------------------------------------------
| Id  | Operation                                   | Name              |
-------------------------------------------------------------------------
|   0 | SELECT STATEMENT                            |                   |
|   1 |  COUNT STOPKEY                              |                   |
|   2 |   VIEW                                      |                   |
|   3 |    SORT ORDER BY STOPKEY                    |                   |
|   4 |     FILTER                                  |                   |
|   5 |      HASH JOIN                              |                   |
|   6 |       NESTED LOOPS                          |                   |
|   7 |        NESTED LOOPS                         |                   |
|   8 |         STATISTICS COLLECTOR                |                   |
|   9 |          TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_TICKETS     |
|  10 |           INDEX FULL SCAN                   | IX_TBSSS_TCK_FILA |
|  11 |         INDEX UNIQUE SCAN                   | PK_TBSSS_SCRIPTS  |
|  12 |        TABLE ACCESS BY INDEX ROWID          | TBSSS_SCRIPTS     |
|  13 |       TABLE ACCESS FULL                     | TBSSS_SCRIPTS     |
|  14 |      SORT AGGREGATE                         |                   |
|  15 |       INDEX RANGE SCAN                      | IX_TBSSS_TCK_SCR  |
-------------------------------------------------------------------------
```

### claim_1_script_for_update

```text
---------------------------------------------------------
| Id  | Operation                    | Name             |
---------------------------------------------------------
|   0 | SELECT STATEMENT             |                  |
|   1 |  FOR UPDATE                  |                  |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_SCRIPTS    |
|   3 |    INDEX UNIQUE SCAN         | PK_TBSSS_SCRIPTS |
---------------------------------------------------------
```

### claim_2_teto

```text
----------------------------------------------
| Id  | Operation         | Name             |
----------------------------------------------
|   0 | SELECT STATEMENT  |                  |
|   1 |  SORT AGGREGATE   |                  |
|   2 |   INDEX RANGE SCAN| IX_TBSSS_TCK_SCR |
----------------------------------------------
```

### claim_3_reserva

```text
---------------------------------------------------------
| Id  | Operation                    | Name             |
---------------------------------------------------------
|   0 | UPDATE STATEMENT             |                  |
|   1 |  UPDATE                      | TBSSS_TICKETS    |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_TICKETS    |
|   3 |    INDEX UNIQUE SCAN         | PK_TBSSS_TICKETS |
---------------------------------------------------------
```

### varredura_propria

```text
----------------------------------------------------------------
| Id  | Operation                           | Name             |
----------------------------------------------------------------
|   0 | SELECT STATEMENT                    |                  |
|   1 |  TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_TICKETS    |
|   2 |   INDEX RANGE SCAN                  | IX_TBSSS_TCK_RUN |
----------------------------------------------------------------
```

### heartbeat_ticket

```text
---------------------------------------------------------
| Id  | Operation                    | Name             |
---------------------------------------------------------
|   0 | UPDATE STATEMENT             |                  |
|   1 |  UPDATE                      | TBSSS_TICKETS    |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_TICKETS    |
|   3 |    INDEX UNIQUE SCAN         | PK_TBSSS_TICKETS |
---------------------------------------------------------
```

### heartbeat_agente

```text
------------------------------------------------------------
| Id  | Operation                    | Name                |
------------------------------------------------------------
|   0 | UPDATE STATEMENT             |                     |
|   1 |  UPDATE                      | TBSSS_AGENTES       |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_AGENTES       |
|   3 |    INDEX UNIQUE SCAN         | UK_TBSSS_AGT_CODIGO |
------------------------------------------------------------
```

### finalizar

```text
---------------------------------------------------------
| Id  | Operation                    | Name             |
---------------------------------------------------------
|   0 | UPDATE STATEMENT             |                  |
|   1 |  UPDATE                      | TBSSS_TICKETS    |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_TICKETS    |
|   3 |    INDEX UNIQUE SCAN         | PK_TBSSS_TICKETS |
---------------------------------------------------------
```
