# Guia de Configuração do Ambiente de Desenvolvimento (SSS)

> Para instalar o SSS em **outro servidor** (uma conta de SO e uma de banco, sem root; pastas, segredos, subida pelo `sss-keepalive.sh` no `cron`, acesso, atualização pelo `sss-update.sh` e problemas), siga o `docs/DEPLOYMENT.md`.

Este documento descreve como configurar o ambiente de desenvolvimento local para o **Script Scheduling Service (SSS)**, executar o verificador de ambiente, iniciar o servidor web em modo de desenvolvimento e rodar a suíte de testes.

---

## 1. Pré-requisitos de Runtime

O projeto utiliza **Python 3.6 estrito**, só com a biblioteca padrão e o driver Oracle; não há framework web (o web2py saiu no CR-021f). Conforme especificado em `AGENTS.md`, o código deve compilar e rodar em CPython 3.6 sem dependências externas adicionais e sem recursos de Python 3.7+.

### 1.1 Instalação do Python 3.6 via pyenv (Linux)

Recomenda-se o uso do `pyenv` para gerenciamento da versão do Python:

1. Instale as dependências de compilação do sistema operacional (exemplo Debian/Ubuntu):
   ```bash
   sudo apt-get update
   sudo apt-get install -y build-essential libssl-dev zlib1g-dev libbz2-dev \
       libreadline-dev libsqlite3-dev libffi-dev tk-dev libncurses5-dev \
       libncursesw5-dev xz-utils curl
   ```

2. Instale o **Python 3.6.8**, a versão de referência do projeto. É a do pacote `python36` do RHEL/Oracle Linux usado em produção. A versão **mínima suportada é a 3.6.0**, que se instala com a mesma receita trocando `3.6.8` por `3.6.0`. Rode a suíte nas duas (AGENTS §7, item 3).

   Em distribuições recentes, a 3.6.8 **não compila direto** com `pyenv install 3.6.8`, por dois motivos:
   * **GCC 11 ou mais novo:** dá segfault no `ensurepip` durante a instalação, por um bug de alinhamento de memória (bpo-27987) que só foi corrigido na 3.6.15;
   * **OpenSSL 3 do sistema:** a 3.6.8 não reconhece essa versão, e o `_hashlib` não é compilado. Sem o `_hashlib`, o `hashlib.pbkdf2_hmac` das senhas cai numa implementação em Python puro: funciona (é o caso do servidor do `docs/DEPLOYMENT.md` Apêndice B.2), mas cada login fica mais lento. Na estação, a receita abaixo compila o `_hashlib` com OpenSSL 1.1.1w, para os testes rodarem na velocidade normal.

   Receita testada no Ubuntu 24.04 (GCC 13, OpenSSL 3), sem `sudo` e sem alterar o sistema:
   ```bash
   # 2.1 OpenSSL 1.1.1w local (somente para o build do Python)
   # Baixe openssl-1.1.1w.tar.gz da página de releases oficial do projeto OpenSSL (tag OpenSSL_1_1_1w)
   # para ~/.local/src e confira o SHA-256 antes de extrair.
   mkdir -p ~/.local/src && cd ~/.local/src
   echo "cf3098950cb4d853ad95c0841f1f9c6d3dc102dccfcacd521d93925208b76ac8  openssl-1.1.1w.tar.gz" | sha256sum -c -
   tar xzf openssl-1.1.1w.tar.gz && cd openssl-1.1.1w
   ./config --prefix=$HOME/.local/openssl-1.1.1w --openssldir=$HOME/.local/openssl-1.1.1w \
       shared zlib -Wl,-rpath,$HOME/.local/openssl-1.1.1w/lib
   make -j"$(nproc)" && make install_sw

   # 2.2 Patch oficial do bpo-27987 (os mesmos arquivos que o pyenv aplica na 3.6.15)
   P=$(pyenv root)/plugins/python-build/share/python-build/patches/3.6.15/Python-3.6.15
   cat "$P"/0009-bpo-27987-*.patch "$P"/0010-bpo-27987-*.patch > /tmp/py368_bpo27987.patch

   # 2.3 Python 3.6.8 com o patch e o OpenSSL 1.1.1w
   O=$HOME/.local/openssl-1.1.1w
   CPPFLAGS="-I$O/include" LDFLAGS="-L$O/lib -Wl,-rpath,$O/lib" \
       pyenv install --patch 3.6.8 < /tmp/py368_bpo27987.patch
   ```

   Em distribuições com GCC 10 ou anterior e OpenSSL 1.1 (ex.: Ubuntu 20.04, RHEL 8), basta `pyenv install 3.6.8`. A 3.6.15 compila direto com `pyenv install 3.6.15` e serve como alternativa, mas a referência de validação é a 3.6.8.

