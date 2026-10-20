# Script Scheduling Service (SSS) — README.md

Serviço web corporativo para gestão, agendamento e execução distribuída de rotinas em Python e Shell em servidores Unix/Linux restritos, integrado ao Oracle Database >= 11gR2 e com arquitetura multi-ambiente e multi-nó.

> **Change requests aplicados:** CR-001 (agente com interpretador lógico; a parte Windows foi revogada pelo CR-005), CR-002 (Oracle único e driver adaptativo), CR-003 (correções da análise funcional pós-F6.1; a D16, várias pastas base, foi substituída pelo CR-005), CR-004 (telas de consulta e linguagem clara) e CR-005 (somente POSIX, caminho livre do script e pastas de log por minuto), em `docs/arquitetura/`. O texto abaixo já os incorpora.
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
| Cliente C (modos Thick e cx_Oracle) | **Oracle Instant Client 19.x** (Linux ou Unix, conforme o nó) | Conecta do 11.2.0.4 ao 23ai. O IC 21c/23ai não conecta ao 11gR2. Obrigatório nos nós que acessam banco 11g; recomendado em todos como contingência |

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
* **Desenvolvimento em macOS:** `oracle_client_lib_dir` só é usado em macOS. O IC 19 para macOS existe apenas para Intel (x86_64). Em Apple Silicon, use o modo Thin (banco 12.1+), Python x86_64 sob Rosetta ou um container/VM Linux x86_64.
* `modules/db_conn.py` é a **única** porta de acesso ao banco. Ele contém a seleção do driver, o adaptador das diferenças de API entre `oracledb` (Thin/Thick) e `cx_Oracle` (exceções mapeadas por driver e modo para os erros do contrato, tipos de bind, conversão do estilo `:nome` para o `paramstyle` do driver, pool e `init_oracle_client`).
* **Toda conexão deve:**
  * usar `autocommit = False`;
  * definir `call_timeout` (`call_timeout_ms` no config);
  * preencher `module`, `action` e `client_identifier` para rastreabilidade pelo DBA (por exemplo, `module='SSS_SCHED'`, `action='CLAIM'`, `client_identifier=<agent_id ou login>`).
* **Reconexão e failover (CR-007, R-12):**
  * Erros de rede e de indisponibilidade descartam a conexão e levam à reconexão. Thick/cx_Oracle: ORA-03113, ORA-03114, ORA-03135, ORA-12541, ORA-12170, ORA-12514, ORA-12528, ORA-12537, ORA-01033, ORA-01034, ORA-01089, ORA-00028, ORA-01012, ORA-02396, ORA-25408 e DPI-1080. Thin: os equivalentes `DPY-*`, como DPY-4011, DPY-6000 e DPY-6005. A lista é mapeada por driver e modo no `db_conn`; um erro de rede fora dela é tratado como erro de operação (ERROR) e investigado.
  * O daemon tenta **uma** reconexão por ciclo, com *backoff* exponencial de 1 s a 60 s contado em prazos do relógio monotônico, **nunca** com `sleep` dentro da operação (orçamento do laço, §8.1). Cada tentativa registra WARN.
  * **Tempo esgotado da chamada** (*call timeout*: DPY-4024 no Thin, DPI-1067 ou ORA-03156 no Thick e no cx_Oracle) é mapeado à parte: `ROLLBACK`, WARN e nova tentativa no ciclo seguinte. É o caso típico de linha travada por uma sessão morta (§8.8).
  * **Conexão com prazo:** a abertura da conexão também respeita `call_timeout_ms` (`tcp_connect_timeout` no Thin; `CONNECT_TIMEOUT` no descritor ou `SQLNET.OUTBOUND_CONNECT_TIMEOUT` no `sqlnet.ora` do cliente, no Thick e no cx_Oracle).
  * **Orçamento da abertura (CR-008, R-17):** com DSN descritor, o pior caso da abertura é `CONNECT_TIMEOUT × (RETRY_COUNT + 1) × endereços` (um endereço por `ADDRESS` da lista, somando as listas). Esse valor precisa ser `<= call_timeout_s`. O `db_conn` calcula a conta a partir do descritor (`CONNECT_TIMEOUT` ausente = `call_timeout_s`; `RETRY_COUNT` ausente = 0) e o agente, o nó web e o `check_env.py` registram WARN `CONEXAO_ACIMA_DO_PRAZO` com o valor quando ela passar; o exemplo do `IMPLANTACAO.md` §18.2 segue a fórmula.
  * **Pool do nó web:** valida a conexão antes do uso depois de 60 s ociosa (`ping_interval`), para descartar sessões perdidas num failover.
  * **Desfecho desconhecido do `COMMIT`** (a conexão cai durante o `COMMIT`): a operação nunca é repetida às cegas. No agente, a varredura própria reconcilia o estado (§8.7); no web, o usuário vê a mensagem de falha e confere o resultado na tela.
  * Exemplos de DSN para RAC e Data Guard (serviço, `FAILOVER`, `RETRY_COUNT`) e o `SQLNET.EXPIRE_TIME` do servidor ficam no `docs/IMPLANTACAO.md`.

### 2.4 Frontend

* HTML5, **Bootstrap 5.3.8** e **Alpine.js (build CSP)**, servidos exclusivamente de `static/` com fontes locais.
* **Identidade visual**, aplicada pelos tokens de `static/css/sss.css`:
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
5. **Nunca** mostrar detalhe técnico (ORA-, stack trace, SQL); essa regra continua valendo (AGENTS §3.1). O caminho do script (`path_file`) não é detalhe técnico oculto: aparece para todos que veem o script ou o ticket (CR-005, D8).
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
| Só administrador, usuários (CR-008, E1) | "Só um administrador pode alterar um usuário administrador ou dar o perfil de administrador." | "Peça a um administrador." |
| Só administrador, perfis (CR-008, E1) | "Só um administrador pode alterar um perfil de administrador, mudar o seu próprio perfil ou marcar um perfil como administrador." | "Peça a um administrador." |
| Sessão no tempo máximo (CR-008, E2) | "A sua sessão chegou ao tempo máximo e foi encerrada por segurança." | "Entre de novo." |

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
* O contrato tem duas implementações, escolhidas pela `modules/repo_factory.py`. **A aplicação usa sempre o Oracle** do `[oracle]` do config (owner e prefixo). A chave `[app] data_backend` foi removida no F7.3, e um config que ainda a tenha é recusado com a instrução de apagar a linha. O FAKE só existe quando um **teste** o injeta pelo gancho `repo_factory.configurar(...)`, e só com `sss_env = DEV`:

| Backend | Uso | Implementação |
|---|---|---|
| `FAKE` | Só testes automáticos sem banco, por injeção (`repo_factory.configurar`) | `modules/repo_fake/`: memória do processo, seed determinístico e `threading.Lock` por agregado |
| `ORACLE` | A aplicação, em DEV, HML e PROD | `modules/repo_oracle/` (§2.7): único local com SQL; conexões pelo pool do processo (`db_conn.pool`, fechado no `atexit`) |

* Os controllers e services **não sabem** qual backend está ativo.
* **Paridade obrigatória:** o FAKE emula a semântica do Oracle que o código consome. Isso inclui `UPDATE` condicional com `rowcount` (transição perdida gera `RepoConflito`), unicidade (`RepoViolacao`), `ON DELETE CASCADE`, triggers de imutabilidade, paginação e ordenação idênticas. Também inclui:
  * **chaves estrangeiras e NOT NULL:** inclusões de ticket, `ticket_resp` e agendamento com script, ambiente (nome), solicitante (login), usuário ou parâmetro inexistente geram `RepoViolacao` com o nome da FK do §10. A UK de `ticket_resp` também é verificada;
  * **limites de coluna** que o código grava, por exemplo `ator` (40) e `detalhe` (1.000) da auditoria;
  * **unicidade da ocorrência** de agendamento nos tickets (`ix_tbsss_tck_ocor`, CR-007, R-27) e o **`total` limitado** das listagens (10.001, §10, R-29);
  * a **linha de controle** (`tbsss_controle`, tabela 17) com a versão do esquema do código (`sql_ident.VERSAO_ESQUEMA`, CR-007, D4);
  * **colunas de registro (CR-006):** `created_*` na inclusão e `updated_*` só nas alterações de negócio (§10), com `store.agora()` no lugar do `SYSDATE`. Gravação sem ator é recusada com `RepoViolacao`, como no Oracle;
  * **comparação de texto** idêntica à do Oracle: UKs diferenciam maiúsculas de minúsculas;
  * **cascatas** (`ON DELETE CASCADE` e `SET NULL` do §10): o contrato não expõe exclusão de registros mestres (só o `purge.py`, que é batch e não tem FAKE, apaga linhas). Por isso, não há cascata a emular no FAKE; o `test_repo_contract.py` as cobre **contra o Oracle** (F7.3), com `DELETE` direto no teste.
* **Seed do FAKE coerente com as regras de negócio:** ele também serve de demonstração na homologação e precisa respeitar as regras:
  * funcionalidades com os nomes do §4.3.D;
  * nenhum parâmetro de senha ou credencial (§6.5); o exemplo sensível é um dado pessoal, como um documento;
  * prioridade 1 só em tickets de solicitante admin;
  * snapshot e `ticket_resp` compatíveis com o script e os vínculos de cada ticket;
  * `created_at` nunca no futuro;
  * colunas de registro coerentes com o §10 (CR-006): `created_by = 'SYSTEM:seed'` nos cadastros e vínculos; `SYSTEM:<codigo>` nos agentes; nos tickets, o login do solicitante (manual) ou `SYSTEM:<agente>` (desdobro); `updated_*` preenchidos só onde o estado do seed implica uma alteração (ticket fora de `PENDING`, regra pausada, registro inativo), sempre entre o `created_at` e o momento atual;
  * `proxima_execucao` calculada pelo `recurrence.py`, alinhada ao minuto e à regra;
  * `parametros_json` com as respostas resolvidas completas (§7.6).
* **Relógio do FAKE:** `store.agora()` (hora local sem microssegundos) simula o `SYSDATE` e é o único uso permitido de `datetime.now()` (AGENTS §6).
* **Simulação de execução no FAKE (somente DEV):** não há daemon. Um ticket `RUNNING` do seed avança e termina quando o log é lido pelo visualizador (`_simular_log`); a finalização simulada grava `updated_*` com `SYSTEM:<agente>` do ticket (§10). Isso é só demonstração e não tem equivalente no Oracle.
* **Leituras de tickets sem CLOB (F7.3, TICKETS), nos dois backends:**
  * `RepoTickets.listar` nunca devolve `log_output` nem `parametros_enviados`.
  * `RepoTickets.obter` devolve o `parametros_enviados` (o snapshot que o detalhe mostra), mas nunca o `log_output`. O log só sai em fatias por `log_ler` (AGENTS §4.13, §8.10).
* **Exceção documentada (F7.3, AGENDAMENTOS):** `RepoAgendamentos.listar` traz o `parametros_json` (CLOB pequeno com as respostas da regra), porque o service avalia cada regra com ele (tela de regras e Agenda). Ler por `obter` faria uma consulta por regra ativa. Nenhuma listagem traz `log_output`.
* **Concorrência das transições no FAKE:** as transições web de ticket rodam sob o lock do agregado, então o FAKE nunca chega a perder uma corrida. O tratamento de `rowcount = 0` (`RepoConflito`) nessas transições só é exercitado pelo `test_repo_contract.py` contra o Oracle (F7.3).
* **Exceções de contrato** (`modules/repo_errors.py`): `RepoErro`, `RepoNaoEncontrado`, `RepoConflito`, `RepoViolacao` e `RepoIndisponivel`.
* A suíte `scripts/test_repo_contract.py` roda **a mesma bateria** contra os dois backends. Contra ORACLE, ela só executa se `SSS_TEST_DSN` estiver definido.
* **Testes Oracle reais: uma chave só, `SSS_TEST_ORACLE=1`** (`scripts/_oracle_test_support.py`).
  * **Origem dos parâmetros:** owner, prefixo, DSN e conta vêm só do `instance/config.ini`, os mesmos da aplicação. Nada é repetido em variáveis de ambiente.
  * **Recusas antes de qualquer conexão:** sem a chave, os testes de banco ficam pulados (`NÃO TESTADO`). Fora de `sss_env = DEV`, ou com `[oracle] dsn`/`owner` inválidos, a execução é recusada. As variáveis da versão anterior (`SSS_TEST_DSN`, `SSS_TEST_OWNER`, `SSS_TEST_CONFIG`, `SSS_TEST_SCHEMA_DISPOSABLE`, `SSS_TEST_SCHEMA_COMPARTILHADO`) também são recusadas, para não serem ignoradas em silêncio.
  * **A partir do F7, aplicação e validações usam as tabelas reais** do owner e do prefixo do config. O FAKE fica só como dublê dos testes automáticos sem banco (os casos que dá para mockar). Desde o fim do F7.3, a aplicação não tem mais `data_backend`: é sempre Oracle.
  * **Modo deduzido do owner:**
    * **Descartável** (owner `SSS_TEST_*`): owner dedicado e conta de teste diferente do owner.
    * **Compartilhado** (qualquer outro owner): para um owner existente, onde não há permissão para criar outro (ex.: `openrisow` no `GFPR`).
      * A conta pode ser o próprio owner, mas o esquema SSS tem de estar implantado na versão do código (`tbsss_controle.versao_esquema = sql_ident.VERSAO_ESQUEMA`).
      * Os testes gravam só registros próprios (nomes `TST_`/`tst_`, IDs das sequences) e nunca alteram os que já existem.
      * A limpeza remove só os IDs criados pelo teste, sem `DROP` nem `TRUNCATE`; limpeza incompleta falha o teste e lista os IDs que sobraram.
      * Os únicos efeitos permanentes são o avanço das sequences e as linhas de auditoria de testes que passam `auditoria=` (a auditoria só recebe inclusões e só o purge remove linhas).
      * **Exceção (F7.3):** algumas operações sempre auditam (`criar` e `solicitar_cancelamento` de tickets, as gravações e a pausa de agendamentos, o `encerrar_sessoes` de usuários). Por isso, só no modo compartilhado, a limpeza apaga a auditoria **dos próprios registros do teste**: `entidade` da tabela (`tbsss_tickets`, `tbsss_agendamentos` ou `tbsss_usuarios`) e `entidade_id` entre os IDs criados pelo teste. Nenhuma outra linha de auditoria é tocada.
  * **Bateria integrada contra o Oracle (`test_repo_contract.py`):** roda com a mesma chave `SSS_TEST_ORACLE=1`; o gate `SSS_TEST_ORACLE_INTEGRATED` saiu depois do 5º agregado. Cada teste cria a própria massa pelos repositórios (classe `_Massa`: ambientes, perfil, usuários, parâmetros, script, agendamento e tickets com sufixo único) e não usa nomes nem IDs do seed.
    * A auditoria é conferida pela `entidade` e pelo `entidade_id` do próprio registro, e o nome das constraints segue o prefixo configurado.
    * O `tearDown` remove só os IDs criados, em ordem de dependência (e, no modo compartilhado, a auditoria deles).
    * A proteção do **último administrador** só é exercida no FAKE e com owner descartável (`SSS_TEST_*`): num owner compartilhado há administradores reais, e a classe fica pulada com o motivo.
* **Trava de ambiente:**
  * `[app] sss_env` aceita `DEV`, `HML` ou `PROD`.
  * O FAKE (só de teste) pedido fora de `sss_env = DEV` é recusado pela factory.
  * `sss_env` continua como trava de segurança da aplicação. Fora de DEV, o código recusa segredos de outro papel, a conta da aplicação igual ao owner, falta de usuário de execução ou de `exec_work_dir`, a galeria `/dev` e o hash não homologado, e exige `purge_user`.
  * **DEV e PROD se separam pelo owner e pelo prefixo** do config: basta apontar para outro owner, ou outro prefixo no mesmo owner.
* O daemon (`run_scheduler.py`) **exige** `ORACLE`. Com `FAKE`, ele aborta.

### 2.6 Plataformas suportadas (CR-005: somente POSIX)

| Nível | Plataformas | Garantia |
|---|---|---|
| **1** | Linux x86_64, para o nó web e para o agente | Testes automatizados e roteiro E2E (F9.2) |
| **2** | Demais Unix (AIX, Solaris, HP-UX, macOS, BSD) | Mesma camada POSIX; homologação pela infraestrutura sob demanda |

* **Windows não é suportado** (CR-005, que revoga a parte Windows do CR-001): nem nó web nem agente.
* Toda primitiva de sistema operacional fica em `modules/plataforma/` (§8.0), só com a implementação POSIX. A camada continua para isolar essas primitivas e permitir os testes.
* O banco e a UI não dependem do sabor de Unix do nó.
* Um mesmo ambiente pode ter agentes com interpretadores diferentes: o claim respeita os interpretadores de cada agente (§8.2).

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
* **Usuários do sistema operacional (CR-007, D1):** o nó web e o agente rodam com contas dedicadas, sem login interativo nem privilégio administrativo. O script de cada ambiente roda com o **usuário de execução** daquele ambiente (`[agent] usuarios_execucao`, §8.0), diferente do usuário do agente. O agente nunca roda como root e só troca de usuário pelo helper `sss-helper`, chamado por `sudo` com regra fixa. Assim, o script não lê os segredos, os logs nem o ambiente do agente.
* `models/*.py` deve ser leve, pois é carregado pelo daemon com `-M`. Esses arquivos não podem executar DDL, abrir conexão no import nem fazer I/O pesado.

### 3.2 Estrutura de diretórios

Os itens marcados com `[F7.x]`, `[F8.x]` ou `[F9.x]` ainda não existem: são criados no prompt indicado (`docs/prompts/00_INDEX.md`).

```text
bin/
  sss-web.sh                  # ambiente do Instant Client/TZ e subida do WSGI
  sss-scheduler.sh            # ambiente e subida do daemon
  sss-stop.sh                 # [F9.1] parada controlada do daemon pelo arquivo .stop (§8.11)
  sss-helper                  # [F8.0] helper de execução com o usuário de execução (run/term/kill/limpar), instalado pelo root em /opt/sss/bin (§8.0, CR-007)
applications/script_scheduling_service/
  controllers/                # default.py (login), tickets.py, logs.py, agendamentos.py, admin_*.py, auditoria.py, dev.py (somente DEV)
  models/
    00_config.py              # carga e validação de config (sem I/O de banco)
    10_security.py            # sessão, cabeçalhos HTTP, CSRF, guarda RBAC
  modules/
    sss_config.py             # parser e validação tipada do config.ini e do secrets.cfg
    sss_logging.py            # configuração de logging (§13)
    db_conn.py                # [F7.0/F7.2] seleção do driver (Thin → Thick → cx_Oracle), adaptador, binds, mapa de erros, pool, conexão dedicada do daemon
    plataforma/               # [F8.0] primitivas de SO, só POSIX (Linux/Unix) (§8.0, CR-005)
    sql_ident.py              # registro de identificadores, validação de owner/prefixo, nomes qualificados
    repo_errors.py            # exceções de contrato (§2.5)
    repo_factory.py           # seleção do backend FAKE/ORACLE (banco real via repo_oracle)
    repo_*.py                 # contratos abstratos por agregado (sem SQL)
    repo_fake/                # implementação em memória + seed (somente DEV)
    repo_oracle/              # implementação SQL Oracle 11gR2 (único local com SQL, §2.7) [F7.3]
    auth_service.py           # autenticação, bloqueio, revalidação de sessão
    ticket_service.py         # criação, cancelamento e reexecução de ticket (§5); rotinas disponíveis e histórico (CR-004)
    admin_*_service.py        # cadastros (PADRAO_CRUD_ADMIN.md); admin_crud.py: validação comum
    agendamentos_service.py, agentes_service.py, permissoes_service.py  # regras, painel de agentes, O que eu posso fazer
    ui_menu.py                # menu por permissão
    ui_helpers.py             # formatação de status, datas e paginação para as views
    rbac.py                   # decisões de autorização (§4.3)
    security.py               # hash de senha, CSRF, comparação em tempo constante
    params_compiler.py        # validação de respostas e compilação do argv (§6)
    cron_parser.py            # parser CRON de 5 campos (§7.3)
    recurrence.py             # cálculo da próxima execução e misfire (§7)
    path_guard.py             # validação de interpretador e script (§8.5)
    pastas_log.py             # pasta do script e caminhos dos logs de execução e da aplicação (§8.4, §13, CR-005)
    env_builder.py            # [F8.1] montagem do ambiente limpo (§8.6)
    executor.py               # [F8.1] spawn, timeout, kill, finalização
    log_pump.py               # [F8.2] arquivo local -> CLOB com mascaramento (§8.10)
    masking.py                # mascaramento de segredos e PII
    scheduler_loop.py         # [F8.3] laço principal do daemon
    auditoria_service.py      # catálogo de ações, consulta e exportação da trilha (§4.4). A escrita de tbsss_auditoria
                              # é feita pelo próprio repositório, na operação que recebe auditoria= (não existe audit.py)
  scripts/
    init_db.py                # [F7.1] bootstrap idempotente de DDL e seed, versão do esquema e migrações (§11)
    migracoes/                # [F7.1] migrações numeradas m<NNNN>_<descricao>.py (§11.1, CR-007)
    saude.py                  # [F9.1] verificação de saúde no padrão Nagios (§13, CR-007)
    sondar_driver.py          # [F7.0] sondagem isolada de um candidato de driver (Thin, Thick, cx_Oracle) (§2.3, CR-002)
    run_scheduler.py          # [F8.3] entrypoint do daemon
    purge.py                  # [F9.1] retenção (§11.3)
    test_*.py                 # testes unittest (AGENTS.md §7)
  static/bootstrap/  static/js/alpine.min.js (build CSP)  static/js/app/  static/css/  static/img/  static/fonts/
  views/                      # layout.html, components/*.html, <controller>/*.html
  instance/config.ini         # configuração sem segredos (§12)
  dev/scripts/                # árvore de scripts de exemplo para DEV/testes (nunca implantada)
docs/
  prompts/                    # prompts de execução faseada (UI-first)
/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/instance          # segredos fora do repositório, modo 0600, um arquivo por papel (§4.1)
/opt/sss/bin/sss-helper       # cópia do bin/sss-helper, dono root, 0755 (§8.0)
```

---

## 4. Segurança, Segredos, Sessão e RBAC

### 4.1 Gestão de segredos

* **Nenhum segredo** reside no `config.ini`, no repositório ou no banco.
* Os segredos ficam em `secrets_file` (padrão `/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/instance`). Cada servidor tem o **seu** arquivo, só com os segredos do papel do processo que roda nele (CR-007, D1b). Na inicialização, web e daemon validam o arquivo pela camada de plataforma e **recusam a subida** caso ele:
  * não seja um arquivo regular;
  * tenha dono diferente de `os.geteuid()` ou `mode & 0o077 != 0`.

```ini
; Nó web
[oracle]
password = ...                 ; conta Oracle do papel web ([oracle] user deste nó)

[web]
cookie_key = ...               ; chave da sessão em cookie cifrado, igual em todos os nós web
```

```ini
; Agente
[oracle]
password = ...                 ; conta Oracle do papel agente ([oracle] user deste nó)

[purge]
password = ...                 ; conta Oracle do papel purge ([retencao] purge_user), usada só pelo purge.py

[monitor]                      ; CR-008, E3: só no servidor que roda o scripts/saude.py
user = sss_monitor
password = ...                 ; conta Oracle só de leitura do papel monitor (§11.1)

[ambiente:PRODUCAO]            ; somente os ambientes de [agent] ambientes_atendidos
user = app_prod
password = ...

[ambiente:HOMOLOGACAO]
user = app_hml
password = ...
```

* **Seções por papel** (validadas por `sss_config.carregar_segredos(caminho, papel)`):

  | Papel | Obrigatórias | Proibidas |
  |---|---|---|
  | `web` | `[web] cookie_key`; `[oracle] password` fora de DEV/FAKE | `[purge]`, `[ambiente:*]` |
  | `agente` (e o `purge.py`, que roda no mesmo servidor) | `[oracle] password`; `[ambiente:X]` de cada ambiente atendido; `[purge] password` no servidor que roda o purge | `[web]` |
  | `monitor` (CR-008, E3: o `scripts/saude.py`) | `[monitor] user` e `[monitor] password` | `[web]`. As demais seções do arquivo do servidor são ignoradas: o `saude.py` não carrega nem registra no `masking` os segredos de outros papéis |

  Fora de DEV, uma seção proibida recusa a subida com CRITICAL (seção e motivo, nunca o valor): o segredo de um papel nunca fica legível no servidor de outro. Em DEV, a mesma situação só gera WARN, porque web e agente dividem a máquina.
* **Contas Oracle por papel (D1b):** dono do esquema (só DDL, usado pelo `init_db.py` com senha digitada, §11.1), **web**, **agente**, **purge** e **monitor** (só leitura, CR-008 E3). Os GRANTs de cada papel estão no §11.1. Nenhuma conta de aplicação (web, agente) altera ou apaga `tbsss_auditoria`; só a de purge apaga, por retenção.
* **Usuário de execução:** o script roda com outro usuário do sistema operacional (§8.0), que não lê o `secrets.cfg` (dono = usuário do agente, `0600`). A credencial do ambiente chega ao script só pelas variáveis `SSS_AMBIENTE_CONEXAO` e `PADRAO_VALOR_RUN_CONEXAO_BD` (§8.6, CR-010).

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
    * Um bloqueio já expirado zera `tentativas_falha` antes de avaliar a nova tentativa, tanto no login quanto em "Minha senha". É rotina técnica (`reiniciar_tentativas` no contrato): não audita nem grava `updated_*` (§10, CR-006). O desbloqueio feito pelo administrador (`desbloquear`) é alteração de negócio e grava `updated_*`.
  * Um sucesso zera `tentativas_falha` e grava `ultimo_login`.
  * Usuário inativo com a senha correta recebe a mensagem genérica e gera `LOGIN_FALHA`, sem incrementar `tentativas_falha`. Com a senha errada, a falha conta normalmente.
  * Login OK, falha e bloqueio são auditados **na mesma operação do repositório** que atualiza o usuário: os métodos `registrar_sucesso_login` e `registrar_falha_login` do contrato recebem `auditoria=` (mesma transação, §4.4).
  * O rehash da senha (iterações abaixo do vigente) é gravado na mesma operação do sucesso do login.
  * Senhas com mais de 1.024 caracteres são recusadas sem calcular o hash (proteção contra negação de serviço).
* **Sessão:**
  * Armazenada em **cookie cifrado** do web2py (`session.connect(request, response, cookie_key=<secrets>)`). Isso dispensa DAL e funciona com N nós web sem sessão aderente.
  * O payload é mínimo: `usuario_id`, `login`, `perfil_id`, `perm_versao`, `sessao_epoch`, `login_em`, `csrf_token` e `ultimo_acesso`.
  * A sessão é renovada no login (`session.renew()`).
  * O timeout por inatividade é `session_idle_timeout_s`. A expiração por inatividade é registrada só no log (INFO), sem auditoria.
  * **Vida máxima (CR-008, E2/R-23):** além da inatividade, a sessão expira `[web] sessao_max_horas` horas (padrão 12) depois do login (`login_em`, relógio do nó web), mesmo com uso contínuo. A expiração é tratada como a de inatividade (log INFO, sem auditoria) e leva ao login com `next` e a mensagem-padrão "Sessão no tempo máximo" (§2.4.2).
  * **Revogação (CR-008, E2/R-23):** `tbsss_usuarios.sessao_epoch` é gravado na sessão no login e comparado na revalidação. Incrementam o valor, na mesma transação da operação: sair (`LOGOUT`), trocar a própria senha, ter a senha redefinida, ser desativado e ter o perfil trocado. Uma sessão com `sessao_epoch` diferente do banco é encerrada pela revalidação e volta ao login, com log INFO `sessão revogada`; não há nova auditoria, porque a operação que revogou já foi auditada na origem (`LOGOUT`, `CAD_ALTERAR` ou `CAD_DESATIVAR`). Consequência declarada: sair em um navegador encerra **todas** as sessões daquele usuário, inclusive um cookie copiado.
  * Cookies com `HttpOnly` e `Secure`.
    * **Exceção de DEV:** com `sss_env = DEV` sobre HTTP (servidor de desenvolvimento), o atributo `Secure` é omitido, porque o navegador descartaria o cookie. Em HML e PROD, `Secure` é sempre enviado.
  * **`SameSite` no Python 3.6:** `http.cookies.Morsel` só aceita o atributo `samesite` a partir do 3.8. No 3.6, a proteção cross-site se apoia em duas camadas:
    * o token CSRF;
    * a checagem obrigatória de `Origin`, ou de `Referer` quando `Origin` estiver ausente, contra `[web] allowed_origins` em todo `POST`.

    Requisição sem nenhum dos dois cabeçalhos é rejeitada com 403.

    **Exceção de DEV:** com `sss_env = DEV`, a origem do próprio `Host` da requisição também é aceita, para permitir o acesso por `localhost`, por IP ou por túnel SSH sem editar `allowed_origins`. Em HML e PROD, vale só a lista configurada.
