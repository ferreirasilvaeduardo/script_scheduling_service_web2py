# SSS — Prompt F7.0: Driver adaptativo (Thin → Thick → cx_Oracle)

## Leitura obrigatória antes de planejar
- `docs/arquitetura/CR-002-oracle-unico-e-driver-adaptativo.md` (inteiro)
- `AGENTS.md` §2.2, §3.3, §6, §7
- `docs/arquitetura/CR-003-correcoes-pos-analise.md` (D5: CRITICAL em falha de configuração)
- `README.md` §2.3 (inteiro), §4.1 (segredos), §8.12 (passo 6), §12.1 (`[oracle]`, tabela de faixas e "Falha de configuração"), §13 (formato do log e níveis)
- Arquivos: `modules/sss_config.py`, `modules/masking.py`, `scripts/check_env.py`, `scripts/test_config.py`

## Objetivo
Escolher, antes da primeira conexão do processo, a combinação de driver que funciona no ambiente — `oracledb` Thin, `oracledb` Thick ou `cx_Oracle` — por sondagem isolada em subprocesso, sem nunca expor a senha.

## Escopo
**IN**
- **Configuração (`modules/sss_config.py`, `instance/config.ini`, `instance/config.ini.example`):**
  - `[oracle] modo_driver` (`enum`: `auto`, `thin`, `thick`, `cx_oracle`; padrão `auto`) no lugar de `driver` e `use_thick_mode`, que deixam de existir (chave desconhecida continua abortando a subida).
  - `scripts/test_config.py` atualizado.
- **`applications/script_scheduling_service/scripts/sondar_driver.py <candidato>`** (`thin`, `thick` ou `cx_oracle`):
  - lê o config, recebe a senha **pela entrada padrão** (nunca por argumento nem variável de ambiente);
  - importa o driver; em `thick`/`cx_oracle`, chama `init_oracle_client` conforme a plataforma (sem `lib_dir` no Linux/Unix; com `oracle_client_lib_dir` no Windows/macOS);
  - conecta, executa `SELECT SYSDATE FROM DUAL`, lê a versão do servidor, do driver e do cliente;
  - escreve em stdout **um** JSON: `{candidato, ok, versao_servidor, versao_driver, versao_cliente, codigo_erro, categoria}`, com `categoria` em `AUTENTICACAO`, `INCOMPATIVEL`, `BIBLIOTECA`, `REDE` ou `OUTRO`;
  - nunca escreve a senha nem o DSN com credencial; código de saída 0 mesmo em falha de conexão (o resultado vai no JSON).
- **`applications/script_scheduling_service/modules/db_conn.py` (parte de seleção):**
  - `selecionar_driver(cfg, segredos)`: em `auto`, executa a sondagem de cada candidato em subprocesso (`sys.executable -I`), na ordem Thin → Thick → cx_Oracle; para no primeiro `ok`; **aborta a cadeia em `AUTENTICACAO`**; registra WARN por candidato que falhou e CRITICAL se todos falharem (com o código de cada um). Em `thin`/`thick`/`cx_oracle`, sonda só o candidato indicado, e a falha dele é fatal (README §2.3).
  - **Falhas fatais em CRITICAL (README §13, §12.1 "Falha de configuração"):** todos os candidatos falharam, erro de autenticação que interrompe a cadeia, candidato forçado que falha e `modo_driver` inválido geram **um** registro CRITICAL no formato do §13 (`%(asctime)s %(levelname)s [pid=...] [agente=...] [ticket=-] [acao=...] mensagem`), com o candidato e o código de erro de cada tentativa, sem senha nem DSN com credencial. Se o logging da aplicação ainda não estiver configurado (por exemplo, `log_dir` inválido), o CRITICAL vai para o stderr no mesmo formato, como em `sss_config.obter_config(nome_log=...)`.
  - `inicializar(selecao)`: importa o driver vencedor e, se for Thick/cx_Oracle, chama `init_oracle_client` **antes** de qualquer conexão. Registra INFO `driver=... modo=... servidor=... cliente=...`.
  - resultado mantido em memória por processo (thread-safe); nova sondagem só em reinício.
- **`scripts/check_env.py`:** exibe a cadeia e a combinação escolhida (sem segredo).
- **`applications/script_scheduling_service/scripts/test_db_conn.py`** (com módulos falsos `oracledb` e `cx_Oracle` e sondagem simulada):
  - `auto` escolhe Thin quando o Thin conecta;
  - Thin com `DPY-3010` → Thick; Thick sem biblioteca (`DPI-1047`) → cx_Oracle;
  - `oracledb` ausente → cx_Oracle;
  - erro de autenticação (ORA-01017, ORA-28000) interrompe a cadeia sem tentar os demais;
  - todos falham → erro fatal com os códigos de cada tentativa, registrado em **CRITICAL** no formato do README §13 (`assertLogs` no nível CRITICAL);
  - candidato forçado que falha → CRITICAL e erro fatal, sem sondar os demais;
  - valores forçados não sondam outros candidatos;
  - a senha não aparece em `argv`, no ambiente do subprocesso nem nos logs (`assertLogs`);
  - `init_oracle_client` sem `lib_dir` no Linux.
  - **Com `SSS_TEST_DSN`:** sondagem real de cada candidato disponível; registro das versões.

**OUT**
- Pool, transações, tipos, mapa de erros completo e reconexão (F7.2). SQL de negócio (F7.3).

## Requisitos
1. Nenhum outro arquivo importa `oracledb` ou `cx_Oracle` além de `db_conn.py` e `sondar_driver.py`. Atualize a checagem do `test_py36_compat.py`.
2. Confirme e registre no relatório os dois pontos em aberto do CR-002 §7: se uma tentativa Thin que falhou impede o Thick no mesmo processo, e se o `DPY-3010` ocorre antes da autenticação.
3. Python 3.6: `oracledb < 2.0`; Python 3.7+: `oracledb 2.x`; `cx_Oracle 8.3`.

## Critérios de aceite
- [ ] Os testes com módulos falsos passam em 3.6.0, 3.6.8 e 3.13.
- [ ] Com `SSS_TEST_DSN`: a combinação escolhida e as versões aparecem no log e no `check_env.py`. Sem `SSS_TEST_DSN`, a parte real fica `NÃO TESTADO`.

## Verificação
`python -m unittest discover -s scripts -p "test_db_conn.py" -v`

## Saída
Relatório AGENTS.md §9.
