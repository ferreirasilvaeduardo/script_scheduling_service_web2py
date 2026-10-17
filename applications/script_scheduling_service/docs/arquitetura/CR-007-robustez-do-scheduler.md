# CR-007: Robustez do scheduler

| Campo | Valor |
|---|---|
| Status | **Aprovado** em 2026-10-17 pelo responsável pelo produto: corrigir os 30 achados da auditoria (S-01 a S-30), com as decisões D1 a D6 tomadas pela opção mais robusta, e fazer nova análise no fim. Plano P0, R1 a R5, UF e FINAL |
| Origem | Auditoria rigorosa do projeto contra o README, feita depois do CR-006 (`docs/arquitetura/AUDITORIA-2026-10-17-scheduler.md`). Veredito FAIL, com 5 furos bloqueantes: o processo do script sobrevivia ao fim do ticket (execução dupla), a invariante do fencing não garantia o que prometia, o ticket podia ficar `RUNNING` sem dono, o desdobro não tinha o SQL de "avançar sem ticket", e o script rodava com o mesmo usuário do agente |
| Restrições | Sem dependência nova de Python. Pilha mantida (Python 3.6+, web2py, Oracle 11gR2, Alpine CSP, somente POSIX). O `sudo` do sistema operacional passa a ser pré-requisito dos agentes fora de DEV (D1) |
| Afeta | README §2.3, §2.5, §3.1, §4.1, §4.4, §5.1 a §5.4, §6.2, §6.4, §6.5, §7.1, §7.4 a §7.7, §8.0 a §8.12, §9.2, §10 (padrões globais e tabelas 6, 12, 13, 15, 16 e a nova 17), §11, §12, §13, §14. AGENTS §3, §4, §7, §8. `docs/IMPLANTACAO.md`, `docs/AMBIENTE_DEV.md`, `docs/PADRAO_CRUD_ADMIN.md`. Prompts F7.0 a F9.2, UI_FREEZE e índice. Manual de homologação (v2.4) |
| Revoga | O aceite do README §14 "credencial legível pelo mesmo usuário" (premissa falsa: o script era o mesmo usuário). A heurística de ReDoS do §6.2. A frase do §7.1 "um horário inexistente executa uma vez". A regra "o startup check só olha tickets `RUNNING`" do §8.12 |
| Contrato | Nova tabela `tbsss_controle` (17ª). Colunas novas: `tbsss_agentes.config_criticos`, `tbsss_scripts.sha256_homologado`, `tbsss_tickets.arquivo_sha256`. Colunas ampliadas: `tbsss_agentes.hostname` (255), `tbsss_agentes.ambientes` (1000), `tbsss_tickets.process_id` (`NUMBER(10)`). Índices: único da ocorrência do agendamento, `tickets(script_id, created_at)` e `agendamentos(ativo, proxima_execucao, id)`. Motivo de pausa novo `ERRO_INTERNO`. Ação de auditoria nova `ESQUEMA_MIGRAR`. Transição nova `RUNNING → PENDING` (devolução). `Decisao` do `recurrence` ganha `ocorrencia`. Novas chaves de configuração (§12.1) |
| Depende de | CR-006 concluído. O F7 (Oracle) e o F8 (agente) ainda não foram executados: o que é do agente e do Oracle fica especificado aqui e nos prompts; o que já tem código (web, FAKE, configuração, `path_guard`, validação de parâmetros) é corrigido nos passos R1 a R5 |

---

