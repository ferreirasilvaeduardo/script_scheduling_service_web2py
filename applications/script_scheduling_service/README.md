# Script Scheduling Service (SSS) — README.md

Serviço web corporativo para gestão, agendamento e execução distribuída de rotinas em Python e Shell em servidores Unix/Linux restritos, integrado ao Oracle Database >= 11gR2 e com arquitetura multi-ambiente e multi-nó.

> **Change requests aplicados:** CR-001 (agente multiplataforma), CR-002 (Oracle único e driver adaptativo), CR-003 (correções da análise funcional pós-F6.1) e CR-004 (telas de consulta e linguagem clara), em `docs/arquitetura/`. O texto abaixo já os incorpora.
>
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

* **Python 3.6.0 ou superior** com o framework **web2py**.
  * A sintaxe e a biblioteca padrão usadas são as da 3.6.0.
  * As versões validadas vão da 3.6.0 à 3.13, e a 3.6.8 é a referência de produção (AGENTS §2.1).
  * A versão do web2py é homologada e fixada no repositório. Patches locais no framework, todos marcados com `SSS:` no código:
    * `gluon/contrib/multipart.py`: proteção de import para rodar na 3.6.0 (`typing.AsyncGenerator` só existe a partir da 3.6.1);
    * `gluon/contenttype.py`: tipo `font/woff2` para as fontes locais (§2.4).
* É proibido usar recursos de Python 3.7+. A lista normativa completa está no `AGENTS.md` §2.1.

### 2.2 Banco de dados

* **Somente Oracle Database (CR-002).** O **11gR2** é o piso de compatibilidade, com suporte às versões superiores (12c, 18c, 19c, 21c, 23ai). Todo SQL e DDL deve rodar no 11gR2, mesmo que o servidor seja mais novo.
* **SQL Oracle 11gR2 escrito diretamente** nos repositórios, sem camada de dialeto (§2.7).
* **Charset:** AL32UTF8. Toda coluna textual usa `VARCHAR2(N CHAR)`.
* **Teto de 30 caracteres** para todo identificador, inclusive após a expansão do prefixo (§9).

### 2.3 Conectividade (dependências homologadas pré-instaladas)

| Componente | Versão permitida | Observação |
|---|---|---|
| Driver (Python 3.6) | `python-oracledb 1.x` (`< 2.0`), com `cryptography <= 40.x`; contingência `cx_Oracle 8.3` | A série 2.x exige Python 3.7+ |
| Driver (Python 3.7 a 3.13) | `python-oracledb 2.x`; contingência `cx_Oracle 8.3` (até 3.10) | — |
| Cliente C (modos Thick e cx_Oracle) | **Oracle Instant Client 19.x** (Linux, Unix ou Windows, conforme o nó) | Conecta do 11.2.0.4 ao 23ai. O IC 21c/23ai não conecta ao 11gR2. Obrigatório nos nós que acessam banco 11g; recomendado em todos como contingência |

**Seleção do driver (CR-002, `[oracle] modo_driver`):**

* `auto` (padrão): ordem **Thin → Thick → cx_Oracle**.
  * O modo Thin dispensa o Instant Client, mas só conecta a banco **12.1 ou superior** (no 11gR2 falha com `DPY-3010`).
  * Como o modo do `oracledb` é fixado por processo, a escolha é feita **antes da primeira conexão** por um subprocesso de sondagem (`scripts/sondar_driver.py`), um candidato por vez: importa o driver, conecta e executa `SELECT SYSDATE FROM DUAL`. O processo principal inicializa apenas o candidato vencedor.
  * Erro de **autenticação** (ORA-01017, ORA-28000, ORA-28001, ORA-01005) interrompe a cadeia e aborta, para não consumir tentativas de login do usuário no banco. Os demais erros geram WARN e passam ao próximo candidato.
  * Se nenhum candidato conectar, a subida aborta com CRITICAL listando o código de erro de cada tentativa.
  * A senha chega ao subprocesso pela entrada padrão, nunca por argumento ou variável de ambiente.
  * A combinação escolhida é registrada em INFO, exibida pelo `check_env.py` e mantida pelo processo; reconexões a reutilizam e só um reinício refaz a sondagem.
* `thin`, `thick` ou `cx_oracle`: força um único candidato, sem sondagem; falha é fatal.
* **Carregamento do Instant Client no Linux/Unix** (Thick e cx_Oracle): o IC deve estar no caminho de bibliotecas **antes** de o processo Python iniciar, via `ldconfig` (preferencial) ou `LD_LIBRARY_PATH` exportado pelos launchers `bin/sss-web.sh` e `bin/sss-scheduler.sh`. Nessas plataformas, `init_oracle_client(lib_dir=...)` não tem efeito e deve ser chamado sem `lib_dir`.
* **Carregamento no Windows:** `init_oracle_client(lib_dir=oracle_client_lib_dir)`, com o mesmo caminho incluído no `PATH` pelos launchers `bin/sss-web.ps1` e `bin/sss-scheduler.ps1`.
* **Desenvolvimento em macOS:** `oracle_client_lib_dir` só é usado em macOS/Windows. O IC 19 para macOS existe apenas para Intel (x86_64). Em Apple Silicon, use o modo Thin (banco 12.1+), Python x86_64 sob Rosetta ou um container/VM Linux x86_64.
* `modules/db_conn.py` é a **única** porta de acesso ao banco. Ele contém a seleção do driver, o adaptador das diferenças de API entre `oracledb` (Thin/Thick) e `cx_Oracle` (exceções mapeadas por driver e modo para os erros do contrato, tipos de bind, conversão do estilo `:nome` para o `paramstyle` do driver, pool e `init_oracle_client`).
* **Toda conexão deve:**
  * usar `autocommit = False`;
  * definir `call_timeout` (`call_timeout_ms` no config);
  * preencher `module`, `action` e `client_identifier` para rastreabilidade pelo DBA (por exemplo, `module='SSS_SCHED'`, `action='CLAIM'`, `client_identifier=<agent_id ou login>`).
* **Reconexão:** em erros de rede (Thick/cx_Oracle: ORA-03113, ORA-03114, ORA-03135, ORA-12541, ORA-12170, DPI-1080; Thin: os equivalentes `DPY-*`, como DPY-4011 e DPY-6005; a lista é mapeada por driver e modo no `db_conn`), o daemon reconecta com *backoff* exponencial de 1 s a 60 s, registrando WARN a cada tentativa.

### 2.4 Frontend

* HTML5, **Bootstrap 5.3.8** e **Alpine.js (build CSP)**, servidos exclusivamente de `static/` com fontes locais.
* **Identidade visual Kyros** (Manual de Marca), aplicada pelos tokens de `static/css/sss.css`:
  * **Cores:** Roxo Vivo `#5f0684` (ações primárias, links, cabeçalho), Azul Esverdeado `#4daf9a` (destaques, item ativo, faixa do cabeçalho) e Amarelo `#faba00` (avisos e faixa de ambiente). As variações claras e escuras do manual são usadas no modo escuro e nos estados de passar o mouse e de clique.
  * **Contraste:** todo par texto/fundo atende WCAG AA (≥ 4,5:1, verificado por `scripts/test_contraste_cores.py`). Por isso o Azul Esverdeado nunca é cor de texto sobre fundo claro (contraste de 2,6:1).
  * **Tipografia:** Montserrat (OFL 1.1), em arquivos `woff2` locais em `static/fonts/montserrat/`, com a licença junto. A Cocomat Light do manual é comercial e não está disponível; os títulos usam Montserrat.
  * **Formas:** cantos levemente arredondados (`--sss-raio: 8px`) e ícones com traço arredondado.
  * **Logo:** a logo oficial não é desenhada nem aproximada (o manual proíbe distorção). Ela só entra quando houver os arquivos oficiais.
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

#### 2.4.2 Linguagem clara (CR-004)

**Público de referência:** qualquer pessoa precisa entender a tela sem treinamento. A régua é **uma criança de 10 anos** que sabe ler: ela deve conseguir responder sozinha "o que eu posso fazer aqui?", "o que está acontecendo?" e "o que eu faço agora?".

Regras para todo texto de interface (rótulos, títulos, mensagens, modais e ajuda):

1. **Frases curtas e diretas**, em português, na voz do sistema falando com o usuário ("Você pode…", "Vamos rodar…"). Nada de jargão sem explicação.
2. **Termo técnico sempre explicado no lugar:** na primeira vez que aparece numa tela (ticket, ambiente, script, agendamento, perfil), vem acompanhado de uma explicação curta no texto de ajuda do campo ou do título. Exemplos:
   * "Ticket: o pedido para rodar um script";
   * "Ambiente: onde o script vai rodar (por exemplo, produção ou homologação)";
   * "Agendamento: uma regra que pede para rodar um script sozinho, de tempos em tempos".
3. **Situação do ticket com nomes simples** (tabela do §5.2.1). O código técnico (`FAILED`, `TIMEOUT`) aparece só como informação secundária no detalhe, para o suporte.
4. **Toda mensagem de erro tem duas partes:** *o que aconteceu* e *o que fazer agora*, nesta ordem e na mesma caixa. As mensagens-padrão estão na tabela abaixo; mensagens de campo dizem o formato esperado **com um exemplo** ("Use o formato AAAA-MM-DD, por exemplo 2026-10-16").
5. **Nunca** mostrar detalhe técnico (ORA-, stack trace, SQL, caminho do servidor para quem não é admin); essa regra continua valendo (AGENTS §3.1).
6. **Cor nunca é o único sinal:** status e avisos têm sempre ícone **e** texto, além da cor (contraste AA, §2.4).

**Mensagens-padrão** (texto exato; `{…}` é preenchido pelo servidor):

| Situação | O que aconteceu | O que fazer agora |
|---|---|---|
| Sem permissão (403) | "Você não tem permissão para abrir esta página." | "Veja em **O que eu posso fazer** o que já está liberado para você, ou peça acesso ao administrador." |
| Não encontrado (404) | "Não encontramos o que você procurou." | "Confira o número ou volte para a lista." |
| Falha interna (500) e falha de infraestrutura | "Algo deu errado do nosso lado." | "Tente de novo em alguns minutos. Se continuar, avise o suporte e informe o horário." |
| Conflito de edição | "Outra pessoa mudou este registro enquanto você editava." | "Recarregue a página para ver a versão nova e faça a sua alteração de novo." |
| Sessão expirada | "Você ficou um tempo sem usar o sistema e saiu por segurança." | "Entre de novo." |
| Login ou senha incorretos | "Usuário ou senha incorretos." | "Confira o que digitou e tente de novo." |
| Conta bloqueada | "Houve muitas tentativas com a senha errada." | "Espere {minutos} minutos ou peça ao administrador para desbloquear." |
| Formulário com erro | "Alguns campos precisam de correção." | "Os campos estão marcados em vermelho, com a explicação embaixo de cada um." |
| Último administrador | "Não pode ficar sem nenhum administrador ativo." | "Antes, dê acesso de administrador a outra pessoa." |

A mensagem antiga de conflito, "O registro foi alterado por outra pessoa. Recarregue a página.", é substituída pela mensagem acima (§10).

#### 2.4.3 Mapa de telas

Todas as telas, quem pode abrir cada uma e para que servem. Telas marcadas com **(CR-004)** são novas ou mudam no CR-004.

| Tela | Rota | Quem pode abrir | Para que serve |
|---|---|---|---|
| Entrar | `default/login` | Todos | Entrar no sistema |
| Painel inicial | `default/index` | Logado | Resumo do que importa para o seu perfil (§13) |
| Minha senha | `default/minha_senha` | Logado | Trocar a própria senha (§4.2) |
| **O que eu posso fazer** (CR-004) | `default/permissoes` | Logado | Ver o que o seu perfil libera e por que algo não aparece (§4.3.E) |
| **Rotinas disponíveis** (CR-004) | `tickets/catalogo` | `EXEC_SCRIPT` | Conhecer os scripts que você pode rodar, onde e como foram as últimas execuções (§5.8) |
| **Histórico do script** (CR-004) | `tickets/historico/<script_id>` | `EXEC_SCRIPT` | Ver como o script se saiu nos últimos 30 dias (§5.8) |
| Disparar script | `tickets/novo` | `EXEC_SCRIPT` | Pedir para rodar um script agora ou num horário (§5.4, **CR-004**: resumo em frase e exemplos) |
| Tickets | `tickets/lista` | `EXEC_SCRIPT` ou `VER_LOGS` | Acompanhar os pedidos e o que está rodando (§4.3.C) |
| Detalhe do ticket | `tickets/detalhe/<id>` | Quem pode ver o ticket | Saber o que aconteceu, ver o log, cancelar ou repetir (§5.7, **CR-004**: frase-resumo e etapas) |
| Agendamentos | `agendamentos/lista`, `form` | `CAD_AGENDAMENTOS` | Criar e cuidar das regras que rodam sozinhas (§7.6) |
| **Agenda** (CR-004) | `agendamentos/agenda` | `CAD_AGENDAMENTOS` | Ver o que vai rodar hoje e nos próximos 7 dias (§7.7) |
| Ambientes | `admin_ambientes/*` | `CAD_AMBIENTES` | Cadastrar onde os scripts rodam |
| Perfis e permissões | `admin_perfis/*` | `CAD_PERFIS` | Definir o que cada perfil pode fazer (§4.3.B.1) |
| **Quem pode o quê** (CR-004) | `admin_perfis/quem_pode` | `CAD_PERFIS` | Descobrir quem pode rodar um script ou usar um ambiente (§4.3.B.2) |
| Usuários | `admin_usuarios/*` | `CAD_USUARIOS` | Cadastrar pessoas, senhas e bloqueios |
| Parâmetros | `admin_parametros/*` | `CAD_PARAMETROS` | Cadastrar as perguntas que os scripts fazem (§6.2) |
| Scripts | `admin_scripts/*` | `CAD_SCRIPTS` | Cadastrar scripts, onde podem rodar e que perguntas fazem (§8.5) |
| Auditoria | `auditoria/lista` | `VER_AUDITORIA` | Ver quem fez o quê e quando (§4.4) |
| Agentes | `auditoria/agentes` | `VER_AUDITORIA` | Ver se os servidores que rodam os scripts estão bem (§13) |

As telas novas do CR-004 são **somente de consulta**: não gravam nada, não auditam e usam `GET`. Elas seguem os mesmos guardas, o mesmo escopo de ambiente e o §2.4.1.

### 2.5 Backend de dados (estratégia UI-first)

* Toda persistência passa por **contratos de repositório** em `modules/repo_*.py`: classes abstratas por agregado, sem SQL.
* O contrato tem duas implementações, selecionadas por `[app] data_backend` via `modules/repo_factory.py`:

| Backend | Uso | Implementação |
|---|---|---|
| `FAKE` | Desenvolvimento da UI e testes unitários | `modules/repo_fake/`: memória do processo, seed determinístico e `threading.Lock` por agregado |
| `ORACLE` | Homologação e produção | `modules/repo_oracle/` (§2.7): único local com SQL |

* Os controllers e services **não sabem** qual backend está ativo.
* **Paridade obrigatória:** o FAKE emula a semântica do Oracle que o código consome. Isso inclui `UPDATE` condicional com `rowcount` (transição perdida gera `RepoConflito`), unicidade (`RepoViolacao`), `ON DELETE CASCADE`, triggers de imutabilidade, paginação e ordenação idênticas. Também inclui:
  * **chaves estrangeiras e NOT NULL:** inclusões de ticket, `ticket_resp` e agendamento com script, ambiente (nome), solicitante (login), usuário ou parâmetro inexistente geram `RepoViolacao` com o nome da FK do §10. A UK de `ticket_resp` também é verificada;
  * **limites de coluna** que o código grava, por exemplo `ator` (40) e `detalhe` (1.000) da auditoria;
  * **comparação de texto** idêntica à do Oracle: UKs diferenciam maiúsculas de minúsculas;
  * **cascatas** (`ON DELETE CASCADE` e `SET NULL` do §10): o contrato não expõe exclusão de registros mestres (só o `purge.py`, que é batch e não tem FAKE, apaga linhas). Por isso, não há cascata a emular no FAKE; o `test_repo_contract.py` as cobre **contra o Oracle** (F7.3), com `DELETE` direto no teste.
* **Seed do FAKE coerente com as regras de negócio:** ele também serve de demonstração na homologação e precisa respeitar as regras:
  * funcionalidades com os nomes do §4.3.D;
  * nenhum parâmetro de senha ou credencial (§6.5); o exemplo sensível é um dado pessoal, como um documento;
  * prioridade 1 só em tickets de solicitante admin;
  * snapshot e `ticket_resp` compatíveis com o script e os vínculos de cada ticket;
  * `created_at` nunca no futuro;
  * `proxima_execucao` calculada pelo `recurrence.py`, alinhada ao minuto e à regra;
  * `parametros_json` com as respostas resolvidas completas (§7.6).
