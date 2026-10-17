# SSS — Prompt F8.1: Ambiente do processo filho e executor

## Leitura obrigatória antes de planejar
- `docs/arquitetura/CR-007-robustez-do-scheduler.md` (D1, R-01 a R-04, R-17, R-32)
- `AGENTS.md` §3.2 (inteiro), §6, §7.4 (`test_env_builder`, `test_executor`)
- `docs/arquitetura/CR-005-posix-caminho-livre-e-logs.md` (D1: somente POSIX; D2: caminho livre; D5, R-a, R-b: pastas de log; snapshot v4)
- `README.md` §5.2 (motivos e return codes), §6.4 (montagem do `argv`), §6.5 (snapshot versão 4), §8.0, §8.4 (passos 1–5), §8.5 (caminho livre e checagens), §8.6 (ambiente do processo filho POSIX), §8.7 (timeout e finalização), §14
- Arquivos: `modules/plataforma/` (F8.0), `modules/pastas_log.py`, `modules/params_compiler.py` (`validar_snapshot`, `montar_argv_agente`), `modules/path_guard.py` (`resolver`)

## Objetivo
Implementar o spawn seguro dos scripts com ambiente limpo, saída direta em arquivo sob `pastas_log`, limites, timeout e encerramento do grupo de processos, **sem** depender do banco e **sem** conhecer o sistema operacional (tudo que é de SO vem de `plataforma`).

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/env_builder.py`** (puro, sem `gluon`):
  - `construir(cfg, segredos, ticket, ambiente, script_real, work_dir_ticket, environ_daemon, plataforma_nome) -> dict`, com as variáveis exatas do README §8.6 (ambiente POSIX):
    - `PATH=/usr/bin:/bin`, `HOME`, `TMPDIR`, `LANG`/`LC_ALL` = `child_locale`, `TZ` herdado;
    - `PYTHONDONTWRITEBYTECODE`, `PYTHONIOENCODING=utf-8`, `SSS_TICKET_ID`, `SSS_AMBIENTE`, `SSS_AGENTE_ID`, `SSS_SCRIPT_DIR`.
    - `SSS_SCRIPT_DIR` = `os.path.dirname(script_real)`, onde `script_real` é o caminho absoluto resolvido pelo `path_guard.resolver` (README §8.5 e §8.6). Não é o `cwd` (que é `work_dir/ticket_<id>`).
  - O `PADRAO_VALOR_RUN_CONEXAO_BD` só é incluído quando o ambiente tem DSN **e** o `secrets.cfg` tem a seção `[ambiente:<NOME>]` com `user` e `password`. Se faltar algum dos dois, a variável é omitida e um WARN é registrado (sem valores). O valor é registrado no `Mascarador`.
  - O `env_passthrough` é copiado de `environ_daemon`, recebido por parâmetro; o módulo **nunca** lê `os.environ`.
  - Variáveis bloqueadas (lista do README §8.6) geram `ValueError`.
- **`env_builder` e o CR-007:** `HOME`/`TMPDIR` são o diretório de trabalho do script (`exec_work_dir/<usuário>/ticket_<id>` e `tmp/`; em DEV, `work_dir/ticket_<id>/exec`); a lista de bloqueio e as chaves fixas recusadas são as do README §8.6; `PYTHON*` só tem efeito em BASH/SH.
- **`applications/script_scheduling_service/modules/executor.py`** (o **único** chamador de `plataforma.iniciar_processo`):
  - `preparar_diretorio(work_dir, ticket_id) -> caminho`: cria `ticket_<id>/` e `tmp/` via `plataforma.criar_dir_trabalho`. Um diretório preexistente é removido antes, com validação de que fica sob `work_dir` (`plataforma.caminho_final` + `commonpath`).
  - `abrir_log(log_dir, nome_script, started_at, ticket_id, script_id=None) -> (fd, caminho)`: cria as pastas `log_dir/<pasta_script>/AAAA/MM/DD/HH/MI/` **nível a nível com `chmod 0750`** em cada pasta nova (README §8.4, passo 3: o `makedirs` só aplica o modo à pasta final, e sempre sob a `umask` 077). Mova a função privada `sss_logging._garantir_diretorio` para uma função pública de `pastas_log` e use-a nos dois lugares. Depois abre `ticket_<id>.log.parcial` (`pastas_log.caminho_log_parcial`) com `O_WRONLY|O_CREAT|O_EXCL|O_APPEND` e `0o600`. O `nome_script` é o `script_nome` do snapshot (o nome da época da criação do ticket, README §6.5).
  - **Especificação para o helper (CR-007, D1):** `especificacao(ticket_id, argv, env, rlimits, pasta_base)` em JSON, entregue pela entrada padrão; o log aberto pelo agente vira stdout/stderr.
  - `iniciar(argv, log_fd, cwd, env, rotulo) -> Execucao`: chama `plataforma.iniciar_processo`, renomeia o log para `ticket_<id>_<PID>.log` (`pastas_log.caminho_log_execucao`), e faz `os.close(log_fd)` no pai. Em caso de falha no spawn, grava a causa no arquivo (sem segredos) e renomeia o parcial para `ticket_<id>_0.log` (README §8.4, passo 3). A `Execucao` guarda o processo, o PID e a identidade (`plataforma.identidade_processo`).
  - **Encerramento como máquina de estados (CR-007, R-04):** `pedir_encerramento(execucao, agora_monotonico)` envia SIGTERM e marca o prazo; `avancar_encerramento(execucao, agora_monotonico)` envia SIGKILL quando o prazo vence e diz se o grupo acabou. Nenhuma das duas espera. O grupo é encerrado em **toda** finalização, mesmo com o líder já terminado (R-02), e WARN `NETOS_ENCERRADOS` quando havia membros.
  - **Estado local (R-01):** `registrar_proc(execucao)` grava `.sss_proc` logo depois do spawn; `registrar_resultado(execucao, status, motivo, rc)` grava `.sss_result` antes do `UPDATE` de finalização.
  - `verificar(execucao) -> None | returncode`.
  - `traduzir_retorno(returncode, plataforma_nome) -> (status, status_motivo, return_code)`, conforme o README §5.2: 0 → `SUCCESS/EXIT_OK`; positivo → `FAILED/EXIT_ERROR`; negativo (POSIX, sinal) → `FAILED/KILLED_SIGNAL` com `128 + abs`.
  - `limpar(execucao)`: remove `work_dir/ticket_<id>/` e, pelo helper (`limpar`), o diretório do script; chamado em todo encerramento.
  - **Qualquer** exceção no spawn (não só `OSError`, por exemplo `UnicodeEncodeError`) é traduzida para `SPAWN_ERROR`, com a linha `[SSS] falha ao iniciar: <classe>` no log (R-17).
- **`applications/script_scheduling_service/scripts/test_env_builder.py`:** os casos do AGENTS §7.4 na base POSIX: o ambiente não contém `HOME` real nem `PATH` do daemon; a omissão sem a seção de segredos; o mascarador recebe a connect string; variáveis bloqueadas geram erro.
- **`applications/script_scheduling_service/scripts/test_executor.py`** (spawn real no ambiente POSIX em diretório temporário):
  - saída em arquivo de log por minuto (`pastas_log`);
  - script que gera **2 MB** de saída termina sem travar (prova de ausência de pipe);
  - `stdin` é nulo (um script que lê da entrada termina);
  - o encerramento (máquina de estados) mata o **neto**, inclusive quando o processo principal já saiu sozinho; nenhuma chamada bloqueia;
  - `.sss_proc` existe logo depois de `iniciar` e `.sss_result` antes da finalização;
  - exceção que não é `OSError` no spawn vira `SPAWN_ERROR`;
  - processo que ignora o pedido de término morre dentro de `grace + 1` s;
  - tradução de `returncode`;
  - arquivo de log com `O_EXCL` e modo `0600`; cada pasta nova do caminho com `0750` sob `umask 077`;
  - falha no spawn: a causa gravada e o arquivo `ticket_<id>_0.log`;
  - timeout: o processo que passa do tempo é encerrado pelo `encerrar` (AGENTS §7);
  - renomeação atômica do parcial para `ticket_<id>_<PID>.log`;
  - argv montado por `params_compiler.montar_argv_agente` (Python com `-I`), a partir de um **snapshot versão 4** (`interpretador`, `path_file`, `args`; README §6.5) passado por `params_compiler.validar_snapshot`; o executável vem de `[agent] interpretadores` e o `script_real` é o `path_file` absoluto resolvido. Estenda `validar_snapshot` para devolver `(snap, argv_real, script_real)`, porque o `env_builder` precisa do `script_real` (`SSS_SCRIPT_DIR`) e o caminho não deve ser resolvido duas vezes;
  - `SSS_SCRIPT_DIR` do filho é o diretório do script.

**OUT**
- Sem banco, sem laço de daemon e sem coleta para o CLOB (isso é o F8.2).
- Plataforma Windows (revogada pelo CR-005).

## Requisitos
1. É proibido `stdout=PIPE`, `shell=True` e `os.environ.copy()` (AGENTS §3.2).
2. Nenhuma primitiva de SO fora de `plataforma/` (varredura do `test_py36_compat.py`).
3. Nenhuma thread. A espera de `encerrar` é por `poll()` com `time.sleep(0.1)`.
4. Os testes de processo limpam os processos em `tearDown` mesmo em caso de falha (`encerrar_grupo` defensivo).

## Critérios de aceite
- [ ] Os dois arquivos de teste passam no Linux em 3.6.0, 3.6.8 e 3.13.
- [ ] Nenhum processo órfão após a suíte.

## Verificação
`python -m unittest discover -s scripts -p "test_e*.py" -v`, depois `ps -u $USER -o pid,pgid,cmd | grep -c "sleep 300"`, que deve dar 0.

## Saída
Relatório AGENTS.md §9.
