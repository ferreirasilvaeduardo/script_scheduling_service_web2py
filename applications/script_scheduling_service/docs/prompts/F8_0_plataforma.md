# SSS — Prompt F8.0: Camada de plataforma (somente POSIX, CR-005)

## Leitura obrigatória antes de planejar
- `docs/arquitetura/CR-007-robustez-do-scheduler.md` (D1: helper e usuário de execução; R-01, R-02, R-04, R-14, R-15)
- `docs/arquitetura/CR-008-auditoria-final.md` (R-01: `.sss_spawn` e helper `encerrar-ticket`; R-25: espaço livre em `log_dir`; R-36: `limpar` com `pasta_base`)
- `docs/arquitetura/CR-005-posix-caminho-livre-e-logs.md` (D1: somente POSIX; D2/D3: caminho livre do script e checagens; revoga Windows do CR-001 e pastas base do CR-003)
- `AGENTS.md` §2.2, §3.2 (inteiro), §3.3, §7 (`test_plataforma.py`)
- `README.md` §2.6, §4.1, §8.0 (inteiro), §8.5 (inteiro, caminho absoluto livre), §8.11, §8.12 (passos 1, 4, 5 e 9), §12.1 (`[agent]`), §14
- Arquivos: `modules/path_guard.py` (`resolver`, checagens de cadeia até `/` e pastas do sistema), `modules/sss_config.py` (validação do `secrets.cfg`), `scripts/test_path_guard.py`, `scripts/test_config.py`, `scripts/test_py36_compat.py`

## Objetivo
Concentrar em `modules/plataforma/` **toda** primitiva que depende do sistema operacional, com implementação POSIX (Linux e demais Unix; CR-005: Windows não é suportado), para que o motor (F8.1–F8.4) não conheça o SO.

## Escopo
**IN**
- **`applications/script_scheduling_service/modules/plataforma/__init__.py`:** a interface do README §8.0 para ambiente POSIX (`os.name == 'posix'`). Exporta `NOME` (`LINUX` ou `UNIX`, gravado em `tbsss_agentes.plataforma`) e as funções:
  - `iniciar_processo(especificacao, log_fd, usuario_execucao) -> Processo`: com `usuario_execucao`, o `Popen` do `sudo -n -u <usuário> -- /opt/sss/bin/sss-helper run` com a especificação pela entrada padrão (README §8.0 e §8.4); sem ele (só DEV), a especificação contém `argv`, `cwd`, `env` e `rlimits`, e a plataforma faz o `Popen` direto do AGENTS §3.2;
  - `sinalizar_grupo(processo, sinal) -> bool`: **não bloqueante** (CR-007, R-04). Com usuário de execução, pelo helper (`term`/`kill <pgid> <process_start>`); sem, `os.killpg`. `ESRCH` = grupo vazio. A escalada SIGTERM → prazo → SIGKILL é do executor (F8.1), como máquina de estados;
  - `grupo_vivo(processo) -> bool`: o grupo ainda tem membros (inclusive netos depois da saída do líder, R-02);
  - `validar_execucao(cfg)` (README §8.0): helper com dono root, `0755` e pasta só do root; `sudo -n -l` com a regra do helper para cada usuário de execução; usuários existentes, não root, diferentes do agente e fora de `script_owner_uids`; `exec_work_dir/<usuário>` do próprio usuário com `0700`. Falha: CRITICAL;
  - `gravar_estado(caminho, dados)` e `ler_estado(caminho)`: JSON em arquivo temporário + `rename`, `0600` (`.sss_spawn`, `.sss_proc`, `.sss_result`; CR-007 R-01 e CR-008 R-01);
  - `encerrar_ticket(pasta_base, ticket_id, usuario_execucao, kill_grace_s) -> 'OK' | 'NAO_SUPORTADO'` (CR-008, R-01): caso "talvez iniciado" do startup check e da varredura. Com usuário de execução, `sudo -n -u <usuário> -- /opt/sss/bin/sss-helper encerrar-ticket <pasta_base> <ticket_id> <kill_grace_s>`; em DEV, a mesma busca feita por `modules/plataforma` (processos do usuário cujo `/proc/<pid>/cwd` está em `<pasta_base>/ticket_<id>`). No processo privilegiado separado, somente o subcomando do helper `encerrar-ticket` pode consultar `/proc/<pid>/cwd` ou invocar `pwdx` por caminho absoluto; esta é a exceção estreita do AGENTS §3.2. Código 5 do helper vira `NAO_SUPORTADO`;
  - `espaco_livre_mb(caminho) -> int` (`os.statvfs`, `f_bavail × f_frsize`; CR-008, R-25);
  - `identidade_processo(pid) -> Optional[int]` e `processo_existe(pid) -> bool`;
  - `reabrir_grupo(estado_sss_proc) -> Optional[Processo]` (startup check, README §8.12 passo 9): grupo que não é filho do daemon, acompanhado por `processo_existe` + identidade, sem `wait()`; identidade `None` com PID vivo devolve um `Processo` marcado `sem_identidade`, que **não** recebe sinal (WARN `ORFAO_SEM_IDENTIDADE`);
  - `travar_instancia(caminho) -> trava` e `liberar_instancia(trava)`;
  - `usuario_privilegiado() -> bool`;
  - `validar_arquivo_restrito(caminho)` (segredos, README §4.1: dono = euid e `mode & 0o077 == 0`) e `validar_dir_restrito(caminho)` (`log_dir`/`work_dir`, README §8.12 passo 4: existe, é diretório, é gravável pelo agente e fica fora das pastas do sistema; **não** exige `0700`, porque o `log_dir` e as pastas de log são `0750`, README §8.4 e §13);
  - `validar_caminho_script(caminho, donos, uids_proibidos) -> Optional[str]` (README §8.0 e §8.5): caminho igual ao `realpath` (`CAMINHO_COM_LINK`); dono do arquivo em `donos`; cada diretório até `/` com dono root ou em `donos`; arquivo e diretórios sem escrita de grupo, outros ou do agente, e **sem** pertencer a um UID de `uids_proibidos` (agente e usuários de execução, R-15); `EACCES` vira `SEM_ACESSO`;
  - o executável do interpretador usa `path_guard.validar_executavel(caminho, donos, uid_agente, uids_proibidos, dirs_sss)`, já existente desde o CR-007 (R-15: a mesma cadeia, pode ficar nas pastas do sistema e pode ser link, com o link e o destino conferidos); a plataforma só o envolve;
  - `caminho_final(caminho)` (`realpath` no POSIX);
  - `criar_dir_trabalho(caminho)` (`0700` no POSIX);
  - `instalar_parada(flag)`: handlers de sinal que **apenas** setam a flag (SIGTERM/SIGINT no POSIX). O arquivo `.stop` é verificado pelo laço, não aqui.