* **Relógio do FAKE:** `store.agora()` (hora local sem microssegundos) simula o `SYSDATE` e é o único uso permitido de `datetime.now()` (AGENTS §6).
* **Simulação de execução no FAKE (somente DEV):** não há daemon. Um ticket `RUNNING` do seed avança e termina quando o log é lido pelo visualizador (`_simular_log`). Isso é só demonstração e não tem equivalente no Oracle.
* **Concorrência das transições no FAKE:** as transições web de ticket rodam sob o lock do agregado, então o FAKE nunca chega a perder uma corrida. O tratamento de `rowcount = 0` (`RepoConflito`) nessas transições só é exercitado pelo `test_repo_contract.py` contra o Oracle (F7.3).
* **Exceções de contrato** (`modules/repo_errors.py`): `RepoErro`, `RepoNaoEncontrado`, `RepoConflito`, `RepoViolacao` e `RepoIndisponivel`.
* A suíte `scripts/test_repo_contract.py` roda **a mesma bateria** contra os dois backends. Contra ORACLE, ela só executa se `SSS_TEST_DSN` estiver definido.
* **Trava de ambiente:**
  * `[app] sss_env` aceita `DEV`, `HML` ou `PROD`.
  * `data_backend = FAKE` com `sss_env != DEV` **aborta a subida** com CRITICAL.
  * O FAKE exige servidor web de processo único (o servidor de desenvolvimento do web2py). Com múltiplos workers, cada um teria um estado diferente.
* O daemon (`run_scheduler.py`) **exige** `ORACLE`. Com `FAKE`, ele aborta.

### 2.6 Plataformas suportadas (CR-001)

| Nível | Plataformas | Garantia |
|---|---|---|
| **1** | Linux x86_64 e Windows Server 2016 ou mais novo (x86_64), para o nó web e para o agente | Testes automatizados e roteiro E2E (F9.2) em cada uma |
| **2** | Demais Unix (AIX, Solaris, HP-UX, macOS, BSD) | Mesma camada POSIX; homologação pela infraestrutura sob demanda |

* Toda primitiva de sistema operacional fica em `modules/plataforma/` (§8.0).
* No Windows, as APIs nativas são usadas via `ctypes`, sem dependência nova (`pywin32` e `psutil` continuam proibidos).
* O banco e a UI não dependem da plataforma do nó.
* Um mesmo ambiente pode ter agentes Linux e Windows: o claim respeita os interpretadores de cada agente (§8.2).

### 2.7 SQL Oracle 11gR2 (CR-002)

* O SQL é escrito diretamente na sintaxe aceita pelo **Oracle 11gR2**, em `modules/repo_oracle/`. O CR-002 revogou a camada de dialeto e o SQL ANSI do CR-001.
* **Permitido:** `ROWNUM`, `SYSDATE`, `seq.NEXTVAL FROM DUAL`, `FOR UPDATE WAIT n` (n ≤ 5), `DBMS_LOB.WRITEAPPEND`, `DBMS_LOB.SUBSTR`, `EMPTY_CLOB()`, `MERGE`, `CASE`, `NVL` e `DECODE`. A comparação nula-segura continua `(c = :v OR (c IS NULL AND :v IS NULL))`.
* **Proibido (12c+):** ver AGENTS §4.3. A varredura `test_sql_oracle11g.py` rejeita essa sintaxe em `repo_oracle/` e em `scripts/init_db.py`.
* A aplicação **sempre informa o `id`** na inclusão (`seq.NEXTVAL` lido antes do `INSERT`). A trigger condicional do §10 continua existindo como defesa.
* Os blocos SQL deste README estão na forma que vai para o código.

---

## 3. Topologia e Estrutura do Repositório

### 3.1 Processos

| Processo | Execução | Responsabilidade |
|---|---|---|
| **Web** (1..N nós) | web2py sob WSGI corporativo | UI, autenticação, RBAC, criação e cancelamento de tickets, cadastros |
| **Scheduler/Agente** (1 por servidor executor) | `python web2py.py -S script_scheduling_service -M -R applications/script_scheduling_service/scripts/run_scheduler.py` | Desdobro de agendamentos, claim, execução, heartbeat, cancelamento, coleta de log |

Regras de topologia:

* É proibido instanciar o scheduler em threads dos workers web.
* O daemon é **single-threaded**: um laço de eventos com `time.sleep`/`select`. No POSIX, essa decisão torna seguro o uso de `preexec_fn` (§8.4).
  * A regra vale para o **processo inteiro**, não só para o código do SSS. O daemon sobe via `web2py.py -S ... -M -R`, que carrega o web2py e os models. A inicialização do daemon confere que só existe a thread principal (`threading.active_count() == 1`) antes do primeiro spawn, e aborta com CRITICAL se houver outra.
* O nó web **nunca** sinaliza nem encerra processos do sistema operacional.
* No Windows, o daemon é um processo de console iniciado por um serviço ou pelo Agendador de Tarefas da infraestrutura. Ele para pelo arquivo `work_dir/sss-<agent_id>.stop` ou por `CTRL_BREAK` (§8.11).
* `models/*.py` deve ser leve, pois é carregado pelo daemon com `-M`. Esses arquivos não podem executar DDL, abrir conexão no import nem fazer I/O pesado.

### 3.2 Estrutura de diretórios

```text
bin/
  sss-web.sh   sss-web.ps1         # Linux/Unix e Windows: ambiente do Instant Client/TZ e subida do WSGI
  sss-scheduler.sh   sss-scheduler.ps1   # Linux/Unix e Windows: ambiente e subida do daemon
applications/script_scheduling_service/
  controllers/                # default.py (login), tickets.py, logs.py, agendamentos.py, admin_*.py, auditoria.py, dev.py (somente DEV)
  models/
    00_config.py              # carga e validação de config (sem I/O de banco)
    10_security.py            # sessão, cabeçalhos HTTP, CSRF, guarda RBAC
  modules/
    sss_config.py             # parser e validação tipada do config.ini e do secrets.cfg
    sss_logging.py            # configuração de logging (§13)
    db_conn.py                # seleção do driver (Thin → Thick → cx_Oracle), adaptador, binds, mapa de erros, pool, conexão dedicada do daemon
    plataforma/               # primitivas de SO: posix.py (Linux/Unix) e windows.py (ctypes) (§8.0)
    sql_ident.py              # registro de identificadores, validação de owner/prefixo, nomes qualificados
    repo_errors.py            # exceções de contrato (§2.5)
    repo_factory.py           # seleção do backend FAKE/ORACLE (banco real via repo_oracle)
    repo_*.py                 # contratos abstratos por agregado (sem SQL)
    repo_fake/                # implementação em memória + seed (somente DEV)
    repo_oracle/              # implementação SQL Oracle 11gR2 (único local com SQL, §2.7)
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
    auditoria_service.py      # catálogo de ações, consulta e exportação da trilha (§4.4). A escrita de tbsss_auditoria
                              # é feita pelo próprio repositório, na operação que recebe auditoria= (não existe audit.py)
  scripts/
    init_db.py                # bootstrap idempotente de DDL e seed (§11)
    sondar_driver.py          # sondagem isolada de um candidato de driver (Thin, Thick, cx_Oracle) (§2.3, CR-002)
    run_scheduler.py          # entrypoint do daemon
    purge.py                  # retenção (§11.3)
    test_*.py                 # testes unittest (AGENTS.md §7)
  static/bootstrap/  static/js/alpine.min.js (build CSP)  static/js/app/  static/css/  static/img/  static/fonts/
  views/                      # layout.html, components/*.html, <controller>/*.html
  instance/config.ini         # configuração sem segredos (§12)
  dev/scripts/                # árvore de scripts de exemplo para DEV/testes (nunca implantada)
docs/
  prompts/                    # prompts de execução faseada (UI-first)
/etc/sss/secrets.cfg          # segredos fora do repositório: 0600 no POSIX; no Windows, ex.: C:\ProgramData\SSS\secrets.cfg com DACL restrita (§4.1)
```

---

## 4. Segurança, Segredos, Sessão e RBAC

### 4.1 Gestão de segredos

* **Nenhum segredo** reside no `config.ini`, no repositório ou no banco.
* Os segredos ficam em `secrets_file` (padrão `/etc/sss/secrets.cfg`; no Windows, por exemplo `C:\ProgramData\SSS\secrets.cfg`). Na inicialização, web e daemon validam o arquivo pela camada de plataforma e **recusam a subida** caso ele:
  * não seja um arquivo regular;
  * **POSIX:** tenha dono diferente de `os.geteuid()` ou `mode & 0o077 != 0`;
  * **Windows:** tenha dono diferente do SID do processo, ou DACL com qualquer entrada além do dono e de SYSTEM (inclusive herdada de Users, Authenticated Users ou Everyone).

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
  * Valores com menos de 4 caracteres não são registrados, porque mascará-los apagaria trechos comuns do texto. Segredos reais devem ter 12 caracteres ou mais (§4.2); o risco está aceito no §14.

### 4.2 Autenticação e sessão web

* **Hash de senha:**
  * `hashlib.pbkdf2_hmac('sha256', ...)` com 200.000 iterações e salt de 16 bytes (`secrets.token_bytes`).
  * Formato: `pbkdf2_sha256$200000$<salt_hex>$<hash_hex>`.
  * A comparação usa `hmac.compare_digest`.
  * Se as iterações armazenadas forem menores que o valor vigente, o hash é refeito no próximo login bem-sucedido.
* **Política de senha:** mínimo de 12 caracteres. A senha nunca é registrada em log nem devolvida pela UI.
* **Proteções do login:**
  * Mensagem de erro genérica.
    * A conta bloqueada recebe uma mensagem própria de bloqueio. Para não revelar quais logins existem, um login inexistente que atinge o limite de tentativas recebe a mesma mensagem (bloqueio simulado).
    * O bloqueio simulado de login inexistente fica na memória do processo web. Com vários nós, ou após um reinício, ele pode divergir do bloqueio real, que fica no banco (risco aceito no §14).
  * Para login inexistente, calcula-se um hash fictício, equalizando o tempo de resposta.
  * Após `login_max_tentativas` falhas consecutivas, a conta fica bloqueada (`bloqueado_ate = SYSDATE + login_bloqueio_s/86400`).
    * **Relógio do banco:** o service informa ao repositório apenas `login_bloqueio_s`. O repositório calcula `bloqueado_ate` com `SYSDATE` e grava `ultimo_login = SYSDATE`. O relógio do nó web nunca é usado.
    * Um bloqueio já expirado zera `tentativas_falha` antes de avaliar a nova tentativa, tanto no login quanto em "Minha senha".
  * Um sucesso zera `tentativas_falha` e grava `ultimo_login`.
  * Usuário inativo com a senha correta recebe a mensagem genérica e gera `LOGIN_FALHA`, sem incrementar `tentativas_falha`. Com a senha errada, a falha conta normalmente.
  * Login OK, falha e bloqueio são auditados **na mesma operação do repositório** que atualiza o usuário: os métodos `registrar_sucesso_login` e `registrar_falha_login` do contrato recebem `auditoria=` (mesma transação, §4.4).
  * O rehash da senha (iterações abaixo do vigente) é gravado na mesma operação do sucesso do login.
  * Senhas com mais de 1.024 caracteres são recusadas sem calcular o hash (proteção contra negação de serviço).
* **Sessão:**
  * Armazenada em **cookie cifrado** do web2py (`session.connect(request, response, cookie_key=<secrets>)`). Isso dispensa DAL e funciona com N nós web sem sessão aderente.
  * O payload é mínimo: `usuario_id`, `login`, `perfil_id`, `perm_versao`, `csrf_token` e `ultimo_acesso`.
  * A sessão é renovada no login (`session.renew()`).
  * O timeout por inatividade é `session_idle_timeout_s`. A expiração por inatividade é registrada só no log (INFO), sem auditoria.
  * Cookies com `HttpOnly` e `Secure`.
    * **Exceção de DEV:** com `sss_env = DEV` sobre HTTP (servidor de desenvolvimento), o atributo `Secure` é omitido, porque o navegador descartaria o cookie. Em HML e PROD, `Secure` é sempre enviado.
  * **`SameSite` no Python 3.6:** `http.cookies.Morsel` só aceita o atributo `samesite` a partir do 3.8. No 3.6, a proteção cross-site se apoia em duas camadas:
    * o token CSRF;
    * a checagem obrigatória de `Origin`, ou de `Referer` quando `Origin` estiver ausente, contra `[web] allowed_origins` em todo `POST`.

    Requisição sem nenhum dos dois cabeçalhos é rejeitada com 403.

    **Exceção de DEV:** com `sss_env = DEV`, a origem do próprio `Host` da requisição também é aceita, para permitir o acesso por `localhost`, por IP ou por túnel SSH sem editar `allowed_origins`. Em HML e PROD, vale só a lista configurada.
* **Revalidação a cada requisição:** uma única query por PK junta `tbsss_usuarios` e `tbsss_perfis` e verifica `usuario.ativo`, `perfil.ativo` e `perfil.perm_versao`.
  * Se a versão divergir da sessão, as permissões são recarregadas. O mesmo acontece quando o `perfil_id` do usuário difere do gravado na sessão.
  * Se o usuário ou o perfil estiver inativo, a sessão é encerrada e auditada como `LOGOUT`, com o detalhe `sessão encerrada pela revalidação: <usuário inativo | perfil inativo>`.
  * A revalidação **não** considera `bloqueado_ate`: o bloqueio só impede novos logins. Uma sessão aberta continua válida até expirar, até o logout ou até o usuário ou o perfil ser desativado.
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
* **Gestão de senhas pela UI** (F4.3):
  * **Inclusão de usuário:** a senha inicial passa pela política e exige confirmação. Grava `senha_hash` (nunca a senha) e `senha_alterada_em`.
  * **Redefinir senha** (administrador, `CAD_USUARIOS`): aplica a política com confirmação e zera `tentativas_falha` e `bloqueado_ate`. A auditoria é `CAD_ALTERAR` com detalhe `senha redefinida`, sem o valor. Não existe "trocar no próximo login".
  * **Desbloquear:** zera tentativas e bloqueio, com auditoria `CAD_ALTERAR`. A ação é auditada mesmo quando a conta não estava bloqueada.
  * **Nova senha igual à atual:** é aceita em todas as telas. Não há histórico de senhas.
  * **Minha senha** (`default/minha_senha`, qualquer usuário logado):
    * exige a senha atual. Uma senha atual errada **conta como falha de login**, com o mesmo limite e bloqueio do item "Proteções do login" e auditoria `LOGIN_FALHA`;
    * se a conta for bloqueada, a sessão é encerrada;
    * no sucesso, a sessão é renovada (`session.renew()`, com novo token CSRF) e a troca é auditada (`CAD_ALTERAR`, "senha alterada pelo próprio usuário").
  * **Autoproteção:** pela administração, o usuário logado não pode:
    * desativar a si mesmo;
    * trocar o próprio perfil administrativo por um não administrativo;
    * redefinir a própria senha (para isso existe "Minha senha", que exige a senha atual).
  * **Senhas não aparecem em lugar nenhum:** campos `type="password"`, nunca reapresentados. A listagem e o formulário recebem os registros sem `senha_hash`. Os controllers retiram as senhas de `request.vars` logo após a leitura, porque o ticket de erro do web2py grava as variáveis da requisição.
* **IP de origem:** usa `request.env.remote_addr`. O `X-Forwarded-For` só é aceito se o `remote_addr` constar em `trusted_proxies`. Nesse caso, a lista é lida da direita para a esquerda, e o IP de origem é o primeiro endereço que não é um proxy confiável.
* **Retorno após o login (`next`):** só caminhos locais da aplicação são aceitos; URL externa é ignorada. O `next` só é gerado quando a requisição sem sessão é um GET ou HEAD. Um POST sem sessão redireciona ao login sem `next`.
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
     * Na UI (F4.5), só ambientes ativos podem ser **adicionados**. Homologações existentes a ambientes inativos aparecem marcadas com o selo "inativo" e **podem ser removidas** (desmarcadas), mas nunca readicionadas enquanto o ambiente estiver inativo.
     * Script inativo pode ter a homologação editada: a regra vale para o caso de ele ser reativado.
     * A alteração é auditada (`CAD_ALTERAR`, `homologação: +A, -B`).
     * O modal mostra os agendamentos ativos afetados nos ambientes removidos.
* **Decisão composta para executar** (`rbac.pode_executar(usuario, script, ambiente)`), verdadeira somente se todas as condições forem atendidas:
  * usuário ativo **e** perfil ativo;
  * script ativo **e** ambiente ativo **e** par (script, ambiente) presente em `tbsss_script_amb`;
  * perfil admin, **ou** (funcionalidade `EXEC_SCRIPT` **e** ambiente em `perfil_amb` **e** script em `perfil_scr`).
