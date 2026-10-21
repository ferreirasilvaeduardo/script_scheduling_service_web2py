# CR-016c1: Nomes de arquivos e pastas em inglês

| Campo | Valor |
|---|---|
| Status | **Concluído** em 2026-10-21. Aprovado pelo responsável pelo produto, inclusive a renomeação dos CRs e prompts históricos |
| Origem | Regra do README §2.8 (CR-016): nome técnico em inglês, também para arquivos e pastas |
| Restrições | Sem dependência nova. Python 3.6. Sem mudança de esquema. Nenhum módulo pode esconder um da biblioteca padrão |
| Afeta | `modules/`, `scripts/` (inclusive testes e `migrations/`), `docs/`, `dev/homologation/`, imports e referências em código, views e documentos, `.gitignore` |
| Fases seguintes | CR-016c2 (identificadores: funções, classes, variáveis, chaves lógicas das entidades e chaves de log), CR-016d (web), CR-016e (pasta de trabalho) |

---

## 1. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | `os_platform`, não `platform` | `modules/` vem antes da biblioteca padrão no `sys.path`: um pacote `platform` esconderia o módulo padrão usado pelo web2py e pelo driver |
| D2 | Só o nome do arquivo | Funções, classes e variáveis (inclusive aliases de import como `as servico`) ficam para o CR-016c2; controllers, views, assets e URLs para o CR-016d |
| D3 | Dados ficam | `dev/scripts/**` (scripts de demonstração cujo caminho o seed grava no banco) e o conteúdo dos documentos não mudam |
| D4 | Histórico | CRs e prompts executados mudam de nome (decisão do responsável pelo produto); o texto deles mantém os nomes de código da época |

## 2. Módulos

| Antes | Depois |
|---|---|
| `admin_ambientes_service` | `admin_environments_service` |
| `admin_parametros_service` | `admin_parameters_service` |
| `admin_perfis_service` | `admin_profiles_service` |
| `admin_usuarios_service` | `admin_users_service` |
| `agendamentos_service` | `schedules_service` |
| `agentes_service` | `agents_service` |
| `auditoria_service` | `audit_service` |
| `permissoes_service` | `permissions_service` |
| `desdobro` | `schedule_expansion` |
| `fase_saida` | `output_phase` |
| `pastas_log` | `log_paths` |
| `plataforma` | `os_platform` |
| `repo_agendamentos` | `repo_schedules` |
| `repo_agentes` | `repo_agents` |
| `repo_auditoria` | `repo_audit` |
| `repo_catalogo` | `repo_catalog` |
| `repo_usuarios` | `repo_users` |
| `_saida_memoria` | `_output_memory` |
| `migracoes` | `migrations` |
| `repo_oracle/agendamentos.py` e `repo_fake/agendamentos.py` (se existir) | `schedules.py` |
| `repo_oracle/agentes.py` e `repo_fake/agentes.py` (se existir) | `agents.py` |
| `repo_oracle/auditoria.py` e `repo_fake/auditoria.py` (se existir) | `audit.py` |
| `repo_oracle/catalogo.py` e `repo_fake/catalogo.py` (se existir) | `catalog.py` |
| `repo_oracle/usuarios.py` e `repo_fake/usuarios.py` (se existir) | `users.py` |
| `repo_oracle/saude.py` e `repo_fake/saude.py` (se existir) | `health.py` |
| `repo_oracle/scheduler_agenda.py` e `repo_fake/scheduler_agenda.py` (se existir) | `scheduler_schedules.py` |
| `repo_oracle/scheduler_fila.py` e `repo_fake/scheduler_fila.py` (se existir) | `scheduler_queue.py` |
| `repo_oracle/scheduler_saida.py` e `repo_fake/scheduler_saida.py` (se existir) | `scheduler_output.py` |

## 3. Testes

