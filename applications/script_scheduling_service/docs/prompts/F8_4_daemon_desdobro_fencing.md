# SSS — Prompt F8.4: Daemon — desdobro de agendamentos, NODE_OFFLINE, self-fencing e shutdown

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.1 (binds de data), §3.2 (encerramento escalonado), §4.9–4.11, §6
- `docs/arquitetura/CR-003-correcoes-pos-analise.md` (D1, D2, D3, D7 e os achados "Conclusão no desdobro", "Bind DATE com microssegundos" e "Contrato do desdobro incompleto"). A D16 (várias pastas base) foi revogada pelo CR-005: o desdobro grava o snapshot v4, com `path_file` absoluto
- `docs/arquitetura/CR-007-robustez-do-scheduler.md` (R-04, R-05, R-08, R-10, R-12, R-19, R-23, R-26, R-27, R-32)
- `docs/arquitetura/CR-008-auditoria-final.md` (R-03, R-09, R-10, R-12, R-19, R-21, R-22, R-31, R-33)
- `docs/arquitetura/CR-006-colunas-de-registro.md` (R-b a R-g: ator `SYSTEM:<agent_id>`, o que grava `updated_*` no desdobro e no ticket)
- `README.md` §4.4 (`AGD_PAUSAR`, `AGENTE_FIM`), §6.5 (snapshot versão 4; CR-005), §7 (inteiro, **especialmente §7.4 e §7.5**, inclusive "Conclusão da regra", "Sobreposição numa regra que conclui", "Bind de datas" e "Contrato do repositório para o desdobro"), §8.0, §8.1, §8.8, §8.9 (inclusive "Mesmos tempos em todos os nós"), §8.11 (inclusive o arquivo `.stop`), §10 (tabelas 12 e 13, a desativação com dependência e "Colunas de registro"), §13
- Arquivos: `modules/scheduler_loop.py`, `modules/repo_oracle/scheduler_fila.py`, `modules/recurrence.py`, `modules/params_compiler.py`, `modules/rbac.py`, `modules/plataforma/`, `modules/db_conn.py`