* **Perfis administrativos** (`is_admin = 'S'`) dispensam as dimensões 1, 2 e 3. Eles **não** dispensam as flags `ativo` nem a homologação (dimensão 4).
* Toda ação do servidor reautoriza com os IDs recebidos. Campos ocultos e IDs do cliente nunca são confiáveis.
* **`perm_versao`:** qualquer alteração em perfil, na matriz do perfil, em `is_admin` ou em `ativo` incrementa `tbsss_perfis.perm_versao` **na mesma transação**.
  * Desativar um usuário ou trocar o perfil dele também incrementa o `perm_versao` dos perfis de origem e de destino. Por isso, uma edição de matriz aberta ao mesmo tempo nesses perfis recebe a mensagem de conflito e precisa ser recarregada.

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
* A rejeição é `RepoViolacao(constraint='sss_ultimo_admin')`, uma regra de aplicação e não uma constraint do banco. A UI exibe a mensagem-padrão do §2.4.2: "Não pode ficar sem nenhum administrador ativo. Antes, dê acesso de administrador a outra pessoa."
* Um perfil `is_admin = 'S'` sem usuários ativos não conta como administrador ativo.
* Para usuários (`repo_usuarios.alterar`), a proteção vale ao desativar o usuário ou ao movê-lo para um perfil não administrativo (ou inativo). No Oracle, é o mesmo `SELECT ... FOR UPDATE WAIT 5`, na mesma transação do `UPDATE`.
* **Autoproteção no cadastro de perfis:** o usuário logado não pode remover `is_admin` nem desativar **o próprio perfil**. A tentativa é recusada com "Você não pode remover o acesso administrativo do seu próprio perfil." ou "Você não pode desativar o seu próprio perfil.", sem gravar nem auditar. Isso vale mesmo que existam outros administradores, e complementa a autoproteção da tela de usuários (§4.2).
  * Não há proteção contra um perfil **não** administrativo retirar da própria matriz `CAD_PERFIS` ou `CAD_USUARIOS`. Quem fizer isso perde o acesso à tela no próximo clique, e um administrador pode restaurar a permissão.
* **Filtro de situação na lista de usuários:** Ativos, Inativos e **Bloqueados**, que são os usuários com `bloqueado_ate` ainda vigente (filtro `bloqueado_em` do contrato).

#### B.1 Matriz de permissões na UI (`admin_perfis`)

* **Um único POST** com as três listas (funcionalidades, ambientes e scripts), revalidado inteiro no servidor.
* **Concorrência:** a tela envia o `perm_versao` lido. `matriz_salvar` só grava se ele não tiver mudado; senão, `RepoConflito`.
* **Validação dos IDs:**
  * um ID inexistente ou não numérico rejeita a operação inteira;
  * só itens **ativos** podem ser adicionados;
  * associações já existentes a itens **inativos** aparecem marcadas, com o selo "inativo", e **podem ser removidas** (desmarcadas). Elas nunca podem ser readicionadas enquanto o item estiver inativo. O servidor recusa a adição e aceita a remoção;
  * **limite operacional:** a matriz trabalha com até 1.000 ambientes e 1.000 scripts cadastrados. Acima disso, IDs válidos ficariam de fora da validação, então o limite deve ser revisto antes de ser atingido.
* **Auditoria `PERM_ALTERAR`:** o `detalhe` é o diff `+EXEC_SCRIPT, -VER_LOGS, +amb:PRODUCAO, -scr:carga_diaria` (por dimensão, rótulo e sinal). Salvar sem mudança não incrementa `perm_versao` nem audita. O resumo do modal de confirmação usa o mesmo formato.
* **Perfil administrativo:** a matriz continua editável e registrada, com um aviso de que o perfil dispensa as dimensões 1 a 3 (mas não a homologação). Ela passa a valer se `is_admin` for removido.
* **Desativar perfil:** o modal mostra a quantidade **e os logins** dos usuários ativos afetados (no máximo 20, seguidos de "e outros N"), que têm a sessão encerrada no próximo request pela revalidação (§4.2).

#### B.2 Consulta "Quem pode o quê" (`admin_perfis/quem_pode`, CR-004)

Responde às duas perguntas mais comuns do administrador, sem abrir perfil por perfil. A tela é só de consulta e exige `CAD_PERFIS`.

* **Por script:** escolhe-se um script e a tela lista os **perfis ativos** que podem executá-lo. Para cada perfil, mostra:
  * os **ambientes onde ele pode rodar** esse script: a interseção `perfil_amb ∩ homologação`, só com ambientes ativos. Para perfil admin, todos os ambientes ativos homologados;
  * quantos **usuários ativos** o perfil tem;
  * o motivo de cada perfil estar na lista: "administrador" ou "tem Disparar Scripts, o ambiente e o script".
* **Por ambiente:** escolhe-se um ambiente e a tela lista os perfis ativos que o acessam e, para cada um, os scripts homologados ali que eles podem rodar.
* Perfis **inativos** aparecem num bloco separado, "Não valem agora (perfil inativo)". Script ou ambiente **inativo** gera um aviso no topo: "Este script está inativo: ninguém consegue rodá-lo agora."
* A regra usada é a mesma de `rbac.pode_executar` (§4.3.A), aplicada perfil a perfil. O cálculo é feito no service com as leituras que já existem no contrato (`perfis_listar`, `matriz_obter`, catálogo e homologações), sem método novo.
* Cada perfil tem um link para a matriz dele (§4.3.B.1).
* A tela de perfis ganha o botão "Quem pode o quê".

#### C. Escopo das funcionalidades operacionais

| Funcionalidade | Escopo |
|---|---|
| `EXEC_SCRIPT` | Criar tickets e reexecutar tickets próprios, sujeito a `pode_executar`. **Perfil admin** reexecuta qualquer ticket que consegue ver. O novo ticket registra o admin como solicitante, então não há uso de privilégio alheio |
| `VER_LOGS` | Tickets de ambientes autorizados ao perfil (admin: todos). Respostas de parâmetros `sensivel = 'S'` aparecem mascaradas. **Sem** `VER_LOGS`, quem tem `EXEC_SCRIPT` vê, lista e lê o log apenas dos **próprios** tickets |
| `CANC_TICKET` | Cancelar qualquer ticket de ambiente autorizado, **sem** exigir `VER_LOGS`: a decisão é só de `rbac.pode_cancelar`. **Sem** esta funcionalidade, o solicitante com `EXEC_SCRIPT` pode cancelar apenas os próprios tickets, mesmo que tenha perdido o acesso ao ambiente |
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

* O seed (FAKE e `init_db.py`) grava os nomes e as finalidades **exatamente** como nesta tabela, com acentuação. A matriz de perfis exibe esses textos.
* **Não existe tela de cadastro de funcionalidades.** O catálogo é fixo: cada código está ligado a rotas e guardas no código (`ui_menu.py`, `_exigir_func`), então um código novo sem rota não teria efeito. Novas funcionalidades entram por change request, com seed e código no mesmo pacote.
* A associação perfil × funcionalidade (`tbsss_perfil_func`) é editada **somente** na aba Funcionalidades da matriz de permissões (§4.3.B.1), no mesmo POST de ambientes e scripts.

#### E. Tela "O que eu posso fazer" (`default/permissoes`, CR-004)

Qualquer usuário logado pode abrir. Ela responde, em linguagem simples (§2.4.2), "o que eu posso fazer aqui?". O acesso fica no cabeçalho, ao lado de "Minha senha", e a mensagem de 403 aponta para ela.

* **Meu perfil:** nome do perfil e, se for administrador, a frase "Seu perfil é de administrador: você pode usar todas as telas e rodar qualquer script ativo, nos ambientes ativos onde ele foi liberado."
* **Telas que posso usar:** as funcionalidades do perfil, com o nome e a finalidade do §4.3.D e um link para cada tela.
* **Onde posso rodar scripts:** os ambientes ativos do perfil, com a descrição de cada um.
* **Scripts que posso rodar:** para cada script, os ambientes onde `rbac.pode_executar` é verdadeiro, com o botão "Rodar aqui" (abre o disparo já preenchido).
* **Por que um script não aparece:** só para os scripts **associados ao perfil** (`perfil_scr`) que não podem rodar em nenhum ambiente. O motivo vem de `pode_executar` em frase simples:
  * "o script está desativado";
  * "o script não foi liberado em nenhum dos seus ambientes";
  * "o ambiente está desativado";
  * "seu perfil não tem Disparar Scripts".

  Scripts fora do perfil **nunca** são listados, para não revelar o catálogo.
* Sem `EXEC_SCRIPT`: a seção de scripts mostra "Você ainda não pode rodar scripts. Peça ao administrador, se precisar."
* No fim da página: "Precisa de mais acesso? Fale com o administrador do sistema." Não há pedido de acesso pelo sistema.
* Usa o contexto da sessão revalidado (§4.2) e as leituras do catálogo que já existem. Não grava nada e não audita.

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

* **Mesma transação:** a linha de auditoria é gravada pelo **próprio repositório**, na operação que recebe `auditoria=`. Isso vale também para o login (§4.2). O service nunca grava a auditoria numa chamada separada.
* **Entidade de cada ação:**

| Ação | `entidade` | `entidade_id` |
|---|---|---|
| `LOGIN_*`, `LOGOUT` | `tbsss_usuarios` | id do usuário (nulo para login inexistente) |
| `TICKET_*` | `tbsss_tickets` | id do ticket |
| `CAD_*` | tabela do cadastro | id do registro |
| `PERM_ALTERAR` | `tbsss_perfis` | id do perfil |
| `AGD_PAUSAR` | `tbsss_agendamentos` | id da regra |
| `AGENTE_INICIO`, `AGENTE_FIM` | `tbsss_agentes` | id do agente |
| `PURGE` | tabela purgada (`tbsss_tickets` ou `tbsss_auditoria`), uma linha por tabela | nulo |
| `AUD_EXPORTAR` | `tbsss_auditoria` | nulo |

  O filtro "Entidade" da consulta oferece exatamente as tabelas acima.
* **Limites da coluna:** `ator` tem até 40 caracteres e é obrigatório (nunca é preenchido com um valor padrão). `detalhe` é cortado em 1.000 caracteres, com `...` no final. O FAKE recusa a gravação fora desses limites, como o Oracle.

**Cadastros** (padrão em `docs/PADRAO_CRUD_ADMIN.md`):

| Situação | Ação | `detalhe` |
|---|---|---|
| Inclusão | `CAD_INSERIR` | `campo: valor` **somente dos campos preenchidos**: campos vazios são omitidos. Todos os campos do formulário entram, inclusive `descricao` (parâmetros e scripts) e `etapa` (scripts). Referências aparecem pelo nome: `perfil: OPERADOR_PROD` |
| Alteração | `CAD_ALTERAR` | `campo: antigo → novo`, só dos campos que mudaram (salvar sem mudança não audita) |
| Desativação | `CAD_DESATIVAR` | `ativo: S → N`, mais o impacto (ex.: `agendamentos ativos afetados: 2`) |
| Reativação | `CAD_ALTERAR` | `ativo: N → S` (não existe ação `CAD_REATIVAR`) |

Todo `detalhe` passa pelo `masking.py`, inclusive os de vínculos de parâmetros, homologação e matriz, e é limitado a 1.000 caracteres. Valores de parâmetros sensíveis aparecem sempre como `****`.

**Consulta e exportação** (tela `auditoria/lista`, `VER_AUDITORIA`, decisões do F6.1):

* Filtros: período (`de`/`até`, por dia, inclusivos), ator (trecho), ação (catálogo da tabela 16), entidade, `entidade_id` e IP (trecho). Ordenação `created_at DESC, id DESC` e página de no máximo 100 linhas.
* Período padrão: últimos 7 dias. Período máximo: 90 dias. Acima disso, até 366 dias, só com filtro seletivo: ator, ou entidade + ID.
* O `detalhe` é sempre exibido escapado (truncado com "ver mais"), e passa de novo pelo `masking.py` na leitura.
* O ID vira link só quando a entidade tem tela (tickets, agendamentos, usuários, perfis, ambientes, scripts e parâmetros) **e** o usuário tem a funcionalidade dessa tela. Nos outros casos, o ID aparece como texto.
* **Exportação CSV** (`auditoria/exportar`):
  * por `POST` com CSRF, porque grava auditoria e `GET` nunca altera estado;
  * mesmos filtros e mesmo RBAC da tela;
  * streaming de no máximo 50.000 linhas (as mais recentes);
  * UTF-8 com BOM, separador `;`, cabeçalho em português e datas `AAAA-MM-DD HH:MM:SS`;
  * neutralização de *CSV injection*: texto iniciado por `=`, `+`, `-`, `@`, TAB ou CR recebe o prefixo `'`;
  * auditada com a ação `AUD_EXPORTAR` (entidade `tbsss_auditoria`, `detalhe` = filtros + quantidade de linhas), gravada antes do streaming. O arquivo para no ID anterior ao dessa linha.
  * **Quantidade registrada:** o `id` da linha de auditoria é obtido primeiro (`seq.NEXTVAL`, §2.7), e `id_max = id − 1`. A quantidade é contada sobre os filtros com `id <= id_max` e limitada a 50.000. Só então a linha é gravada, com essa quantidade, e o streaming lê o mesmo conjunto. Assim, a contagem e o arquivo correspondem ao mesmo recorte.
* Contrato: `RepoAuditoria.iterar(filtros, limite)` alimenta o streaming (no Oracle, um cursor com `arraysize`, sem paginação por offset). O filtro `id_max` delimita o conjunto exportado.

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

#### 5.2.1 Explicação ao usuário (CR-004)

Na interface, a situação do ticket usa **nomes simples** (§2.4.2), sempre com ícone e cor. O código técnico fica como informação secundária no detalhe.

| Status | Nome na tela | Antes do CR-004 |
|---|---|---|
| `PENDING` | Esperando | Pendente |
| `RUNNING` | Rodando | Em execução |
| `SUCCESS` | Deu certo | Sucesso |
| `FAILED` | Deu erro | Falha |
| `CANCELLED` | Cancelado | Cancelado |

Os filtros da lista de tickets usam os mesmos nomes. A auditoria, o CSV e o banco continuam com os códigos.

**Frase do que aconteceu e o que fazer** (exibida no topo do detalhe, §5.7; `{…}` é preenchido pelo servidor):

| Situação | O que aconteceu | O que fazer agora |
|---|---|---|
| `PENDING`, `scheduled_at` no futuro | "Está agendado para começar em {data} às {hora}." | "Não precisa fazer nada. Se não quiser mais, cancele." |
| `PENDING`, já pode rodar | "Está na fila, esperando um servidor livre." | "Não precisa fazer nada. Esta página se atualiza sozinha." |
| `RUNNING` | "Está rodando agora. Começou há {tempo}." | "Acompanhe o log abaixo." |
| `RUNNING` com cancelamento pedido | "O cancelamento foi pedido. O servidor está parando o script." | "Espere alguns segundos." |
| `EXIT_OK` | "Terminou e deu certo." | — |
| `EXIT_ERROR` | "O script rodou, mas terminou avisando que algo deu errado (código {n})." | "Veja o fim do log para entender o erro. Se não souber resolver, envie o número deste ticket ao responsável pelo script." |
| `KILLED_SIGNAL` | "O script foi interrompido de repente pelo servidor." | "Tente de novo. Se acontecer outra vez, avise o suporte com o número deste ticket." |
| `TIMEOUT` | "O script demorou mais do que o tempo máximo ({tempo}) e foi parado." | "Confira se as respostas estão certas e tente de novo. Se o script costuma demorar mais, peça ao administrador para aumentar o tempo máximo." |
| `NODE_OFFLINE` | "O servidor que rodava o script parou de responder." | "Tente de novo: outro servidor pode assumir." |
| `ORPHAN_PROCESS` | "O servidor foi reiniciado e perdeu o controle do script." | "Tente de novo." |
| `FENCED` | "O servidor perdeu contato com o banco de dados e parou o script por segurança." | "Tente de novo em alguns minutos." |
| `PRECHECK_FAILED` | "O script não pôde começar: o servidor não encontrou o arquivo, ou ele não está liberado." | "Avise o administrador com o número deste ticket." |
| `SPAWN_ERROR` | "O servidor não conseguiu iniciar o script." | "Avise o administrador com o número deste ticket." |
| `LOG_LIMIT` | "O script escreveu mensagens demais e foi parado, para não lotar o disco." | "Avise o responsável pelo script." |
| `SHUTDOWN` | "O servidor foi desligado enquanto o script rodava." | "Tente de novo." |
| `CANCEL_USER` | "A execução foi cancelada a pedido." | — |
| Motivo desconhecido | "Terminou com um motivo que o sistema não conhece ({código})." | "Avise o suporte com o número deste ticket." |

O catálogo fica num único lugar do código (`ui_helpers.py`), consumido pelas views e testado por `test_ui_helpers.py`. Os textos técnicos atuais de `descricao_motivo` continuam existindo para o suporte e aparecem no detalhe como "Detalhe técnico".

### 5.3 Prioridade

* Escala de **1 (mais alta) a 4 (mais baixa)**, padrão 2.
* Prioridade 1 é reservada a perfis admin.
* A fila ordena por `prioridade`, depois `scheduled_at` e depois `id`.

### 5.4 Criação manual de ticket (transação única)

1. Validar o CSRF e `rbac.pode_executar(usuario, script_id, ambiente)`.
2. Carregar o vínculo `tbsss_script_param` + `tbsss_parametros` (ativos) do script.
3. Validar as respostas e compilar o snapshot (§6). Em caso de erro, retornar o erro por campo, sem gravar nada.
4. Gravar o `scheduled_at` informado (opcional, padrão `SYSDATE`).
   * Ele deve ser `>= SYSDATE` **exato**, sem tolerância de minuto: um horário no minuto corrente, mas anterior ao `SYSDATE`, é recusado.
   * Não há limite superior.
   * O valor digitado no campo de data e hora do navegador é interpretado como horário de parede do servidor Oracle (§7.1). A tela informa isso ao lado do campo.
