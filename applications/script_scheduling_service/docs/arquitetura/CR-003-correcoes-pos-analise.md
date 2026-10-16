# CR-003: Correções da análise funcional pós-F6.1 (antes do UI Freeze)

| Campo | Valor |
|---|---|
| Status | **Aprovado** em 2026-10-16 pelo responsável pelo produto: D1 a D15, com a condição de que tudo fique documentado no README; D16 (várias pastas base); e as decisões complementares C1 a C10, ratificadas |
| Origem | Análise de negócio e funcionalidade de todo o projeto, feita só por leitura (cinco frentes), complementada por uma análise externa do agendador |
| Restrições | Sem mudança de arquitetura e sem dependência nova. O backend FAKE e as fases F7–F9 continuam como estão planejadas |
| Afeta | README §2.5, §3.1, §3.2, §4.1, §4.2, §4.3 (A, B, B.1, C, D), §4.4, §5.4, §5.5, §5.6, §6.2, §6.3, §6.5, §7.2, §7.3, §7.4, §7.5, §7.6, §8.5, §8.9, §8.10, §10 (padrões globais, tabelas 1 e 6), §12.1, §12.2, §13 e §14. AGENTS §3.4 e §8. `docs/PADRAO_CRUD_ADMIN.md`. Prompts F7.3, F8.3, F8.4 e F9.2 (passo P11) |
| Afeta também (D16) | README §6.4, §6.5 (snapshot versão 3), §8.2 (filtro do claim), §8.4, §8.5, §8.12, §10 tabelas 6 e 15, §12.1 e §13. AGENTS §3.2 |
| Modelo de dados | CK `ck_tbsss_scr_path` endurecida (C4). Colunas novas `tbsss_scripts.pasta_base` (com a CK `ck_tbsss_scr_pasta`) e `tbsss_agentes.pastas_base` (D16). O banco Oracle ainda não foi criado (F7.1), então não há migração |
| Não afeta | Topologia, camada de plataforma, driver e contratos, exceto o de usuários (auditoria no login) e o de scripts (`pasta_base`) |

---

## 1. Decisões aprovadas

| # | Decisão | README |
|---|---|---|
| D1 | A conclusão de uma regra mantém `proxima_execucao = antiga_data` (NOT NULL) e grava `ativo='N'`, `CONCLUIDO`, `ultima_execucao` e `ultimo_ticket_id` num único UPDATE otimista. O passo 7 não se aplica | §7.5 |
| D2 | Sobreposição numa regra que conclui: conclui sem ticket, conta a ocorrência como perdida e registra INFO `SKIP_OVERLAP` | §7.5 |
| D3 | Perdidas dentro da tolerância vão em INFO; WARN só fora dela | §7.4 |
| D4 | Nó web: a etapa 1 roda sempre. A etapa 2 só roda se a plataforma do nó suportar o interpretador; senão, aviso e validação definitiva no agente. Vale no cadastro e na criação do ticket | §5.4, §8.5 |
| D5 | Tabela de faixas no README. `login_max_tentativas` vai de 1 a 99. `table_prefix` começa com letra. Configuração inválida gera CRITICAL (no log ou no stderr) | §12.1 |
| D6 | Login atômico: o contrato de usuários recebe `auditoria=` e os segundos do bloqueio; o repositório usa `SYSDATE`. O rehash entra na mesma operação | §4.2, §4.4 |
| D7 | `fence_timeout_s` e `node_offline_timeout_s` idênticos em todos os agentes; registro em INFO e conferência no E2E | §8.9, §14 |
| D8 | Admin reexecuta qualquer ticket visível; o novo ticket fica em nome dele | §4.3.C |
| D9 | Associações a itens inativos podem ser removidas e nunca readicionadas (matriz, homologação, vínculos) | §4.3.A, §4.3.B.1 |
| D10 | Autoproteção: o usuário não remove `is_admin` nem desativa o próprio perfil | §4.3.B |
| D11 | Entrada inválida é recusada, nunca truncada | §7.6, §10, AGENTS §3.4 |
| D12 | `AUD_EXPORTAR` conta sobre `id <= id_max` antes de gravar a linha. Tabela de entidade por ação | §4.4 |
| D13 | Encerramento pela revalidação audita `LOGOUT`; expiração por inatividade fica só no log | §4.2 |
| D14 | Sem tela de funcionalidades; a associação com o perfil fica só na matriz | §4.3.D |
| D15 | Comportamentos que o código já decidiu ficam documentados como estão (snapshot, visibilidade, CHECKBOX, limites, visor de log, lista) | §4.2, §5.5, §6.2, §6.3, §6.5, §8.10 |
| D16 | **Os scripts podem ficar em qualquer pasta cadastrada, desde que o arquivo exista.** Cada nó tem uma lista `[agent] base_script_dirs` (`NOME=caminho`). O script grava `pasta_base` (nome lógico) e `path_file` (relativo a ela). O snapshot vai para a versão 3. O claim filtra pelas pastas do agente. As checagens de dono e permissão valem para cada pasta. Caminho absoluto livre e o caminho sem checagens foram descartados: perderiam o multiplataforma e a proteção contra troca do arquivo | §6.4, §6.5, §8.2, §8.4, §8.5, §8.12, §10, §12.1, §13 |

