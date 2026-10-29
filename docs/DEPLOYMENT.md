# SSS — Guia de Implantação e Operação (Linux/Unix)

Guia para instalar, operar e investigar falhas do SSS **lendo os logs**, por quem não participou do desenvolvimento. Vale para servidores POSIX (Linux e Unix, CR-005) sem acesso à internet.

O README.md é a especificação. Quando este guia e o README divergirem, vale o README; avise a equipe para corrigir o guia.

**O cenário do guia (CR-032, D15):** sem administrador. **Um usuário do sistema operacional** e **um usuário de banco** fazem tudo: sem root, sem `sudo` e sem `systemd`; os processos ficam no ar pelo `cron` da própria conta. Há só DEV e PROD, com o **mesmo comportamento** (CR-032, D11); a diferença é a pasta `<TIPO>` e o que se pode desenvolver no DEV. O registro do que saiu daqui (instalação anterior ao CR-028, notas daquele formato e os registros de servidores antigos) está em `docs/architecture/DEPLOYMENT-history.md`.

**Roteiro por servidor:** para instalar num servidor concreto, use o modelo `docs/DEPLOYMENT-SERVER.md`. Os valores do servidor ficam num arquivo `sss_vars.sh`, e os passos seguem este guia; o Apêndice A dele é o servidor `brtlvlty3067sl`.

**Marcas de validação:**
* **[ensaiado]:** executado a partir do pacote extraído (F9.1d, 2026-10-21; CR-031, 2026-10-27) contra o Oracle de homologação (GFPR).
* **[não ensaiado]:** sintaxe conferida, mas ainda não executado. Valide antes de usar em produção.

---

## 1. Visão geral

### 1.1 Componentes

```text
 usuários ── HTTP(S) ──> nó web (run_web.py, bin/sss-web.sh) ──────────────────┐
                                                                           ├──> Oracle (owner do esquema, tabelas tbsss_*)
 cron ──> sss-keepalive.sh ──┐                                             │
 cron ──> health.py ──────────┼──> agente (bin/sss-scheduler.sh) ───────────┘
                             │       └── script do usuário (com a conta do agente)
```

* **Nó web:** telas, cadastros e disparo de tickets. Não executa scripts.
* **Agente:** daemon (`scripts/run_scheduler.py`) que desdobra os agendamentos, reserva os tickets (claim), executa os scripts com a própria conta (CR-032, D7: sem `sudo` nem helper), coleta o log e mantém o heartbeat. Pode haver vários agentes, no mesmo servidor ou em outros; cada ticket roda em um só.
* **Keepalive** (`bin/sss-keepalive.sh`, CR-030) e **saúde** (`scripts/health.py`): chamados pelo `cron` da conta. Não há purge: a limpeza é manual (README §11.3, §12).

### 1.2 Contas

| Conta | Para quê | Onde fica a senha |
|---|---|---|
| Conta do sistema operacional (uma só) | Roda o web, os agentes, o keepalive, o `health.py` e os scripts | — |
| Conta de banco (uma só) | Dona do esquema e conta da aplicação: web e agentes (CR-032, D11: a conta igual ao owner é aceita) | `[oracle] password` do `instance/secrets.cfg` |
| Contas dos bancos dos scripts | Cada ambiente tem a sua; os scripts as recebem pelas variáveis do README §8.6 | `[environment:<NOME>]` do `instance/secrets.cfg` |

O `health.py` usa a conta do processo do `--name` (CR-032, D8: não há papel monitor). Contas separadas por papel (web e agente) no mesmo servidor precisam ter a mesma senha, porque o `secrets.cfg` tem um só `[oracle] password` (CR-032, D20); os privilégios delas estão no README §11.1 e saem do gerador de scripts SQL (§5.2).

### 1.3 Ordem do procedimento

```text
 1. Requisitos ......................... §2     9. Scripts cadastrados ........... §9
 2. Pacote ............................. §3    10. Subida e parada .............. §10
 3. Conta, pastas e roteiro ............ §4    11. Validação pós-subida ......... §11
 4. Banco ............................... §5    12. Limpeza manual ............... §12
 5. Driver Oracle ...................... §6    13. Monitoração .................. §13
 6. Configuração ....................... §7    14. Logs ......................... §14
 7. Pastas dos processos ............... §8    15. Problemas e soluções ......... §15
                                               16 a 20. Rotações, backup, atualização, checklist, desinstalação
```

**Convenções:**
* Todos os comandos rodam com a conta do SSS, na `<RAIZ>`, salvo indicação.
* **`<RAIZ>`** = `/portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service`, com `<TIPO>` = `DEV` ou `PROD`. A estrutura dentro da raiz é **idêntica** nos dois (CR-028, D1); o `<TIPO>` aparece na tela e no log de subida (CR-032).
* **Processos e nomes (CR-028):** cada processo tem um nome, o mesmo em todo lugar: `web0001`, `web0002`... para os nós web e `agente0001`, `agente0002`... para os agentes. O nome do agente é o `agent_id`, **único em toda a instalação** (não repita um número em outro servidor).

**Estrutura de pastas (CR-028)**, igual em DEV e PROD:

```text
<RAIZ>/                                 # dono: a conta do SSS
├── bin/  scripts/  src/  docs/         # código: trocado a cada atualização (bin/sss-update.sh, §18)
├── AGENTS.md  README.md  SHA256SUMS
├── instance/                           # PRESERVADO na atualização
│   ├── exemplos/                       # modelos (vêm no pacote)
│   ├── common.ini  secrets.cfg         # do servidor: [oracle] comum (D18) e segredos (D14)
│   ├── web0001/      config.ini        # do nó web
│   ├── agente0001/   config.ini        # de cada agente
│   └── agente0002/   config.ini
├── var/                                # PRESERVADO; de preferência numa partição própria (§4.3)
│   ├── web0001/      logs/  tmp/
│   ├── agente0001/   logs/  works/  outputs/  inputs/  script_works/  files/
│   ├── agente0002/   logs/  works/  outputs/  inputs/  script_works/  files/
│   └── update/<data>/retorno/          # pacotes de retorno do sss-update.sh
└── scripts_ambiente/                   # PRESERVADO: scripts dos ambientes (script_base_dir padrão)
```

| Caminho | Conteúdo | Modo | Origem no `config.ini` |
|---|---|---|---|
| `<RAIZ>` | Pacote extraído (código) | `0750` | — |
| `<RAIZ>/instance/common.ini` | O `[oracle]` comum a todos os processos do servidor (CR-032, D18) | `0640` | — |
| `<RAIZ>/instance/secrets.cfg` | Segredos do servidor, um arquivo só (CR-032, D14) | `0600` | — |
| `<RAIZ>/instance/<nome>/config.ini` | Configuração do processo (sem segredos) | `0640` | — |
| `<RAIZ>/var/<nome>/logs` | Logs da aplicação e dos scripts | `0750` | do nome |
| `<RAIZ>/var/<agente>/works` | Trabalho do agente (trava, `.stop`, pastas dos tickets) | `0700` | do nome |
| `<RAIZ>/var/<agente>/outputs` | Saída dos scripts (CR-012) | `0755`; abaixo, `0700` | padrão de `[agent] output_dir` |
| `<RAIZ>/var/<agente>/inputs` | Entrada dos scripts, uma subpasta permanente por script (CR-014) | `0755`; abaixo, `0700` | padrão de `[agent] input_dir` |
| `<RAIZ>/var/<agente>/script_works` | Pasta de trabalho dos scripts, uma por ticket (CR-019) | `0755`; abaixo, `0700` | padrão de `[agent] script_work_dir` |
| `<RAIZ>/var/<agente>/files` | Pasta de arquivos só em disco: `<ambiente>/<script>/inputs` e `outputs`, permanentes (CR-037; README §5.11 e §8.16) | `0755`; abaixo, `0700` | sempre do nome (sem chave) |
| `<RAIZ>/var/<web>/tmp` | Temporário dos envios do web acima de 1 MiB, da Entrada e da Pasta de Arquivos (CR-037, D6) | `0700` | sempre do nome (sem chave) |
| `<RAIZ>/scripts_ambiente` | Scripts dos ambientes | `0755` | padrão de `[agent] script_base_dir` |

Tudo pertence à conta do SSS. As pastas saem do nome do processo, sem precisar escrevê-las, e são criadas na subida (CR-028, D5; CR-032, D12; README §12.1). Uma chave escrita no `config.ini` vale no lugar do padrão; escrita vazia (ex.: `output_dir =`) desliga a função.

---

## 2. Requisitos

| Item | Requisito |
|---|---|
| Sistema operacional | Linux x86_64 ou outro Unix POSIX (CR-005). Validado em Oracle Linux 6.9 e Ubuntu 24.04 |
| Python | **3.6.0 ou superior** (referência de produção: 3.6.8). Só a biblioteca padrão, mais o driver Oracle. Não use `pip install` no servidor |
| Driver Oracle | `python-oracledb` (`< 2.0` no Python 3.6; `2.x` no 3.7+) e `cx_Oracle 8.3` como contingência, **pré-instalados** pela infraestrutura (AGENTS §2.2), com o **Oracle Instant Client 19.x**. A biblioteca `cryptography` não é usada (o modo Thin fica fora de uso; `driver_mode = thick`) |
| Oracle Instant Client 19 | **Obrigatório se algum banco for 11g** (o modo Thin não conecta ao 11g: `DPY-3010`); recomendado sempre, como contingência da cadeia de driver (§6). Registrado no `ldconfig` |
| Banco | Oracle 11gR2 (11.2.0.4) ou superior, charset AL32UTF8, servidor **sem horário de verão** (UTC recomendado) e NTP em modo *slew* em todas as instâncias (README §7.1) |
| Rede | Dos nós web e agentes até o listener Oracle. Dos usuários até a porta do web, quando ele atende num endereço da rede (§10.4) |
| Relógio dos servidores | NTP ativo. O fuso vem de `SSS_TZ` no launcher (§10) |
| Ferramentas | `tar`, `sha256sum`, `curl` e o `cron` da conta |

