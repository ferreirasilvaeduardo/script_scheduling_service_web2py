# CR-006: Colunas de registro (quem e quando criou ou alterou)

| Campo | Valor |
|---|---|
| Status | **Aprovado** em 2026-10-17 pelo responsável pelo produto: D1 a D4, as regras R-a a R-h e o plano C0, P0, R1 a R4 + UF. **Implementado** no mesmo dia: C0 `cd10c47`, P0 `3c89905`, R1 `e214c3a`, R2 `7c987bc`, R3 `4ab418a`, R4 `a0d6a90` e o fechamento UF: 737 testes OK em Python 3.6.0, 3.6.8 e 3.13.2 (22 pulados por dependerem do Oracle), sete telas sem rolagem horizontal nas cinco larguras e sem violação de CSP, e manual de homologação v2.3 (CT-23). Executar antes da homologação manual do UI Freeze |
| Origem | Análise de 2026-10-17 (tabelas × telas): só 7 das 16 tabelas tinham `created_at`, nenhuma tinha `updated_at`, e nenhuma registrava quem criou ou alterou. Essa informação existia só em `tbsss_auditoria`, que o `purge.py` apaga após `audit_retention_days` (730 dias por padrão), e não aparecia nas telas de cadastro. O criador original de um agendamento se perdia na primeira edição (`usuario_id` passa a ser o editor) |
| Restrições | Sem dependência nova. Nenhuma mudança na pilha (Python 3.6+, web2py, Oracle 11gR2, Alpine CSP). Identificadores com até 30 caracteres |
| Afeta | README §2.5, §4.4, §5.4, §5.5, §5.6, §5.7, §7.5, §7.6, §8.3, §8.4, §8.7, §8.8, §8.9, §8.10, §8.12, §10 (padrões globais e as 15 tabelas) e §11.1. `AGENTS.md` §4, §7 e §8. `docs/PADRAO_CRUD_ADMIN.md`. Prompts F7.1, F7.3, F8.2, F8.3, F8.4, F9.2, UI_FREEZE e o índice. Manual de homologação (v2.3) |
| Revoga | Nada |
| Contrato | 54 colunas novas e 15 CKs `ck_<prefixo><abrev>_upd`. Toda operação de gravação de negócio dos repositórios ganha o parâmetro `ator=` e passa a exigir o ator (por ele ou por `auditoria['ator']`); `RepoTickets.criar` usa o solicitante quando `ator=` não vem. `RepoUsuarios.reiniciar_tentativas(id)` é nova: rotina técnica do bloqueio vencido (README §4.2), sem `updated_*` nem auditoria. Os vínculos de conjunto passam a ser gravados por diferença |
| Depende de | CR-005 concluído. O F7 (Oracle) e o F8 (agente) ainda não foram executados, então não há banco nem dado de produção a migrar: as colunas entram direto no `CREATE TABLE` |

---

## 1. Decisões

| # | Decisão | Resumo |
|---|---|---|
| D1 | Escopo | As 15 tabelas, exceto `tbsss_auditoria`, recebem as colunas que faltam entre `created_at`, `created_by`, `updated_at` e `updated_by`. A auditoria fica de fora porque só recebe inclusões, nunca é alterada e já tem `ator` e `created_at` |
| D2 | Exibição | Quadro **Registro** (criado em/por, última alteração em/por) no formulário de edição dos seis cadastros (ambientes, perfis, usuários, parâmetros, scripts e agendamentos) e no detalhe do ticket. As listas não mudam, para não estourar a largura no celular (README §2.4.1) |
| D3 | Inclusão | `updated_at` e `updated_by` ficam **nulos** até a primeira alteração de negócio. A tela mostra "Nunca alterado" |
| D4 | Ordem | O CR-006 entra antes da homologação manual do UI Freeze. O manual sobe para a v2.3 |

## 2. Regras derivadas

