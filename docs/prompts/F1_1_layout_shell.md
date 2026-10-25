# SSS — Prompt F1.1: Layout base, design tokens e navegação

## Leitura obrigatória antes de planejar
- `AGENTS.md` §2.3, §2.4, §3.4, §5
- `README.md` §2.4, §4.2 (cabeçalhos e XSS), §4.3.D (catálogo de funcionalidades), §5.1 (estados)

## Objetivo
Construir o "shell" visual da aplicação: layout, design tokens, navegação por permissão e o carregamento hermético de assets compatível com CSP estrita.

## Direção visual
- Console operacional corporativo, **denso e legível**: tabelas compactas, foco em status e em horários.
- **Paleta neutra** com um único acento institucional. Os status usam o semáforo do README §5.1 **sempre** com texto e ícone, nunca só a cor:
  - `PENDING` âmbar;
  - `RUNNING` azul;
  - `SUCCESS` verde;
  - `FAILED` vermelho;
  - `CANCELLED` cinza.
- Tema claro e escuro via `prefers-color-scheme`, com tokens CSS em `:root`.
- Acessibilidade: `lang="pt-BR"`, contraste AA, foco visível, navegação por teclado e `aria-current` no menu ativo.

## Escopo
**IN**
- `applications/script_scheduling_service/models/00_config.py`:
  - carrega o config uma vez por processo (cache no módulo `sss_config`) e expõe `current.sss_cfg`;
  - faz `repo_factory` disponível;
  - **não** abre conexão.
- `applications/script_scheduling_service/views/layout.html`:
  - `<meta charset>`, viewport, `<title>` por página;
  - CSS: `static/bootstrap/bootstrap.min.css` e `static/css/sss.css`;
  - JS ao final, com `defer` e nesta ordem: `static/js/app/*.js` (registro de componentes no evento `alpine:init`) e depois `static/js/alpine.min.js`;
  - navbar, área de conteúdo, `<div>` de toasts e rodapé com o ambiente de execução (`sss_env`) e a versão.
- `applications/script_scheduling_service/static/css/sss.css`: tokens (cores, espaçamento, tipografia com pilha de fontes do sistema, `--sss-status-*`), ajustes de densidade de tabelas e foco, e uma faixa de alerta visível quando `sss_env != PROD`.
- `applications/script_scheduling_service/static/img/icons.svg`: sprite SVG próprio, com ícones simples desenhados por você para status, menu e ações. **Não copie** ícones de bibliotecas.
- `applications/script_scheduling_service/modules/ui_menu.py`:
  - `montar_menu(funcionalidades, is_admin) -> lista` de seções `OPERACAO` e `ADMIN`;
  - itens com rótulo acentuado, rota e código de funcionalidade;
  - função pura, sem `gluon`.
- `applications/script_scheduling_service/modules/ui_helpers.py`:
  - `status_info(status) -> {rotulo, classe, icone}`;
  - `formatar_data(dt)` no formato `dd/mm/aaaa HH:MM:SS`;
  - `formatar_duracao(inicio, fim)`;
  - funções puras.
- `applications/script_scheduling_service/controllers/dev.py`: action `shell()` que renderiza o layout com um menu simulado. Retorna **404 se `sss_env != DEV`**.
- `applications/script_scheduling_service/static/js/app/sss.js`: registro do namespace e um componente Alpine `toast` via `Alpine.data`.

**OUT**
- Sem login ou guarda real (isso é o F2.2), sem CSRF (isso é o F2.1) e sem telas de negócio.
- Cabeçalhos de segurança completos ficam para o F2.1. **Porém**, já defina em `models/00_config.py` a CSP do README §4.2 para validar que o layout funciona sob ela.

## Requisitos
1. Zero `<script>` inline, zero `style=` dinâmico, zero `on*=` e zero URL externa (AGENTS §2.3).
2. Todo dado nas views passa por `{{=...}}`, sem `XML()`.
3. O menu é derivado **somente** de `ui_menu.montar_menu`. A view não decide permissão.

## Critérios de aceite
- [ ] Em `/script_scheduling_service/dev/shell`, o layout renderiza nos temas claro e escuro.
- [ ] O console do browser não mostra **nenhuma** violação de CSP e nenhuma requisição a domínio externo (aba Network).
- [ ] Navegação completa por teclado no menu.
- [ ] `test_ui_helpers.py` (unittest) cobre `status_info` para os 5 status e um status desconhecido, além de `formatar_duracao`.
- [ ] `test_py36_compat.py` continua passando.

## Verificação
- **Browser (agente do Antigravity):** abrir `/dev/shell`, alternar o tema do sistema, conferir o console e a aba Network e capturar telas.
- Testes: `python -m unittest discover -s scripts -p "test_ui_*.py"`

## Regras de parada
Se a versão do web2py injetar scripts inline no layout ou em respostas de erro (o que viola a CSP), **pare** e reporte onde.

## Saída
Relatório AGENTS.md §9.
