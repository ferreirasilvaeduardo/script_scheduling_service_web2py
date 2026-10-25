# CR-022: Estrutura padrão do repositório

| Campo | Valor |
|---|---|
| Status | **Em andamento**. 022a aprovado pelo responsável pelo produto em 2026-10-24; os passos seguintes terão plano e aprovação próprios |
| Origem | Decisão de 2026-10-24 ("2 no CR-022"): depois do CR-021, levar o repositório ao padrão de mercado para Python. Em 2026-10-24, o responsável pediu também tirar a pasta `web2py/` (022a) |
| Restrições | Sem dependência nova (AGENTS §2.2). Python 3.6.0 a 3.13. As URLs (`/script_scheduling_service/...`), as regras de negócio, o banco e o daemon não mudam |
| Afeta | README §3.2, §12.2 e §12.3; AGENTS §3.3 e §7; `docs/DEPLOYMENT.md`; `docs/DEV_ENVIRONMENT.md`; launchers, `package.py`, testes e o roteiro de homologação |

---

## 1. Situação de partida

Depois do CR-021, o repositório não tinha mais nada do web2py, mas mantinha a forma dele: raiz em `/portaloptrib/TESHUVA/SSS/DEV/web2py`, com a aplicação em `applications/script_scheduling_service/` e o `bin/` ao lado de `applications/`. O pacote extraía em `/opt/sss/web2py`.

---

## 2. Decisões (022a)

| # | Decisão |
|---|---|
| D1 | A aplicação passa a ser a raiz do repositório: o conteúdo de `applications/script_scheduling_service/` sobe para a raiz, junto com o `bin/`. Saem `applications/` e os `__init__.py` que só existiam para o web2py |
| D2 | A pasta do repositório no DEV passa de `/portaloptrib/TESHUVA/SSS/DEV/web2py` para `/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service`, sem link com o nome antigo |
| D3 | Nos servidores, o pacote extrai em `/opt/sss/app` (antes `/opt/sss/web2py`); `W` = `APP` no DEPLOYMENT |
| D4 | O pacote usa lista de permissão da raiz (`bin/` de produção, `AGENTS.md`, `README.md` e as pastas da aplicação), porque a raiz agora também tem `.git`, `Makefile`, `input/`, `output/` e outros arquivos da máquina de desenvolvimento |
| D5 | O rodapé mostra a versão do pacote (`sss_config.SSS_VERSION`), a mesma do nome do pacote e do log do agente; antes era um `0.1.0` fixo herdado do web2py |

---

## 3. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 022a | Aplicação na raiz do repositório e pasta sem `web2py` (D1 a D5): launchers, `package.py` (lista de permissão), `posix.PACKAGE_HELPER` (`../../bin/sss-helper`), testes que subiam três níveis até o `bin/`, `.gitignore`, `Makefile`, `CLAUDE.md`, README, AGENTS, DEPLOYMENT (§18 com a primeira atualização para `/opt/sss/app`) e DEV_ENVIRONMENT. Defeito pego pela suíte: o `PACKAGE_HELPER` subia quatro níveis e não acharia o helper do pacote | Concluído |
| 022b em diante | Estrutura interna padrão (`src/sss/` com subpacotes, `tests/` separado de `scripts/`, `pyproject.toml` só com configuração de ferramentas, imports sem mexer no `sys.path`, 99 colunas e tipagem gradual) | Pendente (plano próprio) |

---

## 4. Riscos

* **Caminhos fora do repositório:** o link `/opt/automacoes/scripts/utilitarios` (do root) e os caminhos absolutos do `instance/config.ini` do DEV apontavam para a pasta antiga e são refeitos à mão; scripts cadastrados no DEV não rodam enquanto o link não for refeito.
* **Servidores:** a primeira atualização para esta versão muda a pasta (`/opt/sss/web2py` → `/opt/sss/app`) e os caminhos de operação (DEPLOYMENT §18); o retorno é subir de novo pela pasta antiga, que fica intacta.
