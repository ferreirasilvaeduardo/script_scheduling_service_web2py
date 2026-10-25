PYTHON := python3

# Nome base dos pacotes de deploy com timestamp
DEPLOY_PKG = ./.bkp/deploy_sss_$(shell date +%Y%m%d_%H%M%S).tar.gz
ZIP_FILE   = ./.bkp/deploy_sss_$(shell date +%Y%m%d_%H%M%S).zip
REQ_FILE   = ./.bkp/python_env_requirements_$(shell date +%Y%m%d_%H%M%S).txt

# Lista de módulos de desenvolvimento no Python local
REQUIRED_PACKAGES := isort autopep8 flake8 pylint mypy

# Pastas e padrões a ignorar no lint (tests/ é lintado: os testes saíram de scripts/ no CR-022b1)
EXCLUDES := .pytest_cache .mypy_cache .bkp .sql __pycache__ sss_dev_script_examples sss_packages
PY_FILES := $(shell find . -name "*.py" $(foreach d,$(EXCLUDES),! -path "./$(d)/*"))

.PHONY: check-sqlplus check-runtime check-dev-deps check-deps freeze-req zip-deploy zip-deploy-zip list-deploy format lint type-check check-all test-unit test-integration test-functional test-architecture test-all

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
	@echo "Validação do ambiente Oracle concluída com sucesso.\n"

# Gera snapshot completo: versão do Python, dados do ambiente e lista de bibliotecas
freeze-req: ## Salva snapshot com versão do Python e bibliotecas em ./.bkp
	@mkdir -p ./.bkp
	@echo "# ==================================================" > $(REQ_FILE)
	@echo "# AMBIENTE PYTHON - SNAPSHOT DE DEPENDENCIAS" >> $(REQ_FILE)
	@echo "# Data/Hora: $$(date '+%Y-%m-%d %H:%M:%S')" >> $(REQ_FILE)
	@echo "# Executável: $$($(PYTHON) -c 'import sys; print(sys.executable)')" >> $(REQ_FILE)
	@echo "# Versao Python: $$($(PYTHON) -c 'import sys; print(sys.version.replace("\n", " "))')" >> $(REQ_FILE)
	@echo "# ==================================================" >> $(REQ_FILE)
	@echo "" >> $(REQ_FILE)
	@echo "# --- PACOTES INSTALADOS (FORMATO REQUIREMENTS) ---" >> $(REQ_FILE)
	@$(PYTHON) -m pip freeze >> $(REQ_FILE)
	@echo "" >> $(REQ_FILE)
	@echo "# --- TABELA DETALHADA DE PACOTES (PIP LIST) ---" >> $(REQ_FILE)
	@$(PYTHON) -m pip list >> $(REQ_FILE) 2>/dev/null || true
	@echo "[+] Snapshot do Python e dependências salvo em: $(REQ_FILE)"

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
	@echo "Runtime validado com sucesso.\n"

# Valida as ferramentas de desenvolvimento e formatação locais
check-dev-deps:
	@echo "Verificando dependências de desenvolvimento no Python local..."
	@missing=0; \
	for pkg in $(REQUIRED_PACKAGES); do \
		if ! $(PYTHON) -c "import $$pkg" >/dev/null 2>&1; then \
			echo "[-] Pacote ausente: $$pkg"; \
			missing=1; \
		else \
			echo "[+] OK: $$pkg"; \
		fi; \
	done; \
	if [ $$missing -eq 1 ]; then \
		echo "\nInstale os pacotes ausentes via: $(PYTHON) -m pip install $(REQUIRED_PACKAGES)"; \
		exit 1; \
	fi; \
	echo "Ferramentas de desenvolvimento validadas.\n"

# Valida tanto runtime do projeto quanto dependências de desenvolvimento
check-deps: check-runtime check-dev-deps

