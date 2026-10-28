# Histórico do guia de implantação (registro)

Conteúdo retirado do `docs/DEPLOYMENT.md` no CR-032 (passo 032d2, D15, 2026-10-28), guardado como registro. **Não é procedimento vigente**: o guia atual é o `docs/DEPLOYMENT.md`. As referências `§n` abaixo são da versão anterior do guia.

* **Parte 1:** migração da instalação anterior ao CR-028 (`/opt/sss/app`) e notas por versão daquele formato, com os SQL de migração do CR-023, CR-025, CR-026 e CR-030.
* **Parte 2:** o antigo Apêndice B, com os registros dos servidores de homologação (clone 7 e `brtlvlty3067sl`), anteriores ao CR-005.

---

## Parte 1. Instalação anterior ao CR-028

### 1.1 Da instalação anterior para a estrutura por processo (CR-028, D9)

Uma instalação no formato anterior (`/opt/sss/app`, `/etc/sss/secrets.cfg`, `/var/lib/sss`, `/var/log/sss`) passa para a `<RAIZ>` **uma vez**, com tudo parado:

1. Instale o pacote novo na `<RAIZ>` (§3) e apague o `sudoers` e o helper da instalação anterior (§8).
2. Divida o `config.ini` antigo em um por processo (`instance/web0001/`, `instance/agente0001/`, §7.1), a partir dos modelos: copie só as chaves que fogem do padrão, e apague as de pastas (elas saem do nome). Divida o `secrets.cfg` da mesma forma (§7.2).
3. **Mova** os dados de cada agente: `log_dir` → `var/<nome>/logs`, `output_dir` → `var/<nome>/output`, `input_dir` → `var/<nome>/input`, `script_work_dir` → `var/<nome>/script_work`. O `work_dir` não precisa ir: pare os agentes sem tickets `RUNNING` e ele é recriado vazio. Depois de mover, acerte o dono para a conta do serviço.
4. Troque as units do `systemd` pelas novas, por nome (§10.5), e o monitoramento (`--name`, §13); a limpeza passa a ser manual (§12).
5. Suba, valide (§11) e só depois apague as pastas antigas. Retorno: as pastas antigas continuam intactas até esse passo.

### 1.2 Notas por versão (formato anterior ao CR-028)

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

## Parte 2. Apêndice B. Registros de servidores de homologação

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
