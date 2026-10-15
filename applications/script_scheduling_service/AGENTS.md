# Script Scheduling Service (SSS) — Regras de Desenvolvimento (AGENTS.md)

Regras **obrigatórias e inegociáveis** para qualquer agente de IA ou desenvolvedor atuando neste projeto.

**Precedência:** o `README.md` é a autoridade de negócio, dados e algoritmos. Este documento é a autoridade de **como** codificar. Se uma regra deste documento conflitar com o README, **pare e reporte** no campo "Observações" do relatório (§9), sem escolher uma das versões por conta própria.

---

## 1. Postura do Agente

* Atue como **Engenheiro de Software Sênior e DBA Oracle**, com foco em Python 3.6, web2py e Oracle 11gR2.
* **Escopo:**
  * Implemente **somente** o subitem solicitado.
  * Não refatore, renomeie nem "melhore" código fora do escopo.
* **Fail-fast documental:** se o README não especifica um comportamento necessário, **não invente**. Pare, liste a lacuna e peça decisão.
* **Estilo:**
  * Sem código didático e sem comentários redundantes. Comente apenas o "porquê" não óbvio (invariantes, ordem de locks, armadilhas do 11g).
  * Docstrings curtas em funções públicas de `modules/`.
* **Proibições gerais:**
  * Não gere código "temporário" nem `TODO` em fluxos de segurança, concorrência ou transação.
  * Não desabilite validações para "fazer passar" um teste.

---

## 2. Runtime e Dependências

### 2.1 Python: sintaxe 3.6, execução em 3.6.0 ou superior

O código deve compilar e rodar em **CPython 3.6.0 ou superior**. As versões validadas vão da **3.6.0** (mínima) à **3.13**, e a **3.6.8** é a versão de referência de produção. A sintaxe e a biblioteca padrão permitidas são as da **3.6.0**. É proibido usar:

| Versão | Recurso proibido |
|---|---|
| 3.7 | `subprocess.run(capture_output=..., text=...)`, `dataclasses`, `datetime.fromisoformat()`, `asyncio.run()`, `contextlib.nullcontext`, `from __future__ import annotations`, `time.time_ns()`, `time.monotonic_ns()`, `breakpoint()`, `contextvars` |
| 3.8 | operador walrus `:=`, parâmetros posicionais `/`, f-string com `=` (`f"{x=}"`), `typing.Literal`, `typing.TypedDict`, `typing.Final`, `typing.Protocol`, `functools.cached_property`, `math.prod`, `shlex.join` |
| 3.9 | generics nativos (`list[int]`, `dict[str, int]`), `str.removeprefix()`, `str.removesuffix()`, `zoneinfo`, `graphlib`, operadores `|` e `|=` em dict |
| 3.10+ | `match`/`case`, `X | Y` em tipos, `zip(strict=True)`, `itertools.pairwise` |

**Permitidos** (existem no 3.6): f-strings simples, `secrets`, `pathlib`, `typing` básico (`List`, `Dict`, `Optional`), `hmac.compare_digest`, `re.fullmatch`, `os.path.commonpath`, `subprocess.DEVNULL`, `time.monotonic()`.

**Compatibilidade nas duas pontas:**

* **Mínimo (3.6.0):** não use nada que tenha surgido em versões de correção posteriores (3.6.1 em diante). Por exemplo, `typing.AsyncGenerator` só existe a partir da 3.6.1; o web2py do repositório recebeu uma proteção de import para isso em `gluon/contrib/multipart.py`.
* **Máximo (3.13):** é proibido depender de módulos removidos ou depreciados nas versões novas (`cgi`, `cgitb`, `imp`, `asyncore`, `asynchat`, `distutils`, `smtpd`, `telnetlib`, `pipes`, `crypt`).

**Atenção a comportamentos:**

* A ordem de inserção de `dict` só é garantia de linguagem a partir do 3.7. Quando a ordem importar (montagem do argv, serialização), use `collections.OrderedDict` ou ordene explicitamente.
* `subprocess` sem `text=`: decodifique bytes explicitamente com `.decode('utf-8', 'replace')`.

### 2.2 Bibliotecas

