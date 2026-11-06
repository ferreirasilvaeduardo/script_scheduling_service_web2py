# Script Scheduling Service (SSS) — Memória Permanente e Regras Completas (GEMINI.md)

Este arquivo é carregado automaticamente pelo Antigravity no início de toda conversa neste workspace. Ele complementa o `AGENTS.md` (que tem ~118 KB e sofre truncamento na injeção automática após ~24 KB, na altura da §3.3) e trabalha em conjunto com o `PROJECT_CONTEXT.md`.

---

## 1. Hierarquia de Autoridade e Postura

1. **`README.md`** — Autoridade máxima de negócio, modelo de dados, máquina de estados e algoritmos.
2. **`AGENTS.md`** — Autoridade de **como** codificar, testar, validar segurança e reportar entregas.
3. **`CLAUDE.md`** — Postura de trabalho, fluxo de decisões com o responsável e regras de operação/git.
4. **`PROJECT_CONTEXT.md`** — Memória viva do projeto: status das instalações, ADRs 001–012, pendências e catálogo completo de módulos, banco e `docs/`.

**Regras de ouro:**
* **Conflito ou lacuna documental:** se `AGENTS.md` conflitar com `README.md`, ou se o `README.md` não especificar um comportamento, **pare imediatamente**, não invente e reporte para decisão.
* **Decisões com o usuário (`CLAUDE.md`):** apresente **uma dúvida por vez**, com opções claras (A, B, ...) e a recomendação técnica justificada.
* **Escopo estrito:** implemente apenas o item solicitado; não refatore nem renomeie código fora do escopo.
* **Idioma (`CR-016`):** código novo nasce com identificadores em **inglês** (módulos, classes, funções, variáveis, rotas, chaves INI, colunas/tabelas SQL, binds). Textos de tela, mensagens ao usuário, logs legíveis, docstrings, comentários e documentação ficam em **português** com acentuação UTF-8 correta. O legado em português que restou após 2026-10-22 fica como está e só muda junto com alteração funcional do mesmo trecho.

---

## 2. Regras do `AGENTS.md` §§3.3–9 (Complemento da Parte Truncada)

### 2.1 Segredos, Credenciais e PII (`AGENTS.md` §3.3)
* **Proibido em git/código:** senhas, hashes reais, `cookie_key`, tokens ou chaves privadas. Modelos usam `CHANGE_ME`.
* **Arquivos de segredo (`CR-032`, D14/D18):** `instance/secrets.cfg` único por servidor (modo `0600`, dono igual ao UID do processo; recusado se grupo/outros tiverem permissão ou em diretório gravável por outros) e `instance/common.ini` para `[oracle]`. Cada processo lê apenas as chaves do seu papel (`agent` lê `agent_password`; `web` lê `web_password` e `cookie_key`).
* **Senhas de usuário:** `PBKDF2-HMAC-SHA256` (`hashlib.pbkdf2_hmac`) com sal de 16 bytes (`secrets.SystemRandom`), mínimo de `310_000` iterações e comparação em tempo constante (`hmac.compare_digest`). Troca de senha, redefinição, desativação ou mudança de perfil incrementa `session_epoch`.
* **Mascaramento (`src/sss/core/masking.py`):** todo log de execução e de aplicação passa pelo filtro em fluxo com janela de retenção `len(maior_segredo) - 1` entre blocos (`flush()` só no encerramento). Valores sensíveis têm no mínimo 4 caracteres (`CR-008`, R-07).
* **Proibido em logs, HTML ou URL:** senhas, `cookie_key`, `password_hash`, tokens de sessão/CSRF, DSN completo e valores de parâmetros `is_sensitive = 'Y'`. A resposta de parâmetro sensível é apagada do banco ao fim da execução (`FINISHED`, `FAILED`, `CANCELED`, `STOPPED`).

