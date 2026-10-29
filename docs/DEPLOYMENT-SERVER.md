# SSS — Roteiro de implantação por servidor (modelo)

Roteiro passo a passo, auditável, para instalar o Script Scheduling Service num servidor Linux, em uma ou mais instalações independentes (por exemplo, **DEV** e **PROD**), cada uma com 1 web e N agentes (um por ambiente). Serve para qualquer servidor: tudo o que muda de um servidor para outro fica num único arquivo de valores, o `sss_vars.sh` (passo 0), e os comandos dos passos leem esse arquivo. O guia geral é o `docs/DEPLOYMENT.md`.

* Cada passo diz o que conferir antes de seguir. Se uma conferência falhar, **pare** e resolva antes do passo seguinte.
* **Senhas:** nenhuma senha aparece neste documento nem no `sss_vars.sh`. As senhas de banco vão do cofre direto para o `secrets.cfg` no servidor (passo 8.2), nunca por e-mail, chat ou arquivo intermediário.
* **Exemplo preenchido:** o Apêndice A traz os valores, os achados e as decisões do servidor `brtlvlty3067sl` (29/10/2026).

---

## 0. Valores da implantação (`sss_vars.sh`)

Na máquina de origem, crie o arquivo e preencha cada `<...>` (o Apêndice A tem um exemplo completo). A parte de baixo (Python e cliente Oracle) é preenchida depois da pré-checagem no servidor (passo 3).

```bash
mkdir -m 0700 -p ~/sss_pacote && cat > ~/sss_pacote/sss_vars.sh <<'EOF'
# Valores de uma implantação do SSS (DEPLOYMENT-SERVER). SEM SENHAS. Carregue com: . ~/sss_pacote/sss_vars.sh
SSS_SERVIDOR='<hostname>'                       # o que o comando `hostname` mostra no servidor
SSS_CONTA='<conta do SO>'                       # a conta que roda o SSS (sem root)
SSS_BASE='<pasta base>'                         # as raízes ficam em $SSS_BASE/<TIPO>/script_scheduling_service
SSS_TIPOS="DEV PROD"                          # as instalações deste servidor (nomes de pasta: DEV, PROD)
SSS_DB_USER='<conta Oracle>'                    # conta única, dona do esquema (DEPLOYMENT §4.0)
SSS_OWNER='<owner>'                             # owner do esquema (em geral, a própria conta)
SSS_DSN_DEV='<DSN do DEV>'                    # ex.: (DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=h)(PORT=1521))(CONNECT_DATA=(SID=s)))
SSS_DSN_PROD='<DSN do PROD>'
SSS_PREFIXO_DEV='<prefixo>_'                    # até 8 caracteres: ^[a-z][a-z0-9_]{0,7}$, novo no owner
SSS_PREFIXO_PROD='<prefixo>_'
SSS_OUTROS_PREFIXOS="<prefixos de outras instalações no mesmo owner>"   # ex.: "tbsss_ ssdev_"; nunca tocados
SSS_PORTA_DEV='<porta>'                         # o web atende em 127.0.0.1:<porta>
SSS_PORTA_PROD='<porta>'
SSS_WEB=web0001
SSS_AGENTES='<nome:AMBIENTE ...>'            # ex.: "agente0001:GFPREPROD agente0002:CLONE2"; um ambiente por agente, do seed
SSS_MAX_PARALLEL=4
SSS_TZ=America/Sao_Paulo
# --- preenchidos depois do passo 3 (pré-checagem no servidor) ---
PYTHON='<interpretador escolhido no passo 3.2>'
ORACLE_HOME='<ORACLE_HOME do cliente, ou vazio>'
SSS_IC_DIR='<pasta do libclntsh, vazio se estiver no ldconfig>'
SSS_DRIVER_MODE=auto                          # auto | thick | cx_oracle | thin (DEPLOYMENT §6)
SSS_LOCALE='<locale UTF-8 do passo 3.1, vazio para C.UTF-8>'

# --- derivados: não altere abaixo desta linha ---
SSS_NOMES_AGENTES=$(for a in $SSS_AGENTES; do printf '%s ' "${a%%:*}"; done)
SSS_AMBIENTES=$(for a in $SSS_AGENTES; do echo "${a#*:}"; done | sort -u | tr '\n' ' ')
SSS_AGENTE_HEALTH=${SSS_NOMES_AGENTES%% *}
[ -n "$SSS_LOCALE" ] || unset SSS_LOCALE
export PYTHON SSS_TZ ORACLE_HOME SSS_IC_DIR SSS_LOCALE
if [ -n "$SSS_IC_DIR" ]; then
  case ":${LD_LIBRARY_PATH:-}:" in *":$SSS_IC_DIR:"*) ;; *) export LD_LIBRARY_PATH="$SSS_IC_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}";; esac
fi
# sss_tipo DEV|PROD: acerta T, R (raiz), PREFIX, P (prefixo sem _), PORT e DSN do tipo.
sss_tipo() {
  case " $SSS_TIPOS " in *" $1 "*) ;; *) echo "tipo invalido: $1 (use: $SSS_TIPOS)"; return 1;; esac
  T=$1; R=$SSS_BASE/$T/script_scheduling_service
  eval "PREFIX=\$SSS_PREFIXO_$T; PORT=\$SSS_PORTA_$T; DSN=\$SSS_DSN_$T"
  P=${PREFIX%_}; export T R PREFIX P PORT DSN
  echo "tipo=$T raiz=$R prefixo=$PREFIX porta=$PORT"
}
EOF
chmod 0600 ~/sss_pacote/sss_vars.sh && vi ~/sss_pacote/sss_vars.sh
```

Conferência (em toda sessão nova, na origem e no servidor, comece por carregar o arquivo):

```bash
. ~/sss_pacote/sss_vars.sh
grep -nE "^[A-Z_]+=['\"]?<" ~/sss_pacote/sss_vars.sh || echo "tudo preenchido"   # o que ainda falta (antes do passo 3, só a parte de baixo)
echo "agentes: $SSS_NOMES_AGENTES | ambientes: $SSS_AMBIENTES | health: $SSS_AGENTE_HEALTH"
for t in $SSS_TIPOS; do sss_tipo $t; done
```

