# SSS — Explain Plan: Agregado AUDITORIA_AGENTES (F7.3)

Consultas SQL estáticas do `RepoAuditOracle` e do `RepoAgentsOracle` (`modules/repo_oracle/audit.py` e `agentes.py`) no Oracle 11gR2+.

> **Identificadores dinâmicos (README §9.1, §12.1):** `{owner}` vem de `[oracle] owner` e `{prefixo}` de `[oracle] table_prefix` (padrão `tbsss_`). Os dois são validados por `sql_ident` e qualificados **uma vez**, na criação do repositório. Todo valor entra por bind, com as datas como `TIPO_DATE` (README §7.5).
>
> **Expressões dos índices por função (AGENTS §4.8):** `tickets_running`, `running_without_pid` e `unattended_queue` repetem as expressões de `ix_{prefixo}tck_run` (`CASE`) e `ix_{prefixo}tck_queue` (`GREATEST(scheduled_at, created_at)`, CR-013), importadas do `sql_ident`. Nenhuma das três lê CLOB.

---

## 1. Consultas

| Método | Consulta | Acesso esperado |
|---|---|---|
| `auditoria.list` | `COUNT(*)` com `ROWNUM <= 10001` e página `ROWNUM`, ordem `created_at DESC, id DESC`. O service sempre envia o período (`created_at >= :start_date AND created_at <= :end_date`, sem `TRUNC`, até 31 dias, ou 366 com filtro seletivo); filtros de ator e IP por trecho, ação, entidade, `entity_id` e `id_max` | `ix_{prefixo}aud_crt` no período; `ix_{prefixo}aud_ent` com entidade + id |
| `auditoria.iterate` | Os mesmos filtros e ordem, `ROWNUM <= :cutoff`, cursor com `arraysize` (exportação, sem offset) | idem |
| `auditoria.register` / `reserve_id` | `INSERT` pela PK; `NEXTVAL` da sequence | — |
| `agentes.list` | Todos os agentes por `codigo, id` (dezenas de linhas) | `TABLE ACCESS FULL` aceitável em `tbsss_agents` |
| `agentes.tickets_running` | `(CASE WHEN status = 'RUNNING' THEN agent_id END) = :code` | `ix_{prefixo}tck_run` |
| `agentes.unattended_queue` (CR-013) | `status = 'PENDING' AND GREATEST(scheduled_at, created_at) <= :now`, `COUNT(*)` e `MIN(inicio)` por ambiente e script, depois `JOIN` com `{prefixo}scripts` pelo interpretador do cadastro (CR-008, R-15) | `ix_{prefixo}tck_queue` só (`INDEX FAST FULL SCAN`, sem tabela): com 1 milhão de `PENDING`, 8.346 leituras e 0,3 s (agregado de toda a fila, só no painel) |
| `agentes.running_without_pid` | `(CASE WHEN status = 'RUNNING' THEN agent_id END) >= CHR(1)` (equivale a `IS NOT NULL` para o `agent_id`), sem PID e `started_at < :cutoff` | `ix_{prefixo}tck_run` |

---

## 2. Avaliação de execução do plano

**Plano: TESTADO em 2026-10-19**, Oracle 19.24 (banco `GFPR`), owner `openrisow` em modo compartilhado (README §2.5), driver Thin. Os planos saíram de `EXPLAIN PLAN SET STATEMENT_ID … FOR <query>` + `DBMS_XPLAN.DISPLAY`, sem executar os comandos. O texto `{owner}` substitui `OPENRISOW`.

* **Volume simulado:** só durante o `EXPLAIN`, via `DBMS_STATS.SET_*`, com 5 milhões de linhas de auditoria, 1 milhão de tickets e 50 agentes. As **colunas ocultas** dos índices por função também receberam estatísticas, com só os `RUNNING`/`PENDING` preenchidos, porque sem elas o otimizador supõe que quase toda a tabela tem valor na expressão.
  * Logo depois, as estatísticas foram restauradas ao estado anterior: as das tabelas apagadas e as dos índices vazios recoletadas.
  * O estado antes e depois foi conferido e é idêntico. Nenhuma linha foi gravada.
* **Sem `TABLE ACCESS FULL` em `tbsss_tickets` e `tbsss_audit`:** conforme. O `TABLE ACCESS FULL` restante é em `tbsss_agents`, que tem dezenas de linhas, e o ramo alternativo do plano adaptativo em `tbsss_scripts`.
* **Correção feita no F7.3:** `running_without_pid` com `(CASE …) IS NOT NULL` varria `tbsss_tickets` inteira, mesmo com a coluna oculta indicando só os `RUNNING`, porque o otimizador não transforma `IS NOT NULL` em faixa do índice. Com `>= CHR(1)`, equivalente para qualquer `agent_id` válido (`[A-Za-z0-9._-]`), a consulta passou a `INDEX RANGE SCAN` em `ix_{prefixo}tck_run`.
* **Lista da auditoria:** usa `ix_{prefixo}aud_crt` no período e ordena as linhas do período (`SORT ORDER BY STOPKEY`), limitado ao intervalo máximo do service. Se o volume diário crescer muito, a melhoria é o índice `(created_at, id)`, como em `ix_{prefixo}tck_crt`.

