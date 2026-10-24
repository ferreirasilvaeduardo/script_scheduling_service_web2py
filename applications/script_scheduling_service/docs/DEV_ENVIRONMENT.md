# Guia de Configuração do Ambiente de Desenvolvimento (SSS)

> Para instalar o SSS em **outro servidor** (usuário de serviço, diretórios, segredos, subida, acesso por túnel, systemd, atualização e troubleshooting), siga o `docs/DEPLOYMENT.md`.

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
  * `applications/script_scheduling_service/static/bootstrap/bootstrap.min.css`
  * `applications/script_scheduling_service/static/bootstrap/bootstrap.bundle.min.js`
* **JavaScript próprio, sem framework:** `applications/script_scheduling_service/static/js/app/`, com o `dom.js` carregado primeiro (AGENTS §2.3). O Alpine.js saiu no CR-021.

---

## 3. Verificação do Ambiente (`check_env.py`)

Antes de iniciar qualquer atividade de desenvolvimento, execute o verificador de ambiente para garantir que todos os pré-requisitos estão satisfeitos:

```bash
cd applications/script_scheduling_service
python scripts/check_env.py
```

O script é somente leitura e exibirá uma tabela detalhada com o status `OK` ou `FALHA` de cada item. O código de retorno será `0` se todos os pré-requisitos forem atendidos, `1` em caso de falha de ativos/estrutura, e `2` se a versão do Python for anterior à 3.6.0. O `check_env.py` confere só o mínimo; o projeto é validado da 3.6.0 à 3.13 (a sintaxe do código continua restrita à 3.6, AGENTS §2.1).

---

## 4. Execução do Servidor de Desenvolvimento

O servidor web é o próprio do SSS (`scripts/run_web.py`, CR-021e); o web2py não roda mais a aplicação. Suba a partir da raiz do repositório (`/portaloptrib/TESHUVA/SSS/DEV/web2py`):

```bash
cd /portaloptrib/TESHUVA/SSS/DEV/web2py
~/.pyenv/versions/3.6.15/bin/python applications/script_scheduling_service/scripts/run_web.py --port 8000
# só conferir configuração e segredos, sem abrir a porta:
~/.pyenv/versions/3.6.15/bin/python applications/script_scheduling_service/scripts/run_web.py --check
```

**A aplicação usa sempre o Oracle** do `[oracle]` do `instance/config.ini` (owner e prefixo; F7.3). Por isso, o Python precisa ter o driver Oracle (`oracledb` ou `cx_Oracle`). Nesta máquina, o 3.6.0 e o 3.6.15 têm; no `bin/start_local.sh`, use `PYTHON=~/.pyenv/versions/3.6.15/bin/python3` (o launcher só aceita interpretador chamado `python3` ou `python3.X`, não o `python` do pyenv). Para parar, `Ctrl+C` ou `SIGTERM`: o servidor espera as requisições em andamento até `[web] socket_timeout_s`.

Antes da primeira subida, crie `instance/config.ini` a partir do `config.ini.example` (`sss_env = DEV`, o `[oracle]` com owner, prefixo e DSN, `secrets_file`, `log_dir` e `work_dir` apontando para pastas suas) e o `secrets.cfg` com o `cookie_key`, dono você e modo `0600`. O passo a passo está no `docs/DEPLOYMENT.md` §7.2 e §7.1.

A aplicação fica no endereço local `127.0.0.1:8000/script_scheduling_service` (porta 8000, caminho `/script_scheduling_service`).

Para subir de forma prática em segundo plano (com nohup, carimbo de data/hora no log e validação de subida):

```bash
cd /portaloptrib/TESHUVA/SSS/DEV/web2py
bin/start_local.sh               # sobe em background na porta 8000
# ou: bin/start_local.sh 18000   # porta customizada
# ou: bin/start_local.sh -f      # em primeiro plano no terminal
bin/stop_local.sh               # SIGTERM; SIGKILL só se não parar em 40 s (SSS_STOP_GRACE_S)
```

O `start_local.sh` recusa subir se o `run_web.py --check` falhar, se `sss_env` não for `DEV` ou se o Python escolhido não tiver o driver Oracle.