3. Instale também a **3.6.0** (mínima suportada) com a mesma receita, trocando `3.6.8` por `3.6.0`, e escolha a versão padrão. Qualquer uma das duas serve como global; a suíte precisa passar **nas duas** (AGENTS §7, item 3). As demais versões podem ser chamadas pelo caminho completo (ex.: `~/.pyenv/versions/3.13.2/bin/python`):
   ```bash
   pyenv global 3.6.0      # ou 3.6.8
   ```

4. Valide a versão ativa e os módulos da receita (o SSS não exige `ssl` nem `sqlite3`; servem só para conferir que a compilação com o OpenSSL 1.1.1w deu certo):
   ```bash
   python --version
   # Saída esperada: Python 3.6.0 (ou 3.6.8)
   python -c "import ssl, hashlib, _hashlib, sqlite3; print(ssl.OPENSSL_VERSION, hashlib.pbkdf2_hmac is _hashlib.pbkdf2_hmac)"
   # Saída esperada: OpenSSL 1.1.1w  11 Sep 2023 True
   ```

### 1.2 Nota sobre Apple Silicon (macOS ARM64)

O CPython 3.6 foi concebido e lançado antes da existência dos processadores Apple Silicon (M1/M2/M3/M4) e **não possui suporte nativo à compilação em macOS ARM64**. A compilação direta via pyenv em um terminal ARM64 falhará.

Para desenvolver em computadores Apple Silicon, adote uma das seguintes abordagens:

* **Emulação x86_64 via Rosetta 2:**
  Inicie uma sessão de terminal emulada em x86_64:
  ```bash
  arch -x86_64 zsh
  ```
  Nessa sessão, utilize o `pyenv` configurado para arquitetura x86_64 para compilar e executar o Python 3.6.8 (ou a 3.6.15, se o build da 3.6.8 falhar) sob Rosetta 2.
* **Container Linux x86_64 (Recomendado):**
  Utilize um container Docker ou Podman emulado para Linux x86_64 (`--platform linux/amd64`) com Ubuntu 18.04/20.04 ou Debian Buster/Bullseye, onde o Python 3.6 compila e roda de forma estável.

---

## 2. Ativos de Frontend Herméticos

O SSS adota arquitetura de frontend **100% hermética**, em conformidade com políticas restritivas de Content Security Policy (CSP):

* **Sem conexões externas:** É estritamente proibido o uso de CDNs, Google Fonts, diretivas `@import` remotas ou quaisquer recursos baixados da internet em tempo de execução.
* **Bootstrap 5.3.8:** Fornecido localmente nos caminhos:
  * `src/sss/web/static/bootstrap/bootstrap.min.css`
  * `src/sss/web/static/bootstrap/bootstrap.bundle.min.js`
* **JavaScript próprio, sem framework:** `src/sss/web/static/js/app/`, com o `dom.js` carregado primeiro (AGENTS §2.3). O Alpine.js saiu no CR-021.

---

## 3. Verificação do Ambiente (`check_env.py`)

Antes de iniciar qualquer atividade de desenvolvimento, execute o verificador de ambiente para garantir que todos os pré-requisitos estão satisfeitos:

```bash
cd /portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service
python scripts/check_env.py --name web0001
```

O script é somente leitura e exibirá uma tabela detalhada com o status `OK`, `AVISO` ou `FALHA` de cada item, inclusive a conexão ao banco do processo, que ele sempre tenta (CR-033, D6; antes, só com `SSS_TEST_ORACLE=1`), e o orçamento da abertura da conexão. O código de retorno será `0` se todos os pré-requisitos forem atendidos (avisos não reprovam), `1` em caso de falha de ativos, de estrutura ou de conexão, e `2` sem processo (`--name` nem `--config`) ou se a versão do Python for anterior à 3.6.0. O `check_env.py` confere só o mínimo; o projeto é validado da 3.6.0 à 3.13 (a sintaxe do código continua restrita à 3.6, AGENTS §2.1).

