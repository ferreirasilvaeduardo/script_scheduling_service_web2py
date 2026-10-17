# SSS — Prompt F8.3: Daemon — inicialização, claim, heartbeat, cancelamento e finalização

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.2, §4.9–4.11, §5.6, §6
- `docs/arquitetura/CR-007-robustez-do-scheduler.md` (inteiro: é a especificação de robustez deste passo)
- `docs/arquitetura/CR-002-oracle-unico-e-driver-adaptativo.md`, `docs/arquitetura/CR-005-posix-caminho-livre-e-logs.md` (D1 a D8, R-a a R-e) e `docs/arquitetura/CR-006-colunas-de-registro.md` (R-b a R-e: ator `SYSTEM:<agent_id>`, alteração de negócio × rotina técnica)
- `README.md` §2.3 (seleção do driver), §3.1 (inclusive a regra de thread única do processo inteiro, C10), §4.4 (tabela de entidade por ação), §5.1, §5.2, §5.6 (parte do agente), §6.4, §6.5 (snapshot **versão 4**), §8.0–8.4 (em especial o passo 1 do §8.4), §8.5 (caminho livre e checagens), §8.9 ("Mesmos tempos em todos os nós"), §8.7, §8.10, §8.11 (apenas a parte de sinais e do arquivo `.stop`; o resto é F8.4), §8.12 (inteiro), §10 (tabelas 6, 13 e 15, e "Colunas de registro"), §12.1 ("Falha de configuração"), §13 (formato e níveis)
- Arquivos: `modules/plataforma/`, `modules/pastas_log.py`, `modules/executor.py`, `modules/env_builder.py`, `modules/log_pump.py`, `modules/params_compiler.py` (`validar_snapshot`, `montar_argv_agente`), `modules/path_guard.py` (`resolver`), `modules/sss_config.py`, `modules/db_conn.py`, `modules/sql_ident.py`

