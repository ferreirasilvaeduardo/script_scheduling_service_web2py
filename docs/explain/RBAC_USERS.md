# SSS — Explain Plan: Agregado RBAC_USUARIOS (F7.3)

Este documento registra as consultas SQL estáticas executadas pelos repositórios `RepoUsersOracle` e `RepoRbacOracle` no Oracle 11gR2, mapeando os índices esperados e a garantia de desempenho.

> **Parâmetros Dinâmicos de Esquema e Tabela (README §9.1 e §12.1):**
> * `{owner}`: configurado em `[oracle] owner` no `instance/config.ini` (ex.: `openrisow`). Validado por `^[A-Za-z][A-Za-z0-9_]{0,29}$`.
> * `{prefixo}`: configurado em `[oracle] table_prefix` no `instance/config.ini` (padrão: `tbsss_`). Validado por `^[a-z][a-z0-9_]{0,7}$` (CR-007 R-31, CR-008 R-28).
>
> Nenhum SQL dos repositórios possui nomes de tabela, sequence ou constraint fixos no código; todos são qualificados dinamicamente via `BaseRepoOracle.qualify_table(entity)`, `qualify_sequence(entity)` e `constraint_name(kind, entity, suffix)` com base em `modules/sql_ident.py`.

---

## 1. Consultas de Usuários (`{prefixo}users`)

### 1.1 Leitura por Login (`get_by_login`)
```sql
SELECT id, login, name, password_hash, profile_id, failed_attempts, locked_until,
       last_login_at, password_changed_at, session_epoch, active,
       created_at, created_by, updated_at, updated_by
  FROM {owner}.{prefixo}users
 WHERE login = :login
```
* **Acesso esperado:** `INDEX UNIQUE SCAN` em `uk_{prefixo}usr_login` (`login`).

---

### 1.2 Leitura por ID (`get_by_id`)
```sql
SELECT id, login, name, password_hash, profile_id, failed_attempts, locked_until,
       last_login_at, password_changed_at, session_epoch, active,
       created_at, created_by, updated_at, updated_by
  FROM {owner}.{prefixo}users
 WHERE id = :id
```
* **Acesso esperado:** `INDEX UNIQUE SCAN` em `pk_{prefixo}users` (`id`).

---

### 1.3 Estado de Sessão (`get_session_state`)
```sql
SELECT u.id, u.login, u.name, u.active,
       p.id, p.name, p.active, p.is_admin, p.perm_version, u.session_epoch
  FROM {owner}.{prefixo}users u
  JOIN {owner}.{prefixo}profiles p ON p.id = u.profile_id
 WHERE u.id = :user_id
```
* **Acesso esperado:** `INDEX UNIQUE SCAN` em `pk_{prefixo}users` seguido de `INDEX UNIQUE SCAN` em `pk_{prefixo}profiles` por `NESTED LOOPS`.

---

### 1.4 Listagem Paginada (`list`)
```sql
SELECT * FROM (
  SELECT a.*, ROWNUM rn FROM (
    SELECT id, login, name, password_hash, profile_id, failed_attempts, locked_until,
           last_login_at, password_changed_at, session_epoch, active,
           created_at, created_by, updated_at, updated_by
      FROM {owner}.{prefixo}users
     WHERE 1=1
       AND LOWER(login) LIKE :login_f
       AND LOWER(name) LIKE :name_f
       AND profile_id = :profile_f
       AND active = :active_f
       AND locked_until IS NOT NULL AND locked_until > :locked_f
     ORDER BY login ASC, id ASC
  ) a WHERE ROWNUM <= :end_ts
) WHERE rn > :start_ts
```
* **Contagem com teto:**
```sql
SELECT COUNT(*) FROM (
  SELECT id FROM {owner}.{prefixo}users
   WHERE 1=1 [filtros] AND ROWNUM <= 10001
)
```
* **Acesso esperado:** `COUNT STOPKEY` e `VIEW` com `WINDOW SORT PUSHED RANK` / `INDEX FULL SCAN` em `uk_{prefixo}usr_login`.

