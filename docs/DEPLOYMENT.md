# SSS — Guia de Implantação e Operação (Linux/Unix)

Guia para instalar, operar e investigar falhas do SSS **lendo os logs**, por quem não participou do desenvolvimento. Vale para servidores POSIX (Linux e Unix, CR-005) sem acesso à internet.

O README.md é a especificação. Quando este guia e o README divergirem, vale o README; avise a equipe para corrigir o guia.

**Marcas de validação:**
* **[ensaiado]:** o comando foi executado a partir do pacote extraído, em 2026-10-21 (F9.1d), contra o Oracle de homologação (GFPR), em modo DEV. Nesse ensaio não houve `sudo`, helper nem usuário de execução, porque em DEV o agente roda os scripts com o próprio usuário.
* **[não ensaiado]:** sintaxe conferida, mas ainda não executado. Valide com a infraestrutura antes de usar em produção.

---

## 1. Visão geral

### 1.1 Componentes

```text
 usuários ── HTTP(S) ──> nó web (run_web.py, bin/sss-web.sh) ──────────────────┐
                                                                           ├──> Oracle (owner do esquema, tabelas tbsss_*)
 cron ──> sss-keepalive.sh ──┐                                             │
 monitoramento ──> health.py ─┼──> agente (bin/sss-scheduler.sh) ───────────┘
                             │       └── script do usuário (com a conta do agente, CR-032)
```

* **Nó web:** telas, cadastros e disparo de tickets. Não executa scripts.
* **Agente:** daemon (`scripts/run_scheduler.py`) que desdobra os agendamentos, reserva os tickets (claim), executa os scripts com a própria conta (CR-032, D7: sem `sudo` nem helper), coleta o log e mantém o heartbeat. Pode haver vários agentes; cada ticket roda em um só.
* **Keepalive** (`bin/sss-keepalive.sh`, CR-030) e **saúde** (`scripts/health.py`): chamados pelo `cron` e pelo monitoramento. Não há purge: a limpeza é manual (README §11.3, §12).

### 1.2 Contas Oracle por papel

| Papel | Conta sugerida | Usada por | Onde fica a senha |
|---|---|---|---|
| Dono do esquema | `openrisow` (exemplo) | Só o DBA, na criação do esquema (§5) | Com o DBA; nunca em arquivo do SSS |
| web | `sss_web` | Nó web | `[oracle] password` do `secrets.cfg` do web |
| agente | `sss_agente` | Agente | `[oracle] password` do `secrets.cfg` do agente |

O `health.py` usa a conta do processo do `--name` (CR-032, D8: não há papel monitor). **Com um usuário de banco só** (§4.0), essa conta é a dona do esquema e faz os papéis web e agente; a conta igual ao owner é aceita (CR-032, D11). Os privilégios de cada papel estão no README §11.1 e saem do gerador de scripts SQL (§5.2).

### 1.3 Ordem do procedimento

```text
 1. Requisitos ......................... §2     9. Scripts cadastrados ........... §9
 2. Pacote ............................. §3    10. Subida e parada .............. §10
 3. Usuários e diretórios .............. §4    11. Validação pós-subida ......... §11
 4. Banco (DBA) ........................ §5    12. Limpeza manual ............... §12
 5. Driver Oracle ...................... §6    13. Monitoração .................. §13
 6. Configuração ....................... §7    14. Logs ......................... §14
 7. (retirado no CR-032) .............. §8    15. Problemas e soluções ......... §15
                                               16 a 20. Rotações, backup, atualização, checklist, desinstalação
```

**Convenções:**
* Comandos com `sudo` ou "como root" são do administrador do servidor. Os demais rodam como o usuário de serviço `sss` (`sudo -u sss -H bash`). Sem um usuário chamado `sss`, use a conta de serviço que existir.
* **`<RAIZ>`** = `/portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service`, com `<TIPO>` = `DEV` ou `PROD` (não há HOM, CR-030). A estrutura dentro da raiz é **idêntica** nos dois (CR-028, D1): só o `<TIPO>` muda.
* **Processos e nomes (CR-028):** cada processo tem um nome, o mesmo em todo lugar: `web0001`, `web0002`... para os nós web e `agente0001`, `agente0002`... para os agentes. O nome do agente é o `agent_id`, **único em toda a instalação** (não repita um número em outro servidor).

**Estrutura de pastas (CR-028)**, igual em DEV e PROD:

```text
/portaloptrib/TESHUVA/SSS/<TIPO>/       # dono: root, 0755 (§4.1)
└── script_scheduling_service/          # a <RAIZ>

<RAIZ>/                                 # dono: sss
├── bin/  scripts/  src/  docs/         # código: trocado a cada atualização (bin/sss-update.sh, §18)
├── AGENTS.md  README.md  SHA256SUMS
├── instance/                           # PRESERVADO na atualização
│   ├── exemplos/web0001/  exemplos/agente0001/   # modelos (vêm no pacote)
│   ├── web0001/      config.ini  secrets.cfg     # do nó web
│   ├── agente0001/   config.ini  secrets.cfg     # de cada agente
│   └── agente0002/   config.ini  secrets.cfg
├── var/                                # PRESERVADO; de preferência numa partição própria (§4.3)
│   ├── web0001/      logs/
│   ├── agente0001/   logs/  work/  output/  input/  script_work/
│   ├── agente0002/   logs/  work/  output/  input/  script_work/
│   └── update/<data>/retorno/          # pacotes de retorno do sss-update.sh
└── scripts_ambiente/                   # PRESERVADO: scripts dos ambientes (script_base_dir padrão)
```

| Caminho | Conteúdo | Dono | Modo | Origem no `config.ini` |
|---|---|---|---|---|
| `<RAIZ>` | Pacote extraído (código) | `sss` | `0750` | — |
| `<RAIZ>/instance/<nome>/config.ini` | Configuração do processo (sem segredos) | `sss` | `0640` | — |
| `<RAIZ>/instance/secrets.cfg` | Segredos do servidor, um arquivo só (CR-032, D14) | `sss` | `0600` | — |
| `<RAIZ>/var/<nome>/logs` | Logs da aplicação e dos scripts | `sss` | `0750` | padrão de `[logging] log_dir` |
| `<RAIZ>/var/<agente>/work` | Trabalho do agente (trava, `.stop`, pastas dos tickets) | `sss` | `0700` | padrão de `[agent] work_dir` |
| `<RAIZ>/var/<agente>/output/<ambiente>` | Saída dos scripts (CR-012) | `sss` | `0700` (pai `0755`) | padrão de `[agent] output_dir` |
| `<RAIZ>/var/<agente>/input/<ambiente>` | Entrada dos scripts, uma subpasta permanente por script (CR-014) | `sss` | `0700` (pai `0755`) | padrão de `[agent] input_dir` |
| `<RAIZ>/var/<agente>/script_work/<ambiente>` | Pasta de trabalho dos scripts, uma por ticket (CR-019) | `sss` | `0700` (pai `0755`) | padrão de `[agent] script_work_dir` |
| `<RAIZ>/scripts_ambiente` | Scripts dos ambientes | `sss` (ou a equipe do ambiente) | `0755` | padrão de `[agent] script_base_dir` |

Com `[app] name`, todas essas pastas saem do nome do processo, sem precisar escrevê-las (CR-028, D5; README §12.1). Uma chave escrita no `config.ini` vale no lugar do padrão; escrita vazia (ex.: `output_dir =`) desliga a função. A instalação anterior ao CR-028 (`/opt/sss/app`, `/etc/sss/secrets.cfg`, `/var/lib/sss`, `/var/log/sss`, com o `config.ini` de formato único) continua aceita, com os caminhos escritos no `config.ini`.

---

## 2. Requisitos

| Item | Requisito |
|---|---|
| Sistema operacional | Linux x86_64 ou outro Unix POSIX (CR-005). Validado em Oracle Linux 6.9 e Ubuntu 24.04 |
| Python | **3.6.0 ou superior** (referência de produção: 3.6.8). Só a biblioteca padrão, mais o driver Oracle. Não use `pip install` no servidor |
| Driver Oracle | `python-oracledb` (`< 2.0` no Python 3.6; `2.x` no 3.7+) e `cx_Oracle 8.3` como contingência, **pré-instalados** pela infraestrutura (AGENTS §2.2), com o **Oracle Instant Client 19.x**. A biblioteca `cryptography` não é usada (o modo Thin fica fora de uso; `driver_mode = thick`) |
| Oracle Instant Client 19 | **Obrigatório se algum banco for 11g** (o modo Thin não conecta ao 11g: `DPY-3010`); recomendado sempre, como contingência da cadeia de driver (§6). Registrado no `ldconfig` |
| Banco | Oracle 11gR2 (11.2.0.4) ou superior, charset AL32UTF8, servidor **sem horário de verão** (UTC recomendado) e NTP em modo *slew* em todas as instâncias (README §7.1) |
| Rede | Dos nós web e agentes até o listener Oracle. O nó web escuta só em `127.0.0.1`; os usuários chegam por proxy reverso HTTPS ou túnel SSH (§10.4) |
| Relógio dos servidores | NTP ativo. O fuso vem de `SSS_TZ` no launcher (§10) |
| Ferramentas | `tar`, `sha256sum`, `curl` e o `cron` da conta (ou `systemd`, com administrador) |

---

## 3. Pacote de implantação [ensaiado]

O pacote é gerado na máquina de desenvolvimento, a partir de uma cópia **limpa** do repositório. Uma árvore de trabalho sempre tem `__pycache__` e o `secrets.cfg` local, e o `package.py` a recusa (README §12.2).

```bash
# na máquina de desenvolvimento, no commit a implantar
mkdir -p /tmp/sss-limpo && git archive HEAD | tar -x -C /tmp/sss-limpo
python3 /tmp/sss-limpo/tools/package.py --source /tmp/sss-limpo --out-dir /tmp/sss-dist
# esperado: "Pacote: .../sss-<versao>.tar.gz" e "SHA256SUMS: .../SHA256SUMS"; código 0
```

O `package.py` fica em `tools/` desde o CR-022b2 (antes, `scripts/`): é ferramenta de build e não vai no pacote. Ensaiado de novo no CR-021f3, já sem web2py: o `package.py` não grava `__pycache__` na cópia que empacota (antes, o próprio `__pycache__` recusava o pacote). Com código 1, a saída diz o que foi recusado ("Pacote recusado:" e uma linha por problema, com arquivo e linha, nunca o valor). O caso comum é um `password` ou `cookie_key` que não é `CHANGE_ME` no `instance/secrets.cfg.example`.

Leve os dois arquivos (`sss-<version>.tar.gz` e `SHA256SUMS`) ao servidor e confira. Na **primeira instalação**:

```bash
# como sss, na pasta onde estão os dois arquivos
sha256sum -c SHA256SUMS                                     # esperado: "sss-<versao>.tar.gz: OK"
mkdir -p /portaloptrib/TESHUVA/SSS/<TIPO>                    # se ainda nao existir (com administrador: §4.1)
cd /portaloptrib/TESHUVA/SSS/<TIPO>                          # a pasta de cima da <RAIZ>
tar -xzf <pasta do pacote>/sss-<versao>.tar.gz
mv sss-<versao> script_scheduling_service                    # a <RAIZ>
cd script_scheduling_service && sha256sum -c --quiet SHA256SUMS && echo "conteúdo confere"
ls                                                          # esperado: AGENTS.md README.md SHA256SUMS bin docs instance scripts src
```

Nas **atualizações** seguintes, não extraia por cima: use o `bin/sss-update.sh` (§18), que preserva `instance/`, `var/` e `scripts_ambiente/`.

O pacote só tem o `bin/` e a aplicação (o código, os templates e os estáticos ficam em `src/sss/`, CR-022b): sem web2py (CR-021f), sem `src/sss/web/controllers/dev.py`, sem o FAKE (`src/sss/persistence/fake/`) e sem testes. O servidor web é o `scripts/run_web.py` da própria aplicação, e a raiz `/` leva ao login.

---

## 4. Usuários e diretórios [não ensaiado]

### 4.0 Instalação com um usuário só (CR-028, D12; CR-030)

É o caso dos servidores sem administrador: **um usuário de banco** e **um usuário do sistema operacional** para tudo, sem root, sem `sudo` e sem `systemd`. DEV e PROD têm o mesmo comportamento (CR-032, D11: não há `sss_env`); a separação entre eles é física, pela pasta `<TIPO>` (`DEV` ou `PROD`), que também dá o ambiente mostrado na tela. Roteiro:

1. **Pacote (§3)** extraído na `<RAIZ>` com a sua conta.
2. **Pule** o usuário `sss` (§4.1; use a sua conta no lugar dele) e as units do `systemd` (§10.5). Não há usuário de execução, helper nem `sudoers` desde o CR-032.
3. **Banco (§5):** a conta única é a **dona do esquema**. Não há GRANT a aplicar (pule o `03_grants`); o `init_db.py --name agente0001` precisa de `--real-schema`, porque o esquema não é descartável (§5.3).
4. **Configuração (§7):** um `instance/<nome>/config.ini` por processo, com `[app] name` igual ao nome da pasta e `[oracle] user` = a conta única. Os segredos ficam num **único** `instance/secrets.cfg` (CR-032, D14): `[oracle] password`, `[web] cookie_key` e os `[environment:<NOME>]` dos ambientes atendidos (os bancos que os scripts usam têm usuários próprios). O `health.py` usa a conta do processo do `--name` (CR-032, D8).
5. **Pastas:** nada a fazer. Na subida, o web e o agente criam as pastas que faltarem em `var/<nome>/` e `scripts_ambiente/` (CR-032, D12), com uma linha `pasta criada` no log.
6. **Subida e permanência (§10.6):** `bin/sss-keepalive.sh` no `crontab` da sua conta, com `@reboot` e a cada 5 minutos.
7. **Monitoração (§13)** e **limpeza manual (§12, README §11.3)** pelo mesmo `crontab`.

Exemplo de `crontab -e` da conta (troque `<TIPO>`, a porta e o Python):

```text
PYTHON=/usr/bin/python3
SSS_TZ=America/Sao_Paulo
R=/portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service
@reboot      cd $R && bin/sss-keepalive.sh web0001:18000 agente0001
*/5 * * * *  cd $R && bin/sss-keepalive.sh web0001:18000 agente0001
*/5 * * * *  cd $R && $PYTHON scripts/health.py --name agente0001 > var/agente0001/logs/health.txt 2>&1
15 2 * * *   cd $R && find var/*/logs var/*/output var/*/script_work -mindepth 7 -maxdepth 7 -type d -mtime +30 -exec rm -rf {} + ; find var/*/logs var/*/output var/*/script_work -mindepth 3 -type d -empty -delete
```

* **Risco aceito:** os scripts rodam com a mesma conta do agente e podem ler o `secrets.cfg`, o `config.ini` e os logs do SSS, além de alterar o código. Quem cadastra um script tem o poder dessa conta. E a conta do banco, sendo a dona do esquema, pode alterar qualquer objeto dele.
* **Comportamento único (CR-032, D11)**, o mesmo em DEV e PROD:

| Item | Como fica |
|---|---|
| Conta Oracle | Pode ser a dona do esquema; guarde a senha como a do dono do esquema |
| Segredos | Um `secrets.cfg` por servidor (§7.2); cada processo usa só o que precisa. Ambiente atendido sem `[environment:<NOME>]` recusa a subida do agente |
| Cookie de sessão | `Secure` só quando a requisição chega por HTTPS; com acesso por HTTP, o cookie vai sem `Secure` |
| Origem | `allowed_origins` e a do próprio `Host` da requisição |
| Scripts dentro da raiz | Recusados, salvo `scripts_ambiente/` e `dev/` onde ela existe; o pacote não leva `dev/`, então não crie essa pasta na `<RAIZ>` |
| `init_db.py` | Recusa um esquema que não é descartável sem `--real-schema` (§5.3) |

* **Faixa na tela (CR-028, D12; CR-032):** a faixa "Ambiente ... — dados e execuções não produtivos", o rodapé, o `[DEV]` no título da aba e a cor do cabeçalho vêm do nome da pasta `<TIPO>` acima da raiz. Em `PROD` a faixa não aparece; o cabeçalho tem outra cor só em `DEV`. O web e o agente registram na subida `ambiente da instalação: <TIPO> (<raiz>)`.
* A tela de DEV (`/dev/...`) não existe numa instalação feita pelo pacote, que não leva o `dev.py` (§3).

### 4.1 Usuário de serviço

O SSS **recusa rodar como root** (os launchers saem com código 1 e o agente com o código 10).

```bash
# como root, em todo servidor (web e agentes)
useradd --system --home-dir /portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service/var \
        --no-create-home --shell /sbin/nologin sss                 # Debian/Ubuntu: /usr/sbin/nologin
install -d -o root -g root -m 0755 /portaloptrib/TESHUVA/SSS /portaloptrib/TESHUVA/SSS/<TIPO>
install -d -o sss -g sss -m 0750 /portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service
```

