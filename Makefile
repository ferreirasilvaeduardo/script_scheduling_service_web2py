# Python da aplicação e dos testes (3.6.0 ou superior, com o driver Oracle)
PYTHON := python3
# Python das ferramentas de desenvolvimento (lint, tipos, formatação): o 3.11 da máquina de desenvolvimento
# (CR-022b9; o 3.6 não tem as versões atuais e o flake8/mypy dele quebram). Troque com make lint DEV_PYTHON=...
DEV_PYTHON ?= $(HOME)/.pyenv/versions/3.11.11/bin/python3

# Lista de módulos de desenvolvimento no Python das ferramentas
REQUIRED_PACKAGES := isort autopep8 flake8 pylint mypy

# CR-033 (D4): sairam o zip-deploy, o zip-deploy-zip e o freeze-req, que empacotavam a arvore inteira (com o
# instance/secrets.cfg real, o LEIA-ME.TXT e o var/). O unico pacote e o do make package (DEPLOYMENT §3).
.PHONY: check-sqlplus check-runtime check-dev-deps check-deps list-deploy clean-cache package package-local format lint lint-pylint type-check check-all test-unit test-integration test-functional test-architecture test-all

# Valida o sqlplus, ORACLE_HOME e bibliotecas partilhadas do Instant Client
check-sqlplus:
	@echo "Verificando ambiente Oracle Client (sqlplus, ORACLE_HOME, LD_LIBRARY_PATH)..."
	@if [ -n "$$ORACLE_HOME" ]; then \
		echo "[+] ORACLE_HOME definido: $$ORACLE_HOME"; \
	else \
		echo "[!] Aviso: ORACLE_HOME não está definido no ambiente."; \
	fi
	@if [ -n "$$LD_LIBRARY_PATH" ]; then \
		echo "[+] LD_LIBRARY_PATH definido: $$LD_LIBRARY_PATH"; \
	else \
		echo "[!] Aviso: LD_LIBRARY_PATH não está definido (necessário caso o Instant Client não conste no ldconfig)."; \
	fi
	@if command -v sqlplus >/dev/null 2>&1; then \
		echo "[+] sqlplus encontrado no PATH: $$(which sqlplus)"; \
		sqlplus -V 2>/dev/null || true; \
	elif [ -n "$$ORACLE_HOME" ] && [ -x "$$ORACLE_HOME/bin/sqlplus" ]; then \
		echo "[+] sqlplus encontrado via ORACLE_HOME em: $$ORACLE_HOME/bin/sqlplus"; \
	else \
		echo "[-] Erro: sqlplus não foi encontrado no PATH nem em \$$ORACLE_HOME/bin."; \
		echo "    Certifique-se de que o Oracle Instant Client / Client está instalado e configurado."; \
		exit 1; \
	fi
	@echo "Validação do ambiente Oracle concluída com sucesso."

# Valida o ambiente de runtime do projeto (Python >= 3.6.0 e Driver Oracle homologado)
check-runtime:
	@echo "Verificando ambiente de runtime do projeto..."
	@$(PYTHON) -c 'import sys; assert sys.version_info >= (3, 6, 0), "Python deve ser 3.6.0 ou superior"; print("[+] Versão Python: %s.%s.%s" % sys.version_info[:3])'
	@if $(PYTHON) -c "import oracledb" >/dev/null 2>&1; then \
		echo "[+] Driver detectado: python-oracledb"; \
	elif $(PYTHON) -c "import cx_Oracle" >/dev/null 2>&1; then \
		echo "[+] Driver detectado: cx_Oracle"; \
	else \
		echo "[-] Erro: Nenhum driver Oracle encontrado (necessário python-oracledb ou cx_Oracle)"; \
		exit 1; \
	fi
	@echo "Runtime validado com sucesso."

