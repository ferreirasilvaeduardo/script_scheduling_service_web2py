# SSS — Prompt F8.2: Coleta de log arquivo → CLOB

## Leitura obrigatória antes de planejar
- `AGENTS.md` §4.13, §6
- `docs/architecture/CR-008-final-audit.md` (R-11: orçamento de tempo do pump e rodízio entre tickets)
- `README.md` §4.1 (segredos com menos de 4 caracteres não são registrados no mascarador), §5.2 (`LOG_LIMIT`), §8.10 (inteiro, revisado no CR-003: medida do teto, marcador e leitura da UI), §12.1 (`[logging]`), §14 (risco aceito dos segredos curtos)
- Arquivos: `modules/masking.py` (`MascaradorFluxo`), `modules/db_conn.py` (F7.0/F7.2, CR-002), `modules/executor.py`, `modules/plataforma/` (F8.0)

## Objetivo
Transferir o log local do ticket para `log_output` de forma incremental, mascarada, sem cortar caracteres multibyte e com limites que protegem o banco e o disco.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/log_pump.py`:**
  - **Mascarador por ticket (CR-007, R-25):** cada `Bomba` recebe um `masking.Mascarador` próprio com os segredos carregados, o `PADRAO_VALOR_RUN_CONEXAO_BD` do ambiente e os valores das `respostas` cujos códigos estão em `sensiveis` no snapshot (README §8.10).
  - `class Bomba` (uma instância por ticket em execução). Separe explicitamente: offset de bytes lidos do arquivo; estado do decoder incremental e seus bytes incompletos; estado do `MascaradorFluxo`; fila de texto já mascarado ainda não confirmada no banco; total de bytes UTF-8 confirmados para o limite; `offset_confirmado_chars` igual a `tbsss_tickets.log_offset_chars`; e flag de truncado. O offset de caracteres CLOB e o limite em bytes UTF-8 são grandezas distintas. O cursor de leitura pode avançar antes do envio somente se todo o texto decodificado/mascarado que ainda não foi confirmado permanecer na fila pendente da bomba.
  - `coletar(max_bytes_leitura=1 MiB) -> texto_seguro`:
    - lê do offset de bytes lidos, sem alterar o total confirmado no CLOB;
    - decodifica com um decoder incremental (`codecs.getincrementaldecoder('utf-8')(errors='replace')`), que resolve os multibytes cortados;
    - passa o texto pelo `MascaradorFluxo.alimentar`.
  - `finalizar() -> texto_seguro`: só depois que o processo terminou, drena o arquivo até o fim, faz `decoder.decode(b'', final=True)` e chama `MascaradorFluxo.finalizar()`. A saída final também entra na fila pendente e só é descartada após confirmação de gravação.
  - **Limites:**
    - `excedeu_local() -> bool` verifica o tamanho do arquivo contra `max_local_log_size_bytes`;
    - `aplicar_teto_banco(texto) -> (texto_para_enviar, truncou)` limita os bytes UTF-8 acumulados do CLOB, **incluindo** o marcador literal do README §8.10, a `max_log_size_bytes`. O corte nunca divide caractere. Mantenha em buffer o sufixo de até `len(marcador.encode('utf-8'))` bytes ainda não confirmados: se a entrada terminar antes de exceder o teto, `Bomba.finalizar()` libera esse sufixo sem marcador; se exceder, confirme somente o prefixo que caiba em `max_log_size_bytes - bytes_do_marcador` e acrescente o marcador exatamente uma vez. O flush final também respeita o offset CLOB e a confirmação idempotente; o total confirmado, marcador incluído, nunca passa do teto.
  - `blocos(texto, tamanho=8000)` divide para o `WRITEAPPEND`.
  - **Orçamento, rodízio e `COMMIT` incerto (CR-008, R-11):** `class Rodada(bombas, relogio_monotonico, orcamento_s)` coordena uma rodada: começa pela bomba seguinte à última atendida, chama `coletar` e envia blocos ticket a ticket; **para** ao passar de `orcamento_s` (`heartbeat_interval_s / 2`), mesmo no meio da fila. Cada bomba tem no máximo um append em voo. Chame `anexar(conn, ticket_id, agente_id, offset_esperado, bloco)` e, se o resultado indicar `GRAVADO`, confirme a transação antes de remover o bloco pendente. Se o `COMMIT` falhar ou tiver desfecho desconhecido, preserve o mesmo bloco, offset e fila; numa conexão nova, reapresente exatamente a mesma operação. O protocolo retorna `JA_GRAVADO` somente após validar offset final e conteúdo do CLOB, ou grava o bloco uma vez e retorna `GRAVADO`. Ambos contam como confirmado após o `COMMIT` correspondente. `POSSE_PERDIDA` encaminha `OWNERSHIP_LOST` sem descartar o texto como gravado. Divergência de offset ou conteúdo é `LogOffsetInconsistente`: interromper o pump do ticket e registrar ERROR, sem repetição nem descarte silencioso. O texto pendente só sai da fila após confirmação; isso torna a repetição após resultado de `COMMIT` desconhecido idempotente. `finalizar()` não tem orçamento, mas o laço só faz um flush final por iteração. O relógio é injetado (nada de `time.sleep`).
- **`applications/script_scheduling_service/modules/repo_oracle/scheduler_log.py`** (repositório **interno** do daemon, fora do contrato da UI):
  - `anexar(conn, ticket_id, agente_id, offset_esperado, bloco) -> 'GRAVADO' | 'JA_GRAVADO' | 'POSSE_PERDIDA'`: o bloco PL/SQL do README §8.10, **literal**, com `FOR UPDATE WAIT 5`, validação de `log_offset_chars` contra `DBMS_LOB.GETLENGTH`, append condicional e comparação do bloco já escrito por `DBMS_LOB.COMPARE`. O bind OUT `:resultado` é criado com `db_conn.variavel_saida(cursor, db_conn.TIPO_VARCHAR, tamanho=20)` e lido com `db_conn.valor_saida`; nenhum acesso direto a `cursor.var` ou tipos do driver. `NO_DATA_FOUND` retorna `POSSE_PERDIDA`; offset ou conteúdo divergente lança `LogOffsetInconsistente`. O `COMMIT` fica a cargo do chamador. O claim inicializa `log_offset_chars = 0` ao definir `log_output = EMPTY_CLOB()`.
  - `marcar_truncado(conn, ticket_id, agente_id) -> bool`.
  - Gravar o log é rotina técnica (CR-006, README §10): `anexar` e `marcar_truncado` **não** gravam `updated_at`/`updated_by`.
- **`applications/script_scheduling_service/scripts/test_log_pump.py`:**
  - texto ASCII;
  - texto com acentos e emoji (4 bytes) cortado em todas as posições de byte possíveis (o resultado final é igual ao original);
  - segredo cortado entre leituras é mascarado;
  - valor sensível do snapshot de um ticket é mascarado no log dele e não interfere no mascarador de outro ticket;
  - segredo com menos de 4 caracteres não é mascarado (comportamento do `masking.py`, README §4.1);
  - teto do CLOB nos limites exatos: payload que termina sem exceder envia tudo sem marcador; payload que excede reserva espaço para o marcador, preserva fronteiras multibyte, acrescenta o marcador uma vez e mantém bytes UTF-8 totais `<= max_log_size_bytes`;
  - teto local detectado;
  - `blocos` com o tamanho exato;
  - arquivo que cresce entre coletas;
  - `anexar` com conexão mock retornando `NO_DATA_FOUND`, resultando em `POSSE_PERDIDA`, `OWNERSHIP_LOST` para o chamador e nenhum avanço do texto confirmado.
  - `anexar` repetido com mesmo ticket/agente/offset/bloco: após commit, segunda chamada retorna `JA_GRAVADO` e o CLOB contém o bloco uma única vez; rollback antes do primeiro commit permite retry que retorna `GRAVADO`;
  - bind OUT `:resultado` criado/lido exclusivamente por `db_conn.variavel_saida`/`db_conn.valor_saida`, com resultado equivalente em Thin, Thick e cx_Oracle;
  - `COMMIT` simulado como incerto depois de persistir: a mesma chamada repetida reconcilia por offset e conteúdo, sem perda nem duplicação; offset divergente, comprimento CLOB divergente ou conteúdo diferente gera `LogOffsetInconsistente` e não altera o CLOB;
  - **Orçamento (CR-008, R-11):** com relógio simulado que avança a cada bloco, a rodada para ao passar de `orcamento_s`; a rodada seguinte começa pelo ticket seguinte (rodízio: nenhum ticket fica sem coleta por duas rodadas seguidas quando há 3 tickets verbosos e o orçamento cobre só 1); bytes lidos mas ainda não confirmados sobrevivem à rodada, e falha/timeout entre envio e commit é resolvido pelo protocolo idempotente acima;
  - arquivo aberto para escrita por outro processo durante a coleta (simula o filho);
  - Com `SSS_TEST_ORACLE=1` (README §2.5; owner e prefixo do `instance/config.ini`, modo descartável ou compartilhado): `preparar_schema_descartavel` antes de DML; `WRITEAPPEND` real somente em ticket criado pela própria massa do teste (posto em `RUNNING` com `log_output = EMPTY_CLOB()` e `log_offset_chars = 0`), repetir a chamada com o mesmo offset e bloco deve retornar `JA_GRAVADO`, e limpar apenas esse ticket após o teste. `log_output` deve conter o texto mascarado exatamente uma vez em cada combinação de driver disponível (cada uma num processo separado).

**OUT**
- Sem o laço do daemon (isso é o F8.3). Este módulo só fornece as peças.

## Requisitos
1. É proibido reescrever o CLOB inteiro ou ler o CLOB para concatenar (AGENTS §4.13).
2. O texto **nunca** chega ao banco sem passar pelo mascarador. Segredos com menos de 4 caracteres **não** são mascarados (README §4.1, risco aceito no §14): não crie regra própria para eles; o teste confirma que um valor curto passa intacto e que um de 4 ou mais é mascarado.
3. Leitura de arquivo sempre em binário, com o offset controlado pela bomba.
4. **Leitura concorrente (POSIX):** o arquivo é lido enquanto o filho ainda escreve nele. Abra para leitura sem bloquear a escrita do filho (o `open` padrão do Python compartilha leitura e escrita no POSIX). Trate arquivos em crescimento incremental mantendo o offset.
5. O bloco PL/SQL é o mesmo nas três combinações de driver (CR-002); o tipo do bind de CLOB vem do `db_conn`.

## Critérios de aceite
- [ ] Os testes passam. O teste de corte multibyte cobre todas as posições.
- [ ] Sem `SSS_TEST_ORACLE=1` (README §2.5), a parte real fica `NÃO TESTADO`.

## Verificação
`python -m unittest discover -s scripts -p "test_log_pump.py" -v`

## Saída
Relatório AGENTS.md §9.
