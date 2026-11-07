# Contexto e Diretrizes do Projeto

## 1. Visão Geral do Sistema

- **Objetivo do Projeto:** agendar e executar scripts por ambiente, com rastreabilidade total. Nenhuma tarefa roda avulsa: cada execução é um **ticket** que registra de forma imutável o solicitante, o IP, o script, o ambiente, o snapshot das respostas e do `argv`, o agente, o PID, a situação, o código de retorno e o log completo (README §1).
  - Usuários disparam scripts, acompanham tickets, baixam saídas, enviam arquivos de entrada e cadastram regras recorrentes (diária, semanal, mensal, CRON).
  - Agentes (hoje um por ambiente) pegam os tickets da fila, executam o script com a conta do agente, coletam o log e gravam o resultado.
  - Administradores mantêm usuários, perfis, ambientes, parâmetros e scripts, com auditoria de tudo.
  - Dois processos:
    - **Web** (`web0001`): `bin/sss-web.sh` → `scripts/run_web.py`. UI, login, RBAC, tickets, cadastros, downloads e envio de arquivos.
    - **Agente** (`agente0001`…): `bin/sss-scheduler.sh <nome>` → `scripts/run_scheduler.py`. Desdobro de agendamentos, claim da fila, execução, heartbeat, coleta de log, saída e entrada. Thread única, com laço de eventos e prazos do relógio monotônico.
    - Os processos coordenam-se **só pelo banco**: claim por `UPDATE` condicional com `rowcount`, heartbeat, *fencing* e detecção de nó offline. O web nunca sinaliza processos do SO.
  - Projeto SSS (Script Scheduling Service); este resumo é de 07/11/2026 (base `c2462b9`, HEAD de `main`: prefixo fixo por ambiente em `a75e3c1`, perfis `ADMINISTRADOR`/`OPERADOR`/`CONSULTA` em `11966d7`, `scripts_ambiente/` versionado em `8a4b5ba`, `utilitarios.tar.gz` no pacote em `ae396c7` e revisão docs × código, passos 1 e 2, em `690d608` e `c2462b9`) e **não substitui as fontes normativas**: o `README.md` (negócio, dados e algoritmos) e o `AGENTS.md` (regras de código e de entrega), nesta ordem. O `CLAUDE.md` traz as diretrizes do agente de IA e o `GEMINI.md` consolida na raiz as regras completas do `AGENTS.md` (§§3.3–9) e o mapa arquitetural para carregamento automático sem truncamento em cada conversa.
- **Stack Tecnológico:**
  - Linguagem / Runtime: **Python 3.6.0 ou superior**, com sintaxe e biblioteca padrão da 3.6.0; validado em 3.6.0, 3.6.15 e 3.13.2 (referência de produção 3.6.8; no servidor 3067, 3.8.5).
  - Frameworks / Bibliotecas: **nenhum framework**. Só a biblioteca padrão e o driver Oracle: `python-oracledb` (`< 2.0` no 3.6, `2.x` no 3.7+) e `cx_Oracle 8.3` como contingência. Servidor web, roteador, sessão e templates próprios (`src/sss/web/framework/`). Frontend com Bootstrap 5.3.8 local e JavaScript próprio, sem CDN nem script inline.
  - Banco de Dados: **somente Oracle**, piso **11gR2** (todo SQL roda no 11g) até 23ai; o banco de trabalho (GFPR) é 19c, charset WE8ISO8859P15. Cliente: Instant Client 19 recomendado; outro só avisa (no 3067, cliente 12.2).
  - Infraestrutura / Nuvem: servidores **Linux/Unix POSIX** próprios, sem contêiner; desenvolvimento em WSL (Ubuntu 24.04); servidor 3067 em CentOS 6 (bash 4.1, sem `C.UTF-8`), acessado por bastion SSH. Permanência pelo `crontab` da conta.

---

