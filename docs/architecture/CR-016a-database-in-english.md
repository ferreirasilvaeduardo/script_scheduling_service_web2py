# CR-016a: Banco em inglês

| Campo | Valor |
|---|---|
| Status | **Concluído** em 2026-10-21. Aprovado pelo responsável pelo produto: banco recriado (sem migração de dados), flags `Y`/`N`, tela e documentação em português |
| Origem | Pedido do responsável pelo produto: padronizar em inglês os nomes técnicos (tabelas, colunas, variáveis, código). Primeira fase do CR-016, depois do CR-015a |
| Restrições | Sem dependência nova. Python 3.6. Oracle 11gR2. Identificadores com até 30 caracteres |
| Afeta | `sql_ident`, `ddl_builder`, `init_db`, `gerar_scripts_sql`, `repo_oracle/`, `repo_fake/`, serviços, controllers, views e JavaScript que leem colunas; testes; README §9, §10 e §11; `AGENTS.md`; `docs/DEPLOYMENT.md`; `docs/sql/` |
| Fases seguintes | CR-016b (configuração e operação), CR-016c (código: módulos, funções, chaves lógicas das entidades), CR-016d (web), CR-016e (pasta de trabalho) |

---

## 1. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Nome físico | Tabela física em inglês por `sql_ident.TABELAS[e]['fisico']`; o código monta o nome só por `sql_ident.fisico`, `tabela`, `sequence` e `nomes`. A chave lógica da entidade (`ambientes`, `agendamentos`…) continua até o CR-016c, porque também é nome de repositório e de controller |
| D2 | Colunas e chaves | Coluna em inglês; as chaves das linhas (dicionários dos repositórios), os campos de formulário e os binds acompanham a coluna |
| D3 | Valores gravados | Flags `Y`/`N` (antes `S`/`N`); domínios (`DAILY`, `NAMED`, `ACTIVE`, `AVAILABLE`…), funcionalidades, perfis padrão e ações de auditoria em inglês. As respostas `S`/`N` dos parâmetros de demonstração (opções do script) não mudam |
| D4 | Texto | Comentários de tabela e coluna (`COMMENT ON`), rótulos de tela, mensagens e documentação continuam em português. O `detail` da auditoria passa a citar os nomes de coluna novos |
| D5 | Versão do esquema | Continua 1: a exceção do AGENTS §4.16 (versão aberta até a primeira produção) vale. Sem migração; o banco é refeito pelo ciclo `02_rollback` → `01_deploy` → `99_validate` |
| D6 | Esquema anterior | O `init_db` recusa criar o esquema com a `tbsss_controle` antiga no owner (código 3) e pede o `02_rollback_sss.sql` da versão anterior. Web e agente não acham a `tbsss_control` num banco antigo e não sobem (código 15) |
| D7 | SQL gerado | `01_implantar_sss.sql` → `01_deploy_sss.sql` e `99_validar_implantacao.sql` → `99_validate_deploy.sql`; `02_rollback_sss.sql` mantém o nome |

## 2. Tabelas (com o prefixo padrão)

| Antes | Depois | Abreviação |
|---|---|---|
| `tbsss_ambientes` | `tbsss_environments` | `amb` → `env` |
| `tbsss_perfis` | `tbsss_profiles` | `per` → `prf` |
| `tbsss_funcionalidades` | `tbsss_features` | `fnc` → `fea` |
| `tbsss_perfil_func` | `tbsss_profile_feature` | `pfnc` → `pfea` |
| `tbsss_perfil_amb` | `tbsss_profile_env` | `pamb` → `penv` |
| `tbsss_scripts` | `tbsss_scripts` | `scr` → `scr` |
| `tbsss_perfil_scr` | `tbsss_profile_script` | `pscr` → `pscr` |
| `tbsss_script_amb` | `tbsss_script_env` | `samb` → `senv` |
| `tbsss_usuarios` | `tbsss_users` | `usr` → `usr` |
| `tbsss_parametros` | `tbsss_parameters` | `prm` → `prm` |
| `tbsss_script_param` | `tbsss_script_param` | `sprm` → `sprm` |
| `tbsss_agendamentos` | `tbsss_schedules` | `agd` → `sch` |
| `tbsss_tickets` | `tbsss_tickets` | `tck` → `tck` |
| `tbsss_ticket_resp` | `tbsss_ticket_answer` | `trsp` → `tans` |
| `tbsss_agentes` | `tbsss_agents` | `agt` → `agt` |
| `tbsss_auditoria` | `tbsss_audit` | `aud` → `aud` |
| `tbsss_controle` | `tbsss_control` | `ctl` → `ctl` |
| `tbsss_ticket_saida` | `tbsss_ticket_output` | `tsai` → `tout` |

