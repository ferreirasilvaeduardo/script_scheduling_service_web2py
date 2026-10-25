# Script Scheduling Service (SSS) — Regras de Desenvolvimento (AGENTS.md)

Regras **obrigatórias e inegociáveis** para qualquer agente de IA ou desenvolvedor atuando neste projeto.

**Precedência:** o `README.md` é a autoridade de negócio, dados e algoritmos. Este documento é a autoridade de **como** codificar. Se uma regra deste documento conflitar com o README, **pare e reporte** no campo "Observações" do relatório (§9), sem escolher uma das versões por conta própria.

---

## 1. Postura do Agente

* Atue como **Engenheiro de Software Sênior e DBA Oracle**, com foco em Python 3.6+ (biblioteca padrão, sem framework web desde o CR-021), Oracle 11gR2+ e agente **somente POSIX** (Linux e Unix — `docs/architecture/CR-005-posix-free-path-and-logs.md`, que revoga a parte Windows do CR-001). Banco **somente Oracle**, com SQL 11gR2 e driver adaptativo (`docs/architecture/CR-002-single-oracle-and-adaptive-driver.md`).
* **Escopo:**
  * Implemente **somente** o subitem solicitado.
  * Não refatore, renomeie nem "melhore" código fora do escopo.
* **Fail-fast documental:** se o README não especifica um comportamento necessário, **não invente**. Pare, liste a lacuna e peça decisão.
* **Estilo:**
  * Sem código didático e sem comentários redundantes. Comente apenas o "porquê" não óbvio (invariantes, ordem de locks, armadilhas do 11g).
  * Docstrings curtas em funções públicas de `src/sss/`.
  * **Nomes em inglês (CR-016, README §2.8):** objetos do banco, valores gravados, arquivos, pastas, módulos, funções, classes, variáveis, chaves, configuração, variáveis de ambiente, opções de linha de comando e rotas têm nome em inglês. Ficam em português o conteúdo (texto de tela, mensagens, logs legíveis e documentação), os comentários e docstrings e os dados cadastrados. Código novo nasce em inglês. A tradução do legado está encerrada (2026-10-22, README §2.8): os nomes em português que restaram ficam como estão e só mudam junto com uma alteração funcional do mesmo trecho. Rota renomeada não ganha redirecionamento do nome antigo (CR-016d, D22), nem atributo de sessão ou campo de formulário renomeado ganha leitura do nome antigo (D26 a D28). Nome de campo que o JavaScript envia muda junto com o controller que o lê, e chave JSON que o JavaScript lê muda junto com o servidor que a devolve (o percurso confere esse contrato, CR-016d d2b). Variável de tela, entrada de componente e chave de dicionário que vai do serviço ou do repositório para a tela também são em inglês (CR-016d d2c), assim como classe e variável CSS, id HTML, atributo `data-*`, componente JS (`data-component`) e identificador JS (CR-016d d3a), e função, constante, parâmetro e variável local da camada web: `ui_helpers`, `ui_menu`, `models/`, controllers e locais dos templates (CR-016d d3b). Campo oculto de modal (`hidden_fields`) também é contrato com o controller e muda junto.
* **Estrutura em migração (CR-022b, `docs/architecture/CR-022-standard-structure.md` §2b):** o código sai de `modules/`, `webapp/`, `controllers/`, `views/` e `static/` para o pacote `src/sss/` (subpacotes `config`, `core`, `platform`, `persistence`, `ui`, `services`, `scheduler`, `web`, `cli`), os testes já saíram de `scripts/` para `tests/` (022b1, §7 item 1) e o `package.py` já está em `tools/` (022b2, ferramenta de build, fora do pacote). Já estão em `src/sss/`: `config` (`sss_config`, `app_context`, `sss_logging`, `log_paths`) e `core` (`cron_parser`, `recurrence`, `params_compiler`, `masking`, `rbac`, `security`, `sql_ident`) (022b3), `platform` (`os_platform`, `path_guard`) e `persistence` (`db_conn`, `ddl_builder`, `repo_errors`, `repo_factory`, `contracts/repo_*`, e os pacotes `oracle` e `fake`, antes `repo_oracle` e `repo_fake`) (022b4), `ui` (`ui_helpers`, `ui_menu`) e `services` (`admin_crud` e os `*_service`) (022b5) e `scheduler` (`scheduler_loop`, `executor`, `env_builder`, `log_pump`, `input_phase`, `output_phase`, `schedule_expansion`) (022b6) e `web` (`framework`, antes `modules/web`; `app`, antes `webapp`; `controllers`; `templates`, antes `views`; `static`) (022b7) e `cli` (o código de `scripts/`, que ficou só com os involucros; sai o `modules/`) (022b8). Os caminhos citados neste documento são os **atuais** e mudam no passo que move cada camada. Enquanto o CR-022b estiver aberto:
  * módulo de `src/sss/` só é importado pelo nome qualificado, `from sss.<camada> import <módulo>` ou `from sss.<camada>.<módulo> import <nome>`, nunca pelo nome curto (`import masking`), nem em template (`{{import ...}}`): carregado com dois nomes, ele teria classes de exceção duplicadas (`tests/architecture/test_package_layout.py`). Dublê de teste de um módulo de `src/sss/` vai no atributo do pacote (`mock.patch("sss.config.sss_config", ...)`), porque `from sss.config import sss_config` lê o atributo antes de `sys.modules`;
  * um módulo só se move junto com a reescrita de **todos** os seus importadores, no mesmo commit;
  * as camadas seguem uma ordem (CR-022 §2b), e uma camada só importa as que estão **abaixo** dela: `platform` (base, só biblioteca padrão) < `core` < `config` < `persistence` < `ui` < `services` < `web`; o `scheduler` fica acima de `persistence` e não importa `ui`, `services` nem `web`; o `cli` fica no topo. Import dentro de função conta igual (o `sss_config` usa `masking` e `os_platform` assim);
  * os comandos de operação dos servidores (`scripts/run_web.py`, `scripts/run_scheduler.py`, `scripts/health.py`, `scripts/purge.py`, `scripts/init_db.py`) não mudam.
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

**Única exceção ao `exec` (CR-021, D2):** `src/sss/web/framework/template.py`, só para o código gerado de arquivos dentro de `src/sss/web/templates/` (caminho real conferido; `include`/`extend` só por nome literal). `exec()` não aparece em nenhum outro arquivo, e `compile()` só nos testes para conferir sintaxe (`test_py36_compat.py`).

**Compatibilidade nas duas pontas:**

* **Mínimo (3.6.0):** não use nada que tenha surgido em versões de correção posteriores (3.6.1 em diante). Por exemplo, `typing.AsyncGenerator` só existe a partir da 3.6.1 e `typing.NoReturn` a partir da 3.6.2 (os dois são recusados pelo `test_py36_compat`).
* **Máximo (3.13):** é proibido depender de módulos removidos ou depreciados nas versões novas (`cgi`, `cgitb`, `imp`, `asyncore`, `asynchat`, `distutils`, `smtpd`, `telnetlib`, `pipes`, `crypt`).

**Atenção a comportamentos:**

* A ordem de inserção de `dict` só é garantia de linguagem a partir do 3.7. Quando a ordem importar (montagem do argv, serialização), use `collections.OrderedDict` ou ordene explicitamente.
* `subprocess` sem `text=`: decodifique bytes explicitamente com `.decode('utf-8', 'replace')`.

### 2.2 Bibliotecas

* Proibido `pip install` e qualquer dependência nova.
* **Proibidos:** Celery, Redis, APScheduler, croniter, Flask, FastAPI, Django, Bottle, SQLAlchemy, Peewee, requests, web2py (removido no CR-021f, inclusive DAL, auth, sessão e `gluon.scheduler`) e qualquer outro framework web.
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
  * Todo acesso ao driver passa por `src/sss/persistence/db_conn.py` (e pela sondagem `scripts/probe_driver.py`). Nenhum outro módulo pode importar `oracledb` ou `cx_Oracle`.
* **O web2py não roda mais a aplicação (CR-021e):** o servidor é o núcleo próprio (`src/sss/web/framework/`), ligado pela camada `src/sss/web/app/` e iniciado por `scripts/run_web.py`. Nenhum `.py` da aplicação, dos testes, de `dev/` ou do `bin/` importa `gluon` (`test_app_context`, CR-021f1); as saídas do web2py que os testes de paridade conferem (URL, campo CSRF, template sintético) ficaram gravadas nos próprios testes.

### 2.3 Frontend hermético

* Proibido CDN, Google Fonts, `@import` remoto e qualquer URL externa em HTML, CSS ou JS.
* **Ativos permitidos:**
  * `src/sss/web/static/bootstrap/` (5.3.8)
  * `src/sss/web/static/js/app/*.js`, com o `dom.js` carregado antes dos demais
  * `src/sss/web/static/css/*.css` (estilos próprios, sobre o Bootstrap)
  * `src/sss/web/static/img/` (inclui sprite SVG local de ícones)
  * `src/sss/web/static/fonts/`
* **Proibidos:**
  * `<script>` inline, `onclick=` e atributos de evento inline;
  * `style=` inline com dado dinâmico;
  * `eval` e `new Function`;
  * `innerHTML`, `outerHTML`, `insertAdjacentHTML` e `document.write` em `src/sss/web/static/js/app/` (texto só por `textContent`; marcação repetida vem de um `<template>` do servidor, copiado por `SSS.dom.clone`);
  * framework de JavaScript (o Alpine.js saiu no CR-021) e qualquer sintaxe dele nas views (`x-*`, `@evento=`, `:atributo=`), conferido por `tests/architecture/test_frontend_components.py`.
