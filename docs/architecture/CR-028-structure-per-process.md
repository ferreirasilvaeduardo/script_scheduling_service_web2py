# CR-028: Estrutura idêntica por processo (web0001, agente0001...)

| Campo | Valor |
|---|---|
| Status | **Encerrado** em 2026-10-27 (028d). Pedido e decisões do responsável pelo produto em 2026-10-27, uma a uma |
| Origem | Separar claramente diretórios e arquivos do web e de cada agente, para facilitar a configuração e a documentação, com a mesma estrutura em DEV, HML e PROD |
| Restrições | Sem dependência nova (AGENTS §2.2). Python 3.6.0 a 3.13. Sem mudança de banco. O formato único anterior (`instance/config.ini` com todas as seções) continua aceito |
| Afeta | `sss_config`, `path_guard`, comandos de `src/sss/cli/`, launchers de `bin/`, `tools/package.py`, `bin/sss-update.sh` (novo), README §12, DEPLOYMENT, DEV_ENVIRONMENT, AGENTS, roteiro da homologação |

---

## 1. Decisões

| # | Decisão |
|---|---|
| D1 | Estrutura idêntica em DEV, HML e PROD: só muda o `<TIPO>` em `/portaloptrib/TESHUVA/SSS/<TIPO>/script_scheduling_service/` |
| D2 | Config e segredos de cada processo em `instance/<nome>/` (`config.ini`, `secrets.cfg`); dados em `var/<nome>/` (`logs`, `work`, `output`, `input`, `script_work`) e `var/exec/<usuário>/`; preservados na atualização |
| D3 | Scripts dos ambientes em `scripts_ambiente/`, dentro do projeto, preservada na atualização e aceita pela regra `APP_DIR` nos três ambientes |
| D4 | Config validado por papel, pelo próprio arquivo: `[web]` sem `[agent]` é o web; `[agent]` sem `[web]` é o agente; com as duas, o formato único anterior. O web não exige `exec_users`, `exec_work_dir` nem `purge_user` |
| D5 | Com `[app] name`, as pastas não escritas saem de `var/<nome>/` (e `var/exec`, `scripts_ambiente/`); uma chave escrita vazia desliga a função (ex.: `output_dir =`) |
| D6 | O nome do agente é o `agent_id`, único em toda a instalação (`agente0001`, `agente0002`...); um `agent_id` diferente do nome é recusado |
| D7 | Subida pelo nome: `bin/sss-web.sh web0001`, `bin/sss-scheduler.sh agente0001`, `bin/sss-stop.sh agente0001`; `--name` nos comandos Python; `--config` continua aceito |
| D8 | Web numerado como os agentes: `web0001`, `web0002`... |
| D9 | DEV migrado movendo os dados atuais para `var/agente0001/` e `var/web0001/`; o agente passa a se chamar `agente0001`; nada é apagado antes da conferência |
| D10 | `bin/sss-update.sh <pacote>`: atualização no lugar, com tudo parado, preservando `instance/`, `var/` e `scripts_ambiente/`, com pacote de retorno |
| D11 | Helper de execução numa pasta do root **ao lado** da raiz, `/portaloptrib/TESHUVA/SSS/<TIPO>/sss-root/bin/sss-helper`, com o caminho em `[agent] helper_path` (opção B, 2026-10-27). Como a raiz é do usuário de serviço, o helper nunca fica dentro dela. Na subida, o agente confere a pasta do helper e todas as pastas acima dela, até `/`, no caminho escrito e no real: do root e sem escrita de grupo e outros, ou com sticky bit. No DEV, `/portaloptrib` e `/portaloptrib/TESHUVA` têm `777`, e fora de DEV o administrador aplica o sticky bit ou tira a escrita (DEPLOYMENT §4.1) |
| D12 | Nos servidores da empresa não é possível criar usuários nem mudar permissões de pastas: HOM e PROD sobem com `sss_env = DEV` (opção B, 2026-10-27), e a separação entre os ambientes é física, pela pasta `<TIPO>`. Os scripts rodam com a conta do agente (risco aceito), e as proteções que o DEV desliga passam a ser seguidas à mão (DEPLOYMENT §4.0). A D11 continua no código para uma instalação com administrador. A opção A (modo `own_user` explícito, sem afrouxar o resto) foi recusada. A faixa de ambiente e o rodapé da tela mostram o `<TIPO>` da pasta (`sss_config.env_label`), e não o `sss_env` (opção A, 2026-10-27) |
| D13 | Revisão do CR-028, achado A1 (opção A, 2026-10-27): o config do web aceita um `[agent]` parcial só com as sete chaves que o web usa e que precisam ser iguais às dos agentes (`sss_config.WEB_AGENT_KEYS`), sem mudar o papel |

