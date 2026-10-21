# Auditoria do scheduler contra o README (2026-10-17, pós-CR-006)

| Campo | Valor |
|---|---|
| Escopo | README, AGENTS, prompts F7.0 a F9.2 e o código existente (web, FAKE, `sql_ident`, `sss_config`, `path_guard`, `params_compiler`, `recurrence`, `cron_parser`) |
| Método | Quatro frentes independentes, somente leitura: (1) ciclo de vida do ticket e motor; (2) agendamentos e desdobro; (3) dados, Oracle e operação; (4) segurança da cadeia pedido → snapshot → execução. Achados repetidos entre frentes foram unificados; os principais foram conferidos no código e no README |
| Veredito | **FAIL**: 5 bloqueantes, 12 altos, 12 médios e 1 baixo, além de contradições entre documentos |
| Correção | CR-007 (`CR-007-scheduler-robustness.md`), aprovado no mesmo dia; a coluna "Regra" aponta a correção |

## Achados

| # | Sev. | Achado | Conferido | Regra |
|---|---|---|---|---|
| S-01 | Bloqueante | O processo do script sobrevive ao fim do ticket: depois de `NODE_OFFLINE`, o startup check só olhava tickets `RUNNING` e nunca matava o filho; netos continuavam depois da saída do processo principal; o F8.4 prometia um tratamento que o README não tinha | README §8.12 passo 9 | R-01, R-02 |
| S-02 | Bloqueante | O laço single-thread não tinha orçamento de tempo: `kill_grace_s` até 300 s, encerramento sequencial de grupos, `call_timeout` longo, reconexão com espera e lote de claim podiam passar do `node_offline_timeout_s`, com os filhos vivos (execução dupla) | README §8.9, §12.1 | R-04 |
| S-03 | Bloqueante | Ticket `RUNNING` sem dono: falha de banco na finalização, exceção depois do claim, `COMMIT` com desfecho desconhecido ou erro de codificação no spawn terminavam em `NODE_OFFLINE` com o motivo errado | README §8.7 | R-03 |
| S-04 | Bloqueante | O desdobro não tinha SQL para "avançar sem ticket": seguir o passo 6 gravava `ultimo_ticket_id` inexistente e quebrava a proteção contra sobreposição | README §7.5 | R-05 |
| S-05 | Bloqueante | Agente e script com o mesmo usuário: o script lia o `secrets.cfg` (o `cookie_key` era obrigatório também no agente), forjava sessão de administrador, usava a conta Oracle dona do esquema e lia o ambiente de outros tickets; o aceite do §14 partia de premissa falsa | `sss_config.py`, README §14 | R-06 |
| S-06 | Alto | Bloqueio na cabeça da fila: um script no teto ocupava o lote e os outros nunca eram vistos; prioridade 4 sem envelhecimento | README §8.2 | R-07 |
| S-07 | Alto | Desdobro com um lote único compartilhado pelos agentes (atraso, *misfire* falso, perda com `SKIP`); regra que falha sempre travava o desdobro | README §7.5 | R-08 |
| S-08 | Alto | Contexto muda depois da criação: o ticket manual não revalidava solicitante nem ambiente; ambiente desativado não parava os agentes; `scheduled_at` sem teto | README §8.4, §5.4 | R-09 |
| S-09 | Alto | Salto do `SYSDATE` (horário de verão, NTP) marcava todos os tickets como `NODE_OFFLINE`; o §7.1 prometia "executa uma vez", falso com `SKIP` | README §7.1, §8.8 | R-10 |
| S-10 | Alto | `agent_id` duplicado: registro com corrida e sem detecção em execução | README §8.12 | R-11 |
| S-11 | Alto | Sessão zumbi segurando lock (DML sem limite de espera), *call timeout* e erros de failover RAC/Data Guard sem mapeamento | README §2.3, §8.8 | R-12 |
| S-12 | Alto | Sem versão do esquema nem migração; `init_db` idempotente só pelo nome; trigger inválida passava | README §11.1 | R-13 |
| S-13 | Alto | Link simbólico no caminho digitado: só a cadeia do caminho real era checada | `path_guard.py` | R-14 |
| S-14 | Alto | Arquivo ou diretório do próprio agente com modo sem escrita passava na checagem; executável do interpretador sem checagem de cadeia | `path_guard.py` | R-15 |
| S-15 | Alto | A heurística anti-ReDoS era contornável (`(a|a)*b` aceita, tempo exponencial) e a regex roda no desdobro, travando o laço | `params_compiler.py` | R-16 |
| S-16 | Alto | Locale: launcher sem `LANG`; `-I` anula `PYTHONIOENCODING`; `UnicodeEncodeError` no spawn não virava `SPAWN_ERROR` | README §8.6, §12.2 | R-17 |
| S-17 | Alto | Sem monitoração (fila sem atendente, `RUNNING` sem PID, purge falhando, crescimento de LOB) e motivo da pré-validação invisível | README §13 | R-18 |
| S-18 | Médio | A pausa não conferia `ativo = 'S'` e sobrescrevia `CONCLUIDO`/`MANUAL` (README e FAKE) | `repo_fake/agendamentos.py` | R-19 |
| S-19 | Médio | `sensivel` de `S` para `N` expunha respostas já gravadas em tickets e agendamentos | `admin_parametros_service.py` | R-20 |
| S-20 | Médio | Purge concorrente em todos os nós e ator indefinido | README §11.3 | R-21 |
| S-21 | Médio | Retenção da auditoria sem piso; o usuário da aplicação era o dono do esquema e podia apagar a trilha | README §12.1 | R-22, R-06 |
| S-22 | Médio | Configurações que precisam ser iguais em todos os nós sem garantia; horizonte do CRON curto quebrava regra válida | README §12.1 | R-23 |
| S-23 | Médio | O snapshot não amarrava o conteúdo do arquivo; catálogo e snapshot podiam divergir no claim | README §6.5 | R-24 |
| S-24 | Médio | Mascaramento por ticket no agente não especificado; valores sensíveis curtos | README §8.10 | R-25 |
| S-25 | Médio | Sobreposição sem fim e sem aviso; agenda e lista não refletiam o daemon; retomada sem reavaliar a causa; motivo da pausa sem detalhe | README §7.5 a §7.7 | R-26 |
| S-26 | Médio | O ticket do desdobro não registrava a ocorrência que cobria | README §7.5 | R-27 |
| S-27 | Médio | Cancelamento entre claim e spawn não impedia a execução; heartbeat do agente ocioso não garantido | README §8.4, §8.7 | R-28 |
| S-28 | Médio | Dimensionamento de LOB, `COUNT` e leitura de histórico inteiro nas telas, estatísticas coletadas com tabelas vazias | README §10, §11.1 | R-29 |
| S-29 | Médio | O quadro Registro (CR-006) mostrava o login de quem alterou a quem não tem `VER_AUDITORIA` | README §10 | R-30 |
| S-30 | Baixo | `table_prefix` com maiúsculas aceito pela configuração e recusado pelo registro | `sss_config.py` × `sql_ident.py` | R-31 |

Contradições e ajustes menores (colunas curtas, lista de bloqueio do ambiente, limpeza do `work_dir`, purge de log de ticket em execução, mensagem do CRON, conclusão sem ticket, prioridade 1 no desdobro, `--recreate`, alias nas expressões dos índices, `RETURNING id`, encerramento de grupo que não é filho, momento do fence, arquivo `.stop`, nível de log de lock, definição de `PENDING`): regra R-32 do CR-007.

## O que foi conferido e estava correto

* Todo identificador cabe em 30 caracteres com prefixo de 8; toda FK tem índice de coluna líder.
* Fila, varredura, NODE_OFFLINE, teto por script e purge usam os índices corretos; os SQLs literais do README referenciam colunas e índices do registro.
* Sem ciclo de deadlock entre web (cancelamento, cadastros) e daemon (claim, desdobro, offline).
* `recurrence.py` e `cron_parser.py` corretos nos casos de borda (dia 31, 29/02, `UNICA` no passado, `data_fim` inclusiva); corrida de dois agentes no desdobro resolvida pelo `UPDATE` otimista.
* `argv` sem shell, valores iniciados em `-` tratados, NUL recusado na web, auditoria sem valores, ARG_MAX folgado, daemon recusa root.
