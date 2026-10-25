# Homologação no DEV real: Registro de Evidências

**Data:** 25/10/2026 11:24:00 a 11:44:33 (horário de Brasília)

**Ambiente:** DEV, banco Oracle, servidor web próprio (scripts/run_web.py), código em src/sss (CR-022b) em `127.0.0.1:18000`, agente `srv-linux-local-01`
**Resultado geral:** 283 de 283 verificações OK; 93 figuras.

Documento completo, com as telas: `SSS_Homologation_Evidence_2026-10-25_r6.docx` (mesma pasta). Gerado por `dev/homologation/tools/capture_evidence.js` e `build_evidence_docx.py`; o resultado bruto de cada verificação está em `dev/homologation/evidence_20261025_r6/results.json`. Nenhuma senha foi registrada.

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

Nenhum.

## Observações e diferenças em relação ao manual

- Rodada do CR-022b7, depois de mover para o pacote src/sss a camada web: núcleo (framework), montagem (app), controllers, templates e arquivos estáticos. As URLs não mudaram; todas as telas e estáticos desta rodada saem das pastas novas. Servidor web pelo bin/start_local.sh, agente pelo bin/sss-scheduler.sh, Oracle. Marca HOMOLOG_20261025R6.
- Antes desta rodada: suíte nas versões 3.6.0, 3.6.8 e 3.13.2 e bateria contra o Oracle real no 3.6.15 (driver oracledb, modo Thick), com o agente do DEV parado; pacote gerado de cópia limpa, sem o FAKE.
- Cancelamento no agente real: o log não ganha a linha "processo encerrado por cancelamento (SIGTERM)", que só existia na simulação do FAKE; o motivo aparece no Detalhe técnico (CANCELLED / CANCEL_USER).

## Ressalvas

- **CT-20:** Estados Atrasado/Em risco/Offline e quadros de atenção não reproduzíveis com um único agente saudável.
- **CT-24:** Cenário de responsável inativo não reproduzível no DEV sem mudar permissões (coberto pelos testes automatizados).

## Verificações que não passaram

Nenhuma.