* **As instalações não se misturam:** cada raiz tem as suas pastas (`var/`, `instance/`) e cada prefixo tem as suas tabelas. Os mesmos nomes de processo em raízes diferentes não conflitam: o keepalive e o `sss-stop.sh` trabalham só na raiz de onde são chamados.
* **Prefixos novos:** use prefixos que ainda não existem no owner. Os de `SSS_OUTROS_PREFIXOS` (outras instalações no mesmo owner) **nunca** são tocados por este roteiro: o passo 4.1 confere que os scripts gerados não os citam, e o passo 9 confere que o prefixo novo está vazio.

---

## 1. Antes de começar

* Janela combinada e acesso ao cofre com: a senha da conta `$SSS_DB_USER` e as contas (usuário e senha) dos bancos de cada ambiente de `SSS_AMBIENTES`.
* Na máquina de origem: a pasta da aplicação de referência. O pacote sai dos arquivos dela como estão, sem git, sem config e sem senha locais. Também: Python 3.6 ou superior, `make`, `rsync` e `tar`.
* Abra um registro da execução (passo 17) e anote cada conferência com o resultado.

---

## 2. Acesso ao servidor

Os passos 3 e 6 a 16 rodam numa sessão de terminal no servidor, com a conta `$SSS_CONTA`, aberta pelo meio habitual da equipe (bastion, VPN). O `sss_vars.sh` chega ao servidor no passo 5. Até lá, use os valores do arquivo da origem:

```bash
hostname; whoami                              # esperado: os valores de SSS_SERVIDOR e SSS_CONTA
```

---

## 3. Pré-checagem no servidor (só leitura)

Nada é criado nem alterado neste passo. Os resultados preenchem a parte de baixo do `sss_vars.sh` (na origem; ele é levado no passo 5).

### 3.1 Conta, sistema, disco e locale

```bash
BASE=<SSS_BASE do sss_vars.sh>
id; uname -a; ldd --version | head -1
df -h "$(dirname "$BASE")"                    # espaço para as raízes, os logs e as saídas (DEPLOYMENT §4.3)
ls -ld "$BASE" "$(dirname "$BASE")"           # a base existe e é da conta, ou a pasta de cima é gravável por ela
ls -la "$BASE" 2>/dev/null                    # as pastas DEV/, PROD/ não podem existir com conteúdo
ls /proc/self/cwd >/dev/null && echo "proc OK" # o keepalive usa /proc
locale -a 2>/dev/null | grep -i -E '^(c|en_US|pt_BR)\.utf-?8$'
```

* `SSS_LOCALE`: vazio se aparecer `C.utf8` (o padrão dos launchers é `C.UTF-8`); senão, `en_US.utf8` ou `pt_BR.utf8`. O SSS exige codificação UTF-8.

### 3.2 Python

O SSS precisa de Python 3.6.0 ou superior. O launcher só aceita interpretador chamado `python3` ou `python3.X`.

```bash
for p in python3 python3.6 python3.8 python3.9 python3.11 python3.12; do
  command -v "$p" >/dev/null 2>&1 && echo "$p -> $("$p" -c 'import sys; print(sys.version.split()[0], sys.executable)')"
done
ls -d /usr/bin/python3* /usr/local/bin/python3* /opt/*/bin/python3* 2>/dev/null
```

Escolha um (ele vira o `PYTHON` do `sss_vars.sh`) e confira:

```bash
PYTHON=<caminho escolhido>
"$PYTHON" -c "import sys; assert sys.version_info >= (3, 6, 0); import zlib, hmac, secrets, json, configparser, zipfile; print('stdlib OK')"
"$PYTHON" -c "import _hashlib" 2>/dev/null && echo "_hashlib OK" || echo "SEM _hashlib (PBKDF2 em Python puro)"
"$PYTHON" -c "import hashlib, time; t=time.time(); hashlib.pbkdf2_hmac('sha256', b'a', b'b', 200000); print('PBKDF2 200000: %.1f s' % (time.time()-t))"
```

* `stdlib OK` é obrigatório. Sem ele, **pare**: o Python não serve.
* PBKDF2 acima de 3 s: cada login demora isso. Registre e prefira outro Python, se houver.

### 3.3 Driver e cliente Oracle

```bash
"$PYTHON" -c "import oracledb; print('oracledb', oracledb.__version__)" 2>&1 | tail -1
"$PYTHON" -c "import cx_Oracle; print('cx_Oracle', cx_Oracle.version)" 2>&1 | tail -1
"$PYTHON" -c "import ssl" 2>/dev/null && echo "ssl OK (modo thin possivel)" || echo "SEM ssl: so thick ou cx_oracle"
ldconfig -p 2>/dev/null | grep -c libclntsh; echo "ORACLE_HOME=$ORACLE_HOME"
ls "$ORACLE_HOME"/lib/libclntsh.so* /opt/oracle/instantclient*/libclntsh.so* /usr/lib/oracle/*/client64/lib/libclntsh.so* 2>/dev/null
LIB=<pasta do libclntsh encontrada acima>
LD_LIBRARY_PATH="$LIB" "$PYTHON" -c "import cx_Oracle; print('cx_Oracle cliente', cx_Oracle.clientversion())" 2>&1 | tail -1
LD_LIBRARY_PATH="$LIB" "$PYTHON" -c "import oracledb; oracledb.init_oracle_client(lib_dir='$LIB'); print('oracledb thick cliente', oracledb.clientversion())" 2>&1 | tail -1
command -v sqlplus && sqlplus -V
```

* Precisa de um driver que carregue o cliente (ou do `oracledb` com `ssl`, no modo Thin). Sem nenhum, **pare**: o driver é instalado pela infraestrutura (DEPLOYMENT §2, sem `pip install` no servidor).
* `SSS_IC_DIR` = a pasta do `libclntsh` quando ele não está no `ldconfig` (a contagem acima deu 0); `ORACLE_HOME` = o do cliente completo, se for o caso. O `SSS_DRIVER_MODE = auto` (padrão) acha sozinho o driver que funciona.
* Sem `sqlplus`, o banco é criado pelo `init_db.py` (passo 9, alternativa).

### 3.4 Banco, portas e instalação anterior

