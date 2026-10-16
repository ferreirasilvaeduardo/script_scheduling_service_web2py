# SSS — Prompt F7.3: Repositórios Oracle — AGREGADO = `<<PREENCHER>>`

> **Execute este prompt 5 vezes, uma por conversa**, trocando o AGREGADO nesta ordem:
> 1. `RBAC_USUARIOS` → `repo_usuarios`, `repo_rbac`
> 2. `CATALOGO` → `repo_catalogo`
> 3. `TICKETS` → `repo_tickets`
> 4. `AGENDAMENTOS` → `repo_agendamentos`
> 5. `AUDITORIA_AGENTES` → `repo_auditoria`, `repo_agentes`
>
> Faça commit entre uma execução e outra.

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.1, §4 (inteiro)
- `docs/arquitetura/CR-003-correcoes-pos-analise.md` (inteiro: D6, D9, D11, D12, D16, C3, C4, C9 e a rastreabilidade) e `docs/arquitetura/CR-004-telas-de-consulta-e-linguagem-clara.md` ("Contrato": as duas leituras novas de `RepoTickets`)
- `README.md` §2.5 (paridade: FKs, NOT NULL, limites, maiúsculas e cascatas), §2.7, §4.2 ("Proteções do login" e "Relógio do banco"), §4.3.A (`perm_versao`), §4.3.B, §4.4 (inteiro: tabela de entidade por ação, limites e "Quantidade registrada"), §5 (inteiro, em especial §5.6 e §5.8), §7.5 ("Bind de datas"), §7.6, §8.2, §8.3 (ordem de locks), §8.5 ("Pastas base" e "CKs de banco"), §8.10 ("UI `VER_LOGS`"), §10 (tabelas do agregado), §10 (política de exclusão e texto nos cadastros)
- Arquivos: o contrato `modules/repo_<x>.py` do agregado, a implementação `modules/repo_fake/<x>.py` (e `repo_fake/store.py`, que emula FKs e limites), `modules/db_conn.py` (`definir_tipos_entrada`, `agora_banco`, `proximo_id`), `modules/sql_ident.py` e `scripts/test_repo_contract.py` (inclusive `test_06b_fks_e_limites_de_auditoria`)

