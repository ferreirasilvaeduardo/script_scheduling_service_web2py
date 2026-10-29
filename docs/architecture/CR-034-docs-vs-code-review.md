# CR-034: Revisão da documentação contra o código

| Campo | Valor |
|---|---|
| Status | **Encerrado** em 2026-10-29 |
| Origem | Pedido do responsável pelo produto, durante o CR-033: validar em paralelo o README e o AGENTS contra o código |
| Método | Revisão só de leitura (subagente): cada afirmação verificável do README.md e do AGENTS.md comparada com `src/sss/`, `bin/`, `scripts/`, `tools/package.py`, `instance/exemplos/` e `tests/`; cada achado conferido de novo no código antes da correção |
| Decisões | D5 A (corrigir a documentação e decidir uma a uma as cinco divergências que pedem mudar o texto ou o código); D6 A; D7 A; D8 A; D9 A; D10 A |

## 1. Achados

33 achados: 1 de prioridade alta, 13 médios e 19 baixos. Nenhuma sintaxe ou API posterior à 3.6.0 no código que vai no pacote.

### 1.1 Corrigidos só na documentação

| # | Onde | Divergência | Correção |
|---|---|---|---|
| A1 | AGENTS §1 (estrutura de instalação) | Segredos por processo em `instance/<nome>/`, `var/exec/` e helper em `../sss-root`, tudo anterior ao CR-032 | `config.ini` por processo; `common.ini` e `secrets.cfg` por servidor; pastas do agente no plural; sem helper |
| M1 | README §12.1 (tabela de chaves) | `output_dir`, `input_dir`, `script_work_dir` e `script_base_dir` com padrão "vazio" | Padrões `var/<nome>/outputs`, `inputs`, `script_works` e `scripts_ambiente/`; a chave escrita vazia desliga |
| M2 | README §12.2 e comentário do `bin/sss-web.sh` | `sss-web.sh` sem argumentos subiria em `127.0.0.1:8000` | Formas com `<nome>`/`--name`; sem processo, código 2 (CR-029) |
| M3 | README §8.12 (subida) | Regex antiga do `agent_id` | O `agent_id` é o `[app] name` (`^[a-z][a-z0-9_-]{0,29}$`) |
| M4 | README §8.12 (subida) | Conferência de `input_dir/<ambiente>/` e `script_work_dir/<ambiente>/` com CRITICALs que não existem | Subitens retirados |
| M5 | README §4.3 e §11 | "10 funcionalidades" | 12 (`ddl_builder.FEATURE_CATALOG`) |
| M6 | AGENTS §7 (`test_db_schema.py`) | "17 tabelas" | 21 |
| M7 | AGENTS §7 (`test_log_paths.py`) | Testes de retenção que saíram com o purge (CR-030) | Trecho retirado |
| M9 | AGENTS §5 | Faltava a exceção do `oracle/inputs.py`, que usa o `RepoSchedulerInput` | Exceção documentada |
| M10 | README §2.5, AGENTS §7 e comentário do `_oracle_test_support.py` | Segredos da bateria Oracle "no `secrets.cfg` do agente0001" | `instance/common.ini` e o `instance/secrets.cfg` único (CR-032, D14 e D18) |
| M12 | README §12.2 e docstring do `tools/package.py` | Recusa de "outra aplicação (`/admin/`, `welcome`, `examples`)", que não existe; `CHANGE_ME` em `instance/secrets.cfg.example` | Só o que o código recusa (`applications/`); o modelo fica em `instance/exemplos/` |
| B1 | AGENTS §7 | Índice `ix_tck_ocor` | `ix_tbsss_tck_occur` |
| B2 | AGENTS §7 (`test_ticket_files.py`) | `pack`: código 7 para arquivos ou bytes | 7 para arquivos e 8 para bytes |
| B3 | README §3 (árvore) | `var/update/<data>/retorno/` | `var/update/<data>/` |
| B4 | README §3 (árvore) | `instance/exemplos/` sem o `common.ini.example` | Acrescentado |
| B5 | README §8.0 | `collect(execution)` na plataforma e identidade por `psinfo`/`sysctl` nos outros Unix | `executor.check`; fora do Linux, `None` |
| B6 | README §13 | Log do `init_db` chamado `init_db` | `sss_init_db` |
| B7 | README §4.4 | `audit_service.ACOES` | `ACTIONS` |
| B8 | README §11.3 | `output` e `script_work` no singular | `outputs` e `script_works` |
| B9 | README §12.2, AGENTS §3.2, DEPLOYMENT §3 | O `docs/homologation/` excluído do pacote (CR-033, D3) também leva o manual do UI Freeze | Texto completado |
| B12 | README §12.1 (pastas) | O `script_base_dir` seguiria a recusa com código 13 | Exceção: a falha ao criá-lo só gera WARNING (os tickets relativos dão `NOT_FOUND`) |
| B13 | README §3.1 | Assinatura do `sss-scheduler.sh` só com `--config` | `<nome>` ou `--config` |
| B14 | README §8.5 e comentário do `bin/sss-update.sh` | `PATH` da unit do systemd e `systemctl stop` | `PATH` do `crontab`; parada pelo keepalive (§10.6) |
| B15 | Comentários de `tools/package.py`, `sss_logging.py` e `_oracle_test_support.py` | Helper no `bin/`, `log_dir/app/...` e segredos antigos | Atualizados |
| B16 | AGENTS §6 | `print` só no `init_db` e no `health` | Os CLIs de `src/sss/cli/` |
| B17 | AGENTS §2.1 | `compile()` só nos testes | Também no `template.py`, junto do `exec` |
| B18 | README §2.4.3 | O mapa de "todas as telas" sem Saídas e Entrada | Linhas acrescentadas |
| B19 | AGENTS §3.2 e README §2.5 | `scripts_ambiente/` faltando nas exceções do `APP_DIR`; "o daemon com FAKE aborta" | Exceção citada; frase corrigida (o daemon não passa pelo `repo_factory`) |

