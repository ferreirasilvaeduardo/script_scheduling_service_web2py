# SSS — Prompt F1.2: Biblioteca de componentes

## Leitura obrigatória antes de planejar
- `AGENTS.md` §2.3, §3.4, §4.4 (paginação)
- `README.md` §5.1, §5.2
- Arquivos do F1.1: `views/layout.html`, `static/css/sss.css`, `modules/ui_helpers.py`

## Objetivo
Criar os componentes reutilizados por todas as telas, para que as fases 3–6 só componham.

## Escopo
**IN**
- **Partials em `applications/script_scheduling_service/views/components/`** (incluídos com `{{include}}` e recebendo dados por variáveis documentadas no topo de cada arquivo, em comentário de template):
  - `badge_status.html`: status com ícone e rótulo de `ui_helpers.status_info`; `status_motivo` opcional em tooltip textual (`title`).
  - `tabela.html`: cabeçalho, linhas, estado vazio ("Nenhum registro encontrado") e estado de erro.
  - `paginacao.html`: primeira, anterior, "página X de Y", próxima e última, além do total de registros. Recebe `{pagina, tamanho, total, url_base, query_params}` e monta links preservando os filtros via `URL(vars=...)`.
  - `filtros.html`: formulário GET com campos declarados (texto, select, data início/fim) e botões "Filtrar" e "Limpar".
  - `form_campo.html`: label, input, ajuda e **erro por campo** (`is-invalid` + `invalid-feedback`). Atributos `aria-describedby` corretos.
  - `modal_confirmacao.html`: modal Bootstrap acionado por Alpine, com título, texto e botão de confirmação de cor variável (perigo/normal). O submit é um POST real, preparado para o CSRF do F2.1.
  - `alerta.html`: mensagens `response.flash` tipadas (sucesso, aviso, erro).
- **`applications/script_scheduling_service/modules/ui_helpers.py` (ampliar):**
  - `paginacao_info(pagina, tamanho, total)`, com limites de página;
  - `sanitizar_pagina(valor, padrao=1)` e `sanitizar_tamanho(valor, permitidos=(20, 50, 100))`.
- **`applications/script_scheduling_service/static/js/app/componentes.js`** com componentes `Alpine.data`:
  - `confirmacao` (abre/fecha o modal);
  - `filtros` (limpar);
  - `copiar` (copia texto para a área de transferência com feedback).
- **`applications/script_scheduling_service/controllers/dev.py`:** action `componentes()` com galeria de todos os componentes, com dados fictícios e todos os 5 status. Retorna 404 fora de DEV.
- **`applications/script_scheduling_service/scripts/test_ui_helpers.py` (ampliar):** paginação nos limites (0, negativo, além do total, total 0) e tamanho fora da lista.

**OUT**
- Sem chamadas ao repositório e sem regras de negócio.

## Requisitos
1. Os componentes funcionam **sem JavaScript** para leitura (tabelas, paginação e filtros são HTML + GET). O Alpine só melhora a interação.
2. Nenhum componente usa `x-html` nem expressão complexa inline (AGENTS §2.3).
3. Todo texto de interface fica em português com acentuação correta.

## Critérios de aceite
- [ ] `/dev/componentes` exibe todos os componentes nos temas claro e escuro, sem violação de CSP.
- [ ] A paginação preserva os filtros na URL.
- [ ] O formulário de exemplo exibe erro por campo com foco no primeiro campo inválido.
- [ ] Os testes `test_ui_*` passam.

## Verificação
- **Browser:** `/dev/componentes`, navegar pela paginação, abrir e cancelar o modal, conferir o console.
- Testes: `python -m unittest discover -s scripts -p "test_ui_*.py"`

## Saída
Relatório AGENTS.md §9.