---

## 4. Execução do Servidor de Desenvolvimento

O servidor web é o próprio do SSS (`scripts/run_web.py`, CR-021e); o web2py não roda mais a aplicação. Suba a partir da raiz do repositório (`/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service`):

```bash
cd /portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service
~/.pyenv/versions/3.6.15/bin/python scripts/run_web.py --port 8000
# só conferir configuração e segredos, sem abrir a porta:
~/.pyenv/versions/3.6.15/bin/python scripts/run_web.py --check
```

**A aplicação usa sempre o Oracle** do `[oracle]` do config do processo (`instance/web0001/` e `instance/agente0001/`: owner e prefixo; F7.3). Por isso, o Python precisa ter o driver Oracle (`oracledb` ou `cx_Oracle`). Nesta máquina, o 3.6.0 e o 3.6.15 têm; no `bin/start_local.sh`, use `PYTHON=~/.pyenv/versions/3.6.15/bin/python3` (o launcher só aceita interpretador chamado `python3` ou `python3.X`, não o `python` do pyenv). Para parar, `Ctrl+C` ou `SIGTERM`: o servidor espera as requisições em andamento até `[web] socket_timeout_s`.

**Prefixo do DEV (2026-10-29):** o `instance/common.ini` do DEV usa `table_prefix = ssdev_`; o PROD usa `tbsss_`, no mesmo owner (DEPLOYMENT, Apêndice A). O esquema `ssdev_` foi criado pelo `init_db --name agente0001 --real-schema`, com o seed: o `admin` começa com a senha inicial do DEPLOYMENT §5.3, e a homologação a troca no CT-01. Os scripts do DEV ficam em `docs/sql/` ao lado dos do PROD, com o prefixo no nome (`01_deploy_sss_openrisow_ssdev.sql`, `02_rollback_sss_openrisow_ssdev.sql`, `99_validate_deploy_openrisow_ssdev.sql`), gerados por `python3 scripts/generate_sql.py --config instance/agente0001/config.ini`. Para recriar o esquema do DEV: `02_rollback` e `01_deploy` do `ssdev` (apaga os dados), ou um `DROP` das tabelas `ssdev_*` seguido do `init_db`. Os comentários de coluna das FKs citam `tbsss_<tabela>` em todos os prefixos (texto fixo do dicionário, sem efeito). Os `*_s3dev.sql` e `*_s3prd.sql` são do DEV e do PROD do servidor 3067 (`docs/DEPLOYMENT-SERVER.md`, Apêndice A): nunca os rode a partir desta máquina.

**Um agente por ambiente no DEV (2026-10-29):** `agente0001` = GFPREPROD (o de antes, que ficou só com ele: a massa de teste e a pasta de entrada do GFPREPROD continuam em `var/agente0001/`), `agente0002` = CLONE2, `agente0003` = CLONE1, `agente0004` = CLONE6 e `agente0005` = CLONE7. Cada um com o mesmo config enxuto (`max_parallel_jobs = 4`, `script_base_dir` = `dev/scripts`, `env_passthrough`, `level = DEBUG`) e as suas pastas em `var/agente000N/`; o `secrets.cfg` único já tem as credenciais dos cinco ambientes. Subida: `bin/sss-keepalive.sh web0001:18000 agente0001 agente0002 agente0003 agente0004 agente0005` (e `bin/sss-stop.sh` de cada um para parar). O PROD tem a mesma divisão desde o CR-039 (parado, sem `crontab`).

**Estrutura por processo (CR-028):** o DEV tem a mesma estrutura do PROD (DEPLOYMENT §1; não há HOM, CR-030), com `<RAIZ>` = `/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service`: `instance/web0001/` e `instance/agente0001/` a `instance/agente0005/` (cada um com o seu `config.ini`; o `[oracle]` num único `instance/common.ini` e os segredos num único `instance/secrets.cfg` `0600`, os dois fora do git), logs do web em `var/web0001/logs` e as pastas de cada agente em `var/agente000N/` (`logs`, `works`, `outputs`, `inputs`, `script_works`, `files`). Para criar do zero, copie os modelos de `instance/exemplos/` (o `[oracle]` com owner, prefixo e DSN; não há `sss_env` desde o CR-032: o ambiente mostrado vem da pasta `DEV`), as pastas são criadas na subida (CR-032) e siga o `docs/DEPLOYMENT.md` §7. O `bin/start_local.sh` sobe o `web0001` (outro nome com `SSS_WEB_NAME`) e carrega `instance/web0001/web.env` (`SSS_DEV_SEED_PASSWORD` e `SSS_TZ`; `0600`, fora do git). Não há config padrão (CR-029): as ferramentas de banco rodam com `--name agente0001` (`init_db.py`, `generate_sql.py`, `check_env.py`), e a bateria Oracle lê `instance/agente0001/` (config e segredos).

