# SSS — Prompt F9.1: Purge, hardening de implantação e runbook

## Leitura obrigatória antes de planejar
- `docs/arquitetura/CR-001-multiplataforma-e-sql-ansi.md` e `docs/arquitetura/CR-002-oracle-unico-e-driver-adaptativo.md`
- `AGENTS.md` §2.2, §3.2, §4.9, §6
- `README.md` §2.3 (seleção do driver), §2.6, §4.1, §8.0, §8.5, §8.11, §8.12, §11.3, §12.2 (incluindo o **hardening do web2py**), §13, §14
- Arquivos: `bin/*.sh`, `instance/config.ini.example`, `scripts/init_db.py`, `scripts/sondar_driver.py`, `modules/plataforma/`

## Objetivo
Fechar o produto para implantação manual em servidores air-gapped **Linux/Unix e Windows**: retenção de dados, launchers das duas plataformas, hardening do pacote e documentação operacional suficiente para operar e investigar falhas **apenas lendo logs**.

## Escopo
**IN**
- **`applications/script_scheduling_service/scripts/purge.py`** (CLI), com as opções `--config`, `--dry-run` (só conta) e `--alvo tickets|auditoria|logs_locais|todos`:
  - **Tickets:** o `DELETE` em lotes do README §11.3, **literal**, com `COMMIT` por lote (a exceção prevista no AGENTS §4.9) até `rowcount = 0`. O limite (`:limite`) é calculado **uma vez** a partir de `agora_banco()` no início.
  - **Auditoria:** o mesmo padrão, com `audit_retention_days`.
  - **Logs locais:** remove `log_dir/tickets/AAAAMM/ticket_*.log` com `mtime` mais antigo que `local_log_retention_days`, validando cada caminho sob `log_dir` (`plataforma.caminho_final` + `commonpath`), e remove os diretórios de mês vazios.
  - Registra a auditoria `PURGE` com as contagens e exibe um resumo no stdout.
  - Seguro contra execução concorrente: `plataforma.travar_instancia` em `work_dir/sss-purge.lock`.
- **`applications/script_scheduling_service/modules/repo_oracle/purge.py`:** repositório interno, importado só pelo `scripts/purge.py`, conforme a exceção do AGENTS §5.5.
- **Launchers (README §12.2):**
  - revisar `bin/sss-web.sh` e `bin/sss-scheduler.sh` (`LD_LIBRARY_PATH` do IC 19 só quando não houver `ldconfig`, `TZ`, `umask 077`, recusa de root, `exec`);
  - criar `bin/sss-web.ps1` e `bin/sss-scheduler.ps1`: IC 19 no `PATH` do processo (quando houver), `TZ`, recusa de token elevado ou SYSTEM, Python em primeiro plano (para `CTRL_BREAK` e `.stop`), código de saída repassado;
  - criar `bin/sss-stop.ps1` e `bin/sss-stop.sh`, que criam o arquivo `work_dir/sss-<agent_id>.stop` (parada controlada sem sinal).
- **`applications/script_scheduling_service/scripts/empacotar.py`** (biblioteca padrão; roda em Linux e Windows), no lugar de um script de shell:
  - gera `dist/sss-<versao>.tar.gz` **e** `dist/sss-<versao>.zip` com o mesmo conteúdo;
  - **inclui:** `web2py` (sem `applications/admin`, `welcome` e `examples`), `APP` (sem `controllers/dev.py`, `views/dev/`, `dev/`, `modules/repo_fake/`, `instance/config.ini`, `log/`, `sessions/`, `errors/` e `cache/`), `routes.py` com a aplicação padrão única, `bin/` (`.sh` e `.ps1`) e `docs/`;
  - gera um `SHA256SUMS` do conteúdo;
  - **falha** se encontrar no pacote: `secrets.cfg`, `*.pyc`, `__pycache__`, `controllers/dev.py`, `repo_fake` ou o padrão `password\s*=\s*\S` em arquivos `.ini`/`.cfg`.
