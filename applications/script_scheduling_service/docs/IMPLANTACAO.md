# SSS — Guia de Implantação em Outro Servidor

| Campo | Valor |
|---|---|
| Público | Quem vai instalar e operar o SSS num servidor novo (infraestrutura, desenvolvimento, homologação) |
| Versão do sistema | 0.1.0 — commit de referência `3b9a065` ou posterior (fases F0.1 a F6.1, CR-003 a CR-008; limpeza da raiz do web2py e scripts de controle local em `bin/`). Os servidores dos §21 e §22 foram implantados inicialmente com o `fdf6f35` |
| Validação | Procedimento **ensaiado de ponta a ponta** em 2026-10-15 num clone limpo do repositório (Python 3.6.0 e 3.13) e **implantado** no mesmo dia no servidor clone 7 (Oracle Linux 6.9, Python 3.7 sem `ssl`, sem `sudo` nem `systemd` — registro no §21). A versão com o CR-003 e o CR-004 foi validada em 2026-10-16 na estação de desenvolvimento (suíte em Python 3.6.0, 3.6.8 e 3.13.2 e verificação das telas no navegador), mas ainda não foi reimplantada em servidor (§22). A versão com o CR-005 (somente POSIX, caminho absoluto do script e logs em pastas por minuto) foi validada em 2026-10-16 na estação (suíte em 3.6.0, 3.6.8 e 3.13.2). O que não foi ensaiado está marcado como **[não ensaiado]** |
| Documentos relacionados | `README.md` (regras de negócio e arquitetura), `AGENTS.md` (regras de desenvolvimento), `docs/AMBIENTE_DEV.md` (estação do desenvolvedor), `docs/homologacao/SSS_Manual_Homologacao_UI_Freeze.docx` (roteiro de homologação) |

---

## 1. Leia antes: o que dá para implantar hoje

O SSS está sendo construído em fases (`docs/prompts/00_INDEX.md`). Hoje está pronta a **interface web completa**, o **banco Oracle real com DDL/DML e scripts SQL autônomos (F7)** e a **árvore de scripts utilitários homologados**. O agente executor em produção (`run_scheduler.py`, F8) e o pacote de empacotamento (F9) estão no roadmap subsequente.

| Cenário | Possível hoje? | Por quê |
|---|---|---|
| **Servidor de homologação visual** (UI Freeze): web + backend FAKE, `sss_env = DEV` | **Sim** — é o que este guia instala | Tudo implementado e testado |
| **Implantação de Banco Oracle Real** (F7): DDL, DML, Governança, Seed e Estatísticas | **Sim** — via `01_implantar_sss.sql` ou `init_db.py` | 17 tabelas, sequences, triggers, 14 rotinas utilitárias, 4 perfis e 4 usuários criados e validados |
| Execução real de scripts pelo daemon | **Em conclusão (F8)** | O executor do daemon (`run_scheduler.py`) é o F8. Em DEV/FAKE, tickets são simulados; os 14 scripts utilitários físicos já existem em `dev/scripts/utilitarios/` |
| Nó web ou agente em Windows | **Não, por decisão** | O SSS é somente POSIX (CR-005): Linux x86_64 e, sob demanda, demais Unix |

> **Consequências práticas do backend FAKE:**
> * os dados ficam **na memória do processo**: reiniciar o servidor apaga tudo o que foi feito e restaura o seed;
> * ele exige **um único processo** web (o servidor embutido do web2py). Não use gunicorn/uWSGI com vários workers;
> * por regra do projeto, o servidor DEV escuta **somente em `127.0.0.1`**. Os usuários acessam por túnel SSH (§13).

O capítulo 18 detalha o procedimento de implantação no banco Oracle real e o catálogo de scripts utilitários.

---

## 2. Visão geral do procedimento

```text
 1. Requisitos do servidor ............ §3      9. Configuração (config.ini) .......... §9
 2. Usuário e diretórios .............. §4     10. Teste de carga da configuração ..... §10
 3. Código-fonte ...................... §5     11. Subida do servidor ................. §11
 4. Python ............................ §6     12. Validação pós-subida ............... §12
 5. Verificação do código ............. §7     13. Acesso dos usuários ................ §13
 6. Árvore de scripts de exemplo ...... §8.1   14. Execução contínua (systemd) ........ §14
 7. Segredos (secrets.cfg) ............ §8.2   15. Operação, logs e atualização ....... §15-16
 8. Senha dos usuários de demonstração  §8.3   17. Problemas e soluções ............... §17
                                               21. Servidor sem sudo/systemd (clone 7) . §21
                                               22. Servidor acessado por salto (3067) .. §22
```

Convenções deste guia:

* Os comandos marcados com `sudo` são executados por um administrador do servidor. Os demais, pelo usuário de serviço `sss` (`sudo -u sss -H bash`).
* Caminhos padrão (podem ser trocados, desde que trocados também no `config.ini`):

| Caminho | Conteúdo | Dono | Modo |
|---|---|---|---|
| `/opt/sss/web2py` | Código (web2py + aplicação) | `sss` | `0750` |
| `/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/instance` | Segredos | `sss` | arquivo `0600`, diretório `0700` |
| `/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/logs` | Logs da aplicação, em `app/AAAA/MM/DD/HH/MI/` (§15.2) | `sss` | `0750` |
| `/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/work` | Diretório de trabalho do agente (reservado ao F8) | `sss` | `0700` |
| `/opt/automacoes/scripts` | Árvore de scripts (somente leitura para o `sss`) | `root` | diretórios `0755`, arquivos `0644` |

* `APP` = `/opt/sss/web2py/applications/script_scheduling_service`.

---

## 3. Requisitos do servidor

| Item | Requisito |
|---|---|
| Sistema operacional | Linux x86_64. Validado em Oracle Linux 6.9 (clone 7) e Ubuntu 24.04; esperado em RHEL/Oracle Linux/Rocky/Alma 7+, Ubuntu 20.04+, Debian 11+ |
| CPU / memória / disco | 1 vCPU, 1 GB de RAM livre, 500 MB de disco (código ~60 MB + logs) |
| Python | **3.6.0 ou superior** (validado de 3.6.0 a 3.13). Os módulos `ssl`, `sqlite3` e `_hashlib` (OpenSSL) **não** são necessários (desde o commit `fdf6f35`); basta o `hashlib.pbkdf2_hmac` funcionar. Ver §6 |
| Pacotes Python | **Nenhum.** O web2py e todas as bibliotecas de frontend vêm no repositório. Não use `pip install` |
| Ferramentas | `git` (ou `tar`), `curl`. `sudo` e `systemd` são opcionais: sem eles, use a variante do §21 |
| Rede | Nenhuma porta aberta para a rede: o servidor escuta em `127.0.0.1:8000`. Acesso dos usuários por SSH (porta 22). **Não precisa de internet** |
| Relógio | NTP ativo e fuso definido (o FAKE usa o relógio do servidor). Recomendado `America/Sao_Paulo` |
| Navegador dos usuários | Chrome, Edge ou Firefox atualizados |

---

## 4. Usuário de serviço e diretórios

O SSS **recusa rodar como root** (o launcher aborta). Crie um usuário dedicado, sem login interativo:

```bash
# 4.1 Usuário de serviço (sem shell de login; os comandos rodam via "sudo -u sss")
sudo useradd --system --create-home --home-dir /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service --shell /sbin/nologin sss
# Em Debian/Ubuntu, se /sbin/nologin não existir, use /usr/sbin/nologin

# 4.2 Diretórios
sudo install -d -o sss -g sss -m 0750 /opt/sss
sudo install -d -o sss -g sss -m 0700 /etc/sss
sudo install -d -o sss -g sss -m 0750 /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/logs
sudo install -d -o sss -g sss -m 0700 /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/work

# 4.3 Fuso horário do servidor (se ainda não estiver definido)
sudo timedatectl set-timezone America/Sao_Paulo
timedatectl | grep -E "Time zone|synchronized"
```

Para abrir um shell como `sss` durante a instalação:

```bash
sudo -u sss -H bash
cd /opt/sss
```

---

## 5. Obter o código-fonte

> **Importante:** use **o web2py que está no repositório**, não um download do site do web2py. O repositório traz correções necessárias para o Python 3.6 (`gluon/packages/rocket3`, `gluon/contrib/multipart.py`).

Escolha **uma** das opções, sempre fixando um commit ou tag conhecido.

### 5.1 Servidor com acesso ao Git

```bash
# como sss
cd /opt/sss
git clone https://github.com/ferreirasilvaeduardo/script_scheduling_service_web2py.git web2py
cd web2py
git checkout 3b9a065        # ou a tag/commit homologado
git log --oneline -1
```

Se o repositório for privado, use um *deploy token* de leitura ou a opção 5.2. Nunca grave credenciais do Git no servidor.

### 5.2 Servidor sem acesso ao Git (air-gapped)

Na máquina que tem o repositório:

```bash
cd /caminho/do/repositorio
git archive --format=tar.gz -o sss-3b9a065.tar.gz 3b9a065
sha256sum sss-3b9a065.tar.gz > sss-3b9a065.tar.gz.sha256
```

Copie os dois arquivos para o servidor (por exemplo, `scp` para `/tmp`) e:

```bash
# como sss
cd /tmp && sha256sum -c sss-3b9a065.tar.gz.sha256      # deve responder "OK"
mkdir -p /opt/sss/web2py && tar -xzf /tmp/sss-3b9a065.tar.gz -C /opt/sss/web2py
```

O pacote do `git archive` (~13,8 MB) não contém `config.ini`, `secrets.cfg`, logs nem arquivos de parâmetros do web2py: eles são criados nos passos seguintes.

### 5.3 Conferência

```bash
cd /opt/sss/web2py
ls                      # deve listar web2py.py, anyserver.py, gluon/, applications/, bin/, routes.py
ls applications         # deve listar SOMENTE script_scheduling_service
ls applications/script_scheduling_service/instance   # config.ini.example e secrets.cfg.example
```

As aplicações de exemplo do web2py (`admin`, `welcome`, `examples`), bem como as pastas legadas dispensáveis da raiz (`examples/`, `extras/`, `handlers/`, `scripts/`, `site-packages/`), foram removidas no commit `3b9a065` para manter a árvore hermética, limpa e segura.

---