* **Revalidação a cada requisição:** uma única query por PK junta `tbsss_usuarios` e `tbsss_perfis` e verifica `usuario.ativo`, `perfil.ativo`, `perfil.perm_versao` e `usuario.sessao_epoch` (CR-008, E2), além da vida máxima da sessão.
  * Se a versão divergir da sessão, as permissões são recarregadas. O mesmo acontece quando o `perfil_id` do usuário difere do gravado na sessão.
  * Se o usuário ou o perfil estiver inativo, a sessão é encerrada e auditada como `LOGOUT`, com o detalhe `sessão encerrada pela revalidação: <usuário inativo | perfil inativo>`.
  * A revalidação **não** considera `bloqueado_ate`: o bloqueio só impede novos logins. Uma sessão aberta continua válida até expirar (inatividade ou vida máxima), até a revogação por `sessao_epoch` (logout, troca ou redefinição de senha, desativação ou troca de perfil) ou até o perfil ser desativado.
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
  * **Redefinir senha** (administrador, `CAD_USUARIOS`): aplica a política com confirmação, zera `tentativas_falha` e `bloqueado_ate` e incrementa `sessao_epoch` (as sessões abertas do alvo caem, CR-008 E2). A auditoria é `CAD_ALTERAR` com detalhe `senha redefinida`, sem o valor. Não existe "trocar no próximo login". A senha de um **administrador** só é redefinida por outro administrador (CR-008, E1).
  * **Desbloquear:** zera tentativas e bloqueio, com auditoria `CAD_ALTERAR`. A ação é auditada mesmo quando a conta não estava bloqueada.
  * **Nova senha igual à atual:** é aceita em todas as telas. Não há histórico de senhas.
  * **Minha senha** (`default/minha_senha`, qualquer usuário logado):
    * exige a senha atual. Uma senha atual errada **conta como falha de login**, com o mesmo limite e bloqueio do item "Proteções do login" e auditoria `LOGIN_FALHA`;
    * se a conta for bloqueada, a sessão é encerrada;
    * no sucesso, `sessao_epoch` é incrementado (as outras sessões do usuário caem, CR-008 E2), a sessão atual é renovada (`session.renew()`, com novo token CSRF e o novo `sessao_epoch`) e a troca é auditada (`CAD_ALTERAR`, "senha alterada pelo próprio usuário").
  * **Autoproteção:** pela administração, o usuário logado não pode:
    * desativar a si mesmo;
    * trocar o próprio perfil administrativo por um não administrativo;
    * sem ser administrador, trocar o próprio perfil por qualquer outro (mudaria as próprias permissões; CR-008 E1, revisão de 2026-10-20). A recusa usa a mensagem "Só um administrador pode … mudar o seu próprio perfil";
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
* **`RepoCatalogo.scripts_executaveis` no Oracle (F7.3, CATALOGO):** uma única consulta.
  * O não administrador precisa de `EXEC_SCRIPT` no contexto. A matriz é lida do banco pelo `perfil_id` do contexto, com `EXISTS` sobre `tbsss_perfil_scr` e `tbsss_perfil_amb`, e não pelos conjuntos `ambientes`/`scripts` do contexto.
  * O administrador dispensa as dimensões 1 a 3, mas não a homologação em ambiente ativo.
  * O resultado é o mesmo do FAKE quando o contexto está atualizado (`perm_versao`). Ele continua sendo só a lista de candidatos: a decisão por ambiente segue em `rbac.pode_executar`.
* **`perm_versao`:** qualquer alteração em perfil, na matriz do perfil, em `is_admin` ou em `ativo` incrementa `tbsss_perfis.perm_versao` **na mesma transação**.
  * Desativar um usuário ou trocar o perfil dele também incrementa o `perm_versao` dos perfis de origem e de destino. Por isso, uma edição de matriz aberta ao mesmo tempo nesses perfis recebe a mensagem de conflito e precisa ser recarregada.
* **Administrador só por administrador (CR-008, E1/R-05):** quem tem `CAD_USUARIOS` ou `CAD_PERFIS` sem ser administrador **não** pode:
  * incluir um usuário num perfil administrativo nem mover alguém (inclusive a si) para um perfil administrativo;
  * redefinir a senha, desbloquear, desativar ou trocar o perfil de um usuário que esteja num perfil administrativo;
  * marcar ou desmarcar `is_admin` em qualquer perfil, incluir perfil com `is_admin = 'S'` ou alterar um perfil administrativo (dados, matriz, ativação);
  * alterar a matriz (funcionalidades, ambientes, scripts) ou a ativação do **próprio** perfil.

  A checagem é do service, sobre os dados lidos do repositório (nunca do formulário), antes de gravar. A recusa usa a mensagem-padrão "Só administrador" do §2.4.2 (usuários ou perfis), sem gravar nem auditar (como as autoproteções); é registrada no log (WARN, `acao = CAD_ALTERAR`, com o login e a regra). O formulário mostra a mensagem no topo e mantém os dados digitados. A lista de perfis do formulário de usuários, para quem não é administrador, não oferece perfis administrativos.

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

#### D.1 Perfis e Usuários Padrão Homologados (Seed Inicial)

O processo de inicialização do banco (`init_db.py` e script SQL de implantação) cadastra de forma idempotente a matriz operacional inicial e os usuários para demonstração e homologação das telas (UI Freeze):

1. **Perfis de Acesso (`tbsss_perfis`):**
   * **`ADMINISTRADOR`:** Super Administrador (`is_admin = 'S'`). Acesso total a todas as 10 funcionalidades, a todos os ambientes atendidos e a todas as rotinas homologadas.
   * **`OPERADOR_PROD`:** Operacional de Produção (`is_admin = 'N'`). Acesso a `EXEC_SCRIPT`, `VER_LOGS` e `CANC_TICKET` em todos os ambientes operacionais (`CLONE2`, `CLONE1`, `CLONE6`, `CLONE7`, `GFPREPROD`).
   * **`OPERADOR_HML`:** Operacional de Homologação (`is_admin = 'N'`). Acesso a `EXEC_SCRIPT`, `VER_LOGS` e `CANC_TICKET` restrito aos ambientes de teste e validação (`CLONE6`, `CLONE7`, `GFPREPROD`).
   * **`CONSULTA`:** Auditoria e Consulta (`is_admin = 'N'`). Perfil de somente leitura, restrito a `VER_LOGS` em todos os ambientes, sem permissão de disparo ou alteração de cadastros.

2. **Usuários Padrão Homologados (`tbsss_usuarios`):**
   * **`admin`** (`Super Administrador`): vinculado ao perfil `ADMINISTRADOR`.
   * **`op.prod`** (`Operador Producao`): vinculado ao perfil `OPERADOR_PROD`.
   * **`op.hml`** (`Operador Homologacao`): vinculado ao perfil `OPERADOR_HML`.
   * **`consulta`** (`Auditor e Consulta`): vinculado ao perfil `CONSULTA`.
   * **Credencial Inicial de Homologação:** senha `Sss@Homolog2026!` (hash PBKDF2-SHA256, 200k iterações: `pbkdf2_sha256$200000$f9fb31dc39b754d083af236a880dfa6e$2229f3f8a694a9c45be82d9c3bd38110f8b474d2a0aa0ee7f691d405738a4cd8`).
   * **Idempotência:** o `MERGE` do seed atualiza nome e perfil de acesso, mas preserva a senha existente caso tenha sido redefinida pelo operador.

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

* login (OK, falha, bloqueio) e logout (o logout também revoga as sessões do usuário, §4.2, CR-008 E2);
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
| `PURGE` | tabela purgada (`tbsss_tickets` ou `tbsss_auditoria`), uma linha por tabela, **sempre** que a execução obtém a concessão, mesmo com 0 linhas apagadas (CR-008, R-16) | nulo |
| `ESQUEMA_MIGRAR` (CR-007, D4) | `tbsss_controle` | `1` (a linha de controle) |
| `AUD_EXPORTAR` | `tbsss_auditoria` | nulo |

  O filtro "Entidade" da consulta oferece exatamente as tabelas acima.
* **Atores do sistema:** `SYSTEM:<agent_id>` (agente), `SYSTEM:init_db` (`init_db.py`), `SYSTEM:purge` (`purge.py`) e `SYSTEM:seed` (seed FAKE). Por isso `init_db`, `seed` e `purge` não podem ser `agent_id` (§8.12).
* **Trilha protegida (CR-007, D1b):** as contas web e agente só têm `SELECT`/`INSERT` em `tbsss_auditoria` (o agente, só `INSERT`); só a conta de purge apaga, por retenção (§11.3). Nenhuma conta de aplicação a altera.
* **Limites da coluna:** `ator` tem até 40 caracteres e é obrigatório (nunca é preenchido com um valor padrão). `detalhe` é cortado em 1.000 caracteres, com `...` no final. O FAKE recusa a gravação fora desses limites, como o Oracle.
* **Colunas de registro (CR-006):** cada tabela guarda só quem criou o registro e quem fez a **última** alteração de negócio (§10), com o mesmo ator da linha de auditoria e na mesma transação. O histórico completo fica aqui, dentro de `audit_retention_days`; as colunas de registro não são purgadas.

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
| `PENDING` | Na fila. Pode ser reservado (claim) quando `scheduled_at <= SYSDATE`; antes disso, está agendado para o futuro |
| `RUNNING` | Reservado e em execução no agente dono |
| `SUCCESS` | Encerrado com código 0 |
| `FAILED` | Erro, timeout, falha de pré-validação, nó offline, órfão etc. |
| `CANCELLED` | Interrompido por solicitação explícita |

| Transição | Executor | Condição SQL obrigatória |
|---|---|---|
| `PENDING → RUNNING` | Agente (claim) | `WHERE status = 'PENDING' AND cancel_requested = 'N'` |
| `PENDING → CANCELLED` | Web | `WHERE status = 'PENDING'` |
| `RUNNING → SUCCESS / FAILED / CANCELLED` | Agente dono | `WHERE status = 'RUNNING' AND agente_id = :agente_id` |
| `RUNNING → FAILED (NODE_OFFLINE)` | Qualquer outro agente | `heartbeat_at` defasado (§8.8) |
| `RUNNING → PENDING` (devolução, CR-007, R-03) | Agente dono | `WHERE status = 'RUNNING' AND agente_id = :agente_id AND process_id IS NULL AND cancel_requested = 'N'`, e só quando o script nunca foi iniciado: sem `.sss_proc` **e** sem `.sss_spawn` (§8.7; CR-008, R-01 e R-02), e por erro de rede ou prazo do banco (CR-008, R-07). Limpa `agente_id`, `started_at`, `heartbeat_at` e `log_output` |
| `RUNNING → CANCELLED` (devolução com cancelamento pedido, CR-008, R-02) | Agente dono | Mesmas condições da devolução, mas com `cancel_requested = 'S'`: em vez de voltar à fila, o ticket é finalizado `CANCELLED`/`CANCEL_USER`/`-1`, com `finished_at = SYSDATE` e `updated_by = 'SYSTEM:<agent_id>'` |

Os estados `SUCCESS`, `FAILED` e `CANCELLED` são **terminais e imutáveis**. Toda transição é um `UPDATE` condicional. Se `rowcount = 0`, a transição perdeu a corrida e o código deve tratar o caso, nunca ignorá-lo.

* **Sem retentativa automática (CR-007, R-18):** um ticket encerrado com falha (inclusive `NODE_OFFLINE`, `FENCED`, `ORPHAN_PROCESS` e `SHUTDOWN`) nunca é executado de novo sozinho. Ele roda outra vez só por reexecução (§5.5) ou, se veio de um agendamento, na próxima ocorrência da regra. A única volta à fila é a devolução acima, quando o script não chegou a ser iniciado.

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
* **Motivo técnico no log (CR-007, R-18):** antes de gravar `PRECHECK_FAILED` ou `SPAWN_ERROR`, o agente anexa ao `log_output` a linha `[SSS] pré-validação recusada: <código> (agente <agent_id>)` ou `[SSS] falha ao iniciar: <classe do erro> (agente <agent_id>)`, sem o caminho do arquivo. Códigos da pré-validação: os do `path_guard` (§8.5), `VERSAO_NAO_SUPORTADA`, `INTERPRETADOR_NAO_DISPONIVEL`, `SCRIPT_INATIVO`, `NAO_HOMOLOGADO`, `AMBIENTE_INATIVO`, `SEM_PERMISSAO` e `CADASTRO_MUDOU`. O mesmo vale para as finalizações pelo startup check, com `[SSS] <motivo>: <detalhe>`.

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
| `PRECHECK_FAILED` | "O script não pôde começar: o arquivo, o cadastro ou a permissão não estavam liberados na hora de rodar." | "Veja o motivo no fim do log e avise o administrador com o número deste ticket." |
| `SPAWN_ERROR` | "O servidor não conseguiu iniciar o script." | "Avise o administrador com o número deste ticket." |
| `LOG_LIMIT` | "O script escreveu mensagens demais e foi parado, para não lotar o disco." | "Avise o responsável pelo script." |
| `SHUTDOWN` | "O servidor foi desligado enquanto o script rodava." | "Tente de novo." |
| `CANCEL_USER` | "A execução foi cancelada a pedido." | — |
| Motivo desconhecido | "Terminou com um motivo que o sistema não conhece ({código})." | "Avise o suporte com o número deste ticket." |

O catálogo fica num único lugar do código (`ui_helpers.py`), consumido pelas views e testado por `test_ui_helpers.py`. Os textos técnicos atuais de `descricao_motivo` continuam existindo para o suporte e aparecem no detalhe como "Detalhe técnico".

### 5.3 Prioridade

* Escala de **1 (mais alta) a 4 (mais baixa)**, padrão 2.
* Prioridade 1 é reservada a perfis admin. No desdobro, se o responsável pela regra deixou de ser admin, o ticket sai com prioridade 2 (§7.5, passo 2).
* A fila ordena pela **prioridade efetiva**, depois `scheduled_at` e depois `id` (§8.2).
* **Envelhecimento (CR-007, R-07):** a prioridade efetiva é `GREATEST(1, prioridade − FLOOR(minutos na fila / fila_envelhecimento_min))`, com os minutos contados desde `GREATEST(scheduled_at, created_at)` (CR-008, R-20): um ticket criado já vencido (desdobro atrasado, R-27 do CR-007, ou disparo com horário passado na fila) não herda a idade da ocorrência e não passa à frente de quem já esperava. Com `fila_envelhecimento_min = 60`, um ticket de prioridade 4 chega a 1 depois de 3 horas na fila; com `0`, o envelhecimento fica desligado. A prioridade gravada no ticket não muda.

### 5.4 Criação manual de ticket (transação única)

1. Validar o CSRF e `rbac.pode_executar(usuario, script_id, ambiente)`.
2. Carregar o vínculo `tbsss_script_param` + `tbsss_parametros` (ativos) do script.
3. Validar as respostas e compilar o snapshot (§6). Em caso de erro, retornar o erro por campo, sem gravar nada.
4. Gravar o `scheduled_at` informado (opcional, padrão `SYSDATE`).
   * Ele deve ser `>= SYSDATE` **exato**, sem tolerância de minuto: um horário no minuto corrente, mas anterior ao `SYSDATE`, é recusado.
   * O limite superior é `SYSDATE + 366` dias (CR-007, D2). Acima disso, o campo é recusado: "Escolha uma data até {data}."
   * O valor digitado no campo de data e hora do navegador é interpretado como horário de parede do servidor Oracle (§7.1). A tela informa isso ao lado do campo.
5. `INSERT INTO tbsss_tickets (...) VALUES (...) RETURNING id INTO :out_id`, com `parametros_enviados` contendo o JSON do snapshot, `created_at = SYSDATE` e `created_by` = login do solicitante (§10, CR-006).
6. `INSERT` em `tbsss_ticket_resp` via `executemany`, com os valores **resolvidos** (após a precedência) e o mesmo `created_by` do ticket.
7. Auditoria `TICKET_CRIAR` e `COMMIT`. Em qualquer exceção, `ROLLBACK`.

* **Caminho do script na criação (CR-005, D4):** o nó web valida `path_file` conforme a §8.5 ("Validação no nó web"). O formato e as pastas do sistema são conferidos sempre. Se o arquivo existe no nó web, as checagens de dono e permissão também rodam e bloqueiam a criação. Se não existe ali, o ticket é criado e a validação definitiva fica no claim (§8.4).
* **`ticket_resp`:** respostas sem valor (`None`) não são gravadas. `CHECKBOX` é gravado como `"true"`/`"false"`.
* **O contexto é conferido de novo na execução (CR-007, D2):** se, até o claim, o solicitante perder a permissão, o usuário ou o perfil forem desativados, ou o ambiente for desativado, o agente recusa com `PRECHECK_FAILED` e o subcódigo `SEM_PERMISSAO` ou `AMBIENTE_INATIVO` (§8.4). O ticket agendado para o futuro não "guarda" a permissão da época da criação.

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

  **Montagem do texto de ajuda** de cada campo, nesta ordem e em frases separadas: a `descricao` do parâmetro, o exemplo do tipo e, por último, uma destas frases (só uma):
  * campo sensível com valor já salvo (edição de agendamento): "Valor sigiloso já salvo (não exibido): deixe em branco para manter o valor atual.";
  * campo sensível com padrão configurado: "Valor sigiloso: deixe em branco para usar o padrão configurado." (vale a precedência da §6.1);
  * campo com padrão não sensível: "Padrão: {valor}.".

  Se a `descricao` não terminar em ponto, interrogação ou exclamação e vier alguma frase depois dela, o servidor acrescenta o ponto, para que as frases não fiquem grudadas.
* **Resumo em frase antes de confirmar:** o modal de confirmação abre com uma frase montada pelo servidor:

  > "Vamos rodar **{script}** no ambiente **{ambiente}** {agora | em {data} às {hora}}, com prioridade {n}. Respostas: {rótulo} = {valor}; …"

  * valores sensíveis aparecem como `****`;
  * respostas vazias aparecem como "(sem resposta)";
  * o comando lógico (argv, §6.4) continua no modal, abaixo da frase, com o título "Comando que será executado".
* **"Usar as respostas da minha última execução":** o botão aparece na etapa 3 quando existe um ticket **do próprio usuário** para o mesmo script e o mesmo ambiente. Ele usa `listar` com os filtros `solicitante`, `script_id` e `ambiente`, `tamanho=1`, e depois `respostas`, sem método novo no contrato.
  * Preenche só as respostas **não sensíveis**; os campos sensíveis ficam vazios, com a nota "Por segurança, digite de novo." no início do texto de ajuda.
  * Uma resposta que não vale mais no catálogo atual (opção removida, formato novo) fica vazia, com o aviso "esta resposta mudou desde a última vez".
  * Nada é gravado até a confirmação, que segue o fluxo normal (§5.4).
* **Aviso de horário:** ao lado do campo de agendamento aparece "Horário do servidor do banco de dados" (§5.4, passo 4).

### 5.5 Reexecução

* Cria um novo ticket com `parent_ticket_id = <original>` e `created_by` = login de quem reexecutou, que também é o `solicitante` (§10, CR-006).
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
   SET cancel_requested = 'S',
       updated_at = SYSDATE, updated_by = :ator
 WHERE id = :id AND status IN ('PENDING', 'RUNNING') AND cancel_requested = 'N';

UPDATE {owner}.tbsss_tickets
   SET status = 'CANCELLED', status_motivo = 'CANCEL_USER',
       return_code = -1, finished_at = SYSDATE,
       updated_at = SYSDATE, updated_by = :ator
 WHERE id = :id AND status = 'PENDING';
```

* `:ator` é o login de quem pediu o cancelamento (§10, CR-006).

* Se o primeiro `UPDATE` afetar 0 linhas, o ticket já é terminal **ou** o cancelamento já tinha sido pedido. Para saber qual, a mesma transação lê a linha pela PK (`SELECT status, cancel_requested FROM {owner}.tbsss_tickets WHERE id = :id FOR UPDATE WAIT 5`): terminal dá `sem efeito: ticket encerrado`; `RUNNING` com `cancel_requested = 'S'` dá `já sinalizado`. O sistema informa o usuário nos dois casos.
* Se o segundo afetar 0 linhas, o ticket está `RUNNING` e o agente dono trata o cancelamento.
* **`PENDING` com `cancel_requested = 'S'` (CR-008, R-02):** é um resíduo (ex.: ticket devolvido por versão anterior do agente). A leitura pela PK o identifica, e o segundo `UPDATE` o cancela na mesma transação, com o resultado `cancelado`. O agente nunca o reserva (o claim exige `'N'`).
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

1. Iniciar o encerramento do grupo pela máquina de estados do §8.7 (CR-007, R-02 e R-04): `sinalizar_grupo(execucao, SIGTERM)` pela camada de plataforma (§8.0; fora de DEV, pelo helper `term`), **sem esperar** no laço.
2. Nos ciclos seguintes, conferir com `coletar` (`Popen.poll()`); passado `kill_grace_s` sem o processo terminar, `sinalizar_grupo(execucao, SIGKILL)` (helper `kill`). Nunca `Popen.wait()` bloqueante (AGENTS §3.2).
3. Com o processo coletado, encerrar o restante do grupo (R-02 do CR-007) e gravar `.sss_result` antes do `UPDATE` (§8.7).
4. Fazer o flush final do log (§8.10).
5. `UPDATE ... SET status = 'CANCELLED', status_motivo = 'CANCEL_USER', return_code = -1, finished_at = SYSDATE, updated_at = SYSDATE, updated_by = :ator WHERE id = :id AND agente_id = :agente_id AND status = 'RUNNING'`, com `:ator = 'SYSTEM:<agent_id>'`, seguido de `COMMIT`.

Se o processo terminou sozinho **antes** de o agente sinalizá-lo, prevalece o resultado real (`SUCCESS` ou `FAILED`).

`ProcessLookupError` no `killpg` (DEV) ou `ESRCH` no helper é tratado como "grupo já encerrado". O detalhe da escalada, do `.sss_result` e da finalização pendente está no §8.7, que prevalece (CR-008, R-26).

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
3. Depois disso vêm, como hoje: resumo, linha do tempo, comando executado, respostas, reexecuções e log. A linha "Detalhe técnico" do resumo traz o status, o `status_motivo`, o `return_code` e a descrição técnica (`descricao_motivo`). O bloco do snapshot mostra o **arquivo do script** (`path_file`, snapshot v4), com o caminho completo para todos (CR-005, D8). Logo depois do resumo vem o quadro **Registro** (§10, CR-006): quem criou o pedido e quando, e a última alteração, que normalmente é a última mudança de situação feita pelo agente.
4. **Botões com o efeito escrito:** "Cancelar este pedido" (com a consequência no modal) e "Rodar de novo com as mesmas respostas" (reexecução, §5.5).
5. A página continua se atualizando sozinha enquanto o ticket não termina, e a frase e a barra acompanham. Quando o polling do log (§8.10) recebe uma situação diferente da que a página mostrou ao abrir, o visualizador para, mostra "A situação mudou; atualizando a página…" e recarrega a página após 1,5 s.

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
  * **gráfico de barras por dia**, empilhado por situação, como SVG gerado no servidor (`ui_helpers.barras_empilhadas`). As cores vêm por classe CSS e não há `style=` inline:
    * quatro séries, sempre na mesma ordem e com a mesma cor: Deu certo, Deu erro, Cancelado e Esperando ou rodando;
    * as cores são tokens de `static/css/sss.css`, com valores próprios para o modo escuro:

      | Token | Série | Claro | Escuro |
      |---|---|---|---|
      | `--sss-graf-certo` | Deu certo | `#4daf9a` | `#4daf9a` |
      | `--sss-graf-erro` | Deu erro | `#ef4444` | `#ef4444` |
      | `--sss-graf-cancelado` | Cancelado | `#9ca3af` | `#8b939f` |
      | `--sss-graf-andamento` | Esperando ou rodando | `#831fb2` | `#b56ee0` |

    * a cor nunca é a única pista: a **legenda** com o nome das séries fica sempre acima do gráfico; cada segmento tem um `<title>` com dia, série e quantidade, que aparece ao passar o mouse; e a mesma informação está na tabela "Ver os números em tabela" (`<details>`), logo abaixo, que também serve aos leitores de tela;
    * um vão de 2 px separa os segmentos; o eixo vertical tem linhas de grade discretas;
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
3. o resultado não pode conter NUL nem caracteres de controle `\x00-\x1f` e `\x7f`. Um controle que estava só nas pontas já foi removido no passo 1 e não causa rejeição;
4. em parâmetro **sensível**, o valor não vazio tem pelo menos 4 caracteres (CR-007, R-25): valores mais curtos não podem ser mascarados com segurança (§4.1). Mensagem: "O valor sigiloso precisa ter pelo menos 4 caracteres." Vale para respostas, `valor_padrao` e `valor_padrao_sub`.

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
* **Subconjunto seguro (CR-007, D5).** O Python 3.6 não tem timeout de regex, e a regex roda também no desdobro do agente (§7.5), que faz uma coisa por vez. Por isso, `params_compiler.validar_regex_cadastro` recusa, com a regra violada na mensagem:
  * grupo seguido de quantificador, exceto `?` (por exemplo, `(ab)+`, `(a|b)*`, `(\d{2}){3}`);
  * quantificador logo depois de outro quantificador (`a{2}{3}`, `a**`); o modificador preguiçoso `?` (`a+?`) é permitido;
  * referência a grupo (`\1`, `(?P=nome)`), lookahead e lookbehind (`(?=`, `(?!`, `(?<=`, `(?<!`) e grupo condicional (`(?(`);
  * mais de 2 quantificadores ilimitados (`*`, `+`, `{n,}`) no padrão inteiro;
  * mais de 6 quantificadores que criam escolha (`?`, `*`, `+`, `{m,n}` com `m ≠ n`, `{n,}`); `{n}` não cria escolha (por exemplo, `a?a?a?a?a?a?a?aaaaaaa` é recusado);
  * padrão com mais de 150 caracteres (tamanho da coluna);
  * **quantificadores limitados largos (CR-008, R-06):** `{m,n}` com `n − m > 10` conta como **ilimitado** (entra no limite de 2 acima); e, se houver algum quantificador ilimitado, o limite de quantificadores que criam escolha cai de 6 para **4**. Sem isso, `\w{0,100}` ×5 + `x` passava e levava 8,6 s com 200 caracteres, e `\w*\w*` + 6 × `\w{0,10}` + `x` levava 23 s com 100.

  Exemplos aceitos: `^[A-Z]{2}\d{6}$`, `^\d{3}\.\d{3}\.\d{3}-\d{2}$`, `^(PF|PJ)$`, `^\d+(\.\d{1,2})?$`, `^[\w.]+@[\w.]+$`, `^\w{0,10}$`. Recusados: `(a|a)*b`, `^(\w|\d)+$`, `(a+)+`, `\w{0,100}\w{0,100}\w{0,100}x` (3 ilimitados), `\w*\w{0,10}\w{0,10}\w{0,10}\w{0,10}\w?x` (6 escolhas com ilimitado). Com essas regras, o `fullmatch` no tamanho máximo do valor (500 caracteres) fica abaixo de 0,2 s no pior caso medido no Python 3.6.8; a promessa anterior, "no máximo quadrático", não valia para quantificadores limitados largos (auditoria final, F-06). Uma regex gravada antes do CR-007 que não atenda continua valendo até a próxima gravação do parâmetro, que exige a correção; o `init_db`/migração não a altera.
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
  * **`sensivel` nunca volta de `S` para `N`** (CR-007, R-20): respostas já gravadas em tickets (`tbsss_ticket_resp`, snapshots) e agendamentos (`parametros_json`), além dos padrões, passariam a aparecer em claro. A mensagem orienta: "Um parâmetro sigiloso não pode deixar de ser sigiloso. Se o dado não for mais sigiloso, crie outro parâmetro." Trocar de `N` para `S` é sempre permitido.
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

O catálogo guarda um **interpretador lógico** (CR-001, D1). O nó web compila apenas os **argumentos** (`args`). O **agente** monta o `argv` real no claim, com o executável **dele**:

```text
PYTHON3    -> [<exe PYTHON3>, "-I", <script_real>, ...args]
BASH       -> [<exe BASH>, <script_real>, ...args]
SH         -> [<exe SH>, <script_real>, ...args]
```

* `<exe X>` vem de `[agent] interpretadores` do agente (§12.1).
* `<script_real>` é o `realpath` de `path_file`, o caminho absoluto cadastrado (CR-005, D2), conferido pelo `path_guard` do agente (§8.5).
* A UI mostra o `argv` **lógico**, por exemplo `PYTHON3 -I /opt/automacoes/scripts/carga.py --data 2026-10-13`, com o caminho completo para todos (CR-005, D8).
* Fora de DEV, o `argv` é executado pelo helper com o usuário de execução do ambiente (§8.0, §8.4); o `argv` em si não muda.

### 6.5 Snapshot imutável (`tbsss_tickets.parametros_enviados`)

JSON serializado com `json.dumps(obj, ensure_ascii=False, sort_keys=True)`:

```json
{
  "versao": 4,
  "script_id": 12,
  "script_nome": "carga_faturas",
  "interpretador": "PYTHON3",
  "path_file": "/opt/automacoes/scripts/faturamento/carga_faturas.py",
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
* **Versão 3 (CR-003, várias pastas base):** acrescentava `pasta_base`, o nome lógico da pasta onde o script ficava.
* **Versão 4 (CR-005, caminho livre):** sai `pasta_base`; `path_file` é o caminho **absoluto** cadastrado. O agente o confere pelo `path_guard` local (§8.5) e monta o `argv` (§6.4, §8.4). O executável do interpretador continua fora do snapshot.
* Snapshots das versões 1 a 3 foram gerados apenas em DEV/FAKE e não são aceitos pelo agente. O claim os rejeita com `PRECHECK_FAILED`.

* O snapshot é **compilado na criação do ticket** (manual ou desdobro). O agente **nunca** recompila nem lê `tbsss_script_param` e `tbsss_parametros` para executar.
* **Defesa em profundidade no claim:** o agente revalida o snapshot (§8.4, passo 1).
* **Snapshot × cadastro (CR-007, R-24):** se `path_file` ou `interpretador` do snapshot diferirem do cadastro atual do script, o agente recusa (`CADASTRO_MUDOU`): o ticket foi criado antes de uma mudança de cadastro e deve ser reexecutado, para ser compilado de novo.
* **Conteúdo do arquivo (CR-011):** o SSS não guarda nem confere hash do arquivo; o ambiente controla o conteúdo e a versão do script (§8.5).
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
  * Ficam mascarados na UI, nos logs do daemon e no `log_output`, pelo mascarador do próprio ticket (§8.10).
  * No `argv` exibido, todo token igual a um valor sensível do ticket vira `****`, mesmo que apareça em outro parâmetro. Na dúvida, o sistema prefere mascarar a mais.
  * **Continuam visíveis em `ps` no servidor e no banco.** Por isso, é **proibido** cadastrar parâmetro destinado a senha ou credencial, que deve vir do ambiente (§8.6).

---

## 7. Agendamentos Recorrentes (`tbsss_agendamentos`)

### 7.1 Base de tempo

* Todo cálculo usa o **horário de parede do servidor Oracle**. O daemon obtém o instante atual com `SELECT SYSDATE FROM DUAL` e **nunca** usa `datetime.now()` para agendamento.
* Datas são `datetime` *naive*, sem microssegundos.
* **Horário de verão:**
  * Semântica de parede: um horário inexistente (avanço do relógio) é tratado pela regra de *misfire* (§7.4). Com `RUN_ONCE`, executa uma vez, com WARN se o avanço passar de `misfire_tolerance_s`. Com `SKIP` e avanço acima da tolerância, a ocorrência é **perdida** (CR-007, D3).
  * No horário duplicado (recuo do relógio), não há reexecução, porque `proxima_execucao` já aponta para a próxima ocorrência.
  * O fuso do servidor de banco é a referência oficial.
* **Pré-requisito operacional (CR-007, D3):** o servidor de banco (todas as instâncias, inclusive no RAC e no Data Guard) usa um fuso **sem horário de verão** (UTC recomendado) e NTP em modo *slew*, sem saltos. Mesmo assim, o agente detecta saltos do `SYSDATE` e suspende a detecção de nó offline (§8.8), e a subida registra WARN se o `SYSDATE` divergir do relógio local em mais de 60 s (§8.12).

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
* O cálculo da próxima ocorrência é feito campo a campo, não minuto a minuto, com horizonte de `cron_horizon_days` (mínimo 1461, para cobrir regras de 29/02, que ocorrem a cada 4 anos; CR-008, R-32; o mínimo anterior, 366, aceitava `0 0 29 2 *` no cadastro e pausava a regra no primeiro desdobro. Igual em todos os agentes e no web, §8.12 e §12.1). Uma expressão sem ocorrência no horizonte é rejeitada no cadastro e pausa a regra (`CRON_INVALIDO`) no desdobro.
  * O horizonte é contado a partir do instante de referência da busca: `data_inicio` no cadastro e na prévia, e o "agora" do banco no desdobro.
  * **Exceção:** se `data_fim` cair dentro do horizonte, a falta de ocorrência significa que a regra terminou (`CONCLUIDO`), não que a expressão é inválida. No cadastro, a mensagem é a de "sem próxima execução", e não a de expressão sem ocorrência (CR-007, R-32).
* O passo exige `*` ou intervalo (`*/5`, `0-30/5`). A forma `a/n` é rejeitada, e a expressão tem no máximo 60 caracteres.
* `CronExpr.descrever()` gera a descrição em português exibida na UI. Exemplos:
  * `30 2 * * 1-5` → "às 02:30, de segunda a sexta";
  * `*/15 * * * *` → "a cada 15 minutos";
  * `0 0 1 * 1` → "às 00:00, no dia 1 de cada mês ou às segundas";
  * passo no dia do mês: `0 0 */2 * *` → "às 00:00, a cada 2 dias a partir do dia 1"; `0 0 */2 * 1` → "às 00:00, a cada 2 dias a partir do dia 1, quando cair numa segunda". A descrição não repete "de cada mês" e não usa "nos dias do mês a cada".

### 7.4 Política de *misfire*

O atraso é medido pela ocorrência vencida **mais recente** (CR-008, R-21): `atraso = agora − última vencida`. Se `atraso > misfire_tolerance_s` (por exemplo, após um downtime longo):

| `misfire_policy` | Comportamento |
|---|---|
| `RUN_ONCE` (padrão) | Gera **um** ticket, coalescendo as ocorrências perdidas |
| `SKIP` | Não gera ticket |

Com `atraso ≤ misfire_tolerance_s`, as duas políticas geram **um** ticket para a vencida mais recente, e as anteriores contam como perdidas (ex.: CRON `*/5`, `proxima_execucao` 10:00, agora 10:06, tolerância 300 s: gera o ticket das 10:05 e registra 1 perdida; antes do CR-008, `SKIP` media pela de 10:00 e descartava as duas).

Nos dois casos, `proxima_execucao` recebe a **primeira ocorrência futura** maior que `SYSDATE`. O número de ocorrências perdidas vai para o log:

* em **WARN** quando a vencida **mais antiga** (`proxima_execucao`) passa de `misfire_tolerance_s` (houve misfire de verdade, mesmo que a mais recente esteja na tolerância);
* em **INFO** quando há ocorrências coalescidas **dentro** da tolerância (por exemplo, CRON a cada minuto com o daemon 4 minutos atrasado gera 1 ticket e 4 perdidas em INFO).

**Contrato de `recurrence.avaliar_disparo(regra, agora, misfire_policy, misfire_tolerance_s)`** (decisões do F5.1). A função devolve `Decisao(gerar_ticket, nova_data, perdidas, concluir, ocorrencia, cron_erro)`; `cron_erro` tem padrão `False` (CR-008, R-19):

* **Vencidas** são as ocorrências em `[proxima_execucao, agora]`, contando a própria `proxima_execucao`.
* **Atraso dentro da tolerância** (`agora − última vencida ≤ misfire_tolerance_s`, CR-008 R-21): gera **um** ticket para a vencida mais recente, mesmo que várias tenham vencido e mesmo com `SKIP`. Exemplo: CRON a cada minuto com o daemon 4 minutos atrasado.
* **`perdidas`:**
  * `vencidas − 1` quando há ticket (o ticket cobre a ocorrência mais recente);
  * todas as vencidas com `SKIP` fora da tolerância;
  * limitada a 10.000.
  * Exemplo: `DIARIA` com 3 dias de downtime e `RUN_ONCE` gera 1 ticket e 3 perdidas.
* **`nova_data`:** sempre a primeira ocorrência maior que `agora`, respeitando piso e teto. É `None` quando a regra terminou.
* **`concluir`:**
  * `UNICA` depois da decisão. No passado, `RUN_ONCE` dispara uma vez e conclui; `SKIP` fora da tolerância conclui sem ticket.
  * Ou quando não há próxima ocorrência até `data_fim`. Nesse caso, o ticket da ocorrência atual ainda é gerado.
* **`ocorrencia` (CR-007, R-27):** quando `gerar_ticket`, a ocorrência coberta pelo ticket (a vencida mais recente, nunca no futuro); senão `None`. O desdobro a grava como `scheduled_at` do ticket (§7.5).
* **Conclusão sem ticket:** sempre que `gerar_ticket = False` e `concluir = True`. Exemplos: `UNICA` com `SKIP` fora da tolerância, ou `data_fim` vencida durante uma parada com `SKIP` (CR-007, R-32).
* **Sem próxima ocorrência no horizonte (CR-008, R-19):** a expressão é válida, mas a próxima ocorrência depois de `agora` não existe em `cron_horizon_days` (e `data_fim` não explica). A função **não** lança exceção: devolve a decisão normal (`gerar_ticket`, `perdidas` e `ocorrencia` calculados pelas vencidas, como em qualquer regra) com `nova_data = None`, `concluir = False` e `cron_erro = True`. O daemon aplica os passos 4 e 5 do §7.5 normalmente e grava a pausa `CRON_INVALIDO` (§7.5, passo 6, variante `cron_erro`).
* **Expressão CRON sintaticamente inválida** (gravada por fora da validação): lança `CronErro`, sem decisão. O daemon pausa com `CRON_INVALIDO` **sem** ticket (passo 7), porque não há como calcular as vencidas.
* Os módulos `cron_parser.py` e `recurrence.py` são puros: não importam `gluon`, nunca chamam `datetime.now()` e recebem o "agora" por parâmetro.

### 7.5 Algoritmo de desdobro (ciclo 1 do daemon)

**Leitura paginada (CR-007, R-08).** A cada ciclo do orquestrador, o agente lê páginas de regras vencidas (usa `ix_tbsss_agd_prox (ativo, proxima_execucao, id)`), começando do início e continuando depois da última regra lida:

```sql
SELECT id, proxima_execucao FROM (
  SELECT id, proxima_execucao FROM {owner}.tbsss_agendamentos
   WHERE ativo = 'S' AND proxima_execucao <= SYSDATE
     AND (proxima_execucao > :ult_prox OR (proxima_execucao = :ult_prox AND id > :ult_id))
   ORDER BY proxima_execucao, id
) WHERE ROWNUM <= :lote
```

* Na primeira página, `:ult_prox` é `DATE '0001-01-01'` e `:ult_id` é `0`.
* O agente lê a página seguinte enquanto a anterior vier cheia e o tempo gasto no desdobro neste ciclo for menor que `heartbeat_interval_s / 2` (orçamento do laço, §8.1). O que sobrar fica para o ciclo seguinte, a partir do início.
* Antes de tudo, cada regra da página é travada **sem esperar**:

  ```sql
  SELECT id FROM {owner}.tbsss_agendamentos
   WHERE id = :id AND ativo = 'S' AND proxima_execucao <= SYSDATE
     FOR UPDATE SKIP LOCKED
  ```

  Sem linha, outro agente está processando a regra (ou ela já mudou): o agente passa à seguinte, sem esperar nem registrar erro. Assim, os agentes repartem as regras vencidas em vez de disputar as mesmas. `SKIP LOCKED` é aceito no 11gR2.

Para cada regra travada, na **mesma transação** (que já detém o lock da linha):

1. Ler a regra completa, guardando `antiga_data = proxima_execucao` **exatamente como retornada pelo banco**.
2. **Revalidar privilégios** do `usuario_id` com `rbac.pode_executar(usuario, script, ambiente)`. Se falhar, pausar (passo 7) com o motivo dado por `rbac.motivo_pausa(motivo_rbac)` (CR-008, R-33), função pura usada também pela web (aviso "Será pausada", §7.6), para que o daemon nunca grave um valor fora de `ck_tbsss_agd_pausa`:

   | `rbac.Motivo` | `pausa_motivo` |
   |---|---|
   | `USUARIO_INATIVO` | `USUARIO_INATIVO` |
   | `SCRIPT_INATIVO` | `SCRIPT_INATIVO` |
   | `AMBIENTE_INATIVO` | `AMBIENTE_INATIVO` |
   | `PERFIL_INATIVO`, `SEM_HOMOLOGACAO`, `SEM_FUNC`, `SEM_AMBIENTE`, `SEM_SCRIPT`, `DADO_INVALIDO` e qualquer outro | `SEM_PERMISSAO` |

   Se a regra tem prioridade 1 e o responsável deixou de ser admin, o ticket sai com prioridade 2 e o log registra WARN `PRIORIDADE_REBAIXADA`; a regra não muda.
3. Calcular a decisão com `recurrence.avaliar_disparo` (§7.4): `gerar_ticket`, `nova_data`, `perdidas`, `concluir` e `ocorrencia`. Se não houver próxima ocorrência, a conclusão vem depois do ticket deste ciclo. Decisão com `cron_erro = True` (CR-008, R-19): seguir os passos 4 e 5 como em qualquer regra (sobreposição, `SKIP` e snapshot) e, no passo 6, usar a variante `cron_erro`. `CronErro` (expressão inválida): pausar com `CRON_INVALIDO`, sem ticket (passo 7).
4. **Prevenir sobreposição:** se `ultimo_ticket_id` estiver em `PENDING` ou `RUNNING`, não gerar ticket: aplicar o **avanço sem ticket** (abaixo), registrar INFO `SKIP_OVERLAP` e encerrar a regra.
   * `ultimo_ticket_id` nulo, inexistente (purgado, §11.3) ou terminal significa **livre**.
   * Se o ticket que bloqueia foi criado há mais que o tempo máximo do script (`timeout_seg` ou `script_timeout_s`) mais `node_offline_timeout_s`, o registro é **WARN** `SKIP_OVERLAP_PRESO`, com o id do ticket: ele provavelmente está preso e precisa de atenção (CR-007, R-26). A lista e a agenda também avisam (§7.6, §7.7).
5. **Compilar o snapshot** a partir de `parametros_json`. Se for inválido, pausar com `PARAM_INVALIDO`. O `detalhe` do `AGD_PAUSAR` traz o código do parâmetro e a mensagem do erro, nunca o valor (R-26). O mesmo vale para `CRON_INVALIDO`, com a mensagem do parser.
6. Se `gerar_ticket`, obter `:ticket_id` com `SELECT sq_tbsss_tickets.NEXTVAL FROM DUAL` e aplicar a reserva otimista:

   ```sql
   UPDATE {owner}.tbsss_agendamentos
      SET proxima_execucao = :nova_data,
          ultima_execucao  = SYSDATE,
          ultimo_ticket_id = :ticket_id
    WHERE id = :id
      AND ativo = 'S'
      AND proxima_execucao = :antiga_data
   ```

   * Se `rowcount = 1`, fazer o `INSERT` do ticket com `id = :ticket_id`, `agendamento_id = :id`, `solicitante = <login do usuario_id>`, `ip_origem = NULL`, **`scheduled_at = :ocorrencia`** (a ocorrência coberta, nunca no futuro, CR-007 R-27) e a prioridade do passo 2. Em seguida, o `INSERT` em `tbsss_ticket_resp`.
   * O índice único `ix_tbsss_tck_ocor` impede um segundo ticket para a mesma ocorrência da mesma regra. A violação (ORA-00001) leva a `ROLLBACK` e WARN `OCORRENCIA_DUPLICADA`: outro caminho já gerou o ticket. Em seguida, numa **nova transação**, o agente aplica o **avanço sem ticket** (abaixo) com a mesma `:antiga_data` e a `:nova_data` da decisão (CR-008, R-31); `rowcount = 0` é ignorado. Assim, a regra não é reprocessada a cada ciclo até a próxima ocorrência.
   * Se `rowcount = 0`, outro nó processou a regra: fazer `ROLLBACK` e seguir para a próxima.
   * A trigger condicional (§10) preserva o `:ticket_id`. Valores de sequence descartados geram apenas lacunas inofensivas.
   * A reserva é rotina técnica e **não** grava `updated_*` na regra (§10, CR-006). O ticket e o `ticket_resp` nascem com `created_by = 'SYSTEM:<agent_id>'`.

   Se `gerar_ticket` for falso e a regra não concluir (por exemplo, *misfire* `SKIP` fora da tolerância), aplicar o avanço sem ticket.

   **Variante `cron_erro` (CR-008, R-19):** a reserva (com ticket) ou o avanço (sem ticket) não move `proxima_execucao`, porque não há `nova_data`; a regra é pausada no mesmo `UPDATE` otimista, que mantém `proxima_execucao` com o valor lido:

   ```sql
   UPDATE {owner}.tbsss_agendamentos
      SET ativo = 'N', pausa_motivo = 'CRON_INVALIDO',
          ultima_execucao  = CASE WHEN :ticket_id IS NULL THEN ultima_execucao ELSE SYSDATE END,
          ultimo_ticket_id = NVL(:ticket_id, ultimo_ticket_id),
          updated_at = SYSDATE, updated_by = :ator
    WHERE id = :id AND ativo = 'S' AND proxima_execucao = :antiga_data
   ```

   Com ticket, o `INSERT` do ticket e do `ticket_resp` segue como acima. Com `rowcount = 0`, `ROLLBACK` e próxima regra. A pausa é auditada como `AGD_PAUSAR` (`detalhe` com a mensagem do parser) e registrada em WARN.

   **Avanço sem ticket (CR-007, R-05)**, usado no passo 4 e no *misfire* `SKIP` sem conclusão. Não mexe em `ultima_execucao`, `ultimo_ticket_id` nem `updated_*` (rotina técnica, §10):

   ```sql
   UPDATE {owner}.tbsss_agendamentos
      SET proxima_execucao = :nova_data
    WHERE id = :id AND ativo = 'S' AND proxima_execucao = :antiga_data
   ```

   Se `rowcount = 0`, `ROLLBACK` e próxima regra.
7. **Pausa** (sempre otimista e só sobre regra **ativa**, CR-007 R-19):

   ```sql
   UPDATE {owner}.tbsss_agendamentos
      SET ativo = 'N', pausa_motivo = :motivo,
          updated_at = SYSDATE, updated_by = :ator
    WHERE id = :id AND ativo = 'S' AND proxima_execucao = :antiga_data
   ```

   `:ator` é `SYSTEM:<agent_id>` no desdobro e o login de quem pausou na pausa manual (§7.6). Com `rowcount = 0`, a regra já foi pausada ou concluída por outro caminho: `ROLLBACK`, sem auditoria.

   A pausa é registrada em `tbsss_auditoria` (`AGD_PAUSAR`) e no log em WARN.
8. `COMMIT` único. **Erro de banco (CR-008, R-22):** qualquer `DatabaseError` do contrato (rede, prazo, ORA-01653/01688 de espaço, ORA-30036, ORA-00060, ORA-04068 e outros) leva a `ROLLBACK`, WARN `DESDOBRO_ERRO_BANCO` com o código e nova tentativa no ciclo seguinte, sem pausar. O agente conta, em memória, as falhas seguidas de cada regra (zeradas no primeiro sucesso ou ao reiniciar); na **3ª** falha seguida, a regra é pausada como abaixo. **Exceção que não é de banco** (ex.: erro de programação, dado incoerente): `ROLLBACK`, log ERROR com o stack e, numa **transação separada**, pausa da regra com `ERRO_INTERNO` (passo 7, ator `SYSTEM:<agent_id>`), auditada como `AGD_PAUSAR` com a classe do erro no `detalhe` (CR-007, R-08). Se essa pausa também falhar, a regra é ignorada até o fim do ciclo. Uma regra com defeito nunca fica travando as demais no topo da leitura.

**Conclusão da regra (`concluir = True`, `nova_data = None`):**

`proxima_execucao` é `NOT NULL`, então a conclusão **não** grava `NULL`. Ela substitui os passos 6 e 7 por um **único** `UPDATE` otimista, que mantém `proxima_execucao` com o valor lido:

```sql
UPDATE {owner}.tbsss_agendamentos
   SET ativo = 'N', pausa_motivo = 'CONCLUIDO',
       ultima_execucao  = SYSDATE,
       ultimo_ticket_id = :ticket_id,
       updated_at = SYSDATE, updated_by = :ator
 WHERE id = :id
   AND ativo = 'S'
   AND proxima_execucao = :antiga_data