## 3. Colunas

| Antes | Depois |
|---|---|
| `acao` | `action` |
| `agendamento_id` | `schedule_id` |
| `agente_id` | `agent_id` |
| `ambiente` | `environment` |
| `ambiente_id` | `environment_id` |
| `ambientes` | `environments` |
| `ativo` | `active` |
| `ator` | `actor` |
| `bloqueado_ate` | `locked_until` |
| `categoria` | `category` |
| `codigo` | `code` |
| `conexao` | `connection` |
| `config_criticos` | `critical_config` |
| `conteudo` | `content` |
| `data_fim` | `end_date` |
| `data_inicio` | `start_date` |
| `descricao` | `description` |
| `detalhe` | `detail` |
| `dia_mes` | `month_day` |
| `dias_semana` | `week_days` |
| `entidade` | `entity` |
| `entidade_id` | `entity_id` |
| `etapa` | `stage` |
| `expressao_cron` | `cron_expression` |
| `funcionalidade_id` | `feature_id` |
| `grupo` | `script_group` |
| `hora_execucao` | `run_time` |
| `iniciado_em` | `started_at` |
| `interpretador` | `interpreter` |
| `interpretadores` | `interpreters` |
| `ip_origem` | `source_ip` |
| `log_truncado` | `log_truncated` |
| `max_qtd_parallel_env` | `max_parallel_env` |
| `modulo` | `module` |
| `motivo` | `reason` |
| `nome` | `name` |
| `obrigatorio` | `required` |
| `opcoes_json` | `options_json` |
| `ordem` | `sort_order` |
| `param_nomeado` | `param_flag` |
| `parametro_id` | `parameter_id` |
| `parametros_enviados` | `submitted_params` |
| `parametros_json` | `params_json` |
| `pausa_motivo` | `pause_reason` |
| `perfil_id` | `profile_id` |
| `perm_versao` | `perm_version` |
| `pid_daemon` | `daemon_pid` |
| `plataforma` | `platform` |
| `prioridade` | `priority` |
| `proxima_execucao` | `next_run_at` |
| `purge_concessao_ate` | `purge_lease_until` |
| `purge_dono` | `purge_owner` |
| `qtd_arquivos` | `file_count` |
| `regex_validacao` | `validation_regex` |
| `senha_alterada_em` | `password_changed_at` |
| `senha_hash` | `password_hash` |
| `sensivel` | `sensitive` |
| `sessao_epoch` | `session_epoch` |
| `situacao` | `state` |
| `solicitante` | `requested_by` |
| `status_motivo` | `status_reason` |
| `tamanho_bytes` | `size_bytes` |
| `tentativas_falha` | `failed_attempts` |
| `timeout_seg` | `timeout_s` |
| `tipo_componente` | `component_type` |
| `tipo_param` | `param_type` |
| `tipo_recorrencia` | `recurrence_type` |
| `ultima_execucao` | `last_run_at` |
| `ultimo_login` | `last_login_at` |
| `ultimo_ticket_id` | `last_ticket_id` |
| `usuario_id` | `user_id` |
| `valor_padrao` | `default_value` |
| `valor_padrao_sub` | `default_value_override` |
| `valor_resposta` | `answer_value` |
| `versao` | `version` |
| `versao_aplicada_em` | `version_applied_at` |
| `versao_aplicada_por` | `version_applied_by` |
| `versao_esquema` | `schema_version` |

## 4. Sufixos de constraint e índice

| Antes | Depois |
|---|---|
| `agd` | `sch` |
| `amb` | `env` |
| `campos` | `fields` |
| `dia` | `day` |
| `dsem` | `wday` |
| `fila` | `queue` |
| `fim` | `end` |
| `fnc` | `fea` |
| `grav` | `write` |
| `hora` | `time` |
| `mot` | `rsn` |
| `obrig` | `req` |
| `ocor` | `occur` |
| `pausa` | `pause` |
| `per` | `prf` |
| `per_amb` | `prf_env` |
| `per_fnc` | `prf_fea` |
| `per_scr` | `prf_scr` |
| `prox` | `next` |
| `scr_amb` | `scr_env` |
| `sit` | `state` |
| `tam` | `size` |
| `tcomp` | `ctype` |
| `tent` | `att` |
| `tparam` | `ptype` |
| `trec` | `rtype` |