## 2. Padrões de Arquitetura e Código

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
  - `bin/`: launchers (`sss-web.sh`, `sss-scheduler.sh`), operação no servidor (`sss-ctl.sh`, `sss-keepalive.sh`, `sss-update.sh`, `sss-stop.sh`) e o web do DEV (`start_local.sh`, `stop_local.sh`).
  - `tests/`:
    - `unit/`: sem banco;
    - `integration/oracle/`: só com `SSS_TEST_ORACLE=1`;
    - `integration/process/`;
    - `functional/`;
    - `architecture/`: regras lidas no código e nos documentos.
  - `tools/package.py`: pacote de implantação.
  - `scripts_ambiente/`: árvore versionada dos scripts de negócio que o SSS executa (`script_base_dir` padrão do agente, `<RAIZ>/scripts_ambiente`), com `utilitarios/` (vai também no `utilitarios.tar.gz` do pacote) e `diagnostico/`; fora do lint.
  - `dev/`: só desenvolvimento, fora do pacote: `dev/others/` (`homologation/`, com as ferramentas em `tools/`; `web_harness/`; `notas/`); `dev/scripts/` fica vazia (só `.gitkeep`).
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
    - binds sempre; nomes físicos só via `sql_ident` (prefixo fixo pelo ambiente: `tbsdev_` em DEV, `tbsprd_` em PROD; até 30 caracteres);
    - `rowcount` conferido em toda transição; `FOR UPDATE WAIT n` com n ≤ 5;
    - sem sintaxe 12c+; paginação por `ROWNUM`;
    - SQL só em `persistence/oracle/`, `init_db` e `ddl_builder`.
  - Tratamento de Erros:
    - **Logs:** no formato fixo do README §13, em `log_dir/internal/app/AAAA/MM/DD/HH/MI/<log_name>_<PID>[_<n>].log` (`config/log_paths.py`); todo `except` registra o código ORA e o stack trace antes do `ROLLBACK`; segredos mascarados.
    - **Repositório:** lança exceções de contrato (`RepoNotFound`, `RepoConflict`, `RepoViolation`, `RepoUnavailable`). A `RepoViolation` traz o **nome lógico** da constraint (sempre com `tbsss_`), que o serviço traduz para a mensagem do campo.
    - **Tela:** mensagens do catálogo de `ui_helpers`, em duas partes.
    - **Subida:** o agente sai com códigos 10 a 20 por passo; avisos que não impedem o funcionamento viram WARNING, e não recusa (CR-036).
  - Segurança:
    - **Contas:** conta de SO sem privilégio; o agente recusa root; `umask 077`.
    - **Execução de scripts:** spawn único (`os_platform.start_process`, `shell=False`); ambiente do filho limpo; allowlist de interpretador e `path_guard`.
    - **Web:** CSRF em todo POST; sessão em cookie assinado; nada sensível no HTML.

---

## 3. Ambiente e Execução

- **Comandos Principais** (toda automação pelo `Makefile`; `make help` lista os 34 alvos; parâmetros na linha do make, com padrões `NAME := agente0001`, `CMD := status`, `OWNER := openrisow`, `PREFIX := tbsdev_` (usado no `make sql`) e `CANDIDATE := thick` (usado no `make probe-driver`)):
  - Instalação de Dependências: **não há `pip install`**. O Python e o driver Oracle são pré-instalados pela infraestrutura; conferência com `make check-deps` (aplicação e ferramentas de DEV) e `make check-env NAME=agente0001`. As ferramentas de lint e tipos ficam no Python 3.11 da máquina de desenvolvimento (`DEV_PYTHON`).
  - Execução Local: `make dev-start PORT=18000` / `make dev-stop` (web do DEV), `make ctl CMD=status|start|stop` (processos da raiz pelo `bin/sss-ctl.sh`), `make health`, `make init-db-dry`.
  - Bateria de Testes:
    - `make test-all` no `PYTHON`;
    - `make test-matrix` em 3.6.0, 3.6.15 e 3.13.2;
    - `make test-oracle` com o Oracle real, que exige o DEV local parado;
    - `make test-unit`, `test-integration`, `test-functional` e `test-architecture` por pasta.
    - Framework: só `unittest`.
  - Linters / Formatação: `make check-all` (portões: `flake8` com zero achados, sem `dev/scripts` e `scripts_ambiente` pelo `extend-exclude` do `.flake8`, e `mypy` estrito); `make format` (isort e autopep8; reescreve arquivos); `make lint-pylint` (fora do portão).
  - SQL e pacote: `make sql` / `make sql-all` (scripts do DBA em `docs/sql`, só ASCII); `make package-local` (pacote para o servidor em `.bkp/pacote_local_<data>`, com `ORIGEM` e `SHA256SUMS`).
  - Homologação: `make homolog-massa`, `make homolog` (roteiro no navegador, Puppeteer), `make homolog-docx`; acesso ao 3067 por `make tunel-3067 CMD=start`.