| # | Regra | Motivo |
|---|---|---|
| R-a | **Colunas:** `created_at DATE DEFAULT SYSDATE NOT NULL`, `created_by VARCHAR2(40 CHAR) NOT NULL` (sem `DEFAULT`), `updated_at DATE` e `updated_by VARCHAR2(40 CHAR)`, nesta ordem, no fim de cada tabela (depois do `created_at`, onde ele já existia). CK `ck_<prefixo><abrev>_upd`: `(updated_at IS NULL AND updated_by IS NULL) OR (updated_at IS NOT NULL AND updated_by IS NOT NULL)`. Sem FK nem índice | O ator tem o mesmo domínio de `tbsss_auditoria.ator` (40 caracteres: login ou `SYSTEM:<agent_id>`). Sem FK porque um ator `SYSTEM:` não é usuário e o registro deve sobreviver à desativação do usuário. Nenhuma consulta filtra por essas colunas |
| R-b | **Ator:** login do usuário da sessão; `SYSTEM:<agent_id>` no daemon; `SYSTEM:init_db` no `init_db.py`; `SYSTEM:seed` no seed FAKE. `agent_id` não pode ser `init_db` nem `seed` (reservados) | Mesma convenção da auditoria (README §4.4) |
| R-c | **Quem grava:** sempre a aplicação. O `INSERT` grava `created_at = SYSDATE` e `created_by = :ator`; o `UPDATE` de negócio grava `updated_at = SYSDATE` e `updated_by = :ator`. Nenhum `UPDATE` toca `created_*`. O repositório recebe o ator por `auditoria['ator']` ou, nas operações sem auditoria, pelo parâmetro `ator=`. Sem ator, `RepoViolacao`, sem gravar nada | AGENTS §4: a aplicação informa os valores; o banco só tem as triggers do template. `created_by` sem `DEFAULT` obriga a inserção manual a se identificar |
| R-d | **Alteração de negócio** (atualiza `updated_*`): edição de cadastro; ativar e desativar; matriz de permissões (o perfil); homologação e parâmetros do script (o script); desbloquear e redefinir senha pelo admin; troca da própria senha (`minha_senha`); pausar, retomar e editar agendamento; pausa e conclusão automáticas do desdobro; toda transição de status do ticket (claim, finalização, cancelamento, `NODE_OFFLINE`, `FENCED`, `ORPHAN_PROCESS`) e o pedido de cancelamento; registro (`MERGE`) e parada do agente | São mudanças que alguém precisa saber "quem fez" |
| R-e | **Rotina técnica** (não atualiza `updated_*`): heartbeat do ticket e do agente; gravação do log (`log_output`, `log_truncado`); registro do PID (`process_id`, `process_start`); contadores e bloqueio automático do login (`tentativas_falha`, `bloqueado_ate`, `ultimo_login`) e o rehash da senha no login; avanço de `proxima_execucao`, `ultima_execucao` e `ultimo_ticket_id` no desdobro | Acontecem o tempo todo e esconderiam a última alteração feita por uma pessoa |
| R-f | **Vínculos:** `perfil_func`, `perfil_amb`, `perfil_scr` e `script_amb` são gravados por **diferença**: só insere os novos e só apaga os removidos; os que ficam mantêm o `created_*`. `script_param` continua apagando e reinserindo (a UK `(script_id, ordem)` impede trocar a ordem com `UPDATE` sem estado intermediário inválido), mas cada parâmetro que continua leva o `created_*` anterior; o `updated_*` dele muda só se `ordem`, `obrigatorio` ou `valor_padrao_sub` mudar. Salvar vínculos também grava o `updated_*` da entidade dona (o perfil na matriz, o script na homologação e nos parâmetros), a mesma entidade da auditoria | Sem a diferença, cada gravação zeraria a data de criação de todos os vínculos |
| R-g | **Significado em tickets e agendamentos:** `tickets.created_by` é o solicitante na criação manual e na reexecução, e `SYSTEM:<agent_id>` no ticket do desdobro (o `solicitante` continua o login do `usuario_id` da regra). `agendamentos.created_by` é o criador original e nunca muda; `usuario_id` continua sendo quem salvou por último (README §7.6) | Separa a autoria técnica do privilégio usado na execução |
| R-h | **Fora da concorrência e da auditoria:** as quatro colunas não entram na `versao` do formulário, no `esperado` do repositório nem no `detalhe` da auditoria. Na tela, o ator `SYSTEM:<agent_id>` aparece como "Sistema (agente <agent_id>)", `SYSTEM:init_db` como "Sistema (instalação)" e `SYSTEM:seed` como "Sistema (dados de demonstração)" | Não são campos editáveis. Linguagem clara (README §2.4.2) |

## 3. Riscos

| Risco | Mitigação |
|---|---|
| Mais escrita em toda transição do ticket | Duas colunas a mais no mesmo `UPDATE`, sem índice novo; heartbeat e log ficam de fora (R-e) |
| Repositório chamado sem ator | `RepoViolacao` antes de gravar (R-c), coberta pelo `test_repo_contract.py` no FAKE e no Oracle |
| As colunas guardam só a **última** alteração | O histórico completo continua na auditoria (README §4.4), dentro da retenção |

## 4. Plano de execução

Cada passo segue o fluxo do projeto: implementação, testes (3.6.0, 3.6.8 e 3.13.2), validação no navegador quando houver tela, relatório AGENTS §9, commit e push.

| Passo | Escopo | Testes principais |
|---|---|---|
| C0 | Título "Caminho do arquivo" na lista de scripts (achado da mesma análise; CR-005 D8) | Suíte completa e navegador |
| P0 | Este documento; README, AGENTS, `PADRAO_CRUD_ADMIN.md` e prompts não executados (F7.1, F7.3, F8.2, F8.3, F8.4, F9.2, UI_FREEZE, índice) | Suíte completa (sem código novo) |
| R1 | R-a: registro em `sql_ident.py`; R-b: `agent_id` reservado em `sss_config` | `test_db_schema.py`, `test_config.py` |
| R2 | R-c a R-g no FAKE: `store`, repositórios, contratos (ator obrigatório), vínculos por diferença e seed | `test_repo_contract.py`, `test_seed_fake.py` |
| R3 | Serviços: ator repassado em toda gravação e dados do quadro Registro em cada `formulario()` e no detalhe do ticket | Testes dos serviços de cadastro, de agendamentos e de tickets |
| R4 | D2 e R-h: componente `components/registro.html`, formatação do ator em `ui_helpers`, seis formulários e o detalhe do ticket | `test_ui_helpers.py` e navegador nas cinco larguras, sem violação de CSP |
| UF | Fechamento: bateria completa, manual de homologação v2.3 e git | Suíte completa e roteiro manual |
