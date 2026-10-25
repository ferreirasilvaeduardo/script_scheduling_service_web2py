# SSS — Prompt F4.3: Gestão de usuários

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.3, §3.4
- `README.md` §4.2 (hash, política de senha, bloqueio), §4.3.B, §4.4, §10 (tabela 9 `tbsss_usuarios`, imutabilidade de `login`)
- `docs/ADMIN_CRUD_PATTERN.md`, `modules/security.py`, `modules/auth_service.py`

## Objetivo
Gerenciar operadores com segurança: criação, troca de perfil, ativação, redefinição de senha e desbloqueio, aplicando a proteção do último administrador.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/admin_usuarios_service.py`:**
  - **Inclusão:**
    - `login` validado pela CK `ck_tbsss_usr_login` (minúsculas, dígitos, `.`, `_`, `-`, 3–30) e imutável;
    - `nome`;
    - `perfil_id` (somente perfis ativos);
    - senha inicial com `validar_politica_senha` e **confirmação**;
    - a senha nunca é armazenada nem registrada em claro (`hash_senha`); grava `senha_alterada_em`.
  - **Edição:** `nome`, `perfil_id` e `ativo`. A troca de perfil e a desativação aplicam a **proteção do último admin** (README §4.3.B) na mesma operação de repositório.
  - **Redefinir senha** (ação separada, POST + CSRF + confirmação): aplica a política, zera `tentativas_falha` e `bloqueado_ate`. A auditoria é `CAD_ALTERAR`, com detalhe `senha redefinida` e **sem** o valor.
  - **Desbloquear:** zera as tentativas e o bloqueio, com auditoria.
  - **Autoproteção:** o usuário logado não pode desativar a si mesmo nem remover o próprio perfil admin.
- **Troca de senha pelo próprio usuário:** em `controllers/default.py`, a action `minha_senha` (qualquer usuário logado) exige a senha atual, aplica a política, renova a sessão (`session.renew()`) e audita.
- **`applications/script_scheduling_service/controllers/admin_usuarios.py`:** `lista` (filtros login/nome/perfil/status, com indicador "Bloqueado até …"), `form`, `salvar`, `alternar_ativo`, `redefinir_senha` e `desbloquear`, todos com `_exigir_func('CAD_USUARIOS')`.
- **Views:**
  - Os campos de senha usam `type="password"` e `autocomplete="new-password"`.
  - Os requisitos da política aparecem como ajuda.
  - O campo `login` fica somente leitura na edição.
- **`applications/script_scheduling_service/scripts/test_admin_usuarios_service.py`** (FAKE):
  - inclusão OK;
  - login inválido ou duplicado;
  - senha fraca;
  - confirmação divergente;
  - troca do perfil do último admin negada;
  - desativação do último admin negada;
  - autodesativação negada;
  - redefinição zerando o bloqueio;
  - auditoria sem senha;
  - `minha_senha` com a senha atual errada.

**OUT**
- Sem recuperação de senha por e-mail (fora do escopo do README).

## Requisitos
1. Hash, senha, token e `senha_hash` nunca aparecem em tela, log, auditoria nem resposta JSON.
2. A sessão de um usuário desativado é encerrada na próxima requisição (revalidação do F2.2). Valide esse comportamento.

## Critérios de aceite
- [ ] Desativar `op.prod` com ele logado em outra janela derruba a sessão no próximo clique.
- [ ] Todas as negações da proteção de admin exibem mensagem clara.
- [ ] Os testes passam.

## Verificação
- **Browser:** os fluxos acima; inspecionar o HTML e a aba Network à procura de qualquer vestígio de hash ou senha.
- Testes: `python -m unittest discover -s scripts -p "test_admin_usuarios_service.py"`

## Saída
Relatório AGENTS.md §9.
