# Auditoria FINAL do scheduler contra o README (2026-10-17, pós-CR-007)

| Campo | Valor |
|---|---|
| Escopo | README, AGENTS, IMPLANTACAO, prompts F7.0 a F9.2 e o código existente no commit `aeb2b2e` (web, FAKE, `sql_ident`, `sss_config`, `path_guard`, `params_compiler`, `recurrence`, `cron_parser`, serviços e views) |
| Método | As mesmas quatro frentes independentes da auditoria anterior (`AUDITORIA-2026-10-17-scheduler.md`), somente leitura: (1) ciclo de vida do ticket e motor; (2) agendamentos e desdobro; (3) dados, Oracle e operação; (4) segurança da cadeia pedido → snapshot → execução. Achados repetidos entre frentes foram unificados. Coluna "Conferido": **C** = reconferido na consolidação (código executado ou texto lido); **F** = conferido pela frente, com a evidência citada |
| Verificações executadas | 3.000 expressões CRON aleatórias contra força bruta minuto a minuto e 400 regras DIARIA/SEMANAL/MENSAL, sem divergência; `sql_ident` × README §10 nas 17 tabelas, sem divergência (exceto F-13); CSRF, CSP, cabeçalhos, escape e bypass por URL sem achado |
| Veredito | **FAIL**: nenhum bloqueante, mas 6 altos (2 deles no código já entregue), 19 médios e 11 baixos. Os 30 achados da auditoria anterior (S-01 a S-30) estão tratados pelo CR-007; os itens abaixo são novos ou resíduos |
| Correção | Proposta de CR-008 (seção 3), a aprovar pelo responsável pelo produto |

## 1. Achados

### Altos

| # | Achado | Evidência | Conferido | Cenário de falha |
|---|---|---|---|---|
| F-01 | Janela entre o `Popen` e a gravação do `.sss_proc`: "sem `.sss_proc`" é tratado como "nunca iniciado" | README §8.4 passos 4–5, §8.7 (R-03), §8.12 passo 9; F8.3 | F | O agente morre logo após o spawn; o ticket fica `RUNNING` sem PID e sem `.sss_proc`, é devolvido à fila e o script roda duas vezes |
| F-02 | Devolução à fila ignora `cancel_requested = 'S'` | README §5.1, §8.7 (l. 1607), §8.12 (l. 1749); claim exige `'N'` (§8.2, §8.3); FAKE `repo_fake/tickets.py:283` cancelaria | C | Ticket cancelado durante a queda do agente volta `PENDING` com `'S'`: nunca é reservado nem cancelado; se veio de regra, a proteção de sobreposição trava a regra para sempre |
| F-03 | F8.4 se contradiz: o contrato de `reservar_e_criar_ticket` grava `scheduled_at = SYSDATE` e a prioridade da regra | F8_4 l. 20 × l. 40, README §7.5 passo 6, R-27 | F (duas frentes) | Implementação pelo contrato anula o `ix_tbsss_tck_ocor` (duplicatas passam) e não rebaixa a prioridade 1 |
| F-04 | `health.py` usa a conta do agente, que não tem `SELECT` em `tbsss_auditoria` | F9_1 l. 24; README §11.1 (GRANTs), §13 (checagem de `PURGE` em 2 dias) | F | ORA-00942/01031 em toda execução; o monitor sai com 3 (desconhecido) e mascara os demais alertas |
| F-05 | Quem tem `CAD_USUARIOS` ou `CAD_PERFIS` sem ser admin vira administrador | `admin_usuarios_service.py:226` (só barra o admin de rebaixar a si), `:276-291` (redefine senha de admin); `admin_perfis_service.py` (`is_admin` vindo do formulário) | C | Um perfil "Suporte" redefine a senha de um admin ou se move para o perfil ADMINISTRADOR: prioridade 1, todos os scripts e o cadastro de regex |
| F-06 | A regex "segura" (D5) não limita quantificadores `{m,n}` largos | `params_compiler.py:191-197` (até 6 `{m,n}`) | C: `\w{0,100}` ×5 + `x` aceita; `fullmatch` de 200 caracteres = 8,6 s (Python 3.6.8) | `tickets/previa` repetido prende workers web; no desdobro (agente single-thread) trava o laço, para o heartbeat e provoca fencing. Reabre a S-15 |

### Médios

