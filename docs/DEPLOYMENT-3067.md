# SSS — Implantação do DEV e do PROD no servidor 3067

Roteiro passo a passo, com comandos completos e conferências, para instalar o Script Scheduling Service no `brtlvlty3067sl` em duas instalações independentes: **DEV** e **PROD**, cada uma com 1 web e 5 agentes (um por ambiente). O guia geral é o `docs/DEPLOYMENT.md`; aqui ficam só os valores e a ordem deste servidor. Cada passo diz o que conferir antes de seguir. Se uma conferência falhar, **pare** e resolva antes do passo seguinte.

**Senhas:** nenhuma senha aparece neste documento. A senha do bastion é digitada quando o `ssh` pede. As senhas de banco são copiadas do cofre direto para o `secrets.cfg` no servidor (passo 8.2), nunca por e-mail, chat ou arquivo intermediário.

## 0. Valores desta implantação

| Item | DEV | PROD |
|---|---|---|
| Bastion | `mastersafgf@brtlvlts1216pl` (10.238.10.109), com senha | idem |
| Destino | `mastersafgf@brtlvlty3067sl` (10.129.164.55), só com chave | idem |
| Raiz (`<RAIZ>`) | `/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service` | `/portaloptrib/TESHUVA/SSS/PROD/script_scheduling_service` |
| Banco (`[oracle] dsn`) | `(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=10.129.177.188)(PORT=1521))(CONNECT_DATA=(SID=GFPR)))` | o mesmo |
| Conta e owner | `openrisow` (conta única, dona do esquema; DEPLOYMENT §4.0) | a mesma |
| `[oracle] table_prefix` | `s3dev_` | `s3prd_` |
| Scripts SQL | `docs/sql/*_openrisow_s3dev.sql` | `docs/sql/*_openrisow_s3prd.sql` |
| Web | `web0001`, `127.0.0.1:18000`, `allowed_origins = http://127.0.0.1:18000` | `web0001`, `127.0.0.1:18001`, `allowed_origins = http://127.0.0.1:18001` |
| Agentes | `agente0001` GFPREPROD, `agente0002` CLONE2, `agente0003` CLONE1, `agente0004` CLONE6, `agente0005` CLONE7 | os mesmos nomes e ambientes |

* **DEV e PROD não se misturam:** cada raiz tem as suas pastas (`var/`, `instance/`), e cada prefixo tem as suas tabelas. Os mesmos nomes de processo nas duas raízes não conflitam: o keepalive e o `sss-stop.sh` trabalham só na raiz de onde são chamados.
* **Independente das outras instalações:** os prefixos `s3dev_` e `s3prd_` são novos. As tabelas `ssdev_` e `tbsss_` do mesmo owner (DEV e PROD da máquina de desenvolvimento) **não são tocadas** por nenhum passo deste roteiro.

### 0.1 Diferenças em relação ao pedido original

O pedido foi escrito para uma versão anterior do SSS. Este roteiro segue o código atual (decisão A):

| Pedido | Como é hoje |
|---|---|
| web2py | Não existe mais: o web é o servidor próprio do SSS (`scripts/run_web.py`, CR-021) |
| `scripts/empacotar.py` | `make package` (ou `tools/package.py`), na máquina de origem (passo 4) |
| `/etc/sss/secrets.cfg` | O SSS só lê `<RAIZ>/instance/secrets.cfg` (CR-032), `0600`, dono a conta do SSS. Também não há `sudo` no 3067 |
| `sss_env = DEV/PROD` | Retirada no CR-032 (só gera aviso). O ambiente vem do nome da pasta `DEV` ou `PROD` acima da raiz |
| DSN do DEV `localhost:2424` | Esse endereço é um túnel SSH da máquina de desenvolvimento para `10.129.177.188:1521`. No 3067 o DEV usa o endereço direto (decisão A) |
| `base_script_dir` | `[agent] script_base_dir`; o padrão é `<RAIZ>/scripts_ambiente/` (passo 10) |
| `agent_id` e `ambientes_atendidos` | O `agent_id` é o `[app] name`; os ambientes ficam em `[agent] environments` |
| `sondar_driver` | `scripts/probe_driver.py` e `scripts/check_env.py --name` (passos 3 e 11) |

---

## 1. Antes de começar

* Janela combinada e acesso ao cofre com: a senha da conta `openrisow` no GFPR e as contas (usuário e senha) dos bancos dos cinco ambientes (GFPREPROD, CLONE2, CLONE1, CLONE6, CLONE7).
* Na máquina de origem: o repositório git do SSS (com o `instance/agente0001/config.ini` do DEV da origem, usado só para gerar os scripts SQL), Python 3.6 ou superior, `git`, `make`, `ssh`, `scp` e `rsync`.
* Abra um registro da execução (passo 17) e anote cada conferência com o resultado.

