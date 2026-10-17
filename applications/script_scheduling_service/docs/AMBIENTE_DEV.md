# Guia de Configuração do Ambiente de Desenvolvimento (SSS)

> Para instalar o SSS em **outro servidor** (usuário de serviço, diretórios, segredos, subida, acesso por túnel, systemd, atualização e troubleshooting), siga o `docs/IMPLANTACAO.md`.

Este documento descreve como configurar o ambiente de desenvolvimento local para o **Script Scheduling Service (SSS)**, executar o verificador de ambiente, iniciar o servidor web2py em modo de desenvolvimento e rodar a suíte de testes.

---

## 1. Pré-requisitos de Runtime

O projeto utiliza **Python 3.6 estrito** e o framework **web2py**. Conforme especificado em `AGENTS.md`, o código deve compilar e rodar em CPython 3.6 sem dependências externas adicionais e sem recursos de Python 3.7+.

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
   * **OpenSSL 3 do sistema:** a 3.6.8 não reconhece essa versão, e o `_hashlib` não é compilado. Sem o `_hashlib`, o `hashlib.pbkdf2_hmac` das senhas cai numa implementação em Python puro: funciona (é o caso do servidor do `docs/IMPLANTACAO.md` §22), mas cada login fica mais lento. Na estação, a receita abaixo compila o `_hashlib` com OpenSSL 1.1.1w, para os testes rodarem na velocidade normal.

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
* **Alpine.js (build CSP):** Fornecido localmente em:
  * `applications/script_scheduling_service/static/js/alpine.min.js`
  * O build CSP (`@alpinejs/csp`) não utiliza `new Function` ou `eval`, permitindo o cumprimento da política CSP `script-src 'self'`.

---

## 3. Verificação do Ambiente (`check_env.py`)

Antes de iniciar qualquer atividade de desenvolvimento, execute o verificador de ambiente para garantir que todos os pré-requisitos estão satisfeitos:

```bash
cd applications/script_scheduling_service
python scripts/check_env.py
```

O script é somente leitura e exibirá uma tabela detalhada com o status `OK` ou `FALHA` de cada item. O código de retorno será `0` se todos os pré-requisitos forem atendidos, `1` em caso de falha de ativos/estrutura, e `2` se a versão do Python for anterior à 3.6.0. O `check_env.py` confere só o mínimo; o projeto é validado da 3.6.0 à 3.13 (a sintaxe do código continua restrita à 3.6, AGENTS §2.1).

---

## 4. Execução do Servidor de Desenvolvimento web2py

O servidor de desenvolvimento do web2py deve ser iniciado a partir da raiz do web2py (`/portaloptrib/TESHUVA/web2py`):

```bash
cd /portaloptrib/TESHUVA/web2py
read -s -p "SSS_DEV_SEED_PASSWORD: " SSS_DEV_SEED_PASSWORD && export SSS_DEV_SEED_PASSWORD && echo
python web2py.py -a '<recycle>' -i 127.0.0.1 -p 8000 --no_gui
```

O `read -s` não deixa a senha no histórico do shell, e o `-a '<recycle>'` desabilita o painel do web2py sem pôr senha na lista de processos (`docs/IMPLANTACAO.md` §11.1).

Antes da primeira subida, crie `instance/config.ini` a partir do `config.ini.example` (`sss_env = DEV`, `data_backend = FAKE`, `secrets_file`, `log_dir` e `work_dir` apontando para pastas suas) e o `secrets.cfg` com o `cookie_key`, dono você e modo `0600`. O passo a passo está no `docs/IMPLANTACAO.md` §8.2 e §9.

A aplicação fica no endereço local `127.0.0.1:8000/script_scheduling_service` (porta 8000, caminho `/script_scheduling_service`).

Para subir como nos servidores, use o launcher `bin/sss-web.sh "$(command -v python3)" web2py.py -a '<recycle>' -i 127.0.0.1 -p 8000 --no_gui` (o launcher só aceita interpretador chamado `python3` ou `python3.X`): ele recusa root, aplica `umask 077`, exporta `TZ` a partir de `SSS_TZ` e `LANG`/`LC_ALL` a partir de `SSS_LOCALE` (padrão `C.UTF-8`) (`docs/IMPLANTACAO.md` §11.1).

**Codificação (CR-007):** o processo web aborta se a codificação do sistema de arquivos não for UTF-8 (`sys.getfilesystemencoding()`). Subindo sem o launcher, exporte antes `LANG=C.UTF-8` e `LC_ALL=C.UTF-8` (ou outro locale UTF-8 da máquina, `locale -a`).

**Segredos em DEV (CR-007, D1b):** o `secrets.cfg` do nó web leva só `[web] cookie_key` (e `[oracle] password` com Oracle). Seções do agente (`[ambiente:*]`, `[purge]`) no arquivo do web geram WARN em DEV e recusam a subida fora de DEV.