### 1.2 Decididos (texto ou código)

| # | Decisão | Mudança |
|---|---|---|
| M8 (D6 A) | O `check_env` só sondava o banco com `SSS_TEST_ORACLE=1`; no servidor, "Driver Oracle: OK" sem conectar; sem processo, saía com 1 | Sonda sempre, com a conta e os segredos do processo; linha nova do orçamento da conexão (`AVISO` com `CONEXAO_ACIMA_DO_PRAZO`, sem reprovar); sem processo, código 2 sem tabela. `test_check_env.py` e `test_env_skeleton.py` (este com um DSN que recusa na hora, sem tocar em banco); DEPLOYMENT §6, DEV_ENVIRONMENT §3 |
| M11 (D7 A) | O `health.py` gravava `health_<PID>.log` com a configuração inválida (uma pasta de minuto nova a cada passada do cron), contra o README §13 | `get_config` sem `log_name`; teste com config inválido numa pasta temporária, sem arquivo gravado |
| M13 (D8 A) | O CLAUDE.md proibia f-strings; o AGENTS §2.1 as permite; há 63 em 18 arquivos, validadas no 3.6.0 | Valem as f-strings simples (só `f"{x=}"`, do 3.8, é proibida); frase do CLAUDE.md alinhada ao AGENTS |
| B10 (D9 A) | Os nomes reservados (`init_db`, `seed`, `purge`) só eram recusados no agente | Recusados em todo papel, como diz o README §12.1; teste com o web |
| B11 (D10 A) | O `sss-stop.sh --config` conferia o `name` com `^[A-Za-z0-9._-]{1,30}$`: aceitava `..`, e o `.stop` iria para fora de `var/` | Mesma regra do §12.1; teste com `..`, maiúscula, ponto e nome reservado |

## 2. Validação

* Suíte completa em 3.6.0, 3.6.15 e 3.13.2: 1499 testes OK (61 pulados, os do Oracle real); `var/` do DEV intacto.
* `make check-all` (flake8 e mypy no 3.11): zero achados.
* Cada teste novo dos itens de código conferido contra o comportamento antigo: falha sem a correção e passa com ela.
* `check_env --name agente0001` e `--name web0001` no DEV, sem `SSS_TEST_ORACLE`: conexão real (servidor 19.24, modo thick) e o orçamento de 30 s.
* Bateria Oracle não rodada: nenhuma mudança em SQL, repositórios ou agente.
