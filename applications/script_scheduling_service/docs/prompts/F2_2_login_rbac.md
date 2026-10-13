# SSS — Prompt F2.2: Login, bloqueio, guardas e RBAC

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.4, §5
- `README.md` §4.2 (autenticação, sessão e revalidação), §4.3 (inteiro), §4.4
- Arquivos: `modules/security.py`, `models/10_security.py`, `modules/repo_usuarios.py`, `modules/repo_rbac.py`, `modules/repo_fake/seed.py`

## Objetivo
Proteger toda a aplicação com autenticação e autorização reais, sobre o backend FAKE, antes de qualquer tela de negócio.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/rbac.py`** (puro):
  - `contexto_usuario(estado)` monta `{usuario_id, login, perfil_id, is_admin, funcionalidades:set, ambientes:set, scripts:set, perm_versao}`.
  - `tem_func(ctx, codigo)`: admin sempre `True`, se o perfil estiver ativo.
  - `pode_ver_ambiente(ctx, ambiente)`.
  - `pode_executar(ctx, script, ambiente, homologacoes) -> (bool, motivo)`, cobrindo **todas** as condições do README §4.3.A. O motivo vem de um enum interno para log, nunca para o usuário.
  - `pode_cancelar(ctx, ticket)` e `pode_ver_ticket(ctx, ticket)`, conforme o README §4.3.C.
  - `prioridade_permitida(ctx, prioridade)`: a prioridade 1 é só para admin.
- **`applications/script_scheduling_service/modules/auth_service.py`:**
  - `autenticar(login, senha, ip) -> (ctx | None, mensagem_generica)`:
    - checa bloqueio e verifica a senha;
    - para login inexistente, verifica contra `hash_ficticio()`;
    - contabiliza falhas, aplica o bloqueio após `login_max_tentativas` e registra o sucesso;
    - rehash quando necessário;
    - auditoria `LOGIN_OK`, `LOGIN_FALHA` e `LOGIN_BLOQUEIO`.
  - `revalidar(sessao) -> ctx | None`, conforme a revalidação por requisição do README §4.2: recarrega a matriz quando `perm_versao` divergir e encerra a sessão se o usuário ou o perfil estiver inativo.
  - `logout(ctx, ip)`, com auditoria.
- **Guardas em `applications/script_scheduling_service/models/10_security.py`** (para os controllers):
  - `_exigir_login()`: sem sessão, redireciona para o login com `next` validado (somente caminho local que comece com `/script_scheduling_service/`, para evitar open redirect).
  - `_exigir_func(codigo)`: sem permissão, retorna 403 com página amigável e log WARN.
  - `current.sss_ctx`, preenchido pela revalidação.
- **`applications/script_scheduling_service/controllers/default.py`:**
  - `index` (painel inicial simples, que a fase 3 completa);
  - `login` (GET formulário, POST autenticação, `session.renew()` após o sucesso);
  - `logout` (**somente POST** com CSRF).
- **`applications/script_scheduling_service/views/default/login.html` e `index.html`:**
  - O login exibe a mensagem genérica "Usuário ou senha inválidos." e a mensagem de bloqueio **sem** revelar se o login existe.
  - O campo de senha usa `autocomplete="current-password"`.
- **Menu real:** o layout passa a usar `ui_menu.montar_menu` com o `current.sss_ctx` e exibe o usuário logado e o botão "Sair".
- **Senhas DEV:** em `sss_env = DEV`, o seed FAKE define as senhas dos usuários a partir da variável de ambiente `SSS_DEV_SEED_PASSWORD`, igual para todos exceto `inativo` e `bloqueado`. Sem a variável, os logins ficam impossíveis e um WARN é registrado. **Nenhuma senha no código.**
- **Testes:**
  - `applications/script_scheduling_service/scripts/test_rbac.py`: matriz de `pode_executar` (admin; admin com perfil inativo; script inativo; ambiente inativo; sem homologação; sem `EXEC_SCRIPT`; sem o ambiente; sem o script; caso OK), `pode_cancelar` (próprio vs. de terceiro, com e sem `CANC_TICKET`), `prioridade_permitida`.
  - `applications/script_scheduling_service/scripts/test_auth_service.py` (com FAKE e relógio injetado): sucesso, senha errada, inexistente, bloqueio na enésima falha, desbloqueio por tempo, inativo, rehash e auditoria gravada.

**OUT**
- Sem telas de cadastro (isso é a fase 4). A proteção do último admin é implementada no F4.2/F4.3.

## Requisitos
1. **Toda** action pública existente (exceto `default/login` e páginas de erro) chama `_exigir_login()` primeiro. O `dev/*` também, além da trava de DEV.
2. Ids e flags vindos do cliente nunca são confiáveis (README §4.3.A, último item).
3. A mensagem ao usuário é sempre genérica. O detalhe vai para o log, sem senha.

## Critérios de aceite
- [ ] Sem login, qualquer URL redireciona para `/default/login`. Um `next` externo (`//evil.com`) é ignorado.
- [ ] Com `consulta`, o menu ADMIN não aparece e a URL direta de uma rota admin (testável em `dev/`) retorna 403.
- [ ] 5 senhas erradas bloqueiam a conta, e o login correto durante o bloqueio também falha com a mensagem de bloqueio.
- [ ] Alterar `perm_versao` no FAKE (via teste) recarrega as permissões na próxima requisição.
- [ ] Os testes `test_rbac.py` e `test_auth_service.py` passam.

## Verificação
- **Browser:** fluxo de login com `admin` e com `consulta`, bloqueio, logout (confirmar que é POST) e tentativa de acesso direto a rotas.
- Testes: `python -m unittest discover -s scripts -p "test_rbac.py"` e `... -p "test_auth_service.py"`

## Saída
Relatório AGENTS.md §9.
