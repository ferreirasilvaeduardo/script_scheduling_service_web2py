# CR-027: O interpretador digitado volta a vencer o `#!`, e `python` ↔ `python3` no cadastro

| Campo | Valor |
|---|---|
| Status | **Em andamento**. Proposta e decisões do responsável pelo produto em 2026-10-27 |
| Origem | Com o CR-026, um script com `#!` válido sempre rodava com ele, e o operador não conseguia trocar o interpretador no disparo |
| Restrições | Sem dependência nova (AGENTS §2.2). Python 3.6.0 a 3.13. Sem mudança de banco, de snapshot (continua na versão 7), de telas (só o texto de ajuda) nem de config |
| Afeta | README §5.4, §6.4, §8.4, §8.5; AGENTS §3.2, §7; DEPLOYMENT §9, §15; `params_compiler`; ajuda das telas de disparo e de cadastro; CT-32 da homologação |

---

## 1. Decisões

| # | Decisão |
|---|---|
| D1 | Ordem na execução: (1) o interpretador digitado no disparo; (2) o `#!` da primeira linha do script; (3) o nome do cadastro. Substitui a ordem do CR-026 (D5), em que o `#!` vinha primeiro |
| D2 | Quem não existe no servidor é pulado, com uma linha `[SSS]` no log do ticket: `interpretador informado nao encontrado neste servidor: ...`, `#! ignorado: ...` e `python nao encontrado neste servidor; usando python3`. `INTERPRETER_NOT_FOUND` só quando nenhum dos três existe |
| D3 | No cadastro, `python` e `python3` servem um ao outro: cadastro `python` sem `python` no servidor usa o `python3`, e vice-versa. `sh` e `bash` não têm troca |
| D4 | As opções do Python seguem o executável usado: o `python3` achado pelo cadastro roda com `-I`; o `python` (que pode ser o Python 2) com `-E -s`, mesmo quando o cadastro diz o outro |

## 2. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 027a | `params_compiler` (`_agent_argv` com a nova ordem e notas; `_registered_argv` com a troca e as opções pelo executável usado); testes; documentação (README §5.4, §6.4, §8.4, §8.5; AGENTS §3.2, §7; DEPLOYMENT §9, §15; DEV_ENVIRONMENT; CR-026 D5 marcada como substituída; ajuda das telas de disparo e de cadastro). Suíte de 1530 testes em 3.6.0, 3.6.8 e 3.13.2; bateria Oracle (1528); `make lint` e `make type-check` com zero achados | Concluído |
| 027b | Homologação real com o CT-32 ajustado (o digitado vencendo o `#!`, o digitado inexistente caindo para o `#!` e o cadastro, a troca `python` ↔ `python3`), revisão independente e encerramento | Pendente |

## 3. Riscos

* Os do CR-025 e do CR-026 continuam (README §8.5 e §14).
* **O operador sempre escolhe o executável:** o digitado vence o `#!`.
* **Troca silenciosa de versão no cadastro:** um script cadastrado como `python` (pensado para o Python 2) roda no `python3` quando o servidor não tem `python`, e o contrário. A troca fica registrada no log do ticket e em `interpreter_used`.
