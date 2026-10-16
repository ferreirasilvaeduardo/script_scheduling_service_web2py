# SSS — Guia de Implantação em Outro Servidor

| Campo | Valor |
|---|---|
| Público | Quem vai instalar e operar o SSS num servidor novo (infraestrutura, desenvolvimento, homologação) |
| Versão do sistema | 0.1.0 — commit de referência `fdf6f35` ou posterior (fases F0.1 a F6.1 concluídas) |
| Validação | Procedimento **ensaiado de ponta a ponta** em 2026-10-15 num clone limpo do repositório (Python 3.6.0 e 3.13) e **implantado** no mesmo dia no servidor clone 7 (Oracle Linux 6.9, Python 3.7 sem `ssl`, sem `sudo` nem `systemd` — registro no §21). O que não foi ensaiado está marcado como **[não ensaiado]** |
| Documentos relacionados | `README.md` (regras de negócio e arquitetura), `AGENTS.md` (regras de desenvolvimento), `docs/AMBIENTE_DEV.md` (estação do desenvolvedor), `docs/homologacao/SSS_Manual_Homologacao_UI_Freeze.docx` (roteiro de homologação) |

---

## 1. Leia antes: o que dá para implantar hoje

O SSS está sendo construído em fases (`docs/prompts/00_INDEX.md`). Hoje está pronta a **interface web completa sobre o backend FAKE** (dados de demonstração em memória). O banco Oracle real (F7), o agente executor (F8) e o pacote de produção (F9) **ainda não existem**.

| Cenário | Possível hoje? | Por quê |
|---|---|---|
| **Servidor de homologação visual** (UI Freeze): web + backend FAKE, `sss_env = DEV` | **Sim** — é o que este guia instala | Tudo implementado e testado |
| Homologação integrada ou produção (`sss_env = HML`/`PROD`) | **Não** | O backend FAKE é proibido fora de DEV (a subida aborta) e o backend ORACLE ainda não foi implementado (F7) |
| Execução real de scripts | **Não** | O agente executor (`run_scheduler.py`) é o F8. No FAKE, os tickets "em execução" são simulados |
| Nó web em Windows | **Não** | A camada de plataforma Windows é o F8.0. Hoje o nó web roda em **Linux** (x86_64) |

> **Consequências práticas do backend FAKE:**
> * os dados ficam **na memória do processo**: reiniciar o servidor apaga tudo o que foi feito e restaura o seed;
> * ele exige **um único processo** web (o servidor embutido do web2py). Não use gunicorn/uWSGI com vários workers;
> * por regra do projeto, o servidor DEV escuta **somente em `127.0.0.1`**. Os usuários acessam por túnel SSH (§13).

O capítulo 18 lista o que preparar desde já para a implantação definitiva (Oracle + agentes).

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
| `/etc/sss/secrets.cfg` | Segredos | `sss` | arquivo `0600`, diretório `0700` |
| `/var/log/sss` | Logs da aplicação | `sss` | `0750` |
| `/var/lib/sss/work` | Diretório de trabalho do agente (reservado ao F8) | `sss` | `0700` |
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
sudo useradd --system --create-home --home-dir /var/lib/sss --shell /sbin/nologin sss
# Em Debian/Ubuntu, se /sbin/nologin não existir, use /usr/sbin/nologin