- **`modules/plataforma/posix.py`:** as colunas POSIX do README §8.0 e o Popen literal do AGENTS §3.2, com `_child_limits` (somente `os.umask(0o077)` e `resource.setrlimit`: `RLIMIT_CORE` 0 e `RLIMIT_NOFILE` 1024).
  - `identidade_processo`: Linux, campo 22 de `/proc/<pid>/stat` contado **depois do último `)`**; AIX/Solaris, `/proc/<pid>/psinfo`; demais Unix, `sysctl KERN_PROC` **sem `ctypes`** (proibido em todo o projeto, AGENTS §3.2; README §8.0). Onde a leitura não for possível sem `ctypes` (por exemplo, macOS/BSD), retorna `None`. Plataforma sem suporte retorna `None` e o startup check trata `None` como identidade desconhecida (`ORPHAN_PROCESS`).
  - `sinalizar_grupo`: `killpg(pgid, sinal)` (DEV) ou o helper; nunca espera (CR-007: sem `time.sleep` nem `wait()` com prazo).
- O encerramento escalonado é responsabilidade de `executor.pedir_encerramento`/`executor.avancar_encerramento` (F8.1), que consultam `sinalizar_grupo` e `grupo_vivo` em iterações sucessivas. **Não** definir nem chamar `plataforma.encerrar_grupo`: nenhuma função de encerramento aguarda o prazo ou bloqueia.
- **`bin/sss-helper`** (Python 3.6, só biblioteca padrão, sem importar a aplicação; README §8.0): subcomandos `run`, `term`, `kill`, `limpar <pasta_base> <ticket_id>` e `encerrar-ticket <pasta_base> <ticket_id> <kill_grace_s>` (CR-008, R-01 e R-36: a `pasta_base` é validada como absoluta, normalizada, sem link e de dono igual ao próprio usuário), com a validação de argumentos, a checagem de identidade do grupo, a criação do diretório de trabalho do script e os códigos de saída 0/2/3/4/5 (5 = não suportado nesta plataforma). A exceção do AGENTS §3.2 permite `resource.setrlimit` somente em `run`, `os.killpg` somente em `term`/`kill`, e `/proc/<pid>/cwd` ou `pwdx` por caminho absoluto somente em `encerrar-ticket`; cada ação fica restrita a processos do próprio usuário. É copiado pelo root para `/opt/sss/bin/sss-helper` (`IMPLANTACAO.md` §18.1).
- **Integração com o código existente:**
  - `modules/sss_config.py`: a checagem de dono e modo do `secrets.cfg` passa a chamar `plataforma.validar_arquivo_restrito`;
  - `modules/path_guard.py`: a regra de dono/escrita por item (`_checar_dono_e_modo`, `_gravavel_pelo_agente`) passa a chamar `plataforma.validar_caminho_script`, e a resolução usa `plataforma.caminho_final`.