As pastas `var/<nome>/...` são criadas pelo próprio processo na subida (CR-032, D12).

### 4.2 Usuários de execução (retirados no CR-032)

Não há mais usuário de execução por ambiente (CR-032, D7): os scripts rodam com a conta do agente, sem `sudo` nem helper. Linhas antigas `exec_users`, `exec_work_dir` e `helper_path` no `config.ini` só geram aviso. Com root, limites de recurso (`nproc`, `nofile` em `/etc/security/limits.d/`) e cota de disco valem para a conta do serviço.

### 4.3 Partição dos logs (CR-008, R-25)

A pasta `<RAIZ>/var/` (onde ficam os `log_dir` de cada processo, `var/<nome>/logs`) fica de preferência num **sistema de arquivos próprio**, separado de `/`, e dimensionado para os dias de logs que você guarda até a limpeza manual (§12).

O agente para de fazer claim com menos de `[agent] log_dir_min_free_mb` livres (padrão 1.024 MB; linha `DISCO_LOG` no log, §15). O monitoramento corporativo deve alertar antes, por exemplo com 80% de uso.

### 4.4 Permissões que o SSS cria

O launcher aplica `umask 077`. O próprio SSS cria:
* pastas de log com `0750` (todos os níveis: `internal/`, `app/`, ano, mês, dia, hora e minuto);
* log da aplicação com `0640`;
* log de execução de cada ticket com `0600`.

---

## 5. Banco Oracle (DBA)

### 5.1 Pré-requisitos do banco

* **Fuso e relógio:** servidor de banco sem horário de verão e NTP em *slew* (README §7.1). O SSS usa o `SYSDATE` como relógio de todas as decisões.
* **Sessões mortas:** `SQLNET.EXPIRE_TIME = 1` no `sqlnet.ora` do servidor de banco, para derrubar sessões perdidas que seguram lock.
* **Estatísticas:** job automático de estatísticas ativo para o esquema. O plano das consultas da fila depende delas (CR-013).
* **Espaço:** dimensione os LOBs pelo §5.5.

### 5.2 Scripts SQL e contas por papel [ensaiado no GFPR: ciclo 02 → 01 → 99]

Os três scripts saem do mesmo registro de identificadores, com o owner e o prefixo do `config.ini`. Os GRANTs saem com as contas de cada papel:

```bash
# na máquina de desenvolvimento ou num servidor com o pacote
cd <RAIZ>
python3 scripts/generate_sql.py --config instance/web0001/config.ini --grants-to web=sss_web,agent=sss_agente
# gera docs/sql/01_deploy_sss_openrisow_tbsss.sql, 02_rollback_sss_<owner>_<prefixo>.sql, 99_validate_deploy_<owner>_<prefixo>.sql e 03_grants_sss_<owner>_<prefixo>.sql
```

O DBA revisa o `01` (ou a saída de `python3 scripts/init_db.py --name agente0001 --dry-run`, que imprime o DDL sem conectar) **antes** de executar. Depois:

```sql
-- como a conta dona do esquema, gravando a saída
SPOOL /tmp/sss_01_deploy.log
@docs/sql/01_deploy_sss_openrisow_tbsss.sql
SPOOL OFF
SPOOL /tmp/sss_99_validate.log
@docs/sql/99_validate_deploy_openrisow_tbsss.sql
SPOOL OFF
```

* O `01` termina com "concluída com sucesso!" mesmo que um comando falhe (`WHENEVER SQLERROR CONTINUE`). Procure `ORA-` e `SP2-` nos dois logs antes de dar a implantação por concluída.
* O `99` só lê. As duas linhas de resumo precisam dizer `OK: nenhuma falha`.
* As contas `sss_web` e `sss_agente` são criadas pelo DBA antes do `01` (com um usuário só, §4.0, nenhuma conta nova), com a política de senhas da empresa. Nenhum GRANT vai para PUBLIC.
* **Rollback total** (só em instalação nova ou com autorização): `@docs/sql/02_rollback_sss_openrisow_tbsss.sql`. Ele apaga os dados.

### 5.3 Usuários iniciais

O seed cria os usuários de homologação `admin`, `op.prod`, `op.hml` e `consulta` com a senha inicial `Sss@Homolog2026!` (PBKDF2-SHA256). **Troque essa senha no primeiro acesso** (checklist do §19). O `MERGE` do seed preserva senhas já alteradas.

### 5.4 DSN com RAC e Data Guard (CR-007, R-12; CR-008, R-17)

* **Orçamento da abertura:** `CONNECT_TIMEOUT × (RETRY_COUNT + 1) × endereços` precisa ser **menor ou igual** a `call_timeout_ms / 1000` (30 s no padrão). Acima disso, os processos avisam com WARN `CONEXAO_ACIMA_DO_PRAZO`.
* **RAC:** nome do serviço, nunca o SID, com balanceamento e failover (5 × 2 × 1 = 10 s com o SCAN):
  `(DESCRIPTION=(CONNECT_TIMEOUT=5)(RETRY_COUNT=1)(ADDRESS_LIST=(LOAD_BALANCE=on)(FAILOVER=on)(ADDRESS=(PROTOCOL=TCP)(HOST=scan.empresa.local)(PORT=1521)))(CONNECT_DATA=(SERVICE_NAME=sss_srv)))`
* **Data Guard:** serviço iniciado só no primário (`role = PRIMARY`) e os dois endereços (primário e standby) em `ADDRESS_LIST` com `FAILOVER=on`, `CONNECT_TIMEOUT=5` e `RETRY_COUNT=1` (5 × 2 × 2 = 20 s).
* `CONNECT_TIMEOUT` e `RETRY_COUNT` no descritor valem a partir do cliente 19c (Thick e cx_Oracle); no modo Thin, o SSS usa `tcp_connect_timeout`.

### 5.5 Dimensionamento dos LOBs (CR-007, R-29; CR-012)

* **Log no banco:** num banco AL32UTF8, o CLOB guarda cerca de **2 bytes por caractere**. Estimativa do segmento LOB de `tbsss_tickets`: `tickets por dia × caracteres médios do log × 2 × dias guardados até a limpeza × 1,3`. Exemplo: 2.000 × 50.000 × 2 × 180 × 1,3 ≈ 47 GB. O teto por ticket é `max_log_size_bytes` (até 64 MiB).
* **Saída dos scripts:** o zip fica no BLOB de `tbsss_ticket_output` até o ticket sair na limpeza manual: `tickets com saída por dia × zip médio × dias guardados × 1,3`. O teto por ticket é `output_max_bytes` (até 200 MiB).
* Depois da limpeza manual (§12), o espaço volta ao segmento, não ao tablespace. Para devolvê-lo, o DBA usa `ALTER TABLE ... MOVE LOB` ou redefinição online numa janela.

---

## 6. Driver Oracle (CR-002) [ensaiado]

* `[oracle] driver_mode = auto` (padrão) tenta, na ordem, **Thin → Thick → cx_Oracle**, cada um numa sondagem isolada, e usa o primeiro que conectar. A sondagem usa a conta do papel que está conectando: `[oracle] user` no web e no agente, `[monitor] user` no `health.py`.
* **Linha da combinação escolhida**, no log da aplicação de cada processo (ensaio, banco 19c):
  `INFO ... [action=INICIO] driver=oracledb modo=thin servidor=19.24.0.0.0 cliente=-`
  Com Thick ou cx_Oracle, `cliente=` mostra a versão do Instant Client (precisa ser 19). Registre essa linha no checklist (§19).
* **Conferência antes de subir:** `python3 scripts/check_env.py --name <nome>`, a partir de `W`. Ela confere os pré-requisitos (código 0 = tudo OK, 1 = falta arquivo, 2 = Python menor que 3.6.0).
* **Quando forçar:**
  * `driver_mode = thick` quando o banco é 11g. O Thin recusa com `DPY-3010` e a cadeia já pula para o Thick, mas forçar evita a sondagem a cada subida.
  * `driver_mode = cx_oracle` quando o `python-oracledb` não estiver disponível ou falhar nesse servidor.
* **Instant Client:** no Linux/Unix, ele precisa estar no `ldconfig` **antes** de o processo subir. Sem ele no `ldconfig`, defina `SSS_IC_DIR`: o launcher exporta `LD_LIBRARY_PATH` só nesse caso (README §12.2).

---

## 7. Configuração

### 7.1 `config.ini` [ensaiado]

Um `config.ini` **por processo**, em `<RAIZ>/instance/<nome>/`, a partir dos modelos do pacote (CR-028):

```bash
# como sss, na <RAIZ>; um bloco por processo do servidor
mkdir -m 0750 instance/web0001
cp instance/exemplos/web0001/config.ini.example instance/web0001/config.ini && chmod 0640 instance/web0001/config.ini
mkdir -m 0750 instance/agente0001
cp instance/exemplos/agente0001/config.ini.example instance/agente0001/config.ini && chmod 0640 instance/agente0001/config.ini
```

O papel vem do próprio arquivo (CR-028, D4): o do web tem `[web]` e não tem `[agent]`; o do agente tem `[agent]` e não tem `[web]`. Cada um só tem o que o seu papel usa:

| Processo | Chaves a preencher |
|---|---|
| Web (`instance/web0001/`) | `[app] name` (o nome da pasta); `[oracle]` (`user` = `sss_web`, `dsn`, `owner`, `table_prefix`); `[web] allowed_origins` e, atrás de proxy, `trusted_proxies` |
| Agente (`instance/agente0001/`) | `[app] name` (o nome da pasta, que é o `agent_id`); `[oracle]` (`user` = `sss_agente`...); `[agent] environments`, `max_parallel_jobs` |

As pastas (`log_dir`, `work_dir`, `output_dir`, `input_dir`, `script_work_dir` e `script_base_dir`) saem do nome e não precisam ser escritas. A tabela completa, com o padrão e a faixa de cada chave, está no README §12.1. **O próprio processo cria na subida as pastas que faltarem** (CR-032, D12): não há passo manual de pastas. `[agent] interpreters` não existe mais (CR-026): uma linha antiga só gera aviso. Dos valores de `[agent]`, o web usa só a `misfire_policy` (os demais são fixos desde o CR-032). Sem `[agent]` no config do web, vale o padrão. Se mudar a `misfire_policy` nos agentes, escreva o mesmo valor num `[agent]` do config do web, que só aceita essa chave e continua com o papel web (README §12.1). Em `instance/<nome>/`, o `[app] name` precisa ser o nome da pasta: ao copiar a pasta de um agente para criar outro, troque o `name`.

**Tempos que precisam ser idênticos em todos os agentes (README §8.9, D7):** desde o CR-032, os tempos de saúde e os ajustes do desdobro são fixos no código (`heartbeat_interval_s` 10, `fence_timeout_s` 90, `node_offline_timeout_s` 180, `kill_grace_s` 5, `misfire_tolerance_s` 300, `cron_horizon_days` 1461, `queue_aging_min` 60). O `critical_config` tem só `call_timeout_ms` e `misfire_policy` (CR-032, D16): escreva-os iguais em todos os agentes (ou deixe o padrão). Na troca desta versão, pare todos os agentes antes de subir o primeiro, porque o texto mudou. Cada agente registra na subida:

`INFO ... [action=INICIO] tempos do fencing: fence_timeout_s=90 node_offline_timeout_s=180`

Confira que a linha é igual em todos. Se um agente subir com valores diferentes dos que já estão ativos, ele é recusado (código 16, §15).

**Mais de um agente no mesmo servidor** (por exemplo, um por ambiente): um `instance/<nome>/` para cada um, com o seu `name`, e `bin/sss-scheduler.sh <nome>` para cada um. As pastas não se misturam, porque saem do nome. Para só rodar mais scripts ao mesmo tempo, basta aumentar `max_parallel_jobs` de um agente.

### 7.2 `secrets.cfg` [ensaiado]

Um arquivo **único por servidor**, em `<RAIZ>/instance/secrets.cfg` (CR-032, D14), lido por todos os processos; cada um usa só o que precisa. Dono a conta do SSS, modo `0600`. Nunca versione o arquivo real.

| Seção | Quem usa |
|---|---|
| `[oracle] password` | todos (a senha da conta do `[oracle] user`) |
| `[web] cookie_key` | o web (igual em todos os nós web) |
| `[environment:<NOME>]` com `user` e `password` | os agentes, um bloco por ambiente atendido (bancos dos scripts) |

```bash
# na <RAIZ>
cp instance/exemplos/secrets.cfg.example instance/secrets.cfg && chmod 0600 instance/secrets.cfg
vi instance/secrets.cfg
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # um cookie_key novo, para o [web]
```

Um `secrets.cfg` antigo dentro de `instance/<nome>/` ainda é lido, com um aviso no log para movê-lo para `instance/secrets.cfg`.

---

## 8. Pastas dos processos (sem helper nem `sudoers` desde o CR-032)

O web e o agente criam na subida as pastas que faltarem (CR-032, D12): `var/<nome>/logs` (`0750`), `var/<nome>/work` (`0700`), `output`, `input`, `script_work` e `scripts_ambiente` (`0755`). Uma pasta existente que não possa ser usada (arquivo no lugar, sem escrita, pasta do sistema) recusa a subida (código 13, §15). Não há helper de execução, `sudoers` nem usuário de execução (CR-032, D7): os scripts rodam com a conta do agente. Numa instalação anterior, depois de atualizar, apague `/etc/sudoers.d/sss`, a pasta `sss-root/` ao lado da `<RAIZ>` e `var/exec/` (com root), e as linhas `exec_users`, `exec_work_dir` e `helper_path` dos `config.ini`.

---

## 9. Scripts cadastrados (CR-005, CR-011, CR-023)

* O caminho cadastrado (`path_file`) é **absoluto** ou **relativo à pasta base** do agente (CR-023), em qualquer pasta fora das pastas do sistema (`/bin`, `/sbin`, `/usr`, `/lib*`, `/etc`, `/boot`, `/proc`, `/sys`, `/dev`, `/root`), fora das pastas do SSS (`log_dir`, `work_dir`, `output_dir`, `input_dir` e `script_work_dir`) e fora da pasta da aplicação (a `<RAIZ>`, cujo código é trocado a cada atualização), **exceto** `<RAIZ>/scripts_ambiente/`, que a atualização preserva (CR-028, D3).
* **Pasta base (CR-023, CR-028):** `[agent] script_base_dir`, por padrão `<RAIZ>/scripts_ambiente/`. O agente junta o caminho relativo cadastrado (ex.: `faturamento/carga.py`) a ela e confere o resultado como um caminho absoluto; o arquivo real pode ficar fora da pasta base (link). A pasta pode ser diferente em cada servidor, mas **todo agente de um ambiente que tem script com caminho relativo precisa dela**: o ticket vai para qualquer agente do ambiente, e o agente sem pasta base termina o ticket em `PRECHECK_FAILED` (`NO_BASE_DIR`). Na subida, o log mostra a pasta base (INFO) ou avisa que ela não existe (WARNING); o painel de agentes mostra a de cada um. Os 14 scripts de demonstração do seed são cadastrados como `utilitarios/<arquivo>`.
* **Pasta de entrada (CR-014):** com `[agent] input_dir`, cada script recebe `SSS_INPUT_DIR` = `input_dir/<ambiente>/<nome do script em minúsculo, sem acento nem espaço>/` (ex.: "Carga Diária" em `PRODUCAO`, no `agente0001` → `<RAIZ>/var/agente0001/input/producao/carga_diaria/`). A pasta é criada na primeira execução e **nunca** é limpa pelo SSS: quem deposita os arquivos e o próprio script cuidam do conteúdo. Para depositar arquivos de fora, use a conta do agente (ou a tela de Entrada, CR-020).
* **Pasta de trabalho (CR-019):** com `[agent] script_work_dir`, cada ticket recebe `SSS_WORK_DIR` = `script_work_dir/<ambiente>/<script>/AAAA/MM/DD/HH/MI/ticket_<id>/`, criada antes da execução e mantida depois dela, para consulta no servidor do agente. O `HOME` e a pasta corrente do script continuam na pasta descartável `work_dir/ticket_<id>/exec`.
* Pode ser um link simbólico. O arquivo **real** precisa existir no servidor do agente, ser arquivo regular, ser legível pela conta do agente e **não** ter escrita de grupo nem de outros (`chmod go-w`).
* O conteúdo e a versão do script são controlados pelo ambiente: o SSS não confere hash nem dono (CR-011). Quem grava na pasta do script muda o que vai rodar.
* O nó web confere o formato do caminho e, no caminho absoluto, as pastas do sistema e a da aplicação (o relativo só pelo formato). A conferência do arquivo é feita pelo agente, antes de cada execução; uma recusa aparece como `PRECHECK_FAILED` (§15).
* **Interpretador (CR-025, CR-026, CR-027):** o cadastro guarda só o nome (`python`, `python3`, `sh` ou `bash`). Na execução vale, nesta ordem (CR-027): o interpretador digitado no disparo (caminho absoluto ou só o nome, ex.: `python3.13`), se existir no servidor; o `#!` da primeira linha do script, se o executável existir; o nome do cadastro, com `python` e `python3` servindo um ao outro. Quem não existe é pulado, com uma linha `[SSS]` no log do ticket. Os nomes são procurados no `PATH` herdado pelo **processo do agente**: o da unit do systemd (o padrão do systemd, ou `Environment=PATH=...` na unit) ou o do shell que rodou o `bin/sss-scheduler.sh`, que não o altera. **Confira esse `PATH` em cada servidor:** ele precisa achar `python3`, `bash` e os demais que os scripts usam. O agente atende qualquer interpretador; num servidor sem nenhum interpretador possível (o digitado, o do `#!` e o do cadastro, com a troca `python` ↔ `python3`), o ticket termina em `PRECHECK_FAILED` (`INTERPRETER_NOT_FOUND`). O agente só confere, como o usuário do agente, se o executável existe e é executável (não confere se ele está numa pasta do SSS: risco aceito, README §14), e o executa sem resolver links (o Python de um virtualenv funciona). `#!/usr/bin/env python3` funciona: o `env` procura o `python3` no `PATH` fixo do filho (`/usr/bin:/bin`, README §8.6), não no do agente, e o interpretador registrado como usado é `/usr/bin/env`. Um interpretador digitado que não existe é pulado (CR-027): vale o `#!` ou o cadastro, e o log do ticket registra a tentativa. **Risco aceito pelo responsável pelo produto:** quem pode disparar escolhe o programa que roda o script (o digitado vence o `#!`, CR-027), e, sem digitado, quem edita a primeira linha troca o interpretador sem passar pelo cadastro. O digitado fica no snapshot, em `tbsss_tickets.interpreter_path` e na auditoria do disparo; o usado, em `tbsss_tickets.interpreter_used` e na linha `[SSS] interpretador usado` do log (README §8.5).

