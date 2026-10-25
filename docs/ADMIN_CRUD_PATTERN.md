# Padrão de CRUD administrativo

Este padrão foi definido no F4.1 (ambientes) e vale para todos os cadastros do F4.2 ao F4.5. A referência de implementação está em:

* `controllers/admin_environments.py`
* `modules/admin_environments_service.py`
* `modules/admin_crud.py`
* `views/admin_environments/`

As regras de negócio estão no README §4.4 e §10 (padrões globais e tabela 1).

## Camadas

| Camada | Arquivo | Responsabilidade |
|---|---|---|
| Controller | `controllers/admin_<entidade>.py` | Aplica o guarda `_require_func('<FUNC>')`, restringe o método HTTP, lê `request.vars` com um teto defensivo por campo (sempre **acima** do limite do campo, para que o service veja o excesso e o recuse; nada é cortado sem aviso), chama o service, define o flash e renderiza ou redireciona. Não contém regra de negócio. |
| Service | `modules/admin_<entity>_service.py` | Não importa `gluon` e recebe `ctx` e `ip` como parâmetros. Reconfirma a funcionalidade com `admin_crud.require_feature`, valida os campos, calcula a versão e o detalhe de auditoria e chama o repositório. O serviço padrão do processo é obtido sob demanda (`_servico()`). |
| Base comum | `modules/admin_crud.py` | Fornece `version` (com `sensiveis=`), `esperado`, `texto`, `identificador`, `free_text`, `changes_detail`, `insert_detail`, `free_detail`, `auditoria`, `AccessDenied`, `OperationDenied` e as mensagens padrão (`MSG_CONFLICT` vem de `ui_helpers.MESSAGES`). |
| Repositório | `repo_<agregado>` | A inclusão e a alteração recebem `audit=` e gravam a linha de `tbsss_audit` na **mesma** operação. A alteração recebe `esperado=` e faz um `UPDATE` condicional. O ator da auditoria também preenche as colunas de registro (`created_*` na inclusão, `updated_*` na alteração; CR-006, README §10); sem ator, a gravação é recusada. |

## Telas e ações

| Ação | Método | Comportamento |
|---|---|---|
| `index` | GET | Filtros com `components/filters.html`, tabela com `components/table.html` (colunas `active` e `action`) e paginação com `components/pagination.html`. Ordenação definida pelo repositório. O `total` vem limitado a 10.001: acima de 10.000, a paginação mostra "mais de 10.000 registros" e não oferece "Última" (CR-007, R-29). |
| `form[/id]` | GET | Uma única view para inclusão (sem id) e edição. Campos com `components/form_field.html`. Na edição, a chave natural fica `read_only` e o servidor ignora o valor enviado. Também na edição, o quadro **Registro** (`components/record.html`, CR-006) mostra quem criou o registro e quando, e a última alteração ("Nunca alterado" enquanto `updated_at` for nulo). O service entrega `created_at`, `created_by`, `updated_at` e `updated_by` no dicionário do `formulario()`, por `ui_helpers.record_info(rec, ctx)`: o login do ator só vai para quem tem `VIEW_AUDIT` ou é administrador; os demais veem "você", "Sistema (…)" ou "outra pessoa" (CR-007, D6). |
| `salvar` | POST + CSRF | Em caso de sucesso, grava o flash e redireciona para a `lista`. A exceção é o cadastro de scripts, que volta ao `form` para mostrar avisos e atalhos (README §8.5). Em caso de erro, responde **200**, reapresenta o que foi digitado e destaca os campos. O primeiro campo inválido recebe `autofocus`. Valor acima do limite ou fora do formato é recusado, nunca truncado (README §10, "Texto nos cadastros"). |
| `toggle_active` | POST + CSRF | O botão fica no **formulário de edição**, e não na lista, e abre `components/confirm_modal.html`. O modal diz a consequência e o impacto da ação: no ambiente, os agendamentos ativos afetados e a quantidade de scripts homologados nele; no perfil, a quantidade e os logins dos usuários ativos afetados (README §4.3.B.1); no parâmetro vinculado a script ativo, a desativação é bloqueada e os scripts são listados. Depois redireciona de volta para o `form`. |

As entidades mestras nunca são excluídas, apenas desativadas (README §10).

## Texto dos campos (CR-003)

