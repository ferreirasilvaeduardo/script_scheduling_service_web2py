# Script Scheduling Service (SSS) — README.md

Serviço web corporativo para gestão, agendamento e execução distribuída de rotinas em Python e Shell em servidores Unix/Linux restritos, integrado ao Oracle Database >= 11gR2 e com arquitetura multi-ambiente e multi-nó.

> **Autoridade documental:** este README é a autoridade máxima de **negócio, dados e algoritmos**. O `AGENTS.md` é a autoridade sobre **como codificar**. Em conflito sobre regra de negócio ou modelo de dados, prevalece este documento. Em caso de lacuna, o desenvolvedor ou agente deve **parar e perguntar**, sem presumir.

---

## 1. Princípio Fundamental de Negócio

No SSS, **nenhuma tarefa roda de forma avulsa ou desvinculada de ambiente**.

Os scripts do catálogo não pertencem a um único ambiente. Cada script declara em quais ambientes está homologado (`tbsss_script_amb`). A associação concreta acontece na criação do **Ticket**, que registra de forma imutável:

* o solicitante autenticado e o IP de origem;
* o script e o ambiente alvo, validados contra perfil, ambiente, script e homologação;
* o **snapshot imutável** das respostas e do `argv` compilado no momento da criação;
* o agente executor, o PID, o instante de início do processo e os timestamps de auditoria;
* o histórico de status, o motivo, o código de retorno e o log completo em `CLOB`.

---

## 2. Pilha Tecnológica e Restrições de Runtime

### 2.1 Linguagem e framework

* **Python 3.6** com o framework **web2py**. A versão do web2py é homologada e fixada no repositório.
* É proibido usar recursos de Python 3.7+. A lista normativa completa está no `AGENTS.md` §2.1.

### 2.2 Banco de dados

* **Oracle Database 11gR2** como piso de compatibilidade. Todo SQL e DDL deve rodar no 11gR2, mesmo que o servidor seja mais novo.
* **Charset:** AL32UTF8. Toda coluna textual usa `VARCHAR2(N CHAR)`.
* **Teto de 30 caracteres** para todo identificador, inclusive após a expansão do prefixo (§9).

### 2.3 Conectividade (dependências homologadas pré-instaladas)

| Componente | Versão permitida | Observação |
|---|---|---|
| Driver | `python-oracledb < 2.0` (série 1.x), em modo **Thick** | A série 2.x exige Python 3.7+ |
| Driver alternativo | `cx_Oracle 8.3` | — |
| Cliente C | **Oracle Instant Client 19.x** | O IC 21c/23ai não conecta ao 11gR2 |

* O modo **Thin** é proibido porque não suporta o 11g.
* **Carregamento no Linux:** o Instant Client deve estar no caminho de bibliotecas **antes** de o processo Python iniciar, via `ldconfig` (preferencial) ou `LD_LIBRARY_PATH` exportado pelos launchers `bin/sss-web.sh` e `bin/sss-scheduler.sh`. No Linux, `init_oracle_client(lib_dir=...)` não tem efeito e deve ser chamado sem `lib_dir`.
* **Desenvolvimento em macOS:** `oracle_client_lib_dir` só é usado em macOS/Windows. O IC 19 para macOS existe apenas para Intel (x86_64). Em Apple Silicon, use Python x86_64 sob Rosetta ou um container/VM Linux x86_64. Valide no portal da Oracle antes de montar o ambiente.
* `modules/oracle_conn.py` é a **única** porta de acesso ao banco. Ele contém o *shim* que abstrai `oracledb` e `cx_Oracle` (exceções, tipos de bind, pool, `init_oracle_client`).
* **Toda conexão deve:**
  * usar `autocommit = False`;
  * definir `call_timeout` (`call_timeout_ms` no config);
  * preencher `module`, `action` e `client_identifier` para rastreabilidade pelo DBA (por exemplo, `module='SSS_SCHED'`, `action='CLAIM'`, `client_identifier=<agent_id ou login>`).
* **Reconexão:** em erros de rede (ORA-03113, ORA-03114, ORA-03135, ORA-12541, ORA-12170, DPI-1080), o daemon reconecta com *backoff* exponencial de 1 s a 60 s, registrando WARN a cada tentativa.

### 2.4 Frontend

* HTML5, **Bootstrap 5.3.8** e **Alpine.js (build CSP)**, servidos exclusivamente de `static/` com fontes locais.
* Não há CDN, Google Fonts nem `@import` remoto.
* O build CSP do Alpine é obrigatório porque a política `script-src 'self'` proíbe `unsafe-eval`. Toda lógica de componente fica registrada via `Alpine.data()` em arquivos `.js` de `static/js/app/`, sem expressões complexas inline.

#### 2.4.1 Contrato de responsividade

* **Larguras suportadas:** de 360 px (celular) a 1440 px ou mais (desktop), usando os breakpoints do Bootstrap 5.3.8.
* **Sem rolagem horizontal da página:** em 360, 414, 768, 1024 e 1440 px, nenhuma página pode ficar mais larga que a tela (`scrollWidth <= clientWidth` no documento).
* **Conteúdo largo rola dentro do próprio container:**
  * tabelas ficam dentro de `.table-responsive`, que é posicionado para conter filhos absolutos, como o `.visually-hidden` dos badges;
  * logs e comandos ficam em `<pre>` com `white-space: pre-wrap` e rolagem própria.
* **Texto sem ponto de quebra** (caminhos, identificadores, argv) usa `overflow-wrap: anywhere`. Colunas flexíveis de grid usam `minmax(0, 1fr)`, nunca `1fr` puro.
* **Barras de ações e de filtros** usam `flex-wrap`: nenhum botão ou campo fica fora da área visível.
* **Verificação:** toda tela nova ou alterada é conferida nas cinco larguras acima antes da entrega, no DevTools ou com Playwright local. O Playwright fica fora do repositório (AGENTS §2.2).

### 2.5 Backend de dados (estratégia UI-first)

* Toda persistência passa por **contratos de repositório** em `modules/repo_*.py`: classes abstratas por agregado, sem SQL.
* O contrato tem duas implementações, selecionadas por `[app] data_backend` via `modules/repo_factory.py`:

| Backend | Uso | Implementação |
|---|---|---|
| `FAKE` | Desenvolvimento da UI e testes unitários | `modules/repo_fake/`: memória do processo, seed determinístico e `threading.Lock` por agregado |
| `ORACLE` | Homologação e produção | `modules/repo_oracle/`: único local com SQL |

* Os controllers e services **não sabem** qual backend está ativo.
* **Paridade obrigatória:** o FAKE emula a semântica do Oracle que o código consome. Isso inclui `UPDATE` condicional com `rowcount` (transição perdida gera `RepoConflito`), unicidade (`RepoViolacao`), `ON DELETE CASCADE`, triggers de imutabilidade, paginação e ordenação idênticas.
* **Exceções de contrato** (`modules/repo_errors.py`): `RepoErro`, `RepoNaoEncontrado`, `RepoConflito`, `RepoViolacao` e `RepoIndisponivel`.
* A suíte `scripts/test_repo_contract.py` roda **a mesma bateria** contra os dois backends. Contra ORACLE, ela só executa se `SSS_TEST_DSN` estiver definido.
* **Trava de ambiente:**
  * `[app] sss_env` aceita `DEV`, `HML` ou `PROD`.
  * `data_backend = FAKE` com `sss_env != DEV` **aborta a subida** com CRITICAL.
  * O FAKE exige servidor web de processo único (o servidor de desenvolvimento do web2py). Com múltiplos workers, cada um teria um estado diferente.
* O daemon (`run_scheduler.py`) **exige** `ORACLE`. Com `FAKE`, ele aborta.

---

## 3. Topologia e Estrutura do Repositório

### 3.1 Processos

| Processo | Execução | Responsabilidade |
|---|---|---|
| **Web** (1..N nós) | web2py sob WSGI corporativo | UI, autenticação, RBAC, criação e cancelamento de tickets, cadastros |
| **Scheduler/Agente** (1 por servidor executor) | `python web2py.py -S script_scheduling_service -M -R applications/script_scheduling_service/scripts/run_scheduler.py` | Desdobro de agendamentos, claim, execução, heartbeat, cancelamento, coleta de log |

Regras de topologia:

* É proibido instanciar o scheduler em threads dos workers web.
* O daemon é **single-threaded**: um laço de eventos com `time.sleep`/`select`. Essa decisão torna seguro o uso de `preexec_fn` (§8.4).
* O nó web **nunca** sinaliza processos do sistema operacional.
* `models/*.py` deve ser leve, pois é carregado pelo daemon com `-M`. Esses arquivos não podem executar DDL, abrir conexão no import nem fazer I/O pesado.

### 3.2 Estrutura de diretórios

```text
bin/
  sss-web.sh                  # exporta LD_LIBRARY_PATH/TZ e sobe o WSGI
  sss-scheduler.sh            # exporta LD_LIBRARY_PATH/TZ e sobe o daemon
applications/script_scheduling_service/
  controllers/                # default.py (login), tickets.py, logs.py, agendamentos.py, admin_*.py, auditoria.py, dev.py (somente DEV)
  models/
    00_config.py              # carga e validação de config (sem I/O de banco)
    10_security.py            # sessão, cabeçalhos HTTP, CSRF, guarda RBAC
  modules/
    sss_config.py             # parser e validação tipada do config.ini e do secrets.cfg
    sss_logging.py            # configuração de logging (§13)
    oracle_conn.py            # shim de driver, pool, conexão dedicada do daemon
    sql_ident.py              # registro de identificadores, validação de owner/prefixo, nomes qualificados
    repo_errors.py            # exceções de contrato (§2.5)
    repo_factory.py           # seleção do backend FAKE/ORACLE
    repo_*.py                 # contratos abstratos por agregado (sem SQL)
    repo_fake/                # implementação em memória + seed (somente DEV)
    repo_oracle/              # implementação SQL (único local com SQL)
    auth_service.py           # autenticação, bloqueio, revalidação de sessão
    ticket_service.py         # criação, cancelamento e reexecução de ticket (§5)
    ui_menu.py                # menu por permissão
    ui_helpers.py             # formatação de status, datas e paginação para as views
    rbac.py                   # decisões de autorização (§4.3)
    security.py               # hash de senha, CSRF, comparação em tempo constante
    params_compiler.py        # validação de respostas e compilação do argv (§6)
    cron_parser.py            # parser CRON de 5 campos (§7.3)
    recurrence.py             # cálculo da próxima execução e misfire (§7)
    path_guard.py             # validação de interpretador e script (§8.5)
    env_builder.py            # montagem do ambiente limpo (§8.6)
    executor.py               # spawn, timeout, kill, finalização
    log_pump.py               # arquivo local -> CLOB com mascaramento (§8.10)
    masking.py                # mascaramento de segredos e PII
    scheduler_loop.py         # laço principal do daemon
    audit.py                  # escrita em tbsss_auditoria
  scripts/
    init_db.py                # bootstrap idempotente de DDL e seed (§11)
    run_scheduler.py          # entrypoint do daemon
    purge.py                  # retenção (§11.3)
    test_*.py                 # testes unittest (AGENTS.md §7)
  static/bootstrap/  static/js/alpine.min.js (build CSP)  static/js/app/  static/css/  static/img/  static/fonts/
  views/                      # layout.html, components/*.html, <controller>/*.html
  instance/config.ini         # configuração sem segredos (§12)
  dev/scripts/                # árvore de scripts de exemplo para DEV/testes (nunca implantada)
docs/
  prompts/                    # prompts de execução faseada (UI-first)
/etc/sss/secrets.cfg          # segredos, 0600, fora do repositório (§4.1)
```

---

## 4. Segurança, Segredos, Sessão e RBAC

### 4.1 Gestão de segredos

