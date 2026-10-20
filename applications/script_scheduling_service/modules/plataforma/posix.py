# -*- coding: utf-8 -*-
"""Implementacao POSIX da camada de plataforma (README §8.0; CR-005: Linux e demais Unix).

Unico lugar do projeto (fora do helper) com primitivas dependentes do SO: os.killpg, os.setsid,
resource, fcntl, leituras sob /proc e sys.platform (AGENTS §3.2). Nada aqui espera um prazo ou
bloqueia, exceto encerrar_ticket, que roda so no startup check, antes do laco (README §8.0).
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

NOME = "UNIX" if not sys.platform.startswith("linux") else "LINUX"

HELPER = "/opt/sss/bin/sss-helper"
SUDO = "/usr/bin/sudo"
# Ambiente minimo do sudo/helper: nada herdado do agente (AGENTS §3.2, README §8.6).
_ENV_HELPER = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
# Politica fixa de limites do filho (README §8.4): sem core dump e com descritores limitados. O executor
# a manda na especificacao (helper) e o DEV a aplica no preexec_fn.
RLIMITS_PADRAO = {"RLIMIT_CORE": (0, 0), "RLIMIT_NOFILE": (1024, 1024)}
_RLIMITS_PERMITIDOS = ("RLIMIT_CORE", "RLIMIT_NOFILE", "RLIMIT_CPU", "RLIMIT_AS", "RLIMIT_FSIZE",
                       "RLIMIT_NPROC", "RLIMIT_DATA", "RLIMIT_STACK")
# Pastas do sistema (README §8.5): nem script nem log_dir/work_dir podem ficar nelas.
PASTAS_DO_SISTEMA = ("/bin", "/sbin", "/usr", "/lib", "/lib32", "/lib64", "/libx32",
                     "/etc", "/boot", "/proc", "/sys", "/dev", "/root")
CODIGO_NAO_SUPORTADO = 5

# Pedidos ao helper (term/kill) ainda nao coletados: sinalizar_grupo nunca espera o helper terminar.
_pedidos_helper = []


class InstanciaJaEmExecucao(RuntimeError):
    """Outra instancia do agente ja tem a trava (travar_instancia)."""


class FalhaAposSpawn(RuntimeError):
    """O Popen do sudo/helper retornou, mas a entrega da especificacao falhou (CR-008, R-01): o grupo
    existe e vai em processo, para o executor encerra-lo sem esperar."""

    def __init__(self, processo, causa):
        RuntimeError.__init__(self, causa.__class__.__name__)
        self.processo = processo
        self.causa = causa


class Processo(object):
    """Grupo de processos de um ticket: lider (pid = pgid, start_new_session) e sua identidade."""

    def __init__(self, pid, identidade, popen=None, usuario_execucao=None, sem_identidade=False):
        self.pid = pid
        self.pgid = pid
        self.identidade = identidade
        self.popen = popen
        self.usuario_execucao = usuario_execucao
        # Identidade desconhecida com PID vivo: nunca recebe sinal (WARN ORFAO_SEM_IDENTIDADE).
        self.sem_identidade = sem_identidade

    def __repr__(self):
        return "Processo(pid=%s, identidade=%s, usuario=%s)" % (self.pid, self.identidade, self.usuario_execucao)


# -----------------------------------------------------------------------------
# Execucao
# -----------------------------------------------------------------------------

def _rlimits(especificacao):
    limites = dict(RLIMITS_PADRAO)
    for nome, valor in (especificacao.get("rlimits") or {}).items():
        if nome not in _RLIMITS_PERMITIDOS:
            raise ValueError("Limite de recurso nao permitido: %s" % nome)
        limites[nome] = (int(valor[0]), int(valor[1]))
    return [(getattr(resource, nome), par) for nome, par in sorted(limites.items())]


def _limites_do_filho(limites):
    """preexec_fn em DEV: somente os.umask e resource.setrlimit (AGENTS §3.2; sem threads no daemon)."""
    def _child_limits():
        os.umask(0o077)
        for recurso, par in limites:
            resource.setrlimit(recurso, par)
    return _child_limits


def iniciar_processo(especificacao, log_fd, usuario_execucao=None):
    """Inicia o script num grupo proprio (start_new_session) com stdout/stderr no arquivo de log.

    Com usuario_execucao: sudo -n -u <usuario> -- /opt/sss/bin/sss-helper run, com a especificacao JSON
    (ticket_id, argv, env, rlimits, pasta_base) pela entrada padrao. Sem ele (so DEV): Popen direto com
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
            raise FalhaAposSpawn(Processo(p.pid, identidade_processo(p.pid), popen=p,
                                          usuario_execucao=usuario_execucao), e)
    else:
        p = subprocess.Popen(list(especificacao["argv"]), shell=False, start_new_session=True, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=log_fd, stderr=subprocess.STDOUT,
                             cwd=especificacao.get("cwd"), env=dict(especificacao.get("env") or {}),
                             preexec_fn=_limites_do_filho(_rlimits(especificacao)))
    return Processo(p.pid, identidade_processo(p.pid), popen=p, usuario_execucao=usuario_execucao)