### Senha dos usuários de demonstração (`SSS_DEV_SEED_PASSWORD`)

* Com `data_backend = FAKE`, o seed define a senha de **todos** os usuários de demonstração (`admin`, `op.prod`, `op.hml`, `consulta`) a partir dessa variável de ambiente. `inativo` e `bloqueado` nunca conseguem entrar, de propósito.
* A senha precisa atender à política (mínimo de 12 caracteres). Sem a variável, ou fora da política, a aplicação sobe, registra um WARN e **nenhum login funciona**.
* Nenhuma senha fica no código nem no `config.ini`. A variável é registrada no mascarador e não aparece nos logs.
* O FAKE guarda tudo em memória: reiniciar o servidor restaura o seed (útil para repetir testes e a homologação).
* Perfis, permissões e dados de apoio de cada usuário: `docs/homologacao/SSS_Manual_Homologacao_UI_Freeze.docx`, capítulo 3.

### Regras Mandatórias de Execução:

1. **Escuta estrita em 127.0.0.1:**
   O parâmetro `-i 127.0.0.1` é obrigatório. Nunca utilize `0.0.0.0` em ambiente de desenvolvimento, garantindo isolamento na máquina local.
2. **Processo único para backend FAKE (Aviso Crítico):**
   * O backend em memória (`data_backend = FAKE` em `modules/repo_fake/`) mantém o estado e as tabelas na memória do processo em execução.
   * Portanto, **o backend FAKE exige estritamente um servidor web de processo único**, que é o comportamento padrão do servidor embutido do web2py (`web2py.py`).
   * Não execute o web2py com múltiplos workers (como via gunicorn ou uWSGI multiprocessado) durante o uso do backend FAKE, pois cada worker manteria um estado em memória diferente, quebrando a consistência das transações e dos dados.
   * **Trava de segurança:** O backend FAKE só é aceito quando `sss_env = DEV`. Em ambientes `HML` e `PROD`, a aplicação aborta a inicialização imediatamente.

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

O módulo `scripts/_testenv.py` é responsável por configurar o `sys.path` dinamicamente para permitir a importação dos módulos da aplicação (`modules/`) e do web2py (`gluon`) sem caminhos fixos.

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

### 6.1 Dono e permissões exigidos pelo `path_guard` (CR-005)

O script fica num **caminho absoluto** em qualquer lugar do servidor (`path_file`, README §8.5); não há pastas base. O `path_guard` confere o arquivo e **cada diretório até `/`**:

* o dono do arquivo é um UID de `script_owner_uids`; o dono de cada diretório é o root ou um UID de `script_owner_uids`;
* nenhum deles tem escrita para grupo ou outros (`st_mode & 0o022 == 0`), o que exclui `/tmp` e pastas compartilhadas;
* o usuário que roda o SSS **não** consegue escrever em nenhum deles (`os.access(p, os.W_OK)` falso), e nenhum deles pertence a esse usuário nem a um usuário de execução (CR-007);
* não há link simbólico em nenhum ponto do caminho (`CAMINHO_COM_LINK`, CR-007): o caminho cadastrado é igual ao `realpath`;
* o caminho, digitado ou resolvido, não fica em pastas do sistema (`/bin`, `/sbin`, `/usr`, `/lib*`, `/etc`, `/boot`, `/proc`, `/sys`, `/dev`, `/root`) nem dentro de `log_dir` ou `work_dir`.

Por causa da cadeia até `/`, **nenhuma pasta dentro do seu `$HOME` passa**: o próprio `$HOME` pertence a você e tem escrita do dono, então o `path_guard` recusa com `GRAVAVEL_PELO_AGENTE` ("O arquivo, ou uma pasta do caminho, é gravável pelo usuário do sistema; ajuste as permissões."). Executar como `root` também não resolve: o launcher recusa root, e `os.access(W_OK)` é sempre verdadeiro para ele.

Os scripts do seed FAKE apontam para `/opt/automacoes/scripts/<arquivo>` (ex.: `/opt/automacoes/scripts/carga_diaria.py`). Há duas formas de trabalhar:

**A. Com `sudo` (validação completa no nó web):** instale a árvore como root, no caminho do seed:

```bash
cd applications/script_scheduling_service
sudo install -d -o root -g root -m 0755 /opt/automacoes
sudo rm -rf /opt/automacoes/scripts
sudo cp -r dev/scripts /opt/automacoes/scripts
sudo rm -f /opt/automacoes/scripts/.gitkeep
sudo chown -R root:root /opt/automacoes/scripts
sudo find /opt/automacoes/scripts -type d -exec chmod 0755 {} +
sudo find /opt/automacoes/scripts -type f -exec chmod 0644 {} +
```