* **Nenhum segredo** reside no `config.ini`, no repositório ou no banco.
* Os segredos ficam em `secrets_file` (padrão `/etc/sss/secrets.cfg`). Na inicialização, web e daemon validam o arquivo e **recusam a subida** caso ele:
  * não seja um arquivo regular;
  * tenha dono diferente de `os.geteuid()`;
  * tenha `mode & 0o077 != 0`.

```ini
[oracle]
password = ...

[web]
cookie_key = ...               ; chave da sessão em cookie cifrado, igual em todos os nós web

[ambiente:PRODUCAO]
user = app_prod
password = ...

[ambiente:HOMOLOGACAO]
user = app_hml
password = ...
```

* `tbsss_ambientes.conexao` armazena **somente o DSN** (Easy Connect `host:porta/servico` ou alias TNS), nunca credenciais. A CK `ck_tbsss_amb_conexao` rejeita qualquer valor contendo `@`.
* Valores de segredo carregados são registrados no módulo `masking.py`. Eles são substituídos por `****` em todo log do daemon, do web e no `log_output`.

### 4.2 Autenticação e sessão web

* **Hash de senha:**
  * `hashlib.pbkdf2_hmac('sha256', ...)` com 200.000 iterações e salt de 16 bytes (`secrets.token_bytes`).
  * Formato: `pbkdf2_sha256$200000$<salt_hex>$<hash_hex>`.
  * A comparação usa `hmac.compare_digest`.
  * Se as iterações armazenadas forem menores que o valor vigente, o hash é refeito no próximo login bem-sucedido.
* **Política de senha:** mínimo de 12 caracteres. A senha nunca é registrada em log nem devolvida pela UI.
* **Proteções do login:**
  * Mensagem de erro genérica.
  * Para login inexistente, calcula-se um hash fictício, equalizando o tempo de resposta.
  * Após `login_max_tentativas` falhas consecutivas, a conta fica bloqueada (`bloqueado_ate = SYSDATE + login_bloqueio_s/86400`).
  * Um sucesso zera `tentativas_falha` e grava `ultimo_login`.
  * Login OK, falha e bloqueio são auditados.
* **Sessão:**
  * Armazenada em **cookie cifrado** do web2py (`session.connect(request, response, cookie_key=<secrets>)`). Isso dispensa DAL e funciona com N nós web sem sessão aderente.
  * O payload é mínimo: `usuario_id`, `login`, `perfil_id`, `perm_versao`, `csrf_token` e `ultimo_acesso`.
  * A sessão é renovada no login (`session.renew()`).
  * O timeout por inatividade é `session_idle_timeout_s`.
  * Cookies com `HttpOnly` e `Secure`.
  * **`SameSite` no Python 3.6:** `http.cookies.Morsel` só aceita o atributo `samesite` a partir do 3.8. No 3.6, a proteção cross-site se apoia em duas camadas:
    * o token CSRF;
    * a checagem obrigatória de `Origin`, ou de `Referer` quando `Origin` estiver ausente, contra `[web] allowed_origins` em todo `POST`.

    Requisição sem nenhum dos dois cabeçalhos é rejeitada com 403.
* **Revalidação a cada requisição:** uma única query por PK junta `tbsss_usuarios` e `tbsss_perfis` e verifica `usuario.ativo`, `perfil.ativo` e `perfil.perm_versao`. Se a versão divergir da sessão, as permissões são recarregadas. Se o usuário ou o perfil estiver inativo, a sessão é encerrada.
* **CSRF:** token sincronizador por sessão.
  * Formulários enviam o campo oculto `_csrf`.
  * Chamadas `fetch` do Alpine enviam o cabeçalho `X-CSRF-Token`.
  * Todo `POST` valida o token com `hmac.compare_digest`.
  * `GET` nunca altera estado.
* **Cabeçalhos HTTP obrigatórios:**
  * `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'`
  * `X-Content-Type-Options: nosniff`
  * `X-Frame-Options: DENY`
  * `Referrer-Policy: same-origin`. Com `no-referrer`, o navegador envia `Origin: null` em POST de formulário (especificação Fetch), o que inviabiliza a checagem de `Origin` descrita acima. `same-origin` continua omitindo o `Referer` em navegação para fora do site.
  * `Cache-Control: no-store` em páginas autenticadas
* **IP de origem:** usa `request.env.remote_addr`. O `X-Forwarded-For` só é aceito se o `remote_addr` constar em `trusted_proxies`.
* **XSS:**
  * Saída sempre escapada (`{{=valor}}`).
  * É proibido `XML()` com dado de usuário.
  * No Alpine, apenas `x-text`; é proibido `x-html`.

### 4.3 RBAC

#### A. Regras fundamentais

* **1 usuário → 1 perfil** (`perfil_id NOT NULL`).
* **Dimensões de acesso:**
  1. **Ambiente** (`tbsss_perfil_amb`): ambientes que o perfil enxerga e seleciona.
  2. **Funcionalidade** (`tbsss_perfil_func`): telas e ações.
  3. **Script** (`tbsss_perfil_scr`): rotinas que o perfil pode executar.
  4. **Homologação** (`tbsss_script_amb`): em quais ambientes cada script **pode** rodar. Esta é uma propriedade do catálogo, não do perfil.
* **Decisão composta para executar** (`rbac.pode_executar(usuario, script, ambiente)`), verdadeira somente se todas as condições forem atendidas:
  * usuário ativo **e** perfil ativo;
  * script ativo **e** ambiente ativo **e** par (script, ambiente) presente em `tbsss_script_amb`;
  * perfil admin, **ou** (funcionalidade `EXEC_SCRIPT` **e** ambiente em `perfil_amb` **e** script em `perfil_scr`).
* **Perfis administrativos** (`is_admin = 'S'`) dispensam as dimensões 1, 2 e 3. Eles **não** dispensam as flags `ativo` nem a homologação (dimensão 4).
* Toda ação do servidor reautoriza com os IDs recebidos. Campos ocultos e IDs do cliente nunca são confiáveis.
* **`perm_versao`:** qualquer alteração em perfil, na matriz do perfil, em `is_admin` ou em `ativo` incrementa `tbsss_perfis.perm_versao` **na mesma transação**.

#### B. Proteção do último administrador

Qualquer operação que possa reduzir o conjunto de administradores ativos executa, na mesma transação e antes da alteração:

```sql
SELECT u.id
  FROM {owner}.tbsss_usuarios u
  JOIN {owner}.tbsss_perfis p ON p.id = u.perfil_id
 WHERE u.ativo = 'S' AND p.ativo = 'S' AND p.is_admin = 'S'
   FOR UPDATE OF u.ativo WAIT 5
```

As operações cobertas são: desativar usuário, trocar o perfil de usuário, desativar perfil e remover `is_admin`. Se o conjunto resultante ficar vazio, a operação é rejeitada com `ROLLBACK`. O lock serializa operações concorrentes.

* **No contrato de repositório**, a proteção faz parte da própria operação de alteração (`perfis_alterar`; no F4.3, a de usuários): lock, cálculo do conjunto resultante e `UPDATE` ou rejeição, numa só chamada. O service nunca faz check-then-act com duas chamadas soltas.
* A rejeição é `RepoViolacao(constraint='sss_ultimo_admin')`, uma regra de aplicação e não uma constraint do banco. A UI exibe "Operação negada: não pode restar nenhum administrador ativo."
* Um perfil `is_admin = 'S'` sem usuários ativos não conta como administrador ativo.

#### B.1 Matriz de permissões na UI (`admin_perfis`)

* **Um único POST** com as três listas (funcionalidades, ambientes e scripts), revalidado inteiro no servidor.
* **Concorrência:** a tela envia o `perm_versao` lido. `matriz_salvar` só grava se ele não tiver mudado; senão, `RepoConflito`.
* **Validação dos IDs:**
  * um ID inexistente ou não numérico rejeita a operação inteira;
  * só itens **ativos** podem ser adicionados;
  * associações já existentes a itens **inativos** aparecem marcadas e desabilitadas e são **preservadas** pelo servidor.
* **Auditoria `PERM_ALTERAR`:** o `detalhe` é o diff `+EXEC_SCRIPT, -VER_LOGS, +amb:PRODUCAO, -scr:carga_diaria` (por dimensão, rótulo e sinal). Salvar sem mudança não incrementa `perm_versao` nem audita. O resumo do modal de confirmação usa o mesmo formato.
* **Perfil administrativo:** a matriz continua editável e registrada, com um aviso de que o perfil dispensa as dimensões 1 a 3 (mas não a homologação). Ela passa a valer se `is_admin` for removido.
* **Desativar perfil:** o modal mostra os usuários ativos afetados, que têm a sessão encerrada no próximo request pela revalidação (§4.2).

#### C. Escopo das funcionalidades operacionais

| Funcionalidade | Escopo |
|---|---|
| `EXEC_SCRIPT` | Criar tickets e reexecutar tickets próprios, sujeito a `pode_executar` |
| `VER_LOGS` | Tickets de ambientes autorizados ao perfil (admin: todos). Respostas de parâmetros `sensivel = 'S'` aparecem mascaradas |
| `CANC_TICKET` | Cancelar qualquer ticket de ambiente autorizado. **Sem** esta funcionalidade, o solicitante com `EXEC_SCRIPT` pode cancelar apenas os próprios tickets |
| `CAD_AGENDAMENTOS` | Criar e editar regras. O `usuario_id` da regra é o criador, e cada desdobro roda sob os privilégios vigentes desse usuário |

#### D. Catálogo canônico de funcionalidades (seed)

| Módulo | Código | Nome de exibição | Finalidade |
| :--- | :--- | :--- | :--- |
| `OPERACAO` | `EXEC_SCRIPT` | Disparar Scripts | Preencher questionários e abrir tickets |
| `OPERACAO` | `VER_LOGS` | Consultar Logs | Visualizar logs e histórico em tempo quase real |
| `OPERACAO` | `CANC_TICKET` | Cancelar Tickets | Cancelar tickets de terceiros em ambientes autorizados |
| `ADMIN` | `CAD_USUARIOS` | Gestão de Usuários | Gerenciar operadores e credenciais |
| `ADMIN` | `CAD_PERFIS` | Gestão de Perfis | Gerenciar perfis e matrizes de permissão |
| `ADMIN` | `CAD_AMBIENTES` | Gestão de Ambientes | Gerenciar ambientes e DSNs |
| `ADMIN` | `CAD_SCRIPTS` | Gestão de Scripts | Cadastrar rotinas e homologação por ambiente |
| `ADMIN` | `CAD_PARAMETROS` | Dicionário de Parâmetros | Gerenciar perguntas e flags reutilizáveis |
| `ADMIN` | `CAD_AGENDAMENTOS` | Regras de Agendamento | Criar e gerenciar recorrências |
| `ADMIN` | `VER_AUDITORIA` | Auditoria | Consultar a trilha de auditoria e os agentes |

### 4.4 Auditoria

Toda ação sensível grava uma linha em `tbsss_auditoria` **na mesma transação** da ação:

* login (OK, falha, bloqueio) e logout;
* criação, cancelamento e reexecução de ticket;
* inserção, alteração e desativação em qualquer cadastro;
* alteração de matriz de permissão;
* pausa automática de agendamento;
* início e fim de agente;
* purge.

O campo `detalhe` nunca contém segredos nem valores de parâmetros sensíveis.

**Cadastros** (padrão em `docs/PADRAO_CRUD_ADMIN.md`):

| Situação | Ação | `detalhe` |
|---|---|---|
| Inclusão | `CAD_INSERIR` | `campo: valor` dos campos informados |
| Alteração | `CAD_ALTERAR` | `campo: antigo → novo`, só dos campos que mudaram (salvar sem mudança não audita) |
| Desativação | `CAD_DESATIVAR` | `ativo: S → N`, mais o impacto (ex.: `agendamentos ativos afetados: 2`) |
| Reativação | `CAD_ALTERAR` | `ativo: N → S` (não existe ação `CAD_REATIVAR`) |