def _colher_pedidos_helper():
    """Coleta (sem esperar) os helpers term/kill ja terminados e registra os que falharam."""
    restantes = []
    for argv, p in _pedidos_helper:
        rc = p.poll()
        if rc is None:
            restantes.append((argv, p))
        elif rc not in (0,):
            _log.warning("helper %s terminou com codigo %s", argv[-3], rc, extra={"acao": "SINAL"})
    _pedidos_helper[:] = restantes


def sinalizar_grupo(processo, sinal):
    """Envia o sinal ao grupo do processo, sem esperar (CR-007, R-04). True se o pedido saiu.

    Identidade desconhecida: nao sinaliza (False). Lider vivo com outra identidade (PID reciclado):
    nao sinaliza. ESRCH (grupo vazio) devolve False. Com usuario de execucao, o sinal vai pelo helper
    term/kill <pgid> <process_start>, iniciado sem esperar; o resultado e coletado nas proximas chamadas.
    """
    _colher_pedidos_helper()
    if processo.sem_identidade:
        return False
    if processo.usuario_execucao:
        sub = "kill" if sinal == signal.SIGKILL else "term"
        argv = [SUDO, "-n", "-u", processo.usuario_execucao, "--", HELPER, sub, str(processo.pgid),
                str(processo.identidade if processo.identidade is not None else 0)]
        p = subprocess.Popen(argv, shell=False, close_fds=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(_ENV_HELPER))
        _pedidos_helper.append((argv, p))
        return True
    if processo_existe(processo.pid):
        atual = identidade_processo(processo.pid)
        if processo.identidade is not None and atual is not None and atual != processo.identidade:
            return False
    try:
        os.killpg(processo.pgid, sinal)
        return True
    except ProcessLookupError:  # fluxo previsto (AGENTS §6): ESRCH = grupo vazio
        return False


def grupo_vivo(processo):
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


def reabrir_grupo(estado):
    """Grupo de um ticket que nao e filho do daemon (startup check, README §8.12 passo 9), sem wait().

    estado: o .sss_proc (pid, process_start, usuario_execucao). PID vivo com outra identidade: PID
    reciclado, o grupo antigo acabou (None). PID vivo sem identidade legivel: Processo sem_identidade,
    que nao recebe sinal. Lider morto com o grupo ainda vivo (netos): Processo para o executor encerrar.
    """
    pid = int(estado["pid"])
    esperada = estado.get("process_start")
    usuario = estado.get("usuario_execucao")
    if processo_existe(pid):
        atual = identidade_processo(pid)
        if atual is None:
            _log.warning("ORFAO_SEM_IDENTIDADE pid=%s: identidade ilegivel nesta plataforma", pid,
                         extra={"acao": "STARTUP"})
            return Processo(pid, None, usuario_execucao=usuario, sem_identidade=True)
        if esperada is not None and int(esperada) != atual:
            return None
        return Processo(pid, atual, usuario_execucao=usuario)
    processo = Processo(pid, esperada, usuario_execucao=usuario)
    return processo if grupo_vivo(processo) else None