A aplicação fica no endereço local `127.0.0.1:8000/script_scheduling_service` (porta 8000, caminho `/script_scheduling_service`).

Para subir de forma prática em segundo plano (com nohup, carimbo de data/hora no log e validação de subida):

```bash
cd /portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service
bin/start_local.sh               # sobe em background na porta 8000
# ou: bin/start_local.sh 18000   # porta customizada
# ou: bin/start_local.sh -f      # em primeiro plano no terminal
bin/stop_local.sh               # SIGTERM; SIGKILL só se não parar em 40 s (SSS_STOP_GRACE_S)
```

O `start_local.sh` recusa subir se o `run_web.py --check` falhar ou se o Python escolhido não tiver o driver Oracle. A tela mostra `[DEV]` no título da aba e o cabeçalho em outra cor (além da faixa), porque a pasta acima da raiz é `DEV` (CR-032).

Para subir como nos servidores via launcher oficial:
`bin/sss-web.sh "$(command -v python3)" web0001 --host 127.0.0.1 --port 8000` (o launcher só aceita interpretador chamado `python3` ou `python3.X` e só inicia o `run_web.py`): ele recusa root, aplica `umask 077`, exporta `TZ` a partir de `SSS_TZ` e `LANG`/`LC_ALL` a partir de `SSS_LOCALE` (padrão `C.UTF-8`) (`docs/DEPLOYMENT.md` §10.1 e Apêndice A).

**Codificação (CR-007):** o processo web aborta se a codificação do sistema de arquivos não for UTF-8 (`sys.getfilesystemencoding()`). Subindo sem o launcher, exporte antes `LANG=C.UTF-8` e `LC_ALL=C.UTF-8` (ou outro locale UTF-8 da máquina, `locale -a`).

**Segredos em DEV (CR-032, D14):** um único `instance/secrets.cfg` (`0600`, fora do git) com `[oracle] password`, `[web] cookie_key` e os `[environment:*]`; cada processo lê só o que usa.

### Usuários de homologação

* **No Oracle:** os usuários `admin`, `op.prod`, `op.hml` e `consulta` vêm do seed do `01_deploy_sss_<owner>_<prefixo>.sql`, com a senha padrão de homologação do README §11.1. Troque-as depois da implantação.
* **`SSS_DEV_SEED_PASSWORD`:** só vale para o FAKE dos testes automáticos. A aplicação não usa mais essa variável.
* **Perfis, permissões e dados de apoio de cada usuário:** `docs/homologation/SSS_Homologation_Manual_UI_Freeze.docx`, capítulo 3.

### Regras Mandatórias de Execução:

1. **Escuta estrita em 127.0.0.1:**
   O servidor escuta em `127.0.0.1` (padrão do `--host`). Para os usuários entrarem direto por HTTP, o keepalive aceita `web0001:0.0.0.0:<porta>` (CR-032, D19), igual ao PROD (DEPLOYMENT §10.4); na máquina de desenvolvimento, prefira `127.0.0.1`.
2. **Sem FAKE na aplicação:** desde o F7.3, a aplicação usa sempre o Oracle (pool de conexões por processo). O FAKE em memória só existe nos testes automáticos.
   * **Trava de segurança:** o FAKE dos testes só é aceito onde a pasta `dev/` existe (o repositório); no pacote, a `repo_factory` o recusa (CR-032, D11).

---

## 5. Execução dos Testes

Todos os testes automatizados utilizam exclusivamente o framework nativo `unittest` do Python (o uso de `pytest` é proibido).

Os testes ficam em `tests/`, separados pelo recurso que usam (AGENTS §7, item 1; CR-022b1). Rode-os da raiz do repositório:

```bash
cd /portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service
python -m unittest discover -s tests -t .                   # suíte completa (make test-all)
python -m unittest discover -s tests/unit -t .              # só os unitários, sem banco (make test-unit)
python -m unittest tests.unit.core.test_cron_parser         # um arquivo
```