---

## 2. Acesso SSH pelo bastion

### 2.1 `~/.ssh/config` na máquina de origem

O bastion só aceita os algoritmos `ssh-rsa` antigos. A conexão mestra (`ControlMaster`) faz a senha do bastion ser pedida uma vez por sessão:

```text
Host sss-bastion
    HostName 10.238.10.109
    User mastersafgf
    HostKeyAlgorithms +ssh-rsa
    PubkeyAcceptedAlgorithms +ssh-rsa
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h-%p
    ControlPersist 30m

Host sss-3067
    HostName 10.129.164.55
    User mastersafgf
    ProxyJump sss-bastion
    HostKeyAlgorithms +ssh-rsa
    PubkeyAcceptedAlgorithms +ssh-rsa
```

```bash
chmod 0600 ~/.ssh/config
ssh sss-bastion 'hostname; whoami'          # pede a senha do bastion; esperado: brtlvlts1216pl / mastersafgf
```

### 2.2 Chave da origem autorizada no destino (uma vez)

O `ProxyJump` (`-J`) só repassa a conexão TCP: quem se autentica no 3067 é a máquina de origem, com a chave **dela**. Hoje o 3067 só confia na chave do bastion. Autorize a chave pública da origem uma vez, pelo próprio bastion:

```bash
# na origem; gere a chave só se ainda não existir
[ -f ~/.ssh/id_ed25519.pub ] || ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -C "sss-implantacao-$(whoami)"
cat ~/.ssh/id_ed25519.pub | ssh sss-bastion \
  'ssh -o BatchMode=yes mastersafgf@10.129.164.55 "umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys"'
ssh -o BatchMode=yes sss-3067 'hostname; whoami'    # esperado: brtlvlty3067sl / mastersafgf, sem pedir senha do destino
```

Registre no passo 17 a impressão digital da chave (`ssh-keygen -lf ~/.ssh/id_ed25519.pub`). Ao fim do trabalho, se a chave não deve ficar, remova a linha dela do `~/.ssh/authorized_keys` do 3067.

---

## 3. Pré-checagem no 3067 (só leitura)

Nada é criado nem alterado neste passo. Rode numa sessão `ssh sss-3067`.

### 3.1 Conta, disco e sistema

```bash
id; hostname; uname -a
df -h /portaloptrib                           # espaço para as duas raízes, os logs e as saídas (DEPLOYMENT §4.3)
ls -ld /portaloptrib/TESHUVA/SSS               # a pasta base existe e é da conta (ou gravável por ela)
ls -la /portaloptrib/TESHUVA/SSS               # DEV/ e PROD/ não podem existir com conteúdo
ls /proc/self/cwd >/dev/null && echo "proc OK" # o keepalive usa /proc
```

### 3.2 Python

O SSS precisa de Python 3.6.0 ou superior, com o driver Oracle. O launcher só aceita interpretador chamado `python3` ou `python3.X`.

```bash
for p in python3 python3.6 python3.8 /usr/bin/python3 /portaloptrib/TESHUVA/sparta/python3.8/bin/python3.8; do
  command -v "$p" >/dev/null 2>&1 && echo "$p -> $("$p" -c 'import sys; print(sys.version.split()[0], sys.executable)')"
done
```

Escolha um e use-o em todos os passos seguintes:

```bash
export PYTHON=<caminho escolhido>             # ex.: /usr/bin/python3
"$PYTHON" -c "import sys; assert sys.version_info >= (3, 6, 0); import zlib, hmac, secrets, json, configparser, zipfile; print('stdlib OK')"
"$PYTHON" -c "import _hashlib" 2>/dev/null && echo "_hashlib OK" || echo "SEM _hashlib (PBKDF2 em Python puro)"
"$PYTHON" -c "import hashlib, time; t=time.time(); hashlib.pbkdf2_hmac('sha256', b'a', b'b', 200000); print('PBKDF2 200000: %.1f s' % (time.time()-t))"
```

* `stdlib OK` é obrigatório. Sem ele, **pare**: o Python não serve.
* PBKDF2 acima de 3 s: cada login demora isso. Registre e prefira outro Python, se houver.

### 3.3 Driver Oracle e Instant Client

