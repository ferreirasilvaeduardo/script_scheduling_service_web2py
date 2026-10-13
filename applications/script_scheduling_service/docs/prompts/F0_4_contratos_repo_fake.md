# SSS — Prompt F0.4: Contratos de repositório e backend FAKE

## Leitura obrigatória antes de planejar
- `AGENTS.md` §4.9–4.11, §5.5, §7
- `README.md` §2.5, §4.3, §4.4, §5.1, §5.2, §5.4–5.6, §7.5 (passos 6 e 7), §10 (inteiro, incluindo a política de exclusão)

## Objetivo
Definir os contratos de persistência que toda a UI vai consumir e implementá-los em memória com paridade de semântica com o Oracle, mais um seed determinístico.

## Escopo
**IN**
- `applications/script_scheduling_service/modules/repo_errors.py`: `RepoErro`, `RepoNaoEncontrado`, `RepoConflito`, `RepoViolacao(constraint)` e `RepoIndisponivel`.
- **Contratos** (classes com métodos que lançam `NotImplementedError`, docstring curta e retorno em `dict` simples ou lista de `dict`, com chaves iguais aos nomes de coluna):
  - `repo_usuarios.py`:
    - `obter_por_login`, `obter_por_id`, `obter_estado_sessao(usuario_id)` (usuário + perfil + `perm_versao`);
    - `listar(filtros, pagina, tamanho)`, `inserir`, `alterar`;
    - `registrar_falha_login`, `registrar_sucesso_login`, `desbloquear`, `definir_senha`.
  - `repo_rbac.py`:
    - `perfis_listar/obter/inserir/alterar`;
    - `matriz_obter(perfil_id)` e `matriz_salvar(perfil_id, funcs, ambs, scrs)`, que incrementa `perm_versao` **atomicamente**;
    - `admins_ativos_bloquear()`, a semântica do README §4.3.B, que devolve os IDs;
    - `funcionalidades_listar`.
  - `repo_catalogo.py`:
    - ambientes (listar, obter, inserir, alterar);
    - scripts (listar, obter, inserir, alterar);
    - `homologacao_obter` e `homologacao_salvar`;
    - parâmetros (listar, obter, inserir, alterar);
    - `parametro_vinculos(parametro_id)`;
    - `script_params_obter(script_id)` (ordem, com dados do parâmetro) e `script_params_salvar(script_id, vinculos)`;
    - `scripts_executaveis(usuario_ctx)`, a lista já filtrada pela §4.3.A.
  - `repo_tickets.py`:
    - `criar(ticket, respostas) -> id`, numa transação única;
    - `obter(id)`, `listar(filtros, pagina, tamanho, escopo_ambientes)`, `respostas(ticket_id)`;
    - `solicitar_cancelamento(id) -> 'TERMINAL'|'CANCELADO'|'SINALIZADO'` (README §5.6, parte web);
    - `log_ler(id, offset, max_chars) -> (texto, novo_offset, terminal, truncado)`.
  - `repo_agendamentos.py`: `listar`, `obter`, `inserir`, `alterar` (com `usuario_id` do editor), `pausar(id, motivo, antiga_data)`, `retomar(id, nova_data)` e `ticket_status(ticket_id)`.
  - `repo_auditoria.py`: `registrar(ator, ip, acao, entidade, entidade_id, detalhe)` e `listar(filtros, pagina, tamanho)`.
  - `repo_agentes.py`: `listar()` e `tickets_running(codigo)`.
  - **Paginação de todos os `listar`:** retorna `{'itens': [...], 'total': n, 'pagina': p, 'tamanho': t}`, com ordenação determinística (desempate por `id`).
- `applications/script_scheduling_service/modules/repo_factory.py`:
  - `obter(nome)` devolve um singleton por processo para o backend do config;
  - FAKE fora de DEV gera `RuntimeError` (README §2.5);
  - ORACLE ainda não implementado gera `NotImplementedError` com mensagem clara.