## 1. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Usuário de execução separado | O script roda com um **usuário do sistema operacional por ambiente** (`[agent] usuarios_execucao`), diferente do usuário do agente e nunca root. O agente chama `sudo -n -u <usuário> /opt/sss/bin/sss-helper run`, um helper fixo, instalado pelo root, que recebe a especificação da execução pela entrada padrão e faz `execve` do script. Encerramento e limpeza também passam pelo helper (`term`, `kill`, `limpar`). Em DEV, o mesmo usuário continua permitido, com WARN |
| D1b | Segredos e contas por papel | O `secrets.cfg` de cada processo só tem o que ele usa: web (`[oracle] password` da conta web e `[web] cookie_key`), agente (`[oracle] password` da conta do agente, `[purge] password` e os `[ambiente:X]` de `ambientes_atendidos`). Quatro contas Oracle: dono do esquema (só DDL, no `init_db`), web, agente e purge. Nenhuma conta de aplicação altera ou apaga `tbsss_auditoria`; só a de purge apaga, e só por retenção. O `init_db` imprime os GRANTs de cada papel |
| D2 | Revalidação na execução | Na pré-validação do claim, o agente revalida o ambiente ativo e `rbac.pode_executar` do solicitante. Os ambientes atendidos são relidos a cada ciclo do orquestrador. `scheduled_at` vai no máximo a 366 dias no futuro |
| D3 | Relógio | Trava contra salto do relógio do banco: o agente compara o avanço do `SYSDATE` com o do relógio monotônico e, num salto, suspende a detecção de nó offline por `node_offline_timeout_s`, com WARN. Pré-requisito operacional: servidor de banco sem horário de verão (UTC recomendado) e NTP em modo *slew*. O §7.1 passa a descrever o comportamento real |
| D4 | Versão do esquema | Tabela `tbsss_controle` com `versao_esquema`; migrações numeradas em `scripts/migracoes/`; o `init_db` compara colunas, CKs e o estado das triggers e aborta em divergência; web e agente recusam subir com versão diferente da esperada (`sql_ident.VERSAO_ESQUEMA`) |
| D5 | Regex segura | `regex_validacao` só num subconjunto seguro (§6.2): sem grupo repetido por quantificador (exceto `?`), sem referência a grupo, sem lookaround, sem quantificador aninhado e com no máximo 2 quantificadores ilimitados |
| D6 | Quadro Registro | O ator só aparece pelo login para quem tem `VER_AUDITORIA` ou é administrador. Para os demais: "você" (o próprio usuário), "Sistema (…)" (atores do sistema) ou "outra pessoa" |

## 2. Regras (correção de cada achado)

As regras abaixo são normativas e estão detalhadas nas seções do README indicadas.