## 2. Decisões complementares (ratificadas em 2026-10-16)

| # | Decisão | README | Motivo |
|---|---|---|---|
| C1 | Trocar `sensivel` de S para N é recusado enquanto houver valor sensível gravado. O vínculo ganha a opção "remover valor" | §6.2, §6.5 | Evita que um segredo passe a ser exibido em claro; fecha a lacuna "não há como remover o sub sensível" |
| C2 | Identificadores não recebem `strip()` (espaço é recusado). Texto livre recebe `strip()` e recusa caracteres de controle | §10, tabela 1 | Seguir a CK "à risca" e uniformizar a regra que hoje varia por tela |
| C3 | Toda solicitação de cancelamento é auditada, com o resultado (`cancelado`, `sinalizado`, `já sinalizado`, `sem efeito`) | §5.6 | O README diz "a operação é auditada"; um resultado explícito evita ambiguidade |
| C4 | `path_file` usa só `/`; recusa `\`, `:` e `//`. A CK `ck_tbsss_scr_path` é endurecida | §8.5, tabela 6 | Caminhos no estilo Windows passavam na etapa 1 |
| C5 | Na edição de script, a etapa 2 só roda se a pasta base, o caminho ou o interpretador mudar, ou na reativação | §8.5 | Um arquivo ausente impedia até editar a descrição |
| C6 | O impacto da desativação de ambiente inclui os scripts homologados | §10 | O impacto informado estava incompleto |
| C7 | A lista de parâmetros ganha a coluna "Valor padrão" (`****` quando sensível) | §6.2 | O README descrevia um comportamento que não aparecia na tela |
| C8 | A tela de disparo informa que o horário agendado é o do servidor Oracle | §5.4 | O fuso do navegador não é o do banco |
| C9 | `CAD_INSERIR` mostra referências pelo nome (`perfil: OPERADOR_PROD`) | §4.4 | Hoje registra o ID numérico |
| C10 | O daemon confere `threading.active_count() == 1` antes do primeiro spawn | §3.1 | Garante que o `preexec_fn` é seguro mesmo com o web2py carregado (`-M`) |

## 3. Rastreabilidade dos achados

