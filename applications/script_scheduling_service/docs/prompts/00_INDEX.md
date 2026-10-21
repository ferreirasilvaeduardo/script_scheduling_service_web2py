# SSS — Plano de Execução UI-First (Antigravity)

## Como usar

1. **Regra permanente:** cadastre o conteúdo integral do `AGENTS.md` como regra do workspace no Antigravity. Assim ela vale em toda conversa.
2. **Uma conversa por prompt.** Use o modo **Planning** e revise o plano de implementação gerado **antes** de aprovar a execução.
3. **Cole o prompt inteiro.** Não resuma nem misture dois prompts na mesma conversa.
4. **Ao terminar cada prompt:**
   * confira o relatório (§9 do AGENTS);
   * rode os testes você mesmo;
   * faça o commit (`git commit -m "F<x>.<y> <título>"`);
   * só então abra o próximo prompt.
5. **Relatório com lacuna do README:** se ele apontar uma lacuna ("Observações / Anomalias"), **não prossiga**. Decida, atualize o README e reexecute o prompt.
6. **Convenção:** `APP` = `applications/script_scheduling_service`. Os testes rodam a partir de `APP`.

## Pré-requisitos (antes do F0.1)

| Item | Detalhe |
|---|---|
| Python 3.6 | **3.6.0 ou superior.** Mínima suportada: **3.6.0**. Referência de produção: **3.6.8**. Validado até a 3.13. Rode a suíte ao menos na 3.6.0 e na 3.6.8 (AGENTS §7.3). Em GCC ≥ 11 ou OpenSSL 3, siga a receita de `docs/AMBIENTE_DEV.md` §1.1 (patch bpo-27987 e OpenSSL 1.1.1w local). Em Apple Silicon, use um shell x86_64 (Rosetta) ou um container Linux x86_64 |
| web2py | Versão homologada, descompactada na raiz do repositório (`web2py.py` na raiz) |
| Bootstrap 5.3.8 | `bootstrap.min.css` e `bootstrap.bundle.min.js` copiados para `applications/script_scheduling_service/static/bootstrap/` |
| Alpine.js (build CSP) | Pacote `@alpinejs/csp`, arquivo minificado copiado para `applications/script_scheduling_service/static/js/alpine.min.js` |
| Git | Repositório inicializado, com `README.md` e `AGENTS.md` na raiz |

## Sequência