| Tipo de campo | Função | Regra |
|---|---|---|
| **Identificador** (nome de ambiente, de perfil, login, código de parâmetro) | `admin_crud.identifier` | **Não** é limpo: espaço no início ou no fim é recusado com "Não use espaços no início nem no fim.". O formato (maiúsculas, dígitos, `_` etc.) é validado depois |
| **Texto livre** (nome de usuário e de script, `label`, `description`, `script_group`, `category`, `stage`) | `admin_crud.free_text` | Recebe `strip()` antes da validação e recusa caracteres de controle (`\x00-\x1f`, `\x7f`) com mensagem própria |
| Qualquer campo | — | Acima do limite, é **recusado** com o tamanho máximo na mensagem; nunca é truncado (README §10, AGENTS §3.4). Só o `detail` da auditoria, que é gerado pelo sistema, é cortado em 1.000 caracteres com `...` |

## Concorrência na edição (sem coluna nova)

1. O `form` envia em campo oculto a `version`: o sha256 dos campos editáveis (`active` incluído) no momento da leitura. As colunas de registro (CR-006) não entram na versão nem no `esperado`. Campo sensível entra no hash como marcador fixo (`<sensitive:preenchido>` ou `<sensitive:vazio>`), nunca pelo valor. Uma troca concorrente feita só no valor sensível não gera conflito (README §10, "Consequência aceita").
2. O `save` ou o `toggle_active` do service relê o registro. Se a `version` enviada for diferente da atual, o resultado é conflito.
3. O service repassa os valores lidos como `esperado=`. O repositório executa `UPDATE ... WHERE id = :id AND <coluna = valor lido ...>` e checa o `rowcount`. No ORACLE, cada comparação é nula-segura na forma ANSI `(c = :v OR (c IS NULL AND :v IS NULL))` (README §10). Se o `rowcount` for 0, o repositório lança `RepoConflict` e não altera nada. Com isso, não sobra janela entre a leitura e a escrita.
4. Mensagem exibida (README §2.4.2): "Outra pessoa mudou este registro enquanto você editava. Recarregue a página para ver a versão nova e faça a sua alteração de novo." O formulário volta com os dados atuais e uma nova versão.

## Erros

| Origem | Apresentação |
|---|---|
| Validação do service | Mensagem em português no campo (`errors['<campo>']`), e no topo a mensagem-padrão em duas partes: "Alguns campos precisam de correção. Os campos estão marcados em vermelho, com a explicação embaixo de cada um." (README §2.4.2) |
| `RepoViolation` | Mapeada por `constraint` para o campo. Exemplo: `uk_tbsss_env_name` vira "Já existe um ambiente com este nome." |
| `RepoConflict` | `errors['_geral']`, com a mensagem de conflito |
| Outra `RepoError` | `errors['_geral']` com "Não foi possível salvar...". O detalhe técnico (ORA-, SQL, traceback) vai só para o log. |
| Regra de negócio (ex.: último administrador, desativar o próprio usuário, tirar o próprio perfil de administrador) | `RepoViolation` com constraint de aplicação (`sss_*`), traduzida para `errors['_geral']` ou `OperationDenied(message)`, que o controller exibe no flash |
| Sem funcionalidade | 403 no controller (guarda) e `AccessDenied` no service |
| ID inexistente ou inválido | 404 |

## Auditoria

| Situação | Ação | Detalhe |
|---|---|---|
| Inclusão | `CREATE` | `campo: valor` somente dos campos preenchidos (vazios omitidos), com todos os campos do formulário e referências pelo nome (ex.: `perfil: OPERATOR_PROD`) |
| Alteração | `UPDATE` | `campo: antigo → novo`, só dos campos que mudaram. Se nada mudou, nada é gravado nem auditado. |
| Desativação | `DEACTIVATE` | `ativo: S → N` mais o impacto (por exemplo, `agendamentos ativos afetados: 2`) |
| Reativação | `UPDATE` | `ativo: N → S` |

O detalhe passa sempre pelo `masking` (segredos registrados e senha em connect string), inclusive em vínculos, homologação e matriz, e é limitado a 1.000 caracteres (`VARCHAR2(1000 CHAR)`). A linha é gravada pelo repositório, na mesma operação da ação.

## Testes mínimos por cadastro

`scripts/test_admin_<entity>_service.py`, sobre o FAKE, cobre:
* inclusão;
* chave duplicada;
* campos inválidos, inclusive espaços em volta de identificador e caractere de controle em texto livre;
* valor acima do limite recusado, sem truncar;
* chave natural imutável;
* edição concorrente, tanto pela versão quanto pelo `esperado` entre a leitura e a escrita;
* desativação com impacto;
* auditoria;
* colunas de registro: `created_*` com o ator na inclusão, `updated_*` nulos até a primeira alteração e preenchidos com o ator depois dela, inclusive na desativação (CR-006);
* perfil sem a funcionalidade.

Se o contrato do repositório mudar, o caso correspondente entra em `test_repo_contract.py`.
