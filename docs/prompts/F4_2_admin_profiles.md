# SSS — Prompt F4.2: Perfis e matriz de permissões

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.4, §4.10
- `README.md` §4.2 (revalidação e `perm_versao`), §4.3 (inteiro, **especialmente §4.3.B**), §4.4, §10 (tabelas 2–5, 7)
- `docs/ADMIN_CRUD_PATTERN.md`

## Objetivo
Gerenciar perfis e a matriz tridimensional (funcionalidades × ambientes × scripts), com efeito imediato nas sessões e com a proteção do último administrador.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/admin_perfis_service.py`:**
  - CRUD de perfil (`nome` único, `descricao`, `is_admin`, `ativo`), seguindo o padrão.
  - `salvar_matriz(ctx, ip, perfil_id, funcs, ambs, scrs)`:
    - valida que todos os IDs existem e estão ativos (um ID desconhecido rejeita a operação inteira);
    - chama `repo_rbac.matriz_salvar`, que substitui o conjunto e incrementa `perm_versao` atomicamente;
    - registra a auditoria `PERM_ALTERAR`, com o *diff* do tipo "+EXEC_SCRIPT, -VER_LOGS, +amb:PRODUCAO".
  - **Proteção do último admin** (README §4.3.B) ao desativar perfil e ao remover `is_admin`: a operação usa `repo_rbac.admins_ativos_bloquear()` na mesma operação e é rejeitada com "Operação negada: não pode restar nenhum administrador ativo." se o conjunto resultante ficar vazio.
  - Para perfil admin, a matriz fica **informativa**: a UI mostra que o perfil dispensa as dimensões 1–3, mas não a homologação (README §4.3.A).
- **`applications/script_scheduling_service/controllers/admin_perfis.py`:** `lista`, `form`, `salvar`, `alternar_ativo`, `matriz` e `salvar_matriz`, todos com `_exigir_func('CAD_PERFIS')`.
- **`views/admin_perfis/matriz.html`:**
  - Três abas: Funcionalidades (agrupadas por módulo), Ambientes e Scripts (com busca e agrupamento por grupo/categoria).
  - Checkboxes, com "marcar todos" por grupo (Alpine).
  - Contador de selecionados por aba.
  - **Resumo das alterações** antes de salvar (adicionados/removidos) dentro do modal de confirmação.
  - O salvamento é um único POST (CSRF) com as três listas.
- **Efeito imediato:** depois de salvar a matriz, o próximo request de qualquer usuário do perfil já reflete a mudança (revalidação do F2.2).
- **`applications/script_scheduling_service/scripts/test_rbac.py` (ampliar):** o *diff* da matriz; o incremento de `perm_versao`; ID inexistente rejeitado; a proteção do último admin cobrindo desativar o perfil admin único e remover `is_admin` do único perfil admin (o caso de vários admins deve passar); a auditoria.

**OUT**
- A proteção do último admin aplicada a **usuários** fica para o F4.3.

## Requisitos
1. **Paridade FAKE/ORACLE:** a operação de "travar admins e validar" é **uma** chamada de repositório (`admins_ativos_bloquear` + alteração na mesma operação). O service não pode implementar check-then-act com duas chamadas soltas.
2. Nenhuma permissão é decidida no cliente. O POST é revalidado inteiro.

## Critérios de aceite
- [ ] Retirar `VER_LOGS` de `CONSULTA` faz o menu do usuário `consulta`, já logado em outra janela, refletir a mudança no próximo clique.
- [ ] Desativar o único perfil admin é negado com a mensagem correta.
- [ ] O resumo de alterações bate com o *diff* auditado.
- [ ] Os testes passam.

## Verificação
- **Browser:** alterar a matriz com `admin` enquanto outra janela está logada como `consulta`; tentar desativar `ADMINISTRADOR`.
- Testes: `python -m unittest discover -s scripts -p "test_rbac.py"`

## Saída
Relatório AGENTS.md §9.