| # | Achado | Regra | README |
|---|---|---|---|
| R-01 | S-01 | **Estado local do agente.** Logo depois do spawn e **antes** do `registrar_pid`, o agente grava `work_dir/ticket_<id>/.sss_proc` (JSON: `ticket_id`, `pid`, `pgid`, `process_start`, `usuario_execucao`; escrita em arquivo temporário + `rename`, `0600`). Ao decidir o resultado, grava `.sss_result` (`status`, `status_motivo`, `return_code`) **antes** do `UPDATE` de finalização. O **startup check** varre **todos** os `work_dir/ticket_*`, seja qual for o status no banco: encerra o grupo quando a identidade confere (identidade desconhecida não recebe sinal: `ORPHAN_PROCESS` + WARN para intervenção), finaliza pelo `.sss_result` se houver, senão `ORPHAN_PROCESS` se o ticket ainda estiver `RUNNING` deste agente, e limpa as pastas. Tickets `RUNNING` deste agente sem pasta local seguem as regras de devolução (R-03) ou `ORPHAN_PROCESS` | §8.4, §8.7, §8.12 |
| R-02 | S-01 | **Grupo encerrado sempre.** Quando o processo principal termina (qualquer motivo), o agente encerra o grupo do ticket (ESRCH = já vazio) **antes** do flush final; havendo processos remanescentes, WARN `NETOS_ENCERRADOS`. Script que sai do grupo (`setsid`/double-fork) continua no aceite do §14, agora limitado ao usuário de execução | §8.7 |
| R-03 | S-03 | **Finalização garantida.** (a) O ticket entra no mapa local logo após o `COMMIT` do claim. (b) Qualquer exceção entre o claim e o spawn finaliza o ticket (`PRECHECK_FAILED` ou `SPAWN_ERROR`, -4); se a exceção for de banco antes do spawn, o ticket é **devolvido à fila** (`RUNNING → PENDING`, só com `process_id IS NULL` e sem `.sss_proc`). (c) Resultado decidido e `UPDATE` com erro de banco: estado local "finalização pendente" (`.sss_result` gravado), o ticket continua no heartbeat e o `UPDATE` é tentado de novo a cada ciclo rápido até `rowcount` 1 (feito) ou 0 (`OWNERSHIP_LOST`). (d) A varredura própria trata o caso inverso: ticket `RUNNING` deste agente no banco, fora do mapa e sem `.sss_proc`, é devolvido à fila (`process_id` nulo) ou finalizado `ORPHAN_PROCESS` (com PID) | §5.1, §8.3, §8.7 |
| R-04 | S-02 | **Orçamento de tempo do laço.** Nenhuma etapa bloqueia além de `call_timeout_ms` (toda chamada ao banco, inclusive a conexão: `tcp_connect_timeout` no Thin e `CONNECT_TIMEOUT`/`SQLNET.OUTBOUND_CONNECT_TIMEOUT` no Thick e no cx_Oracle). Reconexão é **uma tentativa por ciclo**, com o *backoff* contado em prazos monotônicos, nunca com `sleep`. O encerramento de processos é uma **máquina de estados não bloqueante** (SIGTERM, prazo `kill_grace_s`, SIGKILL, coleta), nunca espera dentro da chamada. O fence é verificado a cada iteração do laço e depois de cada chamada ao banco. Lotes de claim e de desdobro param ao gastar `heartbeat_interval_s / 2`. Em `DRAIN`, heartbeat, varredura, log pump e fence continuam. Invariantes novas (I3 e I4) no §8.9 | §2.3, §8.1, §8.9, §12.1 |
| R-05 | S-04 | **Avanço sem ticket.** SQL literal próprio, que só move `proxima_execucao` (`... AND ativo = 'S' AND proxima_execucao = :antiga_data`), sem mexer em `ultima_execucao`, `ultimo_ticket_id` nem `updated_*`; usado na sobreposição e no *misfire* `SKIP` sem conclusão. `ultimo_ticket_id` inexistente (purgado) ou terminal = livre | §7.5 |
| R-06 | S-05 | **D1/D1b** detalhados: helper `sss-helper` (subcomandos `run`, `term`, `kill`, `limpar`), regra de sudoers fixa, `exec_work_dir` por usuário de execução, log aberto pelo agente e entregue como stdout/stderr (o usuário de execução não abre o arquivo pelo caminho), segredos e contas por papel | §4.1, §8.0, §8.4, §8.6, §11.1, §12.1 |
| R-07 | S-06 | **Fila sem bloqueio na cabeça.** A seleção de candidatos exclui os pares (script, ambiente) já no teto (`NOT EXISTS`/contagem sobre `ix_tbsss_tck_scr`); o claim continua com a checagem definitiva. **Envelhecimento:** a cada `fila_envelhecimento_min` minutos na fila, a prioridade efetiva sobe 1 nível, até 1 (`0` desliga) | §5.3, §8.2 |
| R-08 | S-07 | **Desdobro paginado e sem disputa.** Leitura em páginas por chave (`proxima_execucao`, `id`) até a página vir incompleta ou o orçamento acabar; cada regra é travada com `FOR UPDATE SKIP LOCKED` (outro agente a está processando = pular). Falha inesperada numa regra: `ROLLBACK` e, numa transação separada, pausa com o motivo novo `ERRO_INTERNO` (auditada, WARN). Índice `ix_tbsss_agd_prox (ativo, proxima_execucao, id)` | §7.5, §10 tabela 12 |
| R-09 | S-08 | **D2** detalhada, com subcódigos `AMBIENTE_INATIVO` e `SEM_PERMISSAO` na linha `[SSS]` do log do ticket | §5.4, §8.4, §8.12 |
| R-10 | S-09 | **D3** detalhada; o §8.8 também exclui o próprio agente e só roda com o heartbeat do detector em dia | §7.1, §8.8, §14 |
| R-11 | S-10 | **`agent_id` único.** Registro sob `SELECT ... FOR UPDATE WAIT 5` na linha do agente; o heartbeat do agente filtra `hostname` e `pid_daemon` e checa o `rowcount` (0 = `REGISTRO_PERDIDO`: CRITICAL, encerramento `TERMINATE` e saída ≠ 0) | §8.7, §8.12 |
| R-12 | S-11 | **Lock preso e failover.** NODE_OFFLINE em duas etapas (`SELECT ... FOR UPDATE SKIP LOCKED` e `UPDATE` por id). Erro de *call timeout* (DPY-4024, DPI-1067, ORA-03156) mapeado: `ROLLBACK`, WARN e nova tentativa no ciclo seguinte. Lista de erros de reconexão ampliada para failover (ORA-01033, ORA-01034, ORA-01089, ORA-12514, ORA-12528, ORA-12537, ORA-00028, ORA-01012, ORA-02396, ORA-25408 e equivalentes `DPY-*`). Pool web com `ping_interval`. `SQLNET.EXPIRE_TIME` no servidor de banco e exemplos de DSN para RAC e Data Guard no `IMPLANTACAO.md` | §2.3, §8.8, AGENTS §4.10 |
| R-13 | S-12 | **D4** detalhada | §10, §11.1 |
| R-14 | S-13 | **Sem link simbólico:** `path_file` precisa ser igual ao `realpath` (`CAMINHO_COM_LINK`). Diretório inacessível vira `SEM_ACESSO`, distinto de `NAO_ENCONTRADO` | §8.5 |
| R-15 | S-14 | **Donos proibidos:** nenhum componente do caminho (arquivo e diretórios) pode pertencer ao UID do agente nem a um usuário de execução (o dono pode mudar o modo), além de `os.access(W_OK)` falso. O UID do agente e os usuários de execução não podem estar em `script_owner_uids`. O executável de cada interpretador passa pela mesma checagem de cadeia | §8.5, §8.12 |
| R-16 | S-15 | **D5** detalhada | §6.2 |
| R-17 | S-16 | **Locale e codificação.** Os launchers exportam `LANG`/`LC_ALL` (`SSS_LOCALE`, padrão `C.UTF-8`); web e agente abortam se `sys.getfilesystemencoding()` não for UTF-8; o agente valida `child_locale` na subida; qualquer exceção no spawn vira `SPAWN_ERROR`. As variáveis `PYTHON*` do §8.6 só valem para BASH/SH (o `-I` do PYTHON3 as ignora) | §8.4, §8.6, §8.12, §12.2 |
| R-18 | S-17 | **Monitoração e diagnóstico.** Linha `[SSS] <evento>: <código>` no `log_output` antes de toda finalização por pré-validação ou spawn (sem o caminho). CLI `scripts/saude.py` com saída no padrão Nagios. Tela de agentes com "Fila sem atendente", "Rodando sem PID" e "Configuração divergente". Códigos de saída do `purge.py` e do `init_db.py` definidos. Sem retentativa automática de tickets (declarado) | §5.2, §11, §13 |
| R-19 | S-18 | A pausa (desdobro e manual) exige `ativo = 'S'`; na web, `rowcount = 0` vira conflito | §7.5, §7.6 |
| R-20 | S-19 | `sensivel` nunca volta de `S` para `N` | §6.2 |
| R-21 | S-20 | **Purge com concessão no banco:** só um nó purga tickets e auditoria por vez, pela concessão (*lease*) em `tbsss_controle` (`purge_dono`, `purge_concessao_ate`); `logs_locais` roda em cada agente. Ator `SYSTEM:purge`; `purge` reservado como `agent_id`. O purge não apaga a pasta de log de ticket ainda `RUNNING` | §11.3 |
| R-22 | S-21 | `audit_retention_days` ≥ 365 e ≥ `ticket_retention_days`. Exportação opcional da auditoria antes do purge (`--exportar-auditoria`) | §11.3, §12.1 |
| R-23 | S-22 | **Configuração crítica igual em todos os nós:** o agente grava `config_criticos` (texto canônico com os tempos, a política de *misfire*, o horizonte e o envelhecimento) no registro; diverge de outro agente ativo = CRITICAL na subida e ERROR no ciclo; a tela de agentes mostra. `cron_horizon_days` ≥ 366. `CronErro` só no cálculo da próxima ocorrência gera o ticket da atual e depois pausa | §7.3, §7.5, §8.12, §12.1 |
| R-24 | S-23 | **Conteúdo do script homologado:** `tbsss_scripts.sha256_homologado` é gravado no cadastro quando o arquivo existe no nó web e o caminho ou o interpretador mudam, o script é reativado ou o admin marca "registrar o conteúdo atual". O agente calcula o sha256 na pré-validação: diferente do homologado = `PRECHECK_FAILED` (`ARQUIVO_ALTERADO`); sempre registra o valor em `tbsss_tickets.arquivo_sha256`. O agente também recusa snapshot cujo `path_file` ou `interpretador` diverge do cadastro atual (`CADASTRO_MUDOU`) | §6.5, §8.4, §8.5 |
| R-25 | S-24 | **Mascaramento por ticket:** o agente usa um mascarador por ticket (segredos globais mais os valores sensíveis do snapshot), aplicado ao log do ticket e às linhas de log da aplicação daquele ticket. Valor de parâmetro sensível tem no mínimo 4 caracteres. O arquivo local é escrito pelo próprio script e não é mascarado (declarado) | §6.2, §8.10, §14 |
| R-26 | S-25 | **Sobreposição visível:** WARN quando o ticket que bloqueia a regra passa do tempo máximo do script mais `node_offline_timeout_s`; lista e agenda indicam a regra que será pulada ou pausada; a retomada reavalia a causa (responsável, script, ambiente e parâmetros); o formulário mostra a última pausa; o `detalhe` do `AGD_PAUSAR` do desdobro traz o campo e o erro (sem valor sensível) | §7.5, §7.6, §7.7 |
| R-27 | S-26 | **Ocorrência coberta:** o ticket do desdobro grava `scheduled_at` = a ocorrência que ele cobre; índice único `ix_tbsss_tck_ocor` impede dois tickets para a mesma ocorrência | §7.4, §7.5, §10 tabela 13 |
| R-28 | S-27 | Releitura de `cancel_requested` logo antes do spawn (cancelado = finaliza `CANCELLED` sem rodar). Heartbeat do agente sempre, mesmo sem tickets; `ultimo_hb_ok` começa no fim da inicialização | §8.4, §8.7, §8.9 |
| R-29 | S-28 | **Volume:** `max_log_size_bytes` ≤ 64 MiB; cláusula LOB explícita para todos os CLOBs; `total` das listagens limitado a 10.001 (a tela mostra "mais de 10.000"); índice `tickets(script_id, created_at)`; sem coleta de estatísticas em tabela vazia, com a exigência do job de estatísticas no `IMPLANTACAO.md`; fórmula de dimensionamento | §10, §11.1, §12.1, AGENTS §4.12 |
| R-30 | S-29 | **D6** detalhada | §10 |
| R-31 | S-30 | `table_prefix` só minúsculas: `^[a-z][a-z0-9_]{0,7}$` | §9.1, §12.1 |
| R-32 | Baixos | `hostname` 255, `ambientes` 1000, `process_id` `NUMBER(10)`; lista de bloqueio do ambiente ampliada e chaves fixas recusadas no `env_passthrough`; limpeza do `work_dir` em todo encerramento; cota de disco e `nproc` por usuário de execução (operação); mensagem do cadastro de CRON com `data_fim`; conclusão sem ticket "sempre que `gerar_ticket = False` e `concluir = True`"; prioridade 1 rebaixada a 2 no desdobro quando o responsável deixou de ser admin; contradições C-02 a C-06 e B1 a B5 da auditoria | vários |

