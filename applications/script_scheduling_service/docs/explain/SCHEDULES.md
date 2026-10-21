# SSS — Explain Plan: Agregado AGENDAMENTOS (F7.3)

Consultas SQL estáticas do `RepoSchedulesOracle` (`modules/repo_oracle/schedules.py`) no Oracle 11gR2+.

> **Identificadores dinâmicos (README §9.1, §12.1):** `{owner}` vem de `[oracle] owner` e `{prefixo}` de `[oracle] table_prefix` (padrão `tbsss_`). Os dois são validados por `sql_ident` e qualificados **uma vez**, na criação do repositório. Todo valor entra por bind; as datas usam `TIPO_DATE` (README §7.5) e o `params_json`, bind CLOB.
>
> **`params_json` na listagem (exceção documentada, README §2.5):** o service avalia cada regra com as respostas gravadas (tela de regras e Agenda), então `list` traz esse CLOB pequeno. O `log_output` nunca entra em listagem.

---

## 1. Consultas

| Método | Consulta | Acesso esperado |
|---|---|---|
| `list` | `COUNT(*)` com `ROWNUM <= 10001` e página `ROWNUM`, ordem `proxima_execucao, id`; filtros `active`, `script_id`, `environment`, `user_id`, `name` (trecho, `ESCAPE`) e escopo por `IN` | `ix_{prefixo}sch_next (active, next_run_at, id)` com `active = 'Y'` (Agenda); `ix_{prefixo}sch_scr`/`amb`/`usr` nos filtros |
| `get`, `update`, `resume` | Leitura pela PK; lock `FOR UPDATE WAIT 5`; `UPDATE` pela PK | `pk_{prefixo}schedules` |
| `pause` | `UPDATE … WHERE id = :id AND active = 'Y' [AND next_run_at = :antiga_data]` (CR-007, R-19), com `rowcount` conferido | `pk_{prefixo}schedules` |
| `ticket_status` | `SELECT status FROM {prefixo}tickets WHERE id = :id` | `pk_{prefixo}tickets` |

---

## 2. Avaliação de execução do plano

**Plano: TESTADO em 2026-10-19**, Oracle 19.24 (banco `GFPR`), owner `openrisow` em modo compartilhado (README §2.5), driver Thin. Os planos saíram de `EXPLAIN PLAN SET STATEMENT_ID … FOR <query>` + `DBMS_XPLAN.DISPLAY`, sem executar os comandos. O texto `{owner}` substitui `OPENRISOW`.

* **Volume simulado:** a tabela está vazia nesse banco. Só durante o `EXPLAIN`, as estatísticas de `tbsss_schedules` e dos seus índices foram trocadas por valores fictícios via `DBMS_STATS.SET_*`: 100 mil regras, 200 scripts, 10 ambientes e 200 usuários.
  * Logo depois, foram restauradas ao estado anterior: as da tabela apagadas e as dos índices vazios recoletadas.
  * O estado antes e depois foi conferido e é idêntico. Nenhuma linha foi gravada.
* **`tbsss_tickets`/`tbsss_audit`:** só `ticket_status` lê tickets, pela PK; a auditoria só recebe `INSERT`. Conforme.
* **Agenda, filtros e transições:** todos por índice; a Agenda (`active = 'Y'`) lê `ix_{prefixo}sch_next` na ordem do índice.
* **Lista do administrador sem filtro:** `TABLE ACCESS FULL` em `tbsss_schedules` + `SORT ORDER BY STOPKEY`, porque a ordem `proxima_execucao, id` não começa por `active`.
  * Fica registrado, sem mudança de esquema: a tabela é de escala de cadastro (centenas de regras) e não está no critério do F7.3 (tickets e auditoria).
  * Se o volume real crescer, a correção é um índice `(next_run_at, id)`.

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
|   4 |     INDEX FAST FULL SCAN| IX_TBSSS_SCH_ENV | 10001 |
------------------------------------------------------------
```

### listar (admin, sem filtro) [2]
```text
 
