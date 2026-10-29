# Ferramentas de homologação (somente DEV)

Geram e conferem as figuras dos documentos de homologação em `docs/homologation/`. Ficam em `dev/`, fora do pacote de implantação (README §12.2).

## Evidências reais no DEV e no PROD (desde 2026-10-22)

`docs/homologation/SSS_Homologation_Evidence_<data>[_r<n>].docx`: os casos de teste do manual de UI Freeze executados de verdade no DEV ou no PROD (banco Oracle, servidor web e agentes reais), com a conferência de cada resultado esperado na própria página.

| Arquivo | Uso |
|---|---|
| `tools/capture_evidence.js` | Executa os casos (CT-01 a CT-33, a preparação da massa e o encerramento; o CT-31 é o caminho relativo do CR-023, o CT-32, o interpretador do disparo, do `#!` e do cadastro, do CR-025 ao CR-027, e o CT-33, a Pasta de Arquivos do CR-037) no navegador (Puppeteer), confere o resultado esperado de cada passo e grava as telas, `results.json`, `state.json` e o log em `evidence_<data>[_r<n>]/` |
| `tools/build_evidence_docx.py` | Gera o `.docx` de evidências de uma rodada, `evidence_<SSS_EVIDENCE_DATE>[_r<SSS_EVIDENCE_ROUND>]/` (`python-docx`) |
| `evidence_20261022/results.json`, `execucao.log` | Resultado de cada verificação e o log da execução que gerou o documento (versionados) |
| `evidence_20261022/*.png`, `state.json` | Capturas e estado da rodada; não versionados, porque as capturas já estão dentro do `.docx` |

Pré-requisitos: servidor web e os cinco agentes no ar, um por ambiente (no DEV, `bin/sss-keepalive.sh web0001:18000 agente0001 agente0002 agente0003 agente0004 agente0005`), os agentes com `[agent] script_base_dir` = `dev/scripts` do repositório (CR-023: o seed e os diagnósticos são cadastrados com caminho relativo, como `utilitarios/zipar_arquivos.py` e `diagnostico/gerar_saida.sh`) e a massa de teste na pasta `inputs` do `agente0001` (GFPREPROD), gerada por `python3 tools/gerar_massa.py` (texto para o `contar_linhas_arquivo` e o `gerar_hash_arquivo` e um lote de 4,5 GB para o ticket longo do `zipar_arquivos`). O roteiro lê o `instance/<SSS_AGENT_NAME>/config.ini` (padrão `agente0001`) e monta o agente de cada ambiente a partir de todos os `instance/*/config.ini` com `[agent]`. Para o CT-32 (CR-025 a CR-027): os Pythons 3.6.0 e 3.13.2 do pyenv, o `python3.12` no `PATH` do agente e em `/usr/bin` (para o `#!/usr/bin/env python3`), e o virtualenv `~/.sss_homolog_venv` (`/usr/bin/python3 -m venv --without-pip ~/.sss_homolog_venv`).

```bash
cd dev/others/homologation/tools
export SSS_EVIDENCE_DATE=20261029 SSS_EVIDENCE_ROUND=2   # a mesma rodada nos dois comandos
node capture_evidence.js                 # todos os casos, na ordem
node capture_evidence.js CT-05 CT-08     # só os casos pedidos (o estado fica em state.json)
python3 build_evidence_docx.py           # precisa da entrada da rodada em RODADAS
```

Variáveis do roteiro (`capture_evidence.js`):

| Variável | Uso |
|---|---|
| `SSS_APP_ROOT` | Raiz da instalação homologada (padrão este repositório, o DEV); para o PROD, a raiz do PROD |
| `SSS_BASE_URL` | Endereço do web (padrão `http://127.0.0.1:18000/script_scheduling_service`; o PROD usa a porta 18100) |
| `SSS_EVIDENCE_DATE`, `SSS_EVIDENCE_ROUND` | Data (`AAAAMMDD`, padrão a do dia) e número da rodada: carimbo `HOMOLOG_<data>[R<n>]` e pasta `evidence_<data>[_r<n>]` |
| `SSS_EVIDENCE_DIR` | Pasta de saída, no lugar da `evidence_<data>[_r<n>]` |
| `SSS_ADMIN_START=new` | O admin já está com a senha nova (rodada repetida no mesmo banco) |
| `SSS_AGENT_NAME` | Agente principal (padrão `agente0001`) |
| `SSS_CHROME`, `PUPPETEER_MODULE` | Navegador e módulo do Puppeteer |

O `build_evidence_docx.py` usa as mesmas `SSS_EVIDENCE_DATE` (padrão a data do dia) e `SSS_EVIDENCE_ROUND`; numa rodada de outro dia, passe a data.

Senhas: nunca no código nem no log. A senha inicial dos usuários do seed vem do `docs/DEPLOYMENT.md` (§5.3, documentada); a senha nova do admin, usada a partir da troca válida do CT-01, vem do arquivo `SSS_ADMIN_NEW_PASSWORD_FILE` (padrão `~/.sss_homolog_pw`, permissão 0600).

## Manual de UI Freeze (2026-10-18, histórico)

Figuras do `docs/homologation/SSS_Homologation_Manual_UI_Freeze.docx`, capturadas sobre o backend FAKE.

| Arquivo | Uso |
|---|---|
| `tools/capture_all_screens.js` | Executa os 25 casos de teste no navegador (Puppeteer) e grava as 68 telas em `screens/` |
| `tools/capture_remaining.js`, `tools/capture_ct25.js` | Recapturam só as figuras que faltaram ou só as do CT-25 |
| `tools/test_step.js`, `tools/test_step2.js` | Depuração de um passo isolado (login e formulário de ambientes) |
| `tools/update_docx_images.py` | Troca as figuras do `.docx` pelas de `screens/` (cria um `.bak` antes) |
| `tools/verify_docx_images.py` | Lista as figuras do `.docx` com as dimensões |
| `all_cts_steps.txt`, `all_figures.txt` | Texto dos casos de teste e mapa figura → imagem, extraídos do manual |
| `screens/` | As 68 capturas (`image<n>.png`); não versionadas, porque já estão dentro do `.docx` |

Uso, com o servidor de DEV em `http://127.0.0.1:8000`:

```bash
cd dev/others/homologation/tools
read -s -p "Senha do admin do DEV: " SSS_HOMOLOG_PASSWORD && export SSS_HOMOLOG_PASSWORD && echo
node capture_all_screens.js
python3 update_docx_images.py && python3 verify_docx_images.py
```

A senha nunca fica no código: sem `SSS_HOMOLOG_PASSWORD`, os scripts param com código 2. O caminho do Chrome do Puppeteer está fixo nos `.js` (`executablePath`); ajuste-o na sua máquina.