---

## 10. Subida e parada

Os launchers recusam root, aplicam `umask 077`, exportam `TZ` (de `SSS_TZ`), `LANG` e `LC_ALL` (de `SSS_LOCALE`, padrão `C.UTF-8`) e `LD_LIBRARY_PATH` só sem o Instant Client no `ldconfig` (de `SSS_IC_DIR`). Também trocam para a raiz do repositório e fazem `exec` do processo Python. O Python vem de `PYTHON` (padrão `python3`).

### 10.1 Nó web [ensaiado em DEV]

```bash
# como sss
cd <RAIZ>
export PYTHON=/usr/bin/python3 SSS_TZ=America/Sao_Paulo
bin/sss-web.sh "$PYTHON" web0001 --check                      # CONFIG_OK ambiente=<TIPO>; nao abre a porta
bin/sss-web.sh "$PYTHON" web0001 --host 127.0.0.1 --port 8000  # instance/web0001/config.ini (CR-028)
```

* O servidor é o próprio do SSS (`scripts/run_web.py`, CR-021e), sem web2py: até 16 requisições ao mesmo tempo e 30 s de espera por conexão (fixos no código desde o CR-032). O `sss-web.sh` só inicia o `run_web.py`; `web2py.py` e `anyserver.py` são recusados (código 2).
* `--host 127.0.0.1`: só local, atrás do proxy reverso ou do túnel (§10.4). **Nunca** use `0.0.0.0`.
* Não cria arquivos na raiz (`httpserver.log`, `httpserver.pid`, `parameters_<porta>.py`, `cron.master` e afins eram do web2py). Requisições, erros e a subida vão para o log da aplicação (`sss_web_<PID>.log`, §14.1); a saída padrão só recebe o que acontecer antes de o log abrir.
* Saída: 2 com configuração ou segredos inválidos (o motivo vai para o log), 3 com a porta em uso ou sem permissão.
* Para parar: `SIGTERM` ou `SIGINT` (Ctrl+C) ao processo Python. O servidor para de aceitar conexões, espera as requisições em andamento por até 30 s e sai com código 0.

### 10.2 Agente [ensaiado em DEV]

```bash
# como sss
cd <RAIZ>
export PYTHON=/usr/bin/python3 SSS_TZ=America/Sao_Paulo
bin/sss-scheduler.sh agente0001            # instance/agente0001/config.ini (CR-028); ou --config <arquivo>
```

* O launcher aceita o nome do processo ou `--config <arquivo>`. Sem nada, o `run_scheduler.py` sai com código 2 e lista os processos de `instance/` (CR-029: não há config padrão); qualquer outro argumento também sai com código 2.
* Subida bem-sucedida, no log da aplicação (`var/<nome>/logs/internal/app/AAAA/MM/DD/HH/MI/sss_scheduler_<PID>.log`):
  ```text
  INFO ... [action=INICIO] tempos do fencing: fence_timeout_s=90 node_offline_timeout_s=180
  INFO ... [action=INICIO] driver=oracledb modo=thin servidor=19.24.0.0.0 cliente=-
  INFO ... [action=INICIO] agente inicializado (versao 1.0.0-dev, 0 grupo(s) em encerramento, 0 pasta(s) preservada(s))
  ```
* Falha na subida: uma linha `CRITICAL ... [action=INICIO] Subida abortada: <reason>` e um código de saída de 10 a 19 (§15.1).
* A primeira conexão registra `INFO ... [action=CONEXAO] Conectando ao Oracle (papel=agente)...` e `Conexao estabelecida (papel=agente)`. `WARNING ... [action=RECONEXAO] Tentando reconexao` só aparece depois de uma queda (§15.3).

### 10.3 Parada controlada [ensaiado]

* **Por sinal:** `SIGTERM` para o agente. Desde o CR-032 a parada é sempre `TERMINATE`, com 30 s de espera: o agente encerra os scripts em andamento e finaliza os tickets (`SHUTDOWN`). Antes de parar para uma atualização, confira na tela se não há script longo rodando.
* **Sem sinal:** `bin/sss-stop.sh <nome>` (ou `--config <config.ini>`) cria `work_dir/sss-<agent_id>.stop`:
  ```text
  parada solicitada: <RAIZ>/var/agente0001/work/sss-agente0001.stop
  ```
  O agente para na próxima iteração (no ensaio, em menos de 2 s; `WARNING ... [action=PARADA] encerramento TERMINATE: 0 execucao(oes) local(is)`) e remove o arquivo. O `sss-stop.sh` sai com código 2 se o `config.ini` for inválido.

### 10.4 Acesso dos usuários

* **Proxy reverso HTTPS** [não ensaiado, opcional]: com administrador, o nó web pode ficar atrás de um proxy (nginx, Apache ou o balanceador da empresa) que termina o TLS e repassa para `http://127.0.0.1:8000`. Inclua a URL pública em `[web] allowed_origins` e o endereço do proxy em `[web] trusted_proxies`. Por HTTPS, o cookie de sessão sai `Secure`; por HTTP, sem `Secure` (CR-032, D11). Sem proxy, os usuários acessam por HTTP a porta do `run_web.py` ou por túnel. **Tamanho do corpo (CR-020d):** o limite de corpo do proxy (por exemplo, `client_max_body_size` do nginx ou `LimitRequestBody` do Apache) precisa ser pelo menos `[web] input_upload_max_bytes` mais 64 KiB, senão o envio da tela de Entrada para no proxy com um erro dele, antes de chegar ao SSS.
* **Túnel SSH** (homologação e suporte): `ssh -N -L 8000:127.0.0.1:8000 <usuário>@<servidor>` e, no navegador, `http://localhost:8000/`. Inclua `http://localhost:8000` em `allowed_origins`.

### 10.5 Units do `systemd` (exemplo) [não ensaiado]

Apresentadas como **exemplo a validar** com a infraestrutura.

Uma unit por **modelo** (`@`), instanciada com o nome do processo: `sss-web@web0001`, `sss-agente@agente0001`, `sss-agente@agente0002`. Troque `<TIPO>` pelo do servidor.

`/etc/systemd/system/sss-web@.service`:

```ini
[Unit]
Description=SSS - no web %i
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=sss
Group=sss
WorkingDirectory=/portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service
Environment=PYTHON=/usr/bin/python3
Environment=SSS_TZ=America/Sao_Paulo
ExecStart=/portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service/bin/sss-web.sh /usr/bin/python3 %i --host 127.0.0.1 --port 8000
KillMode=mixed
# maior que [web] socket_timeout_s: o servidor espera as requisicoes em andamento (§10.1)
TimeoutStopSec=40
Restart=on-failure
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service/var
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/sss-agente@.service`:

```ini
[Unit]
Description=SSS - agente %i
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=sss
Group=sss
WorkingDirectory=/portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service
Environment=PYTHON=/usr/bin/python3
Environment=SSS_TZ=America/Sao_Paulo
# PATH em que o agente procura os interpretadores dos scripts (README §8.5)
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=/portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service/bin/sss-scheduler.sh %i
KillMode=mixed
# maior que shutdown_grace_s + kill_grace_s (30 + 5 no padrao), com folga para finalizar no banco
TimeoutStopSec=60
Restart=on-failure
RestartSec=30
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service/var
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
```

* `TimeoutStopSec` do web precisa ser maior que `[web] socket_timeout_s`; se mudar o timeout, ajuste os dois.
* `KillMode=mixed` manda o `SIGTERM` só ao processo principal e, se o prazo acabar, o `SIGKILL` a todo o grupo. O agente encerra os próprios scripts antes disso.
* `ReadWritePaths` cobre `var/` inteira (logs, trabalho, saída e entrada). Se um script grava em `scripts_ambiente/` ou em outra pasta, inclua-a.
* Dois nós web no mesmo servidor precisam de portas diferentes: crie uma cópia da unit com outra `--port`.
* Ative com `systemctl daemon-reload && systemctl enable --now sss-web@web0001 sss-agente@agente0001`.


### 10.6 Sem root: `sss-keepalive.sh` no cron da conta (CR-030) [ensaiado nos testes]

Sem `systemd` (§4.0), o `bin/sss-keepalive.sh` mantém os processos no ar pelo cron da conta que roda o SSS:

```bash
# na <RAIZ>; o web precisa da porta (<nome>:<porta>), o agente so do nome
PYTHON=/usr/bin/python3 SSS_TZ=America/Sao_Paulo bin/sss-keepalive.sh web0001:18000 agente0001
bin/sss-keepalive.sh --pause agente0001     # antes de parar de proposito: o keepalive nao sobe mais
bin/sss-stop.sh agente0001                  # para o agente
# para o web: SIGTERM no PID do python dele ([p] evita achar o proprio grep)
kill -TERM $(ps -eo pid,args | grep '[p]ython3 scripts/run_web.py --name web0001' | awk '{print $1}')
bin/sss-keepalive.sh --resume agente0001    # volta a subir na proxima passada
```

* Para cada nome, confere se há um `python` rodando `scripts/run_web.py` ou `scripts/run_scheduler.py` com `--name <nome>` a partir da `<RAIZ>`. Se não houver, sobe pelo launcher, em segundo plano (`nohup`), e grava em `var/<nome>/logs/keepalive.log` uma linha por subida, recusa ou falha. A saída do processo vai para `var/<nome>/logs/<nome>.out`.
* O papel vem do `config.ini` (`[web]` sem `[agent]`: web). O web atende só em `127.0.0.1`, na porta informada; os usuários chegam pelo proxy.
* As linhas do `crontab` estão no §4.0 (`@reboot` e a cada 5 minutos). Recusa root (código 1) e uso inválido (2); sai com 3 se algum processo não subiu (veja o `.out`).
* Na atualização (§18.1), pause os processos antes de parar e retome depois de subir.
---

## 11. Validação pós-subida [ensaiado]

```bash
# no próprio servidor do web
curl -s -o /dev/null -w "raiz: HTTP %{http_code} -> %{redirect_url}\n" http://127.0.0.1:8000/
# esperado: raiz: HTTP 303 -> http://127.0.0.1:8000/script_scheduling_service/default/login
curl -s -o /dev/null -w "login: HTTP %{http_code}\n" http://127.0.0.1:8000/script_scheduling_service/default/login
# esperado: login: HTTP 200
curl -s -D - -o /dev/null http://127.0.0.1:8000/script_scheduling_service/default/login | grep -icE "content-security|x-frame|x-content|referrer"
# esperado: 4
curl -s -o /dev/null -w "origem estranha: HTTP %{http_code}\n" -X POST -H "Origin: http://evil.example" -d "x=1" http://127.0.0.1:8000/script_scheduling_service/default/login
# esperado: origem estranha: HTTP 403
curl -s -o /dev/null -w "admin: HTTP %{http_code}\n" http://127.0.0.1:8000/admin/default/index
# esperado: admin: HTTP 404
```

Depois:
1. Entre com o `admin` e troque a senha inicial (§5.3).
2. Em **Agentes**, confira que cada agente aparece como OK, com a plataforma e os interpretadores esperados.
3. Dispare um script simples num ambiente de teste. O ticket deve terminar em `SUCCESS`, e o log do agente mostra:
   ```text
   INFO ... [ticket=1000929] [action=SPAWN] script iniciado (pid 151505)
   INFO ... [ticket=1000929] [action=FINALIZAR] ticket finalizado: SUCCESS/EXIT_OK rc=0
   ```
4. Rode o `health.py` (§13). O esperado é o código 0.

---

## 12. Limpeza manual (README §11.3; CR-030)

O SSS não apaga nada sozinho: não há `purge.py` nem retenção automática. O README §11.3 traz o procedimento completo:

* **Banco:** o SQL comentado, em lotes, para tickets terminais, auditoria e envios da tela de Entrada. Roda o DBA, ou a conta do SSS quando ela é a dona do esquema (§4.0).
* **Arquivos:** os `find` para as pastas de minuto de `var/<nome>/logs`, `output` e `script_work`, primeiro só listando e depois apagando, e para os `.out` dos processos e os pacotes de retorno do `sss-update.sh`.
* **Pelo cron** da conta que roda o SSS, como no exemplo do §4.0. Comece listando (`-print`) e só depois troque por `-exec rm -rf {} +`.

---

## 13. Monitoração (`health.py`; README §13)

```bash
# como a conta do SSS (a dona do instance/secrets.cfg); usa a conta do processo do --name (CR-032, D8)
cd <RAIZ>
python3 scripts/health.py --name agente0001      # [ensaiado]
```

Saída do ensaio (um agente saudável e outros ambientes sem agente):

```text
SSS CRITICAL - 6 problemas | healthy_agents=1 overdue_queue=0;500;5000 max_wait_min=0;30;120
CRITICAL: ambiente CLONE1 ativo sem nenhum agente saudavel
...
```

* **Códigos (padrão Nagios):** 0 OK, 1 WARNING, 2 CRITICAL e 3 UNKNOWN (configuração, segredos, conexão ou erro de banco). A primeira linha traz os dados de desempenho; depois vem uma linha por problema, os críticos primeiro.
* **Limites:** `--no-pid-min 2`, `--queue-warn 500`, `--queue-crit 5000`, `--wait-warn-min 30` e `--wait-crit-min 120`.
* **Agendamento:** a cada 5 minutos no monitoramento corporativo, com alerta no código 2. Exemplo de NRPE [não ensaiado], com o `health.py` rodando como `sss` por uma regra de `sudo` só para ele:
  ```text
  # /etc/sudoers.d/sss-monitor
  nagios ALL=(sss) NOPASSWD: /usr/bin/python3 /portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service/scripts/health.py --name agente0001
  # nrpe.cfg
  command[check_sss]=/usr/bin/sudo -n -u sss /usr/bin/python3 /portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service/scripts/health.py --name agente0001
  ```
  **Sem root nem `sudo` (§4.0):** rode o `health.py` pelo cron da própria conta e grave a saída num arquivo (`var/<nome>/logs/health.txt`, exemplo no §4.0); o código de saída e a primeira linha dizem o estado.
  Num servidor de monitoração separado, use um `config.ini` próprio com `--config` (mesmos `call_timeout_ms` e `misfire_policy`, para a checagem de configuração divergente) e o `secrets.cfg` com a senha da conta dele.

**O que fazer em cada alerta:**

| Linha | Ação |
|---|---|
| `versao do esquema N, esperada M` | O banco e o pacote estão em versões diferentes: aplique a migração ou volte o pacote (§18) |
| `agente X ATIVO sem heartbeat ha N s` | O agente caiu ou perdeu o banco: veja o log dele (§14) e o §15.3. Depois de `node_offline_timeout_s`, outro agente finaliza os tickets dele como `NODE_OFFLINE` |
| `agente X em risco` | Heartbeat atrasado além do fence: o agente já deve ter se isolado (`FENCED`) |
| `ambiente X ativo sem nenhum agente saudavel` | Nenhum agente saudável atende o ambiente: suba um agente com o ambiente em `environments`, ou desative o ambiente |
| `fila sem atendente: N tickets de AMB/INTERP` | Nenhum agente saudável atende o ambiente (CR-026: o interpretador não conta mais; INTERP é o do cadastro): suba um agente para o ambiente ou confira os agentes em risco |
| `fila vencida: N tickets PENDING, espera maxima M min` | Agentes sem vaga: veja `max_parallel_jobs` e o teto por script, e os scripts presos em `RUNNING` |
| `ticket N RUNNING sem PID` | O agente reservou e não iniciou: veja o log do agente para esse ticket |
| `agente X com configuracao divergente` | Tempos diferentes do `config.ini` de referência: corrija e reinicie o agente |

