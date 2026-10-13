# SSS — Prompt F4.1: Gestão de ambientes (estabelece o padrão de CRUD administrativo)

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.4, §5.5
- `README.md` §4.1 (DSN sem credencial), §4.3.D (`CAD_AMBIENTES`), §4.4, §10 (padrões globais, política de exclusão, tabela 1 `tbsss_ambientes`)

## Objetivo
Implementar o cadastro de ambientes e, com ele, o **padrão de CRUD administrativo** que os prompts F4.2–F4.5 vão reutilizar.

## Escopo
**IN**
- **Padrão de CRUD**, documentado em `docs/PADRAO_CRUD_ADMIN.md` (curto e objetivo):
  - telas `lista` (filtros, paginação, coluna de status Ativo/Inativo) e `form` (inclusão e edição na mesma view);
  - ações `salvar` e `alternar_ativo`, ambas POST + CSRF + confirmação;
  - fluxo: o controller chama um service (`modules/admin_<entidade>_service.py`), que valida, chama o repositório e audita (`CAD_INSERIR`, `CAD_ALTERAR`, `CAD_DESATIVAR`) na **mesma** operação de repositório;
  - erros: `RepoViolacao` vira mensagem em português no campo correspondente (por exemplo, "Já existe um ambiente com este nome."); `RepoConflito` vira "O registro foi alterado por outra pessoa. Recarregue a página.";
  - **controle de concorrência na edição:** o formulário carrega uma versão (hash dos campos editáveis no momento da leitura, calculado no servidor). Na hora de salvar, o service compara com o estado atual e, se divergir, gera `RepoConflito`. Esse mecanismo dispensa coluna nova no banco.
  - **auditoria** do `detalhe` com os campos alterados no formato `campo: antigo → novo`, sempre mascarando valores que pareçam credencial.
- **`applications/script_scheduling_service/modules/admin_ambientes_service.py`:**
  - `nome` validado com a regra da CK `ck_tbsss_amb_nome` (maiúsculas, dígitos e `_`) e **imutável** depois de criado (o campo fica somente leitura na edição e o servidor ignora qualquer valor enviado).
  - `conexao`: aceita apenas DSN, no formato Easy Connect `host:porta/servico` (`^[A-Za-z0-9._-]+:[0-9]{1,5}/[A-Za-z0-9._-]+$`) ou alias TNS (`^[A-Za-z0-9._-]{1,128}$`). Um `@` (padrão de credencial) é rejeitado com a mensagem "Informe apenas o DSN; credenciais ficam no secrets.cfg."
  - `descricao` opcional.
  - Desativação conforme a política do README §10: a UI mostra o aviso "Agendamentos que usam este ambiente serão pausados no próximo ciclo." e a quantidade de agendamentos ativos afetados.
- **`applications/script_scheduling_service/controllers/admin_ambientes.py`:** `lista`, `form`, `salvar` e `alternar_ativo`, todos com `_exigir_func('CAD_AMBIENTES')`.
- **Views:** `views/admin_ambientes/lista.html` e `form.html`, usando os componentes do F1.2.
- **Menu:** item "Ambientes" na seção ADMIN (`ui_menu`).
- **`applications/script_scheduling_service/scripts/test_admin_ambientes_service.py`** (FAKE):
  - inclusão;
  - nome duplicado;
  - nome inválido;
  - DSN com `@`;
  - tentativa de alterar o nome ignorada;
  - edição concorrente gerando conflito;
  - desativação com contagem de agendamentos;
  - auditoria.

**OUT**
- Sem gestão de credenciais pela UI (elas ficam no `secrets.cfg`).

## Requisitos
1. Nenhuma credencial em tela, log ou auditoria.
2. Os services ficam em `modules/` e são testáveis sem `gluon` (recebem `ctx` e `ip` como parâmetros).

## Critérios de aceite
- [ ] O CRUD completo funciona com `admin`. `op.prod` recebe 403.
- [ ] Um DSN com `usuario/senha@host` é rejeitado com a mensagem orientativa.
- [ ] Duas abas editando o mesmo ambiente: a segunda a salvar recebe a mensagem de conflito.
- [ ] `docs/PADRAO_CRUD_ADMIN.md` existe e os testes passam.

## Verificação
- **Browser:** fluxo completo, conflito com duas abas e acesso com perfil sem permissão.
- Testes: `python -m unittest discover -s scripts -p "test_admin_ambientes_service.py"`

## Saída
Relatório AGENTS.md §9.
