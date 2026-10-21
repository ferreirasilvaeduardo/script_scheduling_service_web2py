# SSS — Explain Plan: Agregado TICKETS (F7.3)

Consultas SQL estáticas do `RepoTicketsOracle` (`modules/repo_oracle/tickets.py`) no Oracle 11gR2+.

> **Identificadores dinâmicos (README §9.1, §12.1):** `{owner}` vem de `[oracle] owner` e `{prefixo}` de `[oracle] table_prefix` (padrão `tbsss_`). Os dois são validados por `sql_ident` e qualificados **uma vez**, na criação do repositório. Todo valor entra por bind, inclusive as listas `IN` (`:s0..`, `:e0..`, geradas por contagem e em lotes de até 500) e as datas (`TIPO_DATE`, README §7.5).
>
> **Sem CLOB nas leituras (AGENTS §4.13):** `list`, `last_runs`, `script_history` e `answers` nunca selecionam `log_output` nem `submitted_params`. `get` traz `submitted_params`, mas nunca `log_output`, que só sai em fatias por `log_read`.

---

## 1. Consultas

| Método | Consulta | Acesso esperado |
|---|---|---|
| `list` | `COUNT(*)` com `ROWNUM <= 10001` e página `ROWNUM`, ordem `created_at DESC, id DESC`; filtros da allowlist (status/escopo por `IN`, ambiente, script, solicitante, reexecuções, origem e período `created_at >= :inicio AND created_at < :fim`) | `ix_{prefixo}tck_crt (created_at, id)` em ordem descendente, sem ordenar a tabela; o índice do filtro quando houver |
| `last_runs` | `ROW_NUMBER() OVER (PARTITION BY script_id ORDER BY created_at DESC, id DESC)` com `script_id IN (…)`, escopo e solicitante; `rn = 1` | `ix_{prefixo}tck_scr` ou `ix_{prefixo}tck_hist`, conforme o filtro |
| `script_history` | `script_id = :script_id AND created_at >= :desde`, escopo e solicitante, ordem `created_at DESC, id DESC` e `ROWNUM <= :limite` (devolvido em ordem crescente) | `ix_{prefixo}tck_hist (script_id, created_at)` |
| `get`, `log_read` | Leitura pela PK; o log por locator (`lob.read(offset + 1, max_chars)`) | `pk_{prefixo}tickets` |
| `answers` | `ticket_id = :ticket_id ORDER BY id` | `uk_{prefixo}tans_tck_prm` (líder `ticket_id`) |
| `request_cancel` | Os dois `UPDATE` literais do README §5.6 e, com `rowcount = 0`, `SELECT status, cancel_requested … FOR UPDATE WAIT 5` | `pk_{prefixo}tickets`; só a linha do próprio ticket é travada, então a ordem de locks do §8.3 não muda |

---

## 2. Avaliação de execução do plano

**Plano: TESTADO em 2026-10-19**, Oracle 19.24 (banco `GFPR`), owner `openrisow` em modo compartilhado (README §2.5), driver Thin. Os planos saíram de `EXPLAIN PLAN SET STATEMENT_ID … FOR <query>` + `DBMS_XPLAN.DISPLAY`, sem executar os comandos. O texto `{owner}` substitui `OPENRISOW`.

* **Volume simulado:** a `tbsss_tickets` está vazia nesse banco, e sem linhas o otimizador escolheria varrer a tabela, o que não diz nada sobre produção. Por isso, só durante o `EXPLAIN`, as estatísticas foram trocadas por valores fictícios via `DBMS_STATS.SET_TABLE_STATS`/`SET_COLUMN_STATS`/`SET_INDEX_STATS`: 1 milhão de tickets (200 scripts, 10 ambientes, 200 logins) e 3 milhões de respostas.
  * Logo depois, as estatísticas foram restauradas ao estado anterior: as das tabelas apagadas e as dos índices vazios recoletadas.
  * O estado antes e depois foi conferido e é idêntico. Nenhuma linha foi gravada.