# Cria pacote .tar.gz (executa freeze-req automaticamente antes)
zip-deploy: freeze-req ## Cria pacote .tar.gz limpo após gerar o snapshot de dependências
	@mkdir -p ./.bkp
	tar -czvf $(DEPLOY_PKG) \
		--exclude='./.git' \
		--exclude='./.mypy_cache' \
		--exclude='./.pytest_cache' \
		--exclude='./.vscode' \
		--exclude='./.bkp' \
		--exclude='./.sql' \
		--exclude='./.antigravity' \
		--exclude='sss_dev_script_examples' \
		--exclude='sss_packages' \
		--exclude='__pycache__' \
		--exclude='*.pyc' \
		--exclude='*.pyo' \
		--exclude='*.pyd' \
		--exclude='*.log' \
		--exclude='*.env' \
		--exclude='Makefile' \
		--exclude='pytest.ini' \
		--exclude='.flake8' \
		--exclude='.gitignore' \
		--exclude='./sessions/*' \
		--exclude='./errors/*' \
		--exclude='./cache/*' \
		--exclude='./input/*' \
		--exclude='./output/*' \
		--exclude='./logs/*' \
		--exclude='./work/*' \
		--exclude='.parameters_8*.py' \
		--exclude='.parameters_18*.py' \
		--exclude='./databases/storage.sqlite' \
		--exclude='./databases/*.db' \
		.
	@echo "\n[+] Pacote de deploy gerado com sucesso em: $(DEPLOY_PKG)"

# Cria pacote .zip (executa freeze-req automaticamente antes)
zip-deploy-zip: freeze-req ## Gera arquivo .zip nativo após gerar o snapshot de dependências
	@mkdir -p ./.bkp
	zip -r $(ZIP_FILE) . \
		-x "./.git/*" \
		-x "./.mypy_cache/*" \
		-x "./.pytest_cache/*" \
		-x "./.vscode/*" \
		-x "./.bkp/*" \
		-x "./.sql/*" \
		-x "./.antigravity/*" \
		-x "sss_dev_script_examples/*" \
		-x "sss_packages/*" \
		-x "*/__pycache__/*" \
		-x "*.pyc" \
		-x "*.pyo" \
		-x "*.pyd" \
		-x "*.log" \
		-x "*.env" \
		-x "Makefile" \
		-x "pytest.ini" \
		-x ".flake8" \
		-x ".gitignore" \
		-x "./sessions/*" \
		-x "./errors/*" \
		-x "./cache/*" \
		-x "./input/*" \
		-x "./output/*" \
		-x "./logs/*" \
		-x "./work/*" \
		-x ".parameters_8*.py" \
		-x ".parameters_18*.py" \
		-x "./databases/*.db" \
		-x "./databases/storage.sqlite"
	@echo "\n[+] Arquivo .zip gerado: $(ZIP_FILE)"

# Inspeciona o pacote gerado mais recente em ./.bkp
list-deploy: ## Lista os arquivos contidos no pacote mais recente gerado
	@LATEST=$$(ls -t ./.bkp/deploy_sss_* 2>/dev/null | head -n 1); \
	if [ -z "$$LATEST" ]; then \
		echo "[-] Nenhum pacote encontrado em ./.bkp"; \
		exit 1; \
	fi; \
	echo "Inspecionando arquivo: $$LATEST\n"; \
	case "$$LATEST" in \
		*.tar.gz) tar -ztvf "$$LATEST" ;; \
		*.zip)    unzip -l "$$LATEST" ;; \
		*)        echo "Formato não suportado." ;; \
	esac

# Formatação e organização de imports
format: check-deps
	$(PYTHON) -m isort . --skip .pytest_cache --skip .bkp --skip .sql --skip sss_dev_script_examples --skip sss_packages
	$(PYTHON) -m autopep8 --in-place --recursive --exclude .pytest_cache,.bkp,.sql,sss_dev_script_examples,sss_packages .

# Análise estática de código
lint: check-deps
	$(PYTHON) -m flake8 . --exclude=.pytest_cache,.bkp,.sql,sss_dev_script_examples,sss_packages
	$(PYTHON) -m pylint $(PY_FILES)

# Verificação de tipagem
type-check: check-deps
	$(PYTHON) -m mypy --explicit-package-bases . --exclude '(\.pytest_cache|\.bkp|\.sql|sss_dev_script_examples|sss_packages)'

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

# Executa todos os testes e verificações em sequência
check-all: format lint type-check