# Homologação e evidências: roteiro passo a passo

Como executar a homologação completa do SSS numa instalação real (DEV ou PROD, nesta máquina ou num servidor remoto como o 3067) e gerar o documento de evidências. É o procedimento usado nas rodadas registradas em `docs/homologation/` (a última: `SSS_Homologation_Evidence_2026-10-30_r4.docx`, 356/356).

O roteiro abre um navegador sem tela (Puppeteer), executa os casos de teste pelas telas, confere na própria página o resultado esperado de cada passo, fotografa as telas e grava o resultado de cada verificação. Os tickets rodam de verdade, nos agentes reais e no banco Oracle real. Ferramentas em `dev/others/homologation/tools/` (fora do pacote de implantação); detalhes das variáveis no `dev/others/homologation/README.md`.

---

## 1. O que a homologação produz

| Saída | Onde | Versionado? |
|---|---|---|
| Figuras de cada tela (`<CT>_<n>.png`) | `dev/others/homologation/evidence_<rodada>/` | Não (já ficam dentro do `.docx`) |
| `results.json`: cada verificação (descrição, OK ou não, detalhe) por caso | idem | **Sim** (o `.gitignore` ignora a pasta `evidence_*/`, com a exceção `!dev/others/homologation/evidence_*/results.json`) |
| `state.json`: ids e dados criados, para repetir só alguns casos | idem | Não |
| `execucao.log`: saída do roteiro (`[OK]`, `[NAO OK]`, `[fig]`, `[nota]`) | idem (redirecionada pelo comando) | Não (opcional) |
| Documento de evidências | `docs/homologation/SSS_Homologation_Evidence_<AAAA-MM-DD>[_r<n>].docx` | **Sim** |
| Resumo em texto | `docs/homologation/SSS_HOMOLOGATION_EVIDENCE_<AAAA-MM-DD>[_r<n>].md` | **Sim** |
| Registros na aplicação, marcados `HOMOLOG_<data>[R<n>]_*` (tickets, ambiente, perfil, regras pausadas) | banco da instalação | Ficam como evidência |
| Massa própria: perfil `HOMOLOG_RESTRITO` e usuário `homolog.restrito` (passo 3.1) | banco da instalação | Ficam, reaproveitados pela rodada seguinte (o usuário inativo entre as rodadas) |

---

## 2. Pré-requisitos da máquina que roda o roteiro

| Item | Como conferir |
|---|---|
| Node.js e Puppeteer | `node --version`; o roteiro procura o módulo em `PUPPETEER_MODULE`, `puppeteer` ou no cache do `npx` |
| Chrome do Puppeteer | padrão `~/.cache/puppeteer/chrome/linux-131.0.6778.204/chrome-linux64/chrome`; outro caminho em `SSS_CHROME` |
| Python com `python-docx` (para o `.docx`) | `~/.pyenv/versions/3.13.2/bin/python -c "import docx"`. O `python3` padrão desta máquina **não** tem |
| Arquivo da senha nova do admin | `~/.sss_homolog_pw`, modo `0600` (`stat -c %a ~/.sss_homolog_pw` → `600`). **Nunca** exibir o conteúdo |
| Repositório atualizado | `git status` limpo e `git log -1` no commit que será citado na evidência |
| Só no modo remoto: chave SSH | `ssh -o BatchMode=yes <conta>@<bastion> 'ssh -o BatchMode=yes <conta>@<servidor> true'` sem pedir senha |
| Só no modo remoto: túnel até o web | `make tunel-3067` (status) → `porta 18000: HTTP 200`; senão `make tunel-3067 CMD=start` |

As senhas nunca vão para o código, o comando ou o log:
- **senha inicial dos usuários do seed:** o roteiro a lê do `docs/DEPLOYMENT.md` (§5.3, documentada). É também a senha que o roteiro dá ao usuário de teste `homolog.restrito` (passo 3.1);
- **senha nova do admin**, usada a partir da troca do CT-01: o roteiro a lê do `~/.sss_homolog_pw` (ou de `SSS_ADMIN_NEW_PASSWORD_FILE`).

---

## 3. Pré-requisitos da instalação homologada

### 3.0 Pré-condições da homologação local (DEV desta máquina contra o GFPR)

Confira antes de subir o DEV local. Se alguma falhar, **não suba** e não rode o roteiro.

