# Script Scheduling Service (SSS) — Atalho de Regras para Agentes (GEMINI.md)

Este arquivo é carregado automaticamente pelo Antigravity no início de toda conversa neste workspace. O `AGENTS.md` (~117 KiB) sofre truncamento na injeção automática após ~24 KB, por volta da §3.2; por isso, a §2 abaixo resume as §3.3 a §9 do `AGENTS.md`. Quando a tarefa tocar execução de processos (§3.2), leia o `AGENTS.md` diretamente.

---

## 1. Ordem de Leitura, Precedência e Regras Críticas

Ordem de leitura: `AGENTS.md`, depois `README.md`.

### Precedência

- `README.md` é a autoridade de negócio, dados e algoritmos; `AGENTS.md` é a autoridade de **como** codificar.
- Conflito entre `AGENTS.md` e `README.md`: **pare e reporte** no campo "Observações" do relatório (`AGENTS.md` §9), sem escolher uma das versões por conta própria.
- `CLAUDE.md` e `GEMINI.md` são só atalhos para os agentes: resumem as regras críticas e não criam regra nova. Divergência deles com `AGENTS.md` ou `README.md`: vale o `AGENTS.md`/`README.md`, e a divergência é reportada.
- `PROJECT_CONTEXT.md` é um resumo do estado do projeto e nunca prevalece sobre os demais.

### Regras Críticas de Execução

- **Compatibilidade:** Python 3.6 estrito. Não use sintaxes modernas proibidas (dataclasses, walrus operator, pos-only args, f-string com `=` do 3.8). F-strings simples são permitidas, porque existem no 3.6 (AGENTS §2.1; CR-034, D8).
- **Segurança & CSP:** Ambiente hermético (AGENTS §2.3). Nenhum `<script>` inline nem atributo de evento inline, nenhum `style=` inline (estilo só por classe CSS), nenhuma CDN nem URL remota. Todos os assets devem ser locais.
- **Relatórios:** Toda entrega deve finalizar com o relatório estrito no padrão de `AGENTS.md` §9, com veredito (PASS/FAIL) e checklist do §8.
- **Modo de Trabalho:** Primeiro apresente o plano completo de execução e aguarde aprovação antes de modificar arquivos críticos.
- **Decisões:** apresente uma decisão por vez, com opções (A, B, ...) e a recomendação técnica justificada.

### Outras regras de postura (`AGENTS.md` §1)

- **Lacuna documental:** se o `README.md` não especifica um comportamento, **pare**, não invente e peça decisão.
- **Escopo estrito:** implemente apenas o item solicitado; não refatore nem renomeie código fora do escopo.
- **Idioma (`CR-016`, README §2.8):** nomes técnicos novos em **inglês** (módulos, funções, variáveis, rotas, chaves de configuração, tabelas, colunas, binds). Textos de tela, mensagens, logs legíveis, docstrings, comentários e documentação em **português** com acentuação correta. O legado em português fica como está e só muda junto com alteração funcional do mesmo trecho.

---

## 2. Resumo do `AGENTS.md` §3.3 a §9

### 2.1 Segredos e PII (`AGENTS.md` §3.3)

- **Proibido em git, código, `config.ini`, banco, testes ou fixtures:** senhas, hashes reais, `cookie_key`, tokens ou chaves privadas. Modelos usam `CHANGE_ME`.
- **Arquivos (`CR-032`, D14/D18/D20):** um `instance/secrets.cfg` por servidor (modo `0600`, dono = usuário do processo) e um `instance/common.ini` com o `[oracle]` comum. Seções: `[oracle] password` (uma senha por servidor, usada pelo web e pelos agentes), `[web] cookie_key` (só o web) e `[environment:<NOME>] password` (só o agente). A seção do outro papel é ignorada.
- **Senhas de usuário:** só `src/sss/core/security.py`: PBKDF2-HMAC-SHA256, sal de 16 bytes, **200.000** iterações, comparação com `hmac.compare_digest`. Troca e redefinição de senha, desativação e troca de perfil incrementam `session_epoch`.
- **Mascaramento (`src/sss/core/masking.py`):** todo segredo carregado é registrado (mínimo de 4 caracteres); logs, mensagens de erro e `log_output` passam pelo filtro.
- **Proibido em logs, HTML ou URL:** senhas, `cookie_key`, hashes de senha, token CSRF, cabeçalho `Cookie` e valores de parâmetros `sensitive = 'Y'`.

### 2.2 Web (`AGENTS.md` §3.4)