```

* **Com ticket** (a ocorrência atual ainda gera ticket): `:ticket_id` vem do `NEXTVAL` do passo 6. Se `rowcount = 1`, seguem o `INSERT` do ticket e o do `ticket_resp`, como no passo 6. Se `rowcount = 0`, `ROLLBACK` e próxima regra.
* **Sem ticket** (`SKIP` fora da tolerância em `UNICA`, ou sobreposição): `ultima_execucao` e `ultimo_ticket_id` **não** são alterados. O `SET` fica só com `ativo`, `pausa_motivo` e `updated_*`.
* Nos dois casos, `:ator = 'SYSTEM:<agent_id>'` (§10, CR-006).
* A conclusão é auditada como `AGD_PAUSAR`, com o detalhe `pausa_motivo: CONCLUIDO`, e registrada em INFO (não em WARN, porque não é uma falha).
* O passo 7 (pausa) não se aplica à conclusão.

**Sobreposição numa regra que conclui:** se, no passo 4, o `ultimo_ticket_id` ainda estiver `PENDING`/`RUNNING` e a decisão for `concluir = True`, a regra é concluída **sem ticket** (UPDATE acima, variante sem ticket). A ocorrência atual entra em `perdidas`, e o log registra INFO `SKIP_OVERLAP` com o total de perdidas.

**Bind de datas:**

* `:antiga_data` e `:nova_data` são declarados pelo `db_conn` com o tipo de data do driver (no Oracle, `setinputsizes` com `cx_Oracle.DATETIME` ou `oracledb.DB_TYPE_DATE`).
* Um `datetime` com microssegundos **nunca** é comparado a uma coluna `DATE`. A regra travaria silenciosamente.
* `:antiga_data` é usada **exatamente como retornada pelo banco** (passo 1), nunca recalculada nem convertida por fuso. `:nova_data` sai do `recurrence.py` já sem segundos nem microssegundos (§7.2).
* **Teste obrigatório (F7.3/F8.4):** um desdobro com `antiga_data`/`nova_data` contendo microssegundos não pode resultar em `rowcount = 0`. O tipo `DATE` declarado no bind descarta a fração.

**Contrato do repositório para o desdobro (F8.4):** `repo_oracle/scheduler_agenda.py` (processo batch, sem FAKE, §2.5) expõe operações distintas:
* a leitura paginada das regras vencidas e o lock de cada uma com `SKIP LOCKED` (SQL acima);
* a leitura completa da regra;
* a reserva otimista com a inclusão do ticket e do `ticket_resp` (passo 6), numa única operação;
* a conclusão, com e sem ticket;
* o avanço sem ticket;
* a pausa (passo 7), inclusive a pausa por `ERRO_INTERNO` numa transação separada.

Todas recebem a conexão da transação do ciclo e nunca fazem `COMMIT` sozinhas; o `COMMIT` único é do passo 8.

### 7.6 Cadastro de regras na UI (decisões do F5.2)

Implementação: `controllers/agendamentos.py`, `modules/agendamentos_service.py` e `views/agendamentos/`. O questionário de parâmetros é o mesmo do disparo (`views/components/questionario.html`).

* **Validação estrita (sem truncamento):** todo campo recebido é validado no tamanho e no formato exatos. Um valor mais longo ou fora do formato é **recusado** com mensagem no campo, nunca cortado. Exemplos: dia do mês `100` ou `311`, hora `03:000`, data com segundos ou frações (`…T10:00:00.999`).
* **Escolha de script e ambiente:** na inclusão, a escolha é feita em etapas e usa os mesmos filtros do disparo (§4.3.A): só aparecem scripts e ambientes em que o editor tem `pode_executar`. Por isso, quem não é admin precisa também de `EXEC_SCRIPT`.
* **Edição (D2):** script e ambiente ficam **fixos**. Para usar outro script ou ambiente, cria-se uma nova regra.
* **`usuario_id`:** a inclusão e a edição gravam o editor, que precisa ter `pode_executar` vigente (§10). Sem essa permissão, a operação é negada e a regra fica intacta. A tela de edição sempre avisa: "Ao salvar, esta regra passará a executar com as suas permissões." O criador original fica em `created_by`, que nunca muda (§10, CR-006).
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
* **Pausa manual:** grava `ativo = 'N'` e `pausa_motivo = 'MANUAL'`, de forma otimista sobre `proxima_execucao` e só sobre regra ativa (§7.5 passo 7), e audita `AGD_PAUSAR` com o login e o IP de quem pausou. Se a regra foi pausada ou concluída entre a leitura e o clique, a operação vira conflito, sem gravar nem auditar (CR-007, R-19).
* **Retomada:**
  * Revalida `pode_executar` de **quem retoma**, recalcula `proxima_execucao` a partir de agora, limpa `pausa_motivo` e grava `ativo = 'S'`. Audita `CAD_ALTERAR`.
  * **Reavaliação da causa (CR-007, R-26):** antes de retomar, o servidor confere o que o desdobro conferiria: responsável ativo e com `pode_executar` para o script e o ambiente, script e ambiente ativos, snapshot compilável a partir de `parametros_json` e, em `CRON`, ocorrência no horizonte. Se algo falhar, a retomada é recusada com a causa em linguagem simples e a orientação "Edite a regra para corrigir (ao salvar, ela passa a rodar com as suas permissões) e depois retome."
  * O responsável (`usuario_id`) não muda: os privilégios dele continuam sendo revalidados a cada desdobro (§7.5 passo 2).
  * Uma regra `CONCLUIDO` só é retomada se ainda houver próxima execução (D5). Pausar uma regra já pausada, ou retomar uma ativa, gera aviso sem gravar nem auditar.
* **Colunas de registro (CR-006):** a inclusão grava `created_*`; edição, pausa manual e retomada gravam `updated_*` com o login de quem agiu. O formulário de edição mostra o quadro Registro (§10).
* **Lista:**
  * Mostra as regras dos ambientes autorizados ao perfil (admin: todas). Uma regra fora do escopo é tratada como inexistente (404).
  * A situação aparece como "Ativo" ou "Pausado" mais o motivo (D4): Pausado manualmente, Concluída, Responsável inativo, Responsável sem permissão, Script inativo, Ambiente inativo, Parâmetros inválidos, Expressão CRON inválida ou Erro interno (`ERRO_INTERNO`, CR-007).
  * **Aviso nas regras ativas (CR-007, R-26):** a lista avisa a regra cuja execução anterior ainda está na fila ou rodando ("A próxima vez pode ser pulada: a execução #{id} ainda está {situação}") e a regra que o desdobro vai pausar ("Será pausada: {motivo}"), com as mesmas checagens da retomada.
* **Última pausa no formulário (CR-007, R-26):** uma regra pausada mostra "Pausada em {data} por {ator}: {motivo}", a partir de `pausa_motivo` e do quadro Registro (`updated_at`/`updated_by`, §10), com a orientação de corrigir e retomar.
* **Prévia:** um POST com CSRF devolve as próximas 5 execuções e a descrição em português, chamado com *debounce* de 500 ms. A ajuda da sintaxe CRON fica num bloco recolhível do próprio formulário (D6).

---

### 7.7 Agenda: o que vai rodar (`agendamentos/agenda`, CR-004)

Responde "o que vai rodar hoje e nos próximos dias?". Exige `CAD_AGENDAMENTOS` e mostra só as regras dos ambientes autorizados ao perfil (admin: todas), como a lista do §7.6.

* **Período:** de agora até o fim do 7º dia seguinte, pelo relógio do banco (§7.1).
* **Regras incluídas:** só as ativas. A tela avisa: "Regras pausadas não aparecem aqui."
* **Ocorrências:** são calculadas pelo `recurrence.py`, a partir de `proxima_execucao` (inclusive), respeitando `data_fim`. Há dois limites:
  * no máximo **20 por regra** no período; acima disso aparece "e mais {n} vezes neste período" (por exemplo, CRON a cada minuto). A contagem para em 5.000 ocorrências por regra; acima disso, aparece "e mais de 5.000 vezes neste período";
  * no máximo **500 no total**, com aviso quando passar.
* **Apresentação:** agrupada por dia ("Hoje", "Amanhã", "sexta-feira, 18/10"), em ordem de horário. Cada linha mostra:
  * a hora;
  * o nome da regra;
  * o script;
  * o ambiente;
  * a frase da recorrência (`descrever()` ou o tipo em português);
  * o link para a regra.
* `proxima_execucao` no passado (daemon atrasado) aparece em "Atrasado", no topo, com a frase "deveria ter rodado às {hora}; vai rodar assim que o servidor puder". Com `misfire_policy = SKIP` e atraso acima de `misfire_tolerance_s`, a frase é "passou do horário e será pulada (política de atraso: pular)" (CR-007, R-26).
* **Previsão fiel ao daemon (CR-007, R-26):** cada regra recebe as checagens do desdobro (§7.5, passos 2, 4 e 5). A regra que será pausada aparece com "Será pausada: {motivo}", e a regra cuja execução anterior ainda está na fila ou rodando, com "Pode ser pulada: a execução #{id} ainda está {situação}". Regras `CRON` sem ocorrência no horizonte aparecem num bloco "Regras com problema", e não somem.
* A tela traz a nota "É uma previsão: a execução real depende de um servidor livre."
* Usa as leituras existentes de `RepoAgendamentos` (listagem com filtro de ativos). Não grava nada e não audita.
* A lista de agendamentos ganha o botão "Ver agenda".

## 8. Motor de Execução (ciclo 2 do daemon)

### 8.0 Camada de plataforma (`modules/plataforma/`, CR-001 e CR-005)

O daemon chama apenas a interface abaixo, implementada em `posix.py` (Linux e demais Unix; CR-005: somente POSIX). O restante do motor não conhece o sistema operacional.

| Operação | Implementação POSIX |
|---|---|
| `iniciar_processo` (§8.4) | Fora de DEV: `Popen` do `sudo -n -u <usuário de execução> -- /opt/sss/bin/sss-helper run`, com `start_new_session=True`, a especificação da execução pela entrada padrão e o log como stdout/stderr. Em DEV sem usuário de execução: `Popen(argv, start_new_session=True, preexec_fn=_child_limits)`, com `umask(0o077)` e `setrlimit` |
| `sinalizar_grupo(execucao, sinal)` (não bloqueante) | Fora de DEV: `sudo -n -u <usuário> -- /opt/sss/bin/sss-helper term|kill <pgid> <process_start>`. Em DEV: `os.killpg`. **Nunca espera:** a escalada SIGTERM → `kill_grace_s` → SIGKILL → coleta é uma máquina de estados do laço (§8.1, §8.9) |
| `coletar(execucao)` | `Popen.poll()` para o filho direto. Grupo que **não** é filho do daemon (startup check) é acompanhado por `processo_existe` + identidade, sem `wait()` |
| `identidade_processo(pid)` (contra PID reciclado) | Linux: `starttime` de `/proc/<pid>/stat` (campo 22, após o último `)`). Outros Unix: `/proc/<pid>/psinfo` ou `sysctl KERN_PROC`, sempre sem `ctypes` (AGENTS §3.2). Onde a leitura não for possível assim, devolve `None` (identidade desconhecida) |
| `processo_existe(pid)` | `os.kill(pid, 0)`; `EPERM` (processo de outro usuário) conta como existente |
| `travar_instancia(caminho)` | `fcntl.flock(LOCK_EX \| LOCK_NB)` |
| `usuario_privilegiado()` | `os.geteuid() == 0` |
| `validar_arquivo_restrito(caminho)` (segredos, §4.1) | Dono = euid e `mode & 0o077 == 0` |
| `validar_caminho_script` (§8.5, CR-011) | Arquivo real (o caminho pode ter link simbólico): existe, é regular e não é gravável por grupo nem por outros |
| `validar_execucao()` (CR-007, D1) | Na subida, fora de DEV: o helper existe, tem dono root, modo `0755` e pasta só gravável pelo root; `sudo -n -l` do usuário do agente mostra a regra do helper para cada usuário de execução; cada usuário de execução existe, não é root e não é o usuário do agente; `exec_work_dir/<usuário>` existe, pertence ao usuário de execução e tem modo `0700` |
| `criar_dir_trabalho` (§8.4) | `work_dir/ticket_<id>/` do agente com `0700` (estado local). O diretório de trabalho do script é criado pelo helper |
| Parada | SIGTERM/SIGINT acionam a flag |

**Helper `sss-helper` (CR-007, D1).** É a única forma de o agente agir como o usuário de execução:

* Instalado pelo root em `/opt/sss/bin/sss-helper` (cópia de `bin/sss-helper` do pacote; Python 3.6 só com a biblioteca padrão, sem importar a aplicação), dono root, modo `0755`, numa pasta que só o root grava.
* Regra de sudoers, uma por usuário de execução, sem senha e sem outro comando: `sssagente ALL=(sssprd) NOPASSWD: /opt/sss/bin/sss-helper` (o modelo completo está no `IMPLANTACAO.md`). O helper valida os próprios argumentos e recusa qualquer outro uso com código 2.
* **`run`:** lê da entrada padrão uma especificação JSON (até 1 MiB) com `ticket_id`, `argv`, `env`, `rlimits` e `pasta_base` (`exec_work_dir/<usuário>`). Confere que `argv[0]` é absoluto e que a pasta base pertence ao próprio usuário. Reabre a entrada padrão em `/dev/null`, cria `<pasta_base>/ticket_<id>/` e `tmp/` com `0700`, usa a pasta como `cwd`, aplica `umask(0o077)` e os `setrlimit` e faz `execve(argv[0], argv, env)`. O script herda o PID do helper e o grupo do `sudo`. O stdout e o stderr são o arquivo de log aberto pelo agente: o usuário de execução escreve no descritor, mas não consegue abrir o arquivo pelo caminho.
* **`term <pgid> <process_start>`** e **`kill <pgid> <process_start>`:** se o líder do grupo existe, a identidade dele precisa ser igual a `process_start` (lida de `/proc/<pid>/stat` só pela função `_identidade` do helper, exceção estreita do AGENTS §3.2; divergente ou ilegível: código 3); se não existe mais, só os membros do grupo que pertencem ao usuário de execução recebem o sinal (um PGID não é reutilizado enquanto o grupo tem membros). `ESRCH` (grupo vazio) é sucesso.
* **`limpar <pasta_base> <ticket_id>` (CR-008, R-36):** a `pasta_base` vem como argumento e precisa ser exatamente `exec_work_dir/<usuário>` (absoluta, normalizada, dona = o próprio usuário de execução, sem link simbólico); o helper não importa a aplicação nem lê o `config.ini`. Remove `<pasta_base>/ticket_<id>/` sem seguir links simbólicos.
* **`encerrar-ticket <pasta_base> <ticket_id>` (CR-008, R-01):** para o caso "talvez iniciado" (`.sss_spawn` sem `.sss_proc`, §8.7). Com a mesma validação da `pasta_base`, envia SIGTERM e, depois de `kill_grace_s` passado como terceiro argumento (máximo 300), SIGKILL a todo processo **do próprio usuário de execução** cujo diretório atual está em `<pasta_base>/ticket_<id>` (Linux: `/proc/<pid>/cwd`; outros Unix: `pwdx` quando existir). Sem meio de identificar os processos, sai com código 5 (não suportado) e o agente registra WARN. É a única chamada do helper que espera, porque roda só no startup check, antes do laço.
* Códigos de saída: 0 sucesso, 2 uso inválido, 3 recusado (identidade divergente), 4 erro do sistema, 5 não suportado nesta plataforma (`encerrar-ticket`). As mensagens vão para o stderr, sem valores sensíveis.
* **O que o agente acompanha:** o `Popen` do `sudo`, filho direto do agente. O `sudo` devolve o código de saída do script; morte por sinal vira `returncode` negativo, convertido como no §5.2. O PID registrado (`process_id`, nome do log) é o do `sudo`, que lidera o grupo, e `process_start` é a identidade dele.
* **DEV:** com `[agent] usuarios_execucao` vazio (permitido só com `sss_env = DEV`), o agente executa direto, como antes, com WARN `SEM_USUARIO_EXECUCAO` na subida.

O arquivo `work_dir/sss-<agent_id>.stop` também aciona a flag.

### 8.1 Laço principal

```text
inicialização (§8.12) -> loop (uma coisa por vez, sem espera dentro das operações):
  toda iteração                 : checagem do fence (§8.9) + máquinas de encerramento (SIGTERM → prazo → SIGKILL) + coleta dos processos que terminaram
  a cada cancel_poll_interval_s : varredura própria (§8.7) + cancelamentos + timeouts + finalizações pendentes
  a cada heartbeat_interval_s   : heartbeat (§8.7) + log pump (§8.10)
  a cada orchestrator_interval_s: releitura dos ambientes ativos + conferência da configuração crítica (§8.12) + NODE_OFFLINE (§8.8) + desdobro (§7.5) + claim (§8.2-8.4)
  sinal SIGTERM/SIGINT ou arquivo .stop : graceful shutdown (§8.11)
  entre iterações               : select/sleep até o próximo prazo, no máximo 1 s
```

**Orçamento de tempo (CR-007, R-04):**

* Nenhuma operação bloqueia além de `call_timeout_ms` (chamadas ao banco e abertura de conexão, §2.3) ou de um passo de E/S local.
* Não há `sleep` nem `wait()` dentro das operações: reconexão (uma tentativa por ciclo), encerramento de processos (máquina de estados) e espera entre ciclos são prazos do relógio monotônico.
* O fence é verificado no início de toda iteração e depois de cada chamada ao banco.
* O claim e o desdobro param ao gastar `heartbeat_interval_s / 2` no ciclo; o restante fica para o ciclo seguinte.
* **Log pump com orçamento (CR-008, R-11):** cada rodada do pump (§8.10) também para ao gastar `heartbeat_interval_s / 2`, com rodízio entre os tickets (a rodada seguinte começa pelo ticket seguinte ao último atendido). O que sobra fica para a rodada seguinte; o arquivo local continua integral. O heartbeat é feito **antes** do pump na mesma iteração.
* A regex dos parâmetros, que roda no desdobro, é do subconjunto seguro (§6.2, D5).
* Assim, o maior intervalo sem verificar o fence é `call_timeout_ms / 1000 + 1` s, o que sustenta as invariantes I3 e I4 do §8.9.

### 8.2 Seleção de candidatos

O agente só tenta o claim se `execucoes_locais < max_parallel_jobs`, com `max_parallel_jobs <= max_parallel_hard_limit`, **e** se o espaço livre no sistema de arquivos de `log_dir` for de pelo menos `[agent] log_dir_min_livre_mb` (CR-008, R-25; medido por `os.statvfs` a cada ciclo de claim). Abaixo disso, não faz claim e registra WARN `DISCO_LOG` uma vez por minuto; os tickets em execução continuam. Os placeholders `:amb0..:ambN` são **gerados pelo código** a partir dos ambientes atendidos **ativos agora**; os valores sempre são binds.

```sql
SELECT id, script_id, ambiente FROM (
  SELECT t.id, t.script_id, t.ambiente
    FROM {owner}.tbsss_tickets t
    JOIN {owner}.tbsss_scripts s ON s.id = t.script_id
   WHERE (CASE WHEN status = 'PENDING' THEN prioridade END) IS NOT NULL
     AND (CASE WHEN status = 'PENDING' THEN scheduled_at END) <= SYSDATE
     AND t.ambiente IN (:amb0, :amb1)
     AND s.interpretador IN (:int0, :int1)
     AND t.cancel_requested = 'N'
     AND s.max_qtd_parallel_env > (SELECT COUNT(*) FROM {owner}.tbsss_tickets r
                                    WHERE r.script_id = t.script_id
                                      AND r.ambiente = t.ambiente
                                      AND r.status = 'RUNNING')
   ORDER BY GREATEST(1, (CASE WHEN status = 'PENDING' THEN prioridade END)
                        - CASE WHEN :env_min > 0
                               THEN FLOOR((SYSDATE - GREATEST((CASE WHEN status = 'PENDING' THEN scheduled_at END), t.created_at)) * 1440 / :env_min)
                               ELSE 0 END),
            (CASE WHEN status = 'PENDING' THEN scheduled_at END),
            t.id
) WHERE ROWNUM <= :lote
```

* As expressões `CASE` do `WHERE` são **textualmente idênticas** às do índice baseado em função `ix_tbsss_tck_fila`, que contém apenas os tickets `PENDING`, e ficam **sem alias de tabela**, como as constantes do `sql_ident` (CR-007, R-32). As colunas `status`, `prioridade` e `scheduled_at` só existem em `tbsss_tickets`, então não são ambíguas no join.
* **Teto na própria seleção (CR-007, R-07):** a subconsulta exclui os pares (script, ambiente) que já estão no teto, usando `ix_tbsss_tck_scr`. Sem ela, um script saturado ocupava o lote inteiro e os demais nunca eram vistos. O claim (§8.3) continua com a checagem definitiva, sob lock.
* **Ordem:** pela prioridade efetiva (§5.3, `:env_min` = `fila_envelhecimento_min`, idade contada desde `GREATEST(scheduled_at, created_at)`, CR-008 R-20), depois `scheduled_at` e `id`. A ordenação é feita sobre o conjunto `PENDING` vencido, já reduzido pelo índice; o `EXPLAIN PLAN` do F8.3 registra o plano.
* **Ambientes ativos (CR-007, D2):** o agente relê `tbsss_ambientes` a cada ciclo do orquestrador e usa só os ambientes atendidos que estão ativos. Desativar um ambiente para os claims sem reiniciar os agentes; reativá-lo volta a atendê-lo.

O filtro `s.interpretador IN (:int0..:intN)` usa os interpretadores que **este** agente suporta (§12.1). Assim, cada agente só pega os scripts que consegue executar. Os placeholders são gerados pelo código, e os valores vão sempre como binds.

Não há filtro por pasta (CR-005): o script fica num caminho absoluto, e um agente que não tenha o arquivo, ou em que ele não passe na §8.5, finaliza o ticket com `PRECHECK_FAILED`.

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
          log_output = EMPTY_CLOB(),
          log_offset_chars = 0,
          updated_at = SYSDATE, updated_by = :ator
    WHERE id = :ticket_id AND status = 'PENDING' AND cancel_requested = 'N'
   RETURNING started_at INTO :started_at
   ```
   `:ator = 'SYSTEM:<agent_id>'` (§10, CR-006).
   Se `rowcount = 1`, `COMMIT`; o claim devolve o `started_at` (relógio do banco), que dá a pasta do log de execução (§8.4, passo 3). Se for 0, `ROLLBACK` e próximo candidato.

   Logo depois do `COMMIT`, o ticket entra no mapa local do agente, antes de qualquer outra operação (CR-007, R-03). Se o `COMMIT` falhar com desfecho desconhecido, o agente não executa o ticket; a varredura própria reconcilia o estado (§8.7).

**Ordem de locks do sistema** (evita deadlock):
* claim: `tbsss_scripts` → `tbsss_tickets`;
* desdobro: `tbsss_agendamentos` → `tbsss_tickets`.

É proibido inverter essas ordens.

### 8.4 Pré-validação, spawn e registro do PID

1. **Pré-validação do snapshot e do contexto.** Qualquer falha leva a `FAILED` com `PRECHECK_FAILED` e `-4`, com a linha `[SSS]` do §5.2 no log (o código entre parênteses):
   * o JSON é válido e tem `versao` suportada (`VERSAO_NAO_SUPORTADA`);
   * `versao == 4`, e `interpretador` consta na allowlist lógica **e** no mapeamento deste agente (`INTERPRETADOR_NAO_DISPONIVEL`);
   * `path_file` e `interpretador` do snapshot são iguais aos do cadastro atual do script (`CADASTRO_MUDOU`, CR-007 R-24);
   * `path_file` (absoluto) passa na §8.5 neste agente, que fornece o `script_real` (códigos do `path_guard`);
   * o `argv` é montado pelo agente (§6.4) a partir de `interpretador`, `script_real` e `args`;
   * o script segue `ativo = 'S'` (`SCRIPT_INATIVO`) e homologado para o ambiente (`NAO_HOMOLOGADO`);
   * o ambiente do ticket segue ativo (`AMBIENTE_INATIVO`) e o **solicitante** ainda tem `rbac.pode_executar` para o script e o ambiente, com o mesmo contexto de RBAC do desdobro (`SEM_PERMISSAO`, CR-007 D2).

   Uma exceção inesperada nesta fase também finaliza o ticket com `PRECHECK_FAILED` (R-03). **Erro de banco antes do spawn (CR-008, R-07):** só erro de rede ou de prazo (`db_conn.eh_erro_rede` ou `eh_tempo_esgotado`, §2.3) é "banco indisponível": o ticket é **devolvido à fila** (§5.1), ou finalizado `CANCELLED` se `cancel_requested = 'S'` (R-02). Qualquer outro erro de banco (ex.: ORA-01031 por GRANT faltando, ORA-00942, ORA-30006 de lock persistente) finaliza `PRECHECK_FAILED` com a linha `[SSS] ERRO_BANCO: ORA-nnnnn` no log, sem a mensagem do Oracle. Se a própria devolução ou finalização falhar, o ticket fica como "devolução pendente" no mapa local (§8.7, R-08).
2. **Diretórios de trabalho:**
   * `work_dir/ticket_<id>/`, do agente, com `0700`, guarda o estado local (`.sss_spawn`, `.sss_proc` e `.sss_result`, §8.7);
   * o diretório de trabalho do **script** (`cwd`, `HOME` e, com `tmp/`, `TMPDIR`) é `exec_work_dir/<usuário de execução>/ticket_<id>/`, criado pelo helper com o usuário de execução e `0700` (§8.0). Em DEV sem usuário de execução, é `work_dir/ticket_<id>/exec/`, com `tmp/`.
3. **Arquivo de log de execução (CR-005, D5; CR-009):**
   * pasta: `log_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI/`, com a data e a hora de `started_at` (relógio do banco, devolvido pelo claim), a **pasta do ambiente** (CR-009, obrigatória: o nome do ambiente do ticket em minúsculo, sem acento, sem espaço e sem caractere especial, `pastas_log.pasta_ambiente`; ambiente vazio impede o spawn) e a **pasta do script** = forma segura do nome do script (`pastas_log.pasta_script`: sem acento, minúsculo, cada sequência fora de `[a-z0-9._-]` vira `_`, sem `.` ou `_` nas pontas; vazio vira `script_<id>`). Ex.: `log_dir/producao/carga_diaria/2026/10/16/14/05/`;
   * criada nível a nível com `0750` (cada pasta nova da cadeia `<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI` recebe `chmod 0750`, porque o `makedirs` só aplica o modo à pasta final e sempre sob a `umask` 077 do launcher; o mesmo vale para o log da aplicação, §13);
   * o arquivo é aberto **antes** do spawn como `ticket_<id>.log.parcial`, com `os.open(path, O_WRONLY | O_CREAT | O_EXCL | O_APPEND, 0o600)`;
   * logo depois do `Popen`, é renomeado (`os.rename`, atômico no mesmo diretório; o descritor continua válido) para **`ticket_<id>_<PID>.log`**, com o PID do processo do script. Ex.: `log_dir/producao/carga_diaria/2026/10/16/14/05/ticket_41_12345.log`;
   * se o spawn falhar (`SPAWN_ERROR`), o agente grava a causa no arquivo e o renomeia para `ticket_<id>_0.log`;
   * o arquivo pertence ao usuário do agente; o script recebe só o descritor, como stdout e stderr.
4. **Spawn** (`plataforma.iniciar_processo`, §8.0).

   **Releitura do cancelamento (CR-007, R-28):** imediatamente antes do spawn, o agente lê `cancel_requested` pela PK, sem lock. Se for `S`, finaliza `CANCELLED`/`CANCEL_USER`/`-1` sem iniciar o script.

   **Marcador de spawn (CR-008, R-01):** depois da releitura e **imediatamente antes** do `Popen`, o agente grava `work_dir/ticket_<id>/.sss_spawn` (JSON com `ticket_id`, `usuario_execucao` e o instante monotônico e de parede; arquivo temporário + `rename`, `0600`). A partir daí, o ticket é "talvez iniciado" até o `.sss_proc` existir: nunca volta à fila. Se a gravação do marcador falhar, o ticket é finalizado `SPAWN_ERROR` sem spawn.

   Fora de DEV, pelo helper e com o usuário de execução do ambiente:

   ```python
   p = subprocess.Popen(
       ['/usr/bin/sudo', '-n', '-u', usuario_execucao, '--', '/opt/sss/bin/sss-helper', 'run'],
       stdin=subprocess.PIPE,          # a especificação (argv, env, limites) vai por aqui, e o pipe é fechado
       stdout=log_fd,
       stderr=subprocess.STDOUT,
       shell=False,
       close_fds=True,
       start_new_session=True,         # o sudo lidera o grupo; o script herda o grupo
       env={'PATH': '/usr/bin:/bin', 'LANG': locale_processo, 'LC_ALL': locale_processo},
   )
   p.stdin.write(json.dumps(especificacao).encode('utf-8'))
   p.stdin.close()
   os.close(log_fd)
   ```

   Em DEV sem usuário de execução:

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
   **Qualquer** exceção no spawn (não só `OSError`; por exemplo, `UnicodeEncodeError` num processo sem UTF-8) leva a `FAILED` com `SPAWN_ERROR` e `-4`, com a linha `[SSS]` no log (CR-007, R-17).

   **Exceção depois do `Popen` (CR-008, R-01):** se o `Popen` retornou e qualquer passo seguinte falhar antes do `registrar_pid` (escrita na entrada padrão do helper, `rename` do log, leitura da identidade, gravação do `.sss_proc`), o agente encerra o grupo de `p.pid` (`sinalizar_grupo` SIGTERM e, na máquina de estados, SIGKILL; o processo continua no mapa local até ser coletado) e só então finaliza `SPAWN_ERROR`. O script nunca fica vivo sem registro local.
5. **Instante de início:** renomear o log (passo 3), ler `plataforma.identidade_processo(pid)` (`starttime` no Linux; §8.0), gravar **`work_dir/ticket_<id>/.sss_proc`** (JSON com `ticket_id`, `pid`, `pgid`, `process_start` e `usuario_execucao`; arquivo temporário + `rename`, `0600`) **antes** do banco (CR-007, R-01) e então:
   ```sql
   UPDATE {owner}.tbsss_tickets
      SET process_id = :pid, process_start = :process_start
    WHERE id = :ticket_id AND agente_id = :agente_id AND status = 'RUNNING'
   ```
   Se `rowcount = 0`, a posse foi perdida (por exemplo, `NODE_OFFLINE` durante o spawn): encerramento do grupo pela máquina de estados do executor (`pedir_encerramento`/`avancar_encerramento`, sem esperar) e ERROR `OWNERSHIP_LOST`. Se o `UPDATE` falhar por erro de banco, o ticket fica "PID pendente" no mapa local e o `UPDATE` é refeito a cada ciclo rápido até `rowcount` 1 ou 0 (CR-008, R-08); enquanto isso, o processo é acompanhado normalmente (heartbeat, cancelamento, timeout, fencing). O registro do PID é rotina técnica e não grava `updated_*` (§10, CR-006).

### 8.5 Validação de interpretador e caminho (`path_guard.py`, CR-005, CR-011)

**Princípio (CR-011):** o ambiente controla o conteúdo e a versão dos scripts; o SSS agenda e executa. O agente confere só o essencial do arquivo, no servidor onde o script roda. Não há hash do conteúdo nem conferência do dono dos arquivos.

**Interpretadores lógicos (somente POSIX):** `PYTHON3`, `BASH` e `SH`.

* O executável de cada interpretador vem de `[agent] interpretadores`. Na inicialização, o agente confere, por `path_guard.validar_executavel`: caminho absoluto e normalizado, existe, é arquivo executável e fica fora de `log_dir`, `work_dir` e `exec_work_dir`. Pode ser link simbólico (como `/usr/bin/python3`) e pode ficar nas pastas do sistema. Falha: `INTERPRETADOR_INSEGURO` (ou `NAO_ENCONTRADO`), CRITICAL.

**Caminho livre (CR-005, D2): o script pode ficar em qualquer lugar do servidor, fora das pastas do sistema e do SSS**

* O cadastro grava em `path_file` o **caminho absoluto** do arquivo (ex.: `/opt/automacoes/scripts/faturamento/carga_faturas.py`). O mesmo caminho vale para todos os agentes que atendem o script.
* **Link simbólico (CR-011):** o `path_file` pode ser link, ou ter link em qualquer pasta do caminho. O agente resolve o caminho real (`os.path.realpath`) e **executa o arquivo real**; o script recebe os dois (`SSS_SCRIPT_ARQUIVO` e `SSS_SCRIPT_LINK`, §8.6). A pasta onde o link está não é conferida: quem puder gravar nela pode trocar o destino, risco aceito no §14.
* **Formato** (`validar_cadastro`; parte dele também nas CKs, abaixo):
  * absoluto (começa com `/`) e normalizado (`os.path.normpath(p) == p`): sem `//`, sem `/./` e sem barra no fim;
  * sem `..` em nenhum ponto, sem `\` e sem caractere de controle;
  * até 500 caracteres.
* **Pastas proibidas**, no caminho cadastrado e no real: dentro de `/bin`, `/sbin`, `/usr`, `/lib`, `/lib32`, `/lib64`, `/libx32`, `/etc`, `/boot`, `/proc`, `/sys`, `/dev` ou `/root` é `PASTA_DO_SISTEMA`; dentro de `log_dir`, `work_dir` ou `exec_work_dir` é `PASTA_DO_SSS`.
* **O arquivo real** (`plataforma.validar_caminho_script`):
  * existe (`NAO_ENCONTRADO`; um ciclo de links também dá `NAO_ENCONTRADO`);
  * as pastas do caminho deixam o agente passar (`EACCES` é `SEM_ACESSO`, diferente de `NAO_ENCONTRADO`);
  * é arquivo regular (`NAO_E_ARQUIVO`);
  * não é gravável por grupo nem por outros (`st_mode & 0o022 == 0`; senão `GRAVAVEL_GRUPO_OUTROS`). As pastas do caminho não são conferidas.
* **Códigos de recusa:** `CAMINHO_RELATIVO`, `CAMINHO_NAO_NORMALIZADO`, `CONTEM_PONTOS`, `SEPARADOR_INVALIDO`, `CARACTERE_INVALIDO`, `PASTA_DO_SISTEMA`, `PASTA_DO_SSS`, `NAO_ENCONTRADO`, `SEM_ACESSO`, `NAO_E_ARQUIVO`, `GRAVAVEL_GRUPO_OUTROS`, `INTERPRETADOR_NAO_PERMITIDO` e `INTERPRETADOR_INSEGURO`. A mensagem de erro nunca inclui o caminho.
* **Onde cada coisa é conferida (CR-011, S1):**
  * **no nó web** (cadastro, prévia e disparo): só o formato, o interpretador da allowlist e as pastas do sistema. O web pode nem ter o arquivo, e não emite aviso de arquivo ausente;
  * **no agente**, a cada execução (§8.4, passo 1): tudo acima, inclusive o arquivo real. Falha: `PRECHECK_FAILED` com o código na linha `[SSS]` do log.
* **CKs de banco** (defesa adicional):
  * `ck_tbsss_scr_int` restringe `interpretador` à allowlist lógica;
  * `ck_tbsss_scr_path` exige `path_file` absoluto, sem `..`, `//` nem `\`.