```bash
"$PYTHON" -c "import oracledb; print('oracledb', oracledb.__version__)" 2>&1 | tail -1
"$PYTHON" -c "import cx_Oracle; print('cx_Oracle', cx_Oracle.version)" 2>&1 | tail -1
"$PYTHON" -c "import ssl" 2>/dev/null && echo "ssl OK (modo thin possivel)" || echo "SEM ssl: so thick ou cx_oracle"
ldconfig -p 2>/dev/null | grep -c libclntsh; ls -d ${ORACLE_HOME:-/nao}/lib /opt/oracle/instantclient* 2>/dev/null
command -v sqlplus && sqlplus -V
```

* Precisa de `oracledb` ou `cx_Oracle`. Sem nenhum dos dois, **pare**: a instalação do driver é da infraestrutura (DEPLOYMENT §2, sem `pip install` no servidor).
* Sem `ssl`, o modo Thin não funciona: o Instant Client precisa existir (no `ldconfig` ou numa pasta, que vira `SSS_IC_DIR`, passo 12). O `driver_mode` fica `thick` (ou `cx_oracle`, se só houver o cx_Oracle).
* Sem `sqlplus`, o banco é criado pelo `init_db.py` (passo 9, alternativa).

### 3.4 Banco, portas e instalação anterior

```bash
timeout 5 bash -c 'echo > /dev/tcp/10.129.177.188/1521' && echo "GFPR 1521 alcancavel" || echo "GFPR INALCANCAVEL"
(ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null) | grep -E ':(18000|18001)\b' || echo "18000 e 18001 livres"
ps -eo pid,user,lstart,args | grep -E '[r]un_web|[r]un_scheduler|[w]eb2py|[s]ss' 
crontab -l 2>/dev/null | grep -n -i sss || echo "crontab sem SSS"
```

* GFPR inalcançável: **pare** e peça a liberação da rota 10.129.164.55 → 10.129.177.188:1521.
* Porta ocupada ou processo do SSS antigo no ar: siga o passo 6 antes de subir qualquer coisa.

---

## 4. Scripts SQL e pacote na máquina de origem

### 4.1 Geração dos scripts SQL (`s3dev_` e `s3prd_`)

Os scripts saem do registro de identificadores do código, com o owner e o prefixo de cada instalação (DEPLOYMENT §5.2). A conta única é a dona do esquema: nenhum GRANT é gerado (`--grants-to` não se aplica).

```bash
cd <repositório>
git pull --ff-only && git log --oneline -1                    # o commit da janela (registre no passo 17)
for PFX in s3dev_ s3prd_; do
  python3 scripts/generate_sql.py --name agente0001 --owner OPENRISOW --prefix $PFX --out-dir docs/sql
done
ls -l docs/sql/*_s3dev.sql docs/sql/*_s3prd.sql               # esperado: 01_deploy, 02_rollback e 99_validate de cada um
```

O `--name agente0001` só fornece a conta (`openrisow`, a dona do esquema). O owner e o prefixo vêm da linha de comando, e o arquivo não conecta ao banco. Sem esse config, o resultado só difere no comentário dos GRANTs.

Conferências, antes de seguir:

```bash
for P in s3dev s3prd; do
  echo "== $P"
  grep -c "WHENEVER SQLERROR EXIT FAILURE ROLLBACK" docs/sql/01_deploy_sss_openrisow_$P.sql          # esperado: 1
  grep -E -i "tbsss_|ssdev_" docs/sql/01_deploy_sss_openrisow_$P.sql | grep -vc "COMMENT ON COLUMN"   # esperado: 0
  grep -E -ic "tbsss_|ssdev_" docs/sql/02_rollback_sss_openrisow_$P.sql                              # esperado: 0 (só apaga o próprio prefixo)
  grep -oE "[a-z_0-9]*${P}_[a-z_0-9]*" docs/sql/01_deploy_sss_openrisow_$P.sql | awk '{ if (length($0) > m) m = length($0) } END { print "maior identificador:", m }'   # esperado: até 30
  grep -ic "GRANT .* TO PUBLIC" docs/sql/01_deploy_sss_openrisow_$P.sql                              # esperado: 0
done
git status --short docs/sql
```

* As citações de `tbsss_` no `01` ficam só nos `COMMENT ON COLUMN` das FKs (texto fixo do dicionário, sem efeito).
* `git status` vazio: os scripts versionados já estavam iguais. Se aparecerem arquivos novos ou alterados, revise o `git diff` e faça o commit antes do pacote: `git add docs/sql/*_s3dev.sql docs/sql/*_s3prd.sql && git commit -m "SQL do 3067 (s3dev_, s3prd_)"`. O pacote só leva o que está no commit.
* O DBA pode revisar o `01` antes da janela. Ele também pode ser gerado de novo no 3067, depois do passo 8, pelo mesmo comando com `--name agente0001`, para conferir que sai idêntico ao do pacote.

