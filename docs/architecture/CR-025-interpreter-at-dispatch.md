# CR-025: Interpretador informado no disparo e opções "definido no script"

| Campo | Valor |
|---|---|
| Status | **Encerrado** (2026-10-26). Proposta e decisões do responsável pelo produto em 2026-10-26, que aceita o risco descrito em §3 |
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
| D4 | Nome sem `/`: buscado no `PATH` herdado pelo processo do agente ("o ambiente decide": o da unit do systemd ou o do shell que rodou o `bin/sss-scheduler.sh`, que não o altera). O caminho é executado como foi digitado ou encontrado, sem resolver links, para que o Python de um virtualenv ache o venv (025d) |
| D5 | Conferência mínima no agente, sem restringir: o interpretador existe e é executável; senão `PRECHECK_FAILED` com `INTERPRETER_NOT_FOUND`. "Definido no script" sem `#!` com caminho absoluto: `NO_SHEBANG`. Um argumento depois do caminho no `#!` é repassado, como faz o Linux; no `PYTHON_SCRIPT`, o `-E -s` vai depois dele, e por isso `#!/usr/bin/env python3` funciona (025d). Com interpretador digitado, o argumento do `#!` é ignorado |
| D6 | `-I` só no `PYTHON3` configurado; `PYTHON`, `PYTHON_SCRIPT` e todo Python com interpretador digitado rodam com `-E -s` (funcionam no Python 2 e no 3, que podem não ter `-I`) |
| D7 | Snapshot versão 6: acrescenta `interpreter_override` (o digitado, ou nulo). O agente aceita 5 e 6; um agente anterior recusa a 6 (`UNSUPPORTED_VERSION`) em vez de ignorar a escolha |
| D8 | O agente grava o interpretador executado em `tbsss_tickets.interpreter_path` junto com o PID (como o `script_path` do CR-023); o detalhe mostra o digitado e o usado |
| D9 | A fila continua escolhendo o agente pelo tipo cadastrado; o digitado não muda a fila (cada ambiente tem os próprios servidores). Os "definido no script" são atendidos por todo agente saudável do ambiente, inclusive na conta da "fila sem atendente" (025d) |

## 2. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 025a | Agente e banco: opções novas (CK), snapshot v6, leitura do `#!`, busca do nome no `PATH`, conferência mínima, `interpreter_path` com o PID, `docs/sql` regenerados, tabelas do DEV recriadas (esquema 100% compatível). Testes novos: formato do digitado, busca por caminho e por nome, `#!` (com argumento, sem `#!`, relativo, `env`), argv em cada caso, v5 ainda aceita, `PYTHON` configurável e `PYTHON_SCRIPT` não, agente de ponta a ponta (`#!` e nome digitado, `NO_SHEBANG`, `INTERPRETER_NOT_FOUND`), Oracle (`interpreter_path`) | Concluído |
| 025b | Telas: seis opções no cadastro; campo no disparo e na reexecução; detalhe do ticket com o digitado e o usado. Campo "Interpretador (opcional)" no disparo, com a ajuda citando o cadastrado; modal com "Interpretador:" e o comando; detalhe com "Interpretador cadastrado", "informado" e "usado"; reexecução repete o digitado; auditoria do disparo com "interpretador informado"; conferido no navegador sobre o FAKE (sem erro de console nem de CSP) | Concluído |
| 025c | Documentação com os riscos (README §5.4, §6.4, §6.5, §8.4, §8.5, §8.12, §12; AGENTS §3.2, §7; DEPLOYMENT §9, §15, §18) e homologação real: CT-32 com `#!` do Python 3.6, caminho do 3.13 digitado, nome `python3.12`, `INTERPRETER_NOT_FOUND`, `NO_SHEBANG`, formato inválido e auditoria; diagnósticos `dev/scripts/diagnostico/interp_*`; DEV com `PYTHON` em `[agent] interpreters`. Rodada 315/315 (`docs/homologation/SSS_Homologation_Evidence_2026-10-26.docx`); o CT-32 foi rodado duas vezes porque a primeira verificação da auditoria lia só o texto visível do "ver mais" | Concluído |
| 025d | Validação da documentação contra o código (revisão independente) e encerramento. Revisão independente (22 apontamentos, conferidos um a um), com três defeitos de código corrigidos: `#!/usr/bin/env python3` no `PYTHON_SCRIPT` falhava (`env -E`; o `-E -s` passou para depois do argumento do `#!`); a "fila sem atendente" acusava os "definido no script" como sem agente (agora todo agente saudável os atende, no Oracle e no FAKE); o interpretador digitado e o do `#!` eram executados pelo caminho real, e o Python de um virtualenv perdia o venv (agora sem resolver links). Documentação: `PATH` herdado pelo agente, auditoria só com o digitado, `interpreter_path` no SQL do §8.4, `UNSUPPORTED_VERSION` com agente anterior, riscos no README §14, snapshot v6 no §6.5, códigos do §8.5, campo novo no §5, comentários das colunas (`docs/sql` regenerados, `COMMENT` no DEPLOYMENT §18 e aplicados no DEV), `FORMAT A13`, retorno no §18 e checklist §19, DEV_ENVIRONMENT, roteiro e `config.ini.example`. CT-32 com `#!/usr/bin/env python3` e Python de virtualenv; homologação real 321/321 (`docs/homologation/SSS_Homologation_Evidence_2026-10-26_r2.docx`) | Concluído |

## 3. Riscos aceitos pelo responsável

* **Executável escolhido pelo operador:** quem pode disparar escolhe qual programa roda o script, inclusive um que não seja interpretador. Isso substitui a lista fixa de interpretadores do servidor naquela execução.
* **Versão errada:** o script pode rodar numa versão diferente daquela para a qual foi feito e falhar no meio, ou terminar com resultado errado.
* **`#!` sob controle de quem edita o script:** muda o interpretador sem passar pelo cadastro.
* **Mitigações que ficam:** o digitado gravado no snapshot e na auditoria do disparo, e o usado em `interpreter_path`; conferência mínima (existe e é executável); Python isolado (`-I` ou `-E -s`); execução com o usuário de execução do ambiente, nunca como root.

---

## 4. Encerramento (2026-10-26)

* **Validação:** suíte de 1523 testes nas versões 3.6.0, 3.6.8 e 3.13.2; bateria Oracle (1521); `make lint` e `make type-check` com zero achados; homologação real 321/321, com o CT-32 ampliado.
* **Operação:** atualizar **todos** os agentes antes da web (snapshot v6); aplicar os `ALTER` e `COMMENT` do DEPLOYMENT §18 num banco já instalado; conferir o `PATH` do processo do agente em cada servidor e acrescentar `PYTHON=` em `[agent] interpreters` se a opção Python for usada (DEPLOYMENT §9, §19).
* **Riscos:** os do §3, aceitos pelo responsável pelo produto e registrados no README §8.5 e §14.