- **Variáveis de Ambiente:**
  - Não há `.env`. A configuração fica em arquivos INI por processo:
    - os modelos estão em `instance/exemplos/` (`common.ini.example`, `secrets.cfg.example`, `web0001/` e `agente0001/config.ini.example`);
    - todo comando recebe o processo por `--name <nome>` (sem config padrão, CR-029);
    - o `secrets.cfg` real nunca vai para o git.
  - Variáveis dos launchers (DEPLOYMENT §10.5), em geral carregadas do `sss_vars.sh` do servidor:
    - `PYTHON`, `SSS_TZ`, `SSS_LOCALE` (UTF-8; padrão `C.UTF-8`), `SSS_IC_DIR` (Instant Client) e `ORACLE_HOME`;
    - `SSS_WEB_HOST`: endereço do web no `sss-ctl.sh`; sem ela, só `127.0.0.1`;
    - `SSS_STOP_WAIT_S`: espera do `stop` (padrão 45 s).
  - Prefixo das tabelas: `SSS_ENV`, senão `SSS_INSTALL_TYPE`, senão o nome da pasta `<TIPO>` acima da raiz (`sss_config.install_env`); `PROD` dá `tbsprd_` e qualquer outro valor dá `tbsdev_`. A chave `[oracle] table_prefix` é ignorada.
  - Driver: `[oracle] driver_mode` tem padrão `auto` no código (`sss_config.py`); o recomendado, usado nos modelos (`instance/exemplos/common.ini.example`) e nas instalações, é `thick`.
  - Senhas digitadas: `SSS_INIT_DB_PASSWORD` (dono do esquema, no `init_db`) e `SSS_BOOTSTRAP_ADMIN_PASSWORD` (administrador inicial).
  - Testes e homologação: `SSS_TEST_ORACLE=1` (bateria Oracle) e as `SSS_*` do roteiro de homologação (`dev/others/homologation/README.md`).

---

## 4. Decisões Técnicas e Histórico (Memória Acumulada)

O porquê completo de cada decisão está em `docs/architecture/CR-*.md` (CR-001 a CR-039) e no Apêndice A do `docs/DEPLOYMENT-SERVER.md` (decisões da implantação no 3067).

- **ADR 001 - Somente Oracle, com piso no 11gR2 (CR-002):**
  - *Contexto:* o banco da empresa é Oracle, com instâncias de 11g a 19c.
  - *Decisão Tomada:* SQL 11gR2 escrito à mão nos repositórios, sem camada de dialeto; prefixo de tabela fixo pelo ambiente (`tbsdev_` em DEV, `tbsprd_` em PROD), não parametrizado (`a75e3c1`): um DEV e um PROD convivem no mesmo owner, mas só uma instalação de cada tipo (decisão 18).
  - *Impacto:* proibida sintaxe 12c+ (`FETCH FIRST`, `IDENTITY`, JSON no banco); identificadores ≤ 30 caracteres após o prefixo; o `test_sql_oracle11g` varre o código.