| Pasta | O que roda | Alvo |
|---|---|---|
| `tests/unit/` | Sem banco real nem rede | `make test-unit` |
| `tests/integration/oracle/` | Oracle real, só com `SSS_TEST_ORACLE=1` (sem a chave, tudo pulado) | `make test-integration` |
| `tests/integration/process/` | Processos do sistema (spawn, sinais, ticket_files, launchers) | `make test-integration` |
| `tests/functional/` | A aplicação inteira, por requisição ou com o servidor real | `make test-functional` |
| `tests/architecture/` | Regras lidas no código e nos documentos | `make test-architecture` |

Resultado esperado no encerramento do CR-034, sem `SSS_TEST_ORACLE`: `Ran 1499 tests ... OK (skipped=61)` (o total cresce com os testes novos). Os pulados são, na maior parte, os de `tests/integration/oracle/`. Rode a suíte na **3.6.0** e na **3.6.8** (AGENTS §7, item 3) e, de preferência, também na 3.13.2:

```bash
for v in 3.6.0 3.6.8 3.13.2; do ~/.pyenv/versions/$v/bin/python -m unittest discover -s tests -t .; done
```

O `tests/support/_testenv.py` põe no `sys.path` a raiz da aplicação, `src/` (pacote `sss`, CR-022b3; ferramentas de operação em `sss.cli`, CR-022b8) e `tools/`, calculados a partir do próprio arquivo, e expõe `APP_DIR`. Todo teste o importa primeiro (`from tests.support import _testenv`). Cada pasta de `tests/` tem `__init__.py`: sem ele, o `unittest` do Python 3.6 não descobre os testes da pasta.

**Lint e tipos (CR-022b9, AGENTS §1):** `flake8`, `mypy`, `pylint`, `isort` e `autopep8` ficam no Python 3.11 da máquina de desenvolvimento (o 3.6 não tem as versões atuais), que não precisa de driver Oracle para isso. O Makefile usa esse Python pela variável `DEV_PYTHON` (padrão `~/.pyenv/versions/3.11.11/bin/python3`; CR-033, D4), separada do `PYTHON` da aplicação e dos testes, e o `check-dev-deps` roda cada ferramenta antes (um flake8 que só importa, mas quebra ao carregar os plugins, é recusado):

```bash
make lint          # flake8 na árvore (fora dev/scripts/): zero achados
make type-check    # mypy estrito em src/sss: zero achados
make check-all     # os dois em sequência, sem alterar arquivos (make format reescreve: rode à parte)
make lint DEV_PYTHON=/outro/python3.11   # outro Python das ferramentas
```

O pacote de implantação sai só do `make package` (ou `make package-local`); o `make list-deploy` lista o mais recente. Os antigos `zip-deploy`, `zip-deploy-zip` e `freeze-req` saíram no CR-033 (D4): empacotavam a árvore inteira, com o `instance/secrets.cfg` real, o `LEIA-ME.TXT` e o `var/`.

Arquivo novo ou alterado segue 99 colunas e tipos estritos; a dívida antiga está listada no `.flake8` e no `pyproject.toml` e só diminui.

---

## 6. Árvore de Scripts de Exemplo (`dev/scripts/`)

A pasta `dev/scripts/` contém scripts de exemplo **sem lógica perigosa**, usados pelo `path_guard` (README §8.5), pela compilação do snapshot (README §6) e, mais adiante, pelos testes do executor:

| Arquivo | Comportamento |
|---|---|
| `faturamento/carga_faturas.py` | Imprime os argumentos e sai com 0 |
| `faturamento/conciliacao.sh` | Gera N linhas de saída (`$1`, padrão 10) |
| `infra/limpeza.sh` | Sai com 3 se receber `--falhar`; caso contrário, 0 |
| `infra/longo.py` | Dorme em ciclos e imprime progresso (`[ciclos] [intervalo_s]`), para testes de timeout e cancelamento |
| `relatorios/exporta.sh` | Imprime os argumentos posicionais |
| `carga_diaria.py`, `relatorio_mensal.py`, `validacao_fiscal.py`, `cleanup_tmp.sh`, `sync_tabelas.sh`, `backup_extra.sh` | Correspondem aos `path_file` do seed FAKE e imprimem os argumentos |
| `utilitarios/*.py` e `utilitarios/*.sh` | 14 scripts utilitários de arquivos (zip, tar.gz, divisão, concatenação, encoding, substituição, deduplicação, hash, contagem, filtros, ordenação e limpeza). Detalhes em `docs/UTILITY_SCRIPTS.md` |
| `diagnostico/pasta_trabalho.sh` | Diagnóstico do CR-019: confere `SSS_WORK_DIR`, grava `diagnostico.txt` e `sub/arquivo.txt` na pasta de trabalho e lista o que gravou. Sai com 1 sem a variável e com 2 se a pasta não existir |
| `diagnostico/interp_shebang_ausente.py` | Diagnóstico do CT-32 (CR-025 a CR-027): o `#!` aponta para um executável que não existe; o agente o ignora (linha `[SSS]` no log) e usa o interpretador digitado no disparo ou o do cadastro |
| `diagnostico/pasta_arquivos.sh` | Diagnóstico do CR-037 (CT-33): confere `SSS_FILES_INPUTS_DIR` e `SSS_FILES_OUTPUTS_DIR`, copia os arquivos de `inputs` para `outputs/ticket_<id>/copias/` e grava `resumo.txt`. Sai com 1 sem as variáveis |
| `diagnostico/gerar_saida.sh` | Diagnóstico do CR-020a: grava `resumo.txt` e `detalhes/relatório de testes.csv` em `SSS_OUTPUT_DIR`, para gerar uma saída real e testar a tela de Saídas. Sai com 1 sem a variável |
| `diagnostico/interp_info.py` | Diagnóstico do CR-025: imprime o interpretador que rodou o script (`sys.executable`, versão e `sys.prefix`), para o interpretador digitado no disparo e o virtualenv |
| `diagnostico/interp_py36.py`, `diagnostico/interp_env.py` | Diagnóstico do CR-025 e do CR-026: `#!` com o Python 3.6 do pyenv e `#!/usr/bin/env python3`, que valem sem digitado e vencem o cadastro (CR-027: o digitado vence o `#!`) |
| `diagnostico/interp_sem_shebang.sh` | Diagnóstico do CR-026: sem `#!`, roda pelo digitado no disparo ou pelo cadastro (`sh`) |

### 6.1 O que o `path_guard` confere (CR-005, CR-011, CR-023)

O script fica num **caminho absoluto** em qualquer lugar do servidor ou num caminho **relativo à pasta base** do agente (`path_file`, README §8.5; `[agent] script_base_dir`, CR-023). O ambiente controla o conteúdo e a versão dos scripts (CR-011): não há hash nem conferência do dono.

* **No nó web** (cadastro e disparo): o formato do caminho e, no caminho absoluto, as pastas do sistema e a da aplicação (o relativo só pelo formato). O arquivo não precisa existir na sua máquina, e não há aviso.
* **No agente**, a cada execução:
  * o relativo é juntado à `script_base_dir` (sem ela, `NO_BASE_DIR`);
  * o caminho pode ser link simbólico, inclusive para fora da pasta base; o agente resolve o caminho real e executa o arquivo real;
  * o caminho, juntado ou real, não fica em pastas do sistema (`/bin`, `/sbin`, `/usr`, `/lib*`, `/etc`, `/boot`, `/proc`, `/sys`, `/dev`, `/root`), nem dentro de `log_dir`, `work_dir`, `output_dir`, `input_dir`, `script_work_dir` ou `files_dir`, nem na pasta da aplicação (`dev/` é a exceção onde existe, o repositório);
  * o arquivo real existe, é arquivo regular e não tem escrita para grupo nem para outros (`st_mode & 0o022 == 0`); as pastas do caminho não são conferidas.

**No DEV:** o seed (Oracle e FAKE) e os diagnósticos da homologação usam caminho relativo (`utilitarios/zipar_arquivos.py`, `carga_diaria.py`, `diagnostico/gerar_saida.sh`), e o `instance/agente0001/config.ini` aponta a pasta base para os scripts do repositório:

```ini
[agent]
script_base_dir = /portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/dev/scripts
```

Os arquivos precisam de modo `0644` ou `0755` (`chmod -R go-w dev/scripts`). Uma pasta do seu `$HOME` também serve, com caminho absoluto.

