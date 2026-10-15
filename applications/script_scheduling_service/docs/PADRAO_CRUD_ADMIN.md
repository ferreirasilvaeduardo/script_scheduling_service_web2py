# Padrão de CRUD administrativo

Este padrão foi definido no F4.1 (ambientes) e vale para todos os cadastros do F4.2 ao F4.5. A referência de implementação está em:

* `controllers/admin_ambientes.py`
* `modules/admin_ambientes_service.py`
* `modules/admin_crud.py`
* `views/admin_ambientes/`

As regras de negócio estão no README §4.4 e §10 (padrões globais e tabela 1).

## Camadas

| Camada | Arquivo | Responsabilidade |
|---|---|---|
| Controller | `controllers/admin_<entidade>.py` | Aplica o guarda `_exigir_func('<FUNC>')`, restringe o método HTTP, lê e trunca `request.vars`, chama o service, define o flash e renderiza ou redireciona. Não contém regra de negócio. |
| Service | `modules/admin_<entidade>_service.py` | Não importa `gluon` e recebe `ctx` e `ip` como parâmetros. Reconfirma a funcionalidade com `admin_crud.exigir_func`, valida os campos, calcula a versão e o detalhe de auditoria e chama o repositório. O serviço padrão do processo é obtido sob demanda (`_servico()`). |
| Base comum | `modules/admin_crud.py` | Fornece `versao`, `esperado`, `detalhe_alteracoes`, `detalhe_insercao`, `auditoria`, `texto`, `AcessoNegado` e as mensagens padrão. |
| Repositório | `repo_<agregado>` | A inclusão e a alteração recebem `auditoria=` e gravam a linha de `tbsss_auditoria` na **mesma** operação. A alteração recebe `esperado=` e faz um `UPDATE` condicional. |

## Telas e ações

| Ação | Método | Comportamento |
|---|---|---|
| `lista` | GET | Filtros com `components/filtros.html`, tabela com `components/tabela.html` (colunas `ativo` e `acao`) e paginação com `components/paginacao.html`. Ordenação definida pelo repositório. |
| `form[/id]` | GET | Uma única view para inclusão (sem id) e edição. Campos com `components/form_campo.html`. Na edição, a chave natural fica `somente_leitura` e o servidor ignora o valor enviado. |
| `salvar` | POST + CSRF | Em caso de sucesso, grava o flash e redireciona para a `lista`. Em caso de erro, responde **200**, reapresenta o que foi digitado e destaca os campos. O primeiro campo inválido recebe `autofocus`. |
| `alternar_ativo` | POST + CSRF | O botão fica no **formulário de edição**, e não na lista, e abre `components/modal_confirmacao.html`. O modal mostra o impacto da ação (por exemplo, a quantidade de agendamentos ativos afetados). Depois redireciona de volta para o `form`. |

As entidades mestras nunca são excluídas, apenas desativadas (README §10).

## Concorrência na edição (sem coluna nova)

1. O `form` envia em campo oculto a `versao`: o sha256 dos campos editáveis (`ativo` incluído) no momento da leitura.
2. O `salvar` ou o `alternar_ativo` relê o registro. Se a `versao` enviada for diferente da atual, o resultado é conflito.
3. O service repassa os valores lidos como `esperado=`. O repositório executa `UPDATE ... WHERE id = :id AND <coluna = valor lido ...>` e checa o `rowcount`. No ORACLE, as comparações são nulas-seguras, com `DECODE`. Se o `rowcount` for 0, o repositório lança `RepoConflito` e não altera nada. Com isso, não sobra janela entre a leitura e a escrita.
4. Mensagem exibida: "O registro foi alterado por outra pessoa. Recarregue a página." O formulário volta com os dados atuais e uma nova versão.

## Erros

| Origem | Apresentação |
|---|---|
| Validação do service | Mensagem em português no campo (`erros['<campo>']`) |
| `RepoViolacao` | Mapeada por `constraint` para o campo. Exemplo: `uk_tbsss_amb_nome` vira "Já existe um ambiente com este nome." |
| `RepoConflito` | `erros['_geral']`, com a mensagem de conflito |
| Outra `RepoErro` | `erros['_geral']` com "Não foi possível salvar...". O detalhe técnico (ORA-, SQL, traceback) vai só para o log. |
| Regra de negócio (ex.: último administrador) | `RepoViolacao` com constraint de aplicação (`sss_*`), traduzida para `erros['_geral']` ou `OperacaoNegada(mensagem)`, que o controller exibe no flash |
| Sem funcionalidade | 403 no controller (guarda) e `AcessoNegado` no service |
| ID inexistente ou inválido | 404 |

## Auditoria

| Situação | Ação | Detalhe |
|---|---|---|
| Inclusão | `CAD_INSERIR` | `campo: valor` dos campos informados |
| Alteração | `CAD_ALTERAR` | `campo: antigo → novo`, só dos campos que mudaram. Se nada mudou, nada é gravado nem auditado. |
| Desativação | `CAD_DESATIVAR` | `ativo: S → N` mais o impacto (por exemplo, `agendamentos ativos afetados: 2`) |
| Reativação | `CAD_ALTERAR` | `ativo: N → S` |

O detalhe passa sempre pelo `masking` (segredos registrados e senha em connect string) e é limitado a 1.000 caracteres (`VARCHAR2(1000 CHAR)`).

## Testes mínimos por cadastro

`scripts/test_admin_<entidade>_service.py`, sobre o FAKE, cobre:
* inclusão;
* chave duplicada;
* campos inválidos;
* chave natural imutável;
* edição concorrente, tanto pela versão quanto pelo `esperado` entre a leitura e a escrita;
* desativação com impacto;
* auditoria;
* perfil sem a funcionalidade.

Se o contrato do repositório mudar, o caso correspondente entra em `test_repo_contract.py`.