| # | Arquivo | Título | Depende de | Verificação principal |
|---|---|---|---|---|
| 0.1 | `F0_1_ambiente_esqueleto.md` | Ambiente e esqueleto do repositório | — | `scripts/check_env.py` |
| 0.2 | `F0_2_config_logging.md` | Configuração tipada, logging e launchers | 0.1 | `test_config.py` |
| 0.3 | `F0_3_registro_identificadores.md` | Registro de identificadores e testes de schema/compatibilidade | 0.2 | `test_db_schema.py`, `test_py36_compat.py` |
| 0.4 | `F0_4_contratos_repo_fake.md` | Contratos de repositório e backend FAKE | 0.3 | `test_repo_contract.py` |
| 1.1 | `F1_1_layout_shell.md` | Layout base, design tokens e navegação | 0.4 | Browser: CSP sem violação |
| 1.2 | `F1_2_componentes_ui.md` | Biblioteca de componentes | 1.1 | `/dev/componentes` |
| 2.1 | `F2_1_seguranca_base.md` | Hash, CSRF, Origin, sessão, cabeçalhos e mascaramento | 1.2 | `test_security.py`, `test_masking.py` |
| 2.2 | `F2_2_login_rbac.md` | Login, bloqueio, guardas e RBAC | 2.1 | `test_rbac.py`, `test_auth_service.py` |
| 3.1 | `F3_1_params_path_guard.md` | Compilador de parâmetros e path_guard | 2.2 | `test_params_compiler.py`, `test_path_guard.py` |
| 3.2 | `F3_2_tela_disparo.md` | Tela de disparo de script | 3.1 | Browser |
| 3.3 | `F3_3_tickets_lista_detalhe.md` | Tickets: lista, detalhe, cancelamento, reexecução | 3.2 | `test_ticket_service.py` + browser |
| 3.4 | `F3_4_visualizador_log.md` | Visualizador de log com polling | 3.3 | Browser |
| 4.1 | `F4_1_admin_ambientes.md` | Gestão de ambientes | 3.4 | Browser |
| 4.2 | `F4_2_admin_perfis.md` | Perfis e matriz de permissões | 4.1 | `test_rbac.py` ampliado |
| 4.3 | `F4_3_admin_usuarios.md` | Gestão de usuários | 4.2 | Browser |
| 4.4 | `F4_4_admin_parametros.md` | Dicionário de parâmetros | 4.3 | `test_params_compiler.py` ampliado |
| 4.5 | `F4_5_admin_scripts.md` | Gestão de scripts e homologação | 4.4 | Browser + `test_path_guard.py` |
| 5.1 | `F5_1_cron_recorrencia.md` | Parser CRON e recorrência | 4.5 | `test_cron_parser.py`, `test_recurrence.py` |
| 5.2 | `F5_2_tela_agendamentos.md` | Tela de agendamentos | 5.1 | Browser |
| 6.1 | `F6_1_auditoria_agentes.md` | Auditoria e painel de agentes | 5.2 | Browser |
| ◆ | `UI_FREEZE.md` | **Homologação visual e funcional (manual)** | 6.1 | Seu aceite |
| 7.0 | `F7_0_driver_adaptativo.md` | Driver adaptativo Thin → Thick → cx_Oracle (CR-002) | ◆ | `test_db_conn.py` |
| 7.1 | `F7_1_init_db.md` | Bootstrap de DDL Oracle 11gR2 (`init_db.py`) | 7.0 | `test_db_schema.py` + `--dry-run` |
| 7.2 | `F7_2_db_conn.md` | Conexão Oracle (`db_conn`: pool, transação, erros, reconexão) | 7.1 | `test_db_conn.py` |
| 7.3 | `F7_3_repo_oracle.md` | Repositórios Oracle 11gR2 (**executar 1x por agregado**) | 7.2 | teste Oracle progressivo do agregado + `test_sql_oracle11g.py`; contrato Oracle integrado após o quinto agregado |
| 8.0 | `F8_0_plataforma.md` | Camada de plataforma POSIX (Linux/Unix, CR-005) e helper de execução (CR-007) | 7.3 | `test_plataforma.py`, `test_sss_helper.py`, `test_py36_compat.py` |
| 8.1 | `F8_1_env_executor.md` | Ambiente do filho e executor | 8.0 | `test_env_builder.py`, `test_executor.py` |
| 8.2 | `F8_2_log_pump.md` | Coleta idempotente de log para CLOB | 8.1 | `test_log_pump.py` |
| 8.3 | `F8_3_daemon_claim.md` | Daemon: inicialização, claim, heartbeat, cancelamento | 8.2 | `test_scheduler_claim.py` |
| 8.4 | `F8_4_daemon_desdobro_fencing.md` | Daemon: desdobro, NODE_OFFLINE, fencing, shutdown | 8.3 | `test_scheduler_ha.py` |
| 9.1 | `F9_1_purge_hardening.md` | Purge, saúde, launchers Linux/Unix, pacote e runbook | 8.4 | `test_purge.py`, `test_saude.py`, `test_empacotar.py` + revisão |
| 9.2 | `F9_2_e2e.md` | Roteiro E2E com agentes Linux/Unix | 9.1 | Execução assistida |

> **F7.3 é executado uma vez por agregado:** `RBAC_USUARIOS`, `CATALOGO`, `TICKETS`, `AGENDAMENTOS`, `AUDITORIA_AGENTES`. São 31 arquivos de prompt e **35 sessões** do Antigravity (o F7.3 conta 5 vezes), mais o marco manual de UI Freeze.