---

## 3. Pacote de implantação [ensaiado]

O pacote é gerado na máquina de desenvolvimento, a partir de uma cópia **limpa** do repositório. Uma árvore de trabalho sempre tem `__pycache__` e o `secrets.cfg` local, e o `package.py` a recusa (README §12.2).

```bash
# na máquina de desenvolvimento, no commit a implantar
mkdir -p /tmp/sss-limpo && git archive HEAD | tar -x -C /tmp/sss-limpo
python3 /tmp/sss-limpo/tools/package.py --source /tmp/sss-limpo --out-dir /tmp/sss-dist
# esperado: "Pacote: .../sss-<versao>.tar.gz" e "SHA256SUMS: .../SHA256SUMS"; código 0
```

Na máquina de desenvolvimento, `make package` faz o mesmo (cópia do `HEAD` por `git archive` e `package.py`) e grava o pacote, o `SHA256SUMS` e o `COMMIT` em `.bkp/pacote_<data>/` (usado no CR-035).

O `package.py` fica em `tools/` desde o CR-022b2 (antes, `scripts/`): é ferramenta de build e não vai no pacote. Ensaiado de novo no CR-021f3, já sem web2py: o `package.py` não grava `__pycache__` na cópia que empacota (antes, o próprio `__pycache__` recusava o pacote). Com código 1, a saída diz o que foi recusado ("Pacote recusado:" e uma linha por problema, com arquivo e linha, nunca o valor). O caso comum é um `password` ou `cookie_key` que não é `CHANGE_ME` no `instance/secrets.cfg.example`.

Leve os dois arquivos (`sss-<version>.tar.gz` e `SHA256SUMS`) ao servidor e confira. Na **primeira instalação**:

```bash
# com a conta do SSS, na pasta onde estão os dois arquivos
sha256sum -c SHA256SUMS                                     # esperado: "sss-<versao>.tar.gz: OK"
mkdir -p /portaloptrib/TESHUVA/SSS/<TIPO>                    # se ainda nao existir
cd /portaloptrib/TESHUVA/SSS/<TIPO>                          # a pasta de cima da <RAIZ>
tar -xzf <pasta do pacote>/sss-<versao>.tar.gz
mv sss-<versao> script_scheduling_service                    # a <RAIZ>
chmod 0750 script_scheduling_service                         # o tar segue o umask (0755 com 022); §1.3 pede 0750
cd script_scheduling_service && sha256sum -c --quiet SHA256SUMS && echo "conteúdo confere"
ls                                                          # esperado: AGENTS.md README.md SHA256SUMS bin docs instance scripts src
```

Nas **atualizações** seguintes, não extraia por cima: use o `bin/sss-update.sh` (§18), que preserva `instance/`, `var/` e `scripts_ambiente/`.

O pacote só tem o `bin/` e a aplicação (o código, os templates e os estáticos ficam em `src/sss/`, CR-022b): sem web2py (CR-021f), sem `src/sss/web/controllers/dev.py`, sem o FAKE (`src/sss/persistence/fake/`), sem testes e sem `docs/homologation/` (evidências e manual de homologação, que ficam no git; CR-033, D3: o pacote tem cerca de 3 MB). O servidor web é o `scripts/run_web.py` da própria aplicação, e a raiz `/` leva ao login.

---

## 4. Conta, pastas e roteiro

### 4.0 Roteiro de instalação (um usuário de SO e um de banco) [ensaiado no CR-031]

1. **Pacote (§3)** extraído na `<RAIZ>` com a conta do SSS.
2. **Banco (§5):** a conta única é a **dona do esquema**. Não há GRANT a aplicar (pule o `03_grants`); o `init_db.py --name agente0001` precisa de `--real-schema`, porque o esquema não é descartável (§5.3).
3. **Configuração (§7):** um `instance/common.ini` com o `[oracle]` (conta única, DSN, owner e prefixo), um `instance/secrets.cfg` com `[oracle] password`, `[web] cookie_key` e os `[environment:<NOME>]` dos ambientes atendidos (os bancos que os scripts usam têm usuários próprios), e um `instance/<nome>/config.ini` por processo, com `[app] name` igual ao nome da pasta.
4. **Pastas:** nada a fazer. Na subida, o web e o agente criam as que faltarem em `var/<nome>/` e `scripts_ambiente/` (CR-032, D12), com uma linha `pasta criada` no log para cada pasta do agente (o `log_dir` é criado sem essa linha).
5. **Subida e permanência (§10.6):** `bin/sss-keepalive.sh` no `crontab` da conta, com `@reboot` e a cada 5 minutos.
6. **Monitoração (§13)** e **limpeza manual (§12, README §11.3)** pelo mesmo `crontab`.

Exemplo de `crontab -e` da conta, com os usuários entrando direto por HTTP na porta 18000 (§10.4; troque `<TIPO>`, a porta e o Python):

```text
PYTHON=/usr/bin/python3
SSS_TZ=America/Sao_Paulo
R=/portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service
@reboot      cd $R && bin/sss-keepalive.sh web0001:0.0.0.0:18000 agente0001
*/5 * * * *  cd $R && bin/sss-keepalive.sh web0001:0.0.0.0:18000 agente0001
*/5 * * * *  cd $R && $PYTHON scripts/health.py --name agente0001 > var/agente0001/logs/health.txt 2>&1
# Com um agente por ambiente (§7.1; ensaiado no CR-039), os cinco nomes nas duas linhas do keepalive; um
# health.py basta (ele olha todos os agentes e todos os ambientes):
# @reboot     cd $R && bin/sss-keepalive.sh web0001:0.0.0.0:18000 agente0001 agente0002 agente0003 agente0004 agente0005
# */5 * * * * cd $R && bin/sss-keepalive.sh web0001:0.0.0.0:18000 agente0001 agente0002 agente0003 agente0004 agente0005
15 2 * * *   cd $R && find var/*/logs var/*/outputs var/*/script_works -mindepth 7 -maxdepth 7 -type d -mtime +30 -exec rm -rf {} + ; find var/*/logs var/*/outputs var/*/script_works -mindepth 3 -type d -empty -delete
```

* **Risco aceito (README §14):** os scripts rodam com a mesma conta do agente e podem ler o `secrets.cfg`, o `common.ini`, os `config.ini` e os logs do SSS, além de alterar o código. Quem cadastra um script tem o poder dessa conta. E a conta do banco, sendo a dona do esquema, pode alterar qualquer objeto dele.
* **Comportamento único (CR-032, D11)**, o mesmo em DEV e PROD:

| Item | Como fica |
|---|---|
| Conta Oracle | Pode ser a dona do esquema; guarde a senha como a do dono do esquema |
| Segredos | Um `secrets.cfg` por servidor (§7.2); cada processo usa só o que precisa. Ambiente atendido sem `[environment:<NOME>]` recusa a subida do agente |
| Cookie de sessão | `Secure` só quando a requisição chega por HTTPS; com acesso por HTTP, o cookie vai sem `Secure` |
| Origem | `allowed_origins` e a do próprio `Host` da requisição |
| Scripts dentro da raiz | Recusados, salvo `scripts_ambiente/` e `dev/` onde ela existe; o pacote não leva `dev/`, então não crie essa pasta na `<RAIZ>` |
| `init_db.py` | Recusa um esquema que não é descartável sem `--real-schema` (§5.3) |

* **Ambiente na tela (CR-028, D12; CR-032):** a faixa "Ambiente ... — dados e execuções não produtivos", o rodapé, o `[DEV]` no título da aba e a cor do cabeçalho vêm do nome da pasta `<TIPO>` acima da raiz. Em `PROD` a faixa não aparece; o cabeçalho tem outra cor só em `DEV`. O web e o agente registram na subida `ambiente da instalacao: <TIPO> (<raiz>); [oracle] de <arquivo>`.
* A tela de DEV (`/dev/...`) não existe numa instalação feita pelo pacote, que não leva o `dev.py` (§3).

### 4.1 Raiz compartilhada por vários servidores [não ensaiado]

A mesma `<RAIZ>` pode ser montada em vários servidores (pasta de rede) e servir a vários agentes e webs em cada um, com os mesmos fontes, o mesmo `common.ini`, o mesmo `secrets.cfg` e o mesmo `scripts_ambiente/`. Não é preciso uma pasta por servidor: cada processo tem as suas pastas porque elas saem do nome (`instance/<nome>/`, `var/<nome>/`). Exemplo:

```text
<RAIZ>/instance/common.ini, secrets.cfg      # comuns a todos os servidores
<RAIZ>/instance/web0001/                     # roda no servidor A
<RAIZ>/instance/agente0001/  agente0002/     # rodam no servidor A
<RAIZ>/instance/agente0003/                  # roda no servidor B
<RAIZ>/instance/agente0004/  agente0005/     # rodam no servidor C
```

Regras:

