# CR-008: Correções da auditoria final pós-CR-007

| Campo | Valor |
|---|---|
| Status | **Aprovado** em 2026-10-17 pelo responsável pelo produto ("aprovo"), sobre a proposta da seção 3 de `AUDITORIA-2026-10-17-final-pos-CR-007.md`. Plano P0, R1, R2 e UF |
| Origem | Auditoria FINAL do CR-007 nas quatro frentes (commit `a6f6adf`): FAIL sem bloqueantes, com 6 altos (F-01 a F-06), 19 médios e 11 baixos |
| Restrições | Sem dependência nova de Python. Pilha mantida (Python 3.6+, web2py, Oracle 11gR2, Alpine CSP, somente POSIX). Sem objeto Oracle novo: o esquema continua na versão 1 (`sql_ident.VERSAO_ESQUEMA = 1`), porque nenhum banco foi criado ainda (F7 não executado); as mudanças de coluna entram direto na versão 1 |
| Afeta | README §2.3, §4.2, §4.3, §5.1, §5.3, §5.6, §6.2, §7.3 a §7.5, §8.1, §8.2, §8.4, §8.7 a §8.10, §8.12, §10 (tabelas 9 e 15), §11.1, §11.3, §12.1, §13, §14. AGENTS §3, §4. `docs/IMPLANTACAO.md` (§7.2, §18, §19), `docs/AMBIENTE_DEV.md`. Prompts F0.2, F7.1, F7.3, F8.0 a F8.4, F9.1, UI_FREEZE. Manual de homologação (v2.5) |
| Contrato | `tbsss_usuarios.sessao_epoch NUMBER(10) DEFAULT 0 NOT NULL` (nova); `tbsss_agentes.pid_daemon NUMBER(10)` (ampliada). Conta Oracle nova `sss_monitor` (só `SELECT`), papel `monitor` no `secrets.cfg`. Configuração nova: `[web] sessao_max_horas` (padrão 12), `[agent] ambientes_exigem_hash`, `[agent] log_dir_min_livre_mb` (padrão 1024). `cron_horizon_days` com mínimo 1461. Decisão de agendamento com a marca `cron_erro` |
| Depende de | CR-007 concluído. F7 e F8 ainda não executados: o que é do Oracle e do agente fica especificado aqui e nos prompts; o que tem código é corrigido em R1 e R2 |

---

## 1. Decisões

| # | Decisão | Resumo |
|---|---|---|
| E1 | Administrador só por administrador (F-05) | Só um administrador atribui o perfil de administrador a alguém, marca ou desmarca `is_admin` num perfil, altera a matriz do próprio perfil e redefine a senha de outro administrador. Quem tem `CAD_USUARIOS` ou `CAD_PERFIS` sem ser administrador recebe a mensagem-padrão de permissão |
| E2 | Sessão revogável (F-23) | `tbsss_usuarios.sessao_epoch` vai para a sessão no login e é comparado a cada requisição. Sair, trocar a própria senha, ter a senha redefinida, ser desativado ou mudar de perfil incrementam o valor e derrubam **todas** as sessões daquele usuário. Vida máxima da sessão: `[web] sessao_max_horas` (padrão 12), além da inatividade |
| E3 | Monitoração com conta própria (F-04) | `scripts/saude.py` usa a conta Oracle `sss_monitor`, só `SELECT` nas tabelas que consulta (agentes, tickets, agendamentos, scripts, controle e auditoria), e a seção `[monitor]` do `secrets.cfg` (papel `monitor`) |
| E4 | Hash homologado digitável (F-24) | Quando o arquivo não existe no nó web, o administrador informa o SHA-256 (64 hexadecimais) obtido com `sha256sum` no servidor do agente. Mudar o caminho limpa o hash, salvo se um novo for calculado ou informado. Ambientes de `[agent] ambientes_exigem_hash` recusam script sem hash (`PRECHECK_FAILED`, `SEM_HASH`) |
| E5 | Ator mascarado também fora do quadro Registro (F-35) | "solicitado por" (tickets) e "Responsável" (agendamentos) seguem a D6 do CR-007: login só para quem tem `VER_AUDITORIA` ou é administrador; para os demais, "você" ou "outra pessoa". Filtros por solicitante continuam aceitando o login digitado |