## 3. Riscos

| Risco | Mitigação |
|---|---|
| D1 exige `sudo` e usuários de execução nos agentes | Regra de sudoers fixa, helper com dono root e `0755`, validação na subida do agente (`sudo -n -l`), instruções no `IMPLANTACAO.md`; DEV continua com o mesmo usuário |
| Scripts do mesmo usuário de execução ainda se enxergam entre si | Um usuário de execução por ambiente; o aceite residual fica no §14 |
| Envelhecimento muda a ordem da fila | Configurável (`0` desliga) e documentado |
| Bloqueio por hash quando o arquivo muda legitimamente | O admin registra o novo conteúdo no cadastro (auditado); sem hash homologado (arquivo ausente no nó web) não há bloqueio, só o registro do hash executado |

## 4. Plano de execução

Cada passo: implementação, testes (3.6.0, 3.6.8 e 3.13.2), navegador quando houver tela, relatório AGENTS §9, commit e push.

| Passo | Escopo |
|---|---|
| P0 | Este documento, o relatório da auditoria, README, AGENTS, `IMPLANTACAO.md`, `AMBIENTE_DEV.md`, `PADRAO_CRUD_ADMIN.md`, prompts F7.0 a F9.2, UI_FREEZE e índice |
| R1 | Registro `sql_ident`: tabela 17 `tbsss_controle`, `VERSAO_ESQUEMA`, colunas e índices novos, motivo `ERRO_INTERNO`, tamanhos; testes de esquema |
| R2 | Configuração: `table_prefix`, atores reservados, invariantes I3 e I4, faixas novas, chaves novas, segredos por papel, ambiente do filho; launchers e checagem de UTF-8; testes |
| R3 | `path_guard` (links, `SEM_ACESSO`, donos proibidos, interpretador), regex segura, sensível monotônico, valor sensível mínimo, controle no snapshot; testes |
| R4 | Agendamentos, tickets e FAKE: pausa só ativa, retomada com reavaliação, agenda e lista com avisos, última pausa no formulário, `ocorrencia` no `recurrence`, mensagem do CRON, `scheduled_at` ≤ 366 dias, hash do script, índice da ocorrência, controle, total limitado; testes |
| R5 | Telas: quadro Registro com ator mascarado, painel de agentes com os três quadros novos, paginação "mais de 10.000"; testes e navegador |
| UF | Bateria completa, telas nas cinco larguras, manual v2.4 e git |
| FINAL | Nova auditoria rigorosa nas quatro frentes, sobre o estado final, com relatório |

