Ran check sections of DEPLOYMENT-SERVER.md
Ran check package targets in Makefile
Analyzed Makefile:L90-145
Ran check scripts_ambiente/utilitarios
Ran check dev/scripts/utilitarios · Exited with code 2
Ran run test_makefile
Ran inspect previous utilitarios.tar.gz
Ran list .bkp
Analyzed package.py:L1-60
Analyzed DEPLOYMENT-SERVER.md:L570-620
Ran run make package · Exited with code 2
Ran grep utilitarios.tar.gz in docs
Ran check sss_vars.sh · Exited with code 2
Ran find sss_vars.sh
Analyzed sss_vars.sh:L1-41
Analyzed common.ini:L1-6
Analyzed Makefile:L96-146
Analyzed test_makefile.py:L1-60
Edited Makefile
Edited Makefile
Ran run test_makefile
Ran run make package
Ran setup ~/sss_pacote/sss_vars.sh
Analyzed sss_vars.sh:L1-25
Edited sss_vars.sh
Ran check git status
Ran commit and push Makefile
Ran generate official package
Ran list package files
Ran verify SHA256SUMS
Ran read COMMIT file

O pacote oficial foi gerado e validado localmente com sucesso.

Os arquivos estão prontos no diretório:
```bash
/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/.bkp/pacote_20261106_130039/
```

Arquivos contidos no pacote:
1. **`sss-1.0.0-dev.tar.gz`** (aplicação completa, com o commit `ae396c7`)
2. **`utilitarios.tar.gz`** (os 14 scripts utilitários em `scripts_ambiente/`)
3. **`sss_vars.sh`** (parâmetros do servidor `brtlvlty3067sl`, já ajustado com os prefixos `tbsdev_` e `tbsprd_`)
4. **`SHA256SUMS`** (hashes SHA-256 validados)
5. **`COMMIT`** (registro de rastreabilidade do commit)

---

## Roteiro Passo a Passo de Execução

---

### ETAPA 1: Transferir o Pacote para o Servidor 3067

Na sua máquina local (ou através da sua ferramenta de transferência SFTP/SCP):

```bash
# 1.1 Criar a pasta de recepção no servidor 3067 (se ainda não existir)
ssh mastersafgf@brtlvlty3067sl "mkdir -p ~/sss_pacote"

# 1.2 Transferir todos os arquivos da pasta gerada para o servidor
cd /portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/.bkp/pacote_20261106_130039
scp * mastersafgf@brtlvlty3067sl:~/sss_pacote/
```

---

### ETAPA 2: Conferência no Servidor 3067

Conecte-se ao servidor `brtlvlty3067sl`:
```bash
ssh mastersafgf@brtlvlty3067sl
cd ~/sss_pacote

# 2.1 Conferir a integridade dos arquivos transferidos (esperado: OK para todos)
sha256sum -c SHA256SUMS

# 2.2 Carregar as variáveis e funções auxiliares do servidor
chmod 0600 sss_vars.sh
. ./sss_vars.sh
```

---

### ETAPA 3: Escolha do Cenário no Servidor

Escolha o cenário aplicável:
- **Cenário A (Atualização):** Se as raízes `/portaloptrib/TESHUVA/SSS/DEV` e `/portaloptrib/TESHUVA/SSS/PROD` já existem no 3067 e você deseja apenas atualizar a aplicação e recriar o banco com os novos prefixos (`tbsdev_` e `tbsprd_`).
- **Cenário B (Instalação Nova / Do Zero):** Se você vai criar uma instalação limpa no servidor.

---

### CENÁRIO A: Atualização e Carga dos Novos Prefixos

#### A.1 Atualizar o Ambiente DEV

