# SSS — Prompt F8.0: Camada de plataforma (POSIX e Windows)

## Leitura obrigatória antes de planejar
- `docs/arquitetura/CR-001-multiplataforma-e-sql-ansi.md` §2 (parte B, inteira)
- `AGENTS.md` §2.2, §3.2 (inteiro), §3.3, §7 (`test_plataforma.py`)
- `README.md` §2.6, §4.1, §8.0 (inteiro), §8.5, §8.11, §8.12 (passos 1, 4, 5 e 9), §12.1 (`[agent]`), §14
- Arquivos: `modules/path_guard.py`, `modules/sss_config.py` (validação do `secrets.cfg`), `scripts/test_path_guard.py`, `scripts/test_config.py`, `scripts/test_py36_compat.py`

## Objetivo
Concentrar em `modules/plataforma/` **toda** primitiva que depende do sistema operacional, com implementações POSIX (Linux e demais Unix) e Windows (APIs nativas via `ctypes`, sem dependência nova), para que o motor (F8.1–F8.4) não conheça o SO.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/plataforma/__init__.py`:** a interface do README §8.0 e a seleção da implementação **uma única vez** no import (`os.name`). Exporta `NOME` (`LINUX`, `UNIX` ou `WINDOWS`, gravado em `tbsss_agentes.plataforma`) e as funções:
  - `iniciar_processo(argv, log_fd, cwd, env, rotulo) -> Processo` (rótulo = `SSS-<agent_id>-<ticket_id>`, usado no Windows como nome do Job);
  - `encerrar_grupo(processo, grace_s, relogio_monotonico)`: escalonado; **não bloqueia além de `grace_s + 1`**;
  - `identidade_processo(pid) -> int | None` e `processo_existe(pid) -> bool`;
  - `reabrir_grupo(pid, rotulo) -> Processo | None` (startup check, README §8.12 passo 9);
  - `travar_instancia(caminho) -> trava` e `liberar_instancia(trava)`;
  - `usuario_privilegiado() -> bool`;
  - `validar_arquivo_restrito(caminho)` (segredos, README §4.1) e `validar_dir_restrito(caminho)` (`log_dir`/`work_dir`, README §8.12 passo 4);
  - `validar_item_arvore(caminho, donos, conta_agente=None) -> codigo | None` (um item da árvore de scripts, README §8.5);
  - `caminho_final(caminho)` (`realpath` no POSIX; `GetFinalPathNameByHandleW` no Windows, em qualquer versão do Python, rejeitando *reparse points* não resolvidos);
  - `criar_dir_trabalho(caminho)` (`0700` no POSIX; ACL só da conta do agente no Windows);
  - `instalar_parada(flag)`: handlers de sinal que **apenas** setam a flag (SIGTERM/SIGINT no POSIX; SIGBREAK/SIGINT no Windows). O arquivo `.stop` é verificado pelo laço, não aqui.
- **`modules/plataforma/posix.py`:** as colunas POSIX do README §8.0 e o Popen literal do AGENTS §3.2, com `_child_limits` (somente `os.umask(0o077)` e `resource.setrlimit`: `RLIMIT_CORE` 0 e `RLIMIT_NOFILE` 1024).
  - `identidade_processo`: Linux, campo 22 de `/proc/<pid>/stat` contado **depois do último `)`**; AIX/Solaris, `/proc/<pid>/psinfo`; macOS/BSD, `sysctl KERN_PROC` via `ctypes`. Plataforma sem suporte retorna `None` e o startup check trata `None` como identidade desconhecida (`ORPHAN_PROCESS`).
  - `encerrar_grupo`: `killpg(SIGTERM)` → `grace` (polling com `poll()` e `time.sleep(0.1)`) → `killpg(SIGKILL)` → `wait()`; `ProcessLookupError` = grupo encerrado.
- **`modules/plataforma/windows.py`** (somente `ctypes` + `msvcrt` + `subprocess`; **sem** `pywin32` nem `psutil`):
  - Popen com `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` e atribuição **imediata** a um Job Object nomeado (`rotulo`) com `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `JOB_OBJECT_LIMIT_ACTIVE_PROCESS` e limite de memória;
  - `encerrar_grupo`: `CTRL_BREAK_EVENT` → `grace` → `TerminateJobObject` → `wait()`;
  - `identidade_processo`: `GetProcessTimes().CreationTime`; `processo_existe`: `OpenProcess` + `GetExitCodeProcess`;
  - `travar_instancia`: `msvcrt.locking(LK_NBLCK)`;
  - `usuario_privilegiado`: token elevado (membro de Administradores) ou SYSTEM;
  - `validar_arquivo_restrito`/`validar_dir_restrito`: dono = SID do processo e DACL só com o dono e SYSTEM, sem herança de Users, Authenticated Users ou Everyone;
  - `validar_item_arvore`: dono em `script_owner_sids` e **direitos efetivos** sem escrita para a conta do agente nem para os grupos amplos (`GetEffectiveRightsFromAclW`). `os.access` é proibido aqui (só olha o atributo "somente leitura").