* **Sem `TABLE ACCESS FULL` em `tbsss_tickets` em nenhuma consulta:** conforme.
* **Correção feita no F7.3:** com `ix_{prefixo}tck_crt` só em `(created_at)`, a lista sem filtro (a primeira tela do administrador) saía com `TABLE ACCESS FULL` em 1 milhão de linhas e `SORT ORDER BY STOPKEY` a cada página, porque o desempate por `id` não vinha do índice.
  * O índice passou a `(created_at, id)`, ainda na versão 1 do esquema (AGENTS §4.16: versão aberta até a primeira produção).
  * Agora a página é lida por `INDEX FULL SCAN DESCENDING` com `COUNT STOPKEY`, só as linhas da página.
  * O `GFPR` foi refeito pelo ciclo `02_rollback` → `01_implantar` → `99_validar`.
* **`last_runs`:** o prompt do F7.3 cita `ix_{prefixo}tck_hist`; o README §5.8, `ix_{prefixo}tck_scr`. O plano real usa `ix_{prefixo}tck_scr` com escopo de ambiente e `ix_{prefixo}tck_usr` + `ix_{prefixo}tck_hist` com solicitante. Os dois casos são por índice.

### Planos registrados (com volume simulado)

### listar (admin, sem filtro) [1]
```text
 
------------------------------------------------------------
| Id  | Operation               | Name             | Rows  |
------------------------------------------------------------
|   0 | SELECT STATEMENT        |                  |     1 |
|   1 |  SORT AGGREGATE         |                  |     1 |
|   2 |   VIEW                  |                  | 10001 |
|   3 |    COUNT STOPKEY        |                  |       |
|   4 |     INDEX FAST FULL SCAN| IX_TBSSS_TCK_ENV | 10001 |
------------------------------------------------------------
```

### listar (admin, sem filtro) [2]
```text
 
-------------------------------------------------------------------
| Id  | Operation                      | Name             | Rows  |
-------------------------------------------------------------------
|   0 | SELECT STATEMENT               |                  |    10 |
|   1 |  VIEW                          |                  |    10 |
|   2 |   COUNT STOPKEY                |                  |       |
|   3 |    VIEW                        |                  |    10 |
|   4 |     TABLE ACCESS BY INDEX ROWID| TBSSS_TICKETS    |  1000K|
|   5 |      INDEX FULL SCAN DESCENDING| IX_TBSSS_TCK_CRT |    10 |
-------------------------------------------------------------------
```

### listar (escopo + status + periodo) [1]
```text
 
---------------------------------------------------------------------------
| Id  | Operation                              | Name             | Rows  |
---------------------------------------------------------------------------
|   0 | SELECT STATEMENT                       |                  |     1 |
|   1 |  SORT AGGREGATE                        |                  |     1 |
|   2 |   VIEW                                 |                  |  4000 |
|   3 |    COUNT STOPKEY                       |                  |       |
|   4 |     TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_TICKETS    |  4000 |
|   5 |      INDEX RANGE SCAN                  | IX_TBSSS_TCK_CRT |  9000 |
---------------------------------------------------------------------------
```

### listar (escopo + status + periodo) [2]
```text
 
--------------------------------------------------------------------
| Id  | Operation                       | Name             | Rows  |
--------------------------------------------------------------------
|   0 | SELECT STATEMENT                |                  |    10 |
|   1 |  VIEW                           |                  |    10 |
|   2 |   COUNT STOPKEY                 |                  |       |
|   3 |    VIEW                         |                  |    11 |
|   4 |     TABLE ACCESS BY INDEX ROWID | TBSSS_TICKETS    |  4000 |
|   5 |      INDEX RANGE SCAN DESCENDING| IX_TBSSS_TCK_CRT |    25 |
--------------------------------------------------------------------
```

### listar (proprios: solicitante + script) [1]
```text
 
-----------------------------------------------------------
| Id  | Operation             | Name              | Rows  |
-----------------------------------------------------------
|   0 | SELECT STATEMENT      |                   |     1 |
|   1 |  SORT AGGREGATE       |                   |     1 |
|   2 |   VIEW                |                   |    25 |
|   3 |    COUNT STOPKEY      |                   |       |
|   4 |     VIEW              | index$_join$_002  |    25 |
|   5 |      HASH JOIN        |                   |       |
|   6 |       INDEX RANGE SCAN| IX_TBSSS_TCK_USR  |    25 |
|   7 |       INDEX RANGE SCAN| IX_TBSSS_TCK_HIST |    25 |
-----------------------------------------------------------
```

