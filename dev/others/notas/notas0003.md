A lista abaixo vem direto do código (`sss_config.SCHEMA`). O config do agente pode ter seis seções: `[app]`, `[oracle]`, `[secrets]`, `[agent]`, `[logging]` e `[retention]`. **Negrito** marca o que é obrigatório. "Do nome" quer dizer que, com `[app] name`, o valor sai sozinho e você não precisa escrever.

## `[app]`
| Chave | Padrão | Valores |
|---|---|---|
| **`sss_env`** | — | `DEV`, `HML`, `PROD` (com a D12, `DEV` também em HOM e PROD) |
| `name` | vazio | nome do processo, igual ao da pasta `instance/<nome>/` (ex.: `agente0001`) |

## `[oracle]`
| Chave | Padrão | Valores |
|---|---|---|
| **`user`** | — | conta do papel agente |
| **`dsn`** | — | `host[:porta]/serviço` ou descrição TNS |
| **`owner`** | — | dono do esquema |
| **`table_prefix`** | — | ex.: `tbsss_` |
| `driver_mode` | `auto` | `auto`, `thin`, `thick`, `cx_oracle` (recomendado: `thick`) |
| `oracle_client_lib_dir` | vazio | pasta do Instant Client (só macOS) |
| `call_timeout_ms` | `30000` | 1 a 3.600.000 |
| `pool_min` / `pool_max` | `1` / `4` | 1 a 1.000 |

## `[secrets]`
| Chave | Padrão |
|---|---|
| `secrets_file` | o `secrets.cfg` da mesma pasta do `config.ini` |

## `[agent]`
| Chave | Padrão | Valores / observação |
|---|---|---|
| `agent_id` | do nome | com `name`, não escreva; um valor diferente é recusado |
| **`environments`** | — | lista separada por vírgula, ex.: `PRODUCAO,HOMOLOGACAO` |
| **`max_parallel_jobs`** | — | 1 a 999, e no máximo `max_parallel_hard_limit` |
| `max_parallel_hard_limit` | `32` | 1 a 999 |
| `work_dir` | do nome | `var/<nome>/work` |
| `exec_users` | vazio | `AMBIENTE=usuario`; obrigatório fora de DEV (com a D12, fica vazio) |
| `exec_work_dir` | do nome | `var/exec`; só usado com `exec_users` |
| `helper_path` | `../sss-root/bin/sss-helper` | só usado com `exec_users` |
| `claim_batch_size` | `20` | 1 a 1.000 |
| `schedule_batch_size` | `50` | 1 a 1.000 |
| `orchestrator_interval_s` | `10` | 1 a 3.600 |
| `cancel_poll_interval_s` | `2` | 1 a 3.600 |
| `heartbeat_interval_s` ¹ | `10` | 1 a 3.600 |
| `fence_timeout_s` ¹ | `90` | 1 a 86.400 |
| `node_offline_timeout_s` ¹ | `180` | 1 a 86.400 |
| `kill_grace_s` | `5` | 1 a 300 |
| `script_timeout_s` | `21600` (6 h) | 1 a 86.400 |
| `shutdown_mode` | `TERMINATE` | `TERMINATE`, `DRAIN` |
| `shutdown_grace_s` | `30` | 1 a 3.600 |
| `misfire_policy` ¹ | `RUN_ONCE` | `RUN_ONCE`, `SKIP` |
| `misfire_tolerance_s` ¹ | `300` | 1 a 86.400 |
| `cron_horizon_days` ¹ | `1461` | 1.461 a 36.500 |
| `queue_aging_min` ¹ | `60` | 0 a 1.440 (0 desliga) |
| `log_dir_min_free_mb` | `1024` | 0 a 1.048.576 |
| `output_dir` | do nome | `var/<nome>/output`; escrito vazio desliga a saída |
| `output_max_bytes` | `20971520` (20 MiB) | 1 MiB a 200 MiB |
| `output_max_files` | `1000` | 1 a 10.000 |
| `input_dir` | do nome | `var/<nome>/input`; escrito vazio desliga a entrada |
| `script_work_dir` | do nome | `var/<nome>/script_work`; escrito vazio desliga |
| `script_base_dir` | `scripts_ambiente/` | escrito vazio: só caminho absoluto |
| `child_locale` | `C.UTF-8` | locale do script |
| `env_passthrough` | vazio | variáveis repassadas ao script, ex.: `ORACLE_HOME,TNS_ADMIN` |

¹ Esses sete valores precisam ser iguais nos agentes e no web. Se mudar algum, escreva o mesmo valor no `[agent]` do config do web (D13).

**Regras entre chaves** (a subida recusa se forem quebradas): `fence_timeout_s` maior ou igual a 3 × `heartbeat_interval_s`; `node_offline_timeout_s` maior ou igual a 2 × `fence_timeout_s`; e as invariantes I3 e I4 com `call_timeout_ms` (README §8.9).

**Não existe mais:** `interpreters` (CR-026). Se ainda estiver no arquivo, a linha é ignorada e o agente grava um aviso no log.

## `[logging]`
| Chave | Padrão | Valores |
|---|---|---|
| `log_dir` | do nome | `var/<nome>/logs` |
| `level` | `INFO` | `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `app_log_max_bytes` | `10485760` (10 MiB) | 1 KiB a 1 GiB |
| `app_log_retention_days` | `30` | 1 a 3.650 |
| `max_log_size_bytes` | `5242880` (5 MiB) | 1 KiB a 64 MiB (log do ticket no banco) |
| `max_local_log_size_bytes` | `52428800` (50 MiB) | 1 KiB a 10 GiB (log do ticket em disco) |
| `local_log_retention_days` | `30` | 1 a 3.650 |
| `output_retention_days` | `7` | 1 a 365 |
| `script_work_retention_days` | `7` | 1 a 365 |

## `[retention]` (usada pelo purge, que roda com o config do agente)
| Chave | Padrão | Valores |
|---|---|---|
| `ticket_retention_days` | `180` | 1 a 3.650 |
| `audit_retention_days` | `730` | 365 a 3.650, e no mínimo `ticket_retention_days` |
| `purge_batch_size` | `1000` | 1 a 100.000 |
| `input_retention_days` | `30` | 1 a 3.650 |
| `purge_user` | vazio | conta Oracle do purge; vazio desliga o purge (aceito só em DEV) |

A mesma tabela, com a explicação de cada chave, está no README §12.1, e o modelo pronto está em `instance/exemplos/agente0001/config.ini.example`. A bateria Oracle do CR-029 continua rodando.