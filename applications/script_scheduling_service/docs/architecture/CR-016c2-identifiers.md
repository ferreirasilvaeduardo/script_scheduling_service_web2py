# CR-016c2: Identificadores em inglês

| Campo | Valor |
|---|---|
| Status | **Em andamento**, em blocos. Bloco 1 (base) concluído em 2026-10-21 |
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