1. **O 3067 parado, DEV e PROD, quando ele já roda o código do prefixo fixo (a partir do `a75e3c1`).** O prefixo é fixo por tipo (`tbsdev_` no DEV, `tbsprd_` no PROD), e no owner `openrisow` do GFPR existe uma instalação por tipo (decisão 18; `docs/DEPLOYMENT-SERVER.md` §15.3 e Apêndice A). As tabelas são as mesmas do 3067: com ele no ar, os agentes dele disputariam os tickets da rodada, e a rodada mudaria os cadastros dele.
   - Enquanto o 3067 estiver num pacote anterior ao `a75e3c1` (prefixos `s3dev_`/`s3prd_`; ex.: o pacote `2610301500`, em 07/11/2026), as tabelas são outras, não há colisão e ele pode ficar no ar. Confira em cada raiz do 3067: `cat <RAIZ>/src/sss/BUILD` (o pacote no ar) e `grep -c 'def default_prefix' <RAIZ>/src/sss/core/sql_ident.py` → `0` no código antigo (pode ficar no ar), `1` no código do prefixo fixo (pare como abaixo).
   - No 3067, em cada tipo, pelo `bin/sss-ctl.sh`: `cron remove` e `stop` (como no passo 15.3 a do DEPLOYMENT-SERVER). Sem tirar o bloco do `crontab`, o keepalive sobe tudo de novo em até 5 minutos.
   - Confira: `bin/sss-ctl.sh status` sem processo no ar nos dois tipos e `crontab -l | grep -c sss-keepalive.sh` → `0`.
   - Registre a parada e, depois da rodada, devolva o 3067 ao ar (`start` e `cron install`, passos 12 e 14 do DEPLOYMENT-SERVER), com o DEV local parado antes.
   - No modo remoto (passo 6, homologar o próprio 3067), vale o inverso: o DEV e o PROD desta máquina parados.
2. **Esquema `tbsdev_` conferido antes de subir** (no `sqlplus` ou cliente equivalente, com a conta da instalação; a senha nunca no comando):
   - `SELECT COUNT(*) FROM all_tables WHERE owner = 'OPENRISOW' AND table_name LIKE 'TBSDEV\_%' ESCAPE '\';` → **21**;
   - `SELECT schema_version FROM openrisow.tbsdev_control;` → **1** (a versão do código: `grep -n '^SCHEMA_VERSION' src/sss/core/sql_ident.py`);
   - ou o `docs/sql/99_validate_deploy_openrisow_tbsdev.sql` inteiro, sem linha de falha;
   - `SELECT name FROM openrisow.tbsdev_profiles ORDER BY name;` → `ADMINISTRADOR`, `CONSULTA`, `OPERADOR` (mais o `HOMOLOG_RESTRITO` e os `HOMOLOG_<data>_P<hhmm>` de rodadas anteriores). Com outro número de tabelas, outra versão ou os perfis do seed antigo (`ADMINISTRATOR`, `OPERATOR_*`, `READ_ONLY`), **pare**: o esquema não é o do código (o seed só faz `MERGE`; nunca rode o `init_db` num banco em uso).
3. **Usuários do seed e senha.** O seed cadastra só `admin` (ADMINISTRADOR), `op.prod` (OPERADOR) e `consulta` (CONSULTA), com a senha inicial do `docs/DEPLOYMENT.md` §5.3 (o roteiro a lê de lá; não a copie para comando, log ou arquivo versionado).
   - `op.prod` e `consulta` precisam estar na senha inicial, ativos e desbloqueados (o CT-14 bloqueia e desbloqueia o `consulta`).
   - O `admin` está na senha inicial ou na do `~/.sss_homolog_pw`: decida o `SSS_ADMIN_START` no passo 4.
4. **Túnel do GFPR estável durante toda a rodada.** Nesta máquina, o DSN do GFPR é o túnel SSH `localhost:2424` (para `10.129.177.188:1521`; DEPLOYMENT-SERVER, Apêndice A). Se o túnel cair no meio, os agentes e o web recebem `ORA-12541` e a rodada se perde. Suba o túnel com keepalive, por exemplo `ssh -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -L 2424:10.129.177.188:1521 <conta>@<bastion>`, e confira a porta (`nc -z localhost 2424`) antes de subir o DEV local.

### 3.1 Massa própria do roteiro: perfil restrito e usuário de teste