## 6. Python

O código usa somente sintaxe do Python 3.6 e roda de **3.6.0 a 3.13**. A referência de produção é a **3.6.8**. Escolha uma opção e anote o caminho do executável (usado como `PYTHON` nos passos seguintes).

| Opção | Quando usar | Como |
|---|---|---|
| **A. Python do sistema (3.8+)** | Servidor moderno; mais simples | `python3 --version` já atende. Ex.: Ubuntu 22.04 (3.10), Debian 12 (3.11), RHEL 9 (3.9) |
| **B. Python 3.6.8 do RHEL/Oracle Linux 8** | Igualar a referência de produção | `sudo dnf install -y python36` → `/usr/bin/python3.6` **[não ensaiado]** |
| **C. pyenv (3.6.0 ou 3.6.8)** | Distribuição recente sem pacote 3.6 | Receita completa em `docs/AMBIENTE_DEV.md` §1.1 (compilação com OpenSSL 1.1.1w e patch do bpo-27987) |

Verifique a versão e o suporte a PBKDF2 (obrigatório para as senhas):

```bash
PYTHON=python3          # ajuste conforme a opção escolhida (ex.: /usr/bin/python3.6)
$PYTHON --version
$PYTHON -c "import hashlib, time; t=time.time(); hashlib.pbkdf2_hmac('sha256', b'x', b'y', 200000); print('pbkdf2 OK (%.2fs por senha)' % (time.time()-t))"
# esperado: "pbkdf2 OK" em até ~1 s (é o tempo de cada login).
# Sem OpenSSL (_hashlib), o Python 3.6 a 3.9 usa uma implementação em Python puro, que também serve
# (0,28 s no servidor 10.129.164.55). Se der AttributeError/ImportError, use outro Python.
# Ausência de ssl e de sqlite3 não impede o SSS.
```

---

## 7. Verificação do código no servidor

```bash
# como sss
cd /opt/sss/web2py/applications/script_scheduling_service

# 7.1 Pré-requisitos (Python, web2py.py, Bootstrap, Alpine.js em build CSP)
$PYTHON scripts/check_env.py ; echo "codigo de saida: $?"
# esperado: tabela com todos os itens "OK" e código 0 (1 = falta arquivo; 2 = Python < 3.6.0)

# 7.2 Suíte de testes completa (não precisa de configuração nem de segredos)
$PYTHON -m unittest discover -s scripts -p "test_*.py"
# esperado no final: "Ran ... tests ... OK (skipped=23)" (o total cresce com as versões; os 23 ignorados dependem do Oracle real, SSS_TEST_DSN)
# Os 18 "skipped" são testes contra banco Oracle real (SSS_TEST_DSN); é o resultado esperado.
```

Não prossiga se algum desses passos falhar.

---

## 8. Pré-requisitos de dados: árvore de scripts, segredos e senha de demonstração

### 8.1 Árvore de scripts de exemplo (necessária para disparar tickets)

Os scripts do seed FAKE apontam para caminhos absolutos em `/opt/automacoes/scripts` (ex.: `/opt/automacoes/scripts/carga_diaria.py`). Com o CR-005 não há pastas base: o `path_guard` (README §8.5) confere o **arquivo** e **cada diretório até `/`**. O arquivo precisa pertencer a um UID de `script_owner_uids`; cada diretório, ao root ou a um UID de `script_owner_uids`; e nenhum deles pode ter escrita para grupo, para outros ou **para o usuário `sss`**. Pastas do sistema (`/bin`, `/usr`, `/etc`, ...) e as pastas `log_dir`/`work_dir` são recusadas. O modelo correto é a árvore pertencer ao `root`:

```bash
sudo install -d -o root -g root -m 0755 /opt/automacoes
sudo rm -rf /opt/automacoes/scripts          # ao repetir o passo, evita criar scripts/scripts
sudo cp -r /opt/sss/web2py/applications/script_scheduling_service/dev/scripts /opt/automacoes/scripts
sudo rm -f /opt/automacoes/scripts/.gitkeep
sudo chown -R root:root /opt/automacoes/scripts
sudo find /opt/automacoes/scripts -type d -exec chmod 0755 {} +
sudo find /opt/automacoes/scripts -type f -exec chmod 0644 {} +

# conferência: o usuário sss lê, mas não escreve
sudo -u sss test -r /opt/automacoes/scripts/carga_diaria.py && echo "leitura OK"
sudo -u sss test -w /opt/automacoes/scripts/carga_diaria.py || echo "sem escrita OK"
```

No `config.ini` (§9): `script_owner_uids = 0`.

> **Sem `sudo`:** uma árvore numa pasta do próprio `sss` (ou de qualquer usuário que rode o SSS) **não passa**, porque a pasta pessoal dele é gravável por ele (`GRAVAVEL_PELO_AGENTE`). Nesse caso, não instale a árvore: como os arquivos do seed não existem neste servidor, a **Gestão de Scripts** mostra o aviso "Arquivo não encontrado neste servidor: a validação ocorrerá no agente…" e o disparo cria o ticket normalmente, deixando a conferência para o agente (README §8.5, D4). Foi assim que o ensaio sem `sudo` funcionou (`docs/AMBIENTE_DEV.md` §6.1, opção B).

> **Atualização de instalações anteriores (CR-005):** as chaves `[agent] base_script_dirs` e a antiga `base_script_dir` saíram, e `[logging] app_log_backups` foi trocada por `app_log_retention_days`. Antes de subir a versão nova, apague a linha da pasta base e troque a de backups (§16.3); senão a subida é abortada com CRITICAL "Chave desconhecida".

### 8.2 Segredos (`/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/instance`)

O arquivo precisa ser **regular, pertencer ao usuário que roda o processo (`sss`) e ter modo `0600`**; caso contrário a aplicação não sobe (§17). Com o backend FAKE, basta a chave do cookie de sessão:

```bash
# como sss
umask 077
$PYTHON -c "import secrets; print('[web]'); print('cookie_key = ' + secrets.token_urlsafe(48))" > /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/instance
chmod 600 /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/instance
ls -l /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/instance        # -rw------- 1 sss sss ...
```

* `cookie_key` assina e cifra o cookie de sessão. Trocar o valor desconecta todos os usuários.
* As seções `[oracle]` e `[ambiente:<NOME>]` do `secrets.cfg.example` são opcionais em DEV/FAKE e passam a ser obrigatórias com o Oracle (F7).
* **Nunca** copie o `secrets.cfg` de outra máquina por e-mail ou chat, nem o coloque dentro do diretório do código.

### 8.3 Senha dos usuários de demonstração (`SSS_DEV_SEED_PASSWORD`)

No FAKE, os usuários `admin`, `op.prod`, `op.hml` e `consulta` recebem, a cada subida, a senha informada na variável de ambiente `SSS_DEV_SEED_PASSWORD` (`inativo` e `bloqueado` nunca entram, de propósito).

* Mínimo de **12 caracteres**. Fora da política, ou sem a variável, o servidor sobe, mas **nenhum login funciona** (há um WARN no log).
* A senha não fica gravada em arquivo na subida interativa (§11.1). Na subida por `systemd` (§14), ela fica num arquivo `0600` do próprio `sss`.
* Combine a senha com a equipe de homologação por um canal seguro.

---

## 9. Configuração (`instance/config.ini`)

```bash
# como sss
cd /opt/sss/web2py/applications/script_scheduling_service/instance
cp config.ini.example config.ini
chmod 640 config.ini
vi config.ini          # ou o editor de sua preferência
```

O `config.ini` não contém segredos. **Toda chave é validada na subida**: chave desconhecida, ausente ou fora da faixa impede a aplicação de subir, com a chave e o motivo na mensagem (§10). Ajuste **somente** as chaves abaixo:

| Seção | Chave | Valor para este servidor | Observação |
|---|---|---|---|
| `[app]` | `sss_env` | `DEV` | Obrigatório com FAKE. Também exibe a faixa amarela "AMBIENTE DEV" |
| `[app]` | `data_backend` | `FAKE` | `ORACLE` ainda não está implementado |
| `[secrets]` | `secrets_file` | `/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/instance` | Caminho absoluto do §8.2 |
| `[agent]` | `agent_id` | identificador do servidor, ex.: `srv-sss-hml-01` | Aparece em todas as linhas de log; `^[A-Za-z0-9._-]{1,30}$` |
| `[agent]` | `script_owner_uids` | `0` | UID do dono da árvore do §8.1 (root). Os diretórios do caminho do script podem pertencer ao root mesmo sem o 0 na lista; com scripts reais, prefira um UID dedicado (README §8.5) |
| `[agent]` | `work_dir` | `/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/work` | Reservado ao agente (F8) |
| `[logging]` | `log_dir` | `/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/logs` | Criado com `0750` se não existir |
| `[logging]` | `level` | `INFO` | `DEBUG` só para investigação |
| `[logging]` | `app_log_retention_days` | `30` | Dias de log da aplicação mantidos; o próprio processo apaga as pastas de dia mais antigas (§15.2) |
| `[web]` | `allowed_origins` | `http://127.0.0.1:8000` | Lista separada por vírgula. Em DEV, o próprio endereço acessado já é aceito automaticamente; com proxy reverso, inclua a URL pública (§13.2) |
| `[web]` | `trusted_proxies` | vazio | Só com proxy reverso (§13.2) |

**Não altere** as demais chaves. Em especial:

* a seção `[oracle]` é obrigatória mesmo com FAKE (o arquivo é validado inteiro), mas não é usada; mantenha os valores do exemplo;
* `[agent]`: `fence_timeout_s * 2 <= node_offline_timeout_s`, `heartbeat_interval_s * 3 <= fence_timeout_s` e `max_parallel_jobs <= max_parallel_hard_limit` são validados;
* `[web] session_idle_timeout_s` (30 min), `login_max_tentativas` (5) e `login_bloqueio_s` (15 min) são os padrões de segurança do README §4.2.

---

## 10. Teste de carga da configuração (antes de subir)

Este teste carrega a aplicação no terminal, sem servidor, e mostra **a causa exata** de qualquer erro de configuração ou de segredos:

```bash
# como sss
cd /opt/sss/web2py
umask 077
echo 'print("SSS: configuracao OK (sss_env=%s, backend=%s, agent_id=%s)" % (current.sss_cfg.app.sss_env, current.sss_cfg.app.data_backend, current.sss_cfg.agent.agent_id))' > /tmp/sss_diag.py
$PYTHON web2py.py -S script_scheduling_service -M -R /tmp/sss_diag.py 2>&1 | grep -E "^SSS:|ConfigErro"
rm -f /tmp/sss_diag.py
```

* **Sucesso:** `SSS: configuracao OK (sss_env=DEV, backend=FAKE, agent_id=srv-sss-hml-01)`.
* **Falha:** aparece a linha `ConfigErro` com o motivo, por exemplo `ConfigErro: Arquivo de segredos possui permissoes inseguras (mode 644, ...)`. Corrija conforme o §17 e repita.
* Se nenhuma das duas linhas aparecer, rode o comando sem o `grep` e leia as últimas linhas da saída. O aviso `unable to create welcome.w2p file` pode aparecer e é inofensivo (§11.1).

---

## 11. Subir o servidor

### 11.1 Subida interativa e scripts locais de controle

Para subida local de desenvolvimento em segundo plano com geração de log carimbado com data/hora e verificação automática de HTTP 200:

```bash
# como sss
cd /opt/sss/web2py
bin/iniciar_local.sh               # sobe em segundo plano com nohup (porta 8000 padrao)
# ou: bin/iniciar_local.sh 18000   # porta customizada
# ou: bin/iniciar_local.sh -f      # em primeiro plano no terminal
bin/parar_servico.sh               # encerra graciosamente (SIGINT) e libera a porta
```

Alternativamente, a chamada direta ao launcher:

```bash
# como sss
cd /opt/sss/web2py
read -s -p "SSS_DEV_SEED_PASSWORD: " SSS_DEV_SEED_PASSWORD && export SSS_DEV_SEED_PASSWORD && echo
export PYTHON SSS_TZ=America/Sao_Paulo
bin/sss-web.sh "$PYTHON" web2py.py -a '<recycle>' -i 127.0.0.1 -p 8000 --no_gui
```

O que cada parte faz:

| Parte | Função |
|---|---|
| `bin/iniciar_local.sh` | Script de inicialização em segundo plano: carrega `instance/web.env`, dispara via `bin/sss-web.sh` com `nohup`, carimba a data no nome do arquivo de log (`servidor-AAAA-MM-DD_HH-MI-SS.log`) e no cabeçalho, cria o link `servidor.out` e valida a resposta HTTP 200 do login |
| `bin/parar_servico.sh` | Script de parada graciosa: lê o PID de `work/sss_web.pid`, envia `SIGINT` ao web2py, aguarda a liberação da porta e registra o encerramento no log |
| `bin/sss-web.sh` | Launcher do projeto: **recusa root**, aplica `umask 077`, exporta `TZ` (de `SSS_TZ`) e `LANG`/`LC_ALL` (de `SSS_LOCALE`, padrão `C.UTF-8`; CR-007: o processo aborta sem codificação UTF-8) e substitui o próprio processo pelo comando (`exec`), para que os sinais de parada cheguem direto ao servidor |
| `web2py.py` | Servidor web embutido do web2py (Rocket), multithread em **um único processo**, como o FAKE exige |
| `-a '<recycle>'` | Senha do painel administrativo do web2py. `<recycle>` reaproveita a existente ou, na primeira vez, **desabilita** o painel (que nem é implantado). Assim nenhuma senha aparece na lista de processos (`ps`). **Não** use `-a 'senha'` |
| `-i 127.0.0.1` | Escuta só local (regra do projeto em DEV). **Nunca** use `0.0.0.0` |
| `-p 8000` | Porta. Se mudar, ajuste o túnel (§13) e `allowed_origins` |
| `--no_gui` | Sem interface gráfica do web2py |

A subida está pronta quando aparece `please visit: http://127.0.0.1:8000/` (ou quando `iniciar_local.sh` confirma o HTTP 200). Para parar: **Ctrl+C** (em primeiro plano) ou `bin/parar_servico.sh` (em segundo plano).

Na **primeira** subida aparece no terminal `New installation error: unable to create welcome.w2p file` com um traceback. É **esperado e inofensivo**: o web2py tenta empacotar a aplicação de exemplo `welcome`, que foi removida de propósito.

### 11.2 Arquivos criados pela subida

| Arquivo | O que é |
|---|---|
| `/opt/sss/web2py/parameters_8000.py` | Senha (hash) do painel do web2py; com `<recycle>` na primeira vez, `password=None` |
| `/opt/sss/web2py/httpserver.log` | Log de acesso do servidor web (uma linha por requisição) |
| `/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/logs/app/AAAA/MM/DD/HH/MI/sss_web_<PID>.log` | Log da aplicação, na pasta do minuto da subida (§15.2) |
| `APP/errors/` | "Tickets" de erro interno do web2py (§15.3) |

---

## 12. Validação pós-subida

Num **segundo terminal** do servidor:

```bash
# 12.1 Página de login responde
curl -s -o /dev/null -w "login: HTTP %{http_code}\n" http://127.0.0.1:8000/script_scheduling_service/default/login
# esperado: login: HTTP 200

# 12.2 Cabeçalhos de segurança presentes
curl -sI http://127.0.0.1:8000/script_scheduling_service/default/login | grep -iE "content-security-policy|x-frame-options|x-content-type-options|referrer-policy"
# esperado: as 4 linhas

# 12.3 Requisição de outra origem é recusada
curl -s -o /dev/null -w "origem estranha: HTTP %{http_code}\n" -X POST -H "Origin: http://outro-host" http://127.0.0.1:8000/script_scheduling_service/default/login
# esperado: origem estranha: HTTP 403

# 12.4 Log da aplicação sendo escrito (arquivo mais recente, §15.2)
tail -n 5 "$(find /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/logs/app -name 'sss_web_*.log' -type f -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-)"
```

Depois, pelo navegador (via túnel, §13.1), faça o **teste de fumaça**:

1. Abrir `http://localhost:8000/script_scheduling_service` → tela **Entrar**, com a faixa "AMBIENTE DEV".
2. Entrar com `admin` e a senha do §8.3 → **Painel inicial** "Olá, Administrador Geral", com os cartões de tickets, agendamentos e saúde dos agentes.
   * No topo, **O que eu posso fazer** → lista as telas, os ambientes e os scripts liberados para o perfil.
   * No menu Operação, **Rotinas disponíveis** → um cartão por script, com a última execução.
3. **Disparar Scripts** → `carga_diaria` → `PRODUCAO` → **Criar ticket** → a confirmação mostra o resumo ("Vamos rodar carga_diaria no ambiente PRODUCAO agora…") e o comando com `/opt/automacoes/scripts/carga_diaria.py` → confirmar → mensagem "Ticket #41 criado com sucesso.". Com a árvore do §8.1 correta, o log **não** traz a linha `arquivo do script nao existe no no web`; sem a árvore, o ticket também é criado e essa linha aparece (a conferência fica para o agente).
4. **Auditoria** → aba **Agentes** → dois cartões (`agt-host01` OK; `agt-host02` envelhecendo com o tempo).
5. **Sair** → volta para **Entrar** com "Você saiu do sistema.".

A homologação completa segue o `docs/homologacao/SSS_Manual_Homologacao_UI_Freeze.docx`.

> A raiz do servidor (`http://localhost:8000/`) responde **404**, porque redireciona para a aplicação `welcome`, removida. Use sempre o caminho `/script_scheduling_service`. A aplicação padrão será fixada no `routes.py` no F9.1.

---

## 13. Acesso dos usuários

### 13.1 Túnel SSH (recomendado; não abre porta nenhuma) — [ensaiado o modelo de origem]

Cada usuário cria um túnel da própria máquina até o servidor e usa o navegador normalmente:

```bash
# Linux, macOS ou Windows 10+ (PowerShell/Prompt já trazem o ssh)
ssh -N -L 8000:127.0.0.1:8000 usuario@servidor-sss
# deixe a janela aberta e acesse no navegador: http://localhost:8000/script_scheduling_service
```

* No PuTTY: *Connection → SSH → Tunnels*: Source port `8000`, Destination `127.0.0.1:8000`, **Add**, e conecte.
* O usuário precisa de conta SSH no servidor (pode ser restrita a túnel, sem shell: `PermitTTY no` / `ForceCommand /bin/false` para o grupo, a critério da infraestrutura).
* Em DEV, o endereço acessado (`http://localhost:8000`) é aceito automaticamente na checagem de origem; não é preciso mudar o `config.ini`.
* Se a porta 8000 local estiver ocupada, use outra só do lado do usuário (`-L 18000:127.0.0.1:8000` e `http://localhost:18000/...`).

### 13.2 Proxy reverso HTTPS (alternativa) — [não ensaiado]

Só com aprovação da segurança da informação, porque expõe na rede um ambiente DEV com dados de demonstração. O SSS continua em `127.0.0.1:8000` e um Nginx/Apache **no mesmo servidor** publica `https://sss-hml.empresa.local`:

* `config.ini`: `allowed_origins = https://sss-hml.empresa.local` e `trusted_proxies = 127.0.0.1`;
* o proxy deve repassar `Host`, `X-Forwarded-For` e o corpo sem alteração; não use cache de respostas;
* use certificado da empresa (o cookie de sessão não recebe `Secure` em DEV atrás de proxy HTTP local; o HTTPS do proxy protege o trecho de rede);
* restrinja o acesso por rede/VPN.

---

## 14. Execução contínua com systemd (opcional) — [sintaxe verificada; não ensaiado como serviço]

Para manter o servidor no ar sem um terminal aberto. Lembre que **reiniciar o serviço restaura os dados de demonstração**.

```bash
# 14.1 Senha de demonstração num arquivo do próprio sss (somente leitura dele)
sudo install -o sss -g sss -m 0600 /dev/null /etc/sss/web.env
sudo -u sss bash -c 'read -s -p "SSS_DEV_SEED_PASSWORD: " P; echo; printf "SSS_DEV_SEED_PASSWORD=%s\nSSS_TZ=America/Sao_Paulo\n" "$P" > /etc/sss/web.env'
```

`/etc/systemd/system/sss-web.service` (ajuste `PYTHON` conforme o §6):

