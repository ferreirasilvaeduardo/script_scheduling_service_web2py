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
.PHONY: help dev-start dev-stop ctl check-env health probe-driver sql sql-all init-db-dry test-matrix test-oracle homolog-massa homolog homolog-docx tunel-3067

# Parametros dos alvos de operacao (2026-10-30): troque na linha do make (ex.: make health NAME=agente0002)
NAME := agente0001
CMD := status
OWNER := openrisow
PREFIX := tbsss_
# Prefixos com SQL versionado em docs/sql: PROD e DEV desta maquina e DEV e PROD do 3067
SQL_PREFIXES ?= tbsss_ ssdev_ s3dev_ s3prd_
# Pythons da bateria completa (AGENTS §2.1: sintaxe 3.6, execucao de 3.6.0 a 3.13)
PYTHONS ?= $(HOME)/.pyenv/versions/3.6.0/bin/python $(HOME)/.pyenv/versions/3.6.15/bin/python $(HOME)/.pyenv/versions/3.13.2/bin/python
HOMOLOG_TOOLS := dev/others/homologation/tools

# Valida o sqlplus, ORACLE_HOME e bibliotecas partilhadas do Instant Client
check-sqlplus: ## Confere o sqlplus, o ORACLE_HOME e as bibliotecas do Instant Client
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
check-runtime: ## Confere o Python da aplicacao (PYTHON) e o driver Oracle
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
check-dev-deps: ## Confere as ferramentas de desenvolvimento no DEV_PYTHON
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
check-deps: check-runtime check-dev-deps ## check-runtime e check-dev-deps

# Apaga as pastas de cache do Python e do mypy em toda a árvore (o .git fica de fora)
clean-cache: ## Apaga todas as pastas __pycache__ e .mypy_cache
	@find . -path ./.git -prune -o -type d \( -name __pycache__ -o -name .mypy_cache \) -prune -print -exec rm -rf {} +
	@echo "[+] Pastas __pycache__ e .mypy_cache apagadas."

# Pacote de implantação seguro (DEPLOYMENT §3): cópia limpa do commit atual (git archive HEAD), sem
# docs/homologation (o package.py já a exclui desde o CR-033, D3; o rm fica como defesa), conferida pelo tools/package.py, que recusa senha, secrets.cfg
# real, código de DEV, o FAKE, testes e __pycache__. Mudança não commitada NÃO entra: faça o commit antes.
PKG_DIR = ./.bkp/pacote_$(shell date +%Y%m%d_%H%M%S)
package: ## Gera em ./.bkp/pacote_<data> os arquivos para o servidor: sss-<versao>.tar.gz (BUILD = commit), utilitarios.tar.gz, sss_vars.sh e SHA256SUMS
	@if [ -n "$$(git status --porcelain --untracked-files=no -- . ':!LEIA-ME.TXT')" ]; then \
		echo "[!] Aviso: há mudanças não commitadas; o pacote usa só o commit $$(git rev-parse --short HEAD)."; \
	fi
	@set -e; \
	DEST=$(PKG_DIR); TMP=$$(mktemp -d); \
	trap 'rm -rf "$$TMP"' EXIT; \
	git archive HEAD | tar -x -C "$$TMP"; \
	rm -rf "$$TMP/docs/homologation"; \
	mkdir -p "$$DEST"; \
	$(PYTHON) "$$TMP/tools/package.py" --source "$$TMP" --out-dir "$$DEST" --build "$$(git rev-parse --short=7 HEAD)"; \
	git rev-parse HEAD > "$$DEST/COMMIT"; \
	UTIL_ROOT="$$TMP"; \
	tar -czf "$$DEST/utilitarios.tar.gz" --exclude=__pycache__ --exclude='*.pyc' -C "$$UTIL_ROOT" dev/scripts/utilitarios; \
	VARS="$${SSS_VARS:-$$HOME/sss_pacote/sss_vars.sh}"; \
	if [ -f "$$VARS" ]; then cp "$$VARS" "$$DEST/sss_vars.sh"; chmod 0600 "$$DEST/sss_vars.sh"; \
	else echo "[!] Sem sss_vars.sh ($$VARS): o pacote sai sem ele (defina SSS_VARS=<arquivo>)."; fi; \
	(cd "$$DEST" && sha256sum utilitarios.tar.gz $$([ -f sss_vars.sh ] && echo sss_vars.sh) >> SHA256SUMS \
		&& sha256sum -c --quiet SHA256SUMS); \
	echo ""; echo "[+] Leve ao servidor os arquivos de $$DEST: $$(cd "$$DEST" && ls | tr '\n' ' ')"; \
	echo "    No servidor: sha256sum -c SHA256SUMS (DEPLOYMENT §3). COMMIT guarda o commit empacotado."