1. **Nome único por processo** em toda a instalação (`agente0001`, `agente0002`...; `web0001`, `web0002`...). Dois processos com o mesmo nome dividiriam `var/<nome>/`.
2. **Cada agente roda sempre no mesmo servidor, e só no cron dele.** O `crontab` de cada servidor lista só os seus nomes (no exemplo, `bin/sss-keepalive.sh agente0003` só no servidor B). O keepalive só enxerga os processos da própria máquina: com o mesmo nome no cron de dois servidores, os dois tentam subir o agente; o banco recusa o segundo (`agent_id` duplicado, código 16, §15.1), mas o keepalive insiste a cada 5 minutos.
3. **Não mude um agente de servidor com ticket rodando.** Na subida, o agente procura os processos órfãos dos seus tickets só na máquina local. Para trocar de servidor: `bin/sss-keepalive.sh --pause <nome>` e `bin/sss-stop.sh <nome>` no servidor antigo (a parada termina os tickets), tire o nome do cron dele, ponha no cron do novo e só então `--resume`.
4. **Atualização com tudo parado em todos os servidores.** O `bin/sss-update.sh` troca o código de todos de uma vez, e a conferência de "processo do SSS rodando" que ele faz é local. Antes de atualizar (§18.1), pause e pare os processos de **todos** os servidores, não só os do servidor em que você roda o comando.
5. **`secrets.cfg` com todos os ambientes.** Ele precisa ter o `[environment:<NOME>]` de todos os ambientes atendidos por qualquer agente da raiz: o agente sem a credencial do seu ambiente não sobe (CR-032, D11).
6. **A mesma conta, com o mesmo UID, em todos os servidores.** O `secrets.cfg` exige dono igual ao usuário do processo e modo `0600`, e as pastas são `0700`/`0750`: com UIDs diferentes, a subida é recusada (código 12 ou 13, §15.1).
7. **Webs com nome e porta próprios.** Dois webs no mesmo servidor precisam de portas diferentes (`web0001:0.0.0.0:18000`, `web0002:0.0.0.0:18001` no keepalive); o `[web] allowed_origins` de cada um traz a URL pela qual os usuários chegam a ele.

* **Trava de instância em pasta de rede:** a trava (`flock` em `var/<nome>/works/sss-<nome>.lock`) pode não valer entre máquinas num NFS. Com nomes únicos e a regra 2, isso não acontece; se acontecer (o mesmo nome em dois servidores), o banco barra o `agent_id` duplicado, mas a instância recusada já terá apagado um `.stop` pendente do agente legítimo e regravado o PID na trava: confira a regra 2 antes de pedir uma parada.
* **Desempenho:** os logs dos tickets e o log da aplicação são gravados em `var/`; numa pasta de rede lenta, prefira um `var/` com boa latência (§4.3).

### 4.2 Conta do sistema operacional

O SSS **recusa rodar como root** (os launchers saem com código 1 e o agente com o código 10). Use a conta que já existe no servidor; ela é dona da `<RAIZ>` inteira. Não há usuário de execução por ambiente, `sudo` nem helper (CR-032, D7); linhas antigas `exec_users`, `exec_work_dir` e `helper_path` no `config.ini` só geram aviso.

### 4.3 Partição dos logs (CR-008, R-25)

A pasta `<RAIZ>/var/` (onde ficam os `log_dir` de cada processo, `var/<nome>/logs`) fica de preferência num **sistema de arquivos próprio**, separado de `/`, e dimensionado para os dias de logs que você guarda até a limpeza manual (§12).

O agente para de fazer claim com menos de `[agent] log_dir_min_free_mb` livres (padrão 1.024 MB; linha `DISCO_LOG` no log, §15). O monitoramento corporativo deve alertar antes, por exemplo com 80% de uso.

### 4.4 Permissões que o SSS cria

O launcher aplica `umask 077`. O próprio SSS cria:
* pastas de log com `0750` (todos os níveis: `internal/`, `app/`, ano, mês, dia, hora e minuto);
* log da aplicação com `0640`;
* log de execução de cada ticket com `0600`.

---

## 5. Banco Oracle

### 5.1 Pré-requisitos do banco

* **Fuso e relógio:** servidor de banco sem horário de verão e NTP em *slew* (README §7.1). O SSS usa o `SYSDATE` como relógio de todas as decisões.
* **Sessões mortas:** `SQLNET.EXPIRE_TIME = 1` no `sqlnet.ora` do servidor de banco, para derrubar sessões perdidas que seguram lock.
* **Estatísticas:** job automático de estatísticas ativo para o esquema. O plano das consultas da fila depende delas (CR-013).
* **Espaço:** dimensione os LOBs pelo §5.5.

### 5.2 Scripts SQL e contas por papel [ensaiado no GFPR: ciclo 02 → 01 → 99]

Os três scripts saem do mesmo registro de identificadores, com o owner e o prefixo do `[oracle]`. Com contas separadas por papel, os GRANTs saem com elas (`--grants-to`); com a conta única, que é a dona do esquema, não há GRANT:

```bash
# na máquina de desenvolvimento ou num servidor com o pacote
cd <RAIZ>
python3 scripts/generate_sql.py --config instance/web0001/config.ini --grants-to web=sss_web,agent=sss_agente
# gera docs/sql/01_deploy_sss_<owner>_<prefixo>.sql, 02_rollback_sss_<owner>_<prefixo>.sql, 99_validate_deploy_<owner>_<prefixo>.sql e 03_grants_sss_<owner>_<prefixo>.sql
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

* O `01` para no primeiro erro (`WHENEVER SQLERROR EXIT FAILURE ROLLBACK`): sai com código diferente de zero e sem a mensagem "concluída com sucesso!". Com o `01` interrompido, rode o `02` antes de aplicá-lo de novo. O `02` e o `99` seguem com `WHENEVER SQLERROR CONTINUE`: procure `ORA-` e `SP2-` nos logs deles.
* O `99` só lê. As duas linhas de resumo precisam dizer `OK: nenhuma falha`.
* Com contas separadas, `sss_web` e `sss_agente` são criadas antes do `01`; com a conta única (§4.0), nenhuma conta nova. Nenhum GRANT vai para PUBLIC.
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
* **Saída dos scripts:** o zip fica no BLOB de `tbsss_ticket_output` até o ticket sair na limpeza manual: `tickets com saída por dia × zip médio × dias guardados × 1,3`. **Não há teto por ticket** desde o CR-036 (D3): uma saída grande (vários GB) vai inteira para o BLOB. Acompanhe o tablespace do esquema e combine com o DBA um alerta de espaço.
* Depois da limpeza manual (§12), o espaço volta ao segmento, não ao tablespace. Para devolvê-lo, o DBA usa `ALTER TABLE ... MOVE LOB` ou redefinição online numa janela.

---

## 6. Driver Oracle (CR-002) [ensaiado]

* `[oracle] driver_mode = auto` (padrão) tenta, na ordem, **Thin → Thick → cx_Oracle**, cada um numa sondagem isolada, e usa o primeiro que conectar. A sondagem usa a conta que vai conectar: o `[oracle] user` do processo (no `health.py`, o do `--name`).
* **Linha da combinação escolhida**, no log da aplicação de cada processo (ensaio, banco 19c):
  `INFO ... [action=INICIO] driver=oracledb modo=thin servidor=19.24.0.0.0 cliente=-`
  Com Thick ou cx_Oracle, `cliente=` mostra a versão do Instant Client (precisa ser 19). Registre essa linha no checklist (§19).
* **Conferência antes de subir:** `python3 scripts/check_env.py --name <nome>`, a partir de `W`. Ela confere os arquivos e **conecta ao banco** com a conta e os segredos do processo, mostrando o driver, o modo e as versões (CR-033, D6), e o orçamento da abertura da conexão (`AVISO` com `CONEXAO_ACIMA_DO_PRAZO` quando passa do `call_timeout_s`, §5.4). Código 0 = tudo OK (avisos não reprovam), 1 = falta arquivo ou o banco não conectou (linha `FALHA`, com o motivo), 2 = sem processo (`--name` nem `--config`) ou Python menor que 3.6.0.
* **Quando forçar:**
  * `driver_mode = thick` quando o banco é 11g. O Thin recusa com `DPY-3010` e a cadeia já pula para o Thick, mas forçar evita a sondagem a cada subida.
  * `driver_mode = cx_oracle` quando o `python-oracledb` não estiver disponível ou falhar nesse servidor.
* **Instant Client:** no Linux/Unix, ele precisa estar no `ldconfig` **antes** de o processo subir. Sem ele no `ldconfig`, defina `SSS_IC_DIR`: o launcher exporta `LD_LIBRARY_PATH` só nesse caso (README §12.2).

---

## 7. Configuração

### 7.1 `config.ini` [ensaiado]

Um `instance/common.ini` **por servidor**, com o `[oracle]` comum (CR-032, D18), e um `config.ini` **por processo**, em `<RAIZ>/instance/<nome>/`, a partir dos modelos do pacote (CR-028):

```bash
# na <RAIZ>; o common.ini uma vez, depois um bloco por processo
cp instance/exemplos/common.ini.example instance/common.ini && chmod 0640 instance/common.ini
mkdir -m 0750 instance/web0001
cp instance/exemplos/web0001/config.ini.example instance/web0001/config.ini && chmod 0640 instance/web0001/config.ini
mkdir -m 0750 instance/agente0001
cp instance/exemplos/agente0001/config.ini.example instance/agente0001/config.ini && chmod 0640 instance/agente0001/config.ini
```

O papel vem do próprio arquivo (CR-028, D4): o do web tem `[web]` e não tem `[agent]`; o do agente tem `[agent]` e não tem `[web]`. Cada um só tem o que o seu papel usa:

| Processo | Chaves a preencher |
|---|---|
| Servidor (`instance/common.ini`) | `[oracle]` (`user`, `dsn`, `owner`, `table_prefix`, `driver_mode`): o banco do SSS, comum ao web e aos agentes. Uma chave escrita no `[oracle]` do `config.ini` de um processo vale no lugar da comum |
| Web (`instance/web0001/`) | `[app] name` (o nome da pasta); `[web] allowed_origins` e, atrás de proxy, `trusted_proxies` |
| Agente (`instance/agente0001/`) | `[app] name` (o nome da pasta, que é o `agent_id`); `[agent] environments`, `max_parallel_jobs` |

As pastas (`log_dir`, `work_dir`, `output_dir`, `input_dir`, `script_work_dir`, `script_base_dir` e `files_dir`, CR-037) saem do nome e não precisam ser escritas. A tabela completa, com o padrão e a faixa de cada chave, está no README §12.1. **O próprio processo cria na subida as pastas que faltarem** (CR-032, D12): não há passo manual de pastas. `[agent] interpreters` não existe mais (CR-026): uma linha antiga só gera aviso. Dos valores de `[agent]`, o web usa só a `misfire_policy` (os demais são fixos desde o CR-032). Sem `[agent]` no config do web, vale o padrão. Se mudar a `misfire_policy` nos agentes, escreva o mesmo valor num `[agent]` do config do web, que só aceita essa chave e continua com o papel web (README §12.1). Em `instance/<nome>/`, o `[app] name` precisa ser o nome da pasta: ao copiar a pasta de um agente para criar outro, troque o `name`.

**Tempos que precisam ser idênticos em todos os agentes (README §8.9, D7):** desde o CR-032, os tempos de saúde e os ajustes do desdobro são fixos no código (`heartbeat_interval_s` 10, `fence_timeout_s` 90, `node_offline_timeout_s` 180, `kill_grace_s` 5, `misfire_tolerance_s` 300, `cron_horizon_days` 1461, `queue_aging_min` 60). O `critical_config` tem só `call_timeout_ms` e `misfire_policy` (CR-032, D16): escreva-os iguais em todos os agentes (ou deixe o padrão). Na troca desta versão, pare todos os agentes antes de subir o primeiro, porque o texto mudou. Cada agente registra na subida:

`INFO ... [action=INICIO] tempos do fencing: fence_timeout_s=90 node_offline_timeout_s=180`

Confira que a linha é igual em todos. Se um agente subir com valores diferentes dos que já estão ativos, ele é recusado (código 16, §15).

**Mais de um agente no mesmo servidor** (por exemplo, um por ambiente) [ensaiado no CR-039]: um `instance/<nome>/` para cada um, criado como acima a partir do `instance/exemplos/agente0001/config.ini.example`, com o seu `name` e o seu `environments`, e o nome de cada um na linha do keepalive. Na primeira subida, cada agente cria as suas pastas em `var/<nome>/` e se cadastra sozinho na tabela de agentes (`AGENT_START` na auditoria); um agente que já atendia vários ambientes e passa a atender um só tem a linha atualizada na subida. Um agente que cai ou é parado não afeta os outros, mas deixa o ambiente dele sem atendimento: o `health.py` dá `CRITICAL: ambiente X ativo sem nenhum agente saudavel` enquanto ele estiver fora (numa parada planejada, avise o monitoramento). Em vários servidores com a mesma raiz, veja o §4.1. As pastas não se misturam, porque saem do nome. Para só rodar mais scripts ao mesmo tempo, basta aumentar `max_parallel_jobs` de um agente.

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

## 8. Pastas dos processos

O web e o agente criam na subida as pastas que faltarem (CR-032, D12): `var/<nome>/logs` (`0750`), `var/<nome>/works` (`0700`), `outputs`, `inputs`, `script_works`, `files` e `scripts_ambiente` (`0755`); o web, `var/<web>/tmp` (`0700`, CR-037), o temporário de todo envio acima de 1 MiB, criado se faltar (sem a recusa com código 13). O web lê e grava em `var/<agente>/files` de cada agente que atende o ambiente: a tela Pasta de Arquivos só funciona com o web no mesmo servidor do agente ou na raiz compartilhada (§4.1). Uma pasta existente que não possa ser usada (arquivo no lugar, sem escrita, pasta do sistema) recusa a subida (código 13, §15). Não há helper de execução, `sudoers` nem usuário de execução (CR-032, D7): os scripts rodam com a conta do agente, em `var/<agente>/works/ticket_<id>/exec`, apagada no fim do ticket.

---

## 9. Scripts cadastrados (CR-005, CR-011, CR-023)

* O caminho cadastrado (`path_file`) é **absoluto** ou **relativo à pasta base** do agente (CR-023), em qualquer pasta fora das pastas do sistema (`/bin`, `/sbin`, `/usr`, `/lib*`, `/etc`, `/boot`, `/proc`, `/sys`, `/dev`, `/root`), fora das pastas do SSS (`log_dir`, `work_dir`, `output_dir`, `input_dir`, `script_work_dir` e `files_dir`) e fora da pasta da aplicação (a `<RAIZ>`, cujo código é trocado a cada atualização), **exceto** `<RAIZ>/scripts_ambiente/`, que a atualização preserva (CR-028, D3).
* **Pasta base (CR-023, CR-028):** `[agent] script_base_dir`, por padrão `<RAIZ>/scripts_ambiente/`. O agente junta o caminho relativo cadastrado (ex.: `faturamento/carga.py`) a ela e confere o resultado como um caminho absoluto; o arquivo real pode ficar fora da pasta base (link). A pasta pode ser diferente em cada servidor, mas **todo agente de um ambiente que tem script com caminho relativo precisa dela**: o ticket vai para qualquer agente do ambiente, e o agente sem pasta base termina o ticket em `PRECHECK_FAILED` (`NO_BASE_DIR`). Na subida, o log mostra a pasta base (INFO) ou avisa que ela não existe (WARNING); o painel de agentes mostra a de cada um. Os 14 scripts de demonstração do seed são cadastrados como `utilitarios/<arquivo>`.
* **Pasta de entrada (CR-014):** com `[agent] input_dir`, cada script recebe `SSS_INPUT_DIR` = `input_dir/<ambiente>/<nome do script em minúsculo, sem acento nem espaço>/` (ex.: "Carga Diária" em `PRODUCAO`, no `agente0001` → `<RAIZ>/var/agente0001/inputs/producao/carga_diaria/`). A pasta é criada na primeira execução e **nunca** é limpa pelo SSS: quem deposita os arquivos e o próprio script cuidam do conteúdo. Para depositar arquivos de fora, use a conta do agente (ou a tela de Entrada, CR-020).
* **Pasta de trabalho (CR-019):** com `[agent] script_work_dir`, cada ticket recebe `SSS_WORK_DIR` = `script_work_dir/<ambiente>/<script>/AAAA/MM/DD/HH/MI/ticket_<id>/`, criada antes da execução e mantida depois dela, para consulta no servidor do agente. O `HOME` e a pasta corrente do script continuam na pasta descartável `work_dir/ticket_<id>/exec`.
* Pode ser um link simbólico. O arquivo **real** precisa existir no servidor do agente, ser arquivo regular, ser legível pela conta do agente e **não** ter escrita de grupo nem de outros (`chmod go-w`).
* O conteúdo e a versão do script são controlados pelo ambiente: o SSS não confere hash nem dono (CR-011). Quem grava na pasta do script muda o que vai rodar.
* O nó web confere o formato do caminho e, no caminho absoluto, as pastas do sistema e a da aplicação (o relativo só pelo formato). A conferência do arquivo é feita pelo agente, antes de cada execução; uma recusa aparece como `PRECHECK_FAILED` (§15).
* **Interpretador (CR-025, CR-026, CR-027):** o cadastro guarda só o nome (`python`, `python3`, `sh` ou `bash`). Na execução vale, nesta ordem (CR-027): o interpretador digitado no disparo (caminho absoluto ou só o nome, ex.: `python3.13`), se existir no servidor; o `#!` da primeira linha do script, se o executável existir; o nome do cadastro, com `python` e `python3` servindo um ao outro. Quem não existe é pulado, com uma linha `[SSS]` no log do ticket. Os nomes são procurados no `PATH` herdado pelo **processo do agente**: o do `crontab` que roda o keepalive (§10.5) ou o do shell que rodou o `bin/sss-scheduler.sh`, que não o altera. **Confira esse `PATH` em cada servidor:** ele precisa achar `python3`, `bash` e os demais que os scripts usam. O agente atende qualquer interpretador; num servidor sem nenhum interpretador possível (o digitado, o do `#!` e o do cadastro, com a troca `python` ↔ `python3`), o ticket termina em `PRECHECK_FAILED` (`INTERPRETER_NOT_FOUND`). O agente só confere, com a conta dele, se o executável existe e é executável (não confere se ele está numa pasta do SSS: risco aceito, README §14), e o executa sem resolver links (o Python de um virtualenv funciona). `#!/usr/bin/env python3` funciona: o `env` procura o `python3` no `PATH` fixo do filho (`/usr/bin:/bin`, README §8.6), não no do agente, e o interpretador registrado como usado é `/usr/bin/env`. Um interpretador digitado que não existe é pulado (CR-027): vale o `#!` ou o cadastro, e o log do ticket registra a tentativa. **Risco aceito pelo responsável pelo produto:** quem pode disparar escolhe o programa que roda o script (o digitado vence o `#!`, CR-027), e, sem digitado, quem edita a primeira linha troca o interpretador sem passar pelo cadastro. O digitado fica no snapshot, em `tbsss_tickets.interpreter_path` e na auditoria do disparo; o usado, em `tbsss_tickets.interpreter_used` e na linha `[SSS] interpretador usado` do log (README §8.5).

---

## 10. Subida e parada

