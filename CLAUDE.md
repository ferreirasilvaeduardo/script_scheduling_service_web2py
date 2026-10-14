# Diretrizes Mandatórias do Projeto SSS

Antes de planejar ou executar qualquer tarefa, você DEVE seguir rigorosamente:
1. `AGENTS.md` na raiz (atenção especial a §2, §3, §5, §6, §8 e §9).
2. `applications/script_scheduling_service/README.md` (especificação de arquitetura e regras de negócio).

## Regras Críticas de Execução:
- **Compatibilidade:** Python 3.6 estrito. Não use sintaxes modernas proibidas (f-strings, dataclasses, walrus operator, pos-only args).
- **Segurança & CSP:** Ambiente hermético. Nunca inclua scripts/estilos inline, CDNs externas ou URLs remotas. Todos os assets devem ser locais.
- **Relatórios:** Toda entrega deve finalizar com o relatório estrito no padrão de `AGENTS.md` §9, com veredito (PASS/FAIL) e checklist do §8.
- **Modo de Trabalho:** Primeiro apresente o plano completo de execução e aguarde aprovação antes de modificar arquivos críticos.