Os valores passam pelo `masking.py` e o texto é limitado a 1.000 caracteres.

---

## 5. Ciclo de Vida do Ticket

### 5.1 Estados e transições

| Estado | Significado |
|---|---|
| `PENDING` | Aguardando claim (`scheduled_at <= SYSDATE`) |
| `RUNNING` | Reservado e em execução no agente dono |
| `SUCCESS` | Encerrado com código 0 |
| `FAILED` | Erro, timeout, falha de pré-validação, nó offline, órfão etc. |
| `CANCELLED` | Interrompido por solicitação explícita |

| Transição | Executor | Condição SQL obrigatória |
|---|---|---|
| `PENDING → RUNNING` | Agente (claim) | `WHERE status = 'PENDING' AND cancel_requested = 'N'` |
| `PENDING → CANCELLED` | Web | `WHERE status = 'PENDING'` |
| `RUNNING → SUCCESS / FAILED / CANCELLED` | Agente dono | `WHERE status = 'RUNNING' AND agente_id = :agente_id` |
| `RUNNING → FAILED (NODE_OFFLINE)` | Qualquer agente | `heartbeat_at` defasado (§8.8) |

Os estados `SUCCESS`, `FAILED` e `CANCELLED` são **terminais e imutáveis**. Toda transição é um `UPDATE` condicional. Se `rowcount = 0`, a transição perdeu a corrida e o código deve tratar o caso, nunca ignorá-lo.

### 5.2 Catálogo de `status_motivo` e `return_code`

| Status | `status_motivo` | `return_code` |
|---|---|---|
| `SUCCESS` | `EXIT_OK` | `0` |
| `FAILED` | `EXIT_ERROR` | código do processo (`> 0`) |
| `FAILED` | `KILLED_SIGNAL` | `128 + signum` (morte por sinal não solicitado) |
| `FAILED` | `TIMEOUT` | `-3` |
| `FAILED` | `NODE_OFFLINE` | `-2` |
| `FAILED` | `ORPHAN_PROCESS` | `-2` |
| `FAILED` | `FENCED` | `-2` |
| `FAILED` | `PRECHECK_FAILED` | `-4` |
| `FAILED` | `SPAWN_ERROR` | `-4` |
| `FAILED` | `LOG_LIMIT` | `-5` |
| `FAILED` | `SHUTDOWN` | `-6` |
| `CANCELLED` | `CANCEL_USER` | `-1` |

* `OWNERSHIP_LOST` é um **evento de log** do agente. Ele nunca é gravado no ticket, que já foi finalizado por outro nó.
* `Popen.returncode` negativo (morte por sinal) é convertido para `128 + abs(returncode)`.

### 5.3 Prioridade

* Escala de **1 (mais alta) a 4 (mais baixa)**, padrão 2.
* Prioridade 1 é reservada a perfis admin.
* A fila ordena por `prioridade`, depois `scheduled_at` e depois `id`.

### 5.4 Criação manual de ticket (transação única)

1. Validar o CSRF e `rbac.pode_executar(usuario, script_id, ambiente)`.
2. Carregar o vínculo `tbsss_script_param` + `tbsss_parametros` (ativos) do script.
3. Validar as respostas e compilar o snapshot (§6). Em caso de erro, retornar o erro por campo, sem gravar nada.
4. Gravar o `scheduled_at` informado (opcional, `>= SYSDATE`, padrão `SYSDATE`).
5. `INSERT INTO tbsss_tickets (...) VALUES (...) RETURNING id INTO :out_id`, com `parametros_enviados` contendo o JSON do snapshot.
6. `INSERT` em `tbsss_ticket_resp` via `executemany`, com os valores **resolvidos** (após a precedência).
7. Auditoria `TICKET_CRIAR` e `COMMIT`. Em qualquer exceção, `ROLLBACK`.

### 5.5 Reexecução

* Cria um novo ticket com `parent_ticket_id = <original>`.
* As respostas resolvidas do original (`tbsss_ticket_resp`) são **recompiladas contra o catálogo vigente**, gerando um novo snapshot.
* A reexecução exige `pode_executar` vigente.
* O snapshot original permanece intocado.

### 5.6 Cancelamento distribuído

**No nó web (uma transação):**

```sql
UPDATE {owner}.tbsss_tickets
   SET cancel_requested = 'S'
 WHERE id = :id AND status IN ('PENDING', 'RUNNING');

UPDATE {owner}.tbsss_tickets
   SET status = 'CANCELLED', status_motivo = 'CANCEL_USER',
       return_code = -1, finished_at = SYSDATE
 WHERE id = :id AND status = 'PENDING';
```

* Se o primeiro `UPDATE` afetar 0 linhas, o ticket já é terminal e o sistema informa o usuário.
* Se o segundo afetar 0 linhas, o ticket está `RUNNING` e o agente dono trata o cancelamento.
* A operação é auditada e confirmada com `COMMIT`.

**No agente dono:** a cada `cancel_poll_interval_s`, executa a varredura combinada da §8.7. Ao encontrar `cancel_requested = 'S'` em ticket próprio:

1. `os.killpg(pgid, signal.SIGTERM)`, com o `pgid` obtido no spawn (igual ao PID, por causa de `start_new_session=True`).
2. Aguardar até `kill_grace_s`, consultando `Popen.poll()`.
3. Se o processo persistir, `os.killpg(pgid, signal.SIGKILL)` e então `Popen.wait()`.
4. Fazer o flush final do log (§8.10).
5. `UPDATE ... SET status = 'CANCELLED', status_motivo = 'CANCEL_USER', return_code = -1, finished_at = SYSDATE WHERE id = :id AND agente_id = :agente_id AND status = 'RUNNING'`, seguido de `COMMIT`.

Se o processo terminou sozinho **antes** de o agente sinalizá-lo, prevalece o resultado real (`SUCCESS` ou `FAILED`).

O `ProcessLookupError` no `killpg` é tratado como "grupo já encerrado".

---

## 6. Parâmetros, Validação e Compilação do Snapshot

### 6.1 Precedência de valores

Para cada parâmetro vinculado ao script, nesta ordem:

1. Resposta enviada explicitamente pelo usuário (ou, no agendamento, o valor em `parametros_json`).
2. `tbsss_script_param.valor_padrao_sub`.
3. `tbsss_parametros.valor_padrao`.
4. Sem valor: se `obrigatorio = 'S'`, gera erro de validação. Se for opcional, aplica a regra da estratégia (§6.3).

Os valores padrão (2 e 3) **também** passam pela validação da §6.2.

### 6.2 Validação por `tipo_componente`

Para todos os tipos:

* o valor é texto UTF-8 com até 500 caracteres;
* rejeita NUL e caracteres de controle `\x00-\x1f` e `\x7f`;
* recebe `strip()` antes da validação.

| Tipo | Regra |
|---|---|
| `TEXT` | Se houver `regex_validacao`, aplica `re.fullmatch` |
| `NUMBER` | `^-?\d{1,18}(\.\d{1,6})?$` |
| `DATE` | `datetime.strptime(valor, '%Y-%m-%d')`, emitido como `YYYY-MM-DD` |
| `SELECT` | O valor deve ser uma chave de `opcoes_json` (objeto JSON `{"valor": "Rótulo"}`, parseado em Python) |
| `CHECKBOX` | Aceita `true`, `false`, `1` e `0` (sem distinção de maiúsculas), normalizados para booleano |

**Governança de `regex_validacao`:**

* O padrão é compilado no cadastro, que o rejeita se não compilar.
* Também é rejeitado padrão com quantificador aninhado, detectado pela heurística `\([^)]*[+*][^)]*\)[+*{]`, para mitigar ReDoS. O Python 3.6 não oferece timeout de regex.
* Somente admin cadastra padrões.

### 6.3 Estratégias de montagem (`tipo_param`)

* **`NOMEADO`**: todo parâmetro vinculado exige `param_nomeado`, validado no vínculo. Por parâmetro, em ordem de `ordem`:
  * `CHECKBOX` verdadeiro emite apenas `flag`. Falso é omitido.
  * Opcional sem valor é omitido.
  * Flag longa (`--x`) emite dois tokens, `--x` e `valor`. Se o valor começar com `-`, emite um token único `--x=valor`.
  * Flag curta (`-x`) emite dois tokens, `-x` e `valor`. Valor iniciado em `-` é **rejeitado** na validação, porque não há forma segura universal.
* **`SEQUENCIAL`**: argumentos posicionais ordenados por `ordem`, ignorando `param_nomeado`.
  * Opcional sem valor emite `""`, preservando a posição.
  * `CHECKBOX` emite `"1"` ou `"0"`.
  * Valor iniciado em `-` é **rejeitado**, exceto `NUMBER` negativo.
* **`NENHUM`**: nenhum argumento. Vincular parâmetros a esse script é rejeitado no cadastro.

### 6.4 Montagem do `argv`

```text
/usr/bin/python3 -> ["/usr/bin/python3", "-I", <script_real>, ...args]
/bin/bash        -> ["/bin/bash", <script_real>, ...args]
/bin/sh          -> ["/bin/sh", <script_real>, ...args]
```

`<script_real>` é o caminho absoluto resolvido pela §8.5.

### 6.5 Snapshot imutável (`tbsss_tickets.parametros_enviados`)

JSON serializado com `json.dumps(obj, ensure_ascii=False, sort_keys=True)`:

```json
{
  "versao": 1,
  "script_id": 12,
  "script_nome": "carga_faturas",
  "comando_real": "/usr/bin/python3",
  "path_file": "faturamento/carga_faturas.py",
  "script_real": "/opt/automacoes/scripts/faturamento/carga_faturas.py",
  "tipo_param": "NOMEADO",
  "argv": ["/usr/bin/python3", "-I", "/opt/automacoes/scripts/faturamento/carga_faturas.py", "--data", "2026-10-13"],
  "respostas": {"data_ref": "2026-10-13"},
  "sensiveis": [],
  "compilado_em": "2026-10-13 10:47:00"
}
```

* O snapshot é **compilado na criação do ticket** (manual ou desdobro). O agente **nunca** recompila nem lê `tbsss_script_param` e `tbsss_parametros` para executar.
* **Defesa em profundidade no claim:** o agente revalida o snapshot (§8.4, passo 1).
* `tbsss_ticket_resp` é a cópia normalizada das respostas resolvidas, usada em relatórios, auditoria e reexecução. O executor não a utiliza.
* **Parâmetros sensíveis** (`sensivel = 'S'`):
  * Os valores são listados em `"sensiveis"` (por `codigo`).
  * Ficam mascarados na UI, nos logs do daemon e no `log_output`.
  * **Continuam visíveis em `ps` no servidor e no banco.** Por isso, é **proibido** cadastrar parâmetro destinado a senha ou credencial, que deve vir do ambiente (§8.6).

---

## 7. Agendamentos Recorrentes (`tbsss_agendamentos`)

### 7.1 Base de tempo

* Todo cálculo usa o **horário de parede do servidor Oracle**. O daemon obtém o instante atual com `SELECT SYSDATE FROM DUAL` e **nunca** usa `datetime.now()` para agendamento.
* Datas são `datetime` *naive*, sem microssegundos.
* **Horário de verão:**
  * Semântica de parede: um horário inexistente (avanço do relógio) cai na regra de *misfire* e executa uma vez.
  * No horário duplicado (recuo do relógio), não há reexecução, porque `proxima_execucao` já aponta para a próxima ocorrência.
  * O fuso do servidor de banco é a referência oficial e deve estar documentado na operação.

### 7.2 Tipos de recorrência