* **Cadastro na UI** (`admin_scripts`, F4.5):
  * o formato e as pastas do sistema são conferidos ao salvar e ao reativar, com os códigos traduzidos para português; o estado do arquivo no nó web não impede salvar, editar, desativar nem reativar;
  * `path_file` é um campo de texto com o caminho absoluto; a ajuda dá um exemplo (`/opt/automacoes/scripts/carga.py`) e informa que o arquivo é conferido pelo agente, no servidor onde o script roda, e que pode ser link simbólico;
  * `interpretador` é um select fixo da allowlist lógica, e o servidor exige o valor exato, mesmo que o HTML tenha sido adulterado;
  * **caminho visível a todos (D8):** o caminho completo aparece no cadastro, na prévia do argv, no disparo e no detalhe do ticket, para todos que veem o script ou o ticket (a R-f foi revogada);
  * **nome reservado (D7):** o nome cuja pasta de log (§8.4, passo 3) seria `app` é recusado: "Este nome é reservado pelo sistema. Escolha outro.";
  * o `nome` do script é texto livre de 1 a 60 caracteres (sem caracteres de controle), único e editável, porque o snapshot guarda o nome da época e tickets e agendamentos referenciam o `script_id`. Renomear um script muda a pasta dos **próximos** logs de execução; os antigos ficam onde estão;
  * a unicidade do `nome` **diferencia maiúsculas de minúsculas**, como a UK `uk_tbsss_scr_nome` no Oracle: `Carga` e `carga` são nomes distintos (e dividem a pasta de log `carga`, o que é aceito, porque o arquivo leva o número do ticket). O FAKE segue a mesma regra;
  * depois de salvar com sucesso, a tela **volta ao formulário do script**, e não à lista, para mostrar os atalhos de homologação e de vínculo de parâmetros. É uma exceção documentada ao `PADRAO_CRUD_ADMIN.md`.

### 8.6 Ambiente do processo filho (`env_builder.py`)

| Variável | Valor |
|---|---|
| `PATH` | `/usr/bin:/bin` |
| `HOME` | diretório de trabalho do script (§8.4, passo 2) |
| `TMPDIR` | `tmp/` dentro dele |
| `LANG`, `LC_ALL` | `child_locale` (padrão `C.UTF-8`) |
| `TZ` | herdado do daemon (definido pelo launcher) |
| `PYTHONDONTWRITEBYTECODE` | `1` (só tem efeito em BASH/SH que chamem `python` sem `-I`; o `PYTHON3` roda com `-I`, que ignora as variáveis `PYTHON*`, e o UTF-8 dele vem do `LC_ALL`; CR-007, R-17) |
| `PYTHONIOENCODING` | `utf-8` (mesma observação) |
| `SSS_TICKET_ID`, `SSS_TICKET_PAI_ID` | id da execução e, na reexecução, o do ticket original (CR-010) |
| `SSS_TIPO_EXECUCAO` | `MANUAL` ou `AGENDADA` (ticket com `agendamento_id`; CR-010) |
| `SSS_RECORRENCIA`, `SSS_AGENDAMENTO_ID`, `SSS_AGENDAMENTO_NOME` | só na execução agendada: `UNICA`, `DIARIA`, `SEMANAL`, `MENSAL` ou `CRON`, o id e o nome da regra (CR-010) |
| `SSS_DATA_EXECUCAO`, `SSS_DATA_AGENDADA` | `started_at` (relógio do banco, devolvido pelo claim) e `scheduled_at`, no formato `AAAA-MM-DD HH:MI:SS` (CR-010) |
| `SSS_PRIORIDADE`, `SSS_TIMEOUT_SEG` | prioridade do ticket e prazo efetivo (`timeout_seg` do script ou `script_timeout_s`) (CR-010) |
| `SSS_AMBIENTE`, `SSS_AMBIENTE_DESCRICAO` | nome e descrição do ambiente do ticket |
| `SSS_AMBIENTE_DSN`, `SSS_AMBIENTE_USUARIO` | DSN de `tbsss_ambientes.conexao` (sem credencial) e o usuário de `secrets.cfg [ambiente:<NOME>]` (CR-010) |
| `SSS_AMBIENTE_CONEXAO` e `PADRAO_VALOR_RUN_CONEXAO_BD` | o mesmo valor `user/password@dsn`, com credenciais de `secrets.cfg [ambiente:<NOME>]` e DSN de `tbsss_ambientes.conexao`; a segunda é o nome antigo, mantido para os scripts existentes (CR-010). Omitidas se o ambiente não tiver DSN ou credencial. Mascaradas em todo log |
| `SSS_SCRIPT_ID`, `SSS_SCRIPT_NOME`, `SSS_INTERPRETADOR` | do snapshot (o nome da época da criação do ticket, §6.5) (CR-010) |
| `SSS_SCRIPT_ARQUIVO`, `SSS_SCRIPT_DIR` | `script_real` (o arquivo real, que é o executado) e `os.path.dirname(script_real)` |
| `SSS_SCRIPT_LINK` | o `path_file` cadastrado, só quando ele difere do real (há link simbólico no caminho; CR-011) |
| `SSS_LOG_DIR`, `SSS_LOG_ARQUIVO` | pasta do log da execução (§8.4, passo 3) e o nome do arquivo no início (`ticket_<id>.log.parcial`, renomeado para `ticket_<id>_<PID>.log` logo depois do spawn). Informativas: a saída do script já é o log, e fora de DEV o usuário de execução não abre o arquivo pelo caminho (CR-010) |
| `SSS_AGENTE_ID`, `SSS_AGENTE_HOST`, `SSS_PLATAFORMA`, `SSS_VERSAO` | agente que executa, hostname, `LINUX` ou `UNIX` e versão do SSS (CR-010) |
| `env_passthrough` | copiadas do ambiente do daemon (por exemplo, `ORACLE_HOME`, `TNS_ADMIN`, `NLS_LANG`, `LD_LIBRARY_PATH`) |

* **Bloqueadas** mesmo se listadas em `env_passthrough` (a configuração que as contiver é rejeitada na inicialização):
  * `LD_PRELOAD`, `LD_AUDIT` e qualquer `LD_*` exceto `LD_LIBRARY_PATH`; `BASH_FUNC_*`; `GCONV_PATH`, `LOCPATH`, `NLSPATH`, `HOSTALIASES`, `GLIBC_TUNABLES`, `MALLOC_*`;
  * `PYTHONPATH`, `PYTHONHOME`, `PYTHONSTARTUP`, `PYTHONINSPECT`, `PERL5LIB`, `PERL5OPT`;
  * `BASH_ENV`, `ENV`, `SHELLOPTS`, `BASHOPTS`, `IFS`, `PS4`, `PROMPT_COMMAND`, `CDPATH`, `GLOBIGNORE`.
* **CR-010:** o prefixo `SSS_` é reservado aos dados que o agente passa ao script. Variável sem valor não é definida (por exemplo, `SSS_RECORRENCIA` numa execução manual). O solicitante e os parâmetros **não** vão para o ambiente: os parâmetros chegam pelos argumentos (§6.4).
* **Chaves fixas** também são recusadas no `env_passthrough`, porque o agente as define (CR-007, R-32): `PATH`, `HOME`, `TMPDIR`, `LANG`, `LC_*`, `TZ`, `SSS_*`, `PADRAO_VALOR_RUN_CONEXAO_BD` e `PYTHON*`.
* **Isolamento (CR-007, D1):** o script roda com o usuário de execução do ambiente, que não lê o ambiente do agente nem de scripts de outros ambientes. Resta legível pelo próprio usuário de execução (outros scripts do **mesmo** ambiente) e pelo root (`/proc/<pid>/environ`), aceito no §14.

### 8.7 Varredura própria, heartbeat, timeout e finalização

Varredura combinada (a cada `cancel_poll_interval_s`, usa `ix_tbsss_tck_run`):

```sql
SELECT id, cancel_requested
  FROM {owner}.tbsss_tickets
 WHERE (CASE WHEN status = 'RUNNING' THEN agente_id END) = :agente_id
```

* Um ticket que está no mapa local mas **ausente** do resultado foi finalizado por outro nó. O agente encerra o grupo (§8.9, sem bloquear), registra ERROR `OWNERSHIP_LOST` e não grava status.
* **Ticket no resultado e fora do mapa local (CR-007, R-03; CR-008, R-01 e R-02):**
  * com `.sss_proc` presente, segue o tratamento do startup check (§8.12, passo 9);
  * com `.sss_spawn` e sem `.sss_proc` ("talvez iniciado"): **nunca** volta à fila; o agente chama o helper `encerrar-ticket` (§8.0; em DEV, procura o diretório de trabalho do ticket em `/proc/<pid>/cwd`) e finaliza `ORPHAN_PROCESS` (ERROR `TALVEZ_INICIADO`); com código 5 do helper, registra WARN e finaliza do mesmo jeito;
  * sem `.sss_spawn`, sem `.sss_proc` e com `process_id` nulo, o script nunca foi iniciado: o ticket é **devolvido à fila** (§5.1, WARN `DEVOLVIDO`), ou finalizado `CANCELLED`/`CANCEL_USER` se `cancel_requested = 'S'` (R-02);
  * sem `.sss_proc` e com PID, é finalizado `ORPHAN_PROCESS` (ERROR).

  Isso cobre o `COMMIT` do claim com desfecho desconhecido e qualquer perda do mapa local.
* **Pendências locais com retentativa (CR-008, R-08):** além da finalização pendente, o mapa local tem dois estados de pendência, refeitos a cada `cancel_poll_interval_s` até o banco responder:
  * **devolução pendente:** a devolução (ou o cancelamento do R-02) falhou por erro de banco; o ticket continua no heartbeat, sem processo, e entra no fencing normalmente; `rowcount = 0` na nova tentativa encerra a pendência com WARN;
  * **PID pendente:** o `registrar_pid` (§8.4, passo 5) falhou por erro de banco; o processo é acompanhado normalmente e o `UPDATE` é refeito até `rowcount` 1 (concluído) ou 0 (`OWNERSHIP_LOST`, grupo encerrado).

  Nenhuma pendência dura para sempre: se o banco não voltar, o fencing (§8.9) encerra os processos, e o detector de outro nó marca os tickets `NODE_OFFLINE`.
* **Heartbeat** (a cada `heartbeat_interval_s`):
  * `executemany` de `UPDATE ... SET heartbeat_at = SYSDATE WHERE id = :id AND agente_id = :agente_id AND status = 'RUNNING'`, com `arraydmlrowcounts=True`, incluindo os tickets em finalização pendente;
  * linha com contagem 0 é tratada como `OWNERSHIP_LOST`;
  * **instante de referência (CR-008, R-09):** o agente captura `time.monotonic()` **antes** do primeiro `UPDATE` da transação; no `COMMIT` bem-sucedido, `ultimo_hb_ok` recebe esse instante (e não o do fim da transação). Assim, uma transação lenta, com várias chamadas, não estende o prazo do fence além do que outro nó vê em `heartbeat_at`;
  * na mesma transação, atualiza `tbsss_agentes.heartbeat_at` com `WHERE codigo = :agente_id AND hostname = :hostname AND pid_daemon = :pid AND status = 'ATIVO'` e lê `SYSDATE` (trava de salto de relógio, §8.8). `rowcount = 0` é `REGISTRO_PERDIDO`: outro processo assumiu o registro deste `agent_id` (§8.12). O agente registra CRITICAL, faz o encerramento `TERMINATE` e sai com código diferente de zero (CR-007, R-11);
  * **roda sempre**, mesmo sem tickets: o `executemany` vazio é pulado, o `UPDATE` do agente não (R-28);
  * o heartbeat é rotina técnica: não grava `updated_*` no ticket nem no agente (§10, CR-006).
* **Timeout:** `timeout = tbsss_scripts.timeout_seg` ou, se nulo, `script_timeout_s`. Ao expirar, o agente inicia o encerramento escalonado do grupo (máquina de estados, §8.9) e, quando ele termina, finaliza com `FAILED`, `TIMEOUT` e `-3`.
* **Finalização** (processo terminado, detectado por `Popen.poll()`, ou encerramento concluído por timeout, cancelamento, `LOG_LIMIT` ou `SHUTDOWN`):
  1. **encerrar o grupo** do ticket (CR-007, R-02): mesmo que o processo principal tenha saído sozinho, o agente sinaliza o grupo (SIGTERM, prazo, SIGKILL) antes do flush. Havendo processos remanescentes, WARN `NETOS_ENCERRADOS`. `ESRCH` (grupo vazio) é o caso normal;
  2. flush final do log;
  3. gravar `.sss_result` (`status`, `status_motivo`, `return_code`) no `work_dir/ticket_<id>/` (R-01);
  4. `UPDATE ... SET status, status_motivo, return_code, finished_at = SYSDATE, updated_at = SYSDATE, updated_by = :ator WHERE id = :id AND agente_id = :agente_id AND status = 'RUNNING'`, com `:ator = 'SYSTEM:<agent_id>'`. Toda finalização de ticket pelo agente (timeout, `LOG_LIMIT`, `SHUTDOWN`, `ORPHAN_PROCESS`, `SPAWN_ERROR`, `PRECHECK_FAILED`) grava `updated_*` do mesmo jeito (§10, CR-006);
  5. `COMMIT`. Com erro de banco no passo 4 ou 5, o ticket fica em **finalização pendente** (R-03): continua no heartbeat, e o `UPDATE` é tentado de novo a cada `cancel_poll_interval_s` até `rowcount = 1` (concluído) ou `0` (`OWNERSHIP_LOST`; o resultado local fica só no log). `finished_at` é o `SYSDATE` do `UPDATE` bem-sucedido; o instante real do fim fica na linha `[SSS] terminou às <hora local>` do log;
  6. limpeza de `work_dir/ticket_<id>/` e, pelo helper, de `exec_work_dir/<usuário>/ticket_<id>/`. A limpeza acontece em **todo** encerramento (inclusive `OWNERSHIP_LOST` e `FENCED`), e o startup check limpa o que sobrar (R-32).

### 8.8 Detecção de nó offline (qualquer agente, a cada `orchestrator_interval_s`)

Em duas etapas (CR-007, R-12), para não esperar por linhas travadas (por exemplo, por uma sessão morta de outro agente):

```sql
SELECT id FROM {owner}.tbsss_tickets
 WHERE (CASE WHEN status = 'RUNNING' THEN agente_id END) IS NOT NULL
   AND (CASE WHEN status = 'RUNNING' THEN agente_id END) <> :agente_id
   AND heartbeat_at < SYSDATE - :node_offline_timeout_s * INTERVAL '1' SECOND
   FOR UPDATE SKIP LOCKED
```

```sql
UPDATE {owner}.tbsss_tickets
   SET status = 'FAILED', status_motivo = 'NODE_OFFLINE',
       return_code = -2, finished_at = SYSDATE,
       updated_at = SYSDATE, updated_by = :ator
 WHERE id = :id AND status = 'RUNNING'
```

* O `UPDATE` roda com `executemany` sobre os ids travados, na mesma transação. `:ator` é `SYSTEM:<agent_id>` do agente que detectou (§10, CR-006). Os ids marcados vão para o log em INFO.
* Linhas travadas por outra sessão ficam para o ciclo seguinte (`SKIP LOCKED`), sem bloquear o laço.
* O detector **nunca** marca os próprios tickets (`<> :agente_id`); os dele são tratados pela varredura própria e pelo fencing.
* **Só detecta quem está saudável:** o §8.8 só roda se o último heartbeat confirmado do próprio detector tiver menos de `fence_timeout_s / 2` e se não houver suspensão por salto de relógio.
* **Trava conferida na própria transação (CR-008, R-10):** antes do `SELECT ... FOR UPDATE SKIP LOCKED`, a mesma transação lê `SYSDATE` e compara o avanço dele com o do relógio monotônico desde o último `SYSDATE` lido (heartbeat ou detecção anterior). Se a diferença passar de 30 s, a detecção é pulada, a suspensão por `node_offline_timeout_s` começa ali mesmo (WARN `SALTO_RELOGIO`) e nenhum ticket é marcado. Assim, um salto entre dois heartbeats não chega ao detector.
* **Trava contra salto de relógio (CR-007, D3):** a cada heartbeat, o agente compara o avanço do `SYSDATE` (lido na transação do heartbeat) com o do relógio monotônico desde o heartbeat anterior. Se a diferença passar de 30 s, registra WARN `SALTO_RELOGIO` (com o tamanho do salto) e suspende o §8.8 por `node_offline_timeout_s`, tempo para todos os agentes renovarem o heartbeat sob o relógio novo. Sem a trava, um avanço do relógio do banco marcaria como offline todos os tickets do cluster.

O relógio de referência é sempre o `SYSDATE` do banco, nunca o relógio do nó.

### 8.9 Self-fencing (prevenção de split-brain)

* O agente registra o instante do último heartbeat **confirmado** (commit OK), medido no **início** da transação de heartbeat (§8.7, CR-008 R-09).
* `ultimo_hb_ok` começa no fim da inicialização (§8.12) e só avança com heartbeat confirmado (R-28).
* A condição é verificada a **cada iteração do laço** e depois de cada chamada ao banco (§8.1), não só no ciclo de heartbeat (CR-007, R-04).
* Se `agora_monotonico - ultimo_hb_ok > fence_timeout_s`, o agente:
  1. envia SIGTERM a **todos** os grupos que possui de uma vez e, depois de `kill_grace_s`, SIGKILL aos que restarem (máquina de estados, nunca grupo a grupo);
  2. suspende novos claims;
  3. registra CRITICAL `FENCED`.
* Quando o banco volta, para cada ticket que possuía:
  * **com `.sss_result`** (o script terminou e o resultado foi decidido antes ou durante a queda; CR-008, R-12), finaliza pelo resultado gravado (`status`, `status_motivo`, `return_code`), como no startup check;
  * sem `.sss_result`, tenta `UPDATE ... SET status = 'FAILED', status_motivo = 'FENCED', return_code = -2, ..., updated_at = SYSDATE, updated_by = :ator WHERE id = :id AND agente_id = :agente_id AND status = 'RUNNING'`, com `:ator = 'SYSTEM:<agent_id>'`.

  Nos dois casos, se o ticket já estiver `NODE_OFFLINE`, o `rowcount = 0` é esperado.
* **Invariantes validadas na inicialização** (`sss_config`), com `call_timeout_s = ceil(call_timeout_ms / 1000)`:
  * **I1:** `heartbeat_interval_s * 3 <= fence_timeout_s`;
  * **I2:** `fence_timeout_s * 2 <= node_offline_timeout_s`;
  * **I3 (CR-007):** `heartbeat_interval_s + 2 * call_timeout_s <= fence_timeout_s`, para que um heartbeat atrasado por uma chamada travada não provoque fencing falso;
  * **I4 (CR-007):** `fence_timeout_s + call_timeout_s + kill_grace_s + 2 <= node_offline_timeout_s`, para que o agente termine de matar os filhos **antes** de outro nó declará-lo offline, mesmo com uma chamada travada no momento do fence. A I4 vale para transações de heartbeat com várias chamadas porque `ultimo_hb_ok` é medido no início da transação (CR-008, R-09): o `heartbeat_at` gravado é sempre posterior a esse instante.

  Com os valores de exemplo (heartbeat 10, fence 90, offline 180, `call_timeout_ms` 30.000, `kill_grace_s` 5): I3 = 70 ≤ 90 e I4 = 127 ≤ 180.
* **Mesmos tempos em todos os nós:** quem declara um agente offline é **outro** agente, com o `node_offline_timeout_s` dele (§8.8). Por isso, `fence_timeout_s` e `node_offline_timeout_s` devem ser **idênticos em todos os agentes**; senão a invariante deixa de valer entre nós. A conferência automática é o `config_criticos` (§8.12, CR-007 R-23); além dela:
  * cada agente registra os dois valores em INFO na inicialização;
  * o pacote de implantação (F9.1) usa um único `config.ini` de referência para esses tempos;
  * o roteiro E2E (F9.2) confere que todos os agentes usam os mesmos valores.
* A medição usa `time.monotonic()`, imune a ajuste de relógio.

### 8.10 Coleta de log (`log_pump.py`)

* A cada `heartbeat_interval_s` e no flush final:
  * **orçamento (CR-008, R-11):** a rodada para ao gastar `heartbeat_interval_s / 2` (§8.1), com rodízio entre tickets; o flush final de um ticket não tem orçamento, mas só um flush final roda por iteração do laço;
  * o agente lê os bytes novos do arquivo a partir do offset local;
  * decodifica com `utf-8`, `errors='replace'`, sem cortar caracteres multibyte (o resto incompleto fica para o próximo ciclo);
  * aplica o **mascarador do ticket** (CR-007, R-25): uma instância de `masking.Mascarador` por ticket, com os segredos carregados, o `PADRAO_VALOR_RUN_CONEXAO_BD` (= `SSS_AMBIENTE_CONEXAO`) do ambiente e os valores das `respostas` cujos códigos estão em `sensiveis` no snapshot. O mesmo mascarador filtra as linhas do log da aplicação que tratam do ticket;
  * anexa ao CLOB em blocos de até 8.000 caracteres:

```sql
DECLARE
  v_lob CLOB;
  v_offset NUMBER(20);
  v_tamanho NUMBER(20) := LENGTH(:chunk);
BEGIN
  SELECT log_output, log_offset_chars
    INTO v_lob, v_offset
    FROM {owner}.tbsss_tickets
   WHERE id = :ticket_id AND agente_id = :agente_id AND status = 'RUNNING'
     FOR UPDATE WAIT 5;
  IF DBMS_LOB.GETLENGTH(v_lob) <> v_offset THEN
    RAISE_APPLICATION_ERROR(-20002, 'LOG_OFFSET_DIVERGENTE');
  ELSIF v_offset = :offset_esperado THEN
    DBMS_LOB.WRITEAPPEND(v_lob, v_tamanho, :chunk);
    UPDATE {owner}.tbsss_tickets
       SET log_offset_chars = v_offset + v_tamanho
     WHERE id = :ticket_id AND agente_id = :agente_id
       AND status = 'RUNNING' AND log_offset_chars = v_offset;
    IF SQL%ROWCOUNT <> 1 THEN
      RAISE_APPLICATION_ERROR(-20002, 'LOG_OFFSET_DIVERGENTE');
    END IF;
    :resultado := 'GRAVADO';
  ELSIF v_offset = :offset_esperado + v_tamanho
        AND DBMS_LOB.COMPARE(v_lob, :chunk, v_tamanho,
                             :offset_esperado + 1, 1) = 0 THEN
    :resultado := 'JA_GRAVADO';
  ELSE
    RAISE_APPLICATION_ERROR(-20002, 'LOG_OFFSET_DIVERGENTE');
  END IF;
EXCEPTION
  WHEN NO_DATA_FOUND THEN
    :resultado := 'POSSE_PERDIDA';
END;
```

  * `log_offset_chars` é a posição confirmada em **caracteres CLOB**, não bytes UTF-8. Cada ticket tem no máximo um bloco de log em voo por vez. `:offset_esperado` é a posição conhecida pela bomba antes do bloco.
  * O chamador confirma a transação. Se o `COMMIT` tiver desfecho desconhecido, mantém o bloco pendente e reapresenta exatamente o mesmo offset e bloco numa conexão nova. O SQL devolve `JA_GRAVADO` somente se o offset avançou exatamente pelo tamanho do bloco e o conteúdo nessa posição for idêntico; devolve `GRAVADO` se o bloco ainda não foi anexado. Assim, a repetição não reaplica o `WRITEAPPEND`.
  * `NO_DATA_FOUND` devolve `POSSE_PERDIDA` (`OWNERSHIP_LOST`). Offset divergente ou conteúdo diferente é erro de integridade: não repetir nem descartar o bloco; interromper o pump daquele ticket e registrar ERROR com contexto.
  * A gravação do log (`log_output` e `log_truncado`) é rotina técnica e não grava `updated_*` (§10, CR-006).
* **Limites:**
  * O teto do CLOB é medido em **bytes UTF-8 do texto já enviado** (`len(texto.encode('utf-8'))` acumulado pelo agente), e o corte é feito em fronteira de caractere.
  * `max_log_size_bytes` limita o total de bytes UTF-8 no CLOB, **incluindo** o marcador final `[SSS] log truncado no banco; arquivo integral no agente`. Ao detectar conteúdo além do teto, o agente conserva um prefixo que caiba em `max_log_size_bytes - bytes_do_marcador`, grava `log_truncado = 'S'` e anexa o marcador uma única vez; o total, marcador incluído, nunca excede o teto. O pump mantém em buffer o sufixo necessário para decidir entre enviar o conteúdo integral (se o processo terminar sem exceder o teto) e truncar com marcador.
  * O arquivo local tem teto `max_local_log_size_bytes`. Ao excedê-lo, o processo é encerrado (SIGTERM → SIGKILL) com `FAILED`, `LOG_LIMIT` e `-5`, protegendo o disco. O tamanho é conferido a cada `cancel_poll_interval_s`; contra um script que escreva mais rápido que isso, a operação define cota de disco para o usuário de execução (`IMPLANTACAO.md`).
  * **Arquivo local sem máscara:** o arquivo é escrito pelo próprio script e não é mascarado. Ele pertence ao usuário do agente (`0600`), fica só no agente e é apagado pela retenção (§11.3).
* **UI `VER_LOGS`:** polling a cada `log_poll_interval_s`.
  * O cliente envia o offset já recebido, e o servidor lê pelo locator (`lob.read(offset, amount)`).
    * O offset da API web conta **caracteres a partir de 0**. O repositório Oracle converte para a posição 1 do LOB (`offset + 1`).
    * Cada leitura devolve até 65.536 caracteres.
  * O texto é exibido com `x-text`.
  * A latência esperada é de cerca de `heartbeat_interval_s`.
  * A tela mantém no máximo cerca de 5 milhões de caracteres. Ao passar desse limite, descarta o início e mantém os últimos 4 milhões, com um aviso. O log completo fica disponível no **download**, que é feito em streaming.
  * Em erro transitório, o polling continua com intervalo três vezes maior. Sessão expirada interrompe o polling e pede um novo login.
* **Lista de tickets:** ordenada por `created_at DESC`. A tela se atualiza sozinha a cada 10 s, valor fixo no código e fora do `config.ini`. A ordem da fila de execução (§5.3) é aplicada só pelo daemon.
* Os logs de execução (§8.4, passo 3) com mais de `local_log_retention_days` dias são removidos pelo `purge.py` (§11.3).

### 8.11 Graceful shutdown do daemon

* SIGTERM/SIGINT e o arquivo `work_dir/sss-<agent_id>.stop` apenas acionam uma flag; o laço trata o restante.
* O daemon para de fazer desdobro e claim.

| `shutdown_mode` | Comportamento |
|---|---|
| `DRAIN` | Aguarda os filhos por até `shutdown_grace_s`, mantendo heartbeat, varredura, log pump e fence (CR-007, R-04), e então aplica `TERMINATE` aos restantes |
| `TERMINATE` (padrão) | Encerramento escalonado de todos os grupos de uma vez (§8.9). Finaliza com `FAILED`, `SHUTDOWN` e `-6` |

Em seguida, o daemon faz o flush dos logs, grava `tbsss_agentes.status = 'PARADO'` (com `updated_*` de `SYSTEM:<agent_id>`, §10, e o mesmo filtro de `hostname`/`pid_daemon` do heartbeat), audita `AGENTE_FIM`, remove o arquivo `.stop` (se houver), fecha a conexão e o lock file, e sai com código 0.

### 8.12 Inicialização do daemon (fail-fast)

O daemon aborta com código diferente de zero e log CRITICAL ao falhar em qualquer passo:

* **Códigos de saída por passo (F8.3b):** 10 usuário (root), 11 configuração (inclusive codificação e `child_locale`), 12 segredos, 13 diretórios, interpretadores e execução fora de DEV, 14 instância já em execução, 15 banco (driver, conexão, versão do esquema), 16 registro do agente (`agent_id` duplicado ou `config_criticos` divergente), 17 ambientes atendidos inexistentes, 18 startup check, 19 mais de uma thread antes do primeiro spawn. Em qualquer falha, a trava de instância e a conexão são liberadas antes da saída.

1. **Usuário:** `plataforma.usuario_privilegiado()` precisa ser falso. É proibido rodar como root.
2. **Configuração:** carregar e validar o `config.ini` (tipos, faixas, invariantes da §8.9 e `max_parallel_jobs <= max_parallel_hard_limit`), o `owner` e o `table_prefix` (regex do `AGENTS.md`), e `agent_id` contra `^[A-Za-z0-9._-]{1,30}$`, sem ser `init_db`, `seed` nem `purge` (reservados para os atores do sistema, §4.4). Inclui as invariantes I1 a I4 (§8.9) e, fora de DEV, `usuarios_execucao` cobrindo todos os ambientes atendidos (CR-007, D1).
   **Aviso de configuração (CR-008):** um DSN descritor que passe da fórmula do §2.3 gera WARN `CONEXAO_ACIMA_DO_PRAZO` (R-17).
   **Codificação (CR-007, R-17):** `sys.getfilesystemencoding()` precisa ser UTF-8 (o launcher exporta `LANG`/`LC_ALL`, §12.2); `child_locale` precisa constar em `locale -a`. Falha: CRITICAL.
