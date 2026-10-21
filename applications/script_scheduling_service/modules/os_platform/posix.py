# -*- coding: utf-8 -*-
"""Implementacao POSIX da camada de plataforma (README §8.0; CR-005: Linux e demais Unix).

Unico lugar do projeto (fora do helper) com primitivas dependentes do SO: os.killpg, os.setsid,
resource, fcntl, leituras sob /proc e sys.platform (AGENTS §3.2). Nada aqui espera um prazo ou
bloqueia, exceto stop_ticket, que roda so no startup check, antes do laco (README §8.0).
Modulo puro: nao importa gluon nem a aplicacao (so a biblioteca padrao).
"""
import errno
import fcntl
import json
import logging
import os
import pwd
import resource
import signal
import stat
import subprocess
import sys
import time

_log = logging.getLogger("sss_scheduler")

NAME = "UNIX" if not sys.platform.startswith("linux") else "LINUX"

HELPER = "/opt/sss/bin/sss-helper"
SUDO = "/usr/bin/sudo"
# Copia do helper no pacote (bin/sss-helper): em DEV sem usuario de execucao, os subcomandos da saida
# (CR-012) rodam com o proprio usuario do agente, pela mesma implementacao do servidor.
PACKAGE_HELPER = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                             "..", "..", "..", "..", "bin", "sss-helper"))
# Codigos do helper empacotar (CR-012, README §8.0 e §8.13).
OUTPUT_EMPTY = 6
OUTPUT_TOO_MANY_FILES = 7
OUTPUT_TOO_MANY_BYTES = 8
# Ambiente minimo do sudo/helper: nada herdado do agente (AGENTS §3.2, README §8.6).
_ENV_HELPER = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
# Politica fixa de limites do filho (README §8.4): sem core dump e com descritores limitados. O executor
# a manda na especificacao (helper) e o DEV a aplica no preexec_fn.
DEFAULT_RLIMITS = {"RLIMIT_CORE": (0, 0), "RLIMIT_NOFILE": (1024, 1024)}
_ALLOWED_RLIMITS = ("RLIMIT_CORE", "RLIMIT_NOFILE", "RLIMIT_CPU", "RLIMIT_AS", "RLIMIT_FSIZE",
                       "RLIMIT_NPROC", "RLIMIT_DATA", "RLIMIT_STACK")
# Pastas do sistema (README §8.5): nem script nem log_dir/work_dir podem ficar nelas.
SYSTEM_DIRS = ("/bin", "/sbin", "/usr", "/lib", "/lib32", "/lib64", "/libx32",
                     "/etc", "/boot", "/proc", "/sys", "/dev", "/root")
UNSUPPORTED_CODE = 5

# Pedidos ao helper (term/kill) ainda nao coletados: signal_group nunca espera o helper terminar.
_helper_requests = []


class InstanceAlreadyRunning(RuntimeError):
    """Outra instancia do agente ja tem a trava (lock_instance)."""


class FailureAfterSpawn(RuntimeError):
    """O Popen do sudo/helper retornou, mas a entrega da especificacao falhou (CR-008, R-01): o grupo
    existe e vai em processo, para o executor encerra-lo sem esperar."""

    def __init__(self, processo, causa):
        RuntimeError.__init__(self, causa.__class__.__name__)
        self.process = processo
        self.cause = causa


class Process(object):
    """Grupo de processos de um ticket: lider (pid = pgid, start_new_session) e sua identidade."""

    def __init__(self, pid, identidade, popen=None, usuario_execucao=None, sem_identidade=False):
        self.pid = pid
        self.pgid = pid
        self.identity = identidade
        self.popen = popen
        self.exec_user = usuario_execucao
        # Identidade desconhecida com PID vivo: nunca recebe sinal (WARN ORFAO_SEM_IDENTIDADE).
        self.no_identity = sem_identidade

    def __repr__(self):
        return "Processo(pid=%s, identidade=%s, usuario=%s)" % (self.pid, self.identity, self.exec_user)


# -----------------------------------------------------------------------------
# Execucao
# -----------------------------------------------------------------------------

def _rlimits(especificacao):
    limites = dict(DEFAULT_RLIMITS)
    for nome, valor in (especificacao.get("rlimits") or {}).items():
        if nome not in _ALLOWED_RLIMITS:
            raise ValueError("Limite de recurso nao permitido: %s" % nome)
        limites[nome] = (int(valor[0]), int(valor[1]))
    return [(getattr(resource, nome), par) for nome, par in sorted(limites.items())]