5. `INSERT INTO tbsss_tickets (...) VALUES (...) RETURNING id INTO :out_id`, com `parametros_enviados` contendo o JSON do snapshot.
6. `INSERT` em `tbsss_ticket_resp` via `executemany`, com os valores **resolvidos** (após a precedência).
7. Auditoria `TICKET_CRIAR` e `COMMIT`. Em qualquer exceção, `ROLLBACK`.

* **Caminho do script na criação:** o nó web valida `path_file` conforme a §8.5 ("Validação no nó web"). O `NAO_E_ARQUIVO` bloqueia a criação em qualquer `sss_env`, porque o ticket não poderia ser executado. A exceção é o interpretador que a plataforma do nó web não suporta: aí vale só a etapa 1, e a validação definitiva fica no claim (§8.4).
* **`ticket_resp`:** respostas sem valor (`None`) não são gravadas. `CHECKBOX` é gravado como `"true"`/`"false"`.

**Clareza no disparo (CR-004):**

* **Explicação das etapas:** cada etapa diz em uma frase o que fazer.
  * "1. Escolha o script, que é a rotina que você quer rodar."
  * "2. Escolha o ambiente, que é onde ela vai rodar."
  * "3. Responda às perguntas."
* **Exemplo em cada pergunta**, gerado pelo tipo do parâmetro, sem coluna nova. Vem junto da `descricao` do parâmetro, se houver:

  | Tipo | Texto de ajuda |
  |---|---|
  | `DATE` | "Use o formato AAAA-MM-DD, por exemplo {hoje}." |
  | `NUMBER` | "Use só números, com ponto para decimais, por exemplo 10 ou 2.5." |
  | `SELECT` | "Escolha uma das opções da lista." |
  | `CHECKBOX` | "Marque para sim; deixe desmarcado para não." |
  | `TEXT` com regex | "Siga o formato pedido pelo cadastro. {descricao}" |
  | `TEXT` sem regex | A `descricao` do parâmetro, se houver |

  Obrigatório aparece como "(obrigatório)" no rótulo, e não só com asterisco.
* **Resumo em frase antes de confirmar:** o modal de confirmação abre com uma frase montada pelo servidor:

  > "Vamos rodar **{script}** no ambiente **{ambiente}** {agora | em {data} às {hora}}, com prioridade {n}. Respostas: {rótulo} = {valor}; …"

  * valores sensíveis aparecem como `****`;
  * respostas vazias aparecem como "(sem resposta)";
  * o comando lógico (argv, §6.4) continua no modal, abaixo da frase, com o título "Comando que será executado".
* **"Usar as respostas da minha última execução":** o botão aparece na etapa 3 quando existe um ticket **do próprio usuário** para o mesmo script e o mesmo ambiente. Ele usa `listar` com os filtros `solicitante`, `script_id` e `ambiente`, `tamanho=1`, e depois `respostas`, sem método novo no contrato.
  * Preenche só as respostas **não sensíveis**; os campos sensíveis ficam vazios, com a nota "por segurança, digite de novo".
  * Uma resposta que não vale mais no catálogo atual (opção removida, formato novo) fica vazia, com o aviso "esta resposta mudou desde a última vez".
  * Nada é gravado até a confirmação, que segue o fluxo normal (§5.4).
* **Aviso de horário:** ao lado do campo de agendamento aparece "Horário do servidor do banco de dados" (§5.4, passo 4).

### 5.5 Reexecução

* Cria um novo ticket com `parent_ticket_id = <original>`.
* As respostas resolvidas do original (`tbsss_ticket_resp`) são **recompiladas contra o catálogo vigente**, gerando um novo snapshot.
* A reexecução exige `pode_executar` vigente.
* O snapshot original permanece intocado.
* **Regras complementares:**
  * só ticket **terminal** pode ser reexecutado;
  * o novo ticket usa o **mesmo script e o mesmo ambiente** do original. Se o pedido divergir, a operação é recusada (`REEXECUCAO_DIVERGENTE`);
  * a prioridade é herdada do original, e `scheduled_at` é `SYSDATE`. Se a prioridade herdada não for mais permitida (prioridade 1 e o usuário deixou de ser admin), a reexecução direta é recusada e o formulário de disparo abre preenchido para ajuste;
  * valores sensíveis são reaproveitados do `ticket_resp` original, sem passar pela tela;
  * se a recompilação falhar (por exemplo, o catálogo mudou), o formulário de disparo abre preenchido com as respostas não sensíveis. Um campo sensível deixado em branco recebe o **padrão vigente** (§6.1), não o valor original;
  * códigos de resposta que não existem mais no catálogo vigente são descartados.

### 5.6 Cancelamento distribuído

**No nó web (uma transação):**

```sql
UPDATE {owner}.tbsss_tickets
   SET cancel_requested = 'S'
 WHERE id = :id AND status IN ('PENDING', 'RUNNING') AND cancel_requested = 'N';

UPDATE {owner}.tbsss_tickets
   SET status = 'CANCELLED', status_motivo = 'CANCEL_USER',
       return_code = -1, finished_at = SYSDATE
 WHERE id = :id AND status = 'PENDING';
```

* Se o primeiro `UPDATE` afetar 0 linhas, o ticket já é terminal **ou** o cancelamento já tinha sido pedido. Para saber qual, a mesma transação lê a linha pela PK (`SELECT status, cancel_requested FROM {owner}.tbsss_tickets WHERE id = :id FOR UPDATE WAIT 5`): terminal dá `sem efeito: ticket encerrado`; `RUNNING` com `cancel_requested = 'S'` dá `já sinalizado`. O sistema informa o usuário nos dois casos.
* Se o segundo afetar 0 linhas, o ticket está `RUNNING` e o agente dono trata o cancelamento.
* A operação é auditada e confirmada com `COMMIT`.
* **Toda solicitação é auditada** (`TICKET_CANCELAR`), inclusive as que não mudam nada. O `detalhe` informa o resultado:

  | Resultado | Situação | Mensagem ao usuário |
  |---|---|---|
  | `cancelado` | Era `PENDING` e virou `CANCELLED` | Ticket cancelado |
  | `sinalizado` | Era `RUNNING`; o agente vai encerrar | Cancelamento solicitado ao agente |
  | `já sinalizado` | `RUNNING` com `cancel_requested = 'S'` já gravado | O cancelamento já havia sido solicitado |
  | `sem efeito: ticket encerrado` | Já era terminal | O ticket já estava encerrado |

  O botão some quando o cancelamento já foi solicitado, mas o servidor trata o POST repetido do mesmo modo.

**No agente dono:** a cada `cancel_poll_interval_s`, executa a varredura combinada da §8.7. Ao encontrar `cancel_requested = 'S'` em ticket próprio:

1. Pedir o encerramento do grupo pela camada de plataforma (§8.0): `SIGTERM` ao grupo no POSIX; `CTRL_BREAK_EVENT` no Windows.
2. Aguardar até `kill_grace_s`, consultando `Popen.poll()`.
3. Se o processo persistir, forçar o encerramento (`SIGKILL` ao grupo no POSIX; `TerminateJobObject` no Windows) e então `Popen.wait()`.
4. Fazer o flush final do log (§8.10).
5. `UPDATE ... SET status = 'CANCELLED', status_motivo = 'CANCEL_USER', return_code = -1, finished_at = SYSDATE WHERE id = :id AND agente_id = :agente_id AND status = 'RUNNING'`, seguido de `COMMIT`.

Se o processo terminou sozinho **antes** de o agente sinalizá-lo, prevalece o resultado real (`SUCCESS` ou `FAILED`).

No POSIX, `ProcessLookupError` no `killpg` é tratado como "grupo já encerrado"; no Windows, o mesmo vale para um Job sem processos.

---

### 5.7 Detalhe do ticket: resumo e etapas (CR-004)

O topo do detalhe (`tickets/detalhe/<id>`) responde "o que está acontecendo?" antes de qualquer dado técnico:

1. **Frase-resumo:** um quadro com o nome simples da situação (§5.2.1), a frase "o que aconteceu" e a frase "o que fazer agora", com ícone e cor da situação.
2. **Barra de etapas**, uma lista ordenada acessível, com `aria-current` na etapa atual:

   | Etapa | Horário exibido | Concluída quando |
   |---|---|---|
   | Pedido criado | `created_at` | sempre |
   | Na fila | `scheduled_at` ("agendado para…" se estiver no futuro) | o ticket saiu de `PENDING` |
   | Rodando | `started_at` | o ticket saiu de `RUNNING` |
   | Terminou | `finished_at`, com o nome simples do resultado | status terminal |

   * Um ticket cancelado ainda na fila mostra a etapa "Rodando" como "não chegou a rodar" e a etapa final como "Cancelado".
   * A etapa atual de um ticket `RUNNING` mostra "há {tempo}".
3. Depois disso vêm, como hoje: resumo, linha do tempo, comando executado, respostas, reexecuções e log. A linha "Detalhe técnico" do resumo traz o status, o `status_motivo`, o `return_code` e a descrição técnica (`descricao_motivo`). O bloco do snapshot mostra a **pasta base** (`pasta_base`, snapshot v3) e o **arquivo na pasta base** (`path_file`) em linhas separadas; snapshot antigo sem pasta base mostra "-".
4. **Botões com o efeito escrito:** "Cancelar este pedido" (com a consequência no modal) e "Rodar de novo com as mesmas respostas" (reexecução, §5.5).
5. A página continua se atualizando sozinha enquanto o ticket não termina, e a frase e a barra acompanham.

### 5.8 Rotinas disponíveis e histórico do script (CR-004)

**Rotinas disponíveis** (`tickets/catalogo`, exige `EXEC_SCRIPT`): responde "o que eu posso rodar?".

* Um cartão por script em que o usuário tem `pode_executar` em **pelo menos um** ambiente (admin: todo script ativo homologado em ambiente ativo). Cada cartão traz:
  * nome, descrição, grupo e categoria;
  * as **perguntas** que o script faz (rótulos, com "(obrigatório)" quando for o caso);
  * os **ambientes** onde o usuário pode rodar, cada um com o botão "Rodar em {ambiente}", que abre o disparo já na etapa 3;
  * a **última execução** que o usuário pode ver: o nome simples da situação, "há {tempo}" e o link para o ticket. Sem nenhuma: "Ainda não rodou";
  * o link "Ver histórico".
* Uma busca no topo filtra os cartões por nome, descrição, grupo e categoria, no navegador (Alpine, `static/js/app/`). A lista completa já vem do servidor. Os cartões ficam agrupados por grupo, como no disparo.
* O **escopo da última execução** é o mesmo da lista de tickets (§4.3.C): com `VER_LOGS`, os tickets dos ambientes autorizados (admin: todos); sem `VER_LOGS`, só os próprios.
* **Contrato (leitura nova):** `RepoTickets.ultimas_execucoes(script_ids, escopo_ambientes=None, solicitante=None)` devolve `{script_id: {id, status, status_motivo, created_at, finished_at}}` com o ticket mais recente (`created_at DESC, id DESC`) de cada script no escopo. No Oracle, a consulta usa `ix_tbsss_tck_scr` e um `ROW_NUMBER()` por script, que é sintaxe 11gR2 e não carrega `log_output`.
* O menu Operação ganha o item "Rotinas disponíveis" (`EXEC_SCRIPT`), antes de "Disparar Scripts".

**Histórico do script** (`tickets/historico/<script_id>`, exige `EXEC_SCRIPT`): responde "esse script costuma dar certo?".

* Abre só para um script que aparece nas Rotinas disponíveis do usuário. Fora disso, 404.
* Período fixo: **últimos 30 dias** pelo relógio do banco (`created_at >= SYSDATE - 30`), no mesmo escopo da última execução.
* Mostra:
  * total de pedidos e quantos **deram certo**, **deram erro**, **foram cancelados** e ainda estão **esperando ou rodando**;
  * **taxa de acerto**: deram certo ÷ terminados, em porcentagem inteira, com a frase "De cada 10 vezes, {n} deram certo";
  * **duração típica** (mediana) e **mais demorada**, só dos que terminaram com `started_at`, em linguagem simples ("cerca de 4 minutos");
  * **gráfico de barras por dia**, empilhado por situação, como SVG gerado no servidor. As cores vêm por classe CSS e não há `style=` inline. Abaixo do gráfico fica a mesma informação em tabela, para leitores de tela;
  * os principais motivos de erro, com a contagem por `status_motivo` e o nome simples;
  * o link "Ver estes pedidos", que abre a lista de tickets filtrada por script e período.
* **Contrato (leitura nova):** `RepoTickets.historico_script(script_id, desde, escopo_ambientes=None, solicitante=None, limite=5000)` devolve só `{id, status, status_motivo, created_at, started_at, finished_at}`, sem LOB, ordenado por `created_at`. A agregação é feita no service. Acima do limite, a tela avisa "mostrando os 5.000 mais recentes".
* Não grava nada e não audita.

## 6. Parâmetros, Validação e Compilação do Snapshot

### 6.1 Precedência de valores

Para cada parâmetro vinculado ao script, nesta ordem:

1. Resposta enviada explicitamente pelo usuário (ou, no agendamento, o valor em `parametros_json`).
2. `tbsss_script_param.valor_padrao_sub`.
3. `tbsss_parametros.valor_padrao`.
4. Sem valor: se `obrigatorio = 'S'`, gera erro de validação. Se for opcional, aplica a regra da estratégia (§6.3).

Os valores padrão (2 e 3) **também** passam pela validação da §6.2.

### 6.2 Validação por `tipo_componente`

Para todos os tipos, **nesta ordem**:

1. o valor recebe `strip()`, que remove espaços, tabulações e quebras de linha das pontas;
2. o resultado é texto UTF-8 com até 500 caracteres;
3. o resultado não pode conter NUL nem caracteres de controle `\x00-\x1f` e `\x7f`. Um controle que estava só nas pontas já foi removido no passo 1 e não causa rejeição.

| Tipo | Regra |
|---|---|
| `TEXT` | Se houver `regex_validacao`, aplica `re.fullmatch` |
| `NUMBER` | `^-?\d{1,18}(\.\d{1,6})?$` |
| `DATE` | `datetime.strptime(valor, '%Y-%m-%d')`, emitido como `YYYY-MM-DD` |
| `SELECT` | O valor deve ser uma chave de `opcoes_json` (objeto JSON `{"valor": "Rótulo"}`, parseado em Python) |
| `CHECKBOX` | Aceita `true`, `false`, `1` e `0` (sem distinção de maiúsculas), normalizados para booleano |

**`CHECKBOX` na prática:**
* `false` é um valor válido, inclusive em parâmetro obrigatório. Obrigatório significa "precisa ter resposta", não "precisa estar marcado".
* No questionário da UI, a caixa sempre envia uma resposta explícita (`true` ou `false`). Por isso, os padrões (§6.1, itens 2 e 3) só se aplicam ao `CHECKBOX` em agendamentos (`parametros_json`) e em chamadas sem a resposta.

**Governança de `regex_validacao`:**

* O padrão é compilado no cadastro, que o rejeita se não compilar.
* Também é rejeitado padrão com quantificador aninhado, detectado pela heurística `\([^)]*[+*][^)]*\)[+*{]`, para mitigar ReDoS. O Python 3.6 não oferece timeout de regex.
* Somente admin cadastra padrões.

**Cadastro no dicionário de parâmetros** (UI `admin_parametros`, F4.4):

* **`codigo` imutável depois de criado:** ele é a chave de `respostas` no snapshot (§6.5) e de `tbsss_agendamentos.parametros_json` (§6.1). Renomeá-lo faria agendamentos perderem respostas sem aviso.
* **`opcoes_json`** (somente `SELECT`) é validado no servidor:
  * objeto JSON não vazio, sem chave repetida;
  * chaves e rótulos não vazios, sem caracteres de controle, com até 100 caracteres cada;
  * até 500 caracteres serializado;
  * a ordem do usuário é preservada.

  O editor de pares valor/rótulo do cliente é apenas conveniência. Em outros tipos, `opcoes_json` é proibido.
* **`regex_validacao`** só existe em `TEXT`.
  * Perfil não admin com `CAD_PARAMETROS`:
    * vê a regex somente leitura, e o servidor preserva a gravada;
    * não troca o tipo de parâmetro que tem regex;
    * não usa "Testar valor" com regex.
  * A regex nunca é executada no navegador.
* **`valor_padrao`** é validado por `validar_valor` contra a configuração em edição e gravado normalizado (`CHECKBOX` → `true`/`false`, `DATE` → `AAAA-MM-DD`), com até 100 caracteres.
* **`valor_padrao` de parâmetro sensível é só de escrita:**
  * campo `password` nunca reapresentado; deixar em branco mantém o valor gravado, e "remover" apaga;
  * na auditoria aparece como `****`;
  * na lista, a coluna "Valor padrão" mostra `****` quando existe um valor sensível, o valor quando não é sensível e `-` quando está vazio;
  * o "Testar valor" responde `****`;
  * **o valor sensível nunca entra no HTML, nem de forma derivada:** o hash de versão usado na concorrência (§10) troca o valor sensível por um marcador fixo (ver a consequência no §10);
  * **trocar `sensivel` de `S` para `N`** é recusado enquanto houver valor sensível gravado: o `valor_padrao` do parâmetro ou qualquer `valor_padrao_sub` dos vínculos. A mensagem pede para remover esses valores antes, para que um segredo não passe a ser exibido em claro. Trocar de `N` para `S` é sempre permitido.
