# CR-031: Ensaio da implantação de PROD (um usuário só)

| Campo | Valor |
|---|---|
| Status | **Encerrado** em 2026-10-27 |
| Origem | Pedido do responsável pelo produto: conferir todo o procedimento de implantação antes de levar ao PROD, no cenário real (um usuário de banco, um usuário do sistema operacional, sem root, só DEV e PROD) |
| Decisões | Repositório continua no DEV (nada é movido; o pacote já separa o que vai para servidor); cron **não** instalado (passadas simuladas à mão); ensaio em `/portaloptrib/TESHUVA/SSS/PROD/script_scheduling_service`, apagado no fim; banco do DEV, com o DEV parado e os nomes `web0001` e `agente0001` |

## 1. Roteiro executado

| Passo | Guia | Resultado |
|---|---|---|
| Pacote | DEPLOYMENT §3 (`make package`, `sha256sum -c`, extração, `sha256sum -c --quiet`) | OK; `ls` como o guia espera. **Achado 1** |
| Configuração | §4.0 e §7.1/§7.2 (cópia dos modelos, `sss_env = DEV`, conta única, sem `exec_users`, sem `[monitor]`; segredos `0600` copiados do DEV) | OK. **Achado 2** |
| Pastas | §4.0 item 5 (`prepare_dirs.py agente0001` e `web0001` com a própria conta); scripts de exemplo em `scripts_ambiente/` | OK; `var/`, `var/<nome>/` e `var/update/` criadas |
| Banco | §5 (`check_env --name`, `generate_sql --name`, `init_db --name agente0001 --dry-run`) | `generate_sql` e `init_db --dry-run` OK (21 tabelas, sem as colunas do purge). **Achado 3** no `check_env` |
| Subida sem cron | §10.6 (`sss-keepalive.sh web0001:18100 agente0001`) | passada 1 subiu os dois; passada 2 só conferiu; agente derrubado com `kill -9` voltou na passada seguinte |
| Validação | §11 e §13 | sem faixa de ambiente e rodapé "Ambiente PROD"; ticket 891 disparado pela web (login, CSRF, formulário) terminou `SUCCESS`, log em `var/agente0001/logs/clone1/...`; `health.py --name agente0001` sem `[monitor]`: `SSS OK` |
| Limpeza manual | README §11.3, só listando | `find` acha exatamente as pastas de minuto (7º nível); `SELECT COUNT` dos quatro alvos (12 envios com conteúdo a esvaziar); nada apagado |
| Atualização | §18.1 (`sss-update.sh` com tudo no ar e depois parado; `diff` com o modelo; subida; retorno) | recusa com código 3 com os processos no ar; atualização OK, `instance/`, `var/` e `scripts_ambiente/` intactos, correção do achado 3 entregue; retorno OK, subida da versão de retorno OK. **Achado 4** |
| Encerramento | — | ensaio parado e a pasta `PROD` apagada |

## 2. Achados e correções

| # | Achado | Correção |
|---|---|---|
| 1 | O §3 manda entrar em `/portaloptrib/TESHUVA/SSS/<TIPO>`, que só o §4.1 (root) cria | `mkdir -p` no bloco do §3 |
| 2 | Os modelos de `instance/exemplos/` só falam do cenário com administrador (`sss_env = PROD`, contas por papel, `exec_users`, `prepare_dirs` como root); o `diff` com o modelo, no §18.1, fica cheio de diferenças esperadas | Bloco "UM USUARIO SO" nos dois modelos, com o que muda |
| 3 | `check_env --name agente0001` carregava os segredos do papel web: a sondagem falhava ("[web] ausente") e a linha saía como OK | Papel tirado do config (`app.role`); sondagem que falha vira `FALHA`; teste `test_check_env.py` |
| 4 | Sem `systemd`, o §10.6 e o §18.1 não diziam como parar o web; um `pgrep -f` com o padrão na linha pega o próprio shell | Comando seguro no §10.6 (`grep '[p]ython3 scripts/run_web.py --name web0001'`) e passos 2, 6 e retorno do §18.1 sem `systemd` |

Observação sem correção: com o Python 3.6, o driver Oracle escreve avisos de depreciação no stderr; no `crontab` do §4.0 eles vão para o `health.txt` junto com a saída.

## 3. Linhas do `crontab` para o PROD

Para a conta que roda o SSS (`crontab -e`). Troque o Python, a porta e os dias da limpeza; comece a limpeza só listando (`-print`):

```text
PYTHON=/usr/bin/python3
SSS_TZ=America/Sao_Paulo
R=/portaloptrib/TESHUVA/SSS/PROD/script_scheduling_service
@reboot      cd $R && bin/sss-keepalive.sh web0001:18000 agente0001
*/5 * * * *  cd $R && bin/sss-keepalive.sh web0001:18000 agente0001
*/5 * * * *  cd $R && $PYTHON scripts/health.py --name agente0001 > var/agente0001/logs/health.txt 2>&1
15 2 * * *   cd $R && find var/*/logs var/*/output var/*/script_work -mindepth 7 -maxdepth 7 -type d -mtime +30 -exec rm -rf {} + ; find var/*/logs var/*/output var/*/script_work -mindepth 3 -type d -empty -delete
```

O `-mtime +30` precisa ser maior que o tempo máximo de um ticket (168 h no padrão, README §11.3).