# 4.2 Diretórios
sudo install -d -o sss -g sss -m 0750 /opt/sss
sudo install -d -o sss -g sss -m 0700 /etc/sss
sudo install -d -o sss -g sss -m 0750 /var/log/sss
sudo install -d -o sss -g sss -m 0700 /var/lib/sss/work

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
git checkout fdf6f35        # ou a tag/commit homologado
git log --oneline -1
```

Se o repositório for privado, use um *deploy token* de leitura ou a opção 5.2. Nunca grave credenciais do Git no servidor.

### 5.2 Servidor sem acesso ao Git (air-gapped)

Na máquina que tem o repositório:

```bash
cd /caminho/do/repositorio
git archive --format=tar.gz -o sss-fdf6f35.tar.gz fdf6f35
sha256sum sss-fdf6f35.tar.gz > sss-fdf6f35.tar.gz.sha256
```

Copie os dois arquivos para o servidor (por exemplo, `scp` para `/tmp`) e:

```bash
# como sss
cd /tmp && sha256sum -c sss-fdf6f35.tar.gz.sha256      # deve responder "OK"
mkdir -p /opt/sss/web2py && tar -xzf /tmp/sss-fdf6f35.tar.gz -C /opt/sss/web2py
```

O pacote do `git archive` (~11 MB) não contém `config.ini`, `secrets.cfg`, logs nem arquivos de parâmetros do web2py: eles são criados nos passos seguintes.

### 5.3 Conferência

```bash
cd /opt/sss/web2py
ls                      # deve listar web2py.py, gluon/, applications/, bin/, routes.py ...
ls applications         # deve listar SOMENTE script_scheduling_service
ls applications/script_scheduling_service/instance   # config.ini.example e secrets.cfg.example
```

As aplicações de exemplo do web2py (`admin`, `welcome`, `examples`) **não** vêm no repositório, por segurança. Isso é intencional.

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
# esperado no final: "Ran 615 tests ... OK (skipped=17)" (o total cresce com as versões)
# Os 17 "skipped" são testes de banco Oracle real e de Windows; é o resultado esperado.
```

Não prossiga se algum desses passos falhar.

---

## 8. Pré-requisitos de dados: árvore de scripts, segredos e senha de demonstração

### 8.1 Árvore de scripts de exemplo (necessária para disparar tickets)

Ao criar um ticket, o servidor valida o script com o `path_guard` (README §8.5): o arquivo precisa existir dentro de uma das pastas base de `base_script_dirs`, e o script, **cada diretório** do caminho e a própria base precisam pertencer a um UID de `script_owner_uids`, sem escrita para grupo/outros e **sem escrita para o usuário `sss`**. O modelo correto é a árvore pertencer ao `root`:

```bash
sudo install -d -o root -g root -m 0755 /opt/automacoes
sudo cp -r /opt/sss/web2py/applications/script_scheduling_service/dev/scripts /opt/automacoes/scripts
sudo rm -f /opt/automacoes/scripts/.gitkeep
sudo chown -R root:root /opt/automacoes/scripts
sudo find /opt/automacoes/scripts -type d -exec chmod 0755 {} +
sudo find /opt/automacoes/scripts -type f -exec chmod 0644 {} +

# conferência: o usuário sss lê, mas não escreve
sudo -u sss test -r /opt/automacoes/scripts/carga_diaria.py && echo "leitura OK"
sudo -u sss test -w /opt/automacoes/scripts/carga_diaria.py || echo "sem escrita OK"
```

No `config.ini` (§9): `base_script_dirs = ROTINAS=/opt/automacoes/scripts` e `script_owner_uids = 0`. Para usar mais de uma pasta, liste `NOME=caminho` separados por vírgula (README §8.5); cada pasta segue o mesmo padrão de dono e modo acima.

> **Atualização de instalações anteriores (CR-003):** a chave antiga `base_script_dir = <caminho>` deixou de ser aceita. Antes de atualizar o código, troque-a por `base_script_dirs = ROTINAS=<caminho>` no `config.ini`; senão a subida é abortada com CRITICAL na chave `base_script_dir`.

> Sem `sudo` (árvore pertencente ao próprio `sss`), use a alternativa do `docs/AMBIENTE_DEV.md` §6.1: modos `0444`/`0555` e o UID do `sss` em `script_owner_uids`. Essa variante foi a usada no ensaio.

### 8.2 Segredos (`/etc/sss/secrets.cfg`)

O arquivo precisa ser **regular, pertencer ao usuário que roda o processo (`sss`) e ter modo `0600`**; caso contrário a aplicação não sobe (§17). Com o backend FAKE, basta a chave do cookie de sessão:

```bash
# como sss
umask 077
$PYTHON -c "import secrets; print('[web]'); print('cookie_key = ' + secrets.token_urlsafe(48))" > /etc/sss/secrets.cfg
chmod 600 /etc/sss/secrets.cfg
ls -l /etc/sss/secrets.cfg        # -rw------- 1 sss sss ...
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
| `[secrets]` | `secrets_file` | `/etc/sss/secrets.cfg` | Caminho absoluto do §8.2 |
| `[agent]` | `agent_id` | identificador do servidor, ex.: `srv-sss-hml-01` | Aparece em todas as linhas de log; `^[A-Za-z0-9._-]{1,30}$` |
| `[agent]` | `base_script_dirs` | `ROTINAS=/opt/automacoes/scripts` (uma ou mais pastas `NOME=caminho`, README §8.5) | §8.1 |
| `[agent]` | `script_owner_uids` | `0` | UID do dono da árvore (root). Na variante sem sudo, o UID do `sss` (`id -u sss`) |
| `[agent]` | `work_dir` | `/var/lib/sss/work` | Reservado ao agente (F8) |
| `[logging]` | `log_dir` | `/var/log/sss` | Criado com `0750` se não existir |
| `[logging]` | `level` | `INFO` | `DEBUG` só para investigação |
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

### 11.1 Subida interativa (primeira vez e testes)

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
| `bin/sss-web.sh` | Launcher do projeto: **recusa root**, aplica `umask 077`, exporta `TZ` (de `SSS_TZ`) e substitui o próprio processo pelo comando (`exec`), para que os sinais de parada cheguem direto ao servidor |
| `web2py.py` | Servidor web embutido do web2py (Rocket), multithread em **um único processo**, como o FAKE exige |
| `-a '<recycle>'` | Senha do painel administrativo do web2py. `<recycle>` reaproveita a existente ou, na primeira vez, **desabilita** o painel (que nem é implantado). Assim nenhuma senha aparece na lista de processos (`ps`). **Não** use `-a 'senha'` |
| `-i 127.0.0.1` | Escuta só local (regra do projeto em DEV). **Nunca** use `0.0.0.0` |
| `-p 8000` | Porta. Se mudar, ajuste o túnel (§13) e `allowed_origins` |
| `--no_gui` | Sem interface gráfica do web2py |

A subida está pronta quando aparece `please visit: http://127.0.0.1:8000/`. Para parar: **Ctrl+C**.

Na **primeira** subida aparece no terminal `New installation error: unable to create welcome.w2p file` com um traceback. É **esperado e inofensivo**: o web2py tenta empacotar a aplicação de exemplo `welcome`, que foi removida de propósito.

### 11.2 Arquivos criados pela subida

| Arquivo | O que é |
|---|---|
| `/opt/sss/web2py/parameters_8000.py` | Senha (hash) do painel do web2py; com `<recycle>` na primeira vez, `password=None` |
| `/opt/sss/web2py/httpserver.log` | Log de acesso do servidor web (uma linha por requisição) |
| `/var/log/sss/sss_web.log` | Log da aplicação (§15.2) |
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

# 12.4 Log da aplicação sendo escrito
tail -n 5 /var/log/sss/sss_web.log
```

Depois, pelo navegador (via túnel, §13.1), faça o **teste de fumaça**:

1. Abrir `http://localhost:8000/script_scheduling_service` → tela **Entrar**, com a faixa "AMBIENTE DEV".
2. Entrar com `admin` e a senha do §8.3 → **Painel inicial** "Olá, Administrador Geral", com os cartões de tickets, agendamentos e saúde dos agentes.
3. **Disparar script** → `carga_diaria` → `PRODUCAO` → **Criar ticket** → confirmar → mensagem "Ticket #41 criado com sucesso." (prova que a árvore de scripts do §8.1 está correta).
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
ReadWritePaths=/opt/sss/web2py /var/log/sss /var/lib/sss

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
| Aplicação | `/var/log/sss/sss_web.log` (rotação automática: 10 MB × 10 arquivos) | Formato `data nível [pid] [agente] [ticket] [acao] mensagem`. Login, logout, criação/cancelamento de ticket, negações de acesso, recusas de CSRF/origem. **Nunca** contém senhas nem valores sigilosos |
| Acesso HTTP | `/opt/sss/web2py/httpserver.log` | Uma linha por requisição (IP, método, caminho, status) |
| Serviço | `journalctl -u sss-web` | Saída do processo quando rodando por systemd |
| Erros internos | `APP/errors/` | Ver 15.3 |