* **Textos livres** (`label` e `descricao`) seguem a regra global de texto dos cadastros (§10): sem caracteres de controle e sem truncamento silencioso.
* **Regras de dependência**, verificadas antes (a mensagem lista os scripts) e garantidas na **mesma operação** do repositório (`RepoViolacao` com constraint de aplicação):
  * trocar `tipo_componente` com qualquer vínculo: `sss_prm_tipo_vinculado`;
  * alterar ou remover `param_nomeado` com vínculo a script `NOMEADO`, ativo ou não: `sss_prm_flag_nomeado`;
  * desativar com vínculo a script **ativo**: `sss_prm_vinculo_ativo`.
* **"Usado por N scripts"** conta todos os vínculos e vem de `parametros_listar` (`qtd_scripts`, uma subconsulta `COUNT` no Oracle).
* **Risco aceito:** alterar `opcoes_json` ou a regex de um parâmetro vinculado pode invalidar um `valor_padrao_sub` já gravado. Isso é detectado na compilação do ticket (§6.1); a revalidação dos vínculos ao salvar fica com o cadastro de scripts (F4.5).

### 6.3 Estratégias de montagem (`tipo_param`)

* **`NOMEADO`**: todo parâmetro vinculado exige `param_nomeado`, validado no vínculo. Por parâmetro, em ordem de `ordem`:
  * `CHECKBOX` verdadeiro emite apenas `flag`. Falso é omitido.
  * Opcional sem valor é omitido.
  * Flag longa (`--x`) emite dois tokens, `--x` e `valor`. Se o valor começar com `-`, emite um token único `--x=valor`.
  * Flag curta (`-x`) emite dois tokens, `-x` e `valor`. Valor iniciado em `-` é **rejeitado** na validação, porque não há forma segura universal.
* **`SEQUENCIAL`**: argumentos posicionais ordenados por `ordem`, ignorando `param_nomeado`.
  * Opcional sem valor emite `""`, preservando a posição. Isso vale para todos os tipos, inclusive `CHECKBOX` opcional sem resposta (emite `""`, não `"0"`).
  * `CHECKBOX` com resposta emite `"1"` ou `"0"`.
  * Valor iniciado em `-` é **rejeitado**, exceto `NUMBER` negativo.
* **`NENHUM`**: nenhum argumento. Vincular parâmetros a esse script é rejeitado no cadastro.

### 6.4 Montagem do `argv`

O catálogo guarda um **interpretador lógico** (CR-001, D1). O nó web compila apenas os **argumentos** (`args`). O **agente** monta o `argv` real no claim, com o executável e o diretório base **dele**:

```text
PYTHON3    -> [<exe PYTHON3>, "-I", <script_real>, ...args]
BASH       -> [<exe BASH>, <script_real>, ...args]                 (só POSIX)
SH         -> [<exe SH>, <script_real>, ...args]                   (só POSIX)
POWERSHELL -> [<exe POWERSHELL>, "-NoProfile", "-NonInteractive",
               "-ExecutionPolicy", "Bypass", "-File", <script_real>, ...args]   (só Windows)
```

* `<exe X>` vem de `[agent] interpretadores` do agente (§12.1).
* `<script_real>` é resolvido pelo agente a partir de `pasta_base` e `path_file`. O nome lógico da pasta é traduzido para o diretório local pelo mapeamento `[agent] base_script_dirs` do agente (§8.5).
* A UI mostra o `argv` **lógico**, com o nome da pasta base no lugar do diretório, por exemplo `PYTHON3 -I <ROTINAS>/carga.py --data 2026-10-13`.

### 6.5 Snapshot imutável (`tbsss_tickets.parametros_enviados`)

JSON serializado com `json.dumps(obj, ensure_ascii=False, sort_keys=True)`:

```json
{
  "versao": 3,
  "script_id": 12,
  "script_nome": "carga_faturas",
  "interpretador": "PYTHON3",
  "pasta_base": "ROTINAS",
  "path_file": "faturamento/carga_faturas.py",
  "tipo_param": "NOMEADO",
  "args": ["--data", "2026-10-13"],
  "respostas": {"data_ref": "2026-10-13"},
  "sensiveis": [],
  "compilado_em": "2026-10-13 10:47:00"
}
```

* **Tipos em `respostas`:** os valores são os resolvidos e normalizados (§6.2). Opcional sem valor fica `null`, `CHECKBOX` é booleano JSON (`true`/`false`) e os demais tipos são string. Os valores sensíveis ficam no snapshot (o banco é o único lugar onde ficam visíveis, §6.5 "Parâmetros sensíveis").
* **`sensiveis`:** lista os códigos de **todos** os parâmetros sensíveis vinculados, mesmo os que ficaram sem valor.
* **Versão 2 (CR-001):** o snapshot não guarda mais caminho absoluto nem executável do nó que o compilou. O agente revalida `interpretador` contra a allowlist e o próprio mapeamento, resolve `path_file` pelo `path_guard` local e monta o `argv` (§6.4, §8.4).
* **Versão 3 (CR-003, várias pastas base):** acrescenta `pasta_base`, o nome lógico da pasta onde o script fica. O agente a traduz pelo próprio mapeamento `base_script_dirs` (§8.5).
* Snapshots das versões 1 e 2 foram gerados apenas em DEV/FAKE e não são aceitos pelo agente. O claim os rejeita com `PRECHECK_FAILED`.

* O snapshot é **compilado na criação do ticket** (manual ou desdobro). O agente **nunca** recompila nem lê `tbsss_script_param` e `tbsss_parametros` para executar.
* **Defesa em profundidade no claim:** o agente revalida o snapshot (§8.4, passo 1).
* **Vínculo de parâmetros pela UI** (`admin_scripts/parametros`, F4.5):
  * a lista inteira vai num único POST, e a ordem é renumerada pelo servidor (1..n, pela posição);
  * a lista é revalidada inteira: ID inexistente ou duplicado, `valor_padrao_sub` por `validar_valor` (com até 100 caracteres), `NENHUM` sem vínculos e `NOMEADO` com flag em todos os parâmetros;
  * as regras de `NENHUM`/`NOMEADO` também são garantidas pelo repositório na mesma operação (`sss_scr_nenhum_vinculado` e `sss_scr_nomeado_sem_flag`), inclusive ao trocar `tipo_param`;
  * só parâmetros ativos podem ser adicionados; vínculos existentes a parâmetros inativos aparecem com o selo "inativo" e podem ser removidos, mas nunca readicionados enquanto o parâmetro estiver inativo (D9);
  * o `valor_padrao_sub` de parâmetro sensível é só de escrita (em branco mantém o gravado) e aparece como `****` na auditoria e na prévia. Há uma opção explícita "remover valor" por vínculo, que apaga o valor gravado sem remover o vínculo;
  * o valor sensível **mantido** também é revalidado por `validar_valor` contra a configuração atual do parâmetro. Se tiver ficado inválido, a gravação é recusada com a orientação de informar um novo valor ou removê-lo;
  * o hash de versão dos vínculos troca o valor sensível por um marcador fixo (§6.2), para que o segredo não saia no HTML nem de forma derivada;
  * a **prévia do argv** usa a configuração em edição, com os valores padrão (§6.1), e não grava nada;
  * concorrência pelo estado lido (hash dos vínculos), com a mensagem de conflito;
  * **limites operacionais:** até 200 vínculos por script, e a tela trabalha com até 1.000 parâmetros cadastrados (o mesmo vale para os 1.000 ambientes da homologação). Os limites devem ser revistos antes de serem atingidos;
  * script inativo pode ter os vínculos editados, para o caso de ser reativado.
* `tbsss_ticket_resp` é a cópia normalizada das respostas resolvidas, usada em relatórios, auditoria e reexecução. O executor não a utiliza.
* **Parâmetros sensíveis** (`sensivel = 'S'`):
  * Os valores são listados em `"sensiveis"` (por `codigo`).
  * Ficam mascarados na UI, nos logs do daemon e no `log_output`.
  * No `argv` exibido, todo token igual a um valor sensível do ticket vira `****`, mesmo que apareça em outro parâmetro. Na dúvida, o sistema prefere mascarar a mais.
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
  * Em `UNICA`, `data_fim` **não se aplica**: o servidor ignora o valor enviado e grava `NULL`, e a tela esconde e limpa o campo.
* Se a próxima ocorrência passar de `data_fim`, a regra recebe `ativo = 'N'` e `pausa_motivo = 'CONCLUIDO'`.
* `proxima_execucao` é calculada no salvamento da regra pelo mesmo módulo `recurrence.py`.

**Semântica de piso, teto e precisão (decisões do F5.1):**

* **Precisão de minuto:** toda ocorrência tem segundos e microssegundos zerados. `data_inicio` também é considerado truncado ao minuto.
* **Piso inclusivo:** a primeira ocorrência é a primeira **maior ou igual** a `data_inicio` (e maior que o instante de referência). Exemplo:
  * `DIARIA` às 03:00 com `data_inicio = 15/10 10:00` começa em 16/10 às 03:00;
  * com `data_inicio = 15/10 03:00`, começa no próprio 15/10 às 03:00.
* **Teto inclusivo:** uma ocorrência exatamente em `data_fim` ainda vale. `data_fim` é data **e hora**.
* **`UNICA`:** ocorre em `data_inicio` e só é devolvida se for estritamente maior que a referência.
* **`MENSAL`:** o dia inexistente cai no último dia do mês sem deriva. Exemplo para o dia 31: 31/01 → 28/02 → 31/03 → 30/04.

### 7.3 Parser CRON (implementação própria, sem bibliotecas)

* Cinco campos: `minuto hora dia_mes mes dia_semana`.
* Sintaxe suportada: `*`, número, lista `a,b`, intervalo `a-b` e passo `*/n` ou `a-b/n`. **Não** há suporte a nomes (`MON`, `JAN`), `L`, `W`, `#` nem `?`.
* `dia_semana` aceita 0–7, onde 0 e 7 são domingo.
* Se `dia_mes` **e** `dia_semana` forem ambos restritos, vale a semântica **OU** (padrão Vixie cron).
  * Um campo cujo texto começa com `*` (inclusive `*/n`) **não** é restrito. Nesse caso, os dois campos precisam casar (E), como no Vixie. Exemplo: `0 0 */2 * 1` = dias ímpares que caiam numa segunda.
* O cálculo da próxima ocorrência é feito campo a campo, não minuto a minuto, com horizonte de `cron_horizon_days`. Uma expressão sem ocorrência no horizonte é rejeitada no cadastro e pausa a regra (`CRON_INVALIDO`) no desdobro.
  * O horizonte é contado a partir do instante de referência da busca: `data_inicio` no cadastro e na prévia, e o "agora" do banco no desdobro.
  * **Exceção:** se `data_fim` cair dentro do horizonte, a falta de ocorrência significa que a regra terminou (`CONCLUIDO`), não que a expressão é inválida.
* O passo exige `*` ou intervalo (`*/5`, `0-30/5`). A forma `a/n` é rejeitada, e a expressão tem no máximo 60 caracteres.
* `CronExpr.descrever()` gera a descrição em português exibida na UI. Exemplos:
  * `30 2 * * 1-5` → "às 02:30, de segunda a sexta";
  * `*/15 * * * *` → "a cada 15 minutos";
  * `0 0 1 * 1` → "às 00:00, no dia 1 de cada mês ou às segundas";
  * passo no dia do mês: `0 0 */2 * *` → "às 00:00, a cada 2 dias a partir do dia 1"; `0 0 */2 * 1` → "às 00:00, a cada 2 dias a partir do dia 1, quando cair numa segunda". A descrição não repete "de cada mês" e não usa "nos dias do mês a cada".

### 7.4 Política de *misfire*

Se `SYSDATE - proxima_execucao > misfire_tolerance_s` (por exemplo, após um downtime):

| `misfire_policy` | Comportamento |
|---|---|
| `RUN_ONCE` (padrão) | Gera **um** ticket, coalescendo as ocorrências perdidas |
| `SKIP` | Não gera ticket |

Nos dois casos, `proxima_execucao` recebe a **primeira ocorrência futura** maior que `SYSDATE`. O número de ocorrências perdidas vai para o log:

* em **WARN** quando o atraso passa de `misfire_tolerance_s` (misfire de verdade);
* em **INFO** quando há ocorrências coalescidas **dentro** da tolerância (por exemplo, CRON a cada minuto com o daemon 4 minutos atrasado gera 1 ticket e 4 perdidas em INFO).

**Contrato de `recurrence.avaliar_disparo(regra, agora, misfire_policy, misfire_tolerance_s)`** (decisões do F5.1). A função devolve `Decisao(gerar_ticket, nova_data, perdidas, concluir)`:

* **Vencidas** são as ocorrências em `[proxima_execucao, agora]`, contando a própria `proxima_execucao`.
* **Atraso dentro da tolerância** (`agora − proxima_execucao ≤ misfire_tolerance_s`): gera **um** ticket, mesmo que várias ocorrências tenham vencido. Exemplo: CRON a cada minuto com o daemon 4 minutos atrasado.
* **`perdidas`:**
  * `vencidas − 1` quando há ticket (o ticket cobre a ocorrência mais recente);
  * todas as vencidas com `SKIP` fora da tolerância;
  * limitada a 10.000.
  * Exemplo: `DIARIA` com 3 dias de downtime e `RUN_ONCE` gera 1 ticket e 3 perdidas.
* **`nova_data`:** sempre a primeira ocorrência maior que `agora`, respeitando piso e teto. É `None` quando a regra terminou.
* **`concluir`:**
  * `UNICA` depois da decisão. No passado, `RUN_ONCE` dispara uma vez e conclui; `SKIP` fora da tolerância conclui sem ticket.
  * Ou quando não há próxima ocorrência até `data_fim`. Nesse caso, o ticket da ocorrência atual ainda é gerado.
* **Expressão CRON inválida ou sem ocorrência no horizonte:** lança `CronErro`, e o daemon pausa com `CRON_INVALIDO`.
* Os módulos `cron_parser.py` e `recurrence.py` são puros: não importam `gluon`, nunca chamam `datetime.now()` e recebem o "agora" por parâmetro.

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

**Conclusão da regra (`concluir = True`, `nova_data = None`):**

`proxima_execucao` é `NOT NULL`, então a conclusão **não** grava `NULL`. Ela substitui os passos 6 e 7 por um **único** `UPDATE` otimista, que mantém `proxima_execucao` com o valor lido:

```sql
UPDATE {owner}.tbsss_agendamentos
   SET ativo = 'N', pausa_motivo = 'CONCLUIDO',
       ultima_execucao  = SYSDATE,
       ultimo_ticket_id = :ticket_id
 WHERE id = :id
   AND ativo = 'S'
   AND proxima_execucao = :antiga_data
```

* **Com ticket** (a ocorrência atual ainda gera ticket): `:ticket_id` vem do `NEXTVAL` do passo 6. Se `rowcount = 1`, seguem o `INSERT` do ticket e o do `ticket_resp`, como no passo 6. Se `rowcount = 0`, `ROLLBACK` e próxima regra.
* **Sem ticket** (`SKIP` fora da tolerância em `UNICA`, ou sobreposição): `ultima_execucao` e `ultimo_ticket_id` **não** são alterados. O `SET` fica só com `ativo` e `pausa_motivo`.
* A conclusão é auditada como `AGD_PAUSAR`, com o detalhe `pausa_motivo: CONCLUIDO`, e registrada em INFO (não em WARN, porque não é uma falha).
* O passo 7 (pausa) não se aplica à conclusão.

**Sobreposição numa regra que conclui:** se, no passo 4, o `ultimo_ticket_id` ainda estiver `PENDING`/`RUNNING` e a decisão for `concluir = True`, a regra é concluída **sem ticket** (UPDATE acima, variante sem ticket). A ocorrência atual entra em `perdidas`, e o log registra INFO `SKIP_OVERLAP` com o total de perdidas.

**Bind de datas:**

* `:antiga_data` e `:nova_data` são declarados pelo `db_conn` com o tipo de data do driver (no Oracle, `setinputsizes` com `cx_Oracle.DATETIME` ou `oracledb.DB_TYPE_DATE`).
* Um `datetime` com microssegundos **nunca** é comparado a uma coluna `DATE`. A regra travaria silenciosamente.
* `:antiga_data` é usada **exatamente como retornada pelo banco** (passo 1), nunca recalculada nem convertida por fuso. `:nova_data` sai do `recurrence.py` já sem segundos nem microssegundos (§7.2).
* **Teste obrigatório (F7.3/F8.4):** um desdobro com `antiga_data`/`nova_data` contendo microssegundos não pode resultar em `rowcount = 0`. O tipo `DATE` declarado no bind descarta a fração.

**Contrato do repositório para o desdobro (F8.4):** `repo_oracle/scheduler_agenda.py` (processo batch, sem FAKE, §2.5) expõe operações distintas:
* a leitura do lote vencido (SQL acima);
* a leitura completa da regra;
* a reserva otimista com a inclusão do ticket e do `ticket_resp` (passo 6), numa única operação;
* a conclusão, com e sem ticket;
* a pausa (passo 7).

