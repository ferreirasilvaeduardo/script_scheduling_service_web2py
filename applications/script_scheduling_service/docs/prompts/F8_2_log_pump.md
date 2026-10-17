# SSS — Prompt F8.2: Coleta de log arquivo → CLOB

## Leitura obrigatória antes de planejar
- `AGENTS.md` §4.13, §6
- `docs/arquitetura/CR-008-auditoria-final.md` (R-11: orçamento de tempo do pump e rodízio entre tickets)
- `README.md` §4.1 (segredos com menos de 4 caracteres não são registrados no mascarador), §5.2 (`LOG_LIMIT`), §8.10 (inteiro, revisado no CR-003: medida do teto, marcador e leitura da UI), §12.1 (`[logging]`), §14 (risco aceito dos segredos curtos)
- Arquivos: `modules/masking.py` (`MascaradorFluxo`), `modules/db_conn.py` (F7.0/F7.2, CR-002), `modules/executor.py`, `modules/plataforma/` (F8.0)

## Objetivo
Transferir o log local do ticket para `log_output` de forma incremental, mascarada, sem cortar caracteres multibyte e com limites que protegem o banco e o disco.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/log_pump.py`:**
  - **Mascarador por ticket (CR-007, R-25):** cada `Bomba` recebe um `masking.Mascarador` próprio com os segredos carregados, o `PADRAO_VALOR_RUN_CONEXAO_BD` do ambiente e os valores das `respostas` cujos códigos estão em `sensiveis` no snapshot (README §8.10).
  - `class Bomba` (uma instância por ticket em execução). Estado: caminho, offset em bytes, `MascaradorFluxo`, sobra de bytes UTF-8 incompletos, caracteres já enviados e flag de truncado.
  - `coletar(max_bytes_leitura=1 MiB) -> texto_seguro`:
    - lê do offset;
    - decodifica com um decoder incremental (`codecs.getincrementaldecoder('utf-8')(errors='replace')`), que resolve os multibytes cortados;
    - passa o texto pelo `MascaradorFluxo.alimentar`.
  - `finalizar() -> texto_seguro`: drena o arquivo até o fim, faz `decoder.decode(b'', final=True)` e chama `MascaradorFluxo.finalizar()`.
  - **Limites:**
    - `excedeu_local() -> bool` verifica o tamanho do arquivo contra `max_local_log_size_bytes`;
    - `aplicar_teto_banco(texto) -> (texto_para_enviar, truncou)` corta pela medida exata do README §8.10: bytes UTF-8 acumulados já enviados (`len(t.encode('utf-8'))`) contra `max_log_size_bytes`. O corte nunca divide caractere (corta por caractere, não por byte). Ao truncar, anexa o marcador literal do README §8.10.
  - `blocos(texto, tamanho=8000)` divide para o `WRITEAPPEND`.
  - **Orçamento e rodízio (CR-008, R-11):** `class Rodada(bombas, relogio_monotonico, orcamento_s)` coordena uma rodada do pump: começa pela bomba seguinte à última atendida na rodada anterior, chama `coletar` e o envio de blocos ticket a ticket e **para** assim que o tempo gasto passar de `orcamento_s` (`heartbeat_interval_s / 2`, README §8.1), mesmo no meio da fila; o que não foi lido fica para a rodada seguinte (o offset da bomba só avança com o que foi enviado). `finalizar()` de um ticket (flush final) não tem orçamento, mas o laço só faz um por iteração. O relógio é injetado (nada de `time.sleep`).
- **`applications/script_scheduling_service/modules/repo_oracle/scheduler_log.py`** (repositório **interno** do daemon, fora do contrato da UI):
  - `anexar(conn, ticket_id, agente_id, bloco) -> bool`: o bloco PL/SQL do README §8.10, **literal**, com `FOR UPDATE WAIT 5` e as condições de posse. `NO_DATA_FOUND` retorna `False` (posse perdida). O `COMMIT` fica a cargo do chamador.
  - `marcar_truncado(conn, ticket_id, agente_id) -> bool`.
  - Gravar o log é rotina técnica (CR-006, README §10): `anexar` e `marcar_truncado` **não** gravam `updated_at`/`updated_by`.
- **`applications/script_scheduling_service/scripts/test_log_pump.py`:**
  - texto ASCII;
  - texto com acentos e emoji (4 bytes) cortado em todas as posições de byte possíveis (o resultado final é igual ao original);
  - segredo cortado entre leituras é mascarado;
  - valor sensível do snapshot de um ticket é mascarado no log dele e não interfere no mascarador de outro ticket;
  - segredo com menos de 4 caracteres não é mascarado (comportamento do `masking.py`, README §4.1);
  - teto do banco com o marcador;
  - teto local detectado;
  - `blocos` com o tamanho exato;
  - arquivo que cresce entre coletas;
  - `anexar` com conexão mock retornando `NO_DATA_FOUND`, resultando em `False`.
  - **Orçamento (CR-008, R-11):** com relógio simulado que avança a cada bloco, a rodada para ao passar de `orcamento_s`; a rodada seguinte começa pelo ticket seguinte (rodízio: nenhum ticket fica sem coleta por duas rodadas seguidas quando há 3 tickets verbosos e o orçamento cobre só 1); nenhum byte é perdido entre rodadas;
  - arquivo aberto para escrita por outro processo durante a coleta (simula o filho);
  - Com `SSS_TEST_DSN`: `WRITEAPPEND` real em um ticket de teste e leitura do CLOB idêntica ao texto mascarado esperado, em cada combinação de driver disponível.

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
- [ ] Sem `SSS_TEST_DSN`, a parte real fica `NÃO TESTADO`.

## Verificação
`python -m unittest discover -s scripts -p "test_log_pump.py" -v`

## Saída
Relatório AGENTS.md §9.
