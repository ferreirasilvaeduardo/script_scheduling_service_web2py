# SSS — Prompt F9.1: Purge, hardening de implantação e runbook

## Leitura obrigatória antes de planejar
- `AGENTS.md` §4.9, §6
- `README.md` §11.3, §12.2 (incluindo o **hardening do web2py**), §13, §14
- Arquivos: `bin/*.sh`, `instance/config.ini.example`, `scripts/init_db.py`

## Objetivo
Fechar o produto para implantação manual em servidores air-gapped: retenção de dados, hardening do pacote e documentação operacional suficiente para operar e investigar falhas **apenas lendo logs**.

## Escopo
**IN**
- **`applications/script_scheduling_service/scripts/purge.py`** (CLI), com as opções `--config`, `--dry-run` (só conta) e `--alvo tickets|auditoria|logs_locais|todos`:
  - **Tickets:** o `DELETE` em lotes do README §11.3, **literal**, com `COMMIT` por lote (a exceção prevista no AGENTS §4.9) até `rowcount = 0`. O limite (`:limite`) é calculado **uma vez** a partir de `agora_banco()` no início.
  - **Auditoria:** o mesmo padrão, com `audit_retention_days`.
  - **Logs locais:** remove `log_dir/tickets/AAAAMM/ticket_*.log` com `mtime` mais antigo que `local_log_retention_days`, validando cada caminho com `path_guard` sob `log_dir`, e remove os diretórios de mês vazios.
  - Registra a auditoria `PURGE` com as contagens e exibe um resumo no stdout.
  - Deve ser seguro contra execução concorrente: `flock` em `work_dir/sss-purge.lock`.
- **`applications/script_scheduling_service/modules/repo_oracle/purge.py`:** repositório interno, importado só pelo `scripts/purge.py`, conforme a exceção do AGENTS §5.5.
- **`bin/sss-package.sh`:** gera `dist/sss-<versao>.tar.gz` para a implantação manual.
  - **Inclui:** `web2py` (sem `applications/admin`, `welcome` e `examples`), `APP` (sem `controllers/dev.py`, `views/dev/`, `dev/`, `modules/repo_fake/`, `instance/config.ini`, `log/`, `sessions/`, `errors/` e `cache/`), `routes.py` com a aplicação padrão única, `bin/` e `docs/`.
  - Gera um `SHA256SUMS` do conteúdo.
  - **Falha** se encontrar algum desses no pacote: `secrets.cfg`, `*.pyc`, `controllers/dev.py`, `repo_fake` ou o padrão `password\s*=\s*[^C]` em arquivos `.ini`.
- **`docs/RUNBOOK.md`:**
  - instalação passo a passo (usuário de SO dedicado sem shell, diretórios, permissões e donos conforme o README §8.5, `secrets.cfg` com `0600`, Instant Client 19 + `ldconfig`, `init_db.py --dry-run` revisado pelo DBA, depois a execução real);
  - unit `systemd` de exemplo para o web e o scheduler (`KillMode=mixed`, `TimeoutStopSec` maior que `shutdown_grace_s + kill_grace_s`, `User=`, `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ReadWritePaths=` para `log_dir` e `work_dir`), apresentada **como exemplo a validar** com a equipe de infraestrutura;
  - `cron` do purge;
  - rotação e local dos logs;
  - **tabela de troubleshooting** "sintoma → linha de log a procurar → causa provável → ação", cobrindo: falha na inicialização por passo (§8.12), `PRECHECK_FAILED`, `SPAWN_ERROR`, `OWNERSHIP_LOST`, `FENCED`, `NODE_OFFLINE`, `ORPHAN_PROCESS`, `LOG_LIMIT`, lock timeout no claim, agendamento pausado por cada motivo, ORA-12541/03113 e a recusa de Thick/IC;
  - procedimento de rotação do `cookie_key` (invalida as sessões) e das senhas de ambiente;
  - checklist pré-produção (`sss_env = PROD`, `data_backend = ORACLE`, `allowed_origins`, `trusted_proxies`, nível de log `INFO`, apps de exemplo ausentes, `dev.py` ausente).
- **`applications/script_scheduling_service/scripts/test_purge.py`:** com mock, `--dry-run` sem `DELETE`; lotes até `rowcount = 0`; logs locais antigos removidos e recentes mantidos; caminho fora de `log_dir` ignorado; lock concorrente. Com `SSS_TEST_DSN`, um purge real de tickets de teste.

**OUT**
- Sem mudança de comportamento nas telas nem no daemon.

## Requisitos
1. O purge **nunca** remove ticket não terminal.
2. O pacote gerado não contém segredo nem código de DEV, verificado pelo próprio script.

## Critérios de aceite
- [ ] `bin/sss-package.sh` gera o pacote e falha quando um `secrets.cfg` de teste é colocado na árvore.
- [ ] O `RUNBOOK.md` permite a instalação por alguém que não participou do desenvolvimento (revisão sua).
- [ ] Os testes passam.

## Verificação
- `bash bin/sss-package.sh && tar -tzf dist/sss-*.tar.gz | grep -E "dev.py|repo_fake|secrets.cfg|/admin/"` sem nenhuma linha.
- `python -m unittest discover -s scripts -p "test_purge.py" -v`

## Saída
Relatório AGENTS.md §9.
