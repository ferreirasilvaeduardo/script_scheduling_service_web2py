==================================================
RELATÓRIO DE EXECUÇÃO — CR-007 / UF
==================================================
1. Arquivos Criados:
   - docs/architecture/REPORT-CR-007-UF.md

2. Arquivos Alterados:
   - docs/architecture/CR-007-scheduler-robustness.md (seção 5: R5 com commit, UF concluído, FINAL como próximo passo)
   - docs/homologation/SSS_Homologation_Manual_UI_Freeze.docx (v2.4)
   - docs/prompts/UI_FREEZE.md (pré-condição do CR-007 marcada)

3. Testes Executados:
   - python -m unittest discover -s scripts -p "test_*.py": OK em Python 3.6.0, 3.6.8 e 3.13.2; 794 testes por versão, 23 ignorados (Oracle, SSS_TEST_DSN ausente). Código do commit d1a262c; o UF não altera código.
   - Chromium, servidor DEV FAKE reiniciado com o seed: 29 telas (23 com admin, 3 com op.prod, 3 com consulta) em 360, 412, 768, 1024 e 1440 px, somando 145 verificações. Todas com status 200, sem rolagem horizontal da página, sem erro JavaScript e sem violação de CSP. Inclui o detalhe do ticket #16, que roda sem PID.
   - Roteiro do CT-24 executado no navegador antes da redação, com as mensagens copiadas da tela:
     - regex (a|a)*b e ^(\w|\d)+$ recusadas; ^\d+(\.\d{1,2})?$ aceita;
     - sigiloso não volta atrás;
     - valor sigiloso com 3 caracteres recusado;
     - Agendar para além de 366 dias recusado ("Escolha uma data até 18/10/2027.");
     - pausa em duas abas: "A regra já está pausada.";
     - responsável inativo: aviso na lista e retomada recusada;
     - "Pausada em … por admin" no formulário;
     - CAMINHO_COM_LINK;
     - quadro Registro mascarado para consulta e op.prod;
     - os três quadros da tela de agentes.
   - git diff --check: OK.

4. Checklist §8:
   - Aplicáveis: documentação atualizada (manual, UI_FREEZE, CR-007 §5); bateria completa nas duas pontas do Python 3.6 e na 3.13; telas nas cinco larguras; CSP; perfis com e sem auditoria (D6).
   - Não aplicáveis: código (sem alteração neste passo), SQL Oracle, migração, daemon, fencing e helper (F7/F8).

5. Veredito:
   - PASS para o fechamento UF do CR-007 no backend FAKE.
   - NÃO TESTADO para Oracle real e agente (F7/F8 não executados).

6. Observações / Anomalias:
   - Manual v2.4:
     - novo CT-24 com 10 passos, 11 resultados esperados e as figuras 63 a 65;
     - CT-20 com o resultado dos quadros de atenção e a figura 54 refeita;
     - seed descrito com o #4 vencido e o #16 sem PID;
     - pré-condições com 794 testes no d1a262c e a lista de relatórios com o CR-007;
     - escopo e checklist final com o CT-24;
     - nova linha no histórico.
   - "mais de 10.000 registros" não se reproduz com os 40 tickets do seed. O manual remete aos testes automatizados (test_cr007_r5_views, test_ui_helpers).
   - O CT-24 altera o estado do seed (op.hml desativado, parâmetros e regras). O próprio caso manda reiniciar o servidor no fim.
   - O passo do link simbólico exige criar um arquivo e um link no servidor. Um arquivo do próprio usuário do sistema é recusado antes, por GRAVAVEL_PELO_EXECUTOR, o que é o comportamento esperado.
   - O LibreOffice não está instalado: o .docx foi conferido pelo texto, pela estrutura (numeração própria do CT-24, numId 42) e pelas imagens incorporadas, não por renderização em PDF.
   - LEIA-ME.TXT tem alterações preexistentes fora do escopo e não integra este pacote.
   - Próximo passo: FINAL, nova auditoria rigorosa nas quatro frentes (ticket e motor; agendamentos; dados, Oracle e operação; segurança e execução) sobre o estado final, com relatório consolidado.
==================================================
