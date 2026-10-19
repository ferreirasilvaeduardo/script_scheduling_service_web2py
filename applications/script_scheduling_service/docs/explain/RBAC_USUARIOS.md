# SSS — Explain Plan: Agregado RBAC_USUARIOS (F7.3)

Este documento registra as consultas SQL estáticas executadas pelos repositórios `RepoUsuariosOracle` e `RepoRbacOracle` no Oracle 11gR2, mapeando os índices esperados e a garantia de desempenho.

> **Parâmetros Dinâmicos de Esquema e Tabela (README §9.1 e §12.1):**
> * `{owner}`: configurado em `[oracle] owner` no `instance/config.ini` (ex.: `openrisow`). Validado por `^[A-Za-z][A-Za-z0-9_]{0,29}$`.
> * `{prefixo}`: configurado em `[oracle] table_prefix` no `instance/config.ini` (padrão: `tbsss_`). Validado por `^[a-z][a-z0-9_]{0,7}$` (CR-007 R-31, CR-008 R-28).
>
> Nenhum SQL dos repositórios possui nomes de tabela, sequence ou constraint fixos no código; todos são qualificados dinamicamente via `BaseRepoOracle.qualificar_tabela(entidade)`, `qualificar_sequence(entidade)` e `nome_constraint(tipo, entidade, sufixo)` com base em `modules/sql_ident.py`.

---

## 1. Consultas de Usuários (`{prefixo}usuarios`)

### 1.1 Leitura por Login (`obter_por_login`)
```sql
SELECT id, login, nome, senha_hash, perfil_id, tentativas_falha, bloqueado_ate,
       ultimo_login, senha_alterada_em, sessao_epoch, ativo,
       created_at, created_by, updated_at, updated_by
  FROM {owner}.{prefixo}usuarios
 WHERE login = :login
```
* **Acesso esperado:** `INDEX UNIQUE SCAN` em `uk_{prefixo}usr_login` (`login`).

---

### 1.2 Leitura por ID (`obter_por_id`)
```sql
SELECT id, login, nome, senha_hash, perfil_id, tentativas_falha, bloqueado_ate,
       ultimo_login, senha_alterada_em, sessao_epoch, ativo,
       created_at, created_by, updated_at, updated_by
  FROM {owner}.{prefixo}usuarios
 WHERE id = :id
```
* **Acesso esperado:** `INDEX UNIQUE SCAN` em `pk_{prefixo}usuarios` (`id`).

---

### 1.3 Estado de Sessão (`obter_estado_sessao`)
```sql
SELECT u.id, u.login, u.nome, u.ativo,
       p.id, p.nome, p.ativo, p.is_admin, p.perm_versao, u.sessao_epoch
  FROM {owner}.{prefixo}usuarios u
  JOIN {owner}.{prefixo}perfis p ON p.id = u.perfil_id
 WHERE u.id = :usuario_id
```
* **Acesso esperado:** `INDEX UNIQUE SCAN` em `pk_{prefixo}usuarios` seguido de `INDEX UNIQUE SCAN` em `pk_{prefixo}perfis` por `NESTED LOOPS`.

---

### 1.4 Listagem Paginada (`listar`)
```sql
SELECT * FROM (
  SELECT a.*, ROWNUM rn FROM (
    SELECT id, login, nome, senha_hash, perfil_id, tentativas_falha, bloqueado_ate,
           ultimo_login, senha_alterada_em, sessao_epoch, ativo,
           created_at, created_by, updated_at, updated_by
      FROM {owner}.{prefixo}usuarios
     WHERE 1=1
       AND LOWER(login) LIKE :login_f
       AND LOWER(nome) LIKE :nome_f
       AND perfil_id = :perfil_f
       AND ativo = :ativo_f
       AND bloqueado_ate IS NOT NULL AND bloqueado_ate > :bloq_f
     ORDER BY login ASC, id ASC
  ) a WHERE ROWNUM <= :fim
) WHERE rn > :inicio
```
* **Contagem com teto:**
```sql
SELECT COUNT(*) FROM (
  SELECT id FROM {owner}.{prefixo}usuarios
   WHERE 1=1 [filtros] AND ROWNUM <= 10001
)
```
* **Acesso esperado:** `COUNT STOPKEY` e `VIEW` com `WINDOW SORT PUSHED RANK` / `INDEX FULL SCAN` em `uk_{prefixo}usr_login`.