* **Componentes sem framework (CR-021, D7):**
  * a raiz tem `data-component="<nome>"` e a fábrica é registrada uma vez com `SSS.component('<nome>', function (root) { ... })` em `src/sss/web/static/js/app/`; o `dom.js` monta cada raiz uma vez no `DOMContentLoaded`;
  * eventos só por delegação, `SSS.dom.on(root, '<evento>', '<ação>', fn)` com `data-action="<ação>"` no elemento; elementos por `data-ref` (`SSS.dom.ref`), que não enxerga os de um componente aninhado;
  * o estado fica no JavaScript; mostrar e esconder é o atributo `hidden` (`SSS.dom.show`), e o estado inicial escondido sai do servidor com `hidden` (sem `x-cloak`);
  * dentro de um item copiado de um `<template>`, as partes são achadas por `data-part` (o `data-ref` é do componente);
  * lista de textos simples: `SSS.dom.fillList(lista, textos)`;
  * campo que aparece conforme uma escolha: `data-types="<valores>"` no bloco, sem expressão (os valores são conferidos contra o serviço em `test_frontend_components.py`);
  * lista dinâmica: o estado é um array e a lista é redesenhada a partir de um `<template>` do servidor só quando muda a estrutura (incluir, mover, remover). Digitar ou marcar só atualiza o estado, para não tirar o foco do campo; quem redesenha devolve o foco a um elemento equivalente;
  * modal: só por `SSS.modal({modal, backdrop, initialFocus, returnFocus})` (`components.js`), que fecha por Esc e por clique no fundo. O componente dono do modal o controla; nenhum componente lê o estado de outro;
  * fragmento `.load` (lista de tickets, painel de agentes): troca só por `SSS.dom.replaceFragment`, com o HTML renderizado e escapado pelo servidor;
  * todo `data-component` das views tem registro, e todo registro é usado (`tests/architecture/test_frontend_components.py`).
* Toda requisição `fetch` que altera estado envia o cabeçalho `X-CSRF-Token`.
* **Gráficos** (README §5.8):
  * SVG gerado no servidor (ex.: `ui_helpers.stacked_bars`), sem biblioteca de gráficos e sem `style=` inline;
  * cor só por classe CSS, com tokens em `src/sss/web/static/css/sss.css` (`--sss-graf-*`) e valores próprios para o modo escuro;
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
* **Identificadores dinâmicos** (owner, prefixo) só entram no SQL via `src/sss/core/sql_ident.py`, que os valida antes do uso:
  * `owner`: `^[A-Za-z][A-Za-z0-9_]{0,29}$`
  * `table_prefix`: `^[a-z][a-z0-9_]{0,7}$` (começa com letra minúscula; CR-007, R-31)
  * Nome final do objeto: validado contra o registro de identificadores e com `len <= 30`.
* **Listas `IN`:** os placeholders (`:amb0, :amb1, ...`) são gerados pelo código com contagem controlada, e os valores sempre vão como binds.
* **Binds de data** comparados a colunas de data são declarados pelo `db_conn` com o tipo de data do driver (`setinputsizes` no Oracle), sem microssegundos (README §7.5).
* Mensagens de erro exibidas ao usuário **nunca** incluem o texto do ORA-/DPY-/DPI-, SQL ou stack trace. Esses detalhes vão apenas para o log.

### 3.2 Execução de processos

* **Proibido:** `shell=True`, `os.system`, `os.popen`, `subprocess.getoutput`/`getstatusoutput`, `eval`, `exec`, `compile` sobre dado externo, `pickle`/`marshal`/`shelve` em dado externo, `yaml.load`, `__import__` dinâmico e `importlib` com nome vindo de dado.
* **Camada de plataforma:** toda primitiva dependente do sistema operacional (spawn, grupo e encerramento de processos, limites, identidade do processo, lock de instância, checagem de dono e permissão, sinais e parada) fica **somente** em `src/sss/platform/os_platform/` (`posix.py`, para Linux e Unix; CR-005: Windows não é suportado). Fora dela é proibido `os.killpg`, `os.setsid`, `resource`, `fcntl`, `/proc` e `sys.platform` (README §8.0). Também é proibido `ctypes`, `msvcrt` ou qualquer API Windows em todo o projeto, inclusive em `os_platform/` (README §8.0: onde a identidade do processo não puder ser lida sem `ctypes`, `process_identity` devolve `None`).
  * **Exceção isolada do helper (F8.0):** o fonte `bin/sss-helper`, instalado como `/opt/sss/bin/sss-helper`, pode usar `resource.setrlimit` somente em `run`, `os.killpg` somente em `term`/`kill`, ler `/proc/<pid>/stat` (identidade do líder do grupo, README §8.0) somente na função `_identity` usada por `term`/`kill`, e consultar `/proc/<pid>/cwd` ou invocar `pwdx` por caminho absoluto somente em `stop-ticket`. O helper só pode atuar sobre processos do próprio usuário de execução; `stop-ticket` compara o cwd com a pasta exata do ticket. Nenhuma outra primitiva listada nesta regra é permitida nele; `ctypes` e `msvcrt` continuam proibidos em todo o projeto.
  * **Estado provisório até o F8.0:** a camada `os_platform/` ainda não existe. Hoje a checagem de dono e permissão do script fica em `path_guard` e a do `secrets.cfg` em `sss_config`; o F8.0 as move para `os_platform/` sem mudar a regra.
* **Spawn único permitido** (`os_platform.start_process`, chamado só por `src/sss/scheduler/executor.py`):
  * **Fora de DEV (CR-007, D1):** o script roda com o **usuário de execução** do ambiente, nunca com o usuário do agente: `subprocess.Popen(['/usr/bin/sudo', '-n', '-u', user, '--', '/opt/sss/bin/sss-helper', 'run'], shell=False, start_new_session=True, close_fds=True, stdin=PIPE, stdout=log_fd, stderr=STDOUT, env=<mínimo>)`, com a especificação (argv, env, limites) pela entrada padrão (README §8.0, §8.4). O helper é o **único** caminho para agir como o usuário de execução (`run`, `term`, `kill`, `clean`, `stop-ticket` e, no CR-012, `pack`, `clean-output` e `purge-output`); é proibido chamar `sudo` para qualquer outro comando.
  * **Em DEV sem usuário de execução:** `subprocess.Popen(argv, shell=False, start_new_session=True, close_fds=True, stdin=DEVNULL, stdout=log_fd, stderr=STDOUT, cwd=..., env=clean_env, preexec_fn=_child_limits)`. `_child_limits` pode **somente** chamar `os.umask` e `resource.setrlimit`. É proibido criar threads no daemon, porque `preexec_fn` não é thread-safe.
  * Qualquer exceção no spawn vira `SPAWN_ERROR` (não só `OSError`).
  * **Proibido** `stdout=subprocess.PIPE` ou `stderr=subprocess.PIPE` para scripts executados. A saída vai sempre para arquivo.
* **Pasta de saída do script (CR-012, README §8.13):**
  * criada, empacotada, limpa e purgada **só** pelos subcomandos do helper (`run` com `saida`, `pack`, `clean-output`, `purge-output`), chamados por `platform` (fora de DEV pelo `sudo`; em DEV, a cópia do pacote `bin/sss-helper` com o próprio usuário). O agente nunca lê nem apaga a pasta por conta própria; a única exceção é `os_platform.create_output_dir`, em DEV sem usuário de execução;
  * caminho só por `log_paths.output_dir` (base `output_dir/<ambiente>` e relativo `<script>/AAAA/MM/DD/HH/MI/ticket_<id>`), conferido de novo pelo helper, que nunca segue link;
  * o zip só tem arquivos regulares; acima de `output_max_files` ou `output_max_bytes` **não há zip parcial**: a linha fica `EXCEEDED` e a pasta fica no disco;
  * a fase de saída (`src/sss/scheduler/output_phase.py`) **nunca** altera o resultado do ticket; é máquina de estados do laço, sem espera, em duas etapas: empacotar depois do grupo encerrado e antes do flush final (`poll()` do `pack`, prazo de 120 s; a linha `[SSS]` vai para o log local) e gravar depois da finalização, fora do mapa de execuções (até 4 partes de 1 MiB por volta);
  * toda gravação em `tbsss_ticket_output` exige a posse (`agent_id = :agent_id`), pelo `src/sss/persistence/oracle/scheduler_output`, e é proibido gravar o conteúdo da saída em qualquer log.
* **Tela de Entrada (CR-020d, README §5.10):**
  * `UPLOAD_INPUT` com ambiente **e** script no perfil (admin: todos); fora disso, 404;
  * o limite de tamanho do POST fica em `src/sss/web/app/security.py` (`_check_size`), **antes** de qualquer leitura de `request.post_vars` (o teste confere a ordem); nome e subpasta com a regra do helper `put-input`;
  * a pasta mostrada é sempre o retrato dos agentes; a web nunca acessa o disco do agente.
* **Tela de Saídas (CR-020a, README §5.9):**
  * lê só do banco (`RepoTickets.output_summary`, `output_tickets` e `output_read`); o web nunca acessa a pasta de saída do agente;
  * o zip é lido do BLOB por `output_browse_service.BlobReader` (blocos de 256 KiB, `seek`), nunca carregado inteiro; o arquivo avulso é pedido pelo nome **exato** do índice do zip, nunca por caminho montado;
  * `DOWNLOAD_OUTPUT` e o ambiente no perfil; fora do escopo, sem saída `AVAILABLE` ou parâmetro inválido é 404;
  * todo download grava `OUTPUT_DOWNLOAD` por `RepoAudit.register` antes do envio (leitura auditada, como `AUDIT_EXPORT`); navegar não audita.