Todas recebem a conexão da transação do ciclo e nunca fazem `COMMIT` sozinhas; o `COMMIT` único é do passo 8.

### 7.6 Cadastro de regras na UI (decisões do F5.2)

Implementação: `controllers/agendamentos.py`, `modules/agendamentos_service.py` e `views/agendamentos/`. O questionário de parâmetros é o mesmo do disparo (`views/components/questionario.html`).

* **Validação estrita (sem truncamento):** todo campo recebido é validado no tamanho e no formato exatos. Um valor mais longo ou fora do formato é **recusado** com mensagem no campo, nunca cortado. Exemplos: dia do mês `100` ou `311`, hora `03:000`, data com segundos ou frações (`…T10:00:00.999`).
* **Escolha de script e ambiente:** na inclusão, a escolha é feita em etapas e usa os mesmos filtros do disparo (§4.3.A): só aparecem scripts e ambientes em que o editor tem `pode_executar`. Por isso, quem não é admin precisa também de `EXEC_SCRIPT`.
* **Edição (D2):** script e ambiente ficam **fixos**. Para usar outro script ou ambiente, cria-se uma nova regra.
* **`usuario_id`:** a inclusão e a edição gravam o editor, que precisa ter `pode_executar` vigente (§10). Sem essa permissão, a operação é negada e a regra fica intacta. A tela de edição sempre avisa: "Ao salvar, esta regra passará a executar com as suas permissões."
* **Datas:**
  * O servidor valida as datas e as converte para `datetime` sem microssegundos.
  * `data_inicio` é obrigatória em `UNICA`. Nos demais tipos, vazio significa "agora" (relógio do banco, truncado ao minuto) (D3).
  * Um `data_inicio` no passado é aceito, desde que exista próxima execução.
  * Uma regra sem próxima execução (por exemplo, `UNICA` no passado ou `data_fim` vencida) é rejeitada.
* **Campos por tipo:** só os campos do tipo escolhido são gravados; os demais ficam nulos, como exige `ck_tbsss_agd_campos`. Na `SEMANAL`, as caixas seg–dom viram `dias_semana` em ISO ordenado (ex.: `1,3,5`).
* **Nome da regra (D7):** obrigatório, até 60 caracteres e **sem unicidade**.
* **`parametros_json`:**
  * Guarda as respostas **resolvidas** (já com a precedência do §6.1 aplicada) e validadas, como objeto `{codigo: valor}` com `sort_keys`.
  * Valores nulos são omitidos, e `CHECKBOX` é gravado como `"true"`/`"false"`.
  * No salvamento, o snapshot completo é compilado só para validar; o daemon recompila a cada desdobro.
* **Parâmetros sensíveis na edição:** o valor salvo nunca é reexibido, nem de forma derivada: a versão do formulário troca as respostas sensíveis do `parametros_json` pelo marcador do §10. Um campo vazio mantém o valor anterior, e a tela indica isso. Na auditoria, o valor aparece como `******`, com `(alterado)` quando muda.
* **Prioridade:** igual ao disparo (§5.3), com padrão 2. Na edição, quem não é admin não consegue manter a prioridade 1.
* **Concorrência:** a edição usa o padrão de versão e `esperado` dos cadastros (§10). O `esperado` inclui `proxima_execucao`, então um desdobro feito entre a leitura e a gravação gera conflito.
* **Efeito da edição na agenda:**
  * salvar recalcula `proxima_execucao` a partir de agora. Uma ocorrência já vencida e ainda não desdobrada (daemon atrasado) é descartada, sem ticket;
  * editar uma regra pausada ou `CONCLUIDO` **não** a reativa: ela continua pausada até a retomada explícita.
* **Auditoria:**
  * A inclusão grava `CAD_INSERIR`.
  * A edição grava `CAD_ALTERAR` e **sempre** começa por `usuario_id: <anterior> (login) → <novo> (login)`, mesmo quando o editor não muda. Sem nenhuma mudança e com o mesmo editor, nada é gravado.
* **Pausa manual:** grava `ativo = 'N'` e `pausa_motivo = 'MANUAL'`, de forma otimista sobre `proxima_execucao` (§7.5 passo 7), e audita `AGD_PAUSAR` com o login e o IP de quem pausou.
* **Retomada:**
  * Revalida `pode_executar` de **quem retoma**, recalcula `proxima_execucao` a partir de agora, limpa `pausa_motivo` e grava `ativo = 'S'`. Audita `CAD_ALTERAR`.
  * O responsável (`usuario_id`) não muda: os privilégios dele continuam sendo revalidados a cada desdobro (§7.5 passo 2).
  * Uma regra `CONCLUIDO` só é retomada se ainda houver próxima execução (D5). Pausar uma regra já pausada, ou retomar uma ativa, gera aviso sem gravar nem auditar.
* **Lista:**
  * Mostra as regras dos ambientes autorizados ao perfil (admin: todas). Uma regra fora do escopo é tratada como inexistente (404).
  * A situação aparece como "Ativo" ou "Pausado" mais o motivo (D4): Pausado manualmente, Concluída, Responsável inativo, Responsável sem permissão, Script inativo, Ambiente inativo, Parâmetros inválidos ou Expressão CRON inválida.
* **Prévia:** um POST com CSRF devolve as próximas 5 execuções e a descrição em português, chamado com *debounce* de 500 ms. A ajuda da sintaxe CRON fica num bloco recolhível do próprio formulário (D6).

---

### 7.7 Agenda: o que vai rodar (`agendamentos/agenda`, CR-004)

Responde "o que vai rodar hoje e nos próximos dias?". Exige `CAD_AGENDAMENTOS` e mostra só as regras dos ambientes autorizados ao perfil (admin: todas), como a lista do §7.6.

* **Período:** de agora até o fim do 7º dia seguinte, pelo relógio do banco (§7.1).
* **Regras incluídas:** só as ativas. A tela avisa: "Regras pausadas não aparecem aqui."
* **Ocorrências:** são calculadas pelo `recurrence.py`, a partir de `proxima_execucao` (inclusive), respeitando `data_fim`. Há dois limites:
  * no máximo **20 por regra** no período; acima disso aparece "e mais {n} vezes neste período" (por exemplo, CRON a cada minuto);
  * no máximo **500 no total**, com aviso quando passar.
* **Apresentação:** agrupada por dia ("Hoje", "Amanhã", "sexta-feira, 18/10"), em ordem de horário. Cada linha mostra:
  * a hora;
  * o nome da regra;
  * o script;
  * o ambiente;
  * a frase da recorrência (`descrever()` ou o tipo em português);
  * o link para a regra.
* `proxima_execucao` no passado (daemon atrasado) aparece em "Atrasado", no topo, com a frase "deveria ter rodado às {hora}; vai rodar assim que o servidor puder".
* A tela traz a nota "É uma previsão: a execução real depende de um servidor livre."
* Usa as leituras existentes de `RepoAgendamentos` (listagem com filtro de ativos). Não grava nada e não audita.
* A lista de agendamentos ganha o botão "Ver agenda".

## 8. Motor de Execução (ciclo 2 do daemon)

### 8.0 Camada de plataforma (`modules/plataforma/`, CR-001)

O daemon chama apenas a interface abaixo. As implementações ficam em `posix.py` (Linux e Unix) e `windows.py` (APIs nativas via `ctypes`). O restante do motor não conhece o sistema operacional.

| Operação | POSIX | Windows |
|---|---|---|
| `iniciar_processo` (§8.4) | `Popen(..., start_new_session=True, preexec_fn=_child_limits)`, com `umask(0o077)` e `setrlimit` | `Popen(..., creationflags=CREATE_NEW_PROCESS_GROUP \| CREATE_NO_WINDOW)` e atribuição imediata a um **Job Object** com `KILL_ON_JOB_CLOSE` e limites de memória e de processos |
| `encerrar_grupo` (escalonado) | `killpg(SIGTERM)` → `kill_grace_s` → `killpg(SIGKILL)` → `wait()` | `CTRL_BREAK_EVENT` → `kill_grace_s` → `TerminateJobObject` → `wait()`. O Job também encerra netos e processos desacoplados |
| `identidade_processo(pid)` (contra PID reciclado) | Linux: `starttime` de `/proc/<pid>/stat` (campo 22, após o último `)`). Outros Unix: `/proc/<pid>/psinfo` ou `sysctl KERN_PROC` | `GetProcessTimes().CreationTime` |
| `processo_existe(pid)` | `os.kill(pid, 0)` | `OpenProcess` + `GetExitCodeProcess` |
| `travar_instancia(caminho)` | `fcntl.flock(LOCK_EX \| LOCK_NB)` | `msvcrt.locking(LK_NBLCK)` |
| `usuario_privilegiado()` | `os.geteuid() == 0` | Token elevado (Administradores) ou SYSTEM |
| `validar_arquivo_restrito(caminho)` (segredos, §4.1) | Dono = euid e `mode & 0o077 == 0` | Dono = SID do processo e DACL só com o dono e SYSTEM |
| `validar_arvore_scripts` (§8.5) | UID em `script_owner_uids`, sem escrita de grupo ou outros nem do agente | SID em `script_owner_sids`, sem direito de escrita efetivo para o agente nem para grupos amplos |
| `criar_dir_trabalho` (§8.4) | `0700` | ACL só para a conta do agente |
| Parada | SIGTERM/SIGINT acionam a flag | SIGBREAK/SIGINT acionam a flag |

Em todas as plataformas, o arquivo `work_dir/sss-<agent_id>.stop` também aciona a flag.

### 8.1 Laço principal

```text
inicialização (§8.12) -> loop:
  a cada cancel_poll_interval_s : varredura própria (§8.7) + cancelamentos + timeouts + processos finalizados
  a cada heartbeat_interval_s   : heartbeat (§8.7) + log pump (§8.10) + self-fencing (§8.9)
  a cada orchestrator_interval_s: NODE_OFFLINE (§8.8) + desdobro (§7.5) + claim (§8.2-8.4)
  sinal SIGTERM/SIGINT (POSIX), SIGBREAK/SIGINT (Windows) ou arquivo .stop : graceful shutdown (§8.11)
```

### 8.2 Seleção de candidatos

O agente só tenta o claim se `execucoes_locais < max_parallel_jobs`, com `max_parallel_jobs <= max_parallel_hard_limit`. Os placeholders `:amb0..:ambN` são **gerados pelo código** a partir de `ambientes_atendidos`; os valores sempre são binds.

```sql
SELECT id, script_id, ambiente FROM (
  SELECT t.id, t.script_id, t.ambiente
    FROM {owner}.tbsss_tickets t
    JOIN {owner}.tbsss_scripts s ON s.id = t.script_id
   WHERE (CASE WHEN t.status = 'PENDING' THEN t.prioridade END) IS NOT NULL
     AND (CASE WHEN t.status = 'PENDING' THEN t.scheduled_at END) <= SYSDATE
     AND t.ambiente IN (:amb0, :amb1)
     AND s.interpretador IN (:int0, :int1)
     AND s.pasta_base IN (:pb0, :pb1)
     AND t.cancel_requested = 'N'
   ORDER BY (CASE WHEN t.status = 'PENDING' THEN t.prioridade END),
            (CASE WHEN t.status = 'PENDING' THEN t.scheduled_at END),
            t.id
) WHERE ROWNUM <= :lote
```

As expressões `CASE` devem ser **textualmente idênticas** às do índice baseado em função `ix_tbsss_tck_fila`, que contém apenas os tickets `PENDING`.

O filtro `s.interpretador IN (:int0..:intN)` usa os interpretadores que **este** agente suporta (§12.1). Assim, num ambiente com agentes Linux e Windows, cada um só pega os scripts que consegue executar. Os placeholders são gerados pelo código, e os valores vão sempre como binds.

Do mesmo modo, o filtro `s.pasta_base IN (:pb0..:pbN)` usa os nomes lógicos de `[agent] base_script_dirs` **deste** agente. Assim, um agente nunca pega um script de uma pasta que ele não tem.

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
   * `versao == 3`, e `interpretador` consta na allowlist lógica **e** no mapeamento deste agente;
   * `pasta_base` consta no mapeamento `base_script_dirs` deste agente;
   * `path_file` passa na §8.5 contra o diretório local dessa pasta base, que fornece o `script_real`;
   * o `argv` é montado pelo agente (§6.4) a partir de `interpretador`, `script_real` e `args`;
   * o script segue `ativo = 'S'` e homologado para o ambiente.
2. **Preparo do diretório de trabalho:**
   * `work_dir/ticket_<id>/`, criado pela camada de plataforma (`0700` no POSIX; ACL só da conta do agente no Windows), que é o `cwd` do processo;
   * `work_dir/ticket_<id>/tmp/` como `TMPDIR`.
3. **Arquivo de log:** `log_dir/tickets/<AAAAMM>/ticket_<id>.log`, aberto com `os.open(path, O_WRONLY | O_CREAT | O_EXCL | O_APPEND, 0o600)`. No Windows, o modo não tem efeito e a proteção vem da ACL de `log_dir`, validada na inicialização (§8.12).
4. **Spawn** (forma POSIX; no Windows, `plataforma.iniciar_processo` conforme a §8.0):
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
5. **Instante de início:** ler `plataforma.identidade_processo(pid)` (`starttime` no Linux, `CreationTime` no Windows; §8.0) e gravar:
   ```sql
   UPDATE {owner}.tbsss_tickets
      SET process_id = :pid, process_start = :process_start
    WHERE id = :ticket_id AND agente_id = :agente_id AND status = 'RUNNING'
   ```
   Se `rowcount = 0`, a posse foi perdida (por exemplo, `NODE_OFFLINE` durante o spawn): `plataforma.encerrar_grupo` e ERROR `OWNERSHIP_LOST`.

### 8.5 Validação de interpretador e caminho (`path_guard.py`)

**Interpretadores lógicos (CR-001):**

| Lógico | POSIX | Windows |
|---|---|---|
| `PYTHON3` | sim | sim |
| `BASH` | sim | não |
| `SH` | sim | não |
| `POWERSHELL` | não | sim |

* `cmd.exe`, `.bat` e `.cmd` são **proibidos**, porque reinterpretam argumentos e não há *quoting* seguro.
* O executável de cada interpretador vem de `[agent] interpretadores`. Na inicialização, o agente valida que o caminho é absoluto, existe e é executável, e que a pasta dele não é gravável pelo agente.

**Pastas base (CR-003): os scripts podem ficar em qualquer pasta cadastrada, desde que o arquivo exista**

* Cada nó tem uma lista de pastas permitidas em `[agent] base_script_dirs`, no formato `NOME=caminho,NOME=caminho` (ex.: `ROTINAS=/opt/automacoes/scripts,BATCH=/home/batch/scripts,DADOS=/dados/rotinas`).
  * O `NOME` é lógico, segue `^[A-Z][A-Z0-9_]{0,29}$` e é o mesmo em todos os nós que atendem o script. O caminho é o diretório **local** de cada nó, e um agente Windows mapeia o mesmo nome para o próprio diretório (ex.: `ROTINAS=D:\automacoes\scripts`).
  * Os nomes são únicos na lista. Os caminhos são absolutos, distintos e **não aninhados**: nenhuma pasta base fica dentro de outra.
* O cadastro do script grava `pasta_base` (o nome lógico) e `path_file` (o caminho relativo a essa pasta). O script pode ficar em qualquer subpasta de qualquer pasta base, e o arquivo precisa existir:
  * no agente, sempre (claim, §8.4);
  * no nó web, conforme a etapa 2 abaixo.
* Toda pasta base passa pelas mesmas checagens de dono e permissão da antiga `base_script_dir`, na inicialização e a cada resolução.
* Nenhuma pasta base pode conter `log_dir` ou `work_dir`, nem ficar dentro deles.
* A tela de agentes (§13) mostra os nomes das pastas base de cada agente, gravados em `tbsss_agentes.pastas_base`.

**Caminho (forma POSIX):**

```python
ALLOWLIST = ('PYTHON3', 'BASH', 'SH', 'POWERSHELL')

base_script_dir = base_script_dirs[pasta_base]   # KeyError -> PASTA_NAO_MAPEADA
base = os.path.realpath(base_script_dir)
real = os.path.realpath(os.path.join(base, path_file))
try:
    dentro = os.path.commonpath([base, real]) == base
except ValueError:
    dentro = False
ok = (interpretador in ALLOWLIST and dentro and real != base and os.path.isfile(real))
```

**Caminho no Windows:**
* o caminho final é obtido por `GetFinalPathNameByHandleW`, em **qualquer** versão do Python, porque o `realpath` do Python < 3.8 não resolve links nem junctions. *Reparse points* intermediários não resolvidos são rejeitados;
* `commonpath` é aplicado sobre `os.path.normcase`;
* um drive diferente do da base resulta em `FORA_DA_BASE`.

Validações complementares:

