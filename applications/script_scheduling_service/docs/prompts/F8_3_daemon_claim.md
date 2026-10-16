# SSS — Prompt F8.3: Daemon — inicialização, claim, heartbeat, cancelamento e finalização

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.2, §4.9–4.11, §5.6, §6
- `docs/arquitetura/CR-002-oracle-unico-e-driver-adaptativo.md` e `docs/arquitetura/CR-005-posix-caminho-livre-e-logs.md` (D1 a D8, R-a a R-e)
- `README.md` §2.3 (seleção do driver), §3.1 (inclusive a regra de thread única do processo inteiro, C10), §4.4 (tabela de entidade por ação), §5.1, §5.2, §5.6 (parte do agente), §6.4, §6.5 (snapshot **versão 4**), §8.0–8.4 (em especial o passo 1 do §8.4), §8.5 (caminho livre e checagens), §8.9 ("Mesmos tempos em todos os nós"), §8.7, §8.10, §8.11 (apenas a parte de sinais e do arquivo `.stop`; o resto é F8.4), §8.12 (inteiro), §10 (tabelas 6, 13 e 15), §12.1 ("Falha de configuração"), §13 (formato e níveis)
- Arquivos: `modules/plataforma/`, `modules/pastas_log.py`, `modules/executor.py`, `modules/env_builder.py`, `modules/log_pump.py`, `modules/params_compiler.py` (`validar_snapshot`, `montar_argv_agente`), `modules/path_guard.py` (`resolver`), `modules/sss_config.py`, `modules/db_conn.py`, `modules/sql_ident.py`

