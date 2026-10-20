# CR-010: Dados da execução em variáveis de ambiente do script

| Campo | Valor |
|---|---|
| Status | **Aprovado** em 2026-10-20 pelo responsável pelo produto, com as recomendações das decisões D1 a D5 |
| Origem | Pedido do responsável pelo produto: todo script executado deve receber, por variáveis de ambiente com prefixo reservado, os dados do ambiente e da execução (id, conexão, ambiente, data, tipo de execução, log etc.), para usar se quiser |
| Restrições | Sem dependência nova. Sem mudança de esquema. Python 3.6 |
| Afeta | README §4.1, §8.6, §8.10 e §13. `AGENTS.md` §7.4. Prompt F8.3 (o claim passa os dados novos ao `env_builder`). Código: `env_builder.construir` |
| Revoga | Nada. `PADRAO_VALOR_RUN_CONEXAO_BD` continua |
| Depende de | F8.1 (`env_builder`), CR-009 (caminho do log) |

---

## 1. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Prefixo `SSS_` | Já reservado: o `env_passthrough` recusa `SSS_*` (README §8.6, CR-007 R-32) e nenhuma variável padrão do sistema usa esse nome |
| D2 | Nome antigo mantido | `PADRAO_VALOR_RUN_CONEXAO_BD` continua, com o mesmo valor de `SSS_AMBIENTE_CONEXAO`, para os scripts existentes |
| D3 | Sem solicitante | O login de quem disparou não vai para o ambiente (o CR-008 mascara esse dado nas telas) |
| D4 | Log informativo | `SSS_LOG_DIR` e `SSS_LOG_ARQUIVO` com o nome do arquivo no início (`ticket_<id>.log.parcial`), renomeado logo depois do spawn para `ticket_<id>_<PID>.log`. O script não precisa abrir o arquivo: a saída dele já é o log |
| D5 | Sem parâmetros | Os parâmetros continuam só nos argumentos (README §6.4); nada de `SSS_PARAM_*` |

## 2. Variáveis

| Grupo | Variáveis |
|---|---|
| Execução | `SSS_TICKET_ID`, `SSS_TICKET_PAI_ID`, `SSS_TIPO_EXECUCAO` (`MANUAL`/`AGENDADA`), `SSS_RECORRENCIA`, `SSS_AGENDAMENTO_ID`, `SSS_AGENDAMENTO_NOME`, `SSS_DATA_EXECUCAO`, `SSS_DATA_AGENDADA` (`AAAA-MM-DD HH:MI:SS`), `SSS_PRIORIDADE`, `SSS_TIMEOUT_SEG` |
| Ambiente | `SSS_AMBIENTE`, `SSS_AMBIENTE_DESCRICAO`, `SSS_AMBIENTE_DSN`, `SSS_AMBIENTE_USUARIO`, `SSS_AMBIENTE_CONEXAO` (mascarada em todo log) |
| Script | `SSS_SCRIPT_ID`, `SSS_SCRIPT_NOME`, `SSS_INTERPRETADOR`, `SSS_SCRIPT_ARQUIVO`, `SSS_SCRIPT_DIR` |
| Log | `SSS_LOG_DIR`, `SSS_LOG_ARQUIVO` |
| Agente | `SSS_AGENTE_ID`, `SSS_AGENTE_HOST`, `SSS_PLATAFORMA`, `SSS_VERSAO` |

## 3. Regras

| # | Regra |
|---|---|
| R-a | Variável sem valor (nulo ou só espaços) **não é definida**; as de agendamento só existem na execução agendada |
| R-b | `SSS_AMBIENTE_CONEXAO` e a senha entram no mascarador do processo e no do ticket, como a `PADRAO_VALOR_RUN_CONEXAO_BD` |
| R-c | `SSS_AGENTE_HOST` e `SSS_VERSAO` vêm do agente (F8.3), que decide a versão publicada; sem valor, ficam ausentes |