### 2.2 Segurança Web e Entrada de Dados (`AGENTS.md` §3.4)
* **Limites de entrada:** toda entrada tem tamanho máximo validado antes do processamento e é **recusada** (nunca truncada) se exceder (`src/sss/web/app/security.py`, `_check_size` antes de ler `request.post_vars`, retornando HTTP 413). O limite grande `files_upload_max_bytes` vale apenas em `files/upload` com sessão autenticada (`security.body_limit`).
* **CSRF e Sessão:** todo `POST`/`PUT`/`DELETE` valida token CSRF (em formulário ou cabeçalho `X-CSRF-Token`) com `hmac.compare_digest`. Sessão em cookie assinado HMAC-SHA256 (`HttpOnly`, `SameSite=Lax`, `Secure` quando HTTPS), revalidando `is_active`, `session_epoch`, `profile_id` e `session_max_hours` a cada requisição.
* **RBAC no servidor:** toda rota valida autenticação e permissão no servidor (esconder botão na UI não é controle de acesso). Recursos fora do escopo de ambiente/script nas telas de consulta, Saídas (`DOWNLOAD_OUTPUT`), Entrada (`UPLOAD_INPUT`) e Pasta de Arquivos (`FILES_UPLOAD`/`FILES_DOWNLOAD`) retornam **404** (nunca 403).
* **Regex segura (`src/sss/core/params_compiler.py`):** `validation_regex` aceita apenas o subconjunto seguro (sem repetição aninhada como `(a+)+`, sem backreferences `\1`, sem lookaround e com tempo de `re.fullmatch` limitado).
* **Telas de consulta:** usam exclusivamente `GET` e nunca gravam nem geram auditoria.

### 2.3 Banco de Dados Oracle 11gR2 (`AGENTS.md` §4)
* **Onde o SQL pode existir:** exclusivamente em `src/sss/persistence/oracle/`, `src/sss/cli/init_db.py` e `src/sss/persistence/ddl_builder.py` (varrido por `test_sql_oracle11g.py`).
* **Piso Oracle 11gR2 (proibido 12c+):** proibido `FETCH FIRST n ROWS ONLY` / `OFFSET` (usar subquery com `ROWNUM`), `GENERATED AS IDENTITY` (usar `SEQUENCE` + `TRIGGER`), `LATERAL`, `CROSS APPLY`, `OUTER APPLY`, `WITH` contendo `FUNCTION`/`PROCEDURE`, `JSON_VALUE`/`JSON_QUERY`/`JSON_TABLE`/`IS JSON`, `APPROX_COUNT_DISTINCT`, `LISTAGG(... ON OVERFLOW ...)`, `DEFAULT ... ON NULL`, `TRUNCATE TABLE ... CASCADE` e identificadores `> 30` bytes.
* **Identificadores e Binds (`src/sss/core/sql_ident.py`):** todo nome físico passa por `sql_ident` (`owner` validado; prefixo de tabela não parametrizado, fixo pelo ambiente: `tbsdev_` em DEV e `tbsprd_` em PROD; todo identificador físico `<= 30` chars). Todo valor vai por bind `:nome`.
* **Transações e Locks:** `autocommit = False` sempre; toda escrita termina com `COMMIT` ou `ROLLBACK` explícito. Em bloco `except`, registrar `logger.exception` com código ORA e stack trace **antes** do `ROLLBACK`. `SELECT ... FOR UPDATE` sempre com `WAIT n` (`n <= 5`), exceto o desdobro de agendamentos em `12c+` que usa `SKIP LOCKED` com fallback 11g.
* **Transições condicionais e Concorrência:** toda mudança de estado de ticket, agendamento ou cadastro confere `cursor.rowcount == 1` (se `0`, faz `ROLLBACK` e lança `RepoConflict`). `RepoViolation` expõe sempre o nome lógico da constraint com prefixo `tbsss_` (`sql_ident.logical_object_name`).
* **Fila e Índices (`CR-013`):** busca de candidatos do daemon em 3 leituras leves (`candidates` em `persistence/oracle/scheduler_queue.py`) usando `ix_tbsss_tck_queue` (`status, env_id, priority, effective_priority_at, scheduled_at, id`), sem ler `CLOB`/`BLOB` e sem `SELECT *` fora do envelope de paginação. Toda FK tem índice com as colunas da FK na liderança (`test_db_schema.py`).
* **LOBs e Datas:** `log_text` (`CLOB`) incrementado por `DBMS_LOB.WRITEAPPEND` com offset em **caracteres** (não bytes) e truncado em 10 MiB com marcador `\n[SSS] LOG TRUNCADO...`. Saídas (`BLOB`) gravadas em fatias de até 1 MiB (`tbsss_ticket_output`) e lidas em blocos de 256 KiB (`BlobReader`). Datas de negócio usam `SYSDATE`/`SYSTIMESTAMP` do Oracle e binds de data usam `setinputsizes` (`TIPO_DATE`) sem microssegundos.
* **Auditoria e Colunas de Registro (`CR-006`):** toda ação auditável passa `audit=AuditEntry(...)` para o repositório gravar na **mesma transação**. Todas as 21 tabelas mantêm `created_at`, `created_by`, `updated_at`, `updated_by` (`updated_*` só muda quando há alteração real de coluna de negócio; batimento de heartbeat sem mudança não suja `updated_*`).
* **DDL em ASCII (`decisão 16 A`):** `ddl_builder.ascii_sql` converte literais acentuados em `UNISTR('\XXXX')` e remove acentos de comentários/`PROMPT`, garantindo que `docs/sql/*.sql` tenha apenas ASCII puro (`<= 127`).