### 4.2 Pacote

```bash
cd <repositório>                              # árvore limpa no commit a implantar
git status --short                            # esperado: vazio (o make package recusa alterações)
make package                                  # grava .bkp/pacote_<data>/sss-<versao>.tar.gz, SHA256SUMS e COMMIT
PKG=$(ls -d .bkp/pacote_2* | tail -1); ls -l "$PKG"; cat "$PKG/COMMIT"
(cd "$PKG" && sha256sum -c SHA256SUMS)        # esperado: sss-<versao>.tar.gz: OK
tar -tzf "$PKG"/sss-*.tar.gz | grep -E '__pycache__|secrets\.cfg$|common\.ini$|config\.ini$' || echo "sem cache e sem segredos"
tar -tzf "$PKG"/sss-*.tar.gz | grep -E 's3(dev|prd)\.sql'   # esperado: os seis scripts SQL dos prefixos novos
```

O pacote é feito por `git archive` (só arquivos versionados) e pelo `tools/package.py`, que só usa a biblioteca padrão e recusa `__pycache__` e segredos.

Os scripts de exemplo do seed (`utilitarios/*`) ficam em `dev/scripts/`, que o pacote não leva. Gere um tar separado só com eles:

```bash
git archive --format=tar HEAD dev/scripts/utilitarios | gzip -9 > "$PKG/utilitarios.tar.gz"
(cd "$PKG" && sha256sum utilitarios.tar.gz >> SHA256SUMS && sha256sum -c SHA256SUMS)
```

---

## 5. Transferência pelo bastion

Direto da origem para o 3067, pelo `ProxyJump`. Nada fica gravado no bastion.

```bash
ssh sss-3067 'mkdir -m 0700 -p ~/sss_pacote'
scp -J sss-bastion "$PKG"/sss-*.tar.gz "$PKG"/utilitarios.tar.gz "$PKG"/SHA256SUMS "$PKG"/COMMIT sss-3067:sss_pacote/
# equivalente com rsync (retoma uma cópia interrompida):
# rsync -av --partial -e "ssh -J sss-bastion" "$PKG"/ sss-3067:sss_pacote/
ssh sss-3067 'cd ~/sss_pacote && sha256sum -c SHA256SUMS && cat COMMIT'
```

Esperado: `OK` em cada arquivo e o mesmo commit do passo 4. Com o `~/.ssh/config` do passo 2, `scp sss-3067:...` já usa o salto. O `-J sss-bastion` acima é a forma explícita, e `-o ProxyCommand="ssh -W %h:%p sss-bastion"` é a equivalente para um cliente sem `-J`.

---

## 6. Instalação anterior no 3067

Uma instalação antiga do SSS (anterior ao CR-028) roda direto em `/portaloptrib/TESHUVA/SSS`, na porta 18000. Ela precisa parar antes do passo 12. **Nada é apagado.**

```bash
cd /portaloptrib/TESHUVA/SSS
ls -la                                        # registre o conteúdo (passo 17)
crontab -l > ~/sss_pacote/crontab_antes_$(date +%Y%m%d_%H%M%S).txt 2>/dev/null; crontab -l 2>/dev/null | grep -n -i sss
[ -x ./parar_sss.sh ] && ./parar_sss.sh       # o parador da instalação antiga, se existir
[ -f work/sss_web.pid ] && kill -TERM "$(cat work/sss_web.pid)" 2>/dev/null
sleep 5; ps -eo pid,args | grep -E '[r]un_web|[w]eb2py|[r]un_scheduler'   # esperado: nada da instalação antiga
(ss -ltn 2>/dev/null || netstat -ltn) | grep -E ':(18000|18001)\b' || echo "portas livres"
```

Se o `crontab` tiver linhas da instalação antiga, comente-as (`crontab -e`, `#` no início). Os arquivos antigos ficam onde estão. Eles não se misturam com `DEV/` e `PROD/`.

---

## 7. Extração nas duas raízes

```bash
for T in DEV PROD; do
  mkdir -p /portaloptrib/TESHUVA/SSS/$T && cd /portaloptrib/TESHUVA/SSS/$T
  [ -e script_scheduling_service ] && { echo "JA EXISTE: $T/script_scheduling_service (pare e confira)"; break; }
  tar -xzf ~/sss_pacote/sss-*.tar.gz
  mv sss-* script_scheduling_service && chmod 0750 script_scheduling_service
  (cd script_scheduling_service && sha256sum -c --quiet SHA256SUMS && echo "$T: conteudo confere" && ls)
done
```

