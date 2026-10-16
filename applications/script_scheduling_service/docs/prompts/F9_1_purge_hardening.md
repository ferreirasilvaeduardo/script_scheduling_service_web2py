# SSS — Prompt F9.1: Purge, hardening de implantação e runbook

## Leitura obrigatória antes de planejar
- `docs/arquitetura/CR-002-oracle-unico-e-driver-adaptativo.md` e `docs/arquitetura/CR-005-posix-caminho-livre-e-logs.md` (revoga Windows do CR-001, caminho livre e logs por minuto)
- `docs/arquitetura/CR-003-correcoes-pos-analise.md` (D7, D12 e o passo P10: pastas de runtime e launcher restrito)
- `AGENTS.md` §2.2, §3.2, §4.9, §6
- `README.md` §2.3 (seleção do driver), §2.6, §4.1, §4.4 (tabela de entidade por ação: `PURGE`), §8.0, §8.4 (logs de execução), §8.5 (validação de caminho e UIDs), §8.9 ("Mesmos tempos em todos os nós"), §8.11, §8.12, §11.3, §12.1, §12.2 (inteiro: launchers restritos, pacote, **pastas de runtime do web2py** e **hardening do web2py**), §13, §14
- Arquivos: `bin/*.sh` (o `sss-web.sh` já tem a restrição de comando do P10 do CR-003), `docs/IMPLANTACAO.md`, `instance/config.ini.example`, `scripts/init_db.py`, `scripts/sondar_driver.py`, `modules/plataforma/`, `modules/pastas_log.py`

## Objetivo
Fechamento do produto para implantação manual em servidores air-gapped **POSIX (Linux e Unix — CR-005)**: retenção de dados, launchers POSIX, hardening do pacote e documentação operacional suficiente para operar e investigar falhas **apenas lendo logs**.

## Escopo
**IN**
- **`applications/script_scheduling_service/scripts/purge.py`** (CLI), com as opções `--config`, `--dry-run` (só conta) e `--alvo tickets|auditoria|logs_locais|todos`:
  - **Tickets:** o `DELETE` em lotes do README §11.3, **literal**, com `COMMIT` por lote (a exceção prevista no AGENTS §4.9) até `rowcount = 0`. O limite (`:limite`) é calculado **uma vez** a partir de `agora_banco()` no início.
  - **Auditoria:** o mesmo padrão, com `audit_retention_days`.
  - **Logs locais (CR-005):** remove logs de execução sob `log_dir/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log` com data mais antiga que `local_log_retention_days`, validando cada caminho sob `log_dir` (`plataforma.caminho_final` + `commonpath`), e remove os diretórios vazios. A pasta `app/` é preservada (gerida pela retenção própria do app log).
  - Registra a auditoria `PURGE` com **uma linha por tabela purgada**, com `entidade` = a tabela (`tbsss_tickets` ou `tbsss_auditoria`), `entidade_id` nulo e a contagem no `detalhe` (README §4.4), e exibe um resumo no stdout. Logs locais não são tabela e não geram linha própria (a contagem vai no log da aplicação e no resumo).
  - Seguro contra execução concorrente: `plataforma.travar_instancia` em `work_dir/sss-purge.lock`.
- **`applications/script_scheduling_service/modules/repo_oracle/purge.py`:** repositório interno, importado só pelo `scripts/purge.py`, conforme a exceção do AGENTS §5.5.
- **Launchers POSIX (README §12.2, CR-005):**
  - revisar `bin/sss-web.sh` e `bin/sss-scheduler.sh` (`LD_LIBRARY_PATH` do IC 19 só quando não houver `ldconfig`, `TZ`, `umask 077`, recusa de root, `exec`, e **somente** o processo Python do SSS: as três formas aceitas do README §12.2, outro comando recusado com código 2, sem `exec "$@"` livre). O `sss-scheduler.sh` segue a mesma restrição, aceitando só a linha do daemon do README §3.1;
  - todos os launchers executam a partir da **raiz do web2py**, para que o web2py não crie `applications/`, `deposit/`, `logs/` e `site-packages/` dentro da aplicação (README §12.2, "Pastas de runtime do web2py");
  - criar `bin/sss-stop.sh`, que cria o arquivo `work_dir/sss-<agent_id>.stop` (parada controlada sem sinal).
- **`applications/script_scheduling_service/scripts/empacotar.py`** (biblioteca padrão):
  - gera `dist/sss-<versao>.tar.gz` **e** `dist/sss-<versao>.zip` com o mesmo conteúdo;
  - **inclui:** `web2py` (sem `applications/admin`, `welcome` e `examples`), `APP` (sem `controllers/dev.py`, `views/dev/`, `dev/`, `modules/repo_fake/`, `instance/config.ini`, `log/`, `sessions/`, `errors/` e `cache/`), `routes.py` com a aplicação padrão única, `bin/*.sh` e `docs/`;
  - **não** inclui as pastas de runtime do web2py criadas dentro da aplicação (`applications/script_scheduling_service/applications/`, `deposit/`, `logs/`, `site-packages/`; README §12.2);
  - inclui um **único `config.ini` de referência** (`instance/config.ini.example`) para os tempos `fence_timeout_s` e `node_offline_timeout_s`, idênticos para todos os agentes (README §8.9, D7). O RUNBOOK orienta copiar esses dois valores sem alteração em cada nó;
  - gera um `SHA256SUMS` do conteúdo;
  - **falha** se encontrar no pacote: `secrets.cfg`, `*.pyc`, `__pycache__`, `controllers/dev.py`, `repo_fake` ou o padrão `password\s*=\s*\S` em arquivos `.ini`/`.cfg`.
