# Guia de Configuração do Ambiente de Desenvolvimento (SSS)

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

2. Instale o Python 3.6.15:
   ```bash
   pyenv install 3.6.15
   ```

3. Configure a versão para o repositório ou terminal:
   ```bash
   pyenv local 3.6.15
   ```

4. Valide a versão ativa:
   ```bash
   python --version
   # Saída esperada: Python 3.6.15
   ```

### 1.2 Nota sobre Apple Silicon (macOS ARM64)

O CPython 3.6 foi concebido e lançado antes da existência dos processadores Apple Silicon (M1/M2/M3/M4) e **não possui suporte nativo à compilação em macOS ARM64**. A compilação direta via pyenv em um terminal ARM64 falhará.

Para desenvolver em computadores Apple Silicon, adote uma das seguintes abordagens:

* **Emulação x86_64 via Rosetta 2:**
  Inicie uma sessão de terminal emulada em x86_64:
  ```bash
  arch -x86_64 zsh
  ```
  Nessa sessão, utilize o `pyenv` configurado para arquitetura x86_64 para compilar e executar o Python 3.6.15 sob Rosetta 2.
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

O script é somente leitura e exibirá uma tabela detalhada com o status `OK` ou `FALHA` de cada item. O código de retorno será `0` se todos os pré-requisitos forem atendidos, `1` em caso de falha de ativos/estrutura, e `2` se a versão do Python for diferente de 3.6.

---

## 4. Execução do Servidor de Desenvolvimento web2py

O servidor de desenvolvimento do web2py deve ser iniciado a partir da raiz do web2py (`/portaloptrib/TESHUVA/web2py`):

```bash
cd /portaloptrib/TESHUVA/web2py
python web2py.py -a '<senha_administrador>' -i 127.0.0.1 -p 8000 --no_gui
```

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