Os launchers recusam root, aplicam `umask 077`, exportam `TZ` (de `SSS_TZ`), `LANG` e `LC_ALL` (de `SSS_LOCALE`, padrão `C.UTF-8`) e `LD_LIBRARY_PATH` só sem o Instant Client no `ldconfig` (de `SSS_IC_DIR`). Também trocam para a raiz do repositório e fazem `exec` do processo Python. O Python vem de `PYTHON` (padrão `python3`).

Na operação, quem sobe os processos é o keepalive (§10.6); os comandos abaixo servem para conferir e investigar.

### 10.1 Nó web [ensaiado em DEV]

```bash
cd <RAIZ>
export PYTHON=/usr/bin/python3 SSS_TZ=America/Sao_Paulo
bin/sss-web.sh "$PYTHON" web0001 --check                      # CONFIG_OK ambiente=<TIPO>; nao abre a porta
bin/sss-web.sh "$PYTHON" web0001 --host 127.0.0.1 --port 8000  # instance/web0001/config.ini (CR-028)
```

* O servidor é o próprio do SSS (`scripts/run_web.py`, CR-021e), sem web2py: até 16 requisições ao mesmo tempo e 30 s de espera por conexão (fixos no código desde o CR-032). O `sss-web.sh` só inicia o `run_web.py`; `web2py.py` e `anyserver.py` são recusados (código 2).
* `--host 127.0.0.1`: só local, atrás do proxy ou do túnel. Para os usuários entrarem direto por HTTP, `--host 0.0.0.0` (ou o IP do servidor); na operação, pelo keepalive (§10.4).
* Não cria arquivos na raiz (`httpserver.log`, `httpserver.pid`, `parameters_<porta>.py`, `cron.master` e afins eram do web2py). Requisições, erros e a subida vão para o log da aplicação (`sss_web_<PID>.log`, §14.1); a saída padrão só recebe o que acontecer antes de o log abrir.
* Saída: 2 com configuração ou segredos inválidos (o motivo vai para o log), 3 com a porta em uso ou sem permissão.
* Para parar: `SIGTERM` ou `SIGINT` (Ctrl+C) ao processo Python. O servidor para de aceitar conexões, espera as requisições em andamento por até 30 s e sai com código 0.

### 10.2 Agente [ensaiado em DEV]

```bash
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
  parada solicitada: <RAIZ>/var/agente0001/works/sss-agente0001.stop
  ```
  O agente para na próxima iteração (no ensaio, em menos de 2 s; `WARNING ... [action=PARADA] encerramento TERMINATE: 0 execucao(oes) local(is)`) e remove o arquivo. O `sss-stop.sh` sai com código 2 se o `config.ini` for inválido.

### 10.4 Acesso dos usuários

* **Direto por HTTP (CR-032, D19):** na linha do keepalive, `web0001:0.0.0.0:18000` sobe o web em todas as interfaces (ou `web0001:<IP do servidor>:18000`, só nesse endereço). Os usuários abrem `http://<servidor>:18000/`. Ponha essa URL exata em `[web] allowed_origins`. Sem HTTPS, o cookie de sessão vai sem `Secure` (CR-032, D11) e a senha trafega sem criptografia na rede interna: risco aceito (README §14). Confira com a equipe de rede que a porta só é alcançável pela rede interna.
* **Só local (padrão):** `web0001:18000` atende só em `127.0.0.1`. Os usuários chegam por um proxy ou balanceador da empresa que repasse para `http://127.0.0.1:<porta>`, ou por túnel SSH: `ssh -N -L 18000:127.0.0.1:18000 <usuário>@<servidor>` e, no navegador, `http://localhost:18000/` (o próprio `Host` da requisição já vale como origem, CR-032 D11).
* **Proxy** [não ensaiado]: o limite de corpo dele precisa ser pelo menos `[web] input_upload_max_bytes` mais 64 KiB (tela de Entrada, CR-020d); o endereço dele vai em `[web] trusted_proxies`. Um proxy HTTPS precisa mandar `X-Forwarded-Proto: https`: sem isso, o web acha que a requisição chegou por HTTP e o cookie de sessão sai sem `Secure` (CR-032, D11).
* **Trocar o endereço de um web que já está no ar:** o keepalive confere só o nome, não o endereço. Depois de mudar a linha do cron (ex.: de `web0001:18000` para `web0001:0.0.0.0:18000`), pare o web (`--pause`, `SIGTERM` e `--resume`, §10.6) para ele subir de novo no endereço novo.

### 10.5 Variáveis dos launchers

| Variável | Uso | Padrão |
|---|---|---|
| `PYTHON` | Interpretador dos processos (3.6.0 ou superior, com o driver Oracle) | `python3` |
| `SSS_TZ` | Fuso exportado como `TZ` | o do sistema |
| `SSS_LOCALE` | `LANG` e `LC_ALL` (precisa ser UTF-8) | `C.UTF-8` |
| `SSS_IC_DIR` | Pasta do Instant Client, exportada em `LD_LIBRARY_PATH` só se ele não estiver no `ldconfig` (§6) | — |

No cron, defina-as no topo do `crontab` (§4.0). O agente procura os interpretadores dos scripts no `PATH` herdado (§9): o do cron é curto (`/usr/bin:/bin`), então acrescente `PATH=...` no `crontab` se os interpretadores estiverem em outra pasta.

### 10.6 `sss-keepalive.sh` no cron da conta (CR-030) [ensaiado]

O `bin/sss-keepalive.sh` mantém os processos no ar pelo cron da conta do SSS (§4.0):

```bash
# na <RAIZ>; o web precisa da porta (<nome>:<porta>, so local, ou <nome>:<endereco>:<porta>), o agente so do nome
PYTHON=/usr/bin/python3 SSS_TZ=America/Sao_Paulo bin/sss-keepalive.sh web0001:0.0.0.0:18000 agente0001
bin/sss-keepalive.sh --pause agente0001     # antes de parar de proposito: o keepalive nao sobe mais
bin/sss-stop.sh agente0001                  # para o agente
# para o web: SIGTERM no PID do python dele ([p] evita achar o proprio grep)
kill -TERM $(ps -eo pid,args | grep '[p]ython3 scripts/run_web.py --name web0001' | awk '{print $1}')
bin/sss-keepalive.sh --resume agente0001    # volta a subir na proxima passada
```

* Para cada nome, confere se há um `python` rodando `scripts/run_web.py` ou `scripts/run_scheduler.py` com `--name <nome>` a partir da `<RAIZ>`. Se não houver, sobe pelo launcher, em segundo plano (`nohup`), e grava em `var/<nome>/logs/keepalive.log` uma linha por subida, recusa ou falha. A saída do processo vai para `var/<nome>/logs/<nome>.out`.
* O papel vem do `config.ini` (`[web]` sem `[agent]`: web). O web atende em `127.0.0.1` ou no endereço da linha, na porta informada (§10.4); um endereço que não é IPv4 é recusado (`recusado: endereco invalido`, código 3).
* As linhas do `crontab` estão no §4.0 (`@reboot` e a cada 5 minutos). Recusa root (código 1) e uso inválido (2); sai com 3 se algum processo não subiu (veja o `.out`).
* Na atualização (§18.1), pause os processos antes de parar e retome depois de subir.
* Com a raiz compartilhada (§4.1), o keepalive de cada servidor só lista os nomes daquele servidor.

---

## 11. Validação pós-subida [ensaiado]

```bash
# no próprio servidor do web
curl -s -o /dev/null -w "raiz: HTTP %{http_code} -> %{redirect_url}\n" http://127.0.0.1:18000/
# esperado: raiz: HTTP 303 -> http://127.0.0.1:18000/script_scheduling_service/ (que leva ao login)
curl -s -o /dev/null -w "login: HTTP %{http_code}\n" http://127.0.0.1:18000/script_scheduling_service/default/login
# esperado: login: HTTP 200
curl -s -D - -o /dev/null http://127.0.0.1:18000/script_scheduling_service/default/login | grep -icE "content-security|x-frame|x-content|referrer"
# esperado: 4
curl -s -o /dev/null -w "origem estranha: HTTP %{http_code}\n" -X POST -H "Origin: http://evil.example" -d "x=1" http://127.0.0.1:18000/script_scheduling_service/default/login
# esperado: origem estranha: HTTP 403
curl -s -o /dev/null -w "admin: HTTP %{http_code}\n" http://127.0.0.1:18000/admin/default/index
# esperado: admin: HTTP 404
```

Depois:
1. Entre com o `admin` e troque a senha inicial (§5.3).
2. Em **Agentes**, confira que cada agente aparece como OK, com a plataforma, os ambientes e a pasta base esperados.
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
* **Arquivos:** os `find` para as pastas de minuto de `var/<nome>/logs`, `outputs` e `script_works`, primeiro só listando e depois apagando, e para os `.out` dos processos e os pacotes de retorno do `sss-update.sh`.
* **Pasta de arquivos** (`var/<agente>/files`, CR-037): sem procedimento (decisão D8 do CR-037). Os arquivos ficam até alguém apagar à mão; acompanhe o espaço da partição do `var/` (§4.3).
* **Pelo cron** da conta que roda o SSS, como no exemplo do §4.0. Comece listando (`-print`) e só depois troque por `-exec rm -rf {} +`.

---

## 13. Monitoração (`health.py`; README §13)

