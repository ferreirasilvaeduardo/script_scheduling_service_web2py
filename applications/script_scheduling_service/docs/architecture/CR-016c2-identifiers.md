# CR-016c2: Identificadores em inglês

| Campo | Valor |
|---|---|
| Status | **Em andamento**, em blocos. Blocos 1 (base), 2 (repositórios), 3a (regras), 3b (services), 4a (camada de processo), 4b (laço do agente), 4c (helper) e 5a (scripts de linha de comando) concluídos em 2026-10-21 |
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