```ini
[Unit]
Description=SSS - Script Scheduling Service (web, backend FAKE/DEV)
After=network.target

[Service]
Type=simple
User=sss
Group=sss
WorkingDirectory=/opt/sss/web2py
EnvironmentFile=/etc/sss/web.env
Environment=PYTHON=/usr/bin/python3
ExecStart=/opt/sss/web2py/bin/sss-web.sh /usr/bin/python3 web2py.py -a <recycle> -i 127.0.0.1 -p 8000 --no_gui
Restart=on-failure
RestartSec=5
KillMode=mixed
TimeoutStopSec=30
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/sss/web2py /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/logs /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sss-web
systemctl status sss-web --no-pager
journalctl -u sss-web -n 50 --no-pager
```

* `ReadWritePaths` inclui o diretório do código porque o web2py grava `parameters_8000.py`, `httpserver.log`, `errors/` e caches de bytecode nele.
* Parar: `sudo systemctl stop sss-web`. Reiniciar (zera os dados FAKE): `sudo systemctl restart sss-web`.

---

## 15. Operação do dia a dia

### 15.1 Parar, reiniciar e verificar

| Ação | Interativo (§11.1) | systemd (§14) |
|---|---|---|
| Parar | Ctrl+C no terminal | `sudo systemctl stop sss-web` |
| Subir | comando do §11.1 | `sudo systemctl start sss-web` |
| Está no ar? | `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/script_scheduling_service/default/login` (200) | idem, ou `systemctl is-active sss-web` |

### 15.2 Logs

| Log | Onde | Conteúdo |
|---|---|---|
| Aplicação | `/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/logs/app/AAAA/MM/DD/HH/MI/sss_web_<PID>.log`: um arquivo por processo, na pasta do minuto em que ele subiu; ao chegar a 10 MB (`app_log_max_bytes`) abre outro na pasta do minuto atual (no mesmo minuto, com sufixo `_2`, `_3`…); pastas de dia com mais de 30 dias (`app_log_retention_days`) são apagadas pelo próprio processo | Formato `data nível [pid] [agente] [ticket] [acao] mensagem`. Login, logout, criação/cancelamento de ticket, negações de acesso, recusas de CSRF/origem. **Nunca** contém senhas nem valores sigilosos |
| Acesso HTTP | `/opt/sss/web2py/httpserver.log` | Uma linha por requisição (IP, método, caminho, status) |
| Serviço | `journalctl -u sss-web` | Saída do processo quando rodando por systemd |
| Erros internos | `APP/errors/` | Ver 15.3 |

Exemplos úteis:

```bash
applog() { find /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/logs/app -name 'sss_web_*.log' -type f -printf '%T@ %p\n' | sort -n | cut -d' ' -f2-; }   # do mais antigo ao mais recente (última escrita)
applog | tail -n 1                                                           # arquivo atual
applog | xargs grep -h -E " (WARNING|ERROR|CRITICAL) " | tail -n 20          # problemas recentes
applog | xargs grep -h "acao=LOGIN" | tail -n 20                             # logins e logouts
applog | xargs grep -h "acao=CSRF\|acao=RBAC" | tail -n 20                   # recusas de segurança
```

### 15.3 Erro interno (HTTP 500 com "Ticket issued")

O link do ticket na página não abre (o painel `admin` não é implantado). Para ler a causa:

```bash
# como sss, a partir da raiz do web2py
cd /opt/sss/web2py
F=$(ls -t applications/script_scheduling_service/errors/* | head -1)
$PYTHON -c "import pickle,sys; d=pickle.load(open(sys.argv[1],'rb')); print(d['traceback'])" "$F" | tail -n 5
```

Erros de configuração aparecem melhor pelo teste do §10. Depois de resolver, limpe os tickets antigos: `rm -f applications/script_scheduling_service/errors/*`.

### 15.4 Limpeza de disco

* O log da aplicação tem troca por tamanho e retenção por dias próprias (§15.2); não o inclua no `logrotate`. `httpserver.log` **não** tem: inclua-o no `logrotate` da empresa (`copytruncate`, semanal, 4 cópias) ou apague-o periodicamente com o serviço parado.
* `APP/errors/` só cresce quando há erro interno; limpe após a análise.

---

## 16. Atualização de versão e retorno

```bash
# 16.1 Parar o servidor (§15.1) e guardar a configuração local
cp /opt/sss/web2py/applications/script_scheduling_service/instance/config.ini /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/config.ini.bak

# 16.2 Trocar o código
cd /opt/sss/web2py
git fetch && git checkout <novo-commit-ou-tag>          # opção Git
# ou, sem Git: extrair o novo pacote numa pasta nova (/opt/sss/web2py-<versao>), copiar
# instance/config.ini para ela e trocar o caminho no systemd/atalhos

# 16.3 Conferir se o config.ini.example ganhou ou perdeu chaves
diff <(grep -oE "^[a-z_]+ =" applications/script_scheduling_service/instance/config.ini.example | sort) \
     <(grep -oE "^[a-z_]+ =" applications/script_scheduling_service/instance/config.ini | sort)
# qualquer diferença precisa ser refletida no config.ini antes de subir
# vindo de versão anterior ao CR-005: apague a linha base_script_dir (ou base_script_dirs)
# e troque app_log_backups = N por app_log_retention_days = 30 (§8.1); as chaves antigas abortam a subida

# 16.4 Verificar e subir
cd applications/script_scheduling_service
$PYTHON scripts/check_env.py && $PYTHON -m unittest discover -s scripts -p "test_*.py"
# §10 (teste de carga) → §11 (subida) → §12 (validação)
```

**Retorno (rollback):** pare, volte ao commit anterior (`git checkout <commit-anterior>`, ou a pasta anterior), restaure o `config.ini` guardado e suba. Como o FAKE não guarda dados, não há base a restaurar.

> **Atenção para a próxima versão (F7.0):** a seção `[oracle]` troca `driver` e `use_thick_mode` por `modo_driver` (CR-002). O passo 16.3 mostra essa diferença; ajuste o `config.ini` conforme o `config.ini.example` da versão nova.

---

## 17. Problemas e soluções

Mensagens reais, capturadas no ensaio. Para os erros de subida, use sempre o teste do §10, que mostra a causa no terminal.

| Sintoma | Mensagem / onde ver | Causa | Solução |
|---|---|---|---|
| Página com "Internal error — Ticket issued" (HTTP 500) em qualquer tela | §10 ou §15.3: `ConfigErro: Arquivo de configuracao nao encontrado: .../instance/config.ini` | Falta o `config.ini` | §9 |
| Idem | `ConfigErro: Arquivo de segredos nao encontrado: /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/instance` | Caminho de `secrets_file` errado ou arquivo ausente | §8.2 e §9 |
| Idem | `ConfigErro: Arquivo de segredos possui permissoes inseguras (mode 644, esperado sem acesso grupo/outros)` | Modo diferente de `0600` | `chmod 600 /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/instance` |
| Idem | `ConfigErro: Arquivo de segredos deve pertencer ao usuario corrente (UID ..., atual ...)` | O processo roda com outro usuário, ou o arquivo foi criado pelo root | `sudo chown sss:sss /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/instance` e suba como `sss` |
| Idem | `ConfigErro: [web]: cookie_key: Chave cookie_key obrigatoria ausente em [web]` | `secrets.cfg` incompleto | §8.2 |
| Idem | `ConfigErro` citando `[secao] chave` e motivo | Chave ausente, desconhecida ou fora da faixa no `config.ini` | Compare com o `config.ini.example` (§16.3) |
| Idem | `ConfigErro: [app]: data_backend: data_backend=FAKE exige sss_env=DEV (atual: HML)` | `sss_env` diferente de `DEV` com FAKE | `sss_env = DEV` |
| Idem | `ConfigErro: [agent]: base_script_dir: Chave desconhecida na secao [agent]: base_script_dir` (ou `base_script_dirs`, ou `[logging]: app_log_backups: ...`) | `config.ini` de versão anterior ao CR-005 | Apagar a linha da pasta base e trocar `app_log_backups` por `app_log_retention_days = 30` (§8.1, §16.3) |
| Subida abortada sem o motivo no terminal | Log da aplicação do minuto da tentativa, `log_dir/app/AAAA/MM/DD/HH/MI/sss_web_<PID>.log` (ou o stderr, se o `log_dir` não aceitar escrita): linha `CRITICAL` "Subida abortada: configuracao invalida: …" | Qualquer erro de configuração | Ler a linha `CRITICAL` com a função `applog` do §15.2 (`applog` seguido de `xargs grep -h CRITICAL`) e corrigir; o teste do §10 mostra o mesmo motivo |
| Ninguém consegue entrar ("Usuário ou senha incorretos. Confira o que digitou e tente de novo.") | Log da aplicação: `SSS_DEV_SEED_PASSWORD ausente: usuarios do seed FAKE sem senha utilizavel` (ou `fora da politica`) | Variável ausente ou com menos de 12 caracteres | §8.3 e reinicie |
| Um usuário específico não entra | Tela: "Houve muitas tentativas com a senha errada. Espere 15 minutos ou peça ao administrador para desbloquear." | 5 senhas erradas seguidas: bloqueio de 15 minutos (`login_bloqueio_s`) | Aguarde, desbloqueie em **Gestão de Usuários**, ou reinicie o servidor (restaura o seed) |
| Launcher aborta | `Erro: execucao como root nao e permitida.` | Executado como root | Use `sudo -u sss -H bash` |
| Servidor não sobe: porta ocupada | Terminal: `Socket 127.0.0.1:8000 in use by other process and it won't share.` | Outro processo na porta 8000 | Rode `ss -ltnp` e procure `:8000`; pare o outro processo ou troque a porta |
| Formulários retornam "Requisição recusada." (HTTP 403) | Log da aplicação: `requisicao rejeitada (motivo=origem ...)` | Acesso por endereço que não está em `allowed_origins` (típico com proxy reverso) | Incluir a URL pública em `allowed_origins` (§13.2) |
| Idem | `motivo=csrf` | Página aberta há muito tempo ou sessão expirada | Recarregar a página e repetir |
| Sessão cai sozinha | "Você ficou um tempo sem usar o sistema e saiu por segurança. Entre de novo." | 30 min sem uso (`session_idle_timeout_s`) | Comportamento esperado |
| Criar ticket falha com aviso de script indisponível | Log da aplicação: `path_guard rejeitou o script (... codigo=...)` | O arquivo existe neste servidor, mas ele ou uma pasta do caminho até `/` está fora do padrão do §8.1 (dono fora de `script_owner_uids`, escrita de grupo/outros ou do `sss`) | Refazer §8.1 e conferir `script_owner_uids` |
| Ao salvar um script: "Arquivo não encontrado neste servidor: a validação ocorrerá no agente. Se o arquivo não existir lá, a execução será recusada." | Formulário de **Gestão de Scripts** | O caminho absoluto informado não existe neste servidor (README §8.5, D4) | Esperado para script que só existe nos agentes, e para o seed sem a árvore do §8.1. Se o arquivo deveria existir aqui, confira o caminho |
| Raiz `http://localhost:8000/` dá 404 | — | A raiz aponta para a aplicação `welcome`, removida | Use `/script_scheduling_service` |
| Aviso `unable to create welcome.w2p file` na subida | Terminal | Mesma causa acima | Ignorar |
| Dados "sumiram" | — | O servidor foi reiniciado (FAKE em memória) | Comportamento esperado |
| `check_env.py` com código 2 | `FALHA: Python 3.6.0 ou superior e obrigatorio` | Python antigo | §6 |
| `check_env.py` com código 1 | Item `FALHA` na tabela | Código incompleto (Bootstrap/Alpine ausentes) | Obter o código de novo (§5) |