```bash
# 1. Ir para a raiz do DEV e parar os processos atuais
. ~/sss_pacote/sss_vars.sh; sss_tipo DEV && cd "$R"
bin/sss-ctl.sh stop

# 2. Atualizar o código do DEV
bin/sss-update.sh ~/sss_pacote/sss-*.tar.gz
sha256sum -c --quiet SHA256SUMS && echo "DEV: codigo OK"

# 3. Atualizar a pasta scripts_ambiente (se necessário)
mkdir -p scripts_ambiente
tar -xzf ~/sss_pacote/utilitarios.tar.gz -C scripts_ambiente --strip-components=1 2>/dev/null || tar -xzf ~/sss_pacote/utilitarios.tar.gz
chmod 0755 scripts_ambiente scripts_ambiente/utilitarios scripts_ambiente/utilitarios/* 2>/dev/null

# 4. Criar as tabelas do DEV no banco (prefixo tbsdev_)
sqlplus -L "$SSS_DB_USER@$DSN" @$R/docs/sql/01_deploy_sss_openrisow_tbsdev.sql

# 5. Validar o banco do DEV
sqlplus -L "$SSS_DB_USER@$DSN" @$R/docs/sql/99_validate_deploy_openrisow_tbsdev.sql

# 6. Iniciar o DEV
bin/sss-ctl.sh start
bin/sss-ctl.sh status
```

#### A.2 Atualizar o Ambiente PROD

```bash
# 1. Ir para a raiz do PROD e parar os processos atuais
. ~/sss_pacote/sss_vars.sh; sss_tipo PROD && cd "$R"
bin/sss-ctl.sh stop

# 2. Atualizar o código do PROD
bin/sss-update.sh ~/sss_pacote/sss-*.tar.gz
sha256sum -c --quiet SHA256SUMS && echo "PROD: codigo OK"

# 3. Atualizar a pasta scripts_ambiente
mkdir -p scripts_ambiente
tar -xzf ~/sss_pacote/utilitarios.tar.gz -C scripts_ambiente --strip-components=1 2>/dev/null || tar -xzf ~/sss_pacote/utilitarios.tar.gz
chmod 0755 scripts_ambiente scripts_ambiente/utilitarios scripts_ambiente/utilitarios/* 2>/dev/null

# 4. Criar as tabelas do PROD no banco (prefixo tbsprd_)
sqlplus -L "$SSS_DB_USER@$DSN" @$R/docs/sql/01_deploy_sss_openrisow_tbsprd.sql

# 5. Validar o banco do PROD
sqlplus -L "$SSS_DB_USER@$DSN" @$R/docs/sql/99_validate_deploy_openrisow_tbsprd.sql

# 6. Iniciar o PROD (se for deixar rodando)
bin/sss-ctl.sh start
bin/sss-ctl.sh status
```

---

### CENÁRIO B: Instalação do Zero (Fresh Install)

Se as pastas ainda não existem ou deseja refazer a partir do zero:

#### B.1 Preparar as Pastas de Raiz

```bash
. ~/sss_pacote/sss_vars.sh

# Criar a estrutura base
mkdir -p "$SSS_BASE/DEV" "$SSS_BASE/PROD"
```

#### B.2 Extrair o Código em Cada Ambiente

```bash
# --- No DEV ---
sss_tipo DEV
mkdir -p "$R" && tar -xzf ~/sss_pacote/sss-*.tar.gz -C "$R" --strip-components=1
cd "$R"
sha256sum -c --quiet SHA256SUMS && echo "DEV extraido com sucesso"

# --- No PROD ---
sss_tipo PROD
mkdir -p "$R" && tar -xzf ~/sss_pacote/sss-*.tar.gz -C "$R" --strip-components=1
cd "$R"
sha256sum -c --quiet SHA256SUMS && echo "PROD extraido com sucesso"
```

#### B.3 Configuração (`instance/common.ini` e `instance/secrets.cfg`)

Execute para cada ambiente (`sss_tipo DEV` e depois `sss_tipo PROD`):