* Proibido `pip install` e qualquer dependência nova.
* **Proibidos:** Celery, Redis, APScheduler, croniter, Flask, FastAPI, Django, Bottle, SQLAlchemy, Peewee, requests, o **DAL do web2py** (inclusive para auth e sessão) e `gluon.scheduler`.
* **Exceção homologada (pré-instalada na infraestrutura):** `python-oracledb < 2.0` em modo **Thick** **ou** `cx_Oracle 8.3`, mais o **Oracle Instant Client 19.x**.
  * O modo Thin é proibido.
  * É proibido chamar `init_oracle_client(lib_dir=...)` no Linux.
  * Todo acesso ao driver passa por `modules/oracle_conn.py`. Nenhum outro módulo pode importar `oracledb` ou `cx_Oracle`.
* Partes do web2py **permitidas:** roteamento, controllers, views (templating), `gluon.current`, `session.connect(cookie_key=...)`, `HTTP`, `redirect` e `URL`. Proibidos: `SQLFORM`, `Auth`, `Crud`, `DAL` e `Field`.

### 2.3 Frontend hermético

* Proibido CDN, Google Fonts, `@import` remoto e qualquer URL externa em HTML, CSS ou JS.
* **Ativos permitidos:**
  * `static/bootstrap/` (5.3.8)
  * `static/js/alpine.min.js` (**build CSP** do Alpine)
  * `static/js/app/*.js`
  * `static/css/*.css` (estilos próprios, sobre o Bootstrap)
  * `static/img/` (inclui sprite SVG local de ícones)
  * `static/fonts/`
* **Proibidos:**
  * `<script>` inline, `onclick=` e atributos de evento inline;
  * `style=` inline com dado dinâmico;
  * `eval` e `new Function`;
  * `x-html` (use `x-text`);
  * expressões Alpine com lógica complexa no HTML (registre com `Alpine.data()` em `static/js/app/`).
* Toda requisição `fetch` que altera estado envia o cabeçalho `X-CSRF-Token`.

### 2.4 Codificação e texto

* **ASCII puro em:** identificadores, variáveis, rotas, nomes de arquivo e nomes de objetos de banco.
* **Português com acentuação correta (UTF-8) em:** textos de interface (labels, mensagens, telas).
* Arquivos-fonte em UTF-8. Arquivos `.py` com caracteres não ASCII em literais devem declarar `# -*- coding: utf-8 -*-`.

---

## 3. Segurança

### 3.1 SQL

* **Binds obrigatórios** (`:param`) para todo valor.
* **Proibido** concatenar ou formatar valores com `+`, `%`, `.format()` ou f-string.
* **Identificadores dinâmicos** (owner, prefixo) só entram no SQL via `modules/sql_ident.py`, que os valida antes do uso:
  * `owner`: `^[A-Za-z][A-Za-z0-9_]{0,29}$`
  * `table_prefix`: `^[a-zA-Z0-9_]{1,8}$`
  * Nome final do objeto: validado contra o registro de identificadores e com `len <= 30`.
* **Listas `IN`:** os placeholders (`:amb0, :amb1, ...`) são gerados pelo código com contagem controlada, e os valores sempre vão como binds.
* **Binds de data** comparados a colunas `DATE` são declarados via `setinputsizes` como DATE, sem microssegundos (README §7.5).
* Mensagens de erro exibidas ao usuário **nunca** incluem o texto do ORA-, SQL ou stack trace. Esses detalhes vão apenas para o log.

### 3.2 Execução de processos

* **Proibido:** `shell=True`, `os.system`, `os.popen`, `subprocess.getoutput`/`getstatusoutput`, `eval`, `exec`, `compile` sobre dado externo, `pickle`/`marshal`/`shelve` em dado externo, `yaml.load`, `__import__` dinâmico e `importlib` com nome vindo de dado.
* **Spawn único permitido** (`modules/executor.py`): `subprocess.Popen(argv, shell=False, start_new_session=True, close_fds=True, stdin=DEVNULL, stdout=log_fd, stderr=STDOUT, cwd=..., env=clean_env, preexec_fn=_child_limits)`.
  * **Proibido** `stdout=subprocess.PIPE` ou `stderr=subprocess.PIPE` para scripts executados. A saída vai sempre para arquivo.
  * `_child_limits` pode **somente** chamar `os.umask` e `resource.setrlimit`.
  * É proibido criar threads no daemon, porque `preexec_fn` não é thread-safe.
