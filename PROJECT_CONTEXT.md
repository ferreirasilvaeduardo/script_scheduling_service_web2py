# Contexto e Diretrizes do Projeto

SSS (Script Scheduling Service). Atualizado em 30/10/2026 (base `52a9cf8`). Resumo para quem chega ao projeto sem o histórico; **não substitui as fontes normativas**: o `README.md` (negócio, dados e algoritmos) e o `AGENTS.md` (regras de código e de entrega), nesta ordem. O `CLAUDE.md` traz as diretrizes do agente de IA.

## 1. Visão Geral do Sistema

- **Objetivo do Projeto:** agendar e executar scripts por ambiente, com rastreabilidade total. Nenhuma tarefa roda avulsa: cada execução é um **ticket** que registra de forma imutável o solicitante, o IP, o script, o ambiente, o snapshot das respostas e do `argv`, o agente, o PID, a situação, o código de retorno e o log completo (README §1).
  - Usuários disparam scripts, acompanham tickets, baixam saídas, enviam arquivos de entrada e cadastram regras recorrentes (diária, semanal, mensal, CRON).
  - Agentes (hoje um por ambiente) pegam os tickets da fila, executam o script com a conta do agente, coletam o log e gravam o resultado.
  - Administradores mantêm usuários, perfis, ambientes, parâmetros e scripts, com auditoria de tudo.
- **Stack Tecnológico:**
  - Linguagem / Runtime: **Python 3.6.0 ou superior**, com sintaxe e biblioteca padrão da 3.6.0; validado em 3.6.0, 3.6.15 e 3.13.2 (referência de produção 3.6.8; no servidor 3067, 3.8.5).
  - Frameworks / Bibliotecas: **nenhum framework**. Só a biblioteca padrão e o driver Oracle: `python-oracledb` (`< 2.0` no 3.6, `2.x` no 3.7+) e `cx_Oracle 8.3` como contingência. Servidor web, roteador, sessão e templates próprios (`src/sss/web/framework/`). Frontend com Bootstrap 5.3.8 local e JavaScript próprio, sem CDN nem script inline.
  - Banco de Dados: **somente Oracle**, piso **11gR2** (todo SQL roda no 11g) até 23ai; o banco de trabalho (GFPR) é 19c, charset WE8ISO8859P15. Cliente: Instant Client 19 recomendado; outro só avisa (no 3067, cliente 12.2).
  - Infraestrutura / Nuvem: servidores **Linux/Unix POSIX** próprios, sem contêiner; desenvolvimento em WSL (Ubuntu 24.04); servidor 3067 em CentOS 6 (bash 4.1, sem `C.UTF-8`), acessado por bastion SSH. Permanência pelo `crontab` da conta.

---

## 2. Padrões de Arquitetura e Código

- **Processos:**
  - **Web** (`web0001`): `bin/sss-web.sh` → `scripts/run_web.py`. UI, login, RBAC, tickets, cadastros, downloads e envio de arquivos.
  - **Agente** (`agente0001`…): `bin/sss-scheduler.sh <nome>` → `scripts/run_scheduler.py`. Desdobro de agendamentos, claim da fila, execução, heartbeat, coleta de log, saída e entrada. Thread única, com laço de eventos e prazos do relógio monotônico.
  - Os processos coordenam-se **só pelo banco**: claim por `UPDATE` condicional com `rowcount`, heartbeat, *fencing* e detecção de nó offline. O web nunca sinaliza processos do SO.
