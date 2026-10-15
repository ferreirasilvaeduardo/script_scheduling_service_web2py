# SSS — Marco UI Freeze (homologação manual, sem agente)

O objetivo é congelar o comportamento visual e funcional das telas sobre o backend FAKE antes de conectar o Oracle. **Depois deste marco, qualquer mudança de tela vira change request** e exige atualização do README.

> **Roteiro de execução:** `docs/homologacao/SSS_Manual_Homologacao_UI_Freeze.docx` traz, para cada item abaixo, o passo a passo com telas, o resultado esperado e o quadro de registro. Este arquivo continua sendo a lista normativa.

## Pré-condições
- [ ] A suíte completa passa: `python -m unittest discover -s scripts -p "test_*.py"`.
- [ ] `python scripts/check_env.py` retorna 0.
- [ ] Todos os relatórios F0.1–F6.1 estão com `PASS` e sem lacunas abertas.

## Segurança transversal (executar com o DevTools aberto)
- [ ] Nenhuma requisição a domínio externo em nenhuma tela (aba Network com "preserve log").
- [ ] Nenhuma violação de CSP no console em nenhuma tela.
- [ ] Todo POST sem `_csrf` retorna 403, e todo POST com `Origin` forjado também.
- [ ] Logout é somente POST.
- [ ] Cabeçalhos do README §4.2 presentes, inclusive nas páginas 403, 404 e 500.
- [ ] Valores de parâmetro sensível não aparecem em URL, HTML após submit, logs do web2py nem `log_dir`.
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

## Usabilidade
- [ ] Navegação completa por teclado nas telas de disparo, lista de tickets e matriz de perfis.
- [ ] Temas claro e escuro legíveis (contraste AA nos badges de status).
- [ ] Mensagens de erro em português, acentuadas e acionáveis.
- [ ] Largura de 1280 px e de 1920 px sem rolagem horizontal nas listas.

## Aceite
- Responsável: ____________________   Data: ___/___/______
- Commit do freeze: `git tag ui-freeze-v1`
- Pendências aceitas (com justificativa): ____________________