| Tipo | Campos obrigatórios | Regra |
|---|---|---|
| `UNICA` | `data_inicio` (data e hora) | Executa uma vez e então `ativo = 'N'`, `pausa_motivo = 'CONCLUIDO'` |
| `DIARIA` | `hora_execucao` | Todo dia no horário indicado |
| `SEMANAL` | `hora_execucao`, `dias_semana` | `dias_semana` em ISO 1–7 (1 = segunda), por exemplo `1,3,5` |
| `MENSAL` | `hora_execucao`, `dia_mes` | Se o mês não tiver o dia, executa no **último dia do mês** |
| `CRON` | `expressao_cron` | §7.3 |

* `data_inicio` é o piso, e `data_fim` (opcional) é o teto.
* Se a próxima ocorrência passar de `data_fim`, a regra recebe `ativo = 'N'` e `pausa_motivo = 'CONCLUIDO'`.
* `proxima_execucao` é calculada no salvamento da regra pelo mesmo módulo `recurrence.py`.

### 7.3 Parser CRON (implementação própria, sem bibliotecas)

* Cinco campos: `minuto hora dia_mes mes dia_semana`.
* Sintaxe suportada: `*`, número, lista `a,b`, intervalo `a-b` e passo `*/n` ou `a-b/n`. **Não** há suporte a nomes (`MON`, `JAN`), `L`, `W`, `#` nem `?`.
* `dia_semana` aceita 0–7, onde 0 e 7 são domingo.
* Se `dia_mes` **e** `dia_semana` forem ambos restritos, vale a semântica **OU** (padrão Vixie cron).
* O cálculo da próxima ocorrência é feito campo a campo, não minuto a minuto, com horizonte de `cron_horizon_days`. Uma expressão sem ocorrência no horizonte é rejeitada no cadastro e pausa a regra (`CRON_INVALIDO`) no desdobro.

### 7.4 Política de *misfire*

Se `SYSDATE - proxima_execucao > misfire_tolerance_s` (por exemplo, após um downtime):

| `misfire_policy` | Comportamento |
|---|---|
| `RUN_ONCE` (padrão) | Gera **um** ticket, coalescendo as ocorrências perdidas |
| `SKIP` | Não gera ticket |

Nos dois casos, `proxima_execucao` recebe a **primeira ocorrência futura** maior que `SYSDATE`. O número de ocorrências perdidas vai para o log em WARN.

### 7.5 Algoritmo de desdobro (ciclo 1 do daemon)

Leitura das regras vencidas (usa `ix_tbsss_agd_prox`):

```sql
SELECT id FROM (
  SELECT id FROM {owner}.tbsss_agendamentos
   WHERE ativo = 'S' AND proxima_execucao <= SYSDATE
   ORDER BY proxima_execucao, id
) WHERE ROWNUM <= :lote
```

Para cada regra, em **uma transação**:

1. Ler a regra completa, guardando `antiga_data = proxima_execucao` **exatamente como retornada pelo banco**.
2. **Revalidar privilégios** do `usuario_id` com `rbac.pode_executar(usuario, script, ambiente)`. Se falhar, pausar (passo 7) com o motivo adequado: `USUARIO_INATIVO`, `SEM_PERMISSAO`, `SCRIPT_INATIVO` ou `AMBIENTE_INATIVO`.
3. Calcular `nova_data` (§7.2 a §7.4). Se não houver próxima ocorrência, marcar a conclusão após o ticket deste ciclo.
4. **Prevenir sobreposição:** se `ultimo_ticket_id` estiver em `PENDING` ou `RUNNING`, executar só o `UPDATE` otimista (passo 6) **sem** gerar ticket, registrar INFO `SKIP_OVERLAP` e encerrar a regra.
5. **Compilar o snapshot** a partir de `parametros_json`. Se for inválido, pausar com `PARAM_INVALIDO`.
6. Obter `:ticket_id` com `SELECT sq_tbsss_tickets.NEXTVAL FROM DUAL` e aplicar a reserva otimista:

   ```sql
   UPDATE {owner}.tbsss_agendamentos
      SET proxima_execucao = :nova_data,
          ultima_execucao  = SYSDATE,
          ultimo_ticket_id = :ticket_id
    WHERE id = :id
      AND ativo = 'S'
      AND proxima_execucao = :antiga_data
   ```

   * Se `rowcount = 1`, fazer o `INSERT` do ticket com `id = :ticket_id`, `agendamento_id = :id`, `solicitante = <login do usuario_id>`, `ip_origem = NULL`, `scheduled_at = SYSDATE` e a prioridade da regra. Em seguida, o `INSERT` em `tbsss_ticket_resp`.
   * Se `rowcount = 0`, outro nó processou a regra: fazer `ROLLBACK` e seguir para a próxima.
   * A trigger condicional (§10) preserva o `:ticket_id`. Valores de sequence descartados geram apenas lacunas inofensivas.
7. **Pausa** (sempre otimista):

   ```sql
   UPDATE {owner}.tbsss_agendamentos
      SET ativo = 'N', pausa_motivo = :motivo
    WHERE id = :id AND proxima_execucao = :antiga_data
   ```

   A pausa é registrada em `tbsss_auditoria` (`AGD_PAUSAR`) e no log em WARN.
8. `COMMIT` único. Em qualquer exceção, `ROLLBACK`, log ERROR e continuação com a próxima regra.

**Bind de datas:**

* `:antiga_data` e `:nova_data` são declarados como `DATE` via `setinputsizes`, usando `cx_Oracle.DATETIME` ou `oracledb.DB_TYPE_DATE`.
* Um `datetime` com microssegundos **nunca** é comparado a uma coluna `DATE`. A regra travaria silenciosamente.

---

## 8. Motor de Execução (ciclo 2 do daemon)

### 8.1 Laço principal

```text
inicialização (§8.12) -> loop:
  a cada cancel_poll_interval_s : varredura própria (§8.7) + cancelamentos + timeouts + processos finalizados
  a cada heartbeat_interval_s   : heartbeat (§8.7) + log pump (§8.10) + self-fencing (§8.9)
  a cada orchestrator_interval_s: NODE_OFFLINE (§8.8) + desdobro (§7.5) + claim (§8.2-8.4)
  sinal SIGTERM/SIGINT          : graceful shutdown (§8.11)
```

### 8.2 Seleção de candidatos

O agente só tenta o claim se `execucoes_locais < max_parallel_jobs`, com `max_parallel_jobs <= max_parallel_hard_limit`. Os placeholders `:amb0..:ambN` são **gerados pelo código** a partir de `ambientes_atendidos`; os valores sempre são binds.

```sql
SELECT id, script_id, ambiente FROM (
  SELECT t.id, t.script_id, t.ambiente
    FROM {owner}.tbsss_tickets t
   WHERE (CASE WHEN t.status = 'PENDING' THEN t.prioridade END) IS NOT NULL
     AND (CASE WHEN t.status = 'PENDING' THEN t.scheduled_at END) <= SYSDATE
     AND t.ambiente IN (:amb0, :amb1)
     AND t.cancel_requested = 'N'
   ORDER BY (CASE WHEN t.status = 'PENDING' THEN t.prioridade END),
            (CASE WHEN t.status = 'PENDING' THEN t.scheduled_at END),
            t.id
) WHERE ROWNUM <= :lote
```

As expressões `CASE` devem ser **textualmente idênticas** às do índice baseado em função `ix_tbsss_tck_fila`, que contém apenas os tickets `PENDING`.

### 8.3 Claim em três passos (por candidato, uma transação)

1. **Serialização por script:**
   ```sql
   SELECT id, max_qtd_parallel_env
     FROM {owner}.tbsss_scripts
    WHERE id = :script_id
      FOR UPDATE WAIT 5
   ```
   ORA-30006 ou ORA-00054 leva a `ROLLBACK` e ao próximo candidato.
2. **Checagem de teto** (usa `ix_tbsss_tck_scr`):
   ```sql
   SELECT COUNT(*) FROM {owner}.tbsss_tickets
    WHERE script_id = :script_id AND ambiente = :ambiente AND status = 'RUNNING'
   ```
   Se `total >= max_qtd_parallel_env`, `ROLLBACK` e próximo candidato.
3. **Reserva atômica, ainda sem PID:**
   ```sql
   UPDATE {owner}.tbsss_tickets
      SET status = 'RUNNING', agente_id = :agente_id,
          started_at = SYSDATE, heartbeat_at = SYSDATE,
          log_output = EMPTY_CLOB()
    WHERE id = :ticket_id AND status = 'PENDING' AND cancel_requested = 'N'
   ```
   Se `rowcount = 1`, `COMMIT`. Se for 0, `ROLLBACK` e próximo candidato.

**Ordem de locks do sistema** (evita deadlock):
* claim: `tbsss_scripts` → `tbsss_tickets`;
* desdobro: `tbsss_agendamentos` → `tbsss_tickets`.

É proibido inverter essas ordens.

### 8.4 Pré-validação, spawn e registro do PID

1. **Pré-validação do snapshot.** Qualquer falha leva a `FAILED` com `PRECHECK_FAILED` e `-4`:
   * o JSON é válido e tem `versao` suportada;
   * `argv[0] == comando_real`, e o valor consta na allowlist;
   * `script_real` passa na §8.5 e é idêntico ao do snapshot;
   * o script segue `ativo = 'S'` e homologado para o ambiente.
2. **Preparo do diretório de trabalho:**
   * `work_dir/ticket_<id>/` com permissão `0700`, que é o `cwd` do processo;
   * `work_dir/ticket_<id>/tmp/` como `TMPDIR`.
3. **Arquivo de log:** `log_dir/tickets/<AAAAMM>/ticket_<id>.log`, aberto com `os.open(path, O_WRONLY | O_CREAT | O_EXCL | O_APPEND, 0o600)`.
4. **Spawn:**
   ```python
   p = subprocess.Popen(
       argv,
       stdin=subprocess.DEVNULL,
       stdout=log_fd,
       stderr=subprocess.STDOUT,
       shell=False,
       close_fds=True,
       start_new_session=True,
       cwd=ticket_work_dir,
       env=clean_env,
       preexec_fn=_child_limits,   # somente os.umask(0o077) e resource.setrlimit; permitido porque o daemon é single-threaded
   )
   os.close(log_fd)                # o filho mantém a própria cópia do descritor
   ```
   `OSError` no spawn leva a `FAILED` com `SPAWN_ERROR` e `-4`.
5. **Instante de início:** ler `starttime` (campo 22 de `/proc/<pid>/stat`, contado **após o último `)`**) e gravar:
   ```sql
   UPDATE {owner}.tbsss_tickets
      SET process_id = :pid, process_start = :process_start
    WHERE id = :ticket_id AND agente_id = :agente_id AND status = 'RUNNING'
   ```
   Se `rowcount = 0`, a posse foi perdida (por exemplo, `NODE_OFFLINE` durante o spawn): fazer `killpg` com SIGTERM → SIGKILL e registrar ERROR `OWNERSHIP_LOST`.

### 8.5 Validação de interpretador e caminho (`path_guard.py`)

```python
ALLOWLIST = ('/usr/bin/python3', '/bin/bash', '/bin/sh')

base = os.path.realpath(base_script_dir)
real = os.path.realpath(os.path.join(base, path_file))
try:
    dentro = os.path.commonpath([base, real]) == base
except ValueError:
    dentro = False
ok = (comando_real in ALLOWLIST and dentro and real != base and os.path.isfile(real))
```

Validações complementares:

* **Ownership e modo:** o script, **cada diretório** entre `base` e o script, e o próprio `base` devem pertencer a um UID de `script_owner_uids` (padrão: `0`, root). Eles não podem ter escrita para grupo nem para outros (`st_mode & 0o022 == 0`), e o UID do agente não pode ter permissão de escrita (`os.access(p, os.W_OK)` falso).
* **Momento:** a validação ocorre no cadastro (UI), na criação do ticket (snapshot) e novamente no claim (§8.4).
* **CKs de banco** (defesa adicional):
  * `ck_tbsss_scr_cmd` restringe `comando_real` à allowlist;
  * `ck_tbsss_scr_path` exige `path_file` relativo e sem `..`.