- **Estrutura de Pastas:**
  - `src/sss/`: código-fonte, em camadas:
    - `config/`: config, segredos, logging, caminhos de log;
    - `core/`: regras puras (CRON, recorrência, parâmetros, mascaramento, RBAC, senha, `sql_ident`);
    - `platform/`: primitivas de SO, só POSIX;
    - `persistence/`: driver, DDL, contratos, repositórios `oracle/` e `fake/`;
    - `services/`, `scheduler/` e `web/`;
    - `ui/`: mensagens;
    - `cli/`: ferramentas de operação.
  - `scripts/`: comandos de operação (`run_web`, `run_scheduler`, `init_db`, `generate_sql`, `check_env`, `health`, `probe_driver`), que só envolvem `src/sss/cli/`.
  - `bin/`: launchers e operação no servidor (`sss-ctl.sh`, `sss-keepalive.sh`, `sss-update.sh`, `sss-stop.sh`) e o web do DEV (`start_local.sh`).
  - `tests/`:
    - `unit/`: sem banco;
    - `integration/oracle/`: só com `SSS_TEST_ORACLE=1`;
    - `integration/process/`;
    - `functional/`;
    - `architecture/`: regras lidas no código e nos documentos.
  - `tools/package.py`: pacote de implantação. `dev/`: scripts de exemplo, homologação e notas (fora do pacote).
  - `docs/`:
    - manuais `DEPLOYMENT.md` (genérico), `DEPLOYMENT-SERVER.md` (roteiro de um servidor; Apêndice A = 3067) e `DEV_ENVIRONMENT.md`;
    - `sql/` (scripts para o DBA), `architecture/` (histórico dos CRs) e `homologation/` (evidências).
  - `instance/`: `common.ini`, `secrets.cfg` (0600) e `<processo>/config.ini`; modelos em `instance/exemplos/`. `var/<processo>/`: logs, pastas de trabalho, saída e entrada.
- **Estilo e Convenções:**
  - Nomenclatura: `snake_case` em funções, módulos e arquivos; `PascalCase` em classes. Nomes técnicos (código, banco, configuração, variáveis) **em inglês**; textos de tela, comentários e dados em português (CR-016; legado em português aceito). Imports de `sss` sempre qualificados.
  - Linhas de até 99 colunas. Comentar só o porquê não óbvio. Docstrings curtas em funções públicas.
  - Tipagem: `mypy` **estrito** em todo arquivo novo ou alterado. A dívida antiga está listada no `pyproject.toml` e no `.flake8` e só diminui.
  - Proibido em código (AGENTS §2.1): qualquer recurso de Python 3.7+ (dataclasses, walrus, pos-only, f-string com `=`). F-strings simples são permitidas.
  - SQL:
    - binds sempre; nomes físicos só via `sql_ident` (prefixo configurável, até 30 caracteres);
    - `rowcount` conferido em toda transição; `FOR UPDATE WAIT n` com n ≤ 5;
    - sem sintaxe 12c+; paginação por `ROWNUM`;
    - SQL só em `persistence/oracle/`, `init_db` e `ddl_builder`.
  - Tratamento de Erros:
    - **Logs:** no formato fixo do README §13, em `log_dir/internal/app/AAAA/MM/DD/HH/MI/<processo>_<PID>.log`; todo `except` registra o código ORA e o stack trace antes do `ROLLBACK`; segredos mascarados.
    - **Repositório:** lança exceções de contrato (`RepoNotFound`, `RepoConflict`, `RepoViolation`, `RepoUnavailable`). A `RepoViolation` traz o **nome lógico** da constraint (sempre com `tbsss_`), que o serviço traduz para a mensagem do campo.
    - **Tela:** mensagens do catálogo de `ui_helpers`, em duas partes.
    - **Subida:** o agente sai com códigos 10 a 20 por passo; avisos que não impedem o funcionamento viram WARNING, e não recusa (CR-036).
  - Segurança:
    - **Contas:** conta de SO sem privilégio; o agente recusa root; `umask 077`.
    - **Execução de scripts:** spawn único (`os_platform.start_process`, `shell=False`); ambiente do filho limpo; allowlist de interpretador e `path_guard`.
    - **Web:** CSRF em todo POST; sessão em cookie assinado; nada sensível no HTML.

---

## 3. Ambiente e Execução