## 2. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 028a | Config e subida: papel pelo arquivo, `[app] name` e pastas derivadas, `agent_id` = nome, `config_path`/`--name` nos comandos, launchers pelo nome, `scripts_ambiente/` na regra `APP_DIR`, `prepare_dirs` por papel, exemplos em `instance/exemplos/web0001/` e `instance/exemplos/agente0001/`, testes. Suíte de 1538 testes em 3.6.0, 3.6.8 e 3.13.2; bateria Oracle (1536); `make lint` e `make type-check` com zero achados | Concluído |
| 028b | `bin/sss-update.sh` (conferência do pacote pelos dois `SHA256SUMS`, recusa com processo do SSS rodando na pasta, pacote de retorno no mesmo formato, troca só do código); empacotador com `sss-update.sh` e, de `instance/`, só os `.example` e `instance/exemplos/` (o `instance/secrets.cfg` do formato anterior continua recusando o pacote); `.gitignore` de `var/`, `instance/<nome>/` e `scripts_ambiente/`; testes de ponta a ponta (`test_update.py`) | Concluído |
| 028c | D11 e D12 (faixa pelo `<TIPO>`); (`[agent] helper_path`, `set_helper`, conferência das pastas acima do helper); DEV migrado, documentação reescrita para a estrutura nova (README, DEPLOYMENT, DEV_ENVIRONMENT, AGENTS), roteiro da homologação, homologação real | Concluído (homologação r2 de 2026-10-27, 332/332) |
| 028d | Revisão independente e encerramento: sem bloqueantes; todos os achados corrigidos (§3) | Concluído |

## 3. Revisão independente (028d)

Sem bloqueantes; 2 ALTO, 5 MÉDIO e 8 BAIXO, todos corrigidos:

| Achado | Correção |
|---|---|
| A1: o web usava os padrões de `[agent]` em valores que precisam ser iguais aos dos agentes | D13: `[agent]` parcial no config do web (README §12.1, DEPLOYMENT §7.1 e §17) |
| A2: `instance/agente0002/` com `name = agente0001` subia e parava o agente0001 | `name` diferente da pasta recusado no `sss_config` e no `sss-stop.sh` |
| M1: link simbólico no caminho da raiz escondia o processo rodando do `sss-update.sh` | caminho físico (`pwd -P`) |
| M2: `prepare_dirs` como root deixava `var/` do root e o `sss-update.sh` falhava | `var/`, `var/<nome>/` e `var/update/` do usuário do serviço |
| M3: com `var/` em outra partição, a troca deixava de ser por renomeação | extração e código anterior em `<RAIZ>/.update-<data>/`; só o retorno em `var/update/` |
| M4: no DEV com `exec_users`, o agente usava o helper antigo | `set_helper` sempre; a conferência continua só fora de DEV |
| M5: formato anterior sem `helper_path` não subia depois da atualização | nota no DEPLOYMENT §18.3 |
| B1 a B8 | helper link recusado; purge com o config do web sai com código 2; `helper_path` comparado com todas as pastas; mensagens, códigos e retorno absoluto do `sss-update.sh`; só um `python` rodando o comando conta como processo; limpeza de `var/update/` e arquivos locais de `bin/` documentados; testes que faltavam |
