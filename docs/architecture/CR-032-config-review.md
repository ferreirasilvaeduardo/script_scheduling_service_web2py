# CR-032: Revisão de toda a parametrização dos configs

| Campo | Valor |
|---|---|
| Status | **Registrada** em 2026-10-27, pendente (depois do CR-031) |
| Origem | Pedido do responsável pelo produto: verificar toda a parametrização dos `config.ini` e `secrets.cfg`, inclusive as chaves não obrigatórias e as que têm padrão, para ver o que pode ser simplificado ou até retirado |
| Objetivo | Config funcional e prático, sem abrir mão da funcionalidade |
| Restrições | Python 3.6.0 a 3.13; sem dependência nova; o ambiente real tem um usuário de banco e um usuário do sistema operacional, só DEV e PROD, `sss_env = DEV` nos dois (CR-028 D12, CR-030) |

## 1. Escopo

Cada chave de `sss_config.SCHEMA` (`[app]`, `[oracle]`, `[secrets]`, `[agent]`, `[logging]`, `[web]`) e cada seção do `secrets.cfg`, inclusive as que só existem para cenários que o ambiente real não usa (usuários de execução, helper, `sudo`, contas por papel, modo do driver, pool, monitor separado).

Para cada chave, registrar numa tabela:

* quem a lê no código e o que acontece com o valor padrão;
* se alguém já precisou mudá-la (DEV, homologações, ensaios);
* proposta: **manter**, **manter com outro padrão**, **juntar com outra**, **tornar fixa no código** ou **retirar** (com o tratamento das linhas antigas: ignorar com aviso, como no CR-026 e no CR-030);
* risco de cada proposta para a funcionalidade.

## 2. Forma de trabalho

1. Levantamento completo (tabela acima), sem mudar código.
2. Decisões apresentadas uma por vez, com opções A/B e recomendação.
3. Plano com os passos aprovados; implementação, testes, documentação (README §12.1, DEPLOYMENT, AGENTS) e relatório §9 por passo.

## 3. Levantamento (2026-10-27)

Feito no código (`sss_config.SCHEMA` e quem lê cada chave). Propostas: **M** manter; **F** tornar fixa no código; **R** retirar (linha antiga ignorada com aviso); **D** decisão do responsável. "Do nome": sai do `[app] name` (CR-028).

### 3.1 Achados que pedem retirada direta

| Chave | Achado | Proposta |
|---|---|---|
| `[agent] claim_batch_size` | Não é lida por nenhum código: o claim pega tantos tickets quantas vagas livres o agente tem | R |
| `[agent] max_parallel_hard_limit` | Só serve para recusar um `max_parallel_jobs` maior que ela; não limita nada em execução | R (o teto passa a ser a faixa de `max_parallel_jobs`) |
| `[oracle] oracle_client_lib_dir` | Só vale no macOS (`is_macos`); o agente é só POSIX/Linux desde o CR-005 | R |

### 3.2 Todas as chaves