* **Entrada pela tela (CR-020b, README §10 tabelas 19 a 21):**
  * o banco é o único canal entre web e agentes: o arquivo vai em `tbsss_input_upload` (BLOB) e cada agente vivo do ambiente recebe uma linha em `tbsss_input_delivery`; persistência só pelo repositório `inputs` (`repo_inputs`, `src/sss/persistence/oracle/inputs`, `src/sss/persistence/fake/inputs`); no daemon, só por `src/sss/persistence/oracle/scheduler_input`, que nunca importa a camada web (o teste confere);
  * o conteúdo nunca entra em listagem e sai só em partes de até 1 MiB (`read_content`); as entregas pendentes são lidas pela expressão de `ix_tbsss_idl_pend` (`sql_ident.FBI_IDL_PEND_CASE`);
  * sem agente vivo, o envio é recusado (`NoLiveAgent`), nunca fica parado na fila; a entrega só é marcada pelo próprio agente (`agent_id = :agent_id`), com `INPUT_DELIVERY` na mesma transação;
  * a lista `ddl_builder.ROLLBACK_ENTITY_ORDER` é fixa: toda tabela nova entra nela (o teste confere);
  * o purge (alvo `inputs`) esvazia o conteúdo só quando nenhuma entrega está `PENDING` e apaga os envios pela retenção, sob a concessão e em lotes;
  * no agente, a entrega é a máquina de estados de `src/sss/scheduler/input_phase.py` (sem espera; uma por vez; partes de 1 MiB) e o arquivo só chega à pasta pelo helper `put-input`, como o usuário de execução, com publicação atômica e hash conferido; o retrato só pelo `list-input`. Uma falha da entrada nunca derruba o ciclo dos tickets.
* **Pasta de entrada do script (CR-014, README §8.14):**
  * caminho só por `log_paths.input_dir` (base `input_dir/<ambiente>` e relativo = a pasta do script, um nível), na variável `SSS_INPUT_DIR`;
  * criada só pelo helper `run` (campo `entrada`), sem seguir link e só se não existir; em DEV sem usuário de execução, por `os_platform.create_input_dir`. A existente fica como está;
  * **permanente:** o SSS nunca lê, limpa, compacta nem purga essa pasta; nenhum código do agente apaga nada nela;
  * `input_dir` e `output_dir` entram nas pastas do SSS (`SSS_DIR`) para scripts e interpretadores, porque o usuário de execução grava nelas.
* **Pasta de trabalho do script (CR-019, README §8.15):**
  * caminho só por `log_paths.script_work_dir` (base `script_work_dir/<ambiente>` e relativo no formato da pasta de saída), na variável `SSS_WORK_DIR`; o `HOME`, o `cwd` e o `TMPDIR` do script **não** mudam;
  * criada só pelo helper `run` (campo `work`), nível a nível com `0700` e sem seguir link; em DEV sem usuário de execução, por `os_platform.create_script_work_dir`;
  * fica depois do ticket: nenhum código do agente lê, compacta ou apaga a pasta no fim do ticket, e o conteúdo nunca vai para log, banco ou tela; só o `purge.py` (alvo `script_work`) a remove, pelo helper `purge-output`, depois de `script_work_retention_days`;
  * o `work_dir` do agente **nunca** é entregue ao script; `script_work_dir` não se sobrepõe às pastas do SSS e entra em `SSS_DIR`.
* **Nomes em inglês no banco (CR-016a):** tabela, coluna, abreviação, sufixo de constraint/índice e valor gravado são em inglês; o nome físico vem só de `sql_ident` (`physical`, `table`, `sequence`, `names`), nunca de `prefixo + "<entidade>"` no código. A chave lógica da entidade (`ambientes`, `agendamentos`…) muda no CR-016c. Comentários de tabela e coluna (`COMMENT ON`) e texto de tela continuam em português.
* **Nomes em inglês (CR-015a):** variável nova passada ao script e chave nova do `config.ini` têm nome em inglês. Os nomes antigos do CR-015a (`SSS_AMBIENTE`, `saida_dir`…) nunca voltam: chave antiga fica em `sss_config.RENAMED_KEYS` (recusada na subida com o nome novo) e o `env_builder` não define variável antiga. Texto de tela, mensagens e documentação continuam em português.
* **Validação de caminho:** apenas por `src/sss/platform/path_guard.py` (README §8.5). Prefixo por `str.startswith` é **proibido**.
  * **Caminho livre (CR-005):** `path_file` é o caminho **absoluto** do script, em qualquer lugar do servidor; não há pastas base. Formato: absoluto, normalizado, sem `..`, `\`, `//` nem caractere de controle.
  * **Link simbólico aceito (CR-011):** o agente resolve o `realpath` e executa o arquivo real; recusa em pastas do sistema (`/bin`, `/sbin`, `/usr`, `/lib*`, `/etc`, `/boot`, `/proc`, `/sys`, `/dev`, `/root`) e dentro de `log_dir`/`work_dir`/`exec_work_dir`, no caminho cadastrado e no real, conferidas por `commonpath`. `EACCES` é `NO_ACCESS`, nunca `NOT_FOUND`.
  * **Arquivo real (CR-011, S2):** existe, é arquivo regular e não é gravável por grupo nem por outros. Dono e pastas do caminho não são conferidos, e não há hash: o ambiente controla o conteúdo e a versão dos scripts. O executável de cada interpretador (S3) só precisa existir, ser executável e ficar fora das pastas do SSS (`path_guard.validate_executable`; pode ser link simbólico).
  * **No nó web (CR-011, S1)** só o formato, a allowlist e as pastas do sistema são conferidos; o arquivo é conferido pelo agente, a cada execução (README §8.5).
* **Allowlist de interpretadores lógicos:** `PYTHON3`, `BASH` e `SH`, mapeados por agente para o executável local (`[agent] interpreters`).
  * Python é sempre invocado com `-I`.
* **Ambiente do filho:** construído **somente** por `src/sss/scheduler/env_builder.py` a partir de um dicionário novo, com a base por plataforma (README §8.6). É proibido usar `os.environ.copy()` como base.
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
* **Launcher do nó web:** `bin/sss-web.sh` recusa root, aplica `umask 077` e só faz `exec` de um interpretador `python3[.x]` com `scripts/run_web.py` e as opções dele; `web2py.py`, `anyserver.py` e qualquer outro `.py` são recusados (README §12.2, CR-021e2). Nunca o transforme em executor de comando arbitrário. `bin/start_local.sh`/`stop_local.sh` (só DEV) sobem pelo `sss-web.sh`, conferem com `run_web.py --check` e param com `SIGTERM`.

### 3.3 Segredos e PII

* Proibido segredo em código, `config.ini`, banco, testes ou fixtures.
* Segredos são lidos **somente** via `src/sss/config/sss_config.py`, a partir de `secrets.cfg`, com checagem de dono e permissão pela camada de plataforma (até o F8.0, no próprio `sss_config`): dono = usuário do processo e modo `0600` (README §4.1).
* **Segredos por papel (CR-007, D1b):** `sss_config.load_secrets(path, role)` com `papel` em `web`, `agente` ou `monitor` (CR-008, E3: só `[monitor] user/password`, para o `scripts/health.py`). Cada papel só aceita as próprias seções (o agente nunca tem `[web] cookie_key`; o web nunca tem `[environment:*]` nem `[purge]`); fora de DEV, seção de outro papel recusa a subida. O papel `monitor` é a exceção do README §4.1: só `[web]` é proibida, e as demais seções do arquivo do servidor são ignoradas, sem validar nem registrar no `masking` (F9.1b). Cada papel usa a **sua** conta Oracle (web, agente, purge); a conta dona do esquema só é usada pelo `init_db.py`, com senha digitada.
* Todo segredo carregado é registrado em `src/sss/core/masking.py`. Logs, mensagens de erro e `log_output` passam pelo mascaramento.
* Proibido registrar em log: senhas, hashes de senha, `PADRAO_VALOR_RUN_CONEXAO_BD`, `cookie_key`, token CSRF, valores de parâmetros `sensitive = 'Y'` e cabeçalho `Cookie`.

### 3.4 Web

* **Sessão:** somente o cookie assinado de `src/sss/web/framework/session.py` (`sss_session`, CR-021 D1), com payload mínimo (README §4.2). O conteúdo pode ser lido por quem tem o cookie: nunca guarde segredo na sessão.
* **CSRF** obrigatório em todo `POST`, validado com `hmac.compare_digest`. `GET` nunca altera estado.
* **Autorização:**
  * Toda action pública começa por um guarda explícito (`_require_login()`, `_require_func('CODIGO')`) que reconsulta o estado do usuário (README §4.2).
  * As guardas e leituras comuns ficam só em `src/sss/web/app/security.py` (CR-018f, CR-021e): `require_login`, `require_func(código)`, `require_method(*métodos)`, `require_query()`, `denied()`, `not_found(mensagem)`, `text(valor, limite)` e `client_ip()`. Os controllers as importam com o nome de antes (`from sss.web.app.security import require_func as _require_func`); nenhum as redefine, e cada um guarda só a sua mensagem de 404 em `_MSG_NOT_FOUND`.
  * Decisões de execução sempre chamam `rbac.can_execute`. O agente também a chama na pré-validação do claim, para o solicitante do ticket (CR-007, D2). O motivo de pausa vem sempre de `rbac.pause_reason_for` (CR-008, R-33), na web e no daemon.
  * **Administrador só por administrador (CR-008, E1):** `MANAGE_USERS` e `MANAGE_PROFILES` não bastam para tocar em perfil administrativo, em `is_admin`, na senha ou no estado de um administrador, nem na matriz do próprio perfil (README §4.3.A). A checagem é do service, com os dados lidos do repositório.
  * **Sessão revogável (CR-008, E2):** a revalidação compara `session_epoch` e a vida máxima (`session_max_hours`); logout, troca e redefinição de senha, desativação e troca de perfil incrementam `session_epoch` (README §4.2).