O seed não tem mais perfil nem usuário de escopo restrito (o `11966d7` retirou o perfil de homologação antigo e o usuário dele). Os casos de escopo restrito usam uma massa própria, criada **pela tela, pelo admin**, no caso `PREPARO`, o primeiro da rodada:

| Item | Valor | O que tem |
|---|---|---|
| Perfil | `HOMOLOG_RESTRITO` (não administrativo) | As 7 funcionalidades de operação (`EXEC_SCRIPT`, `VIEW_LOGS`, `CANCEL_TICKET`, `DOWNLOAD_OUTPUT`, `UPLOAD_INPUT`, `FILES_UPLOAD`, `FILES_DOWNLOAD`), nenhuma de administração; ambientes `CLONE6`, `CLONE7` e `GFPREPROD` (`CLONE1` e `CLONE2` **fora**); os 14 utilitários do seed (lidos da matriz do `OPERADOR`) |
| Usuário | `homolog.restrito`, no perfil acima | Senha: a senha inicial documentada (a mesma do seed, lida do DEPLOYMENT.md); nenhuma senha no código |

- **Idempotente:** os nomes são fixos, com a marca `HOMOLOG`. Se já existem (rodada anterior), o `PREPARO` os reaproveita: reativa o perfil e o usuário, devolve a matriz exatamente ao escopo acima, devolve o usuário ao perfil e redefine a senha (o que zera tentativas e bloqueio). Não há inclusão repetida, então a mensagem de nome duplicado da tela nunca aparece.
- **O que cobre:** CT-01 (senha errada e login com espaços), CT-02 e CT-03 (painel e "O que eu posso fazer" com 3 ambientes), MASSA (tickets `ok_hml`, `erro_hml`, `ok_clone6`), CT-04, CT-06 (lista só com os ambientes do perfil), CT-07 (log com marcação HTML), CT-12 e CT-13 (matriz e Quem pode o quê), CT-14 (lista de usuários), CT-21 (ticket de CLONE2 → **404**; login com `next` externo), CT-22 (celular), CT-26 e CT-27 (o perfil perde `VIEW_LOGS` por alguns segundos e o recebe de volta), CT-29 (Entrada pela tela).
- **No fim:** o ENCERRAMENTO desativa o `homolog.restrito`; o `HOMOLOG_RESTRITO` fica ativo, sem usuário ativo. A próxima rodada os reativa no `PREPARO`.
- O seed fica intacto: nada é criado por SQL nem pelo `init_db`.

### 3.2 Instalação no ar

1. **Código no commit a homologar.**
   - No servidor: atualizado pelo `docs/DEPLOYMENT-SERVER.md` passo 15.1.
   - Confira a versão no log de subida do agente: `agente inicializado (versao 1.0.0-dev+<BUILD>`.
2. **Processos no ar:** o web e os 5 agentes, um por ambiente (GFPREPROD, CLONE2, CLONE1, CLONE6, CLONE7).
   - `make ctl` (ou `bin/sss-ctl.sh status` na raiz) mostra os 6 processos `no ar`.
   - `scripts/health.py --name agente0001` mostra `SSS OK - 0 problemas | healthy_agents=5`.
   - `scripts/check_env.py --name agente0001` termina com `Todos os pre-requisitos foram atendidos`.
3. **Scripts na pasta base** (`[agent] script_base_dir`; sem a chave, `scripts_ambiente/` da raiz), com `utilitarios/` e `diagnostico/`.
   - O seed cadastra **só** os 14 utilitários, com caminho relativo (`utilitarios/zipar_arquivos.py` etc.).
   - Os diagnósticos (`diagnostico/gerar_saida.sh`, `pasta_trabalho.sh`, `nao_existe.sh`, `interp_*.*`, `pasta_arquivos.sh`) **não** são do seed: o roteiro os cadastra pela tela nos CT-28 a CT-33 (`diag_*`, só GFPREPROD), roda e desativa no próprio caso. Os arquivos precisam estar em `scripts_ambiente/diagnostico/` (no DEV local e no servidor).