---

### 1.5 Lock de Administradores Ativos (`lock_active_admins`, README §4.3.B)
```sql
SELECT u.id
  FROM {owner}.{prefixo}users u
  JOIN {owner}.{prefixo}profiles p ON p.id = u.profile_id
 WHERE u.active = 'Y' AND p.active = 'Y' AND p.is_admin = 'Y'
   FOR UPDATE OF u.active WAIT 5
```
* **Acesso esperado:** `TABLE ACCESS BY INDEX ROWID` em `{prefixo}profiles` e `{prefixo}users` com `FOR UPDATE`.

---

## 2. Consultas de RBAC e Perfis (`{prefixo}profiles`)

### 2.1 Leitura de Perfil por ID (`profiles_get`)
```sql
SELECT id, name, description, is_admin, perm_version, active,
       created_at, created_by, updated_at, updated_by
  FROM {owner}.{prefixo}profiles
 WHERE id = :id
```
* **Acesso esperado:** `INDEX UNIQUE SCAN` em `pk_{prefixo}profiles` (`id`).

---

### 2.2 Listagem Paginada de Perfis (`profiles_list`)
```sql
SELECT * FROM (
  SELECT a.*, ROWNUM rn FROM (
    SELECT id, name, description, is_admin, perm_version, active,
           created_at, created_by, updated_at, updated_by
      FROM {owner}.{prefixo}profiles
     WHERE 1=1
       AND LOWER(name) LIKE :name_f
       AND active = :active_f
       AND is_admin = :is_admin_f
     ORDER BY name ASC, id ASC
  ) a WHERE ROWNUM <= :end_ts
) WHERE rn > :start_ts
```
* **Acesso esperado:** `INDEX FULL SCAN` em `uk_{prefixo}prf_name` com `COUNT STOPKEY`.

---

### 2.3 Matriz de Permissões (`matrix_get`)
```sql
SELECT feature_id FROM {owner}.{prefixo}profile_feature WHERE profile_id = :id ORDER BY feature_id ASC;
SELECT environment_id FROM {owner}.{prefixo}profile_env WHERE profile_id = :id ORDER BY environment_id ASC;
SELECT script_id FROM {owner}.{prefixo}profile_script WHERE profile_id = :id ORDER BY script_id ASC;
```
* **Acesso esperado:** `INDEX RANGE SCAN` nas UKs / FKs que cobrem a coluna líder `profile_id` (`uk_{prefixo}pfea_prf_fea`, `uk_{prefixo}penv_prf_env`, `uk_{prefixo}pscr_prf_scr`).

---

### 2.4 Catálogo de Funcionalidades (`features_list`)
```sql
SELECT id, code, name, module, description, active,
       created_at, created_by, updated_at, updated_by
  FROM {owner}.{prefixo}features
 ORDER BY module ASC, code ASC, id ASC
```
* **Acesso esperado:** `TABLE ACCESS FULL` sobre tabela estática de catálogo de 14 linhas (aceitável e recomendada pelo CBO para tabelas minúsculas com menos de 1 bloco).

---

## 3. Avaliação de Execução do Plano

**Plano: TESTADO em 2026-10-19**, Oracle 19.24 (banco `GFPR`), owner `openrisow` em modo compartilhado (`SSS_TEST_SCHEMA_COMPARTILHADO=1`, README §2.5), driver Thin (python-oracledb 1.4.2). Os planos saíram de `EXPLAIN PLAN SET STATEMENT_ID … FOR <query>` + `DBMS_XPLAN.DISPLAY`, sem executar os comandos. O texto `{owner}` substitui `OPENRISOW`.