# -----------------------------------------------------------------------------
# Identidade e existencia de processos
# -----------------------------------------------------------------------------

def _starttime_linux(conteudo):
    """Campo 22 (starttime) de /proc/<pid>/stat, contado depois do ULTIMO ')' (o comando pode ter ')')."""
    resto = conteudo[conteudo.rindex(")") + 2:].split()
    # O resto comeca no campo 3 (state): o campo 22 fica na posicao 22 - 3.
    return int(resto[19])


def identidade_processo(pid):
    """Identidade contra PID reciclado: no Linux, o starttime; demais Unix sem leitura segura: None."""
    if NOME != "LINUX":
        # psinfo/sysctl exigiriam layout binario por sistema (sem FFI no projeto): identidade desconhecida.
        return None
    try:
        with open("/proc/%d/stat" % int(pid), "r") as f:
            return _starttime_linux(f.read())
    except (OSError, ValueError, IndexError):  # fluxo previsto: identidade desconhecida
        return None


def processo_existe(pid):
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

def gravar_estado(caminho, dados):
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


def ler_estado(caminho):
    """Conteudo do arquivo de estado, ou None se nao existir."""
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:  # fluxo previsto: estado ainda nao gravado
        return None


def criar_dir_trabalho(caminho):
    """work_dir/ticket_<id>/ do agente com 0700 (estado local; README §8.4)."""
    os.makedirs(caminho, mode=0o700, exist_ok=True)
    os.chmod(caminho, 0o700)
    return caminho