4. **Massa de teste** na pasta `inputs` do `agente0001` (GFPREPROD): textos para o `contar_linhas_arquivo` e o `gerar_hash_arquivo` e um lote grande para o ticket longo do `zipar_arquivos` (as telas de "Rodando" e o cancelamento em execução precisam dele).
   - Gere com `make homolog-massa` (DEV local; `LOTE_MB=` troca o tamanho do lote, padrão 4.608 MB).
   - No servidor, rode o `gerar_massa.py` lá, na raiz: `python3 gerar_massa.py --config instance/agente0001/config.ini --lote-mb 2048`.
   - Arquivo que já existe é mantido: rodar de novo é barato.
   - Confira antes o espaço livre da partição do `var/`.
5. **Interpretadores do CT-32** (CR-025 a CR-027):
   - um Python para o `#!` do `diagnostico/interp_py36.py`;
   - um Python para digitar com caminho completo;
   - um nome achado no `PATH` do agente;
   - o `python3` do `PATH` fixo do filho;
   - o virtualenv `~/.sss_homolog_venv`, criado com `python3 -m venv --without-pip ~/.sss_homolog_venv`.

   Os padrões são os do DEV local. Em outro servidor, passe os `SSS_HOM_*` (passo 6).
6. **Nenhum script de diagnóstico ativo sobrando de rodada anterior.** Um que ficou ativo muda a contagem da MASSA, do CT-04 e do `PREPARO` (se tiver ido para a matriz do `OPERADOR`); aconteceu na rodada 2 do 3067. Uma rodada que parou no meio deixa isso; o CT-33 completo o desativa.
7. **Nada disputando o banco:** não rode `make test-oracle` nem outra rodada ao mesmo tempo (e o passo 3.0, item 1).

---

## 4. Decidir os parâmetros da rodada

| Parâmetro | Regra |
|---|---|
| `SSS_EVIDENCE_DATE` | Data da rodada, `AAAAMMDD` (padrão: hoje). Use a mesma no roteiro e no gerador do `.docx` |
| `SSS_EVIDENCE_ROUND` | Próximo número livre do dia: veja `ls docs/homologation | grep <AAAA-MM-DD>`. Sem rodada no dia, pode omitir (1ª) |
| `SSS_EVIDENCE_DIR` | Pasta da rodada. Padrão `evidence_<data>[_r<n>]`; para servidor remoto use um nome que diga onde foi (ex.: `../evidence_20261030_3067_dev_r4`) |
| Senha do `admin` no início | **Senha inicial do seed** (banco novo ou refeito, ou rodada anterior com `SSS_ADMIN_RESET=seed`): **não** defina `SSS_ADMIN_START`. **Senha nova** (rodada anterior sem devolução): `SSS_ADMIN_START=new` |
| `SSS_ADMIN_RESET=seed` | Use quando a instalação deve manter os usuários do seed na senha inicial (o 3067, decisão 15): no encerramento o admin volta à senha inicial, e o roteiro confere com um login |
| `SSS_APP_ROOT` | Raiz da instalação (padrão: este repositório, o DEV local). Para o PROD local, `/portaloptrib/TESHUVA/SSS/PROD/script_scheduling_service`; no remoto, a raiz **no servidor** |
| `SSS_BASE_URL` | Endereço do web, com `/script_scheduling_service` no fim. Padrão `http://127.0.0.1:18000/...` |
| `SSS_AGENT_NAME` | Agente principal (padrão `agente0001`) |

Se o admin estiver numa senha diferente da que você escolheu, o CT-01 falha no primeiro login. Pare a rodada, ajuste o `SSS_ADMIN_START` e comece de novo, numa rodada nova.

---

## 5. Executar: DEV desta máquina

O túnel do 3067 ocupa as portas 18000 e 18001 desta máquina. Pare-o antes (`make tunel-3067 CMD=stop`), ou suba o DEV local em outra porta e passe `SSS_BASE_URL`.

```bash
cd /portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/dev/others/homologation/tools
E=../evidence_20261030_r5; mkdir -p $E          # troque data e rodada
SSS_EVIDENCE_DATE=20261030 SSS_EVIDENCE_ROUND=5 SSS_EVIDENCE_DIR=$E \
  node capture_evidence.js > $E/execucao.log 2>&1; echo "rc=$?"
```

Acrescente `SSS_ADMIN_START=new` ou `SSS_ADMIN_RESET=seed` conforme o passo 4. Pelo Makefile, `make homolog` faz o mesmo `node capture_evidence.js` (com `CTS="CT-01 CT-05"` para só alguns), lendo as variáveis `SSS_*` do ambiente.

## 6. Executar: servidor remoto (ex.: DEV do 3067)

