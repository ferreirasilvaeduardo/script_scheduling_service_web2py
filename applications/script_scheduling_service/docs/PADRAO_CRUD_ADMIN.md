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
| Controller | `controllers/admin_<entidade>.py` | Aplica o guarda `_exigir_func('<FUNC>')`, restringe o método HTTP, lê `request.vars` com um teto defensivo por campo (sempre **acima** do limite do campo, para que o service veja o excesso e o recuse; nada é cortado sem aviso), chama o service, define o flash e renderiza ou redireciona. Não contém regra de negócio. |
| Service | `modules/admin_<entidade>_service.py` | Não importa `gluon` e recebe `ctx` e `ip` como parâmetros. Reconfirma a funcionalidade com `admin_crud.exigir_func`, valida os campos, calcula a versão e o detalhe de auditoria e chama o repositório. O serviço padrão do processo é obtido sob demanda (`_servico()`). |
| Base comum | `modules/admin_crud.py` | Fornece `versao` (com `sensiveis=`), `esperado`, `texto`, `identificador`, `texto_livre`, `detalhe_alteracoes`, `detalhe_insercao`, `detalhe_livre`, `auditoria`, `AcessoNegado`, `OperacaoNegada` e as mensagens padrão (`MSG_CONFLITO` vem de `ui_helpers.MENSAGENS`). |
| Repositório | `repo_<agregado>` | A inclusão e a alteração recebem `auditoria=` e gravam a linha de `tbsss_auditoria` na **mesma** operação. A alteração recebe `esperado=` e faz um `UPDATE` condicional. |

## Telas e ações

| Ação | Método | Comportamento |
|---|---|---|
| `lista` | GET | Filtros com `components/filtros.html`, tabela com `components/tabela.html` (colunas `ativo` e `acao`) e paginação com `components/paginacao.html`. Ordenação definida pelo repositório. |
| `form[/id]` | GET | Uma única view para inclusão (sem id) e edição. Campos com `components/form_campo.html`. Na edição, a chave natural fica `somente_leitura` e o servidor ignora o valor enviado. |
| `salvar` | POST + CSRF | Em caso de sucesso, grava o flash e redireciona para a `lista`. A exceção é o cadastro de scripts, que volta ao `form` para mostrar avisos e atalhos (README §8.5). Em caso de erro, responde **200**, reapresenta o que foi digitado e destaca os campos. O primeiro campo inválido recebe `autofocus`. Valor acima do limite ou fora do formato é recusado, nunca truncado (README §10, "Texto nos cadastros"). |
| `alternar_ativo` | POST + CSRF | O botão fica no **formulário de edição**, e não na lista, e abre `components/modal_confirmacao.html`. O modal diz a consequência e o impacto da ação: no ambiente, os agendamentos ativos afetados e a quantidade de scripts homologados nele; no perfil, a quantidade e os logins dos usuários ativos afetados (README §4.3.B); no parâmetro vinculado a script ativo, a desativação é bloqueada e os scripts são listados. Depois redireciona de volta para o `form`. |

As entidades mestras nunca são excluídas, apenas desativadas (README §10).

## Texto dos campos (CR-003)

| Tipo de campo | Função | Regra |
|---|---|---|
| **Identificador** (nome de ambiente, de perfil, login, código de parâmetro) | `admin_crud.identificador` | **Não** é limpo: espaço no início ou no fim é recusado com "Não use espaços no início nem no fim.". O formato (maiúsculas, dígitos, `_` etc.) é validado depois |
| **Texto livre** (nome de usuário e de script, `label`, `descricao`, `grupo`, `categoria`, `etapa`) | `admin_crud.texto_livre` | Recebe `strip()` antes da validação e recusa caracteres de controle (`\x00-\x1f`, `\x7f`) com mensagem própria |
| Qualquer campo | — | Acima do limite, é **recusado** com o tamanho máximo na mensagem; nunca é truncado (README §10, AGENTS §3.4). Só o `detalhe` da auditoria, que é gerado pelo sistema, é cortado em 1.000 caracteres com `...` |