* **Sem `TABLE ACCESS FULL` em `tbsss_tickets` nem em `tbsss_audit`:** conforme: o agregado não lê `tbsss_tickets`. A auditoria só recebe `INSERT`, sem leitura.
* **`TABLE ACCESS FULL` aceitável:** só nas listagens de cadastro (`tbsss_users`, `tbsss_profiles`), com `COUNT STOPKEY`/`SORT ORDER BY STOPKEY`, no catálogo canônico `tbsss_features` (10 linhas) e no lado `tbsss_profiles` do `lock_active_admins`.
* **Leituras por chave e transições:** `get_by_login` pela `UK_…_USR_LOGIN`; `get_session_state` e a matriz pelas PKs e pelas UKs de líder `profile_id`.

### Planos registrados

### usuarios.obter_por_login [1]
```text
 
------------------------------------------------------------------
| Id  | Operation                   | Name               | Rows  |
------------------------------------------------------------------
|   0 | SELECT STATEMENT            |                    |     1 |
|   1 |  TABLE ACCESS BY INDEX ROWID| TBSSS_USERS     |     1 |
|   2 |   INDEX UNIQUE SCAN         | UK_TBSSS_USR_LOGIN |     1 |
------------------------------------------------------------------
```

### usuarios.obter_estado_sessao [1]
```text
 
------------------------------------------------------------------
| Id  | Operation                    | Name              | Rows  |
------------------------------------------------------------------
|   0 | SELECT STATEMENT             |                   |     1 |
|   1 |  NESTED LOOPS                |                   |     1 |
|   2 |   TABLE ACCESS BY INDEX ROWID| TBSSS_USERS    |     1 |
|   3 |    INDEX UNIQUE SCAN         | PK_TBSSS_USERS |     1 |
|   4 |   TABLE ACCESS BY INDEX ROWID| TBSSS_PROFILES      |     1 |
|   5 |    INDEX UNIQUE SCAN         | PK_TBSSS_PROFILES   |     1 |
------------------------------------------------------------------
```

### usuarios.listar (login, ativo) [1]
```text
 
-------------------------------------------------------
| Id  | Operation            | Name           | Rows  |
-------------------------------------------------------
|   0 | SELECT STATEMENT     |                |     1 |
|   1 |  SORT AGGREGATE      |                |     1 |
|   2 |   VIEW               |                |     1 |
|   3 |    COUNT STOPKEY     |                |       |
|   4 |     TABLE ACCESS FULL| TBSSS_USERS |     1 |
-------------------------------------------------------
```

### usuarios.listar (login, ativo) [2]
```text
 
-----------------------------------------------------------
| Id  | Operation                | Name           | Rows  |
-----------------------------------------------------------
|   0 | SELECT STATEMENT         |                |     1 |
|   1 |  VIEW                    |                |     1 |
|   2 |   COUNT STOPKEY          |                |       |
|   3 |    VIEW                  |                |     1 |
|   4 |     SORT ORDER BY STOPKEY|                |     1 |
|   5 |      TABLE ACCESS FULL   | TBSSS_USERS |     1 |
-----------------------------------------------------------
```

### usuarios.listar (bloqueados) [1]
```text
 
-------------------------------------------------------
| Id  | Operation            | Name           | Rows  |
-------------------------------------------------------
|   0 | SELECT STATEMENT     |                |     1 |
|   1 |  SORT AGGREGATE      |                |     1 |
|   2 |   VIEW               |                |     1 |
|   3 |    COUNT STOPKEY     |                |       |
|   4 |     TABLE ACCESS FULL| TBSSS_USERS |     1 |
-------------------------------------------------------
```

### usuarios.listar (bloqueados) [2]
```text
 
-----------------------------------------------------------
| Id  | Operation                | Name           | Rows  |
-----------------------------------------------------------
|   0 | SELECT STATEMENT         |                |     1 |
|   1 |  VIEW                    |                |     1 |
|   2 |   COUNT STOPKEY          |                |       |
|   3 |    VIEW                  |                |     1 |
|   4 |     SORT ORDER BY STOPKEY|                |     1 |
|   5 |      TABLE ACCESS FULL   | TBSSS_USERS |     1 |
-----------------------------------------------------------
```

