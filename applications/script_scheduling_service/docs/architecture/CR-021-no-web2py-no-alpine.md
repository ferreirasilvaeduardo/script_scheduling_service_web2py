# CR-021: Sem web2py e sem Alpine.js

| Campo | Valor |
|---|---|
| Status | **Em andamento**. Aprovado pelo responsável pelo produto em 2026-10-24 |
| Origem | Pedido do responsável pelo produto (2026-10-24): retirar o web2py e o Alpine.js e ficar só com Python 3.6+ (biblioteca padrão) e Bootstrap 5.3.8, seguindo rigorosamente os padrões de código e de estrutura de diretórios para Python |
| Restrições | Sem dependência nova (AGENTS §2.2). Python 3.6.0 a 3.13. SQL Oracle 11gR2 só em `repo_oracle/`. CSP `script-src 'self'` sem nada inline. As regras de negócio, o banco e o daemon não mudam |
| Afeta | README §2.1, §2.4, §3.1, §3.2, §4.2, §5.8 e §12.2. `AGENTS.md` §1, §2.2, §2.3, §3.4, §5, §7 e §8. `docs/DEPLOYMENT.md` e `docs/DEV_ENVIRONMENT.md`. Código: `static/js/app/`, `views/`, `models/`, `controllers/`, `modules/` (só o `gluon.current`), `scripts/package.py`, `bin/` e a raiz do repositório |

---

## 1. Situação de partida

* **`modules/`** só usa `from gluon import current`, em 15 arquivos, para obter `current.repo_factory` e `current.sss_cfg`. A camada de banco já é própria (`repo_oracle/`), e o DAL do web2py nunca foi usado.
* **O daemon** (`scripts/run_scheduler.py`) já roda em Python puro, fora do web2py.
* **`models/`** (2 arquivos) faz a sessão em cookie cifrado do web2py, os cabeçalhos, as guardas e o CSRF.
* **Os controllers** (14 arquivos) são executados pelo web2py com `request`, `response`, `session`, `HTTP`, `redirect` e `URL` injetados: não são módulos importáveis.
* **As views** (50 arquivos) usam o template do web2py com Python de verdade (imports, comprehensions, `lambda`, blocos de código de várias linhas).
* **O servidor** é o Rocket do web2py, com as páginas de erro pelo `routes_onerror`.
* **O Alpine.js** está em 22 componentes, cerca de 270 ligações nas views (`@click`, `:class`, `x-show`, `x-text`, `x-for` e outras) e 16 registros `Alpine.data()`.

## 2. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Sessão em cookie assinado | HMAC-SHA256 com `[web] cookie_key`, validado com `hmac.compare_digest`, `HttpOnly`, com o mesmo conteúdo mínimo de hoje (README §4.2). Deixa de ser cifrado: a biblioteca padrão não tem AES e a `cryptography` é proibida. O navegador pode **ler** o conteúdo (ids, login, horários, token CSRF, aviso de tela), mas não alterá-lo. A revogação por `session_epoch` não muda |
| D2 | Motor de templates próprio | Compatível com a sintaxe das views atuais (`{{=}}` com escape, `if`/`for`/`pass`, `extend`/`include`/`block` e blocos de código), compilado com `compile()`/`exec`. É a **única** exceção à proibição de `exec`, num só módulo e só para arquivos de `views/`, nunca para dados |
| D3 | Controllers como módulos | `request`, `response` e `session` por thread, importados pelos controllers junto com `HTTP`, `redirect` e `URL`. `modules/` continua sem acesso a eles |
| D4 | URLs mantidas | `/script_scheduling_service/<controller>/<função>/<args>`; `/` redireciona para o início |
| D5 | Servidor da biblioteca padrão | `wsgiref` com pool de threads limitado, só em `127.0.0.1` atrás do proxy. Chaves novas `[web] max_threads` (16) e `socket_timeout_s` (30), validadas pelo `sss_config`. Parada limpa por SIGTERM |
| D6 | Repositório sem web2py | Saem `gluon/`, `web2py.py`, `anyserver.py`, `routes.py` e as pastas de runtime do web2py. Ficam `applications/script_scheduling_service/` e o nome da pasta raiz (o link `/opt/automacoes` aponta para ela) |
| D7 | JavaScript sem framework | Componente é um elemento com `data-component`, montado pela fábrica registrada em `SSS.component` (`static/js/app/dom.js`). Eventos por delegação (`data-action`), elementos por `data-ref`, texto só por `textContent`. Sem expressões no HTML, sem estado reativo e sem `innerHTML` |
| D8 | Padrões de código no código novo (2026-10-24) | A partir do 021d1, o código novo nasce como pacote de verdade (`modules/web/`, com `__init__.py` e imports relativos internos), com anotações de tipo (sintaxe 3.6) e linhas de até 99 colunas, sem mudar as regras do código existente. O harness de navegador do CR-021 entra no repositório (`dev/web_harness/`). A reestruturação completa do projeto (pacote `src/sss/` com subpacotes, `tests/`, `pyproject.toml` com a configuração das ferramentas, linha de 99 colunas e mypy graduais, limpeza da dívida de lint) fica para o **CR-022**, depois do CR-021 |

