# Homologação e evidências: roteiro passo a passo

Como executar a homologação completa do SSS numa instalação real (DEV ou PROD, nesta máquina ou num servidor remoto como o 3067) e gerar o documento de evidências. É o procedimento usado nas rodadas registradas em `docs/homologation/` (a última: `SSS_Homologation_Evidence_2026-10-30_r4.docx`, 356/356).

O roteiro abre um navegador sem tela (Puppeteer), executa os casos de teste pelas telas, confere na própria página o resultado esperado de cada passo, fotografa as telas e grava o resultado de cada verificação. Os tickets rodam de verdade, nos agentes reais e no banco Oracle real. Ferramentas em `dev/others/homologation/tools/` (fora do pacote de implantação); detalhes das variáveis no `dev/others/homologation/README.md`.

---

## 1. O que a homologação produz

| Saída | Onde | Versionado? |
|---|---|---|
| Figuras de cada tela (`<CT>_<n>.png`) | `dev/others/homologation/evidence_<rodada>/` | Não (já ficam dentro do `.docx`) |
| `results.json`: cada verificação (descrição, OK ou não, detalhe) por caso | idem | **Sim** |
| `state.json`: ids e dados criados, para repetir só alguns casos | idem | Não |
| `execucao.log`: saída do roteiro (`[OK]`, `[NAO OK]`, `[fig]`, `[nota]`) | idem (redirecionada pelo comando) | Não (opcional) |
| Documento de evidências | `docs/homologation/SSS_Homologation_Evidence_<AAAA-MM-DD>[_r<n>].docx` | **Sim** |
| Resumo em texto | `docs/homologation/SSS_HOMOLOGATION_EVIDENCE_<AAAA-MM-DD>[_r<n>].md` | **Sim** |
| Registros na aplicação, marcados `HOMOLOG_<data>[R<n>]_*` (tickets, ambiente, perfil, regras pausadas) | banco da instalação | Ficam como evidência |

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
- **senha inicial dos usuários do seed:** o roteiro a lê do `docs/DEPLOYMENT.md` (§5.3, documentada);
- **senha nova do admin**, usada a partir da troca do CT-01: o roteiro a lê do `~/.sss_homolog_pw` (ou de `SSS_ADMIN_NEW_PASSWORD_FILE`).

---

## 3. Pré-requisitos da instalação homologada

1. **Código no commit a homologar.**
   - No servidor: atualizado pelo `docs/DEPLOYMENT-SERVER.md` passo 15.1.
   - Confira a versão no log de subida do agente: `agente inicializado (versao 1.0.0-dev+<BUILD>`.
2. **Processos no ar:** o web e os 5 agentes, um por ambiente (GFPREPROD, CLONE2, CLONE1, CLONE6, CLONE7).
   - `make ctl` (ou `bin/sss-ctl.sh status` na raiz) mostra os 6 processos `no ar`.
   - `scripts/health.py --name agente0001` mostra `SSS OK - 0 problemas | healthy_agents=5`.
   - `scripts/check_env.py --name agente0001` termina com `Todos os pre-requisitos foram atendidos`.
3. **Scripts do seed e de diagnóstico na pasta base** (`[agent] script_base_dir`). O seed cadastra caminhos relativos (`utilitarios/zipar_arquivos.py`, `diagnostico/gerar_saida.sh`).
   - No DEV local, a pasta base é `dev/scripts` do repositório.
   - No servidor, é `scripts_ambiente/`, com `utilitarios/` (do `utilitarios.tar.gz` do pacote) e `diagnostico/`.
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
6. **Nenhum script de diagnóstico ativo sobrando de rodada anterior.** Um que ficou ativo muda a contagem da MASSA e do CT-04 (aconteceu na rodada 2 do 3067). Uma rodada que parou no meio deixa isso; o CT-33 completo o desativa.
7. **Nada disputando o banco:** não rode `make test-oracle` nem outra rodada ao mesmo tempo.

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

`CT-01 → CT-02 → CT-03 → MASSA → CT-04 … CT-33 → ENCERRAMENTO` (35 casos). Cada caso depende do estado deixado pelos anteriores, guardado no `state.json`.