Esperado nas duas: `conteudo confere` e `AGENTS.md README.md SHA256SUMS bin docs instance scripts src`.

---

## 8. Configuração (em cada raiz)

Rode o bloco uma vez com `T=DEV` e outra com `T=PROD`.

```bash
T=DEV                                          # depois, T=PROD
R=/portaloptrib/TESHUVA/SSS/$T/script_scheduling_service; cd "$R"
case $T in DEV) PREFIX=s3dev_; PORT=18000;; PROD) PREFIX=s3prd_; PORT=18001;; esac
```

### 8.1 `instance/common.ini` (o banco)

```bash
umask 027
cat > instance/common.ini <<EOF
; common.ini do servidor (CR-032, D18): [oracle] comum ao web e aos agentes. Senha no instance/secrets.cfg.
[oracle]
user = openrisow
dsn = (DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=10.129.177.188)(PORT=1521))(CONNECT_DATA=(SID=GFPR)))
owner = openrisow
table_prefix = $PREFIX
driver_mode = thick
EOF
chmod 0640 instance/common.ini; grep -n "table_prefix" instance/common.ini
```

Com só o cx_Oracle no passo 3.3, troque para `driver_mode = cx_oracle`.

### 8.2 `instance/secrets.cfg` (senhas e chave da sessão)

O arquivo fica na raiz de cada tipo (`instance/secrets.cfg`), com modo `0600` e dono a conta `mastersafgf`. É o único lugar com senhas. Gere uma `cookie_key` **própria de cada tipo** (DEV e PROD diferentes):

```bash
cp instance/exemplos/secrets.cfg.example instance/secrets.cfg && chmod 0600 instance/secrets.cfg
"$PYTHON" -c "import secrets; print(secrets.token_urlsafe(48))"    # cole o valor em [web] cookie_key
vi instance/secrets.cfg
```

Conteúdo final (os valores vêm do cofre, digitados no `vi`):

```ini
[oracle]
password = <senha da openrisow no GFPR>

[web]
cookie_key = <valor gerado acima>

[environment:GFPREPROD]
user = <usuário do banco do GFPREPROD>
password = <senha>

[environment:CLONE2]
user = <...>
password = <...>

[environment:CLONE1]
user = <...>
password = <...>

[environment:CLONE6]
user = <...>
password = <...>

[environment:CLONE7]
user = <...>
password = <...>
```

```bash
stat -c '%a %U %n' instance/secrets.cfg                      # esperado: 600 mastersafgf instance/secrets.cfg
grep -c CHANGE_ME instance/secrets.cfg                       # esperado: 0
grep -c '^\[environment:' instance/secrets.cfg               # esperado: 5
```

O bloco de exemplo `[environment:PRODUCAO]` deve sair do arquivo: o seed não tem esse ambiente.

### 8.3 Web (`instance/web0001/config.ini`)

```bash
mkdir -m 0750 instance/web0001
cat > instance/web0001/config.ini <<EOF
; config.ini do no web (CR-028). Banco no instance/common.ini; segredos no instance/secrets.cfg.
[app]
name = web0001

[web]
allowed_origins = http://127.0.0.1:$PORT
EOF
chmod 0640 instance/web0001/config.ini
```

### 8.4 Os cinco agentes (`instance/agente000N/config.ini`)

```bash
for pair in agente0001:GFPREPROD agente0002:CLONE2 agente0003:CLONE1 agente0004:CLONE6 agente0005:CLONE7; do
  name=${pair%%:*}; env=${pair#*:}
  mkdir -m 0750 instance/$name
  cat > instance/$name/config.ini <<EOF
; config.ini do agente (CR-028): o nome e o agent_id. Banco no instance/common.ini; segredos no instance/secrets.cfg.
[app]
name = $name

[agent]
environments = $env
max_parallel_jobs = 4
env_passthrough = ORACLE_HOME,TNS_ADMIN,NLS_LANG,LD_LIBRARY_PATH
EOF
  chmod 0640 instance/$name/config.ini
done
grep -H "environments" instance/agente000*/config.ini
```

Esperado: cada agente com um ambiente só, na ordem da tabela do passo 0. Não escreva `agent_id`, `script_base_dir` nem pastas: tudo sai do nome (DEPLOYMENT §7.1).

---

## 9. Banco: esquema `s3dev_` e `s3prd_`

Os dois esquemas são novos: o `01_deploy` só cria objetos do seu prefixo. **Nunca rode aqui um script `*_tbsss.sql` ou `*_ssdev.sql`**: eles são das outras instalações, no mesmo owner, e o `02_rollback` deles apagaria aquelas tabelas.

