# SSS — Prompt F8.4: Daemon — desdobro de agendamentos, NODE_OFFLINE, self-fencing e shutdown

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.1 (binds de data), §3.2 (encerramento escalonado), §4.9–4.11, §6
- `docs/arquitetura/CR-003-correcoes-pos-analise.md` (D1, D2, D3, D7, D16 e os achados "Conclusão no desdobro", "Bind DATE com microssegundos" e "Contrato do desdobro incompleto")
- `README.md` §4.4 (`AGD_PAUSAR`, `AGENTE_FIM`), §6.5 (snapshot versão 4; CR-005), §7 (inteiro, **especialmente §7.4 e §7.5**, inclusive "Conclusão da regra", "Sobreposição numa regra que conclui", "Bind de datas" e "Contrato do repositório para o desdobro"), §8.0, §8.1, §8.8, §8.9 (inclusive "Mesmos tempos em todos os nós"), §8.11 (inclusive o arquivo `.stop`), §10 (tabela 12 e a desativação com dependência), §13
- Arquivos: `modules/scheduler_loop.py`, `modules/repo_oracle/scheduler_fila.py`, `modules/recurrence.py`, `modules/params_compiler.py`, `modules/rbac.py`, `modules/plataforma/`, `modules/db_conn.py`

## Objetivo
Completar o agente com a geração de tickets a partir dos agendamentos (desdobro otimista), a detecção de nós caídos, o self-fencing contra split-brain e o desligamento controlado.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/repo_oracle/scheduler_agenda.py`** (repositório interno, processo batch, sem FAKE; README §2.5), com o SQL do README §7.5 **literal** e as operações **distintas** do "Contrato do repositório para o desdobro":
  - `regras_vencidas(conn, lote)`: a leitura do lote vencido;
  - `carregar_regra(conn, id)`: a leitura completa da regra, que guarda a `antiga_data` exatamente como lida;
  - `contexto_rbac_usuario(conn, usuario_id)` (para `rbac.pode_executar`);
  - `reservar_e_criar_ticket(conn, regra, antiga, nova, ticket) -> bool`: numa **única** operação, `NEXTVAL` de `sq_tbsss_tickets`, a reserva otimista do passo 6 (`rowcount`) e, se `rowcount = 1`, o `INSERT` do ticket com o `id` explícito (`agendamento_id`, `solicitante` = login do `usuario_id`, `ip_origem = NULL`, `scheduled_at = SYSDATE`, prioridade da regra) e o `INSERT` em `tbsss_ticket_resp`;
  - `concluir_com_ticket(conn, regra, antiga, ticket) -> bool` e `concluir_sem_ticket(conn, id, antiga) -> bool`: o `UPDATE` único da conclusão (abaixo);
  - `pausar(conn, id, antiga, motivo) -> bool` (passo 7);
  - `status_ticket(conn, id)`.

  Os nomes acima são sugestões; o que é obrigatório são as operações distintas. **Nenhuma** delas faz `COMMIT` nem `ROLLBACK` sozinha: todas recebem a conexão da transação do ciclo, e o `COMMIT` único é do passo 8. Todos os binds de data (`:antiga_data`, `:nova_data`) são declarados com `TIPO_DATE` via `db_conn.definir_tipos_entrada` (`setinputsizes` com `oracledb.DB_TYPE_DATE` ou `cx_Oracle.DATETIME`; README §7.5 "Bind de datas"). A `antiga_data` nunca é recalculada nem convertida por fuso.
- **`applications/script_scheduling_service/modules/repo_oracle/scheduler_fila.py` (ampliar):**
  - `marcar_node_offline(conn, timeout_s) -> n` (§8.8, literal);
  - `finalizar_fenced(...)`;
  - `agente_parar(conn, agente_id)`.
- **`applications/script_scheduling_service/modules/scheduler_loop.py` (completar os pontos de extensão do F8.3):**
  - **Desdobro** (ciclo do orquestrador): para cada regra vencida, os passos 1–8 do README §7.5, **em uma transação por regra**:
    - revalidação de privilégios (`USUARIO_INATIVO`, `SEM_PERMISSAO`, `SCRIPT_INATIVO`, `AMBIENTE_INATIVO`);
    - `recurrence.avaliar_disparo` com *misfire*;
    - sobreposição (`SKIP_OVERLAP`);
    - compilação do **snapshot versão 4** a partir de `parametros_json`, com `params_compiler.compilar_snapshot` (inclui `path_file` absoluto do script, sem `pasta_base`; README §6.5, CR-005) (`PARAM_INVALIDO`);
    - `CRON_INVALIDO`;
    - reserva + `INSERT` do ticket + `ticket_resp` (passo 6);
    - pausa (passo 7), auditada como `AGD_PAUSAR` (`entidade = 'tbsss_agendamentos'`, `entidade_id` = id da regra, `ator = 'SYSTEM:<agent_id>'`) e registrada em WARN;
    - `rowcount = 0` resulta em `ROLLBACK` e a próxima regra.
  - **Conclusão da regra (`concluir = True`, `nova_data = None`; README §7.5, D1):** `proxima_execucao` é `NOT NULL`, então a conclusão **não** grava `NULL`. Ela substitui os passos 6 e 7 por um **único** `UPDATE` otimista, literal do README, que mantém `proxima_execucao = antiga_data`:
    - **com ticket** (a ocorrência atual ainda gera ticket): `SET ativo = 'N', pausa_motivo = 'CONCLUIDO', ultima_execucao = SYSDATE, ultimo_ticket_id = :ticket_id WHERE id = :id AND ativo = 'S' AND proxima_execucao = :antiga_data`, com o `:ticket_id` do `NEXTVAL`; se `rowcount = 1`, seguem o `INSERT` do ticket e o do `ticket_resp`; se 0, `ROLLBACK` e próxima regra;
    - **sem ticket** (`SKIP` fora da tolerância em `UNICA`, ou sobreposição): o `SET` fica só com `ativo` e `pausa_motivo`; `ultima_execucao` e `ultimo_ticket_id` não mudam;
    - auditada como `AGD_PAUSAR` com o detalhe `pausa_motivo: CONCLUIDO` e registrada em **INFO** (não WARN, porque não é falha). O passo 7 **não** se aplica à conclusão.
  - **Sobreposição numa regra que conclui (D2):** se o `ultimo_ticket_id` estiver `PENDING`/`RUNNING` e a decisão for `concluir = True`, a regra é concluída **sem ticket** (variante acima), a ocorrência atual entra em `perdidas` e o log registra INFO `SKIP_OVERLAP` com o total de perdidas. Sem conclusão, a sobreposição só avança a data (passo 6, sem ticket) com INFO `SKIP_OVERLAP`.
  - **Ocorrências perdidas (README §7.4, D3):** o número de `perdidas` de `recurrence.avaliar_disparo` vai para o log em **INFO** quando coalescidas **dentro** de `misfire_tolerance_s` e em **WARN** só quando o atraso passa da tolerância (misfire de verdade).

    A ordem de locks é `tbsss_agendamentos` → `tbsss_tickets`.
  - **NODE_OFFLINE** (ciclo do orquestrador): `marcar_node_offline`, com log INFO com a contagem.
  - **Self-fencing** (README §8.9):
    - a cada ciclo rápido, se `monotonic() - ultimo_hb_ok > fence_timeout_s`, o agente executa `encerrar` (`plataforma.encerrar_grupo`) em **todas** as execuções, suspende os claims, registra CRITICAL `FENCED` e entra em modo "cercado";
    - em modo cercado, só tenta reconectar, **reutilizando a combinação de driver escolhida na subida** (CR-002; não há nova sondagem sem reinício);
    - ao reconectar, executa `finalizar_fenced` em cada ticket (aceitando `rowcount = 0`), faz o flush dos logs possíveis e volta ao modo normal só depois de um heartbeat confirmado.
  - **Graceful shutdown completo** (§8.11), acionado por sinal (`plataforma.instalar_parada`) ou pelo arquivo `work_dir/sss-<agent_id>.stop` (removido ao final):
    - `DRAIN`: para o claim e o desdobro e aguarda os filhos até `shutdown_grace_s`;
    - `TERMINATE`: `encerrar` + `FAILED/SHUTDOWN/-6`;
    - em ambos: flush dos logs, `agente_parar`, auditoria `AGENTE_FIM` (`entidade = 'tbsss_agentes'`, `entidade_id` = id do agente; README §4.4), fechamento de recursos e saída com código 0.
- **Testes:**
  - `applications/script_scheduling_service/scripts/test_scheduler_ha.py` (mock + relógio monotônico injetável). Cobre:
    - desdobro OK com `ticket_id` preservado;
    - corrida (`reservar` com `rowcount = 0`) sem ticket gerado;
    - pausa por cada motivo;
    - `SKIP_OVERLAP` avança a data sem gerar ticket;
    - *misfire* `RUN_ONCE` gera 1 ticket após downtime;
    - *misfire* `SKIP`;
    - conclusão da `UNICA` **com** ticket: um único `UPDATE` com `ativo = 'N'`, `CONCLUIDO`, `ultima_execucao` e `ultimo_ticket_id`, sem gravar `proxima_execucao = NULL` (o bind de `proxima_execucao` continua `antiga_data`), seguido do `INSERT` do ticket; `AGD_PAUSAR` com `pausa_motivo: CONCLUIDO` em INFO; nenhum `UPDATE` de pausa (passo 7);
    - conclusão **sem** ticket (`SKIP` fora da tolerância em `UNICA`): `SET` só com `ativo` e `pausa_motivo`;
    - conclusão por `data_fim` com o ticket da ocorrência atual;
    - sobreposição numa regra que conclui: conclui sem ticket, `perdidas` inclui a ocorrência atual, INFO `SKIP_OVERLAP`;
    - perdidas dentro da tolerância em INFO e fora dela em WARN (`assertLogs`);
    - snapshot do ticket derivado na **versão 4**, com `path_file` absoluto (sem `pasta_base`);
    - nenhuma operação do `scheduler_agenda` chama `commit`/`rollback` (cursor/conexão mock); o `COMMIT` é um só por regra;
    - bind de data sem microssegundos (inspecionar os parâmetros passados ao cursor mock e o `setinputsizes` com `TIPO_DATE`);
    - fencing disparado no limiar e não antes;
    - recuperação do fencing;
    - `DRAIN` e `TERMINATE`, acionados por sinal e pelo arquivo `.stop`;
    - a invariante `fence * 2 <= offline` respeitada pelo config de teste.
  - Com `SSS_TEST_DSN`:
    - **teste obrigatório de microssegundos (README §7.5):** um desdobro real com `antiga_data`/`nova_data` contendo microssegundos não resulta em `rowcount = 0` (o tipo `DATE` declarado descarta a fração);
    - uma `UNICA` concluída no banco fica com `ativo = 'N'`, `pausa_motivo = 'CONCLUIDO'` e `proxima_execucao` igual à lida (não nula);
    - dois agentes e uma regra `CRON` `* * * * *` por 3 minutos, gerando exatamente 1 ticket por minuto (sem duplicatas, verificado por `COUNT` agrupado por minuto de `created_at`);
    - encerrar um agente abruptamente durante uma execução (`kill -9` no POSIX): o outro agente marca `NODE_OFFLINE` depois de `node_offline_timeout_s`; o filho órfão é tratado pelo startup check da religação.

**OUT**
- Sem purge (isso é o F9.1).

## Requisitos
1. **Uma transação por regra.** Uma regra com erro não bloqueia as demais.
2. A `antiga_data` usada no `UPDATE` é o valor **lido do banco**, nunca recalculado (README §7.5, passo 1).
3. Fencing medido **somente** com `time.monotonic()`.
4. Nenhuma primitiva de SO fora de `plataforma/`.
5. `fence_timeout_s` e `node_offline_timeout_s` vêm do config e devem ser idênticos em todos os agentes (README §8.9, D7); o F8.3 já os registra em INFO na subida. Não crie coluna nem checagem cruzada no banco para isso.

## Critérios de aceite
- [ ] Os testes com mock passam.
- [ ] Os testes com 2 agentes passam com `SSS_TEST_DSN`. Sem ele, ficam `NÃO TESTADO`.
- [ ] O log de um ciclo completo é legível e permite reconstruir as decisões sem acesso ao banco.

## Verificação
`python -m unittest discover -s scripts -p "test_scheduler_ha.py" -v`

## Saída
Relatório AGENTS.md §9.