3. **Segredos:** validar o `secrets.cfg` (§4.1).
4. **Diretórios e interpretadores:**
   * `log_dir` e `work_dir` existem, são graváveis pelo agente e não ficam dentro das pastas do sistema (§8.5);
   * cada entrada de `[agent] interpretadores` é uma chave da allowlist com caminho absoluto e executável, que passa por `path_guard.validar_executavel` (§8.5);
   * fora de DEV, `plataforma.validar_execucao()` (§8.0): helper, regra de sudoers, usuários de execução e `exec_work_dir`.
5. **Instância única por host:** `plataforma.travar_instancia` em `work_dir/sss-<agent_id>.lock`. Um arquivo `.stop` antigo é removido com WARN, para o daemon não parar logo depois de subir (CR-007, R-32).
6. **Banco:** selecionar o driver (§2.3; a sondagem roda aqui), conectar e confirmar o relógio do banco (`SELECT SYSDATE FROM DUAL`). WARN se o `SYSDATE` divergir do relógio local em mais de 60 s (§7.1). **Versão do esquema (CR-007, D4):** `SELECT versao_esquema FROM {owner}.tbsss_controle WHERE id = 1` precisa ser igual a `sql_ident.VERSAO_ESQUEMA`; diferente ou ausente, CRITICAL com as duas versões.
7. **Registro em `tbsss_agentes`**, numa transação (CR-007, R-11):
   * travar a linha do mesmo `codigo` com `SELECT ... FOR UPDATE WAIT 5`. Sem linha, a inclusão pode disputar com outro processo: a violação de `uk_tbsss_agt_codigo` leva a `ROLLBACK` e a uma nova tentativa, que encontra a linha;
   * recusar a subida (`agent_id` duplicado) se a linha estiver `ATIVO` com `heartbeat_at` recente (menor que `node_offline_timeout_s`) e: `hostname` diferente, **ou** o mesmo `hostname` com um `pid_daemon` diferente do próprio que ainda existe (`plataforma.processo_existe`). Mesmo host com o PID antigo morto é a religação depois de uma queda, e segue;
   * caso contrário, executar `MERGE` com `status = 'ATIVO'`, `hostname`, `pid_daemon`, `versao`, `ambientes`, `plataforma`, `interpretadores`, `iniciado_em` e **`config_criticos`** (abaixo). A inclusão grava `created_at = SYSDATE` e `created_by = 'SYSTEM:<agent_id>'`; a atualização grava `updated_*` com o mesmo ator (§10, CR-006).
   * Auditar `AGENTE_INICIO`.
   * **Configuração crítica igual em todos os nós (CR-007, R-23):** `config_criticos` é o texto canônico `hb=<heartbeat_interval_s>;fence=<fence_timeout_s>;offline=<node_offline_timeout_s>;call=<call_timeout_s>;kill=<kill_grace_s>;misfire=<misfire_policy>;tol=<misfire_tolerance_s>;horizonte=<cron_horizon_days>;envelhecimento=<fila_envelhecimento_min>`. Se outro agente `ATIVO` com heartbeat recente tiver um valor diferente, a subida é recusada com CRITICAL (as duas configurações no log). A cada ciclo do orquestrador a conferência se repete: divergência é ERROR `CONFIG_DIVERGENTE`, e a tela de agentes mostra (§13).
   * `ultimo_hb_ok` é inicializado aqui (§8.9).
8. **Ambientes atendidos:** todos existem em `tbsss_ambientes` com `ativo = 'S'`. Um ambiente inexistente é ERROR fatal; um ambiente inativo gera WARN e é ignorado.
9. **Startup check pelo estado local (CR-007, R-01).** O disco do agente é a fonte de verdade sobre o que ele iniciou, seja qual for o status no banco (o ticket pode já ter sido marcado `NODE_OFFLINE` por outro nó enquanto o filho seguia vivo):
   * para **cada** `work_dir/ticket_<id>/` com `.sss_proc`: se o grupo existe e a identidade do líder confere (ou o líder morreu e há membros do usuário de execução), o grupo é encerrado sem bloquear (§8.9). Identidade desconhecida (`None`, §8.0) com PID vivo **não** recebe sinal: WARN `ORFAO_SEM_IDENTIDADE`, para intervenção manual;
   * para **cada** `work_dir/ticket_<id>/` com `.sss_spawn` e **sem** `.sss_proc` ("talvez iniciado", CR-008 R-01): helper `encerrar-ticket` (§8.0), que espera o próprio `kill_grace_s`; o ticket nunca volta à fila;
   * em seguida, se o ticket ainda estiver `RUNNING` deste agente, ele é finalizado pelo `.sss_result` (quando existe: o resultado real que faltou gravar) ou com `ORPHAN_PROCESS`;
   * tickets `RUNNING` deste agente **sem** pasta local: `process_id` nulo é devolvido à fila (§5.1), ou finalizado `CANCELLED`/`CANCEL_USER` se `cancel_requested = 'S'` (CR-008, R-02); com PID, `ORPHAN_PROCESS`;
   * por fim, as pastas são removidas **só depois de confirmar o grupo vazio** (CR-008, R-26): `work_dir/ticket_<id>` e, pelo helper `limpar`, `exec_work_dir/<usuário>/ticket_<id>` saem quando o encerramento terminou (`ESRCH`) e o ticket foi finalizado ou já era terminal. A pasta de um `ORFAO_SEM_IDENTIDADE`, ou de um grupo cujo encerramento ainda corre, fica até a coleta (no laço normal) ou até a próxima subida, para que uma nova queda dentro do `kill_grace_s` não apague o único rastro do processo.

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

* `{prefixo}` vem de `table_prefix`, inclui o `_` final e obedece à regex `^[a-z][a-z0-9_]{0,7}$` (começa com letra minúscula, para gerar nome Oracle válido e casar com o registro, que só aceita identificadores em minúsculas; até 8 caracteres; CR-007, R-31).
* O DDL é gerado por `init_db.py` a partir de um **registro único de identificadores** em `modules/sql_ident.py`, consumido também por `test_db_schema.py`.
* O `owner` vem de `[oracle] owner` no `config.ini` (ex.: `openrisow`) e obedece à regex `^[A-Za-z][A-Za-z0-9_]{0,29}$`. Todo objeto no banco é qualificado como `{owner}.{prefixo}{entidade}`.
* Os exemplos com `tbsss_` neste documento representam a expansão utilizando o prefixo padrão configurado (`table_prefix = tbsss_`).
* **Pior caso com prefixo de 8 caracteres:** `sq_` + 8 + `funcionalidades` = **26** (conforme).

### 9.2 Tabela de abreviações

*(os nomes de sequence, trigger e PK na tabela abaixo utilizam a expansão com o prefixo padrão `tbsss_`; se `table_prefix` for alterado na configuração, os identificadores são gerados com o prefixo correspondente pelo `sql_ident`)*

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
| Controle (CR-007) | `ctl` | `sq_tbsss_controle` | `tr_tbsss_ctl_bi` | `pk_tbsss_controle` |

---

## 10. Modelo de Dados Completo (17 tabelas)

**Padrões globais:**

* O `owner` e o `table_prefix` são parametrizados no `config.ini` (`owner = openrisow`, `table_prefix = tbsss_`; §9.1 e §12.1), e todo SQL qualifica `{owner}.{prefixo}objeto` (ex.: `{owner}.{prefixo}usuarios`). Os exemplos em SQL deste documento utilizam `tbsss_` como a expansão do prefixo padrão `{prefixo}`.
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
* **Colunas de registro (CR-006):** todas as tabelas, **exceto `tbsss_auditoria` e `tbsss_controle`**, terminam com quatro colunas que dizem quem criou o registro e quando, e quem fez a última alteração de negócio:

  | Coluna | Tipo | Gravação |
  |---|---|---|
  | `created_at` | `DATE DEFAULT SYSDATE NOT NULL` | `SYSDATE` no `INSERT`; nunca muda |
  | `created_by` | `VARCHAR2(40 CHAR) NOT NULL`, sem `DEFAULT` | ator do `INSERT`; nunca muda |
  | `updated_at` | `DATE` | `SYSDATE` em cada alteração de negócio; nulo até a primeira |
  | `updated_by` | `VARCHAR2(40 CHAR)` | ator da alteração de negócio; nulo até a primeira |

  * CK `ck_tbsss_<abrev>_upd`: `(updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL)`. Sem FK, porque um ator `SYSTEM:` não é usuário e o registro sobrevive à desativação do usuário. Sem índice, porque nenhuma consulta filtra por essas colunas.
  * `tbsss_auditoria` fica de fora: ela só recebe inclusões e já tem `ator` e `created_at`. `tbsss_controle` (CR-007) também: a própria linha guarda quem aplicou a versão e quando.
  * **Ator:** o mesmo domínio de `tbsss_auditoria.ator`: o login da sessão; `SYSTEM:<agent_id>` no daemon; `SYSTEM:init_db` no `init_db.py`; `SYSTEM:seed` no seed FAKE. `init_db` e `seed` não podem ser usados como `agent_id` (§8.12).
  * **Quem grava:** sempre a aplicação, no mesmo SQL da operação. Nenhum `UPDATE` toca `created_*`. O repositório recebe o ator por `auditoria['ator']` ou, nas operações sem auditoria, pelo parâmetro `ator=`. Sem ator, a operação é recusada com `RepoViolacao`, sem gravar nada (também no FAKE). Como `created_by` não tem `DEFAULT`, uma inserção manual precisa se identificar.
  * **Alteração de negócio** (grava `updated_*`): edição de cadastro; desativar e reativar; matriz de permissões (grava no perfil); homologação e vínculo de parâmetros (gravam no script); desbloquear, redefinir senha e trocar a própria senha; editar, pausar e retomar agendamento; pausa e conclusão automáticas do desdobro (§7.5); toda transição de status do ticket e o pedido de cancelamento (§5.6, §8.3, §8.7 a §8.9, §8.12); registro e parada do agente (§8.11, §8.12).
  * **Rotina técnica** (não grava `updated_*`): heartbeat do ticket e do agente; gravação do log (`log_output`, `log_truncado`); registro do PID (§8.4); contadores e bloqueio automático do login e o rehash da senha (§4.2); avanço de `proxima_execucao`, `ultima_execucao` e `ultimo_ticket_id` no desdobro.
  * **Vínculos:** `perfil_func`, `perfil_amb`, `perfil_scr` e `script_amb` são gravados por **diferença** (só insere os novos e só apaga os removidos), e quem fica mantém o `created_*`. `script_param` é apagado e reinserido, porque a UK `(script_id, ordem)` não permite trocar a ordem com `UPDATE`, mas cada parâmetro que continua leva o `created_*` anterior, e o `updated_*` dele só muda se `ordem`, `obrigatorio` ou `valor_padrao_sub` mudar.
  * **Tickets e agendamentos:** `tickets.created_by` é o login do solicitante na criação manual e na reexecução, e `SYSTEM:<agent_id>` no desdobro; o `ticket_resp` recebe o mesmo `created_by` do ticket. `agendamentos.created_by` guarda o criador original; `usuario_id` continua sendo quem salvou por último (§7.6).
  * As quatro colunas **não** entram na `versao` do formulário, no `esperado` do repositório nem no `detalhe` da auditoria. A trilha completa continua na auditoria (§4.4). As colunas guardam só a criação e a **última** alteração, mas não são purgadas.
  * **Na tela:** quadro **Registro** no formulário de edição de ambientes, perfis, usuários, parâmetros, scripts e agendamentos, e no detalhe do ticket (§5.7). Ele mostra "Criado em {data} por {ator}" e "Última alteração em {data} por {ator}" ou "Nunca alterado". `SYSTEM:<agent_id>` aparece como "Sistema (agente {agent_id})", `SYSTEM:init_db` como "Sistema (instalação)", `SYSTEM:purge` como "Sistema (limpeza)" e `SYSTEM:seed` como "Sistema (dados de demonstração)". As listas não mostram essas colunas.
  * **Quem vê o login (CR-007, D6):** o login do ator só aparece para quem tem `VER_AUDITORIA` ou é administrador. Para os demais, o ator aparece como "você" (quando é o próprio usuário), "Sistema (…)" (atores do sistema) ou "outra pessoa". As datas aparecem para todos. O mascaramento é feito no servidor (`ui_helpers.registro(reg, ctx)`); o login de terceiros nunca vai para o HTML de quem não pode vê-lo.
  * **Solicitante e responsável (CR-008, E5/R-35):** a mesma regra vale para o **solicitante** do ticket ("solicitado por" no detalhe e a coluna da lista de tickets, inclusive o fragmento `.load`) e para o **responsável** da regra de agendamento (lista, formulário, aviso de outro responsável e agenda). O service entrega o texto já mascarado por `ui_helpers.ator_visivel(login, ctx)`: o login para quem tem `VER_AUDITORIA` ou é administrador; "você" para o próprio usuário; "Sistema (…)" para atores do sistema; "outra pessoa" para os demais. Os filtros por solicitante continuam aceitando o login digitado (quem digita já o conhece) e não revelam o login nos resultados. Ficam fora da regra as telas que só existem para gerir pessoas (`CAD_USUARIOS`, e a lista de usuários afetados no formulário de perfis, `CAD_PERFIS`), em que o login é o próprio dado cadastrado.
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
* **Listagens com `total` limitado (CR-007, R-29):** o `COUNT` das listagens paginadas para em 10.001 (`ROWNUM <= 10001` no Oracle, o mesmo limite no FAKE). Acima de 10.000, a tela mostra "mais de 10.000 registros" e a paginação não oferece "Última". O repositório devolve `total_limitado = True` nesse caso.
* **LOBs (CR-007, R-29):** todo CLOB (`tbsss_tickets.parametros_enviados`, `tbsss_tickets.log_output` e `tbsss_agendamentos.parametros_json`) tem cláusula de armazenamento explícita (`SECUREFILE (CACHE)` ou `BASICFILE`, §11.1). Num banco AL32UTF8, o CLOB guarda AL16UTF16, cerca de 2 bytes por caractere: a fórmula de dimensionamento está no `IMPLANTACAO.md`.
* **Edição de agendamento:** ao salvar uma alteração, `usuario_id` passa a ser o **editor**, que precisa ter `pode_executar` vigente para o script e o ambiente da regra. A regra sempre roda sob os privilégios de quem a definiu por último, o que impede um usuário de reaproveitar privilégios de outro editando a regra dele. A alteração é auditada com o `usuario_id` anterior e o novo. Script e ambiente da regra não mudam na edição (§7.6).

### 1. `tbsss_ambientes`
* PK `pk_tbsss_ambientes` · UK `uk_tbsss_amb_nome (nome)`
* **CK:**
  * `ck_tbsss_amb_ativo`
  * `ck_tbsss_amb_nome (REGEXP_LIKE(nome, '^[A-Z0-9_]{1,30}$'))`; o nome `INTERNO` é reservado à pasta dos logs sem ambiente (CR-009) e é recusado pelo cadastro (`admin_ambientes_service`), sem constraint no banco
  * `ck_tbsss_amb_conexao (conexao IS NULL OR INSTR(conexao, '@') = 0)`
  * `ck_tbsss_amb_upd` (colunas de registro, CR-006)
* Trigger extra: `tr_tbsss_amb_bu` (nome imutável)
* **Colunas:**
  * `id`
  * `nome VARCHAR2(30 CHAR) NOT NULL`
  * `descricao VARCHAR2(100 CHAR)`
  * `conexao VARCHAR2(250 CHAR)` (somente DSN, opcional)
  * `ativo CHAR(1) DEFAULT 'S' NOT NULL`
  * `created_at DATE DEFAULT SYSDATE NOT NULL`
  * `created_by VARCHAR2(40 CHAR) NOT NULL` (CR-006)
  * `updated_at DATE` (CR-006)
  * `updated_by VARCHAR2(40 CHAR)` (CR-006)
* **Validação na UI** (`admin_ambientes_service.py`):
  * `nome` segue a CK à risca. Letras minúsculas, espaços (inclusive nas pontas) ou outros caracteres são **rejeitados** com mensagem, não convertidos. O `nome` é imutável depois de criado: o campo fica somente leitura e o servidor ignora o valor enviado.
  * `conexao` é opcional, como a coluna. Quando preenchida, aceita apenas:
    * Easy Connect: `^[A-Za-z0-9._-]+:[0-9]{1,5}/[A-Za-z0-9._-]+$`;
    * alias TNS: `^[A-Za-z0-9._-]{1,128}$`.
  * Um `@` é recusado com "Informe apenas o DSN; credenciais ficam no secrets.cfg."
  * `descricao` é opcional, com até 100 caracteres e sem caracteres de controle.

### 2. `tbsss_perfis`
* PK `pk_tbsss_perfis` · UK `uk_tbsss_per_nome (nome)`
* CK: `ck_tbsss_per_adm`, `ck_tbsss_per_ativo`, `ck_tbsss_per_versao (perm_versao >= 1)`, `ck_tbsss_per_upd`
* **Colunas:**
  * `id`
  * `nome VARCHAR2(30 CHAR) NOT NULL` (na UI: `^[A-Z0-9_]{1,30}$`, mutável, único)
  * `descricao VARCHAR2(100 CHAR)`
  * `is_admin CHAR(1) DEFAULT 'N' NOT NULL`
  * `perm_versao NUMBER(10) DEFAULT 1 NOT NULL`
  * `ativo CHAR(1) DEFAULT 'S' NOT NULL`
  * `created_at DATE DEFAULT SYSDATE NOT NULL` (CR-006)
  * `created_by VARCHAR2(40 CHAR) NOT NULL` (CR-006)
  * `updated_at DATE` (CR-006)
  * `updated_by VARCHAR2(40 CHAR)` (CR-006)

### 3. `tbsss_funcionalidades`
* PK `pk_tbsss_funcionalidades` · UK `uk_tbsss_fnc_codigo (codigo)`
* CK: `ck_tbsss_fnc_ativo`, `ck_tbsss_fnc_upd`
* **Colunas:**
  * `id`
  * `codigo VARCHAR2(30 CHAR) NOT NULL`
  * `nome VARCHAR2(60 CHAR) NOT NULL`
  * `modulo VARCHAR2(30 CHAR) NOT NULL`
  * `descricao VARCHAR2(150 CHAR)`
  * `ativo CHAR(1) DEFAULT 'S' NOT NULL`
  * `created_at DATE DEFAULT SYSDATE NOT NULL` (CR-006)
  * `created_by VARCHAR2(40 CHAR) NOT NULL` (CR-006)
  * `updated_at DATE` (CR-006)
  * `updated_by VARCHAR2(40 CHAR)` (CR-006)

### 4. `tbsss_perfil_func`
* PK `pk_tbsss_perfil_func` · UK `uk_tbsss_pfnc_per_fnc (perfil_id, funcionalidade_id)`
* FK `fk_tbsss_pfnc_per → tbsss_perfis(id) ON DELETE CASCADE` (coberta pela UK)
* FK `fk_tbsss_pfnc_fnc → tbsss_funcionalidades(id) ON DELETE CASCADE` · IX `ix_tbsss_pfnc_fnc (funcionalidade_id)`
* CK: `ck_tbsss_pfnc_upd` (colunas de registro, CR-006)
* **Colunas:** `id`, `perfil_id NUMBER(10) NOT NULL`, `funcionalidade_id NUMBER(10) NOT NULL`, `created_at DATE DEFAULT SYSDATE NOT NULL`, `created_by VARCHAR2(40 CHAR) NOT NULL`, `updated_at DATE`, `updated_by VARCHAR2(40 CHAR)` (colunas de registro, CR-006)

### 5. `tbsss_perfil_amb`
* PK `pk_tbsss_perfil_amb` · UK `uk_tbsss_pamb_per_amb (perfil_id, ambiente_id)`
* FK `fk_tbsss_pamb_per → tbsss_perfis(id) ON DELETE CASCADE` (coberta pela UK)
* FK `fk_tbsss_pamb_amb → tbsss_ambientes(id) ON DELETE CASCADE` · IX `ix_tbsss_pamb_amb (ambiente_id)`
* CK: `ck_tbsss_pamb_upd` (colunas de registro, CR-006)
* **Colunas:** `id`, `perfil_id NUMBER(10) NOT NULL`, `ambiente_id NUMBER(10) NOT NULL`, `created_at DATE DEFAULT SYSDATE NOT NULL`, `created_by VARCHAR2(40 CHAR) NOT NULL`, `updated_at DATE`, `updated_by VARCHAR2(40 CHAR)` (colunas de registro, CR-006)

### 6. `tbsss_scripts`
* PK `pk_tbsss_scripts` · UK `uk_tbsss_scr_nome (nome)`
* **CK:**
  * `ck_tbsss_scr_tparam (tipo_param IN ('NOMEADO','SEQUENCIAL','NENHUM'))`
  * `ck_tbsss_scr_ativo`
  * `ck_tbsss_scr_paral (max_qtd_parallel_env BETWEEN 1 AND 999)`
  * `ck_tbsss_scr_int (interpretador IN ('PYTHON3','BASH','SH'))`
  * `ck_tbsss_scr_path (SUBSTR(path_file, 1, 1) = '/' AND INSTR(path_file, '..') = 0 AND INSTR(path_file, '//') = 0 AND INSTR(path_file, '\') = 0)` (formato do §8.5, CR-005)
  * `ck_tbsss_scr_tmout (timeout_seg IS NULL OR timeout_seg > 0)`
  * `ck_tbsss_scr_upd` (colunas de registro, CR-006)
* **Colunas:**
  * `id`
  * `nome VARCHAR2(60 CHAR) NOT NULL`
  * `descricao VARCHAR2(200 CHAR)`
  * `grupo VARCHAR2(30 CHAR)`
  * `categoria VARCHAR2(30 CHAR)`
  * `etapa VARCHAR2(30 CHAR)`
  * `interpretador VARCHAR2(15 CHAR) NOT NULL` (lógico; o executável é mapeado por agente, §8.5)
  * `path_file VARCHAR2(500 CHAR) NOT NULL` (caminho absoluto do script, §8.5, CR-005)
  * `tipo_param VARCHAR2(15 CHAR) DEFAULT 'NOMEADO' NOT NULL`
  * `max_qtd_parallel_env NUMBER(3) DEFAULT 1 NOT NULL`
  * `timeout_seg NUMBER(7)`
  * `ativo CHAR(1) DEFAULT 'S' NOT NULL`
  * `created_at DATE DEFAULT SYSDATE NOT NULL` (CR-006)
  * `created_by VARCHAR2(40 CHAR) NOT NULL` (CR-006)
  * `updated_at DATE` (CR-006)
  * `updated_by VARCHAR2(40 CHAR)` (CR-006)

### 7. `tbsss_perfil_scr`
* PK `pk_tbsss_perfil_scr` · UK `uk_tbsss_pscr_per_scr (perfil_id, script_id)`
* FK `fk_tbsss_pscr_per → tbsss_perfis(id) ON DELETE CASCADE` (coberta pela UK)
* FK `fk_tbsss_pscr_scr → tbsss_scripts(id) ON DELETE CASCADE` · IX `ix_tbsss_pscr_scr (script_id)`
* CK: `ck_tbsss_pscr_upd` (colunas de registro, CR-006)
* **Colunas:** `id`, `perfil_id NUMBER(10) NOT NULL`, `script_id NUMBER(10) NOT NULL`, `created_at DATE DEFAULT SYSDATE NOT NULL`, `created_by VARCHAR2(40 CHAR) NOT NULL`, `updated_at DATE`, `updated_by VARCHAR2(40 CHAR)` (colunas de registro, CR-006)

### 8. `tbsss_script_amb` (homologação de script por ambiente)
* PK `pk_tbsss_script_amb` · UK `uk_tbsss_samb_scr_amb (script_id, ambiente_id)`
* FK `fk_tbsss_samb_scr → tbsss_scripts(id) ON DELETE CASCADE` (coberta pela UK)
* FK `fk_tbsss_samb_amb → tbsss_ambientes(id) ON DELETE CASCADE` · IX `ix_tbsss_samb_amb (ambiente_id)`
* CK: `ck_tbsss_samb_upd` (colunas de registro, CR-006)
* **Colunas:** `id`, `script_id NUMBER(10) NOT NULL`, `ambiente_id NUMBER(10) NOT NULL`, `created_at DATE DEFAULT SYSDATE NOT NULL`, `created_by VARCHAR2(40 CHAR) NOT NULL`, `updated_at DATE`, `updated_by VARCHAR2(40 CHAR)` (colunas de registro, CR-006)

### 9. `tbsss_usuarios`
* PK `pk_tbsss_usuarios` · UK `uk_tbsss_usr_login (login)`
* FK `fk_tbsss_usr_per → tbsss_perfis(id)` · IX `ix_tbsss_usr_per (perfil_id)`
* **CK:**
  * `ck_tbsss_usr_ativo`
  * `ck_tbsss_usr_login (REGEXP_LIKE(login, '^[a-z0-9._-]{3,30}$'))`
  * `ck_tbsss_usr_tent (tentativas_falha >= 0)`
  * `ck_tbsss_usr_epoch (sessao_epoch >= 0)` (CR-008)
  * `ck_tbsss_usr_upd` (colunas de registro, CR-006)
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
  * `sessao_epoch NUMBER(10) DEFAULT 0 NOT NULL` (CR-008, E2/R-23: época das sessões; incrementada no logout, na troca e na redefinição de senha, na desativação e na troca de perfil, §4.2. O incremento isolado do logout e da troca de senha pelo próprio usuário é rotina técnica e não grava `updated_*`; nas alterações de negócio, vai junto com o `updated_*` delas)
  * `ativo CHAR(1) DEFAULT 'S' NOT NULL`
  * `created_at DATE DEFAULT SYSDATE NOT NULL`
  * `created_by VARCHAR2(40 CHAR) NOT NULL` (CR-006)
  * `updated_at DATE` (CR-006)
  * `updated_by VARCHAR2(40 CHAR)` (CR-006)

### 10. `tbsss_parametros`
* PK `pk_tbsss_parametros` · UK `uk_tbsss_prm_codigo (codigo)`
* **CK:**
  * `ck_tbsss_prm_tcomp (tipo_componente IN ('TEXT','NUMBER','DATE','SELECT','CHECKBOX'))`
  * `ck_tbsss_prm_ativo`
  * `ck_tbsss_prm_sens (sensivel IN ('S','N'))`
  * `ck_tbsss_prm_codigo (REGEXP_LIKE(codigo, '^[a-z0-9_]{1,30}$'))`
  * `ck_tbsss_prm_flag (param_nomeado IS NULL OR REGEXP_LIKE(param_nomeado, '^-{1,2}[A-Za-z0-9][A-Za-z0-9_-]{0,27}$'))`
  * `ck_tbsss_prm_upd` (colunas de registro, CR-006)
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
  * `created_at DATE DEFAULT SYSDATE NOT NULL` (CR-006)
  * `created_by VARCHAR2(40 CHAR) NOT NULL` (CR-006)
  * `updated_at DATE` (CR-006)
  * `updated_by VARCHAR2(40 CHAR)` (CR-006)

### 11. `tbsss_script_param`
* PK `pk_tbsss_script_param` · UK `uk_tbsss_sprm_scr_prm (script_id, parametro_id)` · UK `uk_tbsss_sprm_scr_ord (script_id, ordem)`
* FK `fk_tbsss_sprm_scr → tbsss_scripts(id) ON DELETE CASCADE` (coberta pela UK)
* FK `fk_tbsss_sprm_prm → tbsss_parametros(id)` · IX `ix_tbsss_sprm_prm (parametro_id)`
* CK: `ck_tbsss_sprm_obrig`, `ck_tbsss_sprm_ordem (ordem >= 1)`, `ck_tbsss_sprm_upd`
* **Colunas:**
  * `id`
  * `script_id NUMBER(10) NOT NULL`
  * `parametro_id NUMBER(10) NOT NULL`
  * `ordem NUMBER(3) NOT NULL`
  * `obrigatorio CHAR(1) DEFAULT 'S' NOT NULL`
  * `valor_padrao_sub VARCHAR2(100 CHAR)`
  * `created_at DATE DEFAULT SYSDATE NOT NULL` (CR-006)
  * `created_by VARCHAR2(40 CHAR) NOT NULL` (CR-006)
  * `updated_at DATE` (CR-006)
  * `updated_by VARCHAR2(40 CHAR)` (CR-006)

### 12. `tbsss_agendamentos`
* PK `pk_tbsss_agendamentos`
* **FKs e índices:**
  * FK `fk_tbsss_agd_scr → tbsss_scripts(id)` · IX `ix_tbsss_agd_scr (script_id)`
  * FK `fk_tbsss_agd_usr → tbsss_usuarios(id)` · IX `ix_tbsss_agd_usr (usuario_id)`
  * FK `fk_tbsss_agd_amb → tbsss_ambientes(nome)` · IX `ix_tbsss_agd_amb (ambiente)`
  * Polling: IX `ix_tbsss_agd_prox (ativo, proxima_execucao, id)` (o `id` atende a paginação por chave do §7.5, CR-007)