Os comandos vão num arquivo `.sql`, e o `sqlplus` pede a senha no terminal (`-L`: uma tentativa só). Primeiro, a conferência de que o prefixo está vazio (esperado `0`):

```bash
cd "$R"; P=${PREFIX%_}
DSN='(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=10.129.177.188)(PORT=1521))(CONNECT_DATA=(SID=GFPR)))'
cat > ~/sss_pacote/${P}_00_vazio.sql <<EOF
SELECT COUNT(*) FROM user_tables WHERE table_name LIKE '$(echo $P | tr a-z A-Z)\_%' ESCAPE '\';
EXIT
EOF
sqlplus -L "openrisow@${DSN}" @$HOME/sss_pacote/${P}_00_vazio.sql
```

Depois, a implantação e a validação, gravando a saída:

```bash
cat > ~/sss_pacote/${P}_01_99.sql <<EOF
SPOOL $HOME/sss_pacote/${P}_01_deploy.log
@$R/docs/sql/01_deploy_sss_openrisow_${P}.sql
SPOOL OFF
SPOOL $HOME/sss_pacote/${P}_99_validate.log
@$R/docs/sql/99_validate_deploy_openrisow_${P}.sql
SPOOL OFF
EXIT
EOF
sqlplus -L "openrisow@${DSN}" @$HOME/sss_pacote/${P}_01_99.sql
grep -c -E 'ORA-|SP2-' ~/sss_pacote/${P}_01_deploy.log      # esperado: 0
grep 'OK: nenhuma falha' ~/sss_pacote/${P}_99_validate.log    # esperado: as duas linhas de resumo
```

* O `01` para no primeiro erro (`WHENEVER SQLERROR EXIT FAILURE ROLLBACK`). Se ele parar, guarde o log, rode `@docs/sql/02_rollback_sss_openrisow_${P}.sql` (só o do prefixo deste passo) e repita.
* **Sem `sqlplus`** (passo 3.3): `"$PYTHON" scripts/init_db.py --name agente0001 --real-schema` cria o mesmo esquema e o seed, com a conta e os segredos do agente. Antes, `--dry-run` imprime o DDL sem conectar.
* O seed cria os usuários `admin`, `op.prod`, `op.hml` e `consulta` com a senha inicial do DEPLOYMENT §5.3. Ela é trocada no passo 13.

---

## 10. Árvore de scripts (`script_base_dir`)

A pasta base é a padrão, `<RAIZ>/scripts_ambiente/`, preservada pela atualização (DEPLOYMENT §9). O agente exige que o arquivo real não tenha escrita para grupo nem para outros (README §8.5). Os modos `0444` (arquivos) e `0555` (pastas) atendem a regra e também impedem que a própria conta altere os scripts sem querer:

```bash
cd "$R"
mkdir -p scripts_ambiente && tar -xzf ~/sss_pacote/utilitarios.tar.gz -C scripts_ambiente --strip-components=2
ls scripts_ambiente/utilitarios | wc -l                       # esperado: 14
find scripts_ambiente -type f -exec chmod 0444 {} +
find scripts_ambiente -type d -exec chmod 0555 {} +
find scripts_ambiente -perm /022 | wc -l                      # esperado: 0 (nada gravável por grupo/outros)
```

Para trocar um script depois: `chmod u+w` na pasta e no arquivo, troque, e volte para `0444`/`0555`.

---

## 11. Conferências antes de subir

Em cada raiz:

```bash
cd "$R"
for n in web0001 agente0001 agente0002 agente0003 agente0004 agente0005; do
  echo "== $n"; "$PYTHON" scripts/check_env.py --name $n; echo "codigo $?"
done
"$PYTHON" scripts/probe_driver.py thick --config instance/agente0001/config.ini   # ou cx_oracle
bin/sss-web.sh "$PYTHON" web0001 --check                       # esperado: CONFIG_OK ambiente=<TIPO>
```

* `check_env`: código 0 em todos (avisos não reprovam). A saída mostra o driver, o modo e a versão do servidor. Registre-a.
* Código 1: falta arquivo ou o banco não conectou (veja a linha `FALHA`). Código 2: Python menor que 3.6.0 ou nome errado.
* Instant Client fora do `ldconfig`: `export SSS_IC_DIR=<pasta do Instant Client>` antes destes comandos e no `crontab` (passo 14).

---

## 12. Subida

