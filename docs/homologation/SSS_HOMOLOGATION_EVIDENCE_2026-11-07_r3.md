# Homologação no DEV real: Registro de Evidências

**Data:** 07/11/2026 11:51:49 a 12:19:41 (horário de Brasília)

**Ambiente:** DEV, banco Oracle, servidor web próprio (scripts/run_web.py → sss.cli.run_web), código em src/sss (CR-022b) em `127.0.0.1:18000`, agente `agente0001 a agente0005 (um por ambiente)`
**Resultado geral:** 362 de 363 verificações OK; 112 figuras.

Documento completo, com as telas: `SSS_Homologation_Evidence_2026-11-07_r3.docx` (mesma pasta). Gerado por `dev/others/homologation/tools/capture_evidence.js` e `build_evidence_docx.py`; o resultado bruto de cada verificação está em `dev/others/homologation/evidence_20261107_r3/results.json`. Nenhuma senha foi registrada.

## Resultado por caso

| Caso | Título | Verificações | Figuras | Resultado |
|---|---|---|---|---|
| — | Preparação: perfil restrito e usuário de teste da homologação (massa própria, pela tela) | 11/11 | 2 | OK |
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
| CT-11 | Gestão de Ambientes | 15/15 | 5 | OK |
| CT-12 | Gestão de Perfis e matriz de permissões | 10/10 | 5 | OK |
| CT-13 | Quem pode o quê | 6/6 | 1 | OK |
| CT-14 | Gestão de Usuários | 10/10 | 2 | OK |
| CT-15 | Dicionário de Parâmetros | 5/5 | 3 | OK |
| CT-16 | Gestão de Scripts, homologação e vínculo de parâmetros | 14/14 | 5 | OK |
| CT-17 | Regras de Agendamento | 11/11 | 5 | OK |
| CT-18 | Agenda dos próximos 7 dias | 4/4 | 2 | OK |
| CT-19 | Auditoria: trilha, filtros e exportação CSV | 11/11 | 4 | OK |
| CT-20 | Painel de agentes | 4/4 | 1 | OK com ressalva |
| CT-21 | Controle de acesso direto pela URL | 8/8 | 1 | OK |
| CT-22 | Tema escuro e uso em celular | 2/2 | 4 | OK |
| CT-23 | Quadro Registro: quem criou e quem alterou | 3/4 | 3 | Não OK |
| CT-24 | Robustez do scheduler na interface | 11/11 | 3 | OK com ressalva |
| CT-25 | Correções da auditoria final | 9/9 | 2 | OK |
| CT-26 | CR-017: menu de tickets e um ambiente só | 7/7 | 2 | OK |
| CT-27 | CR-018: cancelar só quem enxerga, avisos ao mudar o cadastro e desempenho | 15/15 | 5 | OK |
| CT-28 | CR-020a: Saídas — navegação e download do zip ou de um arquivo | 12/12 | 4 | OK |
| CT-29 | CR-020b a 020d: Entrada — envio pela tela, entrega pelo agente e uso pelo script | 16/16 | 5 | OK |
| CT-30 | CR-019: pasta de trabalho do script (SSS_WORK_DIR) | 4/4 | 1 | OK |
| CT-31 | CR-023: caminho relativo à pasta base do agente | 6/6 | 3 | OK |
| CT-32 | CR-025 a CR-027: interpretador do disparo, do #! e do cadastro | 41/41 | 6 | OK |
| CT-33 | CR-037: Pasta de Arquivos — envio para inputs, uso pelo script e download de outputs, sem banco | 20/20 | 8 | OK |
| — | Encerramento: regras da homologação pausadas (ficam como evidência, sem rodar) e usuário de teste desativado | 2/2 | 1 | OK |

## Defeitos encontrados e corrigidos

Nenhum.

## Observações e diferenças em relação ao manual

- Primeira rodada com a massa propria do roteiro (PREPARO: perfil HOMOLOG_RESTRITO e usuario homolog.restrito) e o seed novo, no prefixo tbsdev_ do GFPR. Marca HOMOLOG_20261107R3.
- O 3067 ficou no ar: roda o pacote 2610301500 (anterior ao a75e3c1, prefixos s3dev_/s3prd_), sem colisao com o tbsdev_ desta rodada.
- 362/363: a unica falha e o CT-24 (perfil do seed alterado por SQL direto em 06/11), registrada como achado de dado. As rodadas 1 e 2 do dia nao valem (ferramenta com o botao antigo do cartao; queda do tunel do GFPR, ORA-12541).
- O admin comecou na senha escolhida da rodada anterior (SSS_ADMIN_START=new).

## Ressalvas

- **CT-20:** Estados Atrasado/Em risco/Offline e quadros de atenção não reproduzíveis com os cinco agentes saudáveis (um por ambiente).
- **CT-24:** Perfil do seed alterado fora da aplicacao: no tbsdev_ os perfis ADMINISTRADOR e CONSULTA foram renomeados por SQL direto em 06/11/2026 (updated_by = SYSTEM:migration, sem auditoria). A verificacao aponta o dado corretamente; o codigo nao tem defeito (decisao do responsavel).

## Verificações que não passaram

- CT-23: Perfil do seed: criado pelo Sistema (instalação) e nunca alterado (Registro Criado em 06/11/2026 09:30:13 por Sistema (instalação) Última alteração 06/11/2026 10:55:46 por Sistema (agente migration))