| Seção | Chave | Padrão | Quem lê | Proposta |
|---|---|---|---|---|
| app | `sss_env` | — (obrigatória) | segurança, cadastro, CLIs | M |
| app | `name` | vazio | pastas, `agent_id` (CR-028) | D: tornar obrigatória (fim do formato antigo sem nome) |
| oracle | `user` | — (obrigatória) | conexões | D: opcional, padrão = `owner` (conta única) |
| oracle | `dsn`, `owner`, `table_prefix` | — (obrigatórias) | conexões, SQL | M |
| oracle | `driver_mode` | `auto` | `db_conn` | D: padrão `thick` (o recomendado; tira a linha dos modelos) |
| oracle | `call_timeout_ms` | 30000 | conexões, invariantes I3/I4 | M |
| oracle | `pool_min`, `pool_max` | 1, 4 | pool do web | F (ajuste fino nunca usado) |
| secrets | `secrets_file` | pasta do `config.ini` | todos | D: retirar (sempre ao lado do config, CR-028) |
| agent | `agent_id` | do nome | agente, telas | D: retirar se `name` for obrigatória |
| agent | `environments`, `max_parallel_jobs` | — (obrigatórias) | agente | M |
| agent | `work_dir` | do nome | agente | D: retirar se `name` for obrigatória (só pelo nome) |
| agent | `exec_users`, `exec_work_dir`, `helper_path` | vazio, do nome, `../sss-root/...` | execução com `sudo` | D: manter para um futuro com administrador, ou retirar o modo `sudo`/helper inteiro (o ambiente real nunca usa) |
| agent | `schedule_batch_size` | 50 | desdobro | F |
| agent | `orchestrator_interval_s`, `cancel_poll_interval_s` | 10, 2 | laço do agente | F |
| agent | `heartbeat_interval_s`, `fence_timeout_s`, `node_offline_timeout_s` | 10, 90, 180 | agente, web, `health.py` | D: F (precisam ser iguais em todos os processos; fixos, some o `[agent]` parcial do web, D13) |
| agent | `kill_grace_s` | 5 | encerramento | F |
| agent | `script_timeout_s` | 604800 | agente | M (pedido de 2026-10-27; o cadastro do script vence) |
| agent | `shutdown_mode`, `shutdown_grace_s` | TERMINATE, 30 | parada | D: F, ou manter o `DRAIN` como opção |
| agent | `misfire_policy` | RUN_ONCE | desdobro, tela de agendamentos | M (usado na restauração, DEPLOYMENT §17) |
| agent | `misfire_tolerance_s`, `cron_horizon_days` | 300, 1461 | desdobro, telas | F |
| agent | `queue_aging_min` | 60 | fila, tela de tickets | F |
| agent | `log_dir_min_free_mb` | 1024 | trava de claim por disco | M |
| agent | `output_dir`, `input_dir`, `script_work_dir`, `script_base_dir` | do nome | agente | M (escrita vazia desliga; caminho próprio quando preciso) |
| agent | `output_max_bytes`, `output_max_files` | 20 MiB, 1000 | saída | M |
| agent | `child_locale` | C.UTF-8 | ambiente do script | F |
| agent | `env_passthrough` | vazio | ambiente do script | M |
| logging | `log_dir` | do nome | todos | D: retirar se `name` for obrigatória |
| logging | `level` | INFO | todos | M |
| logging | `app_log_max_bytes`, `max_log_size_bytes`, `max_local_log_size_bytes` | 10 MiB, 5 MiB, 50 MiB | logs | M |
| web | `allowed_origins` | — (obrigatória) | CSRF | M |
| web | `trusted_proxies` | vazio | IP do cliente | M |
| web | `session_idle_timeout_s`, `session_max_hours`, `login_max_attempts`, `login_lockout_s` | 1800, 12, 5, 900 | sessão e login | M (política de segurança da empresa) |
| web | `log_poll_interval_s` | 3 | tela do ticket | F |
| web | `input_upload_max_bytes` | 50 MiB | tela de Entrada | M |
| web | `max_threads`, `socket_timeout_s` | 16, 30 | servidor web | F |
| segredos | `[oracle] password`, `[web] cookie_key`, `[environment:*]` | — | conexões, sessão, scripts | M |
| segredos | `[monitor]` | conta do `[oracle]` em DEV (CR-030) | `health.py` | M |

### 3.3 Efeito se tudo for aprovado

O `config.ini` do agente ficaria com `sss_env`, `name`, `[oracle]` (`dsn`, `owner`, `table_prefix`, e `user` só se diferente do owner), `environments`, `max_parallel_jobs` e, quando preciso, `env_passthrough`, `script_timeout_s`, `level` e caminhos próprios. O do web, com `sss_env`, `name`, `[oracle]` e `allowed_origins`. Sairiam 3 chaves mortas (§3.1), cerca de 14 ficariam fixas no código e 5 dependem das decisões D.
