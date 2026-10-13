# SSS — Prompt F0.1: Ambiente e esqueleto do repositório

## Leitura obrigatória antes de planejar
- `AGENTS.md` (inteiro)
- `README.md` §2 (inteiro), §3 (topologia e estrutura), §12.2 (launchers e hardening)
- `docs/prompts/00_INDEX.md` (pré-requisitos)

## Contexto de Diretório de Trabalho
- A raiz da aplicação é `applications/script_scheduling_service` a partir da raiz do web2py (`/portaloptrib/TESHUVA/web2py`).
- Todos os caminhos criados dentro da aplicação devem residir dentro de `applications/script_scheduling_service/`.

## Objetivo
Criar o esqueleto de diretórios da aplicação e um verificador de ambiente que falhe cedo se os pré-requisitos de desenvolvimento não estiverem presentes.

## Escopo
**IN**
- Estrutura de diretórios do README §3.2. Diretórios vazios recebem `.gitkeep`:
  - `bin/` (na raiz do web2py)
  - `applications/script_scheduling_service/controllers/`, `applications/script_scheduling_service/models/`, `applications/script_scheduling_service/modules/` (com `__init__.py`), `applications/script_scheduling_service/modules/repo_fake/` (com `__init__.py`), `applications/script_scheduling_service/modules/repo_oracle/` (com `__init__.py`)
  - `applications/script_scheduling_service/scripts/`, `applications/script_scheduling_service/views/`, `applications/script_scheduling_service/views/components/`
  - `applications/script_scheduling_service/static/css/`, `applications/script_scheduling_service/static/img/`, `applications/script_scheduling_service/static/js/app/`, `applications/script_scheduling_service/static/fonts/`
  - `applications/script_scheduling_service/dev/scripts/`, `applications/script_scheduling_service/instance/`
- `applications/script_scheduling_service/scripts/_testenv.py`:
  - insere em `sys.path` o diretório `applications/script_scheduling_service` e a raiz do web2py, calculada dinamicamente a partir de `__file__`, sem caminho absoluto fixo;
  - não importa `gluon`.
- `applications/script_scheduling_service/scripts/check_env.py` (CLI, `print` permitido). Verifica:
  - `sys.version_info[:2] == (3, 6)`. Se for diferente, sai com código 2 e mensagem clara;
  - existência de `web2py.py` na raiz;
  - existência e tamanho > 0 de `applications/script_scheduling_service/static/bootstrap/bootstrap.min.css`, `applications/script_scheduling_service/static/bootstrap/bootstrap.bundle.min.js` e `applications/script_scheduling_service/static/js/alpine.min.js`;
  - que o `alpine.min.js` **não** contém o token `new Function`, o que indica a build CSP. Se contiver, falha com a mensagem "Alpine não é a build CSP".

  O resultado é impresso em tabela `OK/FALHA` por item, e o código de saída é 0 apenas se tudo estiver OK.
- `.gitignore` na raiz do web2py:
  - `*.pyc`, `__pycache__/`, `applications/script_scheduling_service/sessions/`, `applications/script_scheduling_service/errors/`, `applications/script_scheduling_service/cache/`, `applications/script_scheduling_service/databases/`, `applications/script_scheduling_service/log/`;
  - `applications/script_scheduling_service/instance/config.ini` (fica versionado apenas o `.example`);
  - `*.log`, `secrets.cfg`, `.env`.
- `docs/AMBIENTE_DEV.md` com:
  - instalação do Python 3.6 via pyenv, com a nota sobre Apple Silicon/Rosetta ou container;
  - como subir o servidor de desenvolvimento do web2py **somente em 127.0.0.1**;
  - como rodar os testes a partir de `applications/script_scheduling_service`;
  - aviso de que o backend FAKE exige processo único.

**OUT (não fazer)**
- Nenhum controller, model, view ou módulo de negócio.
- Não baixar Bootstrap/Alpine da internet. Se faltarem, o `check_env.py` reporta FALHA.
- Não criar `config.ini` nem `secrets.cfg` (isso é o F0.2).

## Requisitos
1. Python 3.6 estrito (AGENTS §2.1), sem dependências externas.
2. `check_env.py` sem efeitos colaterais: somente leitura.
3. Nomes de arquivos e diretórios em ASCII (AGENTS §2.4).

## Critérios de aceite
- [ ] A árvore de diretórios bate com o README §3.2 para os itens do escopo IN.
- [ ] `python scripts/check_env.py` (executado de dentro de `applications/script_scheduling_service`) retorna 0 com os pré-requisitos presentes.
- [ ] Renomear temporariamente `alpine.min.js` faz o comando retornar diferente de 0, com a linha de FALHA correspondente.
- [ ] `docs/AMBIENTE_DEV.md` não contém nenhuma URL de CDN.

## Verificação
- `cd applications/script_scheduling_service && python scripts/check_env.py`
- `git status` mostra apenas arquivos do escopo.

## Regras de parada
Se a versão do web2py presente não for compatível com Python 3.6, **pare** e reporte a versão encontrada.

## Saída
Relatório AGENTS.md §9, sem texto adicional.