```bash
cd "$R"
export PYTHON=<o Python do passo 3.2> SSS_TZ=America/Sao_Paulo   # e SSS_IC_DIR, se for o caso
bin/sss-keepalive.sh web0001:$PORT agente0001 agente0002 agente0003 agente0004 agente0005; echo "codigo $?"
sleep 15
tail -n 3 var/*/logs/keepalive.log
for p in /proc/[0-9]*; do
  [ "$(readlink $p/cwd 2>/dev/null)" = "$(pwd -P)" ] && tr '\0' ' ' < $p/cmdline | grep -E 'run_(web|scheduler)\.py' && echo
done                                           # esperado: 1 run_web.py e 5 run_scheduler.py desta raiz
(ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null) | grep ":$PORT\b"   # esperado: 127.0.0.1:<porta> LISTEN
grep -h "pasta criada\|agente inicializado\|Subida abortada" var/agente000*/logs/internal/app/*/*/*/*/*/sss_scheduler_*.log | tail -n 15
"$PYTHON" scripts/health.py --name agente0001; echo "codigo $?"   # esperado: SSS OK ... healthy_agents=5, codigo 0
```

* Keepalive com código 3: algum processo não subiu. Veja `var/<nome>/logs/<nome>.out` e o DEPLOYMENT §15.
* Cada agente cria as suas pastas em `var/<nome>/` na primeira subida e se cadastra na tabela de agentes (`AGENT_START` na auditoria).

---

## 13. Validação

No 3067:

```bash
curl -s -o /dev/null -w "raiz: HTTP %{http_code}\n" http://127.0.0.1:$PORT/                                          # 303
curl -s -o /dev/null -w "login: HTTP %{http_code}\n" http://127.0.0.1:$PORT/script_scheduling_service/default/login    # 200
curl -s -D - -o /dev/null http://127.0.0.1:$PORT/script_scheduling_service/default/login | grep -icE "content-security|x-frame|x-content|referrer"   # 4
curl -s -o /dev/null -w "origem estranha: HTTP %{http_code}\n" -X POST -H "Origin: http://evil.example" -d "x=1" http://127.0.0.1:$PORT/script_scheduling_service/default/login   # 403
```

Na estação do usuário, por túnel (o web atende só em `127.0.0.1`):

```bash
ssh -N -L 18000:127.0.0.1:18000 -L 18001:127.0.0.1:18001 sss-3067
# navegador: http://127.0.0.1:18000/ (DEV, faixa amarela "AMBIENTE DEV") e http://127.0.0.1:18001/ (PROD, sem faixa)
```

Em cada tipo:
1. Entre com `admin` e troque a senha inicial. Troque também as senhas de `op.prod`, `op.hml` e `consulta`, ou inative os que não forem usados.
2. **Agentes:** os cinco `OK`, cada um com um ambiente, o hostname `brtlvlty3067sl` e a pasta base `<RAIZ>/scripts_ambiente`.
3. **Teste de execução:** crie um arquivo de teste (`printf 'a\nb\nc\n' > /portaloptrib/TESHUVA/SSS/$T/teste_sss.txt`) e dispare `contar_linhas_arquivo` no GFPREPROD com esse caminho. O ticket termina em `SUCCESS` no `agente0001`, com o log mostrando 3 linhas.
4. `health.py` com código 0 (passo 12).

---

## 14. Permanência (`crontab` da conta)

Uma linha de keepalive por raiz (`@reboot` e a cada 5 minutos), um `health.py` por raiz e a limpeza manual dos logs (DEPLOYMENT §4.0 e §12). Abra com `crontab -e` e acrescente:

```text
PYTHON=<o Python do passo 3.2>
SSS_TZ=America/Sao_Paulo
# SSS_IC_DIR=<pasta do Instant Client>    # so se ele nao estiver no ldconfig
D=/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service
P=/portaloptrib/TESHUVA/SSS/PROD/script_scheduling_service
@reboot      cd $D && bin/sss-keepalive.sh web0001:18000 agente0001 agente0002 agente0003 agente0004 agente0005
*/5 * * * *  cd $D && bin/sss-keepalive.sh web0001:18000 agente0001 agente0002 agente0003 agente0004 agente0005
@reboot      cd $P && bin/sss-keepalive.sh web0001:18001 agente0001 agente0002 agente0003 agente0004 agente0005
*/5 * * * *  cd $P && bin/sss-keepalive.sh web0001:18001 agente0001 agente0002 agente0003 agente0004 agente0005
*/5 * * * *  cd $D && $PYTHON scripts/health.py --name agente0001 > var/agente0001/logs/health.txt 2>&1
*/5 * * * *  cd $P && $PYTHON scripts/health.py --name agente0001 > var/agente0001/logs/health.txt 2>&1
```

```bash
crontab -l | grep -c sss-keepalive            # esperado: 4
```

