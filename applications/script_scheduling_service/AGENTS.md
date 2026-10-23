# Script Scheduling Service (SSS) — Regras de Desenvolvimento (AGENTS.md)

Regras **obrigatórias e inegociáveis** para qualquer agente de IA ou desenvolvedor atuando neste projeto.

**Precedência:** o `README.md` é a autoridade de negócio, dados e algoritmos. Este documento é a autoridade de **como** codificar. Se uma regra deste documento conflitar com o README, **pare e reporte** no campo "Observações" do relatório (§9), sem escolher uma das versões por conta própria.

---

## 1. Postura do Agente

* Atue como **Engenheiro de Software Sênior e DBA Oracle**, com foco em Python 3.6+, web2py, Oracle 11gR2+ e agente **somente POSIX** (Linux e Unix — `docs/architecture/CR-005-posix-free-path-and-logs.md`, que revoga a parte Windows do CR-001). Banco **somente Oracle**, com SQL 11gR2 e driver adaptativo (`docs/architecture/CR-002-single-oracle-and-adaptive-driver.md`).
* **Escopo:**
  * Implemente **somente** o subitem solicitado.
  * Não refatore, renomeie nem "melhore" código fora do escopo.
* **Fail-fast documental:** se o README não especifica um comportamento necessário, **não invente**. Pare, liste a lacuna e peça decisão.
* **Estilo:**
  * Sem código didático e sem comentários redundantes. Comente apenas o "porquê" não óbvio (invariantes, ordem de locks, armadilhas do 11g).
  * Docstrings curtas em funções públicas de `modules/`.
  * **Nomes em inglês (CR-016, README §2.8):** objetos do banco, valores gravados, arquivos, pastas, módulos, funções, classes, variáveis, chaves, configuração, variáveis de ambiente, opções de linha de comando e rotas têm nome em inglês. Ficam em português o conteúdo (texto de tela, mensagens, logs legíveis e documentação), os comentários e docstrings e os dados cadastrados. Código novo nasce em inglês. A tradução do legado está encerrada (2026-10-22, README §2.8): os nomes em português que restaram ficam como estão e só mudam junto com uma alteração funcional do mesmo trecho. Rota renomeada não ganha redirecionamento do nome antigo (CR-016d, D22), nem atributo de sessão ou campo de formulário renomeado ganha leitura do nome antigo (D26 a D28). Nome de campo que o JavaScript envia muda junto com o controller que o lê, e chave JSON que o JavaScript lê muda junto com o servidor que a devolve (o percurso confere esse contrato, CR-016d d2b). Variável de tela, entrada de componente e chave de dicionário que vai do serviço ou do repositório para a tela também são em inglês (CR-016d d2c), assim como classe e variável CSS, id HTML, atributo `data-*`, componente Alpine e identificador JS (CR-016d d3a), e função, constante, parâmetro e variável local da camada web: `ui_helpers`, `ui_menu`, `models/`, controllers e locais dos templates (CR-016d d3b). Campo oculto de modal (`hidden_fields`) também é contrato com o controller e muda junto.
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
* **Exceção homologada (pré-instalada na infraestrutura):** o driver Oracle, conforme a versão do Python (CR-002):

  | Python | Driver principal (Thick) | Contingência (Thick) |
  |---|---|---|
  | 3.6 | `python-oracledb 1.x` (`< 2.0`) | `cx_Oracle 8.3` |
  | 3.7 a 3.13 | `python-oracledb 2.x` | `cx_Oracle 8.3` (até 3.10) |

  * Modos Thick e cx_Oracle usam o **Oracle Instant Client 19.x**, obrigatório em todos os nós.
  * **A biblioteca `cryptography` não é usada nem pode virar dependência.** Só o modo Thin precisa dela; o projeto usa `driver_mode = thick` (recomendado no `config.ini.example` e no DEV), e nenhum módulo importa `cryptography`.
  * A seleção é feita por `[oracle] driver_mode` (`auto` = Thin → Thick → cx_Oracle), sempre por **sondagem em subprocesso** antes da primeira conexão do processo (README §2.3). É proibido tentar um modo e "cair" para outro dentro do mesmo processo.
  * Erro de autenticação interrompe a cadeia (não pode consumir tentativas de login no banco).
  * É proibido chamar `init_oracle_client(lib_dir=...)` no Linux e no Unix (lá o IC vem do `ldconfig`/`LD_LIBRARY_PATH`). No macOS (só desenvolvimento), `lib_dir` vem de `oracle_client_lib_dir`.
  * Todo acesso ao driver passa por `modules/db_conn.py` (e pela sondagem `scripts/probe_driver.py`). Nenhum outro módulo pode importar `oracledb` ou `cx_Oracle`.
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
* **Gráficos** (README §5.8):
  * SVG gerado no servidor (ex.: `ui_helpers.stacked_bars`), sem biblioteca de gráficos e sem `style=` inline;
  * cor só por classe CSS, com tokens em `static/css/sss.css` (`--sss-graf-*`) e valores próprios para o modo escuro;
  * a cor nunca é a única pista: legenda sempre presente, `<title>` em cada marca e uma tabela com os mesmos números.

### 2.4 Codificação e texto

* **ASCII puro em:** identificadores, variáveis, rotas, nomes de arquivo e nomes de objetos de banco.
* **Português com acentuação correta (UTF-8) em:** textos de interface (labels, mensagens, telas).
* Arquivos-fonte em UTF-8. Arquivos `.py` com caracteres não ASCII em literais devem declarar `# -*- coding: utf-8 -*-`.
* **Linguagem da interface** (README §2.4.2, CR-004; régua: uma pessoa sem treinamento entende sozinha):
  * toda mensagem ao usuário tem duas partes, "o que aconteceu" e "o que fazer agora";
  * as mensagens-padrão vêm **somente** do catálogo `ui_helpers.MESSAGES` (`ui_helpers.message` ou `message_parts`). É proibido reescrevê-las em controller ou view;
  * a situação do ticket aparece com o nome simples de `ui_helpers` (Esperando, Rodando, Deu certo, Deu erro, Cancelado). O código técnico (`PENDING`, `status_reason`) fica só no "Detalhe técnico";
  * botões dizem o efeito ("Cancelar este pedido", e não "OK"), e confirmações dizem a consequência;
  * campo de formulário traz ajuda com um exemplo do formato esperado.

---

## 3. Segurança

### 3.1 SQL

* **Binds obrigatórios** (`:param`) para todo valor. Os repositórios escrevem sempre `:name`; o `db_conn` converte para o `paramstyle` do driver.
* **Proibido** concatenar ou formatar valores com `+`, `%`, `.format()` ou f-string.
* **Identificadores dinâmicos** (owner, prefixo) só entram no SQL via `modules/sql_ident.py`, que os valida antes do uso:
  * `owner`: `^[A-Za-z][A-Za-z0-9_]{0,29}$`
  * `table_prefix`: `^[a-z][a-z0-9_]{0,7}$` (começa com letra minúscula; CR-007, R-31)
  * Nome final do objeto: validado contra o registro de identificadores e com `len <= 30`.
* **Listas `IN`:** os placeholders (`:amb0, :amb1, ...`) são gerados pelo código com contagem controlada, e os valores sempre vão como binds.
* **Binds de data** comparados a colunas de data são declarados pelo `db_conn` com o tipo de data do driver (`setinputsizes` no Oracle), sem microssegundos (README §7.5).
* Mensagens de erro exibidas ao usuário **nunca** incluem o texto do ORA-/DPY-/DPI-, SQL ou stack trace. Esses detalhes vão apenas para o log.

### 3.2 Execução de processos

* **Proibido:** `shell=True`, `os.system`, `os.popen`, `subprocess.getoutput`/`getstatusoutput`, `eval`, `exec`, `compile` sobre dado externo, `pickle`/`marshal`/`shelve` em dado externo, `yaml.load`, `__import__` dinâmico e `importlib` com nome vindo de dado.
* **Camada de plataforma:** toda primitiva dependente do sistema operacional (spawn, grupo e encerramento de processos, limites, identidade do processo, lock de instância, checagem de dono e permissão, sinais e parada) fica **somente** em `modules/os_platform/` (`posix.py`, para Linux e Unix; CR-005: Windows não é suportado). Fora dela é proibido `os.killpg`, `os.setsid`, `resource`, `fcntl`, `/proc` e `sys.platform` (README §8.0). Também é proibido `ctypes`, `msvcrt` ou qualquer API Windows em todo o projeto, inclusive em `os_platform/` (README §8.0: onde a identidade do processo não puder ser lida sem `ctypes`, `process_identity` devolve `None`).
  * **Exceção isolada do helper (F8.0):** o fonte `bin/sss-helper`, instalado como `/opt/sss/bin/sss-helper`, pode usar `resource.setrlimit` somente em `run`, `os.killpg` somente em `term`/`kill`, ler `/proc/<pid>/stat` (identidade do líder do grupo, README §8.0) somente na função `_identity` usada por `term`/`kill`, e consultar `/proc/<pid>/cwd` ou invocar `pwdx` por caminho absoluto somente em `stop-ticket`. O helper só pode atuar sobre processos do próprio usuário de execução; `stop-ticket` compara o cwd com a pasta exata do ticket. Nenhuma outra primitiva listada nesta regra é permitida nele; `ctypes` e `msvcrt` continuam proibidos em todo o projeto.
  * **Estado provisório até o F8.0:** a camada `os_platform/` ainda não existe. Hoje a checagem de dono e permissão do script fica em `path_guard` e a do `secrets.cfg` em `sss_config`; o F8.0 as move para `os_platform/` sem mudar a regra.
