# CR-016c2: Identificadores em inglês

| Campo | Valor |
|---|---|
| Status | **Em andamento**, em blocos. Blocos 1 (base), 2 (repositórios), 3a (regras), 3b (services), 4a (camada de processo), 4b (laço do agente), 4c (helper), 5a (scripts de linha de comando) e 5b (testes) concluídos em 2026-10-21; passada final: F1 a F4 concluídas em 2026-10-22 |
| Origem | Regra do README §2.8 (CR-016): funções, classes, métodos, constantes e variáveis em inglês |
| Restrições | Sem dependência nova. Python 3.6. Sem mudança de esquema |
| Blocos | 1 base (`sql_ident`, `sss_config`, `db_conn`, `sss_logging` e formato do log); 2 repositórios e chaves lógicas das entidades; 3 regras (3a) e services (3b); 4 daemon (4a camada de processo, 4b laço do agente, 4c helper); 5 scripts de linha de comando e lançadores (5a) e testes (5b); passada final de parâmetros e variáveis locais |

---

## 1. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Por escopo | Renomeação com `ast`: definição no módulo, referências globais (sem tocar em nome local que esconda o global), acesso qualificado (`modulo.nome`), `from modulo import nome` e alvos de `mock.patch` |
| D2 | Parâmetros e locais por último | Renomear um parâmetro muda os kwargs de todas as chamadas; fica para a passada final, com ferramenta própria |
| D3 | Chaves lógicas das entidades no bloco 2 | `"agendamentos"`, `"usuarios"`, `"auditoria"` são também nomes de repositório do `repo_factory`: mudam juntos |
| D4 | Formato do log | `[agent=…] [ticket=…] [action=…]` (antes `[agente=…]`, `[acao=…]`); filtros e coletores de log precisam de ajuste (DEPLOYMENT §18) |

## 2. Bloco 1 (base)

### `sql_ident`

| Antes | Depois |
|---|---|
| `PADRAO_OWNER` | `OWNER_PATTERN` |
| `PADRAO_PREFIXO` | `PREFIX_PATTERN` |
| `PADRAO_IDENTIFICADOR` | `IDENTIFIER_PATTERN` |
| `PADRAO_IDENT_ASCII_LOWER` | `IDENT_ASCII_LOWER_PATTERN` |
| `FBI_TCK_FILA_INICIO` | `FBI_TCK_QUEUE_START` |
| `FBI_TCK_FILA_EXPR` | `FBI_TCK_QUEUE_EXPR` |
| `FBI_TCK_RUN_AGENTE_CASE` | `FBI_TCK_RUN_AGENT_CASE` |
| `FBI_TSAI_GRAV_EXPR` | `FBI_TOUT_WRITE_EXPR` |
| `FBI_TSAI_GRAV_CASE` | `FBI_TOUT_WRITE_CASE` |
| `FBI_TCK_OCOR_EXPR` | `FBI_TCK_OCCUR_EXPR` |
| `VERSAO_ESQUEMA` | `SCHEMA_VERSION` |
| `COLUNAS_REGISTRO` | `RECORD_COLUMNS` |
| `TABELAS_SEM_REGISTRO` | `TABLES_WITHOUT_RECORD` |
| `ATOR_MAX` | `ACTOR_MAX` |
| `CK_REGISTRO_EXPR` | `CK_RECORD_EXPR` |
| `_eco_seguro` | `_safe_echo` |
| `validar_owner` | `validate_owner` |
| `validar_prefixo` | `validate_prefix` |
| `validar_nome` | `validate_name` |
| `CONTROLE_ESQUEMA_1` | `LEGACY_CONTROL_TABLE` |
| `fisico` | `physical` |
| `qualificar` | `qualify` |
| `tabela` | `table` |
| `_criar_registro_tabelas` | `_build_table_registry` |
| `_aplicar_colunas_registro` | `_apply_record_columns` |
| `TABELAS` | `TABLES` |
| `NomesEsquema` | `SchemaNames` |
| `nomes` | `names` |
| `todos_identificadores` | `all_identifiers` |
| `validar_registro` | `validate_registry` |
| `_checar_identificador` | `_check_identifier` |
| `normalizar_expressao` | `normalize_expression` |
| `eh_ck_not_null_sistema` | `is_system_not_null_ck` |

### `sss_config`

| Antes | Depois |
|---|---|
| `_PREFIXOS_BLOQUEADOS` | `_BLOCKED_PREFIXES` |
| `_LD_PERMITIDA` | `_ALLOWED_LD` |
| `_CHAVES_FIXAS` | `_FIXED_KEYS` |
| `_PREFIXOS_FIXOS` | `_FIXED_PREFIXES` |
| `VERSAO_SSS` | `SSS_VERSION` |
| `CHAVES_REMOVIDAS` | `REMOVED_KEYS` |
| `CHAVES_RENOMEADAS` | `RENAMED_KEYS` |
| `SECOES_RENOMEADAS` | `RENAMED_SECTIONS` |
| `AGENT_IDS_RESERVADOS` | `RESERVED_AGENT_IDS` |
| `_RE_USUARIO_EXECUCAO` | `_RE_EXEC_USER` |
| `_AMBIENTES_MAX` | `_ENVIRONMENTS_MAX` |
| `PAPEIS` | `ROLES` |
| `variavel_bloqueada` | `is_blocked_variable` |
| `ConfigErro` | `ConfigError` |
| `CampoDef` | `FieldDef` |
| `RetencaoConfig` | `RetentionConfig` |
| `_converter_valor` | `_convert_value` |
| `carregar` | `load` |
| `_dentro` | `_inside` |
| `_validar_cr007` | `_validate_cr007` |
| `verificar_codificacao` | `check_encoding` |
| `OracleSegredo` | `OracleSecret` |
| `WebSegredo` | `WebSecret` |
| `AmbienteSegredo` | `EnvironmentSecret` |
| `Segredos` | `Secrets` |
| `_secao_de_outro_papel` | `_other_role_section` |
| `_segredos_monitor` | `_monitor_secrets` |
| `carregar_segredos` | `load_secrets` |
| `caminho_config_padrao` | `default_config_path` |
| `_log_dir_bruto` | `_raw_log_dir` |
| `_abortar` | `_abort` |
| `obter_config` | `get_config` |
| `_SEGREDOS_CACHE` | `_SECRETS_CACHE` |
| `obter_segredos` | `get_secrets` |
| `reset_segredos_cache` | `reset_secrets_cache` |
| `config_criticos` | `critical_config` |

### `db_conn`

| Antes | Depois |
|---|---|
| `_LOCK_SELECAO` | `_SELECTION_LOCK` |
| `_SELECAO_DRIVER` | `_DRIVER_SELECTION` |
| `_DRIVER_INICIALIZADO` | `_DRIVER_INITIALIZED` |
| `_AVISO_ORCAMENTO_EMITIDO` | `_BUDGET_WARNING_EMITTED` |
| `ErroVersaoEsquema` | `SchemaVersionError` |
| `_obter_senha` | `_get_password` |
| `_registrar_critico` | `_log_critical` |
| `_executar_sondagem_subprocesso` | `_run_probe_subprocess` |
| `selecionar_driver` | `select_driver` |
| `inicializar` | `initialize` |
| `obter_selecao` | `get_selection` |
| `reset_selecao` | `reset_selection` |
| `obter_tipo_driver` | `get_driver_type` |
| `definir_tipos_entrada` | `set_input_types` |
| `variavel_saida` | `output_variable` |
| `valor_saida` | `output_value` |
| `_ERROS_REDE_ORA` | `_NETWORK_ERRORS_ORA` |
| `_ERROS_REDE_DPI` | `_NETWORK_ERRORS_DPI` |
| `_ERROS_REDE_DPY` | `_NETWORK_ERRORS_DPY` |
| `_ERROS_TIMEOUT_DPY` | `_TIMEOUT_ERRORS_DPY` |
| `_ERROS_TIMEOUT_DPI` | `_TIMEOUT_ERRORS_DPI` |
| `_ERROS_TIMEOUT_ORA` | `_TIMEOUT_ERRORS_ORA` |
| `_ERROS_LOCK_ORA` | `_LOCK_ERRORS_ORA` |
| `_ERROS_VIOLACAO_ORA` | `_VIOLATION_ERRORS_ORA` |
| `classificar_erro` | `classify_error` |
| `eh_erro_rede` | `is_network_error` |
| `eh_tempo_esgotado` | `is_timeout` |
| `eh_lock` | `is_lock` |
| `eh_violacao` | `is_violation` |
| `traduzir_erro` | `translate_error` |
| `orcamento_conexao_s` | `connection_budget_s` |
| `conectar` | `connect` |
| `configurar_sessao` | `configure_session` |
| `transacao` | `transaction` |
| `agora_banco` | `db_now` |
| `saude` | `health` |
| `proximo_id` | `next_id` |
| `conferir_versao_esquema` | `check_schema_version` |
| `ConexaoResiliente` | `ResilientConnection` |

### `sss_logging`

| Antes | Depois |
|---|---|
| `_garantir_diretorio` | `_ensure_directory` |
| `configurar` | `configure` |
| `registrar_critico_inicial` | `log_initial_critical` |
| `obter_logger` | `get_logger` |
| `_LOCK_LOGGERS` | `_LOGGERS_LOCK` |

Também: `ConfigError(section=, key=, reason=)` (antes `secao`, `chave`, `motivo`); `FieldDef(kind, required=…)`; `Secrets.environments`, `get_environment()`; `SchemaNames.all_identifiers()`/`list_identifiers()`; métodos de `ResilientConnection`: `get_connection`, `close`, `notify_error`, `ensure`; `get_adapter(agent=, ticket=, action=)`.

## 3. Validação do bloco 1

* Suítes em 3.6.0, 3.6.8 e 3.13.2, bateria Oracle e percurso real das telas (log no formato novo).

## 4. Bloco 2 (repositórios)

Classes, constantes e funções de `repo_errors`, `repo_base`, `repo_factory`, `repo_oracle/*` e `repo_fake/*`; métodos dos repositórios; chaves lógicas das entidades (que são também os nomes do `repo_factory`); atributos do `FakeDataStore`; chaves do dicionário `_sql` de cada repositório Oracle.

Fica para depois:

* `concluir` (repositório de agendamentos) muda no bloco 3, junto com `recurrence.Decisao`;
* variáveis de tela (chaves do `dict` que o controller entrega à view, como `ambientes`, `perfis`, `agora`, `fila_sem_atendente`), atributos de sessão e chaves de `TELAS_ENTIDADE`/`ui_menu` mudam no CR-016d (web), com as views;
* rótulos `snapshot.respostas` (formato gravado no ticket) e o argumento `agora` da recorrência ficam como estão neste bloco.

### Chaves lógicas das entidades

O nome físico (`sql_ident.TABLES[e]['physical']`) não muda; muda só a chave lógica.

| Antes | Depois |
|---|---|
| `agendamentos` | `schedules` |
| `agentes` | `agents` |
| `ambientes` | `environments` |
| `auditoria` | `audit` |
| `catalogo` | `catalog` |
| `controle` | `control` |
| `funcionalidades` | `features` |
| `parametros` | `parameters` |
| `perfil_amb` | `profile_env` |
| `perfil_func` | `profile_feature` |
| `perfil_scr` | `profile_script` |
| `perfis` | `profiles` |
| `script_amb` | `script_env` |
| `ticket_resp` | `ticket_answer` |
| `ticket_saida` | `ticket_output` |
| `usuarios` | `users` |

### `repo_factory`

| Antes | Depois |
|---|---|
| `ENV_SENHA_DEV` | `ENV_DEV_PASSWORD` |
| `_classe_oracle` | `_oracle_class` |
| `_lock_fabrica` | `_factory_lock` |
| `_resolver_config` | `_resolve_config` |
| `_senha_dev_seed` | `_dev_seed_password` |
| `configurar` | `configure` |
| `obter` | `get` |

Nomes aceitos por `repo_factory.get()`: `catalog`, `tickets`, `schedules`, `audit`, `agents`, `users`, `rbac`.

### Métodos dos repositórios

| Antes | Depois |
|---|---|
| `admins_ativos_bloquear` | `lock_active_admins` |
| `agentes` | `agents` |
| `agora` | `now` |
| `alterar` | `update` |
| `ambiente_existe` | `environment_exists` |
| `ambientes_alterar` | `environments_update` |
| `ambientes_ativos` | `active_environments` |
| `ambientes_inserir` | `environments_insert` |
| `ambientes_listar` | `environments_list` |
| `ambientes_obter` | `environments_get` |
| `anexar` | `append_chunk` |
| `apagar_auditoria` | `delete_audit` |
| `apagar_tickets` | `delete_tickets` |
| `ator_registro` | `record_actor` |
| `auditar` | `audit` |
| `avancar_sem_ticket` | `advance_without_ticket` |
| `cancelamento_pedido` | `is_cancel_requested` |
| `candidatos` | `candidates` |
| `carimbar_alteracao` | `stamp_update` |
| `carimbar_inclusao` | `stamp_insert` |
| `carregar_regra` | `load_rule` |
| `checar_fk` | `check_fk` |
| `concluir_com_ticket` | `complete_with_ticket` |
| `concluir_sem_ticket` | `complete_without_ticket` |
| `conferir_config` | `check_config` |
| `contar_auditoria` | `count_audit` |
| `contar_tickets` | `count_tickets` |
| `contexto_execucao` | `execution_context` |
| `contexto_leitura` | `read_context` |
| `criar` | `create` |
| `da_config` | `from_config` |
| `definir_relogio` | `set_clock` |
| `definir_senha` | `set_password` |
| `desbloquear` | `unlock` |
| `devolver` | `return_to_queue` |
| `encerrar_agente` | `stop_agent` |
| `encerrar_sessoes` | `end_sessions` |
| `falhar_gravando_do_agente` | `fail_agent_writing` |
| `fila_por_par` | `queue_by_pair` |
| `fila_sem_atendente` | `unattended_queue` |
| `fila_vencida` | `overdue_queue` |
| `finalizar` | `finalize` |
| `finalizar_fenced` | `finalize_fenced` |
| `funcionalidades_listar` | `features_list` |
| `historico_script` | `script_history` |
| `homologacao_obter` | `homologation_get` |
| `homologacao_salvar` | `homologation_save` |
| `iniciar` | `start` |
| `inserir` | `insert` |
| `iterar` | `iterate` |
| `ler_e_apagar_auditoria` | `read_and_delete_audit` |
| `liberar_concessao` | `release_lease` |
| `listar` | `list` |
| `log_ler` | `log_read` |
| `login_do_usuario` | `user_login` |
| `login_existe` | `login_exists` |
| `marcar_node_offline` | `mark_node_offline` |
| `marcar_truncado` | `mark_truncated` |
| `matriz_obter` | `matrix_get` |
| `matriz_salvar` | `matrix_save` |
| `nome_constraint` | `constraint_name` |
| `nome_trigger` | `trigger_name` |
| `obter` | `get` |
| `obter_estado_sessao` | `get_session_state` |
| `obter_por_id` | `get_by_id` |
| `obter_por_login` | `get_by_login` |
| `obter_ticket` | `get_ticket` |
| `parametro_vinculos` | `parameter_links` |
| `parametros_alterar` | `parameters_update` |
| `parametros_inserir` | `parameters_insert` |
| `parametros_listar` | `parameters_list` |
| `parametros_obter` | `parameters_get` |
| `pausar` | `pause` |
| `pausar_cron_erro` | `pause_cron_error` |
| `pausar_erro_interno` | `pause_internal_error` |
| `perfis_alterar` | `profiles_update` |
| `perfis_inserir` | `profiles_insert` |
| `perfis_listar` | `profiles_list` |
| `perfis_obter` | `profiles_get` |
| `proximo_id` | `next_id` |
| `proximo_ticket_id` | `next_ticket_id` |
| `qualificar_sequence` | `qualify_sequence` |
| `qualificar_tabela` | `qualify_table` |
| `registrar` | `register` |
| `registrar_agente` | `register_agent` |
| `registrar_auditoria_interno` | `register_internal_audit` |
| `registrar_falha_login` | `register_login_failure` |
| `registrar_pid` | `register_pid` |
| `registrar_sem_conteudo` | `register_without_content` |
| `registrar_sucesso_login` | `register_login_success` |
| `regras_vencidas` | `due_rules` |
| `reiniciar_tentativas` | `reset_attempts` |
| `reservar_e_criar_ticket` | `reserve_and_create_ticket` |
| `reservar_id` | `reserve_id` |
| `respostas` | `answers` |
| `retomar` | `resume` |
| `rodando_sem_pid` | `running_without_pid` |
| `running_para_logs` | `running_for_logs` |
| `saida_ler` | `output_read` |
| `saida_obter` | `output_get` |
| `script_ativo_homologado` | `active_homologated_script` |
| `script_e_vinculos` | `script_and_links` |
| `script_params_obter` | `script_params_get` |
| `script_params_salvar` | `script_params_save` |
| `scripts_alterar` | `scripts_update` |
| `scripts_executaveis` | `executable_scripts` |
| `scripts_inserir` | `scripts_insert` |
| `scripts_listar` | `scripts_list` |
| `scripts_obter` | `scripts_get` |
| `situacao` | `output_state` |
| `solicitar_cancelamento` | `request_cancel` |
| `status_ticket` | `get_ticket_status` |
| `tomar_concessao` | `take_lease` |
| `transacao_escrita` | `write_transaction` |
| `travar_regra` | `lock_rule` |
| `tupla_para_dict` | `tuple_to_dict` |
| `ultimas_execucoes` | `last_runs` |
| `ultimo_purge` | `last_purge` |
| `unidade_suplementar` | `supplementary_unit` |
| `varredura_propria` | `own_sweep` |
| `versao_esquema` | `schema_version` |

### Classes, constantes e funções por módulo

Cada título é o arquivo em `repo_oracle/` e `repo_fake/` (os que começam com `repo_` são módulos de `modules/`).

#### `agents`

| Antes | Depois |
|---|---|
| `RepoAgentesFake` | `RepoAgentsFake` |
| `RepoAgentesOracle` | `RepoAgentsOracle` |
| `_COLS_SEM_PID` | `_COLS_NO_PID` |
| `_SQL_FILA` | `_SQL_QUEUE` |
| `_SQL_LISTAR` | `_SQL_LIST` |
| `_SQL_RODANDO_SEM_PID` | `_SQL_RUNNING_NO_PID` |
| `_lista` | `_column_list` |

#### `audit`

| Antes | Depois |
|---|---|
| `RepoAuditoriaFake` | `RepoAuditFake` |
| `RepoAuditoriaOracle` | `RepoAuditOracle` |
| `_LIMITE_TOTAL` | `_LIMIT_TOTAL` |
| `_SQL_CONTAR` | `_SQL_COUNT` |
| `_SQL_INSERIR` | `_SQL_INSERT` |
| `_SQL_ITERAR` | `_SQL_ITERATE` |
| `_SQL_LISTAR` | `_SQL_LIST` |
| `_SQL_OBTER` | `_SQL_GET` |
| `_lista` | `_column_list` |

#### `base`

| Antes | Depois |
|---|---|
| `_ATOR_MAX` | `_ACTOR_MAX` |
| `_DETALHE_MAX` | `_DETAIL_MAX` |
| `descartar_pools` | `discard_pools` |
| `gravar_auditoria` | `write_audit` |
| `traduzir_erro_oracle` | `translate_oracle_error` |
| `validar_ator_registro` | `validate_record_actor` |
| `validar_campos_auditoria` | `validate_audit_fields` |

#### `catalog`

| Antes | Depois |
|---|---|
| `RepoCatalogoFake` | `RepoCatalogFake` |
| `RepoCatalogoOracle` | `RepoCatalogOracle` |
| `_CAMPOS_SCR_ALTERAVEIS` | `_FIELDS_SCR_UPDATABLE` |
| `_COLS_AMB` | `_COLS_ENV` |
| `_LIMITE_TOTAL` | `_LIMIT_TOTAL` |
| `_LOTE_IN` | `_BATCH_IN` |
| `_RE_AMB_NOME` | `_RE_ENV_NAME` |
| `_RE_PRM_CODIGO` | `_RE_PRM_CODE` |
| `_SQL_AMB_ALTERAR` | `_SQL_ENV_UPDATE` |
| `_SQL_AMB_CONTAR` | `_SQL_ENV_COUNT` |
| `_SQL_AMB_EXISTE` | `_SQL_ENV_EXISTS` |
| `_SQL_AMB_INSERIR` | `_SQL_ENV_INSERT` |
| `_SQL_AMB_LISTAR` | `_SQL_ENV_LIST` |
| `_SQL_AMB_OBTER` | `_SQL_ENV_GET` |
| `_SQL_AMB_OBTER_LOCK` | `_SQL_ENV_GET_LOCK` |
| `_SQL_AMB_POR_NOME` | `_SQL_ENV_BY_NAME` |
| `_SQL_EXEC_PERFIL` | `_SQL_EXEC_PROFILE` |
| `_SQL_PRM_ALTERAR` | `_SQL_PRM_UPDATE` |
| `_SQL_PRM_CONTAR` | `_SQL_PRM_COUNT` |
| `_SQL_PRM_EXISTE` | `_SQL_PRM_EXISTS` |
| `_SQL_PRM_INSERIR` | `_SQL_PRM_INSERT` |
| `_SQL_PRM_LISTAR` | `_SQL_PRM_LIST` |
| `_SQL_PRM_OBTER` | `_SQL_PRM_GET` |
| `_SQL_PRM_OBTER_LOCK` | `_SQL_PRM_GET_LOCK` |
| `_SQL_PRM_POR_CODIGO` | `_SQL_PRM_BY_CODE` |
| `_SQL_PRM_SCRIPTS_VINCULADOS` | `_SQL_PRM_SCRIPTS_LINKED` |
| `_SQL_PRM_VINCULOS` | `_SQL_PRM_LINKS` |
| `_SQL_SAMB_DO_SCRIPT` | `_SQL_SENV_OF_SCRIPT` |
| `_SQL_SAMB_EXCLUIR` | `_SQL_SENV_DELETE` |
| `_SQL_SAMB_INSERIR` | `_SQL_SENV_INSERT` |
| `_SQL_SCR_ALTERAR` | `_SQL_SCR_UPDATE` |
| `_SQL_SCR_CARIMBAR` | `_SQL_SCR_STAMP` |
| `_SQL_SCR_CONTAR` | `_SQL_SCR_COUNT` |
| `_SQL_SCR_HOMOLOGADOS` | `_SQL_SCR_HOMOLOGATED` |
| `_SQL_SCR_INSERIR` | `_SQL_SCR_INSERT` |
| `_SQL_SCR_LISTAR` | `_SQL_SCR_LIST` |
| `_SQL_SCR_NOME_EM_USO` | `_SQL_SCR_NAME_IN_USE` |
| `_SQL_SCR_OBTER` | `_SQL_SCR_GET` |
| `_SQL_SCR_OBTER_LOCK` | `_SQL_SCR_GET_LOCK` |
| `_SQL_SPRM_DO_SCRIPT` | `_SQL_SPRM_OF_SCRIPT` |
| `_SQL_SPRM_EXCLUIR_DO_SCRIPT` | `_SQL_SPRM_DELETE_OF_SCRIPT` |
| `_SQL_SPRM_INSERIR` | `_SQL_SPRM_INSERT` |
| `_SQL_SPRM_INSERIR_ALTERADO` | `_SQL_SPRM_INSERT_CHANGED` |
| `_SQL_SPRM_INSERIR_NOVO` | `_SQL_SPRM_INSERT_NEW` |
| `_SQL_SPRM_OBTER` | `_SQL_SPRM_GET` |
| `_SQL_SPRM_PARAMETROS` | `_SQL_SPRM_PARAMETERS` |
| `_igual` | `_equal` |
| `_like_contem` | `_like_contains` |
| `_lista` | `_column_list` |
| `_pagina_tamanho` | `_page_size` |

#### `health`

| Antes | Depois |
|---|---|
| `COLS_AGENTE` | `COLS_AGENT` |
| `COLS_SEM_PID` | `COLS_NO_PID` |
| `RepoSaude` | `RepoHealth` |
| `SQL_FILA` | `SQL_QUEUE` |
| `SQL_RODANDO_SEM_PID` | `SQL_RUNNING_NO_PID` |
| `_INICIO` | `_START` |
| `_SQL_AGENTES` | `_SQL_AGENTS` |
| `_SQL_AMBIENTES` | `_SQL_ENVIRONMENTS` |
| `_SQL_FILA_VENCIDA` | `_SQL_QUEUE_OVERDUE` |
| `_SQL_ULTIMO_PURGE` | `_SQL_LAST_PURGE` |
| `_SQL_VERSAO` | `_SQL_VERSION` |
| `fila_sem_atendente` | `unattended_queue` |
| `pares_atendidos` | `served_pairs` |

#### `purge`

| Antes | Depois |
|---|---|
| `ATOR` | `ACTOR` |
| `TERMINAIS` | `TERMINAL_STATUSES` |
| `_ler_lob` | `_read_lob` |

#### `rbac`

| Antes | Depois |
|---|---|
| `_COLS_PERFIL` | `_COLS_PROFILE` |

#### `repo_agents`

| Antes | Depois |
|---|---|
| `RepoAgentes` | `RepoAgents` |

#### `repo_audit`

| Antes | Depois |
|---|---|
| `RepoAuditoria` | `RepoAudit` |

#### `repo_catalog`

| Antes | Depois |
|---|---|
| `RepoCatalogo` | `RepoCatalog` |

#### `repo_errors`

| Antes | Depois |
|---|---|
| `RepoConflito` | `RepoConflict` |
| `RepoErro` | `RepoError` |
| `RepoIndisponivel` | `RepoUnavailable` |
| `RepoNaoEncontrado` | `RepoNotFound` |
| `RepoViolacao` | `RepoViolation` |

#### `repo_schedules`

| Antes | Depois |
|---|---|
| `RepoAgendamentos` | `RepoSchedules` |

#### `repo_users`

| Antes | Depois |
|---|---|
| `RepoUsuarios` | `RepoUsers` |

#### `scheduler_log`

| Antes | Depois |
|---|---|
| `GRAVADO` | `WRITTEN` |
| `JA_GRAVADO` | `ALREADY_WRITTEN` |
| `LogOffsetInconsistente` | `LogOffsetMismatch` |
| `POSSE_PERDIDA` | `OWNERSHIP_LOST` |
| `_ORA_DIVERGENTE` | `_ORA_DIVERGENT` |
| `_PLSQL_ANEXAR` | `_PLSQL_APPEND` |
| `_RESULTADOS` | `_RESULTS` |
| `_SQL_TRUNCADO` | `_SQL_TRUNCATED` |
| `_SQL_UNIDADE_SUPLEMENTAR` | `_SQL_UNIT_SUPPLEMENTARY` |

#### `scheduler_output`

| Antes | Depois |
|---|---|
| `GRAVADO` | `WRITTEN` |
| `JA_GRAVADO` | `ALREADY_WRITTEN` |
| `MOTIVOS` | `REASONS` |
| `PARTE_MAX` | `PART_MAX` |
| `POSSE_PERDIDA` | `OWNERSHIP_LOST` |
| `RepoSchedulerSaida` | `RepoSchedulerOutput` |
| `SITUACOES_SEM_CONTEUDO` | `STATES_NO_CONTENT` |
| `SaidaOffsetInconsistente` | `OutputOffsetMismatch` |
| `_ORA_DIVERGENTE` | `_ORA_DIVERGENT` |
| `_PLSQL_ANEXAR` | `_PLSQL_APPEND` |
| `_RESULTADOS` | `_RESULTS` |
| `_SQL_CONCLUIR` | `_SQL_COMPLETE` |
| `_SQL_ENCERRAR_GRAVANDO` | `_SQL_CLOSE_WRITING` |
| `_SQL_FALHAR_DO_AGENTE` | `_SQL_FAIL_OF_AGENT` |
| `_SQL_INCLUIR` | `_SQL_INSERT` |
| `_SQL_REINICIAR` | `_SQL_RESTART` |
| `_SQL_SITUACAO` | `_SQL_STATE` |
| `_ator` | `_actor` |

#### `scheduler_queue`

| Antes | Depois |
|---|---|
| `ATOR_MAX` | `ACTOR_MAX` |
| `AgenteDuplicado` | `DuplicateAgent` |
| `DETALHE_MAX` | `DETAIL_MAX` |
| `PRIORIDADES` | `PRIORITIES` |
| `RegistroPerdido` | `RegistrationLost` |
| `RepoSchedulerFila` | `RepoSchedulerQueue` |
| `TERMINAIS` | `TERMINAL_STATUSES` |
| `_INICIO` | `_START` |
| `_Transacao` | `_Transaction` |
| `_ler_lob` | `_read_lob` |
| `ator_sistema` | `system_actor` |

#### `scheduler_schedules`

| Antes | Depois |
|---|---|
| `ATOR_MAX` | `ACTOR_MAX` |
| `DATA_INICIAL` | `DATE_INITIAL` |
| `DETALHE_MAX` | `DETAIL_MAX` |
| `OcorrenciaDuplicada` | `DuplicateOccurrence` |
| `RepoSchedulerAgenda` | `RepoSchedulerSchedules` |
| `_COLS_REGRA` | `_COLS_RULE` |
| `_ORA_DUPLICADO` | `_ORA_DUPLICATE` |
| `_ler_lob` | `_read_lob` |
| `_limpo` | `_clean` |
| `ator_sistema` | `system_actor` |
| `sem_microssegundos` | `without_microseconds` |

#### `schedules`

| Antes | Depois |
|---|---|
| `RepoAgendamentosFake` | `RepoSchedulesFake` |
| `RepoAgendamentosOracle` | `RepoSchedulesOracle` |
| `_COLUNAS_ALTERAVEIS` | `_COLUMNS_UPDATABLE` |
| `_DATAS` | `_DATES` |
| `_LIMITE_TOTAL` | `_LIMIT_TOTAL` |
| `_MOTIVOS_PAUSA` | `_REASONS_PAUSE` |
| `_RE_DSEM` | `_RE_WDAY` |
| `_RE_HORA` | `_RE_TIME` |
| `_SQL_ALTERAR` | `_SQL_UPDATE` |
| `_SQL_AMB_EXISTE` | `_SQL_ENV_EXISTS` |
| `_SQL_CONTAR` | `_SQL_COUNT` |
| `_SQL_EXISTE` | `_SQL_EXISTS` |
| `_SQL_INSERIR` | `_SQL_INSERT` |
| `_SQL_LISTAR` | `_SQL_LIST` |
| `_SQL_OBTER` | `_SQL_GET` |
| `_SQL_OBTER_LOCK` | `_SQL_GET_LOCK` |
| `_SQL_PAUSAR` | `_SQL_PAUSE` |
| `_SQL_PAUSAR_OTIMISTA` | `_SQL_PAUSE_OPTIMISTIC` |
| `_SQL_RETOMAR` | `_SQL_RESUME` |
| `_SQL_SCR_EXISTE` | `_SQL_SCR_EXISTS` |
| `_SQL_USR_EXISTE` | `_SQL_USR_EXISTS` |
| `_TAMANHO_NOME` | `_SIZE_NAME` |
| `_TIPOS` | `_TYPES` |
| `_checar_cks` | `_check_cks` |
| `_igual` | `_equal` |
| `_ler_lob` | `_read_lob` |
| `_lista` | `_column_list` |
| `_nulo` | `_null` |

#### `seed`

| Antes | Depois |
|---|---|
| `MARCADOR_TRUNCADO` | `MARKER_TRUNCATED` |
| `_ATOR_SEED` | `_ACTOR_SEED` |
| `_CADASTROS` | `_REGISTRIES` |
| `_HB_CONGELADO_S` | `_HB_FROZEN_S` |
| `_LINHAS_LOG_VOLUMOSO` | `_LINES_LOG_LARGE` |
| `_PASSO_LOG_S` | `_STEP_LOG_S` |
| `_SEM_SENHA_DEV` | `_NO_PASSWORD_DEV` |
| `_TICKET_FILA_SEM_ATENDENTE` | `_TICKET_QUEUE_NO_SERVER` |
| `_TICKET_LOG_VOLUMOSO` | `_TICKET_LOG_LARGE` |
| `_TICKET_SEM_PID` | `_TICKET_NO_PID` |
| `_carimbar_registro` | `_stamp_record` |
| `_compilar_seed` | `_compile_seed` |
| `_entre` | `_between` |
| `_log_volumoso` | `_large_log` |
| `_parametros_json` | `_params_json` |
| `_seed_saidas` | `_seed_outputs` |
| `_vinculos_compilador` | `_compiler_links` |
| `_zip_seed` | `_seed_zip` |
| `carregar_seed` | `load_seed` |

#### `store`

| Antes | Depois |
|---|---|
| `LIMITE_TOTAL_PAGINACAO` | `LIMIT_TOTAL_PAGINATION` |
| `_ATOR_MAX` | `_ACTOR_MAX` |
| `_DETALHE_MAX` | `_DETAIL_MAX` |
| `paginar` | `paginate` |

#### `tickets`

