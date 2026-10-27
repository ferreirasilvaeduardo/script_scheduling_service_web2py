# CR-027: O interpretador digitado volta a vencer o `#!`, e `python` ↔ `python3` no cadastro

| Campo | Valor |
|---|---|
| Status | **Encerrado** (2026-10-27). Proposta e decisões do responsável pelo produto em 2026-10-27 |
| Origem | Com o CR-026, um script com `#!` válido sempre rodava com ele, e o operador não conseguia trocar o interpretador no disparo |
| Restrições | Sem dependência nova (AGENTS §2.2). Python 3.6.0 a 3.13. Sem mudança de banco, de snapshot (continua na versão 7), de telas (só o texto de ajuda) nem de config |
| Afeta | README §5.4, §6.4, §8.4, §8.5; AGENTS §3.2, §7; DEPLOYMENT §9, §15; `params_compiler`; ajuda das telas de disparo e de cadastro; CT-32 da homologação |

---

## 1. Decisões

| # | Decisão |
|---|---|
| D1 | Ordem na execução: (1) o interpretador digitado no disparo; (2) o `#!` da primeira linha do script; (3) o nome do cadastro. Substitui a ordem do CR-026 (D5), em que o `#!` vinha primeiro |
| D2 | Quem não existe no servidor é pulado, com uma linha `[SSS]` no log do ticket: `interpretador informado nao encontrado neste servidor: ...`, `#! ignorado: ...` e `python nao encontrado neste servidor; usando python3`. `INTERPRETER_NOT_FOUND` só quando nenhum dos três existe; nesse caso, as linhas das tentativas vêm no log antes da linha de recusa (decisão do responsável no 027b) |
| D3 | No cadastro, `python` e `python3` servem um ao outro: cadastro `python` sem `python` no servidor usa o `python3`, e vice-versa. `sh` e `bash` não têm troca |
| D4 | As opções do Python seguem o executável usado: o `python3` achado pelo cadastro roda com `-I`; o `python` (que pode ser o Python 2) com `-E -s`, mesmo quando o cadastro diz o outro |

## 2. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 027a | `params_compiler` (`_agent_argv` com a nova ordem e notas; `_registered_argv` com a troca e as opções pelo executável usado); testes; documentação (README §5.4, §6.4, §8.4, §8.5; AGENTS §3.2, §7; DEPLOYMENT §9, §15; DEV_ENVIRONMENT; CR-026 D5 marcada como substituída; ajuda das telas de disparo e de cadastro). Suíte de 1530 testes em 3.6.0, 3.6.8 e 3.13.2; bateria Oracle (1528); `make lint` e `make type-check` com zero achados | Concluído |
| 027b | CT-32 ajustado (ajudas com a ordem nova; nome digitado inexistente pulado para o cadastro e, no caso novo, para o `#!`; o digitado vencendo o `#!`); a troca `python` ↔ `python3` não é reproduzível no servidor do DEV, que tem os dois, e fica coberta pelos testes automatizados. Revisão independente (1 ponto de código e cerca de 12 de texto): decisão do responsável de gravar as tentativas também quando nenhum interpretador existe (`params_compiler` acrescenta as notas antes de recusar; `_refuse` grava uma linha `[SSS]` por tentativa antes da recusa); textos de README, AGENTS, DEPLOYMENT, comentários das colunas (`docs/sql` regenerados) e docstrings. Homologação real 2026-10-27 332/332 (`docs/homologation/SSS_Homologation_Evidence_2026-10-27.docx`), com o CT-32 repetido depois da decisão | Concluído |

## 3. Riscos

* Os do CR-025 e do CR-026 continuam (README §8.5 e §14).
* **O operador sempre escolhe o executável:** o digitado vence o `#!`.
* **Troca silenciosa de versão no cadastro:** um script cadastrado como `python` (pensado para o Python 2) roda no `python3` quando o servidor não tem `python`, e o contrário. A troca fica registrada no log do ticket e em `interpreter_used`.

---

## 4. Encerramento (2026-10-27)

* **Validação:** suíte de 1531 testes nas versões 3.6.0, 3.6.8 e 3.13.2; bateria Oracle (1528, no 027a; o 027b muda só o `params_compiler`, o `scheduler_loop` e textos); `make lint` e `make type-check` com zero achados; homologação real 332/332.
* **Operação:** sem `ALTER` de estrutura; num banco já instalado, os dois `COMMENT` novos do DEPLOYMENT §18 (opcionais). Atualizar os agentes junto com a web: um agente anterior aplicaria a ordem do CR-026 (o `#!` primeiro).