### listar (proprios: solicitante + script) [2]
```text
 
-----------------------------------------------------------------------------
| Id  | Operation                               | Name              | Rows  |
-----------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                   |    10 |
|   1 |  VIEW                                   |                   |    10 |
|   2 |   COUNT STOPKEY                         |                   |       |
|   3 |    VIEW                                 |                   |    25 |
|   4 |     SORT ORDER BY STOPKEY               |                   |    25 |
|   5 |      TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_TICKETS     |    25 |
|   6 |       BITMAP CONVERSION TO ROWIDS       |                   |       |
|   7 |        BITMAP AND                       |                   |       |
|   8 |         BITMAP CONVERSION FROM ROWIDS   |                   |       |
|   9 |          INDEX RANGE SCAN               | IX_TBSSS_TCK_USR  |  5000 |
|  10 |         BITMAP CONVERSION FROM ROWIDS   |                   |       |
|  11 |          SORT ORDER BY                  |                   |       |
|  12 |           INDEX RANGE SCAN              | IX_TBSSS_TCK_HIST |  5000 |
-----------------------------------------------------------------------------
```

### listar (reexecucoes: parent_ticket_id) [1]
```text
 
--------------------------------------------------------
| Id  | Operation           | Name             | Rows  |
--------------------------------------------------------
|   0 | SELECT STATEMENT    |                  |     1 |
|   1 |  SORT AGGREGATE     |                  |     1 |
|   2 |   VIEW              |                  |     1 |
|   3 |    COUNT STOPKEY    |                  |       |
|   4 |     INDEX RANGE SCAN| IX_TBSSS_TCK_PAR |     1 |
--------------------------------------------------------
```

### listar (reexecucoes: parent_ticket_id) [2]
```text
 
----------------------------------------------------------------------------
| Id  | Operation                               | Name             | Rows  |
----------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                  |     1 |
|   1 |  VIEW                                   |                  |     1 |
|   2 |   COUNT STOPKEY                         |                  |       |
|   3 |    VIEW                                 |                  |     1 |
|   4 |     SORT ORDER BY STOPKEY               |                  |     1 |
|   5 |      TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_TICKETS    |     1 |
|   6 |       INDEX RANGE SCAN                  | IX_TBSSS_TCK_PAR |     1 |
----------------------------------------------------------------------------
```

### ultimas_execucoes (escopo) [1]
```text
 
---------------------------------------------------------------------------
| Id  | Operation                              | Name             | Rows  |
---------------------------------------------------------------------------
|   0 | SELECT STATEMENT                       |                  |  1500 |
|   1 |  VIEW                                  |                  |  1500 |
|   2 |   WINDOW SORT PUSHED RANK              |                  |  1500 |
|   3 |    INLIST ITERATOR                     |                  |       |
|   4 |     TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_TICKETS    |  1500 |
|   5 |      INDEX RANGE SCAN                  | IX_TBSSS_TCK_SCR |  1500 |
---------------------------------------------------------------------------
```

### ultimas_execucoes (solicitante) [1]
```text
 
---------------------------------------------------------------------------
| Id  | Operation                             | Name              | Rows  |
---------------------------------------------------------------------------
|   0 | SELECT STATEMENT                      |                   |    75 |
|   1 |  VIEW                                 |                   |    75 |
|   2 |   WINDOW SORT PUSHED RANK             |                   |    75 |
|   3 |    TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_TICKETS     |    75 |
|   4 |     BITMAP CONVERSION TO ROWIDS       |                   |       |
|   5 |      BITMAP AND                       |                   |       |
|   6 |       BITMAP CONVERSION FROM ROWIDS   |                   |       |
|   7 |        INDEX RANGE SCAN               | IX_TBSSS_TCK_USR  |  5000 |
|   8 |       BITMAP OR                       |                   |       |
|   9 |        BITMAP CONVERSION FROM ROWIDS  |                   |       |
|  10 |         SORT ORDER BY                 |                   |       |
|  11 |          INDEX RANGE SCAN             | IX_TBSSS_TCK_HIST |  5000 |
|  12 |        BITMAP CONVERSION FROM ROWIDS  |                   |       |
|  13 |         SORT ORDER BY                 |                   |       |
|  14 |          INDEX RANGE SCAN             | IX_TBSSS_TCK_HIST |  5000 |
|  15 |        BITMAP CONVERSION FROM ROWIDS  |                   |       |
|  16 |         SORT ORDER BY                 |                   |       |
|  17 |          INDEX RANGE SCAN             | IX_TBSSS_TCK_HIST |  5000 |
---------------------------------------------------------------------------
```