* **Saída:** sempre escapada com `{{=x}}`. **Proibido** `XML()` ou `{{=XML(...)}}` com qualquer dado de usuário ou de banco. No núcleo web próprio (CR-021d2), o `{{=x}}` escapa como o web2py (`None` vazio, o resto por `str()` e `html.escape(quote=True)`), e só um `web.markup.Markup` (ou objeto com `__html__`) sai sem escape: o `.xml()` genérico do web2py não é aceito. `Markup` só para HTML montado pelo código, nunca a partir de dado sem escape.
* **Cabeçalhos de segurança** (CSP, `nosniff`, `frame-ancestors`, `no-store` com usuário logado) são aplicados por `src/sss/web/app/security.after_request` em toda resposta dinâmica, inclusive de erro.
* **Senha:** somente `src/sss/core/security.py` (PBKDF2-SHA256, 200.000 iterações, `hmac.compare_digest`).
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
   * Todo SQL dos repositórios fica em `src/sss/persistence/oracle/`, escrito diretamente na sintaxe aceita pelo **Oracle 11gR2**, e precisa rodar também nas versões superiores (12c a 23ai).
   * Permitidos: `ROWNUM`, `SYSDATE`, `seq.NEXTVAL FROM DUAL`, `FOR UPDATE WAIT n`, `FOR UPDATE SKIP LOCKED` (CR-007: desdobro e NODE_OFFLINE), `DBMS_LOB.*`, `EMPTY_CLOB()`, `MERGE`, `CASE`, `NVL`, `DECODE`, `GREATEST` e `FLOOR`. Prefira `CASE` quando ele deixar a intenção mais clara.

1. **30 caracteres:** todo identificador (tabela, coluna, sequence, trigger, constraint, índice) tem no máximo 30 caracteres **após a expansão do prefixo**. Os nomes vêm exclusivamente do registro em `src/sss/core/sql_ident.py`.
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
14. **DDL:** é gerada a partir do registro de `sql_ident` e executada exclusivamente por `scripts/init_db.py` (código em `src/sss/cli/init_db.py`, CR-022b8), que é idempotente (README §11). Nenhum outro arquivo de `src/sss/` executa DDL.
15. **Colunas de registro (CR-006, README §10):** toda tabela, exceto `tbsss_audit` e `tbsss_control`, tem `created_at`, `created_by`, `updated_at` e `updated_by`.
    * Todo `INSERT` grava `created_at = SYSDATE` e `created_by = :actor`. Nenhum `UPDATE` toca `created_*`.
    * Todo `UPDATE` de **alteração de negócio** grava `updated_at = SYSDATE` e `updated_by = :actor`. Rotina técnica (heartbeat, log, PID, contadores do login, avanço do desdobro) **não** grava. A lista fechada das duas categorias está no README §10.
    * O ator vem de `audit['actor']` ou do parâmetro `actor=`: login, `SYSTEM:<agent_id>`, `SYSTEM:init_db` ou `SYSTEM:seed`. Sem ator, o repositório lança `RepoViolation` sem gravar nada.
    * Vínculos de conjunto são gravados por diferença; `script_param` leva o `created_*` de cada parâmetro que continua.
    * As colunas não entram na `version` do formulário, no `esperado` nem no `detail` da auditoria.
16. **Versão do esquema (CR-007, D4):** `sql_ident.SCHEMA_VERSION` é a versão que o código espera. Toda mudança de esquema (tabela, coluna, CK, índice, trigger) **incrementa** `SCHEMA_VERSION` e traz a migração `src/sss/cli/migrations/m<NNNN>_<descricao>.py`, idempotente, no mesmo pacote. Web e agente recusam subir se `tbsss_control.schema_version` for diferente. O `init_db` compara o esquema real com o registro, depois de normalizar os textos do dicionário (`sql_ident.normalize_expression`, CR-008 R-14), e aborta em divergência; nunca corrige sozinho.
    * **Exceção até a primeira produção (CR-008; ajustada no F7.3):** enquanto o esquema não foi implantado em produção, as mudanças entram direto na versão 1, sem migração; os bancos de DEV (ex.: `GFPR`) são refeitos pelo ciclo `02_rollback` → `01_deploy` → `99_validate`. A primeira implantação em produção congela a versão 1; dali em diante, vale a regra acima.
    * **CR-016a:** os nomes em inglês (tabelas, colunas, constraints, valores gravados) entraram por essa exceção, sem migração. O GFPR foi refeito pelo ciclo; o `init_db` recusa criar o esquema com a `tbsss_controle` antiga no owner.
17. **Contas por papel (CR-007, D1b; CR-008, E3):** papéis web, agente, purge e monitor (só leitura). O código da aplicação nunca usa a conta dona do esquema (`[oracle] user` igual ao `owner` é recusado fora de DEV, CR-008 R-29). Os GRANTs de cada papel estão no README §11.1; uma query nova que precise de privilégio novo atualiza essa tabela no mesmo pacote.

---

## 5. Convenções da camada web (CR-021e)

1. **Actions:** só funções **definidas no próprio controller**, sem `_` no início e sem parâmetro obrigatório (`src/sss/web/app/bootstrap.actions`). Nome importado (`redirect`, `URL`, as guardas) nunca vira rota. Função auxiliar começa com `_`, mesmo com argumentos.
2. **Contexto:** a configuração do processo é gravada por `src/sss/web/app/bootstrap.load_config` (ou por um teste) em `app_context.set_config` e lida por `app_context.require_config()` (falha na hora se não foi carregada) ou `app_context.get_config()` (devolve `None`). **Nenhum arquivo de `src/sss/` importa `gluon`**, nem dentro de função (`tests/unit/config/test_app_context.py`). Os repositórios vêm do `import repo_factory` direto (§5.5). A requisição (`request`, `response`, `session`, o usuário e o `URL`) vem de `src/sss/web/app/context.py`, por thread (D3), e **só** `src/sss/web/app/` e `src/sss/web/controllers/` a importam; o resto do pacote nunca.
3. **Registro dos controllers:** todo controller entra no registro explícito de `src/sss/web/app/bootstrap.controllers` (sem import dinâmico); o `dev` só com `sss_env = DEV` (`tests/functional/test_webapp.py` confere o registro contra os arquivos).
4. **Camada web (`src/sss/web/app/`):** `context` (requisição por thread e `URL`), `security` (hooks e guardas), `errors` (página de erro) e `bootstrap` (configuração, registro, views e o `Application`). Nenhum abre conexão no import; a conexão é obtida sob demanda via `db_conn`. As views recebem `request`, `response`, `session`, `URL`, `csrf_field` e `sss_ctx` (o usuário), além das variáveis da action.
5. **Separação de camadas:**
   * Controllers não contêm SQL nem regra de negócio. Eles validam a requisição, chamam services/módulos e renderizam.
   * Contratos de persistência ficam em `src/sss/persistence/contracts/repo_*.py`: classes abstratas, sem SQL.
   * **SQL reside apenas em `src/sss/persistence/oracle/`** (Oracle 11gR2) e em `scripts/init_db.py` (DDL).
   * `src/sss/persistence/fake/` implementa o mesmo contrato em memória, com paridade de semântica (README §2.5). É proibido adicionar ao FAKE um método que não exista no contrato.
   * Controllers e services obtêm repositórios **somente** via `repo_factory`. É proibido importar `sss.persistence.fake` ou `sss.persistence.oracle` (antes do CR-022b4, `repo_fake` e `repo_oracle`) diretamente.
   * O `repo_factory` importa o `sss.persistence.fake` **só dentro do ramo FAKE**, nunca no nível do módulo: o pacote de implantação não leva o FAKE (README §12.2), e um import de topo derruba a aplicação implantada (F9.1d; `test_package.py` confere que nada que vai no pacote importa no topo o que fica fora dele).
   * **Exceção — repositórios internos de processos batch:** `src/sss/persistence/oracle/scheduler_*.py` (fila, agenda e log), `src/sss/persistence/oracle/purge.py` e `src/sss/persistence/oracle/health.py` não fazem parte do contrato da UI e não têm versão FAKE. Eles são importados diretamente **apenas** por `scheduler_loop.py`, `log_pump.py`, `scripts/purge.py` e `scripts/health.py`, todos processos que exigem banco real (README §2.5), e não importam a camada web. Única exceção: `src/sss/persistence/oracle/agents.py` importa do `src/sss/persistence/oracle/health.py` o SQL da fila sem atendente e do rodando sem PID e o cálculo dos pares atendidos, para a tela de agentes e o monitoramento não divergirem (F9.1b).
   * Regras de negócio residem em `src/sss/core/` (rbac, params_compiler, recurrence), `src/sss/services/` (`*_service`, `admin_crud`) e `src/sss/scheduler/` (laço do agente, executor, desdobro da agenda).
   * **Backend:** a aplicação usa sempre o Oracle do `[oracle]` (owner e prefixo); `[app] data_backend` foi removida no F7.3 e é recusada se aparecer. O FAKE só existe injetado por teste (`repo_factory.configure`) e só com `sss_env = DEV`. DEV e PROD se separam pelo owner e pelo prefixo; `sss_env` continua como trava de segurança.
