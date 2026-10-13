# SSS — Prompt F3.3: Tickets — lista, detalhe, cancelamento e reexecução

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.4, §4.4, §4.12 (filtro de data por intervalo)
- `README.md` §4.3.C, §5 (inteiro), §6.5 (sensíveis)
- Arquivos: `modules/ticket_service.py`, `modules/repo_tickets.py`, `views/components/*`

## Objetivo
Dar visibilidade e controle sobre a fila: lista com filtros, detalhe com o snapshot, cancelamento distribuído (parte web) e reexecução.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/ticket_service.py` (ampliar):**
  - `listar(ctx, filtros, pagina, tamanho)`: aplica o escopo de ambientes de `VER_LOGS` (README §4.3.C); sem `VER_LOGS`, mostra apenas os tickets do próprio solicitante. Filtros:
    - status (múltiplo);
    - ambiente;
    - script;
    - solicitante;
    - período de criação, transformado em intervalo `[inicio, fim + 1 dia)`;
    - origem (manual/agendamento).
  - `detalhe(ctx, ticket_id)`: retorna o ticket, o snapshot parseado, `argv_para_exibicao`, as respostas (sensíveis mascaradas), a cadeia de reexecução (pai e filhos) e a duração.
  - `cancelar(ctx, ip, ticket_id) -> resultado`: `pode_cancelar`, depois `repo_tickets.solicitar_cancelamento` (README §5.6, nó web), com auditoria `TICKET_CANCELAR`. As mensagens são:
    - TERMINAL: "O ticket já estava finalizado."
    - CANCELADO: "Ticket cancelado."
    - SINALIZADO: "Cancelamento solicitado; o agente encerrará a execução."
  - `reexecutar(ctx, ip, ticket_id) -> novo_id`, conforme o README §5.5: recompila as respostas resolvidas contra o catálogo vigente, define `parent_ticket_id` e audita `TICKET_REEXECUTAR`. Um erro de recompilação, por exemplo um parâmetro novo obrigatório, redireciona para `tickets/novo` pré-preenchido com o aviso.
- **`applications/script_scheduling_service/controllers/tickets.py`:**
  - `lista` (GET; filtros por querystring, validados e com allowlist de chaves e valores; paginação com `sanitizar_*`);
  - `detalhe/<id>`;
  - `cancelar` e `reexecutar` (POST + CSRF + confirmação em modal).
- **Views:**
  - `views/tickets/lista.html`:
    - colunas `#`, script, ambiente, status (badge com motivo), prioridade, solicitante, criado em, início, duração e ações;
    - linhas `RUNNING` destacadas;
    - atualização automática **opcional** (alternável, intervalo de 10 s) via Alpine, que recarrega só a tabela por `fetch` de um fragmento HTML (`tickets/lista.load`) renderizado no servidor.
  - `views/tickets/detalhe.html`:
    - cabeçalho com status;
    - linha do tempo (criado, agendado, iniciado, último heartbeat, finalizado);
    - agente e PID;
    - `return_code` e `status_motivo` com descrição em português;
    - argv mascarado, com "Copiar";
    - respostas;
    - links para o pai e os filhos;
    - botões "Cancelar" e "Reexecutar", que aparecem **somente** quando o RBAC e o status permitem;
    - um placeholder do painel de log (isso é o F3.4).
- **`ui_helpers.descricao_motivo(status_motivo)`:** texto em português para cada motivo do README §5.2.
- **`applications/script_scheduling_service/scripts/test_ticket_service.py` (ampliar):**
  - escopo de listagem por perfil;
  - filtro de período nos limites;
  - cancelamento nos 3 resultados;
  - cancelamento de terceiro sem `CANC_TICKET` negado;
  - reexecução OK com `parent_ticket_id`;
  - reexecução com catálogo alterado gerando erro tratado;
  - sensíveis mascarados no detalhe.

**OUT**
- Sem visualizador de log (isso é o F3.4).

## Requisitos
1. **Allowlist** de filtros e de ordenação: nenhum valor da querystring vira nome de coluna.
2. **Autorização no servidor:** o `detalhe` de um ticket fora do escopo retorna 404, não 403, para não revelar que o ticket existe.
3. O fragmento `.load` exige os mesmos guardas da página.

## Critérios de aceite
- [ ] `consulta` vê apenas os tickets dos ambientes autorizados. Um ID fora do escopo retorna 404.
- [ ] Cancelar um `PENDING` muda o status para `CANCELLED` na hora. Cancelar um `RUNNING` exibe "Cancelamento solicitado".
- [ ] Reexecutar cria um novo ticket vinculado e navegável pela cadeia.
- [ ] A atualização automática não gera violação de CSP e para quando desligada.
- [ ] Os testes passam.

## Verificação
- **Browser:** filtros combinados com paginação preservando os filtros; cancelar e reexecutar com `admin` e com `op.prod`; tentar um ID fora do escopo.
- Testes: `python -m unittest discover -s scripts -p "test_ticket_service.py"`

## Saída
Relatório AGENTS.md §9.