### 2.4 Camada Web e Repositórios (`AGENTS.md` §5)
* **Núcleo web próprio (`src/sss/web/framework/`, `CR-021`):** sem `web2py` (`gluon` é proibido em todo o repositório) e sem Alpine.js. Módulos do framework: `server.py`, `wsgi.py`, `router.py`, `request.py`, `response.py`, `multipart.py`, `session.py`, `template.py` (único local com `compile`/`exec`, restrito a `src/sss/web/templates/`), `static.py` e `html.py`.
* **Montagem da aplicação (`src/sss/web/app/`):** `factory.py`, `context.py`, `security.py`, `layout.py`, `errors.py`. Controllers em `src/sss/web/controllers/` são finos (validam entrada HTTP, chamam `src/sss/services/` e renderizam template/JSON).
* **Repositórios (`src/sss/persistence/`):** `contracts/` define DTOs, protocolos e exceções (`RepoNotFound`, `RepoConflict`, `RepoViolation`, `RepoUnavailable`). Toda implementação nova ou alterada deve manter paridade entre `persistence/oracle/` e `persistence/fake/` (testada por `test_repo_contract.py`).

### 2.5 Logging, Tempo e Robustez do Daemon (`AGENTS.md` §6)
* **Logs da aplicação:** gravados em `log_dir/internal/app/AAAA/MM/DD/HH/MI/<processo>_<PID>.log` (pastas `0750`, arquivos `0640`, rotação por minuto e por tamanho com sufixo numérico, sem expurgo automático desde o `CR-030`).
* **Laço do agente (`src/sss/scheduler/loop.py`):** thread única, sem `time.sleep` dentro de operações e sem bloqueio acima de `call_timeout_ms`.
  * *Única exceção documentada (`ADR 011` / decisão 19 C):* `os_platform.stop_ticket` na reconciliação de ticket "talvez iniciado" achado na varredura pode aguardar até `kill_grace_s` (5 s).