| Achado | Sev. | Decisão / README | Passo |
|---|---|---|---|
| Valor sensível no hash de versão (parâmetros e vínculos) | Média | §6.2, §6.5, §10, AGENTS §3.4 | P1 |
| Configuração inválida sem CRITICAL | Média | D5, §12.1 | P2 |
| `login_max_tentativas` 100 contra `NUMBER(2)`; `table_prefix` começando por dígito | Baixa | D5, §12.1 | P2 |
| Login e auditoria em chamadas separadas; rehash separado | Média | D6, §4.2, §4.4 | P3 |
| `bloqueado_ate` e `ultimo_login` pelo relógio do nó web | Baixa | D6, §4.2 | P3 |
| "Minha senha" não reinicia a contagem depois de um bloqueio expirado | Baixa | §4.2 | P3 |
| Encerramento pela revalidação sem auditoria | Lacuna | D13, §4.2 | P3 |
| Modal de desativação de perfil só com a contagem | Baixa | §4.3.B.1 | P4 |
| Admin remove `is_admin` do próprio perfil | Lacuna | D10, §4.3.B | P4 |
| Falta `test_admin_perfis_service.py` | Baixa | PADRAO_CRUD_ADMIN | P4 |
| Associação a item inativo não pode ser removida | Lacuna | D9, §4.3.A, §4.3.B.1, §6.5 | P4 (matriz), P6 (homologação e vínculos) |
| Reexecução por admin de ticket de terceiros | Média | D8, §4.3.C | P5 (só documentação; o código já faz) |
| CANC_TICKET sem VER_LOGS recebe 404 | Baixa | §4.3.C | P5 |
| `scheduled_at` aceito até 59 s no passado | Baixa | §5.4 | P5 |
| Controle nas pontas rejeitado antes do `strip()` | Baixa | §6.2 | P5 |
| Cancelamento de ticket terminal sem auditoria; cancelamento repetido auditado de novo | Baixa | C3, §5.6 | P5 |
| Sem aviso de horário do servidor no disparo | Lacuna | C8, §5.4 | P5 |
| Auditoria de inclusão com "(vazio)" e campos faltando | Baixa | C9, §4.4 | P6 |
| Detalhe de vínculos sem `masking` | Baixa | §4.4 | P6 |
| `valor_padrao_sub` sensível mantido não é revalidado | Baixa | §6.5 | P6 |
| Unicidade do nome de script sem diferenciar maiúsculas no FAKE | Baixa | §8.5, §2.5 | P6 |
| `strip()` no nome de ambiente | Baixa | C2, §10 tabela 1 | P6 |
| Controle aceito em `label` e `descricao` | Lacuna | C2, §10 | P6 |
| Sensível de S para N expõe o valor; sem como remover o sub | Lacuna | C1, §6.2, §6.5 | P6 |
| `path_file` no estilo Windows; etapa 2 multiplataforma; arquivo ausente bloqueia a edição | Lacuna | D4, C4, C5, §8.5 | P6 |
| Impacto da desativação de ambiente incompleto | Lacuna | C6, §10 | P6 |
| "Na lista aparece mascarado" sem a coluna | Baixa | C7, §6.2 | P6 |
| Scripts voltam ao form após salvar | Baixa | §8.5, PADRAO_CRUD_ADMIN | P6 (só documentação) |
| Agendamento truncado em vez de recusado | Baixa | D11, §7.6 | P7 |
| `data_fim` escondido, mas usado, em UNICA | Baixa | §7.2 | P7 |
| `descrever()` redundante em `*/n` no dia do mês | Baixa | §7.3 | P7 |
| Perdidas em WARN dentro da tolerância | Lacuna | D3, §7.4 | P7 (no `recurrence`/log do serviço) e F8.4 |
| FAKE sem FK, NOT NULL e limites; cascatas não testadas | Baixa | §2.5, §4.4 | P8 |
| Seed incoerente (acentos, credencial, prioridade, snapshots, datas) | Baixa | §2.5, §4.3.D | P8 |
| Contagem de `AUD_EXPORTAR` fora do recorte; entidades não definidas | Baixa | D12, §4.4 | P9 |
| Pastas de runtime vazias na app; `exec "$@"` no launcher | Baixa | §12.2 | P10 |
| Conclusão no desdobro com `proxima_execucao NOT NULL` | Lacuna (média) | D1, D2, §7.5 | P11 (prompt F8.4) |
| Bind DATE com microssegundos | Atenção | §7.5 | P11 (prompts F7.3, F8.4) |
| Threads no processo do daemon (`web2py -M`) | Atenção | C10, §3.1 | P11 (prompt F8.3) |
| Tempos de fencing entre nós | Lacuna (média) | D7, §8.9, §14 | P11 (prompts F8.3, F9.2) |
| Contrato do desdobro incompleto | Atenção | §7.5 | P11 (prompt F8.4) |
| `modules/audit.py` inexistente; formatação do §10.1 | Doc | §3.2, §10 tabela 1 | P0 |
| Scripts limitados a uma única pasta base | Pedido do produto | D16 | P6A (web, FAKE, snapshot v3) e P11 (prompts F7.1, F7.3, F8.0, F8.3) |

## 4. Plano de execução

Cada passo segue o fluxo do projeto: plano, aprovação, implementação, testes (3.6.0, 3.6.8 e 3.13), relatório AGENTS §9, commit e push.

| Passo | Escopo |
|---|---|
| P0 | Este CR, README, AGENTS e PADRAO_CRUD_ADMIN (só documentação). Ordem dos passos seguintes: P1, P2, P3, P4, P5, P6A, P6, P7, P8, P9, P10, P11 |
| P1 | Versão de concorrência sem valor sensível |
| P2 | CRITICAL na subida e faixas de configuração |
| P3 | Login atômico, relógio do banco, "Minha senha", auditoria da revalidação |
| P4 | Perfis: modal, autoproteção, remoção de inativos na matriz, teste próprio |
| P5 | Tickets e parâmetros |
| P6A | Pastas base (D16): `base_script_dirs` no `sss_config`; `pasta_base` no registro `sql_ident` (coluna e CK), no contrato e no FAKE; `path_guard` com o mapa; snapshot versão 3; select e prévia no cadastro de scripts; seed; testes |
| P6 | Cadastros |
| P7 | Agendamentos |
| P8 | Paridade do FAKE e seed |
| P9 | Exportação de auditoria |
| P10 | Higiene (pastas de runtime, launcher) |
| P11 | Prompts F7.1, F7.3, F8.0, F8.3, F8.4 e F9.2 (inclui D16: DDL das colunas novas, filtro `pasta_base` no claim, validação das pastas na subida, `pastas_base` no registro do agente) |

Depois do P11, vem o CR-004 (telas de consulta e linguagem clara, passos U1 a U8). Em seguida, o passo de fechamento **UF**: bateria completa de testes e validações e atualização da documentação de homologação (`docs/homologacao/`). Só então a homologação do UI Freeze (`docs/prompts/UI_FREEZE.md`) e a tag `ui-freeze-v1`.