> **A partir do F7, dados reais:** aplicação e validações usam as tabelas do owner e do prefixo do `instance/config.ini`; o FAKE fica só como dublê dos testes automáticos sem banco. Os testes de banco ligam com uma chave só, `SSS_TEST_ORACLE=1` (README §2.5). Desde o fim do F7.3 (5º agregado), a aplicação usa sempre o Oracle: `[app] data_backend` foi removida e é recusada se aparecer; DEV e PROD se separam pelo owner e pelo prefixo.

> Em cada execução do F7.3, rode somente a classe Oracle do agregado selecionado em `test_repo_oracle_progressive.py`; a bateria integrada `test_repo_contract.py` contra Oracle é gate depois da quinta execução. A suíte FAKE continua sendo gate em todas as fases.

> **Prompts já executados são histórico.** Eles refletem o README da época em que rodaram. Mudanças posteriores de arquitetura (CR-001: interpretador lógico, com a parte Windows revogada pelo CR-005; CR-002: Oracle único e driver adaptativo; CR-003: correções da análise funcional pós-F6.1, passos P0–P11 e P6A; CR-004: telas de consulta e linguagem clara, passos U1–U8 e o fechamento UF (testes completos e atualização de `docs/homologacao/`), todos a executar antes do UI Freeze; CR-005: somente POSIX, caminho absoluto livre do script e pastas de log por minuto, passos R0–R5 e UF, também antes do UI Freeze; CR-006: colunas de registro (`created_*`/`updated_*`) e quadro Registro, passos C0, P0, R1–R4 e UF, também antes do UI Freeze; CR-007: robustez do scheduler (usuário de execução por ambiente, estado local do agente, orçamento de tempo do laço, versão do esquema, fila e desdobro sem bloqueio, regex segura e os demais achados da auditoria de 2026-10-17), passos P0, R1–R5 e UF, também antes do UI Freeze; CR-008: correções da auditoria final pós-CR-007 (administrador só por administrador, sessão revogável por `sessao_epoch`, conta de monitoração, hash homologado informado, ator mascarado também no solicitante e no responsável, regex com quantificadores limitados largos contados como ilimitados, marcador `.sss_spawn`, devolução que respeita o cancelamento e os demais achados F-01 a F-36), passos P0, R1, R2 e UF, também antes do UI Freeze; CR-009: pasta do ambiente no topo do caminho do log (`interno` sem ambiente), aplicado ao fim do F8.2; CR-010: dados da execução, do ambiente, do script, do log e do agente em variáveis `SSS_*` para o script; CR-011: script por link simbólico, sem hash nem conferência de dono, com o nó web conferindo só o formato e o agente só o arquivo real; CR-012: pasta de saída por ticket (`SSS_SAIDA_DIR`), com o zip gravado no banco e baixado pelo detalhe do ticket; CR-013: volume da fila com 1 milhão de tickets pendentes (registrado, a executar depois do CR-012 e antes do F8.3d); CR-014: pasta de entrada permanente por ambiente e script (`SSS_ENTRADA_DIR`); CR-015a: nomes em inglês das variáveis `SSS_*` do script e das chaves de pasta do `config.ini` (`SSS_OUTPUT_DIR`, `SSS_INPUT_DIR`, `output_dir`, `input_dir`…); todos em `docs/arquitetura/`) prevalecem e já estão no README, no AGENTS e nos prompts ainda não executados. Exemplo: o F3.1 e o F4.5 citam `comando_real` e caminhos Linux, substituídos pelo interpretador lógico no commit `c904ca3`; o F4.5 também esconde o caminho de quem não é admin, regra (R-f) revogada pela D8 do CR-005, que mostra o caminho completo a todos.

## Regras de ouro para o executor

* O README é a autoridade de negócio. Diante de qualquer lacuna, o executor **para e pergunta**, nunca inventa.
* Nada fora do escopo IN do prompt. Melhorias percebidas vão para "Observações".
* A UI nunca é a única barreira: toda validação existe também no servidor.
