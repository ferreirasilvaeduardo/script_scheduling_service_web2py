# SSS — Prompt F8.4: Daemon — desdobro de agendamentos, NODE_OFFLINE, self-fencing e shutdown

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.1 (binds de data), §3.2 (encerramento escalonado), §4.9–4.11, §6
- `README.md` §7 (inteiro, **especialmente §7.5**), §8.0, §8.1, §8.8, §8.9, §8.11 (inclusive o arquivo `.stop`), §10 (tabela 12 e a desativação com dependência)
- Arquivos: `modules/scheduler_loop.py`, `modules/repo_oracle/scheduler_fila.py`, `modules/recurrence.py`, `modules/params_compiler.py`, `modules/rbac.py`, `modules/plataforma/`, `modules/db_conn.py`

## Objetivo
Completar o agente com a geração de tickets a partir dos agendamentos (desdobro otimista), a detecção de nós caídos, o self-fencing contra split-brain e o desligamento controlado.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/repo_oracle/scheduler_agenda.py`** (repositório interno), com o SQL do README §7.5 **literal**:
  - `regras_vencidas(conn, lote)`;
  - `carregar_regra(conn, id)`, que guarda a `antiga_data` exatamente como lida;
  - `contexto_rbac_usuario(conn, usuario_id)` (para `rbac.pode_executar`);
  - `nextval_ticket(conn)`;
  - `reservar(conn, id, antiga, nova, ticket_id) -> bool` (rowcount);
  - `inserir_ticket_derivado(...)` com o `id` explícito e as respostas;
  - `pausar(conn, id, antiga, motivo) -> bool`;
  - `concluir(conn, id, antiga) -> bool` (`ativo = 'N'`, `pausa_motivo = 'CONCLUIDO'`);
  - `status_ticket(conn, id)`.

  Todos os binds de data usam `TIPO_DATE`, sem microssegundos.
- **`applications/script_scheduling_service/modules/repo_oracle/scheduler_fila.py` (ampliar):**
  - `marcar_node_offline(conn, timeout_s) -> n` (§8.8, literal);
  - `finalizar_fenced(...)`;
  - `agente_parar(conn, agente_id)`.
- **`applications/script_scheduling_service/modules/scheduler_loop.py` (completar os pontos de extensão do F8.3):**
  - **Desdobro** (ciclo do orquestrador): para cada regra vencida, os passos 1–8 do README §7.5, **em uma transação por regra**:
    - revalidação de privilégios (`USUARIO_INATIVO`, `SEM_PERMISSAO`, `SCRIPT_INATIVO`, `AMBIENTE_INATIVO`);
    - `recurrence.avaliar_disparo` com *misfire*;
    - sobreposição (`SKIP_OVERLAP`);
    - compilação do snapshot a partir de `parametros_json` (`PARAM_INVALIDO`);
    - `CRON_INVALIDO`;
    - `reservar` + `inserir_ticket_derivado`;
    - conclusão da `UNICA` / `data_fim`;
    - auditoria `AGD_PAUSAR`;
    - `rowcount = 0` resulta em `ROLLBACK` e a próxima regra.

    A ordem de locks é `tbsss_agendamentos` → `tbsss_tickets`.
  - **NODE_OFFLINE** (ciclo do orquestrador): `marcar_node_offline`, com log INFO com a contagem.
  - **Self-fencing** (README §8.9):
    - a cada ciclo rápido, se `monotonic() - ultimo_hb_ok > fence_timeout_s`, o agente executa `encerrar` (`plataforma.encerrar_grupo`) em **todas** as execuções, suspende os claims, registra CRITICAL `FENCED` e entra em modo "cercado";
    - em modo cercado, só tenta reconectar, **reutilizando a combinação de driver escolhida na subida** (CR-002; não há nova sondagem sem reinício);
    - ao reconectar, executa `finalizar_fenced` em cada ticket (aceitando `rowcount = 0`), faz o flush dos logs possíveis e volta ao modo normal só depois de um heartbeat confirmado.
  - **Graceful shutdown completo** (§8.11), acionado por sinal (`plataforma.instalar_parada`) ou pelo arquivo `work_dir/sss-<agent_id>.stop` (removido ao final):
    - `DRAIN`: para o claim e o desdobro e aguarda os filhos até `shutdown_grace_s`;
    - `TERMINATE`: `encerrar` + `FAILED/SHUTDOWN/-6`;
    - em ambos: flush dos logs, `agente_parar`, auditoria `AGENTE_FIM`, fechamento de recursos e saída com código 0.
- **Testes:**
  - `applications/script_scheduling_service/scripts/test_scheduler_ha.py` (mock + relógio monotônico injetável). Cobre:
    - desdobro OK com `ticket_id` preservado;
    - corrida (`reservar` com `rowcount = 0`) sem ticket gerado;
    - pausa por cada motivo;
    - `SKIP_OVERLAP` avança a data sem gerar ticket;
    - *misfire* `RUN_ONCE` gera 1 ticket após downtime;
    - *misfire* `SKIP`;
    - conclusão da `UNICA`;
    - bind de data sem microssegundos (inspecionar os parâmetros passados ao cursor mock);
    - fencing disparado no limiar e não antes;
    - recuperação do fencing;
    - `DRAIN` e `TERMINATE`, acionados por sinal e pelo arquivo `.stop`;
    - a invariante `fence * 2 <= offline` respeitada pelo config de teste.
  - Com `SSS_TEST_DSN`:
    - dois agentes e uma regra `CRON` `* * * * *` por 3 minutos, gerando exatamente 1 ticket por minuto (sem duplicatas, verificado por `COUNT` agrupado por minuto de `created_at`);
    - encerrar um agente abruptamente durante uma execução (`kill -9` no POSIX; `taskkill /F /PID` no Windows): o outro agente marca `NODE_OFFLINE` depois de `node_offline_timeout_s`. No Windows, o Job com `KILL_ON_JOB_CLOSE` encerra o filho junto com o daemon; no POSIX, o filho órfão é tratado pelo startup check da religação.

**OUT**
- Sem purge (isso é o F9.1).

## Requisitos
1. **Uma transação por regra.** Uma regra com erro não bloqueia as demais.
2. A `antiga_data` usada no `UPDATE` é o valor **lido do banco**, nunca recalculado (README §7.5, passo 1).
3. Fencing medido **somente** com `time.monotonic()`.
4. Nenhuma primitiva de SO fora de `plataforma/`.

## Critérios de aceite
- [ ] Os testes com mock passam.
- [ ] Os testes com 2 agentes passam com `SSS_TEST_DSN`. Sem ele, ficam `NÃO TESTADO`.
- [ ] O log de um ciclo completo é legível e permite reconstruir as decisões sem acesso ao banco.

## Verificação
`python -m unittest discover -s scripts -p "test_scheduler_ha.py" -v`

## Saída
Relatório AGENTS.md §9.
