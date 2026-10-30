# -*- coding: utf-8 -*-
"""Implementacao POSIX da camada de plataforma (README §8.0; CR-005: Linux e demais Unix).

Unico lugar do projeto com primitivas dependentes do SO: os.killpg, os.setsid,
resource, fcntl, leituras sob /proc e sys.platform (AGENTS §3.2). Nada aqui espera um prazo ou
bloqueia, exceto stop_ticket, que roda so no startup check, antes do laco (README §8.0).
Modulo puro: nao importa gluon nem a aplicacao (so a biblioteca padrao).
"""
import errno
import fcntl
import json
import logging
import os
import resource
import shutil
import signal
import stat
import subprocess
import sys
import time

_log = logging.getLogger("sss_scheduler")

NAME = "UNIX" if not sys.platform.startswith("linux") else "LINUX"

# Operacoes de arquivo das pastas do ticket (CR-032, D7): rodam num processo proprio, com a conta do agente.
TICKET_FILES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ticket_files.py")
# Codigos do put-input (CR-020c, README §8.14).
INPUT_EXISTS = 9
INPUT_SPACE = 10
INPUT_HASH = 11
# Codigos do pack (CR-012, README §8.13).
OUTPUT_EMPTY = 6
OUTPUT_TOO_MANY_FILES = 7
OUTPUT_TOO_MANY_BYTES = 8
# Ambiente minimo das operacoes de arquivo e dos comandos curtos: nada herdado do agente (AGENTS §3.2).
_ENV_MINIMAL = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
# Politica fixa de limites do filho (README §8.4): sem core dump (os demais limites sao os da conta, CR-036),
# aplicada no preexec_fn.
# CR-036 (D2): so o core dump desligado; o limite de arquivos abertos (antes fixo em 1024) e o da conta.
DEFAULT_RLIMITS = {"RLIMIT_CORE": (0, 0)}
_ALLOWED_RLIMITS = ("RLIMIT_CORE", "RLIMIT_NOFILE", "RLIMIT_CPU", "RLIMIT_AS", "RLIMIT_FSIZE",
                       "RLIMIT_NPROC", "RLIMIT_DATA", "RLIMIT_STACK")
# Pastas do sistema (README §8.5): nem script nem log_dir/work_dir podem ficar nelas.
SYSTEM_DIRS = ("/bin", "/sbin", "/usr", "/lib", "/lib32", "/lib64", "/libx32",
                     "/etc", "/boot", "/proc", "/sys", "/dev", "/root")


class InstanceAlreadyRunning(RuntimeError):
    """Outra instancia do agente ja tem a trava (lock_instance)."""


class Process(object):
    """Grupo de processos de um ticket: lider (pid = pgid, start_new_session) e sua identidade."""

    def __init__(self, pid, identity, popen=None, no_identity=False):
        self.pid = pid
        self.pgid = pid
        self.identity = identity
        self.popen = popen
        # Identidade desconhecida com PID vivo: nunca recebe sinal (WARN ORFAO_SEM_IDENTIDADE).
        self.no_identity = no_identity

    def __repr__(self):
        return "Processo(pid=%s, identidade=%s)" % (self.pid, self.identity)


# -----------------------------------------------------------------------------
# Execucao
# -----------------------------------------------------------------------------

def _rlimits(spec):
    limits = dict(DEFAULT_RLIMITS)
    for name, value in (spec.get("rlimits") or {}).items():
        if name not in _ALLOWED_RLIMITS:
            raise ValueError("Limite de recurso nao permitido: %s" % name)
        limits[name] = (int(value[0]), int(value[1]))
    return [(getattr(resource, name), pair) for name, pair in sorted(limits.items())]


def _child_limits(limits):
    """preexec_fn: somente os.umask e resource.setrlimit (AGENTS §3.2; sem threads no daemon)."""
    def _child_limits():
        os.umask(0o077)
        for resource_value, pair in limits:
            resource.setrlimit(resource_value, pair)
    return _child_limits