- **ADR 002 - Driver adaptativo (CR-002, F7.0):**
  - *Contexto:* servidores com Pythons e clientes Oracle diferentes; o modo Thin não conecta ao 11g.
  - *Decisão Tomada:* `driver_mode = auto` (padrão do código), que sonda Thin → Thick → cx_Oracle num processo separado e usa o primeiro que conecta; os modelos e as instalações usam `thick`, o recomendado. Cliente fora do 19 só avisa (decisão 10 A); abaixo do 18.1, a sessão segue sem `call_timeout` (11 B).
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
  - *Decisão Tomada:* `--admin-login X` cria X no perfil `ADMINISTRADOR`, além dos 3 usuários do seed (`admin`, `op.prod`, `consulta`), pela mesma lista (`ddl_builder.seed_users`) no `init_db` e no SQL gerado.
  - *Impacto:* login inválido, ou igual a `op.prod` ou `consulta`, sai com código 2 (o perfil `OPERATOR_HML` e o usuário `op.hml` foram aposentados).
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
  - [x] Implantação por roteiro em servidor real (`docs/DEPLOYMENT-SERVER.md`: transferência manual pela equipe, atualização pelo passo 15.1, esquema refeito pelo 15.2 só com autorização), com `crontab`, `sss-ctl.sh` e `sss-update.sh` com retorno.
  - [x] Prefixo físico fixo por ambiente (`a75e3c1`): `tbsdev_` em DEV e `tbsprd_` em PROD, pela regra `SSS_ENV` → `SSS_INSTALL_TYPE` → pasta `<TIPO>` (fora de `PROD`, sempre `tbsdev_`). Decisão 18 (06/11/2026, DEPLOYMENT-SERVER Apêndice A): **uma instalação por tipo no owner `openrisow` do GFPR**:

    | Instalação | Onde | Prefixo | Situação |
    |---|---|---|---|
    | DEV | servidor 3067 | `tbsdev_` | migração do passo 15.3 escrita, ainda não executada |
    | PROD | servidor 3067 | `tbsprd_` | migração do passo 15.3 escrita, ainda não executada |
    | Locais | máquinas de desenvolvimento | `tbsdev_` | só sobem contra o GFPR com o 3067 parado (homologação, ensaio) |

    Os esquemas aposentados `s3dev_`, `s3prd_`, `tbsss_` e `ssdev_` seguem intactos no owner (`SSS_OUTROS_PREFIXOS`); a remoção é manual (DEPLOYMENT-SERVER §15.3.1).
  - [x] Homologação real automatizada no navegador e batimento completo docs × código (30/10/2026): rodada 4 do DEV do 3067 com 356/356 na primeira passada, já com o pacote do batimento (`docs/homologation/SSS_Homologation_Evidence_2026-10-30_r4.docx`).
  - [x] Toda automação pelo `Makefile` (34 alvos, `make help`), com `make test-matrix` de 07/11/2026: 1570 testes OK (61 pulados) em 3.6.0, 3.6.15 e 3.13.2.
- **Tarefas Pendentes / Em Progresso:**
  - [ ] Executar no 3067 a migração para o prefixo fixo (DEPLOYMENT-SERVER §15.3), com autorização e o SSS parado.
  - [ ] Decidir quando congelar a versão 1 do esquema: já há PROD no 3067. O `init_db` ainda não aplica migrações (`src/sss/cli/migrations/` vazia).
  - [ ] Definir a semântica do `--recreate` do `init_db` (README §11.1) antes de implementá-lo.
  - [ ] Decidir se o charset AL32UTF8 do README §2.2 é exigência ou recomendação: o GFPR é WE8ISO8859P15 e o SSS funciona nele.
  - [ ] Opcional: o `init_db --generate-sql` passar a usar as contas do config nos GRANTs, como o `generate_sql.py --name`.
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

### 5.1 Pendências de código

Comportamento atual, já documentado no README como tal; qualquer mudança só por CR:

- **Rede no desdobro** (README §7.5, passo 8): o erro de rede é contado, mas relançado; a regra **nunca** é pausada por rede, nem na 3ª falha seguida (só erro de banco que não é de rede chega ao `INTERNAL_ERROR`).
- **Avanço depois de `DUPLICATE_OCCURRENCE`** (§7.5, CR-008 R-31): o avanço sem ticket recalcula a decisão com um novo `SYSDATE`, e não usa a `:new_date` do passo 3; se o minuto virou, o `next_date` pode ser outro.
- **Agenda** (§7.7): "será pulada" mede o atraso pela vencida **mais antiga** (o daemon usa a mais recente), e o "Será pausada" só aparece quando não há aviso de sobreposição ("Pode ser pulada").
- **Comandos curtos no laço** (§8.1): `list_input` e `clean_output` rodam síncronos (`subprocess.run`) com prazo de 30 s dentro do laço do agente, o que pesa nas invariantes I3 e I4.
- **Falha depois do `Popen`** (§8.4, CR-008 R-01): o grupo é encerrado com 10 s entre SIGTERM e SIGKILL (`executor.DEFAULT_GRACE_S`), e não com o `kill_grace_s`.
- **Parada do agente** (§8.11): o `SHUTDOWN` espera até `kill_grace_s + 5` s; o ticket que não terminar fica `RUNNING` e é resolvido pelo startup check da subida seguinte.
- **Releitura do cancelamento** (§8.4, CR-007 R-28): `cancel_requested` é relido uma vez, antes de criar as pastas; o pedido que chega depois fica para a varredura, com o script já iniciado.
- **Perfis antigos após o MERGE** (README §4.3, D.1): num banco em uso, o seed não remove nada; `ADMINISTRATOR`, `OPERATOR_PROD`, `READ_ONLY`, `OPERATOR_HML` e `op.hml` ficam ao lado dos novos, e a limpeza é manual (§11.3).

---

## 6. Mapa Detalhado de Módulos, Esquema Oracle e Documentação

### 6.1 Hierarquia de Camadas e Módulos (`src/sss/`)

A ordem das camadas é verificada estaticamente por AST em `tests/architecture/test_layers.py` (`platform < core < config < persistence < ui < services < web`; `scheduler` acima de `persistence`; `cli` no topo):

| Camada (`src/sss/`) | Módulos Principais | Responsabilidade |
|---|---|---|
| `platform/` | `os_platform/` (`posix.py`, `ticket_files.py`), `path_guard.py`, `files_area.py` | Primitivas POSIX isoladas (spawn `start_process` sem shell, grupos de processo, sinais, lock de instância, identidade de PID, locale), subcomandos da pasta do ticket (`pack`, `clean-output`, `put-input`, `list-input`), guarda de caminhos e interpretadores e operações da Pasta de Arquivos (CR-037). |
| `core/` | `sql_ident.py`, `cron_parser.py`, `recurrence.py`, `params_compiler.py`, `masking.py`, `rbac.py`, `security.py` | Regras puras sem I/O: registro dos identificadores Oracle (≤ 30 caracteres, prefixo fixo, nome lógico `tbsss_`), CRON de 5 campos, ocorrências e *misfire*, compilação de parâmetros e snapshot, mascaramento de segredos, RBAC e senha `PBKDF2-HMAC-SHA256` com 200.000 iterações. |
| `config/` | `sss_config.py`, `app_context.py`, `sss_logging.py`, `log_paths.py` | Leitura e validação de `instance/common.ini`, `instance/<nome>/config.ini` e `instance/secrets.cfg` (invariantes I1–I4, prefixo pelo ambiente), contexto do processo, caminhos de log, saída, entrada e trabalho, e logger por minuto. |
| `persistence/` | `db_conn.py`, `ddl_builder.py`, `repo_errors.py`, `repo_factory.py`, `contracts/` (`repo_agents`, `repo_audit`, `repo_catalog`, `repo_inputs`, `repo_rbac`, `repo_schedules`, `repo_tickets`, `repo_users`), `oracle/`, `fake/` | Sondagem e conexão adaptativa (Thin → Thick → cx_Oracle), DDL, seed e validação (`ascii_sql` com `UNISTR`), exceções de contrato (`RepoNotFound`, `RepoConflict`, `RepoViolation`, `RepoUnavailable`), escolha do backend e implementações paritárias em Oracle 11gR2 (inclusive os `scheduler_*.py` do agente) e em memória (FAKE). |
| `ui/` | `ui_helpers.py`, `ui_menu.py` | Catálogo de mensagens em duas partes, rótulos de situações e motivos, mascaramento de atores e menu conforme o perfil. |
| `services/` | `auth_service.py`, `ticket_service.py`, `schedules_service.py`, `files_service.py`, `input_browse_service.py`, `output_browse_service.py`, `audit_service.py`, `agents_service.py`, `permissions_service.py`, `admin_crud.py`, `admin_{users,profiles,environments,parameters,scripts}_service.py` | Regras das telas: orquestração dos repositórios, RBAC, tradução de `RepoViolation` (constraint lógica `tbsss_*`) e auditoria transacional. |
| `scheduler/` | `scheduler_loop.py`, `executor.py`, `env_builder.py`, `log_pump.py`, `schedule_expansion.py`, `output_phase.py`, `input_phase.py` | Agente (thread única, prazos monotônicos): startup check, desdobro dos agendamentos, claim, execução e encerramento escalonado, ambiente limpo do filho, coleta de log em caracteres para `CLOB`, empacotamento da saída (`BLOB`) e entrega e retrato da entrada. |
| `web/` | `framework/` (`app`, `errors`, `markup`, `multipart`, `request`, `response`, `routing`, `server`, `session`, `static`, `storage`, `template`), `app/` (`bootstrap`, `context`, `errors`, `security`), `controllers/` (14), `templates/`, `static/` | Servidor HTTP próprio, roteamento, multipart em streaming para disco, sessão em cookie assinado, motor de templates, guarda CSRF/Origin/CSP; 14 controllers (`default`, `tickets`, `logs`, `schedules`, `outputs`, `inputs`, `files`, `audit`, `dev`, `admin_users`, `admin_profiles`, `admin_environments`, `admin_parameters`, `admin_scripts`); templates `.html` e `.load`; Bootstrap 5.3.8 e JS/CSS locais. |
| `cli/` | `run_web.py`, `run_scheduler.py`, `init_db.py`, `generate_sql.py`, `check_env.py`, `health.py`, `probe_driver.py`, `migrations/` (vazia) | Ferramentas de operação chamadas pelos invólucros de `scripts/<nome>.py` (`test_entry_points.py`). |