---

## 18. Para a implantação definitiva (Oracle + agentes): o que preparar desde já

Ainda **não executável** (F7–F9). O `docs/RUNBOOK.md` será entregue no F9.1. Itens com prazo longo que a infraestrutura e o DBA já podem providenciar:

| Item | Detalhe | Referência |
|---|---|---|
| Banco Oracle | 11gR2 (11.2.0.4) ou superior, charset AL32UTF8; schema/owner da aplicação (ex.: `openrisow`), usuário de aplicação e *grants*; espaço para as 17 tabelas `tbsss_*` (CR-007: inclui `tbsss_controle`) | README §2.2, §10, §11.1 |
| Conectividade | Rota e firewall dos servidores web/agentes até o listener Oracle (porta 1521) | README §2.3 |
| Oracle Instant Client 19 | Obrigatório se o banco for 11g (o modo Thin não conecta ao 11g); recomendado em todos os nós como contingência | README §2.3, CR-002 |
| Driver Python | `python-oracledb` (`< 2.0` na 3.6; `2.x` na 3.7+) com `cryptography`, e `cx_Oracle 8.3` como contingência, **pré-instalados** pela infraestrutura | AGENTS §2.2 |
| Servidores agentes | Linux (ou outro Unix, sob demanda), com conta de serviço sem privilégio administrativo; interpretadores (`python3`, `bash`, `sh`) nos caminhos que serão mapeados, com dono root e sem escrita de grupo ou outros (o agente confere a cadeia, CR-007) | README §2.6, §8.5, CR-005 |
| Usuários de execução (CR-007, D1) | Um usuário do sistema operacional **por ambiente** (ex.: `sssprd`, `ssshml`), sem login interativo, sem senha, diferente da conta do agente e fora de `script_owner_uids`; pasta `exec_work_dir/<usuário>` com dono o próprio usuário e `0700`; cota de disco e limite de processos (`nproc`) para cada um; o helper e o `sudoers` do §18.1 | README §8.0, §8.4 |
| Scripts reais | Em qualquer pasta, fora das pastas do sistema; dono de preferência um usuário dedicado (em `script_owner_uids`), sem escrita para grupo e outros, e **sem** pertencer à conta do agente nem a um usuário de execução, no arquivo e em toda a cadeia de pastas; sem link simbólico no caminho (CR-007) | README §8.5, CR-005, CR-007 |
| Contas Oracle por papel (CR-007, D1b; CR-008, E3) | Cinco contas: dona do esquema (só para o `init_db.py`), `sss_web`, `sss_agente`, `sss_purge` e `sss_monitor` (só leitura, para o `saude.py`), com os GRANTs do README §11.1 (o `init_db.py --grants-para` imprime o script). A conta da aplicação nunca é a dona do esquema (recusado fora de DEV, CR-008 R-29) | README §4.1, §11.1 |
| Partição dos logs (CR-008, R-25) | `log_dir` num sistema de arquivos próprio nos agentes, com alerta de uso; a cota do usuário de execução não o protege (§18.1) | README §8.2, §14 |
| Banco: tempo e sessões (CR-007) | Fuso do servidor de banco **sem horário de verão** (UTC recomendado) e NTP em modo *slew* em todas as instâncias; `SQLNET.EXPIRE_TIME = 1` no `sqlnet.ora` do servidor de banco, para derrubar sessões mortas que seguram lock; job automático de estatísticas ativo para o esquema | README §7.1, §8.8, §11.1 |
| HTTPS e DNS | Nome e certificado para o nó web em HML/PROD (`sss_env = HML/PROD` exige cookie `Secure`) | README §4.2 |
| Credenciais | Senha do Oracle e credenciais por ambiente para o `secrets.cfg`, entregues por canal seguro | README §4.1 |

### 18.1 Helper de execução e `sudoers` (CR-007, D1)

```bash
# como root, em cada agente, a partir do pacote descompactado
install -o root -g root -m 0755 -d /opt/sss/bin
install -o root -g root -m 0755 bin/sss-helper /opt/sss/bin/sss-helper
useradd --system --shell /sbin/nologin --home-dir /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/exec/sssprd sssprd
install -o sssprd -g sssprd -m 0700 -d /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/exec/sssprd
visudo -f /etc/sudoers.d/sss        # conteúdo abaixo; uma linha por usuário de execução
```

```text
Defaults:sssagente !requiretty
sssagente ALL=(sssprd) NOPASSWD: /opt/sss/bin/sss-helper
sssagente ALL=(ssshml) NOPASSWD: /opt/sss/bin/sss-helper
```

* `sssagente` é a conta do agente; nenhuma outra regra de `sudo` é concedida a ela.
* O agente confere tudo na subida (`sudo -n -l`, dono e modo do helper, usuários e pastas; README §8.0) e recusa subir com CRITICAL se algo faltar.
* **Cota e limites por usuário de execução:** cota de disco na partição de `exec_work_dir` e `nproc`/`nofile` em `/etc/security/limits.d/`, para que um script não esgote o servidor.
* **Disco dos logs (CR-008, R-25):** a cota do usuário de execução **não** protege o `log_dir`: o arquivo de log de cada ticket pertence à conta do agente, e o script só escreve no descritor herdado. Por isso, `log_dir` fica numa **partição própria** (ou num volume lógico próprio), separada de `/`, `work_dir` e `exec_work_dir`, dimensionada para `local_log_retention_days` de logs. O agente para de fazer claim com menos de `[agent] log_dir_min_livre_mb` livres (padrão 1.024 MB, WARN `DISCO_LOG`, README §8.2); o monitoramento corporativo alerta antes disso (por exemplo, 80% de uso).
* **Hash homologado (CR-008, E4):** com web e agentes em servidores separados, homologue o conteúdo de cada script informando no cadastro o SHA-256 obtido no servidor do agente: `sha256sum /caminho/do/script`. Configure `[agent] ambientes_exigem_hash = PRODUCAO` (e os demais ambientes produtivos) para que um script sem hash homologado seja recusado nesses ambientes.

### 18.2 Conexão Oracle com failover (CR-007, R-12)

* **Orçamento da abertura (CR-008, R-17):** `CONNECT_TIMEOUT × (RETRY_COUNT + 1) × endereços` precisa ser **menor ou igual** a `call_timeout_ms / 1000` (30 s no exemplo do README §12.1). Acima disso, uma reconexão bloqueia o laço do agente além do previsto nas invariantes do fencing; o agente, o nó web e o `check_env.py` avisam com WARN `CONEXAO_ACIMA_DO_PRAZO` (README §2.3).
* **RAC:** use o nome do serviço, nunca o SID, e um descritor com balanceamento e failover, por exemplo (5 × 2 × 1 = 10 s com o SCAN, que é um endereço só):
  `(DESCRIPTION=(CONNECT_TIMEOUT=5)(RETRY_COUNT=1)(ADDRESS_LIST=(LOAD_BALANCE=on)(FAILOVER=on)(ADDRESS=(PROTOCOL=TCP)(HOST=scan.empresa.local)(PORT=1521)))(CONNECT_DATA=(SERVICE_NAME=sss_srv)))`.
* **Data Guard:** um serviço de banco iniciado só no primário (`role = PRIMARY`) e o descritor com os dois endereços (primário e standby) em `ADDRESS_LIST` com `FAILOVER=on`. Com dois endereços, use `CONNECT_TIMEOUT=5` e `RETRY_COUNT=1` (5 × 2 × 2 = 20 s ≤ 30 s).
* `CONNECT_TIMEOUT` e `RETRY_COUNT` no descritor valem a partir do cliente 19c (Thick/cx_Oracle); no modo Thin, o `db_conn` usa `tcp_connect_timeout` e `retry_count`.
* Todos os servidores do banco no mesmo fuso, sem horário de verão, com NTP em modo *slew* (README §7.1).

### 18.3 Dimensionamento dos logs no banco (CR-007, R-29)

* Num banco AL32UTF8, o CLOB guarda AL16UTF16: cerca de **2 bytes por caractere**.
* Estimativa do segmento LOB de `tbsss_tickets`: `tickets por dia × tamanho médio do log em caracteres × 2 × ticket_retention_days × 1,3` (folga de 30%). Exemplo: 2.000 tickets/dia × 50.000 caracteres × 2 × 180 dias × 1,3 ≈ 47 GB.
* `max_log_size_bytes` vai até 64 MiB por ticket (README §12.1). Depois do purge, o espaço volta ao segmento, não ao tablespace; para devolvê-lo, o DBA usa `ALTER TABLE ... MOVE LOB` ou redefinição online numa janela.

### 18.4 Monitoração, backup e restauração (CR-007, R-18)