Para subir como nos servidores via launcher oficial:
`bin/sss-web.sh "$(command -v python3)" --host 127.0.0.1 --port 8000` (o launcher só aceita interpretador chamado `python3` ou `python3.X` e só inicia o `run_web.py`): ele recusa root, aplica `umask 077`, exporta `TZ` a partir de `SSS_TZ` e `LANG`/`LC_ALL` a partir de `SSS_LOCALE` (padrão `C.UTF-8`) (`docs/DEPLOYMENT.md` §10.1 e Apêndice A).

**Codificação (CR-007):** o processo web aborta se a codificação do sistema de arquivos não for UTF-8 (`sys.getfilesystemencoding()`). Subindo sem o launcher, exporte antes `LANG=C.UTF-8` e `LC_ALL=C.UTF-8` (ou outro locale UTF-8 da máquina, `locale -a`).

**Segredos em DEV (CR-007, D1b):** o `secrets.cfg` do nó web leva só `[web] cookie_key` (e `[oracle] password` com Oracle). Seções do agente (`[environment:*]`, `[purge]`) no arquivo do web geram WARN em DEV e recusam a subida fora de DEV.

### Usuários de homologação

* **No Oracle:** os usuários `admin`, `op.prod`, `op.hml` e `consulta` vêm do seed do `01_deploy_sss.sql`, com a senha padrão de homologação do README §11.1. Troque-as depois da implantação.
* **`SSS_DEV_SEED_PASSWORD`:** só vale para o FAKE dos testes automáticos. A aplicação não usa mais essa variável.
* **Perfis, permissões e dados de apoio de cada usuário:** `docs/homologation/SSS_Homologation_Manual_UI_Freeze.docx`, capítulo 3.

### Regras Mandatórias de Execução:

1. **Escuta estrita em 127.0.0.1:**
   O parâmetro `-i 127.0.0.1` é obrigatório. Nunca utilize `0.0.0.0` em ambiente de desenvolvimento, garantindo isolamento na máquina local.
2. **Sem FAKE na aplicação:** desde o F7.3, a aplicação usa sempre o Oracle (pool de conexões por processo). O FAKE em memória só existe nos testes automáticos.
   * **Trava de segurança:** o FAKE dos testes só é aceito com `sss_env = DEV`; fora de DEV, a `repo_factory` o recusa.

---

## 5. Execução dos Testes Unitários

Todos os testes automatizados utilizam exclusivamente o framework nativo `unittest` do Python (o uso de `pytest` é proibido).

Para executar os testes a partir da aplicação:

```bash
cd applications/script_scheduling_service
python -m unittest discover -s scripts -p "test_*.py"
```

Resultado esperado hoje: `Ran ... tests ... OK (skipped=23)` (794 testes no fechamento do CR-007; o total cresce a cada passo). Os 23 ignorados são do contrato contra Oracle real (`SSS_TEST_DSN`). Rode a suíte na **3.6.0** e na **3.6.8** (AGENTS §7, item 3); a validação do fechamento do CR-005 também passou na 3.13.2, a versão mais nova validada:

```bash
for v in 3.6.0 3.6.8 3.13.2; do PYENV_VERSION=$v python -m unittest discover -s scripts -p "test_*.py"; done
```

O módulo `scripts/_testenv.py` é responsável por configurar o `sys.path` dinamicamente para permitir a importação da aplicação (raiz da aplicação e `modules/`) sem caminhos fixos.

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
| `diagnostico/gerar_saida.sh` | Diagnóstico do CR-020a: grava `resumo.txt` e `detalhes/relatório de testes.csv` em `SSS_OUTPUT_DIR`, para gerar uma saída real e testar a tela de Saídas. Sai com 1 sem a variável |

### 6.1 O que o `path_guard` confere (CR-005, CR-011)

O script fica num **caminho absoluto** em qualquer lugar do servidor (`path_file`, README §8.5); não há pastas base. O ambiente controla o conteúdo e a versão dos scripts (CR-011): não há hash nem conferência do dono.

* **No nó web** (cadastro e disparo): só o formato do caminho e as pastas do sistema. O arquivo não precisa existir na sua máquina, e não há aviso.
* **No agente**, a cada execução:
  * o caminho pode ser link simbólico; o agente resolve o caminho real e executa o arquivo real;
  * o caminho, cadastrado ou real, não fica em pastas do sistema (`/bin`, `/sbin`, `/usr`, `/lib*`, `/etc`, `/boot`, `/proc`, `/sys`, `/dev`, `/root`) nem dentro de `log_dir`, `work_dir` ou `exec_work_dir`;
  * o arquivo real existe, é arquivo regular e não tem escrita para grupo nem para outros (`st_mode & 0o022 == 0`); as pastas do caminho não são conferidas.