---------------------------------------------------------------
| Id  | Operation                | Name               | Rows  |
---------------------------------------------------------------
|   0 | SELECT STATEMENT         |                    |    10 |
|   1 |  VIEW                    |                    |    10 |
|   2 |   COUNT STOPKEY          |                    |       |
|   3 |    VIEW                  |                    |   100K|
|   4 |     SORT ORDER BY STOPKEY|                    |   100K|
|   5 |      TABLE ACCESS FULL   | TBSSS_SCHEDULES |   100K|
---------------------------------------------------------------
```

### listar (agenda: ativo = S, escopo) [1]
```text
 
------------------------------------------------------------
| Id  | Operation              | Name              | Rows  |
------------------------------------------------------------
|   0 | SELECT STATEMENT       |                   |     1 |
|   1 |  SORT AGGREGATE        |                   |     1 |
|   2 |   VIEW                 |                   | 10000 |
|   3 |    COUNT STOPKEY       |                   |       |
|   4 |     VIEW               | index$_join$_002  | 10000 |
|   5 |      HASH JOIN         |                   |       |
|   6 |       INLIST ITERATOR  |                   |       |
|   7 |        INDEX RANGE SCAN| IX_TBSSS_SCH_ENV  | 10000 |
|   8 |       INDEX RANGE SCAN | IX_TBSSS_SCH_NEXT | 10000 |
------------------------------------------------------------
```

### listar (agenda: ativo = S, escopo) [2]
```text
 
---------------------------------------------------------------------
| Id  | Operation                      | Name               | Rows  |
---------------------------------------------------------------------
|   0 | SELECT STATEMENT               |                    |    10 |
|   1 |  VIEW                          |                    |    10 |
|   2 |   COUNT STOPKEY                |                    |       |
|   3 |    VIEW                        |                    |    10 |
|   4 |     TABLE ACCESS BY INDEX ROWID| TBSSS_SCHEDULES | 10000 |
|   5 |      INDEX RANGE SCAN          | IX_TBSSS_SCH_NEXT  |    50 |
---------------------------------------------------------------------
```

### listar (por script, contagem do cadastro) [1]
```text
 
--------------------------------------------------------
| Id  | Operation           | Name             | Rows  |
--------------------------------------------------------
|   0 | SELECT STATEMENT    |                  |     1 |
|   1 |  SORT AGGREGATE     |                  |     1 |
|   2 |   VIEW              |                  |   500 |
|   3 |    COUNT STOPKEY    |                  |       |
|   4 |     INDEX RANGE SCAN| IX_TBSSS_SCH_SCR |   500 |
--------------------------------------------------------
```

### listar (por script, contagem do cadastro) [2]
```text
 
------------------------------------------------------------------------------
| Id  | Operation                               | Name               | Rows  |
------------------------------------------------------------------------------
|   0 | SELECT STATEMENT                        |                    |    10 |
|   1 |  VIEW                                   |                    |    10 |
|   2 |   COUNT STOPKEY                         |                    |       |
|   3 |    VIEW                                 |                    |   500 |
|   4 |     SORT ORDER BY STOPKEY               |                    |   500 |
|   5 |      TABLE ACCESS BY INDEX ROWID BATCHED| TBSSS_SCHEDULES |   500 |
|   6 |       INDEX RANGE SCAN                  | IX_TBSSS_SCH_SCR   |   500 |
------------------------------------------------------------------------------
```

### listar (por ambiente ativo) [1]
```text
 