Exemplos úteis:

```bash
grep -E " (WARNING|ERROR|CRITICAL) " /var/log/sss/sss_web.log | tail -n 20     # problemas recentes
grep "acao=LOGIN" /var/log/sss/sss_web.log | tail -n 20                        # logins e logouts
grep "acao=CSRF\|acao=RBAC" /var/log/sss/sss_web.log | tail -n 20              # recusas de segurança
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

* `sss_web.log` tem rotação própria. `httpserver.log` **não**: inclua-o no `logrotate` da empresa (`copytruncate`, semanal, 4 cópias) ou apague-o periodicamente com o serviço parado.
* `APP/errors/` só cresce quando há erro interno; limpe após a análise.

---

## 16. Atualização de versão e retorno

```bash
# 16.1 Parar o servidor (§15.1) e guardar a configuração local
cp /opt/sss/web2py/applications/script_scheduling_service/instance/config.ini /var/lib/sss/config.ini.bak

# 16.2 Trocar o código
cd /opt/sss/web2py
git fetch && git checkout <novo-commit-ou-tag>          # opção Git
# ou, sem Git: extrair o novo pacote numa pasta nova (/opt/sss/web2py-<versao>), copiar
# instance/config.ini para ela e trocar o caminho no systemd/atalhos

# 16.3 Conferir se o config.ini.example ganhou ou perdeu chaves
diff <(grep -oE "^[a-z_]+ =" applications/script_scheduling_service/instance/config.ini.example | sort) \
     <(grep -oE "^[a-z_]+ =" applications/script_scheduling_service/instance/config.ini | sort)