* **Spawn único permitido** (`os_platform.start_process`, chamado só por `modules/executor.py`):
  * **Fora de DEV (CR-007, D1):** o script roda com o **usuário de execução** do ambiente, nunca com o usuário do agente: `subprocess.Popen(['/usr/bin/sudo', '-n', '-u', user, '--', '/opt/sss/bin/sss-helper', 'run'], shell=False, start_new_session=True, close_fds=True, stdin=PIPE, stdout=log_fd, stderr=STDOUT, env=<mínimo>)`, com a especificação (argv, env, limites) pela entrada padrão (README §8.0, §8.4). O helper é o **único** caminho para agir como o usuário de execução (`run`, `term`, `kill`, `clean`, `stop-ticket` e, no CR-012, `pack`, `clean-output` e `purge-output`); é proibido chamar `sudo` para qualquer outro comando.
  * **Em DEV sem usuário de execução:** `subprocess.Popen(argv, shell=False, start_new_session=True, close_fds=True, stdin=DEVNULL, stdout=log_fd, stderr=STDOUT, cwd=..., env=clean_env, preexec_fn=_child_limits)`. `_child_limits` pode **somente** chamar `os.umask` e `resource.setrlimit`. É proibido criar threads no daemon, porque `preexec_fn` não é thread-safe.
  * Qualquer exceção no spawn vira `SPAWN_ERROR` (não só `OSError`).
  * **Proibido** `stdout=subprocess.PIPE` ou `stderr=subprocess.PIPE` para scripts executados. A saída vai sempre para arquivo.
* **Pasta de saída do script (CR-012, README §8.13):**
  * criada, empacotada, limpa e purgada **só** pelos subcomandos do helper (`run` com `saida`, `pack`, `clean-output`, `purge-output`), chamados por `platform` (fora de DEV pelo `sudo`; em DEV, a cópia do pacote `bin/sss-helper` com o próprio usuário). O agente nunca lê nem apaga a pasta por conta própria; a única exceção é `os_platform.create_output_dir`, em DEV sem usuário de execução;
  * caminho só por `log_paths.output_dir` (base `output_dir/<ambiente>` e relativo `<script>/AAAA/MM/DD/HH/MI/ticket_<id>`), conferido de novo pelo helper, que nunca segue link;
  * o zip só tem arquivos regulares; acima de `output_max_files` ou `output_max_bytes` **não há zip parcial**: a linha fica `EXCEEDED` e a pasta fica no disco;
  * a fase de saída (`modules/output_phase.py`) **nunca** altera o resultado do ticket; é máquina de estados do laço, sem espera, em duas etapas: empacotar depois do grupo encerrado e antes do flush final (`poll()` do `pack`, prazo de 120 s; a linha `[SSS]` vai para o log local) e gravar depois da finalização, fora do mapa de execuções (até 4 partes de 1 MiB por volta);
  * toda gravação em `tbsss_ticket_output` exige a posse (`agent_id = :agent_id`), pelo `repo_oracle/scheduler_output`, e é proibido gravar o conteúdo da saída em qualquer log.
* **Pasta de entrada do script (CR-014, README §8.14):**
  * caminho só por `log_paths.input_dir` (base `input_dir/<ambiente>` e relativo = a pasta do script, um nível), na variável `SSS_INPUT_DIR`;
  * criada só pelo helper `run` (campo `entrada`), sem seguir link e só se não existir; em DEV sem usuário de execução, por `os_platform.create_input_dir`. A existente fica como está;
  * **permanente:** o SSS nunca lê, limpa, compacta nem purga essa pasta; nenhum código do agente apaga nada nela;
  * `input_dir` e `output_dir` entram nas pastas do SSS (`SSS_DIR`) para scripts e interpretadores, porque o usuário de execução grava nelas.
* **Nomes em inglês no banco (CR-016a):** tabela, coluna, abreviação, sufixo de constraint/índice e valor gravado são em inglês; o nome físico vem só de `sql_ident` (`physical`, `table`, `sequence`, `names`), nunca de `prefixo + "<entidade>"` no código. A chave lógica da entidade (`ambientes`, `agendamentos`…) muda no CR-016c. Comentários de tabela e coluna (`COMMENT ON`) e texto de tela continuam em português.
* **Nomes em inglês (CR-015a):** variável nova passada ao script e chave nova do `config.ini` têm nome em inglês. Os nomes antigos do CR-015a (`SSS_AMBIENTE`, `saida_dir`…) nunca voltam: chave antiga fica em `sss_config.RENAMED_KEYS` (recusada na subida com o nome novo) e o `env_builder` não define variável antiga. Texto de tela, mensagens e documentação continuam em português.
* **Validação de caminho:** apenas por `modules/path_guard.py` (README §8.5). Prefixo por `str.startswith` é **proibido**.
  * **Caminho livre (CR-005):** `path_file` é o caminho **absoluto** do script, em qualquer lugar do servidor; não há pastas base. Formato: absoluto, normalizado, sem `..`, `\`, `//` nem caractere de controle.
  * **Link simbólico aceito (CR-011):** o agente resolve o `realpath` e executa o arquivo real; recusa em pastas do sistema (`/bin`, `/sbin`, `/usr`, `/lib*`, `/etc`, `/boot`, `/proc`, `/sys`, `/dev`, `/root`) e dentro de `log_dir`/`work_dir`/`exec_work_dir`, no caminho cadastrado e no real, conferidas por `commonpath`. `EACCES` é `NO_ACCESS`, nunca `NOT_FOUND`.
  * **Arquivo real (CR-011, S2):** existe, é arquivo regular e não é gravável por grupo nem por outros. Dono e pastas do caminho não são conferidos, e não há hash: o ambiente controla o conteúdo e a versão dos scripts. O executável de cada interpretador (S3) só precisa existir, ser executável e ficar fora das pastas do SSS (`path_guard.validate_executable`; pode ser link simbólico).
  * **No nó web (CR-011, S1)** só o formato, a allowlist e as pastas do sistema são conferidos; o arquivo é conferido pelo agente, a cada execução (README §8.5).
* **Allowlist de interpretadores lógicos:** `PYTHON3`, `BASH` e `SH`, mapeados por agente para o executável local (`[agent] interpreters`).
  * Python é sempre invocado com `-I`.
* **Ambiente do filho:** construído **somente** por `modules/env_builder.py` a partir de um dicionário novo, com a base por plataforma (README §8.6). É proibido usar `os.environ.copy()` como base.
* **Encerramento escalonado sem bloquear** (`os_platform.signal_group`, CR-007 R-04):
  * SIGTERM ao grupo → prazo `kill_grace_s` → SIGKILL → coleta, como **máquina de estados** do laço. É proibido `sleep`, `time.sleep` em laço de espera ou `Popen.wait()` com prazo dentro de uma operação. `ProcessLookupError`/`ESRCH` é tratado como "grupo encerrado".
  * Ao fim de **todo** ticket, o grupo é encerrado, mesmo que o processo principal tenha saído sozinho (README §8.7, R-02).
  * Fora de DEV, o sinal vai pelo helper (`term`/`kill`), porque o grupo pertence ao usuário de execução.
  * O nó web nunca envia sinais nem encerra processos.
* **Estado local do agente (CR-007, R-01):** `work_dir/ticket_<id>/.sss_proc` (gravado depois do spawn e antes do banco) e `.sss_result` (antes do `UPDATE` de finalização) são a fonte de verdade do startup check. Grave sempre em arquivo temporário + `rename`, com `0600`.
  * O progresso confirmado do CLOB fica em `tbsss_tickets.log_offset_chars`; cada append valida atomicamente offset e conteúdo sob o lock do ticket para permitir recuperação segura de `COMMIT` incerto (README §8.10). É estado técnico e não grava `updated_*`.
  * **Marcador de spawn (CR-008, R-01):** `.sss_spawn` é gravado imediatamente antes do `Popen`. Pasta com `.sss_spawn` e sem `.sss_proc` é "talvez iniciado": nunca devolva esse ticket à fila; use o helper `stop-ticket` e finalize `ORPHAN_PROCESS`. Qualquer exceção depois do `Popen` encerra o grupo de `p.pid` antes de finalizar.
  * **Devolução (CR-008, R-02 e R-07):** só com `process_id` nulo, sem `.sss_proc`, sem `.sss_spawn`, com `cancel_requested = 'N'` e por erro de rede ou prazo do banco (`db_conn.is_network_error`/`is_timeout`). Com `cancel_requested = 'Y'`, finalize `CANCELLED`; outro erro de banco antes do spawn é `PRECHECK_FAILED`.
  * **Nada fica pendente sem retentativa (CR-008, R-08):** finalização, devolução e registro do PID que falham por erro de banco viram estados do mapa local, refeitos a cada ciclo rápido.
