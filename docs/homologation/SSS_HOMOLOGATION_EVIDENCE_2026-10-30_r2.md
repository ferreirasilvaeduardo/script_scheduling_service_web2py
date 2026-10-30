# Homologação no DEV do servidor brtlvlty3067sl (CentOS 6), prefixo s3dev_ real: Registro de Evidências

**Data:** 30/10/2026 10:46:17 a 11:09:15 (horário de Brasília)

**Ambiente:** DEV do servidor brtlvlty3067sl (CentOS 6), prefixo s3dev_, banco Oracle, servidor web próprio (scripts/run_web.py → sss.cli.run_web), código em src/sss (CR-022b) em `127.0.0.1:18000 no 3067, pelo túnel do bastion`, agente `agente0001 a agente0005 (um por ambiente)`
**Resultado geral:** 352 de 352 verificações OK; 110 figuras.

Documento completo, com as telas: `SSS_Homologation_Evidence_2026-10-30_r2.docx` (mesma pasta). Gerado por `dev/others/homologation/tools/capture_evidence.js` e `build_evidence_docx.py`; o resultado bruto de cada verificação está em `dev/others/homologation/evidence_20261030_r2/results.json`. Nenhuma senha foi registrada.

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
| CT-32 | CR-025 a CR-027: interpretador do disparo, do #! e do cadastro | 41/41 | 6 | OK |
| CT-33 | CR-037: Pasta de Arquivos — envio para inputs, uso pelo script e download de outputs, sem banco | 20/20 | 8 | OK |
| — | Encerramento: regras da homologação pausadas (ficam como evidência, sem rodar) | 1/1 | 1 | OK |

## Defeitos encontrados e corrigidos

- **Agente caía com locale -a em Latin-1** (`posix._run_short`): No CentOS 6 o locale -a lista nomes em Latin-1 (bokmål): UnicodeDecodeError na subida. Saída lida em bytes e decodificada com substituição (37a1811).
- **Agente recusava a subida sem C.UTF-8** (`scheduler_loop / posix.pick_child_locale`): O child_locale fixo C.UTF-8 não existe no CentOS 6. Locale substituto com WARNING (decisão 9 B, 4b2f535).
- **Cliente Oracle 12.2 recusado** (`db_conn`): Exigia o Instant Client 19. Outra versão só avisa (decisão 10 A, 2a9b6fe).
- **DPI-1050 na conexão com cliente 12.2** (`db_conn.configure_session`): O call_timeout exige cliente 18.1+; o hasattr já levantava o erro. Sessão sem call_timeout, com WARNING (decisão 11 B, 5543c31 e 724203d).
- **#!/usr/bin/env python3 sem python3 no PATH do filho** (`env_builder`): A rodada 1 deste servidor teve 12 falhas: os utilitários Python do seed caíam com env: python3: No such file (o filho rodava com PATH=/usr/bin:/bin e o 3067 não tem /usr/bin/python3). PATH do filho com a pasta do Python do agente no fim (decisão 13 A, 78fcd99).

## Observações e diferenças em relação ao manual

- Primeira homologação fora da máquina de desenvolvimento: o DEV do servidor brtlvlty3067sl (CentOS 6, Python 3.8.5 do Sparta, cliente Oracle 12.2), instalado pelo roteiro docs/DEPLOYMENT-SERVER.md. O roteiro rodou nesta máquina, com o navegador pelo túnel e o disco do servidor lido por ssh (SSS_REMOTE_HOST e SSS_REMOTE_JUMP). Marca HOMOLOG_20261030R2.
- CT-32 com os interpretadores do 3067: #! do Python 3.8.5 do Sparta, digitado /usr/bin/python2.6, nome python3.8 e o virtualenv ~/.sss_homolog_venv; o #!/usr/bin/env python3 acha o Python do agente.
- Massa reduzida: lote de 2 GB (o /portaloptrib tinha 7,4 GB livres), gerada no próprio servidor.
- A rodada 2 teve 350/352: a MASSA e o CT-04 contaram um script a mais (diag_pasta_arquivos, que a rodada 1 deixou ativo ao parar no CT-33 por uma falha de conexão do ssh). O CT-33 da rodada 2 o desativou; a MASSA e o CT-04 foram repetidos (11/11 e 8/8).
- O admin começou na senha inicial do seed na rodada 1 (trocada no CT-01) e na senha escolhida na rodada 2 (SSS_ADMIN_START=new).

## Ressalvas

- **CT-20:** Estados Atrasado/Em risco/Offline e quadros de atenção não reproduzíveis com os cinco agentes saudáveis (um por ambiente).
- **CT-24:** Cenário de responsável inativo não reproduzível no DEV sem mudar permissões (coberto pelos testes automatizados).

## Verificações que não passaram

Nenhuma.
