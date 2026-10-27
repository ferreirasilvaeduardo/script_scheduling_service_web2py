# CR-028: Estrutura idêntica por processo (web0001, agente0001...)

| Campo | Valor |
|---|---|
| Status | **Em andamento**. Pedido e decisões do responsável pelo produto em 2026-10-27, uma a uma |
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

## 2. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 028a | Config e subida: papel pelo arquivo, `[app] name` e pastas derivadas, `agent_id` = nome, `config_path`/`--name` nos comandos, launchers pelo nome, `scripts_ambiente/` na regra `APP_DIR`, `prepare_dirs` por papel, exemplos em `instance/exemplos/web0001/` e `instance/exemplos/agente0001/`, testes. Suíte de 1538 testes em 3.6.0, 3.6.8 e 3.13.2; bateria Oracle (1536); `make lint` e `make type-check` com zero achados | Concluído |
| 028b | `bin/sss-update.sh` (conferência do pacote pelos dois `SHA256SUMS`, recusa com processo do SSS rodando na pasta, pacote de retorno no mesmo formato, troca só do código); empacotador com `sss-update.sh` e, de `instance/`, só os `.example` e `instance/exemplos/` (o `instance/secrets.cfg` do formato anterior continua recusando o pacote); `.gitignore` de `var/`, `instance/<nome>/` e `scripts_ambiente/`; testes de ponta a ponta (`test_update.py`) | Concluído |
| 028c | DEV migrado, documentação reescrita para a estrutura nova (README, DEPLOYMENT, DEV_ENVIRONMENT, AGENTS), roteiro da homologação, homologação real | Pendente |
| 028d | Revisão independente e encerramento | Pendente |