## Objetivo
Implementar o contrato do agregado em `modules/repo_oracle/` com SQL Oracle 11gR2 escrito diretamente (CR-002, sem camada de dialeto), com paridade comprovada pela mesma bateria de testes do FAKE, em cada combinação de driver disponível (Thin com banco 12.1+, Thick e cx_Oracle).

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/repo_oracle/<agregado>.py`:**
  - **SQL estático** em constantes no topo do módulo, montado **uma vez** na carga a partir de `sql_ident.qualificar(owner, nome)`. Nenhuma formatação de valores, somente binds.
  - **Paginação** pelo padrão `ROWNUM` do AGENTS §4.4, com `total` via `COUNT(*)` na mesma transação de leitura e ordenação idêntica à do FAKE, com desempate por `id`.
  - **Filtros dinâmicos:** combinação de cláusulas **fixas** escolhidas por allowlist (`AND status IN (:s0, :s1)`, com placeholders gerados por contagem). Nunca concatene valores.
  - **Transições de status** com `UPDATE` condicional e `rowcount`, traduzindo `rowcount = 0` em `RepoConflito` conforme o contrato.
  - **Inserção com ID:** `INSERT ... RETURNING id INTO :out_id`, com variável de saída do driver. Para lotes, `executemany`.
  - **Datas (README §7.5, "Bind de datas"):** todo bind comparado ou gravado em coluna `DATE` é declarado como `TIPO_DATE` via `db_conn.definir_tipos_entrada` (`setinputsizes`), inclusive o `proxima_execucao = :antiga_data` otimista e os campos do `esperado`. A leitura de `DATE` vem sem microssegundos. O "agora" é sempre o `SYSDATE` do banco (`db_conn.agora_banco`), nunca o relógio do nó.
  - **IDs:** a aplicação sempre informa o `id` (`db_conn.proximo_id`, `seq.NEXTVAL` antes do `INSERT`, README §2.7); a trigger condicional fica só como defesa.
  - **CLOB:**
    - escrita de `parametros_enviados` como bind CLOB;
    - `log_ler` lê por locator com `lob.read(offset + 1, amount)`: o offset da API web conta caracteres a partir de 0, e o LOB do Oracle começa em 1 (README §8.10, "UI `VER_LOGS`"). Cada leitura devolve até 65.536 caracteres. O retorno `(texto, novo_offset, terminal, truncado)` usa o offset em base 0, coerente com o FAKE (offset negativo vira 0; `max_chars < 1` vira 65.536);
    - listagens **nunca** selecionam colunas CLOB.
  - **Erros:** `db_conn.classificar_erro` traduz o ORA-00001 para `RepoViolacao(constraint)` (extraindo o nome da constraint da mensagem), o ORA-02291/02292 para `RepoViolacao` **com o nome da FK** (o FAKE já devolve `constraint`, README §2.5), o ORA-02290 para `RepoViolacao` com o nome da CK, o ORA-01400 (NOT NULL) e o ORA-12899 (valor maior que a coluna) para `RepoViolacao`, o ORA-20001 (imutável) para `RepoViolacao` e as falhas de rede para `RepoIndisponivel`. O repositório **nunca** trunca valores: a validação estrita fica no service (D11, README §7.6 e §10 "Texto nos cadastros").
  - **Pontos específicos por agregado:**
    - `RBAC_USUARIOS`:
      - `admins_ativos_bloquear` com o SQL do README §4.3.B **literal** (`FOR UPDATE OF u.ativo WAIT 5`), executado na mesma transação que a alteração; `matriz_salvar` com `DELETE` + `executemany INSERT` e `UPDATE perm_versao = perm_versao + 1` em uma transação; `obter_estado_sessao` com uma query por PK (join usuário + perfil).
      - `RepoUsuarios.agora()`: `SELECT SYSDATE FROM DUAL` via `db_conn.agora_banco` (README §4.2, "Relógio do banco").
      - `registrar_falha_login(login, bloqueio_s=None, auditoria=...)`: numa **única** transação, `tentativas_falha = tentativas_falha + 1` e, quando `bloqueio_s` for informado, `bloqueado_ate = SYSDATE + :bloqueio_s/86400`, mais a auditoria recebida (`dict` ou lista de `dict`: `LOGIN_FALHA` e, ao bloquear, `LOGIN_BLOQUEIO`; README §4.2 e §4.4). `tentativas_falha` é `NUMBER(2)` (máximo 99): o estouro (ORA-01438) vira `RepoViolacao(constraint='ck_tbsss_usr_tent')`, como no FAKE. Retorna o registro atualizado.
      - `registrar_sucesso_login(login, novo_hash=None, auditoria=...)`: numa **única** transação, `tentativas_falha = 0`, `bloqueado_ate = NULL`, `ultimo_login = SYSDATE`, `senha_hash = :novo_hash` só quando o rehash for informado, e a auditoria `LOGIN_OK`. Retorna o registro atualizado.
      - A auditoria do login usa `entidade = 'tbsss_usuarios'` e `entidade_id` = id do usuário (tabela do README §4.4), gravada pelo próprio repositório na mesma transação.
      - `alterar`: desativar o usuário ou trocar o perfil dele incrementa o `perm_versao` do perfil de **origem** e do de **destino** na mesma transação (README §4.3.A), além da proteção do último admin.
      - Autoproteção de perfis (D10) e remoção de associações inativas da matriz (D9) ficam no service; o repositório só grava o conjunto recebido.
    - `CATALOGO`:
      - `scripts_executaveis` com uma única query, com joins/`EXISTS` sobre `perfil_scr`, `perfil_amb` e `script_amb` e o atalho para admin; `parametro_vinculos` para o bloqueio de desativação.
      - `tbsss_scripts.pasta_base` (D16) em `scripts_inserir`, `scripts_alterar` (inclusive no `esperado`, com a comparação nula-segura), `scripts_obter` e `scripts_listar`. Violação de `ck_tbsss_scr_pasta` ou da `ck_tbsss_scr_path` endurecida (C4) vira `RepoViolacao` com o nome da CK.
      - A UK `uk_tbsss_scr_nome` diferencia maiúsculas de minúsculas (`Carga` ≠ `carga`, README §8.5): nenhuma comparação com `UPPER`/`LOWER` na checagem de unicidade.
      - O `detalhe` da auditoria de inclusão (só campos preenchidos, referências pelo nome, C9) e o `masking` dos vínculos são montados pelo service; o repositório só grava a linha recebida, na mesma transação.
      - FKs e UKs com os mesmos nomes e efeitos do FAKE (`RepoViolacao.constraint`).
    - `TICKETS`:
      - `criar` com o ticket mais as respostas (`executemany`) e auditoria em **uma** transação; FKs `fk_tbsss_tck_scr`, `fk_tbsss_tck_amb`, `fk_tbsss_tck_usr`, `fk_tbsss_trsp_prm` e a UK `uk_tbsss_trsp_tck_prm` com o nome da constraint, sem gravação parcial (como no `test_06b`).
      - `solicitar_cancelamento` com os dois `UPDATE`s do README §5.6 **literais** e o retorno `'TERMINAL' | 'CANCELADO' | 'SINALIZADO' | 'JA_SINALIZADO'`. **Toda** solicitação grava `TICKET_CANCELAR` na mesma transação, inclusive as sem efeito, com o `detalhe` `resultado: <cancelado | sinalizado | já sinalizado | sem efeito: ticket encerrado>` (README §5.6, C3). O primeiro `UPDATE` do README §5.6 já traz `AND cancel_requested = 'N'`; com `rowcount = 0`, a mesma transação lê a linha pela PK com `FOR UPDATE WAIT 5` e decide entre `TERMINAL` e `JA_SINALIZADO`, exatamente como o README descreve. Confirme que isso não altera a ordem de locks do §8.3 (só a linha do próprio ticket).
      - `log_ler` conforme o item CLOB acima (base 0 na API, `offset + 1` no LOB, até 65.536 caracteres).
      - **Leituras novas do CR-004** (README §5.8; adicionadas ao contrato e ao FAKE nos passos U5 e U7 do CR-004 — se não existirem no contrato quando este prompt rodar, **pare** e reporte):
        - `ultimas_execucoes(script_ids, escopo_ambientes=None, solicitante=None)` → `{script_id: {id, status, status_motivo, created_at, finished_at}}`, com o ticket mais recente (`created_at DESC, id DESC`) de cada script no escopo. Uma query com `ROW_NUMBER() OVER (PARTITION BY script_id ORDER BY created_at DESC, id DESC)` (sintaxe 11gR2), `script_id IN (:s0..:sN)` gerado por contagem, usando `ix_tbsss_tck_scr` e **sem** selecionar `log_output`. `escopo_ambientes` restringe por ambiente e `solicitante` restringe aos próprios tickets, com a mesma semântica do `listar` e do FAKE (§4.3.C).
        - `historico_script(script_id, desde, escopo_ambientes=None, solicitante=None, limite=5000)` → lista de `{id, status, status_motivo, created_at, started_at, finished_at}`, **sem** LOB, ordenada por `created_at`, com `created_at >= :desde` (bind `TIPO_DATE`; o service calcula `SYSDATE - 30`), o mesmo escopo e o limite pelo padrão `ROWNUM`. Quando houver mais que `limite`, devolva os mais recentes (a tela avisa "mostrando os 5.000 mais recentes", README §5.8).
      - A listagem com escopo de ambientes por bind.
    - `AGENDAMENTOS`:
      - `pausar` e `retomar` otimistas com `proxima_execucao = :antiga_data` (bind `TIPO_DATE`); `alterar` atualizando `usuario_id`.
      - FKs `fk_tbsss_agd_scr`, `fk_tbsss_agd_usr` e `fk_tbsss_agd_amb` com o nome da constraint (como no `test_06b`); `ck_tbsss_agd_campos` como no FAKE.
      - A validação estrita (sem truncamento, D11) já está no service (README §7.6); o repositório grava o que recebe e não corta nada.
    - `AUDITORIA_AGENTES`:
      - `reservar_id()`: `NEXTVAL` da sequence da auditoria via `db_conn.proximo_id` (README §2.7). `registrar(ator, ip, acao, entidade, entidade_id=None, detalhe=None, id=None)` usa o `id` recebido ou, se `None`, um `NEXTVAL` próprio.
      - `ator` é `NOT NULL` com até 40 caracteres e `detalhe` tem até 1.000 (README §4.4): valor nulo, vazio (no Oracle, `''` é `NULL`) ou longo demais vira `RepoViolacao` (ORA-01400/ORA-12899), sem valor padrão nem corte no repositório, como no `test_06b`.
      - A `entidade` de cada ação segue a tabela do README §4.4 (o service a informa; o filtro "Entidade" oferece exatamente aquelas tabelas).
      - Exportação (README §4.4, "Quantidade registrada"): o service obtém `id = reservar_id()`, usa `id_max = id − 1` para contar e para `iterar`, e só então grava a linha `AUD_EXPORTAR` com esse `id`. `listar` e `iterar` aceitam `id_max` (inclusivo); `iterar` é um cursor com `arraysize`, sem paginação por offset.
      - O filtro de período sempre por intervalo, sem `TRUNC` (AGENTS §4.12); `tickets_running` usando a expressão `CASE` **idêntica** ao `ix_tbsss_tck_run`, importada do `sql_ident`.
      - `RepoAgentes.listar` devolve também `plataforma`, `interpretadores` e `pastas_base` (só os nomes; README §10 tabela 15 e §13).
- **`applications/script_scheduling_service/modules/repo_factory.py`:** registrar o agregado no backend `ORACLE`.
- **`applications/script_scheduling_service/scripts/test_repo_contract.py` (ampliar, sem `if backend == ...`):**
  - **Cascatas (README §2.5):** o contrato não expõe exclusão de mestres, então as `ON DELETE CASCADE` e `SET NULL` do §10 das tabelas do agregado são cobertas numa classe só do Oracle (`skipUnless(SSS_TEST_DSN)`), com `DELETE` direto no teste (ex.: `tbsss_ticket_resp` some com o ticket; `parent_ticket_id` e `agendamento_id` viram `NULL`; associações de perfil, script e ambiente somem com o mestre).
  - **Microssegundos no bind de datas (README §7.5, teste obrigatório):** uma operação otimista com `antiga_data` contendo microssegundos (por exemplo, `pausar` com o `proxima_execucao` lido mais uma fração) **não** resulta em `rowcount = 0`/`RepoConflito`.
  - **FKs, NOT NULL e limites da auditoria:** os casos do `test_06b` passam contra o Oracle com os mesmos nomes de constraint.
- **`docs/explain/<agregado>.md`:** `EXPLAIN PLAN` (via `DBMS_XPLAN.DISPLAY`) de **cada** query de listagem, fila e transição, inclusive `ultimas_execucoes` e `historico_script` (uso de `ix_tbsss_tck_scr`). Registre o plano e confirme a ausência de `TABLE ACCESS FULL` em `tbsss_tickets` e `tbsss_auditoria`. Sem `SSS_TEST_DSN`, gere o arquivo com as queries e a seção "Plano: NÃO TESTADO".

**OUT**
- Somente o agregado indicado. Não toque nos demais.
- Sem lógica de daemon (claim, heartbeat, desdobro). Esse SQL fica num repositório interno do scheduler (F8.3/F8.4), **exceto** o que o contrato já define.

## Requisitos
1. **Paridade:** a mesma bateria de `test_repo_contract.py` passa contra ORACLE sem nenhum `if backend == ...` nos testes. Se algum teste exigir comportamento diferente, a divergência é do FAKE ou do contrato. **Pare** e reporte.
2. `SELECT` sempre com a lista explícita de colunas (AGENTS §4.12).
3. Toda função de escrita usa `db_conn.transacao`.

## Critérios de aceite
- [ ] Com `SSS_TEST_DSN`: `test_repo_contract.py` passa para o agregado nos dois backends, inclusive as cascatas, o teste de microssegundos e os casos do `test_06b`.
- [ ] Nenhuma listagem ou leitura nova (`ultimas_execucoes`, `historico_script`) seleciona coluna CLOB.
- [ ] O `docs/explain/<agregado>.md` foi gerado.
- [ ] `test_py36_compat.py` passa.
- [ ] Sem `SSS_TEST_DSN`: veredito `NÃO TESTADO`, com o motivo.

## Verificação
`SSS_TEST_DSN=... python -m unittest discover -s scripts -p "test_repo_contract.py" -v`

## Saída
Relatório AGENTS.md §9, informando o agregado no título das Observações.