---

## 14. Logs (CR-005, CR-009; README §8.4 e §13)

### 14.1 Onde ficam

| Log | Caminho | Modo |
|---|---|---|
| Aplicação (web, agente, `init_db`) | `log_dir/internal/app/AAAA/MM/DD/HH/MI/<nome>_<PID>.log`, com `<nome>` = `sss_web`, `sss_scheduler` ou `init_db` | `0640` |
| Execução de cada ticket | `log_dir/<ambiente>/<script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log` (ambiente e script em minúsculo, sem acento) | `0600` |
| Saída padrão do nó web | a escolhida por quem sobe (`journald` no `systemd`, `var/web0001/logs/server.out` no `start_local.sh`) | — |

Com o config por processo (CR-028), o `log_dir` é `<RAIZ>/var/<nome>/logs`: os logs do web ficam em `var/web0001/logs`, e os de cada agente (inclusive os dos tickets) em `var/agente0001/logs`.

* O arquivo nasce na pasta do minuto em que o processo sobe e troca por tamanho (`app_log_max_bytes`) para a pasta do minuto atual. Com o mesmo nome no mesmo minuto, ganha o sufixo `_<n>`.
* **Sem retenção automática (CR-030):** nenhum processo apaga log. A limpeza é manual (§12, README §11.3).
* Formato: `data-hora-ISO NÍVEL [pid=…] [agent=…] [ticket=…] [action=…] mensagem`. Os segredos saem como `****`.

### 14.2 Achar o log certo

```bash
# log da aplicação mais recente de um processo
# na <RAIZ>; L = a pasta de logs do processo
L=var/agente0001/logs
find $L/internal/app -name 'sss_scheduler_*.log' -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-
# todas as linhas de um ticket no log do agente
grep -h "\[ticket=1000929\]" $(find $L/internal/app -name 'sss_scheduler_*.log')
# o log de execução do ticket (procure em var/*/logs se não souber o agente)
find $L -path $L/internal -prune -o -name 'ticket_1000929_*' -print
# falhas de subida
grep -h "Subida abortada" $(find var/*/logs/internal/app -name '*.log')
```

### 14.3 Linhas `[SSS]` no log do ticket

Toda finalização sem execução (pré-validação, falha ao iniciar, cancelamento antes do início) grava no log do ticket uma linha `[SSS] <evento>: <código> (agente <id>)`, visível na tela do ticket. Exemplo: `[SSS] pre-validacao recusada: GROUP_OTHER_WRITABLE (agente srv-linux-prod-01)`.

### 14.4 Saída padrão do nó web

Desde o CR-021e o servidor web não grava `httpserver.log`: requisições e erros vão para o log da aplicação, que troca de arquivo por tamanho (§14.1) e é limpo à mão (§12). A saída padrão só recebe o que acontecer antes de o log abrir (ex.: Python sem o pacote da aplicação) e fica pequena. Se a subida não for pelo `systemd`, redirecione-a para um arquivo (como o `start_local.sh` faz com `logs/server.out`). Um `httpserver.log` que tenha sobrado da versão com web2py pode ser apagado.

---

## 15. Problemas e soluções

Procure a linha indicada no log da aplicação do processo (§14.2). As mensagens são as do código.

### 15.1 Subida do agente (códigos de saída; README §8.12)

| Código | Linha no log (`CRITICAL ... [action=INICIO] Subida abortada: …`) | Causa provável | Ação |
|---|---|---|---|
| 1 (launcher) | `Erro: execucao como root nao e permitida.` (stderr) | Executado como root | Suba como `sss` (`sudo -u sss -H bash`) |
| 10 | `o agente nao pode rodar como root (README §8.12 passo 1)` | Idem, sem o launcher | Idem |
| 11 | `configuracao invalida: Arquivo de configuracao nao encontrado: <caminho>` | `config.ini` ausente ou `--config` errado | §7.1 |
| 11 | `configuracao invalida: [secao] chave: <motivo>` | Chave ausente, desconhecida ou fora da faixa | Compare com o modelo de `instance/exemplos/`; uma chave removida pede "apague a linha" |
| 11 | `child_locale <x> nao consta em locale -a (CR-007, R-17)` | Locale do filho não instalado | Instale o locale `C.UTF-8` (fixo desde o CR-032) |
| 12 | `secrets.cfg invalido: <reason>` (ex.: `Arquivo de segredos possui permissoes inseguras (mode 644, ...)`, `... deve pertencer ao usuario corrente`, `Secao [web] nao pertence ao papel 'agente'`) | Modo, dono ou seções do `secrets.cfg` | `chmod 0600`, `chown sss`, e só as seções do papel (§7.2) |
| 13 | `work_dir <pasta> recusado: <motivo>` (ou `output_dir`, `input_dir`, `script_work_dir`) | A pasta existe mas não pode ser usada (arquivo no lugar, sem escrita, pasta do sistema); a que falta é criada na subida (CR-032, D12) | Corrija ou apague o que está no caminho e suba de novo |
| 13 | `<nome> <caminho> recusado: <código>` (`log_dir`, `work_dir`...), `output_dir ... recusado`, `input_dir ... recusado` e `script_work_dir ... recusado` | Pasta sem escrita ou nas pastas do sistema | §4 e §8 |
| 14 | `Outra instancia do agente ja esta em execucao (<work_dir>/sss-<agent_id>.lock)` | Outro agente com o mesmo `work_dir` e `agent_id` | Pare o outro, ou use `config.ini` próprio (§7.1) |
| 15 | `sem conexao com o Oracle` ou `banco: <erro>` (ex.: `Versao do esquema incompativel: esperada N, encontrada M`) | Banco inacessível, driver (§15.2) ou versão do esquema | §15.2, §15.3 ou a migração (§18) |
| 16 | `agent_id duplicado: ...` | Outro agente ativo com o mesmo `agent_id` | `agent_id` único por agente |
| 16 | `config_criticos diverge do agente X: local=... remoto=...` e `configuracao critica diferente da dos outros agentes (CR-007, R-23)` | Tempos diferentes entre agentes | §7.1: copie do arquivo de referência |
| 17 | `ambientes atendidos inexistentes: X` | Nome em `environments` não cadastrado | Corrija o nome ou cadastre o ambiente. Ambiente inativo só gera `WARNING ambiente atendido X inativo: ignorado ate ser reativado` |
| 18 | `startup check: <erro>` | Falha ao conferir o que ficou da execução anterior | Veja as linhas `TALVEZ_INICIADO`, `ORPHAN_PROCESS` e `pasta do ticket nao removida` logo antes |
| 19 | `o processo tem N threads antes do primeiro spawn (...)` | Algo criou uma thread antes do primeiro script | Suba só pelo `bin/sss-scheduler.sh` (Python puro), nunca de dentro de outro processo |
| 20 | `REGISTRO_PERDIDO: <motivo>; encerramento TERMINATE` (com o agente já no ar) | A linha do agente em `tbsss_agents` sumiu ou mudou de dono | Veja se alguém apagou a linha ou subiu outro agente com o mesmo `agent_id`; reinicie |

### 15.2 Cadeia de driver Oracle (`[action=SELECAO_DRIVER]`)

| Linha | Causa provável | Ação |
|---|---|---|
| `Sondagem do candidato Oracle 'thin' falhou: codigo=DPY-3010 categoria=INCOMPATIBLE` | Banco 11g (o Thin não conecta) | Normal se o Thick conectar em seguida; para evitar a tentativa, `driver_mode = thick` |
| `Sondagem do candidato Oracle 'thick' falhou: codigo=DPI-1047 categoria=LIBRARY` | Instant Client ausente ou fora do `ldconfig` | Instale o IC 19 e registre no `ldconfig`, ou defina `SSS_IC_DIR` (§6) |
| `Falha fatal de autenticacao Oracle com candidato 'thin' (codigo=ORA-01017). Cadeia interrompida para proteger a conta.` | Usuário ou senha errados, ou conta bloqueada (`ORA-28000`) | Corrija a senha do papel no `secrets.cfg`. A cadeia para de propósito, para não bloquear a conta |
| `Falha fatal: todos os candidatos de driver Oracle falharam (thin (NETWORK: DPY-6005); thick (NETWORK: ORA-12541); cx_oracle (NETWORK: ORA-12541))` (capturada no ensaio, com o túnel do banco fora) | Listener inacessível: rede, firewall, DSN ou banco parado | `tnsping`/`nc -z <host> 1521` a partir do servidor; confira o `dsn` |
| `Falha de configuracao: python-oracledb 2.x nao e compativel com Python 3.6 ...` | Driver errado para o Python | Instale `python-oracledb < 2.0` ou use `driver_mode = cx_oracle` |
| `Falha de configuracao: Oracle Instant Client versao X invalida. Exigido major 19 ...` | Outro Instant Client no `ldconfig` | Deixe só o 19 no caminho de bibliotecas |
| `Falha de configuracao: driver_mode '<x>' invalido ...` | Valor errado no `config.ini` | `auto`, `thin`, `thick` ou `cx_oracle` |

### 15.3 Banco durante a operação

| Linha | Causa provável | Ação |
|---|---|---|
| `ciclo <nome> falhou: ... ORA-03113 ...` / `DPY-4011` / `ORA-12541`, seguido de `WARNING ... [action=RECONEXAO] Tentando reconexao com o Oracle (papel=agente)...` e, se falhar, `Falha na tentativa de reconexao: ...` | Queda de rede ou do banco | O agente reconecta sozinho (`Reconexao bem-sucedida`). Se demorar mais que `fence_timeout_s`, ele se isola (`FENCED`) |
| `CRITICAL ... FENCED: sem heartbeat confirmado ha N s (fence_timeout_s 90); M execucao(oes) encerrada(s), claims e desdobro suspensos ate o banco voltar` | O agente ficou sem confirmar o heartbeat por mais que `fence_timeout_s` | Restabeleça a conexão. Na volta: `FENCED encerrado: heartbeat confirmado; ...`. Os tickets que ele tinha terminam `FAILED`/`FENCED` |
| `SALTO_RELOGIO: o SYSDATE andou N s diferente do relogio monotonico; NODE_OFFLINE ...` | Ajuste brusco de relógio no banco ou no servidor | Use NTP em *slew*; a detecção de nó offline fica suspensa por um ciclo |
| `relogio local diverge do SYSDATE em N s (README §7.1)` | Servidor sem NTP | Ative o NTP |
| `CONEXAO_ACIMA_DO_PRAZO: orcamento da conexao Ns excede call_timeout_s Ms (CR-008, R-17)` | `CONNECT_TIMEOUT × tentativas × endereços` maior que o `call_timeout` | Ajuste o descritor (§5.4) |
| `WARNING ... [action=CLAIM] claim do ticket N pulado: linha do script S travada por outra sessao (ORA-30006, FOR UPDATE WAIT 5)` | Outra sessão segura a linha do script em `tbsss_scripts` por mais de 5 s (edição presa ou sessão morta) | Ocasional é normal: o ticket volta no próximo ciclo. Persistente: o DBA procura a sessão em `v$lock`/`v$session` e a encerra; `SQLNET.EXPIRE_TIME` (§5.1) evita sessões mortas |

### 15.4 Tickets (status e motivo na tela e no log)

| Status/motivo | Linha no log do agente (e `[SSS]` no log do ticket) | Causa provável | Ação |
|---|---|---|---|
| `PENDING` que nunca sai | Nenhuma linha. No `health.py` e na tela de agentes: `fila sem atendente: N tickets de AMB/INTERP` | Nenhum agente saudável atende o ambiente do ticket (CR-026: o interpretador não conta) | Suba um agente para o ambiente ou recupere o agente em risco |
| `PENDING` que demora | `DISCO_LOG: N MB livres em log_dir (minimo M): sem claim` ou `DISCO_SAIDA: ...` | Disco quase cheio | Libere espaço (limpeza manual, §12) ou aumente a partição |
| `FAILED` / `PRECHECK_FAILED` | `pre-validacao recusada: <código>` e `[SSS] pre-validacao recusada: <código> (agente X)` | Ver os códigos abaixo | Ver abaixo |
| ↳ `NOT_FOUND`, `NO_ACCESS`, `NOT_A_FILE` | | O arquivo real não existe, não é legível ou não é arquivo, no servidor do agente | Corrija o arquivo no agente (§9) |
| ↳ `GROUP_OTHER_WRITABLE` | | Arquivo real com escrita de grupo ou outros | `chmod go-w <arquivo>` |
| ↳ `SYSTEM_DIR`, `SSS_DIR`, `APP_DIR` | | Script nas pastas do sistema, nas do SSS (inclusive `output_dir`, `input_dir` e `script_work_dir`, CR-014 e CR-019) ou na pasta da aplicação (CR-023) | Mova o script e corrija o cadastro |
| ↳ `NO_BASE_DIR` | | Script com caminho relativo e **este** agente sem `[agent] script_base_dir` (CR-023) | Configure a pasta base no agente (§9) e suba de novo |
| ↳ `RELATIVE_PATH` | | Agente de versão anterior ao CR-023 diante de script com caminho relativo | Atualize todos os agentes do ambiente (§18) |
| ↳ `INTERPRETER_NOT_FOUND` | | Nenhum interpretador existe e é executável neste servidor (CR-027): nem o digitado no disparo, nem o do `#!`, nem o nome do cadastro (`python` e `python3` são tentados um pelo outro). Os nomes são procurados no `PATH` do agente; o log do ticket mostra uma linha `[SSS]` por tentativa pulada, antes da linha de recusa | Instale o interpretador, ajuste o `PATH` do serviço, corrija o `#!` ou dispare de novo com outro interpretador |
| ↳ `INTERPRETER_NOT_ALLOWED` | | O snapshot traz um interpretador fora da allowlist (ticket muito antigo ou gravado à mão) | Dispare de novo pela tela |
| ↳ `INTERPRETER_UNAVAILABLE`, `NO_SHEBANG`, `INTERPRETER_UNSAFE` | | Só de agente anterior ao CR-026 | Atualize os agentes (§18) |
| ↳ `UNSUPPORTED_VERSION` | | Ticket criado por uma versão anterior (snapshot antes da versão 5), ou agente anterior ao CR-026 diante de um ticket com snapshot versão 7 (ou anterior ao CR-025 com a 6) | Dispare de novo pela tela; no segundo caso, atualize os agentes (§18) |
| ↳ `REGISTRATION_CHANGED`, `SCRIPT_INACTIVE`, `NOT_HOMOLOGATED`, `ENVIRONMENT_INACTIVE`, `NO_PERMISSION` | | O cadastro mudou entre o disparo e a execução | Confira o cadastro e dispare de novo |
| ↳ `DB_ERROR: ORA-nnnnn` | `falha antes do spawn: DB_ERROR: ...` | Erro de banco na pré-validação | Veja o código ORA |
| `FAILED` / `SPAWN_ERROR` | `falha antes do spawn: <erro>` e `[SSS] falha ao iniciar: <erro> (agente X)` | Não foi possível criar o log ou o processo (disco, permissão) | Veja o erro; confira o §8 |
| `FAILED` / `LOG_LIMIT` | `encerramento pedido: LOG_LIMIT` | O log local passou de `max_local_log_size_bytes` | Reduza a saída do script ou aumente o limite |
| `FAILED` / `TIMEOUT` | `encerramento pedido: TIMEOUT` | Passou do `timeout_s` do script (ou `script_timeout_s`) | Ajuste o cadastro |
| `FAILED` / `FENCED` | `FENCED: ...` (§15.3) | O agente perdeu o banco durante a execução | §15.3 |
| `FAILED` / `NODE_OFFLINE` | No **outro** agente: `NODE_OFFLINE: ticket(s) N marcado(s) (heartbeat de outro agente vencido ha mais de 180 s)` | O agente dono caiu (ex.: `kill -9`, servidor desligado) | Religue o agente; o filho que ficou vivo é encerrado na religação |
| `FAILED` / `ORPHAN_PROCESS` | Na subida: `ticket finalizado na subida: FAILED/ORPHAN_PROCESS (processo sem acompanhamento)` ou `(PID sem pasta local)` | O agente reiniciou e não pôde acompanhar o processo | Confira no servidor se o script terminou; dispare de novo se precisar |
| Sem status gravado | `OWNERSHIP_LOST: o ticket ja nao e deste agente; nenhum status gravado` | Outro agente marcou o ticket (normalmente `NODE_OFFLINE`) enquanto este estava fora | Veja o heartbeat e a rede deste agente; o resultado real fica só no log local |
| `CANCELLED` / `CANCEL_USER` | `ticket finalizado: CANCELLED/CANCEL_USER ...` | Cancelado pela tela | — |

### 15.5 Agendamentos

