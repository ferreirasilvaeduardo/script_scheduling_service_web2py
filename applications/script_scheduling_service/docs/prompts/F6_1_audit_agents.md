# SSS — Prompt F6.1: Auditoria e painel de agentes

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.3, §4.12
- `README.md` §4.3.D (`VER_AUDITORIA`), §4.4, §8.7–8.9 (heartbeat e fencing, para interpretar o painel), §10 (tabelas 15 e 16), §13 (visão operacional)
- Arquivos: `modules/repo_auditoria.py`, `modules/repo_agentes.py`, `views/components/*`

## Objetivo
Dar visibilidade operacional e de conformidade: trilha de auditoria pesquisável e painel de saúde dos agentes executores. Este é o último prompt antes do UI Freeze.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/auditoria_service.py`:**
  - `listar(ctx, filtros, pagina, tamanho)`:
    - filtros: período (intervalo), ator, ação (catálogo do README §10, tabela 16), entidade, `entidade_id` e IP;
    - ordenação `created_at DESC, id DESC`;
    - tamanho máximo de página 100;
    - período padrão: últimos 7 dias; período máximo: 90 dias (consultas mais longas exigem filtros adicionais).
  - `exportar_csv(ctx, filtros)`:
    - streaming de no máximo 50.000 linhas;
    - CSV com `csv.writer` e cabeçalho em português;
    - **neutralização de *CSV injection***: prefixar com `'` valores que começam com `=`, `+`, `-`, `@`, TAB ou CR;
    - a própria exportação é auditada.
- **`applications/script_scheduling_service/modules/agentes_service.py`:**
  - `painel(ctx, agora)`: para cada agente, retorna `codigo`, `hostname`, `status`, `versao`, `ambientes`, `iniciado_em`, `heartbeat_at` e a **saúde derivada**:
    - `OK` quando o heartbeat tiver menos de `2 × heartbeat_interval_s`;
    - `ATRASADO` até `fence_timeout_s`;
    - `EM_RISCO` até `node_offline_timeout_s`;
    - `OFFLINE` além disso, ou com status `PARADO`.

    Também traz a quantidade de tickets `RUNNING`.
  - `tickets_do_agente(ctx, codigo)`: lista dos `RUNNING`, com link para o detalhe.
- **`applications/script_scheduling_service/controllers/auditoria.py`:** `lista`, `exportar` e `agentes`, com `_exigir_func('VER_AUDITORIA')`.
- **Views:**
  - `views/auditoria/lista.html`: filtros e tabela com ator, ação, entidade, ID (link para a entidade quando houver tela), IP, data e detalhe truncado com "ver mais".
  - `views/auditoria/agentes.html`:
    - cartões por agente com a saúde (cor + ícone + texto) e "há N s";
    - lista expansível dos tickets `RUNNING`;
    - atualização automática a cada 15 s (fragmento `.load`, como no F3.3);
    - legenda explicando cada estado de saúde.
- **Painel inicial (`default/index`):** completar com cartões por permissão: contagem de tickets por status nas últimas 24 h (escopo do usuário), meus últimos 5 tickets, próximos 5 agendamentos (para quem tem `CAD_AGENDAMENTOS`) e saúde dos agentes (para quem tem `VER_AUDITORIA`).
- **`applications/script_scheduling_service/scripts/test_auditoria_service.py`:** período máximo, filtros, *CSV injection* neutralizado, limite de linhas, auditoria da exportação e a saúde do agente nos 4 limiares (relógio injetado).

**OUT**
- Sem alteração de agentes pela UI. O painel é somente leitura.

## Requisitos
1. O campo `detalhe` é exibido sempre escapado. Nenhum segredo pode aparecer (já garantido na escrita; valide com o seed).
2. A exportação respeita os mesmos filtros e o mesmo RBAC da tela.

## Critérios de aceite
- [ ] Um CSV com o valor `=CMD()` sai como `'=CMD()`.
- [ ] O painel mostra os 2 agentes do seed em estados diferentes, mudando com o relógio do FAKE.
- [ ] O painel inicial respeita as permissões de cada perfil do seed.
- [ ] Os testes passam.

## Verificação
- **Browser:** filtros, exportação e painel de agentes com `admin`, depois o painel inicial com cada usuário do seed.
- Testes: `python -m unittest discover -s scripts -p "test_auditoria_service.py"`

## Ao concluir
Rode **toda** a suíte (`python -m unittest discover -s scripts -p "test_*.py"`) e anexe o resultado ao relatório. O próximo passo é o `UI_FREEZE.md` (manual).

## Saída
Relatório AGENTS.md §9.