# qualquer diferença precisa ser refletida no config.ini antes de subir

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
| Idem | `ConfigErro: Arquivo de segredos nao encontrado: /etc/sss/secrets.cfg` | Caminho de `secrets_file` errado ou arquivo ausente | §8.2 e §9 |
| Idem | `ConfigErro: Arquivo de segredos possui permissoes inseguras (mode 644, esperado sem acesso grupo/outros)` | Modo diferente de `0600` | `chmod 600 /etc/sss/secrets.cfg` |
| Idem | `ConfigErro: Arquivo de segredos deve pertencer ao usuario corrente (UID ..., atual ...)` | O processo roda com outro usuário, ou o arquivo foi criado pelo root | `sudo chown sss:sss /etc/sss/secrets.cfg` e suba como `sss` |
| Idem | `ConfigErro: Chave cookie_key obrigatoria ausente em [web]` | `secrets.cfg` incompleto | §8.2 |
| Idem | `ConfigErro` citando `[secao] chave` e motivo | Chave ausente, desconhecida ou fora da faixa no `config.ini` | Compare com o `config.ini.example` (§16.3) |
| Idem | `ConfigErro: [app]: data_backend: data_backend=FAKE exige sss_env=DEV (atual: HML)` | `sss_env` diferente de `DEV` com FAKE | `sss_env = DEV` |
| Ninguém consegue entrar ("Usuário ou senha inválidos.") | `sss_web.log`: `SSS_DEV_SEED_PASSWORD ausente: usuarios do seed FAKE sem senha utilizavel` (ou `fora da politica`) | Variável ausente ou com menos de 12 caracteres | §8.3 e reinicie |
| Um usuário específico não entra | Tela: "Acesso temporariamente bloqueado por excesso de tentativas. Tente novamente mais tarde." | 5 senhas erradas seguidas: bloqueio de 15 minutos (`login_bloqueio_s`) | Aguarde, ou reinicie o servidor (restaura o seed) |
| Launcher aborta | `Erro: execucao como root nao e permitida.` | Executado como root | Use `sudo -u sss -H bash` |
| Servidor não sobe: porta ocupada | Terminal: `Socket 127.0.0.1:8000 in use by other process and it won't share.` | Outro processo na porta 8000 | `ss -ltnp | grep 8000`; pare o outro processo ou troque a porta |
| Formulários retornam "Requisição recusada." (HTTP 403) | `sss_web.log`: `requisicao rejeitada (motivo=origem ...)` | Acesso por endereço que não está em `allowed_origins` (típico com proxy reverso) | Incluir a URL pública em `allowed_origins` (§13.2) |
| Idem | `motivo=csrf` | Página aberta há muito tempo ou sessão expirada | Recarregar a página e repetir |
| Sessão cai sozinha | "Sua sessão expirou por inatividade." | 30 min sem uso (`session_idle_timeout_s`) | Comportamento esperado |
| Criar ticket falha com aviso de script indisponível | `sss_web.log`: `path_guard rejeitou o script (... codigo=...)` | Árvore de scripts fora do padrão do §8.1 (dono, modo, gravável pelo `sss`, ou `base_script_dirs` errado) | Refazer §8.1 e conferir `base_script_dirs`/`script_owner_uids` |
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
| Banco Oracle | 11gR2 (11.2.0.4) ou superior, charset AL32UTF8; schema/owner da aplicação (ex.: `gfcadastro`), usuário de aplicação e *grants*; espaço para as 16 tabelas `tbsss_*` | README §2.2, §10, §11.1 |
| Conectividade | Rota e firewall dos servidores web/agentes até o listener Oracle (porta 1521) | README §2.3 |
| Oracle Instant Client 19 | Obrigatório se o banco for 11g (o modo Thin não conecta ao 11g); recomendado em todos os nós como contingência | README §2.3, CR-002 |
| Driver Python | `python-oracledb` (`< 2.0` na 3.6; `2.x` na 3.7+) com `cryptography`, e `cx_Oracle 8.3` como contingência, **pré-instalados** pela infraestrutura | AGENTS §2.2 |
| Servidores agentes | Linux e/ou Windows Server 2016+, com conta de serviço sem privilégio administrativo; interpretadores (`python3`, `bash`, `sh`, `powershell`) nos caminhos que serão mapeados | README §2.6, §8.5, CR-001 |
| Árvore de scripts real | Dono root (Linux) ou Administradores (Windows), sem escrita para a conta do agente | README §8.5 |
| HTTPS e DNS | Nome e certificado para o nó web em HML/PROD (`sss_env = HML/PROD` exige cookie `Secure`) | README §4.2 |
| Credenciais | Senha do Oracle e credenciais por ambiente para o `secrets.cfg`, entregues por canal seguro | README §4.1 |

---

## 19. Checklist de implantação (resumo)