| Linha (`WARNING ... regra pausada: <MOTIVO> (<detail>)`) | Causa | Ação |
|---|---|---|
| `USER_INACTIVE`, `SCRIPT_INACTIVE`, `ENVIRONMENT_INACTIVE` | O responsável, o script ou o ambiente foram desativados | Reative e retome a regra pela tela |
| `NO_PERMISSION` | O responsável perdeu a permissão de executar | Ajuste o perfil e retome |
| `INVALID_PARAM` | Os parâmetros gravados não valem mais | Edite a regra |
| `INVALID_CRON` (também `regra pausada: INVALID_CRON (sem proxima ocorrencia no horizonte)`) | Expressão sem próxima ocorrência em `cron_horizon_days` | Corrija a expressão |
| `INTERNAL_ERROR` | Três falhas seguidas de banco na mesma regra, ou outro erro inesperado | Veja as linhas anteriores da regra no log do agente |
| `MISFIRE: N ocorrencia(s) perdida(s) (politica X, tolerancia N s)` | Agentes parados além da tolerância | Esperado depois de parada longa |
| `SKIP_OVERLAP_PRESO: o ticket N esta X ha mais de N s; precisa de atencao` | O ticket anterior da regra não termina | Veja o ticket |

### 15.6 Nó web

| Sintoma | Linha / onde ver | Causa | Ação |
|---|---|---|---|
| HTTP 500 em todas as telas | `CRITICAL ... Subida abortada: configuracao invalida: ...` no `sss_web_<PID>.log` (ou no stderr, se o `log_dir` não aceita escrita) | Configuração, segredos ou banco | Corrija pelo motivo da linha; o detalhe de cada erro 500 fica no log `sss_web` (§14), com o id de ocorrência mostrado na tela |
| "Requisição recusada." (HTTP 403) nos formulários | `requisicao rejeitada (reason=origem ...)` | URL de acesso fora de `allowed_origins` | §10.4 |
| Idem | `reason=csrf` | Página aberta há muito tempo | Recarregue e repita |
| Ninguém entra por HTTP atrás de um proxy HTTPS | — | O proxy manda `X-Forwarded-Proto: https` e o cookie sai `Secure`, mas o navegador chega por HTTP | Acesse pela mesma URL do proxy, ou direto pela porta do `run_web.py` (§10.4) |
| Um usuário não entra: "Houve muitas tentativas com a senha errada..." | — | Bloqueio após `login_max_attempts` | Aguarde `login_lockout_s` ou desbloqueie em Gestão de Usuários |
| `Socket 127.0.0.1:8000 in use by other process` | Terminal | Porta ocupada | `ss -ltnp \| grep :8000` |

### 15.7 Keepalive, saúde e pacote

| Linha | Causa | Ação |
|---|---|---|
| `falhou ao subir: veja var/<nome>/logs/<nome>.out` (`keepalive.log`, código 3) | O processo saiu logo depois de subir | Leia o `.out` e o log da aplicação (§14, §15.1) |
| `recusado: o web precisa da porta` (`keepalive.log`) | Faltou `<nome>:<porta>` na linha do cron | §10.6 |
| `config.ini: chave [retention] ... ignorada` ou `secao [purge] ignorada` (WARNING na subida) | Linha antiga de antes do CR-030 | Apague a linha (o processo sobe normalmente) |
| `SSS UNKNOWN - falha ao conectar no Oracle: ...` (`health.py`) | Conta do processo ou rede | §15.2 |
| `SSS UNKNOWN - configuracao invalida: ...` | `config.ini` ou `secrets.cfg` do `--name` (o `health.py` usa a conta do processo, CR-032) | §7 |
| `Pacote recusado:` (`package.py`, código 1) | Segredo, bytecode ou código de DEV na árvore | Gere de uma cópia limpa (§3) |

---

## 16. Rotações de segredos

* **`cookie_key`** (nó web): gere um novo (§7.2), grave em todos os nós web e reinicie todos juntos. **Todas as sessões são invalidadas**; os usuários entram de novo.
* **Senha de uma conta Oracle** (`sss_web`, `sss_agente`, ou a conta única do §4.0): o DBA troca a senha; grave a nova no `secrets.cfg` dos servidores daquele papel e reinicie os processos. Com a senha antiga, a cadeia de driver para em `ORA-01017` (§15.2).
* **Senha de ambiente** (`[environment:X]`): grave a nova em todos os agentes que atendem o ambiente e reinicie-os. A senha chega ao script pela variável `PADRAO_VALOR_RUN_CONEXAO_BD`, só na próxima execução.

---

## 17. Backup e restauração (CR-007, R-18; CR-008, R-18)

* **Backup:** o esquema (RMAN ou Data Pump do owner), o `config.ini` e o `secrets.cfg` de cada servidor (em cofre) e os logs locais conforme a política da empresa.
* **Depois de restaurar o banco** (restore ou *flashback*): o banco volta a um instante anterior, mas os scripts executados depois dele já produziram efeito. Antes de religar qualquer agente:
  1. pare todos os agentes e anote o **instante de restauração** (o do backup ou do *flashback*);
  2. finalize como `FAILED`/`ORPHAN_PROCESS` os tickets `RUNNING` restaurados que têm PID (eles se referem a processos que não existem mais);
  3. **revise** os tickets `PENDING` e os `RUNNING` sem PID criados antes do instante de restauração. Compare com os logs locais dos agentes (`log_dir/<ambiente>/<script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log`), que sobrevivem à restauração. Os que já rodaram depois do backup são cancelados pela tela (auditado como `TICKET_CANCEL` com o login do operador), nunca apagados;
  4. para não repetir ocorrências de agendamento já cumpridas, configure temporariamente `misfire_policy = SKIP` em **todos** os agentes (o `critical_config` precisa ser igual em todos) e no `[agent]` do config do web (§7.1, para a tela de agendamentos) para a primeira subida; volte a `RUN_ONCE` depois que o primeiro desdobro avançar as regras;
  5. avance as sequences de `tbsss_tickets` e `tbsss_audit` acima do maior id visto nos logs locais e no log da aplicação. O DBA recria a sequence com `START WITH` maior; o 11g não tem `ALTER SEQUENCE ... RESTART`. Assim nenhum id se repete entre o banco e os arquivos locais;
  6. religue os agentes. O startup check limpa as pastas locais.

---

## 18. Atualização de versão e retorno [não ensaiado nesta versão]

### 18.1 Atualização no lugar (CR-028, D10)

Com a estrutura por processo, o código é trocado **no lugar** pelo `bin/sss-update.sh`. `instance/<nome>/`, `var/` e `scripts_ambiente/` não são tocados:

1. Gere e confira o pacote novo (§3). Leia as notas da versão (§18.3) e, se o esquema mudou, combine a janela com o DBA.
2. Pare o web e **todos** os agentes do servidor (`systemctl stop sss-web@web0001 sss-agente@agente0001 ...`; sem `systemd`, §10.6: `sss-keepalive.sh --pause` de cada nome, `bin/sss-stop.sh` nos agentes e `SIGTERM` no web). Com SQL de migração, pare os de todos os servidores e o DBA aplica o SQL agora (§5.2).
3. Atualize, como `sss`:
   ```bash
   # na pasta onde estão o pacote e o SHA256SUMS
   <RAIZ>/bin/sss-update.sh sss-<versao>.tar.gz
   # a última linha mostra o comando de retorno: <RAIZ>/bin/sss-update.sh <RAIZ>/var/update/<data>/sss-retorno-<data>.tar.gz
   ```
   O comando confere o pacote (`SHA256SUMS` externo e interno) e recusa root (código 1), pacote inválido ou sem permissão para criar `var/update/` (código 2, nada muda) e um `python` rodando um comando do SSS a partir da `<RAIZ>` (código 3, nada muda; um processo de outro usuário, que não dá para conferir, só gera aviso). Ele guarda o código atual num pacote de retorno, no mesmo formato, em `var/update/<data>/`, e troca só `bin/`, `docs/`, `scripts/`, `src/`, `AGENTS.md`, `README.md`, `SHA256SUMS` e `instance/exemplos/`. A extração e o código anterior ficam em `<RAIZ>/.update-<data>/` (mesma partição da raiz: a troca é por renomeação, mesmo com `var/` em partição própria), apagada no sucesso. Código 4: falha no meio da troca; o código anterior fica em `.update-<data>/anterior/` e o retorno é o pacote impresso.
   * **`bin/` é trocado inteiro:** um arquivo local que você tenha posto em `bin/` some (fica só no pacote de retorno). Guarde scripts próprios fora do código, por exemplo em `scripts_ambiente/`.
   * **Pacotes de retorno:** `var/update/<data>/` não é apagado sozinho. Depois de validar a versão nova, apague à mão os pacotes antigos que não quiser guardar.
   * **Dono de `var/`:** o `sss-update.sh` roda com o usuário do serviço e grava em `var/update/`. Na instalação com um usuário só (§4.0), `var/` é sempre dessa conta.
4. Desde o CR-032 não há helper a copiar (§8).
5. Compare cada `instance/<nome>/config.ini` com o modelo novo (`diff instance/exemplos/agente0001/config.ini.example instance/agente0001/config.ini`). Chave obrigatória nova ou removida aparece na subida como `configuracao invalida` (§15.1).
6. Suba e valide (§11): `systemctl start sss-web@web0001 sss-agente@agente0001 ...`; sem `systemd`, `sss-keepalive.sh --resume` de cada nome e uma passada do `sss-keepalive.sh` (ou espere a do cron).

**Retorno:** pare tudo de novo (como no passo 2), rode o comando de retorno impresso no passo 3. Voltar para uma versão anterior ao CR-032 exige de novo o helper e o `sudoers` dela. Com migração de esquema, o retorno precisa também do SQL de retorno ou do backup do banco (§17).

### 18.2 Da instalação anterior para a estrutura por processo (CR-028, D9)

Uma instalação no formato anterior (`/opt/sss/app`, `/etc/sss/secrets.cfg`, `/var/lib/sss`, `/var/log/sss`) passa para a `<RAIZ>` **uma vez**, com tudo parado:

1. Instale o pacote novo na `<RAIZ>` (§3) e apague o `sudoers` e o helper da instalação anterior (§8).
2. Divida o `config.ini` antigo em um por processo (`instance/web0001/`, `instance/agente0001/`, §7.1), a partir dos modelos: copie só as chaves que fogem do padrão, e apague as de pastas (elas saem do nome). Divida o `secrets.cfg` da mesma forma (§7.2).
3. **Mova** os dados de cada agente: `log_dir` → `var/<nome>/logs`, `output_dir` → `var/<nome>/output`, `input_dir` → `var/<nome>/input`, `script_work_dir` → `var/<nome>/script_work`. O `work_dir` não precisa ir: pare os agentes sem tickets `RUNNING` e ele é recriado vazio. Depois de mover, acerte o dono para a conta do serviço.
4. Troque as units do `systemd` pelas novas, por nome (§10.5), e o monitoramento (`--name`, §13); a limpeza passa a ser manual (§12).
5. Suba, valide (§11) e só depois apague as pastas antigas. Retorno: as pastas antigas continuam intactas até esse passo.

### 18.3 Notas por versão (formato anterior ao CR-028)

Os passos abaixo valem para a instalação no formato anterior, com a aplicação em pasta própria. As notas de cada versão (chaves renomeadas, SQL, helper) valem também para o §18.1.

1. Gere e confira o pacote novo (§3) e extraia **ao lado** do atual: `/opt/sss/app-<versao>`.
2. Copie o `instance/config.ini` atual para a pasta nova e compare com o `config.ini.example` novo (`diff`). Chave nova obrigatória ou removida aparece na subida como `configuracao invalida` (§15.1).
   * **Chaves renomeadas (CR-015a):** `[agent] saida_dir` → `output_dir`, `saida_max_bytes` → `output_max_bytes`, `saida_max_arquivos` → `output_max_files`, `entrada_dir` → `input_dir` e `[logging] saida_retention_days` → `output_retention_days`. Com o nome antigo, a subida para com `Chave renomeada: <antiga> passou a se chamar <nova>`.
   * **Rotas em inglês (CR-016d, D22):** as telas mudam de endereço, sem redirecionamento (`tickets/novo` → `tickets/new`, `admin_usuarios/lista` → `admin_users/index`, `auditoria/agentes` → `audit/agents`; a lista completa está em `docs/architecture/CR-016c2-identifiers.md`). Favoritos e links salvos com o endereço antigo dão 404: avise os usuários e entre pelo menu. A página inicial (`/script_scheduling_service/`) não muda.
   * **Sessão e campos em inglês (CR-016d, D26 a D28):** os atributos da sessão web mudaram de nome, então quem estiver logado na hora da atualização volta para a tela de login e entra de novo (nenhum dado se perde). Os parâmetros de URL `pagina`/`tamanho` passam a `page`/`size`: um link salvo com os nomes antigos abre na primeira página, com o tamanho padrão. O campo de senha do login passa a `password`, e o navegador pode oferecer salvar a senha de novo.
   * **Formato do log (CR-016c2):** as linhas passam a `[pid=…] [agent=…] [ticket=…] [action=…]` (antes `[agente=…]` e `[acao=…]`). Ajuste filtros de `grep`, coletores de log e alertas que procuravam `[acao=`.
   * **Daemon em inglês (CR-016c2, bloco 4):** os logs da aplicação passam de `log_dir/interno/app/` para `log_dir/internal/app/`; a pasta antiga para de crescer e pode ser apagada à mão depois da retenção. O nome de ambiente reservado passa de `INTERNO` para `INTERNAL`. As chaves dos marcadores `.sss_spawn` e `.sss_proc` do `work_dir` mudaram (`exec_user`, `monotonic`, `wall`): **pare o agente sem tickets `RUNNING`** (parada normal, com a drenagem) antes de trocar a versão, porque o agente novo não lê os marcadores do antigo e não retoma processos deixados por ele.
   * **Configuração e operação em inglês (CR-016b):** no `config.ini`, `[oracle] modo_driver` → `driver_mode`; `[agent] ambientes_atendidos` → `environments`, `usuarios_execucao` → `exec_users`, `interpretadores` → `interpreters` (desde o CR-026, as duas são ignoradas com aviso), `fila_envelhecimento_min` → `queue_aging_min`, `log_dir_min_livre_mb` → `log_dir_min_free_mb`; `[web] sessao_max_horas` → `session_max_hours`, `login_max_tentativas` → `login_max_attempts`, `login_bloqueio_s` → `login_lockout_s`; a seção `[retencao]` → `[retention]`. No `secrets.cfg`, `[ambiente:<NOME>]` → `[environment:<NOME>]`. Com o nome antigo, a subida para com `Chave renomeada` ou `Secao renomeada`, citando o nome novo. Os scripts de operação mudaram de nome (`saude.py` → `health.py`, `empacotar.py` → `package.py`, `gerar_scripts_sql.py` → `generate_sql.py`, `sondar_driver.py` → `probe_driver.py`), assim como as opções de linha de comando (`--alvo` → `--target`, `--exportar-auditoria` → `--export-audit`, `--fila-warn` → `--queue-warn`…; de-para em `docs/architecture/CR-016b-config-and-operations.md`): ajuste o `cron`, os `timer`/`service` do systemd e o Nagios. Os subcomandos do helper mudaram (`clean`, `stop-ticket`, `pack`, `clean-output`, `purge-output`): troque o `sss-helper` junto com a aplicação (passo 4).
   * **Variáveis do script renomeadas (CR-015a):** os scripts recebem só os nomes em inglês (de-para em `docs/architecture/CR-015a-english-names.md`). Antes de atualizar, procure os nomes antigos nos scripts cadastrados, por exemplo: `grep -rnE 'SSS_(AMBIENTE|AGENTE|PLATAFORMA|VERSAO|SCRIPT_NOME|SCRIPT_ARQUIVO|INTERPRETADOR|TIPO_EXECUCAO|PRIORIDADE|DATA_|TIMEOUT_SEG|AGENDAMENTO|RECORRENCIA|LOG_ARQUIVO|SAIDA_DIR|ENTRADA_DIR|TICKET_PAI_ID)' <pastas dos scripts>`. Script que ainda lê um nome antigo recebe vazio.
3. Se o esquema mudou (`SCHEMA_VERSION`), o DBA aplica a migração antes (§5.2). Web e agentes recusam subir com versão diferente (código 15).
   * **Nomes em inglês no banco (CR-016a), sem migração:** a atualização de um banco com o esquema anterior (tabelas `tbsss_environments`, `tbsss_controle`…) **apaga os dados do SSS**. Faça o backup (§17), aplique o `02_rollback_sss.sql` **gerado pela versão anterior** e depois o `01_deploy_sss.sql` e o `99_validate_deploy.sql` da versão nova (§5.2). O `init_db` recusa criar o esquema novo com a `tbsss_controle` antiga presente.
