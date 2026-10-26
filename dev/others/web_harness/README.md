# Harness de navegador (somente DEV, CR-021)

Roteiros Playwright que conferem as telas no navegador, contra a aplicação com o backend **FAKE** (o seed dos testes) e a CSP da aplicação. Cobrem os componentes em JavaScript próprio que substituíram o Alpine.js (CR-021a e 021b). Ficam em `dev/`, fora do pacote de implantação (README §12.2).

| Arquivo | O que confere |
|---|---|
| `common.js` | Base comum: URL, Playwright, login, captura de erro de console, de erro de script e de violação de CSP, e o relatório |
| `check_components.js` | Componentes compartilhados nas telas reais: toast (`/dev/shell`), modal genérico com POST real e CSRF, copiar e filtros (`/dev/components`), busca do catálogo (`/tickets/catalog`), temas claro e escuro em 390 e 1280 px |
| `check_screens_a.js` | Lista de tickets (atualização automática), painel de agentes, Entrada (confirmação de substituir), visor de log (partes, pausar, seguir) e cadastro de parâmetro (lista de opções e foco) |
| `check_screens_b.js` | Matriz de permissões, homologação do script, vínculos de parâmetros (lista ordenável e foco), regra de agendamento (blocos por tipo e prévia) e disparo (modal com o resumo) |

## Como rodar

1. Suba a aplicação com o backend FAKE numa porta local, com a senha do seed em `SSS_DEV_SEED_PASSWORD` (o servidor e os roteiros leem a mesma variável). O runner é o `run_fake_web.py` (CR-021e): `SSS_DEV_SEED_PASSWORD=<senha> python dev/web_harness/run_fake_web.py --port 8791`, com o `instance/config.ini` do DEV e o FAKE injetado no `repo_factory`.
2. Rode cada roteiro com a mesma variável:

```bash
export SSS_DEV_SEED_PASSWORD='<senha usada pelo servidor FAKE>'
export SSS_HARNESS_URL=http://127.0.0.1:8791/script_scheduling_service   # padrão
node check_components.js
node check_screens_a.js
node check_screens_b.js
```

Cada roteiro imprime `OK`/`FALHA` por verificação e termina com o total; o código de saída é 1 se houver falha. As capturas vão para `SSS_HARNESS_OUT` (padrão `<tmp>/sss_web_harness`). O Playwright vem de `PW_MODULE` (padrão `~/tools/pw/node_modules/playwright`).

Os roteiros usam os IDs do seed FAKE (perfil 2, script 1, ticket 17, ambiente PRODUCAO). Nenhuma senha fica no código: sem `SSS_DEV_SEED_PASSWORD`, eles param com código 2.