O roteiro roda **nesta máquina**:
- o navegador chega ao web pelo túnel;
- o disco da instalação (configs, pastas do agente) é lido por `ssh` (`SSS_REMOTE_HOST` e, com salto, `SSS_REMOTE_JUMP`), só com chave. Falha de conexão (código 255) é tentada até 3 vezes.

Comando da rodada 4 de 30/10/2026, com o admin começando na senha inicial e voltando a ela:

```bash
cd /portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/dev/others/homologation/tools
E=../evidence_20261030_3067_dev_r4; mkdir -p $E
SSS_APP_ROOT=/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service \
SSS_BASE_URL=http://127.0.0.1:18000/script_scheduling_service \
SSS_REMOTE_HOST=mastersafgf@10.129.164.55 SSS_REMOTE_JUMP=mastersafgf@10.238.10.109 \
SSS_ADMIN_RESET=seed \
SSS_EVIDENCE_DATE=20261030 SSS_EVIDENCE_ROUND=4 SSS_EVIDENCE_DIR=$E \
SSS_HOM_SHEBANG=/portaloptrib/TESHUVA/sparta/python3.8/bin/python3.8 SSS_HOM_SHEBANG_VER=3.8.5 \
SSS_HOM_TYPED=/usr/bin/python2.6 SSS_HOM_TYPED_VER=2.6.6 \
SSS_HOM_NAME=python3.8 SSS_HOM_NAME_PATH=/portaloptrib/TESHUVA/sparta/python3.8/bin/python3.8 \
SSS_HOM_ENV_PYTHON3=/portaloptrib/TESHUVA/sparta/python3.8/bin/python3 \
SSS_HOM_VENV=/home/mastersafgf/.sss_homolog_venv \
  node capture_evidence.js > $E/execucao.log 2>&1; echo "rc=$?"
```

- Para o PROD do 3067: `SSS_APP_ROOT=/portaloptrib/TESHUVA/SSS/PROD/script_scheduling_service` e `SSS_BASE_URL=http://127.0.0.1:18001/script_scheduling_service`.
- Os `SSS_HOM_*` descrevem os interpretadores **daquele servidor**. Confira-os antes com `which python3.8 python3`, `ls` do venv e `python2.6 --version` lá.
- A rodada completa leva cerca de 30 minutos (a do 3067, pelo túnel). Rode em segundo plano e não use a instalação enquanto isso.

---

## 7. Ordem dos casos

`PREPARO → CT-01 → CT-02 → CT-03 → MASSA → CT-04 … CT-33 → ENCERRAMENTO` (36 casos). Cada caso depende do estado deixado pelos anteriores, guardado no `state.json`.

| Caso | O que confere |
|---|---|
| PREPARO | Massa própria (passo 3.1): perfil `HOMOLOG_RESTRITO` e usuário `homolog.restrito` criados ou reaproveitados pela tela, matriz conferida, login do usuário |
| CT-01 | Login, sessão e troca de senha do admin (para a senha do `~/.sss_homolog_pw`); senha errada e login com espaços com o `homolog.restrito` |
| CT-02, CT-03 | Painel inicial por perfil (`admin`, `op.prod`, `homolog.restrito`, `consulta`); "O que eu posso fazer" do `homolog.restrito` (só CLONE6, CLONE7 e GFPREPROD) |
| MASSA | Tickets reais criados pelas telas e executados pelos agentes (usa a massa do passo 3.2, item 4) |
| CT-04 a CT-09 | Rodar script e histórico, disparo, lista e filtros, detalhe e log, cancelamento, reexecução |
| CT-10 | Perfil somente leitura |
| CT-11 a CT-16 | Cadastros: ambientes (com o nome repetido, batimento A1), perfis e matriz (perfis do seed `ADMINISTRADOR`, `OPERADOR`, `CONSULTA` e o `HOMOLOG_RESTRITO`), quem pode o quê, usuários, parâmetros, scripts e vínculos |
| CT-17, CT-18 | Regras de agendamento e agenda dos próximos 7 dias |
| CT-19 | Auditoria: trilha, filtros e CSV |
| CT-20, CT-21 | Painel de agentes; acesso direto pela URL sem permissão (ticket de CLONE2 para o `homolog.restrito` → 404) |
| CT-22, CT-23 | Tema escuro e celular; quadro Registro |
| CT-24, CT-25 | Robustez do scheduler na interface; correções da auditoria final |
| CT-26, CT-27 | CR-017 e CR-018 (menu de tickets, um ambiente só, cancelar só quem enxerga, avisos de cadastro, desempenho) |
| CT-28 a CT-30 | Saídas (download), Entrada (envio, entrega, uso pelo script), pasta de trabalho |
| CT-31, CT-32 | Caminho relativo à pasta base; interpretador do disparo, do `#!` e do cadastro |
| CT-33 | Pasta de Arquivos (inputs, uso pelo script, outputs) |
| ENCERRAMENTO | Regras `HOMOLOG_*` pausadas (ficam como evidência); `homolog.restrito` desativado; com `SSS_ADMIN_RESET=seed`, admin de volta à senha inicial e login conferido |