* **Pasta não mapeada:** `pasta_base` ausente do mapeamento do nó resulta em `PASTA_NAO_MAPEADA`. No agente, isso vira `PRECHECK_FAILED`; no nó web, ver a etapa 2.
* **Ownership e permissão:** o script, **cada diretório** entre `base` (a pasta base do script) e o script, e o próprio `base` são verificados:
  * **POSIX:** pertencem a um UID de `script_owner_uids` (padrão: `0`, root); não têm escrita para grupo nem para outros (`st_mode & 0o022 == 0`); e o UID do agente não tem permissão de escrita (`os.access(p, os.W_OK)` falso).
  * **Windows:** pertencem a um SID de `script_owner_sids` (ex.: `S-1-5-32-544`, Administradores); a conta do agente, Users, Authenticated Users e Everyone não têm direito de escrita **efetivo** (`GetEffectiveRightsFromAclW`). `os.access` não serve no Windows, porque só olha o atributo "somente leitura".
* **Momento:** a validação ocorre no cadastro (UI), na criação do ticket (snapshot) e novamente no claim (§8.4).
* **CKs de banco** (defesa adicional):
  * `ck_tbsss_scr_int` restringe `interpretador` à allowlist lógica;
  * `ck_tbsss_scr_path` exige `path_file` relativo e sem `..`;
  * `ck_tbsss_scr_pasta` exige `pasta_base` no formato do nome lógico.
* **TOCTOU residual:** é aceito porque o UID do agente não consegue alterar nenhuma das pastas base.
* **Formato de `path_file`:** caminho relativo, com `/` como único separador. É recusado se começar com `/`, contiver `..`, `\` ou `:` (letra de drive), ou começar com `//`. O agente Windows converte `/` para o separador local ao resolver (§8.5, "Caminho no Windows").
* **Validação no nó web (decisão de plataforma):** o nó web valida contra a **própria** árvore e plataforma.
  * A etapa 1 (`validar_cadastro`: interpretador na allowlist, formato de `path_file`, formato de `pasta_base`) roda sempre.
  * A etapa 2 (`resolver` contra o diretório local da pasta base) só roda se a plataforma do nó web suportar o interpretador (tabela acima) **e** se a pasta base estiver mapeada no nó web. Sem isso, a tela mostra um aviso e a validação fica com o agente:
    * interpretador de outra plataforma (ex.: `POWERSHELL` num nó web Linux): "Caminho não verificado neste servidor: a validação ocorrerá no agente Windows";
    * pasta não mapeada no nó web: "Pasta base não disponível neste servidor: a validação ocorrerá no agente".
  * A lista de pastas oferecida no cadastro é a do nó web. Uma pasta que só existe nos agentes deve constar no `base_script_dirs` do nó web **sem caminho** (`NOME=`). Assim ela pode ser escolhida, e a etapa 2 fica com o aviso de "pasta não disponível neste servidor". `NOME=` só é aceito no nó web: o daemon recusa a subida se uma pasta base não tiver caminho.
  * Em qualquer caso, a validação definitiva é a do agente, no claim (§8.4).
* **Cadastro na UI** (`admin_scripts`, F4.5):
  * a etapa 1 (`validar_cadastro`) e a etapa 2 (`resolver` contra o servidor local) rodam ao salvar, com os códigos traduzidos para português. A etapa 2 segue a regra de plataforma acima;
  * na **edição**, a etapa 2 só roda quando `pasta_base`, `path_file` ou `interpretador` mudam, ou quando o script é reativado. Assim, um arquivo ausente no nó web não impede editar a descrição ou desativar o script;
  * `pasta_base` é um select com os nomes de `base_script_dirs` do nó web, e o servidor exige um nome dessa lista. Ao editar um script cuja pasta não está mais mapeada, o valor gravado é mantido e aparece com o selo "não mapeada neste servidor";
  * em `sss_env = DEV`, apenas `NAO_E_ARQUIVO` (o arquivo não existe localmente) vira **aviso** e permite salvar; os demais códigos bloqueiam;
  * em HML/PROD, a etapa 2 sempre bloqueia;
  * a UI sempre informa que a validação definitiva ocorre também no agente;
  * `interpretador` é um select fixo da allowlist lógica, e o servidor exige o valor exato, mesmo que o HTML tenha sido adulterado;
  * **caminho absoluto do servidor só para admin:** o diretório de cada pasta base aparece apenas para perfil admin. Na prévia do argv, quem não é admin vê `<NOME>/path_file` (ex.: `<ROTINAS>/carga.py`);
  * o `nome` do script é texto livre de 1 a 60 caracteres (sem caracteres de controle), único e editável, porque o snapshot guarda o nome da época e tickets e agendamentos referenciam o `script_id`;
  * a unicidade do `nome` **diferencia maiúsculas de minúsculas**, como a UK `uk_tbsss_scr_nome` no Oracle: `Carga` e `carga` são nomes distintos. O FAKE segue a mesma regra;
  * depois de salvar com sucesso, a tela **volta ao formulário do script**, e não à lista, para mostrar os avisos de validação (DEV) e os atalhos de homologação e de vínculo de parâmetros. É uma exceção documentada ao `PADRAO_CRUD_ADMIN.md`.

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
* **Windows:** a base é `SystemRoot`, `PATH=%SystemRoot%\System32;%SystemRoot%`, `TEMP`/`TMP` e `USERPROFILE` = `work_dir\ticket_<id>`, `PATHEXT` e `COMSPEC` com os valores padrão fixos, mais as variáveis `PYTHON*`/`SSS_*` da tabela. `LANG`/`LC_ALL` não se aplicam. A lista de bloqueio inclui também `PSModulePath` e `__PSLockdownPolicy` quando vierem do `env_passthrough`.
* **Risco residual documentado:** a credencial no ambiente é legível pelo mesmo usuário e por administradores (`/proc/<pid>/environ` no Linux; leitura da memória do processo no Windows). Mitigação: o agente roda com uma conta dedicada, sem login interativo nem privilégio administrativo.

### 8.7 Varredura própria, heartbeat, timeout e finalização

Varredura combinada (a cada `cancel_poll_interval_s`, usa `ix_tbsss_tck_run`):

```sql
SELECT id, cancel_requested
  FROM {owner}.tbsss_tickets
 WHERE (CASE WHEN status = 'RUNNING' THEN agente_id END) = :agente_id
```

* Um ticket que está no mapa local mas **ausente** do resultado foi finalizado por outro nó. O agente executa `plataforma.encerrar_grupo`, registra ERROR `OWNERSHIP_LOST` e não grava status.
* **Heartbeat** (a cada `heartbeat_interval_s`):
  * `executemany` de `UPDATE ... SET heartbeat_at = SYSDATE WHERE id = :id AND agente_id = :agente_id AND status = 'RUNNING'`, com `arraydmlrowcounts=True`;
  * linha com contagem 0 é tratada como `OWNERSHIP_LOST`;
  * na mesma transação, atualiza `tbsss_agentes.heartbeat_at`.
* **Timeout:** `timeout = tbsss_scripts.timeout_seg` ou, se nulo, `script_timeout_s`. Ao expirar, `plataforma.encerrar_grupo` (escalonado), com finalização `FAILED`, `TIMEOUT` e `-3`.
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
   AND heartbeat_at < SYSDATE - :node_offline_timeout_s * INTERVAL '1' SECOND