* As chaves `script_owner_uids` e `ambientes_exigem_hash` foram retiradas (CR-011). Se ainda estiverem no seu `config.ini`, a subida segue com o aviso "... ignorada: ...; apague a linha" (CR-036, D6). Apague a linha.
* As chaves `base_script_dirs` e a antiga `base_script_dir` foram retiradas (CR-005). Se ainda estiverem no seu `config.ini`, a subida aborta com "Chave desconhecida na secao [agent]". Apague a linha.
* `app_log_backups` saiu no CR-005, e a retenção do log da aplicação (`app_log_retention_days`) saiu no CR-030: nada é apagado sozinho (limpeza manual, README §11.3).

### 6.2 Onde ficam os logs (CR-005)

* **Log da aplicação:** `log_dir/internal/app/AAAA/MM/DD/HH/MI/sss_web_<PID>.log` (CR-009; até o F8.2 era `log_dir/app/...`, que pode ser apagada à mão). O arquivo nasce na pasta do minuto em que o processo sobe e troca para um novo, na pasta do minuto atual, ao atingir `app_log_max_bytes`. Nada é apagado pelo processo (CR-030; limpeza manual, README §11.3). Para seguir o arquivo mais recente:

  ```bash
  LOG_DIR=/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/var/web0001/logs   # derivado do nome (CR-032)
  tail -f "$(find "$LOG_DIR/internal/app" -name 'sss_web_*.log' -type f -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-)"
  ```

  A ordem é pela última escrita (`%T@`), e não pelo nome: com dois processos no mesmo minuto, a ordem do nome segue o texto do PID e pode apontar o arquivo errado.
* **Log de execução de cada ticket** (agente, a partir do F8): `log_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log` (README §8.4; CR-009).

### 6.3 Agente em DEV (a partir do F8, CR-007)

* **Config enxuto (CR-026, CR-028):** o `instance/agente0001/config.ini` do DEV só tem as chaves obrigatórias e as que fogem do padrão (`name = agente0001`, `environments`, `max_parallel_jobs`, `script_base_dir = <RAIZ>/dev/scripts`, `env_passthrough` e `level = DEBUG`); o do `web0001`, `name`, `level` e `allowed_origins`; o `[oracle]` dos dois fica no `instance/common.ini` (CR-032, D18). As pastas saem do nome. Não há `[agent] interpreters`: o agente procura `python3`, `bash`... no `PATH` do terminal que o subiu. O agente sobe pelo nome: `PYTHON=~/.pyenv/versions/3.6.15/bin/python3 bin/sss-scheduler.sh agente0001`. Para parar, `bin/sss-stop.sh agente0001` ou `SIGTERM` no PID do agente: ele encerra pela máquina de estados (README §8.11).
* **Pasta de trabalho dos scripts (CR-019, CR-028):** no DEV é `var/agente0001/script_works` (padrão do nome; fora do git; criada pelo agente na subida, CR-032). Cada ticket recebe `SSS_WORK_DIR` em `script_works/<ambiente>/<script>/AAAA/MM/DD/HH/MI/ticket_<id>/`, que fica depois do ticket até a limpeza manual (README §11.3, CR-030).
* **DEV igual ao PROD (CR-032, D7, D8, D11):** os scripts rodam com a conta do agente, sem `sudo` nem helper, no DEV e no PROD; não há `sss_env` nem papel monitor. As linhas antigas (`sss_env`, `exec_users`, `exec_work_dir`, `helper_path`, `[monitor]`) só geram aviso.
* `cron_horizon_days` é fixo em 1.461 desde o CR-032 (uma linha antiga só gera aviso); `max_log_size_bytes` vai até 64 MiB e o `table_prefix` só aceita minúsculas: um `config.ini` fora dessas faixas aborta a subida com a chave no log.
* **CR-008:** `[web] session_max_hours` (padrão 12) e `[agent] log_dir_min_free_mb` (padrão 1.024; 0 desliga) são opcionais. `[oracle] user` pode ser igual ao `owner` (CR-032, D11). O `scripts/health.py` usa os segredos e a conta do processo do `--name` (CR-032, D8).

---

## 7. Banco Oracle real (F7)

O backend FAKE não precisa de banco. Para o backend ORACLE (README §2.3, CR-002):