- `applications/script_scheduling_service/modules/repo_fake/*.py` com a implementação em memória.
  - **Locks:** `threading.Lock` por agregado (o servidor web é multithread).
  - **Paridade de semântica:**
    - unicidade de UKs (`RepoViolacao`);
    - CKs relevantes (flags, enums, `ck_tbsss_amb_conexao`, `ck_tbsss_scr_cmd`, `ck_tbsss_scr_path`);
    - imutabilidade de `ambientes.nome` e `usuarios.login`;
    - cascatas das associações;
    - política de exclusão;
    - transições de status condicionais com `RepoConflito` (README §5.1);
    - `perm_versao` incrementado em toda alteração de perfil/matriz/admin/ativo;
    - auditoria gravada **dentro** do mesmo lock da ação.
  - **Datas:** `datetime` sem microssegundos, com relógio injetável (`relogio=callable`) para os testes.
- `applications/script_scheduling_service/modules/repo_fake/seed.py` (determinístico, sem aleatoriedade):
  - **Ambientes:** `PRODUCAO`, `HOMOLOGACAO`, `DESENV` (este inativo). DSN fictício `db-<nome>.local:1521/svc`.
  - **Perfis:** `ADMINISTRADOR` (admin), `OPERADOR_PROD`, `OPERADOR_HML`, `CONSULTA`. As matrizes devem ser coerentes com o catálogo do README §4.3.D.
  - **Usuários:** `admin`, `op.prod`, `op.hml`, `consulta`, `inativo` e `bloqueado`. Use `senha_hash = '!'` (login impossível). As senhas são definidas no F2.2.
  - **Scripts (6):** cobrindo `NOMEADO`, `SEQUENCIAL` e `NENHUM`; os três interpretadores; um inativo; um com `max_qtd_parallel_env = 2`; homologações distintas por ambiente. `path_file` aponta para arquivos que o F3.1 criará em `applications/script_scheduling_service/dev/scripts/`.
  - **Parâmetros (10):** todos os `tipo_componente`, um `sensivel = 'S'`, um com regex, um `SELECT` com `opcoes_json`, flags longas e curtas.
  - **Tickets (40):** distribuídos entre os 5 status e os motivos do README §5.2, com datas relativas ao relógio, 2 com `parent_ticket_id`, 5 vindos de agendamento, `parametros_enviados` com JSON no formato do README §6.5 e `log_output` curto.
  - **Agendamentos (5):** um de cada `tipo_recorrencia`, um pausado com `pausa_motivo`.
  - **Agentes (2)** e **auditoria (30 linhas).**
- `applications/script_scheduling_service/scripts/test_repo_contract.py`: bateria parametrizada por backend, rodando FAKE sempre e ORACLE só com `SSS_TEST_DSN` (skip). Cobre:
  - CRUD;
  - UK duplicada;
  - CK de conexão com `@`;
  - imutabilidade;
  - cascata de associação;
  - `solicitar_cancelamento` nos 3 retornos;
  - transição concorrente perdida gerando `RepoConflito`;
  - `perm_versao` incrementando;
  - paginação estável;
  - escopo de ambientes na listagem de tickets.

**OUT**
- Sem UI, sem hash de senha (isso é o F2.1) e sem lógica de RBAC de decisão (isso é o F2.2). O `scripts_executaveis` consome o `rbac` no F2.2; aqui ele recebe o contexto já resolvido.

## Requisitos
1. É proibido o FAKE expor método fora do contrato (AGENTS §5.5).
2. O retorno nunca vaza referência mutável interna: o FAKE devolve cópias (`copy.deepcopy`).
3. O seed é idempotente e carregado uma vez por processo.

## Critérios de aceite
- [ ] `test_repo_contract.py` passa com FAKE, e ORACLE aparece como `skipped`.
- [ ] `repo_factory` com `sss_env=HML` e `data_backend=FAKE` lança erro.
- [ ] Nenhum `import repo_fake` fora de `repo_factory.py` (verificado por grep no teste).

## Verificação
`python -m unittest discover -s scripts -p "test_repo_contract.py" -v`

## Regras de parada
Se algum método necessário às telas das fases 3–6 não puder ser derivado do README, **pare** e liste-o, em vez de inventar a assinatura.

## Saída
Relatório AGENTS.md §9.