def _child_limits(limites):
    """preexec_fn em DEV: somente os.umask e resource.setrlimit (AGENTS §3.2; sem threads no daemon)."""
    def _child_limits():
        os.umask(0o077)
        for recurso, par in limites:
            resource.setrlimit(recurso, par)
    return _child_limits


def start_process(especificacao, log_fd, usuario_execucao=None):
    """Inicia o script num grupo proprio (start_new_session) com stdout/stderr no arquivo de log.

    Com exec_user: sudo -n -u <usuario> -- /opt/sss/bin/sss-helper run, com a especificacao JSON
    (ticket_id, argv, env, rlimits, base_dir) pela entrada padrao. Sem ele (so DEV): Popen direto com
    argv, cwd, env e os limites. Nunca usa shell nem PIPE de saida (AGENTS §3.2).
    """
    if usuario_execucao:
        argv = [SUDO, "-n", "-u", usuario_execucao, "--", HELPER, "run"]
        p = subprocess.Popen(argv, shell=False, start_new_session=True, close_fds=True, stdin=subprocess.PIPE,
                             stdout=log_fd, stderr=subprocess.STDOUT, env=dict(_ENV_HELPER))
        try:
            try:
                p.stdin.write(json.dumps(especificacao, sort_keys=True).encode("utf-8"))
            finally:
                p.stdin.close()
        except Exception as e:  # noqa: BLE001 - qualquer falha aqui deixa um grupo vivo sem registro
            raise FailureAfterSpawn(Process(p.pid, process_identity(p.pid), popen=p,
                                          usuario_execucao=usuario_execucao), e)
    else:
        p = subprocess.Popen(list(especificacao["argv"]), shell=False, start_new_session=True, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=log_fd, stderr=subprocess.STDOUT,
                             cwd=especificacao.get("cwd"), env=dict(especificacao.get("env") or {}),
                             preexec_fn=_child_limits(_rlimits(especificacao)))
    return Process(p.pid, process_identity(p.pid), popen=p, usuario_execucao=usuario_execucao)


def _reap_helper_requests():
    """Coleta (sem esperar) os helpers term/kill ja terminados e registra os que falharam."""
    restantes = []
    for argv, p in _helper_requests:
        rc = p.poll()
        if rc is None:
            restantes.append((argv, p))
        elif rc not in (0,):
            _log.warning("helper %s terminou com codigo %s", argv[-3], rc, extra={"action": "SINAL"})
    _helper_requests[:] = restantes


def signal_group(processo, sinal):
    """Envia o sinal ao grupo do processo, sem esperar (CR-007, R-04). True se o pedido saiu.

    Identidade desconhecida: nao sinaliza (False). Lider vivo com outra identidade (PID reciclado):
    nao sinaliza. ESRCH (grupo vazio) devolve False. Com usuario de execucao, o sinal vai pelo helper
    term/kill <pgid> <process_start>, iniciado sem esperar; o resultado e coletado nas proximas chamadas.
    """
    _reap_helper_requests()
    if processo.no_identity:
        return False
    if processo.exec_user:
        sub = "kill" if sinal == signal.SIGKILL else "term"
        argv = [SUDO, "-n", "-u", processo.exec_user, "--", HELPER, sub, str(processo.pgid),
                str(processo.identity if processo.identity is not None else 0)]
        p = subprocess.Popen(argv, shell=False, close_fds=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(_ENV_HELPER))
        _helper_requests.append((argv, p))
        return True
    if process_exists(processo.pid):
        atual = process_identity(processo.pid)
        if processo.identity is not None and atual is not None and atual != processo.identity:
            return False
    try:
        os.killpg(processo.pgid, sinal)
        return True
    except ProcessLookupError:  # fluxo previsto (AGENTS §6): ESRCH = grupo vazio
        return False


def group_alive(processo):
    """True enquanto o grupo tem membros, inclusive netos depois da saida do lider (CR-007, R-02).

    Coleta o lider filho direto com poll() (sem esperar) para que um zumbi nao conte como vivo.
    """
    if processo.popen is not None:
        processo.popen.poll()
    try:
        os.killpg(processo.pgid, 0)
        return True
    except ProcessLookupError:  # fluxo previsto: grupo sem membros
        return False
    except PermissionError:
        # Membros de outro usuario (usuario de execucao): o grupo existe.
        return True