* **TOCTOU residual:** é aceito porque o UID do agente não consegue alterar a árvore de scripts.

### 8.6 Ambiente do processo filho (`env_builder.py`)

| Variável | Valor |
|---|---|
| `PATH` | `/usr/bin:/bin` |
| `HOME` | `work_dir/ticket_<id>` |
| `TMPDIR` | `work_dir/ticket_<id>/tmp` |
| `LANG`, `LC_ALL` | `child_locale` (padrão `C.UTF-8`) |
| `TZ` | herdado do daemon (definido pelo launcher) |
| `PYTHONDONTWRITEBYTECODE` | `1` |
| `PYTHONIOENCODING` | `utf-8` |
| `SSS_TICKET_ID`, `SSS_AMBIENTE`, `SSS_AGENTE_ID` | metadados do ticket |
| `SSS_SCRIPT_DIR` | `os.path.dirname(script_real)` |
| `PADRAO_VALOR_RUN_CONEXAO_BD` | `user/password@dsn`, com credenciais de `secrets.cfg [ambiente:<NOME>]` e DSN de `tbsss_ambientes.conexao`. Omitida se o ambiente não tiver DSN |
| `env_passthrough` | copiadas do ambiente do daemon (por exemplo, `ORACLE_HOME`, `TNS_ADMIN`, `NLS_LANG`, `LD_LIBRARY_PATH`) |

* **Bloqueadas** mesmo se listadas em `env_passthrough`: `LD_PRELOAD`, `LD_AUDIT`, `PYTHONPATH`, `PYTHONHOME`, `PYTHONSTARTUP`, `PYTHONINSPECT`, `BASH_ENV`, `ENV`, `SHELLOPTS`, `BASHOPTS`, `IFS`, `PERL5LIB`, `PERL5OPT`. A configuração que as contiver é rejeitada na inicialização.
* **Risco residual documentado:** a credencial no ambiente é legível em `/proc/<pid>/environ` pelo mesmo UID e por root. Mitigação: o agente roda com UID dedicado e sem login interativo.

### 8.7 Varredura própria, heartbeat, timeout e finalização

Varredura combinada (a cada `cancel_poll_interval_s`, usa `ix_tbsss_tck_run`):

```sql
SELECT id, cancel_requested
  FROM {owner}.tbsss_tickets
 WHERE (CASE WHEN status = 'RUNNING' THEN agente_id END) = :agente_id
```

* Um ticket que está no mapa local mas **ausente** do resultado foi finalizado por outro nó. O agente executa `killpg` (SIGTERM → SIGKILL), registra ERROR `OWNERSHIP_LOST` e não grava status.
* **Heartbeat** (a cada `heartbeat_interval_s`):
  * `executemany` de `UPDATE ... SET heartbeat_at = SYSDATE WHERE id = :id AND agente_id = :agente_id AND status = 'RUNNING'`, com `arraydmlrowcounts=True`;
  * linha com contagem 0 é tratada como `OWNERSHIP_LOST`;
  * na mesma transação, atualiza `tbsss_agentes.heartbeat_at`.
* **Timeout:** `timeout = tbsss_scripts.timeout_seg` ou, se nulo, `script_timeout_s`. Ao expirar, SIGTERM → `kill_grace_s` → SIGKILL, com finalização `FAILED`, `TIMEOUT` e `-3`.
* **Finalização normal** (detectada por `Popen.poll()`):
  1. flush final do log;
  2. `UPDATE ... SET status, status_motivo, return_code, finished_at = SYSDATE WHERE id = :id AND agente_id = :agente_id AND status = 'RUNNING'`;
  3. `COMMIT`;
  4. remoção de `work_dir/ticket_<id>/`.

### 8.8 Detecção de nó offline (qualquer agente, a cada `orchestrator_interval_s`)

```sql
UPDATE {owner}.tbsss_tickets
   SET status = 'FAILED', status_motivo = 'NODE_OFFLINE',
       return_code = -2, finished_at = SYSDATE
 WHERE (CASE WHEN status = 'RUNNING' THEN agente_id END) IS NOT NULL
   AND heartbeat_at < SYSDATE - (:node_offline_timeout_s / 86400)
```

O relógio de referência é sempre o `SYSDATE` do banco, nunca o relógio do nó.

### 8.9 Self-fencing (prevenção de split-brain)

* O agente registra o instante do último heartbeat **confirmado** (commit OK).
* Se `agora_monotonico - ultimo_hb_ok > fence_timeout_s`, o agente:
  1. executa `killpg` em **todos** os grupos que possui (SIGTERM → SIGKILL);
  2. suspende novos claims;
  3. registra CRITICAL `FENCED`.
* Quando o banco volta, ele tenta `UPDATE ... SET status = 'FAILED', status_motivo = 'FENCED', return_code = -2 ... WHERE id = :id AND agente_id = :agente_id AND status = 'RUNNING'`. Se o ticket já estiver `NODE_OFFLINE`, o `rowcount = 0` é esperado.
* **Invariante validada na inicialização:** `fence_timeout_s * 2 <= node_offline_timeout_s` e `heartbeat_interval_s * 3 <= fence_timeout_s`. Isso garante que o agente se cerca **antes** de outro nó declará-lo offline.
* A medição usa `time.monotonic()`, imune a ajuste de relógio.

### 8.10 Coleta de log (`log_pump.py`)

* A cada `heartbeat_interval_s` e no flush final:
  * o agente lê os bytes novos do arquivo a partir do offset local;
  * decodifica com `utf-8`, `errors='replace'`, sem cortar caracteres multibyte (o resto incompleto fica para o próximo ciclo);
  * aplica `masking.py` (segredos carregados, `PADRAO_VALOR_RUN_CONEXAO_BD`, valores de parâmetros sensíveis);
  * anexa ao CLOB em blocos de até 8.000 caracteres:

```sql
DECLARE
  v_lob CLOB;
BEGIN
  SELECT log_output INTO v_lob
    FROM {owner}.tbsss_tickets
   WHERE id = :ticket_id AND agente_id = :agente_id AND status = 'RUNNING'
     FOR UPDATE WAIT 5;
  DBMS_LOB.WRITEAPPEND(v_lob, LENGTH(:chunk), :chunk);
END;
```

  * Em seguida, `COMMIT`. `NO_DATA_FOUND` é tratado como `OWNERSHIP_LOST`.
* **Limites:**
  * O teto do CLOB é medido em **bytes UTF-8 do texto já enviado** (`len(texto.encode('utf-8'))` acumulado pelo agente), e o corte é feito em fronteira de caractere.
  * Ao atingir `max_log_size_bytes` no CLOB, o agente para de anexar, grava `log_truncado = 'S'` e anexa um marcador final `[SSS] log truncado no banco; arquivo integral no agente`.
  * O arquivo local tem teto `max_local_log_size_bytes`. Ao excedê-lo, o processo é encerrado (SIGTERM → SIGKILL) com `FAILED`, `LOG_LIMIT` e `-5`, protegendo o disco.
* **UI `VER_LOGS`:** polling a cada `log_poll_interval_s`.
  * O cliente envia o offset já recebido, e o servidor lê pelo locator (`lob.read(offset, amount)`).
  * O texto é exibido com `x-text`.
  * A latência esperada é de cerca de `heartbeat_interval_s`.
* Arquivos locais com mais de `local_log_retention_days` dias são removidos pelo `purge.py`.

### 8.11 Graceful shutdown do daemon

* SIGTERM/SIGINT apenas acionam uma flag; o laço trata o restante.
* O daemon para de fazer desdobro e claim.

| `shutdown_mode` | Comportamento |
|---|---|
| `DRAIN` | Aguarda os filhos por até `shutdown_grace_s` e então aplica `TERMINATE` aos restantes |
| `TERMINATE` (padrão) | `killpg` SIGTERM → `kill_grace_s` → SIGKILL. Finaliza com `FAILED`, `SHUTDOWN` e `-6` |

Em seguida, o daemon faz o flush dos logs, grava `tbsss_agentes.status = 'PARADO'`, audita `AGENTE_FIM`, fecha a conexão e o lock file, e sai com código 0.

### 8.12 Inicialização do daemon (fail-fast)

O daemon aborta com código diferente de zero e log CRITICAL ao falhar em qualquer passo:

1. **Usuário:** `os.geteuid() != 0`. É proibido rodar como root.
2. **Configuração:** carregar e validar o `config.ini` (tipos, faixas, invariantes da §8.9 e `max_parallel_jobs <= max_parallel_hard_limit`), o `owner` e o `table_prefix` (regex do `AGENTS.md`), e `agent_id` contra `^[A-Za-z0-9._-]{1,30}$`.
3. **Segredos:** validar o `secrets.cfg` (§4.1).
4. **Diretórios:**
   * `base_script_dir` passa na regra de ownership da §8.5;
   * `log_dir` e `work_dir` existem, são graváveis e **não** ficam sob `base_script_dir`.
5. **Instância única por host:** `fcntl.flock(LOCK_EX | LOCK_NB)` em `work_dir/sss-<agent_id>.lock`.
6. **Banco:** carregar o Instant Client, conectar e confirmar `SELECT SYSDATE FROM DUAL`.
7. **Registro em `tbsss_agentes`:**
   * Se existir linha do mesmo `codigo` com `status = 'ATIVO'`, `heartbeat_at` recente (menor que `node_offline_timeout_s`) **e** `hostname` diferente, recusar a subida (`agent_id` duplicado).
   * Caso contrário, executar `MERGE` com `status = 'ATIVO'`, `hostname`, `pid_daemon`, `versao`, `ambientes` e `iniciado_em`.
   * Auditar `AGENTE_INICIO`.
8. **Ambientes atendidos:** todos existem em `tbsss_ambientes` com `ativo = 'S'`. Um ambiente inexistente é ERROR fatal; um ambiente inativo gera WARN e é ignorado.
9. **Startup check** de tickets `RUNNING` do próprio `agente_id`:
   * `process_id` nulo leva a `FAILED` com `ORPHAN_PROCESS`.
   * PID inexistente (`os.kill(pid, 0)` com `ProcessLookupError`) ou `starttime` diferente de `process_start` (PID reciclado) também leva a `ORPHAN_PROCESS`.
   * PID vivo com `starttime` igual indica um filho de uma instância anterior do daemon. Como não pode ser adotado (`waitpid` impossível), ele é encerrado com `killpg` (SIGTERM → SIGKILL) e finalizado com `ORPHAN_PROCESS`.

---

## 9. Convenção de Identificadores (Oracle 11g ≤ 30 caracteres)

### 9.1 Template

```text
tabela      = {prefixo}{entidade}               tbsss_tickets
sequence    = sq_{prefixo}{entidade}            sq_tbsss_tickets
trigger PK  = tr_{prefixo}{abrev}_bi            tr_tbsss_tck_bi
trigger UPD = tr_{prefixo}{abrev}_bu            tr_tbsss_amb_bu
PK          = pk_{prefixo}{entidade}            pk_tbsss_tickets
UK/FK/CK/IX = {uk|fk|ck|ix}_{prefixo}{abrev}_{sufixo}   ix_tbsss_tck_fila
```

* `{prefixo}` vem de `table_prefix`, inclui o `_` final e obedece à regex `^[a-zA-Z0-9_]{1,8}$`.
* O DDL é gerado por `init_db.py` a partir de um **registro único de identificadores** em `modules/sql_ident.py`, consumido também por `test_db_schema.py`.
* **Pior caso com prefixo de 8 caracteres:** `sq_` + 8 + `funcionalidades` = **26** (conforme).