* **Launcher do nó web:** `bin/sss-web.sh` recusa root, aplica `umask 077` e só inicia um interpretador `python3[.x]` seguido de `web2py.py` ou `anyserver.py` (README §12.2). Nunca o transforme em executor de comando arbitrário.

### 3.3 Segredos e PII

* Proibido segredo em código, `config.ini`, banco, testes ou fixtures.
* Segredos são lidos **somente** via `modules/sss_config.py`, a partir de `secrets.cfg`, com checagem de dono e permissão pela camada de plataforma (até o F8.0, no próprio `sss_config`): dono = usuário do processo e modo `0600` (README §4.1).
* **Segredos por papel (CR-007, D1b):** `sss_config.load_secrets(path, role)` com `papel` em `web`, `agente` ou `monitor` (CR-008, E3: só `[monitor] user/password`, para o `scripts/health.py`). Cada papel só aceita as próprias seções (o agente nunca tem `[web] cookie_key`; o web nunca tem `[environment:*]` nem `[purge]`); fora de DEV, seção de outro papel recusa a subida. O papel `monitor` é a exceção do README §4.1: só `[web]` é proibida, e as demais seções do arquivo do servidor são ignoradas, sem validar nem registrar no `masking` (F9.1b). Cada papel usa a **sua** conta Oracle (web, agente, purge); a conta dona do esquema só é usada pelo `init_db.py`, com senha digitada.
* Todo segredo carregado é registrado em `modules/masking.py`. Logs, mensagens de erro e `log_output` passam pelo mascaramento.
* Proibido registrar em log: senhas, hashes de senha, `PADRAO_VALOR_RUN_CONEXAO_BD`, `cookie_key`, token CSRF, valores de parâmetros `sensitive = 'Y'` e cabeçalho `Cookie`.

### 3.4 Web

* **Sessão:** somente `session.connect(request, response, cookie_key=<secrets>)`, com payload mínimo (README §4.2).
* **CSRF** obrigatório em todo `POST`, validado com `hmac.compare_digest`. `GET` nunca altera estado.
* **Autorização:**
  * Toda action pública começa por um guarda explícito (`_require_login()`, `_require_func('CODIGO')`) que reconsulta o estado do usuário (README §4.2).
  * Decisões de execução sempre chamam `rbac.can_execute`. O agente também a chama na pré-validação do claim, para o solicitante do ticket (CR-007, D2). O motivo de pausa vem sempre de `rbac.pause_reason_for` (CR-008, R-33), na web e no daemon.
  * **Administrador só por administrador (CR-008, E1):** `MANAGE_USERS` e `MANAGE_PROFILES` não bastam para tocar em perfil administrativo, em `is_admin`, na senha ou no estado de um administrador, nem na matriz do próprio perfil (README §4.3.A). A checagem é do service, com os dados lidos do repositório.
  * **Sessão revogável (CR-008, E2):** a revalidação compara `session_epoch` e a vida máxima (`session_max_hours`); logout, troca e redefinição de senha, desativação e troca de perfil incrementam `session_epoch` (README §4.2).
* **Saída:** sempre escapada com `{{=x}}`. **Proibido** `XML()` ou `{{=XML(...)}}` com qualquer dado de usuário ou de banco.
* **Cabeçalhos de segurança** (CSP, `nosniff`, `frame-ancestors`, `no-store`) são aplicados em `models/10_security.py` para toda resposta.
* **Senha:** somente `modules/security.py` (PBKDF2-SHA256, 200.000 iterações, `hmac.compare_digest`).
* **Validação de entrada:** valor acima do limite ou fora do formato é **recusado** com mensagem, nunca truncado nem convertido em silêncio (README §10, "Texto nos cadastros"). O corte de `request.vars` no controller é só proteção de memória: o limite do controller deve ser maior que o do service, para que o service veja o excesso e o recuse.
* **Segredo fora do HTML:** nenhum valor sensível (nem hash, nem derivado dele) vai para o HTML. A versão de concorrência usa um marcador fixo no lugar do valor sensível (README §10). `sensitive` nunca volta de `Y` para `N` (CR-007, R-20).
* **Ator no quadro Registro (CR-007, D6):** o login de quem criou ou alterou só vai para o HTML de quem tem `VIEW_AUDIT` ou é administrador; para os demais, `ui_helpers.record_info(rec, ctx)` troca por "você", "Sistema (…)" ou "outra pessoa" no servidor. **CR-008, E5:** a regra vale também para o solicitante do ticket e o responsável da regra (`ui_helpers.visible_actor(login, ctx)`).
* **Regex de parâmetro:** só no subconjunto seguro de `params_compiler.validate_registry_regex` (README §6.2, CR-007 D5), em que `{m,n}` com `n − m > 10` conta como ilimitado e, com algum ilimitado, valem no máximo 4 quantificadores de escolha (CR-008, R-06). Nunca execute regex de usuário fora dele.
* **Texto de entrada nos cadastros** (README §10, CR-003):
  * **identificador** (nome de ambiente e de perfil, login, código de parâmetro): `admin_crud.identifier`. Não é limpo; espaço no início ou no fim é recusado;
  * **texto livre** (nomes de exibição, `label`, `description`, `script_group`, `category`, `stage`): `admin_crud.free_text`. Recebe `strip()` e recusa caracteres de controle (`\x00-\x1f`, `\x7f`).
* **Download da saída do ticket (CR-012, README §8.13):** `GET`, com a mesma regra de leitura do log do ticket; só situação `AVAILABLE`; resposta `application/zip` como anexo, com `nosniff`, `no-store` e `Content-Length`, lida do BLOB em fatias (nunca o zip inteiro em memória); sem auditoria. O nome do arquivo é fixo (`ticket_<id>_saida.zip`), nunca vindo de dado.
* **Telas de consulta** (README §2.4.3; ex.: O que eu posso fazer, Rodar um script, Histórico, Agenda, Quem pode o quê):
  * só `GET`; não gravam nada e não auditam;
  * usam o mesmo guarda e o mesmo escopo de ambiente da lista de tickets. Item fora do escopo responde 404;
  * nada fora do perfil do usuário vai para o HTML, nem escondido.
* **Ambiente de produção (CR-017, README §5.4):** o destaque de produção (selo, alerta e botão vermelho) vem só de `tbsss_environments.is_production`. Nunca decida "é produção" pelo nome do ambiente.
* **Filtro que revela pessoa (CR-018a):** filtro por login (solicitante) só vale para quem vê logins (`ui_helpers.sees_actors`), e o serviço o ignora para os demais, não só a tela.
* **Cancelar é para quem enxerga (CR-018a):** ticket de terceiro só é cancelado com `CANCEL_TICKET` **e** `VIEW_LOGS` no ambiente (`rbac.can_cancel`).
* **Aviso de efeito futuro (CR-018a):** mudança de cadastro que invalida execução futura (regra ativa ou ticket na fila) avisa quem salvou, com a mesma checagem do agente; o aviso nunca bloqueia nem desfaz a gravação.
* **Menu:** o item de menu de uma tela segue o mesmo guarda da tela. Quando a tela aceita mais de uma funcionalidade, o item em `ui_menu._CATALOG` recebe a tupla dos códigos (ex.: Tickets, `EXEC_SCRIPT` ou `VIEW_LOGS`, CR-017).
* **Proteções de administração no service**, nunca só na tela: desativar o próprio usuário, tirar o próprio perfil de administrador ou deixar o sistema sem administrador ativo é negado (README §4.3.B).

---

## 4. Banco de Dados (somente Oracle; 11gR2 como piso)

0. **SQL Oracle 11gR2 (CR-002):**
   * Todo SQL dos repositórios fica em `modules/repo_oracle/`, escrito diretamente na sintaxe aceita pelo **Oracle 11gR2**, e precisa rodar também nas versões superiores (12c a 23ai).
   * Permitidos: `ROWNUM`, `SYSDATE`, `seq.NEXTVAL FROM DUAL`, `FOR UPDATE WAIT n`, `FOR UPDATE SKIP LOCKED` (CR-007: desdobro e NODE_OFFLINE), `DBMS_LOB.*`, `EMPTY_CLOB()`, `MERGE`, `CASE`, `NVL`, `DECODE`, `GREATEST` e `FLOOR`. Prefira `CASE` quando ele deixar a intenção mais clara.