| Antes | Depois |
|---|---|
| `SAIDA_FATIA_MAX` | `OUTPUT_SLICE_MAX` |
| `_COLS_RESP` | `_COLS_ANS` |
| `_COLS_SAIDA` | `_COLS_OUTPUT` |
| `_COLS_ULTIMA` | `_COLS_LAST` |
| `_COLUNAS_CLOB` | `_COLUMNS_CLOB` |
| `_DATAS_TCK` | `_DATES_TCK` |
| `_ETAPAS_SIMULADAS` | `_STAGES_SIMULATED` |
| `_ETAPA_HTML` | `_STAGE_HTML` |
| `_ETAPA_SEGREDO` | `_STAGE_SECRET` |
| `_LIMITE_TOTAL` | `_LIMIT_TOTAL` |
| `_LOTE_IN` | `_BATCH_IN` |
| `_SQL_AMB_EXISTE` | `_SQL_ENV_EXISTS` |
| `_SQL_CANCEL_LER` | `_SQL_CANCEL_READ` |
| `_SQL_CANCEL_PENDENTE` | `_SQL_CANCEL_PENDING` |
| `_SQL_CANCEL_SINALIZAR` | `_SQL_CANCEL_SIGNAL` |
| `_SQL_CONTAR` | `_SQL_COUNT` |
| `_SQL_HISTORICO` | `_SQL_HISTORY` |
| `_SQL_INSERIR` | `_SQL_INSERT` |
| `_SQL_INSERIR_RESP` | `_SQL_INSERT_ANS` |
| `_SQL_LISTAR` | `_SQL_LIST` |
| `_SQL_OBTER` | `_SQL_GET` |
| `_SQL_PRM_EXISTE` | `_SQL_PRM_EXISTS` |
| `_SQL_RESPOSTAS` | `_SQL_ANSWERS` |
| `_SQL_SAIDA` | `_SQL_OUTPUT` |
| `_SQL_SAIDA_CONTEUDO` | `_SQL_OUTPUT_CONTENT` |
| `_SQL_SCR_EXISTE` | `_SQL_SCR_EXISTS` |
| `_SQL_TCK_EXISTE` | `_SQL_TCK_EXISTS` |
| `_SQL_ULTIMAS` | `_SQL_LAST` |
| `_SQL_USR_EXISTE` | `_SQL_USR_EXISTS` |
| `_TERMINAIS` | `_TERMINAL` |
| `_ler_lob` | `_read_lob` |
| `_linhas_etapa` | `_stage_lines` |
| `_lista` | `_column_list` |
| `_mascarar_como_log_pump` | `_mask_like_log_pump` |
| `_sem` | `_without` |

#### `users`

| Antes | Depois |
|---|---|
| `RepoUsuariosFake` | `RepoUsersFake` |
| `RepoUsuariosOracle` | `RepoUsersOracle` |
| `_COLS_USUARIO` | `_COLS_USER` |
| `_auditoria_falha` | `_failed_login_audit` |
| `_revogar_sessoes` | `_revoke_sessions` |

## 5. Validação do bloco 2

* Suítes em 3.6.0, 3.6.8 e 3.13.2, bateria Oracle no GFPR e percurso real das telas no web2py do DEV.
* Achado na revisão: `scheduler_loop.liberar_recursos` testava `hasattr(conexao, "fechar")` depois que o bloco 1 renomeou o método para `close`, e a conexão deixava de ser fechada na parada. Corrigido; os nomes em `hasattr`/`getattr`/`mock.patch` foram conferidos contra os mapas dos blocos 1 e 2.
* Rótulos de injeção de falha dos fakes de teste do scheduler e chaves `_sql` do `repo_oracle/health` alinhados aos nomes novos dos métodos.
* A bateria Oracle pegou o que o FAKE não vê, e foi corrigido:
  * `repo_oracle/audit`: o dicionário `_sql` ainda tinha as chaves `INSERIR`/`OBTER`, e as consultas já usavam `INSERT`/`GET`;
  * `repo_oracle/scheduler_schedules`: a renomeação de chaves trocou o bind `parametros` por `parameters`, sem o `:parametros` do SQL mudar (DPY-4008). Binds ficam como estão até a passada final, que muda SQL e dicionário juntos;
  * código Python dentro de string, rodado em subprocesso pelos testes de driver (`test_log_pump`, `test_scheduler_output`), ainda chamava `da_config`, `iniciar` e `anexar`.
* Os testes progressivos (`test_repo_oracle_progressive`) só rodam com `SSS_TEST_REPO_AGREGADO=<agregado>` e ficam de fora da bateria comum. Rodados os cinco agregados, apareceram falhas antigas do próprio teste, corrigidas: nomes de CK de agendamentos anteriores ao CR-016a, chaves `_sql` antigas, `import sql_ident` ausente e a fila sem atendente comparada com o `scheduled_at` no passado, quando desde o CR-013 a espera conta de `GREATEST(scheduled_at, created_at)`.
* Conferência automática nos arquivos alterados: chaves `_sql` consultadas x definidas, chaves de bind x `:placeholders` do SQL e nomes antigos em strings de código.

## 6. Bloco 3a (regras)

Módulos `rbac`, `params_compiler`, `recurrence`, `schedule_expansion`, `cron_parser`, `security`, `masking`, `path_guard`, `env_builder` e `ddl_builder`.

Decisões aprovadas (2026-10-21):

| # | Decisão | Resumo |
|---|---|---|
| D5 | Valor muda com o nome | Códigos internos com valor em português passam a valor em inglês: `rbac.Reason` (só log), `path_guard.Code` (log e mensagem do cadastro; os mesmos códigos devolvidos por `os_platform/posix.py`) e os códigos de saúde dos agentes (`ATRASADO` → `DELAYED`, `EM_RISCO` → `AT_RISK`). Nada disso é gravado no banco; a tela mostra o rótulo em português. Muda o que sai no log e na saída do `health.py` |
| D6 | `Decision` e `complete` | Campos de `recurrence.Decision` em inglês; o método `concluir` do repositório de saída (adiado do bloco 2) vira `complete` |
| D7 | `list_page` | No bloco 3b, a função de módulo `listar` vira `list_page` (não `list`, para não esconder o builtin); o método `list` dos services fica |
| D8 | Fora deste bloco | Funções de controller (URLs), variáveis de tela, atributos de sessão e chaves de `TELAS_ENTIDADE` no CR-016d; parâmetros, locais e binds de SQL na passada final |

Métodos com nome genérico mudaram em todas as classes que os definem, depois de conferir que nenhuma já tinha o nome novo nem herdava de `threading.Thread`: `executar` → `run` (`Desdobro`, `Agente`, `Rodada`, `Verificacao` do `health.py`, `Purge`), `processar` → `process`, `mascarar` → `mask`, `alimentar` → `feed`.

### `rbac`

| Antes | Depois |
|---|---|
| `Motivo` | `Reason` |
| `PRIORIDADE_ADMIN` | `ADMIN_PRIORITY` |
| `_ativo` | `_active` |
| `_id_valido` | `_valid_id` |
| `_nome_ambiente` | `_environment_name` |
| `contexto_usuario` | `user_context` |
| `motivo_pausa` | `pause_reason_for` |
| `pode_cancelar` | `can_cancel` |
| `pode_executar` | `can_execute` |
| `pode_ver_ambiente` | `can_view_environment` |
| `pode_ver_ticket` | `can_view_ticket` |
| `prioridade_permitida` | `allowed_priority` |
| `tem_func` | `has_feature` |

### `params_compiler`

| Antes | Depois |
|---|---|
| `AMPLITUDE_LARGA` | `WIDE_RANGE` |
| `CHAVE_GERAL` | `GENERAL_KEY` |
| `MASCARA` | `MASK` |
| `MAX_ESCOLHAS` | `MAX_CHOICES` |
| `MAX_ESCOLHAS_COM_ILIMITADO` | `MAX_CHOICES_WITH_UNBOUNDED` |
| `MAX_ILIMITADOS` | `MAX_UNBOUNDED` |
| `ParamErro` | `ParamError` |
| `SENSIVEL_MINIMO` | `SENSITIVE_MIN_LENGTH` |
| `SnapshotErro` | `SnapshotError` |
| `TAMANHO_CHAVE_OPCAO` | `OPTION_KEY_MAX_LENGTH` |
| `TAMANHO_MAXIMO` | `MAX_LENGTH` |
| `TAMANHO_OPCOES` | `OPTIONS_MAX_LENGTH` |
| `TAMANHO_REGEX` | `REGEX_MAX_LENGTH` |
| `TAMANHO_ROTULO_OPCAO` | `OPTION_LABEL_MAX_LENGTH` |
| `TIPOS_COMPONENTE` | `COMPONENT_TYPES` |
| `TIPOS_PARAM` | `PARAM_TYPES` |
| `VERSAO_SNAPSHOT` | `SNAPSHOT_VERSION` |
| `_CHAVES_SNAPSHOT` | `_SNAPSHOT_KEYS` |
| `_RE_CONTROLE` | `_RE_CONTROL` |
| `_RE_QUANT_CHAVE` | `_RE_BRACE_QUANT` |
| `_arg_sequencial` | `_sequential_arg` |
| `_args_nomeado` | `_named_args` |
| `_fim_da_classe` | `_class_end` |
| `_mascarar_args` | `_mask_args` |
| `_montar` | `_build` |
| `_opcoes_select` | `_select_options` |
| `_ordenados` | `_sorted_links` |
| `_pares_sem_duplicata` | `_unique_pairs` |
| `_recusar_regex` | `_reject_regex` |
| `_resolver` | `_resolve` |
| `_rotulo` | `_label` |
| `_segredos` | `_secrets` |
| `_sensivel` | `_sensitive` |
| `_vazio` | `_empty` |
| `argv_para_exibicao` | `display_argv` |
| `compilar_snapshot` | `compile_snapshot` |
| `montar_args` | `build_args` |
| `montar_argv_agente` | `build_agent_argv` |
| `resolver_respostas` | `resolve_answers` |
| `validar_flag` | `validate_flag` |
| `validar_opcoes_cadastro` | `validate_registry_options` |
| `validar_regex_cadastro` | `validate_registry_regex` |
| `validar_snapshot` | `validate_snapshot` |
| `validar_valor` | `validate_value` |

### `recurrence`

| Antes | Depois |
|---|---|
| `Decisao` | `Decision` |
| `HORIZONTE_PADRAO` | `DEFAULT_HORIZON` |
| `LIMITE_PERDIDAS` | `MISSED_LIMIT` |
| `POLITICAS_MISFIRE` | `MISFIRE_POLICIES` |
| `TIPOS` | `TYPES` |
| `_CACHE_MAXIMO` | `_CACHE_MAX` |
| `_UM_DIA` | `_ONE_DAY` |
| `_UM_MINUTO` | `_ONE_MINUTE` |
| `_diaria` | `_daily` |
| `_expressao` | `_expression` |
| `_hora_minuto` | `_hour_minute` |
| `_mensal` | `_monthly` |
| `_semanal` | `_weekly` |
| `_vazio` | `_empty` |
| `_vencidas` | `_due` |
| `avaliar_disparo` | `evaluate_trigger` |
| `proxima_execucao` | `next_run` |
| `proximas` | `next_runs` |
| `sem_microssegundos` | `without_microseconds` |
| `truncar_segundos` | `truncate_seconds` |
| `validar_regra` | `validate_rule` |

### `schedule_expansion`

| Antes | Depois |
|---|---|
| `Desdobro` | `Expansion` |
| `FALHAS_ATE_PAUSAR` | `FAILURES_BEFORE_PAUSE` |
| `_LogRegra` | `_RuleLog` |
| `_OCUPADO` | `_BUSY` |
| `_avancar` | `_advance` |
| `_cron_erro` | `_cron_error` |
| `_curto` | `_short` |
| `_falha` | `_failure` |
| `_montar_ticket` | `_build_ticket` |
| `_ocorrencia_duplicada` | `_duplicate_occurrence` |
| `_ocupado` | `_busy` |
| `_pausar` | `_pause` |
| `_processar` | `_process` |
| `_registrar_perdidas` | `_log_missed` |
| `_texto_resposta` | `_answer_text` |
| `eh_erro_banco` | `is_db_error` |
| `executar` | `run` |
| `processar` | `process` |

### `cron_parser`

| Antes | Depois |
|---|---|
| `CronErro` | `CronError` |
| `HORIZONTE_PADRAO` | `DEFAULT_HORIZON` |
| `TAMANHO_MAXIMO` | `MAX_LENGTH` |
| `_DIAS_SEMANA` | `_WEEKDAYS` |
| `_DIAS_SEMANA_PLURAL` | `_WEEKDAYS_PLURAL` |
| `_ESPECIAIS` | `_SPECIAL` |
| `_FAIXAS` | `_RANGES` |
| `_MESES` | `_MONTHS` |
| `_PERMITIDOS` | `_ALLOWED` |
| `_UM_MINUTO` | `_ONE_MINUTE` |
| `_campo` | `_field` |
| `_descrever_datas` | `_describe_dates` |
| `_descrever_dsem` | `_describe_weekday` |
| `_descrever_horario` | `_describe_time` |
| `_dia_casa` | `_day_matches` |
| `_dsem_quando` | `_weekday_when` |
| `_estrela` | `_star` |
| `_inteiro` | `_integer` |
| `_juntar` | `_join` |
| `_proximo_mes` | `_next_month` |
| `_seguinte` | `_next_value` |
| `_simples` | `_simple` |
| `_texto_itens` | `_items_text` |
| `_ultimo_dia` | `_last_day` |
| `descrever` | `describe` |
| `proxima` | `next` |

### `security`

| Antes | Depois |
|---|---|
| `ALGORITMO` | `ALGORITHM` |
| `CookiesSeguros` | `SecureCookies` |
| `ITERACOES` | `ITERATIONS` |
| `PREFIXO_APP` | `APP_PREFIX` |
| `SENHA_MIN` | `PASSWORD_MIN` |
| `_HASH_FICTICIO` | `_DUMMY_HASH` |
| `_PORTA_PADRAO` | `_DEFAULT_PORTS` |
| `_decompor` | `_split_hash` |
| `_derivar` | `_derive` |
| `_ip_normalizado` | `_normalized_ip` |
| `_proteger` | `_protect` |
| `adaptar_cookie_sessao` | `adapt_session_cookie` |
| `adotar` | `adopt` |
| `gerar_token_csrf` | `generate_csrf_token` |
| `hash_ficticio` | `dummy_hash` |
| `hash_reconhecido` | `is_known_hash` |
| `hash_senha` | `hash_password` |
| `ip_origem` | `client_ip` |
| `normalizar_origem` | `normalize_origin` |
| `origem_permitida` | `is_allowed_origin` |
| `precisa_rehash` | `needs_rehash` |
| `retirar_senhas` | `strip_passwords` |
| `sessao_expirada` | `is_session_expired` |
| `validar_next` | `validate_next` |
| `validar_politica_senha` | `validate_password_policy` |
| `validar_token_csrf` | `validate_csrf_token` |
| `verificar_senha` | `verify_password` |

### `masking`

| Antes | Depois |
|---|---|
| `MASCARA` | `MASK` |
| `MASCARADOR` | `MASKER` |
| `MAX_TOKEN_RETIDO` | `MAX_HELD_TOKEN` |
| `Mascarador` | `Masker` |
| `MascaradorFluxo` | `StreamMasker` |
| `TAMANHO_MINIMO` | `MIN_LENGTH` |
| `_FiltroMascara` | `_MaskFilter` |
| `_MARCA_FILTRO` | `_FILTER_MARK` |
| `_mascarar_arg` | `_mask_arg` |
| `_recuar_connect_string` | `_trim_connect_string` |
| `alimentar` | `feed` |
| `filtro_logging` | `logging_filter` |
| `instalar_filtro_em_handlers` | `install_filter_on_handlers` |
| `mascarar` | `mask` |
| `registrar_segredo` | `register_secret` |

### `path_guard`

| Antes | Depois |
|---|---|
| `ARGS_FIXOS` | `FIXED_ARGS` |
| `Codigo` | `Code` |
| `PASTAS_DO_SISTEMA` | `SYSTEM_DIRS` |
| `PathGuardErro` | `PathGuardError` |
| `TAMANHO_MAXIMO` | `MAX_LENGTH` |
| `_dentro` | `_inside` |
| `checar_pastas_proibidas` | `check_forbidden_dirs` |
| `resolver` | `resolve` |
| `validar_cadastro` | `validate_registration` |
| `validar_executavel` | `validate_executable` |
| `validar_interpretador` | `validate_interpreter` |

### `env_builder`

| Antes | Depois |
|---|---|
| `PATH_FILHO` | `CHILD_PATH` |
| `PLATAFORMAS` | `PLATFORMS` |
| `VAR_CONEXAO` | `CONNECTION_VAR` |
| `VAR_CONEXAO_SSS` | `SSS_CONNECTION_VAR` |
| `_FMT_DATA` | `_DATE_FMT` |
| `_conexao` | `_connection` |
| `_data` | `_date` |
| `_definir` | `_set` |
| `construir` | `build` |
| `dir_trabalho_script` | `script_work_dir` |
| `usuario_execucao` | `exec_user` |

### `ddl_builder`

| Antes | Depois |
|---|---|
| `CATALOGO_AMBIENTES_PADRAO` | `DEFAULT_ENVIRONMENTS` |
| `CATALOGO_FUNCIONALIDADES` | `FEATURE_CATALOG` |
| `CATALOGO_PARAMETROS_PADRAO` | `DEFAULT_PARAMETERS` |
| `CATALOGO_PERFIS_PADRAO` | `DEFAULT_PROFILES` |
| `CATALOGO_SCRIPTS_PADRAO` | `DEFAULT_SCRIPTS` |
| `CATALOGO_USUARIOS_PADRAO` | `DEFAULT_USERS` |
| `COLUNAS_REGISTRO_DESCRICOES` | `RECORD_COLUMN_DESCRIPTIONS` |
| `DICIONARIO_COLUNAS` | `COLUMN_COMMENTS` |
| `DICIONARIO_TABELAS` | `TABLE_COMMENTS` |
| `HASH_SENHA_PADRAO_HOMOLOGACAO` | `HOMOLOGATION_DEFAULT_PASSWORD_HASH` |
| `ItemDDL` | `DDLItem` |
| `ORDEM_ROLLBACK_ENTIDADES` | `ROLLBACK_ENTITY_ORDER` |
| `PAPEIS_GRANT` | `GRANT_ROLES` |
| `_formatar_coluna` | `_format_column` |
| `_linhas_seed_por_tabela` | `_seed_rows_by_table` |
| `_lista_literais` | `_literal_list` |
| `gerar_grants_por_papel` | `build_grants_by_role` |
| `gerar_instrucoes_comentarios` | `build_comment_statements` |
| `gerar_instrucoes_ddl` | `build_ddl_statements` |
| `gerar_instrucoes_rollback` | `build_rollback_statements` |
| `gerar_instrucoes_seed` | `build_seed_statements` |
| `gerar_script_ddl` | `build_ddl_script` |
| `gerar_script_implantacao_completo` | `build_full_deploy_script` |
| `gerar_script_rollback` | `build_rollback_script` |
| `gerar_script_seed` | `build_seed_script` |
| `gerar_script_validacao` | `build_validation_script` |

### `rbac.Reason` (atributo e valor)

| Antes | Depois |
|---|---|
| `DADO_INVALIDO` | `INVALID_DATA` |
| `PERFIL_INATIVO` | `PROFILE_INACTIVE` |
| `SEM_AMBIENTE` | `NO_ENVIRONMENT` |
| `SEM_FUNC` | `NO_FEATURE` |
| `SEM_HOMOLOGACAO` | `NOT_HOMOLOGATED` |
| `SEM_SCRIPT` | `NO_SCRIPT` |

### `path_guard.Code` (atributo e valor)

| Antes | Depois |
|---|---|
| `CAMINHO_NAO_NORMALIZADO` | `PATH_NOT_NORMALIZED` |
| `CAMINHO_RELATIVO` | `RELATIVE_PATH` |
| `CARACTERE_INVALIDO` | `INVALID_CHARACTER` |
| `CONTEM_PONTOS` | `HAS_DOTS` |
| `GRAVAVEL_GRUPO_OUTROS` | `GROUP_OTHER_WRITABLE` |
| `NAO_ENCONTRADO` | `NOT_FOUND` |
| `NAO_E_ARQUIVO` | `NOT_A_FILE` |
| `PASTA_DO_SISTEMA` | `SYSTEM_DIR` |
| `PASTA_DO_SSS` | `SSS_DIR` |
| `SEM_ACESSO` | `NO_ACCESS` |
| `SEPARADOR_INVALIDO` | `INVALID_SEPARATOR` |

### Códigos de saúde (`agents_service`; atributo e valor)

| Antes | Depois |
|---|---|
| `ATRASADO` | `DELAYED` |
| `EM_RISCO` | `AT_RISK` |

### `recurrence.Decision` (campos)

| Antes | Depois |
|---|---|
| `concluir` | `complete` |
| `cron_erro` | `cron_error` |
| `gerar_ticket` | `create_ticket` |
| `nova_data` | `next_date` |
| `ocorrencia` | `occurrence` |
| `perdidas` | `missed` |

### Repositório de saída

| Antes | Depois |
|---|---|
| `RepoSchedulerOutput.concluir` | `complete` |

## 7. Validação do bloco 3a

* Suítes em 3.6.0, 3.6.8 e 3.13.2, bateria Oracle, testes progressivos nos cinco agregados, percurso real das telas e conferência de resíduos.
* Achados na conferência e corrigidos: nome reexportado (`recurrence.CronErro`, em `schedule_expansion`) que a ferramenta por escopo não alcança; módulo falso de teste (`masking_stub`) com o nome antigo; códigos compostos (`PATH_GUARD_<código>`) que a troca por palavra inteira não pega.

## 8. Bloco 3b (services)

Módulos `admin_crud`, `admin_*_service`, `agents_service`, `audit_service`, `auth_service`, `permissions_service`, `schedules_service` e `ticket_service`. Classes `Servico*` → `*Service`; a fábrica por módulo `_servico`/`_padrao`/`_lock_padrao` → `_service`/`_default`/`_default_lock`; a função de módulo `listar` → `list_page` (D7). Os controllers só tiveram as chamadas atualizadas; nomes das funções de controller (URLs), variáveis de tela e atributos de sessão (`session.sessao_epoch`) ficam para o CR-016d.

Métodos mudaram em todas as classes que os definem, inclusive fakes de teste e `RepoSchedulerOutput._incluir`, `health.Verificacao._ambientes`, conferido que nenhuma classe já tinha o nome novo.

### Nomes de módulo

#### `admin_crud`

| Antes | Depois |
|---|---|
| `AcessoNegado` | `AccessDenied` |
| `CAMPO_GERAL` | `GENERAL_FIELD` |
| `LIMITE_DETALHE` | `DETAIL_LIMIT` |
| `MARCADOR_PREENCHIDO` | `FILLED_MARKER` |
| `MARCADOR_VAZIO` | `EMPTY_MARKER` |
| `MSG_CONFLITO` | `MSG_CONFLICT` |
| `MSG_CONTROLE` | `MSG_CONTROL_CHARS` |
| `MSG_ESPACOS` | `MSG_SPACES` |
| `MSG_FALHA` | `MSG_FAILURE` |
| `OperacaoNegada` | `OperationDenied` |
| `_RE_CONTROLE` | `_RE_CONTROL` |
| `_SETA` | `_ARROW` |
| `_VAZIO` | `_EMPTY` |
| `_exibir` | `_display` |
| `auditoria` | `audit_entry` |
| `detalhe_alteracoes` | `changes_detail` |
| `detalhe_insercao` | `insert_detail` |
| `detalhe_livre` | `free_detail` |
| `esperado` | `expected` |
| `exigir_admin` | `require_admin` |
| `exigir_func` | `require_feature` |
| `hash_estado` | `state_hash` |
| `identificador` | `identifier` |
| `limitar` | `truncate_detail` |
| `marcador_sensivel` | `sensitive_marker` |
| `normalizar` | `normalize` |
| `texto` | `text` |
| `texto_livre` | `free_text` |
| `versao` | `version` |

#### `admin_environments_service`

| Antes | Depois |
|---|---|
| `AVISO_DESATIVACAO` | `DEACTIVATION_WARNING` |
| `CAMPOS_EDITAVEIS` | `EDITABLE_FIELDS` |
| `CAMPOS_INSERCAO` | `INSERT_FIELDS` |
| `FUNCIONALIDADE` | `FEATURE` |
| `MSG_CONEXAO_CREDENCIAL` | `MSG_CONNECTION_CREDENTIAL` |
| `MSG_CONEXAO_INVALIDA` | `MSG_CONNECTION_INVALID` |
| `MSG_CONEXAO_TAMANHO` | `MSG_CONNECTION_LENGTH` |
| `MSG_DESCRICAO_TAMANHO` | `MSG_DESCRIPTION_LENGTH` |
| `MSG_NOME_DUPLICADO` | `MSG_NAME_DUPLICATE` |
| `MSG_NOME_INVALIDO` | `MSG_NAME_INVALID` |
| `MSG_NOME_OBRIGATORIO` | `MSG_NAME_REQUIRED` |
| `MSG_NOME_RESERVADO` | `MSG_NAME_RESERVED` |
| `ServicoAdminAmbientes` | `AdminEnvironmentsService` |
| `TAMANHO_CONEXAO` | `CONNECTION_MAX_LENGTH` |
| `TAMANHO_DESCRICAO` | `DESCRIPTION_MAX_LENGTH` |
| `_CAMPO_POR_CONSTRAINT` | `_FIELD_BY_CONSTRAINT` |
| `_RE_ALIAS_TNS` | `_RE_TNS_ALIAS` |
| `_RE_FILTRO_NOME` | `_RE_NAME_FILTER` |
| `_RE_NOME` | `_RE_NAME` |
| `_SCRIPTS_PAGINA` | `_SCRIPTS_PAGE` |
| `_TAMANHO_CONTAGEM` | `_COUNT_PAGE_SIZE` |
| `_lock_padrao` | `_default_lock` |
| `_padrao` | `_default` |
| `_servico` | `_service` |
| `alternar_ativo` | `toggle_active` |
| `formulario` | `form` |
| `listar` | `list_page` |
| `normalizar_filtros` | `normalize_filters` |
| `salvar` | `save` |
| `validar_conexao` | `validate_connection` |

#### `admin_parameters_service`

| Antes | Depois |
|---|---|
| `AVISO_SENSIVEL` | `SENSITIVE_WARNING` |
| `CAMPOS_EDITAVEIS` | `EDITABLE_FIELDS` |
| `CAMPOS_INSERCAO` | `INSERT_FIELDS` |
| `FUNCIONALIDADE` | `FEATURE` |
| `MASCARA` | `MASK` |
| `MSG_CODIGO_DUPLICADO` | `MSG_CODE_DUPLICATE` |
| `MSG_CODIGO_INVALIDO` | `MSG_CODE_INVALID` |
| `MSG_CODIGO_OBRIGATORIO` | `MSG_CODE_REQUIRED` |
| `MSG_DESCRICAO_TAMANHO` | `MSG_DESCRIPTION_LENGTH` |
| `MSG_LABEL_OBRIGATORIO` | `MSG_LABEL_REQUIRED` |
| `MSG_LABEL_TAMANHO` | `MSG_LABEL_LENGTH` |
| `MSG_OPCOES_PROIBIDAS` | `MSG_OPTIONS_FORBIDDEN` |
| `MSG_PADRAO_TAMANHO` | `MSG_DEFAULT_LENGTH` |
| `MSG_REGEX_SO_ADMIN` | `MSG_REGEX_ADMIN_ONLY` |
| `MSG_REGEX_SO_TEXTO` | `MSG_REGEX_TEXT_ONLY` |
| `MSG_REGEX_TAMANHO` | `MSG_REGEX_LENGTH` |
| `MSG_SENSIVEL_MONOTONICO` | `MSG_SENSITIVE_ONE_WAY` |
| `MSG_TESTE_REGEX_ADMIN` | `MSG_REGEX_TEST_ADMIN` |
| `MSG_TIPO_COM_REGEX` | `MSG_TYPE_WITH_REGEX` |
| `MSG_TIPO_INVALIDO` | `MSG_TYPE_INVALID` |
| `ROTULOS_TIPO` | `TYPE_LABELS` |
| `ServicoAdminParametros` | `AdminParametersService` |
| `TAMANHO_DESCRICAO` | `DESCRIPTION_MAX_LENGTH` |
| `TAMANHO_LABEL` | `LABEL_MAX_LENGTH` |
| `TAMANHO_PADRAO` | `DEFAULT_MAX_LENGTH` |
| `TAMANHO_REGEX` | `REGEX_MAX_LENGTH` |
| `_CAMPO_POR_CONSTRAINT` | `_FIELD_BY_CONSTRAINT` |
| `_RE_CODIGO` | `_RE_CODE` |
| `_RE_FILTRO` | `_RE_FILTER` |
| `_lista_scripts` | `_script_list` |
| `_lock_padrao` | `_default_lock` |
| `_padrao` | `_default` |
| `_padrao_texto` | `_default_text` |
| `_servico` | `_service` |
| `_versao` | `_version` |
| `alternar_ativo` | `toggle_active` |
| `formulario` | `form` |
| `listar` | `list_page` |
| `msg_flag_nomeado` | `msg_named_flag` |
| `msg_tipo_vinculado` | `msg_linked_type` |
| `msg_vinculo_ativo` | `msg_active_link` |
| `normalizar_filtros` | `normalize_filters` |
| `opcoes_em_pares` | `options_as_pairs` |
| `salvar` | `save` |
| `testar` | `test_regex` |

#### `admin_profiles_service`

| Antes | Depois |
|---|---|
| `AFETADOS_MAX` | `AFFECTED_MAX` |
| `AVISO_ADMIN` | `ADMIN_WARNING` |
| `AVISO_DESATIVACAO` | `DEACTIVATION_WARNING` |
| `CAMPOS_EDITAVEIS` | `EDITABLE_FIELDS` |
| `CAMPOS_INSERCAO` | `INSERT_FIELDS` |
| `FUNCIONALIDADE` | `FEATURE` |
| `MSG_AUTO_ADMIN` | `MSG_SELF_ADMIN` |
| `MSG_AUTO_DESATIVAR` | `MSG_SELF_DEACTIVATE` |
| `MSG_DESCRICAO_TAMANHO` | `MSG_DESCRIPTION_LENGTH` |
| `MSG_MATRIZ_ID_INVALIDO` | `MSG_MATRIX_ID_INVALID` |
| `MSG_MATRIZ_INATIVO` | `MSG_MATRIX_INACTIVE` |
| `MSG_NOME_DUPLICADO` | `MSG_NAME_DUPLICATE` |
| `MSG_NOME_INVALIDO` | `MSG_NAME_INVALID` |
| `MSG_NOME_OBRIGATORIO` | `MSG_NAME_REQUIRED` |
| `MSG_SO_ADMIN` | `MSG_ADMIN_ONLY` |
| `MSG_ULTIMO_ADMIN` | `MSG_LAST_ADMIN` |
| `ServicoAdminPerfis` | `AdminProfilesService` |
| `TAMANHO_DESCRICAO` | `DESCRIPTION_MAX_LENGTH` |
| `_CAMPO_POR_CONSTRAINT` | `_FIELD_BY_CONSTRAINT` |
| `_CATALOGO_MAX` | `_CATALOG_MAX` |
| `_PREFIXOS` | `_PREFIXES` |
| `_RE_FILTRO_NOME` | `_RE_NAME_FILTER` |
| `_RE_NOME` | `_RE_NAME` |
| `_SEM_GRUPO` | `_NO_GROUP` |
| `_TAMANHO_CONTAGEM` | `_COUNT_PAGE_SIZE` |
| `_lock_padrao` | `_default_lock` |
| `_padrao` | `_default` |
| `_servico` | `_service` |
| `alternar_ativo` | `toggle_active` |
| `diff_matriz` | `matrix_diff` |
| `formulario` | `form` |
| `listar` | `list_page` |
| `matriz` | `matrix` |
| `normalizar_filtros` | `normalize_filters` |
| `quem_pode` | `who_can` |
| `salvar` | `save` |
| `salvar_matriz` | `save_matrix` |

#### `admin_scripts_service`

