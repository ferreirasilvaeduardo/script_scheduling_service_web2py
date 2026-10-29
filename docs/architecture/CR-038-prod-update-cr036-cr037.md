# CR-038: CR-036 e CR-037 no PROD (tabelas `tbsss_`)

| Campo | Valor |
|---|---|
| Status | **Encerrado** em 2026-10-29 |
| Origem | Pedido do responsável pelo produto: levar ao PROD as entregas do CR-036 (alertas no lugar de bloqueios) e do CR-037 (Pasta de Arquivos), com as tabelas do PROD (`table_prefix = tbsss_`) |
| Decisões | Plano aprovado; homologação completa no PROD (A). O PROD fica parado no fim, sem `crontab`, como desde o CR-033 |
| Versões | De `e0030e7` (CR-035) para `3b56cbd` (CR-037c), pelo pacote do `make package` |

## 1. Roteiro executado

| Passo | Resultado |
|---|---|
| Pacote | `make package` do `3b56cbd`; `sha256sum -c` OK |
| Atualização (DEPLOYMENT §18.1) | PROD parado e pausado; `sss-update.sh` com código 0 e pacote de retorno em `var/update/<data>/`; `sha256sum -c --quiet` OK; `instance/` e `scripts_ambiente/` idênticos byte a byte; `diff` dos configs com os modelos só com os valores da instalação |
| Banco (DEPLOYMENT §18.2), **sem `init_db`** | Arquivo com só os 8 blocos `MERGE` do `docs/sql/01_deploy_sss_openrisow_tbsss.sql` com `FILES_UPLOAD`/`FILES_DOWNLOAD` (2 em `tbsss_features`, 6 em `tbsss_profile_feature` para `ADMINISTRATOR`, `OPERATOR_PROD` e `OPERATOR_HML`), com `WHENEVER SQLERROR EXIT FAILURE ROLLBACK` e `COMMIT`, conferido antes (nenhum `DELETE`, `DROP` ou `ssdev_`). Resultado: 8 linhas, `tbsss_features` com 14, cada operador com 7, `READ_ONLY` com 1; cadastros, senhas e histórico do PROD intactos; o `ssdev_` do DEV não foi tocado |
| Scripts | `diagnostico/pasta_arquivos.sh` (CT-33) copiado para `scripts_ambiente/diagnostico/` |
| Subida e validação | `--resume` e keepalive (`web0001:18100`); HTTP 303/200/4 cabeçalhos/403; `files/index` sem login vai ao login (303); `health.py`: `SSS OK`; `check_env --name agente0001` conectou (thick, servidor 19.24); `pasta criada: files_dir` no log do agente; `var/agente0001/files` (`0755`) e `var/web0001/tmp` (`0700`) criadas na subida |

## 2. Homologação real no PROD

Rodada `SSS_ADMIN_START=new SSS_EVIDENCE_DATE=20261029 SSS_EVIDENCE_ROUND=4` (marca `HOMOLOG_20261029R4`), com `SSS_APP_ROOT` do PROD: **352 de 352 verificações OK**, 35 casos (com o CT-33 da Pasta de Arquivos), 110 figuras. Documento: `docs/homologation/SSS_Homologation_Evidence_2026-10-29_r4.docx` e `.md`.

A rodada completa teve 351/352. A falha era do roteiro: desde a correção do CR-037c, o sha256 fica no fim do detalhe da auditoria, além dos 80 caracteres visíveis da lista, e o CT-33 o procurava só no texto visível (na rodada do DEV, r3, a checagem passou por acaso, com uma linha antiga no formato curto). O roteiro passou a abrir o detalhe antes de conferir; o CT-33 foi repetido com 19/19.

## 3. Feito junto, a pedido, no DEV

* **Scripts SQL do DEV:** `docs/sql/*_ssdev.sql` (implantação, retorno e validação), gerados pelo config do agente do DEV, ao lado dos `*_tbsss.sql` do PROD. Os comentários de coluna das FKs citam `tbsss_<tabela>` nos dois prefixos (texto fixo do dicionário, sem efeito).
* **Um agente por ambiente no DEV:** `agente0001` = GFPREPROD (o de antes; a massa e a pasta de entrada do GFPREPROD ficam nele), `agente0002` = CLONE2, `agente0003` = CLONE1, `agente0004` = CLONE6 e `agente0005` = CLONE7, com o mesmo config enxuto (os `instance/<nome>/` ficam fora do git; DEV_ENVIRONMENT). O PROD continua com um agente. Conferido com o DEV subido pelo keepalive com os cinco nomes: as pastas `var/agente0002` a `var/agente0005` criadas na subida (cinco linhas `pasta criada` em cada agente novo), `healthy_agents=5` no `health.py`, `ssdev_agents` com os cinco `ACTIVE` e um ambiente cada (a linha do `agente0001` passou a só `GFPREPROD`), os `AGENT_START` na auditoria e o `tbsss_agents` do PROD intacto.

## 4. Estado final

O PROD fica parado no `3b56cbd`, com as tabelas `tbsss_` (14 funcionalidades) e um pacote de retorno novo em `var/update/`. O retorno ao `e0030e7` é o pacote de retorno do `sss-update.sh`; as duas funcionalidades novas ficam no banco, sem efeito na versão anterior.