```bash
DSN=<SSS_DSN_DEV ou SSS_DSN_PROD>
H=$(echo "$DSN" | sed -n 's/.*HOST=\([^)]*\).*/\1/p'); PT=$(echo "$DSN" | sed -n 's/.*PORT=\([^)]*\).*/\1/p')
timeout 5 bash -c "echo > /dev/tcp/$H/$PT" && echo "banco $H:$PT alcancavel" || echo "banco $H:$PT INALCANCAVEL"
(ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null) | grep -E ':(<porta DEV>|<porta PROD>)\b' || echo "portas livres"
for pid in $(ps -eo pid,args | grep -E '[r]un_web|[r]un_scheduler|[w]eb2py' | awk '{print $1}'); do
  echo "$pid $(readlink /proc/$pid/cwd) :: $(tr '\0' ' ' < /proc/$pid/cmdline)"
done
crontab -l 2>/dev/null | grep -n -i sss || echo "crontab sem SSS"
```

* Repita a primeira linha com o DSN de cada tipo. Banco inalcançável: **pare** e peça a liberação da rota.
* Porta ocupada ou SSS antigo no ar: o passo 6 trata disso antes de subir qualquer coisa.

Preencha agora, **na origem**, a parte de baixo do `sss_vars.sh` (`PYTHON`, `ORACLE_HOME`, `SSS_IC_DIR`, `SSS_DRIVER_MODE`, `SSS_LOCALE`).

---

## 4. Scripts SQL e pacote na máquina de origem

### 4.1 Geração dos scripts SQL

Os scripts saem do registro de identificadores do código, com o owner e o prefixo de cada instalação (DEPLOYMENT §5.2). O owner e o prefixo vêm da linha de comando: não é preciso config, banco nem senha, e o comando não conecta. Com a conta única, dona do esquema, nenhum GRANT é gerado: o fim do `01` diz "conta nao informada; nenhum GRANT gerado".

```bash
. ~/sss_pacote/sss_vars.sh
ORIGEM=<pasta da aplicação de referência>     # ex.: /portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service
cd "$ORIGEM"
for t in $SSS_TIPOS; do sss_tipo $t >/dev/null
  python3 scripts/generate_sql.py --owner "$SSS_OWNER" --prefix "$PREFIX" --out-dir docs/sql
done
OUTROS=$(echo $SSS_OUTROS_PREFIXOS | tr ' ' '|'); O=$(echo "$SSS_OWNER" | tr A-Z a-z)
for t in $SSS_TIPOS; do sss_tipo $t >/dev/null
  echo "== $P"
  grep -c "WHENEVER SQLERROR EXIT FAILURE ROLLBACK" docs/sql/01_deploy_sss_${O}_$P.sql                  # esperado: 1
  grep -E -i "${OUTROS:-^$}" docs/sql/01_deploy_sss_${O}_$P.sql | grep -vc "COMMENT ON COLUMN"           # esperado: 0
  grep -E -ic "${OUTROS:-^$}" docs/sql/02_rollback_sss_${O}_$P.sql                                      # esperado: 0
  grep -oE "[a-z_0-9]*${P}_[a-z_0-9]*" docs/sql/01_deploy_sss_${O}_$P.sql | awk '{ if (length($0) > m) m = length($0) } END { print "maior identificador:", m }'   # até 30
  grep -ic "GRANT .* TO PUBLIC" docs/sql/01_deploy_sss_${O}_$P.sql                                      # esperado: 0
  sha256sum docs/sql/*_${O}_$P.sql                                                                       # registre no passo 17
done
```

* O `tbsss_` aparece no `01` de qualquer prefixo só nos `COMMENT ON COLUMN` das FKs (texto fixo do dicionário, sem efeito): por isso o filtro da segunda conferência.
* O DBA pode revisar o `01` antes da janela. No servidor, o mesmo comando, rodado na `<RAIZ>` com `--out-dir /tmp/sql_conferencia`, gera arquivos idênticos aos do pacote (mesmo `sha256`).

### 4.2 Pacote

```bash
cd "$ORIGEM"
make package-local                            # grava .bkp/pacote_local_<data>/sss-<versao>.tar.gz, SHA256SUMS e ORIGEM
PKG=$(ls -d .bkp/pacote_local_* | tail -1); ls -l "$PKG"; cat "$PKG/ORIGEM"
(cd "$PKG" && sha256sum -c SHA256SUMS)        # esperado: sss-<versao>.tar.gz: OK
tar -tzf "$PKG"/sss-*.tar.gz | grep -E '__pycache__|secrets\.cfg$|common\.ini$|config\.ini$' || echo "sem cache e sem segredos"
for t in $SSS_TIPOS; do sss_tipo $t >/dev/null; tar -tzf "$PKG"/sss-*.tar.gz | grep -c "_$P\.sql$"; done   # esperado: 3 por tipo
tar -czf "$PKG/utilitarios.tar.gz" --exclude=__pycache__ --exclude='*.pyc' dev/scripts/utilitarios
tar -tzf "$PKG/utilitarios.tar.gz" | grep -c '\.\(py\|sh\)$'           # esperado: 14
cp ~/sss_pacote/sss_vars.sh "$PKG/"
(cd "$PKG" && sha256sum utilitarios.tar.gz sss_vars.sh >> SHA256SUMS && sha256sum -c SHA256SUMS)
```

* O `make package-local` copia só o que vai para o servidor (`bin`, `docs`, `instance/exemplos`, `scripts`, `src`, `AGENTS.md`, `README.md`), sem caches e sem `docs/homologation`, e passa a cópia pelo `tools/package.py`. Esse script só usa a biblioteca padrão e recusa o pacote com `__pycache__`, `*.pyc`, `secrets.cfg` real, senha fora do `CHANGE_ME` dos modelos, código de DEV, testes ou link simbólico. Os `instance/<nome>/` da origem (com senhas reais) nunca entram.
* O `ORIGEM` registra a pasta e a hora do pacote. Se a pasta tiver um `.git`, ele também cita o commit de base, só como informação: a referência são os arquivos.
* Os scripts de exemplo do seed (`utilitarios/*`) ficam em `dev/scripts/`, que o pacote não leva: por isso o tar separado.

---

## 5. Transferência dos arquivos para o servidor

**É necessário levar ao servidor os cinco arquivos da pasta `$PKG` do passo 4.2:**

| Arquivo | Conteúdo |
|---|---|
| `sss-<versao>.tar.gz` | A aplicação, com os scripts SQL dos prefixos em `docs/sql/` |
| `utilitarios.tar.gz` | Os 14 scripts de exemplo do seed (passo 10) |
| `sss_vars.sh` | Os valores desta implantação (sem senhas) |
| `SHA256SUMS` | As impressões digitais dos três arquivos acima |
| `ORIGEM` | A pasta e a hora em que o pacote foi gerado |