Em DEV, uma pasta do seu `$HOME` serve, desde que o arquivo tenha modo `0644` ou `0755`. Os scripts do seed FAKE apontam para `/opt/automacoes/scripts/<arquivo>` (ex.: `/opt/automacoes/scripts/carga_diaria.py`). Para o agente encontrá-los, crie o link uma vez:

```bash
cd applications/script_scheduling_service
chmod -R go-w dev/scripts
sudo install -d -o root -g root -m 0755 /opt/automacoes
sudo ln -sfn "$PWD/dev/scripts" /opt/automacoes/scripts
```

Sem `sudo`, cadastre os scripts com o caminho real de `dev/scripts`.

* As chaves `script_owner_uids` e `ambientes_exigem_hash` foram retiradas (CR-011). Se ainda estiverem no seu `config.ini`, a subida aborta com "Chave removida: ...; apague a linha". Apague a linha.
* As chaves `base_script_dirs` e a antiga `base_script_dir` foram retiradas (CR-005). Se ainda estiverem no seu `config.ini`, a subida aborta com "Chave desconhecida na secao [agent]". Apague a linha.
* `app_log_backups` foi trocada por `app_log_retention_days` (dias de retenção do log da aplicação, README §13).

### 6.2 Onde ficam os logs (CR-005)

* **Log da aplicação:** `log_dir/internal/app/AAAA/MM/DD/HH/MI/sss_web_<PID>.log` (CR-009; até o F8.2 era `log_dir/app/...`, que pode ser apagada à mão). O arquivo nasce na pasta do minuto em que o processo sobe e troca para um novo, na pasta do minuto atual, ao atingir `app_log_max_bytes`. As pastas de dia mais antigas que `app_log_retention_days` são apagadas pelo próprio processo. Para seguir o arquivo mais recente:

  ```bash
  LOG_DIR=/portaloptrib/TESHUVA/SSS/DEV/web2py/applications/script_scheduling_service/logs     # o [logging] log_dir do seu config.ini
  tail -f "$(find "$LOG_DIR/app" -name 'sss_web_*.log' -type f -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-)"
  ```

  A ordem é pela última escrita (`%T@`), e não pelo nome: com dois processos no mesmo minuto, a ordem do nome segue o texto do PID e pode apontar o arquivo errado.
* **Log de execução de cada ticket** (agente, a partir do F8): `log_dir/<ambiente>/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log` (README §8.4; CR-009).

### 6.3 Agente em DEV (a partir do F8, CR-007)

* **`[agent] interpreters` é obrigatório (CR-018d):** sem ele, o agente recusa subir ("[agent] interpreters vazio: o agente nao executaria nada"). O `instance/config.ini` do DEV leva `interpreters = PYTHON3=/usr/bin/python3,BASH=/bin/bash,SH=/bin/sh`, como o `config.ini.example`, e o agente sobe com o config padrão: `PYTHON=~/.pyenv/versions/3.6.15/bin/python3 bin/sss-scheduler.sh` (sem `--config`). Para parar, `SIGTERM` no PID do agente: ele encerra pela máquina de estados (README §8.11).
* **Pasta de trabalho dos scripts (CR-019):** o `instance/config.ini` do DEV leva `script_work_dir = .../script_scheduling_service/script_work` (pasta ignorada pelo git, criada à mão com `0700` antes da primeira subida, porque o agente confere que ela existe). Cada ticket recebe `SSS_WORK_DIR` em `script_work/<ambiente>/<script>/AAAA/MM/DD/HH/MI/ticket_<id>/`, que fica depois do ticket. Com `[retention] purge_user` vazio, o `purge.py` não roda no DEV; a retenção dessa pasta foi conferida chamando a etapa `script_work` do purge diretamente.
* Em DEV, `[agent] exec_users` pode ficar vazio: o agente executa os scripts com o próprio usuário e registra WARN `SEM_USUARIO_EXECUCAO`. Para testar o helper e o `sudo` como nos servidores, siga o `DEPLOYMENT.md` §8 numa VM.
* `cron_horizon_days` vai de 1.461 a 36.500 (CR-008, R-32), `max_log_size_bytes` até 64 MiB e `audit_retention_days` de 365 a 3.650 (e não menor que `ticket_retention_days`); o `table_prefix` só aceita minúsculas. Um `config.ini` antigo fora dessas faixas aborta a subida com a chave no log.
* **CR-008:** `[web] session_max_hours` (padrão 12) e `[agent] log_dir_min_free_mb` (padrão 1.024; 0 desliga, só em DEV) são opcionais. Em DEV, `[oracle] user` pode ser igual ao `owner`; fora de DEV, é recusado. O `scripts/health.py` lê só a seção `[monitor]` do `secrets.cfg`.

