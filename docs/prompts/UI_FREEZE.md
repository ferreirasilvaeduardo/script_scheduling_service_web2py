# SSS — Marco UI Freeze (homologação manual, sem agente)

O objetivo é congelar o comportamento visual e funcional das telas sobre o backend FAKE antes de conectar o Oracle. **Depois deste marco, qualquer mudança de tela vira change request** e exige atualização do README.

> **Roteiro de execução:** `docs/homologation/SSS_Homologation_Manual_UI_Freeze.docx` traz, para cada item abaixo, o passo a passo com telas, o resultado esperado e o quadro de registro. Este arquivo continua sendo a lista normativa.

## Pré-condições
- [ ] A suíte completa passa: `python -m unittest discover -s scripts -p "test_*.py"`.
- [ ] `python scripts/check_env.py` retorna 0.
- [ ] Todos os relatórios F0.1–F6.1 estão com `PASS` e sem lacunas abertas.
- [x] CR-003 (P1–P11, P6A), CR-004 (U1–U8) e CR-005 (R0–R5) concluídos, e o fechamento UF executado: bateria completa de testes e validações e `docs/homologation/` atualizado (manual v2.2, 16/10/2026, revisado após a auditoria pós-CR-005).
- [x] CR-006 (C0, P0, R1–R4) concluído, com o fechamento UF e o manual v2.3 (17/10/2026, CT-23): colunas de registro e quadro Registro (`docs/architecture/CR-006-record-columns.md`).
- [x] CR-007 (P0, R1–R5) concluído na parte web/FAKE, com o fechamento UF e o manual v2.4 (17/10/2026, CT-24): robustez do scheduler (`docs/architecture/CR-007-scheduler-robustness.md`, relatórios `REPORT-CR-007-R4.md`, `-R5.md` e `-UF.md`). O que é do Oracle e do agente segue especificado para o F7 e o F8. A nova auditoria (passo FINAL do CR-007, `AUDIT-2026-10-17-final-post-CR-007.md`) foi feita e originou o CR-008.
- [x] CR-008 (P0, R1, R2) concluído na parte web/FAKE, com o fechamento UF e o manual v2.5 (17/10/2026, CT-25): correções da auditoria final (`docs/architecture/CR-008-final-audit.md`, relatórios `REPORT-CR-008-P0-R1-R2.md` e `REPORT-CR-008-UF.md`). O que é do Oracle e do agente segue especificado para o F7, o F8 e o F9.

- [ ] `instance/config.ini` sem `base_script_dirs` nem `app_log_backups` (recusados desde o CR-005) e com `[logging] app_log_retention_days`.

## Segurança transversal (executar com o DevTools aberto)
- [ ] Nenhuma requisição a domínio externo em nenhuma tela (aba Network com "preserve log").
- [ ] Nenhuma violação de CSP no console em nenhuma tela.
- [ ] Todo POST sem `_csrf` retorna 403, e todo POST com `Origin` forjado também.
- [ ] Logout é somente POST.
- [ ] Cabeçalhos do README §4.2 presentes, inclusive nas páginas 403, 404 e 500.
- [ ] Valores de parâmetro sensível não aparecem em URL, HTML após submit, logs do web2py, `log_dir` nem na auditoria.
- [ ] Telas de consulta não vazam o catálogo: com op.hml, nenhum script fora do perfil aparece em O que eu posso fazer nem em Rotinas disponíveis, nem no código-fonte (AGENTS §3.4).
- [ ] Log com `<script>` é exibido como texto.
- [ ] URLs com IDs fora do escopo retornam 404 (tickets) ou 403 (cadastros).
- [ ] O `next` externo no login é ignorado.

## Matriz perfil × tela (marque o comportamento observado)

| Tela | admin | op.prod | op.hml | consulta | Esperado |
|---|---|---|---|---|---|
| Painel inicial | | | | | Cartões por permissão |
| Disparar script | | | | | Somente scripts e ambientes autorizados e homologados |
| Lista e detalhe de tickets | | | | | Escopo por ambiente |
| Cancelar e reexecutar | | | | | Conforme o README §4.3.C |
| Log do ticket | | | | | Polling, mascaramento, download |
| Ambientes / Perfis / Usuários / Parâmetros / Scripts | | | | | Somente admin, ou perfis com `CAD_*` |
| Agendamentos | | | | | `CAD_AGENDAMENTOS` |
| Auditoria e agentes | | | | | `VER_AUDITORIA` |
| O que eu posso fazer (CR-004) | | | | | Todos logados; mostra só o próprio perfil e nunca scripts fora dele |
| Rotinas disponíveis e histórico (CR-004) | | | | | `EXEC_SCRIPT`; última execução e histórico no escopo da lista de tickets |
| Agenda (CR-004) | | | | | `CAD_AGENDAMENTOS`; só regras ativas dos ambientes autorizados |
| Quem pode o quê (CR-004) | | | | | `CAD_PERFIS` |

## Caminho do script (CR-005, README §8.5)
- [ ] O caminho completo do script aparece para todos os perfis no disparo (prévia e confirmação) e no detalhe do ticket (D8).
- [ ] No cadastro, caminho relativo, com `..`, em pasta do sistema ou com barra no fim é recusado com explicação, sem gravar nada.
- [ ] Arquivo que não existe neste servidor é salvo com o aviso "Arquivo não encontrado neste servidor: a validação ocorrerá no agente…" (D4).
- [ ] O nome `App` é recusado como reservado (D7).
- [ ] A lista de scripts mostra a coluna "Caminho do arquivo" com o caminho completo (CR-006, C0).