## Objetivo
Completar o agente com a geração de tickets a partir dos agendamentos (desdobro otimista), a detecção de nós caídos, o self-fencing contra split-brain e o desligamento controlado.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/repo_oracle/scheduler_agenda.py`** (repositório interno, processo batch, sem FAKE; README §2.5), com o SQL do README §7.5 **literal** e as operações **distintas** do "Contrato do repositório para o desdobro":
  - `regras_vencidas(conn, lote, ult_prox, ult_id)`: a leitura **paginada** do README §7.5 (CR-007, R-08), e `travar_regra(conn, id) -> bool` com `FOR UPDATE SKIP LOCKED` (falso = outro agente a está processando);
  - `carregar_regra(conn, id)`: a leitura completa da regra, que guarda a `antiga_data` exatamente como lida;
  - `contexto_rbac_usuario(conn, usuario_id)` (para `rbac.pode_executar`);
  - `reservar_e_criar_ticket(conn, regra, antiga, nova, ticket) -> bool`: numa **única** operação, `NEXTVAL` de `sq_tbsss_tickets`, a reserva otimista do passo 6 (`rowcount`) e, se `rowcount = 1`, o `INSERT` do ticket com o `id` explícito (`agendamento_id`, `solicitante` = login do `usuario_id`, `ip_origem = NULL`, `scheduled_at = :ocorrencia` (a ocorrência coberta, `Decisao.ocorrencia`, nunca `SYSDATE`; CR-007 R-27, CR-008 R-03), prioridade do passo 2 do README §7.5, já rebaixada a 2 quando o responsável deixou de ser admin) e o `INSERT` em `tbsss_ticket_resp`, os dois com `created_by = 'SYSTEM:<agent_id>'` (CR-006). A reserva é rotina técnica: **não** grava `updated_*` na regra;
  - `concluir_com_ticket(conn, regra, antiga, ticket) -> bool` e `concluir_sem_ticket(conn, id, antiga) -> bool`: o `UPDATE` único da conclusão (abaixo);
  - `pausar(conn, id, antiga, motivo, detalhe) -> bool` (passo 7, com `AND ativo = 'S'`, R-19);
  - `avancar_sem_ticket(conn, id, antiga, nova) -> bool` (R-05: só `proxima_execucao`, sem `ultima_execucao`, `ultimo_ticket_id` nem `updated_*`);
  - `pausar_cron_erro(conn, regra, antiga, ticket_ou_none) -> bool` (CR-008, R-19): o `UPDATE` literal da variante `cron_erro` do README §7.5 (pausa `CRON_INVALIDO` mantendo `proxima_execucao`, com ou sem ticket), seguido do `INSERT` do ticket e do `ticket_resp` quando há ticket;
  - `pausar_erro_interno(conn_nova, id, detalhe) -> bool` (R-08: numa transação separada, depois do `ROLLBACK` da regra);
  - `status_ticket(conn, id)`.

  Os nomes acima são sugestões; o que é obrigatório são as operações distintas. **Nenhuma** delas faz `COMMIT` nem `ROLLBACK` sozinha: todas recebem a conexão da transação do ciclo, e o `COMMIT` único é do passo 8. Todos os binds de data (`:antiga_data`, `:nova_data`) são declarados com `TIPO_DATE` via `db_conn.definir_tipos_entrada` (`setinputsizes` com `oracledb.DB_TYPE_DATE` ou `cx_Oracle.DATETIME`; README §7.5 "Bind de datas"). A `antiga_data` nunca é recalculada nem convertida por fuso.
- **`applications/script_scheduling_service/modules/repo_oracle/scheduler_fila.py` (ampliar):**
  - `marcar_node_offline(conn, agente_id, timeout_s) -> ids` (§8.8, literal, em duas etapas com `FOR UPDATE SKIP LOCKED`, sem os tickets do próprio agente; CR-007, R-12);
  - `finalizar_fenced(...)`;
  - `agente_parar(conn, agente_id)`.
  - **Colunas de registro (CR-006, README §10):** `marcar_node_offline` (ator: o agente que detectou), `finalizar_fenced` e `agente_parar` gravam `updated_at = SYSDATE` e `updated_by = 'SYSTEM:<agent_id>'`. No `scheduler_agenda`, `pausar` e as duas conclusões gravam `updated_*` na regra com o mesmo ator; `reservar_e_criar_ticket` não.
- **`applications/script_scheduling_service/modules/scheduler_loop.py` (completar os pontos de extensão do F8.3):**
  - **Desdobro** (ciclo do orquestrador): para cada regra vencida, os passos 1–8 do README §7.5, **em uma transação por regra**:
    - revalidação de privilégios, com o motivo **sempre** dado por `rbac.motivo_pausa(motivo_rbac)` (CR-008, R-33: `USUARIO_INATIVO`, `SCRIPT_INATIVO`, `AMBIENTE_INATIVO` ou `SEM_PERMISSAO`);
    - `recurrence.avaliar_disparo` com *misfire* (atraso pela vencida mais recente, CR-008 R-21);
    - sobreposição (`SKIP_OVERLAP`);
    - compilação do **snapshot versão 4** a partir de `parametros_json`, com `params_compiler.compilar_snapshot` (inclui `path_file` absoluto do script, sem `pasta_base`; README §6.5, CR-005) (`PARAM_INVALIDO`);
    - `CRON_INVALIDO`;
    - reserva + `INSERT` do ticket (com `scheduled_at = ocorrencia`, R-27; violação de `ix_tbsss_tck_ocor` = `ROLLBACK` + WARN `OCORRENCIA_DUPLICADA` e, numa **nova transação**, `avancar_sem_ticket` com a mesma `antiga` e a `nova_data` da decisão, CR-008 R-31) + `ticket_resp` (passo 6); prioridade 1 rebaixada a 2 quando o responsável deixou de ser admin (WARN `PRIORIDADE_REBAIXADA`);
    - **avanço sem ticket** na sobreposição e no *misfire* `SKIP` sem conclusão (R-05); `ultimo_ticket_id` nulo, inexistente ou terminal = livre; WARN `SKIP_OVERLAP_PRESO` quando o ticket que bloqueia passou do tempo máximo do script mais `node_offline_timeout_s` (R-26);
    - **decisão com `cron_erro = True`** (CR-008, R-19): passos 4 e 5 como em qualquer regra (sobreposição, `SKIP`, snapshot) e `pausar_cron_erro`, com ou sem ticket; **`CronErro`** (expressão sintaticamente inválida): pausa `CRON_INVALIDO` sem ticket (passo 7); `PARAM_INVALIDO` e `CRON_INVALIDO` com o código e a mensagem no `detalhe` (R-26);
    - **erro de banco** (CR-008, R-22): `ROLLBACK`, WARN `DESDOBRO_ERRO_BANCO` e nova tentativa no ciclo seguinte; contador de falhas seguidas por regra em memória (zerado no sucesso); na 3ª, `pausar_erro_interno`;
    - **exceção que não é de banco:** `ROLLBACK`, ERROR com stack e `pausar_erro_interno` (R-08);
    - **paginação e orçamento:** páginas até vir uma incompleta ou gastar `heartbeat_interval_s / 2`;
    - pausa (passo 7), auditada como `AGD_PAUSAR` (`entidade = 'tbsss_agendamentos'`, `entidade_id` = id da regra, `ator = 'SYSTEM:<agent_id>'`) e registrada em WARN;
    - `rowcount = 0` resulta em `ROLLBACK` e a próxima regra.
  - **Conclusão da regra (`concluir = True`, `nova_data = None`; README §7.5, D1):** `proxima_execucao` é `NOT NULL`, então a conclusão **não** grava `NULL`. Ela substitui os passos 6 e 7 por um **único** `UPDATE` otimista, literal do README, que mantém `proxima_execucao = antiga_data`:
    - **com ticket** (a ocorrência atual ainda gera ticket): `SET ativo = 'N', pausa_motivo = 'CONCLUIDO', ultima_execucao = SYSDATE, ultimo_ticket_id = :ticket_id, updated_at = SYSDATE, updated_by = :ator WHERE id = :id AND ativo = 'S' AND proxima_execucao = :antiga_data`, com o `:ticket_id` do `NEXTVAL`; se `rowcount = 1`, seguem o `INSERT` do ticket e o do `ticket_resp`; se 0, `ROLLBACK` e próxima regra;
    - **sem ticket** (`SKIP` fora da tolerância em `UNICA`, ou sobreposição): o `SET` fica só com `ativo`, `pausa_motivo` e `updated_*`; `ultima_execucao` e `ultimo_ticket_id` não mudam;
    - auditada como `AGD_PAUSAR` com o detalhe `pausa_motivo: CONCLUIDO` e registrada em **INFO** (não WARN, porque não é falha). O passo 7 **não** se aplica à conclusão.
  - **Sobreposição numa regra que conclui (D2):** se o `ultimo_ticket_id` estiver `PENDING`/`RUNNING` e a decisão for `concluir = True`, a regra é concluída **sem ticket** (variante acima), a ocorrência atual entra em `perdidas` e o log registra INFO `SKIP_OVERLAP` com o total de perdidas. Sem conclusão, a sobreposição só avança a data (passo 6, sem ticket) com INFO `SKIP_OVERLAP`.
  - **Ocorrências perdidas (README §7.4, D3):** o número de `perdidas` de `recurrence.avaliar_disparo` vai para o log em **INFO** quando coalescidas **dentro** de `misfire_tolerance_s` e em **WARN** só quando o atraso passa da tolerância (misfire de verdade).

    A ordem de locks é `tbsss_agendamentos` → `tbsss_tickets`.
  - **NODE_OFFLINE** (ciclo do orquestrador): `marcar_node_offline`, com log INFO dos ids; só roda com o heartbeat do próprio agente em dia (menos de `fence_timeout_s / 2`) e fora da suspensão por **salto de relógio** (CR-007, D3: diferença entre o avanço do `SYSDATE` do heartbeat e o do relógio monotônico acima de 30 s gera WARN `SALTO_RELOGIO` e suspende o NODE_OFFLINE por `node_offline_timeout_s`). **CR-008, R-10:** a própria transação do `marcar_node_offline` lê `SYSDATE` antes do `SELECT ... FOR UPDATE SKIP LOCKED` e confere o salto contra o monotônico desde o último `SYSDATE` lido; com salto, não marca nada e inicia a suspensão ali mesmo.
  - **Self-fencing** (README §8.9):
    - a **cada iteração do laço e depois de cada chamada ao banco** (CR-007, R-04; unifica README §8.1 e §8.9), se `monotonic() - ultimo_hb_ok > fence_timeout_s`, o agente pede o encerramento de **todas** as execuções de uma vez (máquina de estados: SIGTERM em todos, SIGKILL nos restantes depois de `kill_grace_s`), suspende os claims, registra CRITICAL `FENCED` e entra em modo "cercado";
    - em modo cercado, só tenta reconectar, **reutilizando a combinação de driver escolhida na subida** (CR-002; não há nova sondagem sem reinício);
    - ao reconectar, finaliza cada ticket que possuía: **pelo `.sss_result`** quando ele existe (o resultado real, CR-008 R-12), senão `finalizar_fenced` (aceitando `rowcount = 0` nos dois), faz o flush dos logs possíveis e volta ao modo normal só depois de um heartbeat confirmado (com `ultimo_hb_ok` medido no início da transação, CR-008 R-09).
  - **Graceful shutdown completo** (§8.11), acionado por sinal (`plataforma.instalar_parada`) ou pelo arquivo `work_dir/sss-<agent_id>.stop` (removido ao final):
    - `DRAIN`: para o claim e o desdobro e aguarda os filhos até `shutdown_grace_s`, **mantendo** heartbeat, varredura, log pump e fence (CR-007, R-04);
    - `TERMINATE`: encerramento pela máquina de estados do executor (`pedir_encerramento`/`avancar_encerramento`) + `FAILED/SHUTDOWN/-6`;
    - em ambos: flush dos logs, `agente_parar` (com o filtro de `hostname`/`pid_daemon`), remoção do `.stop`, auditoria `AGENTE_FIM` (`entidade = 'tbsss_agentes'`, `entidade_id` = id do agente; README §4.4), fechamento de recursos e saída com código 0.
- **Testes:**
  - `applications/script_scheduling_service/scripts/test_scheduler_ha.py` (mock + relógio monotônico injetável). Cobre:
    - desdobro OK com `ticket_id` preservado;
    - corrida (`reservar` com `rowcount = 0`) sem ticket gerado;
    - pausa por cada motivo;
    - `SKIP_OVERLAP` avança a data sem gerar ticket;
    - *misfire* `RUN_ONCE` gera 1 ticket após downtime;
    - *misfire* `SKIP`;
    - conclusão da `UNICA` **com** ticket: um único `UPDATE` com `ativo = 'N'`, `CONCLUIDO`, `ultima_execucao` e `ultimo_ticket_id`, sem gravar `proxima_execucao = NULL` (o bind de `proxima_execucao` continua `antiga_data`), seguido do `INSERT` do ticket; `AGD_PAUSAR` com `pausa_motivo: CONCLUIDO` em INFO; nenhum `UPDATE` de pausa (passo 7);
    - conclusão **sem** ticket (`SKIP` fora da tolerância em `UNICA`): `SET` só com `ativo`, `pausa_motivo` e `updated_*`;
    - colunas de registro (CR-006): ticket e `ticket_resp` do desdobro com `created_by = 'SYSTEM:<agent_id>'`; a reserva não grava `updated_*` na regra; pausa, conclusão, `NODE_OFFLINE`, `FENCED` e `agente_parar` gravam `updated_*` com o ator do agente;
    - conclusão por `data_fim` com o ticket da ocorrência atual;
    - sobreposição numa regra que conclui: conclui sem ticket, `perdidas` inclui a ocorrência atual, INFO `SKIP_OVERLAP`;
    - perdidas dentro da tolerância em INFO e fora dela em WARN (`assertLogs`);
    - snapshot do ticket derivado na **versão 4**, com `path_file` absoluto (sem `pasta_base`);
    - nenhuma operação do `scheduler_agenda` chama `commit`/`rollback` (cursor/conexão mock); o `COMMIT` é um só por regra;
    - bind de data sem microssegundos (inspecionar os parâmetros passados ao cursor mock e o `setinputsizes` com `TIPO_DATE`);
    - fencing disparado no limiar e não antes, inclusive quando o limiar vence **durante** uma chamada ao banco travada até `call_timeout`;
    - **CR-007:** paginação do desdobro com 3 páginas e orçamento estourado; regra travada por outro agente pulada (`SKIP LOCKED`); avanço sem ticket sem mexer em `ultimo_ticket_id`; `ultimo_ticket_id` inexistente tratado como livre; `SKIP_OVERLAP_PRESO`; `ERRO_INTERNO` numa transação separada; pausa sobre regra já concluída com `rowcount = 0`; `scheduled_at` = ocorrência coberta; `OCORRENCIA_DUPLICADA`; `PRIORIDADE_REBAIXADA`; `CronErro` gerando o ticket vencido antes de pausar; NODE_OFFLINE sem os próprios tickets, com linha travada pulada, suspenso por salto de relógio e quando o próprio heartbeat está velho; encerramento de 30 execuções no fencing sem bloquear o laço; `DRAIN` mantendo o heartbeat;
    - recuperação do fencing; o flush após reconexão usa o offset idempotente do README §8.10 e não duplica bloco cujo `COMMIT` anterior teve resultado desconhecido;
    - **CR-008:**
      - **R-03:** o `INSERT` do desdobro recebe `scheduled_at = ocorrencia` (nunca `SYSDATE`) e a prioridade rebaixada;
      - **R-09:** fencing medido a partir do início da transação de heartbeat (transação com 3 chamadas lentas não adia o fence);
      - **R-10:** salto de relógio detectado na transação do `NODE_OFFLINE`, entre dois heartbeats: nenhum ticket marcado e suspensão iniciada;
      - **R-12:** recuperação do fencing com `.sss_result` `SUCCESS` grava `SUCCESS`, não `FENCED`; sem `.sss_result`, `FENCED`;
      - **R-19:** regra CRON vencida cuja próxima ocorrência fica além do horizonte (no teste, horizonte reduzido por injeção, porque o mínimo de configuração, 1.461 dias, cobre o 29/02): ticket da vencida, pausa `CRON_INVALIDO` com `proxima_execucao` mantida; com o último ticket `RUNNING`, sem ticket (sobreposição) e mesma pausa; com `SKIP` fora da tolerância, sem ticket;
      - **R-21:** `SKIP` com a vencida mais recente dentro da tolerância gera o ticket dela;
      - **R-22:** ORA-01653 no `INSERT` não pausa a regra (WARN e nova tentativa); 3 falhas seguidas pausam `ERRO_INTERNO`; `ValueError` pausa na primeira;
      - **R-31:** depois de `OCORRENCIA_DUPLICADA`, a regra avança sem ticket numa nova transação e não é reprocessada no ciclo seguinte;
      - **R-33:** todo `rbac.Motivo` vira um `pausa_motivo` aceito por `ck_tbsss_agd_pausa`;
    - `DRAIN` e `TERMINATE`, acionados por sinal e pelo arquivo `.stop`;
    - as invariantes I1 a I4 (README §8.9) respeitadas pelo config de teste.
  - Com `SSS_TEST_ORACLE=1` (README §2.5; owner e prefixo do `instance/config.ini`), após `preparar_schema_descartavel('agente')` de `_oracle_test_support` e antes de qualquer DML. Cada cenário cria agentes, regras e tickets com identificadores próprios da execução; registra todos os IDs retornados; em `finally`, para os agentes/processos iniciados, confirma que os filhos terminaram e remove apenas as regras/tickets/agentes criados pela fixture, na ordem compatível com as FKs. Se a limpeza falhar, o teste falha e informa somente os IDs restantes, sem limpeza ampla.
    - **teste obrigatório de microssegundos (README §7.5):** um desdobro real com `antiga_data`/`nova_data` contendo microssegundos não resulta em `rowcount = 0` (o tipo `DATE` declarado descarta a fração);
    - uma `UNICA` concluída no banco fica com `ativo = 'N'`, `pausa_motivo = 'CONCLUIDO'` e `proxima_execucao` igual à lida (não nula);
    - dois agentes e uma regra `CRON` `* * * * *` por 3 minutos, gerando exatamente 1 ticket por minuto (sem duplicatas, verificado por `COUNT` agrupado por minuto de `created_at`);
    - encerrar um agente abruptamente durante uma execução (`kill -9` somente no PID criado pela fixture, em POSIX): o outro agente marca `NODE_OFFLINE` depois de `node_offline_timeout_s`; o filho órfão é tratado pelo startup check da religação e encerrado antes da limpeza da fixture.

**OUT**
- Sem purge (isso é o F9.1).

## Requisitos
1. **Uma transação por regra.** Uma regra com erro não bloqueia as demais.
2. A `antiga_data` usada no `UPDATE` é o valor **lido do banco**, nunca recalculado (README §7.5, passo 1).
3. Fencing medido **somente** com `time.monotonic()`.
4. `scheduler_loop.py` e `scheduler_fila.py` não usam primitivas de SO diretamente; usam `modules/plataforma/`. A exceção restrita do `bin/sss-helper` é definida em F8.0/AGENTS §3.2.
5. `fence_timeout_s`, `node_offline_timeout_s` e os demais valores de `config_criticos` vêm do config e devem ser idênticos em todos os agentes (README §8.9 e §8.12). O F8.3 os registra em INFO, grava `config_criticos` e confere os outros agentes (CR-007, R-23).

## Critérios de aceite
- [ ] Os testes com mock passam.
- [ ] Os testes com 2 agentes passam apenas no schema descartável validado e limpam somente as fixtures próprias. Sem os pré-requisitos, ficam `NÃO TESTADO`; com DSN e schema inválido, falham antes de DML.
- [ ] O log de um ciclo completo é legível e permite reconstruir as decisões sem acesso ao banco.

## Verificação
`python -m unittest discover -s scripts -p "test_scheduler_ha.py" -v`

## Saída
Relatório AGENTS.md §9.