- [ ] §3 Servidor Linux x86_64 com NTP e fuso `America/Sao_Paulo`
- [ ] §4 Usuário `sss` (sem login) e diretórios com donos/modos da tabela do §2
- [ ] §5 Código obtido por Git (commit fixado) ou pacote com SHA-256 conferido; só `script_scheduling_service` em `applications/`
- [ ] §6 Python ≥ 3.6.0 com PBKDF2 OK
- [ ] §7 `check_env.py` com código 0 e suíte com `OK (skipped=17)`
- [ ] §8.1 Árvore `/opt/automacoes/scripts` do root, sem escrita para o `sss`
- [ ] §8.2 `/etc/sss/secrets.cfg` do `sss`, modo `0600`, com `cookie_key` gerado
- [ ] §8.3 Senha de demonstração (≥ 12 caracteres) combinada com a equipe
- [ ] §9 `config.ini` ajustado (DEV, FAKE, caminhos, `agent_id`, `allowed_origins`)
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
sudo rm -rf /opt/sss /etc/sss /var/log/sss /var/lib/sss /opt/automacoes/scripts
sudo userdel sss
```

O FAKE não deixa dados em banco. Antes de apagar `/var/log/sss`, guarde os logs se forem evidência de homologação.

---

## 21. Variante: servidor compartilhado sem `sudo` nem `systemd` (registro do clone 7)

Implantação feita em 2026-10-15 no servidor **clone 7** (`brtlvlts1216pl`, 10.238.10.109), que serve de modelo para servidores parecidos. **Situação atual:** removida no mesmo dia, a pedido do responsável (o SSS passou para o servidor do §22); o `~/.sss` do clone 7 também foi apagado.

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

Diferenças do `config.ini` em relação ao exemplo: `secrets_file = /home/mastersafgf/.sss/secrets.cfg`, `agent_id = clone7-sss-hml`, `base_script_dirs = ROTINAS=/portaloptrib/TESHUVA/SSS/scripts`, `work_dir = /portaloptrib/TESHUVA/SSS/work`, `script_owner_uids = 4304` (UID do `mastersafgf`), `log_dir = /portaloptrib/TESHUVA/SSS/logs` e `allowed_origins = http://127.0.0.1:18000`.

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

### 22.1 Diferenças em relação ao clone 7

| Item | Situação | Decisão |
|---|---|---|
| Acesso | Só pelo clone 7 (10.238.10.109); não há rota direta das estações | Cópia de arquivos e túnel em dois saltos (22.4) |
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
tail -f /portaloptrib/TESHUVA/SSS/logs/sss_web.log      # log da aplicação
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

### 22.4 Acesso dos usuários (túnel com salto pelo clone 7)

Um único comando, na máquina do usuário (Linux, macOS ou Windows 10+):

```bash
ssh -N -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa \
    -o "ProxyCommand=ssh -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa -W %h:%p mastersafgf@10.238.10.109" \
    -L 18000:127.0.0.1:18000 mastersafgf@10.129.164.55
# navegador: http://localhost:18000/script_scheduling_service
```

* A senha é pedida **duas vezes**: a primeira do clone 7, a segunda do 10.129.164.55 (ambos aceitam senha). Quem tiver chave autorizada nos dois servidores não digita nada.
* Na primeira conexão, o SSH pede para confiar na chave do servidor novo. A impressão digital correta é `SHA256:Gpacuzn+pHDGaLIHMxMnl8l0UVGvNE5N7Dkp3VzHpcM` (RSA 2048, a mesma que o clone 7 já confia).
* No Windows, o comando funciona no PowerShell (OpenSSH do Windows 10+). No PuTTY, use *Connection → Proxy* tipo "Local" com o comando `plink mastersafgf@10.238.10.109 -nc %host:%port` e o túnel de *Connection → SSH → Tunnels* (18000 → `127.0.0.1:18000`). **[não ensaiado]**
* **Alternativa em dois trechos** (usada na validação): no clone 7, `ssh -f -N -L 18001:127.0.0.1:18000 mastersafgf@10.129.164.55 </dev/null >/dev/null 2>&1`; na estação, `ssh -N -o HostKeyAlgorithms=+ssh-rsa -L 18000:127.0.0.1:18001 mastersafgf@10.238.10.109`. Lembre de encerrar o trecho do clone 7 depois (`kill` no PID do `ssh -f`).

### 22.5 Validação realizada

* Pacote com SHA-256 conferido; `check_env.py` OK; suíte no servidor: `Ran 615 tests ... OK (skipped=17)`.
* Teste de carga da configuração: `SSS: configuracao OK (sss_env=DEV, backend=FAKE, agent_id=srv3067-sss-hml)`.
* Escuta só em `127.0.0.1:18000`; cabeçalhos de segurança presentes; origem estranha → 403; painel do web2py desabilitado.
* Processo vivo depois do fim da sessão SSH; reinício e idempotência dos scripts conferidos.
* Pelo túnel em dois trechos: login do `admin`, disparo de ticket, painel de agentes e logout, sem erros. Depois, reinício para entregar os dados de demonstração limpos.
