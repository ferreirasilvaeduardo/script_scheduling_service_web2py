# Diretrizes Mandatórias do Projeto SSS

Antes de planejar ou executar qualquer tarefa, você DEVE seguir rigorosamente:
1. `AGENTS.md` na raiz (atenção especial a §2, §3, §5, §6, §8 e §9).
2. `README.md` na raiz (a aplicação é a raiz do repositório desde o CR-022a) (especificação de arquitetura e regras de negócio).
3. `GEMINI.md` e `PROJECT_CONTEXT.md` (memória permanente, regras estritas de banco, ADRs e topologia).

## Regras Críticas de Execução:
- **Compatibilidade:** Python 3.6 estrito. Não use sintaxes modernas proibidas (dataclasses, walrus operator, pos-only args, f-string com `=` do 3.8). F-strings simples são permitidas, porque existem no 3.6 (AGENTS §2.1; CR-034, D8).
- **Banco de Dados Oracle:** SQL 11gR2 estrito com binds obrigatórios e `sql_ident`. Prefixo de tabela fixo por ambiente (`tbsdev_` para DEV, `tbsprd_` para PROD; não parametrizado pelo config).
- **Perfis e Acesso (RBAC):** Os 3 perfis padrão homologados têm nomes em português: `ADMINISTRADOR`, `OPERADOR` e `CONSULTA`. Usuários padrão do seed: `admin`, `op.prod` e `consulta` (perfil `OPERATOR_HML` e usuário `op.hml` foram aposentados).
- **Scripts de Negócio:** Scripts operacionais e de homologação ficam na pasta base `<RAIZ>/scripts_ambiente/`.
- **Segurança & CSP:** Ambiente hermético. Nunca inclua scripts/estilos inline, CDNs externas ou URLs remotas. Todos os assets devem ser locais.
- **Relatórios:** Toda entrega deve finalizar com o relatório estrito no padrão de `AGENTS.md` §9, com veredito (PASS/FAIL) e checklist do §8.
- **Modo de Trabalho:** Primeiro apresente o plano completo de execução e aguarde aprovação antes de modificar arquivos críticos.