- **Comandos Principais** (toda automação pelo `Makefile`; `make help` lista os 34 alvos; parâmetros na linha do make: `NAME=`, `CMD=`, `OWNER=`, `PREFIX=`):
  - Instalação de Dependências: **não há `pip install`**. O Python e o driver Oracle são pré-instalados pela infraestrutura; conferência com `make check-deps` (aplicação e ferramentas de DEV) e `make check-env NAME=agente0001`. As ferramentas de lint e tipos ficam no Python 3.11 da máquina de desenvolvimento (`DEV_PYTHON`).
  - Execução Local: `make dev-start PORT=18000` / `make dev-stop` (web do DEV), `make ctl CMD=status|start|stop` (processos da raiz pelo `bin/sss-ctl.sh`), `make health`, `make init-db-dry`.
  - Bateria de Testes:
    - `make test-all` no `PYTHON`;
    - `make test-matrix` em 3.6.0, 3.6.15 e 3.13.2;
    - `make test-oracle` com o Oracle real, que exige o DEV local parado;
    - `make test-unit`, `test-integration`, `test-functional` e `test-architecture` por pasta.
    - Framework: só `unittest`.
  - Linters / Formatação: `make check-all` (portões: `flake8` com zero achados e `mypy` estrito); `make format` (isort e autopep8; reescreve arquivos); `make lint-pylint` (fora do portão).
  - SQL e pacote: `make sql` / `make sql-all` (scripts do DBA em `docs/sql`, só ASCII); `make package-local` (pacote para o servidor em `.bkp/pacote_local_<data>`, com `ORIGEM` e `SHA256SUMS`).
  - Homologação: `make homolog-massa`, `make homolog` (roteiro no navegador, Puppeteer), `make homolog-docx`; acesso ao 3067 por `make tunel-3067 CMD=start`.
- **Variáveis de Ambiente e Configuração:**
  - Não há `.env`. A configuração fica em arquivos INI por processo:
    - os modelos estão em `instance/exemplos/` (`common.ini.example`, `secrets.cfg.example`, `web0001/` e `agente0001/config.ini.example`);
    - todo comando recebe o processo por `--name <nome>` (sem config padrão, CR-029);
    - o `secrets.cfg` real nunca vai para o git.
  - Variáveis dos launchers (DEPLOYMENT §10.5), em geral carregadas do `sss_vars.sh` do servidor:
    - `PYTHON`, `SSS_TZ`, `SSS_LOCALE` (UTF-8; padrão `C.UTF-8`), `SSS_IC_DIR` (Instant Client) e `ORACLE_HOME`;
    - `SSS_WEB_HOST`: endereço do web no `sss-ctl.sh`; sem ela, só `127.0.0.1`;
    - `SSS_STOP_WAIT_S`: espera do `stop`.
  - Senhas digitadas: `SSS_INIT_DB_PASSWORD` (dono do esquema, no `init_db`) e `SSS_BOOTSTRAP_ADMIN_PASSWORD` (administrador inicial).
  - Testes e homologação: `SSS_TEST_ORACLE=1` (bateria Oracle) e as `SSS_*` do roteiro de homologação (`dev/others/homologation/README.md`).
- **Instalações:**

  | Instalação | Onde | Prefixo | Situação em 30/10/2026 |
  |---|---|---|---|
  | DEV local | esta máquina (o próprio repositório) | `ssdev_` (GFPR) | web e 5 agentes, todos parados |
  | PROD local | `/portaloptrib/TESHUVA/SSS/PROD/script_scheduling_service` | `tbsss_` (GFPR) | esquema recriado vazio em 30/10; parado |
  | DEV 3067 | `brtlvlty3067sl`, porta 18000 | `s3dev_` | no ar, `1.0.0-dev+2610301500`, esquema refeito em 30/10 |
  | PROD 3067 | idem, porta 18001 | `s3prd_` | no ar, mesma versão, esquema refeito em 30/10 |

  - **Implantação num servidor novo:** `docs/DEPLOYMENT-SERVER.md`. A transferência do pacote é manual, pela equipe. Atualização: passo 15.1. Refazer esquema: passo 15.2, só com autorização.

---