---

## 7. Banco Oracle real (F7)

O backend FAKE não precisa de banco. Para o backend ORACLE (README §2.3, CR-002):

* **Driver:** `python-oracledb` (`< 2.0` na 3.6; `2.x` na 3.7+) e `cx_Oracle 8.3` como contingência, com o Oracle Instant Client 19.x. São pré-instalados pela infraestrutura; não use `pip install` no projeto. O projeto não usa a biblioteca `cryptography`: o DEV vem com `driver_mode = thick`, e o modo Thin (que dependeria dela) fica fora de uso.
* **Modo:** `[oracle] driver_mode = auto` tenta Thin → Thick → cx_Oracle por sondagem. Contra banco **11g**, só Thick e cx_Oracle conectam, então o **Instant Client 19** precisa estar instalado:
  * Linux/Unix: no `ldconfig` (preferencial) ou em `LD_LIBRARY_PATH` exportado **antes** de iniciar o Python;
  * macOS (só desenvolvimento): `oracle_client_lib_dir` no `config.ini`. Windows não é suportado (CR-005).
* **Credencial:** só no `secrets.cfg` (`0600`, dono = usuário do processo), nunca no `config.ini`.
* **Inicialização e DDL/DML:**
  * Via Python: `python3 scripts/init_db.py`
  * Via SQL*Plus (autônomo): `sqlplus usuario/senha@//host:porta/servico @docs/sql/01_deploy_sss.sql`
  * Rollback total: `sqlplus usuario/senha@//host:porta/servico @docs/sql/02_rollback_sss.sql`
* **Testes contra banco real:** só `SSS_TEST_ORACLE=1` (README §2.5). Owner, prefixo, DSN e conta vêm do `instance/config.ini`. O modo sai do owner: `SSS_TEST_*` é descartável e qualquer outro é compartilhado. Sem a chave, as partes de banco ficam `NÃO TESTADO` no relatório.
  * **No `GFPR`** (owner `openrisow`, modo compartilhado), o driver Oracle só está instalado no Python 3.6.15 desta máquina. Exemplo para um agregado do F7.3:
    ```bash
    SSS_TEST_ORACLE=1 SSS_TEST_REPO_AGREGADO=TICKETS \
      ~/.pyenv/versions/3.6.15/bin/python -m unittest discover -s scripts -p "test_repo_oracle_progressive.py" -v
    ```
  * **Outro driver:** os testes usam o `[oracle] driver_mode` do config (`auto`, `thin`, `thick` ou `cx_oracle`).
  * **Produção:** só os scripts SQL de `docs/sql/` (`01_deploy_sss.sql`, `02_rollback_sss.sql`, `99_validate_deploy.sql`), sem Python. Os testes acima são só para DEV.
* `python scripts/check_env.py` mostra a combinação de driver escolhida.

---

## 8. Usuários Padrão para Desenvolvimento e Homologação

Para testes interativos na interface web (tanto no backend FAKE quanto no backend ORACLE), utilize os usuários cadastrados no seed:

| Login | Perfil | Permissões Principais | Escopo de Ambientes |
|---|---|---|---|
| `admin` | `ADMINISTRATOR` | Acesso irrestrito a todas as 10 funcionalidades | Todos os 5 ambientes |
| `op.prod` | `OPERATOR_PROD` | `EXEC_SCRIPT`, `VIEW_LOGS`, `CANCEL_TICKET` | Todos os 5 ambientes |
| `op.hml` | `OPERATOR_HML` | `EXEC_SCRIPT`, `VIEW_LOGS`, `CANCEL_TICKET` | `CLONE6`, `CLONE7`, `GFPREPROD` |
| `consulta` | `READ_ONLY` | Apenas consulta (`VIEW_LOGS`) | Todos os 5 ambientes |

* **Senha Inicial Padrão:** `Sss@Homolog2026!` (hash PBKDF2-SHA256 com 200.000 iterações).
* **Troca de Senha:** Disponível na interface em "Minha senha" no cabeçalho.

