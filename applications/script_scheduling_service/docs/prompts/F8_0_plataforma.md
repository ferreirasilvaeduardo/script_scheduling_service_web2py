# SSS — Prompt F8.0: Camada de plataforma (somente POSIX, CR-005)

## Leitura obrigatória antes de planejar
- `docs/arquitetura/CR-005-posix-caminho-livre-e-logs.md` (D1: somente POSIX; D2/D3: caminho livre do script e checagens; revoga Windows do CR-001 e pastas base do CR-003)
- `AGENTS.md` §2.2, §3.2 (inteiro), §3.3, §7 (`test_plataforma.py`)
- `README.md` §2.6, §4.1, §8.0 (inteiro), §8.5 (inteiro, caminho absoluto livre), §8.11, §8.12 (passos 1, 4, 5 e 9), §12.1 (`[agent]`), §14
- Arquivos: `modules/path_guard.py` (`resolver`, checagens de cadeia até `/` e pastas do sistema), `modules/sss_config.py` (validação do `secrets.cfg`), `scripts/test_path_guard.py`, `scripts/test_config.py`, `scripts/test_py36_compat.py`

## Objetivo
Concentrar em `modules/plataforma/` **toda** primitiva que depende do sistema operacional, com implementação POSIX (Linux e demais Unix; CR-005: Windows não é suportado), para que o motor (F8.1–F8.4) não conheça o SO.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/plataforma/__init__.py`:** a interface do README §8.0 para ambiente POSIX (`os.name == 'posix'`). Exporta `NOME` (`LINUX` ou `UNIX`, gravado em `tbsss_agentes.plataforma`) e as funções:
  - `iniciar_processo(argv, log_fd, cwd, env, rotulo) -> Processo`;
  - `encerrar_grupo(processo, grace_s, relogio_monotonico)`: escalonado; **não bloqueia além de `grace_s + 1`**;
  - `identidade_processo(pid) -> int | None` e `processo_existe(pid) -> bool`;
  - `reabrir_grupo(pid, rotulo) -> Processo | None` (startup check, README §8.12 passo 9);
  - `travar_instancia(caminho) -> trava` e `liberar_instancia(trava)`;
  - `usuario_privilegiado() -> bool`;
  - `validar_arquivo_restrito(caminho)` (segredos, README §4.1: dono = euid e `mode & 0o077 == 0`) e `validar_dir_restrito(caminho)` (`log_dir`/`work_dir`, README §8.12 passo 4: existe, é diretório, é gravável pelo agente e fica fora das pastas do sistema; **não** exige `0700`, porque o `log_dir` e as pastas de log são `0750`, README §8.4 e §13);
  - `validar_caminho_script(caminho_real, donos, conta_agente=None) -> codigo | None` (README §8.0 e §8.5): dono do arquivo em `donos`; cada diretório até `/` com dono root ou em `donos`; arquivo e diretórios sem escrita de grupo, outros ou do agente;
  - `caminho_final(caminho)` (`realpath` no POSIX);
  - `criar_dir_trabalho(caminho)` (`0700` no POSIX);
  - `instalar_parada(flag)`: handlers de sinal que **apenas** setam a flag (SIGTERM/SIGINT no POSIX). O arquivo `.stop` é verificado pelo laço, não aqui.
- **`modules/plataforma/posix.py`:** as colunas POSIX do README §8.0 e o Popen literal do AGENTS §3.2, com `_child_limits` (somente `os.umask(0o077)` e `resource.setrlimit`: `RLIMIT_CORE` 0 e `RLIMIT_NOFILE` 1024).
  - `identidade_processo`: Linux, campo 22 de `/proc/<pid>/stat` contado **depois do último `)`**; AIX/Solaris, `/proc/<pid>/psinfo`; demais Unix, `sysctl KERN_PROC` **sem `ctypes`** (proibido em todo o projeto, AGENTS §3.2; README §8.0). Onde a leitura não for possível sem `ctypes` (por exemplo, macOS/BSD), retorna `None`. Plataforma sem suporte retorna `None` e o startup check trata `None` como identidade desconhecida (`ORPHAN_PROCESS`).
  - `encerrar_grupo`: `killpg(SIGTERM)` → `grace` (polling com `poll()` e `time.sleep(0.1)`) → `killpg(SIGKILL)` → `wait()`; `ProcessLookupError` = grupo encerrado.
- **Integração com o código existente:**
  - `modules/sss_config.py`: a checagem de dono e modo do `secrets.cfg` passa a chamar `plataforma.validar_arquivo_restrito`;
  - `modules/path_guard.py`: a regra de dono/escrita por item (`_checar_dono_e_modo`, `_gravavel_pelo_agente`) passa a chamar `plataforma.validar_caminho_script`, e a resolução usa `plataforma.caminho_final`.
- **Configuração (`sss_config.py`, `config.ini.example`):** `[agent] script_owner_uids` e `[agent] interpretadores` (`LOGICO=caminho`, na allowlist `PYTHON3`, `BASH`, `SH`), conforme o README §12.1. Sem `script_owner_sids` nem `base_script_dirs`.
- **`applications/script_scheduling_service/scripts/test_plataforma.py`:**
  - grupo e encerramento escalonado matando o **neto**; processo que ignora o término morre dentro de `grace + 1` s; identidade do processo estável e diferente para outro PID; PID inexistente; lock de instância (segunda trava falha); recusa de usuário privilegiado (root, com dublê); arquivo restrito OK e rejeitado; diretório de trabalho restrito; item da árvore gravável rejeitado; parada por sinal seta a flag.
  - `/proc/<pid>/stat` com `)` no nome do comando.
- **`scripts/test_py36_compat.py`:** fora de `modules/plataforma/` é proibido `os.killpg`, `os.setsid`, `resource`, `fcntl`, `/proc` e `sys.platform`; em todo o projeto, inclusive em `plataforma/`, é proibido `ctypes` e `msvcrt` (AGENTS §3.2).

**OUT**
- Ambiente do filho, executor e motor (F8.1+).
- Plataforma Windows (revogada pelo CR-005).

## Requisitos
1. Nenhuma dependência nova: só biblioteca padrão (`subprocess`, `signal`, `resource`, `fcntl`).
2. Comportamento no Linux idêntico ao atual: `test_path_guard.py` e `test_config.py` continuam passando sem alteração de expectativa.
3. Python 3.6: sintaxe e biblioteca padrão permitidas da versão 3.6.0.

## Critérios de aceite
- [ ] `test_plataforma.py`, `test_path_guard.py` e `test_config.py` passam em 3.6.0, 3.6.8 e 3.13 no Linux.
- [ ] Nenhum processo órfão após a suíte (`ps -u $USER -o pid,pgid,cmd | grep -c "sleep 300"` = 0).
- [ ] A varredura do `test_py36_compat.py` não encontra primitivas de SO fora de `plataforma/`.

## Verificação
`python -m unittest discover -s scripts -p "test_plataforma.py" -v`, depois a suíte completa.

## Saída
Relatório AGENTS.md §9.
