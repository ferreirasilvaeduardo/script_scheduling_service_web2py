# SSS — Explain Plan: repositório do daemon (F8.3a)

Consultas do `RepoSchedulerQueue` (`modules/repo_oracle/scheduler_queue.py`) no Oracle 11gR2+.

> **Identificadores dinâmicos (README §9.1, §12.1):** `{owner}` vem de `[oracle] owner` e `{prefixo}` de `[oracle] table_prefix`, validados por `sql_ident` e qualificados uma vez, na criação do repositório. As listas `IN` (`:amb0..`, `:int0..`) são geradas por contagem e todo valor entra por bind.
>
> **Índices:** `candidates` lê `ix_{prefixo}tck_queue (status, environment, priority, GREATEST(scheduled_at, created_at), id, script_id)` pela janela do CR-013 (README §8.2); `own_sweep`/`tickets_running_do_agente` a de `ix_{prefixo}tck_run`, textualmente iguais às do `sql_ident` e sem alias de tabela (CR-007, R-32).

---

## 1. Consultas

| Método | Consulta | Acesso esperado |
|---|---|---|
| `candidates` (CR-013) | (1) scripts do agente por interpretador; (2) `RUNNING` por script e ambiente; (3) janela: por ambiente e prioridade 1 a 4, os `:lote` primeiros de `PENDING` vencidos por `(inicio, id)` dos scripts abaixo do teto, juntados e ordenados pela prioridade efetiva (README §8.2) | (1) `{prefixo}scripts` (catálogo); (2) faixa `status = 'RUNNING'` de `ix_{prefixo}tck_queue`; (3) `INDEX RANGE SCAN` de `ix_{prefixo}tck_queue` por bloco, sem sort e sem tabela, `COUNT STOPKEY`; só os escolhidos pela PK |
| `claim` (3 passos) | `SELECT … FOR UPDATE WAIT 5` do script; contagem de `RUNNING` do par; `UPDATE … RETURNING started_at` (README §8.3) | `pk_{prefixo}scripts`; `ix_{prefixo}tck_scr`; `pk_{prefixo}tickets` |
| `own_sweep`, `tickets_running_do_agente` | `(CASE WHEN status = 'RUNNING' THEN agent_id END) = :agent_id` (README §8.7) | `ix_{prefixo}tck_run` |
| `heartbeat` | `executemany` do `UPDATE` por PK dos tickets e `UPDATE` do agente por `code` | `pk_{prefixo}tickets`; `uk_{prefixo}agt_code` |
| `register_pid`, `finalize`, `return_to_queue` | `UPDATE` pela PK com `agent_id` e `status` | `pk_{prefixo}tickets` |

---

## 2. Avaliação de execução do plano

**Plano: TESTADO em 2026-10-20**, Oracle 19.24 (banco `GFPR`), owner `openrisow` em modo compartilhado (README §2.5), driver Thin, com `EXPLAIN PLAN SET STATEMENT_ID … FOR <query>` + `DBMS_XPLAN.DISPLAY` (sem executar os comandos). O texto `{owner}` substitui `OPENRISOW`.

* **Volume simulado:** `tbsss_tickets` e `tbsss_agents` estão vazias depois do ciclo 02 → 01 → 99. Só durante o `EXPLAIN`, as estatísticas foram trocadas por valores fictícios (`DBMS_STATS.SET_TABLE_STATS`/`SET_COLUMN_STATS`/`SET_INDEX_STATS`): 1 milhão de tickets, 2.000 deles nos índices de função `tck_fila` e `tck_run` (inclusive as colunas ocultas `SYS_NC` desses índices), e 50 agentes. Em seguida, as estatísticas das duas tabelas foram apagadas e as dos índices recoletadas (nenhuma das duas é coletada pelo `01_implantar`). O estado antes e depois foi conferido e é idêntico; nenhuma linha foi gravada.
* **Sem `TABLE ACCESS FULL` em `tbsss_tickets` em nenhuma consulta:** conforme.
* **`candidates`:** os tickets vêm só de `INDEX FULL SCAN` em `ix_{prefixo}tck_queue`, que contém apenas os `PENDING` (as linhas dos outros status têm a expressão nula e não entram no índice); o teto usa `INDEX RANGE SCAN` em `ix_{prefixo}tck_scr`. O `TABLE ACCESS FULL` em `tbsss_scripts` é o ramo alternativo do plano **adaptativo** do Oracle 12c+ (`STATISTICS COLLECTOR` escolhe em execução entre nested loops pela PK e hash join); ele incide só sobre o catálogo de scripts. No 11gR2 não há plano adaptativo.
* **Claim:** os três passos são por PK ou por `ix_{prefixo}tck_scr`; a ordem de locks é `tbsss_scripts` → `tbsss_tickets` (README §8.3).