O destino é `~/sss_pacote` da conta `$SSS_CONTA` no servidor. A transferência é feita pela equipe, pelo meio habitual. Os arquivos não têm senha, mas não os deixe em pasta compartilhada de um servidor intermediário. No servidor, antes e depois:

```bash
mkdir -m 0700 -p ~/sss_pacote                                 # antes da transferência
cd ~/sss_pacote && ls -l && sha256sum -c SHA256SUMS && cat ORIGEM   # depois
chmod 0600 sss_vars.sh && . ~/sss_pacote/sss_vars.sh && for t in $SSS_TIPOS; do sss_tipo $t; done
[ "$(hostname)" = "$SSS_SERVIDOR" ] && [ "$(whoami)" = "$SSS_CONTA" ] && echo "servidor e conta conferem"
```

Esperado: `OK` nos três arquivos, o mesmo `ORIGEM` do passo 4.2 e `servidor e conta conferem`. Um `FAILED` é arquivo corrompido ou trocado no caminho: transfira de novo. Apague a cópia intermediária, se ela ficou em outro servidor.

**Daqui em diante, toda sessão no servidor começa com `. ~/sss_pacote/sss_vars.sh`.**

---

## 6. Instalação anterior do SSS no servidor

Se o passo 3.4 mostrou processos do SSS (`web2py.py`, `run_web.py`, `run_scheduler.py`) de outra pasta, decida antes (registre a decisão no passo 17): parar e manter os arquivos (recomendado), ou deixar no ar quando não houver conflito de porta nem de pasta. Para parar, **sem apagar nada**:

```bash
crontab -l > ~/sss_pacote/crontab_antes_$(date +%Y%m%d_%H%M%S).txt 2>/dev/null; crontab -l 2>/dev/null | grep -n -i -E 'sss|web2py'
for pid in $(ps -eo pid,args | grep -E '[r]un_web|[r]un_scheduler|[w]eb2py' | awk '{print $1}'); do
  echo "$pid $(readlink /proc/$pid/cwd) :: $(tr '\0' ' ' < /proc/$pid/cmdline)"
done
kill -TERM <PID da instalação antiga>         # um por um, depois de conferir a pasta (cwd) acima
sleep 5; ps -eo pid,args | grep -E '[r]un_web|[r]un_scheduler|[w]eb2py'   # esperado: nada da instalação antiga
```

Se o `crontab` tiver linhas da instalação antiga, comente-as (`crontab -e`, `#` no início). Os arquivos antigos ficam onde estão.

---

## 7. Extração nas raízes

```bash
. ~/sss_pacote/sss_vars.sh
umask 027                                     # o tar segue o umask; uma conta com 002 deixaria o código gravável pelo grupo
for t in $SSS_TIPOS; do sss_tipo $t
  [ -e "$R" ] && { echo "JA EXISTE: $R (pare e confira)"; break; }
  mkdir -p "$(dirname "$R")" && cd "$(dirname "$R")"
  tar -xzf ~/sss_pacote/sss-*.tar.gz && mv sss-*/ script_scheduling_service && chmod 0750 script_scheduling_service
  (cd "$R" && sha256sum -c --quiet SHA256SUMS && echo "$T: conteudo confere" && ls)
done
```

Esperado em cada tipo: `conteudo confere` e `AGENTS.md README.md SHA256SUMS bin docs instance scripts src`.

---

## 8. Configuração (em cada raiz)

Rode os blocos 8.1 a 8.4 uma vez para cada tipo, na mesma sessão, começando por:

```bash
. ~/sss_pacote/sss_vars.sh; sss_tipo DEV && cd "$R"            # depois, sss_tipo PROD
umask 027
sss_grava() {  # sss_grava <arquivo> <modo>: grava o stdin; se o arquivo já existe e muda, guarda o anterior
  local f=$1 m=$2 tmp; tmp=$(mktemp "$f.XXXXXX") || return 1
  cat > "$tmp"; chmod "$m" "$tmp"
  if [ ! -e "$f" ]; then mv "$tmp" "$f"; echo "criado: $f"
  elif cmp -s "$tmp" "$f"; then rm -f "$tmp"; echo "sem mudanca: $f"
  else cp -p "$f" "$f.antes_$(date +%Y%m%d_%H%M%S)"; diff "$f" "$tmp"; mv "$tmp" "$f"; echo "atualizado: $f (anterior guardado em $f.antes_*)"; fi
}
```

**Pode rodar de novo:** as pastas são criadas com `mkdir -p`; cada `config.ini` passa pelo `sss_grava` (criado, sem mudança, ou atualizado com a cópia anterior guardada e a diferença na tela); o `secrets.cfg` que já existe nunca é recriado (as senhas digitadas e a `cookie_key` ficam).

### 8.1 `instance/common.ini` (o banco)

```bash
sss_grava instance/common.ini 0640 <<EOF
; common.ini do servidor (CR-032, D18): [oracle] comum ao web e aos agentes. Senha no instance/secrets.cfg.
[oracle]
user = $SSS_DB_USER
dsn = $DSN
owner = $SSS_OWNER
table_prefix = $PREFIX
driver_mode = $SSS_DRIVER_MODE
EOF
cat instance/common.ini
```

Com `auto`, cada processo testa Thin → Thick → cx_Oracle na subida e fica com o primeiro que conectar (DEPLOYMENT §6). Um driver não instalado falha na hora e deixa no log uma linha `WARNING ... Sondagem do candidato Oracle '<candidato>' falhou: codigo=IMPORT_ERROR categoria=LIBRARY`, esperada. Só um erro de senha interrompe a cadeia.

### 8.2 `instance/secrets.cfg` (senhas e chave da sessão)

O arquivo fica na raiz de cada tipo, com modo `0600` e dono `$SSS_CONTA`. É o único lugar com senhas. O bloco abaixo o cria, **só se ele ainda não existir**, com uma `cookie_key` nova (própria de cada tipo, sem aparecer na tela), um bloco por ambiente de `SSS_AMBIENTES` e `CHANGE_ME` no lugar das senhas:

```bash
if [ -e instance/secrets.cfg ]; then
  echo "ja existe: instance/secrets.cfg (mantido; para um ambiente novo, acrescente o bloco com o vi)"
  for e in $SSS_AMBIENTES; do grep -q "^\[environment:$e\]" instance/secrets.cfg || echo "  falta o bloco [environment:$e]"; done
else
  ( umask 077
    { printf '[oracle]\npassword = CHANGE_ME\n\n[web]\ncookie_key = %s\n' "$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(48))')"
      for e in $SSS_AMBIENTES; do printf '\n[environment:%s]\nuser = CHANGE_ME\npassword = CHANGE_ME\n' "$e"; done
    } > instance/secrets.cfg ) && echo "criado: instance/secrets.cfg"
fi
vi instance/secrets.cfg                       # troque cada CHANGE_ME pelo valor do cofre
stat -c '%a %U %n' instance/secrets.cfg       # esperado: 600 <SSS_CONTA> instance/secrets.cfg
grep -c CHANGE_ME instance/secrets.cfg        # esperado: 0
grep -c '^\[environment:' instance/secrets.cfg; echo $SSS_AMBIENTES | wc -w   # os dois números iguais
```

### 8.3 Web (`instance/$SSS_WEB/config.ini`)

```bash
mkdir -p -m 0750 instance/$SSS_WEB
sss_grava instance/$SSS_WEB/config.ini 0640 <<EOF
; config.ini do no web (CR-028). Banco no instance/common.ini; segredos no instance/secrets.cfg.
[app]
name = $SSS_WEB

[web]
allowed_origins = http://127.0.0.1:$PORT
EOF
```

`allowed_origins` é a URL que o navegador mostra. Com acesso por túnel ou proxy (passo 13) com outro endereço, use o endereço que o usuário digita.

### 8.4 Os agentes (`instance/<agente>/config.ini`)

```bash
for a in $SSS_AGENTES; do name=${a%%:*}; env=${a#*:}
  mkdir -p -m 0750 instance/$name
  sss_grava instance/$name/config.ini 0640 <<EOF
; config.ini do agente (CR-028): o nome e o agent_id. Banco no instance/common.ini; segredos no instance/secrets.cfg.
[app]
name = $name

[agent]
environments = $env
max_parallel_jobs = $SSS_MAX_PARALLEL
env_passthrough = ORACLE_HOME,TNS_ADMIN,NLS_LANG,LD_LIBRARY_PATH
EOF
done
grep -H "environments" instance/*/config.ini
```

Esperado: cada agente com o seu ambiente, como em `SSS_AGENTES`. Não escreva `agent_id`, `script_base_dir` nem pastas: tudo sai do nome (DEPLOYMENT §7.1).

---

## 9. Banco: um esquema por prefixo

Os esquemas são novos: o `01_deploy` só cria objetos do seu prefixo. **Nunca rode aqui um script de `SSS_OUTROS_PREFIXOS`**: são de outras instalações no mesmo owner, e o `02_rollback` deles apagaria aquelas tabelas.

Os comandos vão num arquivo `.sql`, e o `sqlplus` pede a senha no terminal (`-L`: uma tentativa só). Em cada tipo, primeiro a conferência de que o prefixo está vazio (esperado `0`):

```bash
. ~/sss_pacote/sss_vars.sh; sss_tipo DEV && cd "$R"            # depois, sss_tipo PROD
O=$(echo "$SSS_OWNER" | tr A-Z a-z)
cat > ~/sss_pacote/${P}_00_vazio.sql <<EOF
SELECT COUNT(*) FROM all_tables WHERE owner = UPPER('$SSS_OWNER') AND table_name LIKE UPPER('$P') || '\_%' ESCAPE '\';
EXIT
EOF
sqlplus -L "$SSS_DB_USER@$DSN" @$HOME/sss_pacote/${P}_00_vazio.sql
```

Conferência de que a DDL do pacote é a do código instalado (só leitura, sem senha): os três `sha256` aparecem duas vezes, iguais aos do passo 4.1.

```bash
"$PYTHON" scripts/generate_sql.py --owner "$SSS_OWNER" --prefix "$PREFIX" --out-dir /tmp/sql_conferencia_$$ >/dev/null && sha256sum /tmp/sql_conferencia_$$/*_${P}.sql docs/sql/*_${O}_${P}.sql; rm -rf /tmp/sql_conferencia_$$
```

Depois, a implantação e a validação. A saída vai para um arquivo: o `Enter password:` não aparece na tela, mas o `sqlplus` espera a senha (digite e aperte Enter):

```bash
cat > ~/sss_pacote/${P}_01_99.sql <<EOF
SPOOL $HOME/sss_pacote/${P}_01_deploy.log
@$R/docs/sql/01_deploy_sss_${O}_${P}.sql
SPOOL OFF
SPOOL $HOME/sss_pacote/${P}_99_validate.log
@$R/docs/sql/99_validate_deploy_${O}_${P}.sql
SPOOL OFF
EXIT
EOF
sqlplus -L "$SSS_DB_USER@$DSN" @$HOME/sss_pacote/${P}_01_99.sql > ~/sss_pacote/${P}_sqlplus.out 2>&1; echo "codigo $?"   # esperado: 0
grep -i 'concluida com sucesso' ~/sss_pacote/${P}_01_deploy.log
grep -c -E 'ORA-|SP2-' ~/sss_pacote/${P}_01_deploy.log       # esperado: 0
grep 'OK: nenhuma falha' ~/sss_pacote/${P}_99_validate.log     # esperado: as duas linhas de resumo
```

* O `01` para no primeiro erro (`WHENEVER SQLERROR EXIT FAILURE ROLLBACK`). Se ele parar, guarde o log, rode o `02_rollback_sss_${O}_${P}.sql` (só o do prefixo deste passo) e repita.
* **Sem `sqlplus`:** `"$PYTHON" scripts/init_db.py --name $SSS_AGENTE_HEALTH --real-schema` cria o mesmo esquema e o seed, com a conta e os segredos do agente (passo 11 antes, para conferir o acesso). `--dry-run` imprime o DDL sem conectar.
* O seed cria os usuários `admin`, `op.prod`, `op.hml` e `consulta` com a senha inicial do DEPLOYMENT §5.3. Ela é trocada no passo 13.

---

## 10. Árvore de scripts (`script_base_dir`)

A pasta base é a padrão, `<RAIZ>/scripts_ambiente/`, preservada pela atualização (DEPLOYMENT §9). O agente exige que o arquivo real não tenha escrita para grupo nem para outros (README §8.5). Os modos `0444` (arquivos) e `0555` (pastas) atendem a regra e também impedem que a própria conta altere os scripts sem querer. Em cada tipo:

