==================================================
RELATÓRIO DE EXECUÇÃO — CR-008 / UF
==================================================
1. Arquivos Criados:
   - docs/architecture/REPORT-CR-008-UF.md

2. Arquivos Alterados:
   - docs/homologation/SSS_Homologation_Manual_UI_Freeze.docx (v2.5)
   - docs/prompts/UI_FREEZE.md (pré-condição do CR-008 marcada)
   - docs/architecture/CR-008-final-audit.md (seção 5)

3. Testes Executados:
   - python -m unittest discover -s scripts -p "test_*.py": OK em Python 3.6.0, 3.6.8 e 3.13.2; 819 testes por versão, 23 ignorados (Oracle). Código do commit acb2d25; o UF não altera código.
   - Chromium, servidor DEV FAKE reiniciado: 29 telas (admin, op.prod e consulta) em 360, 412, 768, 1024 e 1440 px. Foram 145 verificações, sem rolagem horizontal, sem erro JavaScript e sem violação de CSP.
   - Roteiro do CT-25 executado antes da redação, com as mensagens copiadas da tela:
     - permissão de usuários dada ao OPERADOR_PROD;
     - perfil ADMINISTRADOR não oferecido ao op.prod;
     - redefinição de senha do admin recusada pela E1;
     - regex com três {0,100} recusada;
     - SHA-256 inválido recusado e o válido gravado e exibido;
     - "solicitado por outra pessoa" para consulta;
     - Sair derrubando a segunda sessão com o mesmo cookie.
   - git diff --check: OK.

4. Checklist §8:
   - Aplicáveis: documentação (manual, UI_FREEZE, CR-008 §5); bateria completa; telas nas cinco larguras; CSP; perfis com e sem auditoria.
   - Não aplicáveis: código (sem alteração neste passo), Oracle, daemon, fencing e helper (F7 a F9).

5. Veredito:
   - PASS para o fechamento UF do CR-008 no backend FAKE.
   - NÃO TESTADO para Oracle real e agente.

6. Observações / Anomalias:
   - Manual v2.5:
     - novo CT-25 com 6 passos, 6 resultados e as figuras 66 a 68;
     - escopo, pré-condições (819 testes, commit acb2d25), lista de relatórios e checklist final atualizados;
     - nova linha no histórico.
   - O CT-25 altera o seed (matriz do OPERADOR_PROD, script carga_diaria). O próprio caso manda reiniciar o servidor no fim.
   - O LibreOffice não está instalado: o .docx foi conferido pelo texto, pela estrutura (numeração própria do CT-25, numId 43) e pelas imagens, não por PDF.
   - LEIA-ME.TXT tem alterações preexistentes fora do escopo e não integra este pacote.
   - O CR-008 está concluído na parte web/FAKE. O que é do Oracle, do agente e do purge (R-01 a R-04, R-07 a R-12, R-14, R-16 a R-18, R-20, R-22, R-25 a R-27, R-31, R-36) está especificado no README e nos prompts F7 a F9, que ainda não foram executados.
==================================================