* **CK:**
  * `ck_tbsss_agd_trec (tipo_recorrencia IN ('UNICA','DIARIA','SEMANAL','MENSAL','CRON'))`
  * `ck_tbsss_agd_prio (prioridade BETWEEN 1 AND 4)`
  * `ck_tbsss_agd_ativo`
  * `ck_tbsss_agd_dia (dia_mes IS NULL OR dia_mes BETWEEN 1 AND 31)`
  * `ck_tbsss_agd_hora (hora_execucao IS NULL OR REGEXP_LIKE(hora_execucao, '^([01][0-9]|2[0-3]):[0-5][0-9]$'))`
  * `ck_tbsss_agd_dsem (dias_semana IS NULL OR REGEXP_LIKE(dias_semana, '^[1-7](,[1-7]){0,6}$'))`
  * `ck_tbsss_agd_fim (data_fim IS NULL OR data_fim >= data_inicio)`
  * `ck_tbsss_agd_pausa (pausa_motivo IS NULL OR pausa_motivo IN ('USUARIO_INATIVO','SEM_PERMISSAO','SCRIPT_INATIVO','AMBIENTE_INATIVO','PARAM_INVALIDO','CRON_INVALIDO','CONCLUIDO','MANUAL','ERRO_INTERNO'))` (`ERRO_INTERNO`: CR-007, R-08)
  * `ck_tbsss_agd_upd` (colunas de registro, CR-006)
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
  * `created_by VARCHAR2(40 CHAR) NOT NULL` (CR-006)
  * `updated_at DATE` (CR-006)
  * `updated_by VARCHAR2(40 CHAR)` (CR-006)
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
* Retenção e ordem da lista de tickets: IX `ix_tbsss_tck_crt (created_at, id)`. O `id` no índice entrega o desempate de `created_at DESC, id DESC` sem ordenar a tabela inteira; o EXPLAIN com 1 milhão de tickets mostrava `TABLE ACCESS FULL` só com `created_at` (F7.3)
* Histórico e últimas execuções (§5.8): IX `ix_tbsss_tck_hist (script_id, created_at)` (CR-007, R-29)
* **Ocorrência do agendamento (CR-007, R-27):** índice **único** baseado em função `ix_tbsss_tck_ocor ((CASE WHEN agendamento_id IS NOT NULL THEN agendamento_id END), (CASE WHEN agendamento_id IS NOT NULL THEN scheduled_at END))`. Contém só os tickets de agendamento e impede dois tickets para a mesma ocorrência da mesma regra. A reexecução (§5.5) não herda `agendamento_id`, então não entra no índice.
* **CK:**
  * `ck_tbsss_tck_stat (status IN ('PENDING','RUNNING','SUCCESS','FAILED','CANCELLED'))`
  * `ck_tbsss_tck_prio (prioridade BETWEEN 1 AND 4)`
  * `ck_tbsss_tck_cancreq (cancel_requested IN ('S','N'))`
  * `ck_tbsss_tck_logtr (log_truncado IN ('S','N'))`
  * `ck_tbsss_tck_logoff (log_offset_chars >= 0)` (offset CLOB não negativo)
  * `ck_tbsss_tck_motivo (status_motivo IS NULL OR status_motivo IN ('EXIT_OK','EXIT_ERROR','KILLED_SIGNAL','TIMEOUT','NODE_OFFLINE','ORPHAN_PROCESS','FENCED','PRECHECK_FAILED','SPAWN_ERROR','LOG_LIMIT','SHUTDOWN','CANCEL_USER'))`
  * `ck_tbsss_tck_upd` (colunas de registro, CR-006)
* **Colunas:**
  * `id`
  * `script_id NUMBER(10) NOT NULL`
  * `ambiente VARCHAR2(30 CHAR) NOT NULL`
  * `solicitante VARCHAR2(30 CHAR) NOT NULL`
  * `ip_origem VARCHAR2(45 CHAR)`
  * `agente_id VARCHAR2(30 CHAR)`
  * `process_id NUMBER(10)` (CR-007: comporta PIDs de até 10 dígitos, como no HP-UX)
  * `process_start NUMBER(20)`
  * `status VARCHAR2(15 CHAR) DEFAULT 'PENDING' NOT NULL`
  * `prioridade NUMBER(1) DEFAULT 2 NOT NULL`
  * `cancel_requested CHAR(1) DEFAULT 'N' NOT NULL`
  * `status_motivo VARCHAR2(30 CHAR)`
  * `parent_ticket_id NUMBER(10)`
  * `agendamento_id NUMBER(10)`
  * `parametros_enviados CLOB NOT NULL`
  * `log_output CLOB`
  * `log_offset_chars NUMBER(20) DEFAULT 0 NOT NULL` (posição confirmada em caracteres CLOB, independente do teto em bytes UTF-8)
  * `log_truncado CHAR(1) DEFAULT 'N' NOT NULL`
  * `return_code NUMBER(6)`
  * `scheduled_at DATE DEFAULT SYSDATE NOT NULL`
  * `started_at DATE`
  * `heartbeat_at DATE`
  * `finished_at DATE`
  * `created_at DATE DEFAULT SYSDATE NOT NULL`
  * `created_by VARCHAR2(40 CHAR) NOT NULL` (CR-006)
  * `updated_at DATE` (CR-006)
  * `updated_by VARCHAR2(40 CHAR)` (CR-006)
* **Armazenamento:** `LOB (parametros_enviados, log_output) STORE AS SECUREFILE (CACHE)`, que exige tablespace ASSM e `COMPATIBLE >= 11.1`. `init_db.py --lob-basicfile` aplica o fallback BASICFILE.

### 14. `tbsss_ticket_resp`
* PK `pk_tbsss_ticket_resp` · UK `uk_tbsss_trsp_tck_prm (ticket_id, parametro_id)`
* FK `fk_tbsss_trsp_tck → tbsss_tickets(id) ON DELETE CASCADE` (coberta pela UK)
* FK `fk_tbsss_trsp_prm → tbsss_parametros(id)` · IX `ix_tbsss_trsp_prm (parametro_id)`
* CK: `ck_tbsss_trsp_upd` (colunas de registro, CR-006)
* **Colunas:**
  * `id`
  * `ticket_id NUMBER(10) NOT NULL`
  * `parametro_id NUMBER(10) NOT NULL`
  * `valor_resposta VARCHAR2(500 CHAR)`
  * `created_at DATE DEFAULT SYSDATE NOT NULL`
  * `created_by VARCHAR2(40 CHAR) NOT NULL` (CR-006)
  * `updated_at DATE` (CR-006)
  * `updated_by VARCHAR2(40 CHAR)` (CR-006)

### 15. `tbsss_agentes`
* PK `pk_tbsss_agentes` · UK `uk_tbsss_agt_codigo (codigo)`
* CK: `ck_tbsss_agt_stat (status IN ('ATIVO','PARADO'))`, `ck_tbsss_agt_upd` (colunas de registro, CR-006)
* **Colunas:**
  * `id`
  * `codigo VARCHAR2(30 CHAR) NOT NULL` (= `agent_id`)
  * `hostname VARCHAR2(255 CHAR) NOT NULL` (CR-007: comporta um FQDN)
  * `pid_daemon NUMBER(10)` (CR-008, R-13: como `tbsss_tickets.process_id`; PIDs de 9 e 10 dígitos em HP-UX e AIX)
  * `versao VARCHAR2(20 CHAR)`
  * `ambientes VARCHAR2(1000 CHAR)` (CR-007; `ambientes_atendidos` que não caiba é recusado na configuração)
  * `plataforma VARCHAR2(10 CHAR)`, com CK `ck_tbsss_agt_plat (plataforma IS NULL OR plataforma IN ('LINUX','UNIX'))`
  * `interpretadores VARCHAR2(100 CHAR)` (lista separada por vírgula dos interpretadores lógicos suportados)
  * `status VARCHAR2(10 CHAR) DEFAULT 'ATIVO' NOT NULL`
  * `iniciado_em DATE`
  * `heartbeat_at DATE`
  * `config_criticos VARCHAR2(400 CHAR)` (CR-007, R-23: configuração crítica do agente em texto canônico, §8.12)
  * `created_at DATE DEFAULT SYSDATE NOT NULL`
  * `created_by VARCHAR2(40 CHAR) NOT NULL` (CR-006)
  * `updated_at DATE` (CR-006)
  * `updated_by VARCHAR2(40 CHAR)` (CR-006)

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
* **Ações:** `LOGIN_OK`, `LOGIN_FALHA`, `LOGIN_BLOQUEIO`, `LOGOUT`, `TICKET_CRIAR`, `TICKET_CANCELAR`, `TICKET_REEXECUTAR`, `CAD_INSERIR`, `CAD_ALTERAR`, `CAD_DESATIVAR`, `PERM_ALTERAR`, `AGD_PAUSAR`, `AGENTE_INICIO`, `AGENTE_FIM`, `PURGE`, `AUD_EXPORTAR` (exportação CSV da trilha, F6.1), `ESQUEMA_MIGRAR` (migração de versão do esquema, CR-007). O catálogo é mantido em código (`auditoria_service.ACOES`) e não usa CK, para permitir extensão.
* A tabela não tem FKs intencionalmente: a trilha sobrevive a exclusões.
* **Privilégios (CR-007, D1b):** web com `SELECT` e `INSERT`; agente só com `INSERT`; purge com `SELECT`, `INSERT` e `DELETE`. Nenhuma conta tem `UPDATE`.

### 17. `tbsss_controle` (CR-007, D4)
* PK `pk_tbsss_controle`
* **CK:**
  * `ck_tbsss_ctl_id (id = 1)`: a tabela tem uma única linha
  * `ck_tbsss_ctl_versao (versao_esquema >= 1)`
* **Colunas:**
  * `id`
  * `versao_esquema NUMBER(6) NOT NULL` (versão do esquema aplicada; o código espera `sql_ident.VERSAO_ESQUEMA`)
  * `versao_aplicada_em DATE NOT NULL`
  * `versao_aplicada_por VARCHAR2(40 CHAR) NOT NULL` (`SYSTEM:init_db`)
  * `purge_dono VARCHAR2(40 CHAR)` (agente que detém a concessão do purge, §11.3)
  * `purge_concessao_ate DATE`
* Sem colunas de registro (CR-006): a própria linha guarda quem aplicou a versão e quando.
* **Uso:** o `init_db.py` cria a linha e a atualiza a cada migração (§11.1); web e agente leem `versao_esquema` na subida e recusam versão diferente (§8.12); o `purge.py` usa a concessão (§11.3).
* **Privilégios:** web e agente com `SELECT`; purge com `SELECT` e `UPDATE` (só as colunas `purge_*`).

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
* **Conexão do `init_db`:** com a conta **dona do esquema** (`--usuario-dono`, padrão o `owner`), senha lida por `getpass` ou de `SSS_INIT_DB_PASSWORD`, nunca de arquivo nem de argumento. É a única conta com privilégio de DDL (CR-007, D1b).
* **Versão do esquema e migração (CR-007, D4):**
  * base vazia: cria tudo e grava `tbsss_controle` com `versao_esquema = sql_ident.VERSAO_ESQUEMA`;
  * base com versão menor: aplica, em ordem, as migrações `scripts/migracoes/m<NNNN>_<descricao>.py` (cada uma com `VERSAO`, idempotente, e auditada como `ESQUEMA_MIGRAR`, com a versão no `detalhe`), atualizando `tbsss_controle` ao fim de cada uma;
  * base com versão maior que a do código: aborta (aplicação mais antiga que o banco);
  * **Versão 1 aberta até a primeira produção (AGENTS §4.16, ajustado no F7.3):** antes da primeira implantação em produção, mudanças de esquema entram direto na versão 1, sem migração. Os bancos de DEV (ex.: `GFPR`) são refeitos pelo ciclo `02_rollback` → `01_implantar` → `99_validar`. A primeira produção congela a versão 1;
  * depois das fases, **conferência do esquema real contra o registro**: colunas (`ALL_TAB_COLUMNS`: tipo, tamanho, `NULLABLE`, `DATA_DEFAULT`), CKs (`SEARCH_CONDITION`), índices (colunas e expressões) e objetos inválidos (`ALL_OBJECTS.STATUS = 'INVALID'` e `ALL_ERRORS`, inclusive triggers compiladas com erro, que o modo Thin só reporta como aviso). Divergência aborta com a lista; o `init_db` nunca corrige sozinho um objeto existente.
  * **Normalização antes de comparar (CR-008, R-14):** o Oracle devolve os textos reescritos, então a comparação literal acusaria divergência sempre. Os dois lados (o do dicionário e o do registro `sql_ident`) passam pela mesma função `sql_ident.normalizar_expressao`: remove aspas duplas, converte para maiúsculas fora de literais entre aspas simples, colapsa espaços, tabulações e quebras de linha num espaço, remove espaços junto de `(`, `)` e `,`, e tira espaços nas pontas (o `DATA_DEFAULT` costuma vir com espaço ou quebra final). CKs de sistema `SYS_C%` cuja condição é só `"<COLUNA>" IS NOT NULL` são ignoradas (repetem o `NULLABLE`). Expressões de índice baseado em função são lidas de `ALL_IND_EXPRESSIONS.COLUMN_EXPRESSION` (`LONG`, lido como texto) e comparadas normalizadas, coluna a coluna, na ordem de `COLUMN_POSITION`. O F7.1 testa a normalização com textos reais do 11gR2 e, com `SSS_TEST_DSN`, cria o esquema e confere que a conferência dá zero divergências.
* **Recriação do esquema:** não há opção `--recreate` nesta versão. O CR-007 R-32 define pré-condições, mas não especifica quais objetos ou dados seriam removidos; a opção só poderá ser implementada após essa semântica ser definida nesta seção.
* **Estatísticas (CR-007, R-29):** não são coletadas em tabela vazia (gerariam planos com 0 linhas). O `--stats` só coleta tabelas com linhas; o `IMPLANTACAO.md` exige o job automático de estatísticas do banco ativo, ou um job próprio, para o esquema.
* **Códigos de saída:** 0 sucesso (inclusive tudo `SKIP`), 1 falha de fase, 2 configuração inválida, 3 divergência de esquema ou versão.
* **Opções:**
  * `--dry-run` imprime o DDL sem executar;
  * `--lob-basicfile` aplica o fallback de LOB;
  * `--gerar-sql <pasta>` (ou via `scripts/gerar_scripts_sql.py`): gera scripts SQL puros e autocontidos (`01_implantar_sss.sql` com DDL/DML de seed/estatísticas, `02_rollback_sss.sql` para desinstalação total e `99_validar_implantacao.sql`, só de leitura) para execução direta por DBAs via SQL*Plus em homologação/produção sem execução Python no servidor de banco;
  * não há opção de `DROP` nem `--recreate`, inclusive em DEV. Objetos existentes nunca são removidos automaticamente por `init_db.py`.
* **Seed Completo** via `MERGE` (idempotente):
  * **Funcionalidades e Controle:** catálogo canônico de 10 funcionalidades (§4.3.D) e a linha de `tbsss_controle` (versão do esquema e auditoria de versão).
  * **Ambientes Padrão (`tbsss_ambientes`):** os 5 ambientes homologados (`CLONE2`, `CLONE1`, `CLONE6`, `CLONE7`, `GFPREPROD`).
  * **Dicionário de Parâmetros (`tbsss_parametros`):** 19 parâmetros reutilizáveis (`TEXT`, `NUMBER`, `SELECT`).
  * **Catálogo de Scripts Utilitários (`tbsss_scripts`):** 14 rotinas de manipulação de arquivos em Python 3 e Shell POSIX (`zipar_arquivos`, `descompactar_zip`, `quebrar_arquivo`, `juntar_arquivos`, `converter_encoding`, `substituir_texto`, `remover_duplicadas`, `gerar_hash_arquivo`, `compactar_targz`, `descompactar_targz`, `contar_linhas_arquivo`, `filtrar_linhas`, `ordenar_arquivo`, `limpar_linhas_vazias`). Especificação completa em `docs/SCRIPTS_UTILITARIOS.md`.
  * **Homologação por Ambiente (`tbsss_script_amb`):** todas as 14 rotinas homologadas para os 5 ambientes (70 registros).
  * **Parâmetros de Rotinas (`tbsss_script_param`):** 38 vínculos com ordens e valores padrão específicos.
  * **Perfis de Acesso (`tbsss_perfis`):** os 4 perfis padrão (`ADMINISTRADOR`, `OPERADOR_PROD`, `OPERADOR_HML`, `CONSULTA`), suas matrizes funcionais (`tbsss_perfil_func`), escopos de ambiente (`tbsss_perfil_amb`) e a liberação das 14 rotinas para todos os perfis (`tbsss_perfil_scr`, total de 56 registros).
  * **Usuários de Demonstração e Homologação (`tbsss_usuarios`):** os 4 operadores padrão do UI Freeze (`admin`, `op.prod`, `op.hml`, `consulta`) com senha padrão `Sss@Homolog2026!` (hash PBKDF2 com 200.000 iterações). O `MERGE` preserva senhas já trocadas.
  * **Governança de Dados:** metadados descritivos aplicados via `COMMENT ON TABLE` e `COMMENT ON COLUMN` para todas as tabelas e colunas, além de comentários em todas as triggers de integridade.
  * **Atores de Auditoria:** a inclusão grava `created_by = 'SYSTEM:init_db'`; quando o `MERGE` muda uma linha existente, grava `updated_*` com o mesmo ator; uma linha igual ao seed não é tocada (§10, CR-006).
* **Administrador inicial:** criado por padrão (`admin` / `ADMINISTRADOR`), ou customizado via `--admin-login` e senha lida de `getpass` ou de `SSS_BOOTSTRAP_ADMIN_PASSWORD`.
* **Script SQL de Produção Autônomo:** gerado em `docs/sql/01_implantar_sss.sql` para implantação direta via SQL*Plus por DBAs, contendo DDL, comentários de governança, DML de seed completo, coleta de estatísticas pelo otimizador e os GRANTs por papel da tabela abaixo, com tratamento de erro tolerante. Script de desinstalação total em `docs/sql/02_rollback_sss.sql`.
  * **Nenhum GRANT a PUBLIC:** `tbsss_usuarios` guarda `senha_hash`, e o banco pode ser compartilhado com outros sistemas.
  * **Contas dos papéis:** sem `--grants-para`, o gerador usa o `config.ini`: web e agente vêm de `[oracle] user`, purge de `[retencao] purge_user`. A conta do monitor fica no `secrets.cfg`, então só entra por `--grants-para`. Cada conta é validada como identificador Oracle, e `PUBLIC` é recusado.
  * Um papel sem conta, ou cuja conta é a dona do esquema, não recebe GRANT: o owner já tem todos os privilégios, e GRANT para si mesmo falha (ORA-01749). Cada caso fica registrado como comentário no script.
  * Uma instalação antiga que já tenha GRANTs a PUBLIC os perde no rollback (o `DROP TABLE` remove as concessões). Sem rollback, o DBA precisa revogá-los à mão.
* **Validação da implantação (`docs/sql/99_validar_implantacao.sql`):** gerada com os outros dois scripts, a partir do mesmo registro, com o owner e o prefixo do `config.ini` ou de `--owner`/`--prefixo`. Só faz leituras.
  * **Dicionário:** confere, pelos nomes do registro, as tabelas, sequences, triggers habilitadas, constraints habilitadas e índices válidos; e exige zero objetos inválidos e zero GRANTs a PUBLIC.
  * **Dados:** confere a versão do esquema contra `sql_ident.VERSAO_ESQUEMA` e o mínimo de linhas que o seed grava em cada tabela.
  * Cada verificação sai como "esperado × encontrado" com OK ou FALHA, e cada seção termina com um resumo.
  * As listagens de usuários, scripts, acesso por perfil e GRANTs **nunca** mostram `senha_hash`: só se a senha está definida (AGENTS §3.3).

  | Papel | Privilégios no esquema |
  |---|---|
  | web | `SELECT, INSERT, UPDATE` nos cadastros e agendamentos; `DELETE` só nas associações (`perfil_func`, `perfil_amb`, `perfil_scr`, `script_amb`, `script_param`); `SELECT, INSERT, UPDATE` em `tbsss_tickets`; `SELECT, INSERT` em `tbsss_ticket_resp` e `tbsss_auditoria`; `SELECT` em `tbsss_agentes` e `tbsss_controle`; `SELECT` nas sequences que usa |
  | agente | `SELECT` nos cadastros e associações (RBAC, catálogo e compilação do snapshot); `SELECT, UPDATE` em `tbsss_agendamentos`; `SELECT, INSERT, UPDATE` em `tbsss_tickets` e `tbsss_agentes`; `SELECT, INSERT` em `tbsss_ticket_resp`; `INSERT` em `tbsss_auditoria`; `SELECT` em `tbsss_controle`; `SELECT` nas sequences de tickets, respostas, agentes e auditoria |
  | purge | `SELECT, DELETE` em `tbsss_tickets` (a cascata remove `tbsss_ticket_resp`); `SELECT, INSERT, DELETE` em `tbsss_auditoria`; `SELECT, UPDATE (purge_dono, purge_concessao_ate)` em `tbsss_controle`; `SELECT` na sequence da auditoria |
  | monitor (CR-008, E3/R-04) | Só `SELECT`, e só nas tabelas que o `scripts/saude.py` consulta: `tbsss_agentes`, `tbsss_tickets`, `tbsss_agendamentos`, `tbsss_scripts`, `tbsss_ambientes`, `tbsss_controle` e `tbsss_auditoria`. Nenhum `INSERT`, `UPDATE` ou `DELETE`, e nenhuma sequence. Conta sugerida: `sss_monitor` |

  O papel agente lê `tbsss_usuarios` inteira, inclusive `senha_hash` (o Oracle 11g não tem `GRANT SELECT` por coluna). O risco é aceito no §14 (hash PBKDF2 com 200.000 iterações); restringir por view fica como melhoria (CR-008, R-30).

### 11.2 Esquema e testes

`scripts/test_db_schema.py` consome o mesmo registro de identificadores do `init_db.py` e falha se qualquer nome expandido com o `table_prefix` configurado (e com o prefixo de pior caso de 8 caracteres) exceder 30 caracteres. Os demais requisitos estão no `AGENTS.md` §7.

### 11.3 `scripts/purge.py` (retenção)

* Roda no servidor do agente, com a conta Oracle de purge (`[retencao] purge_user` e `[purge] password`, §4.1), e audita com o ator `SYSTEM:purge` (CR-007, R-21).
* **Concessão no banco:** só um nó purga tickets e auditoria por vez. Antes, o purge toma a concessão:
  ```sql
  UPDATE {owner}.tbsss_controle
     SET purge_dono = :dono, purge_concessao_ate = SYSDATE + 1/24
   WHERE id = 1
     AND (purge_concessao_ate IS NULL OR purge_concessao_ate < SYSDATE OR purge_dono = :dono)
  ```
  Com `rowcount = 0`, outro nó está purgando: o purge pula tickets e auditoria, registra INFO e sai com 0. A concessão é renovada a cada lote e liberada no fim com `SET purge_dono = NULL, purge_concessao_ate = NULL WHERE id = 1 AND purge_dono = :dono` (CR-008, R-27: zerar só o dono deixava outro nó esperando até 1 h). `:dono` é o `agent_id` do servidor.
* **`--dry-run` (F9.1):** não toma concessão nem lock local, não executa DML, não remove arquivos e não grava auditoria `PURGE`. Calcula os limites de retenção uma vez com `agora_banco()` e consulta as quantidades elegíveis de tickets, auditoria e pastas de logs locais; as consultas para identificar pastas de tickets `RUNNING` são somente leitura. O resumo identifica cada alvo e suas contagens como estimativas sujeitas a corrida.
* Remove tickets terminais com `created_at < SYSDATE - :ticket_retention_days`, em lotes:
  ```sql
  DELETE FROM {owner}.tbsss_tickets
   WHERE created_at < :limite
     AND status IN ('SUCCESS','FAILED','CANCELLED')
     AND ROWNUM <= :lote
  ```
  Com `COMMIT` por lote, até `rowcount = 0`.
* `tbsss_ticket_resp` é removida em cascata, e `parent_ticket_id` dos filhos vira `NULL`. `tbsss_agendamentos.ultimo_ticket_id` pode apontar para um ticket removido: o desdobro o trata como livre (§7.5).
* `tbsss_auditoria` usa `audit_retention_days` e o mesmo padrão de lote. Com `--exportar-auditoria <pasta>`, as linhas de cada lote são gravadas antes em CSV (mesmo formato da exportação do §4.4, arquivo `0600`), para arquivamento (CR-007, R-22).
* **Logs de execução** (§8.4, passo 3): remove as pastas de minuto `log_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI/` cuja data é anterior a `local_log_retention_days` dias, e depois as pastas de hora, dia, mês, ano, script e ambiente que ficarem vazias. A data vem do próprio caminho, não do `mtime`. A pasta `log_dir/interno/` (logs da aplicação) nunca é tocada pelo purge (§13, CR-009). Só entram pastas cujo caminho tem o formato exato `<ambiente>/<pasta>/AAAA/MM/DD/HH/MI`; qualquer outra coisa em `log_dir` é ignorada. **Uma pasta que contém o log de um ticket ainda `RUNNING` é mantida** (CR-007, R-32). Esta etapa roda em todo agente, sem concessão.
* A execução é agendada pelo cron no servidor do agente e auditada como `PURGE`: **sempre** que obtém a concessão, uma linha por tabela (`tbsss_tickets` e `tbsss_auditoria`), com a contagem no `detalhe`, inclusive `0 linhas` (CR-008, R-16). Sem a concessão, não audita (outro nó audita a sua execução).
* **Códigos de saída:** 0 sucesso (inclusive "outro nó está purgando"), 1 falha de banco, 2 configuração inválida, 3 falha na remoção de logs locais. O `scripts/saude.py` alerta se não houver `PURGE` auditado nos últimos 2 dias (§13).

---

## 12. Configuração

### 12.1 `instance/config.ini` (sem segredos; unidades no nome da chave)

```ini
[app]
sss_env = DEV                     ; DEV | HML | PROD

[oracle]
user = sss_web                    ; conta do papel deste nó: sss_web no web, sss_agente no agente (§4.1, D1b)
dsn = localhost:2424/servico_homolog
owner = openrisow
table_prefix = tbsss_
modo_driver = auto                ; auto (Thin → Thick → cx_Oracle) | thin | thick | cx_oracle (§2.3)
oracle_client_lib_dir =           ; somente macOS (DEV); no Linux/Unix usar ldconfig/LD_LIBRARY_PATH
call_timeout_ms = 30000
pool_min = 1
pool_max = 4

[secrets]
secrets_file = /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/instance

[agent]
agent_id = srv-linux-prod-01
ambientes_atendidos = PRODUCAO,HOMOLOGACAO
work_dir = /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/work
usuarios_execucao = PRODUCAO=sssprd,HOMOLOGACAO=ssshml   ; usuário do SO de cada ambiente (§8.0, D1); vazio só em DEV
exec_work_dir = /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/exec ; pasta base dos diretórios de trabalho dos scripts, uma subpasta por usuário de execução
interpretadores = PYTHON3=/usr/bin/python3,BASH=/bin/bash,SH=/bin/sh
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
fila_envelhecimento_min = 60       ; envelhecimento da prioridade na fila (§5.3); 0 desliga
log_dir_min_livre_mb = 1024       ; CR-008, R-25: sem claim com menos espaço livre em log_dir (§8.2)
child_locale = C.UTF-8
env_passthrough = ORACLE_HOME,TNS_ADMIN,NLS_LANG,LD_LIBRARY_PATH

[logging]
log_dir = /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/logs
level = INFO                      ; DEBUG | INFO | WARN | ERROR
app_log_max_bytes = 10485760       ; troca de arquivo do log da aplicação (§13)
app_log_retention_days = 30       ; pastas log_dir/interno/app/AAAA/MM/DD mais antigas são apagadas (§13)
max_log_size_bytes = 5242880
max_local_log_size_bytes = 52428800
local_log_retention_days = 30

[web]
session_idle_timeout_s = 1800
sessao_max_horas = 12             ; CR-008, E2: vida máxima da sessão desde o login (§4.2)
login_max_tentativas = 5
login_bloqueio_s = 900
log_poll_interval_s = 3
trusted_proxies =
allowed_origins = http://127.0.0.1:18000   ; lista separada por vírgula, validada contra Origin/Referer

[retencao]
ticket_retention_days = 180
audit_retention_days = 730
purge_batch_size = 1000
purge_user = sss_purge            ; conta Oracle do papel purge (§11.3, D1b)
```

