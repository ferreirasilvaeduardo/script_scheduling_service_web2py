# CR-020: Telas de entrada e de saída

| Campo | Valor |
|---|---|
| Status | **Em andamento.** Aprovado pelo responsável pelo produto em 2026-10-23. 020a, 020b e 020c concluídos |
| Origem | Pedido do responsável pelo produto (2026-10-23): tela de upload para a pasta de entrada e tela de download da pasta de saída, navegando no diretório correspondente |
| Restrições | Sem dependência nova. Python 3.6. SQL Oracle 11gR2 só em `repo_oracle/`. Sem nada inline (CSP) |
| Afeta | README §4.3, §4.4, §5.9 (nova), §8.13, §8.14 e §10. `AGENTS.md`. Código: `ddl_builder`, `repo_oracle/tickets`, `repo_fake`, `output_browse_service` (novo), `controllers/outputs` (novo), `ui_menu`, `audit_service`, `ticket_service`; depois agente e helper (020c) |

---

## 1. Restrições da arquitetura

* O web não enxerga o disco dos agentes: `input_dir` e `output_dir` existem só no servidor de cada agente, e o único canal entre web e agentes é o banco.
* A pasta de saída é apagada depois do empacotamento: o zip fica em `tbsss_ticket_output`. No disco só sobra o que excedeu o limite ou falhou.

## 2. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Saída pelo banco | A tela de Saídas navega pelas saídas `AVAILABLE` (ambiente, script, dia, ticket, arquivos do zip) e baixa o zip ou um arquivo, sem mudar o agente |
| D2 | Entrada pelo banco | Fila de envio com BLOB; o agente entrega pelo helper (`put-input`) como o usuário de execução e publica o retrato das pastas (`list-input`). Sem pasta de rede |
| D3 | Vários agentes | O arquivo enviado vai para **todos** os agentes do ambiente |
| D4 | Sem exclusão | A tela de entrada não apaga arquivos (o conteúdo continua do script e da operação) |
| D5 | Limite | 50 MiB por arquivo por padrão, configurável |
| D6 | Permissões novas | `DOWNLOAD_OUTPUT` "Baixar Saídas" (020a) e, para a entrada, uma funcionalidade própria (020b), por ambiente |
| D7 | Auditoria | `OUTPUT_DOWNLOAD` em todo download (inclusive pelo detalhe do ticket); depois, as ações da entrada |

## 3. Passos

| Passo | Conteúdo | Situação |
|---|---|---|
| 020a | Tela de Saídas: `DOWNLOAD_OUTPUT` no seed (ADMINISTRATOR, OPERATOR_PROD, OPERATOR_HML), leituras `output_summary` e `output_tickets`, `output_browse_service` com o `BlobReader`, `controllers/outputs`, item de menu, `OUTPUT_DOWNLOAD`, README §4.3, §4.4, §5.9 e §10, AGENTS e testes; DEV atualizado por MERGE | Concluído |
| 020b | Esquema e repositórios da entrada: `tbsss_input_upload`, `tbsss_input_delivery` (uma linha por agente vivo; sem nenhum, `NoLiveAgent`) e `tbsss_input_listing` (retrato JSON até 2.000 itens, `refresh_requested_at`); repositório `inputs` (FAKE e Oracle 11gR2), GRANTs por papel, `INPUT_UPLOAD` e `INPUT_DELIVERY`, `ROLLBACK_ENTITY_ORDER` completo; banco do DEV recriado (`02` → `01` → `99`) | Concluído |
| 020c | Agente e helper: `modules/input_phase.py` (baixar em partes, gravar pelo helper `put-input`, marcar), helper `put-input` e `list-input` (códigos 9 `EXISTS`, 10 `SPACE`, 11 `HASH`), retrato a pedido e depois de cada entrega, limpeza dos temporários na subida; falha da entrada isolada do ciclo dos tickets | Concluído |
| 020d | Tela de Entrada: navegação, envio, situação de cada envio e substituição com confirmação | Pendente |
| 020e | Purge da fila, documentação (README, AGENTS, DEPLOYMENT) e ensaio real no DEV | Pendente |