# Mesmo pacote, mas a partir dos arquivos desta pasta como estão (sem git; inclui o que não foi commitado).
# Copia só o que o tools/package.py empacota (bin, docs, instance/exemplos, scripts, src, AGENTS.md, README.md) e o
# próprio tools/, sem caches e sem docs/homologation; de instance/ só os modelos (CR-029: os instance/<nome>/ têm as
# senhas reais e nunca são copiados). A conferência do
# package.py é a mesma: senha fora do placeholder, código de DEV, o FAKE, testes ou link simbólico recusam o pacote.
PKG_LOCAL_DIR = ./.bkp/pacote_local_$(shell date +%Y%m%d_%H%M%S)
package-local: ## O mesmo a partir dos arquivos locais (sem git; BUILD = AAMMDDHHMM) em ./.bkp/pacote_local_<data>
	@set -e; \
	DEST=$(PKG_LOCAL_DIR); TMP=$$(mktemp -d); \
	trap 'rm -rf "$$TMP"' EXIT; \
	rsync -aR \
		--exclude='__pycache__/' --exclude='*.pyc' --exclude='*.pyo' --exclude='.mypy_cache/' \
		--exclude='docs/homologation/' \
		bin docs instance/exemplos scripts src tools AGENTS.md README.md "$$TMP/"; \
	mkdir -p "$$DEST"; \
	$(PYTHON) -B "$$TMP/tools/package.py" --source "$$TMP" --out-dir "$$DEST" --build "$$(date +%y%m%d%H%M)"; \
	{ echo "Origem: arquivos locais de $$(pwd) em $$(date '+%Y-%m-%d %H:%M:%S')"; \
	  if git rev-parse --short HEAD >/dev/null 2>&1; then \
		echo "Commit de base: $$(git rev-parse --short HEAD) (mais as mudanças locais abaixo)"; \
		git status --short -- bin docs instance/exemplos scripts src AGENTS.md README.md; \
	  fi; } > "$$DEST/ORIGEM"; \
	UTIL_ROOT="$$(pwd)"; \
	tar -czf "$$DEST/utilitarios.tar.gz" --exclude=__pycache__ --exclude='*.pyc' -C "$$UTIL_ROOT" dev/scripts/utilitarios; \
	VARS="$${SSS_VARS:-$$HOME/sss_pacote/sss_vars.sh}"; \
	if [ -f "$$VARS" ]; then cp "$$VARS" "$$DEST/sss_vars.sh"; chmod 0600 "$$DEST/sss_vars.sh"; \
	else echo "[!] Sem sss_vars.sh ($$VARS): o pacote sai sem ele (defina SSS_VARS=<arquivo>)."; fi; \
	(cd "$$DEST" && sha256sum utilitarios.tar.gz $$([ -f sss_vars.sh ] && echo sss_vars.sh) >> SHA256SUMS \
		&& sha256sum -c --quiet SHA256SUMS); \
	echo ""; echo "[+] Leve ao servidor os arquivos de $$DEST: $$(cd "$$DEST" && ls | tr '\n' ' ')"; \
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
format: check-dev-deps ## Formata e ordena imports (reescreve os arquivos)
	$(DEV_PYTHON) -m isort . --skip .pytest_cache --skip .bkp --skip .sql --skip sss_dev_script_examples --skip sss_packages
	$(DEV_PYTHON) -m autopep8 --in-place --recursive --exclude .pytest_cache,.bkp,.sql,sss_dev_script_examples,sss_packages .

# Análise estática de código (CR-022b9, D7): portão com zero achados na árvore inteira.
# Configuração no .flake8 (99 colunas, a dívida por arquivo, que só diminui, e dev/scripts/ fora).
# Sem lista de arquivos na linha de comando: o flake8 ignora o exclude para arquivo passado à mão.
lint: check-dev-deps ## flake8 na arvore inteira (portao)
	$(DEV_PYTHON) -m flake8 .

# pylint fora do portão (muito ruído na dívida atual); configuração no pyproject.toml
lint-pylint: check-dev-deps ## pylint (fora do portao)
	$(DEV_PYTHON) -m pylint $$(git ls-files '*.py')

# Verificação de tipagem (CR-022b9, D7): mypy estrito em src/sss, com a dívida listada no pyproject.toml
type-check: check-dev-deps ## mypy estrito em src/sss (portao)
	$(DEV_PYTHON) -m mypy

# Testes (AGENTS.md §7, CR-022b1): unittest a partir da raiz; o Oracle real só com SSS_TEST_ORACLE=1
test-unit: ## Testes unitarios
	$(PYTHON) -m unittest discover -s tests/unit -t .

test-integration: ## Testes de integracao
	$(PYTHON) -m unittest discover -s tests/integration -t .

test-functional: ## Testes funcionais
	$(PYTHON) -m unittest discover -s tests/functional -t .

test-architecture: ## Testes de arquitetura
	$(PYTHON) -m unittest discover -s tests/architecture -t .

