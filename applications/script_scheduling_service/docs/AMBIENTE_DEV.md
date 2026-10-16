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

2. Instale o **Python 3.6.8**, a versão de referência do projeto. É a do pacote `python36` do RHEL/Oracle Linux usado em produção. A versão **mínima suportada é a 3.6.0**, que se instala com a mesma receita trocando `3.6.8` por `3.6.0`. Rode a suíte nas duas (AGENTS §7.3).

   Em distribuições recentes, a 3.6.8 **não compila direto** com `pyenv install 3.6.8`, por dois motivos:
   * **GCC 11 ou mais novo:** dá segfault no `ensurepip` durante a instalação, por um bug de alinhamento de memória (bpo-27987) que só foi corrigido na 3.6.15;
   * **OpenSSL 3 do sistema:** a 3.6.8 não reconhece essa versão, e o `_hashlib` não é compilado. O projeto exige `hashlib.pbkdf2_hmac` via OpenSSL para as senhas.

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

3. Instale também a **3.6.0** (mínima suportada) com a mesma receita, trocando `3.6.8` por `3.6.0`, e escolha a versão padrão. Qualquer uma das duas serve como global; a suíte precisa passar **nas duas** (AGENTS §7.3). As demais versões podem ser chamadas pelo caminho completo (ex.: `~/.pyenv/versions/3.13.2/bin/python`):
   ```bash
   pyenv global 3.6.0      # ou 3.6.8
   ```

4. Valide a versão ativa e os módulos críticos:
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

O script é somente leitura e exibirá uma tabela detalhada com o status `OK` ou `FALHA` de cada item. O código de retorno será `0` se todos os pré-requisitos forem atendidos, `1` em caso de falha de ativos/estrutura, e `2` se a versão do Python for anterior à 3.6.0. As versões 3.6.0 a 3.13 são aceitas (a sintaxe do código continua restrita à 3.6, AGENTS §2.1).

---

## 4. Execução do Servidor de Desenvolvimento web2py

O servidor de desenvolvimento do web2py deve ser iniciado a partir da raiz do web2py (`/portaloptrib/TESHUVA/web2py`):

```bash
cd /portaloptrib/TESHUVA/web2py
export SSS_DEV_SEED_PASSWORD='<senha-de-demonstração>'
python web2py.py -a '<senha_administrador>' -i 127.0.0.1 -p 8000 --no_gui
```

A aplicação fica no endereço local `127.0.0.1:8000/script_scheduling_service` (porta 8000, caminho `/script_scheduling_service`).

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

### 6.1 Dono e permissões exigidos pelo `path_guard`

O `path_guard` verifica o script, **cada diretório** entre a base e o script, e a própria base. Para cada um deles exige que:

* o dono seja um UID de `script_owner_uids`;
* não haja escrita para grupo nem para outros (`st_mode & 0o022 == 0`);
* o UID do agente **não** consiga escrever (`os.access(p, os.W_OK)` falso).

Em DEV, o agente roda com o **seu** UID, que também é o dono dos arquivos. Por isso, os modos `0644` (scripts) e `0755` (diretórios) **não** servem: o bit de escrita do dono torna `os.access(W_OK)` verdadeiro, e o `path_guard` rejeita com `GRAVAVEL_PELO_AGENTE`. Use modos somente leitura: **`0444` para scripts e `0555` para diretórios, inclusive a base.**

O Git não preserva esses modos. Por isso, aponte a pasta base `ROTINAS` de `base_script_dirs` para uma **cópia** da árvore:

```bash
cd applications/script_scheduling_service
BASE="$HOME/sss_dev_scripts"
rm -rf "$BASE" 2>/dev/null || { chmod -R u+w "$BASE" && rm -rf "$BASE"; }
cp -r dev/scripts "$BASE"
rm -f "$BASE/.gitkeep"
find "$BASE" -type f -exec chmod 0444 {} +
find "$BASE" -type d -exec chmod 0555 {} +
id -u   # UID a incluir em script_owner_uids
```

Em `instance/config.ini`, seção `[agent]`:

```ini
base_script_dirs = ROTINAS=/home/<usuario>/sss_dev_scripts
script_owner_uids = 0,<seu UID>
```

Para alterar um script da cópia, devolva a escrita temporariamente (`chmod -R u+w "$BASE"`) e volte aos modos acima antes de executar. Executar como `root` não funciona com essa checagem, porque `os.access(W_OK)` é sempre verdadeiro para root.

### 6.2 Windows (a partir do F8.0)

No Windows, a checagem equivalente usa SIDs e ACL, não UID e modo (README §8.5):

* o dono do script, de cada diretório e da base deve ser um SID de `script_owner_sids` (ex.: `S-1-5-32-544`, Administradores);
* a conta do agente, Users, Authenticated Users e Everyone não podem ter direito de escrita **efetivo** na árvore;
* o agente roda com uma conta dedicada, **sem** elevação (token de administrador é recusado).

Em DEV, copie `dev/scripts` para uma pasta própria, transfira o dono para Administradores e remova a herança de escrita (`icacls <pasta> /setowner *S-1-5-32-544 /T` e `icacls <pasta> /inheritance:r /grant:r *S-1-5-32-544:(OI)(CI)F *S-1-5-18:(OI)(CI)F <conta-do-agente>:(OI)(CI)RX`). O roteiro definitivo fica no `RUNBOOK.md` (F9.1).

---

## 7. Banco Oracle real (a partir do F7)

O backend FAKE não precisa de banco. Para o F7 em diante (README §2.3, CR-002):

* **Driver:** `python-oracledb` (`< 2.0` na 3.6; `2.x` na 3.7+) com `cryptography`, e `cx_Oracle 8.3` como contingência. São pré-instalados pela infraestrutura; não use `pip install` no projeto.
* **Modo:** `[oracle] modo_driver = auto` tenta Thin → Thick → cx_Oracle por sondagem. Contra banco **11g**, só Thick e cx_Oracle conectam, então o **Instant Client 19** precisa estar instalado:
  * Linux/Unix: no `ldconfig` (preferencial) ou em `LD_LIBRARY_PATH` exportado **antes** de iniciar o Python;
  * Windows/macOS: `oracle_client_lib_dir` no `config.ini`.
* **Credencial:** só no `secrets.cfg` (`0600`, dono = usuário do processo), nunca no `config.ini`.
* **Testes contra banco real:** defina `SSS_TEST_DSN` (e o usuário/senha de teste conforme o prompt do passo). Sem ela, as partes de banco ficam `NÃO TESTADO` no relatório.
* `python scripts/check_env.py` mostra a combinação de driver escolhida (a partir do F7.0).