## 2. Regras (correção de cada achado)

R-xx corrige F-xx. As regras são normativas e estão detalhadas nas seções do README indicadas.

| # | Regra | README / alvo |
|---|---|---|
| R-01 | **Marcador de spawn.** Antes do `Popen`, o agente grava `work_dir/ticket_<id>/.sss_spawn` (JSON com `ticket_id`, `usuario_execucao` e o instante; temporário + `rename`, `0600`). Pasta com `.sss_spawn` e sem `.sss_proc` = "talvez iniciado": **nunca** devolve à fila; o agente chama `sss-helper encerrar-ticket <usuário> <ticket_id>` (encerra os processos do usuário de execução cujo diretório atual está em `exec_work_dir/<usuário>/ticket_<id>`; Linux por `/proc/<pid>/cwd`, outros Unix por `pwdx` quando houver; sem meio de identificar = WARN) e finaliza `ORPHAN_PROCESS`. Qualquer exceção depois do `Popen` (inclusive na gravação do `.sss_proc`) encerra o grupo de `p.pid` antes de finalizar `SPAWN_ERROR`. A devolução à fila exige: `process_id` nulo, sem `.sss_proc` **e** sem `.sss_spawn` | §5.1, §8.0, §8.4, §8.7, §8.12; F8.0, F8.3 |
| R-02 | **Devolução respeita o cancelamento.** `devolver` só com `cancel_requested = 'N'`; com `'S'`, finaliza `CANCELLED`/`CANCEL_USER`/`-1`. No §5.6, `PENDING` com `'S'` (resíduo) é cancelado direto pela web | §5.1, §5.6, §8.7, §8.12; F7.3, F8.3 |
| R-03 | **F8.4 alinhado.** O contrato de `reservar_e_criar_ticket` grava `scheduled_at = :ocorrencia` e a prioridade do passo 2 (rebaixada) | F8.4 |
| R-04 | **E3** detalhada: conta `sss_monitor`, GRANTs, papel `monitor` | §11.1, §12.1, §13; F7.1, F9.1; IMPLANTACAO §18.4 |
| R-05 | **E1** detalhada, com mensagens e auditoria da recusa | §4.3; código R1 |
| R-06 | **Regex: quantificador limitado largo conta como ilimitado.** `{m,n}` com `n − m > 10` entra no limite de 2 ilimitados; com algum ilimitado, no máximo 4 quantificadores que criam escolha (sem ilimitado, continuam 6). Pior caso aceito medido no P0: `\w*\w*` + 2 × `\w{0,10}` + `x` = 0,08 s com 500 caracteres; recusados: `\w*\w*` + 6 × `\w{0,10}` (23 s com 100) e `\w*` + 6 × `\w{0,10}` (5,4 s com 500). A promessa do §6.2 passa a ser "abaixo de 0,2 s no pior caso medido", no lugar de "no máximo quadrático" | §6.2; código R1 |
| R-07 | **Devolução só por erro de rede ou prazo.** Antes do spawn, só `eh_erro_rede`/`eh_tempo_esgotado` devolvem o ticket; qualquer outro erro de banco finaliza `PRECHECK_FAILED` com a linha `[SSS] ERRO_BANCO: <ORA-nnnnn>` | §8.4; F8.3 |
| R-08 | **Pendências locais com retentativa.** Estados "devolução pendente" e "PID pendente" no mapa local, refeitos a cada ciclo rápido; o ticket com PID pendente recebe heartbeat e entra no fencing normalmente | §8.7; F8.3 |
| R-09 | **Heartbeat medido no início.** `ultimo_hb_ok` recebe o instante monotônico capturado **antes** do primeiro `UPDATE` da transação de heartbeat e só é promovido no `COMMIT`; assim a I4 continua válida com várias chamadas | §8.8, §8.9; F8.3, F8.4 |
| R-10 | **Trava de relógio no detector.** A transação de `NODE_OFFLINE` lê o `SYSDATE` e confere o salto contra o monotônico antes do `UPDATE`; com salto, pula a detecção (WARN `SALTO_RELOGIO`) | §8.8; F8.4 |
| R-11 | **Orçamento do log pump.** Cada ciclo do pump gasta no máximo `heartbeat_interval_s / 2`, com rodízio entre tickets; o que sobra fica para o ciclo seguinte (o arquivo local é integral) | §8.1, §8.10; F8.2, F8.3 |
| R-12 | **Fencing respeita o resultado real.** Na recuperação do fencing, ticket com `.sss_result` é finalizado pelo resultado gravado; sem ele, `FENCED` | §8.9; F8.4 |
| R-13 | **`pid_daemon NUMBER(10)`**, como `process_id` | §10 tabela 15; `sql_ident`; código R2 |
| R-14 | **Normalização na conferência de esquema.** Antes de comparar: tirar aspas, maiúsculas, colapsar espaços e quebras, tirar espaço final do `DATA_DEFAULT`, ignorar CKs de sistema `SYS_C%` que só repetem NOT NULL; expressões de FBI comparadas pela forma de `ALL_IND_EXPRESSIONS` normalizada. Teste com `SSS_TEST_DSN` obrigatório no F7.1 | §11.1; F7.1 |
| R-15 | **Fila sem atendente pelo cadastro.** O critério é o mesmo do claim: `tbsss_scripts.interpretador` (join), sem ler `parametros_enviados`; usa as expressões de `ix_tbsss_tck_fila` e `ix_tbsss_tck_run` | §13; `repo_agentes`, FAKE, F7.3; código R2 |
| R-16 | **Purge sempre auditado.** Toda execução que obtém a concessão grava `PURGE` (uma linha por tabela, com a contagem, inclusive 0) | §4.4, §11.3; F9.1 |
| R-17 | **Conexão dentro do orçamento.** `CONNECT_TIMEOUT × (RETRY_COUNT + 1) × endereços ≤ call_timeout_s`; o agente confere no DSN descritor e avisa com WARN; exemplo do IMPLANTACAO corrigido | §2.3; F7.2; IMPLANTACAO §18.2 |
| R-18 | **Pós-restauração sem reexecução.** Antes de subir os agentes: pausar as regras com `SKIP` temporário, revisar e cancelar (`CANCEL_USER`, auditado) os `PENDING` e `RUNNING` sem PID criados antes do instante de restauração, avançar as sequences acima do maior id visto nos logs locais | IMPLANTACAO §18.4 |
| R-19 | **`CronErro` com decisão.** `avaliar_disparo` devolve a decisão normal com a marca `cron_erro = True` e `nova_data` nula quando a próxima ocorrência não existe no horizonte; o daemon aplica os passos 4 e 5 (sobreposição e SKIP) e grava a pausa `CRON_INVALIDO` com SQL literal | §7.4, §7.5; `recurrence`; F8.4; código R2 |
| R-20 | **Envelhecimento por `GREATEST(scheduled_at, created_at)`** | §5.3, §8.2; F8.3 |
| R-21 | **SKIP pela ocorrência mais recente.** O atraso é medido pela vencida mais recente; dentro da tolerância, gera o ticket dela (`ocorrencia` = mais recente), e as anteriores contam como perdidas | §7.4; `recurrence`; código R2 |
| R-22 | **`ERRO_INTERNO` só para falha persistente.** `DatabaseError` no desdobro: `ROLLBACK`, WARN e nova tentativa no ciclo seguinte; `ERRO_INTERNO` para exceção que não é de banco ou para 3 falhas seguidas da mesma regra (contador local) | §7.5; F8.4 |
| R-23 | **E2** detalhada | §4.2, §10 tabela 9; código R1 |
| R-24 | **E4** detalhada | §8.4, §8.5, §14; código R2 |
| R-25 | **Disco dos logs.** `log_dir` em partição própria (IMPLANTACAO); o agente não faz claim com espaço livre em `log_dir` abaixo de `[agent] log_dir_min_livre_mb` (WARN `DISCO_LOG`); o §14 deixa de citar a cota do usuário de execução como proteção do log | §8.2, §8.10, §14; F8.0, F8.3; IMPLANTACAO §18.1 |
| R-26 | **Textos alinhados:** §5.6 remete ao §8.7 (helper `term`/`kill`, R-02 do CR-007, `.sss_result`); F8.3 com `purge` reservado; startup check só remove a pasta depois de confirmar o grupo vazio | §5.6, §8.12; F8.3 |
| R-27 | **Liberação da concessão** zera `purge_dono` e `purge_concessao_ate` | §11.3; F9.1 |
| R-28 | **`table_prefix` só minúsculo** em `sql_ident.PADRAO_PREFIXO` e nos prompts | F0.2, F7.1; código R2 |
| R-29 | **`[oracle] user` diferente do owner** fora de DEV | §12.1; código R1 |
| R-30 | **Documentação de testes:** "skipped=23"; GRANT do agente em `tbsss_usuarios` mantido e declarado no §14 (hash PBKDF2), restrição por view fica como melhoria | IMPLANTACAO §7.2, §19; AMBIENTE_DEV; §14 |
| R-31 | **`OCORRENCIA_DUPLICADA` avança a regra** sem ticket, numa nova transação | §7.5; F8.4 |
| R-32 | **`cron_horizon_days` mínimo 1461** (cobre 29/02) | §7.3, §12.1; código R2 |
| R-33 | **Tradução única de motivos.** `rbac.motivo_pausa(motivo_rbac)`, função pura usada pela web e pelo daemon: `USUARIO_INATIVO`, `SCRIPT_INATIVO`, `AMBIENTE_INATIVO`; demais → `SEM_PERMISSAO` | §7.5; F8.4; código R2 |
| R-34 | **Custo da agenda:** melhoria registrada, sem mudança | — |
| R-35 | **E5** detalhada | §10 (D6); código R2 |
| R-36 | **Textos do helper e do `cwd`:** `limpar` recebe a `pasta_base` pelo argumento validado contra `exec_work_dir/<usuário>`; F8.1 com `cwd = exec_work_dir/<usuário>/ticket_<id>` | §8.0; F8.0, F8.1 |