A limpeza dos logs e saídas antigos é manual (README §11.3). Para agendá-la, use a linha `find` do DEPLOYMENT §4.0, uma para cada raiz, começando só com `-print`.

---

## 15. Operação no dia a dia

Sempre a partir da raiz certa (`cd $D` ou `cd $P`):

```bash
bin/sss-keepalive.sh --pause agente0003       # o keepalive não sobe mais esse processo
bin/sss-stop.sh agente0003                    # para o agente (só o desta raiz)
bin/sss-keepalive.sh --resume agente0003      # volta na próxima passada do cron
# parar o web DESTA raiz: o PID pelo cwd, nunca só pelo nome (as duas raízes têm um web0001)
bin/sss-keepalive.sh --pause web0001
for p in /proc/[0-9]*; do
  [ "$(readlink $p/cwd 2>/dev/null)" = "$(pwd -P)" ] && tr '\0' ' ' < $p/cmdline | grep -q 'scripts/run_web.py --name web0001' && kill -TERM ${p#/proc/}
done
bin/sss-keepalive.sh --resume web0001
```

Um agente parado deixa o ambiente dele sem atendimento: o `health.py` dá `CRITICAL: ambiente X ativo sem nenhum agente saudavel` até ele voltar (DEPLOYMENT §13). Atualizações seguem o DEPLOYMENT §18 (`bin/sss-update.sh`).

---

## 16. Retorno (desfazer a implantação)

Em cada raiz a desfazer, com autorização:

```bash
crontab -e                                    # apague as linhas desta raiz (passo 14)
cd "$R"
for n in web0001 agente0001 agente0002 agente0003 agente0004 agente0005; do bin/sss-keepalive.sh --pause $n; done
for n in agente0001 agente0002 agente0003 agente0004 agente0005; do bin/sss-stop.sh $n; done
# o web: o laço do passo 15
tar -czf ~/sss_pacote/retorno_${T}_$(date +%Y%m%d_%H%M%S).tar.gz instance var   # guarda config e logs (tem senhas: 0600)
chmod 0600 ~/sss_pacote/retorno_*.tar.gz
```

O esquema sai com `@docs/sql/02_rollback_sss_openrisow_s3dev.sql` (DEV) ou `..._s3prd.sql` (PROD), **depois** de um backup e só desse prefixo. Ele apaga os dados. Por fim, `cd .. && rm -rf script_scheduling_service`. A instalação antiga do passo 6 volta descomentando o `crontab` dela.

---

## 17. Registro da execução (auditoria)

Copie esta tabela para o registro da janela e preencha cada linha:

| Passo | Conferência | Esperado | Resultado (data, hora, quem) |
|---|---|---|---|
| 2.2 | Impressão digital da chave autorizada no 3067 | anotada | |
| 3.2 | Python escolhido e versão; `stdlib OK`; tempo da PBKDF2 | ≥ 3.6.0; OK; ≤ 3 s | |
| 3.3 | Driver e Instant Client; `sqlplus` | um driver; cliente presente | |
| 3.4 | GFPR 1521 alcançável; portas 18000/18001 | alcançável; livres após o passo 6 | |
| 4.1 | Scripts SQL gerados; `WHENEVER` 1; outros prefixos 0; maior identificador; `git status` | 1; 0; ≤ 30; vazio ou commit feito | |
| 4.2 | Commit do pacote; `sha256sum -c` na origem; seis SQL no pacote | o commit da janela; OK; 6 | |
| 5 | `sha256sum -c` no 3067 | OK nos três arquivos | |
| 6 | Instalação antiga parada; `crontab` antigo salvo | nada no ar; arquivo salvo | |
| 7 | `conteudo confere` em DEV e PROD | as duas | |
| 8 | `secrets.cfg` `600`, `CHANGE_ME` 0, 5 ambientes, em DEV e PROD | as duas | |
| 9 | Prefixo vazio antes; `ORA-`/`SP2-` = 0; `99` com `OK: nenhuma falha` (s3dev e s3prd) | os dois | |
| 10 | 14 utilitários; nenhum arquivo gravável por grupo/outros | 14; 0 | |
| 11 | `check_env` código 0 nos seis processos de cada raiz; `CONFIG_OK` | 12 × código 0 | |
| 12 | 1 web e 5 agentes por raiz; porta em `127.0.0.1`; `healthy_agents=5` | as duas raízes | |
| 13 | HTTP 303/200/4/403; senhas trocadas; ticket de teste `SUCCESS` | as duas raízes | |
| 14 | `crontab` com 4 keepalives e 2 `health.py` | 4 e 2 | |