### 9.2 Tabela de abreviações

| Entidade | Abrev. | Sequence | Trigger | PK |
|---|---|---|---|---|
| Ambientes | `amb` | `sq_tbsss_ambientes` | `tr_tbsss_amb_bi` | `pk_tbsss_ambientes` |
| Perfis | `per` | `sq_tbsss_perfis` | `tr_tbsss_per_bi` | `pk_tbsss_perfis` |
| Funcionalidades | `fnc` | `sq_tbsss_funcionalidades` | `tr_tbsss_fnc_bi` | `pk_tbsss_funcionalidades` |
| Perfil x Funcionalidade | `pfnc` | `sq_tbsss_perfil_func` | `tr_tbsss_pfnc_bi` | `pk_tbsss_perfil_func` |
| Perfil x Ambiente | `pamb` | `sq_tbsss_perfil_amb` | `tr_tbsss_pamb_bi` | `pk_tbsss_perfil_amb` |
| Scripts | `scr` | `sq_tbsss_scripts` | `tr_tbsss_scr_bi` | `pk_tbsss_scripts` |
| Perfil x Script | `pscr` | `sq_tbsss_perfil_scr` | `tr_tbsss_pscr_bi` | `pk_tbsss_perfil_scr` |
| Script x Ambiente | `samb` | `sq_tbsss_script_amb` | `tr_tbsss_samb_bi` | `pk_tbsss_script_amb` |
| Usuários | `usr` | `sq_tbsss_usuarios` | `tr_tbsss_usr_bi` | `pk_tbsss_usuarios` |
| Parâmetros | `prm` | `sq_tbsss_parametros` | `tr_tbsss_prm_bi` | `pk_tbsss_parametros` |
| Script x Parâmetro | `sprm` | `sq_tbsss_script_param` | `tr_tbsss_sprm_bi` | `pk_tbsss_script_param` |
| Agendamentos | `agd` | `sq_tbsss_agendamentos` | `tr_tbsss_agd_bi` | `pk_tbsss_agendamentos` |
| Tickets | `tck` | `sq_tbsss_tickets` | `tr_tbsss_tck_bi` | `pk_tbsss_tickets` |
| Ticket x Resposta | `trsp` | `sq_tbsss_ticket_resp` | `tr_tbsss_trsp_bi` | `pk_tbsss_ticket_resp` |
| Agentes | `agt` | `sq_tbsss_agentes` | `tr_tbsss_agt_bi` | `pk_tbsss_agentes` |
| Auditoria | `aud` | `sq_tbsss_auditoria` | `tr_tbsss_aud_bi` | `pk_tbsss_auditoria` |

---

## 10. Modelo de Dados Completo (16 tabelas)

**Padrões globais:**

* O `owner` é parametrizado (`gfcadastro`), e todo SQL qualifica `{owner}.objeto`.
* Toda coluna `id` é `NUMBER(10) NOT NULL`, PK, preenchida pela trigger condicional:

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

* As sequences usam `START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE`. Lacunas são aceitas.
* **Toda FK filha tem índice cuja coluna líder é a própria FK.** A UK composta cobre apenas a coluna líder.
* `ativo` e demais flags são `CHAR(1)` com CK `IN ('S','N')`.
* **FKs para chave natural** (`tbsss_ambientes.nome`, `tbsss_usuarios.login`) tornam essas colunas **imutáveis**. A imutabilidade é garantida pelas triggers `tr_tbsss_amb_bu` e `tr_tbsss_usr_bu`, que disparam `RAISE_APPLICATION_ERROR(-20001, ...)` se o valor mudar.
* O ticket referencia `login` (fato de auditoria imutável), enquanto o agendamento referencia `usuario_id` (regra viva).
* **Política de exclusão:**
  * **Entidades mestras não são excluídas, apenas desativadas** (`ativo = 'N'`): ambientes, perfis, funcionalidades, usuários, scripts, parâmetros e agendamentos.
  * **Associações podem ser removidas fisicamente:** `perfil_func`, `perfil_amb`, `perfil_scr`, `script_amb` e `script_param`.
  * Tickets só são removidos pelo `purge.py`.
* **Desativação com dependência:**
  * Desativar um **parâmetro** vinculado a script ativo é bloqueado, e a UI lista os scripts afetados.
  * Desativar **script** ou **ambiente** pausa os agendamentos dependentes no próximo desdobro (§7.5).
  * Na UI, desativar e reativar ficam no **formulário de edição**, não na lista. A ação abre um modal de confirmação que mostra o impacto (ex.: quantidade de agendamentos ativos afetados).
* **Concorrência otimista nos cadastros (sem coluna de versão):**
  * O formulário de edição carrega uma `versao`: o sha256 dos campos editáveis, `ativo` incluído, calculado pelo servidor na leitura.
  * Ao salvar, o service relê o registro e compara a versão. Em seguida, repassa os valores lidos ao repositório, que executa `UPDATE ... WHERE id = :id AND <coluna = valor lido>` com comparação nula-segura (`DECODE`) e checa o `rowcount`.
  * Se a versão divergir ou o `rowcount` for 0, o resultado é `RepoConflito`, sem alteração nem auditoria. A mensagem é "O registro foi alterado por outra pessoa. Recarregue a página."
  * A linha de auditoria é gravada na mesma operação (transação) do `INSERT` ou `UPDATE`.
* **Edição de agendamento:** ao salvar uma alteração, `usuario_id` passa a ser o **editor**, que precisa ter `pode_executar` vigente para o script e o ambiente da regra. A regra sempre roda sob os privilégios de quem a definiu por último, o que impede um usuário de reaproveitar privilégios de outro editando a regra dele. A alteração é auditada com o `usuario_id` anterior e o novo.

### 1. `tbsss_ambientes`
* PK `pk_tbsss_ambientes` · UK `uk_tbsss_amb_nome (nome)`
* **CK:**
  * `ck_tbsss_amb_ativo`
  * `ck_tbsss_amb_nome (REGEXP_LIKE(nome, '^[A-Z0-9_]{1,30}$'))`
  * `ck_tbsss_amb_conexao (conexao IS NULL OR INSTR(conexao, '@') = 0)`
* Trigger extra: `tr_tbsss_amb_bu` (nome imutável)
* **Colunas:**
  * `id`
  * `nome VARCHAR2(30 CHAR) NOT NULL`
  * `descricao VARCHAR2(100 CHAR)`
  * `conexao VARCHAR2(250 CHAR)` (somente DSN, opcional)
* **Validação na UI** (`admin_ambientes_service.py`):
  * `nome` segue a CK à risca. Letras minúsculas ou outros caracteres são **rejeitados** com mensagem, não convertidos. O `nome` é imutável depois de criado: o campo fica somente leitura e o servidor ignora o valor enviado.
  * `conexao` é opcional, como a coluna. Quando preenchida, aceita apenas:
    * Easy Connect: `^[A-Za-z0-9._-]+:[0-9]{1,5}/[A-Za-z0-9._-]+$`;
    * alias TNS: `^[A-Za-z0-9._-]{1,128}$`.
  * Um `@` é recusado com "Informe apenas o DSN; credenciais ficam no secrets.cfg."
  * `descricao` é opcional, com até 100 caracteres.
  * `ativo CHAR(1) DEFAULT 'S' NOT NULL`
  * `created_at DATE DEFAULT SYSDATE NOT NULL`

### 2. `tbsss_perfis`
* PK `pk_tbsss_perfis` · UK `uk_tbsss_per_nome (nome)`
* CK: `ck_tbsss_per_adm`, `ck_tbsss_per_ativo`, `ck_tbsss_per_versao (perm_versao >= 1)`
* **Colunas:**
  * `id`
  * `nome VARCHAR2(30 CHAR) NOT NULL` (na UI: `^[A-Z0-9_]{1,30}$`, mutável, único)
  * `descricao VARCHAR2(100 CHAR)`
  * `is_admin CHAR(1) DEFAULT 'N' NOT NULL`
  * `perm_versao NUMBER(10) DEFAULT 1 NOT NULL`
  * `ativo CHAR(1) DEFAULT 'S' NOT NULL`

### 3. `tbsss_funcionalidades`
* PK `pk_tbsss_funcionalidades` · UK `uk_tbsss_fnc_codigo (codigo)`
* CK: `ck_tbsss_fnc_ativo`
* **Colunas:**
  * `id`
  * `codigo VARCHAR2(30 CHAR) NOT NULL`
  * `nome VARCHAR2(60 CHAR) NOT NULL`
  * `modulo VARCHAR2(30 CHAR) NOT NULL`
  * `descricao VARCHAR2(150 CHAR)`
  * `ativo CHAR(1) DEFAULT 'S' NOT NULL`

### 4. `tbsss_perfil_func`
* PK `pk_tbsss_perfil_func` · UK `uk_tbsss_pfnc_per_fnc (perfil_id, funcionalidade_id)`
* FK `fk_tbsss_pfnc_per → tbsss_perfis(id) ON DELETE CASCADE` (coberta pela UK)
* FK `fk_tbsss_pfnc_fnc → tbsss_funcionalidades(id) ON DELETE CASCADE` · IX `ix_tbsss_pfnc_fnc (funcionalidade_id)`
* **Colunas:** `id`, `perfil_id NUMBER(10) NOT NULL`, `funcionalidade_id NUMBER(10) NOT NULL`

### 5. `tbsss_perfil_amb`
* PK `pk_tbsss_perfil_amb` · UK `uk_tbsss_pamb_per_amb (perfil_id, ambiente_id)`
* FK `fk_tbsss_pamb_per → tbsss_perfis(id) ON DELETE CASCADE` (coberta pela UK)
* FK `fk_tbsss_pamb_amb → tbsss_ambientes(id) ON DELETE CASCADE` · IX `ix_tbsss_pamb_amb (ambiente_id)`
* **Colunas:** `id`, `perfil_id NUMBER(10) NOT NULL`, `ambiente_id NUMBER(10) NOT NULL`

### 6. `tbsss_scripts`
* PK `pk_tbsss_scripts` · UK `uk_tbsss_scr_nome (nome)`
* **CK:**
  * `ck_tbsss_scr_tparam (tipo_param IN ('NOMEADO','SEQUENCIAL','NENHUM'))`
  * `ck_tbsss_scr_ativo`
  * `ck_tbsss_scr_paral (max_qtd_parallel_env BETWEEN 1 AND 999)`
  * `ck_tbsss_scr_cmd (comando_real IN ('/usr/bin/python3','/bin/bash','/bin/sh'))`
  * `ck_tbsss_scr_path (SUBSTR(path_file, 1, 1) <> '/' AND INSTR(path_file, '..') = 0)`
  * `ck_tbsss_scr_tmout (timeout_seg IS NULL OR timeout_seg > 0)`
* **Colunas:**
  * `id`
  * `nome VARCHAR2(60 CHAR) NOT NULL`
  * `descricao VARCHAR2(200 CHAR)`
  * `grupo VARCHAR2(30 CHAR)`
  * `categoria VARCHAR2(30 CHAR)`
  * `etapa VARCHAR2(30 CHAR)`
  * `comando_real VARCHAR2(60 CHAR) NOT NULL`
  * `path_file VARCHAR2(250 CHAR) NOT NULL` (relativo a `base_script_dir`)
  * `tipo_param VARCHAR2(15 CHAR) DEFAULT 'NOMEADO' NOT NULL`
  * `max_qtd_parallel_env NUMBER(3) DEFAULT 1 NOT NULL`
  * `timeout_seg NUMBER(7)`
  * `ativo CHAR(1) DEFAULT 'S' NOT NULL`