---

## 3. Volume real (CR-013)

**Medido em 2026-10-20**, Oracle 19.24 (`GFPR`), owner `openrisow`, com **1.000.000 de tickets `PENDING` vencidos num único ambiente** (14 scripts, prioridades 1 a 4, espera de até 30 dias), estatísticas reais coletadas (`GATHER_TABLE_STATS`, `cascade`), `statistics_level = ALL` e `DBMS_XPLAN.DISPLAY_CURSOR(..., 'ALLSTATS LAST')`. A massa (`created_by = 'TST:cr013'`) foi removida no fim, e as estatísticas voltaram ao estado da implantação (tabela sem estatística, índices recoletados).

* **Antes (índice só dos `PENDING` por `CASE` e ordenação de toda a fila):** `TABLE ACCESS FULL` de `tbsss_tickets` (1.000.000 de linhas), `INDEX FAST FULL SCAN` de `ix_tck_scr` para o teto e `SORT ORDER BY STOPKEY` sobre o milhão, para devolver 20 linhas. Com um índice de `CASE` em todas as colunas, o Oracle nunca elimina o sort (lê a faixa inteira), nem com dicas.
* **Depois (CR-013):** cada bloco da janela é um `INDEX RANGE SCAN` de `ix_tbsss_tck_queue` com 3 leituras, sem sort e sem acesso à tabela; só os 80 escolhidos voltam à tabela pela PK. Resultado idêntico ao da ordenação completa da fila.

| Agentes simultâneos | Antes: mediana / leituras | CR-013: mediana / leituras |
|---|---|---|
| 1 | 1,28 s / 22631 | 0,18 s / 275 |
| 2 | 1,21 s / 22616 | 0,18 s / 264 |
| 5 | 1,25 s / 22616 | 0,17 s / 264 |

O tempo que resta é quase todo de ida e volta à rede (três consultas curtas). O custo da janela não depende do tamanho da fila: cresce com `ambientes atendidos × 4 × :lote`.

### candidatos (CR-013, execução real com 1 milhão de PENDING)

```text
| Id  | Operation                       | Name              | Starts | A-Rows | Buffers |
|   0 | SELECT STATEMENT                |                   |      1 |     20 |     254 |
|*  1 |  COUNT STOPKEY                  |                   |      1 |     20 |     254 |
|   2 |   VIEW                          |                   |      1 |     20 |     254 |
|*  3 |    SORT ORDER BY STOPKEY        |                   |      1 |     20 |     254 |
|   4 |     NESTED LOOPS                |                   |      1 |     80 |     254 |
|   5 |      NESTED LOOPS               |                   |      1 |     80 |     174 |
|   6 |       VIEW                      |                   |      1 |     80 |      12 |
|   7 |        UNION-ALL                |                   |      1 |     80 |      12 |
|*  8 |         COUNT STOPKEY           |                   |      1 |     20 |       3 |
|   9 |          VIEW                   |                   |      1 |     20 |       3 |
|* 10 |           INDEX RANGE SCAN      | IX_TBSSS_TCK_QUEUE |      1 |     20 |       3 |
|* 11 |         COUNT STOPKEY           |                   |      1 |     20 |       3 |
|  12 |          VIEW                   |                   |      1 |     20 |       3 |
|* 13 |           INDEX RANGE SCAN      | IX_TBSSS_TCK_QUEUE |      1 |     20 |       3 |
|* 14 |         COUNT STOPKEY           |                   |      1 |     20 |       3 |
|  15 |          VIEW                   |                   |      1 |     20 |       3 |
|* 16 |           INDEX RANGE SCAN      | IX_TBSSS_TCK_QUEUE |      1 |     20 |       3 |
|* 17 |         COUNT STOPKEY           |                   |      1 |     20 |       3 |
|  18 |          VIEW                   |                   |      1 |     20 |       3 |
|* 19 |           INDEX RANGE SCAN      | IX_TBSSS_TCK_QUEUE |      1 |     20 |       3 |
|* 20 |       INDEX UNIQUE SCAN         | PK_TBSSS_TICKETS  |     80 |     80 |     162 |
|* 21 |      TABLE ACCESS BY INDEX ROWID| TBSSS_TICKETS     |     80 |     80 |      80 |
```

