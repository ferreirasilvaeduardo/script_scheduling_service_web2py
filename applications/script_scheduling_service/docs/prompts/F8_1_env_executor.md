# SSS — Prompt F8.1: Ambiente do processo filho e executor

## Leitura obrigatória antes de planejar
- `AGENTS.md` §3.2 (inteiro), §6, §7.4 (`test_env_builder`, `test_executor`)
- `docs/arquitetura/CR-003-correcoes-pos-analise.md` (D16: pastas base e snapshot versão 3)
- `README.md` §5.2 (motivos e return codes), §6.4 (montagem do `argv`), §6.5 (snapshot versão 3), §8.0, §8.4 (passos 1–5), §8.5 (inclusive "Pastas base"), §8.6 (inteiro, inclusive a base Windows), §8.7 (timeout e finalização), §14
- Arquivos: `modules/plataforma/` (F8.0), `modules/params_compiler.py` (`validar_snapshot`, `montar_argv_agente`), `modules/path_guard.py` (`resolver_pasta`)

## Objetivo
Implementar o spawn seguro dos scripts com ambiente limpo, saída direta em arquivo, limites, timeout e encerramento do grupo de processos, **sem** depender do banco e **sem** conhecer o sistema operacional (tudo que é de SO vem de `plataforma`).

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/env_builder.py`** (puro, sem `gluon`):
  - `construir(cfg, segredos, ticket, ambiente, script_real, work_dir_ticket, environ_daemon, plataforma_nome) -> dict`, com as variáveis exatas do README §8.6:
    - **POSIX:** `PATH=/usr/bin:/bin`, `HOME`, `TMPDIR`, `LANG`/`LC_ALL` = `child_locale`, `TZ` herdado;
    - **Windows:** `SystemRoot`, `PATH=%SystemRoot%\System32;%SystemRoot%`, `TEMP`/`TMP`/`USERPROFILE` no diretório do ticket, `PATHEXT` e `COMSPEC` com valores padrão fixos; sem `LANG`/`LC_ALL`;
    - em ambas: `PYTHONDONTWRITEBYTECODE`, `PYTHONIOENCODING=utf-8`, `SSS_TICKET_ID`, `SSS_AMBIENTE`, `SSS_AGENTE_ID`, `SSS_SCRIPT_DIR`.
    - `SSS_SCRIPT_DIR` = `os.path.dirname(script_real)`, onde `script_real` é o caminho resolvido pelo `path_guard.resolver_pasta` **dentro da pasta base do script** (`pasta_base` traduzida por `base_script_dirs` do agente, README §8.5 e §8.6). Não é a pasta base nem o `cwd` (que é `work_dir/ticket_<id>`).
  - O `PADRAO_VALOR_RUN_CONEXAO_BD` só é incluído quando o ambiente tem DSN **e** o `secrets.cfg` tem a seção `[ambiente:<NOME>]` com `user` e `password`. Se faltar algum dos dois, a variável é omitida e um WARN é registrado (sem valores). O valor é registrado no `Mascarador`.
  - O `env_passthrough` é copiado de `environ_daemon`, recebido por parâmetro; o módulo **nunca** lê `os.environ`.
  - Variáveis bloqueadas (lista do README §8.6, mais `PSModulePath` e `__PSLockdownPolicy` no Windows) geram `ValueError`.
- **`applications/script_scheduling_service/modules/executor.py`** (o **único** chamador de `plataforma.iniciar_processo`):
  - `preparar_diretorio(work_dir, ticket_id) -> caminho`: cria `ticket_<id>/` e `tmp/` via `plataforma.criar_dir_trabalho`. Um diretório preexistente é removido antes, com validação de que fica sob `work_dir` (`plataforma.caminho_final` + `commonpath`).
  - `abrir_log(log_dir, ticket_id, agora) -> (fd, caminho)`: `log_dir/tickets/AAAAMM/ticket_<id>.log` com `O_WRONLY|O_CREAT|O_EXCL|O_APPEND` e `0o600` (no Windows, `O_BINARY` também; a proteção vem da ACL de `log_dir`). Arquivo existente gera `FileExistsError`, tratado pelo chamador.
  - `iniciar(argv, log_fd, cwd, env, rotulo) -> Execucao`: chama `plataforma.iniciar_processo` e faz `os.close(log_fd)` no pai. A `Execucao` guarda o processo, o PID e a identidade (`plataforma.identidade_processo`).
  - `encerrar(execucao, grace_s, relogio_monotonico)`: delega a `plataforma.encerrar_grupo`.
  - `verificar(execucao) -> None | returncode`.
  - `traduzir_retorno(returncode, plataforma_nome) -> (status, status_motivo, return_code)`, conforme o README §5.2: 0 → `SUCCESS/EXIT_OK`; positivo → `FAILED/EXIT_ERROR`; negativo (POSIX, sinal) → `FAILED/KILLED_SIGNAL` com `128 + abs`. No Windows não há `returncode` negativo por sinal; um código de término forçado pelo Job é tratado pelo chamador conforme o motivo (`TIMEOUT`, `CANCEL_USER`, `SHUTDOWN`).
  - `limpar_diretorio(caminho)`.
  - `OSError` no spawn é traduzido para `SPAWN_ERROR`.
- **`applications/script_scheduling_service/scripts/test_env_builder.py`:** os casos do AGENTS §7.4, nas duas bases (POSIX e Windows, ambas testáveis em qualquer SO porque o módulo é puro), além de: o ambiente não contém `HOME`/`USERPROFILE` real nem `PATH` do daemon; a omissão sem a seção de segredos; o mascarador recebe a connect string.
- **`applications/script_scheduling_service/scripts/test_executor.py`** (spawn real na plataforma corrente, em diretório temporário; `SH` no POSIX e `PYTHON3` no Windows):
  - saída em arquivo;
  - script que gera **2 MB** de saída termina sem travar (prova de ausência de pipe);
  - `stdin` é nulo (um script que lê da entrada termina);
  - `encerrar` mata o **neto**;
  - processo que ignora o pedido de término morre dentro de `grace + 1` s;
  - tradução de `returncode`;
  - arquivo de log com `O_EXCL` (e modo `0600` no POSIX);
  - argv montado por `params_compiler.montar_argv_agente` (Python com `-I`; PowerShell com `-NoProfile -NonInteractive -ExecutionPolicy Bypass -File`), a partir de um **snapshot versão 3** (`interpretador`, `pasta_base`, `path_file`, `args`; README §6.5) passado por `params_compiler.validar_snapshot` com um `base_script_dirs` de teste de duas pastas; o executável vem de `[agent] interpretadores` e o `script_real` da pasta base do snapshot;
  - `SSS_SCRIPT_DIR` do filho é o diretório do script dentro da pasta base (script em subpasta de uma segunda pasta base).

**OUT**
- Sem banco, sem laço de daemon e sem coleta para o CLOB (isso é o F8.2).

## Requisitos
1. É proibido `stdout=PIPE`, `shell=True` e `os.environ.copy()` (AGENTS §3.2).
2. Nenhuma primitiva de SO fora de `plataforma/` (varredura do `test_py36_compat.py`).
3. Nenhuma thread. A espera de `encerrar` é por `poll()` com `time.sleep(0.1)`.
4. Os testes de processo limpam os processos em `tearDown` mesmo em caso de falha (`encerrar_grupo` defensivo).

## Critérios de aceite
- [ ] Os dois arquivos de teste passam no Linux em 3.6.0, 3.6.8 e 3.13.
- [ ] Nenhum processo órfão após a suíte.
- [ ] Windows real: executado num runner/VM Windows, ou `NÃO TESTADO` com o motivo (CR-001, D9).

## Verificação
`python -m unittest discover -s scripts -p "test_e*.py" -v`, depois `ps -u $USER -o pid,pgid,cmd | grep -c "sleep 300"`, que deve dar 0.

## Saída
Relatório AGENTS.md §9.
