# SSS — Prompt F8.1: Ambiente do processo filho e executor

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.2 (inteiro), §6, §7.4 (`test_env_builder`, `test_executor`)
- `README.md` §5.2 (motivos e return codes), §8.4 (passos 2–5), §8.5, §8.6 (inteiro), §8.7 (timeout e finalização), §14

## Objetivo
Implementar o spawn seguro dos scripts com ambiente limpo, saída direta em arquivo, limites, timeout e encerramento do grupo de processos, **sem** depender do banco.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/env_builder.py`** (puro):
  - `construir(cfg, segredos, ticket, ambiente, script_real, work_dir_ticket, environ_daemon) -> dict`, com as variáveis exatas da tabela do README §8.6.
    - O `PADRAO_VALOR_RUN_CONEXAO_BD` só é incluído quando o ambiente tem DSN **e** o `secrets.cfg` tem a seção `[ambiente:<NOME>]` com `user` e `password`. Se faltar algum dos dois, a variável é omitida e um WARN é registrado (sem valores).
    - O `env_passthrough` é copiado de `environ_daemon`, recebido por parâmetro; o módulo **nunca** lê `os.environ` diretamente.
    - Variáveis bloqueadas geram `ValueError`.
  - O valor do `PADRAO_VALOR_RUN_CONEXAO_BD` é registrado no `Mascarador`.
- **`applications/script_scheduling_service/modules/executor.py`:**
  - `preparar_diretorio(work_dir, ticket_id) -> caminho` cria `ticket_<id>/` e `tmp/` com permissão `0700`. Um diretório preexistente é removido antes, com validação de que fica sob `work_dir` via `path_guard`.
  - `abrir_log(log_dir, ticket_id, agora) -> (fd, caminho)` usa `log_dir/tickets/AAAAMM/ticket_<id>.log` com `O_WRONLY|O_CREAT|O_EXCL|O_APPEND` e `0o600`. Um arquivo já existente gera `FileExistsError`, tratado pelo chamador.
  - `_child_limits()` só pode chamar `os.umask(0o077)` e `resource.setrlimit` (`RLIMIT_CORE` 0 e `RLIMIT_NOFILE` 1024; documente no código que esses valores são fixos, no limite permitido pelo AGENTS).
  - `iniciar(argv, log_fd, cwd, env) -> Execucao` faz o `Popen` **literal** do AGENTS §3.2 e o `os.close(log_fd)` no pai. A `Execucao` guarda o `Popen`, o PID, o PGID (= PID) e o `process_start`.
  - `ler_starttime(pid) -> int`: campo 22 de `/proc/<pid>/stat`, contado **depois do último `)`**. Fora do Linux, retorna `None`, e a docstring documenta isso.
  - `encerrar(execucao, grace_s, relogio_monotonico)` faz `killpg` com SIGTERM, aguarda até `grace_s` consultando `poll()`, aplica `killpg` com SIGKILL se necessário e então `wait()`. Trata `ProcessLookupError`. **Não bloqueia além de `grace_s + 1`**.
  - `verificar(execucao) -> None | returncode`.
  - `traduzir_retorno(returncode) -> (status, status_motivo, return_code)`, conforme o README §5.2: 0 → `SUCCESS/EXIT_OK`; positivo → `FAILED/EXIT_ERROR`; negativo → `FAILED/KILLED_SIGNAL`, com `128 + abs`.
  - `limpar_diretorio(caminho)`.
  - Erros de `OSError` no spawn são traduzidos para `SPAWN_ERROR`.
- **`applications/script_scheduling_service/scripts/test_env_builder.py`:** os casos do AGENTS §7.4, além de: o ambiente não contém `HOME` real nem `PATH` do daemon; a omissão sem a seção de segredos; o mascarador recebe a connect string.
- **`applications/script_scheduling_service/scripts/test_executor.py`** (spawn real com `/bin/sh` em diretório temporário):
  - saída em arquivo;
  - script que gera **2 MB** de saída termina sem travar (prova de ausência de pipe);
  - `stdin` é `/dev/null` (um script com `read` termina);
  - `encerrar` mata o **neto** (script que dispara `sleep 300 &` e fica em `wait`); verifique com `os.kill(pid_neto, 0)` gerando `ProcessLookupError`;
  - processo que ignora SIGTERM (`trap '' TERM`) morre com SIGKILL dentro de `grace + 1` s;
  - tradução de `returncode` negativo;
  - arquivo de log com modo `0600`;
  - `O_EXCL` em arquivo existente;
  - `starttime` lido (pule fora do Linux, com `skipUnless`).

**OUT**
- Sem banco, sem laço de daemon e sem coleta para o CLOB (isso é o F8.2).

## Requisitos
1. É proibido `stdout=PIPE`, `shell=True` e `os.environ.copy()` (AGENTS §3.2).
2. Nenhuma thread. A espera de `encerrar` é por `poll()` com `time.sleep(0.1)`.
3. Os testes de processo devem ser robustos: limpam os processos em `tearDown` mesmo em caso de falha (`killpg` defensivo).

## Critérios de aceite
- [ ] Os dois arquivos de teste passam no Linux. No macOS, os testes de `/proc` aparecem como `skipped` e os demais passam.
- [ ] Nenhum processo órfão após a suíte (`ps -o pid,pgid,cmd -u $USER` não lista `sleep 300`).

## Verificação
`python -m unittest discover -s scripts -p "test_e*.py" -v`, depois `ps -u $USER -o pid,pgid,cmd | grep -c "sleep 300"`, que deve dar 0.

## Saída
Relatório AGENTS.md §9.
