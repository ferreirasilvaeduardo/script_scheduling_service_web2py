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

O mesmo bloco está no `CLAUDE.md` e no `GEMINI.md`; a fonte de cada regra é a seção citada.

- **Compatibilidade:** Python 3.6 estrito. Não use sintaxes modernas proibidas (dataclasses, walrus operator, pos-only args, f-string com `=` do 3.8). F-strings simples são permitidas, porque existem no 3.6 (AGENTS §2.1; CR-034, D8).
- **Banco de Dados Oracle:** SQL 11gR2 estrito, com binds obrigatórios e nomes físicos só por `sql_ident` (AGENTS §3.1 e §4). Prefixo de tabela fixo por ambiente, não parametrizado pelo config: `tbsdev_` no DEV e `tbsprd_` no PROD, pela regra de `sss_config.install_env()`/`table_prefix()` (nas instalações, a pasta `<TIPO>`; `SSS_ENV` e `SSS_INSTALL_TYPE` só nos testes). A versão 1 do esquema está congelada desde o PROD do 3067 (30/10/2026): mudança de esquema incrementa `SCHEMA_VERSION` e traz migração (AGENTS §4.16).
- **Perfis e Acesso (RBAC):** Os 3 perfis padrão homologados têm nomes em português: `ADMINISTRADOR`, `OPERADOR` e `CONSULTA`. Usuários padrão do seed: `admin`, `op.prod` e `consulta` (perfil `OPERATOR_HML` e usuário `op.hml` foram aposentados).
- **Scripts:** as ferramentas de homologação ficam em `dev/others/homologation/tools/`; em `<RAIZ>/scripts_ambiente/` ficam os scripts dos ambientes (exemplos, `utilitarios/` do seed e `diagnostico/` usados pelos casos de homologação).
- **Segurança & CSP:** Ambiente hermético (AGENTS §2.3). Nenhum `<script>` inline nem atributo de evento inline, nenhum `style=` inline (estilo só por classe CSS), nenhuma CDN nem URL remota. Todos os assets devem ser locais.
- **Relatórios:** Toda entrega deve finalizar com o relatório estrito no padrão de `AGENTS.md` §9, com veredito (PASS/FAIL) e checklist do §8.
- **Modo de Trabalho (AGENTS §1):** primeiro apresente o plano completo de execução e aguarde aprovação antes de modificar arquivos críticos.
- **Decisões (AGENTS §1):** apresente uma decisão por vez, com opções (A, B, ...) e a recomendação técnica justificada.
- **Lacuna documental (AGENTS §1):** se o `README.md` não especifica um comportamento, **pare**, não invente e peça decisão.
- **Escopo estrito (AGENTS §1):** implemente apenas o item solicitado; não refatore nem renomeie código fora do escopo.
- **Idioma (AGENTS §1; `CR-016`, README §2.8):** nomes técnicos novos em **inglês** (módulos, funções, variáveis, rotas, chaves de configuração, tabelas, colunas, binds). Textos de tela, mensagens, logs legíveis, docstrings, comentários e documentação em **português** com acentuação correta. O legado em português fica como está e só muda junto com alteração funcional do mesmo trecho.