* **Validação de caminho:** apenas por `modules/path_guard.py`, que aplica `realpath` na base e no script, `commonpath`, `isfile`, `real != base` e as regras de ownership e modo (README §8.5). Prefixo por `str.startswith` é **proibido**.
* **Allowlist** de interpretadores: `/usr/bin/python3`, `/bin/bash` e `/bin/sh`. Python é sempre invocado com `-I`.
* **Ambiente do filho:** construído **somente** por `modules/env_builder.py` a partir de um dicionário novo. É proibido usar `os.environ.copy()` como base.
* **Sinais:**
  * O encerramento sempre usa `os.killpg(pgid, SIGTERM)`, aguarda `kill_grace_s` e então aplica `os.killpg(pgid, SIGKILL)`, seguido de `Popen.wait()`.
  * `ProcessLookupError` é tratado como "grupo encerrado".
  * O nó web nunca envia sinais.

### 3.3 Segredos e PII

* Proibido segredo em código, `config.ini`, banco, testes ou fixtures.
* Segredos são lidos **somente** via `modules/sss_config.py`, a partir de `secrets.cfg`, com checagem de dono e modo `0600`.
* Todo segredo carregado é registrado em `modules/masking.py`. Logs, mensagens de erro e `log_output` passam pelo mascaramento.
* Proibido registrar em log: senhas, hashes de senha, `PADRAO_VALOR_RUN_CONEXAO_BD`, `cookie_key`, token CSRF, valores de parâmetros `sensivel = 'S'` e cabeçalho `Cookie`.

### 3.4 Web

* **Sessão:** somente `session.connect(request, response, cookie_key=<secrets>)`, com payload mínimo (README §4.2).
* **CSRF** obrigatório em todo `POST`, validado com `hmac.compare_digest`. `GET` nunca altera estado.
* **Autorização:**
  * Toda action pública começa por um guarda explícito (`_exigir_login()`, `_exigir_func('CODIGO')`) que reconsulta o estado do usuário (README §4.2).
  * Decisões de execução sempre chamam `rbac.pode_executar`.
* **Saída:** sempre escapada com `{{=x}}`. **Proibido** `XML()` ou `{{=XML(...)}}` com qualquer dado de usuário ou de banco.
* **Cabeçalhos de segurança** (CSP, `nosniff`, `frame-ancestors`, `no-store`) são aplicados em `models/10_security.py` para toda resposta.
* **Senha:** somente `modules/security.py` (PBKDF2-SHA256, 200.000 iterações, `hmac.compare_digest`).

---

## 4. Banco de Dados (Oracle 11gR2)

1. **30 caracteres:** todo identificador (tabela, coluna, sequence, trigger, constraint, índice) tem no máximo 30 caracteres **após a expansão do prefixo**. Os nomes vêm exclusivamente do registro em `modules/sql_ident.py`.
2. **PK:** apenas `SEQUENCE` + trigger `BEFORE INSERT` condicional, conforme este template **literal**:
   ```sql
   CREATE OR REPLACE TRIGGER {owner}.{trigger_name}
   BEFORE INSERT ON {owner}.{table_name}
   FOR EACH ROW
   BEGIN
       IF :NEW.id IS NULL THEN
           SELECT {owner}.{sequence_name}.NEXTVAL INTO :NEW.id FROM DUAL;
       END IF;
   END;
   /
   ```
   A atribuição `:NEW.id := seq.NEXTVAL` também é proibida: o 11g a aceita, mas o template acima é o padrão único.
3. **Sintaxe 12c+ proibida:**
   * `GENERATED ... AS IDENTITY`, `OFFSET`, `FETCH FIRST`, `DEFAULT seq.NEXTVAL`;
   * `JSON_VALUE`, `JSON_TABLE` e `IS JSON`;
   * `LATERAL`, `CROSS APPLY` e `OUTER APPLY`;
   * `VARCHAR2(32767)` em SQL, `LISTAGG ... ON OVERFLOW` e `WITH FUNCTION`;
   * coluna invisível e índice parcial nativo (use índice baseado em função com `CASE`).