-----------------------------------------------------------
| Id  | Operation             | Name              | Rows  |
-----------------------------------------------------------
|   0 | SELECT STATEMENT      |                   |     1 |
|   1 |  SORT AGGREGATE       |                   |     1 |
|   2 |   VIEW                |                   |  5000 |
|   3 |    COUNT STOPKEY      |                   |       |
|   4 |     VIEW              | index$_join$_002  |  5000 |
|   5 |      HASH JOIN        |                   |       |
|   6 |       INDEX RANGE SCAN| IX_TBSSS_SCH_ENV  |  5000 |
|   7 |       INDEX RANGE SCAN| IX_TBSSS_SCH_NEXT |  5000 |
-----------------------------------------------------------
```

### listar (por ambiente ativo) [2]
```text
 
---------------------------------------------------------------------
| Id  | Operation                      | Name               | Rows  |
---------------------------------------------------------------------
|   0 | SELECT STATEMENT               |                    |    10 |
|   1 |  VIEW                          |                    |    10 |
|   2 |   COUNT STOPKEY                |                    |       |
|   3 |    VIEW                        |                    |    10 |
|   4 |     TABLE ACCESS BY INDEX ROWID| TBSSS_SCHEDULES |  5000 |
|   5 |      INDEX RANGE SCAN          | IX_TBSSS_SCH_NEXT  |   100 |
---------------------------------------------------------------------
```

### OBTER
```text
 
---------------------------------------------------------------------
| Id  | Operation                   | Name                  | Rows  |
---------------------------------------------------------------------
|   0 | SELECT STATEMENT            |                       |     1 |
|   1 |  TABLE ACCESS BY INDEX ROWID| TBSSS_SCHEDULES    |     1 |
|   2 |   INDEX UNIQUE SCAN         | PK_TBSSS_SCHEDULES |     1 |
---------------------------------------------------------------------
```

### OBTER_LOCK
```text
 
----------------------------------------------------------------------
| Id  | Operation                    | Name                  | Rows  |
----------------------------------------------------------------------
|   0 | SELECT STATEMENT             |                       |     1 |
|   1 |  FOR UPDATE                  |                       |       |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_SCHEDULES    |     1 |
|   3 |    INDEX UNIQUE SCAN         | PK_TBSSS_SCHEDULES |     1 |
----------------------------------------------------------------------
```

### PAUSAR
```text
 
----------------------------------------------------------------------
| Id  | Operation                    | Name                  | Rows  |
----------------------------------------------------------------------
|   0 | UPDATE STATEMENT             |                       |     1 |
|   1 |  UPDATE                      | TBSSS_SCHEDULES    |       |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_SCHEDULES    |     1 |
|   3 |    INDEX UNIQUE SCAN         | PK_TBSSS_SCHEDULES |     1 |
----------------------------------------------------------------------
```

### PAUSAR_OTIMISTA
```text
 
----------------------------------------------------------------------
| Id  | Operation                    | Name                  | Rows  |
----------------------------------------------------------------------
|   0 | UPDATE STATEMENT             |                       |     1 |
|   1 |  UPDATE                      | TBSSS_SCHEDULES    |       |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_SCHEDULES    |     1 |
|   3 |    INDEX UNIQUE SCAN         | PK_TBSSS_SCHEDULES |     1 |
----------------------------------------------------------------------
```

### RETOMAR
```text
 
------------------------------------------------------------
| Id  | Operation          | Name                  | Rows  |
------------------------------------------------------------
|   0 | UPDATE STATEMENT   |                       |     1 |
|   1 |  UPDATE            | TBSSS_SCHEDULES    |       |
|   2 |   INDEX UNIQUE SCAN| PK_TBSSS_SCHEDULES |     1 |
------------------------------------------------------------
```

### TICKET_STATUS
```text
 
----------------------------------------------------------------
| Id  | Operation                   | Name             | Rows  |
----------------------------------------------------------------
|   0 | SELECT STATEMENT            |                  |     1 |
|   1 |  TABLE ACCESS BY INDEX ROWID| TBSSS_TICKETS    |     1 |
|   2 |   INDEX UNIQUE SCAN         | PK_TBSSS_TICKETS |     1 |
----------------------------------------------------------------
```