1. **30 caracteres:** todo identificador (tabela, coluna, sequence, trigger, constraint, índice) tem no máximo 30 caracteres **após a expansão do prefixo**. Os nomes vêm exclusivamente do registro em `modules/sql_ident.py`.
2. **PK:** a aplicação **sempre informa o `id`**, obtido de `seq.NEXTVAL` antes do `INSERT`. Existe também uma `SEQUENCE` + trigger `BEFORE INSERT` condicional (defesa para inserções manuais), conforme este template **literal**:
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
3. **Sintaxe 12c+ proibida** (verificada por `test_sql_oracle11g.py`):
   * `GENERATED ... AS IDENTITY`, `OFFSET`, `FETCH FIRST`, `DEFAULT seq.NEXTVAL`;
   * `JSON_VALUE`, `JSON_TABLE` e `IS JSON`;
   * `LATERAL`, `CROSS APPLY` e `OUTER APPLY`;
   * `VARCHAR2(32767)` em SQL, `LISTAGG ... ON OVERFLOW` e `WITH FUNCTION`;
   * coluna invisível e índice parcial nativo (use índice baseado em função com `CASE`).
4. **Paginação:** sempre com a subquery de `ROWNUM`:
   ```sql
   SELECT * FROM (
     SELECT a.*, ROWNUM rn FROM (<query ordenada>) a WHERE ROWNUM <= :end_ts
   ) WHERE rn > :start_ts
   ```
5. **JSON:** é parseado e gerado **apenas em Python** (`json`). O banco armazena o texto em CLOB e nunca o interpreta.
6. **Texto:** colunas textuais `VARCHAR2(N CHAR)` e flags com `CHAR(1)` + CK `IN ('Y','N')`.
7. **FKs:** toda FK filha tem índice cuja coluna líder é a FK. Uma UK composta cobre apenas a sua coluna líder.
8. **Índices baseados em função** (`ix_tbsss_tck_queue`, `ix_tbsss_tck_run`): as queries devem repetir a expressão **textualmente idêntica** à do índice (`sql_ident.FBI_TCK_QUEUE_START`, `FBI_TCK_RUN_AGENT_CASE`). **Fila (CR-013):** a seleção de candidatos lê a fila só pela janela por ambiente e prioridade de `ix_tbsss_tck_queue` (`status`, `environment`, `priority` simples na frente, `ORDER BY` igual à ordem do índice e `ROWNUM <= :batch_size`), sem ordenar a fila inteira; é proibido voltar a ordenar todos os `PENDING` por expressão de `SYSDATE`. Índice de fila só com `CASE` não elimina o sort no Oracle.
9. **Transações:**
   * `autocommit = False` sempre.
   * Cada operação de negócio corresponde a **uma** transação, com `COMMIT` explícito ao final e `ROLLBACK` em qualquer exceção (`try/except/else` ou `finally`).
   * É proibido `COMMIT` dentro de laço de linhas, exceto nos lotes do `purge.py`.
   * É proibido manter transação aberta durante I/O externo ou espera (sleep, `Popen.wait`). O claim faz commit **antes** do spawn.
10. **Locks:**
    * Lock de linha sempre com `FOR UPDATE WAIT n`, com espera de no máximo 5 s, ou com `FOR UPDATE SKIP LOCKED` onde o README manda pular linhas travadas (§7.5, §8.8).
    * **Todo DML pode bloquear** numa linha travada por outra sessão (inclusive uma sessão morta): o limite efetivo é o `call_timeout_ms`, e o *call timeout* (DPY-4024, DPI-1067, ORA-03156) é mapeado pelo `db_conn` e tratado como o timeout de lock (CR-007, R-12). Nenhuma operação do daemon pode depender de uma espera mais longa que isso.
    * A ordem de aquisição é a do README §8.3 e não pode ser invertida.
    * Timeout de lock, deadlock e *call timeout* (ORA-00054, ORA-30006, ORA-00060 e os do item acima, mapeados pelo `db_conn` para cada driver e modo) levam a `ROLLBACK`, log WARN **sem stack trace** e continuação.
11. **Concorrência:**
    * Toda transição de estado é um `UPDATE` condicional (`WHERE status = ... AND agent_id = ...`), com checagem obrigatória de `rowcount`.
    * Ignorar `rowcount` é defeito.
12. **Performance:**
    * Proibido `SELECT *` em código de aplicação.
    * Proibido aplicar função em coluna indexada no `WHERE` (por exemplo, `TRUNC(created_at) = :d`). Use intervalo (`created_at >= :d AND created_at < :d + 1`).
    * Use `executemany` para inserções em lote.
    * Toda query nova da fila, do claim, do heartbeat, do desdobro, do NODE_OFFLINE, do purge **e das listagens e telas de consulta** (lista de tickets, histórico, últimas execuções) tem o `EXPLAIN PLAN` registrado no PR, sem `TABLE ACCESS FULL` nas tabelas de ticket e de auditoria (CR-007, R-29).
    * O `COUNT` das listagens para em 10.001 (`ROWNUM <= 10001`); a tela mostra "mais de 10.000" (README §10).
13. **LOB:**
    * Escrita incremental com `DBMS_LOB.WRITEAPPEND` (README §8.10).
    * Leitura com offset por locator ou `DBMS_LOB.SUBSTR`.
    * É proibido reescrever o CLOB inteiro e proibido carregar `log_output` completo em listagens.
14. **DDL:** é gerada a partir do registro de `sql_ident` e executada exclusivamente por `scripts/init_db.py`, que é idempotente (README §11). Nenhum arquivo em `models/` ou `modules/` executa DDL.
15. **Colunas de registro (CR-006, README §10):** toda tabela, exceto `tbsss_audit` e `tbsss_control`, tem `created_at`, `created_by`, `updated_at` e `updated_by`.
    * Todo `INSERT` grava `created_at = SYSDATE` e `created_by = :actor`. Nenhum `UPDATE` toca `created_*`.
    * Todo `UPDATE` de **alteração de negócio** grava `updated_at = SYSDATE` e `updated_by = :actor`. Rotina técnica (heartbeat, log, PID, contadores do login, avanço do desdobro) **não** grava. A lista fechada das duas categorias está no README §10.
    * O ator vem de `audit['actor']` ou do parâmetro `actor=`: login, `SYSTEM:<agent_id>`, `SYSTEM:init_db` ou `SYSTEM:seed`. Sem ator, o repositório lança `RepoViolation` sem gravar nada.
    * Vínculos de conjunto são gravados por diferença; `script_param` leva o `created_*` de cada parâmetro que continua.
    * As colunas não entram na `version` do formulário, no `esperado` nem no `detail` da auditoria.
16. **Versão do esquema (CR-007, D4):** `sql_ident.SCHEMA_VERSION` é a versão que o código espera. Toda mudança de esquema (tabela, coluna, CK, índice, trigger) **incrementa** `SCHEMA_VERSION` e traz a migração `scripts/migrations/m<NNNN>_<descricao>.py`, idempotente, no mesmo pacote. Web e agente recusam subir se `tbsss_control.schema_version` for diferente. O `init_db` compara o esquema real com o registro, depois de normalizar os textos do dicionário (`sql_ident.normalize_expression`, CR-008 R-14), e aborta em divergência; nunca corrige sozinho.
    * **Exceção até a primeira produção (CR-008; ajustada no F7.3):** enquanto o esquema não foi implantado em produção, as mudanças entram direto na versão 1, sem migração; os bancos de DEV (ex.: `GFPR`) são refeitos pelo ciclo `02_rollback` → `01_deploy` → `99_validate`. A primeira implantação em produção congela a versão 1; dali em diante, vale a regra acima.
    * **CR-016a:** os nomes em inglês (tabelas, colunas, constraints, valores gravados) entraram por essa exceção, sem migração. O GFPR foi refeito pelo ciclo; o `init_db` recusa criar o esquema com a `tbsss_controle` antiga no owner.
17. **Contas por papel (CR-007, D1b; CR-008, E3):** papéis web, agente, purge e monitor (só leitura). O código da aplicação nunca usa a conta dona do esquema (`[oracle] user` igual ao `owner` é recusado fora de DEV, CR-008 R-29). Os GRANTs de cada papel estão no README §11.1; uma query nova que precise de privilégio novo atualiza essa tabela no mesmo pacote.

---

## 5. Convenções web2py

1. **Rotas privadas:** toda função de `controllers/*.py` que não é action pública começa com `_`. Funções com argumentos também não são expostas, mas o prefixo `_` continua obrigatório.
2. **Contexto:** em `modules/`, use `from gluon import current`. É proibido importar `request`, `session` ou `response` como globais em módulos.
3. **Recarga de módulos:** é proibido `track_changes(True)` em produção.
4. **Models:**
   * `models/00_config.py` e `models/10_security.py` são os únicos arquivos permitidos em `models/`.
   * Nenhum deles abre conexão no import. A conexão é obtida sob demanda via `db_conn`.