Sufixos iguais ao nome da coluna seguem a coluna (`nome` → `name`, `ativo` → `active`…).

## 5. Valores gravados

| Antes | Depois |
|---|---|
| `S` (flags) | `Y` |
| `NENHUM` | `NONE` |
| `NOMEADO` | `NAMED` |
| `SEQUENCIAL` | `POSITIONAL` |
| `UNICA` | `ONCE` |
| `DIARIA` | `DAILY` |
| `SEMANAL` | `WEEKLY` |
| `MENSAL` | `MONTHLY` |
| `AMBIENTE_INATIVO` | `ENVIRONMENT_INACTIVE` |
| `CONCLUIDO` | `COMPLETED` |
| `CRON_INVALIDO` | `INVALID_CRON` |
| `ERRO_INTERNO` | `INTERNAL_ERROR` |
| `PARAM_INVALIDO` | `INVALID_PARAM` |
| `SCRIPT_INATIVO` | `SCRIPT_INACTIVE` |
| `SEM_PERMISSAO` | `NO_PERMISSION` |
| `USUARIO_INATIVO` | `USER_INACTIVE` |
| `ATIVO` | `ACTIVE` |
| `PARADO` | `STOPPED` |
| `GRAVANDO` | `WRITING` |
| `DISPONIVEL` | `AVAILABLE` |
| `EXCEDEU` | `EXCEEDED` |
| `FALHOU` | `FAILED` |
| `ARQUIVOS` | `FILES` |
| `ERRO` | `ERROR` |
| `PRAZO` | `DEADLINE` |
| `VER_LOGS` | `VIEW_LOGS` |
| `CANC_TICKET` | `CANCEL_TICKET` |
| `CAD_USUARIOS` | `MANAGE_USERS` |
| `CAD_PERFIS` | `MANAGE_PROFILES` |
| `CAD_AMBIENTES` | `MANAGE_ENVIRONMENTS` |
| `CAD_SCRIPTS` | `MANAGE_SCRIPTS` |
| `CAD_PARAMETROS` | `MANAGE_PARAMETERS` |
| `CAD_AGENDAMENTOS` | `MANAGE_SCHEDULES` |
| `VER_AUDITORIA` | `VIEW_AUDIT` |
| `OPERACAO` | `OPERATION` |
| `ADMINISTRADOR` | `ADMINISTRATOR` |
| `OPERADOR_PROD` | `OPERATOR_PROD` |
| `OPERADOR_HML` | `OPERATOR_HML` |
| `CONSULTA` | `READ_ONLY` |
| `LOGIN_FALHA` | `LOGIN_FAILED` |
| `LOGIN_BLOQUEIO` | `LOGIN_LOCKED` |
| `TICKET_CRIAR` | `TICKET_CREATE` |
| `TICKET_CANCELAR` | `TICKET_CANCEL` |
| `TICKET_REEXECUTAR` | `TICKET_RERUN` |
| `CAD_INSERIR` | `CREATE` |
| `CAD_ALTERAR` | `UPDATE` |
| `CAD_DESATIVAR` | `DEACTIVATE` |
| `PERM_ALTERAR` | `PERM_UPDATE` |
| `AGD_PAUSAR` | `SCHEDULE_PAUSE` |
| `AGENTE_INICIO` | `AGENT_START` |
| `AGENTE_FIM` | `AGENT_STOP` |
| `AUD_EXPORTAR` | `AUDIT_EXPORT` |
| `ESQUEMA_MIGRAR` | `SCHEMA_MIGRATE` |

## 6. Validação

* Suítes em 3.6.0, 3.6.8 e 3.13.2 e bateria Oracle (3.6.15) no GFPR refeito pelo ciclo `02` (versão anterior) → `01` → `99`.
* `99_validate_deploy.sql` sem falhas; `test_db_schema` confere o registro (≤ 30 caracteres) e o README §9.2/§10 contra o registro.
* Teste novo: `test_ddl_builder` (`init_db` detecta a `tbsss_controle` antiga).