Toda chave é validada por tipo e faixa na inicialização (`sss_config.py`). Chave desconhecida, ausente ou fora da faixa interrompe a subida com a chave e o motivo no log.

**Faixas de cada chave** (limites inclusivos; `enum` aceita só os valores listados no exemplo acima):

| Seção | Chave | Tipo | Faixa / formato |
|---|---|---|---|
| `[app]` | `sss_env` | enum | `DEV`, `HML`, `PROD` |
| `[app]` | `data_backend` | — | **removida no F7.3**: a aplicação usa sempre o Oracle; a presença da chave é recusada |
| `[oracle]` | `user`, `dsn` | texto | obrigatório, não vazio; com `sss_env` diferente de `DEV`, `user` diferente de `owner`, sem diferenciar maiúsculas (CR-008, R-29: a conta dona do esquema só faz DDL, D1b) |
| `[oracle]` | `owner` | texto | `^[A-Za-z][A-Za-z0-9_]{0,29}$` |
| `[oracle]` | `table_prefix` | texto | `^[a-z][a-z0-9_]{0,7}$`: começa com letra minúscula, até 8 caracteres (CR-007, R-31) |
| `[oracle]` | `modo_driver` (F7.0) | enum | `auto`, `thin`, `thick`, `cx_oracle` |
| `[oracle]` | `oracle_client_lib_dir` | caminho | opcional |
| `[oracle]` | `call_timeout_ms` | inteiro | 1 a 3.600.000 |
| `[oracle]` | `pool_min`, `pool_max` | inteiro | 1 a 1.000, com `pool_min <= pool_max` |
| `[secrets]` | `secrets_file` | caminho | obrigatório |
| `[agent]` | `agent_id` | texto | `^[A-Za-z0-9._-]{1,30}$`, diferente de `init_db`, `seed` e `purge` |
| `[agent]` | `ambientes_atendidos` | lista CSV | obrigatória; o texto inteiro com até 1.000 caracteres (coluna `tbsss_agentes.ambientes`) |
| `[agent]` | `usuarios_execucao` (CR-007) | lista `AMBIENTE=usuario` | obrigatória fora de DEV, cobrindo todos os `ambientes_atendidos`; usuário `^[a-z_][a-z0-9_-]{0,31}$`, diferente de `root`. Vazia em DEV = execução com o próprio usuário, com WARN |
| `[agent]` | `exec_work_dir` (CR-007) | caminho | obrigatório fora de DEV; fora das pastas do sistema e diferente de `work_dir` e `log_dir` |
| `[agent]` | `fila_envelhecimento_min` (CR-007) | inteiro | 0 a 1.440 (0 desliga) |
| `[agent]` | `interpretadores` (F8.0) | lista `CHAVE=caminho` | conforme §8.5 |
| `[agent]` | `work_dir` | caminho | obrigatório |
| `[agent]` | `max_parallel_jobs`, `max_parallel_hard_limit` | inteiro | 1 a 999, com `max_parallel_jobs <= max_parallel_hard_limit` |
| `[agent]` | `claim_batch_size`, `schedule_batch_size` | inteiro | 1 a 1.000 |
| `[agent]` | `orchestrator_interval_s`, `cancel_poll_interval_s`, `heartbeat_interval_s`, `shutdown_grace_s` | inteiro | 1 a 3.600 |
| `[agent]` | `fence_timeout_s`, `node_offline_timeout_s`, `misfire_tolerance_s` | inteiro | 1 a 86.400, com as invariantes I1 a I4 do §8.9 (I3 e I4 envolvem `call_timeout_ms` e `kill_grace_s`) |
| `[agent]` | `kill_grace_s` | inteiro | 1 a 300 |
| `[agent]` | `script_timeout_s` | inteiro | 1 a 86.400 (padrão global; o `timeout_seg` de cada script vai até 9.999.999, como a coluna) |
| `[agent]` | `shutdown_mode`, `misfire_policy` | enum | conforme o exemplo |
| `[agent]` | `cron_horizon_days` | inteiro | 1.461 a 36.500 (CR-008, R-32: quatro anos, para cobrir 29/02; o mínimo do CR-007 era 366) |
| `[agent]` | `log_dir_min_livre_mb` (CR-008) | inteiro | 0 a 1.048.576, padrão 1.024; 0 desliga a checagem (só em DEV) |
| `[agent]` | `child_locale` | texto | obrigatório |
| `[agent]` | `env_passthrough` | lista CSV | opcional, sem as variáveis bloqueadas nem as chaves fixas do §8.6 |
| `[logging]` | `log_dir` | caminho | obrigatório |
| `[logging]` | `level` | enum | `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `[logging]` | `app_log_max_bytes` | inteiro | 1.024 a 1.073.741.824 |
| `[logging]` | `max_log_size_bytes` | inteiro | 1.024 a 67.108.864 (64 MiB, CR-007, R-29: teto do log de um ticket no banco) |
| `[logging]` | `max_local_log_size_bytes` | inteiro | 1.024 a 10.737.418.240 |
| `[logging]` | `app_log_retention_days`, `local_log_retention_days` | inteiro | 1 a 3.650 |
| `[web]` | `session_idle_timeout_s`, `login_bloqueio_s` | inteiro | 1 a 86.400 |
| `[web]` | `sessao_max_horas` (CR-008) | inteiro | 1 a 168, padrão 12 |
| `[web]` | `login_max_tentativas` | inteiro | **1 a 99** (a coluna `tentativas_falha` é `NUMBER(2)`) |
| `[web]` | `log_poll_interval_s` | inteiro | 1 a 3.600 |
| `[web]` | `trusted_proxies` | lista CSV | opcional |
| `[web]` | `allowed_origins` | lista CSV | obrigatória |
| `[retencao]` | `ticket_retention_days` | inteiro | 1 a 3.650 |
| `[retencao]` | `audit_retention_days` | inteiro | 365 a 3.650, e `>= ticket_retention_days` (CR-007, R-22) |
| `[retencao]` | `purge_user` (CR-007) | texto | obrigatório fora de DEV; em `sss_env = DEV`, vazio significa **purge desligado** (o `scripts/purge.py` recusa rodar); quando informado, diferente de `[oracle] user` e de `owner` |
| `[retencao]` | `purge_batch_size` | inteiro | 1 a 100.000 |

**Falha de configuração (web e daemon):**
* A subida é abortada com um registro **CRITICAL** contendo a seção, a chave e o motivo, sem nunca o valor de um segredo.
* O CRITICAL vai para o log da aplicação do minuto atual (§13, `<nome_log>` `sss_web` ou `sss_scheduler`) sempre que o `[logging] log_dir` do `config.ini`, lido mesmo que outras chaves estejam inválidas, existe e aceita escrita. Falhas repetidas no mesmo minuto e no mesmo processo vão para o mesmo arquivo (sem sufixo `_<n>`). Sem `log_dir` utilizável, vai para o stderr do processo, no mesmo formato do §13.
* No nó web, a requisição recebe a página de erro genérica (500), sem o detalhe.

A chave `modo_driver` substitui `driver` e `use_thick_mode` a partir do F7.0 (CR-002); até lá, o código atual (backend FAKE) ainda lê as chaves antigas. A chave `interpretadores` passa a ser lida e validada a partir do F8.0 (CR-001). **CR-007:** entram `usuarios_execucao`, `exec_work_dir`, `fila_envelhecimento_min` e `purge_user`; `table_prefix` passa a aceitar só minúsculas; as faixas de `cron_horizon_days`, `max_log_size_bytes` e `audit_retention_days` sobem; as invariantes I3 e I4 passam a ser validadas. **CR-008:** entram `[web] sessao_max_horas`, `[agent] ambientes_exigem_hash` (removida no CR-011) e `[agent] log_dir_min_livre_mb` (todas opcionais, com padrão); o mínimo de `cron_horizon_days` sobe para 1.461; `[oracle] user` igual ao `owner` passa a ser recusado fora de DEV. **CR-005:** saem `base_script_dirs` (a antiga `base_script_dir` também continua recusada) e `script_owner_sids`; `app_log_backups` é substituída por `app_log_retention_days`. As chaves que saem passam a ser recusadas como desconhecidas. **CR-011:** saem `[agent] script_owner_uids` e `ambientes_exigem_hash`; uma chave removida é recusada com a mensagem "apague a linha".

### 12.2 Launchers

`bin/sss-web.sh` e `bin/sss-scheduler.sh` (Linux/Unix) devem:

* exportar `LD_LIBRARY_PATH` do Instant Client 19 (quando não houver `ldconfig`) e `TZ`. Os valores vêm das variáveis `SSS_IC_DIR` (diretório do Instant Client) e `SSS_TZ` (fuso), definidas pela operação;
* exportar `LANG` e `LC_ALL` com `SSS_LOCALE` (padrão `C.UTF-8`), porque o processo precisa de codificação UTF-8 no sistema de arquivos e no spawn (CR-007, R-17); o processo aborta se ela não for UTF-8 (§8.12);
* aplicar `umask 077`;
* recusar a execução como root;
* fazer `exec` do processo Python, para que os sinais cheguem diretamente a ele;
* iniciar **somente** o processo Python do SSS. O `sss-web.sh` aceita três formas: sem argumentos (servidor padrão), só opções (`-...`, repassadas ao `anyserver.py`) ou `<python3[.x]> web2py.py|anyserver.py [args]`. Qualquer outro comando é recusado com código 2; repassar um comando arbitrário (`exec "$@"` sem essas checagens) é proibido.

`bin/sss-stop.sh` cria o arquivo `work_dir/sss-<agent_id>.stop`, para a parada controlada sem sinal (§8.11).

`bin/sss-helper` (CR-007, D1) é o helper de execução do §8.0. O pacote o leva, mas ele só vale depois de copiado pelo root para `/opt/sss/bin/sss-helper` (dono root, `0755`), com a regra de sudoers do `IMPLANTACAO.md`.

**Pacote de implantação:** `scripts/empacotar.py` (biblioteca padrão) gera `dist/sss-<versao>.tar.gz` com um `SHA256SUMS`, e falha se encontrar segredo ou código de DEV no pacote (F9.1).

**Pastas de runtime do web2py:** o web2py cria as pastas `applications/`, `deposit/`, `logs/` e `site-packages/` no diretório corrente quando é executado fora da raiz. Essas pastas nunca fazem parte da aplicação: o `.gitignore` as ignora dentro de `applications/script_scheduling_service/`, e os launchers e a documentação sempre executam a partir da raiz do web2py.

**Hardening do web2py em HML e PROD:**
* As aplicações de exemplo `admin`, `welcome` e `examples` são **removidas** do pacote implantado.
* `routes.py` fixa `script_scheduling_service` como aplicação padrão e única.
* `applications/script_scheduling_service/controllers/dev.py` não é implantado.

---

## 13. Observabilidade

* **Pasta de ambiente no topo (CR-009):** todo log fica sob uma pasta de ambiente em `log_dir`: a do ambiente do ticket nos logs de execução dos scripts (obrigatória, §8.4 passo 3) ou `interno` nos logs sem ambiente, os da aplicação. O nome de ambiente `INTERNO` é reservado (§10, tabela 1).
* **Logs da aplicação (CR-005, D6):**
  * Caminho: **`log_dir/interno/app/AAAA/MM/DD/HH/MI/<nome_log>_<PID>.log`**. O `<nome_log>` é o do processo: `sss_web` (nó web), `sss_scheduler` (daemon), `purge` e `init_db` (CLIs). O `<PID>` é o do próprio processo. Ex.: `log_dir/interno/app/2026/10/16/08/54/sss_web_4321.log`.
  * O arquivo nasce na pasta do minuto em que o processo sobe, pelo relógio local do processo (com o `TZ` do launcher). Cada processo (cada worker do WSGI) tem o próprio arquivo.
  * **Troca por tamanho:** ao atingir `app_log_max_bytes`, o processo fecha o arquivo e abre um novo na pasta do minuto **atual**. Se já existir um arquivo com o mesmo nome (mesmo minuto e mesmo PID), o novo ganha o sufixo `_<n>`: `sss_web_4321_2.log`.
  * **Retenção:** o próprio processo apaga as pastas `log_dir/interno/app/AAAA/MM/DD` com data anterior a `app_log_retention_days` dias, na subida e a cada troca de arquivo, e depois as pastas de mês e de ano que ficarem vazias. Só entram pastas com o formato exato de data; o resto é ignorado. O `purge.py` nunca toca em `log_dir/interno/`.
  * **Falhas do próprio log** (remoção na retenção, `chmod` ou fechamento do arquivo anterior) não interrompem o processo: viram uma linha WARN no próprio arquivo, com `[acao=RETENCAO]` ou `[acao=LOG]`, antes do registro seguinte.
  * O `log_dir` é criado com `0750` se não existir. Pastas criadas com `0750` (todas as que o processo cria: `interno/`, `app/`, ano, mês, dia, hora e minuto) e arquivos com `0640`, com `chmod` explícito, porque o launcher aplica `umask 077`.
  * O log de acesso do próprio web2py (`httpserver.log`, na raiz do web2py) não segue este padrão; ele é do servidor embutido e fica fora do `log_dir`.
  * **Logs de execução dos scripts** ficam em `log_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log` (§8.4, passo 3). Nenhum script pode ter a pasta de log `app` (§8.5), regra mantida do CR-005, e nenhum ambiente pode gerar a pasta `interno` (CR-009).
  * Formato: `%(asctime)s %(levelname)s [pid=%(process)d] [agente=<id>] [ticket=<id|->] [acao=<CLAIM|SPAWN|HB|...>] %(message)s`, com data ISO local e offset.
* **Níveis:**

  | Nível | Uso |
  |---|---|
  | DEBUG | SQL lógico (nome da operação, sem valores sensíveis) e `argv` mascarado |
  | INFO | Transições de ticket e ciclos |
  | WARN | Pausas, skips, reconexões e *misfire* |
  | ERROR | Falhas de operação, `OWNERSHIP_LOST` |
  | CRITICAL | Fencing e falhas de inicialização |

* Todo `except` registra o código de erro do banco (ORA- no Oracle) e o stack trace em ERROR antes de qualquer `ROLLBACK`. **Exceção (CR-007, R-32):** situações esperadas e tratadas (timeout de lock, deadlock, *call timeout*, perda de corrida com `rowcount = 0` e `SKIP LOCKED`) registram WARN com o código do erro e sem stack trace, para não poluir o log (AGENTS §4.10).
* É proibido registrar senhas, `PADRAO_VALOR_RUN_CONEXAO_BD`, `SSS_AMBIENTE_CONEXAO`, `cookie_key`, o conteúdo de `secrets.cfg` e valores de parâmetros sensíveis.
* **Visão operacional:** a tela de agentes (`auditoria/agentes`, `VER_AUDITORIA`) lista `tbsss_agentes` com o heartbeat e os tickets `RUNNING` de cada agente. É **somente leitura**.
  * **Saúde derivada** da idade do heartbeat, medida pelo relógio do banco (`SYSDATE`), com os limiares do daemon:

    | Saúde | Condição | Exibição |
    |---|---|---|
    | `OK` | idade < `2 × heartbeat_interval_s` | verde, ícone de confirmação |
    | `ATRASADO` | idade ≤ `fence_timeout_s` (limite inclusivo) | âmbar, ampulheta |
    | `EM_RISCO` | idade ≤ `node_offline_timeout_s` (limite inclusivo) | vermelho, alerta |
    | `OFFLINE` | além disso, sem heartbeat ou com status `PARADO` | cinza, círculo cortado |

  * Cartões por agente com "há N s", lista expansível dos tickets `RUNNING` (com link para o detalhe), legenda dos estados e atualização automática a cada 15 s (fragmento `.load`, que preserva as listas abertas).
  * Cada cartão mostra também a plataforma e os interpretadores do agente.
  * Backend FAKE (DEV): o `agt-host01` renova o heartbeat a cada leitura. O `agt-host02` nasce com o heartbeat congelado 30 s antes da carga do seed, então envelhece com o relógio: começa `ATRASADO`, passa a `EM_RISCO` cerca de 1 min depois e a `OFFLINE` cerca de 2,5 min depois.
* **Quadros de atenção na tela de agentes (CR-007, R-18):**
  * **Fila sem atendente:** tickets `PENDING` vencidos cujo par (ambiente, interpretador) não é atendido por nenhum agente com saúde `OK` ou `ATRASADO` (cruzando `tbsss_agentes.ambientes` e `interpretadores`). Mostra o ambiente, o interpretador, a quantidade e o mais antigo. **Critério do claim (CR-008, R-15):** o interpretador é o do cadastro (`tbsss_scripts.interpretador`, por join), o mesmo que a seleção de candidatos usa (§8.2); `parametros_enviados` (CLOB) nunca é lido. A consulta usa as expressões de `ix_tbsss_tck_fila` (`PENDING` vencidos) e agrupa por `t.ambiente, s.interpretador`; o par é comparado em Python com os agentes saudáveis.
  * **Rodando sem PID:** tickets `RUNNING` com `process_id` nulo há mais de 2 minutos (o agente reservou e não iniciou). A consulta usa a expressão de `ix_tbsss_tck_run` e devolve só `id`, `script_id`, `ambiente`, `agente_id` e `started_at`, sem LOB (CR-008, R-15).
  * **Configuração divergente:** agentes ativos com `config_criticos` diferente entre si ou dos valores do nó web (§8.12).
  * Os quadros só aparecem quando há algo a mostrar e ficam no topo da tela.
  * Backend FAKE (DEV): o seed mostra os três quadros. O `agt-host02` tem `kill=10` (configuração divergente); o ticket 16 está `RUNNING` sem PID desde a carga; o ticket 4 (SH em `HOMOLOGACAO`, vencido 3 min antes da carga) só é atendido pelo `agt-host02` (o `agt-host01` mapeia `PYTHON3,BASH`) e entra na fila sem atendente quando ele passa a `EM_RISCO`, cerca de 1 min depois da carga.
  * `config_criticos` do nó web: `sss_config.config_criticos(cfg)`, com `call` em segundos (`call_timeout_s`, arredondado para cima), igual ao texto do agente (§8.12).
* **Monitoração externa (CR-007, R-18):** `scripts/saude.py` (F9.1) roda, com a conta só de leitura do papel **monitor** (`[monitor]` no `secrets.cfg`, §4.1 e §11.1, CR-008 E3; a conta do agente não lê `tbsss_auditoria`), as consultas de saúde e devolve o código no padrão Nagios (0 OK, 1 WARN, 2 CRITICAL, 3 desconhecido), com uma linha por problema. Verifica: agente `ATIVO` sem heartbeat além de `node_offline_timeout_s`; ambiente ativo sem nenhum agente saudável; os três quadros acima; fila `PENDING` vencida acima de um limite; ausência de `PURGE` auditado em 2 dias; versão do esquema (§11.1). Os limites são argumentos com padrão, e o `IMPLANTACAO.md` traz o exemplo de agendamento no monitoramento corporativo.
* **Painel inicial** (`default/index`), com cartões por permissão:
  * contagem por status dos tickets criados nas últimas 24 h e meus últimos 5 tickets (quem consulta tickets, no escopo da lista);
  * próximos 5 agendamentos ativos (`CAD_AGENDAMENTOS`);
  * saúde dos agentes (`VER_AUDITORIA`).

---

## 14. Riscos Residuais Aceitos

| Risco | Mitigação vigente |
|---|---|
| Credencial legível no ambiente do processo (`/proc/<pid>/environ` no Linux) pelo root e pelos scripts do **mesmo** ambiente (mesmo usuário de execução) | Um usuário de execução por ambiente, diferente do usuário do agente, que não lê segredos nem logs do agente (CR-007, D1); servidor restrito. O aceite anterior, que considerava o usuário do agente confiável, foi revogado pelo CR-007 |
| Argumentos visíveis em `ps`/lista de processos | Proibição de parâmetro de senha; parâmetros sensíveis apenas mascarados na UI e nos logs |
| Script que faça `setsid`/double-fork escapa do `killpg` | Homologação do script no catálogo; política de revisão de código; o processo fugido fica limitado ao usuário de execução do ambiente (D1), e os netos que ficam no grupo são encerrados sempre (§8.7, R-02) |
| Conteúdo e versão do script sob controle do ambiente (CR-011): sem hash nem conferência de dono, um arquivo alterado no disco, ou um link simbólico trocado por quem grava na pasta dele, executa o novo conteúdo sem aviso | O arquivo real não pode ser gravável por grupo nem por outros, nem ficar nas pastas do sistema ou do SSS (§8.5); o script roda com o usuário de execução do ambiente (D1); a gestão de versões e de permissões dos scripts é do ambiente |
| Granularidade fina "perfil × script × ambiente" | Não suportada; a intersecção `perfil_amb ∩ script_amb` atende ao escopo atual |
| Semântica de horário de verão | Horário de parede do servidor Oracle (§7.1), com o pré-requisito de banco sem horário de verão (D3). Se ele não for cumprido: com `SKIP`, a ocorrência que cai no avanço do relógio é perdida; o recuo atrasa a regra pelo tamanho do recuo; a detecção de nó offline é suspensa pela trava de salto de relógio (§8.8) |
| Lacunas em sequences | Aceitas por design |
| Segredos com menos de 4 caracteres não são mascarados nos logs (§4.1) | Política de senha de 12 caracteres ou mais para contas; valores de parâmetros sensíveis com menos de 4 caracteres são recusados (§6.2, R-25) |
| Bloqueio simulado de login inexistente fica na memória de cada processo web (§4.2) | Mensagem genérica e hash fictício; o bloqueio real das contas existentes fica no banco e vale para todos os nós |
| Sessão aberta continua válida depois de um bloqueio por falhas de terceiros (§4.2) | O bloqueio impede novos logins; o administrador pode desativar o usuário ou redefinir a senha, o que revoga as sessões na hora (`sessao_epoch`, CR-008 E2), e toda sessão expira em `sessao_max_horas` |
| Papel agente lê `tbsss_usuarios.senha_hash` (§11.1; o 11g não tem `GRANT SELECT` por coluna) | Hash PBKDF2-SHA256 com 200.000 iterações e salt; o servidor do agente é restrito; restringir por view fica como melhoria (CR-008, R-30) |
| Processo "talvez iniciado" (`.sss_spawn` sem `.sss_proc`) em Unix sem `/proc/<pid>/cwd` nem `pwdx` não é encerrado automaticamente (§8.7) | WARN e `ORPHAN_PROCESS`; o processo fica limitado ao usuário de execução (D1); a janela é de microssegundos (entre o `Popen` e a gravação do `.sss_proc`) |
| Sair em um navegador encerra todas as sessões do mesmo usuário (§4.2) | Consequência declarada da revogação por `sessao_epoch` (CR-008, E2) |
| Tempos de fencing diferentes entre agentes anulam a garantia do §8.9 | Conferência automática de `config_criticos` entre os agentes (recusa na subida, ERROR no ciclo e quadro na tela de agentes, §8.12, R-23), além das invariantes I1 a I4 |
| Arquivo local do log de execução sem máscara (§8.10) | Escrito pelo próprio script; arquivo do usuário do agente (`0600`), só no agente, com retenção |
| Processo órfão com identidade desconhecida (Unix sem leitura de identidade) não é encerrado automaticamente (§8.12) | WARN `ORFAO_SEM_IDENTIDADE` para intervenção; o ticket é finalizado `ORPHAN_PROCESS` |
| Script que escreve mais rápido que a checagem do teto do log local (§8.10) | `log_dir` em partição própria (`IMPLANTACAO.md` §18.1), checagem do teto a cada `cancel_poll_interval_s` e claim suspenso com pouco espaço livre (`log_dir_min_livre_mb`, CR-008 R-25). A cota de disco do usuário de execução **não** protege o `log_dir`: o arquivo de log pertence ao agente, e a cota é cobrada do dono (correção do CR-008; a cota continua protegendo `exec_work_dir`) |
| Regex gravada antes do CR-007 fora do subconjunto seguro (§6.2) | Continua valendo até a próxima gravação do parâmetro, que exige a correção; a revisão dos parâmetros com regex faz parte da implantação do CR-007 |
| Banco com charset `AL32UTF8`: o CLOB conta um caractere fora do BMP (emoji) como 2 posições, e a leitura da tela (`VER_LOGS`, offset em caracteres) ainda não foi validada nesse charset (revisão F8.0–F8.2). O GFPR é `WE8ISO8859P15` (o caractere vira `¿` e conta 1) | O agente mede a unidade no banco (`RepoSchedulerLog.unidade_suplementar`) e o pump grava no offset certo; validar a tela num banco `AL32UTF8` antes de produção nesse charset |
| Host do agente fora do ar sem religar: o startup check não roda e um processo que tenha sobrevivido nele não é encerrado | O ticket vira `NODE_OFFLINE`; a operação recupera o host antes de religá-lo, e o startup check limpa na religação |

## 15. Diagramas

### 15.1 Arquitetura

```mermaid
flowchart LR
    pessoa["Usuário"]
    browser["Navegador"]

    subgraph web["Nós Web (1..N)"]
        wsgi["web2py / WSGI"]
        controllers["Controllers"]
        services["Services e regras de negócio<br/>RBAC, validação e compilação"]
        factory["repo_factory"]
        ui_repos["Contratos e repositórios da UI<br/>ORACLE ou FAKE em DEV"]
        browser --> wsgi --> controllers --> services --> factory --> ui_repos
    end

    subgraph agente["Agente Scheduler (um por servidor executor)"]
        entry["run_scheduler.py"]
        loop["scheduler_loop.py<br/>desdobro, claim e monitoramento"]
        batch["Repositórios batch Oracle<br/>agenda, fila e log"]
        executor["executor.py"]
        guards["path_guard.py<br/>env_builder.py"]
        platform["plataforma POSIX<br/>spawn e encerramento"]
        helper["sss-helper"]
        script["Script homologado<br/>usuário de execução do ambiente"]
        local_log["Arquivo local de saída"]
        entry --> loop
        loop --> batch
        loop --> executor --> guards --> platform
        platform -->|"fora de DEV"| helper --> script
        platform -->|"DEV"| script
        script --> local_log
        local_log --> loop
    end

    oracle[("Oracle Database<br/>estado, tickets, agenda,<br/>auditoria e log")]
    pessoa --> browser --> wsgi
    ui_repos --> oracle
    batch --> oracle
```

Os nós Web e os agentes são processos separados. O daemon é iniciado exclusivamente por `run_scheduler.py`; o nó Web não inicia nem sinaliza processos executados. O backend `FAKE` é restrito ao desenvolvimento da UI; o agente exige `ORACLE`.

### 15.2 Fluxo de criação e execução de um ticket

```mermaid
flowchart TD
    start["Solicitação manual na UI<br/>ou ocorrência de agendamento"]
    manual{"Origem manual?"}
    authorize["Validar sessão, RBAC,<br/>script e ambiente"]
    manual_ticket["Criar ticket e snapshot<br/>imutável das respostas e do argv"]
    schedule["Agente desdobra ocorrência<br/>e cria ticket com snapshot"]
    pending["Ticket PENDING<br/>aguarda scheduled_at"]
    select["Agente seleciona candidato<br/>compatível com ambiente e interpretador"]
    claim["Claim transacional:<br/>lock, checagem de limite<br/>e transição condicional"]
    claimed{"Claim confirmado?"}
    precheck["Validar snapshot, caminho,<br/>interpretador e hash"]
    valid{"Pré-validação aprovada?"}
    spawn["Iniciar pelo mecanismo POSIX<br/>helper fora de DEV"]
    spawned{"Spawn concluído?"}
    monitor["Monitorar processo:<br/>heartbeat, cancelamento e timeout"]
    finish["Encerrar grupo, coletar saída<br/>e finalizar ticket"]
    precheck_failed["Finalizar como FAILED<br/>PRECHECK_FAILED"]
    spawn_failed["Finalizar como FAILED<br/>SPAWN_ERROR"]
    terminal["Ticket em estado terminal"]
    wait["Aguardar próximo ciclo<br/>ou nova tentativa conforme estado"]

    start --> manual
    manual -- "Sim" --> authorize --> manual_ticket --> pending
    manual -- "Não" --> schedule --> pending
    pending --> select --> claim --> claimed
    claimed -- "Não" --> wait
    claimed -- "Sim" --> precheck --> valid
    valid -- "Não" --> precheck_failed --> terminal
    valid -- "Sim" --> spawn --> spawned
    spawned -- "Não" --> spawn_failed --> terminal
    spawned -- "Sim" --> monitor --> finish --> terminal
```