### 6.2 Esquema do Banco de Dados Oracle (21 Tabelas, 14 Funcionalidades e 5 Agentes)

* **Dimensões do DDL (`SCHEMA_VERSION = 1`, contadas em `docs/sql/01_deploy_sss_openrisow_tbsdev.sql`):** 21 tabelas, 21 sequences, 23 triggers, 138 constraints (21 PK, 17 UK, 27 FK, 73 CK) e 31 índices explícitos.
* **Perfis e usuários do seed:** perfis `ADMINISTRADOR`, `OPERADOR` e `CONSULTA`; usuários `admin`, `op.prod` e `consulta` (`ddl_builder.seed_users`).
* **As 21 Tabelas** (registro em `src/sss/core/sql_ident.py`, `TABLES`; nome físico `{prefixo}<nome>`, nome lógico `tbsss_<nome>`). Colunas próprias abaixo; 19 tabelas têm também as colunas de registro `created_at`, `created_by`, `updated_at` e `updated_by`, a `audit` só `created_at` e a `control` nenhuma:
  1. `environments` — `id`, `name`, `description`, `connection`, `active`, `is_production`.
  2. `profiles` — `id`, `name`, `description`, `is_admin`, `perm_version`, `active`.
  3. `features` — `id`, `code`, `name`, `module`, `description`, `active`.
  4. `profile_feature` — `id`, `profile_id`, `feature_id`.
  5. `profile_env` — `id`, `profile_id`, `environment_id`.
  6. `scripts` — `id`, `name`, `description`, `script_group`, `category`, `stage`, `interpreter`, `path_file`, `param_type`, `max_parallel_env`, `timeout_s`, `active`.
  7. `profile_script` — `id`, `profile_id`, `script_id`.
  8. `script_env` — `id`, `script_id`, `environment_id`.
  9. `users` — `id`, `login`, `name`, `password_hash`, `profile_id`, `failed_attempts`, `locked_until`, `last_login_at`, `password_changed_at`, `session_epoch`, `active`.
  10. `parameters` — `id`, `code`, `param_flag`, `label`, `description`, `component_type`, `options_json`, `default_value`, `validation_regex`, `sensitive`, `active`.
  11. `script_param` — `id`, `script_id`, `parameter_id`, `sort_order`, `required`, `default_value_override`.
  12. `schedules` — `id`, `name`, `script_id`, `environment`, `user_id`, `priority`, `recurrence_type`, `cron_expression`, `run_time`, `week_days`, `month_day`, `params_json`, `start_date`, `end_date`, `next_run_at`, `last_run_at`, `last_ticket_id`, `pause_reason`, `active`.
  13. `tickets` — `id`, `script_id`, `environment`, `requested_by`, `source_ip`, `agent_id`, `process_id`, `process_start`, `script_path`, `interpreter_path`, `interpreter_used`, `status`, `priority`, `cancel_requested`, `status_reason`, `parent_ticket_id`, `schedule_id`, `submitted_params`, `log_output` (CLOB), `log_offset_chars`, `log_truncated`, `return_code`, `scheduled_at`, `started_at`, `heartbeat_at`, `finished_at`.
  14. `ticket_answer` — `id`, `ticket_id`, `parameter_id`, `answer_value`.
  15. `agents` — `id`, `code`, `hostname`, `daemon_pid`, `version`, `environments`, `platform`, `script_base_dir`, `status`, `started_at`, `heartbeat_at`, `critical_config`.
  16. `audit` — `id`, `actor`, `source_ip`, `action`, `entity`, `entity_id`, `detail`.
  17. `control` — `id`, `schema_version`, `version_applied_at`, `version_applied_by`.
  18. `ticket_output` — `id`, `ticket_id`, `state`, `reason`, `agent_id`, `file_count`, `size_bytes`, `content` (BLOB).
  19. `input_upload` — `id`, `environment`, `script_id`, `relative_dir`, `file_name`, `size_bytes`, `sha256`, `replace_existing`, `source_ip`, `content` (BLOB).
  20. `input_delivery` — `id`, `upload_id`, `agent_id`, `state`, `reason`, `delivered_at`.
  21. `input_listing` — `id`, `agent_id`, `environment`, `script_id`, `listing`, `file_count`, `truncated`, `listed_at`, `refresh_requested_at`.
