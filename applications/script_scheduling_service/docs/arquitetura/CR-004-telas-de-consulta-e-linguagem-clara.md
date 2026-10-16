# CR-004: Telas de consulta e linguagem clara

| Campo | Valor |
|---|---|
| Status | **Aprovado** em 2026-10-16 pelo responsável pelo produto ("seguir a recomendação"): T1 a T5 e M1 a M4. M5 a M10 ficam no backlog, sem aprovação |
| Origem | Revisão de usabilidade com a régua "uma criança de 10 anos consegue usar sozinha" |
| Restrições | Sem mudança de arquitetura e sem dependência nova. As telas novas são actions nos controllers existentes, services em `modules/`, views com Alpine CSP e arquivos locais. Todas são só de consulta (`GET`, não gravam, não auditam) |
| Afeta | README §2.4.2 (novo), §2.4.3 (novo), §4.3.B.2 (novo), §4.3.E (novo), §5.2.1 (novo), §5.4, §5.7 (novo), §5.8 (novo), §7.7 (novo) e §10 (mensagem de conflito). `docs/PADRAO_CRUD_ADMIN.md`. `docs/prompts/UI_FREEZE.md` |
| Contrato | Duas leituras novas em `RepoTickets`: `ultimas_execucoes` e `historico_script`, em FAKE agora e no Oracle no F7.3. Nenhuma escrita nova. Sem mudança no modelo de dados |
| Depende de | CR-003 concluído (P1 a P11). As telas usam as regras corrigidas (pastas base, mensagens, escopo) |

---

## 1. Itens aprovados

| # | Item | README | Resumo |
|---|---|---|---|
| T1 | O que eu posso fazer | §4.3.E | Tela para qualquer usuário: perfil, telas, ambientes, scripts que pode rodar e por que um script do perfil não aparece |
| M1 | Detalhe do ticket com frase e etapas | §5.7, §5.2.1 | Frase "o que aconteceu / o que fazer" e barra Pedido criado → Na fila → Rodando → Terminou |
| M2 | Nomes simples de situação e motivo | §2.4.2, §5.2.1 | Esperando, Rodando, Deu certo, Deu erro, Cancelado; frase por `status_motivo` |
| M4 | Mensagens em duas partes | §2.4.2 | O que aconteceu + o que fazer agora; tabela de mensagens-padrão |
| M3 | Disparo mais claro | §5.4 | Etapas explicadas, exemplo por tipo, resumo em frase, "usar as respostas da minha última execução" |
| T2 | Rotinas disponíveis | §5.8 | Cartões dos scripts que posso rodar, onde, perguntas e última execução |
| T3 | Agenda | §7.7 | O que vai rodar hoje e nos próximos 7 dias |
| T4 | Histórico do script | §5.8 | 30 dias: acertos, erros, duração típica, gráfico por dia |
| T5 | Quem pode o quê | §4.3.B.2 | Perfis que podem rodar um script ou usar um ambiente |

Também entra no README o **mapa de telas** (§2.4.3), com todas as telas, quem acessa e para que servem.

## 2. Backlog (não aprovado)

| # | Ideia |
|---|---|
| M5 | Painel com botões grandes e cartão "Precisa de atenção" |
| M6 | Listas vazias com o próximo passo |
| M7 | Datas relativas ("há 5 minutos") |
| M8 | Agendamento em modo simples, com CRON só em "Avançado" |
| M9 | Página "Como usar" com glossário |
| M10 | Campo "Ir para o ticket nº" no cabeçalho |

## 3. Plano de execução

Cada passo segue o fluxo do projeto: plano, aprovação, implementação, testes (3.6.0, 3.6.8 e 3.13), validação no navegador nas cinco larguras do §2.4.1, relatório AGENTS §9, commit e push.

| Passo | Escopo | Testes principais |
|---|---|---|
| U1 | M2 + M4: catálogo de nomes, frases e mensagens-padrão em `ui_helpers.py`, aplicado em todas as views e services | `test_ui_helpers.py` e os testes dos services que conferem mensagens |
| U2 | M1: frase e barra de etapas no detalhe do ticket | `test_ticket_service.py` e `test_ui_helpers.py` |
| U3 | T1: `default/permissoes` | Novo `test_permissoes_service.py` (admin, sem EXEC_SCRIPT, motivos, catálogo não vazado) |
| U4 | M3: disparo | `test_ticket_service.py` (frase, exemplos, última execução sem sensíveis) |
| U5 | T2: `tickets/catalogo`, `ultimas_execucoes` no contrato e no FAKE | `test_repo_contract.py` e novo `test_catalogo_service.py` |
| U6 | T3: `agendamentos/agenda` | `test_agendamentos_service.py` (limites 20/500, atrasados, escopo) |
| U7 | T4: `tickets/historico`, `historico_script` no contrato e no FAKE | `test_repo_contract.py` e `test_catalogo_service.py` (mediana, taxa, escopo, 404) |
| U8 | T5: `admin_perfis/quem_pode` | Novo `test_admin_perfis_service.py`, ampliado (admin, interseção com a homologação, inativos) |
| UF | **Fechamento:** bateria completa de testes e validações (suíte inteira nas três versões do Python, verificação no navegador de todas as telas nas cinco larguras, roteiro do `UI_FREEZE.md`) e **atualização da documentação de homologação** (`docs/homologacao/`) com as telas e as regras do CR-003 e do CR-004 | Suíte completa e roteiro manual |

Depois do UF: homologação manual do UI Freeze e tag `ui-freeze-v1`.
