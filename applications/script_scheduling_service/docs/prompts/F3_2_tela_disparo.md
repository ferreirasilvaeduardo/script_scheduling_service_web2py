# SSS — Prompt F3.2: Tela de disparo de script

## Leitura obrigatória antes de planejar
- `AGENTS.md` §2.3, §3.4, §5.5
- `README.md` §4.3.A e §4.3.C, §5.3, §5.4, §6 (inteiro)
- Arquivos: `modules/params_compiler.py`, `modules/path_guard.py`, `modules/rbac.py`, `modules/repo_catalogo.py`, `modules/repo_tickets.py`, `views/components/*`

## Objetivo
Permitir que o operador escolha o script e o ambiente, preencha o questionário dinâmico, confira a prévia do comando e crie o ticket, com toda a validação no servidor.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/ticket_service.py`:**
  - `preparar_formulario(ctx, script_id, ambiente)` retorna os vínculos ordenados e os valores padrão já resolvidos para exibição. Valida `pode_executar`.
  - `criar_ticket(ctx, ip, script_id, ambiente, respostas, prioridade, scheduled_at) -> (ticket_id | None, erros_por_campo)`, implementando o README §5.4 **passo a passo**:
    - revalida tudo no servidor;
    - aplica `prioridade_permitida`;
    - exige `scheduled_at >= agora`;
    - compila o snapshot;
    - chama `repo_tickets.criar` com o ticket e as respostas resolvidas;
    - registra a auditoria `TICKET_CRIAR`.
  - `previa(ctx, script_id, ambiente, respostas) -> (argv_exibicao, erros_por_campo)`.
- **`applications/script_scheduling_service/controllers/tickets.py`:**
  - `novo` (GET), com 3 etapas na mesma página:
    1. seleção do script, a partir de `scripts_executaveis` filtrados, agrupados por `grupo`/`categoria`, com busca textual;
    2. seleção do ambiente: só os homologados **e** autorizados para o script escolhido;
    3. questionário.
  - `criar` (POST + CSRF): em caso de erro, re-renderiza com os erros por campo e os valores preenchidos, **exceto os sensíveis**. Em caso de sucesso, redireciona para `tickets/detalhe/<id>` com flash.
  - `previa` (POST + CSRF, JSON): é POST porque o corpo pode conter valores sensíveis, que não podem ir para a URL nem para os logs de acesso.
- **`applications/script_scheduling_service/views/tickets/novo.html`:**
  - O questionário é renderizado **pelo servidor** a partir dos vínculos, com um componente por `tipo_componente`:
    - `TEXT`: input;
    - `NUMBER`: `inputmode="decimal"`;
    - `DATE`: `type="date"`;
    - `SELECT`: options de `opcoes_json`;
    - `CHECKBOX`;
    - parâmetros sensíveis usam `type="password"` com `autocomplete="off"`.
  - Label e ajuda vêm de `label` e `descricao`. O marcador de obrigatório é visível e acessível.
  - Mostra o valor padrão aplicado como placeholder ou ajuda ("Padrão: …"), exceto para sensíveis.
  - Campos de prioridade (a 1 só aparece para admin) e de agendamento opcional (`scheduled_at`).
  - **Prévia:** o botão "Pré-visualizar comando" chama `previa` via `sssFetch` e exibe o argv mascarado em um bloco monoespaçado com `x-text`, com o botão "Copiar".
  - **Confirmação final** em modal: "Criar ticket para <script> em <AMBIENTE>?". Para `PRODUCAO`, mostrar o aviso destacado "Ambiente de produção".
- **`applications/script_scheduling_service/static/js/app/disparo.js`:** componentes `Alpine.data` (`buscaScript`, `previa`). Nenhuma regra de validação **decisória** fica no cliente; o cliente só dá retorno imediato de formato.
- **Atalho na `default/index`:** cartão "Disparar script" para quem tem `EXEC_SCRIPT`.
- **`applications/script_scheduling_service/scripts/test_ticket_service.py`** (FAKE):
  - criação OK com snapshot correto;
  - sem `EXEC_SCRIPT`;
  - script não homologado no ambiente;
  - obrigatório faltando;
  - regex inválida;
  - prioridade 1 por não admin;
  - `scheduled_at` no passado;
  - auditoria gravada;
  - `tbsss_ticket_resp` com os valores resolvidos.

**OUT**
- Sem lista e sem detalhe completo de tickets (isso é o F3.3). Por enquanto, `detalhe` pode ser um placeholder protegido por guarda.

## Requisitos
1. O servidor é a autoridade (AGENTS, regra de ouro). Remover o atributo `required` pelo DevTools não pode permitir criar um ticket inválido.
2. Valores sensíveis nunca voltam ao HTML depois do POST, nunca vão para o log e nunca vão para a URL.
3. O controller **não** contém regra de negócio: tudo está no `ticket_service` (AGENTS §5.5).

## Critérios de aceite
- [ ] Com `op.hml`, apenas os scripts e ambientes autorizados e homologados aparecem. A URL forjada com outro `script_id` retorna erro de autorização.
- [ ] Um erro de validação destaca **todos** os campos inválidos de uma vez.
- [ ] A prévia mascara o parâmetro sensível.
- [ ] O ticket criado aparece no FAKE com o `parametros_enviados` no formato do README §6.5.
- [ ] `test_ticket_service.py` passa.

## Verificação
- **Browser:** fluxo completo com `op.hml` e com `admin`; forjar `script_id`; remover `required`; conferir o console (CSP) e a aba Network (sem valor sensível em query string).
- Testes: `python -m unittest discover -s scripts -p "test_ticket_service.py"`

## Saída
Relatório AGENTS.md §9.