| Antes | Depois |
|---|---|
| `AVISO_DESATIVACAO` | `DEACTIVATION_WARNING` |
| `CAMPOS_EDITAVEIS` | `EDITABLE_FIELDS` |
| `CAMPOS_INSERCAO` | `INSERT_FIELDS` |
| `FUNCIONALIDADE` | `FEATURE` |
| `MASCARA` | `MASK` |
| `MENSAGENS_PATH` | `PATH_MESSAGES` |
| `MSG_CONTROLE` | `MSG_CONTROL_CHARS` |
| `MSG_HOMOLOG_INATIVO` | `MSG_HOMOLOG_INACTIVE` |
| `MSG_HOMOLOG_INVALIDA` | `MSG_HOMOLOG_INVALID` |
| `MSG_NENHUM_VINCULADO` | `MSG_NONE_LINKED` |
| `MSG_NOME_DUPLICADO` | `MSG_NAME_DUPLICATE` |
| `MSG_NOME_OBRIGATORIO` | `MSG_NAME_REQUIRED` |
| `MSG_NOME_RESERVADO` | `MSG_NAME_RESERVED` |
| `MSG_PARALELO` | `MSG_PARALLEL` |
| `MSG_PATH_OBRIGATORIO` | `MSG_PATH_REQUIRED` |
| `MSG_SIGILOSO_INVALIDO` | `MSG_SENSITIVE_INVALID` |
| `MSG_TIPO_PARAM` | `MSG_PARAM_TYPE` |
| `MSG_VINCULOS_INVALIDOS` | `MSG_LINKS_INVALID` |
| `MSG_VINCULO_DUPLICADO` | `MSG_LINK_DUPLICATE` |
| `MSG_VINCULO_INATIVO` | `MSG_LINK_INACTIVE` |
| `MSG_VINCULO_NENHUM` | `MSG_LINK_NONE` |
| `OBS_VALIDACAO` | `VALIDATION_NOTE` |
| `ROTULOS_INTERPRETADOR` | `INTERPRETER_LABELS` |
| `ROTULOS_TIPO_PARAM` | `PARAM_TYPE_LABELS` |
| `ServicoAdminScripts` | `AdminScriptsService` |
| `TAMANHOS` | `MAX_LENGTHS` |
| `TAMANHO_PADRAO_SUB` | `SUB_DEFAULT_MAX_LENGTH` |
| `TIMEOUT_MAXIMO` | `MAX_TIMEOUT` |
| `VINCULOS_MAXIMO` | `MAX_LINKS` |
| `_CAMPO_POR_CONSTRAINT` | `_FIELD_BY_CONSTRAINT` |
| `_CATALOGO_MAX` | `_CATALOG_MAX` |
| `_RE_CONTROLE` | `_RE_CONTROL` |
| `_RE_FILTRO` | `_RE_FILTER` |
| `_RE_INTEIRO` | `_RE_INTEGER` |
| `_TAMANHO_CONTAGEM` | `_COUNT_PAGE_SIZE` |
| `_lidos` | `_read_back` |
| `_lock_padrao` | `_default_lock` |
| `_padrao` | `_default` |
| `_servico` | `_service` |
| `_versao_vinculos` | `_links_version` |
| `alternar_ativo` | `toggle_active` |
| `formulario` | `form` |
| `homologacao` | `homologation` |
| `listar` | `list_page` |
| `msg_nomeado_sem_flag` | `msg_named_without_flag` |
| `normalizar_filtros` | `normalize_filters` |
| `parametros` | `parameters` |
| `previa` | `preview` |
| `salvar` | `save` |
| `salvar_homologacao` | `save_homologation` |
| `salvar_parametros` | `save_parameters` |

#### `admin_users_service`

| Antes | Depois |
|---|---|
| `AJUDA_POLITICA` | `POLICY_HELP` |
| `AVISO_DESATIVACAO` | `DEACTIVATION_WARNING` |
| `CAMPOS_EDITAVEIS` | `EDITABLE_FIELDS` |
| `CAMPOS_INSERCAO` | `INSERT_FIELDS` |
| `FUNCIONALIDADE` | `FEATURE` |
| `MSG_AUTO_DESATIVAR` | `MSG_SELF_DEACTIVATE` |
| `MSG_AUTO_PERFIL` | `MSG_SELF_PROFILE` |
| `MSG_AUTO_SENHA` | `MSG_SELF_PASSWORD` |
| `MSG_CONFIRMACAO` | `MSG_CONFIRMATION` |
| `MSG_LOGIN_DUPLICADO` | `MSG_LOGIN_DUPLICATE` |
| `MSG_LOGIN_INVALIDO` | `MSG_LOGIN_INVALID` |
| `MSG_LOGIN_OBRIGATORIO` | `MSG_LOGIN_REQUIRED` |
| `MSG_NOME_OBRIGATORIO` | `MSG_NAME_REQUIRED` |
| `MSG_NOME_TAMANHO` | `MSG_NAME_LENGTH` |
| `MSG_PERFIL_INVALIDO` | `MSG_PROFILE_INVALID` |
| `MSG_SENHA_LONGA` | `MSG_PASSWORD_TOO_LONG` |
| `MSG_SENHA_OBRIGATORIA` | `MSG_PASSWORD_REQUIRED` |
| `MSG_SO_ADMIN` | `MSG_ADMIN_ONLY` |
| `MSG_ULTIMO_ADMIN` | `MSG_LAST_ADMIN` |
| `ServicoAdminUsuarios` | `AdminUsersService` |
| `TAMANHO_NOME` | `NAME_MAX_LENGTH` |
| `_CAMPOS_PUBLICOS` | `_PUBLIC_FIELDS` |
| `_CAMPO_POR_CONSTRAINT` | `_FIELD_BY_CONSTRAINT` |
| `_PERFIS_MAX` | `_PROFILES_MAX` |
| `_RE_FILTRO` | `_RE_FILTER` |
| `_lock_padrao` | `_default_lock` |
| `_padrao` | `_default` |
| `_servico` | `_service` |
| `alternar_ativo` | `toggle_active` |
| `desbloquear` | `unlock` |
| `formulario` | `form` |
| `listar` | `list_page` |
| `normalizar_filtros` | `normalize_filters` |
| `perfis` | `profiles` |
| `publico` | `public_view` |
| `redefinir_senha` | `reset_password` |
| `salvar` | `save` |

#### `agents_service`

| Antes | Depois |
|---|---|
| `FUNCIONALIDADE` | `FEATURE` |
| `Limiares` | `Thresholds` |
| `ORDEM_SAUDE` | `HEALTH_ORDER` |
| `ServicoAgentes` | `AgentsService` |
| `_SAUDE` | `_HEALTH` |
| `_lock_padrao` | `_default_lock` |
| `_padrao` | `_default` |
| `_servico` | `_service` |
| `formatar_idade` | `format_age` |
| `legenda` | `legend` |
| `painel` | `dashboard` |
| `saude` | `health` |
| `saude_info` | `health_info` |
| `tickets_do_agente` | `agent_tickets` |

#### `audit_service`

| Antes | Depois |
|---|---|
| `ACAO_EXPORTAR` | `EXPORT_ACTION` |
| `ACOES` | `ACTIONS` |
| `CABECALHO_CSV` | `CSV_HEADER` |
| `CAMPOS_FILTRO` | `FILTER_FIELDS` |
| `DETALHE_CURTO` | `SHORT_DETAIL` |
| `ENTIDADES` | `ENTITIES` |
| `ENTIDADE_AUDITORIA` | `AUDIT_ENTITY` |
| `FUNCIONALIDADE` | `FEATURE` |
| `FiltrosInvalidos` | `InvalidFilters` |
| `LIMITE_EXPORTACAO` | `EXPORT_LIMIT` |
| `MSG_ACAO` | `MSG_ACTION` |
| `MSG_ATOR` | `MSG_ACTOR` |
| `MSG_DATA` | `MSG_DATE` |
| `MSG_ENTIDADE` | `MSG_ENTITY` |
| `MSG_ENTIDADE_ID` | `MSG_ENTITY_ID` |
| `MSG_INTERVALO` | `MSG_RANGE` |
| `MSG_PERIODO` | `MSG_PERIOD` |
| `MSG_PERIODO_SELETIVO` | `MSG_SELECTIVE_PERIOD` |
| `PERIODO_MAX_DIAS` | `MAX_PERIOD_DAYS` |
| `PERIODO_MAX_SELETIVO_DIAS` | `MAX_SELECTIVE_PERIOD_DAYS` |
| `PERIODO_PADRAO_DIAS` | `DEFAULT_PERIOD_DAYS` |
| `ServicoAuditoria` | `AuditService` |
| `TAMANHO_MAX` | `MAX_LENGTH` |
| `TELAS_ENTIDADE` | `ENTITY_SCREENS` |
| `_FORMATO_CSV` | `_CSV_FORMAT` |
| `_FORMATO_DIA` | `_DAY_FORMAT` |
| `_LINHAS_POR_BLOCO` | `_LINES_PER_CHUNK` |
| `_PREFIXOS_PERIGOSOS` | `_DANGEROUS_PREFIXES` |
| `_RE_ATOR` | `_RE_ACTOR` |
| `_RE_DIA` | `_RE_DAY` |
| `_descrever_filtros` | `_describe_filters` |
| `_dia` | `_day` |
| `_lock_padrao` | `_default_lock` |
| `_mascarar` | `_mask` |
| `_padrao` | `_default` |
| `_servico` | `_service` |
| `_texto` | `_text` |
| `exportar_csv` | `export_csv` |
| `filtros_padrao` | `default_filters` |
| `filtros_repo` | `repo_filters` |
| `linha_csv` | `csv_row` |
| `link_entidade` | `entity_link` |
| `listar` | `list_page` |
| `neutralizar_csv` | `neutralize_csv` |
| `normalizar_filtros` | `normalize_filters` |

#### `auth_service`

| Antes | Depois |
|---|---|
| `CACHE_MATRIZ_MAX` | `MATRIX_CACHE_MAX` |
| `ENTIDADE` | `ENTITY` |
| `MSG_CONFIRMACAO` | `MSG_CONFIRMATION` |
| `MSG_GENERICA` | `MSG_GENERIC` |
| `MSG_SENHA_ATUAL` | `MSG_CURRENT_PASSWORD` |
| `SENHA_MAX` | `PASSWORD_MAX` |
| `SIMULADOS_MAX` | `SIMULATED_MAX` |
| `ServicoAuth` | `AuthService` |
| `_lock_padrao` | `_default_lock` |
| `_padrao` | `_default` |
| `_servico` | `_service` |
| `autenticar` | `authenticate` |
| `revalidar` | `revalidate` |
| `sessao_epoch` | `session_epoch` |
| `trocar_senha` | `change_password` |

#### `permissions_service`

| Antes | Depois |
|---|---|
| `FRASE_ADMIN` | `ADMIN_PHRASE` |
| `FRASE_MAIS_ACESSO` | `MORE_ACCESS_PHRASE` |
| `FRASE_SEM_EXEC` | `NO_EXEC_PHRASE` |
| `MOTIVO_AMBIENTE_INATIVO` | `REASON_ENVIRONMENT_INACTIVE` |
| `MOTIVO_SCRIPT_INATIVO` | `REASON_SCRIPT_INACTIVE` |
| `MOTIVO_SEM_FUNC` | `REASON_NO_FEATURE` |
| `MOTIVO_SEM_HOMOLOGACAO` | `REASON_NOT_HOMOLOGATED` |
| `ServicoPermissoes` | `PermissionsService` |
| `_CATALOGO_MAX` | `_CATALOG_MAX` |
| `_lock_padrao` | `_default_lock` |
| `_padrao` | `_default` |
| `_servico` | `_service` |
| `montar` | `build` |

#### `schedules_service`

| Antes | Depois |
|---|---|
| `AGENDA_POR_REGRA` | `AGENDA_PER_RULE` |
| `CAMPOS_AUDITORIA` | `AUDIT_FIELDS` |
| `CAMPOS_VERSAO` | `VERSION_FIELDS` |
| `DIAS_SEMANA` | `WEEKDAYS` |
| `FORMATO_CAMPO_DATA` | `DATE_FIELD_FORMAT` |
| `FUNCIONALIDADE` | `FEATURE` |
| `MASCARA` | `MASK` |
| `MOTIVOS_PAUSA` | `PAUSE_REASONS` |
| `MSG_DATA_INVALIDA` | `MSG_DATE_INVALID` |
| `MSG_INICIO_UNICA` | `MSG_ONCE_START` |
| `MSG_JA_ATIVA` | `MSG_ALREADY_ACTIVE` |
| `MSG_JA_PAUSADA` | `MSG_ALREADY_PAUSED` |
| `MSG_NOME_OBRIGATORIO` | `MSG_NAME_REQUIRED` |
| `MSG_NOME_TAMANHO` | `MSG_NAME_LENGTH` |
| `MSG_ORIENTACAO_RETOMAR` | `MSG_RESUME_GUIDANCE` |
| `MSG_PRIORIDADE` | `MSG_PRIORITY` |
| `MSG_PRIORIDADE_ADMIN` | `MSG_PRIORITY_ADMIN` |
| `MSG_RETOMAR_SEM_PROXIMA` | `MSG_RESUME_NO_NEXT_RUN` |
| `MSG_SEM_PERMISSAO` | `MSG_NO_PERMISSION` |
| `MSG_SEM_PROXIMA` | `MSG_NO_NEXT_RUN` |
| `MSG_TIPO` | `MSG_TYPE` |
| `PRIORIDADE_PADRAO` | `DEFAULT_PRIORITY` |
| `QTD_PREVIA` | `PREVIEW_COUNT` |
| `ROTULOS_TIPO` | `TYPE_LABELS` |
| `ServicoAgendamentos` | `SchedulesService` |
| `TAMANHO_NOME` | `NAME_MAX_LENGTH` |
| `_ABREV_DIA` | `_DAY_ABBREV` |
| `_AGENDA_CONTAGEM_MAX` | `_AGENDA_COUNT_MAX` |
| `_AGENDA_PAGINA` | `_AGENDA_PAGE` |
| `_CAMPOS_ESPERADO` | `_EXPECTED_FIELDS` |
| `_CAMPOS_INSERCAO` | `_INSERT_FIELDS` |
| `_FORMATOS_DATA` | `_DATE_FORMATS` |
| `_NOMES_DIA` | `_DAY_NAMES` |
| `_RE_AMBIENTE` | `_RE_ENVIRONMENT` |
| `_SETA` | `_ARROW` |
| `_data` | `_date` |
| `_dias_semana` | `_weekdays` |
| `_estado` | `_state` |
| `_lock_padrao` | `_default_lock` |
| `_padrao` | `_default` |
| `_parametros` | `_parameters` |
| `_rotulo_dia` | `_day_label` |
| `_serializar` | `_serialize` |
| `_servico` | `_service` |
| `_ultimo` | `_last` |
| `_valor_campo_data` | `_date_field_value` |
| `_vazio` | `_empty` |
| `descrever_regra` | `describe_rule` |
| `formatar_data` | `format_date` |
| `formatar_previa` | `format_preview` |
| `formulario` | `form` |
| `listar` | `list_page` |
| `normalizar_filtros` | `normalize_filters` |
| `pausar` | `pause` |
| `previa` | `preview` |
| `retomar` | `resume` |
| `salvar` | `save` |
| `situacao` | `rule_state` |
| `versao` | `version` |

#### `ticket_service`

| Antes | Depois |
|---|---|
| `AMBIENTE_PRODUCAO` | `PRODUCTION_ENVIRONMENT` |
| `AcessoNegado` | `AccessDenied` |
| `CAMPO_AGENDAMENTO` | `SCHEDULED_AT_FIELD` |
| `CAMPO_GERAL` | `GENERAL_FIELD` |
| `CAMPO_PRIORIDADE` | `PRIORITY_FIELD` |
| `ErroReexecucao` | `RerunError` |
| `FILTROS` | `FILTERS` |
| `HISTORICO_DIAS` | `HISTORY_DAYS` |
| `HISTORICO_LIMITE` | `HISTORY_LIMIT` |
| `MARCADOR_DOWNLOAD_INTERROMPIDO` | `DOWNLOAD_INTERRUPTED_MARKER` |
| `MSG_CANCELAMENTO` | `MSG_CANCEL` |
| `MSG_FALHA_CRIAR` | `MSG_CREATE_FAILED` |
| `MSG_SCRIPT_INDISPONIVEL` | `MSG_SCRIPT_UNAVAILABLE` |
| `MSG_ULTIMA_MUDOU` | `MSG_LAST_CHANGED` |
| `MSG_ULTIMA_SENSIVEL` | `MSG_LAST_SENSITIVE` |
| `ORIGENS` | `SOURCES` |
| `OffsetInvalido` | `InvalidOffset` |
| `PRIORIDADE_PADRAO` | `DEFAULT_PRIORITY` |
| `ROTULOS_PRIORIDADE` | `PRIORITY_LABELS` |
| `SAIDA_FATIA_BYTES` | `OUTPUT_SLICE_BYTES` |
| `STATUS_CANCELAVEIS` | `CANCELLABLE_STATUSES` |
| `STATUS_TERMINAIS` | `TERMINAL_STATUSES` |
| `ServicoTicket` | `TicketService` |
| `_AMBIENTES_MAX` | `_ENVIRONMENTS_MAX` |
| `_FILHOS_MAX` | `_CHILDREN_MAX` |
| `_FORMATOS_AGENDAMENTO` | `_SCHEDULED_AT_FORMATS` |
| `_FORMATO_DIA` | `_DAY_FORMAT` |
| `_RE_AMBIENTE` | `_RE_ENVIRONMENT` |
| `_argv_exibicao` | `_display_argv` |
| `_dia` | `_day` |
| `_duracao` | `_duration` |
| `_filtros_repo` | `_repo_filters` |
| `_lock_padrao` | `_default_lock` |
| `_opcoes` | `_options` |
| `_ordenados` | `_sorted_items` |
| `_padrao` | `_default` |
| `_servico` | `_service` |
| `_texto_resposta` | `_answer_text` |
| `_ultimo` | `_last` |
| `ambientes_disponiveis` | `available_environments` |
| `blocos_log` | `log_chunks` |
| `blocos_saida` | `output_chunks` |
| `cancelar` | `cancel` |
| `catalogo_rotinas` | `routine_catalog` |
| `criar_ticket` | `create_ticket` |
| `detalhe` | `detail` |
| `historico_script` | `script_history` |
| `ler_log` | `read_log` |
| `listar` | `list_page` |
| `normalizar_filtros` | `normalize_filters` |
| `opcoes_filtro` | `filter_options` |
| `pode_consultar` | `can_query` |
| `preparar_formulario` | `prepare_form` |
| `preparar_reexecucao` | `prepare_rerun` |
| `previa` | `preview` |
| `reexecutar` | `rerun` |
| `resumo_disparo` | `trigger_summary` |
| `resumo_inicial` | `home_summary` |
| `scripts_disponiveis` | `available_scripts` |
| `tem_ultima_execucao` | `has_last_run` |
| `ultimas_respostas` | `last_answers` |
| `visivel` | `is_visible` |

### Métodos

| Antes | Depois |
|---|---|
| `_agendamento` | `_scheduled_at` |
| `_agendamentos_ativos` | `_active_schedules` |
| `_agora` | `_now` |
| `_alterar` | `_update` |
| `_ambiente_por_nome` | `_environment_by_name` |
| `_ambientes` | `_environments` |
| `_ambientes_executaveis` | `_executable_environments` |
| `_auditavel` | `_auditable` |
| `_autorizar` | `_authorize` |
| `_avaliar_problema_desdobro` | `_check_expansion_problem` |
| `_aviso_sobreposicao` | `_overlap_warning` |
| `_blocos` | `_chunks` |
| `_bloqueado` | `_is_locked` |
| `_catalogo_matriz` | `_matrix_catalog` |
| `_codigos_sensiveis` | `_sensitive_codes` |
| `_compilar` | `_compile` |
| `_dependencias` | `_dependencies` |
| `_descrever` | `_describe` |
| `_detalhe_alteracao` | `_change_detail` |
| `_dicionario` | `_dictionary` |
| `_escopo_consulta` | `_query_scope` |
| `_escopo_execucoes` | `_runs_scope` |
| `_exemplo` | `_example` |
| `_exigir_admin` | `_require_admin` |
| `_falha_inexistente` | `_unknown_login` |
| `_falha_senha` | `_wrong_password` |
| `_gravar` | `_save` |
| `_hoje` | `_today` |
| `_incluir` | `_insert` |
| `_inteiro` | `_integer` |
| `_matriz` | `_matrix` |
| `_montar_ctx` | `_build_ctx` |
| `_montar_vinculos` | `_build_links` |
| `_motivo` | `_reason` |
| `_negar` | `_deny` |
| `_nome` | `_name` |
| `_nomes_scripts` | `_script_names` |
| `_obter` | `_get` |
| `_obter_visivel` | `_get_visible` |
| `_padrao_exibicao` | `_display_default` |
| `_para_auditoria` | `_for_audit` |
| `_parametros_auditoria` | `_audit_params` |
| `_perfil_admin` | `_admin_profile` |
| `_perfil_ativo` | `_active_profile` |
| `_pode_executar_vigente` | `_can_execute_now` |
| `_pode_reexecutar_regra` | `_can_rerun_by_rule` |
| `_pode_ver` | `_can_view` |
| `_pre_tipo_param` | `_param_type_precheck` |
| `_prioridade` | `_priority` |
| `_proprio` | `_is_own` |
| `_proxima` | `_next_run` |
| `_recompilar` | `_recompile` |
| `_registrar_falha` | `_record_failure` |
| `_regra` | `_rule` |
| `_regra_form` | `_form_rule` |
| `_reiniciar_se_expirado` | `_reset_if_expired` |
| `_reservado` | `_reserved` |
| `_respostas` | `_answers` |
| `_respostas_exibicao` | `_display_answers` |
| `_respostas_originais` | `_original_answers` |
| `_rotulos` | `_labels` |
| `_senha` | `_password` |
| `_telas` | `_screens` |
| `_texto_campo` | `_field_text` |
| `_ticket_reexecutavel` | `_rerunnable_ticket` |
| `_ticket_visivel` | `_visible_ticket` |
| `_ultimo_ticket` | `_last_ticket` |
| `_validar` | `_validate` |
| `_vinculos` | `_links` |
| `_violacao` | `_violation` |
| `agendamentos_ativos` | `active_schedules` |
| `alternar_ativo` | `toggle_active` |
| `ambientes_disponiveis` | `available_environments` |
| `autenticar` | `authenticate` |
| `autorizar` | `authorize` |
| `blocos_log` | `log_chunks` |
| `blocos_saida` | `output_chunks` |
| `bloqueado` | `is_locked` |
| `cancelar` | `cancel` |
| `catalogo_rotinas` | `routine_catalog` |
| `criar_ticket` | `create_ticket` |
| `detalhe` | `detail` |
| `exportar_csv` | `export_csv` |
| `formulario` | `form` |
| `homologacao` | `homologation` |
| `ler_log` | `read_log` |
| `matriz` | `matrix` |
| `montar` | `build` |
| `normalizar_filtros` | `normalize_filters` |
| `opcoes_filtro` | `filter_options` |
| `painel` | `dashboard` |
| `pode_consultar` | `can_query` |
| `preparar_formulario` | `prepare_form` |
| `preparar_reexecucao` | `prepare_rerun` |
| `previa` | `preview` |
| `quem_pode` | `who_can` |
| `redefinir_senha` | `reset_password` |
| `reexecutar` | `rerun` |
| `resumo_disparo` | `trigger_summary` |
| `resumo_inicial` | `home_summary` |
| `revalidar` | `revalidate` |
| `salvar` | `save` |
| `salvar_homologacao` | `save_homologation` |
| `salvar_matriz` | `save_matrix` |
| `salvar_parametros` | `save_parameters` |
| `scripts_disponiveis` | `available_scripts` |
| `scripts_homologados` | `homologated_scripts` |
| `sessao_epoch` | `session_epoch` |
| `tem_ultima_execucao` | `has_last_run` |
| `testar` | `test_regex` |
| `tickets_do_agente` | `agent_tickets` |
| `trocar_senha` | `change_password` |
| `ultimas_respostas` | `last_answers` |
| `usuarios_afetados` | `affected_users` |
| `usuarios_ativos` | `active_users` |
| `validar_caminho` | `validate_path` |
| `vinculos` | `links` |
| `visivel` | `is_visible` |

## 9. Validação do bloco 3b

* Suítes em 3.6.0, 3.6.8 e 3.13.2, bateria Oracle, testes progressivos nos cinco agregados, percurso real das telas e conferência de resíduos.
* Achados na conferência e corrigidos: código Python nas views chamando service pelo nome antigo (`admin_parameters_service.opcoes_em_pares` em `admin_parametros/form.html`, que daria erro 500 na tela de parâmetros); nomes reexportados lidos por outro módulo nos testes (`usr_mod.CAMPO_GERAL`, `agents_service.Limiares`); o atributo de sessão `session.sessao_epoch`, que a renomeação de métodos tinha alcançado, restaurado. A declaração `global _padrao` dos 11 services não acompanhou a renomeação para `_default` (`UnboundLocalError` no login): os testes injetam o service e não passam por `_service()`, e só o percurso real pegou.

## 10. Bloco 4a (camada de processo)

Módulos `os_platform` (pacote e `posix`), `executor` e `log_paths`, com os atributos de instância de `Execution`, `Process`, `FailureAfterSpawn` e `_Lock`.

Decisões aprovadas (2026-10-21):

| # | Decisão | Resumo |
|---|---|---|
| D9 | Valores internos | Fases do executor `FIM` → `END` e `SEM_IDENTIDADE` → `NO_IDENTITY` (no 4b: estados da fase de saída e resultados do `log_pump`). Nada disso vai para o banco |
| D10 | Marcadores | Chaves de `.sss_spawn`/`.sss_proc`: `usuario_execucao` → `exec_user`, `monotonico` → `monotonic`, `parede` → `wall`. Troca direta: atualizar o agente sem tickets `RUNNING` (DEPLOYMENT §18) |
| D11 | Nomes físicos | `log_dir/interno/` → `log_dir/internal/`; o nome de ambiente reservado passa de `INTERNO` a `INTERNAL` (CR-009). No 4b: `saida.zip` → `output.zip` no `work_dir`; o nome do download para o usuário fica para o CR-016d |
| D12 | Atributos de instância | Entram no bloco, conferidos contra homônimos (`fase` do `DDLItem` e `caminho` do `purge.py` ficaram de fora) |
| D13 | Helper | Bloco 4c, só nomes internos |
| D14 | Fora | Scripts de linha de comando e testes no bloco 5; parâmetros, locais e binds na passada final |

O `os_platform` é usado também por um objeto que guarda o módulo (`self.plat`, `plat`) e por plataformas falsas nos testes (`_Plat(**trocas)`, que resolve por `__getattr__`); os acessos e as chaves dessas trocas mudaram junto.

### `os_platform`

| Antes | Depois |
|---|---|
| `CODIGO_NAO_SUPORTADO` | `UNSUPPORTED_CODE` |
| `FalhaAposSpawn` | `FailureAfterSpawn` |
| `HELPER_PACOTE` | `PACKAGE_HELPER` |
| `InstanciaJaEmExecucao` | `InstanceAlreadyRunning` |
| `NOME` | `NAME` |
| `PASTAS_DO_SISTEMA` | `SYSTEM_DIRS` |
| `Processo` | `Process` |
| `RLIMITS_PADRAO` | `DEFAULT_RLIMITS` |
| `SAIDA_EXCEDE_ARQUIVOS` | `OUTPUT_TOO_MANY_FILES` |
| `SAIDA_EXCEDE_BYTES` | `OUTPUT_TOO_MANY_BYTES` |
| `SAIDA_VAZIA` | `OUTPUT_EMPTY` |
| `_RLIMITS_PERMITIDOS` | `_ALLOWED_RLIMITS` |
| `_Trava` | `_Lock` |
| `_argv_helper` | `_helper_argv` |
| `_colher_pedidos_helper` | `_reap_helper_requests` |
| `_dentro` | `_inside` |
| `_executar_curto` | `_run_short` |
| `_limites_do_filho` | `_child_limits` |
| `_normalizar_locale` | `_normalize_locale` |
| `_pedidos_helper` | `_helper_requests` |
| `_pids_na_pasta` | `_pids_in_dir` |
| `_starttime_linux` | `_linux_starttime` |
| `_stat_codigo` | `_stat_code` |
| `caminho_final` | `final_path` |
| `criar_dir_trabalho` | `create_work_dir` |
| `criar_pasta_entrada` | `create_input_dir` |
| `criar_pasta_saida` | `create_output_dir` |
| `eh_macos` | `is_macos` |
| `encerrar_ticket` | `stop_ticket` |
| `espaco_livre_mb` | `free_space_mb` |
| `gravar_estado` | `write_state` |
| `grupo_vivo` | `group_alive` |
| `identidade_processo` | `process_identity` |
| `iniciar_empacotar` | `start_pack` |
| `iniciar_processo` | `start_process` |
| `instalar_parada` | `install_stop_handler` |
| `ler_estado` | `read_state` |
| `liberar_instancia` | `release_instance` |
| `limpar_dir_script` | `clean_script_dir` |
| `limpar_saida` | `clean_output` |
| `locale_disponivel` | `locale_available` |
| `obter_lib_dir_oracle` | `get_oracle_lib_dir` |
| `processo_existe` | `process_exists` |
| `purgar_saida` | `purge_output` |
| `reabrir_grupo` | `reopen_group` |
| `sinalizar_grupo` | `signal_group` |
| `travar_instancia` | `lock_instance` |
| `usuario_privilegiado` | `is_privileged_user` |
| `validar_arquivo_restrito` | `validate_restricted_file` |
| `validar_caminho_script` | `validate_script_path` |
| `validar_dir_restrito` | `validate_restricted_dir` |
| `validar_execucao` | `validate_execution` |
| `validar_interpretador_executavel` | `validate_interpreter_executable` |
| `validar_pastas_saida` | `validate_output_dirs` |

### `executor`

| Antes | Depois |
|---|---|
| `DiretorioPreservado` | `PreservedDirectory` |
| `Execucao` | `Execution` |
| `FASE_FIM` | `PHASE_END` |
| `FASE_KILL` | `PHASE_KILL` |
| `FASE_SEM_IDENTIDADE` | `PHASE_NO_IDENTITY` |
| `FASE_TERM` | `PHASE_TERM` |
| `FIM` | `END` |
| `GRACE_PADRAO_S` | `DEFAULT_GRACE_S` |
| `MARCADORES` | `MARKERS` |
| `SEM_IDENTIDADE` | `NO_IDENTITY` |
| `_agente_do_rotulo` | `_agent_from_label` |
| `_apos_spawn_falhou` | `_after_spawn_failed` |
| `_falha_spawn` | `_spawn_failure` |
| `_linha_sss` | `_sss_line` |
| `_logs_abertos` | `_open_logs` |
| `abrir_log` | `open_log` |
| `anexar_linha_local` | `append_local_line` |
| `avancar_encerramento` | `advance_stop` |
| `especificacao` | `build_spec` |
| `falha_antes_do_spawn` | `failure_before_spawn` |
| `iniciar` | `start` |
| `limpar` | `clean` |
| `pedir_encerramento` | `request_stop` |
| `preparar_diretorio` | `prepare_directory` |
| `registrar_resultado` | `record_result` |
| `traduzir_retorno` | `translate_return` |
| `verificar` | `check` |

### `log_paths`

| Antes | Depois |
|---|---|
| `INTERNO (ambiente reservado)` | `INTERNAL` |
| `PASTA_APP` | `APP_DIR` |
| `PASTA_INTERNA` | `INTERNAL_DIR` |
| `_RE_ANO` | `_RE_YEAR` |
| `_RE_DOIS_DIGITOS` | `_RE_TWO_DIGITS` |
| `_RE_FORA` | `_RE_OUTSIDE` |
| `_subpastas` | `_subdirs` |
| `ambiente_reservado` | `is_reserved_environment` |
| `caminho_log_app` | `app_log_path` |
| `caminho_log_execucao` | `run_log_path` |
| `caminho_log_parcial` | `partial_log_path` |
| `diretorio_log_app` | `app_log_dir` |
| `diretorio_log_execucao` | `run_log_dir` |
| `garantir_diretorio` | `ensure_directory` |
| `interno (pasta)` | `internal` |
| `limpar_retencao_app` | `clean_app_retention` |
| `limpar_retencao_execucao` | `clean_run_retention` |
| `minutos_de_execucao` | `run_minutes` |
| `nome_log_app` | `app_log_name` |
| `nome_log_execucao` | `run_log_name` |
| `nome_log_parcial` | `partial_log_name` |
| `nome_reservado` | `is_reserved_name` |
| `parse_data_dia` | `parse_day_date` |
| `parse_data_minuto` | `parse_minute_date` |
| `partes_minuto` | `minute_parts` |
| `pasta_ambiente` | `environment_dir` |
| `pasta_entrada` | `input_dir` |
| `pasta_saida` | `output_dir` |
| `pasta_script` | `script_dir` |
| `proximo_caminho_log_app` | `next_app_log_path` |

### Métodos e atributos de instância

| Antes | Depois |
|---|---|
| `caminho` | `path` |
| `caminho_log` | `log_path` |
| `causa` | `cause` |
| `erro_spawn` | `spawn_error_info` |
| `falhou_apos_spawn` | `failed_after_spawn` |
| `fase` | `phase` |
| `identidade` | `identity` |
| `pasta_base` | `base_dir` |
| `prazo_kill` | `kill_deadline` |
| `processo` | `process` |
| `sem_identidade` | `no_identity` |
| `travado` | `stuck` |
| `usuario_execucao` | `exec_user` |

### Chaves dos marcadores

| Antes | Depois |
|---|---|
| `monotonico` | `monotonic` |
| `parede` | `wall` |
| `usuario_execucao` | `exec_user` |

## 11. Validação do bloco 4a