## Objetivo
Colocar o agente executor de pé: inicialização fail-fast, claim concorrente seguro, execução, heartbeat, coleta de log, cancelamento, timeout e finalização (somente POSIX).

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/repo_oracle/scheduler_fila.py`** (repositório interno do daemon), com o SQL do README **literal** e as expressões `CASE` importadas do `sql_ident`:
  - `candidatos(conn, ambientes, interpretadores, lote)` (§8.2), com os placeholders `:amb0..N` e `:int0..N` gerados por contagem (sem `pastas_base`). Os interpretadores são os **mapeados neste agente** (`PYTHON3`, `BASH`, `SH`);
  - `claim(conn, ticket_id, script_id, ambiente, agente_id) -> (ok, max_parallel)`, com os 3 passos do §8.3 em **uma** transação. O ORA-30006/54 resulta em `ROLLBACK` e `(False, motivo)`;
  - `registrar_pid(...)` (§8.4, passo 5);
  - `varredura_propria(conn, agente_id)` (§8.7);
  - `heartbeat(conn, agente_id, ids) -> lista_ids_perdidos`, com `executemany` + `arraydmlrowcounts=True` e o update de `tbsss_agentes` na mesma transação;
  - `finalizar(conn, ticket_id, agente_id, status, motivo, rc) -> bool`;
  - `script_ativo_homologado(conn, script_id, ambiente) -> bool`;
  - `registrar_agente(...)` com o `MERGE` e a regra de duplicidade do §8.12, passo 7, gravando também `plataforma` (`plataforma.NOME`), `interpretadores` (sem `pastas_base`; README §10 tabela 15), e a auditoria `AGENTE_INICIO` na mesma transação, com `entidade = 'tbsss_agentes'`, `entidade_id` = id do agente e `ator = 'SYSTEM:<agent_id>'` (README §4.4 e §10 tabela 16);
  - `tickets_running_do_agente(conn, agente_id)` para o startup check.
- **`applications/script_scheduling_service/modules/scheduler_loop.py`:**
  - **`Agente.inicializar()`:** os passos 1–9 do README §8.12, **em ordem**, usando só a interface de `plataforma` (`usuario_privilegiado`, `validar_dir_restrito`, `travar_instancia`, `processo_existe`, `identidade_processo`, `reabrir_grupo`, `encerrar_grupo`) e `db_conn.selecionar_driver`/`inicializar` no passo 6. Cada falha gera log CRITICAL no formato do README §13 e `SystemExit(código distinto por passo)`. O `data_backend = FAKE` aborta (README §2.5). Configuração inválida segue a "Falha de configuração" do §12.1 (`sss_config.obter_config(nome_log='sss_scheduler')`: CRITICAL com seção, chave e motivo, nunca o valor de um segredo; stderr quando `[logging]` for inválido).
    - **Passo 2:** além das faixas, registra em **INFO** os valores de `fence_timeout_s` e `node_offline_timeout_s` (README §8.9, "Mesmos tempos em todos os nós", D7), para a conferência entre nós no E2E (F9.2).
    - **Passo 4 (README §8.12):** `log_dir` e `work_dir` existem, passam pelas checagens de permissão e restrição de acesso da §8.12.
    - **Thread única (README §3.1, C10):** depois dos passos 1–9 e **antes do primeiro spawn**, o agente confere `threading.active_count() == 1`. Se houver outra thread (por exemplo, criada pelo web2py ou pelos models carregados com `-M`), aborta com CRITICAL (com os nomes das threads) e código próprio, porque o `preexec_fn` só é seguro com thread única.
  - **Laço single-threaded** com três temporizadores `time.monotonic()` (§8.1). Neste prompt entram:
    - **Ciclo rápido** (`cancel_poll_interval_s`), para cada execução local:
      1. `verificar` (processo terminou: `finalizar` + flush do log + limpeza);
      2. timeout (`encerrar`, depois `FAILED/TIMEOUT`);
      3. teto local do log (`encerrar`, depois `FAILED/LOG_LIMIT`);
      4. `varredura_propria`: `cancel_requested = 'S'` leva a `encerrar` e `CANCELLED/CANCEL_USER` (se o processo já tiver terminado sozinho, prevalece o resultado real); um ticket ausente do resultado leva a `encerrar` sem gravar status e log ERROR `OWNERSHIP_LOST`.
    - **Ciclo de heartbeat:** `heartbeat` + `log_pump.coletar` + `anexar` em cada execução. Uma perda de posse vai para o tratamento `OWNERSHIP_LOST`. O instante do último heartbeat confirmado também é registrado, para uso pelo F8.4.
    - **Ciclo do orquestrador:** se `len(execucoes) < max_parallel_jobs`, busca `candidatos` e, para cada um, `claim`. Em caso de sucesso:
      1. carregar o snapshot e rodar a pré-validação do README §8.4, passo 1: `validar_snapshot` (só `versao == 4`; versões anteriores são recusadas), interpretador na allowlist **e** mapeado neste agente, `path_guard.resolver` contra o caminho absoluto (que confere existência, dono e permissões na cadeia até `/` e pastas de sistema; fornece o `script_real`), `montar_argv_agente` e `script_ativo_homologado` (`PRECHECK_FAILED`, `-4`);
      2. `preparar_diretorio`, `abrir_log` (em `pastas_log`), `env_builder.construir` e `executor.iniciar` com o rótulo `SSS-<agent_id>-<ticket_id>` (`SPAWN_ERROR`);
      3. `registrar_pid` (perda de posse leva a `encerrar` + `OWNERSHIP_LOST`).

      Os espaços de NODE_OFFLINE e desdobro ficam como **pontos de extensão vazios**, com docstring "implementado no F8.4". Não é permitido usar `TODO` (AGENTS §1).
  - **Parada:** `plataforma.instalar_parada(flag)` (SIGTERM/SIGINT no POSIX) e verificação do arquivo `work_dir/sss-<agent_id>.stop` a cada ciclo rápido; os dois **apenas** setam a flag. Ao detectar a flag, o laço chama `encerrar_tudo('TERMINATE')`, que é a implementação mínima. O `DRAIN` fica para o F8.4.
  - **Resiliência:** cada ciclo fica em `try/except` com log ERROR + contexto. Em `RepoIndisponivel` ou erro de rede, o daemon reconecta pelo `ConexaoResiliente` e **não** faz claim nesse ciclo. Nenhuma transação fica aberta durante `sleep` ou `encerrar` (AGENTS §4.9).
  - **Logs:** um `LoggerAdapter` com `agente`/`ticket`/`acao` em todas as linhas (README §13).
  - **`encerrar_tudo`:** a auditoria `AGENTE_FIM` usa `entidade = 'tbsss_agentes'` e `entidade_id` = id do agente (README §4.4).
- **`applications/script_scheduling_service/scripts/run_scheduler.py`:** carrega a config e os segredos, configura o logging, instancia o `Agente` e chama `inicializar()` e `executar()`. O `finally` fecha a conexão, o lock file e os descritores.
- **Testes:**
  - `applications/script_scheduling_service/scripts/test_scheduler_claim.py` com conexão **mock** que simula o banco: claim OK; teto atingido; lock timeout; perda de posse no `registrar_pid`; `PRECHECK_FAILED` com snapshot v1, v2 e v3, com interpretador fora da allowlist, com interpretador não mapeado neste agente e com `path_file` inexistente ou fora das regras de segurança; candidatos filtrados pelos interpretadores mapeados (placeholders `:int0..N` gerados por contagem, valores só em bind); recusa com CRITICAL quando `threading.active_count() > 1` antes do primeiro spawn; INFO com `fence_timeout_s` e `node_offline_timeout_s`; `MERGE` de registro do agente e `AGENTE_INICIO` com a entidade `tbsss_agentes`; cancelamento de execução real (`SH`/`PYTHON3` no POSIX); processo que termina antes do cancelamento (prevalece o resultado real); timeout; `OWNERSHIP_LOST` na varredura (o processo é morto e nenhum status é gravado); startup check com PID nulo, PID inexistente, PID reciclado (`starttime` no Linux) e PID vivo (encerrado pelo grupo reaberto); rejeição de `agent_id` duplicado; recusa de usuário privilegiado (root, via dublê de `plataforma`); parada pelo arquivo `.stop`.
  - Com `SSS_TEST_DSN`: **dois** agentes (dois processos `run_scheduler` com `agent_id` diferentes) e 10 tickets de um script com `max_qtd_parallel_env = 2`. Nunca devem existir mais de 2 `RUNNING` simultâneos, verificado por polling no banco durante o teste, e todos devem terminar com `SUCCESS`.

**OUT**
- Desdobro de agendamentos, NODE_OFFLINE, self-fencing e shutdown `DRAIN` ficam para o F8.4.

## Requisitos
1. **Ordem de locks** do README §8.3 respeitada.
2. Commit do claim **antes** do spawn.
3. **Toda** transição de status checa `rowcount`. Ignorar `rowcount` é defeito (AGENTS §4.11).
4. Nenhuma thread no daemon (AGENTS §3.2) e no processo inteiro antes do primeiro spawn (`threading.active_count() == 1`, README §3.1).
5. Nenhuma primitiva de SO fora de `plataforma/`; o laço não testa `sys.platform`.

## Critérios de aceite
- [ ] Os testes com mock passam.
- [ ] O teste de concorrência com 2 agentes passa com `SSS_TEST_DSN`. Sem ele, fica `NÃO TESTADO`.
- [ ] Nenhum processo órfão após os testes.

## Verificação
`python -m unittest discover -s scripts -p "test_scheduler_claim.py" -v`

## Saída
Relatório AGENTS.md §9.