## Objetivo
Colocar o agente executor de pé: inicialização fail-fast, claim concorrente seguro, execução, heartbeat, coleta de log, cancelamento, timeout e finalização (somente POSIX).

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/repo_oracle/scheduler_fila.py`** (repositório interno do daemon), com o SQL do README **literal** e as expressões `CASE` importadas do `sql_ident`:
  - `candidatos(conn, ambientes, interpretadores, lote, envelhecimento_min)` (§8.2), com os placeholders `:amb0..N` e `:int0..N` gerados por contagem (sem `pastas_base`), a subconsulta de teto por (script, ambiente) e a ordem pela prioridade efetiva (CR-007, R-07; `CASE` sem alias, R-32). Os interpretadores são os **mapeados neste agente** (`PYTHON3`, `BASH`, `SH`); os ambientes, os atendidos **ativos agora** (`ambientes_ativos(conn, atendidos)`, relido a cada ciclo do orquestrador, D2);
  - `claim(conn, ticket_id, script_id, ambiente, agente_id) -> (ok, motivo, started_at)`, com os 3 passos do §8.3 em **uma** transação e o `RETURNING started_at INTO :started_at` do passo 3 (README §8.3): com sucesso, `(True, None, started_at)`; o ORA-30006/54 resulta em `ROLLBACK` e `(False, 'LOCK', None)`; teto atingido ou `rowcount = 0`, `(False, 'TETO' | 'PERDIDO', None)`. O `started_at` dá a pasta do log de execução (README §8.4, passo 3);
  - `registrar_pid(...)` (§8.4, passo 5), com `arquivo_sha256`;
  - `contexto_execucao(conn, ticket)` (CR-007, D2 e R-24): ambiente ativo, `pode_executar` do solicitante (contexto RBAC do F8.4), cadastro atual do script (`path_file`, `interpretador`, `sha256_homologado`, ativo, homologação) numa leitura;
  - `cancelamento_pedido(conn, ticket_id)` (R-28): leitura de `cancel_requested` pela PK, sem lock;
  - `devolver(conn, ticket_id, agente_id)` (R-03): `RUNNING → PENDING` com `process_id IS NULL` (README §5.1);
  - `conferir_config(conn, agente_id, config_criticos)` (R-23): divergências com outros agentes ativos;
  - `varredura_propria(conn, agente_id)` (§8.7);
  - `heartbeat(conn, agente_id, hostname, pid, ids) -> (lista_ids_perdidos, sysdate)`, com `executemany` + `arraydmlrowcounts=True` (pulado quando `ids` está vazio) e o `UPDATE` de `tbsss_agentes` filtrando `hostname` e `pid_daemon` (`rowcount = 0` = `REGISTRO_PERDIDO`, R-11), na mesma transação, devolvendo o `SYSDATE` para a trava de salto de relógio (D3);
  - `finalizar(conn, ticket_id, agente_id, status, motivo, rc) -> bool`;
  - `script_ativo_homologado(conn, script_id, ambiente) -> bool`;
  - `registrar_agente(...)` sob `SELECT ... FOR UPDATE WAIT 5` (com nova tentativa na corrida da inclusão), com o `MERGE` e a regra de duplicidade do §8.12, passo 7 (`hostname` diferente, ou mesmo host com outro PID vivo; CR-007 R-11), gravando `config_criticos`, gravando também `plataforma` (`plataforma.NOME`), `interpretadores` (sem `pastas_base`; README §10 tabela 15), e a auditoria `AGENTE_INICIO` na mesma transação, com `entidade = 'tbsss_agentes'`, `entidade_id` = id do agente e `ator = 'SYSTEM:<agent_id>'` (README §4.4 e §10 tabela 16);
  - `tickets_running_do_agente(conn, agente_id)` para o startup check.
  - **Colunas de registro (CR-006, README §10):** o ator de toda gravação do daemon é `SYSTEM:<agent_id>`. `claim` e `finalizar` (inclusive cancelamento, timeout, `LOG_LIMIT`, `SHUTDOWN`, `ORPHAN_PROCESS`, `SPAWN_ERROR` e `PRECHECK_FAILED`) gravam `updated_at = SYSDATE` e `updated_by` no ticket, no mesmo `UPDATE` literal do README (§8.3, §8.7, §5.6). `registrar_pid` e `heartbeat` são rotina técnica e **não** gravam `updated_*` (nem no ticket nem em `tbsss_agentes`). O `MERGE` de `registrar_agente` grava `created_*` na inclusão e `updated_*` na atualização; `encerrar_tudo` grava `updated_*` junto com `status = 'PARADO'`.
- **`applications/script_scheduling_service/modules/scheduler_loop.py`:**
  - **`Agente.inicializar()`:** os passos 1–9 do README §8.12, **em ordem**, usando só a interface de `plataforma` (`usuario_privilegiado`, `validar_dir_restrito`, `travar_instancia`, `processo_existe`, `identidade_processo`, `reabrir_grupo`, `encerrar_grupo`) e `db_conn.selecionar_driver`/`inicializar` no passo 6. Cada falha gera log CRITICAL no formato do README §13 e `SystemExit(código distinto por passo)`. O `data_backend = FAKE` aborta (README §2.5). Configuração inválida segue a "Falha de configuração" do §12.1 (`sss_config.obter_config(nome_log='sss_scheduler')`: CRITICAL com seção, chave e motivo, nunca o valor de um segredo; stderr quando `[logging]` for inválido).
    - **Passo 2:** `agent_id` não pode ser `init_db` nem `seed`, reservados para o ator do sistema (README §8.12, CR-006). Além das faixas, registra em **INFO** os valores de `fence_timeout_s` e `node_offline_timeout_s` (README §8.9, "Mesmos tempos em todos os nós", D7), para a conferência entre nós no E2E (F9.2).
    - **Passo 4 (README §8.12):** `log_dir` e `work_dir` existem, passam pelas checagens de permissão e restrição de acesso da §8.12; interpretadores por `path_guard.validar_executavel`; fora de DEV, `plataforma.validar_execucao` (CR-007, D1).
    - **CR-007 na inicialização:** codificação UTF-8 e `child_locale` em `locale -a` (passo 2); `.stop` antigo removido com WARN (passo 5); WARN de relógio local × `SYSDATE` e `db_conn.conferir_versao_esquema` (passo 6); `config_criticos` igual aos outros agentes ativos (passo 7); `ultimo_hb_ok` iniciado no fim; **startup check pelo disco** (passo 9, R-01): todos os `work_dir/ticket_*` com `.sss_proc`, encerramento do grupo pela identidade (sem sinal para identidade desconhecida), finalização por `.sss_result` ou `ORPHAN_PROCESS`, devolução dos `RUNNING` sem pasta e sem PID, limpeza.
    - **Thread única (README §3.1, C10):** depois dos passos 1–9 e **antes do primeiro spawn**, o agente confere `threading.active_count() == 1`. Se houver outra thread (por exemplo, criada pelo web2py ou pelos models carregados com `-M`), aborta com CRITICAL (com os nomes das threads) e código próprio, porque o `preexec_fn` só é seguro com thread única.
  - **Laço single-threaded** com três temporizadores `time.monotonic()` (§8.1), sob o **orçamento de tempo** do CR-007 (R-04): nenhuma espera dentro das operações; fence conferido a cada iteração e depois de cada chamada ao banco (nesta fase, só a medição e o registro; o fencing completo é do F8.4); encerramentos como máquina de estados (`executor.pedir_encerramento`/`avancar_encerramento`); claim parando ao gastar `heartbeat_interval_s / 2`; reconexão com `ConexaoResiliente.garantir()`, uma tentativa por ciclo. Neste prompt entram:
    - **Ciclo rápido** (`cancel_poll_interval_s`), para cada execução local:
      1. `verificar` (processo terminou: encerramento do grupo, R-02 + flush do log + `.sss_result` + `finalizar` + limpeza; com erro de banco, **finalização pendente**, refeita a cada ciclo até `rowcount` 1 ou 0, R-03);
      2. timeout (`encerrar`, depois `FAILED/TIMEOUT`);
      3. teto local do log (`encerrar`, depois `FAILED/LOG_LIMIT`);
      4. `varredura_propria`: `cancel_requested = 'S'` leva a `encerrar` e `CANCELLED/CANCEL_USER` (se o processo já tiver terminado sozinho, prevalece o resultado real); um ticket ausente do resultado leva a `encerrar` sem gravar status e log ERROR `OWNERSHIP_LOST`; um ticket **do resultado fora do mapa** segue o README §8.7 (CR-007, R-03: tratamento do startup check, devolução ou `ORPHAN_PROCESS`).
    - **Ciclo de heartbeat:** `heartbeat` **sempre**, mesmo sem tickets (R-28) + `log_pump.coletar` + `anexar` em cada execução (mascarador por ticket, F8.2). `REGISTRO_PERDIDO` leva a CRITICAL, `TERMINATE` e saída ≠ 0 (R-11). Uma perda de posse vai para o tratamento `OWNERSHIP_LOST`. O instante do último heartbeat confirmado também é registrado, para uso pelo F8.4.
    - **Ciclo do orquestrador:** se `len(execucoes) < max_parallel_jobs`, busca `candidatos` e, para cada um, `claim`. Em caso de sucesso:
      0. o ticket entra no mapa local logo depois do `COMMIT` do claim (R-03);
      1. carregar o snapshot e rodar a pré-validação do README §8.4, passo 1, inclusive `contexto_execucao` (ambiente ativo, `pode_executar` do solicitante, `CADASTRO_MUDOU`, sha256 contra `sha256_homologado`; CR-007), com a linha `[SSS]` do README §5.2 em toda recusa; erro de banco antes do spawn leva a `devolver`; com **uma** chamada a `validar_snapshot`, que já faz tudo e devolve `(snap, argv_real, script_real)` (contrato estendido no F8.1): só `versao == 4` (versões anteriores são recusadas), interpretador na allowlist **e** mapeado neste agente, `path_guard.resolver` contra o caminho absoluto (existência, dono e permissões na cadeia até `/`, pastas do sistema e do SSS) e `montar_argv_agente`. Depois, `script_ativo_homologado`. Qualquer falha dá `PRECHECK_FAILED`, `-4`;
      2. `cancelamento_pedido` imediatamente antes do spawn (R-28); `preparar_diretorio`, `abrir_log` (com o `started_at` devolvido pelo claim e o `script_nome` do snapshot), `env_builder.construir` e `executor.iniciar` com o rótulo `SSS-<agent_id>-<ticket_id>` (`SPAWN_ERROR`);
      3. `executor.registrar_proc` (`.sss_proc`) e então `registrar_pid` (perda de posse leva a `encerrar` + `OWNERSHIP_LOST`).

      Os espaços de NODE_OFFLINE e desdobro ficam como **pontos de extensão vazios**, com docstring "implementado no F8.4". Não é permitido usar `TODO` (AGENTS §1).
  - **Parada:** `plataforma.instalar_parada(flag)` (SIGTERM/SIGINT no POSIX) e verificação do arquivo `work_dir/sss-<agent_id>.stop` a cada ciclo rápido; os dois **apenas** setam a flag. Ao detectar a flag, o laço chama `encerrar_tudo('TERMINATE')`, que é a implementação mínima. O `DRAIN` fica para o F8.4.
  - **Resiliência:** cada ciclo fica em `try/except` com log ERROR + contexto. Em `RepoIndisponivel` ou erro de rede, o daemon reconecta pelo `ConexaoResiliente` e **não** faz claim nesse ciclo. Nenhuma transação fica aberta durante `sleep` ou `encerrar` (AGENTS §4.9).
  - **Logs:** um `LoggerAdapter` com `agente`/`ticket`/`acao` em todas as linhas (README §13).
  - **`encerrar_tudo`:** a auditoria `AGENTE_FIM` usa `entidade = 'tbsss_agentes'` e `entidade_id` = id do agente (README §4.4).
- **`applications/script_scheduling_service/scripts/run_scheduler.py`:** carrega a config e os segredos, configura o logging, instancia o `Agente` e chama `inicializar()` e `executar()`. O `finally` fecha a conexão, o lock file e os descritores.
- **Testes:**
  - `applications/script_scheduling_service/scripts/test_scheduler_claim.py` com conexão **mock** que simula o banco, incluindo os casos do CR-007: candidatos sem o script no teto e com envelhecimento; ambiente desativado no meio da execução sai da lista no ciclo seguinte; `SEM_PERMISSAO`, `AMBIENTE_INATIVO`, `CADASTRO_MUDOU` e `ARQUIVO_ALTERADO` com a linha `[SSS]`; cancelamento pedido entre o claim e o spawn; exceção depois do claim finalizando o ticket; erro de banco antes do spawn devolvendo o ticket; `COMMIT` do claim com desfecho desconhecido reconciliado pela varredura; finalização pendente até `rowcount` 1 e até 0; startup check pelo disco (ticket já `NODE_OFFLINE` no banco com o filho vivo: o grupo é encerrado; `.sss_result` usado; identidade desconhecida sem sinal); heartbeat sem tickets; `REGISTRO_PERDIDO`; duplicidade de `agent_id` no mesmo host com PID vivo e morto; `config_criticos` divergente; versão do esquema divergente; codificação não UTF-8; nenhuma chamada a `time.sleep` dentro das operações (dublê que falha se chamado); claim OK; teto atingido; lock timeout; perda de posse no `registrar_pid`; `PRECHECK_FAILED` com snapshot v1, v2 e v3, com interpretador fora da allowlist, com interpretador não mapeado neste agente e com `path_file` inexistente ou fora das regras de segurança; candidatos filtrados pelos interpretadores mapeados (placeholders `:int0..N` gerados por contagem, valores só em bind); recusa com CRITICAL quando `threading.active_count() > 1` antes do primeiro spawn; INFO com `fence_timeout_s` e `node_offline_timeout_s`; `MERGE` de registro do agente e `AGENTE_INICIO` com a entidade `tbsss_agentes`; colunas de registro com `SYSTEM:<agent_id>` no claim, na finalização, no `MERGE` e na parada, e **sem** `updated_*` no `registrar_pid` e no heartbeat (CR-006); `agent_id` `init_db` ou `seed` recusado; cancelamento de execução real (`SH`/`PYTHON3` no POSIX); processo que termina antes do cancelamento (prevalece o resultado real); timeout; `OWNERSHIP_LOST` na varredura (o processo é morto e nenhum status é gravado); startup check com PID nulo, PID inexistente, PID reciclado (`starttime` no Linux) e PID vivo (encerrado pelo grupo reaberto); rejeição de `agent_id` duplicado; recusa de usuário privilegiado (root, via dublê de `plataforma`); parada pelo arquivo `.stop`.
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