# Valida as ferramentas de desenvolvimento no DEV_PYTHON: roda cada uma (--version), porque o import
# sozinho passava com um flake8 que quebrava ao carregar os plugins (CR-033)
check-dev-deps:
	@echo "Verificando dependências de desenvolvimento em $(DEV_PYTHON)..."
	@missing=0; \
	for pkg in $(REQUIRED_PACKAGES); do \
		if ! $(DEV_PYTHON) -m $$pkg --version >/dev/null 2>&1; then \
			echo "[-] Pacote ausente: $$pkg"; \
			missing=1; \
		else \
			echo "[+] OK: $$pkg"; \
		fi; \
	done; \
	if [ $$missing -eq 1 ]; then \
		echo "Instale os pacotes ausentes via: $(DEV_PYTHON) -m pip install $(REQUIRED_PACKAGES)"; \
		exit 1; \
	fi; \
	echo "Ferramentas de desenvolvimento validadas."

# Valida tanto runtime do projeto quanto dependências de desenvolvimento
check-deps: check-runtime check-dev-deps

# Apaga as pastas de cache do Python e do mypy em toda a árvore (o .git fica de fora)
clean-cache: ## Apaga todas as pastas __pycache__ e .mypy_cache
	@find . -path ./.git -prune -o -type d \( -name __pycache__ -o -name .mypy_cache \) -prune -print -exec rm -rf {} +
	@echo "[+] Pastas __pycache__ e .mypy_cache apagadas."

# Pacote de implantação seguro (DEPLOYMENT §3): cópia limpa do commit atual (git archive HEAD), sem
# docs/homologation (o package.py já a exclui desde o CR-033, D3; o rm fica como defesa), conferida pelo tools/package.py, que recusa senha, secrets.cfg
# real, código de DEV, o FAKE, testes e __pycache__. Mudança não commitada NÃO entra: faça o commit antes.
PKG_DIR = ./.bkp/pacote_$(shell date +%Y%m%d_%H%M%S)
package: ## Gera sss-<versao>.tar.gz e SHA256SUMS em ./.bkp/pacote_<data> para levar ao servidor
	@if [ -n "$$(git status --porcelain --untracked-files=no -- . ':!LEIA-ME.TXT')" ]; then \
		echo "[!] Aviso: há mudanças não commitadas; o pacote usa só o commit $$(git rev-parse --short HEAD)."; \
	fi
	@set -e; \
	DEST=$(PKG_DIR); TMP=$$(mktemp -d); \
	trap 'rm -rf "$$TMP"' EXIT; \
	git archive HEAD | tar -x -C "$$TMP"; \
	rm -rf "$$TMP/docs/homologation"; \
	mkdir -p "$$DEST"; \
	$(PYTHON) "$$TMP/tools/package.py" --source "$$TMP" --out-dir "$$DEST"; \
	git rev-parse HEAD > "$$DEST/COMMIT"; \
	echo ""; echo "[+] Leve ao servidor os dois arquivos de $$DEST: sss-*.tar.gz e SHA256SUMS"; \
	echo "    No servidor: sha256sum -c SHA256SUMS (DEPLOYMENT §3). COMMIT guarda o commit empacotado."