* **As 14 Funcionalidades (`features`, seed):**
  * Operação: `EXEC_SCRIPT`, `VIEW_LOGS`, `CANCEL_TICKET`, `MANAGE_SCHEDULES`, `DOWNLOAD_OUTPUT`, `UPLOAD_INPUT`, `FILES_UPLOAD`, `FILES_DOWNLOAD`.
  * Administração e Governança: `MANAGE_USERS`, `MANAGE_PROFILES`, `MANAGE_ENVIRONMENTS`, `MANAGE_SCRIPTS`, `MANAGE_PARAMETERS` (Gestão de Parâmetros), `VIEW_AUDIT`.
* **Mapeamento Padrão de Processos × Ambientes:**
  * `web0001` → servidor web da instalação.
  * `agente0001` → `GFPREPROD` | `agente0002` → `CLONE2` | `agente0003` → `CLONE1` | `agente0004` → `CLONE6` | `agente0005` → `CLONE7`.

### 6.3 Catálogo Completo da Pasta `docs/`

* **Manuais Principais (`docs/*.md`):**
  * `docs/DEPLOYMENT.md` — manual geral normativo de implantação e operação em produção (validado por `test_deployment_doc.py`).
  * `docs/DEPLOYMENT-SERVER.md` — runbook passo a passo para implantação em servidor único (Web + 5 Agentes) e Apêndice A com histórico de decisões do servidor `brtlvlty3067sl`.
  * `docs/DEV_ENVIRONMENT.md` — guia do ambiente de desenvolvimento local: pré-requisitos e compilação dos Pythons 3.6, ferramentas de lint e tipos no 3.11 (`DEV_PYTHON`), assets herméticos, `check_env`, servidor de desenvolvimento, testes, árvore `scripts_ambiente/`, Oracle real e usuários padrão.
  * `docs/HOMOLOGATION_RUNBOOK.md` — roteiro de homologação manual e automatizada.
  * `docs/UTILITY_SCRIPTS.md` — catálogo das ferramentas e scripts utilitários.
  * `docs/ADMIN_CRUD_PATTERN.md` — padrão arquitetural das 5 telas administrativas.