```

O relógio de referência é sempre o `SYSDATE` do banco, nunca o relógio do nó.

### 8.9 Self-fencing (prevenção de split-brain)

* O agente registra o instante do último heartbeat **confirmado** (commit OK).
* Se `agora_monotonico - ultimo_hb_ok > fence_timeout_s`, o agente:
  1. executa `plataforma.encerrar_grupo` em **todos** os grupos que possui;
  2. suspende novos claims;
  3. registra CRITICAL `FENCED`.
* Quando o banco volta, ele tenta `UPDATE ... SET status = 'FAILED', status_motivo = 'FENCED', return_code = -2 ... WHERE id = :id AND agente_id = :agente_id AND status = 'RUNNING'`. Se o ticket já estiver `NODE_OFFLINE`, o `rowcount = 0` é esperado.
* **Invariante validada na inicialização:** `fence_timeout_s * 2 <= node_offline_timeout_s` e `heartbeat_interval_s * 3 <= fence_timeout_s`. Isso garante que o agente se cerca **antes** de outro nó declará-lo offline.
* **Mesmos tempos em todos os nós:** quem declara um agente offline é **outro** agente, com o `node_offline_timeout_s` dele (§8.8). Por isso, `fence_timeout_s` e `node_offline_timeout_s` devem ser **idênticos em todos os agentes**; senão a invariante deixa de valer entre nós. Não há coluna nova para isso:
  * cada agente registra os dois valores em INFO na inicialização;
  * o pacote de implantação (F9.1) usa um único `config.ini` de referência para esses tempos;
  * o roteiro E2E (F9.2) confere que todos os agentes usam os mesmos valores.
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
    * O offset da API web conta **caracteres a partir de 0**. O repositório Oracle converte para a posição 1 do LOB (`offset + 1`).
    * Cada leitura devolve até 65.536 caracteres.
  * O texto é exibido com `x-text`.
  * A latência esperada é de cerca de `heartbeat_interval_s`.
  * A tela mantém no máximo cerca de 5 milhões de caracteres. Ao passar desse limite, descarta o início e mantém os últimos 4 milhões, com um aviso. O log completo fica disponível no **download**, que é feito em streaming.
  * Em erro transitório, o polling continua com intervalo três vezes maior. Sessão expirada interrompe o polling e pede um novo login.
* **Lista de tickets:** ordenada por `created_at DESC`. A tela se atualiza sozinha a cada 10 s, valor fixo no código e fora do `config.ini`. A ordem da fila de execução (§5.3) é aplicada só pelo daemon.
* Arquivos locais com mais de `local_log_retention_days` dias são removidos pelo `purge.py`.

### 8.11 Graceful shutdown do daemon

* SIGTERM/SIGINT (POSIX), SIGBREAK/SIGINT (Windows) e o arquivo `work_dir/sss-<agent_id>.stop` apenas acionam uma flag; o laço trata o restante.
* O daemon para de fazer desdobro e claim.

| `shutdown_mode` | Comportamento |
|---|---|
| `DRAIN` | Aguarda os filhos por até `shutdown_grace_s` e então aplica `TERMINATE` aos restantes |
| `TERMINATE` (padrão) | `plataforma.encerrar_grupo` (escalonado, §8.0). Finaliza com `FAILED`, `SHUTDOWN` e `-6` |

Em seguida, o daemon faz o flush dos logs, grava `tbsss_agentes.status = 'PARADO'`, audita `AGENTE_FIM`, fecha a conexão e o lock file, e sai com código 0.

### 8.12 Inicialização do daemon (fail-fast)

O daemon aborta com código diferente de zero e log CRITICAL ao falhar em qualquer passo:

1. **Usuário:** `plataforma.usuario_privilegiado()` precisa ser falso. É proibido rodar como root (POSIX) ou com token elevado/SYSTEM (Windows).
2. **Configuração:** carregar e validar o `config.ini` (tipos, faixas, invariantes da §8.9 e `max_parallel_jobs <= max_parallel_hard_limit`), o `owner` e o `table_prefix` (regex do `AGENTS.md`), e `agent_id` contra `^[A-Za-z0-9._-]{1,30}$`.
3. **Segredos:** validar o `secrets.cfg` (§4.1).
4. **Diretórios e interpretadores:**
   * cada pasta de `base_script_dirs` tem caminho, existe e passa na regra de ownership e permissão da §8.5; os nomes são únicos e os caminhos não são aninhados;
   * `log_dir` e `work_dir` existem, são graváveis, **não** ficam sob nenhuma pasta base nem contêm uma pasta base (§8.5) e, no Windows, têm ACL restrita à conta do agente;
   * cada entrada de `[agent] interpretadores` é válida para a plataforma (§8.5).
5. **Instância única por host:** `plataforma.travar_instancia` em `work_dir/sss-<agent_id>.lock`.
6. **Banco:** selecionar o driver (§2.3; a sondagem roda aqui), conectar e confirmar o relógio do banco (`SELECT SYSDATE FROM DUAL`).
7. **Registro em `tbsss_agentes`:**
   * Se existir linha do mesmo `codigo` com `status = 'ATIVO'`, `heartbeat_at` recente (menor que `node_offline_timeout_s`) **e** `hostname` diferente, recusar a subida (`agent_id` duplicado).
   * Caso contrário, executar `MERGE` com `status = 'ATIVO'`, `hostname`, `pid_daemon`, `versao`, `ambientes`, `plataforma`, `interpretadores`, `pastas_base` e `iniciado_em`.
   * Auditar `AGENTE_INICIO`.
8. **Ambientes atendidos:** todos existem em `tbsss_ambientes` com `ativo = 'S'`. Um ambiente inexistente é ERROR fatal; um ambiente inativo gera WARN e é ignorado.
9. **Startup check** de tickets `RUNNING` do próprio `agente_id`:
   * `process_id` nulo leva a `FAILED` com `ORPHAN_PROCESS`.
   * PID inexistente (`plataforma.processo_existe`) ou identidade diferente de `process_start` (PID reciclado) também leva a `ORPHAN_PROCESS`.
   * PID vivo com a mesma identidade indica um filho de uma instância anterior do daemon. Como não pode ser adotado, ele é encerrado (`plataforma.encerrar_grupo`; no Windows, pelo Job nomeado `SSS-<agent_id>-<ticket_id>`, reaberto por nome) e finalizado com `ORPHAN_PROCESS`.

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

* `{prefixo}` vem de `table_prefix`, inclui o `_` final e obedece à regex `^[A-Za-z][A-Za-z0-9_]{0,7}$` (começa com letra, para gerar nome Oracle válido; até 8 caracteres).
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
* Toda coluna `id` é `NUMBER(10) NOT NULL` (inteiro de 10 dígitos), PK. **A aplicação sempre informa o `id`** (`seq.NEXTVAL` lido antes do `INSERT`, §2.7). Existe também a trigger condicional abaixo, como defesa para inserções manuais:

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
  * O impacto da desativação de um **ambiente** mostra os agendamentos ativos afetados **e** a quantidade de scripts homologados nele, que deixam de poder ser disparados ali. O mesmo texto vai para o `detalhe` de `CAD_DESATIVAR`.
* **Texto nos cadastros (regra global):**
  * O servidor valida tamanho e formato **exatos**. Valor maior que o limite, ou fora do formato, é **recusado** com mensagem no campo e nunca truncado em silêncio (vale para todas as telas, inclusive agendamentos, §7.6).
  * Campos de **identificador** (nome de ambiente, nome de perfil, login, código de parâmetro e de funcionalidade) não recebem `strip()`. Espaço no início ou no fim é um caractere inválido e gera recusa, para seguir a CK à risca.
  * Campos de **texto livre** (nome de script, `label`, `descricao`, `grupo`, `categoria`, `etapa`) recebem `strip()` e recusam caracteres de controle (`\x00-\x1f`, `\x7f`).
* **Concorrência otimista nos cadastros (sem coluna de versão):**
  * O formulário de edição carrega uma `versao`: o sha256 dos campos editáveis, `ativo` incluído, calculado pelo servidor na leitura.
    * Campo **sensível** (`valor_padrao` de parâmetro sensível, `valor_padrao_sub` de vínculo sensível, respostas sensíveis no `parametros_json` de agendamento) entra no hash como um **marcador fixo** (`<sensivel:preenchido>` ou `<sensivel:vazio>`), nunca pelo valor. A versão vai para o HTML e não pode permitir adivinhar o segredo por força bruta.
    * **Consequência aceita:** uma troca feita por outra pessoa **só** no valor sensível, entre abrir o formulário e salvar, não gera conflito.
      * Se o usuário deixou o campo sensível em branco, fica valendo o valor mais recente.
      * Se digitou um valor novo, vale o dele.
      * Trocas de preenchido para vazio, ou de vazio para preenchido, mudam o marcador e geram conflito normalmente.
      * O `esperado` do repositório continua comparando os valores reais entre a releitura e a gravação.
    * Nas telas de conjunto (homologação, vínculos), a versão cobre só o conjunto lido. Uma mudança de estado de um item entre a leitura e o POST (por exemplo, ambiente desativado) aparece como a recusa específica ("item inativo"), não como conflito.
  * Ao salvar, o service relê o registro e compara a versão. Em seguida, repassa os valores lidos ao repositório, que executa `UPDATE ... WHERE id = :id AND <coluna = valor lido>` com comparação nula-segura ANSI `(c = :v OR (c IS NULL AND :v IS NULL))` e checa o `rowcount`.
  * Se a versão divergir ou o `rowcount` for 0, o resultado é `RepoConflito`, sem alteração nem auditoria. A mensagem é a de conflito de edição do §2.4.2: "Outra pessoa mudou este registro enquanto você editava. Recarregue a página para ver a versão nova e faça a sua alteração de novo."
  * A linha de auditoria é gravada na mesma operação (transação) do `INSERT` ou `UPDATE`.
* **Edição de agendamento:** ao salvar uma alteração, `usuario_id` passa a ser o **editor**, que precisa ter `pode_executar` vigente para o script e o ambiente da regra. A regra sempre roda sob os privilégios de quem a definiu por último, o que impede um usuário de reaproveitar privilégios de outro editando a regra dele. A alteração é auditada com o `usuario_id` anterior e o novo. Script e ambiente da regra não mudam na edição (§7.6).

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
  * `ativo CHAR(1) DEFAULT 'S' NOT NULL`
  * `created_at DATE DEFAULT SYSDATE NOT NULL`
* **Validação na UI** (`admin_ambientes_service.py`):
  * `nome` segue a CK à risca. Letras minúsculas, espaços (inclusive nas pontas) ou outros caracteres são **rejeitados** com mensagem, não convertidos. O `nome` é imutável depois de criado: o campo fica somente leitura e o servidor ignora o valor enviado.
  * `conexao` é opcional, como a coluna. Quando preenchida, aceita apenas:
    * Easy Connect: `^[A-Za-z0-9._-]+:[0-9]{1,5}/[A-Za-z0-9._-]+$`;
    * alias TNS: `^[A-Za-z0-9._-]{1,128}$`.
  * Um `@` é recusado com "Informe apenas o DSN; credenciais ficam no secrets.cfg."
  * `descricao` é opcional, com até 100 caracteres e sem caracteres de controle.

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
  * `ck_tbsss_scr_int (interpretador IN ('PYTHON3','BASH','SH','POWERSHELL'))`
  * `ck_tbsss_scr_path (SUBSTR(path_file, 1, 1) <> '/' AND INSTR(path_file, '..') = 0 AND INSTR(path_file, '\') = 0 AND INSTR(path_file, ':') = 0)` (formato do §8.5)
  * `ck_tbsss_scr_tmout (timeout_seg IS NULL OR timeout_seg > 0)`
  * `ck_tbsss_scr_pasta (REGEXP_LIKE(pasta_base, '^[A-Z][A-Z0-9_]{0,29}$'))`
* **Colunas:**
  * `id`
  * `nome VARCHAR2(60 CHAR) NOT NULL`
  * `descricao VARCHAR2(200 CHAR)`
  * `grupo VARCHAR2(30 CHAR)`
  * `categoria VARCHAR2(30 CHAR)`
  * `etapa VARCHAR2(30 CHAR)`
  * `interpretador VARCHAR2(15 CHAR) NOT NULL` (lógico; o executável é mapeado por agente, §8.5)
  * `pasta_base VARCHAR2(30 CHAR) NOT NULL` (nome lógico da pasta base, mapeado por nó em `base_script_dirs`, §8.5)
  * `path_file VARCHAR2(250 CHAR) NOT NULL` (relativo à pasta base)
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
  * `senha_hash VARCHAR2(256 CHAR) NOT NULL` (nunca sai da camada de serviço)
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
  * `parametros_json CLOB` (objeto `{"codigo": "valor"}` com as respostas resolvidas; §7.6)
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
  * `plataforma VARCHAR2(10 CHAR)`, com CK `ck_tbsss_agt_plat (plataforma IN ('LINUX','WINDOWS','UNIX'))`
  * `interpretadores VARCHAR2(100 CHAR)` (lista separada por vírgula dos interpretadores lógicos suportados)
  * `pastas_base VARCHAR2(500 CHAR)` (lista separada por vírgula dos **nomes** das pastas base do agente, sem os caminhos)
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
* **Ações:** `LOGIN_OK`, `LOGIN_FALHA`, `LOGIN_BLOQUEIO`, `LOGOUT`, `TICKET_CRIAR`, `TICKET_CANCELAR`, `TICKET_REEXECUTAR`, `CAD_INSERIR`, `CAD_ALTERAR`, `CAD_DESATIVAR`, `PERM_ALTERAR`, `AGD_PAUSAR`, `AGENTE_INICIO`, `AGENTE_FIM`, `PURGE`, `AUD_EXPORTAR` (exportação CSV da trilha, F6.1). O catálogo é mantido em código (`auditoria_service.ACOES`) e não usa CK, para permitir extensão.
* A tabela não tem FKs intencionalmente: a trilha sobrevive a exclusões.

---

## 11. Bootstrap, Seed e Retenção

### 11.1 `scripts/init_db.py` (idempotente)

* A DDL Oracle 11gR2 é gerada por `init_db.py` a partir do registro de `sql_ident` (§2.7).
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
* A execução é agendada pelo agendador do sistema operacional no servidor do agente (cron no POSIX; Agendador de Tarefas no Windows) e auditada como `PURGE`.

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
modo_driver = auto                ; auto (Thin → Thick → cx_Oracle) | thin | thick | cx_oracle (§2.3)
oracle_client_lib_dir =           ; somente Windows/macOS; no Linux/Unix usar ldconfig/LD_LIBRARY_PATH
call_timeout_ms = 30000
pool_min = 1
pool_max = 4

[secrets]
secrets_file = /etc/sss/secrets.cfg

[agent]
agent_id = srv-linux-prod-01
ambientes_atendidos = PRODUCAO,HOMOLOGACAO
base_script_dirs = ROTINAS=/opt/automacoes/scripts,BATCH=/home/batch/scripts
                                  ; NOME=caminho; nomes ^[A-Z][A-Z0-9_]{0,29}$, caminhos absolutos e não aninhados (§8.5)
                                  ; no nó web, NOME= (sem caminho) declara uma pasta que só existe nos agentes
work_dir = /var/lib/sss/work
script_owner_uids = 0             ; POSIX: UIDs donos da árvore de scripts
script_owner_sids =               ; Windows: SIDs donos da árvore (ex.: S-1-5-32-544)
interpretadores = PYTHON3=/usr/bin/python3,BASH=/bin/bash,SH=/bin/sh
                                  ; Windows ex.: PYTHON3=C:\Python36\python.exe,POWERSHELL=C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe
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
child_locale = C.UTF-8            ; somente POSIX
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

**Faixas de cada chave** (limites inclusivos; `enum` aceita só os valores listados no exemplo acima):

| Seção | Chave | Tipo | Faixa / formato |
|---|---|---|---|
| `[app]` | `sss_env` | enum | `DEV`, `HML`, `PROD` |
| `[app]` | `data_backend` | enum | `FAKE`, `ORACLE` |
| `[oracle]` | `user`, `dsn` | texto | obrigatório, não vazio |
| `[oracle]` | `owner` | texto | `^[A-Za-z][A-Za-z0-9_]{0,29}$` |
| `[oracle]` | `table_prefix` | texto | `^[A-Za-z][A-Za-z0-9_]{0,7}$`: começa com letra, até 8 caracteres |
| `[oracle]` | `modo_driver` (F7.0) | enum | `auto`, `thin`, `thick`, `cx_oracle` |
| `[oracle]` | `oracle_client_lib_dir` | caminho | opcional |
| `[oracle]` | `call_timeout_ms` | inteiro | 1 a 3.600.000 |
| `[oracle]` | `pool_min`, `pool_max` | inteiro | 1 a 1.000, com `pool_min <= pool_max` |
| `[secrets]` | `secrets_file` | caminho | obrigatório |
| `[agent]` | `agent_id` | texto | `^[A-Za-z0-9._-]{1,30}$` |
| `[agent]` | `ambientes_atendidos`, `script_owner_uids` | lista CSV | obrigatória |
| `[agent]` | `script_owner_sids`, `interpretadores` (F8.0) | lista CSV | conforme §8.5 |
| `[agent]` | `base_script_dirs` | lista `NOME=caminho` | obrigatória, com ao menos uma pasta; nomes únicos `^[A-Z][A-Z0-9_]{0,29}$`; caminhos absolutos, distintos e não aninhados; caminho vazio só no nó web (§8.5) |
| `[agent]` | `work_dir` | caminho | obrigatório |
| `[agent]` | `max_parallel_jobs`, `max_parallel_hard_limit` | inteiro | 1 a 999, com `max_parallel_jobs <= max_parallel_hard_limit` |
| `[agent]` | `claim_batch_size`, `schedule_batch_size` | inteiro | 1 a 1.000 |
| `[agent]` | `orchestrator_interval_s`, `cancel_poll_interval_s`, `heartbeat_interval_s`, `shutdown_grace_s` | inteiro | 1 a 3.600 |
| `[agent]` | `fence_timeout_s`, `node_offline_timeout_s`, `misfire_tolerance_s` | inteiro | 1 a 86.400, com as invariantes do §8.9 |
| `[agent]` | `kill_grace_s` | inteiro | 1 a 300 |
| `[agent]` | `script_timeout_s` | inteiro | 1 a 86.400 (padrão global; o `timeout_seg` de cada script vai até 9.999.999, como a coluna) |
| `[agent]` | `shutdown_mode`, `misfire_policy` | enum | conforme o exemplo |
| `[agent]` | `cron_horizon_days` | inteiro | 1 a 36.500 |
| `[agent]` | `child_locale` | texto | obrigatório |
| `[agent]` | `env_passthrough` | lista CSV | opcional, sem as variáveis bloqueadas do §8.6 |
| `[logging]` | `log_dir` | caminho | obrigatório |
| `[logging]` | `level` | enum | `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `[logging]` | `app_log_max_bytes`, `max_log_size_bytes` | inteiro | 1.024 a 1.073.741.824 |
| `[logging]` | `max_local_log_size_bytes` | inteiro | 1.024 a 10.737.418.240 |
| `[logging]` | `app_log_backups` | inteiro | 1 a 100 |
| `[logging]` | `local_log_retention_days` | inteiro | 1 a 3.650 |
| `[web]` | `session_idle_timeout_s`, `login_bloqueio_s` | inteiro | 1 a 86.400 |
| `[web]` | `login_max_tentativas` | inteiro | **1 a 99** (a coluna `tentativas_falha` é `NUMBER(2)`) |
| `[web]` | `log_poll_interval_s` | inteiro | 1 a 3.600 |
| `[web]` | `trusted_proxies` | lista CSV | opcional |
| `[web]` | `allowed_origins` | lista CSV | obrigatória |
| `[retencao]` | `ticket_retention_days`, `audit_retention_days` | inteiro | 1 a 3.650 |
| `[retencao]` | `purge_batch_size` | inteiro | 1 a 100.000 |

**Falha de configuração (web e daemon):**
* A subida é abortada com um registro **CRITICAL** contendo a seção, a chave e o motivo, sem nunca o valor de um segredo.
* O CRITICAL vai para o log da aplicação (`sss_web.log` ou `sss_scheduler.log`) quando `[logging]` é válido. Quando não é (por exemplo, `log_dir` inválido), vai para o stderr do processo, no mesmo formato do §13.
* No nó web, a requisição recebe a página de erro genérica (500), sem o detalhe.

A chave `modo_driver` substitui `driver` e `use_thick_mode` a partir do F7.0 (CR-002); até lá, o código atual (backend FAKE) ainda lê as chaves antigas. As chaves `script_owner_sids` e `interpretadores` passam a ser lidas e validadas a partir do F8.0 (CR-001). A chave `base_script_dirs` substitui `base_script_dir` a partir do passo P6A do CR-003, porque o cadastro de scripts no nó web já a utiliza; a chave antiga deixa de ser aceita.

### 12.2 Launchers

`bin/sss-web.sh` e `bin/sss-scheduler.sh` (Linux/Unix) devem:

* exportar `LD_LIBRARY_PATH` do Instant Client 19 (quando não houver `ldconfig`) e `TZ`. Os valores vêm das variáveis `SSS_IC_DIR` (diretório do Instant Client) e `SSS_TZ` (fuso), definidas pela operação;
* aplicar `umask 077`;
* recusar a execução como root;
* fazer `exec` do processo Python, para que os sinais cheguem diretamente a ele;
* iniciar **somente** o processo Python do SSS. O `sss-web.sh` aceita três formas: sem argumentos (servidor padrão), só opções (`-...`, repassadas ao `anyserver.py`) ou `<python3[.x]> web2py.py|anyserver.py [args]`. Qualquer outro comando é recusado com código 2; repassar um comando arbitrário (`exec "$@"` sem essas checagens) é proibido.

`bin/sss-web.ps1` e `bin/sss-scheduler.ps1` (Windows) devem:

* incluir o Instant Client 19 no `PATH` do processo e definir `TZ`;
* recusar a execução com token elevado ou como SYSTEM;
* iniciar o Python em primeiro plano, para que `CTRL_BREAK` e o arquivo `.stop` sejam tratados pelo próprio daemon.

`bin/sss-stop.sh` e `bin/sss-stop.ps1` criam o arquivo `work_dir/sss-<agent_id>.stop`, para a parada controlada sem sinal (§8.11).

**Pacote de implantação:** `scripts/empacotar.py` (biblioteca padrão, roda em Linux e Windows) gera `dist/sss-<versao>.tar.gz` e `dist/sss-<versao>.zip` com o mesmo conteúdo e um `SHA256SUMS`, e falha se encontrar segredo ou código de DEV no pacote (F9.1).

**Pastas de runtime do web2py:** o web2py cria as pastas `applications/`, `deposit/`, `logs/` e `site-packages/` no diretório corrente quando é executado fora da raiz. Essas pastas nunca fazem parte da aplicação: o `.gitignore` as ignora dentro de `applications/script_scheduling_service/`, e os launchers e a documentação sempre executam a partir da raiz do web2py.

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

* Todo `except` registra o código de erro do banco (ORA- no Oracle) e o stack trace em ERROR antes de qualquer `ROLLBACK`.
* É proibido registrar senhas, `PADRAO_VALOR_RUN_CONEXAO_BD`, `cookie_key`, o conteúdo de `secrets.cfg` e valores de parâmetros sensíveis.
* **Visão operacional:** a tela de agentes (`auditoria/agentes`, `VER_AUDITORIA`) lista `tbsss_agentes` com o heartbeat e os tickets `RUNNING` de cada agente. É **somente leitura**.
  * **Saúde derivada** da idade do heartbeat, medida pelo relógio do banco (`SYSDATE`), com os limiares do daemon:

    | Saúde | Condição | Exibição |
    |---|---|---|
    | `OK` | idade < `2 × heartbeat_interval_s` | verde, ícone de confirmação |
    | `ATRASADO` | idade ≤ `fence_timeout_s` (limite inclusivo) | âmbar, ampulheta |
    | `EM_RISCO` | idade ≤ `node_offline_timeout_s` (limite inclusivo) | vermelho, alerta |
    | `OFFLINE` | além disso, sem heartbeat ou com status `PARADO` | cinza, círculo cortado |

  * Cartões por agente com "há N s", lista expansível dos tickets `RUNNING` (com link para o detalhe), legenda dos estados e atualização automática a cada 15 s (fragmento `.load`, que preserva as listas abertas).
  * Cada cartão mostra também a plataforma, os interpretadores e os **nomes** das pastas base do agente (`pastas_base`), sem os caminhos.
  * Backend FAKE (DEV): o `agt-host01` renova o heartbeat a cada leitura. O `agt-host02` nasce com o heartbeat congelado 30 s antes da carga do seed, então envelhece com o relógio: começa `ATRASADO`, passa a `EM_RISCO` cerca de 1 min depois e a `OFFLINE` cerca de 2,5 min depois.
* **Painel inicial** (`default/index`), com cartões por permissão:
  * contagem por status dos tickets criados nas últimas 24 h e meus últimos 5 tickets (quem consulta tickets, no escopo da lista);
  * próximos 5 agendamentos ativos (`CAD_AGENDAMENTOS`);
  * saúde dos agentes (`VER_AUDITORIA`).

---

## 14. Riscos Residuais Aceitos

| Risco | Mitigação vigente |
|---|---|
| Credencial legível no ambiente do processo (`/proc/<pid>/environ` no Linux; memória do processo no Windows), pelo mesmo usuário ou por administradores | Conta dedicada, sem shell interativo nem privilégio administrativo, e servidor restrito |
| Argumentos visíveis em `ps`/lista de processos | Proibição de parâmetro de senha; parâmetros sensíveis apenas mascarados na UI e nos logs |
| POSIX: script que faça `setsid`/double-fork escapa do `killpg` | Homologação do script no catálogo; política de revisão de código. No Windows, o Job Object cobre esse caso |
| Windows: janela entre o spawn e a atribuição ao Job Object, em que o filho poderia criar um processo fora do Job | A atribuição ocorre imediatamente após o `Popen`; homologação e revisão dos scripts |
| Windows: interpretadores com política de execução própria (PowerShell) | `-NoProfile -NonInteractive -ExecutionPolicy Bypass -File` fixos; perfis e módulos de usuário não são carregados |
| TOCTOU entre a validação e o `exec` | Árvore de scripts não gravável pelo agente (§8.5) |
| Granularidade fina "perfil × script × ambiente" | Não suportada; a intersecção `perfil_amb ∩ script_amb` atende ao escopo atual |
| Semântica de horário de verão | Horário de parede do servidor Oracle (§7.1) |
| Lacunas em sequences | Aceitas por design |
| Segredos com menos de 4 caracteres não são mascarados nos logs (§4.1) | Política de senha de 12 caracteres ou mais; segredos curtos não devem existir |
| Bloqueio simulado de login inexistente fica na memória de cada processo web (§4.2) | Mensagem genérica e hash fictício; o bloqueio real das contas existentes fica no banco e vale para todos os nós |
| Sessão aberta continua válida depois de um bloqueio por falhas de terceiros (§4.2) | O bloqueio impede novos logins; o administrador pode desativar o usuário, o que encerra a sessão na hora |
| Tempos de fencing diferentes entre agentes anulam a garantia do §8.9 | Valores idênticos em todos os nós, registrados em INFO e conferidos no E2E (§8.9) |