test-all: ## Bateria completa no PYTHON
	$(PYTHON) -m unittest discover -s tests -t .

# Portões de qualidade em sequência, sem alterar arquivos (rode make format antes, se quiser formatar)
check-all: lint type-check ## Portoes de qualidade: lint e type-check

# ------------------------------------------------------------------------------
# Alvos de operacao, diagnostico, SQL, testes e homologacao (2026-10-30): cada script de automacao do
# repositorio tem o seu alvo. Fora de proposito: o init_db no modo real (nunca em banco em uso; so o --dry-run
# aqui), os launchers do servidor (sss-web, sss-scheduler, sss-stop, sss-keepalive, sss-update), que o
# sss-ctl.sh e o cron chamam, e as ferramentas do manual de UI Freeze de 18/10 (historico).
# ------------------------------------------------------------------------------

help: ## Lista os alvos com a descricao
	@grep -hE '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | sort | awk -F '\t' '{printf "  %-20s %s\n", $$1, $$2}'

dev-start: ## Sobe o web do DEV desta maquina (bin/start_local.sh; PORT=<porta>, padrao 8000)
	bin/start_local.sh $(PORT)

dev-stop: ## Para o web do DEV desta maquina (bin/stop_local.sh)
	bin/stop_local.sh

ctl: ## Opera esta raiz pelo bin/sss-ctl.sh: CMD=status (padrao), stop, start, restart, "cron show|install|remove"
	bin/sss-ctl.sh $(CMD)

check-env: ## Pre-requisitos do processo NAME (scripts/check_env.py)
	$(PYTHON) scripts/check_env.py --name $(NAME)

health: ## Saude do SSS pela conta do processo NAME (scripts/health.py; saida Nagios)
	$(PYTHON) scripts/health.py --name $(NAME)

probe-driver: ## Sonda o driver Oracle com o config de NAME (scripts/probe_driver.py; a senha vem pelo stdin)
	$(PYTHON) scripts/probe_driver.py --config instance/$(NAME)/config.ini

sql: ## Gera em docs/sql o 01/02/99 de OWNER e PREFIX (scripts/generate_sql.py)
	$(PYTHON) scripts/generate_sql.py --owner $(OWNER) --prefix $(PREFIX) --out-dir docs/sql

sql-all: ## Regera em docs/sql os scripts de todos os SQL_PREFIXES (os versionados)
	@for p in $(SQL_PREFIXES); do $(PYTHON) scripts/generate_sql.py --owner $(OWNER) --prefix $$p --out-dir docs/sql >/dev/null || exit 1; echo "docs/sql: $$p"; done

init-db-dry: ## Imprime o DDL do processo NAME sem conectar (scripts/init_db.py --dry-run)
	$(PYTHON) scripts/init_db.py --name $(NAME) --dry-run

test-matrix: ## Bateria completa em cada Python de PYTHONS (3.6.0, 3.6.15 e 3.13.2)
	@rc=0; for py in $(PYTHONS); do out=$$($$py -W ignore -m unittest discover -s tests -t . 2>&1) || rc=1; echo "== $$py: $$(printf '%s\n' "$$out" | grep -E '^(Ran|OK|FAILED)' | tr '\n' ' ')"; done; exit $$rc

test-oracle: ## Bateria com o Oracle real (SSS_TEST_ORACLE=1); recusa com o DEV desta raiz no ar (R-23)
	@if bin/sss-ctl.sh status 2>/dev/null | grep -q 'no ar'; then echo "Erro: pare o DEV antes (make ctl CMD=stop): a bateria Oracle disputa o banco com ele (R-23)." >&2; exit 2; fi
	SSS_TEST_ORACLE=1 $(PYTHON) -m unittest discover -s tests -t .

homolog-massa: ## Massa da homologacao no input_dir de NAME (gerar_massa.py; LOTE_MB=<MB> troca o lote)
	$(PYTHON) $(HOMOLOG_TOOLS)/gerar_massa.py --config instance/$(NAME)/config.ini $(if $(LOTE_MB),--lote-mb $(LOTE_MB))

homolog: ## Homologacao no navegador (capture_evidence.js; CTS="CT-01 CT-05" para so alguns; variaveis SSS_* do ambiente)
	cd $(HOMOLOG_TOOLS) && node capture_evidence.js $(CTS)

homolog-docx: ## Documento de evidencias da rodada (build_evidence_docx.py; SSS_EVIDENCE_DATE e SSS_EVIDENCE_ROUND)
	cd $(HOMOLOG_TOOLS) && $(PYTHON) build_evidence_docx.py

tunel-3067: ## Tunel ate o web do 3067 pelo bastion: CMD=status (padrao), start ou stop
	dev/others/notas/sss-tunel-3067/sss-tunel-3067.sh $(CMD)
