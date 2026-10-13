# SSS — Prompt F7.2: Conexão Oracle (shim Thick)

## Leitura obrigatória antes de planejar
- `AGENTS.md` §2.2, §4.9–4.11, §6 (reconexão)
- `README.md` §2.3 (inteiro), §4.1 (segredos), §12.1 (`[oracle]`)
- Arquivos: `modules/sss_config.py`, `modules/masking.py`, `scripts/init_db.py`

## Objetivo
Ter um ponto único, seguro e resiliente de acesso ao Oracle 11gR2, compatível com `python-oracledb < 2.0` (Thick) e `cx_Oracle 8.3`.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/oracle_conn.py`**, o **único** módulo que importa o driver:
  - **Seleção do driver** por `[oracle] driver`. Validações:
    - `oracledb`: exige `oracledb.__version__ < '2'` e chama `init_oracle_client()` **sem `lib_dir` no Linux** (com `lib_dir` apenas em macOS/Windows, se configurado). Se o Thick não carregar, aborta, porque é proibido cair para o Thin.
    - `cx_Oracle`: exige `8.3.x`.
    - Versão do Instant Client: `clientversion()` com major 19, senão aborta com CRITICAL.
  - **API neutra:** `conectar(cfg, segredos, papel)` com `papel` em `WEB` ou `SCHED`; `pool(cfg, segredos)` para o web com `pool_min`/`pool_max`; e `transacao(conn)`, context manager com `COMMIT` no sucesso, `ROLLBACK` em exceção e log ERROR com o ORA-.
  - **Configuração obrigatória de toda conexão:**
    - `autocommit = False`;
    - `call_timeout` (`call_timeout_ms`);
    - `module`, `action` e `client_identifier` (README §2.3);
    - `current_schema` **não** é alterado (o SQL sempre qualifica o owner).
  - **Tipos neutros:** `TIPO_DATE`, `TIPO_CLOB` e `TIPO_NUMBER`, mapeados para cada driver, e `definir_tipos_entrada(cursor, **mapa)`.
  - **Exceções:** `classificar_erro(exc) -> codigo_ora (int)`. `eh_erro_rede(exc)` cobre a lista do README §2.3; `eh_lock(exc)` cobre 54, 30006 e 60; `eh_violacao(exc)` cobre 1, 2290, 2291, 2292 e 1400. Os demais erros são traduzidos para as exceções `repo_errors`.
  - **Reconexão:** `ConexaoResiliente`, para o daemon. Em erro de rede, reconecta com *backoff* exponencial de 1 s a 60 s e WARN a cada tentativa; a operação em curso **não** é reexecutada automaticamente, e o chamador decide. A espera usa `time.monotonic()` e pode ser interrompida pela flag de shutdown.
  - **`saude(conn)`:** `SELECT SYSDATE FROM DUAL`, retornando o `SYSDATE` *naive*.
  - **`agora_banco(conn)`:** idem, sem microssegundos (README §7.1).
  - **Segredos:** a senha vem de `Segredos`, nunca aparece em `repr` nem em log, e o DSN é logado sem credencial.
- **`applications/script_scheduling_service/scripts/init_db.py`:** substituir o `_conectar` provisório por `oracle_conn.conectar`.
- **`applications/script_scheduling_service/scripts/test_oracle_conn.py`:**
  - **Com mocks** (módulos falsos `oracledb` e `cx_Oracle` injetados em `sys.modules`):
    - recusa de `oracledb` 2.x;
    - `init_oracle_client` sem `lib_dir` no Linux;
    - recusa de IC diferente de 19;
    - `transacao` com commit e rollback;
    - classificação de erros;
    - *backoff* (tempos simulados);
    - `module`/`action` definidos;
    - ausência de senha em logs (captura com `assertLogs`).
  - **Com `SSS_TEST_DSN`:** conexão real, `saude`, `agora_banco` sem microssegundos e roundtrip de bind DATE.

**OUT**
- Sem SQL de negócio (isso é o F7.3).

## Requisitos
1. Nenhum outro arquivo importa `oracledb` ou `cx_Oracle`. Adicione essa checagem ao `test_py36_compat.py`.
2. Mensagens de erro ao usuário nunca expõem o ORA- (AGENTS §3.1). O detalhe fica só no log.

## Critérios de aceite
- [ ] Os testes com mock passam.
- [ ] Com `SSS_TEST_DSN`: a conexão real funciona e `v$session` mostra o `module`/`action` (verificação manual sua, se tiver acesso). Sem `SSS_TEST_DSN`, a parte real fica `NÃO TESTADO`.

## Verificação
`python -m unittest discover -s scripts -p "test_oracle_conn.py" -v`

## Saída
Relatório AGENTS.md §9.
