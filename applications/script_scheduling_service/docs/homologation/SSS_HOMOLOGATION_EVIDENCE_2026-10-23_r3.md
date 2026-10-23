# Homologação no DEV real: Registro de Evidências

**Data:** 23/10/2026 16:53:31 a 17:18:07 (horário de Brasília)

**Ambiente:** DEV, banco Oracle, web2py em `127.0.0.1:18000`, agente `srv-linux-local-01`
**Resultado geral:** 284 de 284 verificações OK; 93 figuras.

Documento completo, com as telas: `SSS_Homologation_Evidence_2026-10-23_r3.docx` (mesma pasta). Gerado por `dev/homologation/tools/capture_evidence.js` e `build_evidence_docx.py`; o resultado bruto de cada verificação está em `dev/homologation/evidence_20261023_r3/results.json`. Nenhuma senha foi registrada.

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
| CT-15 | Dicionário de Parâmetros | 6/6 | 3 | OK |
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

- Terceira rodada do dia. O banco do DEV foi recriado no CR-020b (02 → 01 → 99): os registros das rodadas anteriores não existem mais, e a massa desta rodada foi criada do zero pelas telas (marca HOMOLOG_20261023R3).
- Telas novas desde a rodada 2: Saídas (CR-020a, funcionalidade Baixar Saídas) e Entrada (CR-020d, Enviar Arquivos), ambas concedidas no seed a ADMINISTRATOR, OPERATOR_PROD e OPERATOR_HML; o READ_ONLY recebe 403.
- A entrada pela tela vai pelo banco: o agente grava o arquivo pelo helper put-input como o usuário de execução e publica o retrato da pasta; o web nunca acessa o disco do agente.
- O purge dos envios (CR-020e) não aparece nesta rodada: o purge.py não roda no DEV (purge_user vazio). A etapa foi ensaiada no CR-020e contra o banco do DEV (conteúdos esvaziados e PURGE auditado).
- Os dois scripts de diagnóstico (diag_gerar_saida e diag_pasta_trabalho) ficam cadastrados e inativos; Rodar um script continua com os 14 utilitários do seed.
- Cancelamento no agente real: o log não ganha a linha "processo encerrado por cancelamento (SIGTERM)", que só existia na simulação do FAKE; o motivo aparece no Detalhe técnico (CANCELLED / CANCEL_USER).
- Scripts PYTHON3 rodam com -I e saída em buffer: o log de um script Python aparece quando o buffer descarrega (no fim, ou nunca, se o processo for cancelado). Scripts SH/BASH escrevem na hora.

## Ressalvas

- **CT-20:** Estados Atrasado/Em risco/Offline e quadros de atenção não reproduzíveis com um único agente saudável.
- **CT-24:** Cenário de responsável inativo não reproduzível no DEV sem mudar permissões (coberto pelos testes automatizados).

## Verificações que não passaram

Nenhuma.