* Suítes em 3.6.0, 3.6.8 e 3.13.2, bateria Oracle, testes progressivos nos cinco agregados, percurso real das telas e conferência de resíduos.
* Achados na conferência e corrigidos: funções definidas em `os_platform/__init__.py` (o nome do arquivo não é o do pacote, e a ferramenta não as achou); código Python em string rodado em subprocesso nos testes de trava de instância; lista de nomes da interface em `test_platform`; atributos de classe e chaves de plataformas falsas.

## 12. Bloco 4b (laço do agente)

Módulos `scheduler_loop`, `output_phase` e `log_pump`, com os atributos de instância de `Agent`, `_Item`, `Output`, `Pump`, `Round` e `RoundResult`.

* Métodos e atributos mudaram só nos arquivos do daemon e nos testes dele: nomes genéricos (`_ler`, `_limpar`, `relogio`, `saida`, `tamanho`, `segredos`…) também existem em outras classes (repositórios, services, `purge.py`), que ficam como estão.
* `codigo` → `code` e `motivo` → `reason` mudaram em todas as classes que os definem (`StartupFailure`, `PathGuardError`, `SnapshotError`, `AccessDenied`, `Output`, `_Item`), porque o laço lê os das exceções de `path_guard` e `params_compiler`. O `Falha.codigo` do helper fica para o 4c.
* Valores (D9): estados da fase de saída e resultados do `log_pump`; o zip no `work_dir` passa a `output.zip` (D11). O nome do download (`ticket_<id>_saida.zip`) fica para o CR-016d.

### Nomes de módulo

#### `scheduler_loop`

| Antes | Depois |
|---|---|
| `Agente` | `Agent` |
| `DIVERGENCIA_RELOGIO_S` | `CLOCK_SKEW_S` |
| `FalhaInicializacao` | `StartupFailure` |
| `INTERVALO_AVISO_DISCO_S` | `DISK_WARNING_INTERVAL_S` |
| `INTERVALO_MAXIMO_ESPERA_S` | `MAX_WAIT_INTERVAL_S` |
| `SAIDA_AMBIENTES` | `EXIT_ENVIRONMENTS` |
| `SAIDA_BANCO` | `EXIT_DATABASE` |
| `SAIDA_CONFIG` | `EXIT_CONFIG` |
| `SAIDA_DIRETORIOS` | `EXIT_DIRECTORIES` |
| `SAIDA_INSTANCIA` | `EXIT_INSTANCE` |
| `SAIDA_REGISTRO` | `EXIT_REGISTRATION` |
| `SAIDA_REGISTRO_PERDIDO` | `EXIT_REGISTRATION_LOST` |
| `SAIDA_SEGREDOS` | `EXIT_SECRETS` |
| `SAIDA_STARTUP` | `EXIT_STARTUP` |
| `SAIDA_THREADS` | `EXIT_THREADS` |
| `SAIDA_USUARIO` | `EXIT_USER` |
| `SALTO_RELOGIO_S` | `CLOCK_JUMP_S` |
| `_PREFIXO_PASTA` | `_DIR_PREFIX` |
| `_dirs_sss` | `_sss_dirs` |
| `_ler_estado` | `_read_state` |

#### `output_phase`

| Antes | Depois |
|---|---|
| `ABANDONADA` | `ABANDONED` |
| `CONCLUIDA` | `DONE` |
| `CONTINUA` | `CONTINUE` |
| `EXCEDEU` | `EXCEEDED` |
| `FALHOU` | `FAILED` |
| `NOME_ZIP` | `ZIP_NAME` |
| `PARTES_POR_VOLTA` | `PARTS_PER_ROUND` |
| `PRAZO_EMPACOTAR_S` | `PACK_DEADLINE_S` |
| `Saida` | `Output` |
| `TAMANHO_PARTE` | `PART_SIZE` |
| `VAZIA` | `EMPTY` |
| `_conferir_zip` | `_check_zip` |
| `_ja_esta` | `_already_written` |
| `abandonar` | `abandon` |
| `avancar_empacotar` | `advance_pack` |
| `deve_remover_pasta` | `should_remove_dir` |
| `gravar` | `write` |
| `iniciar_empacotar` | `start_pack` |
| `linha_log` | `log_line` |
| `remover_pasta` | `remove_dir` |

#### `log_pump`

| Antes | Depois |
|---|---|
| `Bomba` | `Pump` |
| `CONEXAO_INCERTA` | `UNCERTAIN_CONNECTION` |
| `INCONSISTENTE` | `INCONSISTENT` |
| `LEITURA_PADRAO` | `DEFAULT_READ` |
| `MARCADOR` | `MARKER` |
| `ResultadoRodada` | `RoundResult` |
| `Rodada` | `Round` |
| `TAMANHO_BLOCO` | `CHUNK_SIZE` |
| `_enviar_um` | `_send_one` |
| `_prefixo_em_bytes` | `_prefix_in_bytes` |
| `blocos` | `chunks` |
| `flush_final` | `final_flush` |
| `mascarador_do_ticket` | `ticket_masker` |
| `unidades_clob` | `clob_units` |

### Valores

| Antes | Depois |
|---|---|
| `ABANDONADA` | `ABANDONED` |
| `CONCLUIDA` | `DONE` |
| `CONEXAO_INCERTA` | `UNCERTAIN_CONNECTION` |
| `CONTINUA` | `CONTINUE` |
| `INCONSISTENTE` | `INCONSISTENT` |
| `VAZIA` | `EMPTY` |
| `saida.zip` | `output.zip` |

### Métodos

| Antes | Depois |
|---|---|
| `_apos_iniciar` | `_after_start` |
| `_avancar_saidas` | `_advance_outputs` |
| `_avisar_leitura` | `_warn_read` |
| `_ciclo` | `_cycle` |
| `_ciclo_heartbeat` | `_heartbeat_cycle` |
| `_ciclo_orquestrador` | `_orchestrator_cycle` |
| `_ciclo_rapido` | `_fast_cycle` |
| `_conferir_entrada_dir` | `_check_input_dir` |
| `_conferir_fence` | `_check_fence` |
| `_conferir_limites` | `_check_limits` |
| `_conferir_saida_dir` | `_check_output_dir` |
| `_conferir_thread_unica` | `_check_single_thread` |
| `_desdobro` | `_expansion` |
| `_devolver` | `_return_to_queue` |
| `_drenado` | `_drained` |
| `_empacotar` | `_pack` |
| `_encerrar` | `_stop` |
| `_erro_antes_do_spawn` | `_error_before_spawn` |
| `_falhar` | `_fail` |
| `_fence_vencido` | `_fence_expired` |
| `_finalizar` | `_finalize` |
| `_finalizar_execucao` | `_finalize_execution` |
| `_finalizar_execucao_sem_processo` | `_finalize_execution_without_process` |
| `_finalizar_sem_spawn` | `_finalize_without_spawn` |
| `_iniciar` | `_start` |
| `_iniciar_drenagem` | `_start_drain` |
| `_iteracao` | `_iteration` |
| `_iteracao_sem_banco` | `_iteration_without_db` |
| `_ler` | `_read` |
| `_limpar` | `_clean` |
| `_limpar_pasta` | `_clean_dir` |
| `_ordem` | `_order` |
| `_passo1_usuario` | `_step1_user` |
| `_passo2_config` | `_step2_config` |
| `_passo3_segredos` | `_step3_secrets` |
| `_passo4_diretorios` | `_step4_directories` |
| `_passo5_instancia` | `_step5_instance` |
| `_passo6_banco` | `_step6_database` |
| `_passo7_registro` | `_step7_registration` |
| `_passo8_ambientes` | `_step8_environments` |
| `_passo9_startup_check` | `_step9_startup_check` |
| `_passos` | `_steps` |
| `_pastas_locais` | `_local_dirs` |
| `_pendencias` | `_pending` |
| `_pode_seguir` | `_can_continue` |
| `_prevalidar` | `_prevalidate` |
| `_reabrir` | `_reopen` |
| `_reconciliar` | `_reconcile` |
| `_recusar` | `_refuse` |
| `_registrar_pid` | `_register_pid` |
| `_remover` | `_remove` |
| `_resultado` | `_result` |
| `_sair_do_cerco` | `_leave_fence` |
| `_salto_de_relogio` | `_clock_jump` |
| `_segredos_lista` | `_secret_values` |
| `_usuario_execucao` | `_exec_user` |
| `agente_id` | `agent_id` |
| `aplicar_teto_banco` | `apply_db_cap` |
| `coletar` | `collect` |
| `confirmar` | `confirm` |
| `empacotada` | `packed` |
| `encerrar_tudo` | `stop_all` |
| `excedeu_local` | `local_exceeded` |
| `inicializar` | `initialize` |
| `liberar_recursos` | `release_resources` |
| `pasta` | `folder` |
| `pendente` | `pending` |
| `preparar_laco` | `prepare_loop` |
| `proximo_bloco` | `next_chunk` |

### Atributos de instância

| Antes | Depois |
|---|---|
| `_bytes_aceitos` | `_accepted_bytes` |
| `_bytes_marcador` | `_marker_bytes` |
| `_carregar_config` | `_load_config` |
| `_carregar_segredos` | `_load_secrets` |
| `_drenagem_ate` | `_drain_until` |
| `_em_voo` | `_in_flight` |
| `_esperar` | `_wait` |
| `_fila` | `_queue` |
| `_fluxo` | `_stream` |
| `_mascarador_fixo` | `_fixed_masker` |
| `_node_offline_suspenso_ate` | `_node_offline_suspended_until` |
| `_parando` | `_stopping` |
| `_ref_relogio` | `_clock_ref` |
| `_retido` | `_held` |
| `_terminando` | `_terminating` |
| `_ultimo` | `_last` |
| `_ultimo_aviso_disco` | `_last_disk_warning` |
| `agente_db_id` | `agent_db_id` |
| `atendidos` | `served` |
| `avisou_pendencia` | `pending_warned` |
| `avisou_pid` | `pid_warned` |
| `bomba` | `pump` |
| `bombas` | `pumps` |
| `bytes_confirmados` | `confirmed_bytes` |
| `caminho_zip` | `zip_path` |
| `cercado` | `fenced` |
| `codigo` | `code` |
| `codigo_saida` | `exit_code` |
| `conexao` | `connection` |
| `conexao_incerta` | `uncertain_connection` |
| `desdobro` | `expansion` |
| `devolucoes_pendentes` | `pending_returns` |
| `encerrando` | `stopping` |
| `erro_leitura` | `read_error` |
| `esgotou_orcamento` | `budget_exhausted` |
| `execucao` | `execution` |
| `execucoes` | `executions` |
| `finalizacao_pendente` | `finalize_pending` |
| `finalizada` | `finished` |
| `inconsistentes` | `inconsistent` |
| `iniciada` | `started` |
| `inicio` | `start` |
| `morto` | `dead` |
| `motivo` | `reason` |
| `offset_confirmado_chars` | `confirmed_offset_chars` |
| `orcamento_s` | `budget_s` |
| `parada` | `stopped` |
| `pid_pendente` | `pid_pending` |
| `posse_perdida` | `ownership_lost` |
| `prazo` | `deadline` |
| `prazos` | `deadlines` |
| `preservadas` | `preserved` |
| `proxima_tentativa` | `next_attempt` |
| `qtd_arquivos` | `file_count` |
| `relativo` | `relative` |
| `relogio` | `clock` |
| `relogio_parede` | `wall_clock` |
| `repo_agenda` | `repo_schedules` |
| `repo_saida` | `repo_output` |
| `resultado` | `result` |
| `rodada` | `round` |
| `saida` | `output` |
| `saidas` | `outputs` |
| `segredos` | `secrets` |
| `tamanho` | `size` |
| `trava` | `lock` |
| `truncado` | `truncated` |
| `truncado_gravado` | `truncated_written` |
| `ultimo_hb_ok` | `last_hb_ok` |

## 13. Validação do bloco 4b

* Suítes em 3.6.0, 3.6.8 e 3.13.2, bateria Oracle, testes progressivos nos cinco agregados, percurso real das telas e conferência de resíduos.
* Ciclo real do agente no DEV, com dados próprios e config próprio: claim, execução do script, marcadores `.sss_spawn` (`exec_user`, `monotonic`, `ticket_id`, `wall`) e `.sss_proc` (`exec_user`, `pgid`, `pid`, `process_start`, `ticket_id`), ticket `SUCCESS`/`EXIT_OK`, saída `AVAILABLE` com 1 arquivo, log do agente em `log_dir/internal/app/` e parada pelo `sss-stop.sh`.
* Achado na bateria e corrigido: o atributo `_esperar` do agente virou `_wait`, e a troca alcançou o método auxiliar de mesmo nome que `test_ha_real_agents` herda de `test_agents_concurrency` (fora do conjunto do daemon); as chamadas voltaram a `_esperar` (testes no bloco 5).
* Decisão do usuário (2026-10-21, D15): os códigos de ação do log (`[action=INICIO]`, `PARADA`, `SAIDA`, `SPAWN`…) **ficam em português**.

## 14. Bloco 4c (helper)

Só nomes internos do `bin/sss-helper` (instalado como `/opt/sss/bin/sss-helper`, roda como root via `sudo`). Os subcomandos (`run`, `term`, `kill`, `clean`, `stop-ticket`, `pack`, `clean-output`, `purge-output`), os códigos de saída numéricos e as chaves da especificação não mudam.

| Antes | Depois |
|---|---|
| `ERRO_SISTEMA` | `SYSTEM_ERROR` |
| `Falha` | `Failure` |
| `NAO_SUPORTADO` | `UNSUPPORTED` |
| `RECUSADO` | `REFUSED` |
| `SAIDA_EXCEDE_ARQUIVOS` | `OUTPUT_TOO_MANY_FILES` |
| `SAIDA_EXCEDE_BYTES` | `OUTPUT_TOO_MANY_BYTES` |
| `SAIDA_VAZIA` | `OUTPUT_EMPTY` |
| `USO_INVALIDO` | `INVALID_USAGE` |
| `_BLOCO` | `_CHUNK` |
| `_MAX_ARQUIVOS_SAIDA` | `_MAX_OUTPUT_FILES` |
| `_MAX_BYTES_SAIDA` | `_MAX_OUTPUT_BYTES` |
| `_MAX_ESPECIFICACAO` | `_MAX_SPEC` |
| `_RE_PASTA_SCRIPT` | `_RE_SCRIPT_DIR` |
| `_RE_RELATIVO_MINUTO` | `_RE_MINUTE_RELATIVE` |
| `_RLIMITS_PERMITIDOS` | `_ALLOWED_RLIMITS` |
| `_SaidaContada` | `_CountedOutput` |
| `_arquivos_da_saida` | `_output_files` |
| `_diretorio_proprio` | `_own_directory` |
| `_empacotar` | `_pack` |
| `_encerrar_ticket` | `_stop_ticket` |
| `_erro` | `_error` |
| `_identidade` | `_identity` |
| `_inteiro` | `_integer` |
| `_ler_especificacao` | `_read_spec` |
| `_limpar` | `_clean` |
| `_limpar_saida` | `_clean_output` |
| `_partes_relativo` | `_relative_parts` |
| `_pasta_base` | `_base_dir` |
| `_pasta_entrada` | `_input_dir` |
| `_pasta_saida` | `_output_dir` |
| `_pasta_ticket` | `_ticket_dir` |
| `_purgar_saida` | `_purge_output` |
| `_sinalizar` | `_signal` |
| `principal` | `run_main` |

Atributos: `Failure.codigo` → `code`; `_CountedOutput`: `destino` → `destination`, `escritos` → `written`, `excedeu` → `exceeded`. Parâmetros e variáveis locais ficam para a passada final.

As funções autorizadas a ler `/proc/<pid>/cwd` e `/proc/<pid>/stat` e a chamar `pwdx` (AGENTS §3.2 e §8) passam a ser `_stop_ticket` e `_identity`; a verificação de `test_py36_compat` acompanha.

## 15. Validação do bloco 4c

* `test_sss_helper`, `test_py36_compat`, `test_platform`, `test_scheduler_init`, `test_package`, `test_launchers` e `test_deployment_doc` em 3.6.0 e 3.13.2; suítes completas em 3.6.0, 3.6.8 e 3.13.2; bateria Oracle.
* Ensaio do pacote: o pacote gerado traz o helper idêntico ao da árvore, que responde com código 2 a subcomando ausente ou inválido, e o `secrets.cfg.example` com `CHANGE_ME`.
* Ciclo real do agente no DEV repetido (em DEV a saída é empacotada pela cópia do helper no pacote): ticket `SUCCESS`, saída `AVAILABLE`.

## 16. Bloco 5a (scripts de linha de comando, apoio dos testes e lançadores)

Decisões aprovadas (2026-10-21):

| # | Decisão | Resumo |
|---|---|---|
| D16 | Nomes dos testes | Os `test_*` (1.280, 919 com português) ficam em português: descrevem o cenário e são a legenda do teste na saída da suíte. Classes, helpers, fakes e constantes de teste mudam no 5b |
| D17 | Lançadores de `bin/` | Eram três cópias idênticas de subida e três de parada: ficam `bin/start_local.sh` e `bin/stop_local.sh` (só DEV, fora do pacote); o log do lançador passa a `logs/server-<data>.log` e `logs/server.out`; o `AAA001-LEIA-ME-SUBIR-PARAR-SERVICO.TXT` vira `AAA001-README-START-STOP.TXT` (conteúdo em português) |
| D18 | Scripts do servidor 3067 | Fora do repositório; a doc passa a `start_sss.sh`, `stop_sss.sh` e `logs/server.out` (DEPLOYMENT, com a nota de renomear no servidor na próxima implantação) |
| D19 | `LEIA-ME.TXT` da raiz | Anotações do usuário, em português: fica como está |

Os alvos internos do `purge.py` passam a ser os mesmos valores do `--target` (`tickets`, `audit`, `local_logs`, `output`, `all`), sem tradução no meio; o resumo usa os mesmos rótulos. A documentação do `--target` (docstring, README e DEPLOYMENT) ainda mostrava os valores anteriores ao CR-016b e foi corrigida.

### `scripts/check_env.py`

| Antes | Depois |
|---|---|
| `_ANTES_DE_REGEX` | `_BEFORE_REGEX` |
| `_JsInvalido` | `_InvalidJs` |
| `_PALAVRAS_ANTES_DE_REGEX` | `_WORDS_BEFORE_REGEX` |
| `_PARES` | `_PAIRS` |
| `_RE_CONSTRUTOR_DINAMICO` | `_RE_DYNAMIC_CONSTRUCTOR` |
| `_RE_DECL_FUNCAO` | `_RE_FUNCTION_DECL` |
| `_RE_EVAL_DIRETO` | `_RE_DIRECT_EVAL` |
| `_casar` | `_match` |
| `_corpos_de_funcoes` | `_function_bodies` |
| `_inicia_regex` | `_starts_regex` |
| `_pular_regex` | `_skip_regex` |
| `verificar_alpine_csp` | `check_alpine_csp` |

### `scripts/health.py`

| Antes | Depois |
|---|---|
| `ESTADOS` | `STATES` |
| `Verificacao` | `Check` |
| `_SAUDAVEIS` | `_HEALTHY` |
| `_agentes` | `_agents` |
| `_argumentos` | `_arguments` |
| `_conectar` | `_connect` |
| `_desconhecido` | `_unknown` |
| `_fila` | `_queue` |
| `_idade` | `_age` |
| `_problema` | `_problem` |
| `_sem_pid` | `_no_pid` |
| `_versao` | `_version` |
| `saida` | `output` |

### `scripts/init_db.py`

| Antes | Depois |
|---|---|
| `_coletar_estatisticas` | `_gather_statistics` |
| `_conectar` | `_connect` |
| `_conferir_esquema` | `_check_schema` |
| `_consultar_existencia` | `_query_existence` |
| `_executar_ddl_fases` | `_run_ddl_phases` |
| `_executar_seed` | `_run_seed` |
| `_existe_esquema_1` | `_schema_1_exists` |
| `_objeto_existe` | `_object_exists` |
| `_registrar_critico_config` | `_log_critical_config` |
| `_validar_schema_descartavel_dev` | `_validate_disposable_schema_dev` |

### `scripts/package.py`

| Antes | Depois |
|---|---|
| `ARQUIVOS_RAIZ` | `ROOT_FILES` |
| `EXCLUIR_APP` | `EXCLUDE_APP` |
| `EXCLUIR_GLUON` | `EXCLUDE_GLUON` |
| `ErroPacote` | `PackageError` |
| `PASTAS_RAIZ` | `ROOT_DIRS` |
| `RAIZ_PADRAO` | `DEFAULT_ROOT` |
| `RUNTIME_VAZIAS` | `EMPTY_RUNTIME_DIRS` |
| `_EXEMPLO_SEGREDOS` | `_SECRETS_EXAMPLE` |
| `_RE_CREDENCIAL` | `_RE_CREDENTIAL` |
| `_RE_TESTE` | `_RE_TEST` |
| `_caminhar` | `_walk` |
| `_credenciais` | `_credentials` |
| `_excluido_da_app` | `_excluded_from_app` |
| `coletar` | `collect` |
| `empacotar` | `build_package` |
| `verificar` | `check` |

### `scripts/probe_driver.py`

| Antes | Depois |
|---|---|
| `_ERROS_AUTENTICACAO` | `_AUTH_ERRORS` |
| `_ERROS_REDE` | `_NETWORK_ERRORS` |
| `_RE_CODIGO_ERRO` | `_RE_ERROR_CODE` |
| `_classificar_erro` | `_classify_error` |
| `_formatar_versao_cliente` | `_format_client_version` |
| `sondar` | `probe` |

### `scripts/purge.py`

| Antes | Depois |
|---|---|
| `ALVOS` | `TARGETS` |
| `ALVOS_CLI` | `CLI_TARGETS` |
| `ConcessaoPerdida` | `LeaseLost` |
| `ExportacaoAuditoria` | `AuditExport` |
| `NOME_TRAVA` | `LOCK_NAME` |
| `SAIDA_BANCO` | `EXIT_DATABASE` |
| `SAIDA_CONFIG` | `EXIT_CONFIG` |
| `SAIDA_LOCAIS` | `EXIT_LOCAL` |
| `SAIDA_OK` | `EXIT_OK` |
| `_LOGGERS_DO_PURGE` | `_PURGE_LOGGERS` |
| `_argumentos` | `_arguments` |
| `_conectar` | `_connect` |
| `_contar_tabelas` | `_count_tables` |
| `_desfazer` | `_undo` |
| `_liberar` | `_release` |
| `_limite` | `_cutoff` |
| `_logs_locais` | `_local_logs` |
| `_purgar_tabela` | `_purge_table` |
| `_purgar_tabelas` | `_purge_tables` |
| `_saida` | `_output` |
| `fechar` | `close` |
| `gravar` | `write` |

### `scripts/run_scheduler.py`

| Antes | Depois |
|---|---|
| `_LOGGERS_DO_DAEMON` | `_DAEMON_LOGGERS` |
| `_esperar` | `_wait` |

### `scripts/_oracle_test_support.py`

| Antes | Depois |
|---|---|
| `CHAVE` | `KEY` |
| `MODO_COMPARTILHADO` | `SHARED_MODE` |
| `MODO_DESCARTAVEL` | `DISPOSABLE_MODE` |
| `PREFIXO_OWNER_RESERVADO` | `RESERVED_OWNER_PREFIX` |
| `PrecondicaoSchemaErro` | `SchemaPreconditionError` |
| `VARIAVEIS_ANTIGAS` | `OLD_VARIABLES` |
| `_RE_OWNER_DESCARTAVEL` | `_RE_DISPOSABLE_OWNER` |
| `_conferir_esquema_sss` | `_check_sss_schema` |
| `_modo_atual` | `_current_mode` |
| `banco_real_configurado` | `real_db_configured` |
| `modo_do_owner` | `owner_mode` |
| `modo_schema` | `schema_mode` |
| `preparar_schema_descartavel` | `prepare_disposable_schema` |
| `validar_schema_descartavel` | `validate_disposable_schema` |
| `verificar_precondicoes_ambiente` | `check_environment_preconditions` |

### `scripts/_output_memory.py`

| Antes | Depois |
|---|---|
| `RepoSaidaMemoria` | `RepoOutputMemory` |
| `_dono` | `_owner` |

### Atributos de instância

| Antes | Depois |
|---|---|
| `_arquivo` | `_file` |
| `_escritor` | `_writer` |
| `caminho` | `path` |
| `desempenho` | `performance` |
| `dono` | `owner` |
| `limiares` | `thresholds` |
| `linhas` | `rows` |
| `problemas` | `problems` |
| `resumo` | `summary` |

### Lançadores de `bin/`

| Antes | Depois |
|---|---|
| `bin/AAA001-LEIA-ME-SUBIR-PARAR-SERVICO.TXT` | `bin/AAA001-README-START-STOP.TXT` |
| `bin/iniciar_local.sh` | `bin/start_local.sh` |
| `bin/iniciar_sss.sh` | removido (cópia idêntica) |
| `bin/parar_local.sh` | removido (cópia idêntica) |
| `bin/parar_servico.sh` | `bin/stop_local.sh` |
| `bin/parar_sss.sh` | removido (cópia idêntica) |
| `bin/subir_local.sh` | removido (cópia idêntica) |

## 17. Validação do bloco 5a

* Suítes em 3.6.0, 3.6.8 e 3.13.2, bateria Oracle, testes progressivos nos cinco agregados, percurso real das telas e conferência de resíduos.
* Execução real no DEV: `purge.py --dry-run` (desligado no DEV, `purge_user` vazio: código 2 e o motivo no log em `internal/`), `health.py` (`UNKNOWN` sem `[monitor]` no DEV), `probe_driver.py thin` com a senha pela entrada padrão (conecta) e `generate_sql.py` (rollback e validação idênticos aos versionados).
* `docs/sql/01_deploy_sss.sql` regenerado: o comentário do papel do agente ainda dizia "agente" (anterior ao CR-016b).
* Ensaio do pacote: só os lançadores de produção (`sss-helper`, `sss-scheduler.sh`, `sss-stop.sh`, `sss-web.sh`), sem os de DEV e sem testes.
* Achado e corrigido: `global _modo_atual` em `_oracle_test_support` (a ferramenta por escopo passou a renomear declarações `global`).
* Para a passada final: as chaves do JSON do `probe_driver` (`candidato`, `versao_servidor`…) são o contrato com o `db_conn` e continuam em português.

## 18. Bloco 5b (testes)

Classes de teste, auxiliares e fakes, funções e constantes de módulo, métodos que não são `test_*` e atributos dos fakes. Os 1.280 nomes `test_*` ficam em português (D16).

Um método ou atributo de teste só mudou quando o mesmo nome não aparece como atributo no código de produção, para não separar um fake do objeto real que ele imita; os bloqueados (`relogio`, `saida`, `segredos`, `fila`, `usuario`…) mudam na passada final, junto com a produção.

### Classes

| Antes | Depois |
|---|---|
| `BaseUltimoAdminTest` | `BaseLastAdminTest` |
| `TestAcessoEAuditoria` | `TestAccessAndAudit` |
| `TestAcessoEExecutavel` | `TestAccessAndExecutable` |
| `TestAdminSoPorAdmin` | `TestAdminOnlyByAdmin` |
| `TestAgendaSemBanco` | `TestAgendaWithoutDb` |
| `TestAlertaInfo` | `TestAlertInfo` |
| `TestArquivoRestrito` | `TestRestrictedFile` |
| `TestAtivoInfo` | `TestActiveInfo` |
| `TestAtorVisivel` | `TestVisibleActor` |
| `TestAuditoriaInclusao` | `TestAuditInsert` |
| `TestAutoprotecao` | `TestSelfProtection` |
| `TestAvaliarDisparo` | `TestEvaluateTrigger` |
| `TestBarrasEmpilhadas` | `TestStackedBars` |
| `TestBlocosLog` | `TestLogChunks` |
| `TestCabecalhoReferrer` | `TestReferrerHeader` |
| `TestCadastro` | `TestRegistration` |
| `TestCadastroOpcoesEFlag` | `TestRegistrationOptionsAndFlag` |
| `TestCadastroPerfil` | `TestProfileRegistration` |
| `TestCatalogoRotinas` | `TestRoutineCatalog` |
| `TestCiclos` | `TestCycles` |
| `TestClarezaDisparo` | `TestTriggerClarity` |
| `TestCompilarSnapshot` | `TestCompileSnapshot` |
| `TestConcorrenciaDoisAgentes` | `TestTwoAgentsConcurrency` |
| `TestContexto` | `TestContext` |
| `TestContrasteCores` | `TestColorContrast` |
| `TestDbConnSelecaoMocks` | `TestDbConnSelectionMocks` |
| `TestDdlSeedERollback` | `TestDdlSeedAndRollback` |
| `TestDependencias` | `TestDependencies` |
| `TestDesativacao` | `TestDeactivation` |
| `TestDesativacaoComImpacto` | `TestDeactivationWithImpact` |
| `TestDescrever` | `TestDescribe` |
| `TestDescricaoMotivo` | `TestReasonDescription` |
| `TestDesdobro` | `TestExpansion` |
| `TestDesdobroOracle` | `TestExpansionOracle` |
| `TestDesempenho` | `TestPerformance` |
| `TestDublesHelper` | `TestHelperDoubles` |
| `TestEdicao` | `TestEdit` |
| `TestEdicaoEUltimoAdmin` | `TestEditAndLastAdmin` |
| `TestEmpacotar` | `TestPack` |
| `TestEncerramento` | `TestStop` |
| `TestEstadoEDiretorios` | `TestStateAndDirectories` |
| `TestEstadoLocal` | `TestLocalState` |
| `TestExecucao` | `TestExecution` |
| `TestExportar` | `TestExport` |
| `TestFalhasDeSpawn` | `TestSpawnFailures` |
| `TestFilaNodeOfflineSemBanco` | `TestQueueNodeOfflineWithoutDb` |
| `TestFiltroLogging` | `TestLoggingFilter` |
| `TestFiltros` | `TestFilters` |
| `TestFonte` | `TestSource` |
| `TestFormatarData` | `TestFormatDate` |
| `TestFormatarDuracao` | `TestFormatDuration` |
| `TestGrantsPorPapel` | `TestGrantsByRole` |
| `TestGuiaDeImplantacao` | `TestDeploymentGuide` |
| `TestHaDoisAgentes` | `TestHaTwoAgents` |
| `TestHashSenha` | `TestPasswordHash` |
| `TestHistoricoScript` | `TestScriptHistory` |
| `TestHomologacao` | `TestHomologation` |
| `TestInclusao` | `TestInsert` |
| `TestInitDbConferenciaMock` | `TestInitDbCheckMock` |
| `TestIpOrigem` | `TestClientIp` |
| `TestLacoComSaida` | `TestLoopWithOutput` |
| `TestLeituraEMascara` | `TestReadAndMask` |
| `TestLerLogConteudo` | `TestReadLogContent` |
| `TestLerLogValidacao` | `TestReadLogValidation` |
| `TestLimites` | `TestLimits` |
| `TestLinguagemClara` | `TestPlainLanguage` |
| `TestListaEAcesso` | `TestListAndAccess` |
| `TestListaPrevia` | `TestPreviewList` |
| `TestListar` | `TestList` |
| `TestLogESaida` | `TestLogAndOutput` |
| `TestLogsLocais` | `TestLocalLogs` |
| `TestMaquina` | `TestStateMachine` |
| `TestMascarador` | `TestMasker` |
| `TestMascaradorFluxo` | `TestStreamMasker` |
| `TestMatriz` | `TestMatrix` |
| `TestModulosPuros` | `TestPureModules` |
| `TestModulosPurosSemGluon` | `TestPureModulesWithoutGluon` |
| `TestMontarArgs` | `TestBuildArgs` |
| `TestMontarArgvAgente` | `TestBuildAgentArgv` |
| `TestMontarMenu` | `TestBuildMenu` |
| `TestMotivoPausa` | `TestPauseReason` |
| `TestNeutralizacaoCsv` | `TestCsvNeutralization` |
| `TestNormalizacaoExpressaoOracle11g` | `TestOracle11gExpressionNormalization` |
| `TestOracleAgendamentos` | `TestOracleSchedules` |
| `TestOracleAuditoriaAgentes` | `TestOracleAuditAgents` |
| `TestOracleCatalogo` | `TestOracleCatalog` |
| `TestOracleRbacUsuarios` | `TestOracleRbacUsers` |
| `TestOrigemPermitida` | `TestAllowedOrigin` |
| `TestPacoteSobeSemODev` | `TestPackageStartsWithoutDev` |
| `TestPaginacaoInfo` | `TestPaginationInfo` |
| `TestPainelAgentes` | `TestAgentsDashboard` |
| `TestParada` | `TestShutdown` |
| `TestPassos` | `TestSteps` |
| `TestPastaDeSaida` | `TestOutputDir` |
| `TestPastasLog` | `TestLogDirs` |
| `TestPausaRetomada` | `TestPauseResume` |
| `TestPendencias` | `TestPending` |
| `TestPermissoes` | `TestPermissions` |
| `TestPodeExecutar` | `TestCanExecute` |
| `TestPoliticaSenha` | `TestPasswordPolicy` |
| `TestPrecedencia` | `TestPrecedence` |
| `TestPrevalidacao` | `TestPrevalidation` |
| `TestPrevia` | `TestPreview` |
| `TestPrimeiraConexaoNaoEReconexao` | `TestFirstConnectionIsNotReconnection` |
| `TestPrimeiroCampoInvalido` | `TestFirstInvalidField` |
| `TestPrioridade` | `TestPriority` |
| `TestProcessos` | `TestProcesses` |
| `TestProtocolo` | `TestProtocol` |
| `TestProxima` | `TestNext` |
| `TestProximaExecucao` | `TestNextRun` |
| `TestPureza` | `TestPurity` |
| `TestQuadroRegistro` | `TestRecordPanel` |
| `TestQuemPode` | `TestWhoCan` |
| `TestRegexCadastro` | `TestRegistrationRegex` |
| `TestRegexQuantificadorLargo` | `TestWideQuantifierRegex` |
| `TestRegistroEsquema` | `TestSchemaRegistry` |
| `TestRegistroNosServicos` | `TestRecordInServices` |
| `TestRegressaoFailFast` | `TestFailFastRegression` |
| `TestRepoFactoryEIntegridade` | `TestRepoFactoryAndIntegrity` |
| `TestResponsavelMascarado` | `TestMaskedOwner` |
| `TestResumoInicial` | `TestHomeSummary` |
| `TestRetirarSenhas` | `TestStripPasswords` |
| `TestRocketSemSSL` | `TestRocketWithoutSSL` |
| `TestSaida` | `TestOutput` |
| `TestSaidaDoTicket` | `TestTicketOutput` |
| `TestSalvarTipos` | `TestSaveTypes` |
| `TestSanitizarPagina` | `TestSanitizePage` |
| `TestSanitizarTamanho` | `TestSanitizeSize` |
| `TestSaudeAgente` | `TestAgentHealth` |
| `TestSaudeOracle` | `TestHealthOracle` |
| `TestSchedulerFilaOracle` | `TestSchedulerQueueOracle` |
| `TestSchedulerSaidaOracle` | `TestSchedulerOutputOracle` |
| `TestSeedColunasRegistro` | `TestSeedRecordColumns` |
| `TestSemBanco` | `TestWithoutDb` |
| `TestSemHashELink` | `TestNoHashAndLink` |
| `TestSenhaEBloqueio` | `TestPasswordAndLock` |
| `TestSensivelETeste` | `TestSensitiveAndTest` |
| `TestSessaoExpirada` | `TestSessionExpired` |
| `TestSessaoRevogavel` | `TestRevocableSession` |
| `TestSinalDeParada` | `TestStopSignal` |
| `TestSintaxe` | `TestSyntax` |
| `TestSondagemComAContaDoPapel` | `TestProbeWithRoleAccount` |
| `TestSondarDriverScript` | `TestProbeDriverScript` |
| `TestSqlRepoSaude` | `TestSqlRepoHealth` |
| `TestSubidaOracle` | `TestStartupOracle` |
| `TestTabelas` | `TestTables` |
| `TestTemFunc` | `TestHasFeature` |
| `TestTicketConsulta` | `TestTicketQuery` |
| `TestTravaParadaPrivilegio` | `TestLockStopPrivilege` |
| `TestUltimasExecucoes` | `TestLastRuns` |
| `TestUltimoAdmin` | `TestLastAdmin` |
| `TestUltimoAdminFake` | `TestLastAdminFake` |
| `TestUltimoAdminOracle` | `TestLastAdminOracle` |
| `TestUtilitarios` | `TestUtilities` |
| `TestValidacao` | `TestValidation` |
| `TestValidacoesDeCaminho` | `TestPathValidations` |
| `TestValidacoesTextuais` | `TestTextValidations` |
| `TestValidarCronComFim` | `TestValidateCronWithEnd` |
| `TestValidarExecucao` | `TestValidateExecution` |
| `TestValidarNext` | `TestValidateNext` |
| `TestValidarRegra` | `TestValidateRule` |
| `TestValidarSnapshot` | `TestValidateSnapshot` |
| `TestValidarValor` | `TestValidateValue` |
| `TestVerificacoes` | `TestChecks` |
| `TestVerificarAlpineCsp` | `TestCheckAlpineCsp` |
| `TestVinculos` | `TestLinks` |
| `_AgendaVazia` | `_EmptyAgenda` |
| `_ArquivoOcioso` | `_IdleFile` |
| `_Banco` | `_Db` |
| `_BasePerfis` | `_BaseProfiles` |
| `_ClobFalso` | `_FakeClob` |
| `_ComProcessos` | `_WithProcesses` |
| `_Conexao` | `_Connection` |
| `_ConexaoGravadora` | `_RecordingConnection` |
| `_ConexaoOciosa` | `_IdleConnection` |
| `_ConexaoRoteirizada` | `_ScriptedConnection` |
| `_ConnAgora` | `_ConnNow` |
| `_ConnAnexar` | `_ConnAppend` |
| `_ConnFalsa` | `_FakeConn` |
| `_CursorAnexar` | `_CursorAppend` |
| `_CursorGravador` | `_RecordingCursor` |
| `_CursorRoteirizado` | `_ScriptedCursor` |
| `_DoisAgentesBase` | `_TwoAgentsBase` |
| `_Erro` | `_Error` |
| `_ErroPrivilegio` | `_PrivilegeError` |
| `_ErroRede` | `_NetworkError` |
| `_FakeSegredos` | `_FakeSecrets` |
| `_Fila` | `_Queue` |
| `_Massa` | `_Fixtures` |
| `_OracleContrato` | `_OracleContract` |
| `_PlatDisco` | `_PlatDisk` |
| `_Relogio` | `_Clock` |
| `_RepoFalso` | `_FakeRepo` |
| `_Tipos` | `_Types` |
| `_nada` | `_nothing` |