```bash
# na <RAIZ>; usa a conta e os segredos do processo do --name (CR-032, D8)
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
* **Agendamento:** pelo cron da conta, a cada 5 minutos, gravando a saída num arquivo (`var/<nome>/logs/health.txt`, exemplo no §4.0); o código de saída e a primeira linha dizem o estado. Um monitoramento corporativo pode ler esse arquivo. Com a raiz compartilhada (§4.1), basta um `health.py` para a instalação inteira: ele lê o estado de todos os agentes no banco.

**O que fazer em cada alerta:**

| Linha | Ação |
|---|---|
| `versao do esquema N, esperada M` | O banco e o pacote estão em versões diferentes: aplique a migração ou volte o pacote (§18) |
| `agente X ATIVO sem heartbeat ha N s` | O agente caiu ou perdeu o banco: veja o log dele (§14) e o §15.3. Depois de `node_offline_timeout_s`, outro agente finaliza os tickets dele como `NODE_OFFLINE` |
| `agente X em risco` | Heartbeat atrasado além do fence: o agente já deve ter se isolado (`FENCED`) |
| `ambiente X ativo sem nenhum agente saudavel` | Nenhum agente saudável atende o ambiente: suba um agente com o ambiente em `environments`, ou desative o ambiente. Com um agente por ambiente, é o que aparece logo que esse agente para (`sss-stop.sh`); um agente derrubado sem parar (`kill -9`, queda) continua contando como saudável até o heartbeat vencer |
| `fila sem atendente: N tickets de AMB/INTERP` | Nenhum agente saudável atende o ambiente (CR-026: o interpretador não conta mais; INTERP é o do cadastro): suba um agente para o ambiente ou confira os agentes em risco |
| `fila vencida: N tickets PENDING, espera maxima M min` | Agentes sem vaga: veja `max_parallel_jobs` e o teto por script, e os scripts presos em `RUNNING` |
| `ticket N RUNNING sem PID` | O agente reservou e não iniciou: veja o log do agente para esse ticket |
| `agente X com configuracao divergente` | `call_timeout_ms` ou `misfire_policy` diferentes entre os agentes: iguale e reinicie o agente |

---

## 14. Logs (CR-005, CR-009; README §8.4 e §13)

### 14.1 Onde ficam

| Log | Caminho | Modo |
|---|---|---|
| Aplicação (web, agente, `init_db`) | `log_dir/internal/app/AAAA/MM/DD/HH/MI/<nome>_<PID>.log`, com `<nome>` = `sss_web`, `sss_scheduler` ou `init_db` | `0640` |
| Execução de cada ticket | `log_dir/<ambiente>/<script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log` (ambiente e script em minúsculo, sem acento) | `0600` |
| Saída padrão dos processos | `var/<nome>/logs/<nome>.out`, pelo keepalive (§10.6) | — |

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

Linhas de alerta (CR-036), no arquivo de log local do ticket e na tela (a do log grande vai depois do marcador de truncado, D8): `[SSS] log local acima de <n> MB (alerta; o script continua)` e `[SSS] empacotamento da saida levou mais de 120 s (alerta; agente <id>)`; e, na saída, `[SSS] saida nao empacotada: falha (agente <id>)`. Toda finalização sem execução (pré-validação, falha ao iniciar, cancelamento antes do início) grava no log do ticket uma linha `[SSS] <evento>: <código> (agente <id>)`, visível na tela do ticket. Exemplo: `[SSS] pre-validacao recusada: GROUP_OTHER_WRITABLE (agente srv-linux-prod-01)`.

### 14.4 Saída padrão do nó web

Desde o CR-021e o servidor web não grava `httpserver.log`: requisições e erros vão para o log da aplicação, que troca de arquivo por tamanho (§14.1) e é limpo à mão (§12). A saída padrão só recebe o que acontecer antes de o log abrir (ex.: Python sem o pacote da aplicação) e fica pequena. O keepalive a grava em `var/<nome>/logs/<nome>.out`. Um `httpserver.log` que tenha sobrado da versão com web2py pode ser apagado.

---

## 15. Problemas e soluções

Procure a linha indicada no log da aplicação do processo (§14.2). As mensagens são as do código.

### 15.1 Subida do agente (códigos de saída; README §8.12)

| Código | Linha no log (`CRITICAL ... [action=INICIO] Subida abortada: …`) | Causa provável | Ação |
|---|---|---|---|
| 1 (launcher) | `Erro: execucao como root nao e permitida.` (stderr) | Executado como root | Suba com a conta do SSS |
| 10 | `o agente nao pode rodar como root (README §8.12 passo 1)` | Idem, sem o launcher | Idem |
| 11 | `configuracao invalida: Arquivo de configuracao nao encontrado: <caminho>` | `config.ini` ausente ou `--config` errado | §7.1 |
| 11 | `configuracao invalida: [secao] chave: <motivo>` | Chave ausente, desconhecida ou fora da faixa | Compare com o modelo de `instance/exemplos/`; uma chave retirada só gera aviso "apague a linha" (CR-036, D6) |
| 11 | `child_locale <x> nao consta em locale -a (CR-007, R-17)` | Locale do filho não instalado | Instale o locale `C.UTF-8` (fixo desde o CR-032) |
| 12 | `secrets.cfg invalido: <reason>` (ex.: `Arquivo de segredos possui permissoes inseguras (mode 644, ...)`, `... deve pertencer ao usuario corrente`, `Ambientes atendidos sem credencial em secrets.cfg: X`) | Modo, dono ou seções do `secrets.cfg` | `chmod 0600` e dono a conta do SSS (§7.2); com a raiz compartilhada, o mesmo UID em todos os servidores (§4.1) |
| 13 | `work_dir <pasta> recusado: <motivo>` (ou `output_dir`, `input_dir`, `script_work_dir`, `files_dir`) | A pasta existe mas não pode ser usada (arquivo no lugar, sem escrita, pasta do sistema); a que falta é criada na subida (CR-032, D12) | Corrija ou apague o que está no caminho e suba de novo |
| 13 | `<nome> <caminho> recusado: <código>` (`log_dir`, `work_dir`...), `output_dir ... recusado`, `input_dir ... recusado` e `script_work_dir ... recusado` | Pasta sem escrita ou nas pastas do sistema | §4 e §8 |
| 14 | `Outra instancia do agente ja esta em execucao (<work_dir>/sss-<agent_id>.lock)` | Outro agente com o mesmo `work_dir` e `agent_id` | Pare o outro, ou use `config.ini` próprio (§7.1) |
| 15 | `sem conexao com o Oracle` ou `banco: <erro>` (ex.: `Versao do esquema incompativel: esperada N, encontrada M`) | Banco inacessível, driver (§15.2) ou versão do esquema | §15.2, §15.3 ou a migração (§18) |
| 16 | `agent_id duplicado: ...` | Outro agente ativo com o mesmo `agent_id` (com a raiz compartilhada, o mesmo nome no cron de dois servidores) | Nome único; cada nome no cron de um servidor só (§4.1) |
| 16 | `config_criticos diverge do agente X: local=... remoto=...` e `configuracao critica diferente da dos outros agentes (CR-007, R-23)` | `call_timeout_ms` ou `misfire_policy` diferentes entre agentes, ou agente de versão anterior ao CR-032 ainda ativo | §7.1 e §18.2 |
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
| ↳ `SYSTEM_DIR`, `SSS_DIR`, `APP_DIR` | | Script nas pastas do sistema, nas do SSS (inclusive `output_dir`, `input_dir`, `script_work_dir` e `files_dir`, CR-014, CR-019 e CR-037) ou na pasta da aplicação (CR-023) | Mova o script e corrija o cadastro |
| ↳ `NO_BASE_DIR` | | Script com caminho relativo e **este** agente sem `[agent] script_base_dir` (CR-023) | Configure a pasta base no agente (§9) e suba de novo |
| ↳ `RELATIVE_PATH` | | Agente de versão anterior ao CR-023 diante de script com caminho relativo | Atualize todos os agentes do ambiente (§18) |
| ↳ `INTERPRETER_NOT_FOUND` | | Nenhum interpretador existe e é executável neste servidor (CR-027): nem o digitado no disparo, nem o do `#!`, nem o nome do cadastro (`python` e `python3` são tentados um pelo outro). Os nomes são procurados no `PATH` do agente; o log do ticket mostra uma linha `[SSS]` por tentativa pulada, antes da linha de recusa | Instale o interpretador, ajuste o `PATH` do serviço, corrija o `#!` ou dispare de novo com outro interpretador |
| ↳ `INTERPRETER_NOT_ALLOWED` | | O snapshot traz um interpretador fora da allowlist (ticket muito antigo ou gravado à mão) | Dispare de novo pela tela |
| ↳ `INTERPRETER_UNAVAILABLE`, `NO_SHEBANG`, `INTERPRETER_UNSAFE` | | Só de agente anterior ao CR-026 | Atualize os agentes (§18) |
| ↳ `UNSUPPORTED_VERSION` | | Ticket criado por uma versão anterior (snapshot antes da versão 5), ou agente anterior ao CR-026 diante de um ticket com snapshot versão 7 (ou anterior ao CR-025 com a 6) | Dispare de novo pela tela; no segundo caso, atualize os agentes (§18) |
| ↳ `REGISTRATION_CHANGED`, `SCRIPT_INACTIVE`, `NOT_HOMOLOGATED`, `ENVIRONMENT_INACTIVE`, `NO_PERMISSION` | | O cadastro mudou entre o disparo e a execução | Confira o cadastro e dispare de novo |
| ↳ `DB_ERROR: ORA-nnnnn` | `falha antes do spawn: DB_ERROR: ...` | Erro de banco na pré-validação | Veja o código ORA |
| `FAILED` / `SPAWN_ERROR` | `falha antes do spawn: <erro>` e `[SSS] falha ao iniciar: <erro> (agente X)` | Não foi possível criar o log ou o processo (disco, permissão) | Veja o erro; confira o §8 |
| `FAILED` / `LOG_LIMIT` (só tickets anteriores ao CR-036) | `encerramento pedido: LOG_LIMIT` | O log local passou de `max_local_log_size_bytes`; desde o CR-036 isso só gera o alerta `log local acima de <n> MB` e o script continua | Reduza a saída do script ou aumente o limite de alerta |
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
| `Socket 127.0.0.1:18000 in use by other process` | `var/web0001/logs/web0001.out` | Porta ocupada | `ss -ltnp \| grep :18000` |

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