5. **Separação de camadas:**
   * Controllers não contêm SQL nem regra de negócio. Eles validam a requisição, chamam services/módulos e renderizam.
   * Contratos de persistência ficam em `modules/repo_*.py`: classes abstratas, sem SQL.
   * **SQL reside apenas em `modules/repo_oracle/`** (Oracle 11gR2) e em `scripts/init_db.py` (DDL).
   * `modules/repo_fake/` implementa o mesmo contrato em memória, com paridade de semântica (README §2.5). É proibido adicionar ao FAKE um método que não exista no contrato.
   * Controllers e services obtêm repositórios **somente** via `repo_factory`. É proibido importar `repo_fake` ou `repo_oracle` diretamente.
   * O `repo_factory` importa o `repo_fake` **só dentro do ramo FAKE**, nunca no nível do módulo: o pacote de implantação não leva o `repo_fake` (README §12.2), e um import de topo derruba a aplicação implantada (F9.1d; `test_package.py` confere que nada que vai no pacote importa no topo o que fica fora dele).
   * **Exceção — repositórios internos de processos batch:** `modules/repo_oracle/scheduler_*.py` (fila, agenda e log), `modules/repo_oracle/purge.py` e `modules/repo_oracle/health.py` não fazem parte do contrato da UI e não têm versão FAKE. Eles são importados diretamente **apenas** por `scheduler_loop.py`, `log_pump.py`, `scripts/purge.py` e `scripts/health.py`, todos processos que exigem banco real (README §2.5), e não importam gluon. Única exceção: `repo_oracle/agents.py` importa do `repo_oracle/health.py` o SQL da fila sem atendente e do rodando sem PID e o cálculo dos pares atendidos, para a tela de agentes e o monitoramento não divergirem (F9.1b).
   * Regras de negócio residem em `modules/` (rbac, params_compiler, recurrence, executor, *_service).
   * **Backend:** a aplicação usa sempre o Oracle do `[oracle]` (owner e prefixo); `[app] data_backend` foi removida no F7.3 e é recusada se aparecer. O FAKE só existe injetado por teste (`repo_factory.configure`) e só com `sss_env = DEV`. DEV e PROD se separam pelo owner e pelo prefixo; `sss_env` continua como trava de segurança.
6. **Daemon:** o `scripts/run_scheduler.py` é o único entrypoint do scheduler. É proibido iniciar threads, timers ou o scheduler a partir de controllers ou models.

---

## 6. Logging e Robustez

* Use o módulo `logging` com o formato e os níveis do README §13. É proibido `print` em código de aplicação, exceto nos CLIs `init_db.py`, `purge.py` e `health.py` (stdout; o `health.py` não grava log em arquivo, a saída do plugin fica no monitoramento).
* **Exceções:**
  * Todo `except` registra o contexto (ticket, agente, ação), o código ORA- quando houver e o stack trace em ERROR.
  * **Exceção (CR-007):** situações esperadas e tratadas (timeout de lock, deadlock, *call timeout*, `rowcount = 0` de corrida perdida, linha pulada por `SKIP LOCKED`) vão em WARN com o código e **sem** stack trace (README §13).
  * **Exceção (revisão F8.0–F8.2):** `except` de fluxo previsto de SO, em que a condição é o próprio resultado esperado (`ProcessLookupError`/ESRCH de grupo já vazio, `FileNotFoundError`/ENOENT de arquivo de estado ainda inexistente, `OSError` ao ler `/proc/<pid>` de um processo que acabou de sair), pode não registrar nada, desde que tenha um comentário explicando o caso. Qualquer outra falha segue a regra acima.
  * É proibido `except:` ou `except Exception: pass` silenciosos.
* **Caminhos de log (CR-005):** montados **somente** por `modules/log_paths.py`, nunca à mão:
  * log da aplicação: `log_dir/internal/app/AAAA/MM/DD/HH/MI/<log_name>_<PID>.log`, com troca por tamanho e retenção por dias (README §13);
  * log de execução do script: `log_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log`, com a hora de `started_at` e o ambiente do ticket **obrigatório** (README §8.4; CR-009). Todo log começa pela pasta do ambiente; sem ambiente, `internal` (nome de ambiente reservado).
* **Configuração:** toda chave tem tipo e faixa validados. Chave ausente, desconhecida ou inválida interrompe a inicialização (fail-fast). Antes de abortar, a falha é registrada em CRITICAL por `sss_logging.log_initial_critical`, no `log_dir` quando ele aceita escrita e no stderr caso contrário (README §12.1).
* **Graceful shutdown:**
  * Handlers de SIGTERM/SIGINT apenas acionam uma flag. O arquivo `work_dir/sss-<agent_id>.stop`, verificado a cada ciclo, tem o mesmo efeito.
  * O fechamento de conexão, lock file e descritores ocorre em `finally`.
* **Reconexão:** só o `db_conn.py` decide reconectar, seguindo a lista de erros (mapeada por driver e modo) e o *backoff* do README §2.3: **uma tentativa por ciclo**, com o *backoff* em prazos do relógio monotônico, nunca com `sleep` (CR-007, R-04).
* **Orçamento do laço do daemon (CR-007, R-04):** nenhuma operação bloqueia além de `call_timeout_ms`; o fence é conferido a cada iteração e depois de cada chamada ao banco; claim e desdobro param ao gastar `heartbeat_interval_s / 2`. As invariantes I1 a I4 do README §8.9 são validadas pelo `sss_config`.
* **Codificação:** web e daemon abortam se `sys.getfilesystemencoding()` não for UTF-8 (os launchers exportam `LANG`/`LC_ALL`; README §12.2).
* **Tempo:**
  * Agendamento e tempo de negócio usam o relógio do banco (`SYSDATE`). No nó web, o horário vem de `now()` do repositório (ex.: bloqueio de login em `repo_users`); o relógio local do servidor web não decide regra de negócio.
  * Intervalos internos usam `time.monotonic()`.
  * É proibido `datetime.now()` em lógica de agendamento, heartbeat ou timeout.

---

## 7. Testes

1. Framework **exclusivamente** `unittest`, executado a partir do diretório da aplicação: `python -m unittest discover -s scripts -p "test_*.py"`. O `pytest` é proibido.
   * `scripts/_testenv.py` ajusta o `sys.path` para a aplicação (`modules/`) e para a raiz do web2py (`gluon`). Todo teste o importa primeiro.
   * Módulos de lógica pura (`params_compiler`, `cron_parser`, `recurrence`, `path_guard`, `env_builder`, `masking`, `security`, `rbac`) **não importam `gluon`**. Isso permite testá-los sem o framework.
2. Testes que dependem de banco real devem usar mocks da interface de `db_conn` **ou** ser ligados só por `SSS_TEST_ORACLE=1` (`_oracle_test_support.real_db_configured()`), com owner, prefixo, DSN e conta lidos do `instance/config.ini` e a guarda de `scripts/_oracle_test_support.py` antes de qualquer escrita (README §2.5). Sem a chave, o veredito do relatório é `NÃO TESTADO` para a parte de banco. A partir do F7, aplicação e validações usam as tabelas reais; o FAKE fica só como dublê dos testes automáticos sem banco.
   * **Plataforma:** a implementação POSIX é testada de verdade, no Linux (CR-005).
3. Os testes rodam em Python real, no mínimo na **3.6.0** (mínima suportada) e na **3.6.8** (referência de produção). Recomenda-se rodar também na mais nova disponível (3.13). Sem nenhum Python 3.6.x no ambiente, o veredito máximo é `NÃO TESTADO`, e o motivo deve constar nas observações.
4. **Testes obrigatórios mínimos** (os marcados com `[F7.x]`/`[F8.x]` são criados no prompt indicado e ainda não existem):