Em `instance/config.ini`, seção `[agent]`: `script_owner_uids = 0` (o padrão do exemplo). Para alterar um script, use `sudo` e mantenha os modos acima.

**B. Sem `sudo`:** não instale nada. Como os arquivos do seed não existem na sua máquina, o nó web segue o README §8.5 (D4): ao salvar um script na **Gestão de Scripts** aparece o aviso "Arquivo não encontrado neste servidor: a validação ocorrerá no agente. Se o arquivo não existir lá, a execução será recusada.", e o disparo cria o ticket normalmente (o log registra `arquivo do script nao existe no no web; o agente confere`). Para ver uma recusa de permissão na tela, cadastre um caminho dentro do seu `$HOME`, por exemplo `$PWD/dev/scripts/carga_diaria.py`: o salvamento é bloqueado. Com `script_owner_uids = 0`, a recusa é `DONO_INVALIDO` ("O arquivo, ou uma pasta do caminho, pertence a um usuário não autorizado."); com o seu UID incluído, é `GRAVAVEL_PELO_AGENTE`.

* As chaves `base_script_dirs` e a antiga `base_script_dir` foram retiradas (CR-005). Se ainda estiverem no seu `config.ini`, a subida aborta com "Chave desconhecida na secao [agent]". Apague a linha.
* `app_log_backups` foi trocada por `app_log_retention_days` (dias de retenção do log da aplicação, README §13).

### 6.2 Onde ficam os logs (CR-005)

* **Log da aplicação:** `log_dir/app/AAAA/MM/DD/HH/MI/sss_web_<PID>.log`. O arquivo nasce na pasta do minuto em que o processo sobe e troca para um novo, na pasta do minuto atual, ao atingir `app_log_max_bytes`. As pastas de dia mais antigas que `app_log_retention_days` são apagadas pelo próprio processo. Para seguir o arquivo mais recente:

  ```bash
  LOG_DIR=/var/log/sss     # o [logging] log_dir do seu config.ini
  tail -f "$(find "$LOG_DIR/app" -name 'sss_web_*.log' -type f -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-)"
  ```

  A ordem é pela última escrita (`%T@`), e não pelo nome: com dois processos no mesmo minuto, a ordem do nome segue o texto do PID e pode apontar o arquivo errado.
* **Log de execução de cada ticket** (agente, a partir do F8): `log_dir/<pasta do script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log` (README §8.4).

### 6.3 Agente em DEV (a partir do F8, CR-007)

* Em DEV, `[agent] usuarios_execucao` pode ficar vazio: o agente executa os scripts com o próprio usuário e registra WARN `SEM_USUARIO_EXECUCAO`. Para testar o helper e o `sudo` como nos servidores, siga o `IMPLANTACAO.md` §18.1 numa VM.
* `cron_horizon_days` vai de 1.461 a 36.500 (CR-008, R-32), `max_log_size_bytes` até 64 MiB e `audit_retention_days` de 365 a 3.650 (e não menor que `ticket_retention_days`); o `table_prefix` só aceita minúsculas. Um `config.ini` antigo fora dessas faixas aborta a subida com a chave no log.
* **CR-008:** `[web] sessao_max_horas` (padrão 12), `[agent] ambientes_exigem_hash` (vazio em DEV, sem aviso) e `[agent] log_dir_min_livre_mb` (padrão 1.024; 0 desliga, só em DEV) são opcionais. Em DEV, `[oracle] user` pode ser igual ao `owner`; fora de DEV, é recusado. O `scripts/saude.py` lê só a seção `[monitor]` do `secrets.cfg`.

---

## 7. Banco Oracle real (a partir do F7)

O backend FAKE não precisa de banco. Para o F7 em diante (README §2.3, CR-002):

* **Driver:** `python-oracledb` (`< 2.0` na 3.6; `2.x` na 3.7+) com `cryptography`, e `cx_Oracle 8.3` como contingência. São pré-instalados pela infraestrutura; não use `pip install` no projeto.
* **Modo:** `[oracle] modo_driver = auto` tenta Thin → Thick → cx_Oracle por sondagem. Contra banco **11g**, só Thick e cx_Oracle conectam, então o **Instant Client 19** precisa estar instalado:
  * Linux/Unix: no `ldconfig` (preferencial) ou em `LD_LIBRARY_PATH` exportado **antes** de iniciar o Python;
  * macOS (só desenvolvimento): `oracle_client_lib_dir` no `config.ini`. Windows não é suportado (CR-005).
* **Credencial:** só no `secrets.cfg` (`0600`, dono = usuário do processo), nunca no `config.ini`.
* **Testes contra banco real:** defina `SSS_TEST_DSN` (e o usuário/senha de teste conforme o prompt do passo). Sem ela, as partes de banco ficam `NÃO TESTADO` no relatório.
* `python scripts/check_env.py` mostra a combinação de driver escolhida (a partir do F7.0).
