# Homologação no DEV real: Registro de Evidências

**Data:** 24/10/2026 13:47:02 a 14:07:57 (horário de Brasília)

**Ambiente:** DEV, banco Oracle, web2py em `127.0.0.1:18000`, agente `srv-linux-local-01`
**Resultado geral:** 283 de 283 verificações OK; 93 figuras.

Documento completo, com as telas: `SSS_Homologation_Evidence_2026-10-24_r2.docx` (mesma pasta). Gerado por `dev/homologation/tools/capture_evidence.js` e `build_evidence_docx.py`; o resultado bruto de cada verificação está em `dev/homologation/evidence_20261024_r2/results.json`. Nenhuma senha foi registrada.

## Resultado por caso

| Caso | Título | Verificações | Figuras | Resultado |
|---|---|---|---|---|
| CT-01 | Login, sessão e troca de senha | 12/12 | 3 | OK |
| CT-02 | Painel inicial por perfil | 9/9 | 4 | OK |
| CT-03 | O que eu posso fazer | 10/10 | 1 | OK |
| — | Preparação da massa: tickets reais criados pelas telas e executados pelo agente | 11/11 | 0 | OK |
| CT-04 | Rodar um script (cartões) e histórico do script | 8/8 | 2 | OK |
| CT-05 | Disparo de script (criação de ticket) | 15/15 | 6 | OK |
| CT-06 | Lista de tickets, filtros e escopo | 11/11 | 4 | OK |
| CT-07 | Detalhe do ticket e visualizador de log | 8/8 | 2 | OK |
| CT-08 | Cancelamento de ticket | 8/8 | 2 | OK |
| CT-09 | Reexecução de ticket | 8/8 | 2 | OK |
| CT-10 | Perfil somente leitura (consulta) | 5/5 | 3 | OK |
| CT-11 | Gestão de Ambientes | 14/14 | 4 | OK |
| CT-12 | Gestão de Perfis e matriz de permissões | 10/10 | 5 | OK |
| CT-13 | Quem pode o quê | 6/6 | 1 | OK |
| CT-14 | Gestão de Usuários | 10/10 | 2 | OK |
| CT-15 | Dicionário de Parâmetros | 5/5 | 3 | OK |
| CT-16 | Gestão de Scripts, homologação e vínculo de parâmetros | 13/13 | 5 | OK |
| CT-17 | Regras de Agendamento | 11/11 | 5 | OK |
| CT-18 | Agenda dos próximos 7 dias | 4/4 | 2 | OK |
| CT-19 | Auditoria: trilha, filtros e exportação CSV | 11/11 | 4 | OK |
| CT-20 | Painel de agentes | 4/4 | 1 | OK com ressalva |
| CT-21 | Controle de acesso direto pela URL | 8/8 | 1 | OK |
| CT-22 | Tema escuro e uso em celular | 2/2 | 4 | OK |
| CT-23 | Quadro Registro: quem criou e quem alterou | 4/4 | 3 | OK |
| CT-24 | Robustez do scheduler na interface | 11/11 | 3 | OK com ressalva |
| CT-25 | Correções da auditoria final | 9/9 | 2 | OK |
| CT-26 | CR-017: menu de tickets, um ambiente só e Quem pode rodar | 8/8 | 3 | OK |
| CT-27 | CR-018: cancelar só quem enxerga, avisos ao mudar o cadastro e desempenho | 15/15 | 5 | OK |
| CT-28 | CR-020a: Saídas — navegação e download do zip ou de um arquivo | 12/12 | 4 | OK |
| CT-29 | CR-020b a 020d: Entrada — envio pela tela, entrega pelo agente e uso pelo script | 16/16 | 5 | OK |
| CT-30 | CR-019: pasta de trabalho do script (SSS_WORK_DIR) | 4/4 | 1 | OK |
| — | Encerramento: regras da homologação pausadas (ficam como evidência, sem rodar) | 1/1 | 1 | OK |

## Defeitos encontrados e corrigidos

- **Roteiro sem o botão Criar ticket** (`dev/homologation/tools/capture_evidence.js`): O roteiro clicava em button[data-summary-trigger], gancho do JavaScript antigo que saiu com o Alpine (CR-021b2). Na rodada 1 deste dia o modal de disparo não abriu, nenhum ticket foi criado e 48 verificações falharam em cascata (227 OK). Corrigido: o roteiro usa o contrato novo ([data-component="ticketTrigger"] [data-action="open"]) e o test_frontend_components confere que todo [data-*] dos seletores do roteiro existe no HTML ou no JS. Rodada 2: 283 OK, 0 falha.
- **Servidor local do DEV não subia** (`bin/start_local.sh`): O diagnóstico antes de subir ainda lia current.sss_cfg, que deixou de existir no CR-021c. Corrigido: lê app_context.require_config(); o test_app_context confere que nenhum código lê o contexto antigo.

## Observações e diferenças em relação ao manual

- Segunda rodada do dia. A primeira (evidence_20261024) parou no botão Criar ticket do roteiro (ver Defeitos); esta rodada repetiu todos os casos com a marca HOMOLOG_20261024R2.
- Telas sem Alpine.js desde o CR-021b: os componentes são JavaScript próprio (static/js/app/dom.js), sem expressão no HTML. Os textos, as classes e o comportamento das telas não mudaram; os casos de matriz, homologação, parâmetros, regra de agendamento, disparo, log, Entrada e listas passaram sem ajuste de resultado esperado.
- O agente desta rodada já tem a correção da parada (479f54b): com o .stop ou o sinal, não faz claim nem desdobro na volta seguinte.
- Cancelamento no agente real: o log não ganha a linha "processo encerrado por cancelamento (SIGTERM)", que só existia na simulação do FAKE; o motivo aparece no Detalhe técnico (CANCELLED / CANCEL_USER).

## Ressalvas

- **CT-20:** Estados Atrasado/Em risco/Offline e quadros de atenção não reproduzíveis com um único agente saudável.
- **CT-24:** Cenário de responsável inativo não reproduzível no DEV sem mudar permissões (coberto pelos testes automatizados).

## Verificações que não passaram

Nenhuma.
