# SSS — Marco UI Freeze (homologação manual, sem agente)

O objetivo é congelar o comportamento visual e funcional das telas sobre o backend FAKE antes de conectar o Oracle. **Depois deste marco, qualquer mudança de tela vira change request** e exige atualização do README.

> **Roteiro de execução:** `docs/homologacao/SSS_Manual_Homologacao_UI_Freeze.docx` traz, para cada item abaixo, o passo a passo com telas, o resultado esperado e o quadro de registro. Este arquivo continua sendo a lista normativa.

## Pré-condições
- [ ] A suíte completa passa: `python -m unittest discover -s scripts -p "test_*.py"`.
- [ ] `python scripts/check_env.py` retorna 0.
- [ ] Todos os relatórios F0.1–F6.1 estão com `PASS` e sem lacunas abertas.
- [x] CR-003 (P1–P11, P6A), CR-004 (U1–U8) e CR-005 (R0–R5) concluídos, e o fechamento UF executado: bateria completa de testes e validações e `docs/homologacao/` atualizado (manual v2.1, 16/10/2026).

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
