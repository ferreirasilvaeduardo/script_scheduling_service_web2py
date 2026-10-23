# Homologação no DEV real: Registro de Evidências

**Data:** 23/10/2026 11:07:40 a 11:32:34 (horário de Brasília)

**Ambiente:** DEV, banco Oracle, web2py em `127.0.0.1:18000`, agente `srv-linux-local-01`
**Resultado geral:** 211 de 211 verificações OK; 75 figuras.

Documento completo, com as telas: `SSS_Homologation_Evidence_2026-10-23.docx` (mesma pasta). Gerado por `dev/homologation/tools/capture_evidence.js` e `build_evidence_docx.py`; o resultado bruto de cada verificação está em `dev/homologation/evidence_20261023/results.json`. Nenhuma senha foi registrada.

## Resultado por caso

| Caso | Título | Verificações | Figuras | Resultado |
|---|---|---|---|---|
| CT-01 | Login, sessão e troca de senha | 12/12 | 3 | OK |
| CT-02 | Painel inicial por perfil | 9/9 | 4 | OK |
| CT-03 | O que eu posso fazer | 6/6 | 1 | OK |
| — | Preparação da massa: tickets reais criados pelas telas e executados pelo agente | 11/11 | 0 | OK |
| CT-04 | Rodar um script (cartões) e histórico do script | 8/8 | 2 | OK |
| CT-05 | Disparo de script (criação de ticket) | 15/15 | 6 | OK |
| CT-06 | Lista de tickets, filtros e escopo | 5/5 | 3 | OK |
| CT-07 | Detalhe do ticket e visualizador de log | 7/7 | 2 | OK |
| CT-08 | Cancelamento de ticket | 8/8 | 2 | OK |
| CT-09 | Reexecução de ticket | 8/8 | 2 | OK |
| CT-10 | Perfil somente leitura (consulta) | 5/5 | 3 | OK |
| CT-11 | Gestão de Ambientes | 10/10 | 4 | OK |
| CT-12 | Gestão de Perfis e matriz de permissões | 7/7 | 4 | OK |
| CT-13 | Quem pode o quê | 4/4 | 1 | OK |
| CT-14 | Gestão de Usuários | 10/10 | 2 | OK |
| CT-15 | Dicionário de Parâmetros | 4/4 | 2 | OK |
| CT-16 | Gestão de Scripts, homologação e vínculo de parâmetros | 13/13 | 5 | OK |
| CT-17 | Regras de Agendamento | 10/10 | 5 | OK |
| CT-18 | Agenda dos próximos 7 dias | 4/4 | 2 | OK |
| CT-19 | Auditoria: trilha, filtros e exportação CSV | 8/8 | 4 | OK |
| CT-20 | Painel de agentes | 4/4 | 1 | OK com ressalva |
| CT-21 | Controle de acesso direto pela URL | 8/8 | 1 | OK |
| CT-22 | Tema escuro e uso em celular | 2/2 | 4 | OK |
| CT-23 | Quadro Registro: quem criou e quem alterou | 4/4 | 3 | OK |
| CT-24 | Robustez do scheduler na interface | 11/11 | 3 | OK com ressalva |
| CT-25 | Correções da auditoria final | 9/9 | 2 | OK |
| CT-26 | CR-017: menu de tickets, um ambiente só e Quem pode rodar | 8/8 | 3 | OK |
| — | Encerramento: regras da homologação pausadas (ficam como evidência, sem rodar) | 1/1 | 1 | OK |

## Defeitos encontrados e corrigidos

Nenhum.

## Observações e diferenças em relação ao manual

- Banco do DEV recriado no CR-017a (rollback, implantação e validação dos scripts de docs/sql/): os registros da rodada de 22/10 não existem mais, e a massa desta rodada foi criada do zero pelas telas.
- Ambiente de produção agora é uma marcação do cadastro (tbsss_environments.is_production, CR-017a). O seed marca os 5 ambientes do DEV como produção; por isso o alerta aparece em todo disparo.
- Cancelamento no agente real: o log não ganha a linha "processo encerrado por cancelamento (SIGTERM)", que só existia na simulação do FAKE; o motivo aparece no Detalhe técnico (CANCELLED / CANCEL_USER).
- Scripts PYTHON3 rodam com -I e saída em buffer: o log de um script Python aparece quando o buffer descarrega (no fim, ou nunca, se o processo for cancelado). Scripts SH/BASH escrevem na hora.
- Três verificações da primeira passada (menu com Administração, alerta de produção e coluna Produção) procuravam o texto como escrito, mas a tela o exibe em maiúsculas por CSS. O roteiro passou a comparar sem diferenciar maiúsculas, e o CT-02, o CT-05 e o CT-11 foram executados de novo; por isso há um segundo ambiente HOMOLOG_20261023_<hhmm> (também inativo) e um segundo ticket do CT-05.

## Ressalvas

- **CT-20:** Estados Atrasado/Em risco/Offline e quadros de atenção não reproduzíveis com um único agente saudável.
- **CT-24:** Cenário de responsável inativo não reproduzível no DEV sem mudar permissões (coberto pelos testes automatizados).

## Verificações que não passaram

Nenhuma.