def reopen_group(estado):
    """Grupo de um ticket que nao e filho do daemon (startup check, README §8.12 passo 9), sem wait().

    estado: o .sss_proc (pid, process_start, exec_user). PID vivo com outra identidade: PID
    reciclado, o grupo antigo acabou (None). PID vivo sem identidade legivel: Processo no_identity,
    que nao recebe sinal. Lider morto com o grupo ainda vivo (netos): Processo para o executor encerrar.
    """
    pid = int(estado["pid"])
    esperada = estado.get("process_start")
    usuario = estado.get("exec_user")
    if process_exists(pid):
        atual = process_identity(pid)
        if atual is None:
            _log.warning("ORFAO_SEM_IDENTIDADE pid=%s: identidade ilegivel nesta plataforma", pid,
                         extra={"action": "STARTUP"})
            return Process(pid, None, usuario_execucao=usuario, sem_identidade=True)
        if esperada is not None and int(esperada) != atual:
            return None
        return Process(pid, atual, usuario_execucao=usuario)
    processo = Process(pid, esperada, usuario_execucao=usuario)
    return processo if group_alive(processo) else None


# -----------------------------------------------------------------------------
# Identidade e existencia de processos
# -----------------------------------------------------------------------------

def _linux_starttime(conteudo):
    """Campo 22 (starttime) de /proc/<pid>/stat, contado depois do ULTIMO ')' (o comando pode ter ')')."""
    resto = conteudo[conteudo.rindex(")") + 2:].split()
    # O resto comeca no campo 3 (state): o campo 22 fica na posicao 22 - 3.
    return int(resto[19])


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

