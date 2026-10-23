# CR-017: Revisão de praticidade das telas

| Campo | Valor |
|---|---|
| Status | **Concluído** em 2026-10-23. Aprovado pelo responsável pelo produto, com o escopo 017a a 017d. Evidências reais no DEV: `docs/homologation/SSS_Homologation_Evidence_2026-10-23.docx` (211 de 211 verificações, CT-26 cobre o CR-017) |
| Origem | Revisão tela a tela e processo a processo (2026-10-23): a lógica de negócio está correta, mas há um aviso de segurança que não funciona com os ambientes reais, uma lacuna de navegação e telas que repetem a mesma informação ou a mesma escolha |
| Restrições | Sem dependência nova. Python 3.6. Mudança de esquema só no 017a, dentro da `SCHEMA_VERSION` 1, que continua aberta até a primeira produção (AGENTS §4.16) |
| Afeta | README §2.4.3, §5.4, §10 (tabela 1) e §11.1. `AGENTS.md` §3.4 e §7. Código: `sql_ident`, `ddl_builder`, `init_db`, `repo_oracle/catalog`, `repo_fake`, `admin_environments_service`, `ticket_service`, `ui_menu` e as telas de ambientes e de disparo |
| Revoga | O destaque de produção pelo nome fixo `PRODUCAO` (`ticket_service.PRODUCTION_ENVIRONMENT`) |
| Fora do escopo | Limpeza de código sem mudança de comportamento (funções auxiliares repetidas nos controllers, código morto, renomear `date` usado como dicionário) e o enxugamento do README |

---

## 1. Achados que motivaram o CR

| # | Achado | Efeito |
|---|---|---|
| A1 | O destaque de produção dependia do nome `PRODUCAO`, que não existe nos ambientes reais (CLONE1, CLONE2, CLONE6, CLONE7, GFPREPROD). O README não definia a regra | O disparo nunca mostrava o selo, o alerta nem o botão vermelho |
| A2 | O item de menu da lista de tickets ("Consultar Logs") exigia `VIEW_LOGS`, mas a tela aceita também `EXEC_SCRIPT` (README §2.4.3) | Quem só dispara não tinha item no menu para ver os próprios pedidos |
| A3 | Rotinas disponíveis, Disparar (etapa 1) e "O que eu posso fazer" listam os mesmos scripts | Dois itens de menu para a mesma escolha |
| A4 | O disparo tem "Pré-visualizar comando" e o modal de confirmação mostra o mesmo comando; com um único ambiente, a etapa 2 é um clique a mais | Passos repetidos |
| A5 | O detalhe do ticket mostra a situação 4 vezes, e a barra de etapas e a linha do tempo repetem os horários | Excesso de informação |
| A6 | O painel inicial repete o menu lateral | Excesso de informação |
| A7 | O agendamento escolhe script e ambiente com listas suspensas; o disparo, com lista clicável e busca. Agenda e Agentes não têm item de menu | Dois padrões para a mesma escolha; telas difíceis de achar |
| A8 | Liberar um script para alguém exige 4 a 5 telas, sem indicação de que ele está "pronto para rodar" | Cadastro sem orientação |

## 2. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Produção no cadastro | Coluna `tbsss_environments.is_production CHAR(1) DEFAULT 'N' NOT NULL` com `ck_tbsss_env_prod`, editável como caixa de marcar na tela de ambientes e auditada. O nome do ambiente não tem significado |
| D2 | Seed | Os 5 ambientes do seed são produção (`'Y'`). O `MERGE` grava a marcação só na inclusão e não desfaz uma alteração feita no cadastro |
| D3 | Menu de tickets | O item passa a se chamar "Tickets" (o nome da tela) e aparece com `EXEC_SCRIPT` ou `VIEW_LOGS`. `ui_menu._CATALOG` aceita a tupla dos códigos |
| D4 | Disparo unificado | A etapa 1 do disparo passa a ser a tela de Rotinas disponíveis, com um único item de menu (017b) |
| D5 | Banco DEV | Recriado pelo ciclo `02` → `01` → `99`. Os registros `HOMOLOG_20261022_*` e a senha trocada do admin se perdem; as evidências de 2026-10-22 ficam como registro histórico e serão refeitas depois do 017c |

## 3. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 017a | D1, D2, D3 (A1 e A2) | Concluído |
| 017b | Telas de operação: disparo unificado com Rotinas disponíveis, sem a pré-visualização repetida, etapa 2 pulada com um ambiente; detalhe do ticket sem repetição; painel sem o menu repetido; ajuda da prioridade com o envelhecimento (A3 a A6) | Concluído |
| 017c | Agendamento com a mesma escolha do disparo, atalho "Agendar", Agenda e Agentes no menu (A7) | Concluído |
| 017d | Quadro "Quem pode rodar" no formulário do script (A8) | Concluído |

## 4. Decisões do 017b

| # | Decisão | Resumo |
|---|---|---|
| D6 | Nome da tela | "Rotinas disponíveis" passa a "Rodar um script", único item de menu para rodar. `tickets/new` sem script redireciona para os cartões |
| D7 | Detalhe do ticket | A situação fica no quadro principal e no cabeçalho do log; saem o selo do título, a linha "Situação" do resumo e a linha do tempo. "Último sinal do servidor" (heartbeat) entra no resumo enquanto roda |
| D8 | Painel inicial | Só os cartões de dados; o menu já está ao lado |

## 5. Decisões do 017c

| # | Decisão | Resumo |
|---|---|---|
| D9 | Escolha na nova regra | Lista clicável com busca (a de Rodar um script, `scriptSearch` em `components.js`) e ambientes clicáveis; com um ambiente só, direto ao formulário |
| D10 | Agendar | Botão nos cartões de Rodar um script, só com `MANAGE_SCHEDULES` |
| D11 | Menu | Agenda e Agentes no menu Operação, com os ícones já existentes; a Auditoria perde as abas |

## 6. Decisões do 017d

| # | Decisão | Resumo |
|---|---|---|
| D12 | Quem pode rodar | O quadro do cadastro de scripts usa `admin_profiles_service.script_runners`, a mesma conta de "Quem pode o quê". Parâmetro obrigatório não entra como requisito: não impede o script de rodar |
| D13 | Agendar | A regra do atalho sai do controller para `ticket_service.can_schedule`, com teste (pendência do 017c) |

## 7. Validação do 017a

* `test_admin_environments_service`, `test_ticket_service`, `test_ui_helpers`, `test_db_schema`, `test_ddl_builder` e as demais suítes afetadas (ver AGENTS §7).
* Banco DEV recriado e bateria Oracle (`SSS_TEST_ORACLE=1`).
