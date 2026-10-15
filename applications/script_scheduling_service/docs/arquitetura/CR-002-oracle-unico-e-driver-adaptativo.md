# CR-002: Oracle como banco único (SQL 11gR2) e driver adaptativo Thin → Thick → cx_Oracle

| Campo | Valor |
|---|---|
| Status | **Aprovado** em 2026-10-15 (D1 a D6). Aplicado ao README, ao AGENTS e aos prompts F7–F9 |
| Origem | Decisão do responsável pelo produto em 2026-10-15: aceitar somente Oracle, com SQL compatível a partir do 11g; driver `python-oracledb` tentando Thin e Thick, com `cx_Oracle` como último recurso |
| Revoga | CR-001 **D7** (repositório SQL genérico/ANSI + dialeto) e a parte de dialeto da **D8**. **Substitui** a CR-001 **D10** (driver só em modo Thick) |
| Mantém | Todo o restante do CR-001: agente multiplataforma (D1–D6, D9), DDL a partir do registro de identificadores e limite de 30 caracteres (D8) |
| Afeta | README §2.2, §2.3, §2.5, §2.7, §3.2, §8.12, §10, §11.1 e §12.1. AGENTS §1, §2.2, §4, §5.5, §6, §7 e §8. Prompts F7.x (novo F7.0), F8.x e F9.1 (nome do módulo de conexão) |
| Não afeta | Regras de negócio, RBAC, UI, backend FAKE, modelo de dados, camada de plataforma do agente |

---

## 1. Contexto

O CR-001 previa SQL ANSI com a sintaxe Oracle isolada em `modules/sql_dialeto/`, para permitir outro banco no futuro, e o driver só em modo Thick (o Thin não conecta ao 11g). A camada de banco (F7) **ainda não foi implementada**: não existem `sql_dialeto/`, `repo_sql/` nem `db_conn.py`. A mudança tem custo apenas documental neste momento.

O produto passa a aceitar **somente Oracle**. A portabilidade de banco deixa de ser objetivo, e o SQL é escrito diretamente na forma do Oracle 11gR2. Ao mesmo tempo, quer-se dispensar o Instant Client onde o banco permitir.

---

## 2. Decisões aprovadas

| # | Decisão |
|---|---|
| D1 | **Somente Oracle.** O SQL é escrito diretamente na sintaxe aceita pelo **Oracle 11gR2** (`ROWNUM`, `SYSDATE`, `seq.NEXTVAL`, `FOR UPDATE WAIT n`, `DBMS_LOB`, `EMPTY_CLOB()`, `NVL`, `DECODE`), e continua rodando do 11gR2 ao 23ai. Sintaxe 12c+ segue proibida. Some a camada `sql_dialeto/`; o SQL fica em `modules/repo_oracle/` |
| D2 | **Driver adaptativo** com `[oracle] modo_driver = auto` (padrão). Em `auto`, a ordem é **Thin → Thick → cx_Oracle** (ver §3). Valores forçados: `thin`, `thick`, `cx_oracle` |
| D3 | `cx_Oracle 8.3` é o último recurso: usado quando o `oracledb` não pode ser importado **ou** quando nem o Thin nem o Thick conectam. `modules/db_conn.py` continua sendo a única porta e contém o adaptador das diferenças de API entre os drivers |
| D4 | A lista de erros de rede (reconexão), de lock e de violação é **mapeada por driver e por modo**: `DPY-*` no Thin, `ORA-*`/`DPI-*` no Thick e no cx_Oracle |
| D5 | A suíte de contrato roda em **cada combinação disponível** no ambiente de teste: Thin (exige banco 12.1+), Thick e cx_Oracle |
| D6 | `cryptography` (exigido pelo modo Thin do `oracledb`) entra como dependência homologada. No Python 3.6: `cryptography <= 40.x` |

---

## 3. Seleção do driver (`modo_driver = auto`)

### 3.1 Por que uma sondagem em subprocesso

1. **O modo Thin não conecta ao Oracle 11gR2.** Ele exige banco 12.1 ou superior e falha com `DPY-3010` em versões anteriores. Com o piso no 11g, o Thick continua necessário em parte dos ambientes.
2. **O modo do `oracledb` é fixado por processo.** Depois que o Thick é habilitado (`init_oracle_client`), não há volta ao Thin, e a criação de conexões Thin pode impedir a ativação posterior do Thick. Não é seguro "tentar e cair" dentro do mesmo processo.

Por isso, a escolha é feita **antes da primeira conexão do processo**, por um subprocesso de sondagem descartável, e o processo principal inicializa apenas a combinação vencedora.

### 3.2 Algoritmo

```
para cada candidato em [THIN (oracledb), THICK (oracledb + IC 19), CX_ORACLE (cx_Oracle 8.3 + IC 19)]:
    executar a sondagem do candidato num subprocesso novo (python -I scripts/sondar_driver.py <candidato>)
        - importa o driver; no Thick/cx_Oracle chama init_oracle_client conforme a plataforma (README §2.3)
        - conecta com o DSN e o usuário do config e a senha do secrets.cfg
        - SELECT SYSDATE FROM DUAL e lê a versão do servidor
        - devolve em stdout um JSON: {candidato, ok, versao_servidor, versao_driver, versao_cliente, codigo_erro}
    se ok: escolher o candidato e parar
    se o erro for de AUTENTICAÇÃO (ORA-01017, ORA-28000, ORA-28001, ORA-01005): parar a cadeia e abortar
    caso contrário: registrar WARN com o código do erro e tentar o próximo
se nenhum candidato conectar: abortar com CRITICAL listando o código de erro de cada tentativa
```