* **Fencing e Orçamento (`CR-007`):** o *fence* monotônico é conferido a cada iteração e após cada chamada ao banco; se o agente perdeu o lease, encerra imediatamente os grupos de processos locais e suspende claims até renovar o heartbeat. Claim e desdobro param ao consumir `heartbeat_interval_s / 2`. Invariantes `I1` a `I4` validadas por `sss_config`.
* **Relógios:** regras de negócio e agendamento usam `SYSDATE` do Oracle (`now()` do repositório); prazos internos, timeouts, reconexão e heartbeats usam `time.monotonic()`. Proibido `datetime.now()` em agendamento, heartbeat ou timeout.

### 2.6 Testes e Portões de Qualidade (`AGENTS.md` §7)
* **Portões obrigatórios (`make check-all`):**
  1. `make lint` (`flake8` com limite de **99 colunas**, zero achados).
  2. `make type-check` (`mypy` estrito em todo arquivo novo ou alterado, zero achados).
  3. `tests/architecture/test_quality_debt.py`: a lista de exceções legadas em `.flake8` e `pyproject.toml` **só diminui** (proibido adicionar arquivo, módulo ou código de erro).
* **Suíte de testes (`unittest` exclusivo; `pytest` é proibido):**
  * `make test-unit` (`tests/unit/<camada>/`)
  * `make test-integration` (`tests/integration/process/` e, com `SSS_TEST_ORACLE=1`, `tests/integration/oracle/`)
  * `make test-functional` (`tests/functional/`)
  * `make test-architecture` (`tests/architecture/`)
  * `make test-matrix` (roda a suíte em Python `3.6.0`, `3.6.15` e `3.13.2`).
* **Cuidado com `SSS_TEST_ORACLE=1`:** pare o DEV local antes (`make ctl CMD=stop`) para não disputar filas no esquema `tbsdev_`.

### 2.7 Checklist Obrigatório (§8) e Formato de Relatório (§9)
Antes de concluir qualquer tarefa de código ou documentação, valide todos os itens da §8 do `AGENTS.md` (compatibilidade Python 3.6.0–3.13, zero dependências novas, SQL 11gR2 seguro com `sql_ident` e `rowcount`, camadas respeitadas, `os_platform` isolado, web sem inline/CDN e com CSRF/RBAC, logs sem segredos, testes executados) e **encerre sempre a resposta com o bloco exato da §9**:

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

## 3. Mapa Rápido da Arquitetura e Topologia

### 3.1 Ordem Estrita de Camadas em `src/sss/` (`tests/architecture/test_layers.py`)
Uma camada **só importa camadas abaixo dela**, sempre com import qualificado (`from sss.<camada> import <módulo>`):
```text
platform (base: só stdlib, POSIX)
  └── core (regras puras: cron_parser, recurrence, params_compiler, masking, rbac, password_hasher, sql_ident, input_names)
        └── config (sss_config, sss_context, sss_logging, log_paths)
              └── persistence (db_conn, ddl_builder, contracts/, oracle/, fake/)
                    ├── ui (ui_helpers, ui_menu)
                    │     └── services (auth, catalog, ticket, schedules, files, input_browse, output_browse, audit, permissions, health, admin_*)
                    │           └── web (framework/, app/, controllers/, templates/, static/)
                    └── scheduler (loop, executor, log_pump, schedule_expansion, output_phase, input_phase, startup, state)
cli (topo: run_web, run_scheduler, init_db, generate_sql, check_env, health, probe_driver) -> invocado por scripts/<nome>.py
```

### 3.2 Banco de Dados Oracle (21 Tabelas e 14 Funcionalidades RBAC)
* **21 Tabelas Lógicas (`src/sss/core/sql_ident.py`):**
  * Controle e Segurança (4): `tbsss_control`, `tbsss_users`, `tbsss_profiles`, `tbsss_features`.
  * Catálogo e Ambientes (4): `tbsss_environments`, `tbsss_scripts`, `tbsss_parameters`, `tbsss_script_Params`.
  * Vínculos RBAC e Homologação (4): `tbsss_profile_features`, `tbsss_profile_envs`, `tbsss_profile_scripts`, `tbsss_script_envs`.
  * Operação, Fila, Agentes e Arquivos (8): `tbsss_schedules`, `tbsss_tickets`, `tbsss_ticket_params`, `tbsss_ticket_output`, `tbsss_agents`, `tbsss_agent_envs`, `tbsss_inputs`, `tbsss_input_Snapshot`.
  * Auditoria (1): `tbsss_audit_logs`.