| Caso | O que confere |
|---|---|
| CT-01 | Login, sessão e troca de senha do admin (para a senha do `~/.sss_homolog_pw`) |
| CT-02, CT-03 | Painel inicial por perfil; "O que eu posso fazer" |
| MASSA | Tickets reais criados pelas telas e executados pelos agentes (usa a massa do passo 3.4) |
| CT-04 a CT-09 | Rodar script e histórico, disparo, lista e filtros, detalhe e log, cancelamento, reexecução |
| CT-10 | Perfil somente leitura |
| CT-11 a CT-16 | Cadastros: ambientes (com o nome repetido, batimento A1), perfis e matriz, quem pode o quê, usuários, parâmetros, scripts e vínculos |
| CT-17, CT-18 | Regras de agendamento e agenda dos próximos 7 dias |
| CT-19 | Auditoria: trilha, filtros e CSV |
| CT-20, CT-21 | Painel de agentes; acesso direto pela URL sem permissão |
| CT-22, CT-23 | Tema escuro e celular; quadro Registro |
| CT-24, CT-25 | Robustez do scheduler na interface; correções da auditoria final |
| CT-26, CT-27 | CR-017 e CR-018 (menu de tickets, cancelar só quem enxerga, avisos de cadastro, desempenho) |
| CT-28 a CT-30 | Saídas (download), Entrada (envio, entrega, uso pelo script), pasta de trabalho |
| CT-31, CT-32 | Caminho relativo à pasta base; interpretador do disparo, do `#!` e do cadastro |
| CT-33 | Pasta de Arquivos (inputs, uso pelo script, outputs) |
| ENCERRAMENTO | Regras `HOMOLOG_*` pausadas (ficam como evidência); com `SSS_ADMIN_RESET=seed`, admin de volta à senha inicial e login conferido |

---

## 8. Conferir o resultado

```bash
cd /portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/dev/others/homologation/tools
E=../evidence_20261030_3067_dev_r4
echo "OK=$(grep -c '\[OK\]' $E/execucao.log) NAO_OK=$(grep -c '\[NAO OK\]' $E/execucao.log)"
awk '/^=== /{ct=$2} /\[NAO OK\]/{print ct": "substr($0,1,170)}' $E/execucao.log    # o que falhou, por caso
grep -c '^=== ' $E/execucao.log                                                     # esperado: 35 casos
tail -5 $E/execucao.log                                                             # ENCERRAMENTO no fim
```

- `rc=0` e `NAO_OK=0`: a rodada passou. Siga para o passo 10.
- O total de verificações muda quando o roteiro ganha conferências: 352 na rodada 3 do 3067 e 356 na rodada 4, com o CT-11 novo. Compare com a rodada anterior e explique a diferença na evidência.

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
   })
   ```

   - **Campos que mudam de instalação:** `instalacao`, `endereco`, `python`, `web`, `agente` e `seed_scripts` (veja a entrada `20261030_r2`, a primeira do 3067).
   - **Sem defeito nesta rodada:** `"defeitos": []`, para não herdar os da anterior.
   - **Repetição de casos:** registre-a nas `observacoes`.
2. **Gere**, com o Python que tem `python-docx`, a mesma data e rodada e a pasta da rodada:

   ```bash
   cd /portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service/dev/others/homologation/tools
   SSS_EVIDENCE_DATE=20261030 SSS_EVIDENCE_ROUND=4 \
     ~/.pyenv/versions/3.13.2/bin/python build_evidence_docx.py ../evidence_20261030_3067_dev_r4
   ```

   Esperado: `gerado: .../SSS_Homologation_Evidence_2026-10-30_r4.docx | casos: 35 | verificacoes: 356 / 356 | figuras: 111`, e o `.md` ao lado. Pelo Makefile: `make homolog-docx PYTHON=~/.pyenv/versions/3.13.2/bin/python`, que usa a pasta padrão `evidence_<data>[_r<n>]`; para outro nome, chame o script com a pasta, como acima.
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

- As figuras e o `state.json` ficam fora (`.gitignore`); o `execucao.log` não é versionado nas rodadas recentes.
- **Nunca** use `git add -A` sem a exclusão do `LEIA-ME.TXT`, e nunca commite `instance/secrets.cfg`.
- Se o roteiro mudou nesta rodada (correção ou caso novo), o `capture_evidence.js` vai num commit próprio, antes.

## 13. Depois da rodada

- Os registros `HOMOLOG_<data>[R<n>]_*` ficam no banco como evidência: regras pausadas, ambiente e perfil inativos, tickets terminados. Não apague.
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
| Tickets da MASSA não terminam | agente sem a pasta base ou sem a massa | passo 3 (`script_base_dir`, `inputs` do `agente0001`) |