# Mesmo pacote, mas a partir dos arquivos desta pasta como estão (sem git; inclui o que não foi commitado).
# Copia só o que o tools/package.py empacota (bin, docs, instance/exemplos, scripts, src, AGENTS.md, README.md) e o
# próprio tools/, sem caches e sem docs/homologation; de instance/ só os modelos (CR-029: os instance/<nome>/ têm as
# senhas reais e nunca são copiados). A conferência do
# package.py é a mesma: senha fora do placeholder, código de DEV, o FAKE, testes ou link simbólico recusam o pacote.
PKG_LOCAL_DIR = ./.bkp/pacote_local_$(shell date +%Y%m%d_%H%M%S)
package-local: ## Gera o pacote a partir dos arquivos locais (sem git) em ./.bkp/pacote_local_<data>
	@set -e; \
	DEST=$(PKG_LOCAL_DIR); TMP=$$(mktemp -d); \
	trap 'rm -rf "$$TMP"' EXIT; \
	rsync -aR \
		--exclude='__pycache__/' --exclude='*.pyc' --exclude='*.pyo' --exclude='.mypy_cache/' \
		--exclude='docs/homologation/' \
		bin docs instance/exemplos scripts src tools AGENTS.md README.md "$$TMP/"; \
	mkdir -p "$$DEST"; \
	$(PYTHON) -B "$$TMP/tools/package.py" --source "$$TMP" --out-dir "$$DEST"; \
	{ echo "Origem: arquivos locais de $$(pwd) em $$(date '+%Y-%m-%d %H:%M:%S')"; \
	  if git rev-parse --short HEAD >/dev/null 2>&1; then \
		echo "Commit de base: $$(git rev-parse --short HEAD) (mais as mudanças locais abaixo)"; \
		git status --short -- bin docs instance/exemplos scripts src AGENTS.md README.md; \
	  fi; } > "$$DEST/ORIGEM"; \
	echo ""; echo "[+] Leve ao servidor os dois arquivos de $$DEST: sss-*.tar.gz e SHA256SUMS"; \
	echo "    No servidor: sha256sum -c SHA256SUMS (DEPLOYMENT §3). ORIGEM diz de onde veio o pacote."

# Inspeciona o pacote mais recente do make package ou do make package-local em ./.bkp
list-deploy: ## Lista os arquivos contidos no pacote mais recente gerado
	@LATEST=$$(ls -t ./.bkp/pacote_*/sss-*.tar.gz 2>/dev/null | head -n 1); \
	if [ -z "$$LATEST" ]; then \
		echo "[-] Nenhum pacote encontrado em ./.bkp"; \
		exit 1; \
	fi; \
	echo "Inspecionando arquivo: $$LATEST"; echo ""; \
	tar -ztvf "$$LATEST"

# Formatação e organização de imports
# Reescreve os arquivos (fora do check-all desde o CR-033, D4: um check nao altera a arvore)
format: check-dev-deps
	$(DEV_PYTHON) -m isort . --skip .pytest_cache --skip .bkp --skip .sql --skip sss_dev_script_examples --skip sss_packages
	$(DEV_PYTHON) -m autopep8 --in-place --recursive --exclude .pytest_cache,.bkp,.sql,sss_dev_script_examples,sss_packages .

# Análise estática de código (CR-022b9, D7): portão com zero achados na árvore inteira.
# Configuração no .flake8 (99 colunas, a dívida por arquivo, que só diminui, e dev/scripts/ fora).
# Sem lista de arquivos na linha de comando: o flake8 ignora o exclude para arquivo passado à mão.
lint: check-dev-deps
	$(DEV_PYTHON) -m flake8 .

# pylint fora do portão (muito ruído na dívida atual); configuração no pyproject.toml
lint-pylint: check-dev-deps
	$(DEV_PYTHON) -m pylint $$(git ls-files '*.py')

# Verificação de tipagem (CR-022b9, D7): mypy estrito em src/sss, com a dívida listada no pyproject.toml
type-check: check-dev-deps
	$(DEV_PYTHON) -m mypy

# Testes (AGENTS.md §7, CR-022b1): unittest a partir da raiz; o Oracle real só com SSS_TEST_ORACLE=1
test-unit:
	$(PYTHON) -m unittest discover -s tests/unit -t .

test-integration:
	$(PYTHON) -m unittest discover -s tests/integration -t .

test-functional:
	$(PYTHON) -m unittest discover -s tests/functional -t .

test-architecture:
	$(PYTHON) -m unittest discover -s tests/architecture -t .

test-all:
	$(PYTHON) -m unittest discover -s tests -t .

# Portões de qualidade em sequência, sem alterar arquivos (rode make format antes, se quiser formatar)
check-all: lint type-check