| # | Achado | Evidência | Conferido |
|---|---|---|---|
| F-07 | "Erro de banco antes do spawn → devolver" sem restrição no F8.3: GRANT faltando ou lock persistente devolve o ticket a cada ciclo, sem estado final | README §8.4 l. 1445 × F8.3 | F |
| F-08 | Devolução que falha e `registrar_pid` com erro de banco não têm retentativa: o ticket recebe heartbeat para sempre, `RUNNING` sem PID | README §8.4 passo 5, §8.7 | F |
| F-09 | I4 soma um único `call_timeout_s`, mas a transação de heartbeat tem até 4 chamadas e `ultimo_hb_ok` só é marcado no `COMMIT` | README §8.9 l. 1653/1665; `sss_config.py:504` | F |
| F-10 | A trava de salto de relógio (D3) só é medida no heartbeat; o detector de `NODE_OFFLINE` pode rodar antes | README §8.8 l. 1647; F8.4 l. 133 | F |
| F-11 | Log pump sem orçamento de tempo (1 MiB por ticket, `COMMIT` por bloco, até 999 jobs): fencing falso | README §8.1 (R-04 só limita claim e desdobro), §8.10; F8.2 | F |
| F-12 | A recuperação do fencing grava `FENCED` mesmo com `.sss_result` presente: resultado real perdido e reexecução de job não idempotente | F8.4 l. 137; README §8.9 l. 1660 | F |
| F-13 | `tbsss_agentes.pid_daemon NUMBER(8)` não foi ampliado como `process_id` (R-32): ORA-01438 em HP-UX/AIX | `sql_ident.py:608`; README l. 2175 | F |
| F-14 | Conferência de esquema do `init_db` sem regra de normalização (`ALL_IND_EXPRESSIONS`, `DATA_DEFAULT`, CKs `SYS_C` de NOT NULL): divergência sempre | README §11.1; F7_1 l. 154 | F |
| F-15 | "Fila sem atendente" usa o interpretador do snapshot (CLOB) enquanto o claim usa `tbsss_scripts.interpretador`: falso positivo/negativo e leitura de N CLOBs por atualização | `repo_agentes.py:16-23`; `repo_fake/agentes.py`; README §8.2; F7_3 l. 38 | C (código do R5) |
| F-16 | Não está definido se o purge audita `PURGE` quando apaga 0 linhas: o monitor alerta todo dia nos primeiros 180 dias | README §4.4 l. 571; F9_1 l. 20 | F |
| F-17 | O exemplo de DSN do IMPLANTACAO (`CONNECT_TIMEOUT=10`, `RETRY_COUNT=3`, vários endereços) passa do `call_timeout_ms`; falta a fórmula | IMPLANTACAO §18.2; README §2.3 | F |
| F-18 | Procedimento pós-restauração não trata `PENDING` já executados depois do backup, ocorrências já cumpridas nem sequences | IMPLANTACAO §18.4 | F |
| F-19 | `CronErro` no desdobro sem SQL e sem os passos 4–5 (sobreposição e SKIP): ticket concorrente ou atrasado | `recurrence.py:220/269`; README §7.4 l. 1119, §7.5 passo 3 | F |
| F-20 | Envelhecimento da fila conta a partir de `scheduled_at`, que a R-27 deixa no passado: ticket de regra atrasada passa à frente da prioridade 1 | README §5.3 l. 698, §8.2 | F |
| F-21 | SKIP mede o atraso pela vencida mais antiga e descarta a mais recente, ainda dentro da tolerância | `recurrence.py:260`; README §7.4 | F (executado) |
| F-22 | `ERRO_INTERNO` pausa a regra também em erro transitório de banco (tablespace, ORA-00060, ORA-04068) | README §7.5 passo 8, R-08 | F |
| F-23 | Sessão em cookie não é invalidada por troca de senha, redefinição nem logout, e não tem vida máxima | `auth_service.revalidar`; README §4.2 | F |
| F-24 | `sha256_homologado` nunca é gravado quando o arquivo não está no nó web; trocar o caminho para um arquivo ausente mantém o hash antigo (todo ticket falha com `ARQUIVO_ALTERADO`) | `admin_scripts_service.py:293-299/358-365`; README §8.5, §14 | F |
| F-25 | A cota do usuário de execução não protege o `log_dir`: o arquivo de log pertence ao agente | README §8.4 passo 3, §8.10, §14; IMPLANTACAO §18.1; F8_0 | F |

### Baixos