### rbac.perfis_listar [1]
```text
 
--------------------------------------------------------
| Id  | Operation          | Name              | Rows  |
--------------------------------------------------------
|   0 | SELECT STATEMENT   |                   |     1 |
|   1 |  SORT AGGREGATE    |                   |     1 |
|   2 |   VIEW             |                   |     1 |
|   3 |    COUNT STOPKEY   |                   |       |
|   4 |     INDEX FULL SCAN| UK_TBSSS_PRF_NAME |     1 |
--------------------------------------------------------
```

### rbac.perfis_listar [2]
```text
 
---------------------------------------------------------
| Id  | Operation                | Name         | Rows  |
---------------------------------------------------------
|   0 | SELECT STATEMENT         |              |     1 |
|   1 |  VIEW                    |              |     1 |
|   2 |   COUNT STOPKEY          |              |       |
|   3 |    VIEW                  |              |     1 |
|   4 |     SORT ORDER BY STOPKEY|              |     1 |
|   5 |      TABLE ACCESS FULL   | TBSSS_PROFILES |     1 |
---------------------------------------------------------
```

### rbac.matriz_obter [1]
```text
 
-----------------------------------------------------
| Id  | Operation         | Name            | Rows  |
-----------------------------------------------------
|   0 | SELECT STATEMENT  |                 |     1 |
|   1 |  INDEX UNIQUE SCAN| PK_TBSSS_PROFILES |     1 |
-----------------------------------------------------
```

### rbac.matriz_obter [2]
```text
 
----------------------------------------------------------
| Id  | Operation        | Name                  | Rows  |
----------------------------------------------------------
|   0 | SELECT STATEMENT |                       |     4 |
|   1 |  INDEX RANGE SCAN| UK_TBSSS_PFEA_PRF_FEA |     4 |
----------------------------------------------------------
```

### rbac.matriz_obter [3]
```text
 
----------------------------------------------------------
| Id  | Operation        | Name                  | Rows  |
----------------------------------------------------------
|   0 | SELECT STATEMENT |                       |     5 |
|   1 |  INDEX RANGE SCAN| UK_TBSSS_PENV_PRF_ENV |     5 |
----------------------------------------------------------
```

### rbac.matriz_obter [4]
```text
 
----------------------------------------------------------
| Id  | Operation        | Name                  | Rows  |
----------------------------------------------------------
|   0 | SELECT STATEMENT |                       |    14 |
|   1 |  INDEX RANGE SCAN| UK_TBSSS_PSCR_PRF_SCR |    14 |
----------------------------------------------------------
```

### rbac.admins_ativos_bloquear [1]
```text
 
-------------------------------------------------------------------
| Id  | Operation                      | Name             | Rows  |
-------------------------------------------------------------------
|   0 | SELECT STATEMENT               |                  |     1 |
|   1 |  FOR UPDATE                    |                  |       |
|   2 |   BUFFER SORT                  |                  |       |
|   3 |    NESTED LOOPS                |                  |     1 |
|   4 |     NESTED LOOPS               |                  |     1 |
|   5 |      TABLE ACCESS FULL         | TBSSS_PROFILES     |     1 |
|   6 |      INDEX RANGE SCAN          | IX_TBSSS_USR_PRF |     1 |
|   7 |     TABLE ACCESS BY INDEX ROWID| TBSSS_USERS   |     1 |
-------------------------------------------------------------------
```

### rbac.funcionalidades_listar [1]
```text
 
------------------------------------------------------------
| Id  | Operation          | Name                  | Rows  |
------------------------------------------------------------
|   0 | SELECT STATEMENT   |                       |    10 |
|   1 |  SORT ORDER BY     |                       |    10 |
|   2 |   TABLE ACCESS FULL| TBSSS_FEATURES |    10 |
------------------------------------------------------------
```