- **Configuração (`sss_config.py`, `config.ini.example`):** `[agent] script_owner_uids` e `[agent] interpretadores` (`LOGICO=caminho`, na allowlist `PYTHON3`, `BASH`, `SH`), conforme o README §12.1. Sem `script_owner_sids` nem `base_script_dirs`.
- **`applications/script_scheduling_service/scripts/test_plataforma.py`:**
  - sinalização sem bloquear (a chamada volta em menos de 0,5 s mesmo com um processo que ignora SIGTERM); grupo com o **neto** vivo depois da saída do líder detectado por `grupo_vivo` e encerrado pelo ciclo não bloqueante do executor; identidade do processo estável e diferente para outro PID; PID inexistente; lock de instância (segunda trava falha); recusa de usuário privilegiado (root, com dublê); arquivo restrito OK e rejeitado; diretório de trabalho restrito; item da árvore gravável rejeitado; parada por sinal seta a flag.
  - `/proc/<pid>/stat` com `)` no nome do comando;
  - `gravar_estado`/`ler_estado` atômicos, inclusive `.sss_spawn` (CR-008, R-01); `encerrar_ticket` em DEV encerrando um processo de teste (e o neto) cujo diretório atual está na pasta do ticket, sem tocar em outro processo do mesmo usuário fora dela; `espaco_livre_mb` com `os.statvfs` simulado; `validar_execucao` com dublês de `sudo -n -l`, do helper e dos usuários; `validar_caminho_script` com link simbólico, `EACCES` e dono proibido; executável do interpretador por `validar_executavel`.
- **`applications/script_scheduling_service/scripts/test_sss_helper.py`** (AGENTS §7.4): uso inválido (2); especificação inválida; `term`/`kill` com identidade divergente (3) e com grupo vazio (0); `limpar` e `encerrar-ticket` com `pasta_base` inválida (relativa, com `..`, com link, de outro dono) recusados com 2 e sem seguir links; `encerrar-ticket` com código 5 quando não há `/proc/<pid>/cwd` nem `pwdx` (dublê) (CR-008, R-01 e R-36); `run` executado direto (sem `sudo`, com o próprio usuário) num script de teste, com `cwd`, `umask` e entrada padrão nula.
- **`scripts/test_py36_compat.py`:** fora de `modules/plataforma/` são proibidos `os.killpg`, `os.setsid`, `resource`, `fcntl`, acesso a caminhos sob `/proc`, `pwdx` e `sys.platform`; em `bin/sss-helper`, somente `resource`, `os.killpg`, `/proc/` e `pwdx` são permitidos pela exceção estreita do AGENTS §3.2. `ctypes` e `msvcrt` são proibidos em todo o projeto. A checagem compila também `bin/sss-helper`, apesar de não ter sufixo `.py`, e verifica que os demais primitivos listados não aparecem nele.

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
- [ ] A varredura do `test_py36_compat.py` não encontra primitivas fora de `modules/plataforma/`, salvo a allowlist exata do helper; testes negativos confirmam que `os.setsid`, `fcntl` e `sys.platform` continuam proibidos nele, e o helper sem extensão é compilado.

## Verificação
`python -m unittest discover -s scripts -p "test_plataforma.py" -v`, depois a suíte completa.

## Saída
Relatório AGENTS.md §9.