* **Conta de monitoração (CR-008, E3):** crie a conta Oracle `sss_monitor`, só com os `SELECT` do papel monitor (`init_db.py --grants-para ... monitor=sss_monitor`, README §11.1), e a seção `[monitor]` (`user` e `password`) no `secrets.cfg` do servidor que roda o `saude.py`. A conta do agente não serve: ela não lê `tbsss_auditoria`, e a checagem do purge falharia sempre.
* **Monitoração:** `scripts/saude.py` (F9.1) no monitoramento corporativo a cada 5 minutos, com alerta no código 2 (README §13). Alertas mínimos: agente parado, fila sem atendente, ticket rodando sem PID, configuração divergente entre agentes, purge sem rodar há 2 dias.
* **Backup:** o esquema (RMAN ou Data Pump do owner), o `config.ini` e o `secrets.cfg` de cada servidor (cofre), e os logs locais conforme a política da empresa.
* **Depois de restaurar o banco** (restore ou *flashback*; CR-008, R-18). O banco volta a um instante anterior, mas os scripts executados depois dele já produziram efeito. Antes de religar qualquer agente:
  1. pare todos os agentes e anote o **instante de restauração** (o do backup ou do *flashback*);
  2. finalize como `FAILED`/`ORPHAN_PROCESS` os tickets `RUNNING` restaurados que têm PID (eles se referem a processos que não existem mais);
  3. **revise** os tickets `PENDING` e os `RUNNING` sem PID criados antes do instante de restauração: compare com os logs locais dos agentes (`log_dir/<script>/AAAA/MM/DD/HH/MI/ticket_<id>_<PID>.log`, que sobrevivem à restauração). Os que já rodaram depois do backup são cancelados pela tela (Cancelar, auditado como `TICKET_CANCELAR` com o login do operador), nunca apagados;
  4. para não repetir as ocorrências de agendamento já cumpridas, configure temporariamente `misfire_policy = SKIP` em **todos** os agentes (o `config_criticos` precisa ser igual em todos, README §8.12) para a primeira subida; volte a `RUN_ONCE` depois que o primeiro desdobro avançar as regras;
  5. avance as sequences de `tbsss_tickets` e `tbsss_auditoria` acima do maior id visto nos logs locais e no log da aplicação (o DBA recria a sequence com `START WITH` maior; o 11g não tem `ALTER SEQUENCE ... RESTART`), para que nenhum id se repita entre o banco e os arquivos locais;
  6. religue os agentes. O startup check limpa as pastas locais.

### 18.5 Implantação do Banco Oracle Real e Catálogo de Scripts (F7)

O procedimento de implantação física do banco de dados e das rotinas operacionais homologadas é realizado de forma autônoma:

#### 18.5.1 Execução do Script SQL no Banco Oracle (DBA)