Pior caso conhecido: um script no teto com a fila inteira à frente dos demais. O filtro `script_id IN (...)` é aplicado no próprio índice, então o bloco percorre só entradas de índice (sem tabela) até achar o lote.

### Planos registrados (com volume simulado, F8.3a; o de `candidates` foi substituído pelo da seção 3)

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
|  10 |           INDEX FULL SCAN                   | IX_TBSSS_TCK_QUEUE |
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
|   1 |  UPDATE                      | TBSSS_AGENTS       |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_AGENTS       |
|   3 |    INDEX UNIQUE SCAN         | UK_TBSSS_AGT_CODE |
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

---

## 4. Desdobro e nó offline (F8.4a)

**Plano: TESTADO em 2026-10-20**, Oracle 19.24 (`GFPR`), `EXPLAIN PLAN` + `DBMS_XPLAN.DISPLAY(..., 'BASIC')`. `tbsss_schedules` com as estatísticas da implantação; para o nó offline, estatísticas de `tbsss_tickets` simuladas só durante o `EXPLAIN` (1.000.000 de tickets, 2.000 em `ix_tck_run`) e restauradas em seguida (tabela sem estatística, índices recoletados).

| Método | Consulta | Acesso |
|---|---|---|
| `scheduler_agenda.due_rules` | README §7.5, paginada (R-08) | `INDEX RANGE SCAN` de `ix_{prefixo}sch_next (active, next_run_at, id)` com `COUNT STOPKEY` |
| `scheduler_agenda.lock_rule` | `FOR UPDATE SKIP LOCKED` pela regra | `ix_{prefixo}sch_next` |
| `scheduler_agenda.get_ticket_status` | sobreposição (passo 4) | `pk_{prefixo}tickets` |
| `scheduler_fila.mark_node_offline` | README §8.8, 1ª etapa, `FOR UPDATE SKIP LOCKED` | `ix_{prefixo}tck_run` (só os `RUNNING`), sem `TABLE ACCESS FULL` com volume; tabela vazia e sem estatística dá `TABLE ACCESS FULL`, que é o mais barato nesse caso |

### regras_vencidas

```text
------------------------------------------------
| Id  | Operation          | Name              |
------------------------------------------------
|   0 | SELECT STATEMENT   |                   |
|   1 |  COUNT STOPKEY     |                   |
|   2 |   VIEW             |                   |
|   3 |    INDEX RANGE SCAN| IX_TBSSS_SCH_NEXT |
------------------------------------------------
```

### marcar_node_offline (1ª etapa, volume simulado)

```text
-----------------------------------------------------------------
| Id  | Operation                            | Name             |
-----------------------------------------------------------------
|   0 | SELECT STATEMENT                     |                  |
|   1 |  FOR UPDATE                          |                  |
|   2 |   TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_TICKETS    |
|   3 |    INDEX FULL SCAN                   | IX_TBSSS_TCK_RUN |
-----------------------------------------------------------------
```

A forma `(CASE … agent_id END) >= CHR(1)`, usada no painel de agentes, dá `INDEX RANGE SCAN` do mesmo índice; com o índice só dos `RUNNING`, a diferença é pequena, e o SQL fica literal do README §8.8.