### 7. `tbsss_perfil_scr`
* PK `pk_tbsss_perfil_scr` · UK `uk_tbsss_pscr_per_scr (perfil_id, script_id)`
* FK `fk_tbsss_pscr_per → tbsss_perfis(id) ON DELETE CASCADE` (coberta pela UK)
* FK `fk_tbsss_pscr_scr → tbsss_scripts(id) ON DELETE CASCADE` · IX `ix_tbsss_pscr_scr (script_id)`
* **Colunas:** `id`, `perfil_id NUMBER(10) NOT NULL`, `script_id NUMBER(10) NOT NULL`

### 8. `tbsss_script_amb` (homologação de script por ambiente)
* PK `pk_tbsss_script_amb` · UK `uk_tbsss_samb_scr_amb (script_id, ambiente_id)`
* FK `fk_tbsss_samb_scr → tbsss_scripts(id) ON DELETE CASCADE` (coberta pela UK)
* FK `fk_tbsss_samb_amb → tbsss_ambientes(id) ON DELETE CASCADE` · IX `ix_tbsss_samb_amb (ambiente_id)`
* **Colunas:** `id`, `script_id NUMBER(10) NOT NULL`, `ambiente_id NUMBER(10) NOT NULL`

### 9. `tbsss_usuarios`
* PK `pk_tbsss_usuarios` · UK `uk_tbsss_usr_login (login)`
* FK `fk_tbsss_usr_per → tbsss_perfis(id)` · IX `ix_tbsss_usr_per (perfil_id)`
* **CK:**
  * `ck_tbsss_usr_ativo`
  * `ck_tbsss_usr_login (REGEXP_LIKE(login, '^[a-z0-9._-]{3,30}$'))`
  * `ck_tbsss_usr_tent (tentativas_falha >= 0)`
* Trigger extra: `tr_tbsss_usr_bu` (login imutável)
* **Colunas:**
  * `id`
  * `login VARCHAR2(30 CHAR) NOT NULL`
  * `nome VARCHAR2(60 CHAR) NOT NULL`
  * `senha_hash VARCHAR2(256 CHAR) NOT NULL`
  * `perfil_id NUMBER(10) NOT NULL`
  * `tentativas_falha NUMBER(2) DEFAULT 0 NOT NULL`
  * `bloqueado_ate DATE`
  * `ultimo_login DATE`
  * `senha_alterada_em DATE`
  * `ativo CHAR(1) DEFAULT 'S' NOT NULL`
  * `created_at DATE DEFAULT SYSDATE NOT NULL`

### 10. `tbsss_parametros`
* PK `pk_tbsss_parametros` · UK `uk_tbsss_prm_codigo (codigo)`
* **CK:**
  * `ck_tbsss_prm_tcomp (tipo_componente IN ('TEXT','NUMBER','DATE','SELECT','CHECKBOX'))`
  * `ck_tbsss_prm_ativo`
  * `ck_tbsss_prm_sens (sensivel IN ('S','N'))`
  * `ck_tbsss_prm_codigo (REGEXP_LIKE(codigo, '^[a-z0-9_]{1,30}$'))`
  * `ck_tbsss_prm_flag (param_nomeado IS NULL OR REGEXP_LIKE(param_nomeado, '^-{1,2}[A-Za-z0-9][A-Za-z0-9_-]{0,27}$'))`
* **Colunas:**
  * `id`
  * `codigo VARCHAR2(30 CHAR) NOT NULL`
  * `param_nomeado VARCHAR2(30 CHAR)` (obrigatória para vínculo com script `NOMEADO`)
  * `label VARCHAR2(60 CHAR) NOT NULL`
  * `descricao VARCHAR2(150 CHAR)`
  * `tipo_componente VARCHAR2(20 CHAR) NOT NULL`
  * `opcoes_json VARCHAR2(500 CHAR)`
  * `valor_padrao VARCHAR2(100 CHAR)`
  * `regex_validacao VARCHAR2(150 CHAR)`
  * `sensivel CHAR(1) DEFAULT 'N' NOT NULL`
  * `ativo CHAR(1) DEFAULT 'S' NOT NULL`

### 11. `tbsss_script_param`
* PK `pk_tbsss_script_param` · UK `uk_tbsss_sprm_scr_prm (script_id, parametro_id)` · UK `uk_tbsss_sprm_scr_ord (script_id, ordem)`
* FK `fk_tbsss_sprm_scr → tbsss_scripts(id) ON DELETE CASCADE` (coberta pela UK)
* FK `fk_tbsss_sprm_prm → tbsss_parametros(id)` · IX `ix_tbsss_sprm_prm (parametro_id)`
* CK: `ck_tbsss_sprm_obrig`, `ck_tbsss_sprm_ordem (ordem >= 1)`
* **Colunas:**
  * `id`
  * `script_id NUMBER(10) NOT NULL`
  * `parametro_id NUMBER(10) NOT NULL`
  * `ordem NUMBER(3) NOT NULL`
  * `obrigatorio CHAR(1) DEFAULT 'S' NOT NULL`
  * `valor_padrao_sub VARCHAR2(100 CHAR)`

### 12. `tbsss_agendamentos`
* PK `pk_tbsss_agendamentos`
* **FKs e índices:**
  * FK `fk_tbsss_agd_scr → tbsss_scripts(id)` · IX `ix_tbsss_agd_scr (script_id)`
  * FK `fk_tbsss_agd_usr → tbsss_usuarios(id)` · IX `ix_tbsss_agd_usr (usuario_id)`
  * FK `fk_tbsss_agd_amb → tbsss_ambientes(nome)` · IX `ix_tbsss_agd_amb (ambiente)`
  * Polling: IX `ix_tbsss_agd_prox (ativo, proxima_execucao)`
* **CK:**
  * `ck_tbsss_agd_trec (tipo_recorrencia IN ('UNICA','DIARIA','SEMANAL','MENSAL','CRON'))`
  * `ck_tbsss_agd_prio (prioridade BETWEEN 1 AND 4)`
  * `ck_tbsss_agd_ativo`
  * `ck_tbsss_agd_dia (dia_mes IS NULL OR dia_mes BETWEEN 1 AND 31)`
  * `ck_tbsss_agd_hora (hora_execucao IS NULL OR REGEXP_LIKE(hora_execucao, '^([01][0-9]|2[0-3]):[0-5][0-9]$'))`
  * `ck_tbsss_agd_dsem (dias_semana IS NULL OR REGEXP_LIKE(dias_semana, '^[1-7](,[1-7]){0,6}$'))`
  * `ck_tbsss_agd_fim (data_fim IS NULL OR data_fim >= data_inicio)`
  * `ck_tbsss_agd_pausa (pausa_motivo IS NULL OR pausa_motivo IN ('USUARIO_INATIVO','SEM_PERMISSAO','SCRIPT_INATIVO','AMBIENTE_INATIVO','PARAM_INVALIDO','CRON_INVALIDO','CONCLUIDO','MANUAL'))`
  * `ck_tbsss_agd_campos`:
    ```sql
    (tipo_recorrencia = 'UNICA')
    OR (tipo_recorrencia = 'DIARIA'  AND hora_execucao IS NOT NULL)
    OR (tipo_recorrencia = 'SEMANAL' AND hora_execucao IS NOT NULL AND dias_semana IS NOT NULL)
    OR (tipo_recorrencia = 'MENSAL'  AND hora_execucao IS NOT NULL AND dia_mes IS NOT NULL)
    OR (tipo_recorrencia = 'CRON'    AND expressao_cron IS NOT NULL)
    ```
* **Colunas:**
  * `id`
  * `nome VARCHAR2(60 CHAR) NOT NULL`
  * `script_id NUMBER(10) NOT NULL`
  * `ambiente VARCHAR2(30 CHAR) NOT NULL`
  * `usuario_id NUMBER(10) NOT NULL`
  * `prioridade NUMBER(1) DEFAULT 2 NOT NULL`
  * `tipo_recorrencia VARCHAR2(15 CHAR) NOT NULL`
  * `expressao_cron VARCHAR2(60 CHAR)`
  * `hora_execucao VARCHAR2(5 CHAR)`
  * `dias_semana VARCHAR2(20 CHAR)`
  * `dia_mes NUMBER(2)`
  * `parametros_json CLOB` (objeto `{"codigo": "valor"}`)
  * `data_inicio DATE NOT NULL`
  * `data_fim DATE`
  * `proxima_execucao DATE NOT NULL`
  * `ultima_execucao DATE`
  * `ultimo_ticket_id NUMBER(10)` (sem FK, para evitar ciclo)
  * `pausa_motivo VARCHAR2(30 CHAR)`
  * `ativo CHAR(1) DEFAULT 'S' NOT NULL`
  * `created_at DATE DEFAULT SYSDATE NOT NULL`
* **Política de exclusão:** agendamentos não são excluídos, apenas desativados.

### 13. `tbsss_tickets`
* PK `pk_tbsss_tickets`
* **FKs e índices:**
  * FK `fk_tbsss_tck_scr → tbsss_scripts(id)` · IX `ix_tbsss_tck_scr (script_id, ambiente, status)` (cobre a FK e a checagem de teto)
  * FK `fk_tbsss_tck_amb → tbsss_ambientes(nome)` · IX `ix_tbsss_tck_amb (ambiente)`
  * FK `fk_tbsss_tck_usr → tbsss_usuarios(login)` · IX `ix_tbsss_tck_usr (solicitante)`
  * FK `fk_tbsss_tck_parent → tbsss_tickets(id) ON DELETE SET NULL` · IX `ix_tbsss_tck_par (parent_ticket_id)`
  * FK `fk_tbsss_tck_agd → tbsss_agendamentos(id) ON DELETE SET NULL` · IX `ix_tbsss_tck_agd (agendamento_id)`
* **Índices baseados em função:**
  * `ix_tbsss_tck_fila ((CASE WHEN status = 'PENDING' THEN prioridade END), (CASE WHEN status = 'PENDING' THEN scheduled_at END))` contém apenas os `PENDING`
  * `ix_tbsss_tck_run ((CASE WHEN status = 'RUNNING' THEN agente_id END))` contém apenas os `RUNNING`
* Retenção: IX `ix_tbsss_tck_crt (created_at)`
* **CK:**
  * `ck_tbsss_tck_stat (status IN ('PENDING','RUNNING','SUCCESS','FAILED','CANCELLED'))`
  * `ck_tbsss_tck_prio (prioridade BETWEEN 1 AND 4)`
  * `ck_tbsss_tck_cancreq (cancel_requested IN ('S','N'))`
  * `ck_tbsss_tck_logtr (log_truncado IN ('S','N'))`
  * `ck_tbsss_tck_motivo (status_motivo IS NULL OR status_motivo IN ('EXIT_OK','EXIT_ERROR','KILLED_SIGNAL','TIMEOUT','NODE_OFFLINE','ORPHAN_PROCESS','FENCED','PRECHECK_FAILED','SPAWN_ERROR','LOG_LIMIT','SHUTDOWN','CANCEL_USER'))`
* **Colunas:**
  * `id`
  * `script_id NUMBER(10) NOT NULL`
  * `ambiente VARCHAR2(30 CHAR) NOT NULL`
  * `solicitante VARCHAR2(30 CHAR) NOT NULL`
  * `ip_origem VARCHAR2(45 CHAR)`
  * `agente_id VARCHAR2(30 CHAR)`
  * `process_id NUMBER(8)`
  * `process_start NUMBER(20)`
  * `status VARCHAR2(15 CHAR) DEFAULT 'PENDING' NOT NULL`
  * `prioridade NUMBER(1) DEFAULT 2 NOT NULL`
  * `cancel_requested CHAR(1) DEFAULT 'N' NOT NULL`
  * `status_motivo VARCHAR2(30 CHAR)`
  * `parent_ticket_id NUMBER(10)`
  * `agendamento_id NUMBER(10)`
  * `parametros_enviados CLOB NOT NULL`
  * `log_output CLOB`
  * `log_truncado CHAR(1) DEFAULT 'N' NOT NULL`
  * `return_code NUMBER(6)`
  * `scheduled_at DATE DEFAULT SYSDATE NOT NULL`
  * `started_at DATE`
  * `heartbeat_at DATE`
  * `finished_at DATE`
  * `created_at DATE DEFAULT SYSDATE NOT NULL`