| # | Achado | Evidência |
|---|---|---|
| F-26 | §5.6 ainda manda `Popen.wait()` e `SIGTERM` direto ao grupo (contra AGENTS §3.2, R-04 e D1); F8.3 lista só `init_db` e `seed` como reservados (falta `purge`); startup check remove a pasta antes de confirmar a morte do grupo | README §5.6 l. 805, §8.12; F8.3 l. 32 |
| F-27 | Liberação da concessão do purge zera só o dono: outro nó espera até 1 h | README §11.3 l. 527 |
| F-28 | Regex de `table_prefix` aceita maiúsculas nos prompts e em `sql_ident.PADRAO_PREFIXO` (o runtime recusa) | F7_1 l. 160, F0_2 l. 21, `sql_ident.py:15` |
| F-29 | `[oracle] user` igual ao owner não é recusado (anula a D1b) | `sss_config.py:546` |
| F-30 | Papel agente com `SELECT` em `tbsss_usuarios.senha_hash`; IMPLANTACAO §7.2/§19 e AMBIENTE_DEV ainda citam `skipped=18` (atual: 23) | README §11.1; `AMBIENTE_DEV.md:165` |
| F-31 | `OCORRENCIA_DUPLICADA` só faz `ROLLBACK`: a regra é reprocessada a cada ciclo até a próxima ocorrência | README §7.5 passo 6 l. 1169 |
| F-32 | `cron_horizon_days = 366` aceito quebra regras de 29/02 (pausa `CRON_INVALIDO` sem retomada) | `sss_config.py:140` |
| F-33 | Tradução dos motivos de `rbac.pode_executar` para `pausa_motivo` não especificada para o daemon | `rbac.py:88-117`; README §7.5 passo 2 |
| F-34 | Agenda de 7 dias com custo por regra alto (checagem de pausa e até 5.020 cálculos) | `agendamentos_service.py:544-583` |
| F-35 | A D6 promete que o login de terceiros nunca vai ao HTML, mas "solicitado por" e "Responsável" continuam visíveis | `views/tickets/detalhe.html:31`, `tickets/lista.load:57`, `agendamentos/lista.html:66`, `form.html:15/98`; README §10 |
| F-36 | `sss-helper limpar` sem origem da `pasta_base`; F8_1 ainda diz `cwd = work_dir/ticket_<id>` (D1: `exec_work_dir/<usuário>/ticket_<id>`) | README §8.0; F8_0; F8_1 |

## 2. Conferido como OK

* **Frente 1:** R-02, R-09, R-11, R-12, R-17, R-18, R-23 (código de `config_criticos`), R-24 (pré-validação), R-25, R-28; invariantes I1–I4 em `sss_config.py` iguais ao README.
* **Frente 2:** recorrência e CRON corretos (força bruta); R-05, R-08, R-19, R-26, R-27 literais no README e cumpridos pela web e pelo FAKE; D2 (`scheduled_at` ≤ 366 dias); D3 (datas *naive*); limite de 10.000 perdidas.
* **Frente 3:** `sql_ident` × README §10 nas 17 tabelas; R-12, R-13/D4, R-21, R-22, R-27, R-29, R-31 (runtime), R-32 (exceto F-13); GRANTs suficientes para web, purge e agente (exceto F-04); os dois `AGENTS.md` idênticos.
* **Frente 4:** CSRF e Origin/Referer; bypass por URL (`.json`/`.xml` 404, `.load` com o mesmo guarda); cabeçalhos HTTP; CSP e escape (sem inline, CDN ou `XML()`); sessão e cookie; RBAC de execução revalidado; compilação e snapshot (sigiloso ≥ 4, flags, caracteres de controle, mascaramento); `path_guard`; D1/D1b; ambiente do filho; CSV com neutralização de fórmula.

## 3. Proposta de correção (CR-008, a aprovar)

| Passo | Conteúdo | Achados |
|---|---|---|
| P0 | Documentação: README §5.1/§5.6/§7.4/§7.5/§8.1/§8.4/§8.7/§8.8/§8.9/§8.12/§11.1/§11.3/§13/§14, AGENTS, IMPLANTACAO §18 e prompts F7.1, F7.3, F8.0–F8.4, F9.1 | F-01–F-04, F-07–F-14, F-16–F-20, F-22, F-25–F-28, F-30, F-31, F-33, F-36 |
| R1 | Código, segurança: só admin atribui perfil admin, altera `is_admin`/matriz do próprio perfil e redefine senha de admin; `{m,n}` com amplitude > 10 conta como ilimitado; sessão com época invalidada por senha/logout e vida máxima; `user` ≠ owner fora de DEV | F-05, F-06, F-23, F-29 |
| R2 | Código, dados e agendamento: `pid_daemon NUMBER(10)`; fila sem atendente pelo cadastro e sem CLOB; SKIP pela vencida mais recente; `cron_horizon_days` mínimo 1461; hash limpo ao mudar o caminho e homologação pelo agente; decisão sobre a D6 para solicitante e responsável | F-13, F-15, F-21, F-24, F-32, F-35 |
| UF | Bateria, telas, manual v2.5 | — |

Itens F-34 (custo da agenda) e a restrição de GRANT por coluna (F-30) ficam como melhoria, sem bloqueio.