### Funções e constantes de módulo

| Antes | Depois |
|---|---|
| `AGENTE` | `AGENT` |
| `AGENTE_FALSO` | `FAKE_AGENT` |
| `AGORA` | `NOW` |
| `AMBIENTE` | `ENVIRONMENT` |
| `ANTIGA` | `OLD` |
| `ARQUIVOS` | `FILES` |
| `ARQUIVOS_EXCECAO_TOKENS` | `TOKEN_EXCEPTION_FILES` |
| `ATOR` | `ACTOR` |
| `BLOQUEIO_S` | `LOCKOUT_S` |
| `CATALOGO` | `CATALOG` |
| `CHAVES_6_5` | `KEYS_6_5` |
| `CONFIG_CRITICOS` | `CRITICAL_CONFIG` |
| `CRITICOS` | `CRITICAL` |
| `CfgAgente` | `AgentCfg` |
| `ETAPAS` | `STAGES` |
| `GRANDE` | `LARGE` |
| `GUIA` | `GUIDE` |
| `HOJE` | `TODAY` |
| `HOMOLOGACOES` | `HOMOLOGATIONS` |
| `HORIZONTE` | `HORIZON` |
| `INICIO` | `START` |
| `LIMIARES` | `THRESHOLDS` |
| `MARCA_LONGO` | `LONG_MARK` |
| `MINUTOS` | `MINUTES` |
| `MODO_ARQ` | `FILE_MODE` |
| `MODO_DIR` | `DIR_MODE` |
| `NOVA` | `NEW` |
| `PADROES_PROIBIDOS` | `FORBIDDEN_PATTERNS` |
| `PALETA_KYROS` | `KYROS_PALETTE` |
| `PARES_INDICADOR` | `INDICATOR_PAIRS` |
| `PARES_TEXTO` | `TEXT_PAIRS` |
| `PASSO_13_S` | `STEP_13_S` |
| `PID_INEXISTENTE` | `NONEXISTENT_PID` |
| `RAIZ` | `ROOT` |
| `REGRA` | `RULE` |
| `SEGREDO` | `SECRET` |
| `SEGREDO_SEED` | `SEED_SECRET` |
| `SENHA_AMB` | `ENV_PASSWORD` |
| `SENHA_DEV` | `DEV_PASSWORD` |
| `SENHA_NOVA` | `NEW_PASSWORD` |
| `SESSAO_ADMIN` | `ADMIN_SESSION` |
| `SESSOES` | `SESSIONS` |
| `SETA` | `ARROW` |
| `TETO` | `CAP` |
| `TEXTO_MB` | `MB_TEXT` |
| `_Agente` | `_AgentStub` |
| `_COPIA` | `_COPY` |
| `_FILHO` | `_CHILD` |
| `_PADRAO` | `_PATTERN` |
| `_PADROES_12C` | `_PATTERNS_12C` |
| `_PADROES_COMPILADOS` | `_COMPILED_PATTERNS` |
| `_PALAVRAS_CREDENCIAL` | `_CREDENTIAL_WORDS` |
| `_PYTHON_FALSO` | `_FAKE_PYTHON` |
| `_agente` | `_agent` |
| `_arvore` | `_tree` |
| `_blocos` | `_chunks` |
| `_carregar_helper` | `_load_helper` |
| `_casa_bruto` | `_raw_match` |
| `_conteudo` | `_content` |
| `_corpo` | `_body` |
| `_criar_arvore` | `_create_tree` |
| `_dias` | `_days` |
| `_esperar` | `_wait` |
| `_fluxo` | `_stream` |
| `_hash_com_iteracoes` | `_hash_with_iterations` |
| `_ler` | `_read` |
| `_ler_csv` | `_read_csv` |
| `_ler_pid` | `_read_pid` |
| `_luminancia` | `_luminance` |
| `_pids_do_longo` | `_long_pids` |
| `_preparar_banco_real` | `_prepare_real_db` |
| `_remover` | `_remove` |
| `_remover_arvore` | `_remove_tree` |
| `_restaurar_banco_real` | `_restore_real_db` |
| `_segredos` | `_secrets` |
| `_sessao` | `_session` |
| `_vinculo` | `_link` |
| `_vivo` | `_alive` |
| `compilar_arquivo_py` | `compile_py_file` |
| `contraste` | `contrast` |
| `diaria` | `daily` |
| `encontrar_arquivos_python` | `find_python_files` |
| `prox` | `next_run` |
| `regra` | `rule` |
| `sem_micro` | `without_micro` |
| `sequencia` | `sequence` |
| `verificar_imports_driver_oracle` | `check_oracle_driver_imports` |
| `verificar_primitivas_so` | `check_os_primitives` |
| `verificar_tokens_proibidos_em_arquivo` | `check_forbidden_tokens_in_file` |
| `verificar_urls_externas_em_arquivo` | `check_external_urls_in_file` |

### Métodos (não `test_*`)

| Antes | Depois |
|---|---|
| `_acoes` | `_actions` |
| `_alterado` | `_changed` |
| `_arquivo` | `_file` |
| `_auditorias` | `_audits` |
| `_base_saida` | `_output_base` |
| `_cancelar_com` | `_cancel_with` |
| `_carregar` | `_load` |
| `_cfg_com_log_dir` | `_cfg_with_log_dir` |
| `_codigo` | `_code` |
| `_codigos` | `_codes` |
| `_como_banco` | `_as_db` |
| `_conferir_alteracao` | `_check_update` |
| `_conferir_inclusao` | `_check_insert` |
| `_consulta` | `_query` |
| `_contar` | *passada final* |
| `_contar_por_ip` | `_count_by_ip` |
| `_copiar_e_modificar_ini` | `_copy_and_edit_ini` |
| `_criar` | `_create` |
| `_criar_cfg` | `_create_cfg` |
| `_criar_secrets_temporario` | `_create_temp_secrets` |
| `_dados` | `_data` |
| `_dados_agente` | `_agent_data` |
| `_derrubar_agentes` | `_kill_agents` |
| `_editar` | `_edit` |
| `_elegiveis` | `_eligible` |
| `_errar` | `_fail_login` |
| `_erro` | `_error` |
| `_escrever` | `_write` |
| `_esperar` | `_wait` |
| `_estado` | `_state` |
| `_executar` | *passada final* |
| `_executavel` | `_executable` |
| `_exportacoes` | `_exports` |
| `_fila_diagnostico` | `_queue_diagnostics` |
| `_fixtures_do_seed` | `_seed_fixtures` |
| `_grupo` | `_group` |
| `_helper_saida` | `_helper_output` |
| `_inserir` | `_insert_row` |
| `_itens` | `_items` |
| `_ler_log_app` | `_read_app_log` |
| `_ler_tudo` | `_read_all` |
| `_limpar` | `_clean` |
| `_limpar_agentes` | `_clean_agents` |
| `_limpar_massa` | `_clean_fixtures` |
| `_limpar_registro` | `_clean_registration` |
| `_limpar_tudo` | `_clean_all` |
| `_linha` | *passada final* |
| `_linhas` | `_lines` |
| `_log_integral` | `_full_log` |
| `_minuto` | `_minute` |
| `_minuto_exec` | `_run_minute` |
| `_nomes` | `_names` |
| `_novo_admin_com_usuario` | `_new_admin_with_user` |
| `_obter_arquivos_sql` | `_get_sql_files` |
| `_obter_com_ini` | `_get_with_ini` |
| `_obter_prefixo_config_example` | `_get_config_example_prefix` |
| `_pacote` | `_package` |
| `_pasta` | `_dir` |
| `_pasta_do_ticket` | `_ticket_dir` |
| `_pastas_de_saida` | `_output_dirs` |
| `_pastas_invalidas` | `_invalid_dirs` |
| `_preencher` | `_fill` |
| `_recusa` | `_refusal` |
| `_recusada` | `_refused_f` |
| `_recusado` | `_refused` |
| `_registrar` | `_register` |
| `_regra_ok` | `_rule_ok` |
| `_responder` | `_reply` |
| `_resumo` | `_summary` |
| `_rodando` | `_running` |
| `_rodar` | `_run_loop` |
| `_salvar` | `_save` |
| `_salvar_matriz` | `_save_matrix` |
| `_saude` | `_health` |
| `_saudes` | `_healths` |
| `_sem` | `_without` |
| `_sem_segredo` | `_without_secret` |
| `_sem_transacao` | `_without_transaction` |
| `_servico` | `_service` |
| `_sessao` | `_session` |
| `_subir` | `_start_agent` |
| `_ticket_de_outro` | `_other_ticket` |
| `_ticket_do_agente` | `_agent_ticket` |
| `_total_tickets` | `_ticket_total` |
| `_travar` | `_lock` |
| `_ultimo_logout` | `_last_logout` |
| `_um` | `_one` |
| `_versao` | `_version` |
| `_vinculos_json` | `_links_json` |
| `agendamento` | `schedule` |
| `agente` | `agent` |
| `ambiente` | `environment` |
| `anexar_bytes` | `append_bytes` |
| `anotar` | `note` |
| `arquivo` | `file` |
| `assertNegado` | `assertDenied` |
| `assertReprova` | `assertRejects` |
| `ate_sair` | `until_exit` |
| `aud_ultima` | `aud_last` |
| `auditorias` | `audits` |
| `avancar` | `advance` |
| `cenario` | `scenario` |
| `concluido` | `completed` |
| `construir` | `build` |
| `contar` | `count` |
| `drenar` | `drain` |
| `encerrar` | `stop` |
| `falha` | `failure` |
| `grupo` | `group` |
| `iniciar_tx` | `start_tx` |
| `parametro` | `parameter` |
| `perfil` | `profile` |
| `regra` | `rule` |
| `rodar` | `run_loop` |
| `subir` | `start_agent` |
| `terminado` | `finished` |
| `tickets_running_do_agente` | *passada final* |
| `usuario` | *passada final* |
| `validar` | `validate` |

### Atributos

| Antes | Depois |
|---|---|
| `AGENTE` | `AGENT` |
| `AGORA` | `NOW` |
| `DIAS` | `DAYS` |
| `MOTIVOS` | `REASONS` |
| `ORDEM` | `ORDER` |
| `PERMITIDAS` | `ALLOWED` |
| `PREFIXO_AGENTE` | `AGENT_PREFIX` |
| `TICKET_OUTRO_AMB` | `TICKET_OTHER_ENV` |
| `TICKET_PROPRIO` | `TICKET_OWN` |
| `TICKET_TERCEIRO` | `TICKET_THIRD_PARTY` |
| `_LIGADO` | `_ENABLED` |
| `_antes` | `_before` |
| `_cenario` | `_scenario` |
| `_contagens` | `_counts` |
| `_espera` | `_wait_s` |
| `_massa` | `_fixtures` |
| `_sss_cfg_anterior` | `_previous_sss_cfg` |
| `_tipos` | *passada final* |
| `_troca` | `_overrides` |
| `_uma` | *passada final* |
| `agente` | `agent` |
| `agente_ativo` | `active_agent` |
| `agoras` | `nows` |
| `ambiente` | `environment` |
| `ator` | `actor` |
| `banco` | `db` |
| `caminho_arquivo` | `file_path` |
| `carregar` | `load` |
| `chamadas` | `calls` |
| `claim_respostas` | `claim_answers` |
| `commit_incerto_persistiu` | `uncertain_commit_persisted` |
| `conexoes` | `connections` |
| `contagem` | `count` |
| `contagens` | `counts` |
| `conteudo` | `content` |
| `criados` | `created` |
| `disparo` | `trigger` |
| `divergentes` | `divergent` |
| `dono` | `owner` |
| `duplicado` | `duplicated` |
| `duplicar` | `duplicate` |
| `encerrou` | `stopped_flag` |
| `entradas` | `inputs` |
| `erro` | `error` |
| `executados` | `executed` |
| `falhar` | `fail` |
| `falhar_commit` | `fail_commit` |
| `falhar_em` | `fail_at` |
| `falhas` | *passada final* |
| `falsos` | `fakes` |
| `fechada` | `closed` |
| `fechamentos` | `closings` |
| `fila` | *passada final* |
| `fora` | `down` |
| `grants_texto` | `grants_text` |
| `grupos` | `groups` |
| `homologacoes` | `homologations` |
| `homologados` | *passada final* |
| `horizonte` | *passada final* |
| `instante` | `instant` |
| `instrucoes` | `statements` |
| `limpas` | `cleaned` |
| `linhas` | `rows` |
| `mascarados` | `masked` |
| `monotonico` | `monotonic` |
| `n_auditoria` | `n_audit` |
| `node_offline_chamadas` | `node_offline_calls` |
| `operador` | `operator` |
| `origem` | *passada final* |
| `papeis` | `roles` |
| `pendentes` | `pending` |
| `perfil` | `profile` |
| `prefixo` | *passada final* |
| `processos` | `processes` |
| `raiz` | `root` |
| `registro` | *passada final* |
| `regras` | `rules` |
| `relogio` | *passada final* |
| `roteiro` | `script_steps` |
| `roubar_na_renovacao` | `steal_on_renewal` |
| `saida` | *passada final* |
| `segredos` | *passada final* |
| `senha` | `password` |
| `servico` | `service` |
| `servicos` | `services` |
| `sinais` | `signals` |
| `sysdate_deslocamento_s` | `sysdate_offset_s` |
| `temas` | `themes` |
| `texto` | *passada final* |
| `tipos` | `types` |
| `tomadas` | `taken` |
| `travadas_por_outro` | `locked_by_other` |
| `travas` | `locks` |
| `unidade` | `unit` |
| `usuario` | *passada final* |
| `usuario_id` | *passada final* |
| `valor` | `value` |
| `versao` | `version` |

## 19. Validação do bloco 5b

* Suítes em 3.6.0, 3.6.8 e 3.13.2, bateria Oracle, testes progressivos nos cinco agregados, percurso real das telas e conferência de resíduos.
* Achados e corrigidos: atribuições no corpo da classe (`ORDEM = …`, `_copiar_e_modificar_ini = OutraClasse.metodo`), que a troca por atributo não alcança; um `getattr` com o nome do atributo vindo de uma tupla de strings em `test_scheduler_ha`. A bateria Oracle pegou ainda o módulo `test_repo_contract` guardado em atributo (`self.trc._Massa`, em sete arquivos), que a ferramenta por escopo não reconhece.
* Para a passada final: o método de produção `tickets_running_do_agente`, ainda em português.

## 20. Passada final, parte F1 (atributos e estruturas)

Plano da passada final (aprovado em 2026-10-21): F1 atributos e estruturas; F2 binds de SQL e abreviações de tabela dos templates; F3 parâmetros (com os `nome=` das chamadas); F4 variáveis locais e variáveis dos lançadores `.sh`. Parâmetros e locais dos controllers e models ficam para o CR-016d.

| # | Decisão | Resumo |
|---|---|---|
| D20 | Snapshot v5 | Chaves do snapshot em `tbsss_tickets.submitted_params` em inglês (`script_name`, `answers`, `sensitive`, `compiled_at`), `SNAPSHOT_VERSION` 5, troca direta: o agente recusa as versões 1 a 4 (`VERSAO_NAO_SUPORTADA`). O CR-016a já recria o banco, então não há ticket v4 num ambiente atualizado |

As chaves de tela entregues às views (`script_nome`, `respostas`, `compilado_em` no detalhe do ticket) ficam para o CR-016d; o detalhe lê `compiled_at` do snapshot e entrega `compilado_em` à view.

### Atributos de instância

| Antes | Depois |
|---|---|
| `_agendamentos` | `_schedules` |
| `_agentes` | `_agents` |
| `_auditoria` | `_audit` |
| `_avisos` | `_warnings` |
| `_bloqueio` | `_lockout` |
| `_bloqueio_s` | `_lockout_s` |
| `_cache_matriz` | `_matrix_cache` |
| `_catalogo` | `_catalog` |
| `_config_criticos` | `_critical_config` |
| `_disparo` | `_trigger_service` |
| `_horizonte` | `_horizon` |
| `_it_dia` | `_it_day` |
| `_it_dsem` | `_it_wday` |
| `_it_hora` | `_it_hour` |
| `_it_mes` | `_it_month` |
| `_ja_conectou` | `_connected_once` |
| `_limiares` | `_thresholds` |
| `_lista_hora` | `_hour_list` |
| `_lista_min` | `_minute_list` |
| `_mascarador` | `_masker` |
| `_pendente` | `_pending` |
| `_regra_atual` | `_current_rule` |
| `_relogio` | `_clock` |
| `_relogio_fn` | `_clock_fn` |
| `_segredos` | `_secrets` |
| `_simulados` | `_simulated` |
| `_sql_encerrar` | `_sql_finish` |
| `_sql_falhar` | `_sql_fail` |
| `_sql_incluir_gravando` | `_sql_insert_writing` |
| `_sql_incluir_sem_conteudo` | `_sql_insert_without_content` |
| `_sql_reiniciar` | `_sql_restart` |
| `_sql_situacao` | `_sql_state` |
| `_sql_truncado` | `_sql_truncated` |
| `_usuarios` | `_users` |
| `agente_id` | `agent_id` |
| `agentes_hb_sim` | `agents_hb_simulated` |
| `codigo_param` | `param_code` |
| `dia_restrito` | `day_restricted` |
| `dias` | `days` |
| `dias_semana` | `weekdays` |
| `dsem_restrito` | `wday_restricted` |
| `em_falha` | `failing` |
| `erros` | `errors` |
| `falhas` | `failures` |
| `fila` | `queue` |
| `horas` | `hours` |
| `horizonte` | `horizon` |
| `lock_agendamentos` | `lock_schedules` |
| `lock_agentes` | `lock_agents` |
| `lock_auditoria` | `lock_audit` |
| `lock_catalogo` | `lock_catalog` |
| `lock_usuarios` | `lock_users` |
| `log_sim` | `log_simulated` |
| `mascarador` | `masker` |
| `mensagem` | `message` |
| `meses` | `months` |
| `minutos` | `minutes` |
| `msg_bloqueio` | `lockout_message` |
| `nome_processo` | `process_name` |
| `offset_esperado` | `expected_offset` |
| `papel` | `role` |
| `proxima_tentativa_monotonic` | `next_attempt_monotonic` |
| `relogio` | `clock` |
| `segredos` | `secrets` |
| `tamanho` | `size` |
| `texto` | `text` |

### Método

| Antes | Depois |
|---|---|
| `tickets_running_do_agente` | `agent_running_tickets` |

### namedtuples

* `db_conn.SelecaoDriver` → `DriverSelection`: `candidato` → `candidate`, `versao_servidor` → `server_version`, `versao_driver` → `driver_version`, `versao_cliente` → `client_version`.
* `ddl_builder.DDLItem` (tipo `ItemDDL` → `DDLItem`): `fase` → `phase`, `tipo` → `kind`, `nome` → `name`, `entidade` → `entity`.
* Nomes de tipo `RetencaoConfig` → `RetentionConfig` e `Limiares` → `Thresholds`.

### JSON do `probe_driver`

| Antes | Depois |
|---|---|
| `candidato` | `candidate` |
| `codigo_erro` | `error_code` |
| `versao_cliente` | `client_version` |
| `versao_driver` | `driver_version` |
| `versao_servidor` | `server_version` |

Categorias:

| Antes | Depois |
|---|---|
| `AUTENTICACAO` | `AUTHENTICATION` |
| `BIBLIOTECA` | `LIBRARY` |
| `CANDIDATO_INVALIDO` | `INVALID_CANDIDATE` |
| `ERR_OUTRO` | `ERR_OTHER` |
| `INCOMPATIVEL` | `INCOMPATIBLE` |
| `OUTRO` | `OTHER` |
| `REDE` | `NETWORK` |

## 21. Validação da F1

* Suítes em 3.6.0, 3.6.8 e 3.13.2, bateria Oracle, testes progressivos nos cinco agregados, `probe_driver` real (conecta; com senha errada, `AUTHENTICATION`), ciclo real do agente (snapshot v5 de ponta a ponta), percurso real das telas e conferência de resíduos.
* Achados e corrigidos: kwargs do construtor da namedtuple e de `mock.Mock(...)`, que a troca por atributo não alcança; código em string de subprocesso (`get_selection().candidato`); argumento posicional do `argparse` (`args.candidato`); helpers de teste com `version=4` como padrão. A ferramenta de comentários passou a tratar só docstrings de verdade (um bloco PL/SQL entre três aspas parou na proteção por AST, sem alteração).
* README §6.5: o exemplo do snapshot ainda mostrava chaves anteriores ao CR-016a (`versao`, `interpretador`, `tipo_param`); passou ao formato v5.

## 22. Passada final, parte F2 (binds de SQL e abreviações de tabela)

Cada bind mudou junto no SQL (`:nome`), nas chaves dos dicionários de bind (literais e `binds["…"] = …`), nos kwargs de `execute`/`set_input_types`, nas tuplas `datas=(…)` e nos binds gerados (`_placeholders`, `"env%d" % i`). As abreviações de tabela passaram às siglas físicas do `sql_ident` (`TABLES[e]['abrev']`), as mesmas dos nomes de constraint desde o CR-016a.

Ficam como estão: `"dono"` (nome do papel da conta dona do esquema em `db_conn`/`init_db`) e as chaves de filtro que vêm dos services (`filtros["criado_inicio"]`…), que são da camada web (CR-016d).

### Binds

| Antes | Depois |
|---|---|
| `a_nome` | `env_name` |
| `acao_f` | `action_f` |
| `agora` | `now` |
| `amb` | `env` |
| `amb_nome` | `env_name` |
| `ambiente_f` | `environment_f` |
| `antiga_data` | `old_date` |
| `ativo_f` | `active_f` |
| `ator_f` | `actor_f` |
| `bloq_f` | `locked_f` |
| `bloqueio_s` | `lockout_s` |
| `codigo_f` | `code_f` |
| `criado_fim` | `created_to` |
| `criado_inicio` | `created_from` |
| `desde` | `since` |
| `destino` | `target` |
| `dono` | `owner` |
| `entidade_f` | `entity_f` |
| `entidade_id_f` | `entity_id_f` |
| `fim` | `end_ts` |
| `inicio` | `start_ts` |
| `limite` | `cutoff` |
| `lote` | `batch_size` |
| `max_paral` | `max_par` |
| `nome_f` | `name_f` |
| `nome_u` | `user_name` |
| `nova_data` | `new_date` |
| `offset_esperado` | `expected_offset` |
| `origem` | `source` |
| `p_cod` | `p_code` |
| `parametros` | `params` |
| `parte` | `part` |
| `per_nome` | `prf_name` |
| `perfil` | `profile` |
| `perfil_f` | `profile_f` |
| `resultado` | `result` |
| `s_nome` | `scr_name` |
| `solicitante_f` | `requester_f` |
| `ult_id` | `last_id` |
| `ult_prox` | `last_next` |
| `usuario_id_f` | `user_id_f` |
| `valor` | `value` |

### Abreviações de tabela (chaves de template e de `_idents`)

| Antes | Depois |
|---|---|
| `agd` | `sch` |
| `amb` | `env` |
| `fnc` | `fea` |
| `func` | `fea` |
| `ocor` | `occ` |
| `pamb` | `penv` |
| `per` | `prf` |
| `pfnc` | `pfea` |
| `pfunc` | `pfea` |
| `resp` | `tans` |
| `sai` | `tout` |
| `samb` | `senv` |

### Atributos de tabela

| Antes | Depois |
|---|---|
| `_agd` | `_sch` |
| `_amb` | `_env` |
| `_func` | `_fea` |
| `_ocor` | `_occ` |
| `_pamb` | `_penv` |
| `_per` | `_prf` |
| `_pfunc` | `_pfea` |
| `_resp` | `_tans` |
| `_samb` | `_senv` |
| `_seq_agd` | `_seq_sch` |
| `_seq_resp` | `_seq_tans` |

### Variáveis `tb_`/`sq_` (`init_db`, `ddl_builder`)

| Antes | Depois |
|---|---|
| `sq_amb` | `sq_env` |
| `sq_fnc` | `sq_fea` |
| `sq_pamb` | `sq_penv` |
| `sq_per` | `sq_prf` |
| `sq_pfnc` | `sq_pfea` |
| `sq_samb` | `sq_senv` |
| `tb_amb` | `tb_env` |
| `tb_fnc` | `tb_fea` |
| `tb_pamb` | `tb_penv` |
| `tb_per` | `tb_prf` |
| `tb_pfnc` | `tb_pfea` |
| `tb_samb` | `tb_senv` |

### Outras chaves de template (geração do seed)

| Antes | Depois |
|---|---|
| `a_nome` | `env_name` |
| `amb_nome` | `env_name` |
| `atrib` | `attr` |
| `cod` | `code` |
| `coluna` | `column` |
| `escopo` | `scope` |
| `etp` | `stage` |
| `f_cod` | `f_code` |
| `lista` | `items` |
| `obrig` | `req` |
| `opc` | `opts` |
| `p_cod` | `p_code` |
| `paral` | `par` |
| `per_nome` | `prf_name` |
| `perfil` | `profile` |
| `pnom` | `pname` |
| `s_nome` | `scr_name` |
| `tcomp` | `ctype` |
| `tpar` | `ptype` |
| `vpad` | `vdef` |
| `vsub` | `vovr` |

## 23. Validação da F2

* `generate_sql.py`: `01_deploy_sss.sql`, `02_rollback_sss.sql` e `99_validate_deploy.sql` gerados byte a byte iguais aos versionados (as chaves de template só existem no Python).
* Suítes em 3.6.0, 3.6.8 e 3.13.2, bateria Oracle, testes progressivos nos cinco agregados, ciclo real do agente, percurso real das telas e conferência de resíduos.
* README, AGENTS e docs/explain com os binds novos; o bloco PL/SQL do README é conferido literalmente por `test_log_pump`.
* Achados e corrigidos: literais adjacentes em várias linhas (uma constante só no AST), tratados por token; chave de bind montada sem dois-pontos (`"amb%d" % i`); binds lidos por nome nos fakes de teste. Os testes progressivos pegaram um defeito que teria ido para a tela: no filtro por data da lista de tickets, o dicionário de tipos (`datas["criado_inicio"]`) não acompanhou o bind (`:created_from`), e o driver recusaria a consulta (DPY-4008); corrigido. O mesmo agregado pegou ainda o `{scope}` das últimas execuções e do histórico de tickets, formatado por `_sql_dinamico(…, escopo=…)`, caminho que a troca de kwargs não cobria; corrigido. O `tb_amb` indefinido do seed do `init_db` (bug anterior, pendente por decisão do usuário) passou a `tb_env`.

## 24. Passada final, parte F3 (parâmetros)

Parâmetros de `modules/`, `scripts/`, testes e `bin/sss-helper` (cerca de 1.280 definições, 7.660 trocas). Cada parâmetro mudou na assinatura e nos usos do corpo, por escopo (funções aninhadas só quando não religam o nome; valores padrão e decoradores ficam no escopo de fora), e nas chamadas por nome (`nome=`) resolvidas pelo índice de definições do projeto (1.163, inclusive as dos controllers para funções de `modules/`; o repasse por `**kwargs` é aceito). Os parâmetros dos controllers e models ficam para o CR-016d.

Não mudam: kwargs de `dict(...)` e `.update(...)` (dados e chaves de tela), de `subTest(...)` (rótulos de teste) e de `ui_helpers.mensagem(..., minutos=)` (placeholders de texto); aliases de SQL (`MIN(inicio)`) e fórmulas descritivas nas docs.