- **Entrada:** valor acima do limite ou fora do formato é **recusado**, nunca truncado; o POST grande demais recebe 413 sem ler o corpo (`src/sss/web/app/security.py`, `_check_size` e `body_limit`).
- **CSRF e sessão:** todo `POST` valida o token CSRF com `hmac.compare_digest`; `GET` nunca altera estado. Sessão só no cookie assinado de `src/sss/web/framework/session.py`, revalidada a cada requisição (`session_epoch`, `session_max_hours`).
- **RBAC no servidor:** toda action começa por guarda (`require_login`, `require_func`); item fora do escopo do usuário responde **404**. Administrador só é alterado por administrador.
- **Saída:** sempre escapada com `{{=x}}`; proibido `XML()` com dado de usuário ou de banco.
- **Regex de parâmetro:** só no subconjunto seguro de `params_compiler.validate_registry_regex`.
- **Telas de consulta:** só `GET`, sem gravação nem auditoria.

### 2.3 Banco Oracle 11gR2 (`AGENTS.md` §3.1 e §4)

- **Onde o SQL pode existir:** `src/sss/persistence/oracle/`, `src/sss/cli/init_db.py` e `src/sss/persistence/ddl_builder.py` (fora deles, só o `SELECT SYSDATE FROM DUAL` de `src/sss/cli/probe_driver.py`).
- **Sintaxe 12c+ proibida:** `FETCH FIRST`/`OFFSET` (use a subquery de `ROWNUM`), `GENERATED AS IDENTITY` (use `SEQUENCE` + trigger), `LATERAL`, `CROSS/OUTER APPLY`, `WITH FUNCTION`, `JSON_*`/`IS JSON`, `LISTAGG ... ON OVERFLOW`, `DEFAULT seq.NEXTVAL`; identificador com mais de 30 caracteres.
- **Identificadores e binds (`src/sss/core/sql_ident.py`):** todo valor por bind `:nome`; todo nome físico por `sql_ident`. O prefixo físico é fixo: `tbsdev_` ou `tbsprd_`, escolhido por `SSS_ENV`, senão `SSS_INSTALL_TYPE`, senão a pasta `<TIPO>` (só `PROD` dá `tbsprd_`); `[oracle] table_prefix` é ignorada com aviso. `tbsss_` é só o prefixo lógico (`LOGICAL_PREFIX`, documentação e nomes de constraint em `RepoViolation`).
- **Transações e locks:** `autocommit = False`; toda escrita termina em `COMMIT` ou `ROLLBACK` explícito. `FOR UPDATE WAIT n` (n ≤ 5), ou `FOR UPDATE SKIP LOCKED` no desdobro de agendamentos e no NODE_OFFLINE. Timeout de lock, deadlock e *call timeout* vão em WARN sem stack trace.
- **Concorrência:** toda transição de estado é `UPDATE` condicional com checagem de `rowcount` (ignorar é defeito).
- **Fila (`CR-013`):** a seleção de candidatos (`candidates` em `persistence/oracle/scheduler_queue.py`) lê só a janela de `ix_tbsss_tck_queue`, índice baseado em função `(status, environment, priority, GREATEST(scheduled_at, created_at), id, script_id)` (`sql_ident.FBI_TCK_QUEUE_EXPR`); a query repete a expressão textualmente (`FBI_TCK_QUEUE_START`). Proibido `SELECT *` fora do envelope de paginação. Toda FK tem índice com a FK na liderança.
- **LOBs:** `log_output` (`CLOB`) cresce por `DBMS_LOB.WRITEAPPEND`, até `max_log_size_bytes` (padrão 5 MiB, máximo 64 MiB), com o marcador `[SSS] log truncado no banco; arquivo integral no agente` (`src/sss/scheduler/log_pump.py`). Saídas (`BLOB`) em fatias de até 1 MiB (`tbsss_ticket_output`), lidas em blocos de 256 KiB (`BlobReader`).
- **Status do ticket:** `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, `CANCELLED`.
- **Colunas de registro (`CR-006`):** 19 das 21 tabelas têm `created_at`, `created_by`, `updated_at`, `updated_by`; `tbsss_audit` só tem `created_at` e `tbsss_control` nenhuma. `updated_*` só muda em alteração de negócio (heartbeat, log, PID e contadores não gravam). Ator obrigatório.
- **Auditoria:** a ação auditável passa `audit=` ao repositório, gravada na mesma transação.
- **Versão do esquema:** mudança de esquema incrementa `sql_ident.SCHEMA_VERSION` e traz migração em `src/sss/cli/migrations/`.
- **SQL gerado em ASCII (decisão 16 A):** `ddl_builder.ascii_sql` converte acentos em `UNISTR`; `docs/sql/*.sql` só tem bytes ≤ 127.

### 2.4 Camada Web e Repositórios (`AGENTS.md` §5)

- **Núcleo web próprio (`src/sss/web/framework/`, `CR-021`):** sem web2py (`gluon` proibido) e sem Alpine.js. Módulos: `app`, `errors`, `markup`, `multipart`, `request`, `response`, `routing`, `server`, `session`, `static`, `storage`, `template`.
- **Montagem (`src/sss/web/app/`):** `bootstrap` (configuração, registro dos controllers, views e o `Application`), `context` (requisição por thread), `security` (hooks e guardas) e `errors`. Controllers em `src/sss/web/controllers/` são finos: validam a requisição, chamam `src/sss/services/` e renderizam.
- **Repositórios:** contratos em `src/sss/persistence/contracts/repo_*.py`, exceções em `src/sss/persistence/repo_errors.py`, obtidos só pelo `repo_factory`. Paridade de semântica entre `persistence/oracle/` e `persistence/fake/` (`test_repo_contract.py`); os `oracle/scheduler_*.py` e `oracle/health.py` são do agente e da ferramenta `health`, sem FAKE.

### 2.5 Logging e Robustez (`AGENTS.md` §6)

- **Caminhos de log só por `src/sss/config/log_paths.py`:** aplicação em `log_dir/internal/app/AAAA/MM/DD/HH/MI/<log_name>_<PID>[_<n>].log` (troca por tamanho, sem expurgo automático desde o `CR-030`); execução em `log_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log`.
- **Laço do agente (`src/sss/scheduler/scheduler_loop.py`):** thread única, sem espera dentro das operações, nada bloqueia além de `call_timeout_ms`; fence conferido a cada iteração e após cada chamada ao banco; claim e desdobro param ao gastar `heartbeat_interval_s / 2`. Exceção documentada: `os_platform.stop_ticket` pode aguardar até `kill_grace_s` (5 s) na reconciliação.
- **Relógios:** regra de negócio e agendamento usam o `SYSDATE` do Oracle; prazos internos usam `time.monotonic()`. Proibido `datetime.now()` em agendamento, heartbeat ou timeout.
- **Exceções:** todo `except` registra contexto e stack trace; proibido `except:` ou `except Exception: pass` silenciosos.

### 2.6 Testes e Portões (`AGENTS.md` §1 e §7)

- **Portões:** `make lint` (flake8, 99 colunas) e `make type-check` (mypy estrito), zero achados; a dívida em `.flake8` e `pyproject.toml` **só diminui** (`tests/architecture/test_quality_debt.py`).
- **Suíte (`unittest`; `pytest` proibido):** `make test-unit`, `make test-integration` (o Oracle real só com `SSS_TEST_ORACLE=1`), `make test-functional`, `make test-architecture`, `make test-matrix` (3.6.0, 3.6.15 e 3.13.2).
- **Com `SSS_TEST_ORACLE=1`:** pare o DEV local antes (`make ctl CMD=stop`) para não disputar a fila.

### 2.7 Checklist (§8) e Relatório (§9)

Antes de concluir, valide todos os itens do §8 do `AGENTS.md` e **encerre a resposta com o bloco exato do §9**:

```text
==================================================
RELATÓRIO DE EXECUÇÃO
==================================================
1. Arquivos Criados:
   - caminho/do/arquivo1.ext

2. Arquivos Alterados:
   - caminho/do/arquivo2.ext

3. Testes Executados:
   - tests/unit/<camada>/test_exemplo.py (OK / FALHA / NÃO TESTADO: motivo)

4. Checklist §8:
   - Todos os itens OK | Itens não aplicáveis: <lista> | Itens violados: <lista>

5. Veredito:
   - PASS | FAIL | NÃO TESTADO

6. Observações / Anomalias:
   - Lacunas ou conflitos do README encontrados (bloqueantes)
   - Riscos e pontos de atenção
==================================================
```

---

## 3. Mapa Rápido

### 3.1 Camadas de `src/sss/` (`tests/architecture/test_layers.py`)

Uma camada só importa as que estão abaixo dela, sempre com import qualificado (`from sss.<camada> import <módulo>`): `platform` < `core` < `config` < `persistence` < `ui` < `services` < `web`; o `scheduler` fica acima de `persistence` e não importa `ui`, `services` nem `web`; o `cli` fica no topo.

```text
platform     files_area, path_guard, os_platform/ (posix, ticket_files)
core         cron_parser, masking, params_compiler, rbac, recurrence, security, sql_ident
config       app_context, log_paths, sss_config, sss_logging
persistence  db_conn, ddl_builder, repo_errors, repo_factory, contracts/, oracle/, fake/
ui           ui_helpers, ui_menu
services     admin_crud, admin_*_service, agents, audit, auth, files, input_browse,
             output_browse, permissions, schedules, ticket (*_service)
web          framework/, app/, controllers/, templates/, static/
scheduler    scheduler_loop, executor, env_builder, log_pump, schedule_expansion,
             input_phase, output_phase
cli          run_web, run_scheduler, init_db, generate_sql, check_env, health,
             probe_driver, migrations/  -> invocados por scripts/<nome>.py
```

### 3.2 Banco e Seed

- **21 tabelas (`sql_ident.TABLES`, com o prefixo lógico):** `tbsss_environments`, `tbsss_profiles`, `tbsss_features`, `tbsss_profile_feature`, `tbsss_profile_env`, `tbsss_scripts`, `tbsss_profile_script`, `tbsss_script_env`, `tbsss_users`, `tbsss_parameters`, `tbsss_script_param`, `tbsss_schedules`, `tbsss_tickets`, `tbsss_ticket_answer`, `tbsss_agents`, `tbsss_audit`, `tbsss_control`, `tbsss_ticket_output`, `tbsss_input_upload`, `tbsss_input_delivery`, `tbsss_input_listing`.
- **14 funcionalidades RBAC:** `EXEC_SCRIPT`, `VIEW_LOGS`, `CANCEL_TICKET`, `DOWNLOAD_OUTPUT`, `UPLOAD_INPUT`, `FILES_UPLOAD`, `FILES_DOWNLOAD`, `MANAGE_USERS`, `MANAGE_PROFILES`, `MANAGE_ENVIRONMENTS`, `MANAGE_SCRIPTS`, `MANAGE_PARAMETERS`, `MANAGE_SCHEDULES`, `VIEW_AUDIT`.
- **Perfis do seed (`ddl_builder.DEFAULT_PROFILES`):** `ADMINISTRADOR` (`is_admin = 'Y'`, todas as funcionalidades), `OPERADOR` (execução, logs, cancelamento, entrada, saída e Pasta de Arquivos) e `CONSULTA` (só `VIEW_LOGS`), nos 5 ambientes. Usuários: `admin`, `op.prod` e `consulta`. O perfil `OPERATOR_HML` e o usuário `op.hml` foram aposentados.
- **Driver (`[oracle] driver_mode`):** padrão `auto` (Thin → Thick → cx_Oracle por sondagem); recomendado `thick`.

### 3.3 Instalação

- **Raiz:** `/portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service` (DEV e PROD). Configuração em `instance/<nome>/config.ini` (modelos em `instance/exemplos/`); dados em `var/<nome>/`.
- **Processos (1 web + 5 agentes):** `web0001`; `agente0001` (`GFPREPROD`), `agente0002` (`CLONE2`), `agente0003` (`CLONE1`), `agente0004` (`CLONE6`), `agente0005` (`CLONE7`).
- **Scripts:** as ferramentas de homologação ficam em `dev/others/homologation/tools/`; em `<RAIZ>/scripts_ambiente/` ficam os scripts dos ambientes (exemplos, `utilitarios/` do seed e `diagnostico/` usados pelos casos de homologação).

### 3.4 Documentação (`docs/`)

- **Manuais:** `DEPLOYMENT.md` (normativo, testado por `test_deployment_doc.py`), `DEPLOYMENT-SERVER.md`, `DEV_ENVIRONMENT.md`, `HOMOLOGATION_RUNBOOK.md`, `UTILITY_SCRIPTS.md`, `ADMIN_CRUD_PATTERN.md`.
- **`docs/explain/`:** 6 planos EXPLAIN: `AUDIT_AGENTS.md`, `CATALOG.md`, `RBAC_USERS.md`, `SCHEDULER.md`, `SCHEDULES.md`, `TICKETS.md`.
- **`docs/architecture/`:** os CRs e `DEPLOYMENT-history.md`.
- **`docs/sql/`:** `01_deploy_sss_<owner>_<prefixo>.sql`, `02_rollback_sss_<owner>_<prefixo>.sql` e `99_validate_deploy_<owner>_<prefixo>.sql` (gerados pelo `generate_sql`, 100% ASCII).
