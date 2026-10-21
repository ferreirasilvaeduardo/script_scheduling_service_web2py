# CR-016c2: Identificadores em inglês

| Campo | Valor |
|---|---|
| Status | **Em andamento**, em blocos. Blocos 1 (base) e 2 (repositórios) concluídos em 2026-10-21 |
| Origem | Regra do README §2.8 (CR-016): funções, classes, métodos, constantes e variáveis em inglês |
| Restrições | Sem dependência nova. Python 3.6. Sem mudança de esquema |
| Blocos | 1 base (`sql_ident`, `sss_config`, `db_conn`, `sss_logging` e formato do log); 2 repositórios e chaves lógicas das entidades; 3 services e regras; 4 daemon; 5 scripts e testes; passada final de parâmetros e variáveis locais |

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
