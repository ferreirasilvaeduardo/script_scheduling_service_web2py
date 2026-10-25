# CR-022: Estrutura padrão do repositório

| Campo | Valor |
|---|---|
| Status | **Em andamento**. 022a aprovado pelo responsável pelo produto em 2026-10-24; plano do 022b (D6 a D10) aprovado em 2026-10-25 |
| Origem | Decisão de 2026-10-24 ("2 no CR-022"): depois do CR-021, levar o repositório ao padrão de mercado para Python. Em 2026-10-24, o responsável pediu também tirar a pasta `web2py/` (022a) |
| Restrições | Sem dependência nova (AGENTS §2.2). Python 3.6.0 a 3.13. As URLs (`/script_scheduling_service/...`), as regras de negócio, o banco e o daemon não mudam |
| Afeta | README §3.2, §12.2 e §12.3; AGENTS §3.3 e §7; `docs/DEPLOYMENT.md`; `docs/DEV_ENVIRONMENT.md`; launchers, `package.py`, testes e o roteiro de homologação |

---

## 1. Situação de partida

Depois do CR-021, o repositório não tinha mais nada do web2py, mas mantinha a forma dele: raiz em `/portaloptrib/TESHUVA/SSS/DEV/web2py`, com a aplicação em `applications/script_scheduling_service/` e o `bin/` ao lado de `applications/`. O pacote extraía em `/opt/sss/web2py`.

---

## 2. Decisões (022a)

| # | Decisão |
|---|---|
| D1 | A aplicação passa a ser a raiz do repositório: o conteúdo de `applications/script_scheduling_service/` sobe para a raiz, junto com o `bin/`. Saem `applications/` e os `__init__.py` que só existiam para o web2py |
| D2 | A pasta do repositório no DEV passa de `/portaloptrib/TESHUVA/SSS/DEV/web2py` para `/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service`, sem link com o nome antigo |
| D3 | Nos servidores, o pacote extrai em `/opt/sss/app` (antes `/opt/sss/web2py`); `W` = `APP` no DEPLOYMENT |
| D4 | O pacote usa lista de permissão da raiz (`bin/` de produção, `AGENTS.md`, `README.md` e as pastas da aplicação), porque a raiz agora também tem `.git`, `Makefile`, `input/`, `output/` e outros arquivos da máquina de desenvolvimento |
| D5 | O rodapé mostra a versão do pacote (`sss_config.SSS_VERSION`), a mesma do nome do pacote e do log do agente; antes era um `0.1.0` fixo herdado do web2py |

## 2b. Decisões (022b, aprovadas em 2026-10-25)

Estrutura alvo:

```text
bin/                 launchers .sh e sss-helper (sem mudança)
scripts/             operação no servidor (systemd, cron, Nagios): invólucros finos → sss.cli.*
tools/               build e desenvolvimento (package.py), fora do pacote
src/sss/
  config/            sss_config, app_context, sss_logging, log_paths
  core/              cron_parser, recurrence, params_compiler, masking, rbac, security, sql_ident
  platform/          os_platform (posix), path_guard
  persistence/       db_conn, ddl_builder, repo_errors, repo_factory; contracts/ (repo_*), oracle/, fake/
  ui/                ui_helpers (catálogo de mensagens), ui_menu
  services/          admin_crud, admin_*_service e os demais *_service
  scheduler/         scheduler_loop, executor, env_builder, log_pump, input_phase, output_phase, schedule_expansion
  web/               framework/ (núcleo), app/ (montagem), controllers/, templates/, static/
  cli/               código das ferramentas de operação
tests/
  unit/<espelho de src/sss>   sem banco, sem rede, sem processo filho (FAKE e mocks)
  integration/oracle/         precisa do Oracle real (SSS_TEST_ORACLE=1)
  integration/process/        sobe processos reais (launchers, helper, executor, agente)
  functional/                 aplicação inteira por HTTP, servidor real e backend FAKE
  architecture/               lê código e documentos (compatibilidade 3.6, regras por AST, pacote, camadas)
  support/                    auxiliares (_testenv, _oracle_test_support, _output_memory)
dev/                 seed de scripts, web_harness e homologação (sem mudança)
```

Dependências permitidas entre camadas: `web → services → (persistence, ui, core, config)`; `scheduler → (persistence, platform, core, config)`; `cli` pode usar todas. `ui_helpers` fica fora de `web/` porque todos os serviços usam o catálogo de mensagens (AGENTS §8).

| # | Decisão |
|---|---|
| D6 | Pontos de entrada: `scripts/*.py` ficam como invólucros finos (põem `src/` no caminho e chamam `sss.cli.<nome>.main()`), únicos lugares que mexem no `sys.path`. Os comandos de operação dos servidores (systemd, cron, Nagios, DEPLOYMENT) não mudam. Sem `pip install` (AGENTS §2.2) |
| D7 | Lint e tipos graduais: 99 colunas e mypy estrito valem para arquivo novo ou alterado; a dívida atual (flake8: 884 achados a 240 colunas e 4.802 linhas acima de 99; mypy: 277 erros; 150 de 1.726 funções anotadas, medidos em 2026-10-25) fica listada por arquivo e é paga depois do 022b10, um subpacote por vez |
| D8 | `views/` e `static/` vão para `src/sss/web/templates/` e `src/sss/web/static/`; as URLs dos estáticos não mudam |
| D9 | Pacote de import `sss` (`src/app` foi considerado e recusado: nome genérico, sujeito a colisão no caminho de import, sem identidade em traceback e log, e confuso com `/opt/sss/app`). `tools/` só para build e desenvolvimento; a operação fica em `scripts/` |
| D10 | Testes classificados pelo recurso que usam (tabela acima); arquivo com casos de categorias diferentes é dividido. Os testes de ponta a ponta são a homologação no navegador, que fica em `dev/homologation/` |