O script [`docs/sql/01_implantar_sss.sql`](file:///portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/docs/sql/01_implantar_sss.sql) é totalmente autocontido e não requer Python no servidor de banco de dados. Ele aplica:
- Criação das 17 sequences, tabelas (com LOB Basic/Securefile), constraints (PK, UK, CK, FK), índices e triggers.
- Metadados de governança de dados (`COMMENT ON TABLE` e `COMMENT ON COLUMN` em todas as tabelas e colunas, além de comentários nas triggers).
- Carga de seed DML idempotente com `MERGE INTO`: 10 funcionalidades, 5 ambientes, 19 parâmetros reutilizáveis, 14 scripts utilitários com 70 homologações em ambientes e 38 vínculos de parâmetros, 4 perfis operacionais e 4 usuários de homologação.
- Coleta inicial de estatísticas pelo otimizador (`DBMS_STATS.GATHER_TABLE_STATS`).
- GRANTs por papel (web, agente, purge e monitor; README §11.1), **sem GRANT a PUBLIC**. Papel cuja conta é a dona do esquema, ou sem conta informada, aparece como comentário no fim do script. Para contas separadas por papel, regere com `python3 scripts/gerar_scripts_sql.py --grants-para web=<conta>,agente=<conta>,purge=<conta>,monitor=<conta>`, o que também gera o `03_grants_sss.sql` avulso.
- Atenção: o script termina com "concluída com sucesso!" mesmo se algum comando falhar (`WHENEVER SQLERROR CONTINUE`). Grave a saída com `SPOOL` e procure `ORA-`/`SP2-` no log antes de dar a implantação por concluída.

Comando de execução via SQL*Plus:
```bash
sqlplus usuario_owner/senha@//host:porta/servico @docs/sql/01_implantar_sss.sql
```

Para desinstalação total (rollback limpo dos 53 objetos do esquema: 19 triggers, 17 tabelas e 17 sequences, com constraints, índices e GRANTs removidos junto das tabelas):
```bash
sqlplus usuario_owner/senha@//host:porta/servico @docs/sql/02_rollback_sss.sql
```

Validação, só de leitura, logo depois da implantação. Grave a saída e confira que as duas linhas de resumo dizem `OK: nenhuma falha` e que não há `ORA-`/`SP2-`:
```sql
SPOOL /tmp/sss_99_validar.log
@docs/sql/99_validar_implantacao.sql
```
Os esperados (objetos, versão do esquema e mínimo de linhas do seed) saem do mesmo registro que gerou o `01`. Por isso o `99` precisa ser regerado junto com ele, por `python3 scripts/gerar_scripts_sql.py`. A listagem de usuários não mostra hash de senha.

#### 18.5.2 Instalação dos Scripts Utilitários Físicos no Servidor

Copie os 14 scripts utilitários desenvolvidos em Python 3 e Shell POSIX para o caminho padrão de automações:

```bash
sudo install -d -o root -g root -m 0755 /opt/automacoes/scripts/utilitarios
sudo cp dev/scripts/utilitarios/* /opt/automacoes/scripts/utilitarios/
sudo chown -R root:root /opt/automacoes/scripts/utilitarios
sudo chmod 0755 /opt/automacoes/scripts/utilitarios
sudo chmod 0755 /opt/automacoes/scripts/utilitarios/*.sh
sudo chmod 0755 /opt/automacoes/scripts/utilitarios/*.py
```

*Consulte a especificação detalhada de parâmetros e exemplos de execução em [`docs/SCRIPTS_UTILITARIOS.md`](file:///portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/docs/SCRIPTS_UTILITARIOS.md).*

#### 18.5.3 Usuários e Perfis Padrão para Homologação e Demonstração

| Login | Perfil | Privilégio | Escopo de Acesso | Finalidade de Teste |
|:---|:---|:---:|:---|:---|
| `admin` | `ADMINISTRADOR` | Sim (`is_admin = 'S'`) | Todas as funcionalidades e todos os ambientes | Acesso irrestrito a cadastros, agendamentos, auditoria e execução |
| `op.prod` | `OPERADOR_PROD` | Não (`is_admin = 'N'`) | `EXEC_SCRIPT`, `VER_LOGS`, `CANC_TICKET` em todos os 5 ambientes | Operação padrão em produção e clones |
| `op.hml` | `OPERADOR_HML` | Não (`is_admin = 'N'`) | `EXEC_SCRIPT`, `VER_LOGS`, `CANC_TICKET` restrito a `CLONE6`, `CLONE7`, `GFPREPROD` | Teste de bloqueio de escopo de ambientes não autorizados |
| `consulta` | `CONSULTA` | Não (`is_admin = 'N'`) | `VER_LOGS` em todos os ambientes | Teste de perfil somente leitura (sem disparo nem alteração) |

* **Senha Padrão Inicial:** `Sss@Homolog2026!` (criptografada em PBKDF2-SHA256, 200k iterações).
* **Proteção de Senha:** O `MERGE` preserva senhas customizadas alteradas posteriormente pelos operadores.

---

## 19. Checklist de implantação (resumo)

- [ ] §3 Servidor Linux x86_64 com NTP e fuso `America/Sao_Paulo`
- [ ] §4 Usuário `sss` (sem login) e diretórios com donos/modos da tabela do §2
- [ ] §5 Código obtido por Git (commit fixado) ou pacote com SHA-256 conferido; só `script_scheduling_service` em `applications/`
- [ ] §6 Python ≥ 3.6.0 com PBKDF2 OK
- [ ] §7 `check_env.py` com código 0 e suíte com `OK (skipped=23)`
- [ ] §8.1 Árvore `/opt/automacoes/scripts` do root, sem escrita para o `sss`
- [ ] §8.2 `/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/instance` do `sss`, modo `0600`, com `cookie_key` gerado
- [ ] §8.3 Senha de demonstração (≥ 12 caracteres) combinada com a equipe
- [ ] §9 `config.ini` ajustado (DEV, FAKE, caminhos, `agent_id`, `script_owner_uids`, `allowed_origins`), sem `base_script_dirs` nem `app_log_backups`
- [ ] §10 Teste de carga: `SSS: configuracao OK`
- [ ] §11 Subida pelo `bin/sss-web.sh` com `-a '<recycle>' -i 127.0.0.1`
- [ ] §12 Validações por `curl` (200, cabeçalhos, 403) e teste de fumaça no navegador
- [ ] §13 Túnel SSH testado por um usuário da homologação
- [ ] §14 (opcional) Serviço `systemd` ativo
- [ ] §15.4 `httpserver.log` no `logrotate`

---

## 20. Desinstalação

```bash
sudo systemctl disable --now sss-web 2>/dev/null; sudo rm -f /etc/systemd/system/sss-web.service; sudo systemctl daemon-reload
sudo rm -rf /opt/sss /etc/sss /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/logs /portaloptrib/TESHUVA/web2py/applications/script_scheduling_service /opt/automacoes/scripts
sudo userdel sss
```

O FAKE não deixa dados em banco. Antes de apagar `/portaloptrib/TESHUVA/web2py/applications/script_scheduling_service/logs`, guarde os logs se forem evidência de homologação.

---

## 21. Variante: servidor compartilhado sem `sudo` nem `systemd` (registro do clone 7)

Implantação feita em 2026-10-15 no servidor **clone 7** (`brtlvlts1216pl`, 10.238.10.109), que serve de modelo para servidores parecidos. **Situação atual:** removida no mesmo dia, a pedido do responsável (o SSS passou para o servidor do §22); o `~/.sss` do clone 7 também foi apagado.

> **Registro histórico, anterior ao CR-005.** A árvore de scripts do próprio usuário (§21.2) e as chaves `base_script_dir(s)` e `app_log_backups` não valem mais: para a versão atual, siga o §8.1 (opção sem `sudo`) e o §16.3.

### 21.1 O que o servidor tinha

| Item | Situação | Decisão |
|---|---|---|
| Sistema | Oracle Linux 6.9 (glibc 2.12) | Funciona com o Python já instalado |
| Python | `/usr/local/bin/python3.7` (3.7.4), **sem `ssl` e sem `sqlite3`** | Usado como está. Correção do Rocket para Python sem `ssl` no commit `fdf6f35` (antes dela, cada conexão ociosa gerava `NameError` no log) |
| `git`, `sudo`, `systemd`, `crontab` | Ausentes ou sem permissão | Código por pacote (§5.2); tudo no usuário `mastersafgf`; processo mantido num `screen` |
| `/portaloptrib/TESHUVA` | Modo `777`, compartilhado com outros sistemas | Pasta própria `SSS/` com `0750`; segredos **fora** da árvore compartilhada, em `~/.sss` (`0700`) |
| Portas | Várias em uso por outros sistemas | Porta **18000**, somente `127.0.0.1` |

### 21.2 Estrutura instalada

| Caminho | Conteúdo | Modo |
|---|---|---|
| `/portaloptrib/TESHUVA/SSS/web2py` | Código (pacote `sss-fdf6f35.tar.gz`, SHA-256 conferido) | `0750` |
| `/portaloptrib/TESHUVA/SSS/scripts` | Árvore de scripts de exemplo, do próprio usuário, somente leitura | arquivos `0444`, diretórios `0555` |
| `/portaloptrib/TESHUVA/SSS/logs` | `sss_web.log` (aplicação) e `servidor.out` (saída do servidor) | `0750` |
| `/portaloptrib/TESHUVA/SSS/work` | Reservado ao agente (F8) | `0700` |
| `/portaloptrib/TESHUVA/SSS/pacotes` | Pacotes recebidos e `.sha256` | `0750` |
| `/portaloptrib/TESHUVA/SSS/iniciar_sss.sh`, `parar_sss.sh` | Operação | `0750` |
| `~/.sss/secrets.cfg` | `cookie_key` | `0600` |
| `~/.sss/web.env` | `SSS_DEV_SEED_PASSWORD` (gerada no servidor) e `SSS_TZ` | `0600` |

Diferenças do `config.ini` em relação ao exemplo: `secrets_file = /home/mastersafgf/.sss/secrets.cfg`, `agent_id = clone7-sss-hml`, `base_script_dir = /portaloptrib/TESHUVA/SSS/scripts`, `work_dir = /portaloptrib/TESHUVA/SSS/work`, `script_owner_uids = 4304` (UID do `mastersafgf`), `log_dir = /portaloptrib/TESHUVA/SSS/logs` e `allowed_origins = http://127.0.0.1:18000`.

### 21.3 Operação

```bash
/portaloptrib/TESHUVA/SSS/iniciar_sss.sh    # sobe no screen "sss" e confere o HTTP 200 do login
/portaloptrib/TESHUVA/SSS/parar_sss.sh      # Ctrl+C no screen e espera a porta 18000 ser liberada
screen -r sss                               # acompanhar a saída; sair SEM parar: Ctrl+A e depois D
cat ~/.sss/web.env                          # senha dos usuários de demonstração (admin, op.prod, op.hml, consulta)
tail -f /portaloptrib/TESHUVA/SSS/logs/sss_web.log
```

* O `iniciar_sss.sh` carrega `~/.sss/web.env` dentro do `screen` e chama `bin/sss-web.sh /usr/local/bin/python3.7 web2py.py -a '<recycle>' -i 127.0.0.1 -p 18000 --no_gui`. A senha não aparece na lista de processos.
* **Sem início automático:** se o servidor reiniciar, rode o `iniciar_sss.sh` de novo. Reiniciar o SSS restaura os dados de demonstração.
* Trocar a senha de demonstração: edite `~/.sss/web.env` e reinicie (`parar_sss.sh` + `iniciar_sss.sh`).

### 21.4 Acesso dos usuários

Túnel SSH da máquina do usuário (§13.1), com uma conta que tenha SSH no servidor. Este servidor exige os algoritmos RSA legados:

```bash
ssh -N -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa -L 18000:127.0.0.1:18000 <usuario>@10.238.10.109
# navegador: http://localhost:18000/script_scheduling_service
```

### 21.5 Validação realizada

* `check_env.py`: todos os itens OK; suíte completa no servidor: `Ran 615 tests ... OK (skipped=17)`.
* Teste de carga da configuração (§10): `SSS: configuracao OK (sss_env=DEV, backend=FAKE, agent_id=clone7-sss-hml)`.
* Escuta somente em `127.0.0.1:18000`; cabeçalhos de segurança presentes; POST com origem estranha → 403 (registrado no log); painel do web2py desabilitado (`parameters_18000.py` com `password=None`).
* Pelo túnel: login do `admin`, disparo de ticket, painel de agentes e logout, sem erros no console. Em seguida, reinício pelos scripts para entregar os dados de demonstração limpos.

---

## 22. Servidor acessado por salto: `brtlvlty3067sl` (10.129.164.55)

Implantação feita em 2026-10-15 com o pacote do commit `aca60b0` (código do `fdf6f35` mais documentação). **Este é o servidor ativo do SSS.**

> **Atualização pendente (CR-003, CR-004 e CR-005):** este servidor ainda roda o código do `fdf6f35`. O `config.ini` dele ainda tem `base_script_dir` e `app_log_backups`, que a versão atual recusa, e o log da aplicação ainda é o arquivo único `logs/sss_web.log`. O pacote da versão atual (`fe5884c`) e o roteiro de atualização, já ensaiados, estão no §22.6. O pacote `e8759e3`, preparado antes do CR-005, foi **descartado** e não deve ser instalado.

### 22.1 Diferenças em relação ao clone 7

| Item | Situação | Decisão |
|---|---|---|
| Acesso | Só pelo clone 7 (10.238.10.109); não há rota direta das estações | Cópia de arquivos e túnel pelo clone 7 (22.4) |
| Sistema | Oracle Linux 6.10 | — |
| Python | `/portaloptrib/TESHUVA/sparta/python3.8/bin/python3` (3.8.5), **sem `ssl`, sem `sqlite3` e sem `_hashlib`** | Usado como está: suíte completa OK, PBKDF2 em Python puro (0,28 s por login). **Risco:** esse Python pertence ao sistema Sparta; se for trocado ou removido, o SSS para |
| Ferramentas | `git`, `crontab` e `nohup` disponíveis; **sem `screen`/`tmux`**, `sudo` ou `systemd` | Processo com `nohup` e arquivo de PID |
| `/portaloptrib/TESHUVA` | Do próprio usuário, modo `755` (não compartilhado como no clone 7) | Mesma estrutura do §21.2, em `/portaloptrib/TESHUVA/SSS` |
| Porta | 18000 livre | `127.0.0.1:18000` |

`config.ini`: igual ao do clone 7, exceto `agent_id = srv3067-sss-hml` e `script_owner_uids = 4135` (UID do `mastersafgf` neste servidor). Segredos e senha de demonstração em `~/.sss` (`0600`), gerados no servidor.

### 22.2 Operação

```bash
/portaloptrib/TESHUVA/SSS/iniciar_sss.sh    # sobe com nohup, grava o PID em SSS/work/sss_web.pid e confere o HTTP 200
/portaloptrib/TESHUVA/SSS/parar_sss.sh      # SIGINT ao PID (só se o PID ainda for o do SSS), espera a porta ser liberada
tail -f /portaloptrib/TESHUVA/SSS/logs/servidor.out     # saída do servidor (equivale ao "screen -r" do clone 7)
tail -f /portaloptrib/TESHUVA/SSS/logs/sss_web.log      # log da aplicação (até a atualização do §22.6)
# depois do §22.6: tail -f "$(find /portaloptrib/TESHUVA/SSS/logs/app -name 'sss_web_*.log' -type f -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-)"
cat ~/.sss/web.env                                      # senha dos usuários de demonstração
```

* Os dois scripts são idempotentes: subir com o SSS no ar responde "O SSS ja esta rodando (PID ...)"; parar com ele parado responde "O SSS nao esta rodando.".
* O processo continua no ar depois que a sessão SSH é encerrada (`nohup`).

### 22.3 Início automático no boot (não ativado)

O `crontab` do usuário está vazio e **não foi alterado**. Para ativar, o responsável roda uma vez no servidor:

```bash
( crontab -l 2>/dev/null; echo "@reboot /portaloptrib/TESHUVA/SSS/iniciar_sss.sh >> /portaloptrib/TESHUVA/SSS/logs/servidor.out 2>&1" ) | crontab -
crontab -l      # conferir
```

Para desativar: `crontab -e` e apagar a linha. Depois de um reboot, os dados de demonstração voltam ao seed.

### 22.4 Acesso dos usuários (túnel pelo clone 7)

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

### 22.5 Validação realizada

* Pacote com SHA-256 conferido; `check_env.py` OK; suíte no servidor: `Ran 615 tests ... OK (skipped=17)`.
* Teste de carga da configuração: `SSS: configuracao OK (sss_env=DEV, backend=FAKE, agent_id=srv3067-sss-hml)`.
* Escuta só em `127.0.0.1:18000`; cabeçalhos de segurança presentes; origem estranha → 403; painel do web2py desabilitado.
* Processo vivo depois do fim da sessão SSH; reinício e idempotência dos scripts conferidos.
* Pelo túnel em dois trechos: login do `admin`, disparo de ticket, painel de agentes e logout, sem erros. Depois, reinício para entregar os dados de demonstração limpos.

### 22.6 Atualização para a versão `fe5884c` (CR-003, CR-004 e CR-005) — [substituída pelo §22.7; não executada]

O pacote `e8759e3` (CR-003 e CR-004), ensaiado antes do CR-005, foi descartado: a versão atual também muda a configuração e os logs.

| Item | Valor |
|---|---|
| Pacote | `sss-fe5884c.tar.gz` (13,8 MB), gerado por `git archive` (§5.2) do commit `fe5884c` |
| SHA-256 | `c68916bdff5e44ba4609c4e802326ff94b8f4bac7265bc10815debcd84616a60` |
| Onde está | Máquina de desenvolvimento: `/home/eduardof/sss_pacotes/` (pacote e `.sha256`) |
| Mudança de configuração | Duas, no `config.ini`: apagar a linha `base_script_dir = ...` e trocar `app_log_backups = 10` por `app_log_retention_days = 30`. `secrets.cfg` e `web.env` não mudam |
| Árvore de scripts | `$SSS/scripts` deixa de ser usada: os scripts do seed apontam para `/opt/automacoes/scripts/...`, que não existe neste servidor (sem `sudo`). A **Gestão de Scripts** mostra o aviso "Arquivo não encontrado neste servidor…" e o disparo cria o ticket normalmente (§8.1, opção sem `sudo`). A pasta pode ficar onde está |
| Logs | O log da aplicação passa para `$SSS/logs/app/AAAA/MM/DD/HH/MI/sss_web_<PID>.log` (§15.2). O `$SSS/logs/sss_web.log` antigo para de crescer e pode ser guardado como evidência |
| Parada | Cerca de 1 minuto (passo 6). Os dados de demonstração voltam ao seed, como em todo reinício |

**Ensaio (2026-10-16, na máquina de desenvolvimento, com o Python 3.8.5, a mesma versão do servidor, numa estrutura `$SSS` igual à do servidor):**
* `config.ini` do servidor reproduzido a partir do exemplo do `fdf6f35` (com `base_script_dir` e `app_log_backups`): sem conversão, a carga é recusada com `ConfigErro` "Chave desconhecida na secao [agent]: base_script_dir";
* passos 1 a 4 como abaixo: SHA-256 OK; só `script_scheduling_service` em `applications`; passo 2 deixa `app_log_max_bytes` e `app_log_retention_days = 30` e responde "chaves OK"; `check_env.py` com código 0; suíte `Ran 718 tests ... OK (skipped=18)`; teste de carga `SSS: configuracao OK (sss_env=DEV, backend=FAKE, agent_id=srv3067-sss-hml)`;
* subida pelo `bin/sss-web.sh` com `-a '<recycle>' -i 127.0.0.1`: login HTTP 200, os 4 cabeçalhos de segurança, origem estranha recusada com 403, painel do web2py desabilitado (`password=None`);
* log em `$SSS/logs/app/AAAA/MM/DD/HH/MI/sss_web_<PID>.log` (o teste de carga do passo 4 deixa um arquivo próprio, do minuto em que rodou), com `[agente=srv3067-sss-hml]`, nenhum `CRITICAL`, pastas `0750` e arquivos `0640`;
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
echo 'print("SSS: configuracao OK (sss_env=%s, backend=%s, agent_id=%s)" % (current.sss_cfg.app.sss_env, current.sss_cfg.app.data_backend, current.sss_cfg.agent.agent_id))' > /tmp/sss_diag.py
$PY web2py.py -S script_scheduling_service -M -R /tmp/sss_diag.py 2>&1 | grep -E "^SSS:|ConfigErro"
rm -f /tmp/sss_diag.py
# esperado: SSS: configuracao OK (sss_env=DEV, backend=FAKE, agent_id=srv3067-sss-hml)

# 5. Conferir que os scripts de operação usam o caminho $SSS/web2py e não dependem do log antigo
grep -n "web2py\|sss_web.log" $SSS/iniciar_sss.sh $SSS/parar_sss.sh

# 6. Trocar a versão (parada de ~1 minuto)
$SSS/parar_sss.sh
mv $SSS/web2py $SSS/web2py-fdf6f35 && mv $NOVO $SSS/web2py
$SSS/iniciar_sss.sh

# 7. Validar
curl -s -o /dev/null -w "login: HTTP %{http_code}\n" http://127.0.0.1:18000/script_scheduling_service/default/login     # 200
curl -sI http://127.0.0.1:18000/script_scheduling_service/default/login | grep -icE "content-security-policy|x-frame-options|x-content-type-options|referrer-policy"   # 4
curl -s -o /dev/null -w "origem estranha: HTTP %{http_code}\n" -X POST -H "Origin: http://outro-host" http://127.0.0.1:18000/script_scheduling_service/default/login   # 403
find $SSS/logs/app -name 'sss_web_*.log' -type f -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-   # log mais recente: o da subida
find $SSS/logs/app -name 'sss_web_*.log' -type f | xargs grep -c CRITICAL   # 0 em cada arquivo (o do passo 4 e o da subida)
tail -n 5 $SSS/logs/servidor.out
```

Se no passo 4 aparecer `ConfigErro` com "Chave desconhecida", a linha citada ficou no `config.ini`: apague-a ou corrija-a e repita o passo 4.

Depois, pelo túnel (§22.4), faça o teste de fumaça do §12: login, **O que eu posso fazer**, **Rotinas disponíveis**, disparo com o resumo (o comando mostra `/opt/automacoes/scripts/carga_diaria.py`), agentes e saída.

**Retorno (rollback), se algo falhar no passo 7:**

```bash
$SSS/parar_sss.sh
mv $SSS/web2py $SSS/web2py-$VER && mv $SSS/web2py-fdf6f35 $SSS/web2py
$SSS/iniciar_sss.sh
```

A versão anterior fica intacta em `$SSS/web2py-fdf6f35`, com o `config.ini` antigo. Apague essa pasta só depois do aceite da homologação. Depois da atualização, troque neste capítulo o commit do §22 para `fe5884c` e registre a validação no §22.5.

### 22.7 Atualização para a versão `17950fb` (CR-003 a CR-008) — [ensaiada; não executada no servidor]

Substitui o §22.6: o pacote `fe5884c` não chegou a ser aplicado e fica descartado. O servidor continua no `fdf6f35`, e esta atualização sai dele direto para o `17950fb`.

| Item | Valor |
|---|---|
| Pacote | `sss-17950fb.tar.gz` (14,6 MB), gerado por `git archive` (§5.2) do commit `17950fb` |
| SHA-256 | `d8c47422a8c5055e5b1b5a4c9886ddee8aa5503aa8a3447d02ced944ccf57e72` |
| Onde está | Máquina de desenvolvimento: `/home/eduardof/sss_pacotes/` (pacote, `.sha256` e o roteiro `ATUALIZAR-17950fb.txt`) |
| Mudança de configuração | No `config.ini`: apagar `base_script_dir`, trocar `app_log_backups` por `app_log_retention_days = 30` e acrescentar as chaves opcionais novas com o valor padrão (CR-007 e CR-008; passo 2). `secrets.cfg` e `web.env` não mudam: as seções `[ambiente:*]` do `secrets.cfg` antigo só geram WARN em DEV ("não pertence ao papel 'web'") |
| Árvore de scripts | Como no §22.6: os scripts do seed apontam para `/opt/automacoes/scripts/...`, que não existe neste servidor; a Gestão de Scripts avisa "Arquivo não encontrado neste servidor…" e o disparo funciona |
| Logs | `$SSS/logs/app/AAAA/MM/DD/HH/MI/sss_web_<PID>.log` (§15.2); o `$SSS/logs/sss_web.log` antigo para de crescer |
| Usuários | Todos precisam entrar de novo depois da troca (CR-008, E2: a sessão antiga não tem `sessao_epoch`). Os dados de demonstração voltam ao seed, como em todo reinício |
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
       -e '/^work_dir *=/a usuarios_execucao =\nexec_work_dir =' \
       -e '/^cron_horizon_days *=/a fila_envelhecimento_min = 60\nambientes_exigem_hash =\nlog_dir_min_livre_mb = 1024' \
       -e '/^session_idle_timeout_s *=/a sessao_max_horas = 12' \
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
echo 'print("SSS: configuracao OK (sss_env=%s, backend=%s, agent_id=%s)" % (current.sss_cfg.app.sss_env, current.sss_cfg.app.data_backend, current.sss_cfg.agent.agent_id))' > /tmp/sss_diag.py
$PY web2py.py -S script_scheduling_service -M -R /tmp/sss_diag.py 2>&1 | grep -E "^SSS:|ConfigErro"
rm -f /tmp/sss_diag.py
# esperado: SSS: configuracao OK (sss_env=DEV, backend=FAKE, agent_id=srv3067-sss-hml)

# 5. Conferir que os scripts de operação usam o caminho $SSS/web2py e exportam um locale UTF-8
grep -n "web2py\|sss_web.log\|LANG\|LC_ALL\|sss-web.sh" $SSS/iniciar_sss.sh $SSS/parar_sss.sh
# Se o iniciar_sss.sh não passar pelo bin/sss-web.sh nem exportar LANG/LC_ALL UTF-8, a subida é recusada
# (CR-007, R-17): acrescente "export LANG=C.UTF-8 LC_ALL=C.UTF-8" antes do comando do web2py.

# 6. Trocar a versão (parada de ~1 minuto)
$SSS/parar_sss.sh
mv $SSS/web2py $SSS/web2py-fdf6f35 && mv $NOVO $SSS/web2py
$SSS/iniciar_sss.sh

# 7. Validar
curl -s -o /dev/null -w "login: HTTP %{http_code}\n" http://127.0.0.1:18000/script_scheduling_service/default/login     # 200
curl -sI http://127.0.0.1:18000/script_scheduling_service/default/login | grep -icE "content-security-policy|x-frame-options|x-content-type-options|referrer-policy"   # 4
curl -s -o /dev/null -w "origem estranha: HTTP %{http_code}\n" -X POST -H "Origin: http://outro-host" http://127.0.0.1:18000/script_scheduling_service/default/login   # 403
find $SSS/logs/app -name 'sss_web_*.log' -type f | xargs grep -c CRITICAL   # 0 em cada arquivo
tail -n 5 $SSS/logs/servidor.out
```

Depois, pelo túnel (§22.4), faça o teste de fumaça do §12 e, se quiser, os casos CT-24 e CT-25 do manual v2.5 (reinicie o servidor no fim de cada um para restaurar o seed).

**Retorno (rollback), se algo falhar no passo 7:**

```bash
$SSS/parar_sss.sh
mv $SSS/web2py $SSS/web2py-$VER && mv $SSS/web2py-fdf6f35 $SSS/web2py
$SSS/iniciar_sss.sh
```

A versão anterior fica intacta em `$SSS/web2py-fdf6f35`, com o `config.ini` antigo. Apague essa pasta só depois do aceite da homologação. Depois da atualização, troque neste capítulo o commit do §22 para `17950fb` e registre a validação no §22.5.