| Antes | Depois |
|---|---|
| `_segredos` | `_secrets` |
| `_tipos` | `_types` |
| `acao` | `action` |
| `acao_padrao` | `default_action` |
| `admin_nome` | `admin_name` |
| `admin_senha` | `admin_password` |
| `admin_senha_hash` | `admin_password_hash` |
| `agd_ids` | `sch_ids` |
| `agenda` | `schedule_repo` |
| `agendamento` | `schedule` |
| `agendamento_id` | `schedule_id` |
| `agendamentos` | `schedules` |
| `agente` | `agent` |
| `agente_id` | `agent_id` |
| `agentes` | `agents` |
| `agora` | `now` |
| `agora_monotonico` | `now_monotonic` |
| `alteracoes` | `changes` |
| `altura` | `height` |
| `alvos` | `targets` |
| `amb` | `env` |
| `ambiente` | `environment` |
| `ambiente_id` | `environment_id` |
| `ambiente_ids` | `environment_ids` |
| `ambiente_nome` | `environment_name` |
| `ambientes` | `environments` |
| `ambs` | `envs` |
| `analisados` | `analyzed` |
| `ano` | `year` |
| `ano_str` | `year_str` |
| `anteriores` | `previous` |
| `antes` | `before` |
| `antiga` | `old` |
| `antiga_data` | `old_date` |
| `apagadas` | `deleted` |
| `apenas_ativos` | `active_only` |
| `apos` | `after` |
| `armazenado` | `stored` |
| `arquivo` | `file` |
| `arquivos` | `files` |
| `ate` | `until` |
| `atendidos` | `served` |
| `ator` | `actor` |
| `atuais` | `current` |
| `atual` | `current_value` |
| `auditoria` | `audit` |
| `auditoria_bloqueio` | `lock_audit` |
| `avisos` | `warnings` |
| `banco` | `db` |
| `bloco` | `chunk` |
| `blocos` | `chunks` |
| `bloqueio_s` | `lockout_s` |
| `bloqueou` | `locked` |
| `bomba` | `pump` |
| `bombas` | `pumps` |
| `caminho` | `path` |
| `caminho_final` | `final_path` |
| `caminho_ini` | `ini_path` |
| `caminho_log` | `log_path` |
| `campo` | `field` |
| `campos` | `fields` |
| `candidato` | `candidate` |
| `carregar_config` | `load_config` |
| `carregar_segredos` | `load_secrets` |
| `caso` | `case` |
| `catalogo` | `catalog` |
| `causa` | `cause` |
| `cfg_agente` | `agent_cfg` |
| `cfg_erro` | `cfg_error` |
| `cfg_sondagem` | `probe_cfg` |
| `chave` | `key_name` |
| `chave_grupo` | `group_key` |
| `chaves_remover` | `keys_to_remove` |
| `clausulas` | `clauses` |
| `codigo` | `code` |
| `codigo_param` | `param_code` |
| `codigos` | `codes` |
| `col_nome` | `col_name` |
| `colunas` | `columns` |
| `comando` | `command` |
| `comparar_com` | `compare_with` |
| `condicao` | `condition` |
| `conectar` | `connect` |
| `conexao` | `connection` |
| `confirmacao` | `confirmation` |
| `contagem` | `count` |
| `contagens` | `counts` |
| `contar` | `count_only` |
| `conteudo` | `content` |
| `contexto` | `context` |
| `continuar` | `keep_going` |
| `corpo` | `body` |
| `corte` | `cutoff` |
| `criar` | `create` |
| `criticos` | `critical` |
| `dados` | `data` |
| `data` | `date` |
| `datas` | `dates` |
| `dec` | `decision` |
| `depois` | `after_value` |
| `desde` | `since` |
| `destino` | `destination` |
| `destino_fd` | `destination_fd` |
| `detalhe` | `detail` |
| `detalhe_padrao` | `default_detail` |
| `detalhes` | `details` |
| `dia` | `day` |
| `dia_mes` | `month_day` |
| `dia_str` | `day_str` |
| `dias` | `days` |
| `dias_semana` | `weekdays` |
| `dicionario` | `mapping` |
| `diretorio` | `directory` |
| `dirs_sss` | `sss_dirs` |
| `disparo` | `trigger_service` |
| `dono` | `owner` |
| `entidade` | `entity` |
| `entidade_id` | `entity_id` |
| `entrada` | `input_value` |
| `envelhecimento_min` | `aging_min` |
| `enviados` | `submitted` |
| `erro` | `error` |
| `erros` | `errors` |
| `escopo_ambientes` | `environment_scope` |
| `especificacao` | `spec` |
| `esperado` | `expected` |
| `esperar` | `wait` |
| `estado` | `state` |
| `estados` | `states` |
| `execucao` | `execution` |
| `executar` | `run` |
| `executavel` | `executable` |
| `executor_sondagem` | `probe_runner` |
| `existe` | `exists` |
| `exportar` | `export` |
| `falhar` | `fail` |
| `falhar_commit` | `fail_commit` |
| `falhas` | `failures` |
| `fila` | `queue` |
| `filtro` | `filter_value` |
| `filtros` | `filters` |
| `fim` | `end` |
| `fonte` | `source` |
| `forcar` | `force` |
| `funcao` | `function` |
| `funcionalidades` | `features` |
| `funcs` | `features_ids` |
| `hoje` | `today` |
| `homologacoes` | `homologations` |
| `homologar` | `homologate` |
| `hora` | `hour` |
| `hora_str` | `hour_str` |
| `horas` | `hours` |
| `horizonte` | `horizon` |
| `horizonte_dias` | `horizon_days` |
| `id_atual` | `current_id` |
| `idade_s` | `age_s` |
| `identidade` | `identity` |
| `incluir_colunas` | `include_columns` |
| `incluir_comentarios` | `include_comments` |
| `incluir_oracle` | `include_oracle` |
| `inicio` | `start` |
| `instante` | `instant` |
| `interpretador` | `interpreter` |
| `interpretadores` | `interpreters` |
| `it_hora` | `it_hour` |
| `itens` | `items` |
| `iteracoes` | `iterations` |
| `largura` | `width` |
| `ler` | `read` |
| `limiares` | `thresholds` |
| `limite` | `limit` |
| `limite_s` | `limit_s` |
| `limites` | `limits` |
| `limpos` | `cleaned` |
| `linha_sss` | `sss_line` |
| `linhas` | `rows` |
| `linhas_fila` | `queue_rows` |
| `lista` | `items_list` |
| `lista_ordenada` | `sorted_list` |
| `listar` | `list_fn` |
| `local` | `local_value` |
| `lote` | `batch` |
| `maiusculas` | `uppercase` |
| `manter` | `keep` |
| `mapa` | `mapping` |
| `mapa_existencia` | `existence_map` |
| `marca` | `mark` |
| `marca_ip` | `ip_mark` |
| `margem_esq` | `left_margin` |
| `margem_inf` | `bottom_margin` |
| `mascarador` | `masker` |
| `max_arquivos` | `max_files` |
| `max_tentativas` | `max_attempts` |
| `maximo` | `maximum` |
| `mensagem` | `message` |
| `mes` | `month` |
| `mes_str` | `month_str` |
| `metodo` | `method` |
| `minimo` | `minimum` |
| `minutos` | `minutes` |
| `minutos_atras` | `minutes_ago` |
| `modelo` | `template` |
| `modelo_conta` | `count_template` |
| `modelo_lista` | `list_template` |
| `modo` | `mode` |
| `montar` | `build` |
| `motivo` | `reason` |
| `motivo_rbac` | `rbac_reason` |
| `mudancas` | `changes` |
| `nivel` | `level` |
| `nome` | `name` |
| `nome_ck` | `ck_name` |
| `nome_log` | `log_name` |
| `nome_norm` | `normalized_name` |
| `nome_processo` | `process_name` |
| `nome_script` | `script_name` |
| `nomes` | `names` |
| `nova` | `new` |
| `nova_data` | `new_date` |
| `novo_hash` | `new_hash` |
| `obrigatorio` | `required_flag` |
| `obter_repo` | `get_repo` |
| `ocorrencia` | `occurrence` |
| `offset_confirmado_chars` | `confirmed_offset_chars` |
| `offset_esperado` | `expected_offset` |
| `opcional` | `optional` |
| `opcoes` | `options` |
| `operacao` | `operation` |
| `orcamento_s` | `budget_s` |
| `ordem` | `order` |
| `origem` | `source` |
| `origens` | `sources` |
| `owner_configurado` | `configured_owner` |
| `padrao` | `default_value` |
| `padrao_sub` | `default_override` |
| `pagina` | `page` |
| `papeis_usuarios` | `user_roles` |
| `papel` | `role` |
| `par` | `pair` |
| `parada` | `stop_event` |
| `parametro` | `parameter` |
| `parametro_id` | `parameter_id` |
| `parametro_ids` | `parameter_ids` |
| `pares` | `pairs` |
| `parte` | `part` |
| `partes` | `parts` |
| `passo` | `step` |
| `pasta` | `folder` |
| `pasta_base` | `base_dir` |
| `pasta_entrada` | `input_dir` |
| `pasta_saida` | `output_dir` |
| `pastas_usuarios` | `user_dirs` |
| `perfil` | `profile` |
| `perfil_ativo` | `active_profile` |
| `perfil_id` | `profile_id` |
| `perfis` | `profiles` |
| `perm_versao` | `perm_version` |
| `perm_versao_esperada` | `expected_perm_version` |
| `permitidos` | `allowed` |
| `plataforma_nome` | `platform_name` |
| `pode_ver_tickets` | `can_view_tickets` |
| `prazo` | `deadline` |
| `prefixo` | `prefix` |
| `prioridade` | `priority` |
| `problemas` | `problems` |
| `processo` | `process` |
| `processo_existe` | `process_exists` |
| `qtd` | `count_n` |
| `qtd_arquivos` | `file_count` |
| `quando` | `when` |
| `quantidade` | `quantity` |
| `raiz` | `root` |
| `recebido` | `received` |
| `recente` | `recent` |
| `reexecucao_de` | `rerun_of` |
| `registro` | `record` |
| `registro_perdido` | `registration_lost` |
| `registros` | `records` |
| `regra` | `rule` |
| `regra_id` | `rule_id` |
| `relativo` | `relative` |
| `relogio` | `clock` |
| `relogio_monotonico` | `monotonic_clock` |
| `relogio_parede` | `wall_clock` |
| `repo_agenda` | `repo_schedules` |
| `repo_filtros` | `repo_filters` |
| `repo_saida` | `repo_output` |
| `resolvidos` | `resolved` |
| `respostas` | `answers` |
| `resultado` | `result` |
| `retencao` | `retention` |
| `rota_atual` | `current_route` |
| `roteiro` | `script_steps` |
| `rotulo` | `label` |
| `rotulos` | `labels` |
| `saida` | `output` |
| `saida_texto` | `output_text` |
| `salto_de_relogio` | `clock_jump` |
| `secao` | `section_name` |
| `secoes` | `sections` |
| `secoes_remover` | `sections_to_remove` |
| `seg` | `secrets_obj` |
| `seg_erro` | `secrets_error` |
| `segredos` | `secrets` |
| `segredos_erro` | `secrets_error_flag` |
| `segundos` | `seconds` |
| `selecao` | `selection` |
| `sem_identidade` | `no_identity` |
| `senha` | `password_value` |
| `senha_dev` | `dev_password` |
| `senha_hash` | `password_hash` |
| `senha_sondagem` | `probe_password` |
| `sensiveis` | `sensitive` |
| `sensivel` | `sensitive_flag` |
| `sequence_qualificada` | `qualified_sequence` |
| `sinal` | `signal_value` |
| `situacao` | `state_value` |
| `solicitante` | `requester` |
| `status_motivo` | `status_reason` |
| `subcomando` | `subcommand` |
| `subir` | `start_agent` |
| `sufixo` | `suffix` |
| `tabela` | `table` |
| `tabelas` | `tables` |
| `tamanho` | `size` |
| `tamanho_bytes` | `size_bytes` |
| `tentativas` | `attempts` |
| `teto` | `cap` |
| `texto` | `text` |
| `texto_dsem` | `weekday_text` |
| `timeout_seg` | `timeout_sec` |
| `tipo` | `kind` |
| `tipo_neutro` | `neutral_type` |
| `tipo_param` | `param_type` |
| `tipos` | `types` |
| `topo` | `top` |
| `total_limitado` | `capped_total` |
| `trava` | `lock` |
| `trecho` | `snippet` |
| `troca` | `overrides` |
| `ult_id` | `last_id` |
| `ult_prox` | `last_next` |
| `ultimo_acesso` | `last_access` |
| `ultimos` | `latest` |
| `uma` | `once` |
| `unidade_suplementar` | `supplementary_unit` |
| `usuario` | `user` |
| `usuario_agente` | `agent_user` |
| `usuario_ativo` | `active_user` |
| `usuario_ctx` | `user_ctx` |
| `usuario_dono` | `owner_user` |
| `usuario_execucao` | `exec_user` |
| `usuario_id` | `user_id` |
| `usuario_sessao_esperado` | `expected_session_user` |
| `usuarios` | `users` |
| `valor` | `value` |
| `valor_bruto` | `raw_value` |
| `valores` | `values` |
| `vao` | `gap` |
| `variavel` | `variable` |
| `versao` | `version` |
| `vezes` | `times` |
| `vinculo` | `link` |
| `vinculos` | `links` |
| `vinculos_json` | `links_json` |

## 25. Validação da F3

* Suítes em 3.6.0, 3.6.8 e 3.13.2, bateria Oracle, testes progressivos nos cinco agregados, ciclo real do agente, percurso real das telas e conferência de resíduos; o helper compila em 3.6.0.
* Análise a seco antes de gravar: nenhuma colisão de nome dentro de uma função; nenhuma chamada ambígua depois de aceitar o repasse por `**kwargs`.
* Achados e corrigidos (caminhos indiretos que a análise estática não resolve): kwargs montados com `kw.setdefault(...)` e repassados por `**kw`; wrappers `original(...)` dos testes; `mock.assert_called_with(..., nome=)`; leituras de `call_args[1]["papel"]`. As views não chamam funções de `modules/` com argumento nomeado antigo.
* A primeira passada deixou 76 definições sem renomear (a segunda, rodada para os scripts de apoio, as completou); a ferramenta ficou idempotente, e suítes, bateria Oracle, agregados, ciclo real do agente e percurso foram repetidos depois disso. Parâmetros de `lambda` ficam para a F4.
* Docs: assinaturas citadas entre crases atualizadas (`load_secrets(path, role)`, `can_execute(user, script, environment)`, `evaluate_trigger(rule, now, …)`…).

## 26. Passada final, parte F4 (variáveis locais)

Variáveis locais e parâmetros de `lambda` de `modules/`, `scripts/`, testes e `bin/sss-helper` (cerca de 14.600 trocas). Tradução por partes do nome (`snake_case`), mantendo a ordem das palavras; exceções manuais para palavras coladas a número e abreviações de tabela. Locais de controllers e models ficam para o CR-016d.

Regras da troca, por escopo de função: o nome muda em todos os usos da função e das funções aninhadas que só o leem; nenhum nome novo coincide com builtin, módulo da biblioteca padrão ou palavra reservada (nesses casos, sufixo `_value`); se o nome novo já existe na função, ou se dois nomes da mesma função iriam para o mesmo destino, a troca usa o mapa alternativo abaixo; nomes ligados por `def`/`class` aninhados não mudam. O código não usa `locals()`, `vars()` nem `eval`.

Também: atributo `dirs_sss` → `sss_dirs` (configuração montada no laço e lida pelo `params_compiler`); variáveis dos lançadores `.sh`; README §8.4 (`version == 5`).

### Mapa principal