---

## 8. Conferir o resultado

```bash
cd /portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/dev/others/homologation/tools
E=../evidence_20261030_3067_dev_r4
echo "OK=$(grep -c '\[OK\]' $E/execucao.log) NAO_OK=$(grep -c '\[NAO OK\]' $E/execucao.log)"
awk '/^=== /{ct=$2} /\[NAO OK\]/{print ct": "substr($0,1,170)}' $E/execucao.log    # o que falhou, por caso
grep -c '^=== ' $E/execucao.log                                                     # esperado: 36 casos
tail -5 $E/execucao.log                                                             # ENCERRAMENTO no fim
```

- `rc=0` e `NAO_OK=0`: a rodada passou. Siga para o passo 10.
- O total de verificações muda quando o roteiro ganha conferências: 352 na rodada 3 do 3067 e 356 na rodada 4, com o CT-11 novo. A primeira rodada com a massa própria muda de novo (caso `PREPARO` e a conferência do ENCERRAMENTO; o `PREPARO` também varia com o que já existia: inclusão ou reaproveitamento). Compare com a rodada anterior e explique a diferença na evidência.

## 9. Se algo falhou

1. **Leia a causa antes de repetir**, no `execucao.log` (a linha `[NAO OK]` e as `[nota]` do caso) e nos logs da instalação: o log da aplicação e o log do ticket. Classifique a falha:

   | Tipo | Exemplo real | O que fazer |
   |---|---|---|
   | Defeito do produto | rodada 1 do 3067: `env: python3: No such file` em 12 verificações | Corrigir no código, com teste, nova versão, nova rodada completa |
   | Defeito do roteiro | CT-32 da rodada 3: espera fixa de 1,5 s curta pelo túnel | Corrigir o `capture_evidence.js`, commitar, repetir só o caso |
   | Ambiente | script de diagnóstico ativo de rodada interrompida; falha de `ssh` | Corrigir o ambiente, repetir os casos afetados |

2. **Repetir só alguns casos** é permitido para defeito de roteiro ou de ambiente. Use a **mesma** pasta, data e rodada; o `state.json` traz o que os casos anteriores criaram. O log da repetição vai num arquivo separado:

   ```bash
   <as mesmas variaveis do passo 5 ou 6> node capture_evidence.js CT-32 > $E/repeticao_ct32.log 2>&1
   grep -c '\[OK\]' $E/repeticao_ct32.log; grep '\[NAO OK\]' $E/repeticao_ct32.log
   ```

   O `results.json` passa a ter o resultado da repetição para esses casos. Isso precisa ficar registrado na evidência (passo 10, `observacoes`).

   Depois do ENCERRAMENTO, o `homolog.restrito` está inativo: para repetir um caso que o usa (CT-01 a CT-04, MASSA, CT-06, CT-07, CT-12 a CT-14, CT-21, CT-22, CT-26, CT-27, CT-29), ponha o `PREPARO` antes (`node capture_evidence.js PREPARO CT-29`) e, no fim, desative-o de novo pela tela (ou rode o `ENCERRAMENTO`).
3. **Defeito do produto** pede uma rodada completa nova, no código corrigido. Não "consertar" o resultado.
4. **Nunca** edite o `results.json` nem o log à mão.

---

## 10. Gerar o documento de evidências