- **`docs/RUNBOOK.md`:**
  - **instalação Linux/Unix:** usuário de SO dedicado sem shell, diretórios, donos e permissões conforme o README §8.5 (UIDs), `secrets.cfg` com `0600`, Instant Client 19 + `ldconfig` (obrigatório se algum banco for 11g; recomendado sempre como contingência da cadeia de driver), unit `systemd` de exemplo para o web e o scheduler (`KillMode=mixed`, `TimeoutStopSec` maior que `shutdown_grace_s + kill_grace_s`, `User=`, `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ReadWritePaths=` para `log_dir` e `work_dir`), apresentada **como exemplo a validar** com a infraestrutura;
  - **instalação Windows:** conta de serviço dedicada **sem** privilégio administrativo, árvore de scripts com dono em `script_owner_sids` e sem escrita efetiva para a conta do agente (`icacls`), `secrets.cfg`/`log_dir`/`work_dir` com ACL só da conta e SYSTEM, IC 19 e `oracle_client_lib_dir`, execução pelo Agendador de Tarefas ou pelo gerenciador de serviços da infraestrutura chamando `sss-scheduler.ps1` (sem `pywin32`), parada por `sss-stop.ps1`;
  - **driver Oracle (CR-002):** `modo_driver`, como ler a linha INFO da combinação escolhida, `check_env.py`, quando forçar `thick`/`cx_oracle`;
  - `init_db.py --dry-run` revisado pelo DBA, depois a execução real;
  - agendamento do purge (cron no POSIX; Agendador de Tarefas no Windows);
  - rotação e local dos logs;
  - **tabela de troubleshooting** "sintoma → linha de log a procurar → causa provável → ação", cobrindo: falha na inicialização por passo (§8.12), cadeia de driver (`DPY-3010` em banco 11g, `DPI-1047` sem Instant Client, erro de autenticação que interrompe a cadeia, todos os candidatos falharam), `PRECHECK_FAILED` (inclusive interpretador não mapeado no agente), `SPAWN_ERROR`, `OWNERSHIP_LOST`, `FENCED`, `NODE_OFFLINE`, `ORPHAN_PROCESS`, `LOG_LIMIT`, lock timeout no claim, agendamento pausado por cada motivo, ORA-12541/03113 (e os `DPY-*` equivalentes do Thin), recusa de usuário privilegiado e ACL inválida no Windows;
  - procedimento de rotação do `cookie_key` (invalida as sessões) e das senhas de ambiente;
  - checklist pré-produção (`sss_env = PROD`, `data_backend = ORACLE`, `allowed_origins`, `trusted_proxies`, nível de log `INFO`, apps de exemplo ausentes, `dev.py` ausente, combinação de driver registrada).
- **`applications/script_scheduling_service/scripts/test_purge.py`:** com mock, `--dry-run` sem `DELETE`; lotes até `rowcount = 0`; logs locais antigos removidos e recentes mantidos; caminho fora de `log_dir` ignorado; lock concorrente. Com `SSS_TEST_DSN`, um purge real de tickets de teste.
- **`applications/script_scheduling_service/scripts/test_empacotar.py`:** pacote gerado em diretório temporário; falha com `secrets.cfg` de teste na árvore; `tar.gz` e `zip` com a mesma lista de arquivos.

**OUT**
- Sem mudança de comportamento nas telas nem no daemon.

## Requisitos
1. O purge **nunca** remove ticket não terminal.
2. O pacote gerado não contém segredo nem código de DEV, verificado pelo próprio script.
3. Nenhuma primitiva de SO fora de `plataforma/` nos scripts Python; os `.ps1` não exigem módulos externos do PowerShell.

## Critérios de aceite
- [ ] `scripts/empacotar.py` gera os dois pacotes e falha quando um `secrets.cfg` de teste é colocado na árvore.
- [ ] O `RUNBOOK.md` permite a instalação, em Linux e em Windows, por alguém que não participou do desenvolvimento (revisão sua).
- [ ] Os testes passam. Os `.ps1` validados num Windows real, ou `NÃO TESTADO` com o motivo.

## Verificação
- `python scripts/empacotar.py && tar -tzf dist/sss-*.tar.gz | grep -E "dev.py|repo_fake|secrets.cfg|/admin/"` sem nenhuma linha.
- `python -m unittest discover -s scripts -p "test_purge.py" -v` e `-p "test_empacotar.py"`.

## Saída
Relatório AGENTS.md §9.