## 3. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 021a | `static/js/app/dom.js`. Sem Alpine: `toast` e `toastDemo` (`sss.js`), `copy`, `filters`, `scriptSearch` e o modal genérico `confirmation` (`components.js`), com o `layout`, `components/confirm_modal.html`, `components/filters.html`, o catálogo, o passo 1 da nova regra, o comando do ticket, o "Redefinir senha" e as telas de DEV. O `confirmation` do Alpine fica só nas três telas em que o modal usa o estado de outro componente Alpine (matriz de permissões, homologação do script e disparo). Corrigido o tipo `warning` do toast, que caía em `info` (o `sss.js` aceitava `alert`, que não existe no CSS). Teste `test_frontend_components.py` | Concluído |
| 021b0 | Fora do CR: `test_output_browse_service` deixa de fixar o dia (o seed FAKE monta as datas a partir de `store.now()`) | Concluído |
| 021b1 | `SSS.modal` (modal do Bootstrap por classe, compartilhado pelo `confirmation` e pelos componentes que têm modal próprio), `SSS.dom.replaceFragment` e `SSS.dom.clockTime`. Sem Alpine: `ticketsRefresh`, `agentsRefresh`, `inputUpload`, `logViewer` e `parameterForm` (lista de opções redesenhada só ao incluir ou remover; digitar só atualiza o estado; ao remover, o foco vai ao "Remover" que ocupou o lugar, ou ao "Adicionar opção" com a lista vazia) | Concluído |
| 021b2 | Sem Alpine: `scheduleRule` (blocos por `data-types`), `scriptLinks` (lista ordenável com `<template>` e `data-part`), `permissionMatrix` e `scriptHomologation`, cada um dono do próprio modal pelo `SSS.modal`; o `triggerSummary`, que era aninhado no modal, vira o `ticketTrigger`, dono do formulário, do modal e do resumo. `SSS.dom.fillList`. Saem `alpine.min.js`, `[x-cloak]`, o analisador do build CSP do `check_env.py` e o `test_check_env.py`. O `test_frontend_components` proíbe a sintaxe do Alpine em todas as views; o `test_py36_compat` troca `x-html` por qualquer diretiva em HTML montado em Python. Homologação real completa no DEV: rodada 1 de 24/10 com 48 falhas em cascata (o roteiro clicava em `button[data-summary-trigger]`, que saiu com o Alpine; corrigido, com teste de contrato dos seletores do roteiro); rodada 2 com 283/283 (`docs/homologation/SSS_Homologation_Evidence_2026-10-24_r2.docx`) | Concluído |
| 021c | `modules/app_context.py` (`set_config`, `get_config`, `require_config`) no lugar do `gluon.current` para a configuração do processo: services, `repo_factory`, `repo_oracle/base`, controllers e `models/`. O `current.repo_factory` virou `import repo_factory`. Nenhum arquivo de `modules/` importa `gluon` (`test_app_context.py`). O `current.sss_ctx`, que é da requisição, fica na camada web até o 021e. Sem gravação dupla na transição: todos os leitores foram trocados de uma vez. Correção posterior: o `bin/start_local.sh` ainda lia `current.sss_cfg` no diagnóstico antes de subir (achado ao subir o DEV para a homologação do 021b), com teste de regressão em `test_app_context.py` | Concluído |
| 021d1a | Pacote `modules/web/` (D8) com `errors`, `storage`, `routing` (`url()` igual ao `gluon.html.URL`, conferido nas extensões html, load e json), `request` (consulta só com `&`, vars juntando GET e POST como o web2py, JSON do `fetch` em `post_vars`, JSON inválido 400), `multipart` (em fluxo), `response` (JSON seguro para HTML, `Set-Cookie` com `HttpOnly` e `SameSite`) e `session` (cookie assinado, D1; `connect` move o `flash` como o web2py). Defeito achado pelos próprios testes e corrigido: o limite do cabeçalho de parte não valia quando o marcador chegava no mesmo bloco | Concluído |
| 021d1b | `static` (só GET/HEAD, `realpath` dentro de `static/`, sem listagem, `ETag`/`Last-Modified` com 304, `nosniff`), `app` (WSGI: rota, hooks, action, resposta, página de erro sem detalhe técnico e id da ocorrência no log) e `server` (`wsgiref` com semáforo de `max_threads`, `timeout` por conexão, log pelo `logging`, parada limpa por flag); harness de navegador versionado em `dev/web_harness/` (D8) | Pendente |
| 021d2 | Motor de templates (D2), com teste de paridade de HTML contra o template do web2py em todas as views | Pendente |
| 021e | `models/` vira módulos, controllers no formato do D3, entrypoint `scripts/run_web.py` e `bin/sss-web.sh` novos; os dois servidores lado a lado no DEV; homologação real completa no servidor novo | Pendente |
| 021f | Repositório sem web2py (D6): pacote, launchers, testes, README, AGENTS, DEPLOYMENT, DEV_ENVIRONMENT, Makefile e `.gitignore`; ensaio do pacote e documento de evidências | Pendente |

## 4. Riscos

* **Segurança que passa a ser do projeto:** sessão, multipart, conexões lentas e páginas de erro. O 021d1 tem testes de ataque dedicados (cookie forjado, multipart malformado ou grande demais, caminho com `..`, conexão lenta).
* **Homologação:** é refeita no 021b e no 021e.
* **Sessões abertas:** a troca do formato do cookie (021e) encerra todas uma vez.