- **Migração do código existente** (sem mudar comportamento no Linux):
  - `modules/sss_config.py`: a checagem de dono e modo do `secrets.cfg` passa a chamar `plataforma.validar_arquivo_restrito`;
  - `modules/path_guard.py`: a regra de dono/escrita por item (`_checar_dono_e_modo`, `_gravavel_pelo_agente`) passa a chamar `plataforma.validar_item_arvore`, e a resolução usa `plataforma.caminho_final`. Os códigos de retorno do `path_guard` e as mensagens da UI (F4.5) não mudam.
- **Configuração (`sss_config.py`, `config.ini.example`):** `[agent] script_owner_sids` (lista de SIDs, `^S-1-[0-9-]+$`) e `[agent] interpretadores` (`LOGICO=caminho`, lógico na allowlist **da plataforma corrente**), conforme o README §12.1; `script_owner_uids` só é exigido no POSIX e `script_owner_sids` só no Windows. Atualize `test_config.py`.
- **`applications/script_scheduling_service/scripts/test_plataforma.py`:**
  - **Plataforma corrente (real):** grupo e encerramento escalonado matando o **neto**; processo que ignora o término morre dentro de `grace + 1` s; identidade do processo estável e diferente para outro PID; PID inexistente; lock de instância (segunda trava falha); recusa de usuário privilegiado (com dublê); arquivo restrito OK e rejeitado; diretório de trabalho restrito; item da árvore gravável rejeitado; parada por sinal seta a flag.
  - **Outra plataforma:** dublês da API nativa (módulo `ctypes` falso ou funções injetadas) cobrindo a lógica de decisão, marcados com `skipUnless(sys.platform ...)` para a execução real.
  - **POSIX:** `/proc/<pid>/stat` com `)` no nome do comando.
  - **Windows (dublês):** link e junction resolvidos por `caminho_final`; *reparse point* não resolvido rejeitado; drive diferente da base = `FORA_DA_BASE`.
- **`scripts/test_py36_compat.py`:** fora de `modules/plataforma/` é proibido `os.killpg`, `os.setsid`, `resource`, `fcntl`, `msvcrt`, `ctypes.windll`, `/proc` e `sys.platform` (AGENTS §3.2).

**OUT**
- Ambiente do filho, executor e motor (F8.1+). Launchers `.ps1` (F9.1).

## Requisitos
1. Nenhuma dependência nova: só biblioteca padrão (`ctypes`, `msvcrt`, `subprocess`, `signal`).
2. Comportamento no Linux idêntico ao atual: `test_path_guard.py` e `test_config.py` continuam passando sem alteração de expectativa.
3. Python 3.6: `ctypes.wintypes` disponível; nada de API 3.7+ (ex.: `subprocess` com `capture_output`).
4. Sem runner Windows, a parte Windows real fica `NÃO TESTADO` (CR-001, D9); os dublês precisam passar em qualquer SO.

## Critérios de aceite
- [ ] `test_plataforma.py`, `test_path_guard.py` e `test_config.py` passam em 3.6.0, 3.6.8 e 3.13 no Linux.
- [ ] Nenhum processo órfão após a suíte (`ps -u $USER -o pid,pgid,cmd | grep -c "sleep 300"` = 0).
- [ ] A varredura do `test_py36_compat.py` não encontra primitivas de SO fora de `plataforma/`.
- [ ] Windows real: executado num runner/VM Windows, ou `NÃO TESTADO` com o motivo.

## Verificação
`python -m unittest discover -s scripts -p "test_plataforma.py" -v`, depois a suíte completa.

## Saída
Relatório AGENTS.md §9.
