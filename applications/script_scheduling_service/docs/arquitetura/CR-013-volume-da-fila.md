# CR-013: Volume da fila (1 milhão de tickets pendentes)

| Campo | Valor |
|---|---|
| Status | **Registrado** em 2026-10-20 pelo responsável pelo produto. A executar depois do CR-012 e antes do F8.3d |
| Origem | Pergunta do responsável pelo produto: com mais de 1 milhão de tickets abertos no mesmo ambiente, é possível colocar mais de um agente para atender? |
| Restrições | Python 3.6. Oracle 11gR2 (sem sintaxe 12c+). A massa de teste no GFPR só com aprovação explícita, porque mexe no banco compartilhado de DEV |
| Afeta | README §5.3, §8.2 e §14; `docs/explain/SCHEDULER.md`; `sql_ident` (índice da fila); `repo_oracle/scheduler_fila.candidatos` |
| Depende de | F8.3a (consulta de candidatos), CR-012 |

---

## 1. Situação atual

* **Vários agentes no mesmo ambiente funcionam.** Cada agente lista o ambiente em `ambientes_atendidos`; a reserva é `UPDATE ... WHERE status = 'PENDING'` e só um agente ganha cada ticket (README §8.3). Mais de um agente no mesmo servidor também é possível (`agent_id` e `work_dir` diferentes), mas aumentar `max_parallel_jobs` costuma bastar.
* **O teto do script limita o paralelismo, não o número de agentes.** `max_qtd_parallel_env` vale por script e ambiente, somando todos os agentes. Um milhão de tickets do mesmo script com teto 2 roda 2 por vez, com qualquer número de agentes.
* **Disputa pelo lock do script.** Agentes que tentam o mesmo script ao mesmo tempo se revezam (`FOR UPDATE WAIT 5`, e quem espera passa para o próximo candidato). Funciona, sem ganho de vazão para aquele script.
* **Ponto de atenção: a consulta de candidatos.** A ordem da fila é a prioridade com envelhecimento (README §5.3), que depende de `SYSDATE`. O banco não consegue usar a ordem do índice `ix_tbsss_tck_fila`: a cada ciclo de claim, cada agente percorre todos os tickets `PENDING` vencidos, lê a tabela para cada um (ambiente, script, cancelamento), avalia a subconsulta do teto e ordena, para devolver `claim_batch_size` linhas. O `EXPLAIN` do F8.3a usou estatísticas simuladas de 1 milhão de tickets na tabela, mas só 2.000 na fila. Com 1 milhão pendentes, o custo de cada ciclo cresce com a fila e com o número de agentes: mais agentes aumentam a carga do banco em vez de acelerar.

## 2. Proposta

1. **Medir antes de mudar.** Com aprovação, gerar 1 milhão de tickets `PENDING` de teste no GFPR (massa própria, removida no fim) e medir a consulta de candidatos e o claim com 1, 2 e 5 agentes: tempo por ciclo, `consistent gets` e plano real (`DBMS_XPLAN.DISPLAY_CURSOR`).
2. **Ajustar o índice e a consulta conforme o resultado.** Hipótese principal:
   * índice da fila com o ambiente na frente e a prioridade e o agendamento na ordem da fila, para o banco ler os candidatos já ordenados por ambiente;
   * envelhecimento aplicado só dentro de uma janela dos primeiros N tickets de cada prioridade, e não sobre a fila inteira, preservando a regra do README §5.3 (nenhum ticket fica parado para sempre);
   * o teto continua na seleção (CR-007, R-07) e a checagem definitiva continua no claim, sob lock.
3. **Registrar o novo `EXPLAIN`** em `docs/explain/SCHEDULER.md` com o volume real de 1 milhão pendentes, e o limite medido no README §14.

## 3. Critérios de aceite

* O ciclo de claim de um agente com 1 milhão pendentes fica dentro do orçamento de tempo do laço (CR-007), com plano sem `TABLE ACCESS FULL` em `tbsss_tickets` e sem ordenar a fila inteira.
* Com 5 agentes, o tempo por ciclo não cresce de forma proporcional ao número de agentes.
* A ordem efetiva da fila (prioridade, envelhecimento, `scheduled_at`, `id`) continua igual à do README §5.3 nos casos de teste existentes.
