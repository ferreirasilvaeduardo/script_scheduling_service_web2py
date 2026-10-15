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
- `README.md` §2.5 (paridade), §4.3.B, §5 (inteiro), §8.2, §8.3 (ordem de locks), §10 (tabelas do agregado), §10 (política de exclusão)
- Arquivos: o contrato `modules/repo_<x>.py` do agregado, a implementação `modules/repo_fake/<x>.py`, `modules/db_conn.py`, `modules/sql_ident.py` e `scripts/test_repo_contract.py`

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
  - **Datas:** binds declarados como `TIPO_DATE` (`setinputsizes`) e leitura de `DATE` sem microssegundos.
  - **CLOB:**
    - escrita de `parametros_enviados` como bind CLOB;
    - `log_ler` lê por locator com `lob.read(offset + 1, amount)` (o LOB do Oracle começa em 1) e retorna o offset em base 0 coerente com o FAKE;
    - listagens **nunca** selecionam colunas CLOB.
  - **Erros:** `db_conn.classificar_erro` traduz o ORA-00001 para `RepoViolacao(constraint)` (extraindo o nome da constraint da mensagem), o ORA-02291/02292 para `RepoViolacao`, o ORA-20001 (imutável) para `RepoViolacao` e as falhas de rede para `RepoIndisponivel`.
  - **Pontos específicos por agregado:**
    - `RBAC_USUARIOS`: `admins_ativos_bloquear` com o SQL do README §4.3.B **literal** (`FOR UPDATE OF u.ativo WAIT 5`), executado na mesma transação que a alteração; `matriz_salvar` com `DELETE` + `executemany INSERT` e `UPDATE perm_versao = perm_versao + 1` em uma transação; `obter_estado_sessao` com uma query por PK (join usuário + perfil).
    - `CATALOGO`: `scripts_executaveis` com uma única query, com joins/`EXISTS` sobre `perfil_scr`, `perfil_amb` e `script_amb` e o atalho para admin; `parametro_vinculos` para o bloqueio de desativação.
    - `TICKETS`: `criar` com o ticket mais as respostas (`executemany`) e auditoria em **uma** transação; `solicitar_cancelamento` com os dois `UPDATE`s do README §5.6 **literais**; a listagem com escopo de ambientes por bind.
    - `AGENDAMENTOS`: `pausar` e `retomar` otimistas com `proxima_execucao = :antiga_data` (bind DATE); `alterar` atualizando `usuario_id`.
    - `AUDITORIA_AGENTES`: o filtro de período sempre por intervalo, sem `TRUNC` (AGENTS §4.12); `tickets_running` usando a expressão `CASE` **idêntica** ao `ix_tbsss_tck_run`, importada do `sql_ident`.
- **`applications/script_scheduling_service/modules/repo_factory.py`:** registrar o agregado no backend `ORACLE`.
- **`docs/explain/<agregado>.md`:** `EXPLAIN PLAN` (via `DBMS_XPLAN.DISPLAY`) de **cada** query de listagem, fila e transição. Registre o plano e confirme a ausência de `TABLE ACCESS FULL` em `tbsss_tickets` e `tbsss_auditoria`. Sem `SSS_TEST_DSN`, gere o arquivo com as queries e a seção "Plano: NÃO TESTADO".

**OUT**
- Somente o agregado indicado. Não toque nos demais.
- Sem lógica de daemon (claim, heartbeat, desdobro). Esse SQL fica num repositório interno do scheduler (F8.3/F8.4), **exceto** o que o contrato já define.

## Requisitos
1. **Paridade:** a mesma bateria de `test_repo_contract.py` passa contra ORACLE sem nenhum `if backend == ...` nos testes. Se algum teste exigir comportamento diferente, a divergência é do FAKE ou do contrato. **Pare** e reporte.
2. `SELECT` sempre com a lista explícita de colunas (AGENTS §4.12).
3. Toda função de escrita usa `db_conn.transacao`.

## Critérios de aceite
- [ ] Com `SSS_TEST_DSN`: `test_repo_contract.py` passa para o agregado nos dois backends.
- [ ] O `docs/explain/<agregado>.md` foi gerado.
- [ ] `test_py36_compat.py` passa.
- [ ] Sem `SSS_TEST_DSN`: veredito `NÃO TESTADO`, com o motivo.

## Verificação
`SSS_TEST_DSN=... python -m unittest discover -s scripts -p "test_repo_contract.py" -v`

## Saída
Relatório AGENTS.md §9, informando o agregado no título das Observações.