4. Desde o CR-032 não há helper (§8); as notas abaixo valem só para voltar a uma versão anterior.
   * **Helper ao lado da raiz (CR-028):** o padrão do `helper_path` passou a ser `sss-root/bin/sss-helper` na pasta de cima da aplicação (em `/opt/sss/app`, seria `/opt/sss/sss-root/bin/sss-helper`). Na instalação no formato anterior, escreva `helper_path = /opt/sss/bin/sss-helper` no `[agent]` de cada agente antes de subir; sem isso, o agente recusa a subida com `helper ... nao encontrado` (código 13).
   * **Entrada pela tela (CR-020c):** o helper anterior não tem `put-input` nem `list-input`, e as entregas terminariam em `FAILED`/`ERROR`. Instale o helper novo em todos os agentes junto com a versão.
   * **Pasta de trabalho (CR-019):** o helper anterior ignora o campo `work` da especificação: a pasta não é criada e o script recebe em `SSS_WORK_DIR` um caminho que não existe. Antes de ligar `[agent] script_work_dir`, instale o helper novo e crie `script_work_dir/<ambiente>/` de cada ambiente atendido (§8); com a chave vazia, nada muda.
   * **Sem web2py (CR-021f):** o `bin/sss-web.sh` novo só aceita as opções do `scripts/run_web.py` e recusa `web2py.py`/`anyserver.py` (código 2). Troque, junto com a versão, a linha que sobe o web na unit do `systemd` ou no script de operação: `bin/sss-web.sh <python3> --host 127.0.0.1 --port <porta>` (§10.1). Confira antes com `bin/sss-web.sh <python3> --check`. A sessão passa a ser o cookie assinado `sss_session` (CR-021e, D1): quem estiver logado na hora da atualização entra de novo. O `httpserver.log`, os `parameters_<porta>.py` e o painel `/admin` do web2py deixam de existir: tire o `httpserver.log` do `logrotate` (§14.4) e não copie nada disso para a pasta nova.
   * **Aplicação na raiz do pacote (CR-022a):** o pacote não tem mais `applications/script_scheduling_service/`; tudo fica direto em `/opt/sss/app` (antes `/opt/sss/web2py`). Na primeira atualização com esta versão, extraia em `/opt/sss/app` (sem renomear a pasta antiga para ela), copie o `config.ini` de `/opt/sss/web2py/applications/script_scheduling_service/instance/` para `/opt/sss/app/instance/` e troque nos caminhos de operação (unit do `systemd`, `cron` do purge, `sudoers` do monitoramento, scripts de subida) `/opt/sss/web2py` por `/opt/sss/app` e `.../applications/script_scheduling_service/scripts/` por `.../scripts/`. Caminhos absolutos do `config.ini` que apontavam para dentro da pasta antiga (ex.: `log_dir`, `work_dir`) também mudam. O retorno é subir de novo pela pasta antiga, que fica intacta.
   * **Código no pacote `src/sss/` (CR-022b):** para a operação nada muda: os comandos continuam `bin/*.sh` e `scripts/<nome>.py` (agora involucros que chamam `src/sss/cli/`), com as mesmas opções e códigos de saída. O pacote passa a ter só `bin/`, `docs/`, `instance/`, `scripts/` e `src/` (§3); as pastas `modules/`, `webapp/`, `controllers/`, `views/` e `static/` saíram, e templates e estáticos ficam em `src/sss/web/`. Automação local que apontava para arquivos dessas pastas (cópia de CSS, inspeção de template) precisa do caminho novo; as URLs não mudam.
   * **Ordem dos blocos de SQL abaixo:** estão do mais novo para o mais antigo. Quem vem de uma versão anterior ao CR-023 aplica na ordem cronológica: CR-023, CR-025, CR-026 e CR-030. Instruções de um bloco antigo que um bloco mais novo substituiu estão marcadas.
   * **Purge retirado (CR-030): com tudo parado.** O comando `purge.py`, a conta e o papel `purge`, a seção `[retention]`, as retenções de `[logging]` e a limpeza automática dos logs da aplicação saíram; a limpeza passa a ser manual (§12, README §11.3). Tire do `cron` a linha do `purge.py` e, do monitoramento, o `--purge-days`. As linhas antigas do `config.ini` e o `[purge]` do `secrets.cfg` só geram aviso; apague-as. O esquema perde as duas colunas da concessão; num banco já instalado, o DBA aplica (troque `openrisow` e `tbsss_`):
     ```sql
     ALTER TABLE openrisow.tbsss_control DROP (purge_owner, purge_lease_until);
     ```
     Se existir a conta `sss_purge`, ela pode ser removida pelo DBA. **Retorno:** a versão anterior precisa das colunas de volta (`ALTER TABLE openrisow.tbsss_control ADD (purge_owner VARCHAR2(40 CHAR), purge_lease_until DATE)`), das linhas de `[retention]` e do cron do purge.
   * **Config simplificado e interpretador só no cadastro (CR-026): com tudo parado.** O SQL abaixo troca os nomes do cadastro para minúsculas e apaga `tbsss_agents.interpreters`, e a versão anterior não funciona com ele: o web anterior recusaria os disparos, os agentes anteriores parariam de pegar tickets, e as regras agendadas que vencessem nesse meio-tempo ficariam pausadas (`INVALID_PARAM`, reativação à mão). Por isso: **pare o web e todos os agentes**, aplique o SQL, troque as pastas (passo 5) e suba web e agentes na versão nova. O ticket passa à versão 7 do snapshot, que um agente anterior recusaria (`UNSUPPORTED_VERSION`). No `config.ini`, a linha `[agent] interpreters` pode ser apagada (só gera aviso), e as chaves com o valor padrão também (README §12.1). Confira o `PATH` do serviço de cada agente (§9). Num banco já instalado, o DBA aplica antes da subida (troque `openrisow` e `tbsss_`):
     ```sql
     ALTER TABLE openrisow.tbsss_scripts DROP CONSTRAINT ck_tbsss_scr_int;
     ALTER TABLE openrisow.tbsss_scripts MODIFY (interpreter VARCHAR2(100 CHAR));
     UPDATE openrisow.tbsss_scripts SET interpreter = CASE interpreter
       WHEN 'PYTHON3' THEN 'python3' WHEN 'PYTHON' THEN 'python' WHEN 'BASH' THEN 'bash' WHEN 'SH' THEN 'sh'
       WHEN 'PYTHON_SCRIPT' THEN 'python3' WHEN 'SHELL_SCRIPT' THEN 'sh' ELSE interpreter END;
     ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_int
       CHECK (interpreter IN ('python','python3','sh','bash'));
     ALTER TABLE openrisow.tbsss_tickets ADD (interpreter_used VARCHAR2(1000 CHAR));
     -- interpreter_path guardava o usado (CR-025); passa a ser o digitado, que o snapshot ja guarda
     UPDATE openrisow.tbsss_tickets SET interpreter_used = interpreter_path, interpreter_path = NULL
      WHERE interpreter_path IS NOT NULL;
     COMMIT;
     ALTER TABLE openrisow.tbsss_agents DROP COLUMN interpreters;
     COMMENT ON COLUMN openrisow.tbsss_scripts.interpreter IS 'Interpretador do cadastro (python, python3, sh, bash), usado quando nem o digitado nem o #! existem no servidor';
     COMMENT ON COLUMN openrisow.tbsss_tickets.interpreter_path IS 'Interpretador digitado no disparo (caminho ou nome, CR-026); vazio quando nao informado';
     COMMENT ON COLUMN openrisow.tbsss_tickets.interpreter_used IS 'Interpretador executado (digitado, #! ou do cadastro, CR-027); vazio antes do inicio';
     ```
     Os scripts "definido no script" viram `python3` ou `sh` e continuam rodando pelo `#!`, que agora vem primeiro. **Retorno:** a versão anterior precisa da coluna `tbsss_agents.interpreters` (`ALTER TABLE ... ADD (interpreters VARCHAR2(100 CHAR))`), da CK anterior e dos nomes anteriores no cadastro (o `UPDATE` inverso), além da linha `interpreters` no `config.ini`; os tickets com snapshot versão 7 ainda na fila são recusados por ela (`UNSUPPORTED_VERSION`). O retorno também é feito com tudo parado. Prefira o backup do esquema (§17).
   * **Interpretador no disparo e "definido no script" (CR-025):** atualize **todos** os agentes antes de liberar a versão nova da web: o ticket passa à versão 6 do snapshot, que o agente anterior recusa (`UNSUPPORTED_VERSION`). Num banco já instalado, o DBA aplica antes da subida (troque `openrisow` e `tbsss_`):
     ```sql
     ALTER TABLE openrisow.tbsss_scripts DROP CONSTRAINT ck_tbsss_scr_int;
     ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_int
       CHECK (interpreter IN ('PYTHON3','PYTHON','BASH','SH','PYTHON_SCRIPT','SHELL_SCRIPT'));
     ALTER TABLE openrisow.tbsss_tickets ADD (interpreter_path VARCHAR2(1000 CHAR));
     COMMENT ON COLUMN openrisow.tbsss_tickets.interpreter_path IS 'Interpretador executado (configurado, do #! ou digitado no disparo, CR-025); vazio antes do inicio';
     COMMENT ON COLUMN openrisow.tbsss_scripts.interpreter IS 'Interpretador logico (PYTHON3, PYTHON, BASH, SH; PYTHON_SCRIPT e SHELL_SCRIPT usam o #! do script)';
     COMMENT ON COLUMN openrisow.tbsss_agents.interpreters IS 'Interpretadores configurados no agente (PYTHON3, PYTHON, BASH, SH); os definidos no script nao aparecem';
     ```
     *(Substituído pelo CR-026: não há mais `[agent] interpreters`.)* Para usar a opção Python, acrescente `PYTHON=<executável>` em `[agent] interpreters` dos agentes do ambiente. Para voltar à versão anterior, nada no banco precisa ser desfeito (ela não usa a coluna nova); os agentes dela recusam os tickets com snapshot versão 6 (`UNSUPPORTED_VERSION`) e não pegam scripts `PYTHON`, `PYTHON_SCRIPT` nem `SHELL_SCRIPT` (ficam `PENDING`).
   * **Caminho relativo à pasta base (CR-023):** atualize **todos** os agentes antes de cadastrar o primeiro script com caminho relativo (o agente anterior termina o ticket em `PRECHECK_FAILED`, `RELATIVE_PATH`) e configure `[agent] script_base_dir` em cada um (§9). O esquema continua na versão 1, sem migração: num banco já instalado, o DBA aplica antes da subida (troque `openrisow` e `tbsss_` pelo owner e prefixo do ambiente):
     ```sql
     ALTER TABLE openrisow.tbsss_scripts DROP CONSTRAINT ck_tbsss_scr_path;
     ALTER TABLE openrisow.tbsss_scripts ADD CONSTRAINT ck_tbsss_scr_path
       CHECK (INSTR(path_file, '..') = 0 AND INSTR(path_file, '//') = 0 AND INSTR(path_file, '\') = 0);
     ALTER TABLE openrisow.tbsss_tickets ADD (script_path VARCHAR2(1000 CHAR));
     ALTER TABLE openrisow.tbsss_agents ADD (script_base_dir VARCHAR2(500 CHAR));
     COMMENT ON COLUMN openrisow.tbsss_tickets.script_path IS 'Caminho real do script executado, resolvido pelo agente (CR-023); vazio antes do inicio';
     COMMENT ON COLUMN openrisow.tbsss_agents.script_base_dir IS 'Pasta base dos scripts com caminho relativo ([agent] script_base_dir); vazio sem base';
     COMMENT ON COLUMN openrisow.tbsss_scripts.path_file IS 'Caminho normalizado do script: absoluto ou relativo a [agent] script_base_dir de cada agente';
     ```
     Para voltar à versão anterior, nada no banco precisa ser desfeito: ela não usa as colunas novas, e a CK nova aceita os caminhos absolutos que ela grava (um script já cadastrado com caminho relativo termina em `RELATIVE_PATH` nos agentes dela). Num banco já instalado, os 14 scripts de demonstração continuam com o caminho absoluto: o `01_deploy_sss_<owner>_<prefixo>.sql` não roda sobre um esquema existente, e só o `scripts/init_db.py` reaplica o seed (o `MERGE` passa os 14 para `utilitarios/<arquivo>`). Antes de reaplicar o seed, ou de cadastrar qualquer script com caminho relativo, configure `script_base_dir` em todos os agentes do ambiente.
5. Pare os agentes (`sss-stop.sh` ou `SIGTERM`) e o web, troque as pastas (`mv /opt/sss/app /opt/sss/app-<anterior> && mv /opt/sss/app-<versao> /opt/sss/app`) e suba de novo.
6. Valide (§11). **Retorno:** pare, troque as pastas de volta e suba. Com migração de esquema, o retorno precisa do backup do banco (§17).

---

## 19. Checklist pré-produção

- [ ] Estrutura por processo (CR-028): `<RAIZ>` = `/portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service`, um `instance/<nome>/` por processo com `[app] name` igual ao nome da pasta, e nomes de agente únicos em toda a instalação
- [ ] Nenhuma linha `[app] sss_env`, `exec_users`, `exec_work_dir` nem `helper_path` (CR-032; só geram aviso); a pasta `<TIPO>` acima da raiz é `PROD`
- [ ] Tela de Entrada (CR-020): cada agente com `[agent] input_dir` (padrão `var/<nome>/input`) e, com proxy, o limite de corpo acima de `[web] input_upload_max_bytes`
- [ ] Nenhuma linha `data_backend` no `config.ini` (removida no F7.3; a aplicação usa sempre o Oracle)
- [ ] `[oracle] user` de cada servidor: a conta do papel ou, com um usuário de banco só, a dona do esquema (CR-032)
- [ ] Nenhuma linha `[retention]`, `*_retention_days` nem `[purge]` (CR-030; só geram aviso)
- [ ] Limpeza manual combinada: quem roda o SQL do banco e o `find` dos arquivos, e com que frequência (§12, README §11.3)
- [ ] `[web] allowed_origins` com a URL pública e `trusted_proxies` com o proxy
- [ ] `[logging] level = INFO`
- [ ] `call_timeout_ms` e `misfire_policy` iguais em todos os agentes (os demais tempos são fixos, CR-032), conferidos pela linha `tempos do fencing` de cada um
- [ ] Combinação de driver registrada (linha `driver=... modo=... servidor=... cliente=...` de cada servidor)
- [ ] `ls <RAIZ>` sem `applications/`, `gluon/` nem `web2py.py`; `curl .../admin/...` dá 404; `src/sss/web/controllers/dev.py` ausente
- [ ] `instance/secrets.cfg` único, com `0600` e dono a conta do serviço, com o `[environment:*]` de todo ambiente atendido
- [ ] Com script de caminho relativo (CR-023): `[agent] script_base_dir` em **todos** os agentes do ambiente, a pasta existente e a linha `pasta base dos scripts` no log de subida e no painel de agentes (§9)
- [ ] Interpretador (CR-025, CR-026): o `PATH` do processo do agente (unit ou shell que roda o `sss-scheduler.sh`) acha `python3`, `bash` e os demais interpretadores dos scripts e os que os operadores vão digitar só pelo nome (§9); nenhuma linha `[agent] interpreters` (só gera aviso)
- [ ] `config.ini` só com as chaves obrigatórias e as que fogem do padrão (README §12.1); as pastas são criadas na subida (§8)
- [ ] `<RAIZ>/var` em partição própria, com alerta de uso (§4.3)
- [ ] Senha inicial do seed trocada (§5.3)
- [ ] `sss-keepalive.sh` no cron (§10.6) e `health.py` no monitoramento (§13)
- [ ] Saída padrão do nó web redirecionada (`journald` ou arquivo, §14.4)
- [ ] Backup do esquema e dos arquivos de configuração (§17)

---

## 20. Desinstalação

```bash
# como root
systemctl disable --now 'sss-web@*' 'sss-agente@*' 2>/dev/null
rm -f /etc/systemd/system/sss-web@.service /etc/systemd/system/sss-agente@.service && systemctl daemon-reload
rm -f /etc/sudoers.d/sss-monitor      # só se o monitoramento usar sudo (§13)
# depois de guardar o que precisar de var/ (logs, saídas) e de instance/ (configuração, em cofre)
rm -rf /portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service
userdel sss
```

O esquema do banco é removido pelo DBA com o `02_rollback_sss_<owner>_<prefixo>.sql` (§5.2), **depois** do backup.

---

## Apêndice A. Servidor único de demonstração (DEV)

Para demonstração ou homologação interna, web e agente podem ficar no mesmo servidor, na pasta `DEV`:

* A mesma estrutura por processo (CR-028): `instance/web0001/` e `instance/agente0001/`, dados em `var/web0001/` e `var/agente0001/`, subida por `bin/sss-web.sh <python3> web0001` e `bin/sss-scheduler.sh agente0001`. O DEV de referência guarda os scripts de teste em `dev/scripts` (`script_base_dir`) e mantém um `instance/config.ini` no formato único, usado pela bateria de testes e pelas ferramentas de banco (`init_db.py`, `generate_sql.py`).
* Um único `instance/secrets.cfg` com `[oracle]`, `[web]` e os `[environment:*]` (CR-032, D14).
* A conta Oracle pode ser a dona do esquema (CR-032, D11: também no PROD).
* Siga o §3 (pacote), o §7 (configuração), o §10.1 e o §10.2 (subida), o §10.4 (túnel SSH) e o §11 (validação). **Esse é o cenário ensaiado em 2026-10-21.**