1. **Registre a rodada** em `dev/others/homologation/tools/build_evidence_docx.py`, no dicionário `RODADAS`. A chave é `<AAAAMMDD>[_r<n>]`, e a entrada herda da anterior parecida:

   ```python
   RODADAS["20261030_r4"] = dict(RODADAS["20261030_r3"], **{
       "commit": u"<commit> (<o que mudou>) instalado no DEV do <servidor> pelo sss-update.sh (pacote <BUILD>)",
       "defeitos": [],      # (titulo, onde, causa, correcao) de cada defeito achado nesta rodada
       "observacoes": [     # o que o leitor precisa saber: banco refeito, casos repetidos, senha do admin...
           u"... Marca %s." % STAMP,
       ],
       "massa_propria": True,   # seed depois do 11966d7 e caso PREPARO (passo 3.1); herdado pelas seguintes
   })
   ```

   - **Campos que mudam de instalação:** `instalacao`, `endereco`, `python`, `web`, `agente` e `seed_scripts` (veja a entrada `20261030_r2`, a primeira do 3067).
   - **Sem defeito nesta rodada:** `"defeitos": []`, para não herdar os da anterior.
   - **Repetição de casos:** registre-a nas `observacoes`.
   - **Massa própria:** a primeira rodada depois do `11966d7` marca `"massa_propria": True`. Com ela, o documento usa os perfis e usuários do seed novo, descreve o `PREPARO` e aplica o `ADAPTACAO_MASSA_PROPRIA` por cima dos textos herdados (os das rodadas até `20261030_r4` ficam como histórico, com o seed antigo e o `dev/scripts`).
2. **Gere**, com o Python que tem `python-docx`, a mesma data e rodada e a pasta da rodada:

   ```bash
   cd /portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/dev/others/homologation/tools
   SSS_EVIDENCE_DATE=20261030 SSS_EVIDENCE_ROUND=4 \
     ~/.pyenv/versions/3.13.2/bin/python build_evidence_docx.py ../evidence_20261030_3067_dev_r4
   ```

   Esperado (rodada 4 do 3067, ainda sem o `PREPARO`): `gerado: .../SSS_Homologation_Evidence_2026-10-30_r4.docx | casos: 35 | verificacoes: 356 / 356 | figuras: 111`, e o `.md` ao lado. Com a massa própria, `casos: 36`. Pelo Makefile: `make homolog-docx PYTHON=~/.pyenv/versions/3.13.2/bin/python`, que usa a pasta padrão `evidence_<data>[_r<n>]`; para outro nome, chame o script com a pasta, como acima.
3. **Revise o `.docx`** aberto, seção por seção:
   - 1. Resumo (commit, instalação, contagens);
   - 2. Preparação (web, agente, usuários e senhas, massa, registros mantidos);
   - 3. Defeitos;
   - 4. Observações;
   - 5. Casos, cada um com as verificações, as telas e o registro.

## 11. Conferir que nenhuma senha vazou

Confira o `.docx` (o XML de dentro), o `.md`, o `results.json` e o log. O resultado esperado é **0** em todos. As senhas não aparecem no comando nem na tela.

```bash
cd /portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service
D=2026-10-30_r4; E=dev/others/homologation/evidence_20261030_3067_dev_r4
X=$(mktemp -d); unzip -q docs/homologation/SSS_Homologation_Evidence_$D.docx -d $X
for f in $X/word/document.xml docs/homologation/SSS_HOMOLOGATION_EVIDENCE_$D.md $E/results.json $E/execucao.log; do
  echo "$(basename $f): $(grep -cF -f ~/.sss_homolog_pw $f)"      # senha do admin da homologacao: esperado 0
done
rm -rf $X
```

Confira também a senha do banco da instalação:
- **Local:** gere um arquivo `0600` com o `[oracle] password` do `instance/secrets.cfg`, use-o no `grep -cF -f` e apague-o em seguida.
- **Remoto:** a senha não está nesta máquina. Confira com o mesmo `grep`, digitando a senha num arquivo temporário `0600` que você apaga logo depois.

Com qualquer resultado diferente de 0: **não commite**. Descubra de onde veio e gere a evidência de novo.

## 12. Versionar

```bash
cd /portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service
git add docs/homologation/SSS_Homologation_Evidence_2026-10-30_r4.docx \
        docs/homologation/SSS_HOMOLOGATION_EVIDENCE_2026-10-30_r4.md \
        dev/others/homologation/evidence_20261030_3067_dev_r4/results.json \
        dev/others/homologation/tools/build_evidence_docx.py
git commit -m "Homologacao do DEV no 3067, rodada 4: 356/356 com o pacote 2610301500 (...)"
git push origin main
```