* **14 Funcionalidades RBAC (`tbsss_features`):** `EXEC_SCRIPT`, `VIEW_LOGS`, `CANCEL_TICKET`, `MANAGE_SCHEDULES`, `MANAGE_USERS`, `MANAGE_PROFILES`, `MANAGE_ENVIRONMENTS`, `MANAGE_SCRIPTS`, `MANAGE_PARAMETERS` ("Gestão de Parâmetros"), `VIEW_AUDIT`, `DOWNLOAD_OUTPUT`, `UPLOAD_INPUT`, `FILES_UPLOAD`, `FILES_DOWNLOAD`.
* **3 Perfis Padrão Homologados (em português):**
  * `ADMINISTRADOR`: Super Administrador (`is_admin = 'Y'`). Acesso total a todas as funcionalidades e ambientes.
  * `OPERADOR`: Operacional (`is_admin = 'N'`). Acesso a execução, cancelamento, logs, entradas, saídas e pasta de arquivos nos ambientes operacionais.
  * `CONSULTA`: Auditoria e Consulta (`is_admin = 'N'`). Apenas consulta de logs e tickets (`VIEW_LOGS`).
  * *(Nota: o perfil `OPERATOR_HML` e o usuário `op.hml` foram aposentados e removidos do seed).*
* **3 Usuários Padrão Homologados do Seed:** `admin` (`ADMINISTRADOR`), `op.prod` (`OPERADOR`) e `consulta` (`CONSULTA`).
* **Prefixos de Tabela Oficiais por Ambiente:**
  * `tbsdev_` (Ambiente de desenvolvimento - `DEV`, não parametrizado)
  * `tbsprd_` (Ambiente de produção - `PROD`, não parametrizado)
* **Scripts dos Ambientes:** residem na pasta base `<RAIZ>/scripts_ambiente/`.
* **Processos por Instalação (1 Web + 5 Agentes):**
  * `web0001` (interface web)
  * `agente0001` (`GFPREPROD`), `agente0002` (`CLONE2`), `agente0003` (`CLONE1`), `agente0004` (`CLONE6`), `agente0005` (`CLONE7`).

### 3.3 Mapa de Documentação (`docs/`)
* **Manuais Operacionais:** `docs/DEPLOYMENT.md` (manual geral normativo, testado por `test_deployment_doc.py`), `docs/DEPLOYMENT-SERVER.md` (runbook passo a passo de 1 servidor e Apêndice A do 3067), `docs/DEV_ENVIRONMENT.md` (ambiente local, Python 3.6/3.11/3.13 e alvos do `Makefile`), `docs/HOMOLOGATION_RUNBOOK.md`, `docs/UTILITY_SCRIPTS.md`, `docs/ADMIN_CRUD_PATTERN.md`.
* **Guias Explicativos (`docs/explain/`):** `00-indice-geral.md` a `06-testes-qualidade-e-operacao.md`.
* **Histórico Arquitetural (`docs/architecture/`):** `CR-001` a `CR-039` + `DEPLOYMENT-history.md`.
* **Scripts DBA (`docs/sql/`):** `{tbsdev,tbsprd}_{01_deploy,02_rollback,99_validate}.sql` (gerados por `make sql-all`, 100% ASCII).
* **Homologação (`docs/homologation/` e `docs/prompts/`):** evidências `.docx` (até `2026-10-30_r4`) e roteiros de fase (`F0` a `F9_2`).

