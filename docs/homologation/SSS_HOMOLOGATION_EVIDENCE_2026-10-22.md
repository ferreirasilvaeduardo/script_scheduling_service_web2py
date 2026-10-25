# Homologação no DEV real: Registro de Evidências

**Data:** 22/10/2026 18:05:27 a 18:24:53 (horário de Brasília)

**Ambiente:** DEV, banco Oracle, web2py em `127.0.0.1:18000`, agente `srv-linux-local-01`
**Resultado geral:** 186 de 186 verificações OK; 69 figuras.

Documento completo, com as telas: `SSS_Homologation_Evidence_2026-10-22.docx` (mesma pasta). Gerado por `dev/homologation/tools/capture_evidence.js` e `build_evidence_docx.py`; o resultado bruto de cada verificação está em `dev/homologation/evidence_20261022/results.json`. Nenhuma senha foi registrada.

## Resultado por caso

| Caso | Título | Verificações | Figuras | Resultado |
|---|---|---|---|---|
| CT-01 | Login, sessão e troca de senha | 12/12 | 3 | OK |
| CT-02 | Painel inicial por perfil | 8/8 | 4 | OK |
| CT-03 | O que eu posso fazer | 6/6 | 1 | OK |
| — | Preparação da massa: tickets reais criados pelas telas e executados pelo agente | 11/11 | 0 | OK |
| CT-04 | Rotinas disponíveis e histórico do script | 6/6 | 2 | OK |
| CT-05 | Disparo de script (criação de ticket) | 11/11 | 6 | OK com ressalva |
| CT-06 | Lista de tickets, filtros e escopo | 5/5 | 3 | OK |
| CT-07 | Detalhe do ticket e visualizador de log | 5/5 | 2 | OK |
| CT-08 | Cancelamento de ticket | 8/8 | 2 | OK |
| CT-09 | Reexecução de ticket | 8/8 | 2 | OK |
| CT-10 | Perfil somente leitura (consulta) | 5/5 | 3 | OK |
| CT-11 | Gestão de Ambientes | 8/8 | 3 | OK |
| CT-12 | Gestão de Perfis e matriz de permissões | 7/7 | 4 | OK |
| CT-13 | Quem pode o quê | 4/4 | 1 | OK |
| CT-14 | Gestão de Usuários | 10/10 | 2 | OK |
| CT-15 | Dicionário de Parâmetros | 3/3 | 2 | OK |
| CT-16 | Gestão de Scripts, homologação e vínculo de parâmetros | 12/12 | 5 | OK |
| CT-17 | Regras de Agendamento | 8/8 | 3 | OK |
| CT-18 | Agenda dos próximos 7 dias | 4/4 | 2 | OK |
| CT-19 | Auditoria: trilha, filtros e exportação CSV | 7/7 | 4 | OK |
| CT-20 | Painel de agentes | 3/3 | 1 | OK com ressalva |
| CT-21 | Controle de acesso direto pela URL | 8/8 | 1 | OK |
| CT-22 | Tema escuro e uso em celular | 2/2 | 4 | OK |
| CT-23 | Quadro Registro: quem criou e quem alterou | 4/4 | 3 | OK |
| CT-24 | Robustez do scheduler na interface | 11/11 | 3 | OK com ressalva |
| CT-25 | Correções da auditoria final | 9/9 | 2 | OK |
| — | Encerramento: regras da homologação pausadas (ficam como evidência, sem rodar) | 1/1 | 1 | OK |

## Defeitos encontrados e corrigidos

- **Linha de situação ao vivo vazia em 4 telas** (`views/tickets/index.html, views/tickets/detail.html, views/audit/agents.html, views/admin_profiles/matrix.html`): O template mostrava x-text="state", mas os componentes Alpine expõem statusText. Desde o CR-016a não apareciam: "Atualizada às …" da lista de tickets, "Atualizado às …" do painel de agentes, a situação do visualizador de log ("Acompanhando a execução", "Atualização pausada") e a contagem de alterações pendentes da matriz. Corrigido; conferido no CT-06, CT-12 e CT-20.
- **Duração típica "cerca de menos de 1 minuto"** (`modules/ticket_service.py (histórico do script)`): O prefixo "cerca de" era somado ao texto "menos de 1 minuto". Corrigido (abaixo de 1 minuto: "menos de 1 minuto"); teste novo em test_catalog_service.
- **Caminho longo estoura a janela de confirmação do disparo** (`static/css/sss.css (.sss-summary-answers)`): As respostas do resumo (caminhos de arquivo sem espaço) não quebravam linha e passavam da borda do modal. Corrigido (quebra em qualquer ponto); conferido na figura de confirmação do CT-05.

## Observações e diferenças em relação ao manual

- Destaque de ambiente de produção: só o ambiente chamado PRODUCAO recebe o selo vermelho e a confirmação "AMBIENTE DE PRODUÇÃO" (ticket_service.PRODUCTION_ENVIRONMENT). No DEV nenhum ambiente tem esse nome; recomenda-se torná-lo configurável antes da implantação em produção.
- Cancelamento no agente real: o log não ganha a linha "processo encerrado por cancelamento (SIGTERM)", que só existia na simulação do FAKE; o motivo aparece no Detalhe técnico (CANCELLED / CANCEL_USER).
- Scripts PYTHON3 rodam com -I e saída em buffer: o log de um script Python aparece quando o buffer descarrega (no fim, ou nunca, se o processo for cancelado). Scripts SH/BASH escrevem na hora.
- Sufixo do id da mensagem de erro dos campos: components/form_field.html usa "-erro" e os formulários próprios (disparo, regra) usam "-error". Sem efeito para o usuário; resquício do CR-016, cuja tradução foi encerrada.

## Ressalvas

- **CT-05:** Destaque de produção fixo no nome PRODUCAO (ticket_service.PRODUCTION_ENVIRONMENT): não aparece para nenhum ambiente do DEV.
- **CT-20:** Estados Atrasado/Em risco/Offline e quadros de atenção não reproduzíveis com um único agente saudável.
- **CT-24:** Cenário de responsável inativo não reproduzível no DEV sem mudar permissões (coberto pelos testes automatizados).

## Verificações que não passaram

Nenhuma.
