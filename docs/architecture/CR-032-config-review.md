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

## 4. Decisões (2026-10-27, uma por vez)

| # | Decisão |
|---|---|
| D1 | A: retirar `claim_batch_size`, `max_parallel_hard_limit` e `oracle_client_lib_dir` (linha antiga ignorada com aviso) |
| D2 | A: fixar no código `orchestrator_interval_s` (10), `cancel_poll_interval_s` (2), `kill_grace_s` (5), `schedule_batch_size` (50), `misfire_tolerance_s` (300), `cron_horizon_days` (1461), `queue_aging_min` (60), `child_locale` (C.UTF-8), `pool_min`/`pool_max` (1/4), `max_threads` (16), `socket_timeout_s` (30) e `log_poll_interval_s` (3) |
| D3 | A: fixar `heartbeat_interval_s` (10), `fence_timeout_s` (90) e `node_offline_timeout_s` (180); I3/I4 viram limite do `call_timeout_ms` (até 40 s); o `[agent]` parcial do web (CR-028, D13) fica só com `misfire_policy` |
| D4 | A: `[app] name` obrigatório; `agent_id`, `work_dir`, `log_dir` e `secrets_file` sempre derivados do nome; fim do formato único (`[web]` e `[agent]` no mesmo arquivo); testes passam a usar configs por processo |
| D5 | B: `[oracle] user` continua obrigatório |
| D6 | B: `driver_mode` continua com padrão `auto` |
| D7 | B: retirar o modo `sudo`/helper inteiro (`exec_users`, `exec_work_dir`, `helper_path`, `sudoers`, conferências, DEPLOYMENT §4.1/§4.2/§8); empacotar a saída, gravar e listar a entrada e limpar pastas continuam no agente, com a própria conta |
| D8 | A: retirar o papel monitor (`[monitor]`, GRANTs, papel no `db_conn`); o `health.py` usa a conta do próprio processo |
| D9 | B: parada fixa em `TERMINATE` com 30 s (`shutdown_mode` e `shutdown_grace_s` saem) |
| D10 | A: o PROD continua com `sss_env = DEV` (D12 do CR-028): os usuários acessam por HTTP, sem proxy HTTPS (senha e cookie de sessão abertos na rede interna: risco aceito, DEPLOYMENT §4.0) |
| D11 | A: retirar o `[app] sss_env` (passo 032c); DEV e PROD idênticos por construção. Comportamento único: cookie `Secure` só quando a requisição chega por HTTPS; origem das `allowed_origins` e do próprio `Host`; conta Oracle igual ao owner aceita; seção de outro papel nos segredos só gera aviso; ambiente atendido sem credencial no `secrets.cfg` do agente recusa a subida; `init_db` mantém a trava de esquema descartável (`--real-schema`); tela `/dev`, FAKE e scripts em `dev/` só onde existem (o repositório; o pacote não os leva); a faixa de ambiente vem da pasta `<TIPO>` |

### 4.1 Decisões D12 a D17 (2026-10-27, depois do 032a)

| # | Decisão |
|---|---|
| D12 | A: o processo cria na subida as pastas que faltarem (modos de hoje, uma linha no log por pasta criada); o `prepare_dirs.py` sai; continua recusando pasta existente inutilizável (link, outro dono, modo errado) |
| D13 | A: saída e entrada por chamadas diretas no agente (zip em segundo plano, sem travar o laço; mesmas validações de caminho); sai o `bin/sss-helper` |
| D14 | A: um `instance/secrets.cfg` compartilhado (`[oracle]`, `[web]`, `[environment:*]`); configs continuam um por processo; `secrets.cfg` antigo em `instance/<nome>/` lido com aviso para mover |
| D15 | A: DEPLOYMENT só com o caminho real (roteiro do §4.0); saem o cenário com administrador, `systemd`, apêndice B e a migração de `/opt/sss/app`; notas por versão só as da estrutura nova |
| D16 | A: `critical_config` só com `call_timeout_ms` e `misfire_policy` (atualização com todos os agentes parados) |
| D17 | B: o `check_env.py` fica |

## 5. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 032a | D1, D2, D3, D9 | Concluído (cf886f3) |
| 032b | D4 (`name` obrigatório, fim do formato único), D14 (`secrets.cfg` único), D12 (pastas criadas na subida, sem `prepare_dirs`) | Pendente |
| 032c | D7 e D13 (sem `sudo`/helper; funções no agente), D8 (sem monitor), D11 (sem `sss_env`), D16 (`critical_config` enxuto); linha de subida com o ambiente da instalação (`<TIPO>` e caminho) no web e no agente; no DEV, título da aba com `[DEV]` e cabeçalho com outra cor (além da faixa que já existe) | Pendente |
| 032e | Pastas do processo no plural: `inputs`, `outputs`, `works`, `script_works` (pedido de 2026-10-27; passo separado depois do 032d) | Pendente |
| 032d | D15 (DEPLOYMENT enxuto), configs do DEV e modelos, homologação real, revisão independente, encerramento | Pendente |
