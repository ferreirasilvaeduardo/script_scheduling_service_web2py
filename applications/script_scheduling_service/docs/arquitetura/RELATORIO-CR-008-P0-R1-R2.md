==================================================
RELATÓRIO DE EXECUÇÃO — CR-008 / P0, R1 e R2
==================================================
1. Arquivos Criados:
   - docs/arquitetura/CR-008-auditoria-final.md
   - docs/arquitetura/RELATORIO-CR-008-P0-R1-R2.md
   - scripts/test_cr008_r1.py
   - scripts/test_cr008_r2.py

2. Arquivos Alterados:
   - Documentação (P0): README.md, AGENTS.md (a cópia da raiz é link), docs/IMPLANTACAO.md, docs/AMBIENTE_DEV.md, docs/prompts/00_INDEX.md, F0_2, F7_1, F7_2, F7_3, F8_0, F8_1, F8_2, F8_3, F8_4, F9_1, UI_FREEZE.md
   - R1 (segurança):
     - modules/admin_crud.py (exigir_admin);
     - modules/admin_usuarios_service.py e controllers/admin_usuarios.py (E1);
     - modules/admin_perfis_service.py (E1);
     - modules/params_compiler.py (R-06);
     - modules/auth_service.py, controllers/default.py, models/10_security.py, modules/repo_usuarios.py, modules/repo_fake/usuarios.py, modules/repo_fake/seed.py e modules/rbac.py (E2);
     - modules/sss_config.py e instance/config.ini.example (sessao_max_horas, R-29);
     - modules/ui_helpers.py (mensagem sessao_max).
   - R2 (dados e agendamento):
     - modules/sql_ident.py (sessao_epoch, pid_daemon NUMBER(10), prefixo minúsculo);
     - modules/repo_agentes.py e modules/repo_fake/agentes.py (R-15);
     - modules/recurrence.py (R-19, R-21);
     - modules/admin_scripts_service.py, controllers/admin_scripts.py e views/admin_scripts/form.html (E4);
     - modules/sss_config.py (R-32, ambientes_exigem_hash, log_dir_min_livre_mb);
     - modules/rbac.py e modules/agendamentos_service.py (R-33);
     - modules/ui_helpers.py, modules/ticket_service.py e modules/agendamentos_service.py (E5).
   - Testes:
     - test_config, test_rbac, test_admin_perfis_service, test_admin_scripts_service, test_recurrence, test_ticket_service, test_auditoria_service;
     - as sessões de teste dos demais arquivos ganharam sessao_epoch.

3. Testes Executados:
   - python -m unittest discover -s scripts -p "test_*.py": OK em Python 3.6.0, 3.6.8 e 3.13.2; 819 testes por versão, 23 ignorados (Oracle, SSS_TEST_DSN ausente).
   - Regex (R-06), medido em Python 3.6.8: o pior caso aceito pela regra nova (\w*\w* + 2 × \w{0,10}) leva menos de 0,11 s com 500 caracteres. O caso da auditoria (\w{0,100} × 5) leva 8,6 s e agora é recusado. Outro caso, 2 ilimitados + 4 × \d{0,10}, levava 6,4 s com 400 caracteres e era aceito pela regra antiga; agora é recusado.
   - Chromium (servidor DEV FAKE reiniciado):
     - 29 telas com admin, op.prod e consulta, em 360, 412, 768, 1024 e 1440 px: 145 verificações, sem rolagem horizontal, sem erro JavaScript e sem violação de CSP.
     - E2: cópia do cookie de op.prod aberta antes do logout e levada ao login depois dele.
     - E5: consulta vê "solicitado por outra pessoa", e nenhum login aparece no HTML dela; admin vê os logins.
     - E4: SHA-256 inválido recusado no campo, com a mensagem de orientação.
   - git diff --check: OK no escopo da aplicação.

4. Checklist §8:
   - Aplicáveis e conferidos:
     - Python 3.6 estrito;
     - sem dependência nova;
     - sem inline nem CDN (o campo novo do formulário não tem script nem estilo);
     - RBAC no serviço (E1) e na tela (perfil admin só oferecido a admin);
     - CSRF inalterado;
     - escape no servidor (E5);
     - contratos repo_* com paridade FAKE (encerrar_sessoes, sessao_epoch, fila pelo cadastro);
     - registro do esquema × README §10 (test_db_schema);
     - regressões.
   - Não aplicáveis: SQL Oracle e EXPLAIN PLAN (F7), daemon, fencing e helper (F8). O que é deles ficou especificado no P0.

5. Veredito:
   - PASS para P0, R1 e R2 no backend FAKE e nas telas verificadas.
   - NÃO TESTADO para Oracle real e agente.

6. Observações / Anomalias:
   - Desvio do plano: R1 e R2 vão no mesmo commit. As mudanças se cruzam em ui_helpers, sql_ident, sss_config, rbac e nos testes; separá-las deixaria um dos commits sem passar na suíte.
   - E1:
     - Sem ação de auditoria nova (a lista de ações do §4.4 não muda): a recusa é WARN no log com acao=ACESSO_NEGADO, e nada é gravado.
     - Os testes de "último administrador" passaram a usar um administrador externo ao perfil, porque o caminho do "gestor" não administrador ficou fechado pela E1.
     - A proteção atômica no repositório continua testada.
   - E2: sessão anterior ao deploy (sem sessao_epoch) é encerrada na primeira requisição, com a mensagem de acesso alterado. A troca da própria senha mantém a sessão atual e derruba as demais.
   - E4: mudar o caminho sem hash calculado nem informado agora limpa o hash. O teste antigo, que preservava o hash, foi invertido.
   - E5: a gestão de usuários e a lista de usuários afetados do formulário de perfis continuam com o login, porque nelas o login é o próprio dado cadastrado.
   - R-21: test_perdidas_limitadas mudou de expectativa. Com a vencida mais recente dentro da tolerância, o SKIP gera o ticket.
   - R-19: CRON sem ocorrência no horizonte agora gera uma decisão com cron_erro. Só a sintaxe inválida lança CronErro.
   - LEIA-ME.TXT tem alterações preexistentes fora do escopo e não integra este pacote.
   - Próximo passo: UF (manual v2.5 com o CT-25, bateria e telas).
==================================================
