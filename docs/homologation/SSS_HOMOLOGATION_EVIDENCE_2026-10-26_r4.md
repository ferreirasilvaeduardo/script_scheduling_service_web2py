# Homologação no DEV real: Registro de Evidências

**Data:** 26/10/2026 16:19:24 a 16:43:35 (horário de Brasília)

**Ambiente:** DEV, banco Oracle, servidor web próprio (scripts/run_web.py → sss.cli.run_web), código em src/sss (CR-022b) em `127.0.0.1:18000`, agente `srv-linux-local-01`
**Resultado geral:** 329 de 329 verificações OK; 101 figuras.

Documento completo, com as telas: `SSS_Homologation_Evidence_2026-10-26_r4.docx` (mesma pasta). Gerado por `dev/others/homologation/tools/capture_evidence.js` e `build_evidence_docx.py`; o resultado bruto de cada verificação está em `dev/others/homologation/evidence_20261026_r4/results.json`. Nenhuma senha foi registrada.

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
| CT-16 | Gestão de Scripts, homologação e vínculo de parâmetros | 15/15 | 5 | OK |
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
| CT-31 | CR-023: caminho relativo à pasta base do agente | 6/6 | 3 | OK |
| CT-32 | CR-025/CR-026: interpretador do #!, do disparo e do cadastro | 38/38 | 5 | OK |
| — | Encerramento: regras da homologação pausadas (ficam como evidência, sem rodar) | 1/1 | 1 | OK |

## Defeitos encontrados e corrigidos

Nenhum.

## Observações e diferenças em relação ao manual

- Rodada do CR-026d (config simplificado e interpretador só no cadastro). As tabelas do DEV foram recriadas no CR-026a; o config.ini do DEV ficou só com as chaves obrigatórias e as que fogem do padrão, sem [agent] interpreters. Marca HOMOLOG_20261026R4.
- A rodada r3 do mesmo dia ficou incompleta: a massa de teste (input/ na raiz) não existia mais, e o config.ini do DEV tinha passado a usar outro agent_id e as pastas dev/input e dev/work. O roteiro passou a ler o agent_id e as pastas do config.ini, a massa passou a ser gerada por tools/gerar_massa.py no input_dir (lote de 4,5 GB para o ticket longo) e a rodada foi refeita como r4.
- Risco aceito pelo responsável pelo produto (README §8.5): quem dispara escolhe o executável quando o script não tem #! válido, e o #! vence o digitado.

## Ressalvas

- **CT-20:** Estados Atrasado/Em risco/Offline e quadros de atenção não reproduzíveis com um único agente saudável.
- **CT-24:** Cenário de responsável inativo não reproduzível no DEV sem mudar permissões (coberto pelos testes automatizados).

## Verificações que não passaram

Nenhuma.