## Colunas de registro (CR-006, README §10)
- [ ] O formulário de edição de ambientes, perfis, usuários, parâmetros, scripts e agendamentos, e o detalhe do ticket, mostram o quadro Registro: "Criado em … por …" e "Última alteração em … por …" ou "Nunca alterado". Na inclusão, o quadro não aparece.
- [ ] Um registro recém-incluído mostra "Nunca alterado"; depois de salvar uma alteração, mostra o seu login e o horário. Desativar e reativar também contam como alteração.
- [ ] Salvar sem mudar nada não altera o quadro (nada é gravado nem auditado).
- [ ] Salvar a matriz de permissões atualiza a última alteração do perfil; salvar a homologação ou os parâmetros de um script atualiza a do script.
- [ ] Num agendamento editado por outro usuário, "Criado por" continua o criador original, e a última alteração mostra quem editou.
- [ ] Registros do seed aparecem como "Sistema (dados de demonstração)"; tickets do seed finalizados pelo agente mostram "Sistema (agente …)" na última alteração.
- [ ] Cancelar um ticket na fila mostra o seu login na última alteração do detalhe.
- [ ] As listas continuam sem essas colunas e sem rolagem horizontal da página nas larguras do README §2.4.1.
- [ ] **Quem vê o login (CR-007, D6):** com `consulta` ou `op.hml`, o quadro mostra "você", "Sistema (…)" ou "outra pessoa", nunca o login de terceiros; com `admin`, mostra o login.

## Robustez na interface (CR-007)
- [ ] Cadastrar um parâmetro com regex `(a|a)*b` ou `^(\w|\d)+$` é recusado com a regra violada; `^\d+(\.\d{1,2})?$` é aceita.
- [ ] Um parâmetro sigiloso não pode voltar a não sigiloso (mensagem de orientação).
- [ ] Um valor sigiloso com menos de 4 caracteres é recusado no disparo.
- [ ] Disparar com data de agendamento além de 366 dias é recusado no campo.
- [ ] Pausar uma regra que já estava pausada em outra aba dá a mensagem de conflito; retomar uma regra cujo responsável está inativo é recusado com a causa e a orientação.
- [ ] A regra pausada mostra "Pausada em … por …: motivo" no formulário; a agenda e a lista avisam a regra que será pulada ou pausada.
- [ ] A tela de agentes mostra os quadros "Fila sem atendente", "Rodando sem PID" e "Configuração divergente" com os dados de demonstração.
- [ ] Cadastrar um script por um caminho com link simbólico é aceito (CR-011); o arquivo é conferido pelo agente, e um caminho em pasta do sistema é recusado.

## Correções da auditoria final (CR-008)
- [ ] **Administrador só por administrador (E1):** com um usuário de um perfil **não** administrativo que tenha `CAD_USUARIOS` e `CAD_PERFIS` (crie um perfil de teste), a lista de perfis do formulário de usuários não oferece o ADMINISTRADOR; redefinir a senha, desbloquear ou desativar o `admin`, marcar `is_admin` num perfil, alterar o perfil ADMINISTRADOR ou a matriz do próprio perfil é recusado com a mensagem "Só um administrador pode …" e a orientação "Peça a um administrador." (README §2.4.2), sem gravar nada.
- [ ] **Sessão revogável (E2):** com o mesmo usuário aberto em dois navegadores, sair em um encerra o outro no próximo clique (volta ao login); o mesmo vale para "Minha senha" (a sessão atual continua) e para a redefinição da senha pelo administrador.
- [ ] **Sem hash (CR-011):** o cadastro de scripts não tem campo de hash, e o estado do arquivo no nó web não impede salvar nem reativar.
- [ ] **Quadro Saída (CR-012):** no detalhe de um ticket com saída `DISPONIVEL`, o quadro mostra a quantidade e o tamanho e o botão **Baixar** entrega `ticket_<id>_saida.zip`; `EXCEDEU` e `FALHOU` mostram o agente onde os arquivos ficaram, sem botão; quem não lê o log do ticket recebe 404 no download; ticket sem saída não mostra o quadro.
- [ ] **Ator mascarado também no solicitante e no responsável (E5):** com `consulta` ou `op.hml`, "solicitado por" no detalhe e na lista de tickets e "Responsável" nas regras mostram "você" ou "outra pessoa", nunca o login de terceiros; com `admin`, mostram o login.
- [ ] **Regex com quantificadores largos (R-06):** `\w{0,100}\w{0,100}\w{0,100}x` é recusada com "mais de 2 quantificadores ilimitados (*, +, {n,} ou {m,n} com mais de 10 de diferença)"; `^[\w.]+@[\w.]+$` e `^\w{0,10}$` são aceitas.

## Usabilidade
- [ ] Navegação completa por teclado nas telas de disparo, lista de tickets e matriz de perfis.
- [ ] Temas claro e escuro legíveis (contraste AA nos badges de status).
- [ ] Mensagens de erro em português, acentuadas e acionáveis: sempre "o que aconteceu" + "o que fazer agora" (README §2.4.2).
- [ ] **Teste da criança de 10 anos** (README §2.4.2): uma pessoa sem treinamento consegue, sozinha, (1) descobrir o que pode fazer, (2) rodar um script, (3) dizer se ele deu certo e (4) saber o que fazer quando deu erro.
- [ ] Situação do ticket com os nomes simples (Esperando, Rodando, Deu certo, Deu erro, Cancelado) e a frase do detalhe conforme o README §5.2.1.
- [ ] Todas as telas do mapa (README §2.4.3) conferidas nas larguras do §2.4.1.
- [ ] Largura de 1280 px e de 1920 px sem rolagem horizontal nas listas.

## Aceite
- Responsável: ____________________   Data: ___/___/______
- Commit do freeze: `git tag ui-freeze-v1`
- Pendências aceitas (com justificativa): ____________________