4. **Paginação:** subquery com `ROWNUM`:
   ```sql
   SELECT * FROM (
     SELECT a.*, ROWNUM rn FROM (<query ordenada>) a WHERE ROWNUM <= :fim
   ) WHERE rn > :inicio
   ```
5. **JSON:** é parseado e gerado **apenas em Python** (`json`). O banco armazena o texto em CLOB e nunca o interpreta.
6. **Texto:** colunas textuais sempre com `VARCHAR2(N CHAR)`, e flags com `CHAR(1)` + CK `IN ('S','N')`.
7. **FKs:** toda FK filha tem índice cuja coluna líder é a FK. Uma UK composta cobre apenas a sua coluna líder.
8. **Índices baseados em função** (`ix_tbsss_tck_fila`, `ix_tbsss_tck_run`): as queries devem repetir a expressão `CASE` **textualmente idêntica** à do índice.
9. **Transações:**
   * `autocommit = False` sempre.
   * Cada operação de negócio corresponde a **uma** transação, com `COMMIT` explícito ao final e `ROLLBACK` em qualquer exceção (`try/except/else` ou `finally`).
   * É proibido `COMMIT` dentro de laço de linhas, exceto nos lotes do `purge.py`.
   * É proibido manter transação aberta durante I/O externo ou espera (sleep, `Popen.wait`). O claim faz commit **antes** do spawn.
10. **Locks:**
    * `SELECT ... FOR UPDATE` sempre com `WAIT n` (n ≤ 5) ou `NOWAIT`.
    * A ordem de aquisição é a do README §8.3 e não pode ser invertida.
    * ORA-00054, ORA-30006 e ORA-00060 levam a `ROLLBACK`, log WARN e continuação.
11. **Concorrência:**
    * Toda transição de estado é um `UPDATE` condicional (`WHERE status = ... AND agente_id = ...`), com checagem obrigatória de `rowcount`.
    * Ignorar `rowcount` é defeito.
12. **Performance:**
    * Proibido `SELECT *` em código de aplicação.
    * Proibido aplicar função em coluna indexada no `WHERE` (por exemplo, `TRUNC(created_at) = :d`). Use intervalo (`created_at >= :d AND created_at < :d + 1`).
    * Use `executemany` para inserções em lote.
    * Toda query nova da fila, do claim, do heartbeat ou do purge tem o `EXPLAIN PLAN` registrado no PR, sem `TABLE ACCESS FULL` nas tabelas de ticket.
13. **LOB:**
    * Escrita incremental via `DBMS_LOB.WRITEAPPEND` (README §8.10).
    * Leitura por locator com offset.
    * É proibido reescrever o CLOB inteiro e proibido carregar `log_output` completo em listagens.
14. **DDL:** reside exclusivamente em `scripts/init_db.py`, que é idempotente (README §11). Nenhum arquivo em `models/` ou `modules/` executa DDL.

---

## 5. Convenções web2py

1. **Rotas privadas:** toda função de `controllers/*.py` que não é action pública começa com `_`. Funções com argumentos também não são expostas, mas o prefixo `_` continua obrigatório.
2. **Contexto:** em `modules/`, use `from gluon import current`. É proibido importar `request`, `session` ou `response` como globais em módulos.
3. **Recarga de módulos:** é proibido `track_changes(True)` em produção.
4. **Models:**
   * `models/00_config.py` e `models/10_security.py` são os únicos arquivos permitidos em `models/`.
   * Nenhum deles abre conexão no import. A conexão é obtida sob demanda via `oracle_conn`.