## 3. Riscos

| Risco | Tratamento |
|---|---|
| `sessao_epoch` derruba todas as sessões do usuário ao sair | Comportamento declarado (§4.2): sair em um navegador encerra as outras sessões |
| Marcador `.sss_spawn` sem meio de achar o processo em Unix sem `/proc` nem `pwdx` | WARN e `ORPHAN_PROCESS`; o processo fica no aceite do §14, limitado ao usuário de execução |
| Hash digitado errado | Todo ticket falha com `ARQUIVO_ALTERADO` e a mensagem orienta conferir o hash; a homologação é auditada |

## 4. Plano

| Passo | Conteúdo |
|---|---|
| P0 | Este documento; README, AGENTS, IMPLANTACAO, AMBIENTE_DEV e prompts F0.2, F7.1, F7.2, F7.3, F8.0 a F8.4, F9.1, UI_FREEZE |
| R1 | Segurança: E1 (R-05), regex (R-06), E2 (R-23), `user` ≠ owner (R-29); testes e navegador |
| R2 | Dados e agendamento: R-13, R-15, R-19, R-21, R-24 (E4), R-28, R-32, R-33, R-35 (E5); testes e navegador |
| UF | Bateria nos três Pythons, telas nas cinco larguras, manual v2.5 |

## 5. Acompanhamento da execução

| Passo | Situação |
|---|---|
| P0 | Concluído: documentação aplicada (README, AGENTS, IMPLANTACAO, AMBIENTE_DEV, prompts F0.2, F7.1–F7.3, F8.0–F8.4, F9.1, índice e UI_FREEZE) |
| R1 | Concluído: E1, R-06, E2, R-29; relatório em `RELATORIO-CR-008-P0-R1-R2.md` |
| R2 | Concluído: R-13, R-15, R-19, R-21, E4/R-24, R-25 (configuração), R-28, R-32, R-33, E5; mesmo relatório e mesmo commit do R1 (as mudanças se cruzam nos mesmos arquivos) |
| UF | Próximo passo: manual v2.5 |