| Antes | Depois |
|---|---|
| `_acao` | `_action` |
| `_agora` | `_now` |
| `_amb` | `_env` |
| `_antigo` | `_old` |
| `_cod` | `_code` |
| `_codigo` | `_code` |
| `_erros` | `_errors` |
| `_inexistentes` | `_nonexistent` |
| `_motivo` | `_reason` |
| `_nivel` | `_level` |
| `_nome` | `_name` |
| `_parcial` | `_partial` |
| `_pastas` | `_dirs` |
| `_prefixo` | `_prefix` |
| `_problemas` | `_problems` |
| `_resolvidos` | `_resolved` |
| `_saida` | `_output` |
| `_tela` | `_screen` |
| `_truncado` | `_truncated` |
| `_truncou` | `_truncated` |
| `_vinculos` | `_links` |
| `a_atuais` | `a_current` |
| `a_nome` | `a_name` |
| `abre` | `open_value` |
| `abrev` | `abbr` |
| `acao` | `action` |
| `acao_f` | `action_f` |
| `aceitas` | `accepted` |
| `aceitos` | `accepted` |
| `achado` | `found` |
| `achados` | `found` |
| `acoes` | `actions` |
| `aconteceu` | `happened` |
| `adicionados` | `added` |
| `admin_senha` | `admin_password` |
| `admins_outros` | `admins_others` |
| `admins_restantes` | `admins_remaining` |
| `afetados` | `affected` |
| `agd` | `sch` |
| `agd_id` | `sch_id` |
| `agd_ids` | `sch_ids` |
| `agend` | `sched_value` |
| `agendada` | `scheduled` |
| `agendado` | `scheduled` |
| `agendamento` | `schedule` |
| `agente` | `agent` |
| `agente_dono` | `agent_owner` |
| `agente_id` | `agent_id` |
| `agentes` | `agents` |
| `agora` | `now` |
| `agora_agd` | `now_sch` |
| `agora_banco` | `now_db` |
| `agregado` | `aggregate` |
| `agregados` | `aggregates` |
| `aid_ativo` | `aid_active` |
| `aid_longo` | `aid_long` |
| `alcancaveis` | `reachable` |
| `alem` | `beyond` |
| `alheios_aud` | `foreign_aud` |
| `alheios_tck` | `foreign_tck` |
| `alteracoes` | `changes` |
| `alterado` | `changed` |
| `alto` | `high` |
| `alvo` | `target` |
| `alvos` | `targets` |
| `amanha` | `tomorrow` |
| `amb` | `env` |
| `amb_conn` | `env_conn` |
| `amb_desc` | `env_desc` |
| `amb_f` | `env_f` |
| `amb_id` | `env_id` |
| `amb_nome` | `env_name` |
| `ambiente` | `environment` |
| `ambientes` | `environments` |
| `ambientes_ativos_ids` | `environments_active_ids` |
| `ambientes_ativos_nomes` | `environments_active_names` |
| `ambs` | `envs` |
| `ambs_homologados` | `envs_homologated` |
| `ambs_ids` | `envs_ids` |
| `ambs_nomes` | `envs_names` |
| `ambs_permitidos` | `envs_allowed` |
| `analisados` | `analyzed` |
| `ano` | `year` |
| `ano_str` | `year_str` |
| `anos` | `years` |
| `anterior` | `previous` |
| `anteriores` | `previous` |
| `anteriores_lista` | `previous_items` |
| `antes` | `before` |
| `antes_do_marcador` | `before_of_marker` |
| `antiga` | `old` |
| `antigas` | `old` |
| `antigo` | `old` |
| `antigos` | `old` |
| `apos_quant` | `after_quant` |
| `args_gerar` | `args_generate` |
| `armazenado` | `stored` |
| `arq` | `file` |
| `arq_grants` | `file_grants` |
| `arq_implantar` | `file_deploy` |
| `arq_rollback` | `file_rollback` |
| `arq_validar` | `file_validate` |
| `arquivo` | `file` |
| `arquivo_novo` | `file_new` |
| `arquivos` | `files` |
| `arquivos_para_checar` | `files_for_check` |
| `arquivos_py` | `files_py` |
| `arquivos_violadores` | `files_violators` |
| `arvore` | `tree` |
| `associacoes` | `associations` |
| `ate` | `until` |
| `atendidos` | `served` |
| `ativo` | `active` |
| `ativo_alterado` | `active_changed` |
| `ativo_efetivo` | `active_effective` |
| `ativo_f` | `active_f` |
| `ativos` | `active` |
| `atomo` | `atom` |
| `ator` | `actor` |
| `ator_f` | `actor_f` |
| `ator_invalido` | `actor_invalid` |
| `ator_limpo` | `actor_clean` |
| `ator_pausa` | `actor_pause` |
| `ator_teste` | `actor_test` |
| `atrasada` | `late` |
| `atrasados` | `late` |
| `atraso` | `delay` |
| `atraso_s` | `delay_s` |
| `atributo` | `attribute` |
| `attr_tipo` | `attr_kind` |
| `atuais` | `current` |
| `atuais_por_id` | `current_by_id` |
| `atual` | `current` |
| `atual_ok` | `current_ok` |
| `atualizado` | `updated` |
| `auditoria` | `audit` |
| `auditorias` | `audits` |
| `ausente` | `missing` |
| `ausentes` | `missing` |
| `avaliador` | `evaluator` |
| `aviso` | `warning` |
| `aviso_regra` | `warning_rule` |
| `aviso_total` | `warning_total` |
| `avisos` | `warnings_value` |
| `b_amb` | `b_env` |
| `banco` | `db` |
| `barras` | `bars` |
| `barreira` | `barrier` |
| `binds_data` | `binds_date` |
| `binds_pag` | `binds_page` |
| `binds_perfil` | `binds_profile` |
| `bloco` | `chunk` |
| `blocos` | `chunks` |
| `bloq` | `locked` |
| `bloq_f` | `locked_f` |
| `bloqueado_ate` | `locked_until` |
| `bloqueados` | `locked` |
| `bloquear` | `lock` |
| `bomba` | `pump` |
| `bombas` | `pumps` |
| `bons` | `good` |
| `bruto` | `raw` |
| `brutos` | `raw` |
| `c_erro` | `c_error` |
| `c_limpa` | `c_clean` |
| `c_nome` | `c_name` |
| `c_parcial` | `c_partial` |
| `c_ver` | `c_view` |
| `cadastros_e_agendamentos` | `registries_and_schedules` |
| `cadastros_e_assoc` | `registries_and_assoc` |
| `cadeia_desc` | `chain_desc` |
| `caminho` | `path` |
| `caminho_0` | `path_0` |
| `caminho_1` | `path_1` |
| `caminho_2` | `path_2` |
| `caminho_3` | `path_3` |
| `caminho_ano` | `path_year` |
| `caminho_cfg` | `path_cfg` |
| `caminho_dest` | `path_dest` |
| `caminho_dia` | `path_day` |
| `caminho_esperado` | `path_expected` |
| `caminho_inicial` | `path_initial` |
| `caminho_mes` | `path_month` |
| `caminho_ruim` | `path_bad` |
| `caminho_sec` | `path_sec` |
| `caminhos` | `paths` |
| `campo` | `field` |
| `campos` | `fields` |
| `canais` | `channels` |
| `canc` | `cancel` |
| `canc_req` | `cancel_req` |
| `cancelado` | `cancelled` |
| `cancelar` | `cancel` |
| `candidato` | `candidate` |
| `candidato_ex` | `candidate_ex` |
| `candidatos` | `candidates` |
| `canonico` | `canonical` |
| `capturado` | `captured` |
| `caractere` | `character` |
| `carga` | `load` |
| `carregar` | `load` |
| `cartoes` | `cards` |
| `casa_dia` | `match_day` |
| `casa_dsem` | `match_wday` |
| `casos` | `cases` |
| `casou` | `matched` |
| `cat_esperada` | `cat_expected` |
| `catalogo` | `catalog` |
| `categoria` | `category` |
| `causa` | `cause` |
| `certo` | `right` |
| `chamada` | `call` |
| `chamadas` | `calls` |
| `chave` | `key` |
| `chave_legada` | `key_legacy` |
| `chaves` | `keys` |
| `ck_esperada` | `ck_expected` |
| `ck_nome` | `ck_name` |
| `ck_upd_nome` | `ck_upd_name` |
| `cks_banco` | `cks_db` |
| `cks_da_tabela` | `cks_of_table` |
| `claro` | `light` |
| `classe` | `cls_name` |
| `clausula` | `clause` |
| `clausula_lob` | `clause_lob` |
| `clausulas` | `clauses` |
| `clob_texto` | `clob_text` |
| `coberta` | `covered` |
| `cod` | `code` |
| `cod_erro` | `code_error` |
| `cod_esperado` | `code_expected` |
| `cod_f` | `code_f` |
| `cod_str` | `code_str` |
| `codigo` | `code` |
| `codigo_saude` | `code_health` |
| `codigos` | `codes` |
| `col_esperada` | `col_expected` |
| `col_imutavel` | `col_immutable` |
| `col_nome` | `col_name` |
| `coletado` | `collected` |
| `cols_entidade` | `cols_entity` |
| `coluna` | `column` |
| `colunas` | `columns` |
| `colunas_banco` | `columns_db` |
| `colunas_lob` | `columns_lob` |
| `colunas_pk` | `columns_pk` |
| `colunas_uk` | `columns_uk` |
| `com_flag` | `with_flag` |
| `com_pendencia` | `with_pending` |
| `com_pid` | `with_pid` |
| `com_py` | `with_py` |
| `com_valor` | `with_value` |
| `comandos` | `commands` |
| `comentarios` | `comments` |
| `compartilhado` | `shared` |
| `compilados` | `compiled` |
| `comum` | `common` |
| `concedidas` | `granted` |
| `cond_esp` | `expected_cond` |
| `cond_real` | `real_cond` |
| `conectar` | `connect` |
| `conector` | `connector` |
| `conexao` | `connection` |
| `confiaveis` | `trusted` |
| `consulta` | `query` |
| `contagem` | `count` |
| `contagens` | `counts` |
| `contar` | `count` |
| `conteudo` | `content` |
| `contexto` | `context` |
| `contrato_cls` | `contract_cls` |
| `corpo` | `body` |
| `corpos` | `bodies` |
| `corrida` | `race` |
| `corte` | `cutoff` |
| `criado` | `created` |
| `criado_antes` | `created_before` |
| `criadores` | `creators` |
| `criticos` | `critical` |
| `cron_erro` | `cron_error` |
| `ctx_antigo` | `ctx_old` |
| `ctx_gestor` | `ctx_manager` |
| `ctx_usuario` | `ctx_user` |
| `curto` | `short` |
| `curtos` | `short` |
| `da_saida` | `of_output` |
| `dados` | `data` |
| `dados2` | `data2` |
| `dados_ctx` | `data_ctx` |
| `dados_sec` | `data_sec` |
| `dados_secoes` | `data_sections` |
| `data` | `date` |
| `data_correta` | `date_correct` |
| `data_dia` | `date_day` |
| `data_ref` | `date_ref` |
| `datas` | `dates` |
| `de` | `of` |
| `decisao` | `decision` |
| `decorrido` | `elapsed` |
| `def_esperado` | `expected_def` |
| `def_real` | `real_def` |
| `dentro` | `inside` |
| `depois` | `after` |
| `desconhecidos` | `unknown` |
| `descricao` | `description` |
| `desde` | `since` |
| `desenv` | `dev` |
| `desfecho` | `outcome` |
| `desloc` | `offset` |
| `destino` | `destination` |
| `detalhe` | `detail` |
| `detalhe_driver` | `detail_driver` |
| `detalhe_erros` | `detail_errors` |
| `detalhe_tentativas` | `detail_attempts` |
| `detalhes` | `details` |
| `detectou` | `detected` |
| `dia` | `day` |
| `dia_1` | `day_1` |
| `dia_r` | `day_r` |
| `dia_str` | `day_str` |
| `dias` | `days` |
| `dicionario` | `mapping` |
| `diferenca` | `difference` |
| `direita` | `right` |
| `diretorio` | `directory` |
| `diretorios_alvo` | `directories_target` |
| `disparo` | `trigger` |
| `disponiveis` | `available` |
| `disponivel` | `available` |
| `distribuicao` | `distribution` |
| `divergencia` | `divergence` |
| `divergencias` | `divergences` |
| `divergentes` | `divergent` |
| `dois` | `two` |
| `dono` | `owner` |
| `dono_longo` | `owner_long` |
| `donos` | `owners` |
| `dsem` | `wday` |
| `dsem_r` | `wday_r` |
| `dt_banco` | `dt_db` |
| `dt_com_micro` | `dt_with_micro` |
| `dt_com_micros` | `dt_with_micros` |
| `dt_esperado` | `dt_expected` |
| `dt_fim` | `dt_end` |
| `dt_pausa` | `dt_pause` |
| `dt_saude` | `dt_health` |
| `duracao` | `duration` |
| `duracoes` | `durations` |
| `e_init` | `and_init` |
| `e_sonda` | `and_probe` |
| `editada` | `edited` |
| `eixo_x` | `axis_x` |
| `elegiveis` | `eligible` |
| `em_classe` | `in_cls_name` |
| `em_literal` | `in_literal` |
| `em_prod` | `in_prod` |
| `emitido` | `emitted` |
| `enderecos` | `addresses` |
| `enfileirado` | `queued` |
| `entidade` | `entity` |
| `entidade_id` | `entity_id` |
| `entidades_esperadas` | `entities_expected` |
| `entrada` | `input_value` |
| `enviado` | `sent` |
| `enviados` | `sent` |
| `enviar` | `send` |
| `era_admin_ativo` | `was_admin_active` |
| `erro` | `error` |
| `erro_conexao` | `error_connection` |
| `erros` | `errors` |
| `erros2` | `errors2` |
| `erros_param` | `errors_param` |
| `erros_rede` | `errors_network` |
| `escala_max` | `scale_max` |
| `escolhas` | `choices` |
| `escopo` | `scope` |
| `escritor` | `writer` |
| `escuro` | `dark` |
| `espaco` | `space` |
| `espera` | `wait` |
| `espera_min` | `wait_min` |
| `esperada` | `expected` |
| `esperado` | `expected` |
| `esperado_null` | `expected_null` |
| `esperado_readme` | `expected_readme` |
| `esperado_unique` | `expected_unique` |
| `esperados` | `expected` |
| `esquema` | `schema` |
| `esquerda` | `left` |
| `estado` | `state` |
| `estados` | `states` |
| `estranha` | `odd` |
| `estranho` | `odd` |
| `etapa_atual` | `stage_current` |
| `eu` | `me` |
| `exato` | `exact` |
| `excedeu` | `exceeded` |
| `excluidos` | `excluded` |
| `execucao` | `execution` |
| `execucoes` | `executions` |
| `executaveis` | `executables` |
| `executavel` | `executable` |
| `exemplo` | `example` |
| `exemplos` | `examples` |
| `exib` | `disp` |
| `exibidos` | `displayed` |
| `exigidos` | `required` |
| `existe` | `exists` |
| `f_atuais` | `f_current` |
| `f_cod` | `f_code` |
| `fabrica` | `factory` |
| `faixa` | `span` |
| `falha` | `failure` |
| `falhadas` | `failed` |
| `falhas` | `failures` |
| `falhas_map` | `failures_map` |
| `falhou` | `failed` |
| `falso` | `fake` |
| `faltando` | `missing` |
| `fase_atual` | `phase_current` |
| `fases` | `phases` |
| `fases_titulos` | `phases_titles` |
| `fatia` | `slice_value` |
| `fazer` | `todo` |
| `fechar` | `close` |
| `fechou_antes` | `closed_before` |
| `fez_flush` | `flushed` |
| `fila` | `queue_value` |
| `fila_quando` | `queue_when` |
| `filho` | `child` |
| `filhos` | `children` |
| `filtro` | `filter_value` |
| `filtros` | `filters` |
| `fim` | `end` |
| `fim_escuro` | `end_dark` |
| `fim_no_horizonte` | `end_no_horizon` |
| `fim_params` | `end_params` |
| `finalidade` | `purpose` |
| `fk_col_lider` | `fk_col_leader` |
| `fk_nome` | `fk_name` |
| `flush_feito` | `flush_done` |
| `fonte` | `source` |
| `fontes` | `sources` |
| `fora` | `outside` |
| `formato` | `format_value` |
| `frase` | `phrase` |
| `func` | `feature` |
| `func_ids` | `feature_ids` |
| `funcao` | `function` |
| `funcs` | `features` |
| `funcs_ids` | `features_ids` |
| `fundo` | `background` |
| `futura` | `future` |
| `futuro` | `future` |
| `gerar` | `generate` |
| `gestor` | `manager` |
| `grade` | `grid` |
| `grande` | `large` |
| `gravou` | `wrote` |
| `grupo` | `group` |
| `grupos` | `groups` |
| `guardado` | `saved` |
| `hash_pacote` | `hash_package` |
| `hoje` | `today` |
| `homologacoes` | `homologations` |
| `homologados` | `homologated` |
| `homologados_ativos` | `homologated_active` |
| `hora` | `hour` |
| `horario` | `schedule_time` |
| `horas` | `hours` |
| `icone` | `icon` |
| `idade` | `age` |
| `identidade` | `identity` |
| `ignoradas` | `ignored` |
| `ilimitados` | `unbounded` |
| `importados` | `imported` |
| `inativos` | `inactive` |
| `incluir` | `include` |
| `inclusoes` | `inserts` |
| `indice` | `index` |
| `indices` | `indexes` |
| `inexistentes` | `nonexistent` |
| `ini_antigo` | `ini_old` |
| `ini_modo` | `ini_mode` |
| `ini_ruim` | `ini_bad` |
| `inicia` | `starts` |
| `inicio` | `start` |
| `instante` | `instant` |
| `instantes` | `instants` |
| `instrucoes` | `statements` |
| `integral` | `full` |
| `interpretador` | `interpreter` |
| `interpretadores` | `interpreters` |
| `invalidas` | `invalid` |
| `invalido` | `invalid` |
| `invalidos` | `invalid` |
| `is_admin_efetivo` | `is_admin_effective` |
| `is_unico` | `is_single` |
| `itens` | `items` |
| `itens_principais` | `items_main` |
| `itens_r1` | `items_r1` |
| `iteracoes` | `iterations` |
| `ix_esperado` | `ix_expected` |
| `ix_nome` | `ix_name` |
| `ja` | `already` |
| `janela` | `window` |
| `larg_barra` | `width_bar` |
| `largo` | `wide` |
| `lento` | `slow` |
| `ler` | `read` |
| `lida` | `read` |
| `lidas` | `read` |
| `lider` | `leader` |
| `lider_vivo` | `leader_alive` |
| `lido` | `read` |
| `lidos` | `read` |
| `limiares` | `thresholds` |
| `limite` | `limit` |
| `limites` | `limits` |
| `limpa` | `clean` |
| `limpas` | `cleaned` |
| `limpeza` | `cleanup` |
| `limpos` | `cleaned` |
| `linha` | `line` |
| `linha_adapter` | `line_adapter` |
| `linhas` | `rows` |
| `linhas_cols` | `rows_cols` |
| `linhas_stats` | `rows_stats` |
| `lista` | `items` |
| `lista_a` | `items_a` |
| `lista_b` | `items_b` |
| `lista_ordem` | `items_order` |
| `listar` | `list_value` |
| `literais` | `literals` |
| `livre` | `free` |
| `livre_saida` | `free_output` |
| `log_ler` | `log_read` |
| `log_truncado` | `log_truncated` |
| `logico` | `logical` |
| `login_valido` | `login_valid` |
| `longo` | `long` |
| `lote` | `batch` |
| `lote_alterado` | `batch_changed` |
| `lote_mantido` | `batch_kept` |
| `lote_novo` | `batch_new` |
| `lotes` | `batches` |
| `mais_366` | `plus_366` |
| `mais_367` | `plus_367` |
| `manter` | `keep` |
| `mapa` | `map_value` |
| `mapa_driver` | `map_driver` |
| `marca` | `mark` |
| `marca_ip` | `mark_ip` |
| `marcado` | `marked` |
| `marcador` | `marker` |
| `marcados` | `marked` |
| `marcas` | `marks` |
| `masc` | `masker` |
| `massa` | `fixtures` |
| `matriz` | `matrix` |
| `maximo` | `max_value` |
| `mediana` | `median` |
| `meio` | `middle` |
| `melhores` | `best` |
| `membros` | `members` |
| `mensagem` | `message` |
| `mes` | `month` |
| `mes_str` | `month_str` |
| `meses` | `months` |
| `metodos_contrato` | `methods_contract` |
| `metodos_fake` | `methods_fake` |
| `meu` | `my` |
| `meu_uid` | `my_uid` |
| `meus` | `mine` |
| `minha` | `my` |
| `minhas` | `mine` |
| `minimo` | `min_value` |
| `minuto` | `minute` |
| `minutos` | `minutes` |
| `mock_conectar` | `mock_connect` |
| `modelo` | `template` |
| `modo` | `mode` |
| `modos` | `modes` |
| `modulos` | `modules` |
| `motivo` | `reason` |
| `motivo_rbac` | `reason_rbac` |
| `motivo_stderr` | `reason_stderr` |
| `motivo_txt` | `reason_txt` |
| `motivos` | `reasons` |
| `msg_erro` | `msg_error` |
| `msg_violacoes` | `msg_violations` |
| `mudanca` | `change` |
| `mudancas` | `changes` |
| `mudou` | `changed` |
| `nao_sensivel` | `not_sensitive` |
| `neto` | `grandchild` |
| `neto_pid` | `grandchild_pid` |
| `niveis` | `levels` |
| `nivel` | `level` |
| `nome` | `name` |
| `nome_base` | `name_base` |
| `nome_driver` | `name_driver` |
| `nome_exib` | `name_disp` |
| `nome_f` | `name_f` |
| `nome_final` | `name_final` |
| `nome_inativo` | `name_inactive` |
| `nome_low` | `name_low` |
| `nome_norm` | `name_norm` |
| `nome_perfil` | `name_profile` |
| `nome_scr` | `name_scr` |
| `nome_tok` | `name_tok` |
| `nome_u` | `name_u` |
| `nomeados` | `named` |
| `nomes` | `names` |
| `nomes_cols` | `names_cols` |
| `nomes_esperados` | `names_expected` |
| `nomes_gerados` | `names_generated` |
| `normalizado` | `normalized` |
| `nos_meus` | `in_mine` |
| `nova` | `new` |
| `nova_data` | `new_date` |
| `novas` | `new` |
| `novo` | `new` |
| `novo_ativo` | `new_active` |
| `novo_caminho` | `new_path` |
| `novo_conexao` | `new_connection` |
| `novo_hash` | `new_hash` |
| `novo_id` | `new_id` |
| `novo_is_admin` | `new_is_admin` |
| `novo_login` | `new_login` |
| `novo_nome` | `new_name` |
| `novo_offset` | `new_offset` |
| `novo_ok` | `new_ok` |
| `novo_perfil` | `new_profile` |
| `novo_ticket` | `new_ticket` |
| `novos` | `new` |
| `novos_vinculos` | `new_links` |
| `nulo` | `null` |
| `num_linha` | `num_line` |
| `numero` | `number` |
| `nunca_rodou` | `never_ran` |
| `obj_nome` | `obj_name` |
| `obj_tipo` | `obj_kind` |
| `objetos` | `objects` |
| `obrig` | `req` |
| `obrigatorios` | `required` |
| `obter` | `get` |
| `obtido` | `got` |
| `obtidos` | `got` |
| `ocor` | `occ` |
| `ocorrencia` | `occurrence` |
| `ocorrencias` | `occurrences` |
| `opc` | `opts` |
| `opc_sql` | `opts_sql` |
| `opcoes` | `options` |
| `orc` | `budget` |
| `orcamento` | `budget` |
| `ordem` | `order` |
| `ordenados` | `sorted_value` |
| `ordens_vistas` | `orders_seen` |
| `orfaos` | `orphans` |
| `origem` | `source` |
| `origem_f` | `source_f` |
| `outra` | `other` |
| `outro` | `other` |
| `outro_host` | `other_host` |
| `outro_pid` | `other_pid` |
| `outros` | `others` |
| `p_amb` | `p_env` |
| `p_ano` | `p_year` |
| `p_antiga` | `p_old` |
| `p_antiga_2` | `p_old_2` |
| `p_atual_ativo` | `p_current_active` |
| `p_atual_is_admin` | `p_current_is_admin` |
| `p_cod` | `p_code` |
| `p_destino` | `p_destination` |
| `p_dia` | `p_day` |
| `p_hora` | `p_hour` |
| `p_invalida` | `p_invalid` |
| `p_limite` | `p_limit` |
| `p_mes` | `p_month` |
| `p_novo_ativo` | `p_new_active` |
| `p_novo_is_admin` | `p_new_is_admin` |
| `p_obrig` | `p_req` |
| `p_origem` | `p_source` |
| `p_recente` | `p_recent` |
| `pacote` | `package` |
| `padrao` | `default` |
| `padrao_mudou` | `default_changed` |
| `padrao_real` | `default_real` |
| `padrao_texto` | `default_text` |
| `padroes` | `patterns` |
| `pag` | `page` |
| `pagina` | `page` |
| `pagina2` | `page2` |
| `pagina_` | `page_` |
| `paginas` | `pages` |
| `pai` | `parent` |
| `painel` | `dashboard` |
| `palavra` | `word` |
| `papeis` | `roles` |
| `papeis_grants` | `roles_grants` |
| `papel` | `role` |
| `par` | `pair` |
| `par_f` | `pair_f` |
| `parada` | `stop` |
| `parados` | `stopped` |
| `params_vistos` | `params_seen` |
| `parar` | `stop` |
| `parcial` | `partial` |
| `pares` | `pairs` |
| `parte` | `part` |
| `partes` | `parts` |
| `passado` | `past` |
| `passo` | `step` |
| `passo_dia` | `step_day` |
| `passo_hora` | `step_hour` |
| `passo_min` | `step_min` |
| `pasta` | `dir_value` |
| `pasta_app` | `dir_app` |
| `pasta_base` | `dir_base` |
| `pasta_entrada` | `dir_input` |
| `pasta_expirada_1` | `dir_expired_1` |
| `pasta_expirada_2` | `dir_expired_2` |
| `pasta_limite` | `dir_limit` |
| `pasta_nao_data` | `dir_not_date` |
| `pasta_recente` | `dir_recent` |
| `pastas` | `dirs` |
| `pausa` | `pause` |
| `pausa_aviso` | `pause_warning` |
| `pausada` | `paused` |
| `pausado` | `paused` |
| `pausas` | `pauses` |
| `pausou` | `paused` |
| `pedacos` | `pieces` |
| `pedido` | `request` |
| `pendente` | `pending` |
| `pendentes` | `pending` |
| `per` | `prf` |
| `per_ambs` | `prf_envs` |
| `per_desc` | `prf_desc` |
| `per_funcs` | `prf_features` |
| `per_nome` | `prf_name` |
| `perdidas` | `missed` |
| `perdidos` | `lost` |
| `perfil` | `profile` |
| `perfil_alterado` | `profile_changed` |
| `perfil_f` | `profile_f` |
| `perfil_id` | `profile_id` |
| `perfis` | `profiles` |
| `perguntas` | `questions` |
| `perm_versao` | `perm_version` |
| `perm_versao_atual` | `perm_version_current` |
| `permitida` | `allowed` |
| `permitido` | `allowed` |
| `permitido1` | `allowed1` |
| `permitido2` | `allowed2` |
| `permitido3` | `allowed3` |
| `ph_amb` | `ph_env` |
| `pid_neto` | `pid_grandchild` |
| `pilha` | `stack` |
| `piso` | `floor` |
| `pk_nome` | `pk_name` |
| `plano` | `plan` |
| `plataforma` | `platform_value` |
| `plataforma_dir` | `platform_dir` |
| `pode_cancelar` | `can_cancel` |
| `pode_em_algum` | `can_in_any` |
| `pode_exec` | `can_exec` |
| `pode_reexecutar` | `can_rerun` |
| `pode_regex` | `can_regex` |
| `podem` | `can` |
| `por_amb` | `by_env` |
| `por_dia` | `by_day` |
| `por_id` | `by_id` |
| `por_tabela` | `by_table` |
| `porta` | `port` |
| `pos_amb` | `pos_env` |
| `posicao` | `position` |
| `prazo` | `deadline` |
| `prefixo` | `prefix` |
| `prefixo_cfg` | `prefix_cfg` |
| `prefixos_para_testar` | `prefixes_for_test` |
| `preguicoso` | `lazy` |
| `prevista` | `expected` |
| `primeira` | `first` |
| `primeiro` | `first` |
| `primeiro_id` | `first_id` |
| `prioridade` | `priority` |
| `prioridades` | `priorities` |
| `problema` | `problem` |
| `problemas` | `problems` |
| `processo` | `process` |
| `processo_dono` | `process_owner` |
| `proibido` | `forbidden` |
| `proibidos` | `forbidden` |
| `pronto` | `ready` |
| `proprio` | `own` |
| `proprios` | `own` |
| `prox` | `next_value` |
| `prox_off` | `next_off` |
| `prox_off2` | `next_off2` |
| `proxima` | `next_value` |
| `proxima_calculada` | `next_computed` |
| `proximo` | `next_value` |
| `proximos` | `next_value` |
| `qtd` | `count` |
| `quando` | `when` |
| `quandos` | `whens` |
| `quantidade` | `quantity` |
| `r_ruim` | `r_bad` |
| `raiz` | `root` |
| `re_padrao` | `re_default` |
| `reaberto` | `reopened` |
| `recente` | `recent` |
| `recurso` | `resource_value` |
| `recusadas` | `refused` |
| `reduz_admin` | `reduces_admin` |
| `ref_tabela` | `ref_table` |
| `ref_tabela_nome` | `ref_table_name` |
| `reg_col_invalida` | `reg_col_invalid` |
| `reg_uk_invalida` | `reg_uk_invalid` |
| `regex_atual` | `regex_current` |
| `registrados` | `registered` |
| `registro` | `record` |
| `registros` | `records` |
| `regra` | `rule` |
| `regra_id` | `rule_id` |
| `regras` | `rules` |
| `rel_pasta` | `rel_dir` |
| `relativo` | `relative` |
| `relogio` | `clock` |
| `remoto` | `remote` |
| `remover` | `remove` |
| `removidas` | `removed` |
| `removidos` | `removed` |
| `repo_filtros` | `repo_filters` |
| `reservado` | `reserved` |
| `resiliente` | `resilient` |
| `resolvidos` | `resolved` |
| `responsaveis` | `owners` |
| `responsavel` | `owner` |
| `resposta` | `answer` |
| `respostas` | `answers` |
| `restantes` | `remaining` |
| `resto` | `rest` |
| `resultado` | `result` |
| `resultados` | `results` |
| `resultantes` | `resulting` |
| `resumo` | `summary` |
| `retencao_cfg` | `retention_cfg` |
| `retomadas` | `resumed` |
| `retomado` | `resumed` |
| `retorno` | `return_value` |
| `rod` | `run` |
| `rodada` | `round_value` |
| `rodando` | `running` |
| `rodando_quando` | `running_when` |
| `rotas` | `routes` |
| `roteiro` | `script_steps` |
| `rotulo` | `label` |
| `rotulos` | `labels` |
| `ruim` | `bad` |
| `ruins` | `bad` |
| `s_atuais` | `s_current` |
| `s_nome` | `s_name` |
| `sai` | `tout` |
| `saida` | `output` |
| `saida_txt` | `output_txt` |
| `saudaveis` | `healthy` |
| `saude` | `health` |
| `scr_antes` | `scr_before` |
| `scr_teto` | `scr_cap` |
| `script_implantar` | `script_deploy` |
| `script_nome` | `script_name` |
| `script_validar` | `script_validate` |
| `scripts_candidatos` | `scripts_candidates` |
| `scrs_permitidos` | `scrs_allowed` |
| `sec_campos` | `sec_fields` |
| `sec_nome` | `sec_name` |
| `secao` | `section` |
| `secoes` | `sections` |
| `segredo` | `secret` |
| `segredos` | `secrets_value` |
| `segredos_dummy` | `secrets_dummy` |
| `seguinte` | `next_value` |
| `segunda` | `second` |
| `segundo` | `second` |
| `segundos` | `seconds` |
| `selecao` | `selection` |
| `selecao_cx` | `selection_cx` |
| `selecao_thin` | `selection_thin` |
| `selecionado` | `selected` |
| `seletivo` | `selective` |
| `sem` | `without` |
| `sem_desenv` | `without_dev` |
| `sem_env` | `without_env` |
| `sem_flag` | `without_flag` |
| `sem_func` | `without_feature` |
| `sem_link` | `without_link` |
| `sem_nada` | `without_nothing` |
| `sem_pid` | `without_pid` |
| `semanal` | `weekly` |
| `senha` | `password` |
| `senha_confere` | `password_matches` |
| `senha_dono` | `password_owner` |
| `senha_ok_tipo` | `password_ok_kind` |
| `senha_super_secreta` | `password_super_secret` |
| `senha_txt` | `password_txt` |
| `senhas` | `passwords` |
| `sensiveis` | `sensitive` |
| `sensiveis_por_script` | `sensitive_by_script` |
| `sensivel` | `sensitive` |
| `seq_nome` | `seq_name` |
| `sera_admin_ativo` | `will_be_admin_active` |
| `serie` | `series` |
| `sessao` | `session` |
| `sid_inativo` | `sid_inactive` |
| `sigiloso` | `sensitive` |
| `sim` | `yes` |
| `sinal` | `signal_value` |
| `sinalizou` | `signaled` |
| `situacao` | `state` |
| `smotivo` | `sreason` |
| `snap_novo` | `snap_new` |
| `so_cancelados` | `only_cancelled` |
| `so_leitura` | `only_read` |
| `so_meus` | `only_mine` |
| `so_prod` | `only_prod` |
| `solicitante` | `requester` |
| `somas` | `sums` |
| `somas_dist` | `sums_dist` |
| `sondador` | `prober` |
| `sondar_script` | `probe_script` |
| `sorteio` | `draw` |
| `sozinho` | `alone` |
| `sql_amb` | `sql_env` |
| `sql_conta` | `sql_count_tpl` |
| `sql_lista` | `sql_items` |
| `sql_merge_amb` | `sql_merge_env` |
| `sql_merge_fnc` | `sql_merge_fea` |
| `sql_merge_pamb` | `sql_merge_penv` |
| `sql_merge_per` | `sql_merge_prf` |
| `sql_merge_pfnc` | `sql_merge_pfea` |
| `sql_merge_samb` | `sql_merge_senv` |
| `sql_pag` | `sql_page` |
| `sql_paginada` | `sql_paged` |
| `sql_pamb` | `sql_penv` |
| `sql_per` | `sql_prf` |
| `sql_perfil` | `sql_profile` |
| `sql_pfnc` | `sql_pfea` |
| `sql_samb` | `sql_senv` |
| `subpastas` | `subdirs` |
| `sucesso_count` | `success_count` |
| `sufixo` | `suffix` |
| `sufixo_18` | `suffix_18` |
| `sufixo_key` | `suffix_key` |
| `t_atual` | `t_current` |
| `t_meu` | `t_my` |
| `t_nome` | `t_name` |
| `t_novo` | `t_new` |
| `t_outro` | `t_other` |
| `tabela` | `table` |
| `tabela_nome` | `table_name` |
| `tabelas` | `tables` |
| `tabelas_basic` | `tables_basic` |
| `tabelas_monitor` | `tables_monitor` |
| `tabelas_stats` | `tables_stats` |
| `tam` | `size` |
| `tamanho` | `size` |
| `taxa` | `rate` |
| `tck_indices` | `tck_indexes` |
| `tela` | `screen` |
| `tela_consulta` | `screen_query` |
| `telas` | `screens` |
| `tem_ck` | `has_ck` |
| `tema` | `theme` |
| `template_esperado` | `template_expected` |
| `tempo` | `time_value` |
| `temporario` | `temporary` |
| `tentativa` | `attempt` |
| `tentativas` | `attempts` |
| `terceiro` | `third` |
| `terminados` | `finished` |
| `termo` | `term` |
| `teto` | `cap` |
| `tetos` | `caps` |
| `texto` | `text` |
| `texto1` | `text1` |
| `texto2` | `text2` |
| `texto_campo` | `text_field` |
| `texto_dia` | `text_day` |
| `texto_dsem` | `text_wday` |
| `texto_mes` | `text_month` |
| `texto_oracle` | `text_oracle` |
| `texto_reg` | `text_reg` |
| `texto_upper` | `text_upper` |
| `textos` | `texts` |
| `tid_agd` | `tid_sch` |
| `timeout_padrao` | `timeout_default` |
| `tipo` | `kind` |
| `tipo_concreto` | `kind_concrete` |
| `tipo_f` | `kind_f` |
| `tipo_neutro` | `kind_neutral` |
| `tipos` | `kinds` |
| `tipos_extras` | `kinds_extras` |
| `tipos_por_fase` | `kinds_by_phase` |
| `titulo` | `title` |
| `todas` | `all_value` |
| `todas_violacoes` | `all_violations` |
| `todos` | `all_value` |
| `tokens_escuro` | `tokens_dark` |
| `tomadas` | `taken` |
| `topo` | `top` |
| `total_limitado` | `total_capped` |
| `total_paginas` | `total_pages` |
| `total_regras` | `total_rules` |
| `tr_amb_bu` | `tr_env_bu` |
| `tr_bi_nome` | `tr_bi_name` |
| `tr_bu_nome` | `tr_bu_name` |
| `trava` | `lock` |
| `trecho` | `snippet` |
| `tres_dias` | `three_days` |
| `troca_propria` | `swap_own` |
| `trocado` | `swapped` |
| `trocados` | `swapped` |
| `trocou_responsavel` | `swapped_owner` |
| `truncado` | `truncated` |
| `truncou` | `truncated` |
| `txt_fim` | `txt_end` |
| `txt_passo` | `txt_step` |
| `u_falha` | `u_failure` |
| `u_nome` | `u_name` |
| `u_perfil` | `u_profile` |
| `uk_nome` | `uk_name` |
| `ult_id` | `last_id` |
| `ult_prox` | `last_next` |
| `ultima` | `last` |
| `ultimas` | `last` |
| `ultimo` | `last` |
| `um` | `one` |
| `um_min` | `one_min` |
| `um_seg` | `one_seg` |
| `umask_anterior` | `umask_previous` |
| `umask_antiga` | `umask_old` |
| `uniao` | `union` |
| `unidades` | `units` |
| `user_sessao` | `user_session` |
| `usos` | `uses` |
| `usuario` | `user` |
| `usuario_banco` | `user_db` |
| `usuario_bd` | `user_db` |
| `usuario_dono` | `user_owner` |
| `usuario_esperado` | `user_expected` |
| `usuario_id` | `user_id` |
| `usuarios` | `users` |
| `v_antes` | `v_before` |
| `v_nome` | `v_name` |
| `vagas` | `slots` |
| `val_atual` | `val_current` |
| `val_esp` | `expected_val` |
| `valida` | `valid` |
| `valido` | `valid` |
| `valor` | `value` |
| `valor_longo` | `value_long` |
| `valor_tok` | `value_tok` |
| `valores` | `values` |
| `variantes` | `variants` |
| `varreduras` | `scans` |
| `vazio` | `empty` |
| `velha` | `old` |
| `velho` | `old` |
| `velho_ok` | `old_ok` |
| `velho_pend` | `old_pend` |
| `velhos` | `old` |
| `vencidas` | `due` |
| `verificacao` | `check` |
| `versao` | `version` |
| `versao_banco` | `version_db` |
| `versao_cliente` | `version_client` |
| `versao_driver` | `version_driver` |
| `versao_servidor` | `version_server` |
| `versao_str` | `version_str` |
| `vinc` | `link` |
| `vinc_scr` | `link_scr` |
| `vinculados` | `linked` |
| `vinculos` | `links` |
| `violacoes` | `violations` |
| `visiveis` | `visible` |
| `visivel` | `visible` |
| `vistas` | `seen` |
| `vistos` | `seen` |
| `vizinha` | `neighbor` |
| `voltas` | `rounds` |

### Mapa alternativo (colisões)

| Antes | Depois |
|---|---|
| `amb` | `env_name` |
| `arquivos` | `file_paths` |
| `cod` | `err_code` |
| `codigo` | `code` |
| `detalhe` | `detail_text` |
| `espera` | `wait_s` |
| `funcs_ids` | `feature_id_list` |
| `linha` | `src_line` |
| `motivo` | `reason_text` |
| `nova` | `new_value` |
| `novo` | `new` |
| `repo_filtros` | `repo_filters_dict` |
| `sensiveis` | `sensitive` |
| `sensivel` | `is_sensitive` |
| `tam` | `size_n` |
| `ultima` | `last` |
| `ultimas` | `recent_runs` |
| `violacoes` | `found_violations` |

### Lançadores `.sh`

| Antes | Depois |
|---|---|
| `DATA_HORA` | `DATE_TIME` |
| `INTERPRETADOR` | `INTERPRETER` |
| `LOG_ARQUIVO_DATA` | `LOG_FILE_DATED` |
| `PAROU` | `STOPPED` |
| `PRONTO` | `READY` |

## 27. Validação da F4

* Suítes em 3.6.0, 3.6.8 e 3.13.2, bateria Oracle, testes progressivos nos cinco agregados, ciclo real do agente, percurso real das telas, conferência de resíduos, `bash -n` e subida e parada reais do `start_local.sh`/`stop_local.sh`.
* Achados durante a aplicação e corrigidos antes do commit (os arquivos foram restaurados do commit da F3 e a troca refeita): um nome traduzido para palavra reservada (`retorno` → `return`, que quebrou a sintaxe); dois nomes da mesma função traduzidos para o mesmo destino (`sensiveis` e `sensivel` → `sensitive`; `ultimas` e `ultima` → `last`), o que trocava o tipo da variável; uma função aninhada ligada a um nome que mudava (`def sondador`). A ferramenta passou a recusar os três casos e chegou a ponto fixo.

## 28. Códigos internos de pré-validação e do desdobro (D21)

Decisão do usuário (2026-10-22, D21): os códigos de recusa da pré-validação, que aparecem na linha `[SSS] pré-validação recusada: <código>` do log do ticket, passam a inglês, como os demais valores internos (D9). No mesmo passo, os resultados internos do desdobro (`Expansion.process`) e o código do erro de banco antes do spawn. O código de ação do log `DESDOBRO` fica em português (D15).

| Antes | Depois |
|---|---|
| `VERSAO_NAO_SUPORTADA` | `UNSUPPORTED_VERSION` |
| `ESTRUTURA_INVALIDA` | `INVALID_STRUCTURE` |
| `JSON_INVALIDO` | `INVALID_JSON` |
| `ARGS_INVALIDOS` | `INVALID_ARGS` |
| `INTERPRETADOR_NAO_PERMITIDO` | `INTERPRETER_NOT_ALLOWED` |
| `INTERPRETADOR_NAO_DISPONIVEL` | `INTERPRETER_UNAVAILABLE` |
| `INTERPRETADOR_INSEGURO` | `INTERPRETER_UNSAFE` |
| `NAO_HOMOLOGADO` | `NOT_HOMOLOGATED` |
| `CADASTRO_MUDOU` | `REGISTRATION_CHANGED` |
| `NAO_SUPORTADO` (`stop_ticket` da plataforma) | `UNSUPPORTED` |
| `ERRO_BANCO` (log do ticket e resultado do desdobro) | `DB_ERROR` |
| `AVANCADA` | `ADVANCED` |
| `CONCLUIDA_COM_TICKET` / `CONCLUIDA_SEM_TICKET` | `COMPLETED_WITH_TICKET` / `COMPLETED_WITHOUT_TICKET` |
| `CORRIDA` | `RACE` |
| `CRON_INVALIDO_COM_TICKET` | `INVALID_CRON_WITH_TICKET` |
| `IGNORAR` | `IGNORE` |
| `OCORRENCIA_DUPLICADA` (também o prefixo da mensagem de log) | `DUPLICATE_OCCURRENCE` |
| `OUTRO_AGENTE` | `OTHER_AGENT` |
| `PAUSADA` | `PAUSED` |

Validação: suítes em 3.6.0, 3.6.8 e 3.13.2, bateria Oracle, testes progressivos, ciclo real do agente, percurso real das telas e conferência de resíduos; README (§8.4) e DEPLOYMENT (tabela de diagnóstico) atualizados.

## 29. Driver sem a biblioteca `cryptography` (opção B)

Pedido do usuário (2026-10-22): o projeto não pode usar a biblioteca `cryptography`. O código nunca a importou; só o modo Thin do `python-oracledb` precisa dela. Decisão (opção B): tirar o `cryptography` dos requisitos (README §2.3, AGENTS §2.2, DEPLOYMENT, DEV_ENVIRONMENT) e recomendar `driver_mode = thick` (`config.ini.example` e DEV). Sem mudança de código: o modo Thin continua disponível e pode ser ligado num ambiente futuro instalando a `cryptography` e usando `driver_mode = auto` ou `thin`.

* O Thick conecta do 11.2.0.4 ao 23ai com o Instant Client 19.x, agora obrigatório em todos os nós; o Thin só conecta a 12.1+ (em 11gR2, `DPY-3010`).
* Com `auto` num nó sem `cryptography`, a sondagem do Thin falha com `DPY-3016` (WARN) e a cadeia segue para o Thick.
* Validado no DEV com o Python 3.6.0 sem `cryptography` (removida pelo usuário): sondagem Thick conecta, Thin falha com `DPY-3016`, conexão da aplicação em `thick` e em `auto` escolhe o Thick e a biblioteca nunca é carregada; agregado Oracle CATALOGO OK. No 3.6.15: bateria Oracle completa e cinco agregados em `thick`, ciclo real do agente (`driver=oracledb modo=thick`) e percurso das telas.
* Achado no modo Thick: o Oracle recusa valores de bind num `EXPLAIN PLAN` (`ORA-01036`), o que o Thin tolerava; o teste `test_health.test_explain_…` passou a explicar o SQL com `SYSDATE` no lugar dos binds de data (o produto não roda `EXPLAIN`).

## 30. Rotas da web (CR-016d, parte d1)

Plano aprovado pelo usuário (2026-10-22) com as decisões D22 a D25:

* **D22:** troca direta, sem redirecionamento do endereço antigo (dá 404); a página inicial não muda. Nota de atualização no DEPLOYMENT §18.
* **D23:** as classes CSS também passam a inglês (parte d3).
* **D24:** o nome do arquivo baixado `ticket_<id>_saida.zip` fica em português (é conteúdo que o usuário vê).
* **D25:** o manual de homologação e as evidências do UI Freeze ficam como registro histórico, com os endereços da época; as ferramentas de `dev/homologation` (roteiro e capturas) usam as rotas novas.

Os arquivos de controller, as pastas e arquivos de view, os componentes e os scripts de `static/js/app` foram movidos com `git mv`; o nome da função de cada ação acompanha a rota. `routes.py` (raiz) aponta o erro para `error/index`.

| Controller antes | Depois |
|---|---|
| `admin_ambientes` | `admin_environments` |
| `admin_parametros` | `admin_parameters` |
| `admin_perfis` | `admin_profiles` |
| `admin_usuarios` | `admin_users` |
| `agendamentos` | `schedules` |
| `auditoria` | `audit` |
| `erro` | `error` |

| Ação antes | Depois |
|---|---|
| `admin_teste` | `admin_test` |
| `agentes` | `agents` |
| `alternar_ativo` | `toggle_active` |
| `baixar` | `download` |
| `cancelar` | `cancel` |
| `catalogo` | `catalog` |
| `componentes` | `components` |
| `criar` | `create` |
| `desbloquear` | `unlock` |
| `detalhe` | `detail` |
| `exportar` | `export` |
| `historico` | `history` |
| `homologacao` | `homologation` |
| `lista` | `index` |
| `matriz` | `matrix` |
| `minha_senha` | `my_password` |
| `novo` | `new` |
| `parametros` | `parameters` |
| `pausar` | `pause` |
| `permissoes` | `permissions` |
| `previa` | `preview` |
| `quem_pode` | `who_can` |
| `redefinir_senha` | `reset_password` |
| `reexecutar` | `rerun` |
| `retomar` | `resume` |
| `saida` | `output` |
| `salvar` | `save` |
| `salvar_homologacao` | `save_homologation` |
| `salvar_matriz` | `save_matrix` |
| `salvar_parametros` | `save_parameters` |
| `testar` | `test_regex` |

| View parcial ou componente antes | Depois |
|---|---|
| `_abas.html` | `_tabs.html` |
| `_diagnosticos_agentes.html` | `_agent_diagnostics.html` |
| `alerta.html` | `alert.html` |
| `filtros.html` | `filters.html` |
| `form_campo.html` | `form_field.html` |
| `modal_confirmacao.html` | `confirm_modal.html` |
| `paginacao.html` | `pagination.html` |
| `questionario.html` | `questionnaire.html` |
| `registro.html` | `record.html` |
| `tabela.html` | `table.html` |

| JavaScript antes (`static/js/app/`) | Depois |
|---|---|
| `agendamentos.js` | `schedules.js` |
| `agentes.js` | `agents.js` |
| `componentes.js` | `components.js` |
| `disparo.js` | `trigger.js` |
| `matriz.js` | `matrix.js` |
| `parametros.js` | `parameters.js` |

Ficam: os controllers `default`, `tickets`, `logs`, `admin_scripts` e `dev`, e as ações `index`, `form`, `login`, `logout`, `agenda` e `shell`.

Achado durante a aplicação e corrigido antes do commit: a regra que troca o par `("controller", "ação")` casou `"erro", "mensagem"` no dicionário do flash (`{"tipo": "erro", ...}`) e `"FAILED": "erro", "CANCELLED"` no `ticket_service`, porque `erro` também era nome de controller; os valores voltaram a `erro` (as chaves de flash são da parte d2).

Achado pela varredura das URLs geradas nas telas (todo endereço do app citado em `href`, `action` e `data-*`, pedido por GET): a aba "Trilha de auditoria" (`views/audit/_tabs.html`) montava `audit/lista`, porque o nome da ação estava numa tupla que as regras de troca não alcançam; corrigido para `index`. Os demais 404 da varredura são legítimos: links da trilha de auditoria para registros já apagados pelas baterias e `logs/download` sem argumento. Endereços antigos (`tickets/novo`, `admin_usuarios/lista`, `auditoria/agentes`) respondem 404 (D22).