### historico_script (escopo, limite) [1]
```text
 
----------------------------------------------------------------------------
| Id  | Operation                              | Name              | Rows  |
----------------------------------------------------------------------------
|   0 | SELECT STATEMENT                       |                   |    10 |
|   1 |  COUNT STOPKEY                         |                   |       |
|   2 |   VIEW                                 |                   |    25 |
|   3 |    SORT ORDER BY STOPKEY               |                   |    25 |
|   4 |     TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_TICKETS     |    25 |
|   5 |      INDEX RANGE SCAN                  | IX_TBSSS_TCK_HIST |    45 |
----------------------------------------------------------------------------
```

### OBTER
```text
 
----------------------------------------------------------------
| Id  | Operation                   | Name             | Rows  |
----------------------------------------------------------------
|   0 | SELECT STATEMENT            |                  |     1 |
|   1 |  TABLE ACCESS BY INDEX ROWID| TBSSS_TICKETS    |     1 |
|   2 |   INDEX UNIQUE SCAN         | PK_TBSSS_TICKETS |     1 |
----------------------------------------------------------------
```

### RESPOSTAS
```text
 
------------------------------------------------------------------------------
| Id  | Operation                            | Name                  | Rows  |
------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                     |                       |     3 |
|   1 |  SORT ORDER BY                       |                       |     3 |
|   2 |   TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_TICKET_ANSWER     |     3 |
|   3 |    INDEX RANGE SCAN                  | UK_TBSSS_TANS_TCK_PRM |     3 |
------------------------------------------------------------------------------
```

### LOG
```text
 
----------------------------------------------------------------
| Id  | Operation                   | Name             | Rows  |
----------------------------------------------------------------
|   0 | SELECT STATEMENT            |                  |     1 |
|   1 |  TABLE ACCESS BY INDEX ROWID| TBSSS_TICKETS    |     1 |
|   2 |   INDEX UNIQUE SCAN         | PK_TBSSS_TICKETS |     1 |
----------------------------------------------------------------
```

### CANCEL_SINALIZAR
```text
 
-----------------------------------------------------------------
| Id  | Operation                    | Name             | Rows  |
-----------------------------------------------------------------
|   0 | UPDATE STATEMENT             |                  |     1 |
|   1 |  UPDATE                      | TBSSS_TICKETS    |       |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_TICKETS    |     1 |
|   3 |    INDEX UNIQUE SCAN         | PK_TBSSS_TICKETS |     1 |
-----------------------------------------------------------------
```

### CANCEL_PENDENTE
```text
 
-----------------------------------------------------------------
| Id  | Operation                    | Name             | Rows  |
-----------------------------------------------------------------
|   0 | UPDATE STATEMENT             |                  |     1 |
|   1 |  UPDATE                      | TBSSS_TICKETS    |       |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_TICKETS    |     1 |
|   3 |    INDEX UNIQUE SCAN         | PK_TBSSS_TICKETS |     1 |
-----------------------------------------------------------------
```

### CANCEL_LER
```text
 
-----------------------------------------------------------------
| Id  | Operation                    | Name             | Rows  |
-----------------------------------------------------------------
|   0 | SELECT STATEMENT             |                  |     1 |
|   1 |  FOR UPDATE                  |                  |       |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_TICKETS    |     1 |
|   3 |    INDEX UNIQUE SCAN         | PK_TBSSS_TICKETS |     1 |
-----------------------------------------------------------------
```
