# SSS — Prompt F7.2: Conexão Oracle (`db_conn`: API sobre o driver escolhido)

## Leitura obrigatória antes de planejar
- `docs/arquitetura/CR-007-robustez-do-scheduler.md` (R-04, R-12, D1b e D4)
- `docs/arquitetura/CR-002-oracle-unico-e-driver-adaptativo.md`
- `AGENTS.md` §2.2, §4.9–4.11, §6 (reconexão)
- `docs/arquitetura/CR-003-correcoes-pos-analise.md` (D5, D6, D12 e o achado "Bind DATE com microssegundos")
- `README.md` §2.3 (inteiro), §2.7 (`seq.NEXTVAL` antes do `INSERT`), §4.1 (segredos), §4.2 ("Relógio do banco"), §4.4 ("Quantidade registrada" da exportação), §7.1, §7.5 ("Bind de datas"), §12.1 (`[oracle]` e "Falha de configuração"), §13 (formato do log)
- `AGENTS.md` §3.1 (binds de data)
- Arquivos: `modules/sss_config.py`, `modules/masking.py`, `modules/db_conn.py` (seleção do F7.0), `scripts/init_db.py`

## Objetivo
Ter um ponto único, seguro e resiliente de acesso ao Oracle (11gR2 a 23ai), com a mesma API para as três combinações do CR-002: `oracledb` Thin, `oracledb` Thick e `cx_Oracle 8.3`.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/db_conn.py`** (amplia o F7.0), o **único** módulo da aplicação que importa o driver:
  - **Pré-requisito:** a combinação vem de `selecionar_driver`/`inicializar` (F7.0). Nenhuma troca de modo depois da inicialização.
  - **Versões:** em Thick/cx_Oracle, `clientversion()` com major 19, senão CRITICAL. Em Thin, o servidor precisa ser 12.1+ (garantido pela sondagem).
  - **Falhas fatais em CRITICAL:** versão de cliente recusada, `oracledb` 2.x no Python 3.6, falha de conexão no passo 6 da inicialização do daemon (README §8.12) e configuração `[oracle]` inválida geram **um** registro CRITICAL no formato do README §13, com o motivo e o código (ORA-/DPY-/DPI-), sem senha nem DSN com credencial. Sem logging configurado, o CRITICAL vai para o stderr no mesmo formato (README §12.1, "Falha de configuração").
  - **API neutra:** `conectar(cfg, segredos, papel)` com `papel` em `WEB` ou `SCHED`; `pool(cfg, segredos)` para o web com `pool_min`/`pool_max`; e `transacao(conn)`, context manager com `COMMIT` no sucesso, `ROLLBACK` em exceção e log ERROR com o ORA-.
  - **Configuração obrigatória de toda conexão:**
    - `autocommit = False`;
    - `call_timeout` (`call_timeout_ms`);
    - `module`, `action` e `client_identifier` (README §2.3);
    - `current_schema` **não** é alterado (o SQL sempre qualifica o owner).
  - **Tipos neutros:** `TIPO_DATE`, `TIPO_CLOB` e `TIPO_NUMBER`, mapeados para cada driver e modo, e `definir_tipos_entrada(cursor, **mapa)`.
  - **Bind de datas (README §7.5 "Bind de datas", AGENTS §3.1):** todo bind comparado ou gravado numa coluna `DATE` é declarado por `definir_tipos_entrada` com `TIPO_DATE`, que vira `cursor.setinputsizes(...)` com `oracledb.DB_TYPE_DATE` (Thin e Thick) ou `cx_Oracle.DATETIME` (cx_Oracle). O tipo `DATE` declarado descarta a fração, então um `datetime` com microssegundos **nunca** é comparado como `TIMESTAMP` a uma coluna `DATE` (o `UPDATE` otimista travaria silenciosamente com `rowcount = 0`). Os repositórios (F7.3) e o daemon (F8.3/F8.4) não chamam `setinputsizes` direto: usam esta função.
  - **Relógio e IDs do banco para os repositórios** (nomes sugeridos; registre os definitivos no relatório):
    - `agora_banco(conn)` (abaixo) é a base de `RepoUsuarios.agora()` e `RepoTickets.agora()` no Oracle. O relógio do nó nunca é usado para regra de negócio (README §4.2 "Relógio do banco", §7.1);
    - `proximo_id(conn, sequence_qualificada)`: `SELECT {owner}.sq_<...>.NEXTVAL FROM DUAL`, com o nome vindo de `sql_ident`. É a base de `RepoAuditoria.reservar_id()` (a exportação usa `id_max = id reservado − 1`, README §4.4 "Quantidade registrada") e de toda inclusão, porque a aplicação sempre informa o `id` (README §2.7).
  - **Contas por papel (CR-007, D1b):** `[oracle] user` é a conta do papel deste processo (web ou agente); o `purge.py` usa `[retencao] purge_user` com `[purge] password`. A conta dona do esquema nunca é usada aqui (só pelo `init_db.py`).
  - **Conexão com prazo (R-04):** a abertura da conexão respeita `call_timeout_ms` (Thin: `tcp_connect_timeout`; Thick e cx_Oracle: `CONNECT_TIMEOUT` no descritor ou `SQLNET.OUTBOUND_CONNECT_TIMEOUT`, documentado no RUNBOOK).
  - **Pool do web:** `ping_interval` de 60 s (oracledb e cx_Oracle 8.3), para descartar sessões mortas depois de um failover (R-12).
  - **Versão do esquema (CR-007, D4):** `conferir_versao_esquema(conn)`: `SELECT versao_esquema FROM {owner}.tbsss_controle WHERE id = 1` igual a `sql_ident.VERSAO_ESQUEMA`, senão `ErroVersaoEsquema` (CRITICAL na subida do web e do agente, com as duas versões).
  - **Exceções:** `classificar_erro(exc) -> (prefixo, numero)` (`ORA`, `DPY` ou `DPI`). `eh_erro_rede(exc)` cobre a lista do README §2.3 **por modo** (incluindo os `DPY-*` do Thin e os erros de failover do CR-007: ORA-01033, ORA-01034, ORA-01089, ORA-12514, ORA-12528, ORA-12537, ORA-00028, ORA-01012, ORA-02396, ORA-25408); `eh_tempo_esgotado(exc)` cobre o *call timeout* (DPY-4024, DPI-1067, ORA-03156), tratado como timeout de lock (AGENTS §4.10); `eh_lock(exc)` cobre 54, 30006 e 60; `eh_violacao(exc)` cobre 1, 2290, 2291, 2292 e 1400, mais 12899 (valor maior que a coluna) e 1438 (número maior que a precisão), que o FAKE já recusa como `RepoViolacao` (limites de `ator`/`detalhe` da auditoria e `tentativas_falha NUMBER(2)`, README §2.5 e §4.4). Os demais erros são traduzidos para as exceções `repo_errors`.
  - **Reconexão:** `ConexaoResiliente`, para o daemon. Em erro de rede, a conexão é descartada; `garantir()` faz **no máximo uma** tentativa de reconexão quando o prazo do *backoff* (1 s a 60 s, exponencial, em `time.monotonic()`) venceu, e devolve se há conexão, **sem `sleep`** (CR-007, R-04: o laço do daemon nunca espera dentro de uma operação). WARN a cada tentativa; a operação em curso **não** é reexecutada automaticamente, e o chamador decide.
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
    - *backoff* (tempos simulados), sem nenhuma chamada a `time.sleep` em `garantir()` (CR-007);
    - erros de failover e *call timeout* classificados por driver e modo;
    - `conferir_versao_esquema` com versão igual, menor, maior e linha ausente;
    - `module`/`action` definidos;
    - ausência de senha em logs (captura com `assertLogs`);
    - falhas fatais registradas em CRITICAL no formato do §13 (`assertLogs` no nível CRITICAL);
    - `definir_tipos_entrada` com `TIPO_DATE` chama `setinputsizes` com o tipo de data de cada driver (`DB_TYPE_DATE` ou `DATETIME`);
    - `proximo_id` monta o `NEXTVAL` com o nome qualificado do `sql_ident`.
  - **Com `SSS_TEST_DSN`:** em cada combinação disponível, conexão real, `saude`, `agora_banco` sem microssegundos, `proximo_id` e roundtrip de bind DATE. **Teste obrigatório de microssegundos (README §7.5):** um `datetime` igual a um valor `DATE` lido do banco, mas com microssegundos acrescentados, declarado com `TIPO_DATE`, casa na comparação com a coluna (`WHERE col = :d` retorna a linha).

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