### Planos registrados (com volume simulado)

### auditoria.listar (periodo) [1]
```text
 
---------------------------------------------------------
| Id  | Operation            | Name             | Rows  |
---------------------------------------------------------
|   0 | SELECT STATEMENT     |                  |     1 |
|   1 |  SORT AGGREGATE      |                  |     1 |
|   2 |   VIEW               |                  | 10001 |
|   3 |    COUNT STOPKEY     |                  |       |
|   4 |     FILTER           |                  |       |
|   5 |      INDEX RANGE SCAN| IX_TBSSS_AUD_CRT | 10002 |
---------------------------------------------------------
```

### auditoria.listar (periodo) [2]
```text
 
-----------------------------------------------------------------------------
| Id  | Operation                                | Name             | Rows  |
-----------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                  |    10 |
|   1 |  VIEW                                    |                  |    10 |
|   2 |   COUNT STOPKEY                          |                  |       |
|   3 |    VIEW                                  |                  | 12500 |
|   4 |     SORT ORDER BY STOPKEY                |                  | 12500 |
|   5 |      FILTER                              |                  |       |
|   6 |       TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_AUDIT  | 12500 |
|   7 |        INDEX RANGE SCAN                  | IX_TBSSS_AUD_CRT | 22500 |
-----------------------------------------------------------------------------
```

### auditoria.listar (periodo + ator) [1]
```text
 
----------------------------------------------------------------------------
| Id  | Operation                               | Name             | Rows  |
----------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                  |     1 |
|   1 |  SORT AGGREGATE                         |                  |     1 |
|   2 |   VIEW                                  |                  |   625 |
|   3 |    COUNT STOPKEY                        |                  |       |
|   4 |     FILTER                              |                  |       |
|   5 |      TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_AUDIT  |   625 |
|   6 |       INDEX RANGE SCAN                  | IX_TBSSS_AUD_CRT | 22500 |
----------------------------------------------------------------------------
```

### auditoria.listar (periodo + ator) [2]
```text
 
-----------------------------------------------------------------------------
| Id  | Operation                                | Name             | Rows  |
-----------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                  |    10 |
|   1 |  VIEW                                    |                  |    10 |
|   2 |   COUNT STOPKEY                          |                  |       |
|   3 |    VIEW                                  |                  |   625 |
|   4 |     SORT ORDER BY STOPKEY                |                  |   625 |
|   5 |      FILTER                              |                  |       |
|   6 |       TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_AUDIT  |   625 |
|   7 |        INDEX RANGE SCAN                  | IX_TBSSS_AUD_CRT | 22500 |
-----------------------------------------------------------------------------
```

### auditoria.listar (periodo + entidade + entidade_id) [1]
```text
 
----------------------------------------------------------------------------
| Id  | Operation                               | Name             | Rows  |
----------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                  |     1 |
|   1 |  SORT AGGREGATE                         |                  |     1 |
|   2 |   VIEW                                  |                  |     1 |
|   3 |    COUNT STOPKEY                        |                  |       |
|   4 |     FILTER                              |                  |       |
|   5 |      TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_AUDIT  |     1 |
|   6 |       INDEX RANGE SCAN                  | IX_TBSSS_AUD_ENT |     5 |
----------------------------------------------------------------------------
```

### auditoria.listar (periodo + entidade + entidade_id) [2]
```text
 
-----------------------------------------------------------------------------
| Id  | Operation                                | Name             | Rows  |
-----------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                  |     1 |
|   1 |  VIEW                                    |                  |     1 |
|   2 |   COUNT STOPKEY                          |                  |       |
|   3 |    VIEW                                  |                  |     1 |
|   4 |     SORT ORDER BY STOPKEY                |                  |     1 |
|   5 |      FILTER                              |                  |       |
|   6 |       TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_AUDIT  |     1 |
|   7 |        INDEX RANGE SCAN                  | IX_TBSSS_AUD_ENT |     5 |
-----------------------------------------------------------------------------
```

### auditoria.listar (exportacao: periodo + id_max) [1]
```text
 
-------------------------------------------------------------
| Id  | Operation              | Name               | Rows  |
-------------------------------------------------------------
|   0 | SELECT STATEMENT       |                    |     1 |
|   1 |  SORT AGGREGATE        |                    |     1 |
|   2 |   VIEW                 |                    |   625 |
|   3 |    COUNT STOPKEY       |                    |       |
|   4 |     FILTER             |                    |       |
|   5 |      VIEW              | index$_join$_002   |   625 |
|   6 |       HASH JOIN        |                    |       |
|   7 |        INDEX RANGE SCAN| IX_TBSSS_AUD_CRT   |   625 |
|   8 |        INDEX RANGE SCAN| PK_TBSSS_AUDIT |   625 |
-------------------------------------------------------------
```