5. **Separação de camadas:**
   * Controllers não contêm SQL nem regra de negócio. Eles validam a requisição, chamam services/módulos e renderizam.
   * Contratos de persistência ficam em `modules/repo_*.py`: classes abstratas, sem SQL.
   * **SQL reside apenas em `modules/repo_oracle/`.**
   * `modules/repo_fake/` implementa o mesmo contrato em memória, com paridade de semântica (README §2.5). É proibido adicionar ao FAKE um método que não exista no contrato.
   * Controllers e services obtêm repositórios **somente** via `repo_factory`. É proibido importar `repo_fake` ou `repo_oracle` diretamente.
   * **Exceção — repositórios internos de processos batch:** `modules/repo_oracle/scheduler_*.py` (fila, agenda e log) e `modules/repo_oracle/purge.py` não fazem parte do contrato da UI e não têm versão FAKE. Eles são importados diretamente **apenas** por `scheduler_loop.py`, `log_pump.py` e `scripts/purge.py`, todos processos que exigem ORACLE (README §2.5).
   * Regras de negócio residem em `modules/` (rbac, params_compiler, recurrence, executor, *_service).
   * **Trava de ambiente:** `data_backend = FAKE` fora de `sss_env = DEV` aborta a subida. O daemon aborta com FAKE.
6. **Daemon:** o `scripts/run_scheduler.py` é o único entrypoint do scheduler. É proibido iniciar threads, timers ou o scheduler a partir de controllers ou models.

---

## 6. Logging e Robustez

* Use o módulo `logging` com o formato e os níveis do README §13. É proibido `print` em código de aplicação, exceto nos CLIs `init_db.py` e `purge.py` (stdout).
* **Exceções:**
  * Todo `except` registra o contexto (ticket, agente, ação), o código ORA- quando houver e o stack trace em ERROR.
  * É proibido `except:` ou `except Exception: pass` silenciosos.
* **Configuração:** toda chave tem tipo e faixa validados. Chave ausente ou inválida interrompe a inicialização (fail-fast).
* **Graceful shutdown:**
  * Handlers de SIGTERM/SIGINT apenas acionam uma flag.
  * O fechamento de conexão, lock file e descritores ocorre em `finally`.
* **Reconexão:** só o `oracle_conn.py` decide reconectar, seguindo a lista de erros e o *backoff* do README §2.3.
* **Tempo:**
  * Agendamento e tempo de negócio usam o `SYSDATE` do banco.
  * Intervalos internos usam `time.monotonic()`.
  * É proibido `datetime.now()` em lógica de agendamento, heartbeat ou timeout.

---

## 7. Testes

1. Framework **exclusivamente** `unittest`, executado a partir do diretório da aplicação: `python -m unittest discover -s scripts -p "test_*.py"`. O `pytest` é proibido.
   * `scripts/_testenv.py` ajusta o `sys.path` para a aplicação (`modules/`) e para a raiz do web2py (`gluon`). Todo teste o importa primeiro.
   * Módulos de lógica pura (`params_compiler`, `cron_parser`, `recurrence`, `path_guard`, `env_builder`, `masking`, `security`, `rbac`) **não importam `gluon`**. Isso permite testá-los sem o framework.
2. Testes que dependem de Oracle real devem usar mocks da interface de `oracle_conn` **ou** se marcar com `@unittest.skipUnless(os.environ.get('SSS_TEST_DSN'), ...)`. Nesse caso, o veredito do relatório é `NÃO TESTADO` para a parte de banco.
3. Os testes rodam em Python real, no mínimo na **3.6.0** (mínima suportada) e na **3.6.8** (referência de produção). Recomenda-se rodar também na mais nova disponível (3.13). Sem nenhum Python 3.6.x no ambiente, o veredito máximo é `NÃO TESTADO`, e o motivo deve constar nas observações.
4. **Testes obrigatórios mínimos:**