| Antes | Depois |
|---|---|
| `test_admin_ambientes_service.py` | `test_admin_environments_service.py` |
| `test_admin_parametros_service.py` | `test_admin_parameters_service.py` |
| `test_admin_perfis_service.py` | `test_admin_profiles_service.py` |
| `test_admin_usuarios_service.py` | `test_admin_users_service.py` |
| `test_agendamentos_service.py` | `test_schedules_service.py` |
| `test_auditoria_service.py` | `test_audit_service.py` |
| `test_catalogo_service.py` | `test_catalog_service.py` |
| `test_fase_saida.py` | `test_output_phase.py` |
| `test_pastas_log.py` | `test_log_paths.py` |
| `test_permissoes_service.py` | `test_permissions_service.py` |
| `test_plataforma.py` | `test_platform.py` |
| `test_scheduler_agenda.py` | `test_scheduler_schedules.py` |
| `test_scheduler_fila.py` | `test_scheduler_queue.py` |
| `test_scheduler_saida.py` | `test_scheduler_output.py` |
| `test_concorrencia_agentes.py` | `test_agents_concurrency.py` |
| `test_ha_agentes_reais.py` | `test_ha_real_agents.py` |
| `test_contraste_cores.py` | `test_color_contrast.py` |
| `test_implantacao_doc.py` | `test_deployment_doc.py` |
| `test_registro_cr006.py` | `test_record_cr006.py` |

## 4. Documentos e pastas

