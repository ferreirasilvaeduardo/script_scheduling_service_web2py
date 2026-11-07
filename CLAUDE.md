# Diretrizes Mandatórias do Projeto SSS

Antes de planejar ou executar qualquer tarefa, você DEVE seguir rigorosamente, nesta ordem de leitura:

1. `AGENTS.md` na raiz (atenção especial a §2, §3, §5, §6, §8 e §9).
2. `README.md` na raiz (a aplicação é a raiz do repositório desde o CR-022a) (especificação de arquitetura e regras de negócio).

## Precedência

- `README.md` é a autoridade de negócio, dados e algoritmos; `AGENTS.md` é a autoridade de **como** codificar.
- Conflito entre `AGENTS.md` e `README.md`: **pare e reporte** no campo "Observações" do relatório (`AGENTS.md` §9), sem escolher uma das versões por conta própria.
- `CLAUDE.md` e `GEMINI.md` são só atalhos para os agentes: resumem as regras críticas e não criam regra nova. Divergência deles com `AGENTS.md` ou `README.md`: vale o `AGENTS.md`/`README.md`, e a divergência é reportada.
- `PROJECT_CONTEXT.md` é um resumo do estado do projeto e nunca prevalece sobre os demais.

## Regras Críticas de Execução

- **Compatibilidade:** Python 3.6 estrito. Não use sintaxes modernas proibidas (dataclasses, walrus operator, pos-only args, f-string com `=` do 3.8). F-strings simples são permitidas, porque existem no 3.6 (AGENTS §2.1; CR-034, D8).
- **Banco de Dados Oracle:** SQL 11gR2 estrito com binds obrigatórios e `sql_ident`. Prefixo de tabela fixo por ambiente (`tbsdev_` para DEV, `tbsprd_` para PROD; não parametrizado pelo config).
- **Perfis e Acesso (RBAC):** Os 3 perfis padrão homologados têm nomes em português: `ADMINISTRADOR`, `OPERADOR` e `CONSULTA`. Usuários padrão do seed: `admin`, `op.prod` e `consulta` (perfil `OPERATOR_HML` e usuário `op.hml` foram aposentados).
- **Scripts:** as ferramentas de homologação ficam em `dev/others/homologation/tools/`; em `<RAIZ>/scripts_ambiente/` ficam os scripts dos ambientes (exemplos, `utilitarios/` do seed e `diagnostico/` usados pelos casos de homologação).
- **Segurança & CSP:** Ambiente hermético (AGENTS §2.3). Nenhum `<script>` inline nem atributo de evento inline, nenhum `style=` inline (estilo só por classe CSS), nenhuma CDN nem URL remota. Todos os assets devem ser locais.
- **Relatórios:** Toda entrega deve finalizar com o relatório estrito no padrão de `AGENTS.md` §9, com veredito (PASS/FAIL) e checklist do §8.
- **Modo de Trabalho:** Primeiro apresente o plano completo de execução e aguarde aprovação antes de modificar arquivos críticos.
- **Decisões:** apresente uma decisão por vez, com opções (A, B, ...) e a recomendação técnica justificada.