* **`cookie_key`** (nó web): gere um novo (§7.2), grave no `instance/secrets.cfg` e reinicie todos os webs juntos. **Todas as sessões são invalidadas**; os usuários entram de novo.
* **Senha da conta Oracle** (a conta única do §4.0, ou `sss_web`/`sss_agente`): troque a senha no banco, grave a nova no `[oracle] password` do `instance/secrets.cfg` e reinicie os processos. Com a senha antiga, a cadeia de driver para em `ORA-01017` (§15.2).
* **Senha de ambiente** (`[environment:X]`): grave a nova no `instance/secrets.cfg` e reinicie os agentes que atendem o ambiente. A senha chega ao script pela variável `PADRAO_VALOR_RUN_CONEXAO_BD`, só na próxima execução.

---

## 17. Backup e restauração (CR-007, R-18; CR-008, R-18)

* **Backup:** o esquema (RMAN ou Data Pump do owner), a pasta `instance/` (com o `secrets.cfg`, em cofre) e os logs locais conforme a política da empresa.
* **Depois de restaurar o banco** (restore ou *flashback*): o banco volta a um instante anterior, mas os scripts executados depois dele já produziram efeito. Antes de religar qualquer agente:
  1. pare todos os agentes e anote o **instante de restauração** (o do backup ou do *flashback*);
  2. finalize como `FAILED`/`ORPHAN_PROCESS` os tickets `RUNNING` restaurados que têm PID (eles se referem a processos que não existem mais);
  3. **revise** os tickets `PENDING` e os `RUNNING` sem PID criados antes do instante de restauração. Compare com os logs locais dos agentes (`log_dir/<ambiente>/<script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log`), que sobrevivem à restauração. Os que já rodaram depois do backup são cancelados pela tela (auditado como `TICKET_CANCEL` com o login do operador), nunca apagados;
  4. para não repetir ocorrências de agendamento já cumpridas, configure temporariamente `misfire_policy = SKIP` em **todos** os agentes (o `critical_config` precisa ser igual em todos) e no `[agent]` do config do web (§7.1, para a tela de agendamentos) para a primeira subida; volte a `RUN_ONCE` depois que o primeiro desdobro avançar as regras;
  5. avance as sequences de `tbsss_tickets` e `tbsss_audit` acima do maior id visto nos logs locais e no log da aplicação. O DBA recria a sequence com `START WITH` maior; o 11g não tem `ALTER SEQUENCE ... RESTART`. Assim nenhum id se repete entre o banco e os arquivos locais;
  6. religue os agentes. O startup check limpa as pastas locais.

---

## 18. Atualização de versão e retorno [ensaiado no CR-031 e no CR-035]

### 18.1 Atualização no lugar (CR-028, D10)

O código é trocado **no lugar** pelo `bin/sss-update.sh`. `instance/`, `var/` e `scripts_ambiente/` não são tocados (de `instance/`, só `instance/exemplos/` é trocado):

1. Gere e confira o pacote novo (§3). Leia as notas da versão (§18.2) e, se o esquema mudou, combine a janela com quem roda o SQL.
2. Pare o web e **todos** os agentes: `bin/sss-keepalive.sh --pause <nome>` de cada um, `bin/sss-stop.sh` nos agentes e `SIGTERM` no web (§10.6). Com a raiz compartilhada (§4.1), em **todos** os servidores. Com SQL de migração, aplique-o agora (§5.2).
3. Atualize:
   ```bash
   # na pasta onde estão o pacote e o SHA256SUMS
   <RAIZ>/bin/sss-update.sh sss-<versao>.tar.gz
   # a última linha mostra o comando de retorno: <RAIZ>/bin/sss-update.sh <RAIZ>/var/update/<data>/sss-retorno-<data>.tar.gz
   ```
   O comando confere o pacote (`SHA256SUMS` externo e interno) e recusa root (código 1), pacote inválido ou sem permissão para criar `var/update/` (código 2, nada muda) e um `python` rodando um comando do SSS a partir da `<RAIZ>` neste servidor (código 3, nada muda). Ele guarda o código atual num pacote de retorno, no mesmo formato, em `var/update/<data>/`, e troca só `bin/`, `docs/`, `scripts/`, `src/`, `AGENTS.md`, `README.md`, `SHA256SUMS` e `instance/exemplos/`. A extração e o código anterior ficam em `<RAIZ>/.update-<data>/` (mesma partição da raiz: a troca é por renomeação), apagada no sucesso. Código 4: falha no meio da troca; o código anterior fica em `.update-<data>/anterior/` e o retorno é o pacote impresso.
   * **`bin/` é trocado inteiro:** um arquivo local que você tenha posto em `bin/` some (fica só no pacote de retorno). Guarde scripts próprios fora do código, por exemplo em `scripts_ambiente/`.
   * **Pacotes de retorno:** `var/update/<data>/` não é apagado sozinho. Depois de validar a versão nova, apague à mão os que não quiser guardar.
4. Compare o `instance/common.ini` e cada `instance/<nome>/config.ini` com os modelos novos (`diff instance/exemplos/agente0001/config.ini.example instance/agente0001/config.ini`). Chave obrigatória nova ou removida aparece na subida como `configuracao invalida` (§15.1); chave retirada só gera aviso.
5. Suba e valide (§11): `bin/sss-keepalive.sh --resume` de cada nome e uma passada do `sss-keepalive.sh` (ou espere a do cron).

**Retorno:** pare tudo de novo (como no passo 2) e rode o comando de retorno impresso no passo 3. Com migração de esquema, o retorno precisa também do SQL de retorno ou do backup do banco (§17).

### 18.2 Notas por versão (estrutura por processo)

Do mais novo para o mais antigo. Quem vem de uma versão anterior aplica na ordem cronológica. As notas da instalação anterior ao CR-028 (`/opt/sss/app`) estão em `docs/architecture/DEPLOYMENT-history.md`.

* **CR-037: Pasta de Arquivos, só em disco (sem mudança de esquema; muda o catálogo).**
  * Duas funcionalidades novas no catálogo, `FILES_UPLOAD` e `FILES_DOWNLOAD`, e no seed dos perfis `ADMINISTRATOR`, `OPERATOR_PROD` e `OPERATOR_HML`. Numa instalação nova, o `01_deploy` já as traz. **Num banco em uso, não rode o `init_db`**: ele refaz o seed inteiro e devolve ao padrão ambientes, parâmetros, scripts, perfis e usuários do seed (reativa e sobrescreve o que foi mudado pela tela). Aplique só os blocos `MERGE` das duas funcionalidades e das marcas dos três perfis, copiados do `docs/sql/01_deploy_sss_<owner>_<prefixo>.sql` da versão (procure por `FILES_UPLOAD` e `FILES_DOWNLOAD`), com `COMMIT` no fim.
  * Pastas novas, criadas na subida: `var/<agente>/files` (agente) e `var/<web>/tmp` (web). Chave opcional nova: `[web] files_upload_max_bytes` (1 GiB por padrão).
  * O script recebe `SSS_FILES_INPUTS_DIR` e `SSS_FILES_OUTPUTS_DIR`. A tela exige o web no mesmo servidor do agente ou na raiz compartilhada (§4.1, §8).
  * **Retorno:** o pacote de retorno; as funcionalidades novas ficam no banco, sem efeito na versão anterior (os perfis podem desmarcá-las).
* **CR-036: alertas no lugar de bloqueios (sem mudança de esquema).**
  * Log local do ticket acima de `max_local_log_size_bytes`: só alerta (`[SSS] log local acima de <n> MB`); o script continua. Novos tickets não terminam mais em `FAILED/LOG_LIMIT`.
  * Os scripts herdam o limite de arquivos abertos da conta (antes, fixo em 1024); o *core dump* continua desligado.
  * A saída não tem mais limite de tamanho nem de arquivos: todo zip vai ao banco (§5.5; acompanhe o tablespace). `output_max_bytes` e `output_max_files` no `config.ini` só geram aviso; apague as linhas.
  * O prazo de 120 s do empacotamento e o da entrega de um arquivo da tela Entrada só alertam; o zip e a gravação terminam. Uma entrega travada (disco ou NFS pendurado) segura as seguintes até a parada do agente: o WARNING `entrega <id> passou de 120 s` é o sinal para investigar.
  * `[app] data_backend`, `[agent] script_owner_uids` e `ambientes_exigem_hash` só geram aviso (antes, recusavam a subida).
  * **Retorno:** o pacote de retorno. A versão anterior volta aos limites dela (20 MiB e 1.000 arquivos por saída, ou as linhas de `output_max_*`, se ainda estiverem no `config.ini`): uma saída maior volta a ficar `EXCEEDED`, e um log acima do limite volta a encerrar o script.