## 4. Decisões Técnicas e Histórico (Memória Acumulada)

O porquê completo de cada decisão está em `docs/architecture/CR-*.md` (CR-001 a CR-039) e no Apêndice A do `docs/DEPLOYMENT-SERVER.md` (decisões da implantação no 3067).

- **ADR 001 - Somente Oracle, com piso no 11gR2 (CR-002):**
  - *Contexto:* o banco da empresa é Oracle, com instâncias de 11g a 19c.
  - *Decisão Tomada:* SQL 11gR2 escrito à mão nos repositórios, sem camada de dialeto; prefixo de tabela configurável para várias instalações no mesmo owner.
  - *Impacto:* proibida sintaxe 12c+ (`FETCH FIRST`, `IDENTITY`, JSON no banco); identificadores ≤ 30 caracteres após o prefixo; o `test_sql_oracle11g` varre o código.
- **ADR 002 - Driver adaptativo (CR-002, F7.0):**
  - *Contexto:* servidores com Pythons e clientes Oracle diferentes; o modo Thin não conecta ao 11g.
  - *Decisão Tomada:* `driver_mode = auto`, que sonda Thin → Thick → cx_Oracle num processo separado e usa o primeiro que conecta. Cliente fora do 19 só avisa (decisão 10 A); abaixo do 18.1, a sessão segue sem `call_timeout` (11 B).
  - *Impacto:* sem `cryptography` nem `pip`; o driver só é importado em `db_conn` e na sondagem.
- **ADR 003 - Sem framework web e só biblioteca padrão (CR-021):**
  - *Contexto:* o web2py e o Alpine traziam dependências e superfície de ataque num ambiente hermético.
  - *Decisão Tomada:* núcleo web próprio (`wsgiref`, roteador, sessão em cookie assinado, templates); JavaScript sem framework; todos os assets locais.
  - *Impacto:* proibidos CDN, script e estilo inline (CSP); `exec` só no motor de templates.
- **ADR 004 - Somente POSIX, com camada de plataforma (CR-005):**
  - *Contexto:* os agentes rodam em Linux e Unix.
  - *Decisão Tomada:* toda primitiva de SO (spawn, sinais, identidade do processo, lock, locale) em `src/sss/platform/os_platform/`.
  - *Impacto:* nenhum `subprocess` ou sinal fora dessa camada (exceção: a sondagem do driver).
- **ADR 005 - Uma conta de SO e uma conta de banco por servidor (CR-032):**
  - *Contexto:* simplificar a implantação, sem `sudo` nem usuário de execução.
  - *Decisão Tomada:* os scripts rodam com a conta do agente; a conta Oracle pode ser a dona do esquema.
  - *Impacto:* risco aceito (os scripts podem ler os segredos do SSS); quem cadastra script tem o poder da conta.
- **ADR 006 - Nomes técnicos em inglês (CR-016):**
  - *Contexto:* padronizar o código e o banco.
  - *Decisão Tomada:* tabelas, colunas, valores gravados, módulos e configuração em inglês; telas e documentos em português.
  - *Impacto:* a tradução parou no CR-016 (legado em português aceito); nome novo é sempre em inglês.
- **ADR 007 - Avisos no lugar de bloqueios (CR-036, decisões 9 B a 13 A):**
  - *Contexto:* servidores antigos (CentOS 6 sem `C.UTF-8`, Python 2 como `python`, cliente 12.2) recusavam a subida.
  - *Decisão Tomada:* locale substituto, versão de cliente e interpretadores viram WARNING e linhas `AVISO` no `check_env`; o `PATH` do filho inclui a pasta do Python do agente.
  - *Impacto:* o código segue genérico para vários servidores; o que não impede o funcionamento não recusa.