## Concorrência na edição (sem coluna nova)

1. O `form` envia em campo oculto a `versao`: o sha256 dos campos editáveis (`ativo` incluído) no momento da leitura. Campo sensível entra no hash como marcador fixo (`<sensivel:preenchido>` ou `<sensivel:vazio>`), nunca pelo valor. Uma troca concorrente feita só no valor sensível não gera conflito (README §10, "Consequência aceita").
2. O `salvar` ou o `alternar_ativo` relê o registro. Se a `versao` enviada for diferente da atual, o resultado é conflito.
3. O service repassa os valores lidos como `esperado=`. O repositório executa `UPDATE ... WHERE id = :id AND <coluna = valor lido ...>` e checa o `rowcount`. No ORACLE, as comparações são nulas-seguras, com `DECODE`. Se o `rowcount` for 0, o repositório lança `RepoConflito` e não altera nada. Com isso, não sobra janela entre a leitura e a escrita.
4. Mensagem exibida (README §2.4.2): "Outra pessoa mudou este registro enquanto você editava. Recarregue a página para ver a versão nova e faça a sua alteração de novo." O formulário volta com os dados atuais e uma nova versão.

## Erros

| Origem | Apresentação |
|---|---|
| Validação do service | Mensagem em português no campo (`erros['<campo>']`), e no topo a mensagem-padrão em duas partes: "Alguns campos precisam de correção. Os campos estão marcados em vermelho, com a explicação embaixo de cada um." (README §2.4.2) |
| `RepoViolacao` | Mapeada por `constraint` para o campo. Exemplo: `uk_tbsss_amb_nome` vira "Já existe um ambiente com este nome." |
| `RepoConflito` | `erros['_geral']`, com a mensagem de conflito |
| Outra `RepoErro` | `erros['_geral']` com "Não foi possível salvar...". O detalhe técnico (ORA-, SQL, traceback) vai só para o log. |
| Regra de negócio (ex.: último administrador, desativar o próprio usuário, tirar o próprio perfil de administrador) | `RepoViolacao` com constraint de aplicação (`sss_*`), traduzida para `erros['_geral']` ou `OperacaoNegada(mensagem)`, que o controller exibe no flash |
| Sem funcionalidade | 403 no controller (guarda) e `AcessoNegado` no service |
| ID inexistente ou inválido | 404 |

## Auditoria

| Situação | Ação | Detalhe |
|---|---|---|
| Inclusão | `CAD_INSERIR` | `campo: valor` somente dos campos preenchidos (vazios omitidos), com todos os campos do formulário e referências pelo nome (ex.: `perfil: OPERADOR_PROD`) |
| Alteração | `CAD_ALTERAR` | `campo: antigo → novo`, só dos campos que mudaram. Se nada mudou, nada é gravado nem auditado. |
| Desativação | `CAD_DESATIVAR` | `ativo: S → N` mais o impacto (por exemplo, `agendamentos ativos afetados: 2`) |
| Reativação | `CAD_ALTERAR` | `ativo: N → S` |

O detalhe passa sempre pelo `masking` (segredos registrados e senha em connect string), inclusive em vínculos, homologação e matriz, e é limitado a 1.000 caracteres (`VARCHAR2(1000 CHAR)`). A linha é gravada pelo repositório, na mesma operação da ação.

## Testes mínimos por cadastro

`scripts/test_admin_<entidade>_service.py`, sobre o FAKE, cobre:
* inclusão;
* chave duplicada;
* campos inválidos, inclusive espaços em volta de identificador e caractere de controle em texto livre;
* valor acima do limite recusado, sem truncar;
* chave natural imutável;
* edição concorrente, tanto pela versão quanto pelo `esperado` entre a leitura e a escrita;
* desativação com impacto;
* auditoria;
* perfil sem a funcionalidade.

Se o contrato do repositório mudar, o caso correspondente entra em `test_repo_contract.py`.