```bash
. ~/sss_pacote/sss_vars.sh; sss_tipo DEV && cd "$R"            # depois, sss_tipo PROD
if [ -d scripts_ambiente/utilitarios ]; then
  echo "ja existe: scripts_ambiente/utilitarios (mantido; para trocar, veja abaixo)"
else
  mkdir -p scripts_ambiente && tar -xzf ~/sss_pacote/utilitarios.tar.gz -C scripts_ambiente --strip-components=2
fi
ls scripts_ambiente/utilitarios | wc -l                        # esperado: 14
find scripts_ambiente -type f -exec chmod 0444 {} +
find scripts_ambiente -type d -exec chmod 0555 {} +
find scripts_ambiente -perm /022 | wc -l                       # esperado: 0
```

Para trocar um script depois: `chmod u+w` na pasta e no arquivo, troque, e volte para `0444`/`0555`.

---

## 11. Conferências antes de subir

Em cada tipo:

```bash
. ~/sss_pacote/sss_vars.sh; sss_tipo DEV && cd "$R"            # depois, sss_tipo PROD
for n in $SSS_WEB $SSS_NOMES_AGENTES; do echo "== $n"; "$PYTHON" scripts/check_env.py --name $n; echo "codigo $?"; done
for c in thin thick cx_oracle; do echo "== $c"; "$PYTHON" scripts/probe_driver.py $c --config instance/$SSS_AGENTE_HEALTH/config.ini; done
bin/sss-web.sh "$PYTHON" $SSS_WEB --check                     # esperado: CONFIG_OK ambiente=<TIPO>
```

* `check_env`: código 0 em todos (avisos não reprovam). A saída mostra o driver, o modo e as versões. Registre-a. Código 1: falta arquivo ou o banco não conectou (veja a linha `FALHA`). Código 2: Python menor que 3.6.0 ou nome errado.
* `probe_driver`: uma linha por candidato, com `"ok": true` no que funciona neste servidor. Ele deve bater com o escolhido pelo `check_env`.
* O `check_env.py`, o `probe_driver.py` e o `health.py` rodam direto no Python. Com o cliente fora do `ldconfig`, eles usam o `LD_LIBRARY_PATH` que o `sss_vars.sh` monta a partir do `SSS_IC_DIR`. Os launchers (`sss-web.sh`, `sss-scheduler.sh`) o montam sozinhos.

---

## 12. Subida

Em cada tipo:

```bash
. ~/sss_pacote/sss_vars.sh; sss_tipo DEV && cd "$R"            # depois, sss_tipo PROD
bin/sss-keepalive.sh $SSS_WEB:$PORT $SSS_NOMES_AGENTES; echo "codigo $?"
sleep 15
tail -n 3 var/*/logs/keepalive.log
for p in /proc/[0-9]*; do
  [ "$(readlink $p/cwd 2>/dev/null)" = "$(pwd -P)" ] && tr '\0' ' ' < $p/cmdline | grep -E 'run_(web|scheduler)\.py' && echo
done                                           # esperado: 1 run_web.py e um run_scheduler.py por agente, desta raiz
(ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null) | grep ":$PORT\b"   # esperado: 127.0.0.1:<porta> LISTEN
grep -h "pasta criada\|driver=\|agente inicializado\|Subida abortada" var/agente*/logs/internal/app/*/*/*/*/*/sss_scheduler_*.log | tail -n 20
"$PYTHON" scripts/health.py --name $SSS_AGENTE_HEALTH; echo "codigo $?"   # esperado: SSS OK ... healthy_agents=<N>, codigo 0
```

* Keepalive com código 3: algum processo não subiu. Veja `var/<nome>/logs/<nome>.out` e o DEPLOYMENT §15.
* Cada agente cria as suas pastas em `var/<nome>/` na primeira subida e se cadastra na tabela de agentes (`AGENT_START` na auditoria).

---

## 13. Validação

No servidor, em cada tipo:

```bash
. ~/sss_pacote/sss_vars.sh; sss_tipo DEV                       # depois, sss_tipo PROD
U=http://127.0.0.1:$PORT
curl -s -o /dev/null -w "raiz: HTTP %{http_code}\n" $U/                                                 # 303
curl -s -o /dev/null -w "login: HTTP %{http_code}\n" $U/script_scheduling_service/default/login          # 200
curl -s -D - -o /dev/null $U/script_scheduling_service/default/login | grep -icE "content-security|x-frame|x-content|referrer"   # 4
curl -s -o /dev/null -w "origem estranha: HTTP %{http_code}\n" -X POST -H "Origin: http://evil.example" -d "x=1" $U/script_scheduling_service/default/login   # 403
```

Na estação do usuário: o web atende só em `127.0.0.1` do servidor. O navegador chega a ele por um túnel SSH que encaminhe a porta local `<PORT>` para `127.0.0.1:<PORT>` do servidor, ou por um proxy da empresa (DEPLOYMENT §10.4). Com o túnel nas mesmas portas, a URL é `http://127.0.0.1:<PORT>/`: o DEV mostra a faixa amarela "AMBIENTE DEV"; o PROD, sem faixa.

Em cada tipo:
1. Entre com `admin` e troque a senha inicial. Troque também as de `op.prod`, `op.hml` e `consulta`, ou inative os que não forem usados.
2. **Agentes:** todos `OK`, cada um com o seu ambiente, o hostname `$SSS_SERVIDOR` e a pasta base `<RAIZ>/scripts_ambiente`.
3. **Teste de execução:** crie um arquivo (`printf 'a\nb\nc\n' > $SSS_BASE/$T/teste_sss.txt`) e dispare `contar_linhas_arquivo` no ambiente do `$SSS_AGENTE_HEALTH` com esse caminho. O ticket termina em `SUCCESS` nesse agente, e o log mostra 3 linhas.
4. `health.py` com código 0 (passo 12).

---

## 14. Permanência (`crontab` da conta)

O bloco gera as linhas do SSS (variáveis, keepalive com `@reboot` e a cada 5 minutos, e um `health.py` por tipo) num arquivo para revisão:

```bash
. ~/sss_pacote/sss_vars.sh
{ echo "# --- SSS (DEPLOYMENT-SERVER), gerado em $(date '+%Y-%m-%d %H:%M') ---"
  echo "PYTHON=$PYTHON"; echo "SSS_TZ=$SSS_TZ"
  [ -n "$ORACLE_HOME" ] && echo "ORACLE_HOME=$ORACLE_HOME"
  [ -n "$SSS_IC_DIR" ] && { echo "SSS_IC_DIR=$SSS_IC_DIR"; echo "LD_LIBRARY_PATH=$SSS_IC_DIR"; }
  [ -n "${SSS_LOCALE:-}" ] && echo "SSS_LOCALE=$SSS_LOCALE"
  for t in $SSS_TIPOS; do sss_tipo $t >/dev/null
    echo "@reboot      cd $R && bin/sss-keepalive.sh $SSS_WEB:$PORT $SSS_NOMES_AGENTES"
    echo "*/5 * * * *  cd $R && bin/sss-keepalive.sh $SSS_WEB:$PORT $SSS_NOMES_AGENTES"
    echo "*/5 * * * *  cd $R && \$PYTHON scripts/health.py --name $SSS_AGENTE_HEALTH > var/$SSS_AGENTE_HEALTH/logs/health.txt 2>&1"
  done; } > ~/sss_pacote/crontab_sss.txt
cat ~/sss_pacote/crontab_sss.txt
```

Revise e acrescente ao fim do `crontab` atual (as variáveis valem para as linhas abaixo delas). Se o bloco do SSS já estiver lá, ele não é repetido: para trocá-lo, apague o bloco antigo com `crontab -e` e rode de novo.

```bash
if crontab -l 2>/dev/null | grep -q '^# --- SSS (DEPLOYMENT-SERVER)'; then echo "ja existe um bloco do SSS no crontab (nada acrescentado)"
else (crontab -l 2>/dev/null; cat ~/sss_pacote/crontab_sss.txt) | crontab - && echo "bloco do SSS acrescentado"; fi
crontab -l | grep -c sss-keepalive; echo $(( $(echo $SSS_TIPOS | wc -w) * 2 ))   # os dois números iguais
```

A limpeza dos logs e saídas antigos é manual (README §11.3). Para agendá-la, use a linha `find` do DEPLOYMENT §4.0, uma para cada raiz, começando só com `-print`.

---

## 15. Operação no dia a dia

Sempre a partir da raiz certa (`. ~/sss_pacote/sss_vars.sh; sss_tipo <TIPO> && cd "$R"`):

```bash
bin/sss-keepalive.sh --pause <agente>         # o keepalive não sobe mais esse processo
bin/sss-stop.sh <agente>                      # para o agente (só o desta raiz)
bin/sss-keepalive.sh --resume <agente>        # volta na próxima passada do cron
# parar o web DESTA raiz: o PID pelo cwd, nunca só pelo nome (cada raiz tem o seu web0001)
bin/sss-keepalive.sh --pause $SSS_WEB
for p in /proc/[0-9]*; do
  [ "$(readlink $p/cwd 2>/dev/null)" = "$(pwd -P)" ] && tr '\0' ' ' < $p/cmdline | grep -q "scripts/run_web.py --name $SSS_WEB" && kill -TERM ${p#/proc/}
done
bin/sss-keepalive.sh --resume $SSS_WEB
```

Um agente parado deixa o ambiente dele sem atendimento: o `health.py` dá `CRITICAL: ambiente X ativo sem nenhum agente saudavel` até ele voltar (DEPLOYMENT §13). Atualizações seguem o DEPLOYMENT §18 (`bin/sss-update.sh`).

---

## 16. Retorno (desfazer a implantação)

Em cada tipo a desfazer, com autorização:

```bash
crontab -e                                    # apague as linhas deste tipo (passo 14)
. ~/sss_pacote/sss_vars.sh; sss_tipo <TIPO> && cd "$R"
for n in $SSS_WEB $SSS_NOMES_AGENTES; do bin/sss-keepalive.sh --pause $n; done
for n in $SSS_NOMES_AGENTES; do bin/sss-stop.sh $n; done
# o web: o laço do passo 15
( umask 077; tar -czf ~/sss_pacote/retorno_${T}_$(date +%Y%m%d_%H%M%S).tar.gz instance var )   # config e logs; tem senhas
```

O esquema sai com o `02_rollback_sss_<owner>_${P}.sql` deste tipo, **depois** de um backup e só desse prefixo. Ele apaga os dados. Por fim, `cd .. && rm -rf script_scheduling_service`. Uma instalação antiga parada no passo 6 volta descomentando o `crontab` dela.

---

## 17. Registro da execução (auditoria)

Copie esta tabela para o registro da janela e preencha cada linha (uma coluna de resultado por tipo, quando o passo for por tipo):

| Passo | Conferência | Esperado | Resultado (data, hora, quem) |
|---|---|---|---|
| 0 | `sss_vars.sh` preenchido; `sss_tipo` de cada tipo | sem `<...>`; raiz, prefixo e porta certos | |
| 2 | Sessão no servidor | `SSS_SERVIDOR` / `SSS_CONTA` | |
| 3.1 | Sistema, glibc, disco, pasta base, locale | anotados; base gravável | |
| 3.2 | Python e versão; `stdlib OK`; tempo da PBKDF2 | ≥ 3.6.0; OK; ≤ 3 s | |
| 3.3 | Driver e cliente Oracle; `sqlplus` | um driver carrega o cliente | |
| 3.4 | Banco alcançável (cada DSN); portas; SSS antigo | alcançável; livres; anotado | |
| 4.1 | Por prefixo: `WHENEVER` 1; outros prefixos 0; maior identificador; `sha256sum` | 1; 0; ≤ 30; anotados | |
| 4.2 | `ORIGEM`; `sha256sum -c`; 3 SQL por tipo; 14 utilitários | anotado; OK; 3; 14 | |
| 5 | Cinco arquivos; `sha256sum -c`; servidor e conta | OK; conferem | |
| 6 | Decisão sobre o SSS antigo; `crontab` salvo | anotada; salvo | |
| 7 | `conteudo confere` em cada tipo | todos | |
| 8 | `secrets.cfg` `600`, `CHANGE_ME` 0, um bloco por ambiente | todos os tipos | |
| 9 | Prefixo vazio antes; `ORA-`/`SP2-` = 0; `99` com `OK: nenhuma falha` | todos os tipos | |
| 10 | 14 utilitários; nada gravável por grupo/outros | 14; 0 | |
| 11 | `check_env` código 0 em todos os processos; `probe_driver`; `CONFIG_OK` | todos | |
| 12 | 1 web e um processo por agente; porta em `127.0.0.1`; `healthy_agents` | todos os tipos | |
| 13 | HTTP 303/200/4/403; senhas trocadas; ticket de teste `SUCCESS` | todos os tipos | |
| 14 | `crontab` com 2 keepalives e 1 `health.py` por tipo | conferido | |

