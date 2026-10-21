==================================================
RELATÓRIO DE EXECUÇÃO — CR-007 / R4
==================================================
1. Arquivos Criados:
   - docs/architecture/REPORT-CR-007-R4.md

2. Arquivos Alterados:
   - controllers/admin_scripts.py
   - docs/architecture/CR-007-scheduler-robustness.md
   - modules/admin_crud.py
   - modules/admin_scripts_service.py
   - modules/agendamentos_service.py
   - modules/auditoria_service.py
   - modules/recurrence.py
   - modules/repo_fake/agendamentos.py
   - modules/repo_fake/catalogo.py
   - modules/repo_fake/store.py
   - modules/repo_fake/tickets.py
   - modules/ticket_service.py
   - scripts/test_admin_scripts_service.py
   - scripts/test_agendamentos_service.py
   - scripts/test_auditoria_service.py
   - scripts/test_recurrence.py
   - scripts/test_repo_contract.py
   - scripts/test_seed_fake.py
   - scripts/test_ticket_service.py
   - views/admin_scripts/form.html
   - views/agendamentos/agenda.html
   - views/agendamentos/form.html
   - views/agendamentos/lista.html

3. Testes Executados:
   - python -m unittest discover -s scripts -p "test_*.py": OK em Python 3.6.0, 3.6.8 e 3.13.2; 782 testes por versão, 23 ignorados.
   - Oracle real: NÃO TESTADO; SSS_TEST_DSN não configurado. Os 23 testes ignorados pertencem à bateria Oracle.
   - Chromium: OK em agendamentos/lista, agendamentos/agenda, agendamentos/form/1 e admin_scripts/form/1, nas larguras 360, 390, 768, 1366 e 1920 px. Sem rolagem horizontal ou erros JavaScript; checkbox de homologação enviado por POST.
   - git diff --check HEAD -- applications/script_scheduling_service: OK.

4. Checklist §8:
   - Itens aplicáveis ao R4 conferidos: compatibilidade, dependências, FAKE, entrada, auditoria, CSRF, escape e regressões.
   - Não aplicáveis ao R4: SQL Oracle, EXPLAIN PLAN, migração/GRANTs, processos do daemon, fencing e helper. Registro do esquema foi tratado em R1; Oracle e agente são F7/F8.
   - R5, UF e FINAL pendentes; este relatório não constitui aceite do CR completo.

5. Veredito:
   - PASS para R4 no backend FAKE e nas telas verificadas.
   - NÃO TESTADO para Oracle real.

6. Observações / Anomalias:
   - Retomada a partir de 20 arquivos já preparados para R4, depois do commit R3 c69c988. As alterações preexistentes foram revisadas contra o README.
   - Corrigidos: checkbox ausente no controller; homologação explícita sem revalidar permissões do arquivo; falha silenciosa ao calcular hash; fallback de RBAC que permitia revalidação incompleta; ocorrência errada após o limite de 10.000; listagem de auditoria sem limite; CRON anual válido classificado como problema apenas por não ocorrer nos sete dias da agenda.
   - A exportação continua limitada a 50.000 e conta seu recorte por iterar, sem depender do total limitado da listagem.
   - Regressões adicionais: falha de RBAC sem retomada ou auditoria; arquivo que se torna gravável; erro de leitura sem gravação; preservação do hash quando o arquivo não existe no nó web; ocorrência duplicada; ocorrência recente após o limite e com data_fim.
   - O sandbox apresenta / e /usr com dono nobody. O teste POSIX falhou nesse ambiente e passou fora do sandbox, sem alteração ou desativação da validação. As três suítes finais rodaram fora dele.
   - LEIA-ME.TXT tem alterações preexistentes fora do escopo e não integra este pacote.
   - Próximo passo: R5. Permanecem para ele o mascaramento do quadro Registro (também no aviso de pausa), os diagnósticos dos agentes e a apresentação de "mais de 10.000". UF atualizará o manual v2.4; FINAL fará a nova auditoria.
   - Nenhuma lacuna documental bloqueante identificada no escopo R4.
==================================================