* **Armazenamento:** `LOB (parametros_enviados, log_output) STORE AS SECUREFILE (CACHE)`, que exige tablespace ASSM e `COMPATIBLE >= 11.1`. `init_db.py --lob-basicfile` aplica o fallback BASICFILE.

### 14. `tbsss_ticket_resp`
* PK `pk_tbsss_ticket_resp` · UK `uk_tbsss_trsp_tck_prm (ticket_id, parametro_id)`
* FK `fk_tbsss_trsp_tck → tbsss_tickets(id) ON DELETE CASCADE` (coberta pela UK)
* FK `fk_tbsss_trsp_prm → tbsss_parametros(id)` · IX `ix_tbsss_trsp_prm (parametro_id)`
* **Colunas:**
  * `id`
  * `ticket_id NUMBER(10) NOT NULL`
  * `parametro_id NUMBER(10) NOT NULL`
  * `valor_resposta VARCHAR2(500 CHAR)`
  * `created_at DATE DEFAULT SYSDATE NOT NULL`

### 15. `tbsss_agentes`
* PK `pk_tbsss_agentes` · UK `uk_tbsss_agt_codigo (codigo)`
* CK: `ck_tbsss_agt_stat (status IN ('ATIVO','PARADO'))`
* **Colunas:**
  * `id`
  * `codigo VARCHAR2(30 CHAR) NOT NULL` (= `agent_id`)
  * `hostname VARCHAR2(64 CHAR) NOT NULL`
  * `pid_daemon NUMBER(8)`
  * `versao VARCHAR2(20 CHAR)`
  * `ambientes VARCHAR2(500 CHAR)`
  * `status VARCHAR2(10 CHAR) DEFAULT 'ATIVO' NOT NULL`
  * `iniciado_em DATE`
  * `heartbeat_at DATE`
  * `created_at DATE DEFAULT SYSDATE NOT NULL`

### 16. `tbsss_auditoria`
* PK `pk_tbsss_auditoria`
* **Índices:**
  * `ix_tbsss_aud_crt (created_at)`
  * `ix_tbsss_aud_ent (entidade, entidade_id)`
  * `ix_tbsss_aud_ator (ator)`
* **Colunas:**
  * `id`
  * `ator VARCHAR2(40 CHAR) NOT NULL` (login, ou `SYSTEM:<agent_id>`)
  * `ip_origem VARCHAR2(45 CHAR)`
  * `acao VARCHAR2(30 CHAR) NOT NULL`
  * `entidade VARCHAR2(30 CHAR) NOT NULL`
  * `entidade_id NUMBER(10)`
  * `detalhe VARCHAR2(1000 CHAR)`
  * `created_at DATE DEFAULT SYSDATE NOT NULL`
* **Ações:** `LOGIN_OK`, `LOGIN_FALHA`, `LOGIN_BLOQUEIO`, `LOGOUT`, `TICKET_CRIAR`, `TICKET_CANCELAR`, `TICKET_REEXECUTAR`, `CAD_INSERIR`, `CAD_ALTERAR`, `CAD_DESATIVAR`, `PERM_ALTERAR`, `AGD_PAUSAR`, `AGENTE_INICIO`, `AGENTE_FIM`, `PURGE`. O catálogo é mantido em código e não usa CK, para permitir extensão.
* A tabela não tem FKs intencionalmente: a trilha sobrevive a exclusões.

---

## 11. Bootstrap, Seed e Retenção

### 11.1 `scripts/init_db.py` (idempotente)

* **Fases**, nesta ordem:
  1. sequences;
  2. tabelas sem FK;
  3. PK, UK e CK;
  4. FKs;
  5. índices;
  6. triggers;
  7. seed;
  8. `DBMS_STATS.GATHER_TABLE_STATS` por tabela.
* Cada objeto é verificado em `ALL_OBJECTS`/`ALL_CONSTRAINTS`/`ALL_INDEXES` (filtro por `owner` via bind) antes da criação. Objetos existentes são registrados como `SKIP`.
* **Opções:**
  * `--dry-run` imprime o DDL sem executar;
  * `--lob-basicfile` aplica o fallback de LOB;
  * **não há** opção de DROP em produção. `--recreate` só é aceito com `SSS_ENV=DEV` e confirmação interativa.
* Toda falha de fase aborta com código diferente de zero e com o objeto e o ORA- no log.
* **Seed** via `MERGE` (idempotente): o catálogo de funcionalidades (§4.3.D) e o perfil `ADMINISTRADOR` (`is_admin = 'S'`).
* **Administrador inicial:** o login vem de `--admin-login`, e a senha é lida de `getpass` ou de `SSS_BOOTSTRAP_ADMIN_PASSWORD`. Nunca há valor fixo no código.
* Se o usuário de aplicação for diferente do `owner`, o script emite os `GRANT`s e documenta os sinônimos necessários. Todo SQL da aplicação já qualifica o `owner`.

### 11.2 Esquema e testes

`scripts/test_db_schema.py` consome o mesmo registro de identificadores do `init_db.py` e falha se qualquer nome expandido com o `table_prefix` configurado (e com o prefixo de pior caso de 8 caracteres) exceder 30 caracteres. Os demais requisitos estão no `AGENTS.md` §7.

### 11.3 `scripts/purge.py` (retenção)

* Remove tickets terminais com `created_at < SYSDATE - :ticket_retention_days`, em lotes:
  ```sql
  DELETE FROM {owner}.tbsss_tickets
   WHERE created_at < :limite
     AND status IN ('SUCCESS','FAILED','CANCELLED')
     AND ROWNUM <= :lote
  ```
  Com `COMMIT` por lote, até `rowcount = 0`.
* `tbsss_ticket_resp` é removida em cascata, e `parent_ticket_id` dos filhos vira `NULL`.
* `tbsss_auditoria` usa `audit_retention_days` e o mesmo padrão de lote.
* Os logs locais de ticket mais antigos que `local_log_retention_days` são removidos.
* A execução é agendada via cron do sistema operacional no servidor do agente e auditada como `PURGE`.

---

## 12. Configuração

### 12.1 `instance/config.ini` (sem segredos; unidades no nome da chave)

```ini
[app]
sss_env = DEV                     ; DEV | HML | PROD
data_backend = FAKE               ; FAKE (somente DEV) | ORACLE

[oracle]
user = gfcadastro
dsn = 10.0.0.1:1521/servico_homolog
owner = gfcadastro
table_prefix = tbsss_
driver = oracledb                 ; oracledb | cx_Oracle
use_thick_mode = true
oracle_client_lib_dir =           ; somente macOS/Windows (dev); no Linux usar ldconfig/LD_LIBRARY_PATH
call_timeout_ms = 30000
pool_min = 1
pool_max = 4

[secrets]
secrets_file = /etc/sss/secrets.cfg

[agent]
agent_id = srv-linux-prod-01
ambientes_atendidos = PRODUCAO,HOMOLOGACAO
base_script_dir = /opt/automacoes/scripts
work_dir = /var/lib/sss/work
script_owner_uids = 0
max_parallel_jobs = 4
max_parallel_hard_limit = 32
claim_batch_size = 20
schedule_batch_size = 50
orchestrator_interval_s = 10
cancel_poll_interval_s = 2
heartbeat_interval_s = 10
fence_timeout_s = 90
node_offline_timeout_s = 180
kill_grace_s = 5
script_timeout_s = 21600
shutdown_mode = TERMINATE         ; TERMINATE | DRAIN
shutdown_grace_s = 30
misfire_policy = RUN_ONCE         ; RUN_ONCE | SKIP
misfire_tolerance_s = 300
cron_horizon_days = 1461
child_locale = C.UTF-8
env_passthrough = ORACLE_HOME,TNS_ADMIN,NLS_LANG,LD_LIBRARY_PATH

[logging]
log_dir = /var/log/sss
level = INFO                      ; DEBUG | INFO | WARN | ERROR
app_log_max_bytes = 10485760
app_log_backups = 10
max_log_size_bytes = 5242880
max_local_log_size_bytes = 52428800
local_log_retention_days = 30

[web]
session_idle_timeout_s = 1800
login_max_tentativas = 5
login_bloqueio_s = 900
log_poll_interval_s = 3
trusted_proxies =
allowed_origins = https://sss.empresa.local   ; lista separada por vírgula, validada contra Origin/Referer

[retencao]
ticket_retention_days = 180
audit_retention_days = 730
purge_batch_size = 1000
```

Toda chave é validada por tipo e faixa na inicialização (`sss_config.py`). Chave desconhecida, ausente ou fora da faixa interrompe a subida com a chave e o motivo no log.

### 12.2 Launchers

`bin/sss-web.sh` e `bin/sss-scheduler.sh` devem:

* exportar `LD_LIBRARY_PATH` do Instant Client 19 (quando não houver `ldconfig`) e `TZ`;
* aplicar `umask 077`;
* recusar a execução como root;
* fazer `exec` do processo Python, para que os sinais cheguem diretamente a ele.

**Hardening do web2py em HML e PROD:**
* As aplicações de exemplo `admin`, `welcome` e `examples` são **removidas** do pacote implantado.
* `routes.py` fixa `script_scheduling_service` como aplicação padrão e única.
* `applications/script_scheduling_service/controllers/dev.py` não é implantado.

---

## 13. Observabilidade

* **Logs da aplicação:**
  * Arquivos `log_dir/sss_web.log` e `log_dir/sss_scheduler.log`, com `RotatingFileHandler` (`app_log_max_bytes`, `app_log_backups`).
  * Formato: `%(asctime)s %(levelname)s [pid=%(process)d] [agente=<id>] [ticket=<id|->] [acao=<CLAIM|SPAWN|HB|...>] %(message)s`, com data ISO local e offset.
* **Níveis:**

  | Nível | Uso |
  |---|---|
  | DEBUG | SQL lógico (nome da operação, sem valores sensíveis) e `argv` mascarado |
  | INFO | Transições de ticket e ciclos |
  | WARN | Pausas, skips, reconexões e *misfire* |
  | ERROR | Falhas de operação, `OWNERSHIP_LOST` |
  | CRITICAL | Fencing e falhas de inicialização |

* Todo `except` registra o ORA- e o stack trace em ERROR antes de qualquer `ROLLBACK`.
* É proibido registrar senhas, `PADRAO_VALOR_RUN_CONEXAO_BD`, `cookie_key`, o conteúdo de `secrets.cfg` e valores de parâmetros sensíveis.
* **Visão operacional:** a tela de agentes (`VER_AUDITORIA`) lista `tbsss_agentes` com o heartbeat e os tickets `RUNNING` de cada agente.

---

## 14. Riscos Residuais Aceitos

| Risco | Mitigação vigente |
|---|---|
| Credencial legível em `/proc/<pid>/environ` (mesmo UID ou root) | UID dedicado, sem shell interativo, e servidor restrito |
| Argumentos visíveis em `ps` | Proibição de parâmetro de senha; parâmetros sensíveis apenas mascarados na UI e nos logs |
| Script que faça `setsid`/double-fork escapa do `killpg` | Homologação do script no catálogo; política de revisão de código dos scripts |
| TOCTOU entre a validação e o `exec` | Árvore de scripts não gravável pelo agente (§8.5) |
| Granularidade fina "perfil × script × ambiente" | Não suportada; a intersecção `perfil_amb ∩ script_amb` atende ao escopo atual |
| Semântica de horário de verão | Horário de parede do servidor Oracle (§7.1) |
| Lacunas em sequences | Aceitas por design |