| Antes | Depois |
|---|---|
| `docs/IMPLANTACAO.md` | `docs/DEPLOYMENT.md` |
| `docs/AMBIENTE_DEV.md` | `docs/DEV_ENVIRONMENT.md` |
| `docs/PADRAO_CRUD_ADMIN.md` | `docs/ADMIN_CRUD_PATTERN.md` |
| `docs/SCRIPTS_UTILITARIOS.md` | `docs/UTILITY_SCRIPTS.md` |
| `docs/explain/AGENDAMENTOS.md` | `docs/explain/SCHEDULES.md` |
| `docs/explain/AUDITORIA_AGENTES.md` | `docs/explain/AUDIT_AGENTS.md` |
| `docs/explain/CATALOGO.md` | `docs/explain/CATALOG.md` |
| `docs/explain/RBAC_USUARIOS.md` | `docs/explain/RBAC_USERS.md` |
| `docs/sss_pacotes/ATUALIZAR-17950fb.txt` | `docs/sss_packages/UPDATE-17950fb.txt` |
| `docs/homologacao/SSS_Manual_Homologacao_UI_Freeze.docx` | `docs/homologation/SSS_Homologation_Manual_UI_Freeze.docx` |
| `docs/homologacao/SSS_UI_FREEZE_EVIDENCIAS_2026-10-18.md` | `docs/homologation/SSS_UI_FREEZE_EVIDENCE_2026-10-18.md` |
| `dev/homologacao/LEIA-ME.md` | `dev/homologation/README.md` |
| `docs/arquitetura` | `docs/architecture` |
| `docs/homologacao` | `docs/homologation` |
| `docs/sss_pacotes` | `docs/sss_packages` |
| `docs/sss_dev_scripts_exemplos` | `docs/sss_dev_script_examples` |
| `dev/homologacao` | `dev/homologation` |
| `dev/homologation/ferramentas` | `dev/homologation/tools` |
| `dev/homologation/telas` | `dev/homologation/screens` |
| `docs/arquitetura/AUDITORIA-2026-10-17-final-pos-CR-007.md` | `docs/architecture/AUDIT-2026-10-17-final-post-CR-007.md` |
| `docs/arquitetura/AUDITORIA-2026-10-17-scheduler.md` | `docs/architecture/AUDIT-2026-10-17-scheduler.md` |
| `docs/arquitetura/CR-001-multiplataforma-e-sql-ansi.md` | `docs/architecture/CR-001-multiplatform-and-ansi-sql.md` |
| `docs/arquitetura/CR-002-oracle-unico-e-driver-adaptativo.md` | `docs/architecture/CR-002-single-oracle-and-adaptive-driver.md` |
| `docs/arquitetura/CR-003-correcoes-pos-analise.md` | `docs/architecture/CR-003-post-analysis-fixes.md` |
| `docs/arquitetura/CR-004-telas-de-consulta-e-linguagem-clara.md` | `docs/architecture/CR-004-query-screens-and-plain-language.md` |
| `docs/arquitetura/CR-005-posix-caminho-livre-e-logs.md` | `docs/architecture/CR-005-posix-free-path-and-logs.md` |
| `docs/arquitetura/CR-006-colunas-de-registro.md` | `docs/architecture/CR-006-record-columns.md` |
| `docs/arquitetura/CR-007-robustez-do-scheduler.md` | `docs/architecture/CR-007-scheduler-robustness.md` |
| `docs/arquitetura/CR-008-auditoria-final.md` | `docs/architecture/CR-008-final-audit.md` |
| `docs/arquitetura/CR-009-ambiente-no-caminho-do-log.md` | `docs/architecture/CR-009-environment-in-log-path.md` |
| `docs/arquitetura/CR-010-variaveis-de-ambiente-do-script.md` | `docs/architecture/CR-010-script-environment-variables.md` |
| `docs/arquitetura/CR-011-link-simbolico-e-sem-hash.md` | `docs/architecture/CR-011-symlink-and-no-hash.md` |
| `docs/arquitetura/CR-012-pasta-de-saida-do-script.md` | `docs/architecture/CR-012-script-output-folder.md` |
| `docs/arquitetura/CR-013-volume-da-fila.md` | `docs/architecture/CR-013-queue-volume.md` |
| `docs/arquitetura/CR-014-pasta-de-entrada.md` | `docs/architecture/CR-014-input-folder.md` |
| `docs/arquitetura/CR-015a-nomes-em-ingles.md` | `docs/architecture/CR-015a-english-names.md` |
| `docs/arquitetura/CR-016a-banco-em-ingles.md` | `docs/architecture/CR-016a-database-in-english.md` |
| `docs/arquitetura/CR-016b-config-e-operacao.md` | `docs/architecture/CR-016b-config-and-operations.md` |
| `docs/arquitetura/RELATORIO-CR-007-R4.md` | `docs/architecture/REPORT-CR-007-R4.md` |
| `docs/arquitetura/RELATORIO-CR-007-R5.md` | `docs/architecture/REPORT-CR-007-R5.md` |
| `docs/arquitetura/RELATORIO-CR-007-UF.md` | `docs/architecture/REPORT-CR-007-UF.md` |
| `docs/arquitetura/RELATORIO-CR-008-P0-R1-R2.md` | `docs/architecture/REPORT-CR-008-P0-R1-R2.md` |
| `docs/arquitetura/RELATORIO-CR-008-UF.md` | `docs/architecture/REPORT-CR-008-UF.md` |
| `docs/prompts/F0_1_ambiente_esqueleto.md` | `docs/prompts/F0_1_environment_skeleton.md` |
| `docs/prompts/F0_3_registro_identificadores.md` | `docs/prompts/F0_3_identifier_registry.md` |
| `docs/prompts/F0_4_contratos_repo_fake.md` | `docs/prompts/F0_4_fake_repo_contracts.md` |
| `docs/prompts/F1_2_componentes_ui.md` | `docs/prompts/F1_2_ui_components.md` |
| `docs/prompts/F2_1_seguranca_base.md` | `docs/prompts/F2_1_security_base.md` |
| `docs/prompts/F3_2_tela_disparo.md` | `docs/prompts/F3_2_dispatch_screen.md` |
| `docs/prompts/F3_3_tickets_lista_detalhe.md` | `docs/prompts/F3_3_tickets_list_detail.md` |
| `docs/prompts/F3_4_visualizador_log.md` | `docs/prompts/F3_4_log_viewer.md` |
| `docs/prompts/F4_1_admin_ambientes.md` | `docs/prompts/F4_1_admin_environments.md` |
| `docs/prompts/F4_2_admin_perfis.md` | `docs/prompts/F4_2_admin_profiles.md` |
| `docs/prompts/F4_3_admin_usuarios.md` | `docs/prompts/F4_3_admin_users.md` |
| `docs/prompts/F4_4_admin_parametros.md` | `docs/prompts/F4_4_admin_parameters.md` |
| `docs/prompts/F5_1_cron_recorrencia.md` | `docs/prompts/F5_1_cron_recurrence.md` |
| `docs/prompts/F5_2_tela_agendamentos.md` | `docs/prompts/F5_2_schedules_screen.md` |
| `docs/prompts/F6_1_auditoria_agentes.md` | `docs/prompts/F6_1_audit_agents.md` |
| `docs/prompts/F7_0_driver_adaptativo.md` | `docs/prompts/F7_0_adaptive_driver.md` |
| `docs/prompts/F8_0_plataforma.md` | `docs/prompts/F8_0_platform.md` |
| `docs/prompts/F8_4_daemon_desdobro_fencing.md` | `docs/prompts/F8_4_daemon_expansion_fencing.md` |

## 5. Validação

* Suítes em 3.6.0, 3.6.8 e 3.13.2, bateria Oracle (3.6.15, GFPR) e percurso real das telas.
* Pacote gerado com os arquivos novos (`package.py`).
* Imports trocados por ferramenta com `ast`/`tokenize`: nome de submódulo genérico (`agendamentos`, `saude`…) só muda dentro da instrução de import e em caminhos pontuados, nunca como chave de entidade.
