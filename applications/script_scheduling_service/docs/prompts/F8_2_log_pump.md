# SSS — Prompt F8.2: Coleta de log arquivo → CLOB

## Leitura obrigatória antes de planejar
- `AGENTS.md` §4.13, §6
- `README.md` §5.2 (`LOG_LIMIT`), §8.10 (inteiro), §12.1 (`[logging]`)
- Arquivos: `modules/masking.py` (`MascaradorFluxo`), `modules/oracle_conn.py`, `modules/executor.py`

## Objetivo
Transferir o log local do ticket para `log_output` de forma incremental, mascarada, sem cortar caracteres multibyte e com limites que protegem o banco e o disco.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/log_pump.py`:**
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
- **`applications/script_scheduling_service/modules/repo_oracle/scheduler_log.py`** (repositório **interno** do daemon, fora do contrato da UI):
  - `anexar(conn, ticket_id, agente_id, bloco) -> bool`: o bloco PL/SQL do README §8.10, **literal**, com `FOR UPDATE WAIT 5` e as condições de posse. `NO_DATA_FOUND` retorna `False` (posse perdida). O `COMMIT` fica a cargo do chamador.
  - `marcar_truncado(conn, ticket_id, agente_id) -> bool`.
- **`applications/script_scheduling_service/scripts/test_log_pump.py`:**
  - texto ASCII;
  - texto com acentos e emoji (4 bytes) cortado em todas as posições de byte possíveis (o resultado final é igual ao original);
  - segredo cortado entre leituras é mascarado;
  - teto do banco com o marcador;
  - teto local detectado;
  - `blocos` com o tamanho exato;
  - arquivo que cresce entre coletas;
  - `anexar` com conexão mock retornando `NO_DATA_FOUND`, resultando em `False`.
  - Com `SSS_TEST_DSN`: `WRITEAPPEND` real em um ticket de teste e leitura do CLOB idêntica ao texto mascarado esperado.

**OUT**
- Sem o laço do daemon (isso é o F8.3). Este módulo só fornece as peças.

## Requisitos
1. É proibido reescrever o CLOB inteiro ou ler o CLOB para concatenar (AGENTS §4.13).
2. O texto **nunca** chega ao banco sem passar pelo mascarador.
3. Leitura de arquivo sempre em binário, com o offset controlado pela bomba.

## Critérios de aceite
- [ ] Os testes passam. O teste de corte multibyte cobre todas as posições.
- [ ] Sem `SSS_TEST_DSN`, a parte real fica `NÃO TESTADO`.

## Verificação
`python -m unittest discover -s scripts -p "test_log_pump.py" -v`

## Saída
Relatório AGENTS.md §9.