- **ADR 008 - SQL gerado só em ASCII (decisão 16 A):**
  - *Contexto:* o seed em UTF-8, lido pelo sqlplus com `NLS_LANG` WE8MSWIN1252, gravou "GestÃ£o" no banco do 3067.
  - *Decisão Tomada:* `ddl_builder.ascii_sql` grava os literais com acento como `UNISTR('\XXXX')`; comentários e `PROMPT` saem sem acento.
  - *Impacto:* os arquivos de `docs/sql` nunca têm byte acima de 127; o texto chega igual com qualquer `NLS_LANG` e qualquer charset.
- **ADR 009 - Nome lógico da constraint nos erros (batimento de 30/10/2026):**
  - *Contexto:* com prefixo diferente de `tbsss_`, nome repetido mostrava a mensagem genérica nas 5 telas de cadastro.
  - *Decisão Tomada:* `RepoViolation.constraint` sempre com `tbsss_` (`sql_ident.logical_object_name`).
  - *Impacto:* constraint nova que vire mensagem de campo entra no `_FIELD_BY_CONSTRAINT` com `tbsss_`.
- **ADR 010 - Administrador inicial por `--admin-login` (decisão 18 B):**
  - *Contexto:* a opção existia, mas não tinha efeito.
  - *Decisão Tomada:* `--admin-login X` cria X no perfil `ADMINISTRATOR`, além dos 4 usuários do seed, pela mesma lista (`ddl_builder.seed_users`) no `init_db` e no SQL gerado.
  - *Impacto:* login inválido, ou igual a `op.prod`, `op.hml` ou `consulta`, sai com código 2.
- **ADR 011 - Espera no `stop_ticket` dentro do laço (decisão 19 C):**
  - *Contexto:* a regra proíbe espera dentro de operação do agente.
  - *Decisão Tomada:* aceita a exceção do ticket "talvez iniciado" achado na varredura, que é um caso raro (até `kill_grace_s`, 5 s).
  - *Impacto:* registrada no README §8.1, no AGENTS e na docstring; não usar o padrão em outro lugar.
- **ADR 012 - Toda automação pelo Makefile (30/10/2026):**
  - *Contexto:* scripts de build, teste, operação, SQL e homologação espalhados.
  - *Decisão Tomada:* cada script de automação tem um alvo com descrição `##`; os parâmetros têm atribuição simples (`NAME :=`), porque o ambiente costuma ter `NAME` com o nome da máquina.
  - *Impacto:* o `tests/architecture/test_makefile.py` cobra; os launchers do servidor ficam com o `sss-ctl.sh` e o cron.
- **Restrições Importantes:**
  - Python 3.6: nada de recurso 3.7+; testar nas 3 versões antes de commitar código.
  - **Nunca rodar `init_db` num banco em uso**; nele, só os MERGE do seed. Refazer um esquema é o ciclo `02_rollback` → `01_deploy` → `99_validate`, com autorização, porque apaga os dados.
  - SQL ao DBA em duas chamadas do sqlplus (o `01` termina com `EXIT`).
  - Mudança de esquema com a versão 1 ainda "aberta": entra direto na versão 1; quando ela for congelada, toda mudança traz migração (AGENTS §4.16).
  - Nunca commitar o `LEIA-ME.TXT` nem `instance/secrets.cfg`: usar `git add -A -- . ':!LEIA-ME.TXT'`.
  - Processo de trabalho:
    - plano → aprovação → implementação → testes → documentação → commit e push → pacote;
    - decisões do responsável uma de cada vez, em opções A/B com recomendação;
    - toda entrega termina com o relatório do AGENTS §9;
    - o README e o AGENTS mudam juntos.
  - O código local é a referência (o git é controle pessoal). Transferência ao servidor é feita pela equipe; a instalação do `crontab` no servidor também.

---

## 5. Status Atual e Próximos Passos

