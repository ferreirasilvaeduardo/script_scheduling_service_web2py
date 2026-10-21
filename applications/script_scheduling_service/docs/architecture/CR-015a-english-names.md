# CR-015a: Nomes em inglês das variáveis do script e das chaves de pasta

| Campo | Valor |
|---|---|
| Status | **Concluído** em 2026-10-21. Aprovado pelo responsável pelo produto: todas as variáveis `SSS_*` passadas ao script, troca direta (sem aceitar o nome antigo) e entrega antes da pasta de trabalho |
| Origem | Pedido do responsável pelo produto: padronizar em inglês os nomes técnicos. Primeiro passo da padronização (o CR-016 trata tabelas, colunas, código, configuração e URLs) |
| Restrições | Sem dependência nova. Python 3.6. Sem mudança de esquema |
| Afeta | README §8.6, §8.13, §8.14 e §12.1. `AGENTS.md`. `docs/DEPLOYMENT.md` §18. Código: `env_builder`, `sss_config`, `scheduler_loop`, `pastas_log`, `fase_saida`, `plataforma`, `purge.py` e `bin/sss-helper` (comentários). Notas nos CR-010, CR-012 e CR-014 |
| Revoga | Os nomes em português das variáveis do CR-010, CR-012 e CR-014 e das chaves de pasta do CR-012 e CR-014 |

---

## 1. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Escopo | Todas as variáveis `SSS_*` que o script recebe e as chaves de pasta do `config.ini`. As variáveis do operador e dos testes (`SSS_TEST_*`, `SSS_INIT_DB_PASSWORD`…) não chegam ao script e ficam fora |
| D2 | Valores | Só os nomes mudam. Os valores continuam iguais (`MANUAL`/`AGENDADA`, `DIARIO`/`SEMANAL`/`CRON`, datas `AAAA-MM-DD HH:MM:SS`); os valores de domínio são tratados no CR-016 |
| D3 | Troca direta | O script recebe só os nomes novos. Chave antiga no `config.ini` é recusada na subida com `Chave renomeada: <antiga> passou a se chamar <nova> (CR-015a)` (`sss_config.CHAVES_RENOMEADAS`) |
| D4 | Nomes internos | Funções, subcomandos do helper (`limpar-saida`, `purgar-saida`), campos da especificação do helper (`saida`, `entrada`) e tabelas ficam como estão neste CR |
| D5 | Texto | Telas, mensagens e documentação continuam em português, citando os nomes novos |

## 2. Variáveis do script

| Antes | Depois |
|---|---|
| `SSS_TICKET_PAI_ID` | `SSS_PARENT_TICKET_ID` |
| `SSS_AMBIENTE` | `SSS_ENVIRONMENT` |
| `SSS_AMBIENTE_DESCRICAO` | `SSS_ENVIRONMENT_DESCRIPTION` |
| `SSS_AMBIENTE_DSN` | `SSS_ENVIRONMENT_DSN` |
| `SSS_AMBIENTE_USUARIO` | `SSS_ENVIRONMENT_USER` |
| `SSS_AMBIENTE_CONEXAO` | `SSS_ENVIRONMENT_CONNECTION` |
| `SSS_AGENTE_ID` | `SSS_AGENT_ID` |
| `SSS_AGENTE_HOST` | `SSS_AGENT_HOST` |
| `SSS_PLATAFORMA` | `SSS_PLATFORM` |
| `SSS_VERSAO` | `SSS_VERSION` |
| `SSS_SCRIPT_NOME` | `SSS_SCRIPT_NAME` |
| `SSS_SCRIPT_ARQUIVO` | `SSS_SCRIPT_FILE` |
| `SSS_INTERPRETADOR` | `SSS_INTERPRETER` |
| `SSS_TIPO_EXECUCAO` | `SSS_EXECUTION_TYPE` |
| `SSS_PRIORIDADE` | `SSS_PRIORITY` |
| `SSS_DATA_EXECUCAO` | `SSS_STARTED_AT` |
| `SSS_DATA_AGENDADA` | `SSS_SCHEDULED_AT` |
| `SSS_TIMEOUT_SEG` | `SSS_TIMEOUT_SECONDS` |
| `SSS_AGENDAMENTO_ID` | `SSS_SCHEDULE_ID` |
| `SSS_AGENDAMENTO_NOME` | `SSS_SCHEDULE_NAME` |
| `SSS_RECORRENCIA` | `SSS_RECURRENCE` |
| `SSS_LOG_ARQUIVO` | `SSS_LOG_FILE` |
| `SSS_SAIDA_DIR` | `SSS_OUTPUT_DIR` |
| `SSS_ENTRADA_DIR` | `SSS_INPUT_DIR` |

Sem mudança: `SSS_TICKET_ID`, `SSS_SCRIPT_ID`, `SSS_SCRIPT_DIR`, `SSS_SCRIPT_LINK` e `SSS_LOG_DIR`. A variável `PADRAO_VALOR_RUN_CONEXAO_BD` (compatibilidade do CR-010) continua.

## 3. Chaves do `config.ini`

| Seção | Antes | Depois |
|---|---|---|
| `[agent]` | `saida_dir` | `output_dir` |
| `[agent]` | `saida_max_bytes` | `output_max_bytes` |
| `[agent]` | `saida_max_arquivos` | `output_max_files` |
| `[agent]` | `entrada_dir` | `input_dir` |
| `[logging]` | `saida_retention_days` | `output_retention_days` |

## 4. Validação

* Suítes em 3.6.0, 3.6.8 e 3.13.2 e bateria Oracle (3.6.15, GFPR).
* Testes novos: `test_config` (cada chave renomeada recusada com o nome novo) e `test_env_builder` (nenhum nome antigo definido, nem com todos os dados presentes).
* Ensaio real no GFPR: o script lista as variáveis `SSS_*` que recebeu.
* DEV: `instance/config.ini` com os nomes novos.
