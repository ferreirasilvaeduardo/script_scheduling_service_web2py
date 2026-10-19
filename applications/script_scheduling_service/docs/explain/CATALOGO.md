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

**Plano: NÃO TESTADO**

* **Motivo:** não há schema Oracle descartável `SSS_TEST_*` disponível nesta sessão. O túnel do `[oracle] dsn` responde, mas o owner configurado (`openrisow`) não é descartável, e a guarda `preparar_schema_descartavel` recusa usá-lo.
* **Como gerar os planos:** com o schema descartável, rode `EXPLAIN PLAN FOR <query>` e depois `SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY)` para cada consulta acima. Registre a saída nesta seção, substituindo este aviso.
