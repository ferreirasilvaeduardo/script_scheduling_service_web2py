# SSS — Prompt F8.3: Daemon — inicialização, claim, heartbeat, cancelamento e finalização

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.2, §4.9–4.11, §5.6, §6
- `README.md` §3.1, §5.1, §5.2, §5.6 (parte do agente), §8.1–8.4, §8.7, §8.10, §8.11 (apenas a parte de sinais; o resto é F8.4), §8.12 (inteiro), §10 (tabelas 13 e 15)
- Arquivos: `modules/executor.py`, `modules/env_builder.py`, `modules/log_pump.py`, `modules/params_compiler.py` (`validar_snapshot`), `modules/oracle_conn.py`, `modules/sql_ident.py`

## Objetivo
Colocar o agente executor de pé: inicialização fail-fast, claim concorrente seguro, execução, heartbeat, coleta de log, cancelamento, timeout e finalização.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/repo_oracle/scheduler_fila.py`** (repositório interno do daemon), com o SQL do README **literal** e as expressões `CASE` importadas do `sql_ident`:
  - `candidatos(conn, ambientes, lote)` (§8.2), com os placeholders `:amb0..N` gerados por contagem;
  - `claim(conn, ticket_id, script_id, ambiente, agente_id) -> (ok, max_parallel)`, com os 3 passos do §8.3 em **uma** transação. O ORA-30006/54 resulta em `ROLLBACK` e `(False, motivo)`;
  - `registrar_pid(...)` (§8.4, passo 5);
  - `varredura_propria(conn, agente_id)` (§8.7);
  - `heartbeat(conn, agente_id, ids) -> lista_ids_perdidos`, com `executemany` + `arraydmlrowcounts=True` e o update de `tbsss_agentes` na mesma transação;
  - `finalizar(conn, ticket_id, agente_id, status, motivo, rc) -> bool`;
  - `script_ativo_homologado(conn, script_id, ambiente) -> bool`;
  - `registrar_agente(...)` com o `MERGE` e a regra de duplicidade do §8.12, passo 7;
  - `tickets_running_do_agente(conn, agente_id)` para o startup check.
- **`applications/script_scheduling_service/modules/scheduler_loop.py`:**
  - **`Agente.inicializar()`:** os passos 1–9 do README §8.12, **em ordem**. Cada falha gera log CRITICAL e `SystemExit(código distinto por passo)`. O `data_backend = FAKE` aborta (README §2.5).
  - **Laço single-threaded** com três temporizadores `time.monotonic()` (§8.1). Neste prompt entram:
    - **Ciclo rápido** (`cancel_poll_interval_s`), para cada execução local:
      1. `verificar` (processo terminou: `finalizar` + flush do log + limpeza);
      2. timeout (`encerrar`, depois `FAILED/TIMEOUT`);
      3. teto local do log (`encerrar`, depois `FAILED/LOG_LIMIT`);
      4. `varredura_propria`: `cancel_requested = 'S'` leva a `encerrar` e `CANCELLED/CANCEL_USER` (se o processo já tiver terminado sozinho, prevalece o resultado real); um ticket ausente do resultado leva a `encerrar` sem gravar status e log ERROR `OWNERSHIP_LOST`.
    - **Ciclo de heartbeat:** `heartbeat` + `log_pump.coletar` + `anexar` em cada execução. Uma perda de posse vai para o tratamento `OWNERSHIP_LOST`. O instante do último heartbeat confirmado também é registrado, para uso pelo F8.4.
    - **Ciclo do orquestrador:** se `len(execucoes) < max_parallel_jobs`, busca `candidatos` e, para cada um, `claim`. Em caso de sucesso:
      1. carregar o snapshot e rodar `validar_snapshot` + `script_ativo_homologado` (`PRECHECK_FAILED`, `-4`);
      2. `preparar_diretorio`, `abrir_log`, `env_builder.construir` e `executor.iniciar` (`SPAWN_ERROR`);
      3. `registrar_pid` (perda de posse leva a `encerrar` + `OWNERSHIP_LOST`).

      Os espaços de NODE_OFFLINE e desdobro ficam como **pontos de extensão vazios**, com docstring "implementado no F8.4". Não é permitido usar `TODO` (AGENTS §1).
  - **Sinais:** handlers de SIGTERM/SIGINT que **apenas** setam a flag. Ao detectar a flag, o laço chama `encerrar_tudo('TERMINATE')`, que é a implementação mínima. O `DRAIN` fica para o F8.4.
  - **Resiliência:** cada ciclo fica em `try/except` com log ERROR + contexto. Em `RepoIndisponivel` ou erro de rede, o daemon reconecta pelo `ConexaoResiliente` e **não** faz claim nesse ciclo. Nenhuma transação fica aberta durante `sleep` ou `encerrar` (AGENTS §4.9).
  - **Logs:** um `LoggerAdapter` com `agente`/`ticket`/`acao` em todas as linhas (README §13).
- **`applications/script_scheduling_service/scripts/run_scheduler.py`:** carrega a config e os segredos, configura o logging, instancia o `Agente` e chama `inicializar()` e `executar()`. O `finally` fecha a conexão, o lock file e os descritores.
- **Testes:**
  - `applications/script_scheduling_service/scripts/test_scheduler_claim.py` com conexão **mock** que simula o banco: claim OK; teto atingido; lock timeout; perda de posse no `registrar_pid`; `PRECHECK_FAILED` com snapshot adulterado (`argv[0]` fora da allowlist); cancelamento de execução real com `/bin/sh` sleep; processo que termina antes do cancelamento (prevalece o resultado real); timeout; `OWNERSHIP_LOST` na varredura (o processo é morto e nenhum status é gravado); startup check com PID nulo, PID inexistente, PID reciclado (`starttime` diferente) e PID vivo; rejeição de `agent_id` duplicado; recusa de root.
  - Com `SSS_TEST_DSN`: **dois** agentes (dois processos `run_scheduler` com `agent_id` diferentes) e 10 tickets de um script com `max_qtd_parallel_env = 2`. Nunca devem existir mais de 2 `RUNNING` simultâneos, verificado por polling no banco durante o teste, e todos devem terminar com `SUCCESS`.

**OUT**
- Desdobro de agendamentos, NODE_OFFLINE, self-fencing e shutdown `DRAIN` ficam para o F8.4.

## Requisitos
1. **Ordem de locks** do README §8.3 respeitada.
2. Commit do claim **antes** do spawn.
3. **Toda** transição de status checa `rowcount`. Ignorar `rowcount` é defeito (AGENTS §4.11).
4. Nenhuma thread no daemon (AGENTS §3.2).

## Critérios de aceite
- [ ] Os testes com mock passam.
- [ ] O teste de concorrência com 2 agentes passa com `SSS_TEST_DSN`. Sem ele, fica `NÃO TESTADO`.
- [ ] Nenhum processo órfão após os testes.

## Verificação
`python -m unittest discover -s scripts -p "test_scheduler_claim.py" -v`

## Saída
Relatório AGENTS.md §9.