| Arquivo | Cobertura obrigatória |
|---|---|
| `test_repo_contract.py` | A mesma bateria contra FAKE (sempre) e ORACLE (com `SSS_TEST_ORACLE=1`; cada teste cria e limpa a própria massa, sem depender do seed), em cada combinação de driver disponível — Thin (banco 12.1+), Thick e cx_Oracle (CR-002, D5): CRUD, unicidade, transições condicionais com `RepoConflict`, cascatas, imutabilidade de `name`/`login`, paginação e ordenação; colunas de registro (CR-006): `created_*` na inclusão, `updated_*` só na alteração de negócio, ator obrigatório, vínculos por diferença preservando `created_*` |
| `test_db_schema.py` | Todo identificador do registro com `len <= 30` usando o prefixo configurado **e** o pior caso de 8 caracteres; todo nome em ASCII; toda FK com índice de coluna líder; toda tabela com trigger no template condicional; as 17 tabelas e o README §10 igual ao registro; `SCHEMA_VERSION` declarada (CR-007) |
| `test_py36_compat.py` | `ast.parse(..., feature_version)` ou compilação com 3.6 em todos os `.py`; busca por tokens proibidos (§2.1), `shell=True`, `os.system`, `eval(`, `exec(`, `pickle`, `XML(`, `x-html`, URLs `http(s)://` em `static/` e `views/` |
| `test_path_guard.py` | Caminho relativo, não normalizado, com `..` ou `\`; link simbólico aceito, com o arquivo real conferido, e ciclo de links (`NOT_FOUND`); pastas do sistema no caminho cadastrado e no real; prefixo irmão (`/usrx`, `/etcetera` aceitos); dentro de `log_dir`/`work_dir`/`exec_work_dir`; arquivo inexistente; diretório sem acesso (`NO_ACCESS`); diretório em vez de arquivo; arquivo gravável por grupo ou outros; dono indiferente; interpretador fora da allowlist (`validate_interpreter`) ou executável ausente, não executável ou nas pastas do SSS (`validate_executable`) |
| `test_sss_logging.py` | Log da aplicação (README §13): caminho por minuto, troca por tamanho com sufixo, retenção na subida e na troca, `agent_id` na linha, falhas da retenção como WARN, pastas `0750` em todos os níveis sob `umask 077` e arquivos `0640` |
| `test_log_paths.py` | Pasta do script (acento, espaço, `/`, maiúsculas, vazio, `app`); pasta do ambiente obrigatória e normalizada, `internal` reservado (CR-009); caminho do log de execução e do log da aplicação; sufixo na troca dentro do mesmo minuto; retenção só de pastas com formato de data; retenção dos logs de execução (F9.1a) pela data do caminho, com referência `date` ou `datetime`, `dry_run` sem remover, pasta `RUNNING` e `internal/` mantidas; pasta de entrada (CR-014) só com ambiente e script |
| CR-014 em `test_scheduler_claim.py`, `test_scheduler_init.py`, `test_executor.py`, `test_env_builder.py` e `test_platform.py` | `SSS_INPUT_DIR` em `input_dir/<ambiente>/<script>`, criada sob demanda com `0700` e mantida (conteúdo e modo) entre tickets; sem `input_dir`, sem a variável; script dentro de `input_dir` ou `output_dir` recusado com `SSS_DIR`; na subida, `input_dir` nas pastas do sistema ou inexistente recusado (código 13) e, fora de DEV, a pasta de cada ambiente conferida; campo `entrada` na especificação do helper; em DEV, criação pela plataforma recusando link |
| CR-016a em `test_db_schema.py`, `test_ddl_builder.py`, `test_repo_contract.py` e nas suítes dos repositórios e serviços | Tabelas, colunas, abreviações, sufixos e valores gravados em inglês, todos com até 30 caracteres; `sql_ident.physical`/`table`/`sequence` como única origem do nome físico; README §9.2 e §10 iguais ao registro (pelo nome físico); flags `'Y'`/`'N'`; `init_db` recusa criar o esquema com a `tbsss_controle` antiga no owner; bateria Oracle no esquema refeito pelo ciclo `02` → `01` → `99` |
| `test_purge.py` `[F9.1]` | Banco simulado com o SQL do `repo_oracle/purge.py`: `DELETE` literal em lotes até `rowcount = 0`, só tickets terminais, limite único pelo `db_now()`; concessão tomada, renovada por lote, liberada (dono **e** prazo, CR-008 R-27), negada (sem `DELETE` nem auditoria), vencida tomada e perdida no meio (lote desfeito, código 1); `PURGE` por tabela com 0 linhas (CR-008, R-16); `--export-audit` (CSV `0600`, apagado pelo id); `--dry-run` só com `SELECT`, um `db_now()`, sem trava e com aviso de estimativa; logs locais pela data do caminho (`.log.parcial`, vazias até o ambiente, `RUNNING` mantido, `internal/` e link intocados, fora de `log_dir` recusado, código 3); saída pelo helper por ambiente; trava local concorrente; códigos 0/1/2/3. Com `SSS_TEST_ORACLE=1`, purge real com a conta do owner só quando nada fora da fixture é elegível (pulado senão) |
| `test_params_compiler.py` | Regex no subconjunto seguro (aceitas e recusadas do README §6.2, com tempo de `fullmatch` limitado, inclusive os quantificadores limitados largos e o teto de 4 escolhas com ilimitado do CR-008 R-06); valor sensível com menos de 4 caracteres recusado; NUL e controle recusados também no snapshot; precedência; obrigatório ausente; `NAMED` com flag longa e curta; valor iniciado em `-`; `CHECKBOX`; `POSITIONAL` com opcional vazio intermediário; `NONE`; regex com `fullmatch`; rejeição de NUL e controle; `SELECT` fora de `options_json`; serialização determinística do snapshot |
| `test_cron_parser.py` | Listas, intervalos, passos, semântica OU de dia, dia 31 e fevereiro, ano bissexto, expressão sem ocorrência, rejeição de nomes e `L`/`W`/`#` |
| `test_recurrence.py` | `DAILY`, `WEEKLY`, `MONTHLY` (mês curto), `ONCE`, `end_date`, *misfire* `RUN_ONCE`/`SKIP`, `ocorrencia` coberta (CR-007), `SKIP` medido pela vencida mais recente e `cron_error` sem exceção (CR-008, R-19 e R-21), conclusão sem ticket, mensagem de CRON com `end_date`, datas sem microssegundos |
| `test_env_builder.py` `[F8.1]` | Ambiente sem herança de `os.environ`; rejeição de variáveis bloqueadas; passthrough; ausência de DSN; variáveis `SSS_*` da execução, do ambiente, do script, do log e do agente, ausentes quando sem valor (CR-010); `SSS_OUTPUT_DIR` só com `output_dir` (CR-012); nenhum nome antigo (português) definido, nem com todos os dados presentes (CR-015a) |
| `test_scheduler_ha.py` `[F8.4b]` | Desdobro (`modules/schedule_expansion.py`) com a agenda em memória e as funções reais de `recurrence`, `rbac` e `params_compiler`: ticket com a ocorrência, snapshot v5 e um `COMMIT` por regra; corrida e regra com outro agente; pausas pelo RBAC com a tradução única (R-33, e todo `rbac.Reason` aceito pela CK); `PRIORIDADE_REBAIXADA`; sobreposição sem mexer em `last_ticket_id` e `SKIP_OVERLAP_PRESO`; misfire `RUN_ONCE`, `SKIP` e R-21; perdidas em INFO e WARN pela vencida mais antiga; conclusão da `ONCE` com e sem ticket, por `end_date` e numa sobreposição; `INVALID_PARAM` e `CronError`; R-19 com e sem sobreposição; R-31 (`DUPLICATE_OCCURRENCE` avança numa nova transação); R-22 (3 falhas de banco, sucesso zera, `ValueError` pausa na 1ª, pausa que falha ignora a regra); paginação com 3 páginas e orçamento. No Oracle real: ticket e pausa `INVALID_PARAM` pelos repositórios. **F8.4c**, com o laço real e scripts `/bin/sh`: fence no limiar e não antes, grupo encerrado, claims suspensos no cerco e retomados depois do heartbeat, `FENCED` na recuperação, R-12 (resultado local prevalece), 30 execuções encerradas de uma vez sem bloquear; `NODE_OFFLINE` dos tickets de outro agente com INFO, nunca com o próprio heartbeat velho, suspenso por `SALTO_RELOGIO` no heartbeat e detectado na própria transação (R-10). **F8.4d:** `DRAIN` pelo `.stop` (script termina normalmente, heartbeat mantido, sem claim, saída gravada, `.stop` removido, saída 0), `DRAIN` com `shutdown_grace_s` vencido vira `SHUTDOWN`, `TERMINATE` pela flag, e SIGTERM/SIGINT só acionam a flag |
| `test_scheduler_schedules.py` `[F8.4a]` | Repositório do desdobro (README §7.5) com conexão roteirizada: paginação e `SKIP LOCKED`, reserva sem `updated_*` e ticket com `scheduled_at` da ocorrência e `created_by` do agente, `DuplicateOccurrence` só em `ix_tck_ocor`, conclusões que mantêm `next_run_at`, avanço sem ticket (R-05), pausa só de regra ativa com `SCHEDULE_PAUSE`, `cron_error` com e sem ticket, `INTERNAL_ERROR`, binds de data com `TIPO_DATE` e sem microssegundos, nenhuma operação com `COMMIT`/`ROLLBACK`; `mark_node_offline` em duas etapas sem os próprios tickets e abortado por salto de relógio, e `finalize_fenced`. No Oracle real: o teste obrigatório de microssegundos, a `ONCE` concluída com a data mantida, pausas e avanço, nó offline e `FENCED` |
| `test_scheduler_queue.py` `[F8.3a; CR-013]` | Repositório do daemon com conexão roteirizada: SQL literal, binds gerados por contagem, `rowcount` e transações do claim (o `LOCK` devolve o código ORA, e o laço registra WARN sem stack trace, F9.1d), heartbeat, devolução e finalização; `candidates` em três leituras (catálogo do agente, `RUNNING` por par e a janela por ambiente × prioridade em `ix_tbsss_tck_queue`, sem `SELECT *`, listas `IN` de até 900); no Oracle real, a ordem da janela igual à ordenação completa (prioridades, misfire, teto, interpretador e agendamento futuro) |
| `test_ha_real_agents.py` `[F8.4e]` | Dois agentes reais contra o Oracle com `SSS_TEST_ORACLE=1` (fixture do F8.3d, tempos de fencing reduzidos dentro de I1 a I4): regra CRON `* * * * *` por 3 minutos gera exatamente 1 ticket por minuto, sem duplicata entre os agentes; `kill -9` no agente dono durante uma execução leva o outro a marcar `NODE_OFFLINE` depois de `node_offline_timeout_s`, e o filho que sobreviveu é encerrado pelo startup check da religação; nenhum resíduo, inclusive os tickets gerados pelo desdobro |
| `test_agents_concurrency.py` `[F8.3d]` | Dois agentes reais (`run_scheduler.py --config`) contra o Oracle com `SSS_TEST_ORACLE=1`, só com fixtures próprias: 10 tickets de um script com teto 2 (nunca mais de 2 `RUNNING`, por polling no banco), todos `SUCCESS`, cada ticket executado uma vez pelo agente dono, saída `AVAILABLE` com o zip do próprio ticket e a pasta removida, cancelamento pela web encerrado pelo agente dono, heartbeat e `critical_config` iguais, parada pelo `.stop` com saída 0 e `STOPPED`, nenhum processo órfão e nenhum resíduo no banco |
| `test_scheduler_output.py` `[CR-012]` | Repositório da saída do agente: inclusão só com posse do ticket, reinício da própria gravação, partes com offset esperado e parte já gravada reconhecida, divergência recusada, `AVAILABLE` só com o tamanho conferido no banco, `EXCEEDED`/`FAILED` sem conteúdo, startup check pelo índice de função, owner e prefixo parametrizados; leitura pela web (`output_get`, `output_read`) e o BLOB nos três drivers (Thin, Thick e cx_Oracle, cada um num processo) no Oracle real com `SSS_TEST_ORACLE=1` |
| `test_output_phase.py` `[CR-012]` | Fase de saída do agente com banco mock: pasta vazia sem linha; `EXCEEDED` por arquivos e por bytes com a linha `[SSS]` e a pasta mantida; `AVAILABLE` com envio em partes e pasta removida; prazo do `pack`; `OWNERSHIP_LOST`; erro de banco refeito; abandono no `SHUTDOWN`; `WRITING` vira `FAILED` no startup check; resultado do ticket nunca alterado; `SSS_OUTPUT_DIR` só com `output_dir` |
| `test_ticket_service.py` `[CR-012]` | Quadro Saída por situação, com o agente onde os arquivos ficaram; download só com permissão de ler o log e só `AVAILABLE`, em partes e com os cabeçalhos de anexo |
| `test_masking.py` | Mascaramento de segredos, connect string e valores sensíveis, inclusive quando cortados entre blocos |
| `test_rbac.py` | Matriz de `can_execute` (admin, perfil inativo, sem homologação, sem `EXEC_SCRIPT`); proteção do último admin (mock); tradução de todo `rbac.Reason` por `pause_reason_for` para um valor de `ck_tbsss_sch_pause` (CR-008, R-33) |
| `test_sss_helper.py` `[F8.0]` | Helper de execução (CR-007, D1): uso inválido recusado (código 2); especificação inválida; `term`/`kill` com identidade divergente recusados (código 3) e com grupo vazio aceitos; `clean` e `stop-ticket` com `base_dir` validada e sem seguir links; `run` criando a pasta de saída (`output`) sem seguir links, `pack` (zip sem links nem itens especiais, código 6 vazio, código 7 ao passar de arquivos ou bytes, sem zip parcial), `clean-output` e `purge-output` (CR-012), inclusive o modo `count` do `--dry-run` do purge (F9.1a); `stop-ticket` encerrando só processos do próprio usuário cujo diretório atual está na pasta do ticket e com código 5 sem meio de identificar (CR-008, R-01 e R-36); `run` em DEV com o próprio usuário (sem `sudo`) executando um script de teste; `run` com `input` (CR-014) criando a pasta do script com `0700`, mantendo a existente e o conteúdo entre tickets, e recusando relativo com mais de um nível, fora do formato ou com link (código 2) |
| `test_package.py` `[F9.1]` | Árvore falsa do web2py: pacote gerado; `SHA256SUMS` de fora confere com o `tar.gz` e o de dentro com cada arquivo; tar reprodutível; `routes.py` gerado com a aplicação padrão; `bin/sss-helper` presente e `0755`; pastas de runtime do web2py (`applications/`, `deposit/`, `logs/`, `site-packages/` dentro da aplicação), DEV, testes, `instance/config.ini` e testes do upstream ausentes; runtime vazias presentes; recusa, sem gravar nada e sem imprimir o valor, com `secrets.cfg`, senha ou `cookie_key` fora do placeholder (inclusive em `.cfg.example`), `CHANGE_ME` fora do `secrets.cfg.example`, bytecode, link simbólico, outra aplicação e helper ausente; `CHANGE_ME` aceito no exemplo; nenhum arquivo que vai no pacote importa no nível do módulo o que fica fora dele (`repo_fake`, `dev`, auxiliares de teste; F9.1d) |
| `test_deployment_doc.py` `[F9.1]` | `docs/DEPLOYMENT.md`: todo `bin/…`, `scripts/….py` e `docs/sql/…` citado existe; toda referência interna `§n` do corpo aponta para uma seção existente; nenhum procedimento do FAKE no corpo (o Apêndice B, histórico, fica de fora) |
| `test_launchers.py` `[F9.1]` | `bin/sss-web.sh`, `bin/sss-scheduler.sh` e `bin/sss-stop.sh` numa raiz falsa, com `python3`, `id` e `ldconfig` falsos: sintaxe (`bash -n`), recusa de root, as três formas do web e só a linha do daemon no scheduler (outro comando: código 2), `exec` a partir da raiz com `umask 077`, `LD_LIBRARY_PATH` só sem o Instant Client no `ldconfig`, `TZ` e locale; `.stop` `0600` no `work_dir` do `config.ini` e recusa de configuração inválida (código 2) |
| `test_health.py` `[F9.1]` | `scripts/health.py` com repositório simulado: cada verificação do README §13 no limiar e fora dele, um único `db_now()`, o código Nagios agregado (o pior vence) e a saída (resumo com dados de desempenho e uma linha por problema, críticos primeiro); UNKNOWN em configuração, segredos, conexão e erro de banco; segredos do papel `monitor` sem carregar nem mascarar `[oracle]`, `[purge]` e `[environment:*]` (CR-008, E3); fila sem atendente pelo interpretador do cadastro (R-15); `PURGE` com 0 linhas conta como execução (R-16); SQL do `repo_oracle/health.py` sem LOB e o mesmo da tela de agentes. Com `SSS_TEST_ORACLE=1`, as consultas no Oracle real pela conta do owner (só leitura) e o `EXPLAIN PLAN` sem `TABLE ACCESS FULL` em tickets e auditoria |
| `test_executor.py` `[F8.1]` | Spawn real de script de teste (`/bin/sh`) em diretório temporário; log no caminho do CR-005, com o renome para `ticket_<id>_<PID>.log`; saída em arquivo sem PIPE; geração de mais de 1 MB de saída sem travar; timeout; encerramento escalonado matando também o neto; conversão de `returncode` negativo |
| `test_platform.py` `[F8.0]` | Encerramento escalonado sem bloquear (máquina de estados), grupo encerrado mesmo após a saída do processo principal (netos), `.sss_spawn`/`.sss_proc`/`.sss_result` com escrita atômica (CR-008, R-01), `validate_execution` com dublê de `sudo`, grupo e encerramento escalonado, identidade do processo (`starttime`) contra PID reciclado, lock de instância, recusa de root, dono e permissão de segredos e do caminho do script |
| `test_sql_oracle11g.py` `[F7.3]` | Varredura de `repo_oracle/` e `scripts/init_db.py`: nenhuma sintaxe 12c+ (§4.3); `FOR UPDATE` sempre com `WAIT n` (n ≤ 5); nenhum `SELECT *` |
| `test_ddl_builder.py` (seed do `init_db`) | `_run_seed` com conexão simulada: termina sem rollback e grava cada ambiente padrão antes de ligá-lo aos perfis (matriz perfil × ambiente pelo nome) |
| `test_seed_fake.py` | Seed FAKE coerente com as regras (README §2.5), com a linha de `tbsss_control` na versão do código: funcionalidades com os nomes do README, nenhum parâmetro de credencial, prioridade 1 só para admin, `created_at` nunca no futuro, colunas de registro coerentes com o README §10 (CR-006), snapshot e respostas compilados contra o script, agendamentos no minuto exato e alinhados à regra |
| `test_ui_helpers.py` | Catálogo de mensagens em duas partes, nomes simples de situação e de motivo, frase e etapas do ticket, tempo em linguagem simples, nome do ator no quadro Registro (CR-006) e o mascaramento do ator para quem não tem `VIEW_AUDIT` (CR-007, D6), inclusive solicitante e responsável por `visible_actor` (CR-008, E5) |
| `test_config.py` | Tipos e faixas de toda chave; `table_prefix` só minúsculas; `agent_id` reservados (`init_db`, `seed`, `purge`); invariantes I1 a I4; `exec_users` cobrindo os ambientes fora de DEV; `audit_retention_days` ≥ 365 e ≥ `ticket_retention_days`; `env_passthrough` sem variáveis bloqueadas nem chaves fixas; segredos por papel (CR-007; papel `monitor`, CR-008, que ignora as seções dos outros papéis e recusa `[web]`, F9.1b); `cron_horizon_days` ≥ 1.461, `session_max_hours`, `log_dir_min_free_mb` e `[oracle] user` diferente do `owner` fora de DEV (CR-008) ; chaves removidas recusadas com "apague a linha" (CR-011); `input_dir` (CR-014) opcional e sem sobrepor `log_dir`, `work_dir`, `exec_work_dir` e `output_dir`; chaves renomeadas (CR-015a) recusadas com o nome novo |
| `test_auth_service.py` | Login, revalidação e sessão (README §4.2), inclusive a revogação por `session_epoch` (logout, troca e redefinição de senha, desativação, troca de perfil) e a vida máxima `session_max_hours` (CR-008, E2); a mensagem de bloqueio de "Minha senha" (`lock_message`) e os nomes de `auth_service` usados pelos controllers |
| `test_admin_users_service.py`, `test_admin_profiles_service.py` | CRUD, autoproteções e o último administrador; **E1 do CR-008:** quem não é administrador não inclui nem move ninguém para perfil administrativo, não redefine senha, não desbloqueia, não desativa nem troca o perfil de um administrador, não marca nem desmarca `is_admin`, não altera perfil administrativo nem a matriz do próprio perfil, sem gravar nem auditar |
| `test_admin_scripts_service.py` | Cadastro e homologação de scripts; no nó web só o formato e as pastas do sistema são conferidos, sem conferir o arquivo nem calcular hash, e um link para pasta do sistema é recusado (CR-011) |
| CR-017 em `test_admin_environments_service.py`, `test_ticket_service.py`, `test_ui_helpers.py`, `test_permissions_service.py`, `test_schedules_service.py`, `test_admin_scripts_service.py` e `test_catalog_service.py` | `is_production` marcado e desmarcado no cadastro, com auditoria; o destaque de produção do disparo segue o cadastro e não o nome; item "Tickets" do menu com `EXEC_SCRIPT` ou `VIEW_LOGS`; um só item para rodar ("Rodar um script", `tickets/catalog`), sem "Disparar Scripts" no menu, e "O que eu posso fazer" levando `EXEC_SCRIPT` aos cartões (017b); a prévia do comando pelo `trigger_summary`, o mesmo do modal; em `test_schedules_service.py`, a nova regra com a escolha em lista e o salto com um ambiente só, e no menu os itens Agenda e Agentes na Operação (017c); em `test_admin_scripts_service.py`, o quadro "Quem pode rodar" (pronto, só administradores, sem homologação, script desativado, sem cálculo injetado), e em `test_catalog_service.py`, o atalho Agendar só com `MANAGE_SCHEDULES` (017d) |
| CR-018 em `test_rbac.py`, `test_ticket_service.py`, `test_schedules_service.py`, `test_admin_parameters_service.py` e `test_admin_scripts_service.py` | Cancelar ticket de terceiro só com `CANCEL_TICKET` e `VIEW_LOGS`; filtro por solicitante ignorado para quem não vê logins (o próprio login continua); regras em risco depois de tirar uma opção do parâmetro (`rules_at_risk`, `impact_warning`); aviso do formulário de parâmetro e depois de salvar os vínculos; tickets na fila avisados ao trocar o arquivo do script (018a) |
| `test_catalog_service.py` | Rodar um script (cartões) e histórico: mesmo escopo da lista de tickets (com e sem `VIEW_LOGS`), script fora das rotinas dá 404, contrato sem LOB e limitado, números do resumo iguais aos do gráfico e geometria do gráfico |
| `test_color_contrast.py` | Todo par texto/fundo dos tokens de `sss.css` com contraste WCAG AA (≥ 4,5:1), nos modos claro e escuro |
| `test_db_conn.py` `[F7.0]` | Com módulos falsos de driver: cadeia `auto` Thin → Thick → cx_Oracle, parada em erro de autenticação, valores forçados, senha fora de argv/ambiente/log, mapa de erros por driver e modo, inclusive *call timeout* e erros de failover (CR-007, R-12), reconexão sem `sleep`; cálculo do orçamento de abertura do DSN descritor (CR-008, R-17); sondagem com a conta do papel que conecta (`--user` no argv, senha só no stdin; o `connect` do papel `monitor` sonda com a conta do monitor, F9.1d); primeira conexão em INFO (`Conectando`/`Conexao estabelecida`) e o WARN `Tentando reconexao` só nas reconexões (F9.1d) |

