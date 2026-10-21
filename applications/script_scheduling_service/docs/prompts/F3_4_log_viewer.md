# SSS — Prompt F3.4: Visualizador de log com polling por offset

## Leitura obrigatória antes de planejar
- `AGENTS.md` §2.3 (`x-text`), §4.13 (LOB)
- `README.md` §8.10 (bloco "UI `VER_LOGS`" e limites), §5.1, §12.1 (`log_poll_interval_s`)
- Arquivos: `modules/repo_tickets.py` (`log_ler`), `modules/masking.py`, `views/tickets/detalhe.html`

## Objetivo
Exibir o log do ticket em tempo quase real, de forma incremental e segura, com um gerador de log simulado no FAKE.

## Escopo
**IN**
- **Gerador simulado no FAKE** (`repo_fake`, dentro do contrato existente, sem método novo):
  - Para tickets `RUNNING` do seed, `log_ler` passa a gerar linhas determinísticas em função do tempo decorrido desde `started_at` (por exemplo, "[timestamp] etapa N/50 processada"), usando o relógio injetável.
  - O texto gerado passa pelo `masking` antes de ser "persistido", simulando o `log_pump`. Uma das linhas contém um segredo registrado, para provar o mascaramento.
  - Um ticket do seed tem `log_truncado = 'S'`, com o marcador final do README §8.10.
  - Um ticket do seed gera um log de ~2 MB, para testar a paginação por offset.
- **`applications/script_scheduling_service/controllers/logs.py`:**
  - `chunk` (GET, JSON) com `ticket_id` e `offset` (inteiro >= 0, validado).
  - Retorna `{texto, proximo_offset, terminal, truncado, status}`, com no máximo 64 K caracteres por chamada.
  - Guardas: login, `pode_ver_ticket` e 404 fora do escopo.
  - Cabeçalho `Cache-Control: no-store`.
- **Painel em `views/tickets/detalhe.html`:**
  - Área monoespaçada com rolagem e preenchida **somente** via `x-text`, por concatenação.
  - "Seguir o final" ligado por padrão, que desliga quando o usuário rola para cima.
  - Botões "Pausar/Retomar" e "Baixar log".
  - Indicador de status e de "log truncado no banco".
  - O polling dura enquanto o ticket não for terminal, a cada `log_poll_interval_s` (valor injetado pelo servidor num atributo `data-*`), com *backoff* para 3× em caso de erro de rede. Ao chegar ao terminal, faz a leitura final e para.
  - Proteção de memória do navegador: com mais de 5 milhões de caracteres na tela, descarta o início e mostra o aviso "Exibindo apenas o final do log. Use 'Baixar log' para o conteúdo integral."
- **`baixar`** (GET): `text/plain; charset=utf-8` com `Content-Disposition: attachment; filename="ticket_<id>.log"`, em streaming por blocos de `log_ler` (sem montar tudo em memória). Mesmos guardas.
- **`applications/script_scheduling_service/static/js/app/log_viewer.js`:** componente `Alpine.data('logViewer')`.
- **`applications/script_scheduling_service/scripts/test_logs_controller_logic.py`:** testa a função de serviço por trás do `chunk`, extraída para `ticket_service.ler_log(ctx, id, offset)`. Cobre offset inválido, escopo, terminal, truncado e o limite de 64 K.

**OUT**
- Sem `log_pump` real (isso é o F8.2).

## Requisitos
1. É proibido `x-html` e `innerHTML` com conteúdo de log (XSS). Um log contendo `<script>alert(1)</script>` deve aparecer como texto.
2. O controller lê por offset. Nunca carrega o log inteiro numa listagem (AGENTS §4.13).
3. O download respeita o escopo e não fica em cache.

## Critérios de aceite
- [ ] Um ticket `RUNNING` exibe o log crescendo. Ao finalizar (simulado pelo avanço do relógio no FAKE), o polling para.
- [ ] O segredo simulado aparece como `****`.
- [ ] Um log com tags HTML é exibido literalmente.
- [ ] O download do log de 2 MB fica íntegro.
- [ ] Os testes passam.

## Verificação
- **Browser:** abrir o detalhe de um `RUNNING`; rolar para cima (o "seguir" deve desligar); pausar e retomar; baixar; conferir a aba Network (requisições a cada N s, offset crescente) e o console.
- Testes: `python -m unittest discover -s scripts -p "test_logs_*.py"`

## Saída
Relatório AGENTS.md §9.