6. **Núcleo web próprio (`src/sss/web/framework/`, CR-021d1):** pacote só com a biblioteca padrão, no padrão D8: linhas de até 99 colunas, funções e métodos públicos com anotações de tipo e docstring, imports relativos entre os módulos do pacote e nenhum `gluon` (`tests/architecture/test_web_package.py`). Não conhece regra de negócio (CSRF, guardas e cabeçalhos de segurança entram por hooks no CR-021e). Regras dele:
   * corpo da requisição lido só sob demanda, nunca além do `Content-Length` nem do limite (413 sem ler); multipart **em fluxo** (`web/multipart.py`); corpo malformado ou truncado é 400;
   * sessão só em cookie **assinado** (`web/session.py`, D1): JSON em base64url, HMAC-SHA256 com chave derivada do `cookie_key`, `hmac.compare_digest`; cookie inválido vira sessão vazia com o motivo; nunca objeto Python serializado;
   * `Set-Cookie` sempre `HttpOnly` e com `SameSite`; cabeçalho com quebra de linha é recusado; JSON de resposta só por `json_for_html` (escapa `<`, `>` e `&`);
   * `url()` com saída igual à do `gluon.html.URL` nas formas usadas (tabela gravada em `tests/unit/web/test_web_routing.py`, CR-021f1).
   * raiz como no web2py (D4): `/` responde 303 para `/<app>/`, e `/<app>` e `/<app>/` são `default/index` (o login leva `next=/<app>/`) (CR-021e2);
   * o roteador recebe o `PATH_INFO` **já decodificado** (o servidor faz o `unquote`; `decode_path_info` só passa o latin-1 do WSGI para UTF-8). Decodificar de novo é dupla decodificação (`%252e%252e%252f` viraria `../`);
   * estáticos só por `web/static.py`: GET/HEAD, `realpath` dentro de `src/sss/web/static/` (link para fora dá 404), sem arquivo oculto nem listagem, revalidação por `ETag`/`Last-Modified`;
   * `web/app.py`: todo erro 400+ sai com a página de erro da aplicação (como o `routes_onerror`), o 500 com id de ocorrência e stack trace só no log; hooks `after` em toda resposta dinâmica; sessão regravada só quando muda, nunca no 500;
   * `web/server.py`: semáforo de `max_threads`, `timeout` por conexão, cabeçalho com `_` descartado (o `wsgiref` o confundiria com o de `-`), cabeçalho `Server` só `SSS`, log pelo `logging` e nunca no stderr.
   * `web/template.py`: gera o mesmo código Python que o template do web2py (conferido view a view até o CR-021e; hoje, toda view real compila e o template sintético sai byte a byte igual à saída gravada do web2py, `test_web_template.py`); `block`, `super` e `end` recusados; cache por data de modificação da view e dos incluídos.
7. **Daemon:** o `scripts/run_scheduler.py` é o único entrypoint do scheduler. É proibido iniciar threads, timers ou o scheduler a partir de controllers ou models.

---

## 6. Logging e Robustez

* Use o módulo `logging` com o formato e os níveis do README §13. É proibido `print` em código de aplicação, exceto nos CLIs `init_db.py`, `purge.py` e `health.py` (stdout; o `health.py` não grava log em arquivo, a saída do plugin fica no monitoramento).
* **Exceções:**
  * Todo `except` registra o contexto (ticket, agente, ação), o código ORA- quando houver e o stack trace em ERROR.
  * **Exceção (CR-007):** situações esperadas e tratadas (timeout de lock, deadlock, *call timeout*, `rowcount = 0` de corrida perdida, linha pulada por `SKIP LOCKED`) vão em WARN com o código e **sem** stack trace (README §13).
  * **Exceção (revisão F8.0–F8.2):** `except` de fluxo previsto de SO, em que a condição é o próprio resultado esperado (`ProcessLookupError`/ESRCH de grupo já vazio, `FileNotFoundError`/ENOENT de arquivo de estado ainda inexistente, `OSError` ao ler `/proc/<pid>` de um processo que acabou de sair), pode não registrar nada, desde que tenha um comentário explicando o caso. Qualquer outra falha segue a regra acima.
  * É proibido `except:` ou `except Exception: pass` silenciosos.
* **Caminhos de log (CR-005):** montados **somente** por `src/sss/config/log_paths.py`, nunca à mão:
  * log da aplicação: `log_dir/internal/app/AAAA/MM/DD/HH/MI/<log_name>_<PID>.log`, com troca por tamanho e retenção por dias (README §13);
  * log de execução do script: `log_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log`, com a hora de `started_at` e o ambiente do ticket **obrigatório** (README §8.4; CR-009). Todo log começa pela pasta do ambiente; sem ambiente, `internal` (nome de ambiente reservado).
* **Configuração:** toda chave tem tipo e faixa validados. Chave ausente, desconhecida ou inválida interrompe a inicialização (fail-fast). Antes de abortar, a falha é registrada em CRITICAL por `sss_logging.log_initial_critical`, no `log_dir` quando ele aceita escrita e no stderr caso contrário (README §12.1).
* **Graceful shutdown:**
  * Handlers de SIGTERM/SIGINT apenas acionam uma flag. O arquivo `work_dir/sss-<agent_id>.stop`, verificado a cada ciclo, tem o mesmo efeito. O pedido é conferido no início de cada volta do laço, antes dos ciclos (nenhum claim nem desdobro depois dele), e de novo depois deles (README §8.11).
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

1. Framework **exclusivamente** `unittest`, executado a partir da raiz do repositório: `python -m unittest discover -s tests -t .` (suíte completa; `make test-all`). O `pytest` é proibido.
   * **Organização (CR-022b1):** os testes ficam em `tests/`, fora de `scripts/` (que só tem as ferramentas de operação), separados pelo recurso que usam. Cada pasta é um pacote (`__init__.py`), sem o qual o `unittest` do Python 3.6 não descobre os testes dela:

     | Pasta | Critério | Alvo do Makefile |
     |---|---|---|
     | `tests/unit/<camada>/` | Sem banco real e sem rede (FAKE, mocks, conexão roteirizada). Subpasta pela camada do código testado: `config`, `core`, `platform`, `persistence`, `ui`, `services`, `scheduler`, `web`, `cli`, `tools` | `make test-unit` |
     | `tests/integration/oracle/` | Precisa do Oracle real, ligado só com `SSS_TEST_ORACLE=1` (item 2) | `make test-integration` |
     | `tests/integration/process/` | O assunto é processo do sistema: spawn, sinais, grupo, helper, launchers | `make test-integration` |
     | `tests/functional/` | A aplicação inteira, montada de verdade, por requisição (`sss.web.app`) ou com o servidor real (`sss.web.framework.server`) | `make test-functional` |
     | `tests/architecture/` | Lê código e documentos: compatibilidade com o 3.6, regras por AST, hermeticidade, conteúdo do pacote, contraste de cores, guia de implantação | `make test-architecture` |
     | `tests/support/` | Auxiliares, sem testes: `_testenv`, `_oracle_test_support`, `_output_memory` | — |

     Um teste unitário pode abrir um interpretador filho só para isolar imports; o que vai para `integration/process/` é o teste cujo assunto é o processo. A parte de um arquivo que precisa do Oracle real fica em `tests/integration/oracle/<arquivo>_oracle.py` (ex.: `test_repo_contract.py` roda a bateria no FAKE e `test_repo_contract_oracle.py` no Oracle) e importa as bases e dublês do arquivo unitário, nunca uma classe `TestCase` que tenha testes (rodaria duas vezes). Os testes de ponta a ponta são a homologação no navegador (item 6), fora do `unittest`.
   * `tests/support/_testenv.py` põe no `sys.path` a raiz da aplicação, `src/` (pacote `sss`; as ferramentas de operação são importadas como `sss.cli.<nome>`, CR-022b8) e `tools/` e expõe `APP_DIR` e `WEB_DIR`. Fora dele e dos involucros de `scripts/` (e do `tools/package.py` e do harness, ferramentas de DEV), nenhum código mexe no `sys.path` (`tests/architecture/test_entry_points.py`). Desde o CR-022a a aplicação **é** a raiz do repositório (`/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service`, sem `web2py/` nem `applications/`). Todo teste o importa primeiro (`from tests.support import _testenv`) e usa `_testenv.APP_DIR` para achar arquivos da aplicação, nunca um caminho relativo à própria pasta. O mesmo vale para os auxiliares importados dentro de função (`from tests.support._oracle_test_support import ...`): eles só rodam com o Oracle ligado, e a suíte sem banco não os confere.
   * Nenhum arquivo de `src/sss/` fora de `src/sss/web/` (e de `src/sss/cli/run_web.py`) importa a camada web da aplicação, e nenhum importa `gluon` (CR-021c, §5.2); desde o CR-021f, nenhum `.py` do repositório importa `gluon`.
2. Testes que dependem de banco real devem usar mocks da interface de `db_conn` **ou** ser ligados só por `SSS_TEST_ORACLE=1` (`_oracle_test_support.real_db_configured()`), com owner, prefixo, DSN e conta lidos do `instance/config.ini` e a guarda de `tests/support/_oracle_test_support.py` antes de qualquer escrita (README §2.5). Sem a chave, o veredito do relatório é `NÃO TESTADO` para a parte de banco. A partir do F7, aplicação e validações usam as tabelas reais; o FAKE fica só como dublê dos testes automáticos sem banco.
   * **Plataforma:** a implementação POSIX é testada de verdade, no Linux (CR-005).
3. Os testes rodam em Python real, no mínimo na **3.6.0** (mínima suportada) e na **3.6.8** (referência de produção). Recomenda-se rodar também na mais nova disponível (3.13). Sem nenhum Python 3.6.x no ambiente, o veredito máximo é `NÃO TESTADO`, e o motivo deve constar nas observações.
4. **Testes obrigatórios mínimos** (os marcados com `[F7.x]`/`[F8.x]` são criados no prompt indicado e ainda não existem). A tabela cita o arquivo pelo nome, que é o mesmo em qualquer pasta de `tests/` (item 1); onde ela fala de "Oracle real" ou "`SSS_TEST_ORACLE=1`", essa parte fica no `<arquivo>_oracle.py` de `tests/integration/oracle/`:

| Arquivo | Cobertura obrigatória |
|---|---|
| `test_repo_contract.py` | A mesma bateria contra FAKE (sempre) e ORACLE (com `SSS_TEST_ORACLE=1`; cada teste cria e limpa a própria massa, sem depender do seed), em cada combinação de driver disponível — Thin (banco 12.1+), Thick e cx_Oracle (CR-002, D5): CRUD, unicidade, transições condicionais com `RepoConflict`, cascatas, imutabilidade de `name`/`login`, paginação e ordenação; colunas de registro (CR-006): `created_*` na inclusão, `updated_*` só na alteração de negócio, ator obrigatório, vínculos por diferença preservando `created_*` |
| `test_db_schema.py` | Todo identificador do registro com `len <= 30` usando o prefixo configurado **e** o pior caso de 8 caracteres; todo nome em ASCII; toda FK com índice de coluna líder; toda tabela com trigger no template condicional; as 17 tabelas e o README §10 igual ao registro; `SCHEMA_VERSION` declarada (CR-007) |
| `test_py36_compat.py` | `ast.parse(..., feature_version)` ou compilação com 3.6 em todos os `.py`; busca por tokens proibidos (§2.1), `shell=True`, `os.system`, `eval(`, `exec(`, `pickle`, `XML(`, diretiva do Alpine em HTML montado em Python (`x-…="`), URLs `http(s)://` em `src/sss/web/static/` e `src/sss/web/templates/` |
| `test_path_guard.py` | Caminho relativo, não normalizado, com `..` ou `\`; link simbólico aceito, com o arquivo real conferido, e ciclo de links (`NOT_FOUND`); pastas do sistema no caminho cadastrado e no real; prefixo irmão (`/usrx`, `/etcetera` aceitos); dentro de `log_dir`/`work_dir`/`exec_work_dir`; arquivo inexistente; diretório sem acesso (`NO_ACCESS`); diretório em vez de arquivo; arquivo gravável por grupo ou outros; dono indiferente; interpretador fora da allowlist (`validate_interpreter`) ou executável ausente, não executável ou nas pastas do SSS (`validate_executable`) |
| `test_sss_logging.py` | Log da aplicação (README §13): caminho por minuto, troca por tamanho com sufixo, retenção na subida e na troca, `agent_id` na linha, falhas da retenção como WARN, pastas `0750` em todos os níveis sob `umask 077` e arquivos `0640` |
| `test_log_paths.py` | Pasta do script (acento, espaço, `/`, maiúsculas, vazio, `app`); pasta do ambiente obrigatória e normalizada, `internal` reservado (CR-009); caminho do log de execução e do log da aplicação; sufixo na troca dentro do mesmo minuto; retenção só de pastas com formato de data; retenção dos logs de execução (F9.1a) pela data do caminho, com referência `date` ou `datetime`, `dry_run` sem remover, pasta `RUNNING` e `internal/` mantidas; pasta de entrada (CR-014) só com ambiente e script |
| CR-014 em `test_scheduler_claim.py`, `test_scheduler_init.py`, `test_executor.py`, `test_env_builder.py` e `test_platform.py` | `SSS_INPUT_DIR` em `input_dir/<ambiente>/<script>`, criada sob demanda com `0700` e mantida (conteúdo e modo) entre tickets; sem `input_dir`, sem a variável; script dentro de `input_dir` ou `output_dir` recusado com `SSS_DIR`; na subida, `input_dir` nas pastas do sistema ou inexistente recusado (código 13) e, fora de DEV, a pasta de cada ambiente conferida; campo `entrada` na especificação do helper; em DEV, criação pela plataforma recusando link |
| CR-019 em `test_config.py`, `test_log_paths.py`, `test_env_builder.py`, `test_executor.py`, `test_platform.py`, `test_sss_helper.py`, `test_scheduler_init.py` e `test_purge.py` | `script_work_dir` opcional, absoluto e sem sobreposição com as pastas do SSS, a de saída e a de entrada; `script_work_retention_days` 1 a 365; caminho no formato da saída; `SSS_WORK_DIR` só com a chave, e o `HOME` continua na pasta descartável; campo `work` na especificação; criação com `0700` nível a nível (helper e DEV), recusa de link, de outro ticket e de formato; conferência na subida e `SSS_DIR`; alvo `script_work` do purge com a retenção própria, `--dry-run` só conta, desligado sem a chave e falha com código 3 |
| `test_output_browse_service.py` e CR-020a em `test_repo_oracle_progressive.py` | Tela de Saídas: níveis ambiente, script, dia e ticket só com saídas `AVAILABLE`; solicitante mascarado; escopo (404, nunca 403) e `DOWNLOAD_OUTPUT`; parâmetros fora do formato; índice do zip sem pastas; zip completo e um arquivo pelo nome exato, com `OUTPUT_DOWNLOAD`; nome fora do índice recusado sem auditar; nome do download limpo; `BlobReader` em blocos alinhados com `seek`; SQL Oracle por bind, só `AVAILABLE`, sem BLOB e sem função no `WHERE` |
| `test_repo_inputs.py` (FAKE e Oracle com `SSS_TEST_ORACLE=1`) | Envio só para agentes vivos do ambiente, recusado sem nenhum e sem gravar; FK do script; conteúdo fora das listagens e em partes; entrega só pelo próprio agente, uma vez, com motivo só em `FAILED` e `INPUT_DELIVERY`; retrato pedido, publicado e pedido de novo no mesmo segundo |
| `test_input_phase.py` e CR-020c em `test_sss_helper.py` | Entrega em partes de 1 MiB pelo helper de verdade; `EXISTS` sem substituir e substituição; hash do banco divergente sem chamar o helper; nome recusado (`NAME`) e conteúdo esvaziado (`ERROR`); temporários da subida apagados; `put-input` com subpastas `0700`, publicação atômica, sem temporário no destino, hash e tamanho (11), nomes e níveis inválidos (2), link e destino que não é arquivo; `list-input` sem links, sem temporários e com teto |
| `test_input_browse_service.py` e CR-020d em `test_security.py` e `test_config.py` | Escopo por ambiente e script do perfil (404) e `UPLOAD_INPUT`; pasta montada pelos retratos, subpastas e servidores; motivo da falha em linguagem simples; envio para os agentes vivos com auditoria; erros por campo sem gravar (nome, subpasta, tamanho, sem arquivo); sem servidor no ar; pedido de retrato; limite do POST antes da leitura do corpo; faixa de `input_upload_max_bytes` |
| CR-020e em `test_purge.py` e `test_config.py` | Conteúdo esvaziado só sem entrega `PENDING`; envios além da retenção apagados (inclusive com entrega presa); `PURGE` com as duas contagens, inclusive zero; `--dry-run` só conta; concessão de outro nó pula; faixa de `input_retention_days` |
| CR-016a em `test_db_schema.py`, `test_ddl_builder.py`, `test_repo_contract.py` e nas suítes dos repositórios e serviços | Tabelas, colunas, abreviações, sufixos e valores gravados em inglês, todos com até 30 caracteres; `sql_ident.physical`/`table`/`sequence` como única origem do nome físico; README §9.2 e §10 iguais ao registro (pelo nome físico); flags `'Y'`/`'N'`; `init_db` recusa criar o esquema com a `tbsss_controle` antiga no owner; bateria Oracle no esquema refeito pelo ciclo `02` → `01` → `99` |
| `test_purge.py` `[F9.1]` | Banco simulado com o SQL do `src/sss/persistence/oracle/purge.py`: `DELETE` literal em lotes até `rowcount = 0`, só tickets terminais, limite único pelo `db_now()`; concessão tomada, renovada por lote, liberada (dono **e** prazo, CR-008 R-27), negada (sem `DELETE` nem auditoria), vencida tomada e perdida no meio (lote desfeito, código 1); `PURGE` por tabela com 0 linhas (CR-008, R-16); `--export-audit` (CSV `0600`, apagado pelo id); `--dry-run` só com `SELECT`, um `db_now()`, sem trava e com aviso de estimativa; logs locais pela data do caminho (`.log.parcial`, vazias até o ambiente, `RUNNING` mantido, `internal/` e link intocados, fora de `log_dir` recusado, código 3); saída pelo helper por ambiente; trava local concorrente; códigos 0/1/2/3. Com `SSS_TEST_ORACLE=1`, purge real com a conta do owner só quando nada fora da fixture é elegível (pulado senão) |
| `test_params_compiler.py` | Regex no subconjunto seguro (aceitas e recusadas do README §6.2, com tempo de `fullmatch` limitado, inclusive os quantificadores limitados largos e o teto de 4 escolhas com ilimitado do CR-008 R-06); valor sensível com menos de 4 caracteres recusado; NUL e controle recusados também no snapshot; precedência; obrigatório ausente; `NAMED` com flag longa e curta; valor iniciado em `-`; `CHECKBOX`; `POSITIONAL` com opcional vazio intermediário; `NONE`; regex com `fullmatch`; rejeição de NUL e controle; `SELECT` fora de `options_json`; serialização determinística do snapshot |
| `test_cron_parser.py` | Listas, intervalos, passos, semântica OU de dia, dia 31 e fevereiro, ano bissexto, expressão sem ocorrência, rejeição de nomes e `L`/`W`/`#` |
| `test_recurrence.py` | `DAILY`, `WEEKLY`, `MONTHLY` (mês curto), `ONCE`, `end_date`, *misfire* `RUN_ONCE`/`SKIP`, `ocorrencia` coberta (CR-007), `SKIP` medido pela vencida mais recente e `cron_error` sem exceção (CR-008, R-19 e R-21), conclusão sem ticket, mensagem de CRON com `end_date`, datas sem microssegundos |
| `test_env_builder.py` `[F8.1]` | Ambiente sem herança de `os.environ`; rejeição de variáveis bloqueadas; passthrough; ausência de DSN; variáveis `SSS_*` da execução, do ambiente, do script, do log e do agente, ausentes quando sem valor (CR-010); `SSS_OUTPUT_DIR` só com `output_dir` (CR-012); nenhum nome antigo (português) definido, nem com todos os dados presentes (CR-015a) |
| `test_scheduler_ha.py` `[F8.4b]` | Desdobro (`src/sss/scheduler/schedule_expansion.py`) com a agenda em memória e as funções reais de `recurrence`, `rbac` e `params_compiler`: ticket com a ocorrência, snapshot v5 e um `COMMIT` por regra; corrida e regra com outro agente; pausas pelo RBAC com a tradução única (R-33, e todo `rbac.Reason` aceito pela CK); `PRIORIDADE_REBAIXADA`; sobreposição sem mexer em `last_ticket_id` e `SKIP_OVERLAP_PRESO`; misfire `RUN_ONCE`, `SKIP` e R-21; perdidas em INFO e WARN pela vencida mais antiga; conclusão da `ONCE` com e sem ticket, por `end_date` e numa sobreposição; `INVALID_PARAM` e `CronError`; R-19 com e sem sobreposição; R-31 (`DUPLICATE_OCCURRENCE` avança numa nova transação); R-22 (3 falhas de banco, sucesso zera, `ValueError` pausa na 1ª, pausa que falha ignora a regra); paginação com 3 páginas e orçamento. No Oracle real: ticket e pausa `INVALID_PARAM` pelos repositórios. **F8.4c**, com o laço real e scripts `/bin/sh`: fence no limiar e não antes, grupo encerrado, claims suspensos no cerco e retomados depois do heartbeat, `FENCED` na recuperação, R-12 (resultado local prevalece), 30 execuções encerradas de uma vez sem bloquear; `NODE_OFFLINE` dos tickets de outro agente com INFO, nunca com o próprio heartbeat velho, suspenso por `SALTO_RELOGIO` no heartbeat e detectado na própria transação (R-10). **F8.4d:** parada já pedida antes da volta não faz claim nem desdobro, no `DRAIN` e no `TERMINATE`; `DRAIN` pelo `.stop` (script termina normalmente, heartbeat mantido, sem claim, saída gravada, `.stop` removido, saída 0), `DRAIN` com `shutdown_grace_s` vencido vira `SHUTDOWN`, `TERMINATE` pela flag, e SIGTERM/SIGINT só acionam a flag |
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
| `test_package.py` `[F9.1, CR-021f3, CR-022a]` | Árvore falsa do repositório, com a aplicação na raiz e só a lista de permissão no pacote (nada de `.git`, `Makefile`, `input/`, `output/`): pacote gerado; `SHA256SUMS` de fora confere com o `tar.gz` e o de dentro com cada arquivo; tar reprodutível; `bin/sss-helper` presente e `0755`; `scripts/run_web.py` e `src/sss/web/app/` presentes; nada do web2py (nem pasta de runtime), DEV, testes e `instance/config.ini` ausentes; `package.py` rodando de dentro da cópia que empacota sem gravar `__pycache__` nela; recusa com `gluon/`, `web2py.py`, `anyserver.py` ou `routes.py` na raiz; recusa, sem gravar nada e sem imprimir o valor, com `secrets.cfg`, senha ou `cookie_key` fora do placeholder (inclusive em `.cfg.example`), `CHANGE_ME` fora do `secrets.cfg.example`, bytecode, link simbólico, outra aplicação e helper ausente; `CHANGE_ME` aceito no exemplo; nenhum arquivo que vai no pacote importa no nível do módulo o que fica fora dele (`repo_fake`, `dev`, auxiliares de teste; F9.1d) |
| `test_deployment_doc.py` `[F9.1]` | `docs/DEPLOYMENT.md`: todo `bin/…`, `scripts/….py` e `docs/sql/…` citado existe; toda referência interna `§n` do corpo aponta para uma seção existente; nenhum procedimento do FAKE no corpo (o Apêndice B, histórico, fica de fora) |
| `test_launchers.py` `[F9.1]` | `bin/sss-web.sh`, `bin/sss-scheduler.sh` e `bin/sss-stop.sh` numa raiz falsa, com `python3`, `id` e `ldconfig` falsos: sintaxe (`bash -n`), recusa de root, as três formas do web, sempre o `run_web.py`, e só a linha do daemon no scheduler (`web2py.py`, outro script ou comando: código 2); `start_local.sh`/`stop_local.sh` com sintaxe válida e nenhum script do `bin/` subindo o web2py `[CR-021e2]`; `exec` a partir da raiz com `umask 077`, `LD_LIBRARY_PATH` só sem o Instant Client no `ldconfig`, `TZ` e locale; `.stop` `0600` no `work_dir` do `config.ini` e recusa de configuração inválida (código 2) |
| `test_health.py` `[F9.1]` | `scripts/health.py` com repositório simulado: cada verificação do README §13 no limiar e fora dele, um único `db_now()`, o código Nagios agregado (o pior vence) e a saída (resumo com dados de desempenho e uma linha por problema, críticos primeiro); UNKNOWN em configuração, segredos, conexão e erro de banco; segredos do papel `monitor` sem carregar nem mascarar `[oracle]`, `[purge]` e `[environment:*]` (CR-008, E3); fila sem atendente pelo interpretador do cadastro (R-15); `PURGE` com 0 linhas conta como execução (R-16); SQL do `src/sss/persistence/oracle/health.py` sem LOB e o mesmo da tela de agentes. Com `SSS_TEST_ORACLE=1`, as consultas no Oracle real pela conta do owner (só leitura) e o `EXPLAIN PLAN` sem `TABLE ACCESS FULL` em tickets e auditoria |
| `test_executor.py` `[F8.1]` | Spawn real de script de teste (`/bin/sh`) em diretório temporário; log no caminho do CR-005, com o renome para `ticket_<id>_<PID>.log`; saída em arquivo sem PIPE; geração de mais de 1 MB de saída sem travar; timeout; encerramento escalonado matando também o neto; conversão de `returncode` negativo |
| `test_platform.py` `[F8.0]` | Encerramento escalonado sem bloquear (máquina de estados), grupo encerrado mesmo após a saída do processo principal (netos), `.sss_spawn`/`.sss_proc`/`.sss_result` com escrita atômica (CR-008, R-01), `validate_execution` com dublê de `sudo`, grupo e encerramento escalonado, identidade do processo (`starttime`) contra PID reciclado, lock de instância, recusa de root, dono e permissão de segredos e do caminho do script |
| `test_sql_oracle11g.py` `[F7.3]` | Varredura de `src/sss/persistence/oracle/` e `scripts/init_db.py`: nenhuma sintaxe 12c+ (§4.3); `FOR UPDATE` sempre com `WAIT n` (n ≤ 5); nenhum `SELECT *` |
| `test_ddl_builder.py` (seed do `init_db`) | `_run_seed` com conexão simulada: termina sem rollback e grava cada ambiente padrão antes de ligá-lo aos perfis (matriz perfil × ambiente pelo nome) |
| `test_seed_fake.py` | Seed FAKE coerente com as regras (README §2.5), com a linha de `tbsss_control` na versão do código: funcionalidades com os nomes do README, nenhum parâmetro de credencial, prioridade 1 só para admin, `created_at` nunca no futuro, colunas de registro coerentes com o README §10 (CR-006), snapshot e respostas compilados contra o script, agendamentos no minuto exato e alinhados à regra |
| `test_ui_helpers.py` | Catálogo de mensagens em duas partes, nomes simples de situação e de motivo, frase e etapas do ticket, tempo em linguagem simples, nome do ator no quadro Registro (CR-006) e o mascaramento do ator para quem não tem `VIEW_AUDIT` (CR-007, D6), inclusive solicitante e responsável por `visible_actor` (CR-008, E5) |
| `test_config.py` | Tipos e faixas de toda chave; `table_prefix` só minúsculas; `agent_id` reservados (`init_db`, `seed`, `purge`); invariantes I1 a I4; `exec_users` cobrindo os ambientes fora de DEV; `audit_retention_days` ≥ 365 e ≥ `ticket_retention_days`; `env_passthrough` sem variáveis bloqueadas nem chaves fixas; segredos por papel (CR-007; papel `monitor`, CR-008, que ignora as seções dos outros papéis e recusa `[web]`, F9.1b); `cron_horizon_days` ≥ 1.461, `session_max_hours`, `log_dir_min_free_mb` e `[oracle] user` diferente do `owner` fora de DEV (CR-008) ; chaves removidas recusadas com "apague a linha" (CR-011); `input_dir` (CR-014) opcional e sem sobrepor `log_dir`, `work_dir`, `exec_work_dir` e `output_dir`; chaves renomeadas (CR-015a) recusadas com o nome novo |
| `test_auth_service.py` | Login, revalidação e sessão (README §4.2), inclusive a revogação por `session_epoch` (logout, troca e redefinição de senha, desativação, troca de perfil) e a vida máxima `session_max_hours` (CR-008, E2); a mensagem de bloqueio de "Minha senha" (`lock_message`) e os nomes de `auth_service` usados pelos controllers |
| `test_admin_users_service.py`, `test_admin_profiles_service.py` | CRUD, autoproteções e o último administrador; **E1 do CR-008:** quem não é administrador não inclui nem move ninguém para perfil administrativo, não redefine senha, não desbloqueia, não desativa nem troca o perfil de um administrador, não marca nem desmarca `is_admin`, não altera perfil administrativo nem a matriz do próprio perfil, sem gravar nem auditar |
| `test_admin_scripts_service.py` | Cadastro e homologação de scripts; no nó web só o formato e as pastas do sistema são conferidos, sem conferir o arquivo nem calcular hash, e um link para pasta do sistema é recusado (CR-011) |
| CR-017 em `test_admin_environments_service.py`, `test_ticket_service.py`, `test_ui_helpers.py`, `test_permissions_service.py`, `test_schedules_service.py`, `test_admin_scripts_service.py` e `test_catalog_service.py` | `is_production` marcado e desmarcado no cadastro, com auditoria; o destaque de produção do disparo segue o cadastro e não o nome; item "Tickets" do menu com `EXEC_SCRIPT` ou `VIEW_LOGS`; um só item para rodar ("Rodar um script", `tickets/catalog`), sem "Disparar Scripts" no menu, e "O que eu posso fazer" levando `EXEC_SCRIPT` aos cartões (017b); a prévia do comando pelo `trigger_summary`, o mesmo do modal; em `test_schedules_service.py`, a nova regra com a escolha em lista e o salto com um ambiente só, e no menu os itens Agenda e Agentes na Operação (017c); em `test_admin_scripts_service.py`, o quadro "Quem pode rodar" (pronto, só administradores, sem homologação, script desativado, sem cálculo injetado), e em `test_catalog_service.py`, o atalho Agendar só com `MANAGE_SCHEDULES` (017d) |
| CR-018 em `test_rbac.py`, `test_ticket_service.py`, `test_schedules_service.py`, `test_admin_parameters_service.py`, `test_admin_scripts_service.py`, `test_seed_fake.py`, `test_permissions_service.py`, `test_audit_service.py`, `test_catalog_service.py` e `test_repo_contract.py` | Cancelar ticket de terceiro só com `CANCEL_TICKET` e `VIEW_LOGS`; filtro por solicitante ignorado para quem não vê logins (o próprio login continua); regras em risco depois de tirar uma opção do parâmetro (`rules_at_risk`, `impact_warning`); aviso do formulário de parâmetro e depois de salvar os vínculos; tickets na fila avisados ao trocar o arquivo do script (018a); nomes "Rodar Scripts" e "Consultar Tickets" no seed e lidos do cadastro nos motivos (`test_seed_fake`, `test_permissions_service`), "O que eu posso fazer" só com a contagem de scripts, motivo em nome simples na lista de tickets, ambientes do filtro das regras e nomes simples da Auditoria (`test_audit_service`) (018b); em `test_catalog_service.py`, as telas de execução sem leitura do catálogo por script (cartões: uma leitura de ambientes, de scripts e dos executáveis; disparo: três leituras), e em `test_repo_contract.py`, `RepoAudit.count` igual ao `iterate`, com filtro e teto, no FAKE e no Oracle (018c); em `test_admin_environments_service.py`, o DSN Easy Connect com a porta opcional e todo DSN do seed aceito pela tela (correção do DSN, antes do 018f3) |
| `test_catalog_service.py` | Rodar um script (cartões) e histórico: mesmo escopo da lista de tickets (com e sem `VIEW_LOGS`), script fora das rotinas dá 404, contrato sem LOB e limitado, números do resumo iguais aos do gráfico e geometria do gráfico |
| `test_web_package.py`, `test_web_routing.py`, `test_web_multipart.py`, `test_web_request.py`, `test_web_session.py`, `test_web_static.py`, `test_web_app.py`, `test_web_server.py` e `test_web_template.py` `[CR-021d1, 021d2]` | Padrão D8 do pacote por AST (99 colunas, tipos, docstrings, imports relativos, só biblioteca padrão); `url()` igual ao `gluon.html.URL` nas extensões html, load e json e o roteador recusando travessia, função `_privada`, controle e UTF-8 inválido; raiz do servidor (303) e da aplicação (`default/index`) como no web2py `[CR-021e2]`; multipart com delimitador cortado entre blocos, arquivo indo para o disco, e os ataques (corpo truncado, `Content-Length` mentindo, partes demais, cabeçalho gigante, campo acima do limite, UTF-8 inválido); consulta só com `&`, vars juntando GET e POST como o web2py, JSON do fetch em `post_vars` e JSON inválido 400, corpo acima do limite sem ser lido; JSON de resposta seguro para HTML, `Set-Cookie` com `HttpOnly`/`SameSite`/`Secure` e injeção de cabeçalho recusada; sessão: ida e volta, payload adulterado, outra chave, chave crua sem derivação, versão, tamanho e o `flash` movido como no web2py (com o cookie regravado sem ele); roteador sem dupla decodificação; estáticos: travessia, link para fora, oculto, pasta, 405, HEAD, 304 e arquivo fechado sem leitura; app: hooks, erro 400+ com a página da aplicação, 500 sem detalhe com id no log, sessão no redirect e não no 500, cookie adulterado regravado, corpo em fluxo e uploads fechados, injeção de cabeçalho; servidor com socket real: limite de threads, cliente lento derrubado sem stderr, cabeçalho com `_` descartado, `Server: SSS` e parada com a requisição em andamento terminada, sem thread sobrando; templates: toda view real compila, saída byte a byte igual à gravada do web2py num template com todas as construções `[CR-021f1]`, escape e `Markup`, `include`/`extend` recusando travessia, absoluto, expressão, link para fora e tags não usadas, `pass` faltando/sobrando, sintaxe e cache refeito quando a view ou um incluído muda |
| `test_webapp.py` `[CR-021e]` | `URL` igual à saída gravada do `gluon.html.URL` (posicionais, keywords e extensão herdada), devolvendo `Markup` sem nada que exija escape mesmo com entrada hostil, e recusando nomes e caminho estático fora do formato; registro dos controllers igual aos arquivos, `dev` só em DEV e só com o arquivo presente (DEV instalado pelo pacote, CR-021f3); só funções do próprio módulo viram rota (nomes importados nunca); hooks: cabeçalhos de segurança, 413 antes de ler o corpo, Origin e CSRF (formulário e `X-CSRF-Token`); `csrf_field` com o mesmo HTML do web2py; `require_login` com `next` |
| `test_app_context.py` `[CR-021c]` | `set_config`/`get_config`/`require_config` (falha com "Configuracao ausente"); nenhum `.py` de `src/`, inclusive subpacotes, importa `gluon`, nem dentro de função (varredura por AST, com caso negativo do import tardio); desde o CR-021f1, nenhum `.py` da aplicação (scripts, testes, `dev/`) nem do `bin/`; nenhum código (`bin/`, `src/sss/web/controllers/`, `scripts/`, `src/`, `tests/`, `tools/`) lê `current.sss_cfg` ou `current.repo_factory` (regressão do `bin/start_local.sh`) |
| `test_frontend_components.py` `[CR-021]` | Nenhuma view com sintaxe do Alpine e o `alpine.min.js` ausente; todo `data-component` com registro `SSS.component` e todo registro usado, sem duplicata; `src/sss/web/static/js/app/` sem `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `new Function` e Alpine; `dom.js` como primeiro script do layout, sem o Alpine; tipos do toast iguais aos modificadores `.sss-toast-*` do CSS; `data-types` da regra de agendamento só com os tipos de `schedules_service.TYPE_LABELS`, todos cobertos |
| `test_color_contrast.py` | Todo par texto/fundo dos tokens de `sss.css` com contraste WCAG AA (≥ 4,5:1), nos modos claro e escuro |
| `test_db_conn.py` `[F7.0]` | Com módulos falsos de driver: cadeia `auto` Thin → Thick → cx_Oracle, parada em erro de autenticação, valores forçados, senha fora de argv/ambiente/log, mapa de erros por driver e modo, inclusive *call timeout* e erros de failover (CR-007, R-12), reconexão sem `sleep`; cálculo do orçamento de abertura do DSN descritor (CR-008, R-17); sondagem com a conta do papel que conecta (`--user` no argv, senha só no stdin; o `connect` do papel `monitor` sonda com a conta do monitor, F9.1d); primeira conexão em INFO (`Conectando`/`Conexao estabelecida`) e o WARN `Tentando reconexao` só nas reconexões (F9.1d) |

5. Cada correção de defeito acompanha um teste de regressão.
6. **Homologação real no DEV:** `dev/homologation/tools/capture_evidence.js` executa os casos de teste do manual no navegador contra o DEV (Oracle e agente reais) e confere o resultado esperado de cada passo na própria página; `build_evidence_docx.py` gera o documento de evidências (`docs/homologation/`). Use-o depois de mudanças de tela ou de contrato JavaScript × servidor, que os testes `unittest` não exercitam (o JavaScript não roda neles).

---

## 8. Checklist Obrigatório antes de Entregar

- [ ] Nenhum recurso de Python posterior à 3.6.0 nem módulo removido nas versões novas (§2.1).
- [ ] Nenhuma dependência nova; o driver só é importado em `db_conn.py` e `probe_driver.py`.
- [ ] SQL: só em `src/sss/persistence/oracle/` e `init_db.py`; Oracle 11gR2 sem sintaxe 12c+; apenas binds e identificadores via `sql_ident`; `rowcount` checado em toda transição.
- [ ] Toda transação com `COMMIT`/`ROLLBACK` explícitos; lock de linha com `FOR UPDATE WAIT n` (n ≤ 5).
- [ ] Nenhum identificador novo acima de 30 caracteres; registro de identificadores atualizado.
- [ ] Processos: primitivas de SO só em `src/sss/platform/os_platform/` (somente POSIX), exceto `resource.setrlimit` em `run`, `os.killpg` em `term`/`kill`, leitura de `/proc/<pid>/stat` em `_identity` e `/proc/<pid>/cwd`/`pwdx` em `stop-ticket` no helper; pasta de saída só pelo helper e por `log_paths.output_dir`, pasta de trabalho só pelo helper e por `log_paths.script_work_dir` (CR-019), sem zip parcial e sem alterar o resultado do ticket (CR-012); allowlist lógica, `path_guard`, `env_builder`, sem PIPE e encerramento escalonado; caminhos de log só por `log_paths`.
- [ ] Web: guarda de login/RBAC, CSRF em POST, saída escapada, sem `XML()` com dado; no navegador, texto só por `textContent` e componentes sem framework (§2.3).
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
   - tests/unit/<camada>/test_exemplo.py (OK / FALHA / NÃO TESTADO: motivo)

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