```bash
# 1. Criar o common.ini do servidor (com o DSN do 3067, sem table_prefix pois é fixo)
cat > "$R/instance/common.ini" <<EOF
[oracle]
user = $SSS_DB_USER
dsn = $DSN
owner = $SSS_OWNER
driver_mode = $SSS_DRIVER_MODE
EOF

# 2. Criar a configuração dos processos a partir dos exemplos
cp -rn "$R/instance/exemplos/"* "$R/instance/"

# 3. Ajustar portas do web no config.ini do web0001
# No DEV (porta 18000):
# allowed_origins = http://127.0.0.1:18000
# No PROD (porta 18001):
# allowed_origins = http://127.0.0.1:18001

# 4. Criar o instance/secrets.cfg com as credenciais reais
# (permissão 0600 obrigatória)
cat > "$R/instance/secrets.cfg" <<EOF
[oracle]
password = <SENHA_DO_BANCO_OPENRISOW>

[web]
cookie_key = <CHAVE_HEX_64_CHARS_DO_COOKIE>

[environment:GFPREPROD]
user = openrisow
password = <SENHA_GFPREPROD>

[environment:CLONE2]
user = openrisow
password = <SENHA_CLONE2>

[environment:CLONE1]
user = openrisow
password = <SENHA_CLONE1>

[environment:CLONE6]
user = openrisow
password = <SENHA_CLONE6>

[environment:CLONE7]
user = openrisow
password = <SENHA_CLONE7>
EOF
chmod 0600 "$R/instance/secrets.cfg"
```

#### B.4 Extrair os Scripts em `scripts_ambiente/`

Em cada raiz (`$R`):
```bash
mkdir -p "$R/scripts_ambiente"
tar -xzf ~/sss_pacote/utilitarios.tar.gz -C "$R/scripts_ambiente" --strip-components=1 2>/dev/null || tar -xzf ~/sss_pacote/utilitarios.tar.gz -C "$R"
find "$R/scripts_ambiente" -type f -exec chmod 0444 {} +
find "$R/scripts_ambiente" -type d -exec chmod 0555 {} +
```

#### B.5 Criar o Esquema e Validar no Oracle

```bash
# No DEV:
. ~/sss_pacote/sss_vars.sh; sss_tipo DEV && cd "$R"
sqlplus -L "$SSS_DB_USER@$DSN" @docs/sql/01_deploy_sss_openrisow_tbsdev.sql
sqlplus -L "$SSS_DB_USER@$DSN" @docs/sql/99_validate_deploy_openrisow_tbsdev.sql

# No PROD:
. ~/sss_pacote/sss_vars.sh; sss_tipo PROD && cd "$R"
sqlplus -L "$SSS_DB_USER@$DSN" @docs/sql/01_deploy_sss_openrisow_tbsprd.sql
sqlplus -L "$SSS_DB_USER@$DSN" @docs/sql/99_validate_deploy_openrisow_tbsprd.sql
```

#### B.6 Subida e Ativação no `crontab`

```bash
# Subir o DEV
. ~/sss_pacote/sss_vars.sh; sss_tipo DEV && cd "$R"
bin/sss-ctl.sh start
bin/sss-ctl.sh status
bin/sss-ctl.sh cron install

# Subir o PROD
. ~/sss_pacote/sss_vars.sh; sss_tipo PROD && cd "$R"
bin/sss-ctl.sh start
bin/sss-ctl.sh status
bin/sss-ctl.sh cron install
```

---

### ETAPA 4: Validação Final e Acesso

1. **Checagem de Saúde nos Processos:**
   ```bash
   # No DEV:
   . ~/sss_pacote/sss_vars.sh; sss_tipo DEV && cd "$R"
   $PYTHON scripts/health.py --name agente0001
   # Esperado: SSS OK - 0 problemas | healthy_agents=5

   # No PROD:
   . ~/sss_pacote/sss_vars.sh; sss_tipo PROD && cd "$R"
   $PYTHON scripts/health.py --name agente0001
   # Esperado: SSS OK - 0 problemas | healthy_agents=5
   ```

2. **Acesso Web (via túnel SSH do seu terminal local):**
   ```bash
   # Na sua máquina local, abrir túneis para as portas:
   ssh -L 18000:127.0.0.1:18000 -L 18001:127.0.0.1:18001 mastersafgf@brtlvlty3067sl
   ```
   - **DEV:** `http://127.0.0.1:18000/script_scheduling_service` (faixa amarela "AMBIENTE DEV")
   - **PROD:** `http://127.0.0.1:18001/script_scheduling_service` (sem faixa)
   - **Usuários iniciais do seed:**
     - `admin` (perfil `ADMINISTRADOR`)
     - `op.prod` (perfil `OPERADOR`)
     - `consulta` (perfil `CONSULTA`)
     - Senha inicial: `Sss@Homolog2026!`