## 5. Acompanhamento da execução

Em 2026-10-17, a retomada conferiu o histórico e as alterações locais:

| Passo | Evidência / situação |
|---|---|
| P0 e R1 | Commit `de8db2a` |
| R2 | Commit `76f1961` |
| R3 | Commit `c69c988` |
| R4 | Commit `0497e76`; relatório em `RELATORIO-CR-007-R4.md` |
| R5 | Commit `d1a262c`: ator mascarado (D6), quadros de diagnóstico dos agentes, "mais de 10.000"; relatório em `RELATORIO-CR-007-R5.md` |
| UF | Concluído: bateria nos três Pythons, 29 telas em cinco larguras, manual v2.4 (CT-24) e UI_FREEZE; relatório em `RELATORIO-CR-007-UF.md` |
| FINAL | Concluído: `AUDITORIA-2026-10-17-final-pos-CR-007.md`, veredito FAIL sem bloqueantes (6 altos, 19 médios, 11 baixos, novos ou resíduos); correção proposta como CR-008, a aprovar |

R4: 782 testes em cada Python 3.6.0, 3.6.8 e 3.13.2, com sucesso e 23 testes
Oracle ignorados por ausência de `SSS_TEST_DSN`. Chromium: quatro telas em
360, 390, 768, 1366 e 1920 px, sem rolagem horizontal ou erro JavaScript.
Oracle real permanece não testado; F7 e F8 continuam fora deste passo,
conforme a dependência e o plano acima. O CR completo ainda não está encerrado.

R5: 794 testes em cada Python 3.6.0, 3.6.8 e 3.13.2, com sucesso e 23 ignorados
(Oracle). Chromium: agentes (na carga e 65 s depois) e detalhe do ticket com
`op.prod` e `consulta`, em 360, 412, 768, 1024 e 1440 px, sem rolagem horizontal,
erro JavaScript ou violação de CSP. Correção na revisão: `config_criticos` do nó
web com `call` em segundos (README §8.12); o seed passou a exibir os três quadros.