Os scripts `bin/start_local.sh` e `bin/stop_local.sh` do repositório são só da máquina de desenvolvimento e não vêm no pacote. Um DEV instalado pelo pacote não tem a vitrine `/dev/...` (o `src/sss/web/controllers/dev.py` não vai no pacote): ela responde 404, e o resto sobe normalmente (CR-021f3).

---

## Apêndice B. Registros de servidores de homologação

Registros históricos das instalações de demonstração anteriores ao Oracle (backend FAKE). Ficam como estavam: as referências a seções (`§n`) dentro deles são da versão anterior deste guia (commit `5ee058f`), e os procedimentos do FAKE não valem mais desde o F7.3.

### B.1 Variante: servidor compartilhado sem `sudo` nem `systemd` (registro do clone 7)

Implantação feita em 2026-10-15 no servidor **clone 7** (`brtlvlts1216pl`, 10.238.10.109), que serve de modelo para servidores parecidos. **Situação atual:** removida no mesmo dia, a pedido do responsável (o SSS passou para o servidor do §22); o `~/.sss` do clone 7 também foi apagado.

> **Registro histórico, anterior ao CR-005.** A árvore de scripts do próprio usuário (§21.2) e as chaves `base_script_dir(s)` e `app_log_backups` não valem mais: para a versão atual, siga o §8.1 (opção sem `sudo`) e o §16.3.

#### B.1.1 O que o servidor tinha

| Item | Situação | Decisão |
|---|---|---|
| Sistema | Oracle Linux 6.9 (glibc 2.12) | Funciona com o Python já instalado |
| Python | `/usr/local/bin/python3.7` (3.7.4), **sem `ssl` e sem `sqlite3`** | Usado como está. Correção do Rocket para Python sem `ssl` no commit `fdf6f35` (antes dela, cada conexão ociosa gerava `NameError` no log) |
| `git`, `sudo`, `systemd`, `crontab` | Ausentes ou sem permissão | Código por pacote (§5.2); tudo no usuário `mastersafgf`; processo mantido num `screen` |
| `/portaloptrib/TESHUVA` | Modo `777`, compartilhado com outros sistemas | Pasta própria `SSS/` com `0750`; segredos **fora** da árvore compartilhada, em `~/.sss` (`0700`) |
| Portas | Várias em uso por outros sistemas | Porta **18000**, somente `127.0.0.1` |

#### B.1.2 Estrutura instalada

| Caminho | Conteúdo | Modo |
|---|---|---|
| `/portaloptrib/TESHUVA/SSS/web2py` | Código (pacote `sss-fdf6f35.tar.gz`, SHA-256 conferido) | `0750` |
| `/portaloptrib/TESHUVA/SSS/scripts` | Árvore de scripts de exemplo, do próprio usuário, somente leitura | arquivos `0444`, diretórios `0555` |
| `/portaloptrib/TESHUVA/SSS/logs` | `sss_web.log` (aplicação) e `server.out` (saída do servidor) | `0750` |
| `/portaloptrib/TESHUVA/SSS/work` | Reservado ao agente (F8) | `0700` |
| `/portaloptrib/TESHUVA/SSS/pacotes` | Pacotes recebidos e `.sha256` | `0750` |
| `/portaloptrib/TESHUVA/SSS/start_sss.sh`, `stop_sss.sh` | Operação | `0750` |
| `~/.sss/secrets.cfg` | `cookie_key` | `0600` |
| `~/.sss/web.env` | `SSS_DEV_SEED_PASSWORD` (gerada no servidor) e `SSS_TZ` | `0600` |

> **Nomes em inglês (CR-016c2, bloco 5):** até esta versão os scripts do servidor se chamavam `iniciar_sss.sh` e `parar_sss.sh`, e a saída ia para `logs/servidor.out`. Na próxima implantação, renomeie os três no servidor (`mv iniciar_sss.sh start_sss.sh`, `mv parar_sss.sh stop_sss.sh` e, dentro deles, `servidor.out` → `server.out`).

Diferenças do `config.ini` em relação ao exemplo: `secrets_file = /home/mastersafgf/.sss/secrets.cfg`, `agent_id = clone7-sss-hml`, `base_script_dir = /portaloptrib/TESHUVA/SSS/scripts`, `work_dir = /portaloptrib/TESHUVA/SSS/work`, `script_owner_uids = 4304` (UID do `mastersafgf`), `log_dir = /portaloptrib/TESHUVA/SSS/logs` e `allowed_origins = http://127.0.0.1:18000`.

#### B.1.3 Operação

```bash
/portaloptrib/TESHUVA/SSS/start_sss.sh    # sobe no screen "sss" e confere o HTTP 200 do login
/portaloptrib/TESHUVA/SSS/stop_sss.sh      # Ctrl+C no screen e espera a porta 18000 ser liberada
screen -r sss                               # acompanhar a saída; sair SEM parar: Ctrl+A e depois D
cat ~/.sss/web.env                          # senha dos usuários de demonstração (admin, op.prod, op.hml, consulta)
tail -f /portaloptrib/TESHUVA/SSS/logs/sss_web.log
```

* O `start_sss.sh` carrega `~/.sss/web.env` dentro do `screen` e chama `bin/sss-web.sh /usr/local/bin/python3.7 web2py.py -a '<recycle>' -i 127.0.0.1 -p 18000 --no_gui`. A senha não aparece na lista de processos.
* **A partir do pacote sem web2py (CR-021f)**, a chamada passa a ser `bin/sss-web.sh /usr/local/bin/python3.7 --host 127.0.0.1 --port 18000` (§10.1): o launcher novo recusa `web2py.py`. Troque o `start_sss.sh` junto com o pacote, nunca antes.
* **Sem início automático:** se o servidor reiniciar, rode o `start_sss.sh` de novo. Reiniciar o SSS restaura os dados de demonstração.
* Trocar a senha de demonstração: edite `~/.sss/web.env` e reinicie (`stop_sss.sh` + `start_sss.sh`).

#### B.1.4 Acesso dos usuários

Túnel SSH da máquina do usuário (§13.1), com uma conta que tenha SSH no servidor. Este servidor exige os algoritmos RSA legados:

```bash
ssh -N -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa -L 18000:127.0.0.1:18000 <usuario>@10.238.10.109
# navegador: http://localhost:18000/script_scheduling_service
```

#### B.1.5 Validação realizada

* `check_env.py`: todos os itens OK; suíte completa no servidor: `Ran 615 tests ... OK (skipped=17)`.
* Teste de carga da configuração (§10): `SSS: configuracao OK (sss_env=DEV, backend=FAKE, agent_id=clone7-sss-hml)`.
* Escuta somente em `127.0.0.1:18000`; cabeçalhos de segurança presentes; POST com origem estranha → 403 (registrado no log); painel do web2py desabilitado (`parameters_18000.py` com `password=None`).
* Pelo túnel: login do `admin`, disparo de ticket, painel de agentes e logout, sem erros no console. Em seguida, reinício pelos scripts para entregar os dados de demonstração limpos.

---

### B.2 Servidor acessado por salto: `brtlvlty3067sl` (10.129.164.55)

Implantação feita em 2026-10-15 com o pacote do commit `aca60b0` (código do `fdf6f35` mais documentação). **Este é o servidor ativo do SSS.**

> **Atualização pendente (CR-003, CR-004 e CR-005):** este servidor ainda roda o código do `fdf6f35`. O `config.ini` dele ainda tem `base_script_dir` e `app_log_backups`, que a versão atual recusa, e o log da aplicação ainda é o arquivo único `logs/sss_web.log`. O pacote da versão atual (`fe5884c`) e o roteiro de atualização, já ensaiados, estão no §22.6. O pacote `e8759e3`, preparado antes do CR-005, foi **descartado** e não deve ser instalado.

#### B.2.1 Diferenças em relação ao clone 7

| Item | Situação | Decisão |
|---|---|---|
| Acesso | Só pelo clone 7 (10.238.10.109); não há rota direta das estações | Cópia de arquivos e túnel pelo clone 7 (22.4) |
| Sistema | Oracle Linux 6.10 | — |
| Python | `/portaloptrib/TESHUVA/sparta/python3.8/bin/python3` (3.8.5), **sem `ssl`, sem `sqlite3` e sem `_hashlib`** | Usado como está: suíte completa OK, PBKDF2 em Python puro (0,28 s por login). **Risco:** esse Python pertence ao sistema Sparta; se for trocado ou removido, o SSS para |
| Ferramentas | `git`, `crontab` e `nohup` disponíveis; **sem `screen`/`tmux`**, `sudo` ou `systemd` | Processo com `nohup` e arquivo de PID |
| `/portaloptrib/TESHUVA` | Do próprio usuário, modo `755` (não compartilhado como no clone 7) | Mesma estrutura do §21.2, em `/portaloptrib/TESHUVA/SSS` |
| Porta | 18000 livre | `127.0.0.1:18000` |

`config.ini`: igual ao do clone 7, exceto `agent_id = srv3067-sss-hml` (até o CR-011 também `script_owner_uids = 4135`, UID do `mastersafgf`; a linha é apagada na atualização, §16). Segredos e senha de demonstração em `~/.sss` (`0600`), gerados no servidor.

#### B.2.2 Operação

```bash
/portaloptrib/TESHUVA/SSS/start_sss.sh    # sobe com nohup, grava o PID em SSS/work/sss_web.pid e confere o HTTP 200
/portaloptrib/TESHUVA/SSS/stop_sss.sh      # SIGINT ao PID (só se o PID ainda for o do SSS), espera a porta ser liberada
tail -f /portaloptrib/TESHUVA/SSS/logs/server.out     # saída do servidor (equivale ao "screen -r" do clone 7)
tail -f /portaloptrib/TESHUVA/SSS/logs/sss_web.log      # log da aplicação (até a atualização do §22.6)
# depois do §22.6: tail -f "$(find /portaloptrib/TESHUVA/SSS/logs/internal/app -name 'sss_web_*.log' -type f -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-)"
cat ~/.sss/web.env                                      # senha dos usuários de demonstração
```

* Os dois scripts são idempotentes: subir com o SSS no ar responde "O SSS ja esta rodando (PID ...)"; parar com ele parado responde "O SSS nao esta rodando.".
* O processo continua no ar depois que a sessão SSH é encerrada (`nohup`).

#### B.2.3 Início automático no boot (não ativado)

O `crontab` do usuário está vazio e **não foi alterado**. Para ativar, o responsável roda uma vez no servidor:

```bash
( crontab -l 2>/dev/null; echo "@reboot /portaloptrib/TESHUVA/SSS/start_sss.sh >> /portaloptrib/TESHUVA/SSS/logs/server.out 2>&1" ) | crontab -
crontab -l      # conferir
```

Para desativar: `crontab -e` e apagar a linha. Depois de um reboot, os dados de demonstração voltam ao seed.

#### B.2.4 Acesso dos usuários (túnel pelo clone 7)

O 10.129.164.55 aceita o `mastersafgf` vindo do clone 7 **pela chave do clone 7**; a senha digitada da estação foi recusada (`Permission denied`). Por isso o segundo trecho do túnel sempre parte do clone 7, e o `ProxyCommand` com senha nos dois servidores **não funciona** aqui.

**Forma recomendada: túnel fixo no clone 7** (um processo só, compartilhado por todos os usuários). Instalação, uma vez, no clone 7:

```bash
mkdir -p -m 700 ~/sss_tunel
cat > ~/sss_tunel/tunel.sh <<'EOF'
#!/bin/bash
# Tunel fixo clone 7 -> 10.129.164.55 (SSS); reconecta sozinho se cair
while true; do
    ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes \
        -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
        -L 127.0.0.1:18000:127.0.0.1:18000 mastersafgf@10.129.164.55
    echo "$(date '+%F %T') tunel caiu (rc=$?); nova tentativa em 10 s"
    sleep 10
done
EOF
chmod 700 ~/sss_tunel/tunel.sh
```

Subir, conferir e parar (no clone 7):

```bash
nohup setsid ~/sss_tunel/tunel.sh >> ~/sss_tunel/tunel.log 2>&1 < /dev/null &
echo $! > ~/sss_tunel/tunel.pid
netstat -ltn | grep 127.0.0.1:18000          # deve mostrar LISTEN
kill -- -$(cat ~/sss_tunel/tunel.pid)        # parar (mata o laco e o ssh)
```

Na estação de cada usuário (um salto só; vários usuários ao mesmo tempo, sem trocar porta):

```bash
ssh -N -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa \
    -L 18000:127.0.0.1:18000 mastersafgf@10.238.10.109
# navegador: http://localhost:18000/script_scheduling_service
```

* O túnel fixo escuta só em `127.0.0.1` do clone 7; como o clone 7 é compartilhado, qualquer usuário logado nele alcança a tela de login do SSS (a senha continua exigida).
* Depois de um reboot do clone 7, suba o túnel de novo (início automático não ativado; exigiria `crontab`).
* Se o `ssh` da estação for antigo e recusar `PubkeyAcceptedAlgorithms`, troque por `PubkeyAcceptedKeyTypes`.
* **Não** abra o SSS na rede (`-i 0.0.0.0`) nem use `-L 0.0.0.0:...` na estação: o tráfego é HTTP sem TLS e o acesso ficaria exposto (§13).

**Alternativa sem o túnel fixo: túnel em dois trechos, por usuário** (validado com HTTP 200):

```bash
ssh -t -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa \
    -L 127.0.0.1:18000:127.0.0.1:18000 mastersafgf@10.238.10.109 \
    "ssh -N -L 18000:127.0.0.1:18000 mastersafgf@10.129.164.55"
```

* O `Ctrl+C` encerra os dois trechos. Pede só a senha do clone 7 (ou nenhuma, com chave).
* A porta do meio (no clone 7) é única por usuário: com duas pessoas conectadas ao mesmo tempo, a segunda troca os dois números do meio (`...:127.0.0.1:18001` e `-L 18001:...`). Não pode coincidir com a do túnel fixo, se ele estiver no ar.
* Impressão digital do 10.129.164.55 (para conferir no clone 7): `SHA256:Gpacuzn+pHDGaLIHMxMnl8l0UVGvNE5N7Dkp3VzHpcM` (RSA 2048).

#### B.2.5 Validação realizada

* Pacote com SHA-256 conferido; `check_env.py` OK; suíte no servidor: `Ran 615 tests ... OK (skipped=17)`.
* Teste de carga da configuração: `SSS: configuracao OK (sss_env=DEV, backend=FAKE, agent_id=srv3067-sss-hml)`.
* Escuta só em `127.0.0.1:18000`; cabeçalhos de segurança presentes; origem estranha → 403; painel do web2py desabilitado.
* Processo vivo depois do fim da sessão SSH; reinício e idempotência dos scripts conferidos.
* Pelo túnel em dois trechos: login do `admin`, disparo de ticket, painel de agentes e logout, sem erros. Depois, reinício para entregar os dados de demonstração limpos.

#### B.2.6 Atualização para a versão `fe5884c` (CR-003, CR-004 e CR-005) — [substituída pelo §22.7; não executada]

O pacote `e8759e3` (CR-003 e CR-004), ensaiado antes do CR-005, foi descartado: a versão atual também muda a configuração e os logs.

| Item | Valor |
|---|---|
| Pacote | `sss-fe5884c.tar.gz` (13,8 MB), gerado por `git archive` (§5.2) do commit `fe5884c` |
| SHA-256 | `c68916bdff5e44ba4609c4e802326ff94b8f4bac7265bc10815debcd84616a60` |
| Onde está | Máquina de desenvolvimento: `/home/eduardof/sss_packages/` (pacote e `.sha256`) |
| Mudança de configuração | Duas, no `config.ini`: apagar a linha `base_script_dir = ...` e trocar `app_log_backups = 10` por `app_log_retention_days = 30`. `secrets.cfg` e `web.env` não mudam |
| Árvore de scripts | `$SSS/scripts` deixa de ser usada: os scripts do seed apontam para `/opt/automacoes/scripts/...`, que não existe neste servidor (sem `sudo`). A **Gestão de Scripts** mostra o aviso "Arquivo não encontrado neste servidor…" e o disparo cria o ticket normalmente (§8.1, opção sem `sudo`). A pasta pode ficar onde está |
| Logs | O log da aplicação passa para `$SSS/logs/internal/app/AAAA/MM/DD/HH/MI/sss_web_<PID>.log` (§15.2). O `$SSS/logs/sss_web.log` antigo para de crescer e pode ser guardado como evidência |
| Parada | Cerca de 1 minuto (passo 6). Os dados de demonstração voltam ao seed, como em todo reinício |