---

### 1.5 Lock de Administradores Ativos (`admins_ativos_bloquear`, README §4.3.B)
```sql
SELECT u.id
  FROM {owner}.{prefixo}usuarios u
  JOIN {owner}.{prefixo}perfis p ON p.id = u.perfil_id
 WHERE u.ativo = 'S' AND p.ativo = 'S' AND p.is_admin = 'S'
   FOR UPDATE OF u.ativo WAIT 5
```
* **Acesso esperado:** `TABLE ACCESS BY INDEX ROWID` em `{prefixo}perfis` e `{prefixo}usuarios` com `FOR UPDATE`.

---

## 2. Consultas de RBAC e Perfis (`{prefixo}perfis`)

### 2.1 Leitura de Perfil por ID (`perfis_obter`)
```sql
SELECT id, nome, descricao, is_admin, perm_versao, ativo,
       created_at, created_by, updated_at, updated_by
  FROM {owner}.{prefixo}perfis
 WHERE id = :id
```
* **Acesso esperado:** `INDEX UNIQUE SCAN` em `pk_{prefixo}perfis` (`id`).

---

### 2.2 Listagem Paginada de Perfis (`perfis_listar`)
```sql
SELECT * FROM (
  SELECT a.*, ROWNUM rn FROM (
    SELECT id, nome, descricao, is_admin, perm_versao, ativo,
           created_at, created_by, updated_at, updated_by
      FROM {owner}.{prefixo}perfis
     WHERE 1=1
       AND LOWER(nome) LIKE :nome_f
       AND ativo = :ativo_f
       AND is_admin = :is_admin_f
     ORDER BY nome ASC, id ASC
  ) a WHERE ROWNUM <= :fim
) WHERE rn > :inicio
```
* **Acesso esperado:** `INDEX FULL SCAN` em `uk_{prefixo}per_nome` com `COUNT STOPKEY`.

---

### 2.3 Matriz de Permissões (`matriz_obter`)
```sql
SELECT funcionalidade_id FROM {owner}.{prefixo}perfil_func WHERE perfil_id = :id ORDER BY funcionalidade_id ASC;
SELECT ambiente_id FROM {owner}.{prefixo}perfil_amb WHERE perfil_id = :id ORDER BY ambiente_id ASC;
SELECT script_id FROM {owner}.{prefixo}perfil_scr WHERE perfil_id = :id ORDER BY script_id ASC;
```
* **Acesso esperado:** `INDEX RANGE SCAN` nas UKs / FKs que cobrem a coluna líder `perfil_id` (`uk_{prefixo}pfnc_per_fnc`, `uk_{prefixo}pamb_per_amb`, `uk_{prefixo}pscr_per_scr`).

---

### 2.4 Catálogo de Funcionalidades (`funcionalidades_listar`)
```sql
SELECT id, codigo, nome, modulo, descricao, ativo,
       created_at, created_by, updated_at, updated_by
  FROM {owner}.{prefixo}funcionalidades
 ORDER BY modulo ASC, codigo ASC, id ASC
```
* **Acesso esperado:** `TABLE ACCESS FULL` sobre tabela estática de catálogo de 14 linhas (aceitável e recomendada pelo CBO para tabelas minúsculas com menos de 1 bloco).

---

## 3. Avaliação de Execução do Plano

**Plano: NÃO TESTADO**

* **Motivo:** A variável `SSS_TEST_DSN` não aponta para um banco Oracle com schema descartável configurado nesta sessão.
* Todas as queries foram construídas estritamente com índices em suas colunas líderes (`id`, `login`, `nome`, `perfil_id`), ordenação determinística e proteção contra `TABLE ACCESS FULL` em tabelas com potencial de crescimento volumétrico.