---

## Apêndice A. Servidor `brtlvlty3067sl` (29/10/2026)

### A.1 `sss_vars.sh`

```bash
SSS_SERVIDOR=brtlvlty3067sl
SSS_CONTA=mastersafgf
SSS_BASE=/portaloptrib/TESHUVA/SSS
SSS_TIPOS="DEV PROD"
SSS_DB_USER=openrisow
SSS_OWNER=openrisow
SSS_DSN_DEV='(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=10.129.177.188)(PORT=1521))(CONNECT_DATA=(SID=GFPR)))'
SSS_DSN_PROD='(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=10.129.177.188)(PORT=1521))(CONNECT_DATA=(SID=GFPR)))'
SSS_PREFIXO_DEV=s3dev_
SSS_PREFIXO_PROD=s3prd_
SSS_OUTROS_PREFIXOS="tbsss_ ssdev_"
SSS_PORTA_DEV=18000
SSS_PORTA_PROD=18001
SSS_WEB=web0001
SSS_AGENTES="agente0001:GFPREPROD agente0002:CLONE2 agente0003:CLONE1 agente0004:CLONE6 agente0005:CLONE7"
SSS_MAX_PARALLEL=4
SSS_TZ=America/Sao_Paulo
PYTHON=/portaloptrib/TESHUVA/sparta/python3.8/bin/python3
ORACLE_HOME=/opt/oracle/product/12c/client
SSS_IC_DIR=/opt/oracle/product/12c/client/lib
SSS_DRIVER_MODE=auto
SSS_LOCALE=en_US.utf8
```

O resto do arquivo (a parte "derivados" e a função `sss_tipo`) é o do passo 0, sem mudança.

### A.2 Achados da pré-checagem (passos 2 e 3)

| Item | Encontrado |
|---|---|
| Acesso | Só pelo bastion `mastersafgf@brtlvlts1216pl` (10.238.10.109); o 3067 é `10.129.164.55` |
| Sistema | CentOS/RHEL 6, kernel 2.6.32, glibc 2.12 (o `python-oracledb` precisa de 2.17 e não serve) |
| Disco | `/portaloptrib` com 15 GB, 7,5 GB livres |
| Pasta base | `/portaloptrib/TESHUVA/SSS` não existia; `/portaloptrib/TESHUVA` é da conta (`755`) |
| Python | Só o 3.8.5 do Sparta: `stdlib OK`, sem `ssl` e sem `_hashlib` (PBKDF2 em 0,3 s) |
| Driver | `cx_Oracle` 8.3.0 com o cliente completo 12.2 (fora do `ldconfig`); sem `oracledb`. Com `auto`, Thin e Thick falham na hora (`IMPORT_ERROR`) e o cx_Oracle conecta |
| `sqlplus` | 12.2, em `/opt/oracle/product/12c/client/bin` |
| Banco | `10.129.177.188:1521` (GFPR) alcançável. No mesmo owner `openrisow` já existem `tbsss_` e `ssdev_` (21 tabelas cada, instalações da máquina de desenvolvimento); `s3dev_` e `s3prd_` vazios |
| Portas | 18000 e 18001 livres |
| Umask da conta | `002` (os arquivos transferidos chegaram `664`): o passo 7 usa `umask 027` |
| Locale | Sem `C.UTF-8`; existem `en_US.utf8` e `pt_BR.utf8` (escolhido `en_US.utf8`, que mantém ponto decimal e mensagens do sistema em inglês nos scripts). A sessão SSH mostra `Cannot set LC_CTYPE to default locale`: o locale da estação não existe no servidor, sem efeito no SSS, que exporta o seu |
| SSS antigo | `web2py.py` na porta 8000 desde 17/10, pasta `/home/mastersafgf/sss/web2py` (anterior ao CR-021); `crontab` sem SSS |

### A.3 Decisões desta implantação

| # | Decisão |
|---|---|
| 1 A | Segue o sistema atual, não o pedido original (tabela A.4) |
| 2 B | Hosts reais no documento, sem senha |
| 3 A | O DEV usa o DSN direto do GFPR (o `localhost:2424` do pedido é um túnel da máquina de desenvolvimento) |
| 4 B, 5 A | Prefixos novos, `s3dev_` e `s3prd_`, independentes do `tbsss_` e do `ssdev_` |
| — | Transferência manual pela equipe; pacote dos arquivos locais (sem git); acesso pelo meio habitual; `driver_mode = auto` |
| 7 A | SSS antigo (web2py, porta 8000, `/home/mastersafgf/sss/web2py`): parado no passo 6, sem apagar nada; a pasta `~/sss` fica como histórico |

### A.4 Diferenças em relação ao pedido original

| Pedido | Como é hoje |
|---|---|
| web2py | Não existe mais: o web é o servidor próprio do SSS (`scripts/run_web.py`, CR-021) |
| `scripts/empacotar.py` | `make package-local` (ou `tools/package.py`), na máquina de origem (passo 4.2) |
| `/etc/sss/secrets.cfg` | O SSS só lê `<RAIZ>/instance/secrets.cfg` (CR-032), `0600`, dono a conta do SSS; o 3067 também não tem `sudo` |
| `sss_env = DEV/PROD` | Retirada no CR-032 (só gera aviso). O ambiente vem do nome da pasta `DEV` ou `PROD` acima da raiz |
| DSN do DEV `localhost:2424` | Túnel SSH da máquina de desenvolvimento para `10.129.177.188:1521`; no servidor, o endereço direto |
| `base_script_dir` | `[agent] script_base_dir`; o padrão é `<RAIZ>/scripts_ambiente/` (passo 10) |
| `agent_id` e `ambientes_atendidos` | O `agent_id` é o `[app] name`; os ambientes ficam em `[agent] environments` |
| `sondar_driver` | `scripts/probe_driver.py` e `scripts/check_env.py --name` (passos 3 e 11) |
| `scp`/`rsync` com `ProxyJump` | Transferência manual pela equipe: o passo 5 lista os arquivos e confere os `sha256` |