def write_state(caminho, dados):
    """JSON em arquivo temporario + rename, 0600 (.sss_spawn, .sss_proc, .sss_result; CR-008, R-01)."""
    tmp = "%s.tmp.%d" % (caminho, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dados, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.rename(tmp, caminho)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:  # temporario ja ausente; a excecao original sobe
            pass
        raise


def read_state(caminho):
    """Conteudo do arquivo de estado, ou None se nao existir."""
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:  # fluxo previsto: estado ainda nao gravado
        return None


def create_work_dir(caminho):
    """work_dir/ticket_<id>/ do agente com 0700 (estado local; README §8.4)."""
    os.makedirs(caminho, mode=0o700, exist_ok=True)
    os.chmod(caminho, 0o700)
    return caminho


def free_space_mb(caminho):
    """Espaco livre para usuario comum em caminho (f_bavail x f_frsize), em MiB (CR-008, R-25)."""
    st = os.statvfs(caminho)
    return int(st.f_bavail * st.f_frsize // (1024 * 1024))


def final_path(caminho):
    """Caminho resolvido (realpath no POSIX)."""
    return os.path.realpath(caminho)


# -----------------------------------------------------------------------------
# Instancia, privilegio e parada
# -----------------------------------------------------------------------------

class _Lock(object):
    def __init__(self, fd, caminho):
        self.fd = fd
        self.path = caminho


def lock_instance(caminho):
    """Trava exclusiva nao bloqueante (fcntl.flock LOCK_EX | LOCK_NB); outra instancia: InstanceAlreadyRunning."""
    fd = os.open(caminho, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, PermissionError):
        os.close(fd)
        raise InstanceAlreadyRunning("Outra instancia do agente ja esta em execucao (%s)" % caminho)
    os.ftruncate(fd, 0)
    os.write(fd, ("%d\n" % os.getpid()).encode("ascii"))
    return _Lock(fd, caminho)


def release_instance(trava):
    if trava is None:
        return
    try:
        fcntl.flock(trava.fd, fcntl.LOCK_UN)
    finally:
        os.close(trava.fd)


def _normalize_locale(nome):
    return (nome or "").strip().lower().replace("-", "")


def locale_available(nome, executar=None):
    """True se o locale consta em `locale -a` (README §8.12 passo 2; CR-007 R-17). C.UTF-8 = C.utf8."""
    executar = executar or _run_short
    try:
        codigo, saida = executar(["/usr/bin/locale", "-a"])
    except OSError:  # sem o comando locale: nao da para confirmar
        return False
    alvo = _normalize_locale(nome)
    return codigo == 0 and any(_normalize_locale(l) == alvo for l in saida.splitlines())


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

def validate_restricted_file(caminho):
    """Segredos (README §4.1): arquivo regular, dono = euid e mode & 0o077 == 0.

    Devolve (codigo, st): codigo None se valido, ou 'NAO_REGULAR', 'DONO_INVALIDO' ou 'PERMISSAO_INSEGURA'.
    """
    st = os.stat(caminho)
    if not stat.S_ISREG(st.st_mode):
        return "NAO_REGULAR", st
    if st.st_uid != os.geteuid():
        return "DONO_INVALIDO", st
    if st.st_mode & 0o077:
        return "PERMISSAO_INSEGURA", st
    return None, st


def _inside(caminho, pasta):
    return os.path.commonpath([caminho, pasta]) == pasta


def validate_restricted_dir(caminho):
    """log_dir/work_dir (README §8.12 passo 4): existe, e diretorio, e gravavel e fica fora das pastas do
    sistema. Nao exige 0700 (log_dir e as pastas de log sao 0750). Devolve o codigo da falha ou None."""
    if not isinstance(caminho, str) or not caminho.startswith("/"):
        return "RELATIVE_PATH"
    real = os.path.realpath(caminho)
    if any(_inside(alvo, d) for alvo in (caminho, real) for d in SYSTEM_DIRS):
        return "SYSTEM_DIR"
    if not os.path.exists(real):
        return "NOT_FOUND"
    if not os.path.isdir(real):
        return "NAO_E_DIRETORIO"
    if not os.access(real, os.W_OK | os.X_OK):
        return "SEM_ESCRITA"
    return None


def _stat_code(caminho):
    try:
        return os.stat(caminho), None
    except OSError as e:
        if e.errno in (errno.EACCES, errno.EPERM):
            return None, "NO_ACCESS"
        return None, "NOT_FOUND"


def validate_script_path(caminho):
    """Script no servidor do agente (README §8.0, §8.5; CR-011): vale o arquivo real (o caminho pode ter link
    simbolico), que precisa existir, ser regular e nao ser gravavel por grupo nem por outros. Ciclo de links:
    NOT_FOUND; EACCES: NO_ACCESS. Devolve o codigo ou None."""
    real = final_path(caminho)
    if os.path.islink(real):
        return "NOT_FOUND"  # realpath parou num link: ciclo ou destino inexistente
    st, codigo = _stat_code(real)
    if codigo:
        return codigo
    if not stat.S_ISREG(st.st_mode):
        return "NOT_A_FILE"
    if st.st_mode & 0o022:
        return "GROUP_OTHER_WRITABLE"
    return None


def validate_interpreter_executable(caminho, dirs_sss=()):
    """Executavel do interpretador: envolve path_guard.validate_executable (README §8.5, CR-011)."""
    import path_guard
    return path_guard.validate_executable(caminho, dirs_sss=dirs_sss)


# -----------------------------------------------------------------------------
# Subida do agente fora de DEV (CR-007, D1)
# -----------------------------------------------------------------------------

def _run_short(argv):
    """Comando de diagnostico da subida (antes do laco): devolve (codigo, saida)."""
    p = subprocess.run(argv, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, env=dict(_ENV_HELPER), universal_newlines=True, timeout=30)
    return p.returncode, p.stdout or ""


def validate_execution(exec_users, exec_work_dir, helper=HELPER, executar=_run_short,
                     usuario_agente=None):
    """Confere o helper, o sudoers e os usuarios de execucao (README §8.0). Devolve a lista de falhas
    (vazia = OK); o agente registra cada uma em CRITICAL e recusa subir.

    exec_users: pares (ambiente, usuario) do [agent] exec_users.
    """
    falhas = []
    try:
        st = os.stat(helper)
        if st.st_uid != 0:
            falhas.append("helper %s nao pertence ao root" % helper)
        if stat.S_IMODE(st.st_mode) != 0o755:
            falhas.append("helper %s deve ter modo 0755" % helper)
        dst = os.stat(os.path.dirname(helper))
        if dst.st_uid != 0 or dst.st_mode & 0o022:
            falhas.append("pasta do helper %s deve ser so do root" % os.path.dirname(helper))
    except OSError:
        falhas.append("helper %s nao encontrado" % helper)

    agente = usuario_agente or pwd.getpwuid(os.geteuid()).pw_name
    for usuario in sorted(set(u for _amb, u in exec_users)):
        try:
            info = pwd.getpwnam(usuario)
        except KeyError:
            falhas.append("usuario de execucao %s nao existe" % usuario)
            continue
        if info.pw_uid == 0 or usuario == "root":
            falhas.append("usuario de execucao %s nao pode ser root" % usuario)
        if usuario == agente or info.pw_uid == os.geteuid():
            falhas.append("usuario de execucao %s e o proprio usuario do agente" % usuario)
        # O agente confere as proprias regras: "sudo -l <comando>" imprime o caminho se a regra existir.
        codigo, saida = executar([SUDO, "-n", "-l", "-u", usuario, helper])
        if codigo != 0 or helper not in saida:
            falhas.append("sudo -n -l sem a regra do helper para %s" % usuario)
        pasta = os.path.join(exec_work_dir or "", usuario)
        try:
            pst = os.stat(pasta)
            if pst.st_uid != info.pw_uid or stat.S_IMODE(pst.st_mode) != 0o700:
                falhas.append("%s deve pertencer a %s com modo 0700" % (pasta, usuario))
        except OSError:
            falhas.append("%s nao existe" % pasta)
    return falhas


def clean_script_dir(pasta_base, ticket_id, usuario_execucao):
    """Remove o diretorio de trabalho do script pelo helper limpar (CR-008, R-36; README §8.7 passo 6).

    So fora de DEV (com usuario de execucao); em DEV a pasta fica dentro de work_dir/ticket_<id>/.
    """
    codigo, _saida = _run_short([SUDO, "-n", "-u", usuario_execucao, "--", HELPER, "clean",
                                      pasta_base, str(int(ticket_id))])
    if codigo != 0:
        raise RuntimeError("helper limpar falhou (codigo %s)" % codigo)


# -----------------------------------------------------------------------------
# Pasta de saida do ticket (CR-012, README §8.13)
# -----------------------------------------------------------------------------

def _helper_argv(subcomando, args, usuario_execucao=None):
    """Fora de DEV: sudo -n -u <usuario> -- helper <sub>; em DEV: a copia do pacote com o proprio usuario."""
    args = [str(a) for a in args]
    if usuario_execucao:
        return [SUDO, "-n", "-u", usuario_execucao, "--", HELPER, subcomando] + args
    return [sys.executable, "-I", PACKAGE_HELPER, subcomando] + args


def create_output_dir(base, relativo):
    """So em DEV sem usuario de execucao: cria base e cada nivel do relativo com 0700, recusando link ou item
    que nao seja diretorio do proprio usuario (fora de DEV, quem cria e o helper run)."""
    atual = None
    for parte in [base] + relativo.split("/"):
        atual = parte if atual is None else os.path.join(atual, parte)
        if atual == base:
            os.makedirs(base, 0o700, exist_ok=True)
        else:
            try:
                os.mkdir(atual, 0o700)
            except FileExistsError:  # fluxo previsto: nivel ja criado por outro ticket do mesmo minuto
                pass
        st = os.lstat(atual)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid():
            raise RuntimeError("pasta de saida com item que nao e diretorio do agente")
    os.chmod(atual, 0o700)
    return atual


def create_input_dir(base, relativo):
    """So em DEV sem usuario de execucao (CR-014, README §8.14): base e a pasta do script com 0700 se nao existirem,
    recusando link ou item que nao seja diretorio do proprio usuario. A pasta e permanente: a existente fica como
    esta (fora de DEV, quem cria e o helper run)."""
    os.makedirs(base, 0o700, exist_ok=True)
    pasta = os.path.join(base, relativo)
    try:
        os.mkdir(pasta, 0o700)
    except FileExistsError:  # fluxo previsto: a pasta do script ja existe (tickets anteriores)
        pass
    for item in (base, pasta):
        st = os.lstat(item)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid():
            raise RuntimeError("pasta de entrada com item que nao e diretorio do agente")
    return pasta


def start_pack(base, relativo, max_bytes, max_arquivos, destino_fd, usuario_execucao=None):
    """Inicia o helper empacotar num grupo proprio, com o zip no descritor destino_fd; nao espera.

    O agente acompanha por processo.popen.poll() e, no prazo, encerra com signal_group (README §8.13).
    """
    argv = _helper_argv("pack", [base, relativo, int(max_bytes), int(max_arquivos)], usuario_execucao)
    p = subprocess.Popen(argv, shell=False, start_new_session=True, close_fds=True, stdin=subprocess.DEVNULL,
                         stdout=destino_fd, stderr=subprocess.DEVNULL, env=dict(_ENV_HELPER))
    return Process(p.pid, process_identity(p.pid), popen=p, usuario_execucao=usuario_execucao)


def clean_output(base, relativo, usuario_execucao=None):
    """Remove a pasta de saida do ticket pelo helper clean-output (sem seguir links)."""
    codigo, _saida = _run_short(_helper_argv("clean-output", [base, relativo], usuario_execucao))
    if codigo != 0:
        raise RuntimeError("helper clean-output falhou (codigo %s)" % codigo)


def purge_output(base, dias, usuario_execucao=None, contar=False):
    """Retencao das pastas de saida (purge.py, README §11.3): devolve quantas pastas de minuto sairam (ou, com
    contar=True, quantas sairiam: o --dry-run, sem remover nada)."""
    args = [base, int(dias)] + (["count"] if contar else [])
    codigo, saida = _run_short(_helper_argv("purge-output", args, usuario_execucao))
    if codigo != 0:
        raise RuntimeError("helper purge-output falhou (codigo %s)" % codigo)
    for linha in saida.splitlines():
        if linha.startswith("removidas="):
            return int(linha.split("=", 1)[1])
    raise RuntimeError("helper purge-output sem contagem")


def validate_output_dirs(pastas_usuarios):
    """Subida fora de DEV (README §8.12, passo 4): cada output_dir/<ambiente> existe, e diretorio (sem link),
    pertence ao usuario de execucao do ambiente e nao tem escrita de grupo nem de outros. Devolve as falhas.

    pastas_usuarios: pares (pasta, usuario).
    """
    falhas = []
    for pasta, usuario in pastas_usuarios:
        try:
            uid = pwd.getpwnam(usuario).pw_uid
        except KeyError:
            falhas.append("usuario de execucao %s nao existe" % usuario)
            continue
        try:
            st = os.lstat(pasta)
        except OSError:
            falhas.append("%s nao existe" % pasta)
            continue
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != uid or st.st_mode & 0o022:
            falhas.append("%s deve ser diretorio de %s sem escrita de grupo nem de outros" % (pasta, usuario))
    return falhas


# -----------------------------------------------------------------------------
# Caso "talvez iniciado" do startup check (CR-008, R-01)
# -----------------------------------------------------------------------------

def _pids_in_dir(pasta):
    """PIDs do proprio usuario cujo diretorio atual esta em pasta (Linux: /proc/<pid>/cwd)."""
    pids = []
    meu_uid = os.geteuid()
    for nome in os.listdir("/proc"):
        if not nome.isdigit() or int(nome) == os.getpid():
            continue
        try:
            if os.stat("/proc/" + nome).st_uid != meu_uid:
                continue
            cwd = os.readlink("/proc/%s/cwd" % nome)
        except OSError:  # fluxo previsto: processo saiu durante a varredura
            continue
        if _inside(os.path.normpath(cwd), pasta):
            pids.append(int(nome))
    return pids


def stop_ticket(pasta_base, ticket_id, usuario_execucao, kill_grace_s):
    """Encerra os processos do ticket "talvez iniciado" (.sss_spawn sem .sss_proc). Devolve 'OK' ou
    'NAO_SUPORTADO'. Unica operacao que espera (kill_grace_s), porque roda so antes do laco.

    Com usuario de execucao: helper stop-ticket (codigo 5 = nao suportado). Em DEV: os processos do
    proprio usuario cujo diretorio atual esta em <base_dir>/ticket_<id>.
    """
    if usuario_execucao:
        codigo, saida = _run_short([SUDO, "-n", "-u", usuario_execucao, "--", HELPER, "stop-ticket",
                                         pasta_base, str(int(ticket_id)), str(int(kill_grace_s))])
        if codigo == UNSUPPORTED_CODE:
            return "NAO_SUPORTADO"
        if codigo != 0:
            raise RuntimeError("helper stop-ticket falhou (codigo %s)" % codigo)
        return "OK"
    if NAME != "LINUX" or not os.path.isdir("/proc/self"):
        return "NAO_SUPORTADO"
    pasta = os.path.normpath(os.path.join(pasta_base, "ticket_%d" % int(ticket_id)))
    for sinal in (signal.SIGTERM, signal.SIGKILL):
        pids = _pids_in_dir(pasta)
        for pid in pids:
            try:
                os.kill(pid, sinal)
            except ProcessLookupError:  # fluxo previsto: processo ja saiu
                pass
        if not pids or sinal == signal.SIGKILL:
            break
        limite = time.monotonic() + min(int(kill_grace_s), 300)
        while time.monotonic() < limite and _pids_in_dir(pasta):
            time.sleep(0.1)
    return "OK"