- As figuras e o `state.json` ficam fora: o `.gitignore` ignora a pasta `evidence_*/` inteira, salvo o `results.json` (exceção `!dev/others/homologation/evidence_*/results.json`), por isso o `git add` acima o aceita sem `-f`. O `execucao.log` não é versionado nas rodadas recentes.
- **Nunca** use `git add -A` sem a exclusão do `LEIA-ME.TXT`, e nunca commite `instance/secrets.cfg`.
- Se o roteiro mudou nesta rodada (correção ou caso novo), o `capture_evidence.js` vai num commit próprio, antes.

## 13. Depois da rodada

- Os registros `HOMOLOG_<data>[R<n>]_*` ficam no banco como evidência: regras pausadas, ambiente e perfil inativos, tickets terminados. Não apague.
- **Massa própria:** o perfil `HOMOLOG_RESTRITO` fica ativo e o usuário `homolog.restrito` inativo (ENCERRAMENTO), para a próxima rodada reaproveitar. Não apague nem os reative à mão.
- **3067:** numa homologação local, devolva o 3067 ao ar (passo 3.0, item 1) só depois de parar o DEV local.
- **Senha do admin:** com `SSS_ADMIN_RESET=seed`, voltou à senha inicial (confira a última linha do log: `Login do admin com a senha inicial`). Sem ele, ficou na senha do `~/.sss_homolog_pw`, e a próxima rodada usa `SSS_ADMIN_START=new`.
- **Massa:** fica na pasta `inputs` (o lote de GB). Apague só se o espaço fizer falta; a próxima rodada precisa dela.
- **Túnel:** pare-o se não for mais usar (`make tunel-3067 CMD=stop`).
- Registre o resultado onde o projeto acompanha o status (ex.: `PROJECT_CONTEXT.md` §5).

---

## 14. Problemas conhecidos

| Sintoma | Causa | Ação |
|---|---|---|
| `Puppeteer nao encontrado` (código 2) | módulo fora dos caminhos procurados | `PUPPETEER_MODULE=<caminho>/node_modules/puppeteer` |
| Chrome não abre | caminho do Chrome diferente | `SSS_CHROME=<caminho do chrome>` |
| `ModuleNotFoundError: No module named 'docx'` | `python3` sem `python-docx` | use `~/.pyenv/versions/3.13.2/bin/python` |
| CT-01 falha no primeiro login | `SSS_ADMIN_START` não bate com a senha atual do admin | passo 4; rodada nova |
| MASSA e CT-04 contam um script a mais | diagnóstico ativo de rodada interrompida | desative-o (ou rode o CT-33 completo) e repita MASSA e CT-04 |
| Falhas espalhadas no modo remoto, com `ssh` | bastion recusando conexões seguidas | o roteiro já tenta 3 vezes; repita os casos afetados |
| Mensagem que chega tarde pelo túnel | espera fixa curta no roteiro | o roteiro espera pela mensagem (`waitForFunction`); se aparecer outro caso, corrija o roteiro e repita só ele |
| Web local não sobe na 18000 | túnel do 3067 ocupando a porta | `make tunel-3067 CMD=stop` ou outra porta |
| Tickets da MASSA não terminam | agente sem a pasta base ou sem a massa | passo 3.2 (`script_base_dir`, `inputs` do `agente0001`) |
| `PREPARO`: "Scripts do seed lidos da matriz do OPERADOR" não OK | seed antigo (sem `OPERADOR`) ou matriz do `OPERADOR` mudada à mão | passo 3.0, item 2; devolva a matriz do `OPERADOR` aos 14 utilitários |
| CT-12, CT-13, CT-23 ou CT-25 sem os perfis `ADMINISTRADOR`, `OPERADOR`, `CONSULTA` | esquema com o seed antigo | passo 3.0, item 2 (pare; não é defeito do roteiro) |
| CT-01 e casos do `homolog.restrito` falham no login | `PREPARO` não rodou nesta pasta, ou o usuário ficou inativo (ENCERRAMENTO) | rode `PREPARO` antes (passo 9) |
| Tickets somem, são pegos por outro agente ou cadastros mudam sozinhos | o 3067 (ou outra instalação do mesmo tipo) no ar contra o mesmo esquema | passo 3.0, item 1; rodada nova |
