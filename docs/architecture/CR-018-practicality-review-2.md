# CR-018: Segunda rodada de praticidade (regras, telas, desempenho)

| Campo | Valor |
|---|---|
| Status | **Concluído** em 2026-10-23. Aprovado pelo responsável pelo produto em 2026-10-23 |
| Origem | Segunda e terceira revisões tela a tela e processo a processo (2026-10-23), depois do CR-017 |
| Restrições | Sem dependência nova. Python 3.6. Sem mudança de esquema |
| Afeta | README §4.3.C, §5.2.1, §6.5. `AGENTS.md` §3.4 e §7. Código: `rbac`, `ticket_service`, `ui_helpers`, `schedules_service`, `admin_parameters_service`, `admin_scripts_service`, controllers e telas de tickets, parâmetros e scripts |
| Revoga | `CANCEL_TICKET` sem `VIEW_LOGS` para tickets de terceiros (CR-003 P5) |

---

## 1. Achados

| # | Achado | Efeito |
|---|---|---|
| A1 | `CANCEL_TICKET` cancelava ticket de terceiro sem `VIEW_LOGS`, mas a lista e o detalhe exigem `VIEW_LOGS` | Permissão sem caminho na interface: só por requisição montada à mão |
| A2 | O filtro "Solicitante (login)" aceitava qualquer login para quem vê "outra pessoa" no lugar do login | Desfazia o mascaramento do CR-008 E5 |
| A3 | Mudar opções, regex ou tipo de parâmetro, incluir vínculo obrigatório ou trocar o arquivo do script não avisava quem mudou | Regras ativas pausadas e tickets na fila recusados sem que o editor soubesse |
| A4 | Nomes das funcionalidades diferentes dos itens de menu; "O que eu posso fazer" repete os cartões; código técnico na lista de tickets; filtro de ambiente em texto livre nas regras; perfil novo volta à lista; Auditoria só com códigos; mensagem do log; botão Desativar que será negado | Telas menos diretas (018b) |
| A5 | Consultas repetidas por script nas telas de execução; contagem da exportação CSV lendo o conjunto duas vezes | Custo que cresce com o catálogo (018c) |

## 2. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Cancelar é para quem enxerga | Ticket de terceiro: `CANCEL_TICKET` **e** `VIEW_LOGS` no ambiente. O próprio solicitante continua com `EXEC_SCRIPT` |
| D2 | Filtro por solicitante | Só para quem vê logins (`VIEW_AUDIT` ou administrador); o serviço ignora o login alheio para os demais |
| D3 | Avisar e deixar salvar | O aviso usa a mesma checagem do agente (`rules_at_risk` e a fila `PENDING`), nunca bloqueia a gravação e uma falha ao montá-lo não desfaz o que foi salvo |
| D4 | Nomes das funcionalidades | EXEC_SCRIPT "Rodar Scripts" e VIEW_LOGS "Consultar Tickets" (Cancelar Tickets não muda), no seed (o MERGE do `init_db` atualiza um banco existente) e lidos do cadastro nos motivos das telas |
| D5 | Limpeza | O 018f entra no CR-018 |
| D6 | Leitura do catálogo | Um retrato por tela (ambientes e scripts com a homologação em lote); os vínculos de parâmetros dos cartões seguem por script, porque o contrato não tem leitura em lote deles e o custo é de uma consulta por cartão |
| D7 | Contagem da exportação | `RepoAudit.count` (COUNT com o filtro e o teto do `iterate`), com paridade FAKE × Oracle no contrato |

## 3. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 018a | D1, D2, D3 (A1 a A3) | Concluído |
| 018b | Telas (A4) | Concluído |
| 018c | Desempenho (A5) | Concluído |
| 018d | `interpreters` no config do DEV (arquivo local, fora do git) e nota no `DEV_ENVIRONMENT.md` §6.3 | Concluído |
| 018g | DSN Easy Connect com a porta opcional (`host[:porta]/serviço`): os DSNs do seed, sem porta, eram recusados e impediam editar qualquer ambiente do seed. Achado durante o 018f2 | Concluído |
| 018f | Limpeza de código: f1 guardas comuns no model, f2 `date` → `data` onde é dicionário, f3 comentários sem nomes antigos e f4 README sem notas históricas (a regra vigente fica; o histórico fica nos CRs) | Concluído |
| 018e | Nova rodada de evidências (por último, para cobrir o 018f): rodada 2 de 23/10 no DEV real, 251 de 251 verificações OK em 29 casos (CT-27 novo), `SSS_Homologation_Evidence_2026-10-23_r2.docx` | Concluído |