- **`docs/RUNBOOK.md`:**
  - **instalação Linux/Unix (POSIX):** usuário de SO dedicado sem shell, diretórios, donos e permissões conforme o README §8.5 (UIDs), `secrets.cfg` com `0600`, Instant Client 19 + `ldconfig` (obrigatório se algum banco for 11g; recomendado sempre como contingência da cadeia de driver), unit `systemd` de exemplo para o web e o scheduler (`KillMode=mixed`, `TimeoutStopSec` maior que `shutdown_grace_s + kill_grace_s`, `User=`, `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ReadWritePaths=` para `log_dir` e `work_dir`), apresentada **como exemplo a validar** com a infraestrutura;
  - **driver Oracle (CR-002):** `modo_driver`, como ler a linha INFO da combinação escolhida, `check_env.py`, quando forçar `thick`/`cx_oracle`;
  - `init_db.py --dry-run` revisado pelo DBA, depois a execução real;
  - **caminho livre e permissões (CR-005):** caminho absoluto `path_file`, UIDs de execução em `script_owner_uids`, checagens de permissão de escrita e árvores de diretórios até a raiz;
  - **tempos de fencing:** `fence_timeout_s` e `node_offline_timeout_s` iguais em todos os agentes, conferidos pela linha INFO de cada um (README §8.9);
  - agendamento do purge (cron no POSIX);
  - rotação e local dos logs por minuto e retenção (CR-005);
  - **tabela de troubleshooting** "sintoma → linha de log a procurar → causa provável → ação", cobrindo: falha na inicialização por passo (§8.12, inclusive permissão de script fora do padrão e mais de uma thread antes do primeiro spawn), configuração inválida (CRITICAL no log ou no stderr, §12.1), cadeia de driver (`DPY-3010` em banco 11g, `DPI-1047` sem Instant Client, erro de autenticação que interrompe a cadeia, todos os candidatos falharam), `PRECHECK_FAILED` (inclusive interpretador não mapeado no agente e snapshot de versão anterior à 4), ticket que nunca sai de `PENDING` porque nenhum agente tem o interpretador do script, `SPAWN_ERROR`, `OWNERSHIP_LOST`, `FENCED`, `NODE_OFFLINE`, `ORPHAN_PROCESS`, `LOG_LIMIT`, lock timeout no claim, agendamento pausado por cada motivo, ORA-12541/03113 (e os `DPY-*` equivalentes do Thin), recusa de usuário root;
  - procedimento de rotação do `cookie_key` (invalida as sessões) e das senhas de ambiente;
  - checklist pré-produção (`sss_env = PROD`, `data_backend = ORACLE`, `allowed_origins`, `trusted_proxies`, nível de log `INFO`, apps de exemplo ausentes, `dev.py` ausente, combinação de driver registrada).
- **`applications/script_scheduling_service/scripts/test_purge.py`:** com mock, `--dry-run` sem `DELETE`; lotes até `rowcount = 0`; uma linha `PURGE` por tabela purgada, com a entidade da tabela; logs locais antigos removidos e recentes mantidos; caminho fora de `log_dir` ignorado; lock concorrente. Com `SSS_TEST_DSN`, um purge real de tickets de teste.
- **`applications/script_scheduling_service/scripts/test_empacotar.py`:** pacote gerado em diretório temporário; falha com `secrets.cfg` de teste na árvore; `tar.gz` e `zip` com a mesma lista de arquivos; pastas de runtime do web2py (`applications/`, `deposit/`, `logs/`, `site-packages/` dentro da aplicação) ausentes do pacote.

**OUT**
- Sem mudança de comportamento nas telas nem no daemon.

## Requisitos
1. O purge **nunca** remove ticket não terminal.
2. O pacote gerado não contém segredo nem código de DEV, verificado pelo próprio script.
3. Nenhuma primitiva de SO fora de `plataforma/` nos scripts Python.

## Critérios de aceite
- [ ] `scripts/empacotar.py` gera os dois pacotes e falha quando um `secrets.cfg` de teste é colocado na árvore.
- [ ] O `RUNBOOK.md` permite a instalação em Linux/Unix por alguém que não participou do desenvolvimento (revisão sua).
- [ ] Os testes passam.

## Verificação
- `python scripts/empacotar.py && tar -tzf dist/sss-*.tar.gz | grep -E "dev.py|repo_fake|secrets.cfg|/admin/"` sem nenhuma linha.
- `python -m unittest discover -s scripts -p "test_purge.py" -v` e `-p "test_empacotar.py"`.

## Saída
Relatório AGENTS.md §9.