* **Planos de execução (`docs/explain/`):** 6 planos EXPLAIN reais das consultas dos repositórios Oracle: `AUDIT_AGENTS.md`, `CATALOG.md`, `RBAC_USERS.md`, `SCHEDULES.md` e `TICKETS.md` (agregados da F7.3) e `SCHEDULER.md` (repositório do agente, F8.3a).
* **Histórico de Change Requests (`docs/architecture/`):**
  * `CR-001` a `CR-005`: separação web/daemon, somente Oracle 11gR2 com driver adaptativo, catálogo de parâmetros, linguagem simples em duas partes, agente somente POSIX e logs por minuto.
  * `CR-006` a `CR-010`: colunas de auditoria nas 21 tabelas, hardening de HA/fencing/orçamento (`SCHEMA_VERSION`), fechamento da revisão R2, reserva da pasta `internal` e variáveis `SSS_*` dos scripts.
  * `CR-011` a `CR-015`: retirada de hash/dono de script e de credencial em parâmetro, pasta de saída (`SSS_OUTPUT_DIR` + BLOB zip), índice e busca de fila escalável, pasta de entrada (`SSS_INPUT_DIR`) e padronização de nomes em inglês.
  * `CR-016` a `CR-020`: código e banco em inglês (`CR-016a..e`), melhorias de UX no catálogo/menu/disparo (`CR-017`, `CR-018`), pasta de trabalho (`SSS_WORK_DIR`, `CR-019`) e telas de Saídas e Entrada via banco (`CR-020a..d`).
  * `CR-021` e `CR-022`: remoção completa do `web2py` e do Alpine.js com framework próprio (`CR-021a..f`) e reorganização no pacote `src/sss/` com portões `flake8` + `mypy` estrito (`CR-022a..b9`).
  * `CR-023` a `CR-027`: `script_base_dir` e caminhos relativos, interpretador informado no disparo ou `#!`, simplificação dos interpretadores (`python3`, `python`, `sh`, `bash`) e ordem de precedência (digitado → `#!` → cadastro).
  * `CR-028` a `CR-035`: estrutura `instance/<nome>/` e `var/<nome>/` com `sss-update.sh`, obrigatoriedade de `--name`/`--config`, retirada do purge e criação do `sss-keepalive.sh`, correções de `check_env`/`init_db`/`generate_sql` e simplificação de uma conta de SO e uma conta Oracle por servidor (`CR-032`).
  * `CR-036` a `CR-039`: alertas no lugar de bloqueios extremos (`CR-036`), Pasta de Arquivos só em disco (`files/<ambiente>/<script>/{inputs,outputs}`, `CR-037`), CR-036 e CR-037 no PROD (`CR-038`) e PROD com um agente por ambiente, com ensaio e homologação (`CR-039`).
  * `DEPLOYMENT-history.md` — arquivo histórico de revisões anteriores do guia de implantação.
* **Scripts SQL para o DBA (`docs/sql/`):**
  * 2 conjuntos (`tbsdev` e `tbsprd`, owner `openrisow`) × 3 arquivos: `01_deploy_sss_<owner>_<prefixo>.sql`, `02_rollback_sss_<owner>_<prefixo>.sql` e `99_validate_deploy_<owner>_<prefixo>.sql` (ex.: `01_deploy_sss_openrisow_tbsdev.sql`), gerados por `make sql-all` em ASCII puro (`UNISTR`).
* **Roteiros de Fases e Evidências de Homologação (`docs/prompts/` e `docs/homologation/`):**
  * `docs/prompts/` (`00_INDEX.md`, `F0_1_environment_skeleton.md` a `F9_2_e2e.md`, `UI_FREEZE.md`) — prompts históricos de construção incremental do SSS.
  * `docs/homologation/*.docx` e `*.md` — relatórios e evidências de homologação automatizada (mais recente: `SSS_Homologation_Evidence_2026-10-30_r4.docx`, 356/356 passos OK).