def start_process(spec, log_fd):
    """Inicia o script num grupo proprio (start_new_session) com stdout/stderr no arquivo de log: Popen direto
    com argv, cwd, env e os limites, com a conta do agente (CR-032, D7). Nunca usa shell nem PIPE de saida
    (AGENTS §3.2).
    """
    p = subprocess.Popen(list(spec["argv"]), shell=False, start_new_session=True, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=log_fd, stderr=subprocess.STDOUT,
                         cwd=spec.get("cwd"), env=dict(spec.get("env") or {}),
                         preexec_fn=_child_limits(_rlimits(spec)))
    return Process(p.pid, process_identity(p.pid), popen=p)


def signal_group(process, signal_value):
    """Envia o sinal ao grupo do processo, sem esperar (CR-007, R-04). True se o pedido saiu.

    Identidade desconhecida: nao sinaliza (False). Lider vivo com outra identidade (PID reciclado):
    nao sinaliza. ESRCH (grupo vazio) devolve False.
    """
    if process.no_identity:
        return False
    if process_exists(process.pid):
        current = process_identity(process.pid)
        if process.identity is not None and current is not None and current != process.identity:
            return False
    try:
        os.killpg(process.pgid, signal_value)
        return True
    except ProcessLookupError:  # fluxo previsto (AGENTS §6): ESRCH = grupo vazio
        return False


def group_alive(process):
    """True enquanto o grupo tem membros, inclusive netos depois da saida do lider (CR-007, R-02).

    Coleta o lider filho direto com poll() (sem esperar) para que um zumbi nao conte como vivo.
    """
    if process.popen is not None:
        process.popen.poll()
    try:
        os.killpg(process.pgid, 0)
        return True
    except ProcessLookupError:  # fluxo previsto: grupo sem membros
        return False
    except PermissionError:  # membro de outra conta no grupo: o grupo existe
        return True


def reopen_group(state):
    """Grupo de um ticket que nao e filho do daemon (startup check, README §8.12 passo 9), sem wait().

    estado: o .sss_proc (pid, process_start). PID vivo com outra identidade: PID
    reciclado, o grupo antigo acabou (None). PID vivo sem identidade legivel: Processo no_identity,
    que nao recebe sinal. Lider morto com o grupo ainda vivo (netos): Processo para o executor encerrar.
    """
    pid = int(state["pid"])
    expected = state.get("process_start")
    if process_exists(pid):
        current = process_identity(pid)
        if current is None:
            _log.warning("ORFAO_SEM_IDENTIDADE pid=%s: identidade ilegivel nesta plataforma", pid,
                         extra={"action": "STARTUP"})
            return Process(pid, None, no_identity=True)
        if expected is not None and int(expected) != current:
            return None
        return Process(pid, current)
    process = Process(pid, expected)
    return process if group_alive(process) else None


# -----------------------------------------------------------------------------
# Identidade e existencia de processos
# -----------------------------------------------------------------------------

def _linux_starttime(content):
    """Campo 22 (starttime) de /proc/<pid>/stat, contado depois do ULTIMO ')' (o comando pode ter ')')."""
    rest = content[content.rindex(")") + 2:].split()
    # O resto comeca no campo 3 (state): o campo 22 fica na posicao 22 - 3.
    return int(rest[19])


def process_identity(pid):
    """Identidade contra PID reciclado: no Linux, o starttime; demais Unix sem leitura segura: None."""
    if NAME != "LINUX":
        # psinfo/sysctl exigiriam layout binario por sistema (sem FFI no projeto): identidade desconhecida.
        return None
    try:
        with open("/proc/%d/stat" % int(pid), "r") as f:
            return _linux_starttime(f.read())
    except (OSError, ValueError, IndexError):  # fluxo previsto: identidade desconhecida
        return None


