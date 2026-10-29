# CR-033: Ensaio de PROD pelo pacote e homologação real no PROD

| Campo | Valor |
|---|---|
| Status | **Encerrado** em 2026-10-28 |
| Origem | Pedido do responsável pelo produto: ensaio em PROD e nova homologação no ambiente de PROD, com o mesmo banco do DEV |
| Decisões | D1 A: o PROD usa os mesmos nomes do DEV (`web0001` e `agente0001`), com o DEV parado o tempo todo (neste banco, DEV e PROD nunca ficam no ar juntos); D2 A: o PROD fica instalado e **parado** no fim, sem `crontab`; D3 A: o pacote não leva `docs/homologation/`; D4 A: o Makefile perde os alvos que empacotavam a árvore inteira e ganha o `DEV_PYTHON` dos portões |
| Instalação | `/portaloptrib/TESHUVA/SSS/PROD/script_scheduling_service`, pelo pacote do commit `5c0383d` (CR-032e); web em `127.0.0.1:18100`; Python 3.6.0 |

## 1. Roteiro executado

| Passo | Guia | Resultado |
|---|---|---|
| Pacote | DEPLOYMENT §3 (`git archive`, `package.py`, `sha256sum -c`, extração, `sha256sum -c --quiet`) | OK; `ls` como o guia espera. **Achados 1 e 3** |
| Configuração | §7.1 e §7.2 (modelos de `instance/exemplos/`; `common.ini` com o `[oracle]` do DEV; `secrets.cfg` `0600` copiado do DEV; agente com os ambientes do DEV) | OK, sem nenhuma chave além das do modelo |
| Banco | §5 (`check_env --name` dos dois, `generate_sql`, `init_db --dry-run`, `99_validate` no `sqlplus`, só leitura) | OK: SQL gerado idêntico ao versionado, 21 tabelas no DDL, `OK: nenhuma falha` nas duas seções do `99`. Nada recriado |
| Scripts | `scripts_ambiente/` (pasta base padrão) com a cópia do `dev/scripts` do repositório | OK; o seed usa caminhos relativos (CR-023) e não mudou |
| Subida sem cron | §10.6 (`sss-keepalive.sh web0001:18100 agente0001`) | passada 1 subiu os dois, com `ambiente da instalacao: PROD` e as pastas `var/agente0001/{works,outputs,inputs,script_works}` criadas; passada 2 só conferiu; agente derrubado com `kill -9` voltou na passada seguinte |
| Validação | §11 e §13 | HTTP 303/200/4 cabeçalhos/403/404; `/dev` 404; rodapé "Ambiente **PROD**" e sem faixa; `health.py --name agente0001`: `SSS OK`, código 0. **Achado 2** |
| Homologação | `dev/others/homologation` com `SSS_APP_ROOT` do PROD | ver §3 |

## 2. Achados e correções

| # | Achado | Correção |
|---|---|---|
| 1 | O pacote tinha 300 MB: `docs/homologation/` levava os 21 `.docx` de evidência (13 a 16 MB cada), inúteis no servidor e crescendo a cada rodada | D3 A: `tools/package.py` exclui `docs/homologation/` (pacote de 2,8 MB); teste em `tests/unit/tools/test_package.py`; README §12.2, AGENTS §3.2 e DEPLOYMENT §3 |
| 2 | O §11 esperava a raiz `/` indo direto para `/default/login`; ela vai para `/script_scheduling_service/`, que leva ao login | Linha esperada corrigida no §11 |
| 3 | A tabela do §1.3 pede a `<RAIZ>` com `0750`, mas o `tar` segue o `umask` (`0755` com `022`) e nenhum passo corrigia | `chmod 0750` no bloco do §3 |
| 4 | Roteiro de homologação: o CT-30 esperava o `HOME` em `work/ticket_<n>/exec`, nome anterior ao CR-032e; o agente grava `works/ticket_<n>/exec`, o correto | Expectativa corrigida no `capture_evidence.js`; CT-30 repetido (4/4). Não é defeito do produto |
| 5 | Sem `crontab` (D2), a reinicialização da máquina derrubou o web e o agente no meio do trabalho e nada os subiu | Esperado no ensaio: subidos de novo pela mesma linha do keepalive (`SSS OK` no `health.py`). Em operação, o `@reboot` do §4.0 cobre o caso |