- **Funcionalidades Concluídas:**
  - [x] Tickets ponta a ponta: criação com snapshot, fila com envelhecimento, claim distribuído, execução, cancelamento, reexecução, log em CLOB e timeout.
  - [x] Agendamentos recorrentes (diário, semanal, mensal, CRON próprio) com política de *misfire*.
  - [x] RBAC por perfil × ambiente × script, auditoria completa e cadastros com controle de concorrência.
  - [x] Pasta de saída (zip no banco), pasta de entrada por tela, pasta de trabalho e Pasta de Arquivos (CR-012, CR-014, CR-019, CR-020, CR-037).
  - [x] Alta disponibilidade entre agentes: heartbeat, *fencing* e detecção de nó offline.
  - [x] Implantação por roteiro em servidor real (3067: DEV e PROD no ar, crontab, `sss-ctl.sh`, `sss-update.sh` com retorno).
  - [x] Homologação real automatizada no navegador (352/352 na rodada 3 do 3067) e batimento completo docs × código (30/10/2026).
- **Tarefas Pendentes / Em Progresso:**
  - [ ] Concluir a homologação da rodada 4 no DEV do 3067 (com o CT-11 conferindo o nome repetido): conferir o resultado, criar `RODADAS["20261030_r4"]` em `build_evidence_docx.py`, gerar o `.docx`, conferir que não há senha nele e commitar.
  - [ ] Commit do `Makefile` (16 alvos novos), do `test_makefile.py` e deste arquivo (bateria `make test-matrix`: 1557 OK nas 3 versões).
  - [ ] Decidir quando congelar a versão 1 do esquema: já há PROD no 3067 e PROD local. O `init_db` ainda não aplica migrações (`src/sss/cli/migrations/` vazia).
  - [ ] Definir a semântica do `--recreate` do `init_db` (README §11.1) antes de implementá-lo.
  - [ ] Decidir se o charset AL32UTF8 do README §2.2 é exigência ou recomendação: o GFPR é WE8ISO8859P15 e o SSS funciona nele.
  - [ ] Opcional: o `init_db --generate-sql` passar a usar as contas do config nos GRANTs, como o `generate_sql.py --name`.
  - [ ] Corrigir o README §2.3: ainda diz que o modo Thin fica fora de uso (`driver_mode = thick`), mas o padrão é `auto`.
  - [ ] Rodar `make test-oracle` (bateria Oracle) com o DEV local parado, depois da correção das constraints.
  - [ ] Teste real dos três drivers (F8.2) e roteiro E2E com agentes POSIX (F9.2, `docs/prompts/F9_2_e2e.md`).
  - [ ] Trocar a senha da conta Oracle usada no 3067 (apareceu numa conversa) e ajustar os `secrets.cfg`.
  - [ ] Atualizar o `~/sss_pacote/sss_vars.sh` real com o `SSS_AGENTE_HEALTH` em ordem alfabética (modelo do DEPLOYMENT-SERVER).
- **Dívidas Técnicas / Cuidados:**
  - **Riscos aceitos** (README §14):
    - web por HTTP sem TLS na rede interna;
    - scripts com a conta do agente;
    - usuários do seed na senha inicial no 3067 (decisão 15);
    - scripts sem hash nem conferência de dono;
    - interpretador escolhido no disparo e `#!`;
    - processo que escapa do `killpg` por double-fork;
    - segredos com menos de 4 caracteres sem mascaramento.
  - **Pontos frágeis — não refatorar sem os testes de arquitetura e de HA:**
    - o laço do agente (`scheduler_loop`): orçamento por ciclo, fence, finalização pendente;
    - o claim em três passos;
    - a coleta de log por offset em caracteres;
    - o `stop_ticket` (exceção 19 C).
  - Dívida de lint e tipos listada no `.flake8` e no `pyproject.toml`: só diminui (`test_quality_debt.py`).
  - `test_ha_agentes_reais` (CRON) pode estourar o prazo sob carga na bateria completa (passa isolado).
  - A bateria Oracle disputa o banco com o DEV local: pare o DEV antes (R-23) e confira `find var -maxdepth 2` antes e depois.
  - O 3067 não comporta o Instant Client 19 (exige glibc 2.14); segue com o cliente 12.2, sem `call_timeout`. Ali, as invariantes I3 e I4 dependem da rede e do `SQLNET.EXPIRE_TIME`.