* **CR-033 e CR-034 (sem mudança de esquema nem de config).** Ensaiados no PROD de `5c0383d` para `e0030e7`, com retorno (CR-035).
  * O pacote não leva mais `docs/homologation/` (CR-033, D3): a pasta some do servidor na atualização.
  * `check_env.py --name <nome>` passa a **conectar ao banco** sempre (CR-034, D6), com uma linha do orçamento da conexão (`AVISO` não reprova); sem processo, sai com 2. Use-o antes da subida (§6).
  * `health.py` não grava mais `health_<PID>.log` com a configuração inválida (D7): o motivo fica só no `health.txt` do cron.
  * `[app] name` igual a `init_db`, `seed` ou `purge` é recusado também no web (D9); `sss-stop.sh --config` segue a mesma regra de nome (D10). Confira os nomes antes de atualizar.
  * **Retorno:** o pacote de retorno do `sss-update.sh`, sem SQL.

* **Pastas no plural (CR-032, 032e, D21).** As pastas que saem do nome do agente passam a `var/<nome>/works`, `inputs`, `outputs` e `script_works`. Na primeira subida da versão nova, o agente renomeia sozinho as anteriores (`work`, `input`, `output`, `script_work`), com a linha `pasta renomeada` no log; nada a fazer à mão. Ajuste os `find` da limpeza manual no `crontab` (§4.0 e §12). Com uma pasta escrita no `config.ini`, nada muda. A pasta `var/exec/` do helper (CR-028) não é mais usada e pode ser apagada.
* **CR-032: com tudo parado em todos os servidores.**
  * **`critical_config`:** passa a ser `call=<s>;misfire=<política>` (D16). Um agente novo convivendo com um antigo seria recusado (código 16); por isso, nenhum agente antigo pode estar ativo quando o primeiro novo sobe.
  * **Chaves retiradas, que só geram aviso** (apague as linhas):
    * no `config.ini`: `[app] sss_env` (D11), `[agent] exec_users`, `exec_work_dir`, `helper_path` (D7) e os ajustes finos que viraram fixos (README §12.1);
    * no `secrets.cfg`: a seção `[monitor]` (D8).
  * **Arquivos únicos do servidor:**
    * o `secrets.cfg` passa a ser um só, em `instance/secrets.cfg` (D14). O antigo, em `instance/<nome>/`, ainda é lido, com aviso para mover;
    * o `[oracle]` pode ir para `instance/common.ini` (D18; opcional, a chave do processo vence).
  * **Sem helper:** saem o `bin/sss-helper`, o usuário de execução e o `sudoers`. Se uma instalação antiga os tinha, apague `/etc/sudoers.d/sss`, a pasta `sss-root/` ao lado da `<RAIZ>` e `var/exec/` (com root).
  * **Sem monitor:** o `health.py` usa a conta do `--name`; a conta `sss_monitor` pode ser removida pelo DBA.
  * **Ambiente sem credencial:** agente com ambiente atendido sem `[environment:<NOME>]` não sobe mais, nem no DEV. Confira o `secrets.cfg` antes.
  * **Retorno:** a versão anterior volta a exigir o que ela usava (por exemplo, o helper e o `sudoers` dela fora de DEV).
* **Purge retirado (CR-030): com tudo parado.**
  * Saíram o comando `purge.py`, a conta e o papel `purge`, a seção `[retention]`, as retenções de `[logging]` e a limpeza automática dos logs da aplicação. A limpeza passa a ser manual (§12, README §11.3).
  * Tire do `cron` a linha do `purge.py` e, do monitoramento, o `--purge-days`. As linhas antigas do `config.ini` e o `[purge]` do `secrets.cfg` só geram aviso; apague-as.
  * O esquema perde as duas colunas da concessão. Num banco já instalado, aplique (troque `openrisow` e `tbsss_`):
    ```sql
    ALTER TABLE openrisow.tbsss_control DROP (purge_owner, purge_lease_until);
    ```
  * **Retorno:** a versão anterior precisa das colunas de volta (`ALTER TABLE openrisow.tbsss_control ADD (purge_owner VARCHAR2(40 CHAR), purge_lease_until DATE)`), das linhas de `[retention]` e do cron do purge.

---

## 19. Checklist pré-produção

- [ ] Estrutura por processo (CR-028): `<RAIZ>` = `/portaloptrib/TESHUVA/SSS/PROD/script_scheduling_service`, um `instance/<nome>/` por processo com `[app] name` igual ao nome da pasta, e nomes únicos em toda a instalação
- [ ] `instance/common.ini` com o `[oracle]` (CR-032, D18) e nenhum `config.ini` de processo repetindo o `[oracle]` sem motivo
- [ ] `instance/secrets.cfg` único, com `0600` e dono a conta do SSS, com o `[environment:*]` de todo ambiente atendido
- [ ] Nenhuma linha `[app] sss_env`, `data_backend`, `exec_users`, `exec_work_dir`, `helper_path`, `script_owner_uids`, `ambientes_exigem_hash`, `output_max_bytes`, `output_max_files`, `[retention]`, `*_retention_days`, `[purge]` nem `[monitor]` (só geram aviso)
- [ ] Espaço da partição do `var/` acompanhado também para a pasta de arquivos (`var/<agente>/files`), que não tem limpeza (CR-037, D8)
- [ ] Alerta de espaço do tablespace do esquema combinado com o DBA: o zip da saída vai inteiro para o banco, sem teto por ticket (§5.5, CR-036)
- [ ] Na tela, sem a faixa de ambiente e com o rodapé `Ambiente PROD`; no log de subida, `ambiente da instalacao: PROD`
- [ ] Limpeza manual combinada: quem roda o SQL do banco e o `find` dos arquivos, e com que frequência (§12, README §11.3)
- [ ] `[web] allowed_origins` com a URL que os usuários digitam (§10.4)
- [ ] `[logging] level = INFO`
- [ ] `call_timeout_ms` e `misfire_policy` iguais em todos os agentes (os demais tempos são fixos, CR-032)
- [ ] Combinação de driver registrada (linha `driver=... modo=... servidor=... cliente=...` de cada processo)
- [ ] `ls <RAIZ>` sem `dev/`, `applications/`, `gluon/` nem `web2py.py`; `src/sss/web/controllers/dev.py` ausente
- [ ] Com script de caminho relativo (CR-023): a pasta base existente e a linha `pasta base dos scripts` no log de subida e no painel de agentes (§9)
- [ ] Interpretador (CR-025, CR-026): o `PATH` do cron acha `python3`, `bash` e os demais interpretadores dos scripts (§9, §10.5)
- [ ] `<RAIZ>/var` em partição própria, com alerta de uso (§4.3)
- [ ] As pastas acima da `<RAIZ>` sem escrita de outros, ou com sticky bit (`stat -c '%a %U %n' /portaloptrib /portaloptrib/TESHUVA ...`): quem renomeia uma delas troca o código que a conta do SSS executa (revisão do CR-032). Sem root para corrigir, registre o risco com a infraestrutura
- [ ] Senha inicial do seed trocada (§5.3)
- [ ] `crontab` com o keepalive (`@reboot` e a cada 5 minutos), o `health.py` e a limpeza (§4.0); com a raiz compartilhada, cada servidor só com os seus nomes (§4.1)
- [ ] Backup do esquema e de `instance/` (§17)

---

## 20. Desinstalação

```bash
# na <RAIZ>, com a conta do SSS
crontab -e                                   # apague as linhas do SSS (§4.0)
bin/sss-keepalive.sh --pause web0001         # e cada um dos nomes
bin/sss-stop.sh agente0001                   # cada agente; o web: SIGTERM (§10.6)
# depois de guardar o que precisar de var/ (logs, saídas) e de instance/ (configuração, em cofre)
cd .. && rm -rf script_scheduling_service
```

O esquema do banco é removido com o `02_rollback_sss_<owner>_<prefixo>.sql` (§5.2), **depois** do backup.

---

## Apêndice A. DEV

O DEV é a mesma instalação, na pasta `DEV` (`<RAIZ>` = `/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service`), com o mesmo comportamento do PROD (CR-032, D11). O que muda é só o que se pode desenvolver:

* a `<RAIZ>` do DEV é o repositório git: tem `dev/` (scripts de exemplo em `dev/scripts`, usados como `script_base_dir`), os testes, a vitrine `/dev/...` e o FAKE dos testes, que o pacote não leva;
* a tela mostra `[DEV]` no título da aba, o cabeçalho em outra cor e a faixa de ambiente não produtivo;
* `bin/start_local.sh` e `bin/stop_local.sh` sobem e param o web na máquina de desenvolvimento e não vêm no pacote;
* a bateria Oracle (`SSS_TEST_ORACLE=1`) usa o `instance/common.ini`, o `instance/secrets.cfg` e o `instance/agente0001/` do DEV, com o DEV parado;
* **prefixo próprio no mesmo banco (2026-10-29):** o DEV usa `table_prefix = ssdev_` e o PROD `tbsss_`, no mesmo owner. Cada um tem as suas tabelas (agentes, fila, tickets, auditoria), então os dois podem ficar no ar ao mesmo tempo, mesmo com os mesmos nomes `web0001`/`agente0001` (substitui a regra do CR-033, D1). O esquema `ssdev_` foi criado pelo `init_db --real-schema`; o `docs/sql/` tem os scripts dos dois prefixos, com o prefixo no nome (`*_tbsss.sql` do PROD e `*_ssdev.sql` do DEV). No PROD, use só os `*_tbsss.sql`. Os `*_s3dev.sql` e `*_s3prd.sql` são das duas instalações do servidor 3067, com o roteiro próprio em `docs/DEPLOYMENT-SERVER.md`, Apêndice A.

Um DEV instalado pelo pacote não tem a vitrine `/dev/...` (o `src/sss/web/controllers/dev.py` não vai no pacote): ela responde 404, e o resto sobe normalmente (CR-021f3).
