# CR-035: Ensaio da atualização do PROD e nova homologação no PROD

| Campo | Valor |
|---|---|
| Status | **Encerrado** em 2026-10-29 |
| Origem | Pedido do responsável pelo produto: novo ensaio em PROD e nova homologação no PROD, com o mesmo banco |
| Decisões | D1 A: atualização no lugar pelo `bin/sss-update.sh`, com o retorno ensaiado (e não uma instalação do zero). Mantidas as do CR-033: mesmos nomes `web0001`/`agente0001` com o DEV parado, e o PROD instalado e parado no fim, sem `crontab` |
| Versões | De `5c0383d` (instalado no CR-033) para `e0030e7` (CR-033 e CR-034), pelo pacote do `make package` (2,7 MB) |

## 1. Roteiro executado (DEPLOYMENT §18.1)

| Passo | Resultado |
|---|---|
| Pacote | `make package` (primeiro uso do Makefile do CR-033): `.bkp/pacote_<data>/` com o pacote, o `SHA256SUMS` e o `COMMIT`; `sha256sum -c` OK |
| Recusa com tudo no ar | `sss-update.sh` com o web e o agente no ar: código 3, "processo do SSS em execucao nesta pasta"; nada mudou (sem `var/update/`) |
| Parada | `sss-keepalive.sh --pause` dos dois, `sss-stop.sh agente0001`, SIGTERM no web; uma passada do keepalive pausado não subiu nada |
| Atualização | Código 0; pacote de retorno em `var/update/<data>/`; `.update-<data>/` apagada; `sha256sum -c --quiet` OK; `docs/homologation/` saiu do servidor (CR-033, D3) |
| Pastas preservadas | `instance/` e `scripts_ambiente/` idênticos byte a byte (`sha256sum`); em `var/`, só o que a parada e a subida gravam (logs, `keepalive.pause`, a trava) |
| Configuração | `diff` com os modelos novos: só os valores da instalação (ambientes, origem, conta e DSN); nenhuma chave nova ou retirada |
| Subida e validação | `--resume` e keepalive; HTTP 303/200/4 cabeçalhos/403/404; rodapé "Ambiente **PROD**"; `health.py`: `SSS OK`; `check_env --name` dos dois conectou ao banco (thick, servidor 19.24; CR-034, D6) e mostrou o orçamento de 30 s |
| Retorno | Parada, `sss-update.sh` com o pacote de retorno: código antigo de volta (`check_env` sem o CR-033), `SSS OK`; parada e reaplicação do `e0030e7`, `SSS OK` |
| Pastas depois das três trocas | `instance/` e `scripts_ambiente/` idênticos aos de antes do ensaio |

Nenhum achado no procedimento. O guia ganhou a marca "[ensaiado no CR-031 e no CR-035]" no §18 e as notas da versão do CR-033/CR-034 no §18.2.

## 2. Homologação real no PROD atualizado

Rodada `SSS_ADMIN_START=new SSS_EVIDENCE_DATE=20261029` (marca `HOMOLOG_20261029`), com o roteiro `capture_evidence.js` e `SSS_APP_ROOT` do PROD: **333 de 333 verificações OK**, 34 casos, 102 figuras, na primeira passada. Ressalvas de sempre: CT-20 (um agente só) e CT-24 (responsável inativo). Documento: `docs/homologation/SSS_Homologation_Evidence_2026-10-29.docx` e `.md`.

## 3. Documentos revisados a pedido

O responsável pediu, durante o ensaio, que `ADMIN_CRUD_PATTERN.md`, `DEPLOYMENT.md`, `DEV_ENVIRONMENT.md` e `UTILITY_SCRIPTS.md` fossem conferidos contra o README e as últimas mudanças:

| Documento | Correção |
|---|---|
| `ADMIN_CRUD_PATTERN.md` | Nenhuma: funções do `admin_crud.py` e componentes citados existem |
| `UTILITY_SCRIPTS.md` | Instalação em PROD sem `sudo` nem `/opt/automacoes`: cópia para `<RAIZ>/scripts_ambiente/utilitarios/` com a conta do SSS e a pasta base padrão; 17 exemplos de linha de comando; 12 funcionalidades; operadores com `DOWNLOAD_OUTPUT` e `UPLOAD_INPUT`, como no seed |
| `DEV_ENVIRONMENT.md` | Referência ao DEPLOYMENT sem "usuário de serviço" e "systemd"; contagem da suíte (1499); `script_works/`; tabela de usuários do seed com 12 funcionalidades e as permissões novas |
| `DEPLOYMENT.md` | `outputs`/`script_works` no §12; `make package` no §3; marca de ensaio e notas da versão no §18 |

## 4. Estado final

O PROD fica parado no `e0030e7`, com três pacotes de retorno em `var/update/` (podem ser apagados à mão depois de validar a versão, §18.1). A massa de teste continua em `var/agente0001/inputs`.
