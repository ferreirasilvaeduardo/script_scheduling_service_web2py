# Homologação no PROD real: Registro de Evidências

**Data:** 28/10/2026 16:13:09 a 29/10/2026 05:21:56 (horário de Brasília)

**Ambiente:** PROD, banco Oracle, servidor web próprio (scripts/run_web.py → sss.cli.run_web), código em src/sss (CR-022b) em `127.0.0.1:18100`, agente `agente0001`
**Resultado geral:** 333 de 333 verificações OK; 102 figuras.

Documento completo, com as telas: `SSS_Homologation_Evidence_2026-10-28_r2.docx` (mesma pasta). Gerado por `dev/others/homologation/tools/capture_evidence.js` e `build_evidence_docx.py`; o resultado bruto de cada verificação está em `dev/others/homologation/evidence_20261028_r2/results.json`. Nenhuma senha foi registrada.

## Resultado por caso

| Caso | Título | Verificações | Figuras | Resultado |
|---|---|---|---|---|
| CT-01 | Login, sessão e troca de senha | 13/13 | 3 | OK |
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
| CT-32 | CR-025 a CR-027: interpretador do disparo, do #! e do cadastro | 41/41 | 6 | OK |
| — | Encerramento: regras da homologação pausadas (ficam como evidência, sem rodar) | 1/1 | 1 | OK |

## Defeitos encontrados e corrigidos

- **Roteiro: CT-30 esperava a pasta do HOME no singular** (`capture_evidence.js (CT-30)`): Expectativa work/ticket_<n>/exec anterior ao CR-032e (pastas no plural); o agente gravou works/ticket_<n>/exec, que é o correto. Corrigido no roteiro; CT-30 repetido em 29/10/2026 com 4/4 OK. Não é defeito do produto.

## Observações e diferenças em relação ao manual

- Rodada do CR-033: primeira homologação no PROD, instalado pelo pacote de implantação (DEPLOYMENT §3 e §4.0), com o mesmo banco do DEV (decisão D1 A: os mesmos nomes web0001 e agente0001, com o DEV parado durante toda a rodada). Marca HOMOLOG_20261028R2.
- O PROD não mostra a faixa de ambiente nem o [DEV] no título; o rodapé diz "Ambiente PROD". Web e agente registram na subida "ambiente da instalacao: PROD".
- Web e agente subidos pelo bin/sss-keepalive.sh (web em 127.0.0.1:18100). Scripts de exemplo copiados do dev/scripts do repositório para scripts_ambiente/ (a pasta base padrão); massa de teste gerada pelo gerar_massa.py no var/agente0001/inputs do PROD.
- O banco não foi recriado: o admin já estava com a senha escolhida (SSS_ADMIN_START=new).
- A rodada completa rodou em 28/10/2026; o CT-30 foi repetido em 29/10/2026, depois da correção do roteiro e de subir de novo o web e o agente pelo keepalive (a máquina tinha reiniciado e, sem crontab, nada os subiu sozinho). Os resultados do CT-30 são os dessa segunda passada.

## Ressalvas

- **CT-20:** Estados Atrasado/Em risco/Offline e quadros de atenção não reproduzíveis com um único agente saudável.
- **CT-24:** Cenário de responsável inativo não reproduzível no DEV sem mudar permissões (coberto pelos testes automatizados).

## Verificações que não passaram

Nenhuma.