def espaco_livre_mb(caminho):
    """Espaco livre para usuario comum em caminho (f_bavail x f_frsize), em MiB (CR-008, R-25)."""
    st = os.statvfs(caminho)
    return int(st.f_bavail * st.f_frsize // (1024 * 1024))


def caminho_final(caminho):
    """Caminho resolvido (realpath no POSIX)."""
    return os.path.realpath(caminho)


# -----------------------------------------------------------------------------
# Instancia, privilegio e parada
# -----------------------------------------------------------------------------

class _Trava(object):
    def __init__(self, fd, caminho):
        self.fd = fd
        self.caminho = caminho


def travar_instancia(caminho):
    """Trava exclusiva nao bloqueante (fcntl.flock LOCK_EX | LOCK_NB); outra instancia: InstanciaJaEmExecucao."""
    fd = os.open(caminho, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, PermissionError):
        os.close(fd)
        raise InstanciaJaEmExecucao("Outra instancia do agente ja esta em execucao (%s)" % caminho)
    os.ftruncate(fd, 0)
    os.write(fd, ("%d\n" % os.getpid()).encode("ascii"))
    return _Trava(fd, caminho)


def liberar_instancia(trava):
    if trava is None:
        return
    try:
        fcntl.flock(trava.fd, fcntl.LOCK_UN)
    finally:
        os.close(trava.fd)


def _normalizar_locale(nome):
    return (nome or "").strip().lower().replace("-", "")


def locale_disponivel(nome, executar=None):
    """True se o locale consta em `locale -a` (README §8.12 passo 2; CR-007 R-17). C.UTF-8 = C.utf8."""
    executar = executar or _executar_curto
    try:
        codigo, saida = executar(["/usr/bin/locale", "-a"])
    except OSError:  # sem o comando locale: nao da para confirmar
        return False
    alvo = _normalizar_locale(nome)
    return codigo == 0 and any(_normalizar_locale(l) == alvo for l in saida.splitlines())


def usuario_privilegiado():
    return os.geteuid() == 0


def instalar_parada(flag):
    """SIGTERM/SIGINT so acionam a flag (um objeto com set(), ex.: threading.Event); nada mais."""
    def _handler(signum, frame):
        flag.set()
    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


# -----------------------------------------------------------------------------
# Validacoes de arquivos, diretorios e caminhos
# -----------------------------------------------------------------------------

def validar_arquivo_restrito(caminho):
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


def _dentro(caminho, pasta):
    return os.path.commonpath([caminho, pasta]) == pasta


def validar_dir_restrito(caminho):
    """log_dir/work_dir (README §8.12 passo 4): existe, e diretorio, e gravavel e fica fora das pastas do
    sistema. Nao exige 0700 (log_dir e as pastas de log sao 0750). Devolve o codigo da falha ou None."""
    if not isinstance(caminho, str) or not caminho.startswith("/"):
        return "CAMINHO_RELATIVO"
    real = os.path.realpath(caminho)
    if any(_dentro(alvo, d) for alvo in (caminho, real) for d in PASTAS_DO_SISTEMA):
        return "PASTA_DO_SISTEMA"
    if not os.path.exists(real):
        return "NAO_ENCONTRADO"
    if not os.path.isdir(real):
        return "NAO_E_DIRETORIO"
    if not os.access(real, os.W_OK | os.X_OK):
        return "SEM_ESCRITA"
    return None


def _stat_codigo(caminho, lstat=False):
    try:
        return (os.lstat(caminho) if lstat else os.stat(caminho)), None
    except OSError as e:
        if e.errno in (errno.EACCES, errno.EPERM):
            return None, "SEM_ACESSO"
        return None, "NAO_ENCONTRADO"


def checar_item(caminho, donos, uid_agente=None, uids_proibidos=()):
    """Regra de dono e escrita de um item da cadeia (README §8.5, CR-007 R-15). Devolve o codigo ou None."""
    st, codigo = _stat_codigo(caminho)
    if codigo:
        return codigo
    if st.st_uid not in donos:
        return "DONO_INVALIDO"
    if st.st_mode & 0o022:
        return "GRAVAVEL_GRUPO_OUTROS"
    # O dono pode mudar o modo a qualquer momento: pertencer ao agente ja e proibido.
    agente = os.geteuid() if uid_agente is None else uid_agente
    if uid_agente is None:
        gravavel = os.access(caminho, os.W_OK)
    else:
        gravavel = uid_agente == 0 or (st.st_uid == uid_agente and bool(st.st_mode & 0o200))
    if st.st_uid == agente or gravavel:
        return "GRAVAVEL_PELO_AGENTE"
    if st.st_uid in uids_proibidos:
        return "GRAVAVEL_PELO_EXECUTOR"
    return None


def checar_cadeia(real, donos, uid_agente=None, uids_proibidos=(), parar_em="/"):
    """O item e cada diretorio ate '/' (diretorios aceitam tambem o root). Devolve o codigo ou None."""
    donos = tuple(donos)
    donos_dir = donos + ((0,) if 0 not in donos else ())
    codigo = checar_item(real, donos, uid_agente, uids_proibidos)
    if codigo:
        return codigo
    limite = os.path.realpath(parar_em)
    atual = os.path.dirname(real)
    while True:
        codigo = checar_item(atual, donos_dir, uid_agente, uids_proibidos)
        if codigo:
            return codigo
        if atual == limite or atual == "/":
            return None
        atual = os.path.dirname(atual)


def validar_caminho_script(caminho, donos, uids_proibidos=(), uid_agente=None, parar_em="/"):
    """Script no servidor local (README §8.0, §8.5): caminho igual ao realpath (CAMINHO_COM_LINK), arquivo
    regular e a cadeia de dono e escrita ate '/'. EACCES vira SEM_ACESSO. Devolve o codigo ou None."""
    if caminho_final(caminho) != caminho:
        return "CAMINHO_COM_LINK"
    _st, codigo = _stat_codigo(caminho, lstat=True)
    if codigo:
        return codigo
    if not os.path.isfile(caminho) or os.path.islink(caminho):
        return "NAO_E_ARQUIVO"
    return checar_cadeia(caminho, donos, uid_agente, tuple(uids_proibidos), parar_em)


def validar_interpretador_executavel(caminho, donos, uid_agente=None, uids_proibidos=(), dirs_sss=()):
    """Executavel do interpretador: envolve path_guard.validar_executavel (README §8.5, CR-007 R-15)."""
    import path_guard
    return path_guard.validar_executavel(caminho, donos, uid_agente=uid_agente, uids_proibidos=uids_proibidos,
                                         dirs_sss=dirs_sss)


# -----------------------------------------------------------------------------
# Subida do agente fora de DEV (CR-007, D1)
# -----------------------------------------------------------------------------

def _executar_curto(argv):
    """Comando de diagnostico da subida (antes do laco): devolve (codigo, saida)."""
    p = subprocess.run(argv, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, env=dict(_ENV_HELPER), universal_newlines=True, timeout=30)
    return p.returncode, p.stdout or ""


def validar_execucao(usuarios_execucao, exec_work_dir, script_owner_uids, helper=HELPER, executar=_executar_curto,
                     usuario_agente=None):
    """Confere o helper, o sudoers e os usuarios de execucao (README §8.0). Devolve a lista de falhas
    (vazia = OK); o agente registra cada uma em CRITICAL e recusa subir.

    usuarios_execucao: pares (ambiente, usuario) do [agent] usuarios_execucao.
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
    for usuario in sorted(set(u for _amb, u in usuarios_execucao)):
        try:
            info = pwd.getpwnam(usuario)
        except KeyError:
            falhas.append("usuario de execucao %s nao existe" % usuario)
            continue
        if info.pw_uid == 0 or usuario == "root":
            falhas.append("usuario de execucao %s nao pode ser root" % usuario)
        if usuario == agente or info.pw_uid == os.geteuid():
            falhas.append("usuario de execucao %s e o proprio usuario do agente" % usuario)
        if info.pw_uid in tuple(int(x) for x in script_owner_uids):
            falhas.append("usuario de execucao %s esta em script_owner_uids" % usuario)
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


def limpar_dir_script(pasta_base, ticket_id, usuario_execucao):
    """Remove o diretorio de trabalho do script pelo helper limpar (CR-008, R-36; README §8.7 passo 6).

    So fora de DEV (com usuario de execucao); em DEV a pasta fica dentro de work_dir/ticket_<id>/.
    """
    codigo, _saida = _executar_curto([SUDO, "-n", "-u", usuario_execucao, "--", HELPER, "limpar",
                                      pasta_base, str(int(ticket_id))])
    if codigo != 0:
        raise RuntimeError("helper limpar falhou (codigo %s)" % codigo)


# -----------------------------------------------------------------------------
# Caso "talvez iniciado" do startup check (CR-008, R-01)
# -----------------------------------------------------------------------------

def _pids_na_pasta(pasta):
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
        if _dentro(os.path.normpath(cwd), pasta):
            pids.append(int(nome))
    return pids


def encerrar_ticket(pasta_base, ticket_id, usuario_execucao, kill_grace_s):
    """Encerra os processos do ticket "talvez iniciado" (.sss_spawn sem .sss_proc). Devolve 'OK' ou
    'NAO_SUPORTADO'. Unica operacao que espera (kill_grace_s), porque roda so antes do laco.

    Com usuario de execucao: helper encerrar-ticket (codigo 5 = nao suportado). Em DEV: os processos do
    proprio usuario cujo diretorio atual esta em <pasta_base>/ticket_<id>.
    """
    if usuario_execucao:
        codigo, saida = _executar_curto([SUDO, "-n", "-u", usuario_execucao, "--", HELPER, "encerrar-ticket",
                                         pasta_base, str(int(ticket_id)), str(int(kill_grace_s))])
        if codigo == CODIGO_NAO_SUPORTADO:
            return "NAO_SUPORTADO"
        if codigo != 0:
            raise RuntimeError("helper encerrar-ticket falhou (codigo %s)" % codigo)
        return "OK"
    if NOME != "LINUX" or not os.path.isdir("/proc/self"):
        return "NAO_SUPORTADO"
    pasta = os.path.normpath(os.path.join(pasta_base, "ticket_%d" % int(ticket_id)))
    for sinal in (signal.SIGTERM, signal.SIGKILL):
        pids = _pids_na_pasta(pasta)
        for pid in pids:
            try:
                os.kill(pid, sinal)
            except ProcessLookupError:  # fluxo previsto: processo ja saiu
                pass
        if not pids or sinal == signal.SIGKILL:
            break
        limite = time.monotonic() + min(int(kill_grace_s), 300)
        while time.monotonic() < limite and _pids_na_pasta(pasta):
            time.sleep(0.1)
    return "OK"
