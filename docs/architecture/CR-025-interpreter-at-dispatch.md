# CR-025: Interpretador informado no disparo e opções "definido no script"

| Campo | Valor |
|---|---|
| Status | **Em andamento**. Proposta e decisões do responsável pelo produto em 2026-10-26, que aceita o risco descrito em §3 |
| Origem | Scripts feitos para versões diferentes do interpretador (ex.: um só roda no Python 3.6, outro no 3.13) e scripts que trazem o interpretador no próprio `#!` |
| Restrições | Sem dependência nova (AGENTS §2.2). Python 3.6.0 a 3.13. Esquema na versão 1, ainda aberta (AGENTS §4.16): muda sem migração; tabelas do DEV recriadas a pedido do responsável; `ALTER` documentado no DEPLOYMENT §18 |
| Afeta | README §5, §6.4, §6.5, §8.4, §8.5, §10, §12; AGENTS §3.2, §7; DEPLOYMENT §7, §9, §15, §18; `path_guard`, `params_compiler`, `sss_config`, `scheduler_loop`, repositórios, cadastro de scripts, disparo, detalhe do ticket |

---

## 1. Decisões

| # | Decisão |
|---|---|
| D1 | Cadastro com seis opções: `PYTHON3` (como hoje), `PYTHON` (novo: segundo Python do servidor, ex.: `/usr/bin/python`, que pode ser o Python 2), `BASH`, `SH`, `PYTHON_SCRIPT` e `SHELL_SCRIPT` ("definido no script": o interpretador é o caminho do `#!` da primeira linha do script) |
| D2 | `[agent] interpreters` mapeia `PYTHON3`, `PYTHON`, `BASH` e `SH`. Os "definido no script" não são configurados: todo agente os atende |
| D3 | Disparo: campo **Interpretador** em todo script, **em branco por padrão** (roda como cadastrado). O operador pode digitar o caminho absoluto (`/opt/py311/bin/python3`) ou só o nome (`python3.13`); o digitado vence o cadastrado e o `#!`. Reexecução repete o valor; agendamento roda como cadastrado |
| D4 | Nome sem `/`: buscado no `PATH` do próprio processo do agente ("o ambiente decide": o `PATH` da unit do systemd ou do `bin/sss-scheduler.sh`) |
| D5 | Conferência mínima no agente, sem restringir: o interpretador existe e é executável; senão `PRECHECK_FAILED` com `INTERPRETER_NOT_FOUND`. "Definido no script" sem `#!` com caminho absoluto: `NO_SHEBANG`. Um argumento depois do caminho no `#!` é repassado, como faz o Linux |
| D6 | `-I` só no `PYTHON3` configurado; `PYTHON`, `PYTHON_SCRIPT` e todo Python com interpretador digitado rodam com `-E -s` (funcionam no Python 2 e no 3, que podem não ter `-I`) |
| D7 | Snapshot versão 6: acrescenta `interpreter_override` (o digitado, ou nulo). O agente aceita 5 e 6; um agente anterior recusa a 6 (`UNSUPPORTED_VERSION`) em vez de ignorar a escolha |
| D8 | O agente grava o interpretador executado em `tbsss_tickets.interpreter_path` junto com o PID (como o `script_path` do CR-023); o detalhe mostra o digitado e o usado |
| D9 | A fila continua escolhendo o agente pelo tipo cadastrado; o digitado não muda a fila (cada ambiente tem os próprios servidores) |

## 2. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 025a | Agente e banco: opções novas (CK), snapshot v6, leitura do `#!`, busca do nome no `PATH`, conferência mínima, `interpreter_path` com o PID, `docs/sql` regenerados, tabelas do DEV recriadas (esquema 100% compatível). Testes novos: formato do digitado, busca por caminho e por nome, `#!` (com argumento, sem `#!`, relativo, `env`), argv em cada caso, v5 ainda aceita, `PYTHON` configurável e `PYTHON_SCRIPT` não, agente de ponta a ponta (`#!` e nome digitado, `NO_SHEBANG`, `INTERPRETER_NOT_FOUND`), Oracle (`interpreter_path`) | Concluído |
| 025b | Telas: seis opções no cadastro; campo no disparo e na reexecução; detalhe do ticket com o digitado e o usado | Pendente |
| 025c | Documentação com os riscos (README, AGENTS, DEPLOYMENT) e homologação real (`#!`, caminho digitado, nome digitado, `#!` inválido, nome inexistente) | Pendente |
| 025d | Validação da documentação contra o código (revisão independente) e encerramento | Pendente |

## 3. Riscos aceitos pelo responsável

* **Executável escolhido pelo operador:** quem pode disparar escolhe qual programa roda o script, inclusive um que não seja interpretador. Isso substitui a lista fixa de interpretadores do servidor naquela execução.
* **Versão errada:** o script pode rodar numa versão diferente daquela para a qual foi feito e falhar no meio, ou terminar com resultado errado.
* **`#!` sob controle de quem edita o script:** muda o interpretador sem passar pelo cadastro.
* **Mitigações que ficam:** o digitado e o usado gravados no ticket e na auditoria do disparo; conferência mínima (existe e é executável); Python isolado (`-I` ou `-E -s`); execução com o usuário de execução do ambiente, nunca como root.