* **Driver:** `python-oracledb` (`< 2.0` na 3.6; `2.x` na 3.7+) e `cx_Oracle 8.3` como contingência, com o Oracle Instant Client 19.x. São pré-instalados pela infraestrutura; não use `pip install` no projeto. O projeto não usa a biblioteca `cryptography`: o DEV vem com `driver_mode = thick`, e o modo Thin (que dependeria dela) fica fora de uso.
* **Modo:** `[oracle] driver_mode = auto` tenta Thin → Thick → cx_Oracle por sondagem. Contra banco **11g**, só Thick e cx_Oracle conectam, então o **Instant Client 19** precisa estar instalado:
  * Linux/Unix: no `ldconfig` (preferencial) ou em `LD_LIBRARY_PATH` exportado **antes** de iniciar o Python;
  * macOS e Windows não são suportados (CR-005; o `oracle_client_lib_dir` saiu no CR-032).
* **Credencial:** só no `secrets.cfg` (`0600`, dono = usuário do processo), nunca no `config.ini`.
* **Inicialização e DDL/DML:**
  * Via Python: `python3 scripts/init_db.py --name agente0001`
  * Via SQL*Plus (autônomo): `sqlplus usuario/senha@//host:porta/servico @docs/sql/01_deploy_sss_openrisow_ssdev.sql`
  * Rollback total: `sqlplus usuario/senha@//host:porta/servico @docs/sql/02_rollback_sss_openrisow_ssdev.sql`
  * **No DEV, só os `*_ssdev.sql`.** Os `*_tbsss.sql` são as tabelas do PROD, no mesmo owner: o `02_rollback_sss_openrisow_tbsss.sql` apagaria o PROD.
* **Testes contra banco real:** só `SSS_TEST_ORACLE=1` (README §2.5). Owner, prefixo, DSN e conta vêm do `[oracle]` do `instance/common.ini` (CR-032, D18; lido pelo `instance/agente0001/config.ini`), e os segredos do `instance/secrets.cfg` único (CR-032).
  * **No `GFPR`** (owner `openrisow`, modo compartilhado), o driver Oracle só está instalado no Python 3.6.15 desta máquina. Exemplo para um agregado do F7.3:
    ```bash
    SSS_TEST_ORACLE=1 SSS_TEST_REPO_AGREGADO=TICKETS \
      ~/.pyenv/versions/3.6.15/bin/python -m unittest tests.integration.oracle.test_repo_oracle_progressive -v
    ```
  * **Outro driver:** os testes usam o `[oracle] driver_mode` do config (`auto`, `thin`, `thick` ou `cx_oracle`).
  * **Produção:** só os scripts SQL de `docs/sql/` (`01_deploy_sss_<owner>_<prefixo>.sql`, `02_rollback_sss_<owner>_<prefixo>.sql`, `99_validate_deploy_<owner>_<prefixo>.sql`), sem Python. Os testes acima são só para DEV.
* `python scripts/check_env.py --name web0001` mostra a combinação de driver escolhida.

---

## 8. Usuários Padrão para Desenvolvimento e Homologação

Para testes interativos na interface web (a aplicação usa sempre o Oracle; o FAKE é só dos testes automáticos), utilize os usuários cadastrados no seed:

| Login | Perfil | Permissões Principais | Escopo de Ambientes |
|---|---|---|---|
| `admin` | `ADMINISTRATOR` | Acesso irrestrito a todas as 14 funcionalidades | Todos os 5 ambientes |
| `op.prod` | `OPERATOR_PROD` | `EXEC_SCRIPT`, `VIEW_LOGS`, `CANCEL_TICKET`, `DOWNLOAD_OUTPUT`, `UPLOAD_INPUT`, `FILES_UPLOAD`, `FILES_DOWNLOAD` | Todos os 5 ambientes |
| `op.hml` | `OPERATOR_HML` | `EXEC_SCRIPT`, `VIEW_LOGS`, `CANCEL_TICKET`, `DOWNLOAD_OUTPUT`, `UPLOAD_INPUT`, `FILES_UPLOAD`, `FILES_DOWNLOAD` | `CLONE6`, `CLONE7`, `GFPREPROD` |
| `consulta` | `READ_ONLY` | Apenas consulta (`VIEW_LOGS`) | Todos os 5 ambientes |

* **Senha Inicial Padrão:** `Sss@Homolog2026!` (hash PBKDF2-SHA256 com 200.000 iterações).
* **Troca de Senha:** Disponível na interface em "Minha senha" no cabeçalho.

