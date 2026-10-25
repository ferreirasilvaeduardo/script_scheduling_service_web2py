==================================================
RELATÓRIO DE EXECUÇÃO — CR-007 / R5
==================================================
1. Arquivos Criados:
   - docs/architecture/REPORT-CR-007-R5.md
   - scripts/test_cr007_r5_views.py
   - views/auditoria/_diagnosticos_agentes.html

2. Arquivos Alterados:
   - README.md
   - docs/architecture/CR-007-scheduler-robustness.md
   - modules/admin_ambientes_service.py
   - modules/admin_parametros_service.py
   - modules/admin_perfis_service.py
   - modules/admin_scripts_service.py
   - modules/admin_usuarios_service.py
   - modules/agendamentos_service.py
   - modules/agentes_service.py
   - modules/auditoria_service.py
   - modules/repo_agentes.py
   - modules/repo_fake/agentes.py
   - modules/repo_fake/seed.py
   - modules/sss_config.py
   - modules/ticket_service.py
   - modules/ui_helpers.py
   - scripts/test_auditoria_service.py
   - scripts/test_config.py
   - scripts/test_registro_cr006.py
   - scripts/test_ui_helpers.py
   - views/admin_ambientes/lista.html
   - views/admin_parametros/lista.html
   - views/admin_perfis/lista.html
   - views/admin_scripts/lista.html
   - views/admin_usuarios/lista.html
   - views/agendamentos/lista.html
   - views/auditoria/agentes.load
   - views/auditoria/lista.html
   - views/components/paginacao.html
   - views/dev/componentes.html
   - views/tickets/lista.load

3. Testes Executados:
   - python -m unittest discover -s scripts -p "test_*.py": OK em Python 3.6.0, 3.6.8 e 3.13.2; 794 testes por versão, 23 ignorados.
   - Oracle real: NÃO TESTADO; SSS_TEST_DSN não configurado. Os 23 testes ignorados pertencem à bateria Oracle.
   - Chromium (servidor DEV FAKE reiniciado com o seed novo): auditoria/agentes como admin, na carga e 65 s depois; tickets/detalhe/17 como op.prod e como consulta. Larguras 360, 412, 768, 1024 e 1440 px, sem rolagem horizontal da página, sem erro JavaScript e sem violação de CSP. O único 403 registrado é o de agendamentos/form/5 para perfis sem acesso, que é o esperado.
   - Conteúdo conferido no navegador: os três quadros aparecem com os dados de demonstração (fila sem atendente depois que o agt-host02 passa a EM_RISCO). O quadro Registro mostra "você" para op.prod e "outra pessoa" para consulta; "Sistema (agente …)" e "Sistema (dados de demonstração)" para os atores do sistema; o login de terceiros não aparece no HTML.
   - "mais de 10.000": coberto por renderização real do componente em scripts/test_cr007_r5_views.py e por test_ui_helpers. O seed tem 40 tickets, então esse estado não aparece no navegador.
   - git diff --check HEAD: OK.

4. Checklist §8:
   - Itens aplicáveis ao R5 conferidos: Python 3.6 estrito; sem dependência nova; sem script, estilo ou URL remota (o parcial novo não tem inline); escape do conteúdo (config_criticos com marcação aparece escapado, conforme teste); RBAC (mascaramento no servidor, D6); contratos repo_* com paridade FAKE (fila_sem_atendente e rodando_sem_pid, sem LOB na resposta); paginação preservando os filtros; regressões.
   - Não aplicáveis ao R5: SQL Oracle e EXPLAIN PLAN (contrato especificado para o F7.3), migração e GRANTs, processos do daemon, fencing e helper (F8).
   - UF e FINAL pendentes; este relatório não constitui aceite do CR completo.

5. Veredito:
   - PASS para R5 no backend FAKE e nas telas verificadas.
   - NÃO TESTADO para Oracle real.

6. Observações / Anomalias:
   - Retomada com o R5 parcialmente implementado e sem commit, depois do commit R4 0497e76. As alterações preexistentes foram revisadas contra o README §8.12, §10 e §13 e o CR-007 (D6, R-18, R-23, R-29).
   - Corrigido: config_criticos do nó web usava call=<call_timeout_ms> (30000). O README §8.12 define call=<call_timeout_s>. Agora usa sss_config.call_timeout_s, arredondando para cima, igual ao texto que o agente grava.
   - Corrigido: o cálculo de saúde da fila sem atendente no FAKE usa o mesmo arredondamento inteiro de agentes_service.saude.
   - Corrigido: o seed não exibia nenhum quadro, mas o UI_FREEZE pede os três com os dados de demonstração. Mudanças:
     - agt-host02 com kill=10;
     - ticket 16 RUNNING sem PID e sem log simulado;
     - agt-host01 mapeia PYTHON3,BASH;
     - ticket 4 (SH em HOMOLOGACAO) vencido 3 min antes da carga.
     O README §13 descreve o cenário.
   - Snapshot inválido na fila do diagnóstico gera RepoViolacao com log; o controller mostra a mensagem de falha do painel, sem expor o snapshot.
   - "solicitado por <login>" no detalhe do ticket é o dono do pedido, um dado de negócio fora do quadro Registro e da D6. Fica registrado para a análise FINAL.
   - O sandbox apresenta / e /usr com dono nobody; as suítes rodaram fora dele, como no R4.
   - LEIA-ME.TXT tem alterações preexistentes fora do escopo e não integra este pacote.
   - Próximo passo: UF (bateria integrada, manual v2.4, UI_FREEZE e IMPLANTACAO). Depois, FINAL (nova auditoria).
==================================================