Cada passo move uma camada e reescreve **todos** os importadores dela no mesmo commit, para um módulo nunca ficar carregado com dois nomes (`ticket_service` e `sss.services.ticket_service`), o que duplicaria as classes de exceção. Cada passo termina com a suíte nas 3 versões, lint sem piorar e a documentação que ele toca atualizada.

---

## 3. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 022a | Aplicação na raiz do repositório e pasta sem `web2py` (D1 a D5): launchers, `package.py` (lista de permissão), `posix.PACKAGE_HELPER` (`../../bin/sss-helper`), testes que subiam três níveis até o `bin/`, `.gitignore`, `Makefile`, `CLAUDE.md`, README, AGENTS, DEPLOYMENT (§18 com a primeira atualização para `/opt/sss/app`) e DEV_ENVIRONMENT. Defeito pego pela suíte: o `PACKAGE_HELPER` subia quatro níveis e não acharia o helper do pacote. Validação depois da renomeação da pasta (2026-10-25): suíte de 1470 testes OK em 3.6.0, 3.6.8 e 3.13.2; pacote gerado de cópia limpa; homologação real r1 com 275 OK e 8 falhas (scripts de diagnóstico cadastrados em rodadas anteriores com o caminho antigo; roteiro corrigido) e r2 com 283/283 (`docs/homologation/SSS_Homologation_Evidence_2026-10-25_r2.docx`) | Concluído |
| 022b1 | `tests/` fora de `scripts/` (D10): 72 arquivos movidos com `git mv` para `unit/<camada>/` (56), `integration/oracle/` (3), `integration/process/` (4), `functional/` (2) e `architecture/` (7), mais os auxiliares em `support/`; 12 arquivos divididos, com a parte que precisa do Oracle real em `integration/oracle/<arquivo>_oracle.py` (o `TestOracleCatalog` fica na bateria progressiva, porque usa o banco com `SSS_TEST_REPO_AGREGADO=CATALOGO`). Critério refinado na execução: subprocesso só para isolar import não tira o teste de `unit/`; vai para `integration/process/` o teste cujo assunto é o processo. `_testenv` com `APP_DIR` e `scripts/` no caminho (até o 022b8); comando `python -m unittest discover -s tests -t .`; alvos `test-unit`, `test-integration`, `test-functional`, `test-architecture` e `test-all`; `tests/` passa a ser lintado (o Makefile o excluía, herança do modelo). Defeitos de teste pegos: `test_py36_compat` e `test_deployment_doc` calculavam a raiz pela própria pasta (a varredura cobriria só `tests/`); 16 imports de auxiliar dentro de função só quebrariam com o Oracle ligado; a checagem de testes no pacote da árvore real nunca falhava (`"/scripts/test_"` com caminho relativo). Mesmos 1510 casos antes e depois (lista por classe e método); flake8 nos testes de 477 para 462 achados | Concluído |
| 022b2 | `tools/package.py` (D9), fora do pacote | Pendente |
| 022b3 | Esqueleto `src/sss/`, `config/` e `core/`, com todos os importadores reescritos | Pendente |
| 022b4 | `platform/` e `persistence/` (`contracts/`, `oracle/`, `fake/`) | Pendente |
| 022b5 | `ui/` e `services/` | Pendente |
| 022b6 | `scheduler/` | Pendente |
| 022b7 | `web/` (`framework/`, `app/`, `controllers/`, `templates/`, `static/`) (D8) | Pendente |
| 022b8 | `sss/cli/` e `scripts/` como invólucros finos (D6); sai o `modules/` | Pendente |
| 022b9 | `pyproject.toml`, 99 colunas e tipagem gradual (D7); teste de regra das dependências entre camadas | Pendente |
| 022b10 | Revisão rigorosa da documentação e dos prompts; homologação real completa; encerra o CR-022b | Pendente |

---

## 4. Riscos

* **Caminhos fora do repositório:** o link `/opt/automacoes/scripts/utilitarios` (do root) e os caminhos absolutos do `instance/config.ini` do DEV apontavam para a pasta antiga e são refeitos à mão; scripts cadastrados no DEV não rodam enquanto o link não for refeito. Também os cadastros de script do banco do DEV com caminho absoluto da pasta antiga (caso dos `diag_*` da homologação, que o roteiro agora corrige ao reaproveitar).
* **Servidores:** a primeira atualização para esta versão muda a pasta (`/opt/sss/web2py` → `/opt/sss/app`) e os caminhos de operação (DEPLOYMENT §18); o retorno é subir de novo pela pasta antiga, que fica intacta.
