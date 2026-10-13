# SSS — Prompt F5.2: Tela de agendamentos

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.4, §5.5
- `README.md` §4.3.C (`CAD_AGENDAMENTOS`), §5.3, §7 (inteiro), §10 (tabela 12 e a regra de **edição de agendamento**: `usuario_id` = editor)
- Arquivos: `modules/recurrence.py`, `modules/cron_parser.py`, `modules/params_compiler.py`, `views/tickets/novo.html` (questionário reutilizável), `docs/PADRAO_CRUD_ADMIN.md`

## Objetivo
Criar e gerenciar regras de recorrência com prévia das próximas execuções, questionário de parâmetros validado e controle de pausa/retomada.

## Escopo
**IN**
- **Questionário como partial:** extraia o questionário do F3.2 para `views/components/questionario.html` e reutilize-o aqui e na tela de disparo, sem alterar o comportamento do F3.2. Esta é a única refatoração permitida, porque o reaproveitamento é requisito deste prompt.
- **`applications/script_scheduling_service/modules/agendamentos_service.py`:**
  - **`salvar(ctx, ip, dados)`:**
    - `pode_executar(ctx, script, ambiente)` do **editor**;
    - `recurrence.validar_regra`;
    - respostas validadas por `params_compiler.resolver_respostas` e serializadas em `parametros_json` (JSON objeto `{codigo: valor}`, `sort_keys`);
    - a compilação completa do snapshot é testada (via `compilar_snapshot`) apenas para validação, sem persistir;
    - `prioridade_permitida`;
    - `proxima_execucao = recurrence.proxima_execucao(regra, agora)`, com erro se for `None`;
    - **`usuario_id = ctx.usuario_id`** na inclusão e na edição (README §10);
    - auditoria com o `usuario_id` anterior e o novo.
  - `pausar(ctx, ip, id)` → `pausa_motivo = 'MANUAL'`, conforme o README §7.5 passo 7 (otimista), com auditoria `AGD_PAUSAR`.
  - `retomar(ctx, ip, id)` → revalida `pode_executar`, recalcula `proxima_execucao` a partir de agora, limpa `pausa_motivo`, `ativo = 'S'` e audita.
  - `listar(ctx, filtros, pagina)`:
    - perfis com `CAD_AGENDAMENTOS` veem as regras dos ambientes autorizados (admin vê todas);
    - colunas `nome`, script, ambiente, recorrência (com `descrever()` para CRON), próxima execução, última execução com link para o `ultimo_ticket_id`, responsável (login do `usuario_id`), status (Ativo / Pausado + motivo traduzido).
  - `previa(dados) -> proximas 5 datas | erros` (POST + CSRF, JSON).
- **`applications/script_scheduling_service/controllers/agendamentos.py`:** `lista`, `form`, `salvar`, `pausar`, `retomar` e `previa`, todos com `_exigir_func('CAD_AGENDAMENTOS')`.
- **`views/agendamentos/form.html`:**
  - Seleção de script e ambiente com os mesmos filtros de autorização do F3.2.
  - `tipo_recorrencia` com campos condicionais (Alpine): `UNICA` (data/hora), `DIARIA` (hora), `SEMANAL` (hora + checkboxes seg–dom, que serializam em `1,3,5`), `MENSAL` (hora + dia, com a nota "Se o mês não tiver o dia, executa no último dia do mês"), `CRON` (expressão + link de ajuda com a sintaxe suportada, README §7.3).
  - `data_inicio`, `data_fim` e prioridade.
  - Questionário (partial).
  - **Prévia ao vivo** das próximas 5 execuções (*debounce* de 500 ms) e a descrição em português.
  - Aviso na edição: "Ao salvar, esta regra passará a executar com as suas permissões."
- **`views/agendamentos/lista.html`:** ações Pausar/Retomar (modal) e Editar.
- **`applications/script_scheduling_service/scripts/test_agendamentos_service.py`** (FAKE + relógio injetável):
  - salvar cada tipo;
  - campos obrigatórios por tipo;
  - CRON inválido;
  - sem próxima ocorrência;
  - parâmetros inválidos;
  - edição troca o `usuario_id` para o editor;
  - editor sem permissão é negado;
  - pausar e retomar com recálculo;
  - auditoria.

**OUT**
- O desdobro real (geração de tickets) fica no daemon (F8.4). No FAKE, as datas apenas são exibidas.

## Requisitos
1. As datas digitadas são validadas no servidor e convertidas para `datetime` sem microssegundos.
2. Na edição, os valores sensíveis em `parametros_json` **não** são reexibidos. O campo vazio mantém o valor anterior, e isso fica indicado na UI.

## Critérios de aceite
- [ ] Uma regra `MENSAL` com dia 31 mostra, na prévia, 30/04 e 28/02 (ou 29/02).
- [ ] O CRON `*/15 8-18 * * 1-5` mostra a descrição e as 5 próximas datas corretas.
- [ ] A edição por outro admin troca o responsável e fica auditada.
- [ ] Os testes passam e o F3.2 continua funcionando com o partial extraído.

## Verificação
- **Browser:** criar uma regra de cada tipo; editar com outro usuário; pausar e retomar; conferir o F3.2 em regressão.
- Testes: `python -m unittest discover -s scripts -p "test_agendamentos_service.py"` e `... -p "test_ticket_service.py"`

## Saída
Relatório AGENTS.md §9.