Validação: suítes em 3.6.0, 3.6.8 e 3.13.2 (1275 testes), bateria Oracle (1273), testes progressivos nos cinco agregados, ciclo real do agente, percurso real das telas com a varredura das URLs (baseline de 2 falhas conhecidas do fixture), conferência de resíduos.

## 31. Sessão, campos de formulário e de URL (CR-016d, parte d2a)

Plano do d2 aprovado pelo usuário (2026-10-22) com as decisões D26 (sessões abertas caem na atualização), D27 (links com `pagina`/`tamanho` abrem na primeira página) e D28 (campo de senha do login em inglês). Sem leitura do nome antigo.

| Antes | Depois |
|---|---|
| `session.usuario_id`, `perfil_id`, `perm_versao`, `login_em`, `ultimo_acesso`, `sessao_epoch` | `user_id`, `profile_id`, `perm_version`, `login_at`, `last_access`, `session_epoch` |
| parâmetros de URL `pagina`, `tamanho` (listas, paginação e filtros) | `page`, `size` |
| campo `senha` (login e usuários), `senha_atual`, `nova`, `confirmacao` | `password`, `current_password`, `new_password`, `confirmation` |
| `ambientes` (homologação), `vinculos_json`, `valor_teste`, `remover_padrao` | `environments`, `links_json`, `test_value`, `remove_default` |
| `reexecucao` (GET), `reexecucao_de` (POST), `ultima=1`, `respostas` (JSON da prévia) | `rerun`, `rerun_of`, `last=1`, `answers` |
| `ex_enviar`, `ex_timeout` (tela de componentes do DEV) | `demo_submit`, `demo_timeout` |
| resultado do `change_password`: `ERRO`, `BLOQUEADO` | `ERROR`, `LOCKED` |

As chaves de erro dos campos de senha (`errors["confirmation"]`…) acompanham o nome do campo, porque a tela marca o campo pelo nome. O teste de regressão `test_controllers_nao_leem_senha_direto_de_request` passou a procurar os nomes novos. As ferramentas de `dev/homologation` usam `#campo-password` e `input[name="password"]`.

Achados no levantamento e corrigidos aqui (vinham do CR-016a, c48f1e2, que renomeou os campos do formulário sem o JavaScript que os lê):

* **Disparo:** o `trigger.js` lia `form.elements.ambiente` e `form.elements.prioridade`, que não existem desde que os campos viraram `environment` e `priority`. O erro de JavaScript impedia a prévia do comando e o resumo em frase do modal de confirmação. Agora envia `environment`, `priority` e `answers`.
* **Agendamento:** a prévia das próximas execuções enviava `dias_semana`, mas o controller lê `week_days`. Na recorrência semanal, os dias marcados eram ignorados na prévia. Agora envia `week_days`.

Nem as suítes nem o percurso por GET executam JavaScript; por isso a validação deste passo inclui as requisições da prévia feitas como o navegador as monta.

Achado na validação e corrigido antes do commit: sete chamadas dos testes passavam os nomes antigos como argumento nomeado (`dict(session, usuario_id=999)`, `_insert(confirmacao=...)`, `_edit(..., remover_padrao="Y")`), que a troca por texto entre aspas não alcança; as cinco falhas apontaram todas.

Validação: suítes em 3.6.0, 3.6.8 e 3.13.2 (1275 testes), bateria Oracle (1273), testes progressivos nos cinco agregados, ciclo real do agente, percurso real das telas com login pelo campo `password`, varredura das URLs, paginação com `page`/`size`, prévia do disparo e prévia semanal do agendamento por POST JSON (com `week_days=1,3` devolve só segundas e quartas; sem os dias, recusa), conferência de resíduos.

## 32. Flash, mensagens, especificação dos componentes e JSON lido pelo JS (CR-016d, parte d2b)

Aprovado pelo usuário (2026-10-22), com a correção das telas quebradas incluída.

* **Flash:** `{'tipo', 'mensagem'}` → `{'kind', 'message'}`; tipos `sucesso`/`aviso`/`erro` → `success`/`warning`/`error`. O toast usa os mesmos valores (`alerta` → `warning`), e as classes `sss-toast-*` acompanham.
* **Mensagens-padrão (`ui_helpers.MENSAGENS`):** `sem_permissao` → `no_permission`, `nao_encontrado` → `not_found`, `falha_interna` → `internal_error`, `conflito` → `conflict`, `sessao_expirada` → `session_expired`, `sessao_max` → `session_max_age`, `login_incorreto` → `login_failed`, `conta_bloqueada` → `account_locked`, `formulario` → `form_errors`, `ultimo_admin` → `last_admin`, `fila_sem_atendente` → `unattended_queue`, `rodando_sem_pid` → `running_without_pid`, `config_divergente` → `config_mismatch` (as três últimas também são as chaves do painel de agentes). A chave interna `PARADA` do quadro de saída passa a `STALLED` (o código de ação `PARADA` do log fica, D15).
* **Especificação dos componentes** (tabela, filtros, campo, questionário, modal, alerta, registro): `tipo` → `kind`, `rotulo` → `label`, `campos` → `fields`, `opcoes` → `options`, `valor` → `value`, `erro`/`erros` → `error`/`errors`, `preservar` → `keep`, `ajuda` → `help`, `classe` → `css_class`, `icone` → `icon`, `chave` → `key`, `colunas` → `columns`, `linhas` → `rows`, `legenda` → `caption`, `msg_vazio` → `empty_message`, `somente_leitura` → `read_only`, `variante` → `variant`, `texto` → `text`, `acao` → `action`, `rotulo_confirmar` → `confirm_label`, `rotulo_gatilho` → `trigger_label`, `campos_ocultos` → `hidden_fields`, `marcado` → `checked`, `mantido` → `kept`, `exemplo` → `example`, `aviso` → `warning`, `padrao_texto` → `default_text`, `tem_padrao` → `has_default`, `alterado`/`criado` → `updated`/`created`, `aconteceu`/`fazer` → `happened`/`todo`. Valores: `texto` → `text`, `acao` → `action`, `data` → `date`, `multipla` → `multiple`, `perigo` → `danger`.
* **JSON lido pelo JS:** `resumo` → `summary` (com `when`, `answers`, `phrase`), `datas` → `dates`, `texto`/`proximo_offset`/`truncado` → `text`/`next_offset`/`truncated`, `tem_sub` → `has_override`, `manter_sigiloso` → `keep_secret`, `respostas` → `answers`.
* **Séries do histórico:** `certo`/`erro`/`cancelado`/`andamento` → `succeeded`/`error`/`cancelled`/`in_progress`, com as classes e variáveis `sss-graf-*` (README, tabela de cores).

Ferramenta: troca por contexto (chave de dicionário, índice, `.get`/`.pop`/`.setdefault` e argumento nomeado de `dict()`/`.update()`), com recusa de chave duplicada no mesmo dicionário. Ficaram fora os metadados de esquema do `sql_ident`/`ddl_builder` (`tipo`, `colunas`…), que não são da tela. As variáveis de tela continuam em português até o d2c (por isso `dados["legenda"]`, `dados["opcoes"]` e o `erros` passado à tela de agendamento ficam).

**Telas que estavam quebradas desde o CR-016a e foram corrigidas aqui:**

* **Vínculo de parâmetros do script:** o JS lia `codigo`, `param_nomeado`, `sensivel`, `ativo`, `obrigatorio`, `valor_padrao_sub` e enviava `parametro_id`; a lista aparecia sem código nem "obrigatório" e salvar falhava. Agora lê e envia os nomes do servidor.
* **Resumo do modal de disparo:** ambiente e prioridade apareciam vazios (`resumo.ambiente`/`prioridade`).
* **Prévia do agendamento:** a frase da recorrência não aparecia (`descricao` × `description`).

**Verificação de contrato no percurso:** para cada tela com JS, o percurso chama o endpoint como o navegador (prévia do disparo e o resumo, prévia do agendamento, teste de regex, prévia dos vínculos, pedaço do log) e lê os JSON embutidos (`data-vinculos`, `data-disponiveis`, `data-status-info`), conferindo que as chaves que `static/js/app` lê estão presentes; a prévia dos vínculos também vai e volta com o JSON montado como o JS monta. A verificação achou, durante este passo, o `data-status-info` do visor de log lido por `info.rotulo`/`info.classe`, corrigido antes do commit.

Achados durante a aplicação e corrigidos antes do commit: comparações de template (`_tipo == 'acao':`) tomadas como chave (a troca coincidiu com a de valor); a série `erro` do histórico trocada só no acesso (completada para as quatro séries); dois `dict` de controller que viram variável de tela (`dados["legenda"]`, `dados["opcoes"]`) e um que vira dado do serviço (`answers=` no salvar do agendamento); argumentos nomeados de helpers de teste (`_save(respostas=...)`).

Pendências registradas (fora do d2b, para decisão): códigos de resultado do cancelamento (`CANCELADO`, `SINALIZADO`, `JA_SINALIZADO`, `TERMINAL`) e da devolução à fila (`DEVOLVIDO`, `PERDIDO`), e as chaves dos metadados de esquema do `sql_ident` (`tipo`, `colunas`, `sufixo`, `tabela`, `abrev`).

## 33. Variáveis de tela e dicionários dos serviços e repositórios (CR-016d, parte d2c)

Aprovado pelo usuário (2026-10-22); o D29 fica para depois do d2c.

Trocados juntos, com o mesmo nome em inglês: as variáveis que os controllers passam às telas (`return dict(...)` e `dados[...]`), as entradas dos componentes (`tabela`, `filtros`, `campo`, `alerta`, `registro`, `pagina`, `tamanho`…, que o template incluído lê pelo nome), as chaves dos dicionários que os serviços devolvem à tela e o contrato de lista dos repositórios Oracle e FAKE (`items`, `page`, `size`, `total_capped`). As chaves do contexto de permissão (`active_user`, `active_profile`, `profile_name`) e do contexto do claim (`homologations`, `schedule`) passam também por `rbac`, `scheduler_queue`, `scheduler_loop`, `schedule_expansion` e `health.py`. Os filtros de URL da auditoria e da lista de tickets passam a `date_from`/`date_to`, `created_from`/`created_to` e `source` (D27: link salvo com o nome antigo perde o filtro).

| Antes | Depois |
|---|---|
| `aba_ativa` | `active_tab` |
| `acoes` | `actions` |
| `aconteceu` | `happened` |
| `agendamento` | `schedule` |
| `agendamentos_ativos` | `active_schedules` |
| `agente` | `agent` |
| `agora` | `now` |
| `ajuda_senha` | `password_help` |
| `alerta` | `alert` |
| `alertas` | `alerts` |
| `altura` | `height` |
| `amb` | `env` |
| `ambiente` | `environment` |
| `ambientes` | `environments` |
| `ambientes_homologados` | `homologated_environments` |
| `anterior` | `previous_page` |
| `argv_para_exibicao` | `display_argv` |
| `ate` | `date_to` |
| `ator` | `actor` |
| `atrasados` | `delayed` |
| `atual` | `current` |
| `ausentes` | `absent` |
| `aviso_admin` | `admin_warning` |
| `aviso_desativacao` | `deactivation_warning` |
| `aviso_limite` | `limit_warning` |
| `aviso_sensivel` | `sensitive_warning` |
| `aviso_total` | `total_warning` |
| `badges` | `badges` |
| `barras` | `bars` |
| `bloqueado` | `locked` |
| `bloqueado_em` | `locked_at` |
| `bloqueio` | `lockout` |
| `bloqueou` | `locked_now` |
| `campo` | `field` |
| `campos` | `fields` |
| `campos_form` | `form_fields` |
| `cartoes` | `cards` |
| `codigo` | `code` |
| `comando_exibicao` | `display_command` |
| `compilado_em` | `compiled_at` |
| `contagem` | `counts` |
| `criado_ate` | `created_to` |
| `criado_de` | `created_from` |
| `criado_fim` | `created_to` |
| `criado_inicio` | `created_from` |
| `dados` | `data` |
| `de` | `date_from` |
| `descricao_motivo` | `reason_description` |
| `desde` | `since` |
| `destino` | `next_url` |
| `detalhe_curto` | `short_detail` |
| `detalhes` | `details` |
| `dias` | `days` |
| `dias_semana` | `weekdays` |
| `disponiveis` | `available` |
| `duracao` | `duration` |
| `duracao_maxima` | `max_duration` |
| `duracao_tipica` | `typical_duration` |
| `edicao` | `editing` |
| `eixo_x` | `x_axis` |
| `emitidos` | `issued` |
| `entidades` | `entities` |
| `erro` | `error` |
| `erro_geral` | `general_error` |
| `erros` | `errors` |
| `erros_senha` | `password_errors` |
| `estado` | `state_info` |
| `etapa` | `step` |
| `etapas` | `steps` |
| `explicacao` | `explanation` |
| `fazer` | `todo` |
| `filhos` | `children` |
| `filtro_lista` | `list_filter` |
| `filtros` | `filters` |
| `filtros_ativos` | `active_filters` |
| `finalidade` | `purpose` |
| `foco_campo` | `focus_field` |
| `form_enviado` | `form_sent` |
| `frase_admin` | `admin_phrase` |
| `frase_mais_acesso` | `more_access_phrase` |
| `frase_sem_exec` | `no_runs_phrase` |
| `frase_taxa` | `rate_phrase` |
| `grade` | `grid` |
| `grafico` | `chart` |
| `grupos` | `groups` |
| `ha` | `ago` |
| `homolog` | `homologation` |
| `homologacoes` | `homologations` |
| `hora` | `hour` |
| `idade_s` | `age_s` |
| `inativo` | `inactive` |
| `inativos` | `inactive_items` |
| `inicio` | `start` |
| `interpretadores` | `interpreters` |
| `intervalo_s` | `interval_s` |
| `itens` | `items` |
| `largura` | `width` |
| `legenda` | `legend` |
| `limiares` | `thresholds` |
| `limite_exportacao` | `export_limit` |
| `login_digitado` | `typed_login` |
| `mais` | `more` |
| `mais_antigo` | `oldest` |
| `margem_esq` | `left_margin` |
| `matriz` | `matrix` |
| `maximo` | `maximum` |
| `mensagem` | `message` |
| `meus` | `mine` |
| `modais` | `modals` |
| `motivos` | `reasons` |
| `obs_validacao` | `validation_note` |
| `opcoes` | `options` |
| `origem` | `source` |
| `origens` | `sources` |
| `outro_responsavel` | `other_owner` |
| `padrao` | `default` |
| `pagina` | `page` |
| `pai` | `parent` |
| `painel` | `dashboard` |
| `passo_s` | `step_s` |
| `pausa_aviso` | `pause_warning` |
| `perfil` | `profile` |
| `perfil_ativo` | `active_profile` |
| `perfil_nome` | `profile_name` |
| `perfis` | `profiles` |
| `perguntas` | `questions` |
| `permissoes` | `permissions` |
| `pode_baixar` | `can_download` |
| `pode_cancelar` | `can_cancel` |
| `pode_disparar` | `can_trigger` |
| `pode_executar` | `can_execute` |
| `pode_reexecutar` | `can_rerun` |
| `pode_regex` | `can_regex` |
| `previa` | `preview` |
| `primeiro_registro` | `first_record` |
| `prioridade` | `priority` |
| `prioridades` | `priorities` |
| `problema` | `problem` |
| `problemas` | `problems` |
| `producao` | `production` |
| `proprio` | `own` |
| `proxima` | `next_page` |
| `qtd` | `count` |
| `qtd_parametros` | `param_count` |
| `qtd_scripts` | `script_count` |
| `quantidade` | `quantity` |
| `quantidade_pagina` | `page_count` |
| `recorrencia` | `recurrence` |
| `reexecucao_de` | `rerun_of` |
| `registro` | `record` |
| `regra` | `rule` |
| `regra_id` | `rule_id` |
| `responsavel` | `responsible` |
| `resultado` | `result` |
| `rota` | `route` |
| `rotulo_diff` | `diff_label` |
| `rotulos_tipo` | `type_labels` |
| `saida` | `output` |
| `saude` | `health` |
| `script_nome` | `script_name` |
| `scripts_homologados` | `homologated_scripts` |
| `secao` | `section` |
| `sensiveis` | `sensitive_codes` |
| `status_desconhecido` | `unknown_status` |
| `status_motivo` | `status_reason` |
| `tabela_erro` | `error_table` |
| `tabela_vazia` | `empty_table` |
| `tamanho` | `size` |
| `tamanhos` | `sizes` |
| `taxa` | `rate` |
| `telas` | `screens` |
| `tem_anterior` | `has_previous` |
| `tem_proxima` | `has_next` |
| `tem_ultima` | `has_last` |
| `texto_copia` | `copy_text` |
| `tipos` | `types` |
| `tipos_param` | `param_types` |
| `total_limitado` | `total_capped` |
| `total_paginas` | `total_pages` |
| `ultima` | `last_run` |
| `ultimo_registro` | `last_record` |
| `url_baixar` | `download_url` |
| `url_fragmento` | `fragment_url` |
| `uso` | `usage` |
| `usou_ultima` | `used_last` |
| `usuario` | `user` |
| `usuario_ativo` | `active_user` |
| `usuarios_afetados` | `affected_users` |
| `usuarios_ativos` | `active_users` |
| `valores` | `values` |
| `vinc` | `links_page` |
| `vinculos` | `links` |
| `visor_log` | `log_viewer` |

Ficam: as dimensões da matriz de perfis (`funcs`, `ambs`, `scrs`), abreviações compartilhadas entre repositório, serviço, formulário e o texto do diff gravado na auditoria (`amb:`/`scr:`); `tabela` como chave dos metadados do `sql_ident` (só a variável de template mudou); os valores de dado e códigos (`agendamento`/`manual`, estados das etapas `feito`/`atual`/`pendente`/`pulado`, que viram classe CSS no d3) e os logins do seed (`inativo`, `bloqueado`).

Ferramenta: a do d2b, agora restrita aos blocos `{{ }}` dos templates (com troca dos nomes de variável, sem comentários nem textos), com chave de dicionário só depois de `{` ou `,` e índice só depois de nome, `)` ou `]`. Achados durante a aplicação e corrigidos antes do commit (a árvore foi revertida e a troca refeita): comparações `if x == "bloqueou":` e listas `["bloqueado"]` tomadas como chave; chave após comentário de linha inteira (`"explicacao"`, achada pelo percurso e conferida por AST); marcadores `{agente}`/`{qtd}`/`{tamanho}` do quadro de saída; valores que apontam para chave (`'key'` das colunas, `INSERT_FIELDS`, `"inativos"`, nomes de filtro em tuplas); um perfil de teste deixado pela primeira tentativa do percurso, removido pelo id.

O percurso passou a reenviar quatro formulários inválidos (ambiente, minha senha, disparo e agendamento) e exige a tela reapresentada com o campo marcado.

Achado pela bateria Oracle e corrigido antes do commit: as contagens extras da listagem de scripts e de parâmetros vinham do alias da coluna no SQL (`qtd_parametros`, `qtd_scripts`), que vira a chave do item; o alias passou a `param_count`/`script_count` (o FAKE já usava os nomes novos). Aliases internos do SQL lidos por posição (`inicio`, `n` no `health` e na janela da fila) ficam para o D29.

Validação: suítes em 3.6.0, 3.6.8 e 3.13.2 (1275 testes), bateria Oracle (1273), testes progressivos nos cinco agregados, ciclo real do agente, percurso real das telas (44 telas, 4 formulários inválidos, varredura das URLs, 11 contratos JS × servidor), conferência de resíduos.

## 34. JS, CSS, `data-*`, ids e estados das etapas (CR-016d, parte d3a)

Aprovado pelo usuário (2026-10-22) com as decisões D30 (tradução palavra a palavra, na ordem original, para classes, ids e `data-*`), D31 (o id de cada campo segue o nome atual do campo) e D32 (variáveis CSS incluídas).

Alcance: 143 classes `sss-*`, 18 variáveis CSS, 24 atributos `data-*`, 124 ids HTML, 15 componentes Alpine e cerca de 240 identificadores dos `static/js/app/*.js` (estado, métodos, funções e constantes), com as expressões do Alpine nos templates (`x-text`, `@click`, `:class`, `x-ref`, `x-for`…), as strings de classe e id no Python, nos testes e nas ferramentas de `dev/homologation`. Os estados das etapas do detalhe passam a `done`/`current`/`pending`/`skipped` (classes `sss-step-*`). As classes do Bootstrap e os nomes nativos do navegador não mudam.

**Dicionário de palavras:** `aba` → `tab` · `abas` → `tabs` · `aberto` → `open` · `abertos` → `opened` · `abrir` → `open` · `acesso` → `access` · `acoes` → `actions` · `adicionar` → `add` · `afetados` → `affected` · `agd` → `sch` · `agendamento` → `schedule` · `agendamentos` → `schedules` · `agendar` → `schedule` · `agente` → `agent` · `agentes` → `agents` · `ajuda` → `help` · `ajustar` → `adjust` · `alerta` → `alert` · `algum` → `any` · `alteracoes` → `changes` · `alterar` → `change` · `alternar` → `toggle` · `alvo` → `target` · `amarelo` → `yellow` · `amb` → `env` · `ambiente` → `environment` · `ambientes` → `environments` · `anexar` → `append` · `ao` → `on` · `aplicar` → `apply` · `ativo` → `active` · `atrasados` → `delayed` · `atributo` → `attribute` · `atual` → `current` · `atualizacao` → `refresh` · `atualizar` → `refresh` · `aud` → `audit` · `auditoria` → `audit` · `ausentes` → `absent` · `aviso` → `warning` · `barra` → `bar` · `bloco` → `block` · `botao` → `button` · `brutas` → `raw` · `bruto` → `raw` · `busca` → `search` · `buscar` → `search` · `cabecalho` → `header` · `cabecalhos` → `headers` · `cadeia` → `chain` · `caixas` → `boxes` · `campo` → `field` · `campos` → `fields` · `cancelar` → `cancel` · `carregando` → `loading` · `carregar` → `load` · `cartao` → `card` · `cartoes` → `cards` · `categoria` → `category` · `chave` → `key` · `cheio` → `full` · `claro` → `light` · `classe` → `class` · `codigo` → `code` · `codigos` → `codes` · `coletar` → `collect` · `comando` → `command` · `completo` → `full` · `componente` → `component` · `confirmacao` → `confirmation` · `confirmar` → `confirm` · `conjunto` → `set` · `contador` → `counter` · `contagem` → `count` · `copia` → `copy` · `copiado` → `copied` · `copiar` → `copy` · `cor` → `color` · `corpo` → `body` · `dados` → `data` · `datas` → `dates` · `descartado` → `discarded` · `descer` → `down` · `descricao` → `description` · `destaque` → `highlight` · `destino` → `target` · `detalhe` → `detail` · `dia` → `day` · `dias` → `days` · `dica` → `hint` · `dimensoes` → `dimensions` · `disparar` → `trigger` · `disparo` → `trigger` · `disponiveis` → `available` · `divergente` → `mismatch` · `dois` → `two` · `duracao` → `duration` · `editado` → `edited` · `editar` → `edit` · `editaveis` → `editable` · `eh` → `is` · `eixo` → `axis` · `encerrado` → `finished` · `encerrar` → `finish` · `erro` → `error` · `erros` → `errors` · `escolha` → `choice` · `escolhido` → `chosen` · `escuro` → `dark` · `esp` → `space` · `esquema` → `scheme` · `estado` → `state` · `estados` → `states` · `estreito` → `narrow` · `etapa` → `stage` · `etapas` → `stages` · `execucao` → `run` · `exibicao` → `display` · `explicacao` → `explanation` · `exportar` → `export` · `expressao` → `expression` · `faixa` → `stripe` · `falha` → `failure` · `fator` → `factor` · `fechar` → `close` · `feita` → `done` · `feito` → `done` · `fila` → `queue` · `filtrar` → `filter` · `filtro` → `filter` · `filtros` → `filters` · `fim` → `end` · `fragmento` → `fragment` · `frase` → `phrase` · `fundo` → `backdrop` · `gatilho` → `trigger` · `geracao` → `generation` · `grade` → `grid` · `grafico` → `chart` · `grupo` → `group` · `grupos` → `groups` · `homolog` → `homologation` · `homologacao` → `homologation` · `hora` → `hour` · `indice` → `index` · `iniciais` → `initial` · `inicial` → `initial` · `iniciar` → `start` · `inicio` → `start` · `intervalo` → `interval` · `itens` → `items` · `legenda` → `legend` · `ler` → `read` · `limite` → `limit` · `limpar` → `clear` · `linha` → `row` · `linhas` → `rows` · `lista` → `list` · `listagem` → `listing` · `listar` → `list` · `mais` → `more` · `manter` → `keep` · `mapa` → `map` · `marca` → `brand` · `marcados` → `checked` · `marcar` → `mark` · `margem` → `margin` · `matriz` → `matrix` · `menos` → `less` · `mensagem` → `message` · `mensal` → `monthly` · `mes` → `month` · `metodo` → `method` · `metodos` → `methods` · `meus` → `mine` · `mostra` → `show` · `mostrar` → `show` · `motivo` → `reason` · `motivos` → `reasons` · `mover` → `move` · `mudancas` → `changes` · `multipla` → `multiple` · `nao` → `not` · `nome` → `name` · `nomeado` → `named` · `normalizar` → `normalize` · `novo` → `new` · `numero` → `number` · `numeros` → `numbers` · `obrig` → `req` · `obrigatorio` → `required` · `opcoes` → `options` · `padrao` → `default` · `paginacao` → `pagination` · `painel` → `panel` · `par` → `pair` · `para` → `to` · `parametro` → `parameter` · `parametros` → `parameters` · `parar` → `stop` · `pares` → `pairs` · `partes` → `parts` · `passo` → `step` · `passos` → `steps` · `pausa` → `pause` · `pausado` → `paused` · `pendente` → `pending` · `perfil` → `profile` · `permissoes` → `permissions` · `pode` → `can` · `prefixo` → `prefix` · `previa` → `preview` · `prioridade` → `priority` · `problemas` → `problems` · `producao` → `production` · `proximo` → `next` · `pulado` → `skipped` · `quando` → `when` · `questionario` → `questionnaire` · `raio` → `radius` · `raiz` → `root` · `reabrir` → `reopen` · `recarregar` → `reload` · `recorrencia` → `recurrence` · `redefinir` → `reset` · `registro` → `record` · `regra` → `rule` · `remover` → `remove` · `resposta` → `response` · `respostas` → `answers` · `resultado` → `result` · `resultados` → `results` · `resumo` → `summary` · `rodando` → `running` · `rodape` → `footer` · `rolar` → `scroll` · `rotina` → `routine` · `rotulo` → `label` · `roxo` → `purple` · `saida` → `output` · `sair` → `logout` · `saude` → `health` · `secao` → `section` · `seguir` → `follow` · `segundos` → `seconds` · `seguros` → `safe` · `seletor` → `selector` · `sem` → `no` · `semana` → `week` · `semanal` → `weekly` · `senha` → `password` · `sensivel` → `sensitive` · `sequencia` → `sequence` · `sigiloso` → `secret` · `simples` → `simple` · `sinal` → `sign` · `situacao` → `status_text` · `suave` → `muted` · `subir` → `up` · `sucesso` → `success` · `tabela` → `table` · `tela` → `screen` · `telas` → `screens` · `tem` → `has` · `tema` → `theme` · `tempo` → `time` · `temporizador` → `timer` · `terminais` → `terminal` · `termo` → `term` · `testando` → `testing` · `testar` → `test` · `teste` → `test` · `texto` → `text` · `tipo` → `type` · `tipos` → `types` · `titulo` → `title` · `todos` → `all` · `trilha` → `trail` · `trocar` → `switch` · `truncado` → `truncated` · `ultima` → `last` · `unica` → `once` · `usados` → `used` · `usuario` → `user` · `validacao` → `validation` · `valido` → `valid` · `valor` → `value` · `valores` → `values` · `vazia` → `empty` · `ver` → `see` · `verde` → `green` · `vinculo` → `link` · `vinculos` → `links` · `visiveis` → `visible`

**Nomes inteiros:** `campo-ambiente` → `field-environment` · `campo-codigo` → `field-code` · `campo-data_fim` → `field-end_date` · `campo-data_inicio` → `field-start_date` · `campo-descricao` → `field-description` · `campo-dia_mes` → `field-month_day` · `campo-dias_semana` → `field-week_days` · `campo-expressao_cron` → `field-cron_expression` · `campo-hora_execucao` → `field-run_time` · `campo-opcoes_json` → `field-options_json` · `campo-param_nomeado` → `field-param_flag` · `campo-prioridade` → `field-priority` · `campo-regex_validacao` → `field-validation_regex` · `campo-sensivel` → `field-sensitive` · `campo-tipo_componente` → `field-component_type` · `campo-tipo_recorrencia` → `field-recurrence_type` · `campo-valor_padrao` → `field-default_value` · `campo-valor_teste` → `field-test_value` · `config-divergente` → `config-mismatch` · `fila-sem-atendente` → `unattended-queue` · `rodando-sem-pid` → `running-without-pid` · `sss-linha-tempo` → `sss-timeline` · `sss-texto-suave` → `sss-text-muted`

**Identificadores JS com tradução própria** (ordem natural do inglês e colisões): `DURACAO_TOAST_MS` → `TOAST_DURATION_MS` · `ErroHttp` → `HttpError` · `FATOR_BACKOFF` → `BACKOFF_FACTOR` · `FEEDBACK_COPIA_MS` → `COPY_FEEDBACK_MS` · `LIMITE_TELA` → `SCREEN_LIMIT` · `MANTER_TELA` → `SCREEN_KEEP` · `MARGEM_FINAL_PX` → `END_MARGIN_PX` · `METODOS_SEGUROS` → `SAFE_METHODS` · `PREFIXO_PARAM` → `PARAM_PREFIX` · `RE_TOKEN_SIMPLES` → `RE_SIMPLE_TOKEN` · `SELETOR_FRAGMENTO` → `FRAGMENT_SELECTOR` · `STATUS_TERMINAIS` → `TERMINAL_STATUSES` · `TIPOS_TOAST` → `TOAST_TYPES` · `aberto` → `isOpen` · `abertos` → `openItems` · `atualizacaoAgentes` → `agentsRefresh` · `atualizacaoTickets` → `ticketsRefresh` · `avisoAfetados` → `affectedWarning` · `busca` → `searchTerm` · `buscaScript` → `scriptSearch` · `classeFundo` → `backdropClass` · `classeModal` → `modalClass` · `classeStatus` → `statusClass` · `classeTeste` → `testClass` · `diasSemana` → `weekDays` · `esquemaEscuro` → `darkScheme` · `homologacaoScript` → `scriptHomologation` · `horaAtual` → `currentTime` · `linhaVinculo` → `linkRow` · `lista` → `listItems` · `matrizPermissoes` → `permissionMatrix` · `opcoesBrutas` → `rawOptions` · `opcoesIniciais` → `initialOptions` · `parametroForm` → `parameterForm` · `previaAviso` → `previewWarning` · `previaErros` → `previewErrors` · `previaTexto` → `previewText` · `regraAgendamento` → `scheduleRule` · `resultadoTeste` → `testResult` · `resumoDisparo` → `triggerSummary` · `rolarParaFinal` → `scrollToEnd` · `rotuloDescer` → `downLabel` · `rotuloPausa` → `pauseLabel` · `rotuloRemover` → `removeLabel` · `rotuloStatus` → `statusLabel` · `rotuloSubir` → `upLabel` · `statusInicial` → `initialStatus` · `tipoPadrao` → `defaultType` · `tokenExibicao` → `displayToken` · `valorTeste` → `testValue` · `valoresDoMapa` → `mapValues` · `vinculosScript` → `scriptLinks`

Palavras reservadas do JavaScript ganham o sufixo `Value` (`novo` → `newValue`, `classe` → `classValue`, `padrao` → `defaultValue`).

Ferramenta (`d3a.py`): três passadas, kebab por prefixo conhecido (`sss-`, `campo-`, `titulo-`, `filtro-`, `painel-`, `aba-`, `data-`…; só as palavras em português mudam), identificadores do JS fora de strings, comentários e regex literais, com recusa de colisão no mesmo arquivo, e as expressões do Alpine nos templates.

Achados e corrigidos antes do commit: `data-field="valor"`/`"rotulo"` do editor de opções do parâmetro (o JS compara o valor com o nome da propriedade da linha, que passou a `value`/`label`); `--sss-raio` (→ `--sss-radius`). Bug anterior corrigido de passagem: o link "Pular para o conteúdo" apontava para `#conteudo`, mas o `<main>` tem `id="content"`.

Validação além da de sempre: `node --check` nos dez arquivos JS e uma verificação cruzada (toda classe usada existe no CSS, salvo os ganchos sem estilo que já existiam; todo id referenciado por `for`/`aria-*`/`href="#"` existe; todo nome usado no Alpine existe no JS; todo `data-*` lido pelo JS aparece em template). Não há navegador headless na máquina (puppeteer ausente), então o JS não foi executado num navegador; os contratos JS × servidor do percurso continuam valendo.