def process_exists(pid):
    """os.kill(pid, 0): EPERM (processo de outro usuario) conta como existente."""
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:  # fluxo previsto: PID inexistente
        return False
    except PermissionError:  # EPERM: processo de outro usuario existe
        return True


# -----------------------------------------------------------------------------
# Estado local, diretorios e espaco
# -----------------------------------------------------------------------------

def write_state(path, data):
    """JSON em arquivo temporario + rename, 0600 (.sss_spawn, .sss_proc, .sss_result; CR-008, R-01)."""
    tmp = "%s.tmp.%d" % (path, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.rename(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:  # temporario ja ausente; a excecao original sobe
            pass
        raise


def read_state(path):
    """Conteudo do arquivo de estado, ou None se nao existir."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:  # fluxo previsto: estado ainda nao gravado
        return None


def create_work_dir(path):
    """work_dir/ticket_<id>/ do agente com 0700 (estado local; README §8.4)."""
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def free_space_mb(path):
    """Espaco livre para usuario comum em caminho (f_bavail x f_frsize), em MiB (CR-008, R-25)."""
    st = os.statvfs(path)
    return int(st.f_bavail * st.f_frsize // (1024 * 1024))


def final_path(path):
    """Caminho resolvido (realpath no POSIX)."""
    return os.path.realpath(path)


# -----------------------------------------------------------------------------
# Instancia, privilegio e parada
# -----------------------------------------------------------------------------

class _Lock(object):
    def __init__(self, fd, path):
        self.fd = fd
        self.path = path


def lock_instance(path):
    """Trava exclusiva nao bloqueante (fcntl.flock LOCK_EX | LOCK_NB); outra instancia: InstanceAlreadyRunning."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, PermissionError):
        os.close(fd)
        raise InstanceAlreadyRunning("Outra instancia do agente ja esta em execucao (%s)" % path)
    os.ftruncate(fd, 0)
    os.write(fd, ("%d\n" % os.getpid()).encode("ascii"))
    return _Lock(fd, path)


def release_instance(lock):
    if lock is None:
        return
    try:
        fcntl.flock(lock.fd, fcntl.LOCK_UN)
    finally:
        os.close(lock.fd)


def _normalize_locale(name):
    return (name or "").strip().lower().replace("-", "")


def _locale_command():
    """O `locale` em /usr/bin (o comum) ou, sem ele, o do PATH do agente (outros Unix)."""
    if os.path.isfile("/usr/bin/locale"):
        return "/usr/bin/locale"
    return shutil.which("locale") or "/usr/bin/locale"


def locale_available(name, run=None):
    """True se o locale consta em `locale -a` (README §8.12 passo 2; CR-007 R-17). C.UTF-8 = C.utf8."""
    run = run or _run_short
    try:
        code, output = run([_locale_command(), "-a"])
    except OSError:  # sem o comando locale: nao da para confirmar
        return False
    target = _normalize_locale(name)
    return code == 0 and any(_normalize_locale(l) == target for l in output.splitlines())


# Ordem dos substitutos quando o locale pedido falta (normalizados por _normalize_locale).
_LOCALE_FALLBACK = ("c.utf8", "en_us.utf8", "pt_br.utf8")


def pick_child_locale(name, run=None):
    """Locale dos scripts: o pedido, se consta em `locale -a`; senao, o primeiro UTF-8 disponivel, nesta ordem:
    C, en_US, pt_BR e os demais em ordem alfabetica (ex.: CentOS 6, sem C.UTF-8). None: nenhum UTF-8."""
    run = run or _run_short
    try:
        code, output = run([_locale_command(), "-a"])
    except OSError:  # sem o comando locale: nao da para escolher
        return None
    if code != 0:
        return None
    found = {}
    for line in output.splitlines():
        if line.strip():
            found.setdefault(_normalize_locale(line), line.strip())
    if _normalize_locale(name) in found:
        return name
    for preferred in _LOCALE_FALLBACK:
        if preferred in found:
            return found[preferred]
    others = sorted(found[key] for key in found if key.endswith(".utf8"))
    return others[0] if others else None


def interpreter_versions(names=("python", "python3"), run=None, which=None):
    """Para cada nome, (nome, caminho no PATH do agente ou None, versao "X.Y.Z" ou None): o que o cadastro
    python/python3 usaria neste servidor. O Python 2 escreve a versao no stderr (o _run_short junta os dois)."""
    run = run or _run_short
    which = which or shutil.which
    found = []
    for name in names:
        path = which(name)
        version = None
        if path:
            try:
                code, output = run([path, "-V"])
            except (OSError, subprocess.SubprocessError):  # sem como rodar: so o caminho
                code, output = 1, ""
            words = output.split()
            if code == 0 and len(words) >= 2 and words[0] == "Python":
                version = words[1]
        found.append((name, path, version))
    return found


def is_privileged_user():
    return os.geteuid() == 0


def install_stop_handler(flag):
    """SIGTERM/SIGINT so acionam a flag (um objeto com set(), ex.: threading.Event); nada mais."""
    def _handler(signum, frame):
        flag.set()
    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


# -----------------------------------------------------------------------------
# Validacoes de arquivos, diretorios e caminhos
# -----------------------------------------------------------------------------

def validate_restricted_file(path):
    """Segredos (README §4.1): arquivo regular, dono = euid e mode & 0o077 == 0.

    Devolve (codigo, st): codigo None se valido, ou 'NAO_REGULAR', 'DONO_INVALIDO' ou 'PERMISSAO_INSEGURA'.
    """
    st = os.stat(path)
    if not stat.S_ISREG(st.st_mode):
        return "NAO_REGULAR", st
    if st.st_uid != os.geteuid():
        return "DONO_INVALIDO", st
    if st.st_mode & 0o077:
        return "PERMISSAO_INSEGURA", st
    return None, st


def _inside(path, folder):
    return os.path.commonpath([path, folder]) == folder


def validate_restricted_dir(path):
    """log_dir/work_dir (README §8.12 passo 4): existe, e diretorio, e gravavel e fica fora das pastas do
    sistema. Nao exige 0700 (log_dir e as pastas de log sao 0750). Devolve o codigo da falha ou None."""
    if not isinstance(path, str) or not path.startswith("/"):
        return "RELATIVE_PATH"
    real = os.path.realpath(path)
    if any(_inside(target, d) for target in (path, real) for d in SYSTEM_DIRS):
        return "SYSTEM_DIR"
    if not os.path.exists(real):
        return "NOT_FOUND"
    if not os.path.isdir(real):
        return "NAO_E_DIRETORIO"
    if not os.access(real, os.W_OK | os.X_OK):
        return "SEM_ESCRITA"
    return None


def ensure_dir(path, mode):
    """CR-032 (D12): cria a pasta que falta (e as de cima), com o modo dado mesmo sob a umask 077 do launcher.
    So cria quando nada existe no caminho (nem link): uma pasta existente fica para validate_restricted_dir.
    Devolve True quando criou."""
    if os.path.lexists(path):
        return False
    os.makedirs(path, mode)
    os.chmod(path, mode)
    return True


def _stat_code(path):
    try:
        return os.stat(path), None
    except OSError as e:
        if e.errno in (errno.EACCES, errno.EPERM):
            return None, "NO_ACCESS"
        return None, "NOT_FOUND"


def validate_script_path(path):
    """Script no servidor do agente (README §8.0, §8.5; CR-011): vale o arquivo real (o caminho pode ter link
    simbolico), que precisa existir, ser regular e nao ser gravavel por grupo nem por outros. Ciclo de links:
    NOT_FOUND; EACCES: NO_ACCESS. Devolve o codigo ou None."""
    real = final_path(path)
    if os.path.islink(real):
        return "NOT_FOUND"  # realpath parou num link: ciclo ou destino inexistente
    st, code = _stat_code(real)
    if code:
        return code
    if not stat.S_ISREG(st.st_mode):
        return "NOT_A_FILE"
    if st.st_mode & 0o022:
        return "GROUP_OTHER_WRITABLE"
    return None


# -----------------------------------------------------------------------------
# Comandos curtos
# -----------------------------------------------------------------------------

def _run_short(argv):
    """Comando curto (locale -a na subida, list-input e clean-output): devolve (codigo, saida).

    A saida e lida em bytes e decodificada como UTF-8 com substituicao: o `locale -a` de sistemas antigos
    (ex.: CentOS 6) lista nomes em Latin-1 (`bokm\\xe5l`), que no modo texto derrubavam a subida do agente."""
    p = subprocess.run(argv, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, env=dict(_ENV_MINIMAL), timeout=30)
    return p.returncode, (p.stdout or b"").decode("utf-8", "replace")


# -----------------------------------------------------------------------------
# Pasta de saida do ticket (CR-012, README §8.13)
# -----------------------------------------------------------------------------

def _files_argv(subcommand, args):
    """ticket_files.py pelo mesmo interpretador, isolado (-I), com a conta do agente."""
    return [sys.executable, "-I", TICKET_FILES, subcommand] + [str(a) for a in args]


def create_output_dir(base, relative):
    """Cria base e cada nivel do relativo com 0700, recusando link ou item que nao seja diretorio do proprio
    usuario."""
    return _create_ticket_dir(base, relative, "pasta de saida")


def create_script_work_dir(base, relative):
    """Pasta de trabalho do ticket (CR-019, README §8.15): as regras de create_output_dir."""
    return _create_ticket_dir(base, relative, "pasta de trabalho")


def _create_ticket_dir(base, relative, name):
    current = None
    for part in [base] + relative.split("/"):
        current = part if current is None else os.path.join(current, part)
        if current == base:
            os.makedirs(base, 0o700, exist_ok=True)
        else:
            try:
                os.mkdir(current, 0o700)
            except FileExistsError:  # fluxo previsto: nivel ja criado por outro ticket do mesmo minuto
                pass
        st = os.lstat(current)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid():
            raise RuntimeError("%s com item que nao e diretorio do agente" % name)
    os.chmod(current, 0o700)
    return current


def create_input_dir(base, relative):
    """Pasta de entrada (CR-014, README §8.14): base e a pasta do script com 0700 se nao existirem, recusando link
    ou item que nao seja diretorio do proprio usuario. A pasta e permanente: a existente fica como esta."""
    os.makedirs(base, 0o700, exist_ok=True)
    dir_value = os.path.join(base, relative)
    try:
        os.mkdir(dir_value, 0o700)
    except FileExistsError:  # fluxo previsto: a pasta do script ja existe (tickets anteriores)
        pass
    for item in (base, dir_value):
        st = os.lstat(item)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid():
            raise RuntimeError("pasta de entrada com item que nao e diretorio do agente")
    return dir_value


def create_files_dirs(base, relative):
    """Pasta de arquivos (CR-037): base, a pasta do script e as subpastas inputs e outputs, com 0700 se nao
    existirem, recusando link ou item que nao seja diretorio do proprio usuario. Permanentes, como a de entrada:
    o agente nunca apaga nem empacota nada aqui. Devolve (inputs, outputs)."""
    folder = create_input_dir(base, relative)
    created = []
    for name in ("inputs", "outputs"):
        sub = os.path.join(folder, name)
        try:
            os.mkdir(sub, 0o700)
        except FileExistsError:  # fluxo previsto: as subpastas ja existem (tickets anteriores)
            pass
        st = os.lstat(sub)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid():
            raise RuntimeError("pasta de arquivos com item que nao e diretorio do agente")
        created.append(sub)
    return created[0], created[1]


def start_pack(base, relative, max_bytes, max_files, destination_fd):
    """Inicia o pack num grupo proprio, com o zip no descritor destination_fd; nao espera.

    O agente acompanha por processo.popen.poll() e, no prazo, encerra com signal_group (README §8.13).
    """
    argv = _files_argv("pack", [base, relative, int(max_bytes), int(max_files)])
    p = subprocess.Popen(argv, shell=False, start_new_session=True, close_fds=True, stdin=subprocess.DEVNULL,
                         stdout=destination_fd, stderr=subprocess.DEVNULL, env=dict(_ENV_MINIMAL))
    return Process(p.pid, process_identity(p.pid), popen=p)


def start_put_input(base, script, relative, name, replace, sha256, size, source_fd):
    """Inicia o put-input num grupo proprio, com o arquivo baixado em source_fd na entrada padrao; nao
    espera (CR-020c, README §8.14). O agente acompanha por popen.poll() e encerra no prazo com signal_group."""
    argv = _files_argv("put-input", [base, script, relative or "-", name, replace, sha256, int(size)])
    p = subprocess.Popen(argv, shell=False, start_new_session=True, close_fds=True, stdin=source_fd,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(_ENV_MINIMAL))
    return Process(p.pid, process_identity(p.pid), popen=p)


def list_input(base, script, max_items):
    """Retrato da pasta de entrada do script pelo list-input (CR-020c): {files, count, truncated}."""
    code, output = _run_short(_files_argv("list-input", [base, script, int(max_items)]))
    if code != 0:
        raise RuntimeError("list-input falhou (codigo %s)" % code)
    try:
        return json.loads(output.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise RuntimeError("list-input sem retrato")


def clean_output(base, relative):
    """Remove a pasta de saida do ticket pelo clean-output (sem seguir links)."""
    code, _output = _run_short(_files_argv("clean-output", [base, relative]))
    if code != 0:
        raise RuntimeError("clean-output falhou (codigo %s)" % code)


# -----------------------------------------------------------------------------
# Caso "talvez iniciado" do startup check (CR-008, R-01)
# -----------------------------------------------------------------------------

def _pids_in_dir(folder):
    """PIDs do proprio usuario cujo diretorio atual esta em pasta (Linux: /proc/<pid>/cwd)."""
    pids = []
    my_uid = os.geteuid()
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) == os.getpid():
            continue
        try:
            if os.stat("/proc/" + name).st_uid != my_uid:
                continue
            cwd = os.readlink("/proc/%s/cwd" % name)
        except OSError:  # fluxo previsto: processo saiu durante a varredura
            continue
        if _inside(os.path.normpath(cwd), folder):
            pids.append(int(name))
    return pids


def stop_ticket(base_dir, ticket_id, kill_grace_s):
    """Encerra os processos do ticket "talvez iniciado" (.sss_spawn sem .sss_proc): os do proprio usuario cujo
    diretorio atual esta em <base_dir>/ticket_<id>. Devolve 'OK' ou 'UNSUPPORTED'. Unica operacao que espera
    (kill_grace_s), porque roda so antes do laco.
    """
    if NAME != "LINUX" or not os.path.isdir("/proc/self"):
        return "UNSUPPORTED"
    dir_value = os.path.normpath(os.path.join(base_dir, "ticket_%d" % int(ticket_id)))
    for signal_value in (signal.SIGTERM, signal.SIGKILL):
        pids = _pids_in_dir(dir_value)
        for pid in pids:
            try:
                os.kill(pid, signal_value)
            except ProcessLookupError:  # fluxo previsto: processo ja saiu
                pass
        if not pids or signal_value == signal.SIGKILL:
            break
        limit = time.monotonic() + min(int(kill_grace_s), 300)
        while time.monotonic() < limit and _pids_in_dir(dir_value):
            time.sleep(0.1)
    return "OK"