### auditoria.listar (exportacao: periodo + id_max) [2]
```text
 
-------------------------------------------------------------------------------
| Id  | Operation                                | Name               | Rows  |
-------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                    |    10 |
|   1 |  VIEW                                    |                    |    10 |
|   2 |   COUNT STOPKEY                          |                    |       |
|   3 |    VIEW                                  |                    |   625 |
|   4 |     SORT ORDER BY STOPKEY                |                    |   625 |
|   5 |      FILTER                              |                    |       |
|   6 |       TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_AUDIT    |   625 |
|   7 |        BITMAP CONVERSION TO ROWIDS       |                    |       |
|   8 |         BITMAP AND                       |                    |       |
|   9 |          BITMAP CONVERSION FROM ROWIDS   |                    |       |
|  10 |           SORT ORDER BY                  |                    |       |
|  11 |            INDEX RANGE SCAN              | IX_TBSSS_AUD_CRT   | 22500 |
|  12 |          BITMAP CONVERSION FROM ROWIDS   |                    |       |
|  13 |           SORT ORDER BY                  |                    |       |
|  14 |            INDEX RANGE SCAN              | PK_TBSSS_AUDIT | 22500 |
-------------------------------------------------------------------------------
```

### auditoria.iterar (exportacao)
```text
 
------------------------------------------------------------------------------
| Id  | Operation                               | Name               | Rows  |
------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                    |    10 |
|   1 |  COUNT STOPKEY                          |                    |       |
|   2 |   VIEW                                  |                    |   625 |
|   3 |    SORT ORDER BY STOPKEY                |                    |   625 |
|   4 |     FILTER                              |                    |       |
|   5 |      TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_AUDIT    |   625 |
|   6 |       BITMAP CONVERSION TO ROWIDS       |                    |       |
|   7 |        BITMAP AND                       |                    |       |
|   8 |         BITMAP CONVERSION FROM ROWIDS   |                    |       |
|   9 |          SORT ORDER BY                  |                    |       |
|  10 |           INDEX RANGE SCAN              | IX_TBSSS_AUD_CRT   | 22500 |
|  11 |         BITMAP CONVERSION FROM ROWIDS   |                    |       |
|  12 |          SORT ORDER BY                  |                    |       |
|  13 |           INDEX RANGE SCAN              | PK_TBSSS_AUDIT | 22500 |
------------------------------------------------------------------------------
```

### agentes.listar [1]
```text
 
----------------------------------------------------
| Id  | Operation          | Name          | Rows  |
----------------------------------------------------
|   0 | SELECT STATEMENT   |               |    50 |
|   1 |  SORT ORDER BY     |               |    50 |
|   2 |   TABLE ACCESS FULL| TBSSS_AGENTS |    50 |
----------------------------------------------------
```

### agentes.tickets_running
```text
 
-------------------------------------------------------------------------
| Id  | Operation                            | Name             | Rows  |
-------------------------------------------------------------------------
|   0 | SELECT STATEMENT                     |                  |    40 |
|   1 |  SORT ORDER BY                       |                  |    40 |
|   2 |   TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_TICKETS    |    40 |
|   3 |    INDEX RANGE SCAN                  | IX_TBSSS_TCK_RUN |    40 |
-------------------------------------------------------------------------
```

### agentes.fila_sem_atendente
```text
 
------------------------------------------------------------------------------
| Id  | Operation                                | Name              | Rows  |
------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                         |                   |     1 |
|   1 |  HASH GROUP BY                           |                   |     1 |
|   2 |   HASH JOIN                              |                   |     1 |
|   3 |    NESTED LOOPS                          |                   |     1 |
|   4 |     NESTED LOOPS                         |                   |     1 |
|   5 |      STATISTICS COLLECTOR                |                   |       |
|   6 |       TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_TICKETS     |     1 |
|   7 |        INDEX RANGE SCAN                  | IX_TBSSS_TCK_QUEUE |     1 |
|   8 |      INDEX UNIQUE SCAN                   | PK_TBSSS_SCRIPTS  |     1 |
|   9 |     TABLE ACCESS BY INDEX ROWID          | TBSSS_SCRIPTS     |     1 |
|  10 |    TABLE ACCESS FULL                     | TBSSS_SCRIPTS     |     1 |
------------------------------------------------------------------------------
```

### agentes.rodando_sem_pid
```text
 
-------------------------------------------------------------------------
| Id  | Operation                            | Name             | Rows  |
-------------------------------------------------------------------------
|   0 | SELECT STATEMENT                     |                  |     1 |
|   1 |  SORT ORDER BY                       |                  |     1 |
|   2 |   TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_TICKETS    |     1 |
|   3 |    INDEX RANGE SCAN                  | IX_TBSSS_TCK_RUN |    18 |
-------------------------------------------------------------------------
```