5. Cada correção de defeito acompanha um teste de regressão.
6. **Homologação real no DEV:** `dev/homologation/tools/capture_evidence.js` executa os casos de teste do manual no navegador contra o DEV (Oracle e agente reais) e confere o resultado esperado de cada passo na própria página; `build_evidence_docx.py` gera o documento de evidências (`docs/homologation/`). Use-o depois de mudanças de tela ou de contrato JavaScript × servidor, que os testes `unittest` não exercitam (o JavaScript não roda neles).

---

## 8. Checklist Obrigatório antes de Entregar

- [ ] Nenhum recurso de Python posterior à 3.6.0 nem módulo removido nas versões novas (§2.1).
- [ ] Nenhuma dependência nova; o driver só é importado em `db_conn.py` e `probe_driver.py`.
- [ ] SQL: só em `repo_oracle/` e `init_db.py`; Oracle 11gR2 sem sintaxe 12c+; apenas binds e identificadores via `sql_ident`; `rowcount` checado em toda transição.
- [ ] Toda transação com `COMMIT`/`ROLLBACK` explícitos; lock de linha com `FOR UPDATE WAIT n` (n ≤ 5).
- [ ] Nenhum identificador novo acima de 30 caracteres; registro de identificadores atualizado.
- [ ] Processos: primitivas de SO só em `modules/os_platform/` (somente POSIX), exceto `resource.setrlimit` em `run`, `os.killpg` em `term`/`kill`, leitura de `/proc/<pid>/stat` em `_identity` e `/proc/<pid>/cwd`/`pwdx` em `stop-ticket` no helper; pasta de saída só pelo helper e por `log_paths.output_dir`, sem zip parcial e sem alterar o resultado do ticket (CR-012); allowlist lógica, `path_guard`, `env_builder`, sem PIPE e encerramento escalonado; caminhos de log só por `log_paths`.
- [ ] Web: guarda de login/RBAC, CSRF em POST, saída escapada, sem `XML()` com dado.
- [ ] Entrada recusada (nunca truncada) acima do limite; nenhum valor sensível, nem derivado, no HTML.
- [ ] Mensagens ao usuário pelo catálogo de `ui_helpers`, em duas partes; telas de consulta só com `GET`, sem gravação nem auditoria.
- [ ] Auditoria gravada pelo repositório na mesma operação da ação (`audit=`).
- [ ] Colunas de registro (§4.15): `created_*` em todo `INSERT`, `updated_*` só em alteração de negócio, ator obrigatório.
- [ ] Mudança de esquema com `SCHEMA_VERSION` incrementada e migração no mesmo pacote (§4.16); privilégio novo na tabela de GRANTs por papel (§4.17).
- [ ] Daemon: nenhuma espera dentro de operação, fence conferido depois de cada chamada ao banco, encerramento por máquina de estados, estado local antes do banco (§3.2, §6; README §8.1).
- [ ] Script executado só pelo helper com o usuário de execução fora de DEV; regex de parâmetro só no subconjunto seguro (§3.2, §3.4).
- [ ] Logs sem segredos/PII; todo `except` com log (salvo o fluxo previsto de SO comentado, §6).
- [ ] Nome técnico novo em inglês; conteúdo, comentários e dados em português (README §2.8, CR-016).
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
