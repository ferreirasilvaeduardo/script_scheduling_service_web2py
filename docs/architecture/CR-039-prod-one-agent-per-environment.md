# CR-039: PROD com um agente por ambiente (ensaio e homologação)

| Campo | Valor |
|---|---|
| Status | **Encerrado** em 2026-10-29 |
| Origem | Pedido do responsável pelo produto: ensaio e homologação no PROD com os mesmos 5 agentes do DEV, um por ambiente |
| Decisões | Plano aprovado. Mesmos nomes do DEV (tabelas separadas: `tbsss_` no PROD, `ssdev_` no DEV): `agente0001` = GFPREPROD (fica com a massa e a pasta de entrada), `agente0002` = CLONE2, `agente0003` = CLONE1, `agente0004` = CLONE6 e `agente0005` = CLONE7. O PROD fica parado no fim, sem `crontab` |
| Código | Nenhuma mudança: só configuração do PROD e documentação |

## 1. Ensaio (DEPLOYMENT §7.1 "Mais de um agente no mesmo servidor" e §10.6)

| Passo | Resultado |
|---|---|
| Configuração | Cópia do `config.ini` atual do `agente0001`; `instance/agente0002` a `agente0005` criados como o §7.1 manda (`mkdir -m 0750`, cópia do `instance/exemplos/agente0001/config.ini.example`, `chmod 0640`), só com `name` e `environments`; `agente0001` com `environments = GFPREPROD`. `check_env --name` dos cinco conectou |
| Subida | `sss-keepalive.sh web0001:18100 agente0001 … agente0005`: os cinco no ar; `var/agente0002` a `agente0005` criadas na subida (cinco linhas `pasta criada` em cada um); `health.py`: `healthy_agents=5`, `SSS OK` |
| Cadastro | `tbsss_agents` com os cinco `ACTIVE`, um ambiente cada (a linha do `agente0001` passou a só `GFPREPROD`); cinco `AGENT_START` na auditoria. A linha antiga `srv-localhost-01` (`STOPPED`, anterior ao CR-028) fica como histórico |
| Isolamento | `kill -9` no `agente0003`: só ele caiu, e a passada seguinte do keepalive o subiu. `--pause` e `sss-stop.sh` no `agente0004`: o keepalive respeitou a pausa e o `health.py` deu `CRITICAL: ambiente CLONE6 ativo sem nenhum agente saudavel`; com `--resume`, de volta a `SSS OK` com os cinco |

**Achados (só documentação):**

| # | Achado | Correção |
|---|---|---|
| 1 | O exemplo de `crontab` do §4.0 só mostrava um agente | Linha comentada com os cinco nomes; um `health.py` basta |
| 2 | O §7.1 não dizia que cada agente se cadastra sozinho nem o efeito de parar um agente quando cada ambiente tem o seu | §7.1 completado (cadastro, linha atualizada, ambiente sem atendimento e `CRITICAL` do `health.py`) |
| 3 | O §13 não explicava que um agente derrubado (`kill -9`) continua contando como saudável até o heartbeat vencer, enquanto o parado pelo `sss-stop.sh` sai na hora | Nota na linha `ambiente X ativo sem nenhum agente saudavel` |

## 2. Homologação real no PROD

Rodada `SSS_ADMIN_START=new SSS_EVIDENCE_DATE=20261029 SSS_EVIDENCE_ROUND=6` (marca `HOMOLOG_20261029R6`), com `SSS_APP_ROOT` do PROD e os cinco agentes no ar: **353 de 353 verificações OK** na primeira passada, 35 casos, 110 figuras. Documento: `docs/homologation/SSS_Homologation_Evidence_2026-10-29_r6.docx` e `.md`. São 353: contra os 352 do DEV (r5), o CT-01 tem no PROD uma conferência a mais (o rodapé com o ambiente); contra os 352 do PROD na r4, o CT-33 ganhou a contagem dos arquivos de `inputs` no ajuste do roteiro para um agente por ambiente (`f74d340`).

No `tbsss_tickets`, cada ticket da rodada rodou no agente do seu ambiente: GFPREPROD no `agente0001` (21), CLONE2 no `agente0002` (4) e CLONE6 no `agente0004` (1). Os sem agente são os cancelados antes do claim, como o roteiro prevê. Os do CLONE2 e do CLONE6 no `agente0001` são da rodada r4 (CR-038), de quando o PROD tinha um agente só.

## 2.1 Comparação da documentação com o código (pedido do responsável)

Revisão só de leitura dos documentos vivos contra o código, durante a homologação: 21 achados, todos conferidos no código e corrigidos no texto. Os principais: o DEV_ENVIRONMENT mandava rodar no DEV o `02_rollback` do `tbsss` (apagaria as tabelas do PROD) e passou aos `*_ssdev.sql`, com aviso; o DEPLOYMENT e o README diziam que o `01` segue depois de um erro, mas ele para no primeiro (`WHENEVER SQLERROR EXIT FAILURE ROLLBACK`); o README dizia que `docs/sql/` só tem o DEV. Também: o README das ferramentas de homologação (CT-33, cinco agentes, variáveis do roteiro), a tela de Agentes sem interpretadores, o `sss-web.sh` com o nome do processo, a linha `@reboot` com os cinco agentes, a pasta `files` nas listas, os caminhos e o "prefixo padrão" dos `docs/explain` e o período de 90 dias da auditoria.

Decisão A: o `build_evidence_docx.py` passou a usar a data do dia quando falta `SSS_EVIDENCE_DATE`, como o `capture_evidence.js` (antes, a data fixa de 2026-10-23).

## 3. Estado final

O PROD fica parado no `3b56cbd`, com cinco agentes configurados (um por ambiente) e as pastas `var/agente0001` a `agente0005`. Para pô-lo em operação, a linha do keepalive no `crontab` leva os cinco nomes (DEPLOYMENT §4.0). A cópia do config anterior do `agente0001` (cinco ambientes) ficou guardada fora da instalação.