| Arquivo | Cobertura obrigatória |
|---|---|
| `test_repo_contract.py` | A mesma bateria contra FAKE (sempre) e ORACLE (com `SSS_TEST_DSN`): CRUD, unicidade, transições condicionais com `RepoConflito`, cascatas, imutabilidade de `nome`/`login`, paginação e ordenação |
| `test_db_schema.py` | Todo identificador do registro com `len <= 30` usando o prefixo configurado **e** o pior caso de 8 caracteres; todo nome em ASCII; toda FK com índice de coluna líder; toda tabela com trigger no template condicional |
| `test_py36_compat.py` | `ast.parse(..., feature_version)` ou compilação com 3.6 em todos os `.py`; busca por tokens proibidos (§2.1), `shell=True`, `os.system`, `eval(`, `exec(`, `pickle`, `XML(`, `x-html`, URLs `http(s)://` em `static/` e `views/` |
| `test_path_guard.py` | Escape com `..`, symlink para fora da base, prefixo irmão (`/opt/x/scripts_evil`), caminho igual à base, diretório em vez de arquivo, arquivo gravável por grupo ou outros, interpretador fora da allowlist |
| `test_params_compiler.py` | Precedência; obrigatório ausente; `NOMEADO` com flag longa e curta; valor iniciado em `-`; `CHECKBOX`; `SEQUENCIAL` com opcional vazio intermediário; `NENHUM`; regex com `fullmatch`; rejeição de NUL e controle; `SELECT` fora de `opcoes_json`; serialização determinística do snapshot |
| `test_cron_parser.py` | Listas, intervalos, passos, semântica OU de dia, dia 31 e fevereiro, ano bissexto, expressão sem ocorrência, rejeição de nomes e `L`/`W`/`#` |
| `test_recurrence.py` | `DIARIA`, `SEMANAL`, `MENSAL` (mês curto), `UNICA`, `data_fim`, *misfire* `RUN_ONCE`/`SKIP`, datas sem microssegundos |
| `test_env_builder.py` | Ambiente sem herança de `os.environ`; rejeição de variáveis bloqueadas; passthrough; ausência de DSN |
| `test_masking.py` | Mascaramento de segredos, connect string e valores sensíveis, inclusive quando cortados entre blocos |
| `test_rbac.py` | Matriz de `pode_executar` (admin, perfil inativo, sem homologação, sem `EXEC_SCRIPT`); proteção do último admin (mock) |
| `test_executor.py` | Spawn real de script de teste com `/bin/sh` em diretório temporário; saída em arquivo sem PIPE; geração de mais de 1 MB de saída sem travar; timeout; `killpg` encerrando neto; conversão de `returncode` negativo |

5. Cada correção de defeito acompanha um teste de regressão.

---

## 8. Checklist Obrigatório antes de Entregar

- [ ] Nenhum recurso de Python ≥ 3.7 (§2.1).
- [ ] Nenhuma dependência nova; o driver só é importado em `oracle_conn.py`.
- [ ] SQL: apenas binds e identificadores via `sql_ident`; sem sintaxe 12c+; `rowcount` checado em toda transição.
- [ ] Toda transação com `COMMIT`/`ROLLBACK` explícitos; `FOR UPDATE` com `WAIT`/`NOWAIT`.
- [ ] Nenhum identificador novo acima de 30 caracteres; registro de identificadores atualizado.
- [ ] Processos: allowlist, `path_guard`, `env_builder`, sem PIPE, `killpg` com escalada.
- [ ] Web: guarda de login/RBAC, CSRF em POST, saída escapada, sem `XML()` com dado.
- [ ] Logs sem segredos/PII; todo `except` com log.
- [ ] Testes do §7 aplicáveis executados.

---

## 9. Formato Obrigatório de Resposta

Ao concluir qualquer tarefa ou subitem, responda **estritamente** com:

```text
==================================================
RELATÓRIO DE EXECUÇÃO
==================================================
1. Arquivos Criados:
   - caminho/do/arquivo1.ext

2. Arquivos Alterados:
   - caminho/do/arquivo2.ext

3. Testes Executados:
   - scripts/test_exemplo.py (OK / FALHA / NÃO TESTADO: motivo)

4. Checklist §8:
   - Todos os itens OK | Itens não aplicáveis: <lista> | Itens violados: <lista>

5. Veredito:
   - PASS | FAIL | NÃO TESTADO

6. Observações / Anomalias:
   - Lacunas ou conflitos do README encontrados (bloqueantes)
   - Riscos e pontos de atenção
==================================================
```

* `PASS` exige todos os testes aplicáveis OK e nenhum item violado no checklist.
* Qualquer item violado resulta em `FAIL`.
* Lacunas do README impedem `PASS` até que haja uma decisão.
