# SSS — Prompt F7.2: Conexão Oracle (`db_conn`: API sobre o driver escolhido)

## Leitura obrigatória antes de planejar
- `docs/arquitetura/CR-002-oracle-unico-e-driver-adaptativo.md`
- `AGENTS.md` §2.2, §4.9–4.11, §6 (reconexão)
- `README.md` §2.3 (inteiro), §4.1 (segredos), §12.1 (`[oracle]`)
- Arquivos: `modules/sss_config.py`, `modules/masking.py`, `modules/db_conn.py` (seleção do F7.0), `scripts/init_db.py`

## Objetivo
Ter um ponto único, seguro e resiliente de acesso ao Oracle (11gR2 a 23ai), com a mesma API para as três combinações do CR-002: `oracledb` Thin, `oracledb` Thick e `cx_Oracle 8.3`.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/db_conn.py`** (amplia o F7.0), o **único** módulo da aplicação que importa o driver:
  - **Pré-requisito:** a combinação vem de `selecionar_driver`/`inicializar` (F7.0). Nenhuma troca de modo depois da inicialização.
  - **Versões:** em Thick/cx_Oracle, `clientversion()` com major 19, senão CRITICAL. Em Thin, o servidor precisa ser 12.1+ (garantido pela sondagem).
  - **API neutra:** `conectar(cfg, segredos, papel)` com `papel` em `WEB` ou `SCHED`; `pool(cfg, segredos)` para o web com `pool_min`/`pool_max`; e `transacao(conn)`, context manager com `COMMIT` no sucesso, `ROLLBACK` em exceção e log ERROR com o ORA-.
  - **Configuração obrigatória de toda conexão:**
    - `autocommit = False`;
    - `call_timeout` (`call_timeout_ms`);
    - `module`, `action` e `client_identifier` (README §2.3);
    - `current_schema` **não** é alterado (o SQL sempre qualifica o owner).
  - **Tipos neutros:** `TIPO_DATE`, `TIPO_CLOB` e `TIPO_NUMBER`, mapeados para cada driver e modo, e `definir_tipos_entrada(cursor, **mapa)`.
  - **Exceções:** `classificar_erro(exc) -> (prefixo, numero)` (`ORA`, `DPY` ou `DPI`). `eh_erro_rede(exc)` cobre a lista do README §2.3 **por modo** (incluindo os `DPY-*` do Thin); `eh_lock(exc)` cobre 54, 30006 e 60; `eh_violacao(exc)` cobre 1, 2290, 2291, 2292 e 1400. Os demais erros são traduzidos para as exceções `repo_errors`.
  - **Reconexão:** `ConexaoResiliente`, para o daemon. Em erro de rede, reconecta com *backoff* exponencial de 1 s a 60 s e WARN a cada tentativa; a operação em curso **não** é reexecutada automaticamente, e o chamador decide. A espera usa `time.monotonic()` e pode ser interrompida pela flag de shutdown.
  - **`saude(conn)`:** `SELECT SYSDATE FROM DUAL`, retornando o `SYSDATE` *naive*.
  - **`agora_banco(conn)`:** idem, sem microssegundos (README §7.1).
  - **Segredos:** a senha vem de `Segredos`, nunca aparece em `repr` nem em log, e o DSN é logado sem credencial.
- **`applications/script_scheduling_service/scripts/init_db.py`:** substituir o `_conectar` provisório por `db_conn.conectar`.
- **`applications/script_scheduling_service/scripts/test_db_conn.py` (ampliar):**
  - **Com mocks** (módulos falsos `oracledb` e `cx_Oracle` injetados em `sys.modules`):
    - recusa de `oracledb` 2.x no Python 3.6;
    - recusa de IC diferente de 19 (Thick/cx_Oracle);
    - mesma API e mesmo comportamento nas três combinações;
    - `transacao` com commit e rollback;
    - classificação de erros por driver e modo (`ORA-`, `DPY-`, `DPI-`);
    - *backoff* (tempos simulados);
    - `module`/`action` definidos;
    - ausência de senha em logs (captura com `assertLogs`).
  - **Com `SSS_TEST_DSN`:** em cada combinação disponível, conexão real, `saude`, `agora_banco` sem microssegundos e roundtrip de bind DATE.

**OUT**
- Sem SQL de negócio (isso é o F7.3).

## Requisitos
1. Nenhum outro arquivo importa `oracledb` ou `cx_Oracle` além de `db_conn.py` e `sondar_driver.py` (checagem do `test_py36_compat.py`, F7.0).
2. Mensagens de erro ao usuário nunca expõem o ORA-/DPY-/DPI- (AGENTS §3.1). O detalhe fica só no log.

## Critérios de aceite
- [ ] Os testes com mock passam.
- [ ] Com `SSS_TEST_DSN`: a conexão real funciona e `v$session` mostra o `module`/`action` (verificação manual sua, se tiver acesso). Sem `SSS_TEST_DSN`, a parte real fica `NÃO TESTADO`.

## Verificação
`python -m unittest discover -s scripts -p "test_db_conn.py" -v`

## Saída
Relatório AGENTS.md §9.