* **Parada em erro de autenticação:** credencial errada falharia igual em todos os candidatos e consumiria tentativas do perfil do usuário no banco (`FAILED_LOGIN_ATTEMPTS`), podendo bloqueá-lo. A cadeia só avança para erros de compatibilidade, de biblioteca ou de rede.
* **Segredo:** a senha é entregue ao subprocesso pela entrada padrão, nunca por argumento nem variável de ambiente. A saída do subprocesso nunca contém a senha nem o DSN com credencial.
* **Resultado:** registrado em INFO (`driver=oracledb modo=thin servidor=19.0.0.0`), exposto pelo `check_env.py` e mantido em memória pelo processo. O daemon e o web sondam uma vez na subida (o web sob demanda, no primeiro acesso ao banco, com lock). Uma reconexão reutiliza a mesma combinação; só um reinício refaz a sondagem.
* **Valores forçados** (`thin`, `thick`, `cx_oracle`) pulam a sondagem e usam somente o candidato indicado; falha é fatal.

### 3.3 Matriz de compatibilidade

| Banco | Thin (`oracledb`) | Thick (`oracledb` + IC 19) | `cx_Oracle 8.3` + IC 19 |
|---|---|---|---|
| 11.2.0.4 | Não conecta (`DPY-3010`) | Sim | Sim |
| 12.1, 12.2, 18c, 19c, 21c, 23ai | Sim | Sim | Sim |

| Python | `oracledb` | `cx_Oracle` |
|---|---|---|
| 3.6 | `1.x` (`< 2.0`), com `cryptography <= 40.x` | `8.3` |
| 3.7 a 3.13 | `2.x` | `8.3` só até 3.10 (sem pacote oficial depois) |

* O **Instant Client 19** continua obrigatório nos nós que acessam banco 11g, e recomendado em todos os nós como contingência da cadeia.
* Diferenças de comportamento entre modos que o `db_conn` absorve: códigos de erro (`DPY-*` × `ORA-`/`DPI-`), `call_timeout`, `module`/`action`/`client_identifier` e tipos de bind de data e CLOB. A suíte de contrato garante a paridade (D5).

---

## 4. SQL Oracle 11gR2 (D1)

* Repositórios em `modules/repo_oracle/<agregado>.py` e internos do daemon em `modules/repo_oracle/scheduler_*.py` e `purge.py`.
* Permitido: `ROWNUM`, `SYSDATE`, `seq.NEXTVAL FROM DUAL`, `FOR UPDATE WAIT n` (n ≤ 5), `DBMS_LOB.WRITEAPPEND`, `DBMS_LOB.SUBSTR`, `EMPTY_CLOB()`, `MERGE`, `CASE`, `NVL`, `DECODE`. A comparação nula-segura continua `(c = :v OR (c IS NULL AND :v IS NULL))`.
* Proibido (12c+): `GENERATED ... AS IDENTITY`, `OFFSET`, `FETCH FIRST`, `DEFAULT seq.NEXTVAL`, `JSON_*`/`IS JSON`, `LATERAL`/`APPLY`, `VARCHAR2(32767)` em SQL, `LISTAGG ... ON OVERFLOW`, `WITH FUNCTION`, coluna invisível e índice parcial nativo.
* A aplicação continua **informando o `id`** (`seq.NEXTVAL` lido antes do `INSERT`), com a trigger condicional como defesa.
* A DDL continua gerada a partir do registro de `sql_ident` (limite de 30 caracteres), agora diretamente por `scripts/init_db.py`, sem camada de dialeto.
* Um teste de varredura (`test_sql_oracle11g.py`) rejeita sintaxe 12c+ em `repo_oracle/` e em `init_db.py`.

---

## 5. Configuração

`[oracle]` passa a ter `modo_driver = auto | thin | thick | cx_oracle` no lugar de `driver` e `use_thick_mode`; a chave `dialeto` deixa de existir. `oracle_client_lib_dir` continua (Windows/macOS). A troca no `sss_config.py`, no `config.ini` e no `test_config.py` é feita no **F7.0**, junto com a sondagem; até lá, o código atual (backend FAKE) continua lendo as chaves antigas.

---

## 6. Impacto no plano de execução

| Passo | Mudança |
|---|---|
| **F7.0 (novo)** | `scripts/sondar_driver.py`, seleção do driver em `db_conn.py`, chave `modo_driver` no config, `check_env.py` e `test_db_conn.py` (cadeia com módulos falsos) |
| F7.1 | DDL Oracle 11g direta a partir do registro de identificadores |
| F7.2 | API do `db_conn` (pool, transação, tipos, erros por driver/modo, reconexão) sobre a combinação escolhida no F7.0 |
| F7.3 | SQL Oracle 11g em `repo_oracle/`; contrato rodando em cada combinação disponível |
| F8.x, F9.1 | Referências a `oracle_conn` passam a `db_conn` |

---

## 7. Riscos e pontos a confirmar no F7.0

* Confirmar, com o `oracledb` da versão homologada, se uma tentativa Thin **que falhou** já impede o Thick no mesmo processo. A sondagem em subprocesso torna o desenho independente dessa resposta.
* Confirmar que a falha `DPY-3010` contra 11g ocorre antes da autenticação (não consome tentativa de login no banco).
* Ambientes com *Native Network Encryption* obrigatória no servidor podem recusar o Thin da série 1.x; a cadeia cai para o Thick.
* `cx_Oracle` está descontinuado. Fica como contingência para servidores sem `oracledb` homologado.