**Ensaio (2026-10-16, na máquina de desenvolvimento, com o Python 3.8.5, a mesma versão do servidor, numa estrutura `$SSS` igual à do servidor):**
* `config.ini` do servidor reproduzido a partir do exemplo do `fdf6f35` (com `base_script_dir` e `app_log_backups`): sem conversão, a carga é recusada com `ConfigError` "Chave desconhecida na secao [agent]: base_script_dir";
* passos 1 a 4 como abaixo: SHA-256 OK; só `script_scheduling_service` em `applications`; passo 2 deixa `app_log_max_bytes` e `app_log_retention_days = 30` e responde "chaves OK"; `check_env.py` com código 0; suíte `Ran 718 tests ... OK (skipped=18)`; teste de carga `SSS: configuracao OK (sss_env=DEV, backend=FAKE, agent_id=srv3067-sss-hml)`;
* subida pelo `bin/sss-web.sh` com `-a '<recycle>' -i 127.0.0.1`: login HTTP 200, os 4 cabeçalhos de segurança, origem estranha recusada com 403, painel do web2py desabilitado (`password=None`);
* log em `$SSS/logs/internal/app/AAAA/MM/DD/HH/MI/sss_web_<PID>.log` (o teste de carga do passo 4 deixa um arquivo próprio, do minuto em que rodou), com `[agent=srv3067-sss-hml]`, nenhum `CRITICAL`, pastas `0750` e arquivos `0640`;
* teste de fumaça no navegador: login, O que eu posso fazer, Rotinas disponíveis (5 scripts), disparo do carga_diaria com o resumo e o comando `PYTHON3 -I /opt/automacoes/scripts/carga_diaria.py ...`, "Ticket #41 criado com sucesso." (o log registra `arquivo do script nao existe no no web; o agente confere`), agentes `agt-host01` e `agt-host02`, saída com "Você saiu do sistema."; nenhum erro no console;
* parada por SIGINT, com a porta liberada.

**0. Levar o pacote até o servidor** (dois saltos, como no §22.4):

```bash
VER=fe5884c
# na estação, a partir da pasta onde estão os dois arquivos
scp -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa \
    sss-$VER.tar.gz sss-$VER.tar.gz.sha256 mastersafgf@10.238.10.109:/tmp/
# no clone 7 (defina VER=fe5884c de novo)
scp /tmp/sss-$VER.tar.gz /tmp/sss-$VER.tar.gz.sha256 mastersafgf@10.129.164.55:/portaloptrib/TESHUVA/SSS/pacotes/
rm -f /tmp/sss-$VER.tar.gz /tmp/sss-$VER.tar.gz.sha256
```

**No 10.129.164.55, como `mastersafgf`:**

```bash
VER=fe5884c
SSS=/portaloptrib/TESHUVA/SSS
PY=/portaloptrib/TESHUVA/sparta/python3.8/bin/python3
APP=applications/script_scheduling_service
NOVO=$SSS/web2py-$VER

# 1. Conferir e extrair AO LADO da versão atual (o SSS continua no ar)
cd $SSS/pacotes && sha256sum -c sss-$VER.tar.gz.sha256              # sss-fe5884c.tar.gz: OK
mkdir -m 750 $NOVO && tar -xzf $SSS/pacotes/sss-$VER.tar.gz -C $NOVO
ls $NOVO/applications                                                # somente script_scheduling_service

# 2. config.ini: copiar o atual, apagar a pasta base e trocar a retenção do log
cp $SSS/web2py/$APP/instance/config.ini $NOVO/$APP/instance/config.ini
chmod 640 $NOVO/$APP/instance/config.ini
sed -i -e '/^base_script_dirs\{0,1\} *=/d' \
       -e 's|^app_log_backups *=.*$|app_log_retention_days = 30|' $NOVO/$APP/instance/config.ini
grep -nE '^(base_script|app_log_)' $NOVO/$APP/instance/config.ini
# esperado: só app_log_max_bytes e app_log_retention_days = 30
diff <(grep -oE "^[a-z_]+ =" $NOVO/$APP/instance/config.ini.example | sort) \
     <(grep -oE "^[a-z_]+ =" $NOVO/$APP/instance/config.ini | sort) && echo "chaves OK"

# 3. Verificar o código novo (não usa a porta; o SSS atual segue no ar)
cd $NOVO/$APP
$PY scripts/check_env.py; echo "codigo: $?"                         # 0
$PY -m unittest discover -s scripts -p "test_*.py" 2>&1 | tail -3     # Ran ... tests ... OK (skipped=23)

# 4. Teste de carga da configuração (§10) na pasta nova
cd $NOVO && umask 077
# Python puro, sem o shell do web2py (CR-021c): a mesma configuracao que a web carrega.
$PY -c 'import sys; sys.path.insert(0, "applications/script_scheduling_service/modules"); import sss_config; c = sss_config.get_config("sss_web"); print("SSS: configuracao OK (sss_env=%s, owner=%s, prefixo=%s, agent_id=%s)" % (c.app.sss_env, c.oracle.owner, c.oracle.table_prefix, c.agent.agent_id))' 2>&1 | grep -E "^SSS:|ConfigError"
# esperado: SSS: configuracao OK (sss_env=DEV, backend=FAKE, agent_id=srv3067-sss-hml)

# 5. Conferir que os scripts de operação usam o caminho $SSS/web2py e não dependem do log antigo
grep -n "web2py\|sss_web.log" $SSS/start_sss.sh $SSS/stop_sss.sh

# 6. Trocar a versão (parada de ~1 minuto)
$SSS/stop_sss.sh
mv $SSS/web2py $SSS/web2py-fdf6f35 && mv $NOVO $SSS/web2py
$SSS/start_sss.sh

# 7. Validar
curl -s -o /dev/null -w "login: HTTP %{http_code}\n" http://127.0.0.1:18000/script_scheduling_service/default/login     # 200
curl -sI http://127.0.0.1:18000/script_scheduling_service/default/login | grep -icE "content-security-policy|x-frame-options|x-content-type-options|referrer-policy"   # 4
curl -s -o /dev/null -w "origem estranha: HTTP %{http_code}\n" -X POST -H "Origin: http://outro-host" http://127.0.0.1:18000/script_scheduling_service/default/login   # 403
find $SSS/logs/internal/app -name 'sss_web_*.log' -type f -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-   # log mais recente: o da subida
find $SSS/logs/internal/app -name 'sss_web_*.log' -type f | xargs grep -c CRITICAL   # 0 em cada arquivo (o do passo 4 e o da subida)
tail -n 5 $SSS/logs/server.out
```

Se no passo 4 aparecer `ConfigError` com "Chave desconhecida", a linha citada ficou no `config.ini`: apague-a ou corrija-a e repita o passo 4.

Depois, pelo túnel (§22.4), faça o teste de fumaça do §12: login, **O que eu posso fazer**, **Rotinas disponíveis**, disparo com o resumo (o comando mostra `/opt/automacoes/scripts/carga_diaria.py`), agentes e saída.

**Retorno (rollback), se algo falhar no passo 7:**

```bash
$SSS/stop_sss.sh
mv $SSS/web2py $SSS/web2py-$VER && mv $SSS/web2py-fdf6f35 $SSS/web2py
$SSS/start_sss.sh
```

A versão anterior fica intacta em `$SSS/web2py-fdf6f35`, com o `config.ini` antigo. Apague essa pasta só depois do aceite da homologação. Depois da atualização, troque neste capítulo o commit do §22 para `fe5884c` e registre a validação no §22.5.

#### B.2.7 Atualização para a versão `17950fb` (CR-003 a CR-008) — [ensaiada; não executada no servidor]

Substitui o §22.6: o pacote `fe5884c` não chegou a ser aplicado e fica descartado. O servidor continua no `fdf6f35`, e esta atualização sai dele direto para o `17950fb`.

| Item | Valor |
|---|---|
| Pacote | `sss-17950fb.tar.gz` (14,6 MB), gerado por `git archive` (§5.2) do commit `17950fb` |
| SHA-256 | `d8c47422a8c5055e5b1b5a4c9886ddee8aa5503aa8a3447d02ced944ccf57e72` |
| Onde está | Máquina de desenvolvimento: `/home/eduardof/sss_packages/` (pacote, `.sha256` e o roteiro `UPDATE-17950fb.txt`) |
| Mudança de configuração | No `config.ini`: apagar `base_script_dir`, trocar `app_log_backups` por `app_log_retention_days = 30` e acrescentar as chaves opcionais novas com o valor padrão (CR-007 e CR-008; passo 2). `secrets.cfg` e `web.env` não mudam: as seções `[environment:*]` do `secrets.cfg` antigo só geram WARN em DEV ("não pertence ao papel 'web'") |
| Árvore de scripts | Como no §22.6: os scripts do seed apontam para `/opt/automacoes/scripts/...`, que não existe neste servidor; a Gestão de Scripts avisa "Arquivo não encontrado neste servidor…" e o disparo funciona |
| Logs | `$SSS/logs/internal/app/AAAA/MM/DD/HH/MI/sss_web_<PID>.log` (§15.2); o `$SSS/logs/sss_web.log` antigo para de crescer |
| Usuários | Todos precisam entrar de novo depois da troca (CR-008, E2: a sessão antiga não tem `session_epoch`). Os dados de demonstração voltam ao seed, como em todo reinício |
| Parada | Cerca de 1 minuto (passo 6) |

**Ensaio (2026-10-17, na máquina de desenvolvimento, com o Python 3.8.5, a mesma versão do servidor, numa estrutura `$SSS` igual à do servidor, partindo do `fdf6f35` com o `config.ini` e o `secrets.cfg` daquela versão):**
* passo 1: SHA-256 OK; só `script_scheduling_service` em `applications`;
* passo 2: "chaves OK" depois da conversão (sem as chaves opcionais, a conferência acusa as 7 chaves novas, embora a carga funcione);
* passo 3: `check_env.py` com código 0; suíte `Ran 819 tests ... OK (skipped=23)`;
* passo 4: `SSS: configuracao OK (sss_env=DEV, backend=FAKE, agent_id=srv3067-sss-hml)`. Antes dela, o web2py imprime "New installation error: unable to create welcome.w2p file" com um *traceback* de `applications/welcome/models`: é esperado, porque a aplicação `welcome` fica fora do pacote de propósito (§5.3);
* subida pelo `bin/sss-web.sh` com `-a '<recycle>' -i 127.0.0.1 -p 18000`: login HTTP 200, os 4 cabeçalhos de segurança, origem estranha recusada com 403, nenhum `CRITICAL` nos logs;
* teste de fumaça no navegador: login, O que eu posso fazer, Rotinas disponíveis, lista de tickets, agentes, formulário de script (com o campo SHA-256 do CR-008), disparo do carga_diaria ("Ticket #41 criado com sucesso."), saída ("Você saiu do sistema."); nenhum erro no console;
* retorno: com o `fdf6f35` de volta no lugar, login HTTP 200.

**0. Levar o pacote até o servidor** (dois saltos, como no §22.4):

```bash
VER=17950fb
# na estação, a partir da pasta onde estão os arquivos
scp -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa \
    sss-$VER.tar.gz sss-$VER.tar.gz.sha256 mastersafgf@10.238.10.109:/tmp/
# no clone 7 (defina VER=17950fb de novo)
scp /tmp/sss-$VER.tar.gz /tmp/sss-$VER.tar.gz.sha256 mastersafgf@10.129.164.55:/portaloptrib/TESHUVA/SSS/pacotes/
rm -f /tmp/sss-$VER.tar.gz /tmp/sss-$VER.tar.gz.sha256
```

**No 10.129.164.55, como `mastersafgf`:**

```bash
VER=17950fb
SSS=/portaloptrib/TESHUVA/SSS
PY=/portaloptrib/TESHUVA/sparta/python3.8/bin/python3
APP=applications/script_scheduling_service
NOVO=$SSS/web2py-$VER

# 1. Conferir e extrair AO LADO da versão atual (o SSS continua no ar)
cd $SSS/pacotes && sha256sum -c sss-$VER.tar.gz.sha256              # sss-17950fb.tar.gz: OK
mkdir -m 750 $NOVO && tar -xzf $SSS/pacotes/sss-$VER.tar.gz -C $NOVO
ls $NOVO/applications                                                # somente script_scheduling_service

# 2. config.ini: copiar o atual e converter (chave removida, retenção do log e chaves opcionais novas)
cp $SSS/web2py/$APP/instance/config.ini $NOVO/$APP/instance/config.ini
chmod 640 $NOVO/$APP/instance/config.ini
sed -i -e '/^base_script_dirs\{0,1\} *=/d' \
       -e 's|^app_log_backups *=.*$|app_log_retention_days = 30|' \
       -e '/^work_dir *=/a exec_users =\nexec_work_dir =' \
       -e '/^cron_horizon_days *=/a queue_aging_min = 60\nlog_dir_min_livre_mb = 1024' \
       -e '/^script_owner_uids *=/d' -e '/^ambientes_exigem_hash *=/d' \
       -e '/^session_idle_timeout_s *=/a session_max_hours = 12' \
       -e '/^purge_batch_size *=/a purge_user =' $NOVO/$APP/instance/config.ini
grep -nE '^(base_script|app_log_|cron_horizon_days)' $NOVO/$APP/instance/config.ini
# esperado: app_log_max_bytes, app_log_retention_days = 30 e cron_horizon_days = 1461 (mínimo novo: 1461)
diff <(grep -oE "^[a-z_]+ =" $NOVO/$APP/instance/config.ini.example | sort) \
     <(grep -oE "^[a-z_]+ =" $NOVO/$APP/instance/config.ini | sort) && echo "chaves OK"

# 3. Verificar o código novo (não usa a porta; o SSS atual segue no ar)
cd $NOVO/$APP
$PY scripts/check_env.py; echo "codigo: $?"                         # 0
$PY -m unittest discover -s scripts -p "test_*.py" 2>&1 | tail -3     # Ran 819 tests ... OK (skipped=23)

# 4. Teste de carga da configuração (§10) na pasta nova
cd $NOVO && umask 077
# Python puro, sem o shell do web2py (CR-021c): a mesma configuracao que a web carrega.
$PY -c 'import sys; sys.path.insert(0, "applications/script_scheduling_service/modules"); import sss_config; c = sss_config.get_config("sss_web"); print("SSS: configuracao OK (sss_env=%s, owner=%s, prefixo=%s, agent_id=%s)" % (c.app.sss_env, c.oracle.owner, c.oracle.table_prefix, c.agent.agent_id))' 2>&1 | grep -E "^SSS:|ConfigError"
# esperado: SSS: configuracao OK (sss_env=DEV, backend=FAKE, agent_id=srv3067-sss-hml)

# 5. Conferir que os scripts de operação usam o caminho $SSS/web2py e exportam um locale UTF-8
grep -n "web2py\|sss_web.log\|LANG\|LC_ALL\|sss-web.sh" $SSS/start_sss.sh $SSS/stop_sss.sh
# Se o start_sss.sh não passar pelo bin/sss-web.sh nem exportar LANG/LC_ALL UTF-8, a subida é recusada
# (CR-007, R-17): acrescente "export LANG=C.UTF-8 LC_ALL=C.UTF-8" antes do comando do web2py.
# Pacote sem web2py (CR-021f): o comando passa a ser "bin/sss-web.sh <python3> --host 127.0.0.1 --port 18000".

# 6. Trocar a versão (parada de ~1 minuto)
$SSS/stop_sss.sh
mv $SSS/web2py $SSS/web2py-fdf6f35 && mv $NOVO $SSS/web2py
$SSS/start_sss.sh

# 7. Validar
curl -s -o /dev/null -w "login: HTTP %{http_code}\n" http://127.0.0.1:18000/script_scheduling_service/default/login     # 200
curl -sI http://127.0.0.1:18000/script_scheduling_service/default/login | grep -icE "content-security-policy|x-frame-options|x-content-type-options|referrer-policy"   # 4
curl -s -o /dev/null -w "origem estranha: HTTP %{http_code}\n" -X POST -H "Origin: http://outro-host" http://127.0.0.1:18000/script_scheduling_service/default/login   # 403
find $SSS/logs/internal/app -name 'sss_web_*.log' -type f | xargs grep -c CRITICAL   # 0 em cada arquivo
tail -n 5 $SSS/logs/server.out
```

Depois, pelo túnel (§22.4), faça o teste de fumaça do §12 e, se quiser, os casos CT-24 e CT-25 do manual v2.5 (reinicie o servidor no fim de cada um para restaurar o seed).

**Retorno (rollback), se algo falhar no passo 7:**

```bash
$SSS/stop_sss.sh
mv $SSS/web2py $SSS/web2py-$VER && mv $SSS/web2py-fdf6f35 $SSS/web2py
$SSS/start_sss.sh
```

A versão anterior fica intacta em `$SSS/web2py-fdf6f35`, com o `config.ini` antigo. Apague essa pasta só depois do aceite da homologação. Depois da atualização, troque neste capítulo o commit do §22 para `17950fb` e registre a validação no §22.5.