## 2.1 Makefile (D4 A)

Validação pedida em paralelo pelo responsável:

| # | Achado | Correção |
|---|---|---|
| M1 | `zip-deploy` e `zip-deploy-zip` empacotavam a árvore inteira: `instance/secrets.cfg` real, `LEIA-ME.TXT`, `var/` (9,7 GB), `dev/`, `tests/`, com exclusões de nomes antigos (`input/`, `output/`, `logs/`, `work/`) | Os dois alvos e o `freeze-req` saíram; o pacote é só o do `make package` |
| M2 | Com o `PYTHON=python3` padrão (3.6.0), `make lint` e `make type-check` quebravam (plugin do flake8, `TypeError` no mypy), e o `check-dev-deps` dizia OK, porque só importava | `DEV_PYTHON` (padrão o 3.11.11 do pyenv) nos alvos de lint, tipos e formatação; `check-dev-deps` roda `-m <ferramenta> --version` |
| M3 | `check-all` chamava `format`, que reescreve arquivos | `check-all` = `lint` + `type-check` |
| M4 | `list-deploy` procurava a saída do `zip-deploy` | Procura `.bkp/pacote_*/sss-*.tar.gz` |
| M5 | `EXCLUDES`/`PY_FILES` faziam um `find` na árvore inteira a cada `make`, sem uso | Saíram |
| M6 | Comentário do `package` com "~225 MB" | Atualizado (o `rm` de `docs/homologation` fica como defesa) |
| M7 | `echo "...\n"` dependia do `dash` como `sh` | Sem `\n` nos `echo` |

`docs/DEV_ENVIRONMENT.md` atualizado (`make lint` e `make type-check` sem `PYTHON=`).

## 3. Homologação real no PROD

O roteiro `capture_evidence.js` (e o `gerar_massa.py`) ganharam `SSS_APP_ROOT`: com a raiz do PROD, leem `instance/` e `var/` de lá, e a pasta base dos scripts vem do `config.ini` do agente ou, sem a chave, de `scripts_ambiente/`. O CT-01 confere a tela pelo `<TIPO>`: no DEV, a faixa; no PROD, sem faixa e com o rodapé "Ambiente PROD". O `build_evidence_docx.py` ganhou os dados da instalação por rodada (`instalacao`, `endereco`, `nome_agente`, `python`, `web`, `agente`, `seed_scripts` e `defeitos`).

Rodada `SSS_ADMIN_START=new SSS_EVIDENCE_DATE=20261028 SSS_EVIDENCE_ROUND=2` (marca `HOMOLOG_20261028R2`): **333 de 333 verificações OK**, 34 casos, 102 figuras (o CT-01 do PROD tem uma verificação a mais que o do DEV: sem faixa e com o rodapé). A rodada completa foi em 28/10/2026; o CT-30 foi repetido em 29/10/2026 (achado 4). Ressalvas de sempre: CT-20 (um agente só) e CT-24 (responsável inativo). Documento: `docs/homologation/SSS_Homologation_Evidence_2026-10-28_r2.docx` e `.md`.

## 4. Validação

* Suíte completa no Python 3.6.0: 1493 testes OK (61 pulados, os do Oracle real); `var/` do DEV intacto antes e depois.
* `make check-all` (flake8 e mypy no 3.11): zero achados.
* `tests/unit/tools/test_package.py` com o `docs/homologation/` fora do pacote; pacote real de 2,8 MB.
* Bateria Oracle não rodada: nenhuma mudança toca SQL, repositórios ou o agente; o banco foi exercitado pela própria homologação real.

## 5. Estado final

O PROD fica instalado e parado (D2 A): `instance/` com a configuração do ensaio, `var/` com os logs, a massa de teste (4,6 GB em `var/agente0001/inputs`) e as saídas da homologação, e `scripts_ambiente/` com os scripts de exemplo. Para pô-lo em operação, use as linhas do `crontab` do DEPLOYMENT §4.0 com `<TIPO>` = `PROD` e a porta escolhida, e ajuste `[web] allowed_origins`. **Antes de subir um dos dois (DEV ou PROD), confira que o outro está parado**: eles usam o mesmo banco e os mesmos nomes (D1 A).
