# -*- coding: utf-8 -*-
"""Daemon do agente: inicializacao fail-fast, startup check e laco (README §8.1-§8.12; CR-007 R-01 a R-04, R-11,
R-17, R-23, R-28; CR-008 R-01, R-02, R-07, R-08, R-09, R-11, R-17, R-25, R-26, E4).

Laco single-threaded com tres prazos monotonicos e nenhuma espera dentro das operacoes: a unica espera e a
de entre iteracoes (injetada, no maximo 1 s). Encerramentos pela maquina de estados do executor. NODE_OFFLINE,
desdobro, fencing completo e DRAIN ficam para o F8.4 (pontos de extensao).
A pasta de saida do ticket (CR-012, README §8.13) passa pela maquina de fase_saida: empacotar antes do flush
final e gravar depois da finalizacao, fora do mapa de execucoes.

Python puro (sem web2py): o processo inteiro precisa de uma unica thread antes do primeiro spawn, por causa
do preexec_fn (README §3.1, C10). Toda primitiva de SO vem de `plataforma`; o banco, do `db_conn` e dos
repositorios internos do daemon. Cada passo que falha registra CRITICAL e sai com um codigo proprio.
"""
import datetime
import logging
import os
import socket
import threading
import time

import db_conn
import desdobro
import env_builder
import executor
import fase_saida
import log_pump
import params_compiler
import pastas_log
import plataforma
import rbac
import sss_config
from repo_oracle.scheduler_agenda import RepoSchedulerAgenda
from repo_oracle.scheduler_fila import AgenteDuplicado, RegistroPerdido, RepoSchedulerFila
from repo_oracle.scheduler_log import RepoSchedulerLog
from repo_oracle.scheduler_saida import RepoSchedulerSaida

_log = logging.getLogger("sss_scheduler")

# Codigos de saida por passo do README §8.12 (o 0 e a parada normal).
SAIDA_USUARIO = 10
SAIDA_CONFIG = 11
SAIDA_SEGREDOS = 12
SAIDA_DIRETORIOS = 13
SAIDA_INSTANCIA = 14
SAIDA_BANCO = 15
SAIDA_REGISTRO = 16
SAIDA_AMBIENTES = 17
SAIDA_STARTUP = 18
SAIDA_THREADS = 19
SAIDA_REGISTRO_PERDIDO = 20

# Motivos de encerramento -> (status, status_motivo, return_code) do README §5.2.
_FINAL = {
    "TIMEOUT": ("FAILED", "TIMEOUT", -3),
    "LOG_LIMIT": ("FAILED", "LOG_LIMIT", -5),
    "CANCEL": ("CANCELLED", "CANCEL_USER", -1),
    "SHUTDOWN": ("FAILED", "SHUTDOWN", -6),
    "SPAWN_ERROR": ("FAILED", "SPAWN_ERROR", -4),
    # Self-fencing (README §8.9): o encerramento pedido pelo fence. Quem ja tinha resultado (o .sss_result,
    # CR-008 R-12) ou outro motivo de encerramento fica com o seu.
    "FENCED": ("FAILED", "FENCED", -2),
}
_PRECHECK = ("FAILED", "PRECHECK_FAILED", -4)
INTERVALO_MAXIMO_ESPERA_S = 1.0
INTERVALO_AVISO_DISCO_S = 60

DIVERGENCIA_RELOGIO_S = 60
# Salto de relogio (CR-007 D3, CR-008 R-10): avanco do SYSDATE diferente do monotonico em mais que isso.
SALTO_RELOGIO_S = 30
_PREFIXO_PASTA = "ticket_"


class FalhaInicializacao(SystemExit):
    """Falha de um passo da inicializacao: o CRITICAL ja foi registrado; o codigo identifica o passo."""

    def __init__(self, codigo, motivo):
        SystemExit.__init__(self, codigo)
        self.codigo = codigo
        self.motivo = motivo


class _Log(logging.LoggerAdapter):
    """Toda linha com agente, ticket e acao (README §13)."""

    def process(self, msg, kwargs):
        extra = dict(self.extra)
        extra.update(kwargs.pop("extra", None) or {})
        kwargs["extra"] = extra
        return msg, kwargs


def _ler_estado(pasta, nome, plat):
    try:
        return plat.ler_estado(os.path.join(pasta, nome))
    except (OSError, ValueError):  # estado ilegivel: tratado como ausente, com o rastro preservado
        return None


class Agente(object):
    """Daemon de um no agente. inicializar() executa os passos 1 a 9 do README §8.12, em ordem."""

    def __init__(self, cfg=None, segredos=None, plat=None, conexao=None, repo=None, repo_log=None,
                 relogio=None, relogio_parede=None, hostname=None, pid=None, carregar_config=None,
                 carregar_segredos=None, repo_saida=None, repo_agenda=None):
        self.cfg = cfg
        self.segredos = segredos
        self.plat = plat or plataforma
        self.conexao = conexao
        self.repo = repo
        self.repo_log = repo_log
        self.repo_saida = repo_saida
        self.repo_agenda = repo_agenda
        self.desdobro = None
        self.relogio = relogio or time.monotonic
        self.relogio_parede = relogio_parede or time.time
        self.hostname = hostname or socket.gethostname()
        self.pid = pid or os.getpid()
        self._carregar_config = carregar_config or (lambda: sss_config.obter_config(nome_log="sss_scheduler"))
        self._carregar_segredos = carregar_segredos
        self.log = _Log(_log, {"agente": "-", "ticket": "-", "acao": "INICIO"})
        self.trava = None
        self.agente_db_id = None
        self.ultimo_hb_ok = None
        self.unidade_suplementar = 2
        self.ambientes_ativos = []
        # Startup check: grupos ainda em encerramento (o laco avanca e limpa) e pastas preservadas.
        self.encerrando = {}
        self.preservadas = set()

    # ------------------------------------------------------------------ util

    def _falhar(self, codigo, motivo, *args):
        texto = motivo % args if args else motivo
        self.log.critical("Subida abortada: %s", texto, extra={"acao": "INICIO"})
        raise FalhaInicializacao(codigo, texto)

    @property
    def agente_id(self):
        return self.cfg.agent.agent_id

    def _conn(self):
        return self.conexao.obter_conexao()

    def _usuario_execucao(self, ambiente):
        return dict(self.cfg.agent.usuarios_execucao or ()).get(ambiente) or None

    # --------------------------------------------------------------- passos

    def inicializar(self):
        """Passos 1 a 9 do README §8.12 e a checagem de thread unica. Falha: FalhaInicializacao, com a trava
        de instancia e a conexao ja liberadas."""
        try:
            self._passos()
        except FalhaInicializacao:
            self.liberar_recursos()
            raise
        self.log.info("agente inicializado (versao %s, %d grupo(s) em encerramento, %d pasta(s) preservada(s))",
                      sss_config.VERSAO_SSS, len(self.encerrando), len(self.preservadas))
        return self

    def liberar_recursos(self):
        """Fecha a conexao e solta a trava de instancia (falha na subida e parada)."""
        if self.conexao is not None and hasattr(self.conexao, "fechar"):
            self.conexao.fechar()
        if self.trava is not None:
            self.plat.liberar_instancia(self.trava)
            self.trava = None

    def _passos(self):
        self._passo1_usuario()
        self._passo2_config()
        self._passo3_segredos()
        self._passo4_diretorios()
        self._passo5_instancia()
        self._passo6_banco()
        self._passo7_registro()
        self._passo8_ambientes()
        self._passo9_startup_check()
        self._conferir_thread_unica()

    def _passo1_usuario(self):
        if self.plat.usuario_privilegiado():
            self._falhar(SAIDA_USUARIO, "o agente nao pode rodar como root (README §8.12 passo 1)")

    def _passo2_config(self):
        if self.cfg is None:
            try:
                self.cfg = self._carregar_config()
            except sss_config.ConfigErro as exc:  # obter_config ja registrou o CRITICAL (README §12.1)
                raise FalhaInicializacao(SAIDA_CONFIG, str(exc))
        agente = self.cfg.agent
        self.log.extra["agente"] = agente.agent_id
        try:
            sss_config.verificar_codificacao()
        except sss_config.ConfigErro as exc:
            self._falhar(SAIDA_CONFIG, "%s", exc)
        if not self.plat.locale_disponivel(agente.child_locale):
            self._falhar(SAIDA_CONFIG, "child_locale %s nao consta em locale -a (CR-007, R-17)", agente.child_locale)
        db_conn.orcamento_conexao_s(self.cfg.oracle.dsn, sss_config.call_timeout_s(self.cfg.oracle.call_timeout_ms))
        # Conferencia entre nos no E2E (README §8.9, "Mesmos tempos em todos os nos").
        self.log.info("tempos do fencing: fence_timeout_s=%s node_offline_timeout_s=%s",
                      agente.fence_timeout_s, agente.node_offline_timeout_s)

    def _passo3_segredos(self):
        if self.segredos is not None:
            return
        try:
            carregar = self._carregar_segredos or (
                lambda: sss_config.carregar_segredos(self.cfg.secrets.secrets_file, cfg=self.cfg, papel="agente"))
            self.segredos = carregar()
        except sss_config.ConfigErro as exc:
            self._falhar(SAIDA_SEGREDOS, "secrets.cfg invalido: %s", exc)

    def _passo4_diretorios(self):
        agente = self.cfg.agent
        for nome, caminho in (("log_dir", self.cfg.logging.log_dir), ("work_dir", agente.work_dir)):
            codigo = self.plat.validar_dir_restrito(caminho)
            if codigo:
                self._falhar(SAIDA_DIRETORIOS, "%s %s recusado: %s", nome, caminho, codigo)
        dirs_sss = tuple(d for d in (self.cfg.logging.log_dir, agente.work_dir, agente.exec_work_dir) if d)
        if not agente.interpretadores:
            self._falhar(SAIDA_DIRETORIOS, "[agent] interpretadores vazio: o agente nao executaria nada")
        for logico, caminho in agente.interpretadores:
            try:
                self.plat.validar_interpretador_executavel(caminho, dirs_sss=dirs_sss)
            except Exception as exc:  # noqa: BLE001 - PathGuardErro e afins: CRITICAL com o codigo
                self._falhar(SAIDA_DIRETORIOS, "interpretador %s (%s) recusado: %s", logico, caminho,
                             getattr(exc, "codigo", exc.__class__.__name__))
        if self.cfg.app.sss_env != "DEV":
            falhas = self.plat.validar_execucao(agente.usuarios_execucao, agente.exec_work_dir)
            for falha in falhas:
                self.log.critical("execucao fora de DEV: %s", falha)
            if falhas:
                self._falhar(SAIDA_DIRETORIOS, "%d falha(s) na conferencia do helper e do sudoers", len(falhas))
        self._conferir_saida_dir()

    def _conferir_saida_dir(self):
        """CR-012 (README §8.12 passo 4): saida_dir fora das pastas do sistema; fora de DEV, a pasta de cada
        ambiente atendido do usuario de execucao dele, sem escrita de grupo nem de outros."""
        agente = self.cfg.agent
        if not agente.saida_dir:
            return
        codigo = self.plat.validar_dir_restrito(agente.saida_dir)
        if codigo:
            self._falhar(SAIDA_DIRETORIOS, "saida_dir %s recusado: %s", agente.saida_dir, codigo)
        if self.cfg.app.sss_env == "DEV" and not agente.usuarios_execucao:
            return
        pares = [(os.path.join(agente.saida_dir, pastas_log.pasta_ambiente(amb)), self._usuario_execucao(amb))
                 for amb in agente.ambientes_atendidos if self._usuario_execucao(amb)]
        falhas = self.plat.validar_pastas_saida(pares)
        for falha in falhas:
            self.log.critical("pasta de saida: %s", falha)
        if falhas:
            self._falhar(SAIDA_DIRETORIOS, "%d falha(s) nas pastas de saida (CR-012)", len(falhas))

    def _passo5_instancia(self):
        work = self.cfg.agent.work_dir
        try:
            self.trava = self.plat.travar_instancia(os.path.join(work, "sss-%s.lock" % self.agente_id))
        except self.plat.InstanciaJaEmExecucao as exc:
            self._falhar(SAIDA_INSTANCIA, "%s", exc)
        stop = os.path.join(work, "sss-%s.stop" % self.agente_id)
        if os.path.exists(stop):
            os.unlink(stop)
            self.log.warning("arquivo .stop antigo removido (CR-007, R-32)")

    def _passo6_banco(self):
        try:
            if self.conexao is None:
                selecao = db_conn.selecionar_driver(self.cfg, self.segredos)
                db_conn.inicializar(selecao, self.cfg)
                self.conexao = db_conn.ConexaoResiliente(self.cfg, self.segredos, papel="agente")
            if not self.conexao.garantir():
                self._falhar(SAIDA_BANCO, "sem conexao com o Oracle")
            conn = self._conn()
            if self.repo is None:
                self.repo = RepoSchedulerFila.da_config(self.cfg)
            if self.repo_log is None:
                self.repo_log = RepoSchedulerLog.da_config(self.cfg)
            if self.repo_saida is None:
                self.repo_saida = RepoSchedulerSaida.da_config(self.cfg)
            if self.repo_agenda is None:
                self.repo_agenda = RepoSchedulerAgenda.da_config(self.cfg)
            agora_banco = db_conn.agora_banco(conn)
            local = self.relogio_parede()
            divergencia = abs((datetime.datetime.fromtimestamp(local) - agora_banco).total_seconds())
            if divergencia > DIVERGENCIA_RELOGIO_S:
                self.log.warning("relogio local diverge do SYSDATE em %d s (README §7.1)", divergencia)
            db_conn.conferir_versao_esquema(conn, owner=self.cfg.oracle.owner.strip(),
                                            prefixo=self.cfg.oracle.table_prefix.strip())
            self.unidade_suplementar = self.repo_log.unidade_suplementar(conn)
        except FalhaInicializacao:
            raise
        except Exception as exc:  # noqa: BLE001 - driver, versao do esquema ou leitura: CRITICAL
            self._falhar(SAIDA_BANCO, "banco: %s", exc)

    def _passo7_registro(self):
        agente = self.cfg.agent
        criticos = sss_config.config_criticos(self.cfg)
        inicio = self.relogio()
        try:
            self.agente_db_id = self.repo.registrar_agente(self._conn(), {
                "codigo": agente.agent_id, "hostname": self.hostname, "pid": self.pid,
                "versao": sss_config.VERSAO_SSS, "ambientes": ",".join(agente.ambientes_atendidos),
                "plataforma": self.plat.NOME, "interpretadores": ",".join(k for k, _v in agente.interpretadores),
                "config_criticos": criticos, "node_offline_timeout_s": agente.node_offline_timeout_s,
            }, self.plat.processo_existe)
            divergentes = self.repo.conferir_config(self._conn(), agente.agent_id, criticos,
                                                    agente.node_offline_timeout_s)
        except AgenteDuplicado as exc:
            self._falhar(SAIDA_REGISTRO, "agent_id duplicado: %s", exc)
        except Exception as exc:  # noqa: BLE001
            self._falhar(SAIDA_REGISTRO, "registro do agente: %s", exc)
        if divergentes:
            for codigo, outra in divergentes:
                self.log.critical("config_criticos diverge do agente %s: local=%s remoto=%s", codigo, criticos, outra)
            self._falhar(SAIDA_REGISTRO, "configuracao critica diferente da dos outros agentes (CR-007, R-23)")
        self.ultimo_hb_ok = inicio

    def _passo8_ambientes(self):
        try:
            ativos, inexistentes = self.repo.ambientes_ativos(self._conn(), self.cfg.agent.ambientes_atendidos)
        except Exception as exc:  # noqa: BLE001
            self._falhar(SAIDA_AMBIENTES, "leitura dos ambientes: %s", exc)
        if inexistentes:
            self._falhar(SAIDA_AMBIENTES, "ambientes atendidos inexistentes: %s", ", ".join(inexistentes))
        for nome in sorted(set(self.cfg.agent.ambientes_atendidos) - set(ativos)):
            self.log.warning("ambiente atendido %s inativo: ignorado ate ser reativado", nome)
        self.ambientes_ativos = ativos

    def _conferir_thread_unica(self):
        if threading.active_count() != 1:
            nomes = ", ".join(sorted(t.name for t in threading.enumerate()))
            self._falhar(SAIDA_THREADS, "o processo tem %d threads antes do primeiro spawn (%s); o preexec_fn "
                                       "exige thread unica (README §3.1)", threading.active_count(), nomes)

    # -------------------------------------------------------- startup check

    def _pastas_locais(self):
        """{ticket_id: pasta} das pastas work_dir/ticket_<id> (nao segue links)."""
        work = self.cfg.agent.work_dir
        pastas = {}
        for nome in sorted(os.listdir(work)):
            caminho = os.path.join(work, nome)
            sufixo = nome[len(_PREFIXO_PASTA):]
            if nome.startswith(_PREFIXO_PASTA) and sufixo.isdigit() and os.path.isdir(caminho) \
                    and not os.path.islink(caminho):
                pastas[int(sufixo)] = caminho
        return pastas

    def _passo9_startup_check(self):
        """O disco do agente e a fonte de verdade sobre o que ele iniciou (README §8.12 passo 9)."""
        try:
            self._startup_check()
        except FalhaInicializacao:
            raise
        except Exception as exc:  # noqa: BLE001
            self._falhar(SAIDA_STARTUP, "startup check: %s", exc)

    def _startup_check(self):
        agente = self.cfg.agent
        conn = self._conn()
        running = dict((t["id"], t) for t in self.repo.tickets_running_do_agente(conn, self.agente_id))
        pastas = self._pastas_locais()
        resultados = {}
        for tid, pasta in sorted(pastas.items()):
            log = _Log(_log, {"agente": self.agente_id, "ticket": tid, "acao": "STARTUP"})
            proc = _ler_estado(pasta, executor.PROC, self.plat)
            spawn = _ler_estado(pasta, executor.SPAWN, self.plat)
            resultados[tid] = _ler_estado(pasta, executor.RESULT, self.plat)
            usuario = (proc or spawn or {}).get("usuario_execucao")
            if proc is not None:
                self._reabrir(tid, pasta, proc, usuario, log)
            elif spawn is not None:
                # Talvez iniciado (CR-008, R-01): nunca volta a fila. Unica espera da subida (kill_grace_s).
                base = os.path.join(agente.exec_work_dir, usuario) if usuario else agente.work_dir
                if self.plat.encerrar_ticket(base, tid, usuario, agente.kill_grace_s) == "NAO_SUPORTADO":
                    # O processo pode seguir vivo: a pasta fica como rastro (CR-008, R-26).
                    self.preservadas.add(tid)
                    log.warning("TALVEZ_INICIADO sem meio de encerrar nesta plataforma: o processo fica com o "
                                "usuario de execucao")
                log.error("TALVEZ_INICIADO: .sss_spawn sem .sss_proc")
        for tid, ticket in sorted(running.items()):
            log = _Log(_log, {"agente": self.agente_id, "ticket": tid, "acao": "STARTUP"})
            if tid in pastas:
                res = resultados.get(tid)
                if res is not None:
                    self._finalizar(tid, res["status"], res["status_motivo"], res["return_code"], log,
                                    "resultado local gravado antes da queda")
                else:
                    self._finalizar(tid, "FAILED", "ORPHAN_PROCESS", -2, log, "processo sem acompanhamento")
            elif ticket["process_id"] is None:
                desfecho = self.repo.devolver(conn, tid, self.agente_id)
                (log.warning if desfecho != "PERDIDO" else log.info)("ticket sem pasta local e sem PID: %s",
                                                                     desfecho)
            else:
                self._finalizar(tid, "FAILED", "ORPHAN_PROCESS", -2, log, "PID sem pasta local")
        for tid, pasta in sorted(pastas.items()):
            if tid in self.encerrando or tid in self.preservadas:
                continue
            self._limpar_pasta(tid, pasta)
        # CR-012 (README §8.13): saidas que ficaram em gravacao numa queda viram FALHOU; a pasta fica no disco.
        falhadas = self.repo_saida.falhar_gravando_do_agente(conn, self.agente_id)
        conn.commit()
        if falhadas:
            self.log.warning("%d saida(s) em gravacao marcada(s) FALHOU na subida", falhadas,
                             extra={"acao": "STARTUP"})

    def _reabrir(self, tid, pasta, proc, usuario, log):
        processo = self.plat.reabrir_grupo(proc)
        if processo is None:
            return
        execucao = executor.Execucao(tid, pasta, usuario,
                                     os.path.join(self.cfg.agent.exec_work_dir, usuario) if usuario else None, None)
        execucao.processo = processo
        execucao.pid = processo.pid
        execucao.identidade = processo.identidade
        executor.pedir_encerramento(execucao, self.relogio(), grace_s=self.cfg.agent.kill_grace_s)
        if execucao.sem_identidade:
            self.preservadas.add(tid)  # CR-008, R-26: o unico rastro do processo fica
        elif not executor.avancar_encerramento(execucao, self.relogio()):
            self.encerrando[tid] = execucao  # o laco avanca o encerramento e limpa a pasta depois
            log.warning("grupo do ticket em encerramento na subida (pid %s)", processo.pid)

    def _finalizar(self, tid, status, motivo, rc, log, detalhe):
        """Finaliza o ticket RUNNING deste agente com a linha [SSS] no log (README §5.2)."""
        conn = self._conn()
        self._linha_sss(conn, tid, "%s: %s (agente %s)" % (motivo, detalhe, self.agente_id))
        if not self.repo.finalizar(conn, tid, self.agente_id, status, motivo, rc):
            log.warning("OWNERSHIP_LOST na subida: o ticket ja nao era deste agente")
        elif status == "SUCCESS":
            log.info("ticket finalizado na subida pelo resultado local: %s/%s", status, motivo)
        else:
            log.error("ticket finalizado na subida: %s/%s (%s)", status, motivo, detalhe)

    def _linha_sss(self, conn, tid, texto):
        ticket = self.repo.obter_ticket(conn, tid)
        if ticket is None:
            return
        try:
            self.repo_log.anexar(conn, tid, self.agente_id, int(ticket.get("log_offset_chars") or 0),
                                 "[SSS] %s\n" % texto)
            conn.commit()
        except Exception as exc:  # noqa: BLE001 - a linha e informativa; a finalizacao segue
            conn.rollback()
            _log.warning("linha [SSS] nao gravada no log do ticket (%s)", exc.__class__.__name__,
                         extra={"agente": self.agente_id, "ticket": tid, "acao": "STARTUP"})

    def _limpar_pasta(self, tid, pasta):
        execucao = executor.Execucao(tid, pasta, None, None, None)
        estado = _ler_estado(pasta, executor.PROC, self.plat) or _ler_estado(pasta, executor.SPAWN, self.plat) or {}
        usuario = estado.get("usuario_execucao")
        if usuario:
            execucao.usuario_execucao = usuario
            execucao.pasta_base = os.path.join(self.cfg.agent.exec_work_dir, usuario)
        try:
            executor.limpar(execucao)
        except Exception as exc:  # noqa: BLE001 - a pasta fica para a proxima subida
            self.preservadas.add(tid)
            _log.warning("pasta do ticket nao removida na subida (%s)", exc.__class__.__name__,
                         extra={"agente": self.agente_id, "ticket": tid, "acao": "STARTUP"})

    # ======================================================================
    # Laco (README §8.1)
    # ======================================================================

    def preparar_laco(self, esperar):
        """Estado do laco: mapa local, bombas do log, rodada do pump e os tres prazos.

        esperar(segundos): a unica espera do daemon, entre iteracoes (no maximo 1 s); o run_scheduler injeta a
        real e os testes, um duble. Nenhuma operacao do laco espera (CR-007, R-04)."""
        agente = self.cfg.agent
        self.execucoes = {}
        self.bombas = {}
        self.devolucoes_pendentes = set()
        # CR-012: saidas a gravar depois da finalizacao do ticket {tid: (Saida, Execucao, log)}.
        self.saidas = {}
        # Parada (README §8.11; F8.4d): _parando suspende claim e desdobro; _terminando abandona a saida em
        # andamento. DRAIN liga so o primeiro ate shutdown_grace_s; TERMINATE liga os dois.
        self._parando = False
        self._terminando = False
        self._drenagem_ate = None
        # Self-fencing e NODE_OFFLINE (F8.4c; README §8.8 e §8.9).
        self.cercado = False
        self._ref_relogio = None          # (SYSDATE, monotonico) do ultimo SYSDATE lido
        self._node_offline_suspenso_ate = None
        self.rodada = log_pump.Rodada(self.bombas, self.relogio, agente.heartbeat_interval_s / 2.0)
        self._esperar = esperar
        agora = self.relogio()
        self.prazos = {"rapido": agora, "heartbeat": agora, "orquestrador": agora}
        self._ultimo_aviso_disco = None
        self._mascarador_fixo = [v for v in self._segredos_lista() if v]
        self.codigo_saida = 0
        return self

    def _segredos_lista(self):
        seg = self.segredos
        valores = [getattr(seg, "oracle_password", None), getattr(seg, "purge_password", None),
                   getattr(seg, "monitor_password", None)]
        for cred in (getattr(seg, "ambientes", None) or {}).values():
            valores.append(getattr(cred, "password", None))
        return valores

    def executar(self, parada, esperar=None, ate=None, limite_s=None):
        """Laco principal ate a parada (flag com is_set() ou arquivo .stop). Devolve o codigo de saida.

        ate/limite_s: so para os testes (condicao de termino e prazo maximo do harness).
        """
        if not hasattr(self, "execucoes"):
            self.preparar_laco(esperar)
        agente = self.cfg.agent
        stop = os.path.join(agente.work_dir, "sss-%s.stop" % self.agente_id)
        fim = None if limite_s is None else self.relogio() + limite_s
        while True:
            self._iteracao()
            self._conferir_fence()
            agora = self.relogio()
            try:
                if agora >= self.prazos["rapido"]:
                    self.prazos["rapido"] = agora + agente.cancel_poll_interval_s
                    self._ciclo("rapido", self._ciclo_rapido)
                    self._conferir_fence()
                if agora >= self.prazos["heartbeat"]:
                    self.prazos["heartbeat"] = agora + agente.heartbeat_interval_s
                    self._ciclo("heartbeat", self._ciclo_heartbeat)
                    self._conferir_fence()
                if agora >= self.prazos["orquestrador"]:
                    self.prazos["orquestrador"] = agora + agente.orchestrator_interval_s
                    if not self.cercado:
                        self._ciclo("orquestrador", self._ciclo_orquestrador)
                        self._conferir_fence()
            except RegistroPerdido as exc:
                self.log.critical("REGISTRO_PERDIDO: %s; encerramento TERMINATE", exc, extra={"acao": "HB"})
                self.encerrar_tudo("TERMINATE", registro_perdido=True)
                return SAIDA_REGISTRO_PERDIDO
            if parada.is_set() or os.path.exists(stop):
                if agente.shutdown_mode != "DRAIN":
                    return self.encerrar_tudo("TERMINATE")
                if self._drenagem_ate is None:
                    self._iniciar_drenagem()
                if self._drenado() or self.relogio() >= self._drenagem_ate:
                    return self.encerrar_tudo("DRAIN")
            if (ate is not None and ate()) or (fim is not None and self.relogio() >= fim):
                return self.codigo_saida
            espera = min(self.prazos.values()) - self.relogio()
            self._esperar(max(0.0, min(INTERVALO_MAXIMO_ESPERA_S, espera)))

    # ---------------------------------------------------- parada DRAIN (README §8.11)

    def _iniciar_drenagem(self):
        """DRAIN: para claim e desdobro e aguarda os filhos por ate shutdown_grace_s, mantendo heartbeat,
        varredura, log pump, saida e fence pelo laco normal (CR-007, R-04)."""
        self._parando = True
        self._drenagem_ate = self.relogio() + self.cfg.agent.shutdown_grace_s
        self.log.warning("DRAIN: parada pedida; sem claim nem desdobro, aguardando %d execucao(oes) por ate %d s",
                         len(self.execucoes), self.cfg.agent.shutdown_grace_s, extra={"acao": "PARADA"})

    def _drenado(self):
        return not (self.execucoes or self.encerrando or getattr(self, "saidas", None))

    # ---------------------------------------------------- self-fencing (README §8.9)

    def _fence_vencido(self):
        return self.ultimo_hb_ok is not None and self.relogio() - self.ultimo_hb_ok > self.cfg.agent.fence_timeout_s

    def _conferir_fence(self):
        """A cada iteracao e depois de cada chamada ao banco (CR-007, R-04): sem heartbeat confirmado ha mais de
        fence_timeout_s (medido do inicio da transacao, CR-008 R-09), encerra TODAS as execucoes de uma vez pela
        maquina de estados (SIGTERM em todas, SIGKILL nas restantes depois de kill_grace_s), suspende claims,
        desdobro e NODE_OFFLINE e registra CRITICAL FENCED. Sai do modo cercado so com um heartbeat confirmado."""
        if self.cercado or not self._fence_vencido():
            return
        self.cercado = True
        rodando = [item for item in self.execucoes.values() if item.fase == _Item.RODANDO]
        for item in rodando:
            self._encerrar(item, "FENCED")
        self.log.critical("FENCED: sem heartbeat confirmado ha %.0f s (fence_timeout_s %d); %d execucao(oes) "
                          "encerrada(s), claims e desdobro suspensos ate o banco voltar",
                          self.relogio() - self.ultimo_hb_ok, self.cfg.agent.fence_timeout_s, len(rodando),
                          extra={"acao": "FENCE"})

    def _sair_do_cerco(self):
        self.cercado = False
        self.log.warning("FENCED encerrado: heartbeat confirmado; os tickets que o agente possuia sao finalizados "
                         "pelo resultado local ou como FENCED", extra={"acao": "FENCE"})

    def _salto_de_relogio(self, sysdate):
        """CR-007 D3 / CR-008 R-10: True (e inicia a suspensao do NODE_OFFLINE) se o avanco do SYSDATE diferir do
        avanco do monotonico em mais de SALTO_RELOGIO_S desde o ultimo SYSDATE lido."""
        agora = self.relogio()
        ref, self._ref_relogio = self._ref_relogio, (sysdate, agora)
        if ref is None or sysdate is None:
            return False
        diferenca = (sysdate - ref[0]).total_seconds() - (agora - ref[1])
        if abs(diferenca) <= SALTO_RELOGIO_S:
            return False
        self._node_offline_suspenso_ate = agora + self.cfg.agent.node_offline_timeout_s
        self.log.warning("SALTO_RELOGIO: o SYSDATE andou %.0f s diferente do relogio monotonico; NODE_OFFLINE "
                         "suspenso por %d s", diferenca, self.cfg.agent.node_offline_timeout_s, extra={"acao": "HB"})
        return True

    def _ciclo(self, nome, funcao):
        """Um ciclo isolado: erro registrado com contexto; erro de rede descarta a conexao (reconexao no
        ciclo seguinte, uma tentativa por ciclo, sem esperar)."""
        if not self.conexao.garantir():
            if nome == "rapido":
                self._iteracao_sem_banco()
            return
        try:
            funcao()
        except RegistroPerdido:
            raise
        except Exception as exc:  # noqa: BLE001 - o laco nunca cai por um ciclo
            self.log.error("ciclo %s falhou: %s", nome, exc, exc_info=not db_conn.eh_erro_rede(exc),
                           extra={"acao": nome.upper()})
            self.conexao.notificar_erro(exc)

    def _iteracao_sem_banco(self):
        """Sem banco, os processos seguem acompanhados localmente (timeout e teto local)."""
        self._conferir_limites()

    # ---------------------------------------------------- toda iteracao

    def _iteracao(self):
        """Maquinas de encerramento, coleta dos processos que terminaram e no maximo um flush final."""
        agora = self.relogio()
        for tid, ex in list(self.encerrando.items()):
            if executor.avancar_encerramento(ex, agora):
                del self.encerrando[tid]
                self._limpar(tid, ex.work_dir_ticket)
        flush_feito = False
        for tid, item in sorted(self.execucoes.items()):
            ex = item.execucao
            if item.fase == _Item.RODANDO:
                if executor.verificar(ex) is not None:
                    # Terminou sozinho: o grupo e encerrado mesmo assim (R-02), prevalece o resultado real.
                    self._encerrar(item, None)
                continue
            if item.fase == _Item.ENCERRANDO:
                if executor.avancar_encerramento(ex, agora):
                    item.fase = _Item.FINALIZAR
                continue
            if item.fase == _Item.FINALIZAR and not self._empacotar(item, agora):
                continue
            if item.fase == _Item.FINALIZAR and not flush_feito:
                flush_feito = self._finalizar_execucao(item)
        self._avancar_saidas(agora)

    # ---------------------------------------------------- saida (CR-012)

    def _empacotar(self, item, agora):
        """Etapa 1 da fase de saida, antes do flush final. True quando o ticket pode seguir para a finalizacao."""
        saida = item.saida
        if saida is None or saida.empacotada:
            return True
        if item.motivo in ("OWNERSHIP_LOST", "SHUTDOWN") or self._terminando:
            fase_saida.abandonar(saida, self.plat)
            return True
        agente = self.cfg.agent
        if saida.processo is None:
            fase_saida.iniciar_empacotar(saida, self.plat, agente.saida_max_bytes, agente.saida_max_arquivos, agora)
            if not saida.empacotada:
                return False
        elif not fase_saida.avancar_empacotar(saida, self.plat, agora):
            return False
        linha = fase_saida.linha_log(saida, self.agente_id, agente.saida_max_arquivos, agente.saida_max_bytes)
        if linha and item.execucao is not None and item.execucao.caminho_log:
            try:
                executor.anexar_linha_local(item.execucao, linha)
            except OSError as exc:  # a linha e informativa; a fase segue
                item.log.warning("linha [SSS] da saida nao gravada (%s)", exc.__class__.__name__,
                                 extra={"acao": "SAIDA"})
        if saida.resultado == fase_saida.EXCEDEU:
            item.log.warning("saida acima do limite (%s): a pasta fica no disco", saida.motivo, extra={"acao": "SAIDA"})
        return True

    def _avancar_saidas(self, agora):
        """Etapa 2, depois da finalizacao: grava a saida sem esperar, refazendo erro de banco a cada
        cancel_poll_interval_s. Ao terminar, remove a pasta (ZIP ou vazia) e o work_dir do ticket."""
        if not self.saidas or self._terminando:
            return
        conn = self.conexao.obter_conexao()
        if conn is None:
            return
        for tid, (saida, ex, log) in sorted(self.saidas.items()):
            if agora < saida.proxima_tentativa:
                continue
            try:
                desfecho = fase_saida.gravar(saida, conn, self.repo_saida, self.agente_id)
            except Exception as exc:  # noqa: BLE001 - pendencia refeita no proximo prazo
                saida.proxima_tentativa = agora + self.cfg.agent.cancel_poll_interval_s
                if not saida.avisou_pendencia:
                    saida.avisou_pendencia = True
                    log.warning("gravacao da saida pendente (%s)", exc.__class__.__name__, extra={"acao": "SAIDA"})
                self.conexao.notificar_erro(exc)
                return
            if desfecho == fase_saida.CONTINUA:
                continue
            del self.saidas[tid]
            if desfecho == fase_saida.POSSE_PERDIDA:
                log.error("OWNERSHIP_LOST na saida: nada gravado; a pasta fica no disco", extra={"acao": "SAIDA"})
            else:
                log.info("saida %s", saida.resultado, extra={"acao": "SAIDA"})
                if fase_saida.deve_remover_pasta(saida):
                    try:
                        fase_saida.remover_pasta(saida, self.plat)
                    except Exception as exc:  # noqa: BLE001 - fica para o purge (saida_retention_days)
                        log.warning("pasta de saida nao removida (%s)", exc.__class__.__name__,
                                    extra={"acao": "SAIDA"})
            self._limpar(tid, ex.work_dir_ticket, ex)

    def _encerrar(self, item, motivo):
        """Pede o encerramento do grupo (SIGTERM, prazo, SIGKILL) sem esperar. motivo None: saida natural."""
        if item.fase != _Item.RODANDO:
            return
        ex = item.execucao
        if motivo is not None and executor.verificar(ex) is not None:
            motivo = None  # o processo ja tinha terminado: prevalece o resultado real (README §5.6)
        item.motivo = motivo
        executor.pedir_encerramento(ex, self.relogio(), grace_s=self.cfg.agent.kill_grace_s)
        item.fase = _Item.ENCERRANDO
        if motivo is not None:
            item.log.warning("encerramento pedido: %s", motivo, extra={"acao": "ENCERRAR"})

    def _resultado(self, item):
        if item.motivo in _FINAL:
            return _FINAL[item.motivo]
        rc = executor.verificar(item.execucao)
        if rc is None:
            # Lider reaberto ou coletado por outro caminho: sem returncode, o agente nao sabe o desfecho.
            return ("FAILED", "ORPHAN_PROCESS", -2)
        return executor.traduzir_retorno(rc, self.plat.NOME)

    def _finalizar_execucao(self, item):
        """Passos 2 a 6 da finalizacao (README §8.7). True se fez um flush final nesta iteracao."""
        conn = self._conn()
        if conn is None:
            return False
        fez_flush = False
        if item.bomba is not None and not item.flush_ok:
            fez_flush = True
            desfecho = log_pump.flush_final(item.bomba, conn, self.repo_log, self.agente_id)
            if desfecho == log_pump.CONEXAO_INCERTA:
                self.conexao.fechar()
                return True
            if desfecho == log_pump.POSSE_PERDIDA:
                item.motivo = "OWNERSHIP_LOST"
            item.flush_ok = True
        if item.motivo == "OWNERSHIP_LOST":
            item.log.error("OWNERSHIP_LOST: o ticket ja nao e deste agente; nenhum status gravado",
                           extra={"acao": "FINALIZAR"})
            self._remover(item)
            return fez_flush
        if item.resultado is None:
            item.resultado = self._resultado(item)
            executor.registrar_resultado(item.execucao, *item.resultado)
        try:
            gravou = self.repo.finalizar(conn, item.tid, self.agente_id, *item.resultado)
        except Exception as exc:  # noqa: BLE001 - finalizacao pendente (CR-007 R-03), refeita no ciclo rapido
            if not item.finalizacao_pendente:
                item.log.warning("finalizacao pendente (%s)", exc.__class__.__name__, extra={"acao": "FINALIZAR"})
            item.finalizacao_pendente = True
            self.conexao.notificar_erro(exc)
            return fez_flush
        if gravou:
            item.log.info("ticket finalizado: %s/%s rc=%s", *item.resultado, extra={"acao": "FINALIZAR"})
            saida = item.saida
            if saida is not None and saida.resultado not in (None, fase_saida.ABANDONADA):
                # CR-012: a gravacao da saida segue fora do mapa de execucoes (nao ocupa vaga de claim).
                self.execucoes.pop(item.tid, None)
                self.bombas.pop(item.tid, None)
                self.saidas[item.tid] = (saida, item.execucao, item.log)
                return fez_flush
        else:
            item.log.error("OWNERSHIP_LOST na finalizacao: o resultado fica so no log local",
                           extra={"acao": "FINALIZAR"})
        self._remover(item)
        return fez_flush

    def _remover(self, item):
        self.execucoes.pop(item.tid, None)
        self.bombas.pop(item.tid, None)
        self._limpar(item.tid, item.execucao.work_dir_ticket if item.execucao else None,
                     item.execucao)

    def _limpar(self, tid, pasta, execucao=None):
        if not pasta:
            return
        if execucao is None:
            return self._limpar_pasta(tid, pasta)
        try:
            executor.limpar(execucao)
        except Exception as exc:  # noqa: BLE001 - a pasta fica para a proxima subida
            _log.warning("pasta do ticket nao removida (%s)", exc.__class__.__name__,
                         extra={"agente": self.agente_id, "ticket": tid, "acao": "LIMPEZA"})

    # ---------------------------------------------------- ciclo rapido

    def _ciclo_rapido(self):
        self._conferir_limites()
        if self.cercado:
            return  # em modo cercado, so o heartbeat tenta o banco (README §8.9)
        conn = self._conn()
        proprios = self.repo.varredura_propria(conn, self.agente_id)
        for tid, item in list(self.execucoes.items()):
            if item.fase == _Item.RESERVADO:
                continue
            if tid not in proprios:
                if item.fase == _Item.RODANDO:
                    self._encerrar(item, "OWNERSHIP_LOST")
                elif item.fase in (_Item.ENCERRANDO, _Item.FINALIZAR) and item.motivo != "OWNERSHIP_LOST" \
                        and not item.finalizacao_pendente:
                    item.motivo = "OWNERSHIP_LOST"
                continue
            if proprios[tid] == "S" and item.fase == _Item.RODANDO:
                self._encerrar(item, "CANCEL")
        for tid in sorted(set(proprios) - set(self.execucoes) - set(self.encerrando) - self.devolucoes_pendentes):
            self._reconciliar(tid)
        self._pendencias()

    def _conferir_limites(self):
        agora = self.relogio()
        for item in list(self.execucoes.values()):
            if item.fase != _Item.RODANDO:
                continue
            if item.timeout_s and agora - item.inicio > item.timeout_s:
                self._encerrar(item, "TIMEOUT")
            elif item.bomba is not None and item.bomba.excedeu_local():
                self._encerrar(item, "LOG_LIMIT")

    def _reconciliar(self, tid):
        """Ticket RUNNING deste agente fora do mapa local (CR-007 R-03; CR-008 R-01, R-02): mesmo tratamento do
        startup check para esse ticket."""
        conn = self._conn()
        pasta = os.path.join(self.cfg.agent.work_dir, "ticket_%d" % tid)
        log = _Log(_log, {"agente": self.agente_id, "ticket": tid, "acao": "VARREDURA"})
        if os.path.isdir(pasta) and not os.path.islink(pasta):
            proc = _ler_estado(pasta, executor.PROC, self.plat)
            spawn = _ler_estado(pasta, executor.SPAWN, self.plat)
            res = _ler_estado(pasta, executor.RESULT, self.plat)
            if proc is not None:
                self._reabrir(tid, pasta, proc, proc.get("usuario_execucao"), log)
            elif spawn is not None:
                usuario = spawn.get("usuario_execucao")
                base = os.path.join(self.cfg.agent.exec_work_dir, usuario) if usuario else self.cfg.agent.work_dir
                if self.plat.encerrar_ticket(base, tid, usuario, self.cfg.agent.kill_grace_s) == "NAO_SUPORTADO":
                    self.preservadas.add(tid)
                    log.warning("TALVEZ_INICIADO sem meio de encerrar nesta plataforma")
                log.error("TALVEZ_INICIADO: .sss_spawn sem .sss_proc")
            if res is not None:
                self._finalizar(tid, res["status"], res["status_motivo"], res["return_code"], log,
                                "resultado local")
            else:
                self._finalizar(tid, "FAILED", "ORPHAN_PROCESS", -2, log, "processo sem acompanhamento")
            if tid not in self.encerrando and tid not in self.preservadas:
                self._limpar_pasta(tid, pasta)
            return
        ticket = self.repo.obter_ticket(conn, tid)
        if ticket is not None and ticket.get("process_id") is None:
            self._devolver(tid, log)
        else:
            self._finalizar(tid, "FAILED", "ORPHAN_PROCESS", -2, log, "PID sem pasta local")

    def _devolver(self, tid, log):
        try:
            desfecho = self.repo.devolver(self._conn(), tid, self.agente_id)
        except Exception as exc:  # noqa: BLE001 - devolucao pendente (CR-008, R-08)
            self.devolucoes_pendentes.add(tid)
            log.warning("devolucao pendente (%s)", exc.__class__.__name__, extra={"acao": "DEVOLVER"})
            self.conexao.notificar_erro(exc)
            return
        self.devolucoes_pendentes.discard(tid)
        if desfecho == "DEVOLVIDO":
            log.info("devolucao: %s", desfecho, extra={"acao": "DEVOLVER"})
        else:
            log.warning("devolucao: %s", desfecho, extra={"acao": "DEVOLVER"})

    def _pendencias(self):
        """Finalizacao, devolucao e PID pendentes (CR-007 R-03; CR-008 R-08), ate rowcount 1 ou 0."""
        for tid in sorted(self.devolucoes_pendentes):
            self._devolver(tid, _Log(_log, {"agente": self.agente_id, "ticket": tid, "acao": "DEVOLVER"}))
        for item in list(self.execucoes.values()):
            if item.pid_pendente:
                self._registrar_pid(item)
            if item.finalizacao_pendente and item.fase == _Item.FINALIZAR:
                self._finalizar_execucao(item)

    # ---------------------------------------------------- heartbeat e pump

    def _ciclo_heartbeat(self):
        conn = self._conn()
        ids = sorted(set(self.execucoes) | self.devolucoes_pendentes)
        inicio = self.relogio()  # CR-008, R-09: instante antes do primeiro UPDATE
        perdidos, sysdate = self.repo.heartbeat(conn, self.agente_id, self.hostname, self.pid, ids)
        self.ultimo_hb_ok = inicio
        self._salto_de_relogio(sysdate)
        if self.cercado:
            self._sair_do_cerco()
        for tid in perdidos:
            item = self.execucoes.get(tid)
            if item is not None and item.fase == _Item.RODANDO:
                self._encerrar(item, "OWNERSHIP_LOST")
            elif item is not None:
                item.motivo = "OWNERSHIP_LOST"
            self.devolucoes_pendentes.discard(tid)
        res = self.rodada.executar(conn, self.repo_log, self.agente_id)
        for tid in res.posse_perdida:
            item = self.execucoes.get(tid)
            if item is None:
                continue
            if item.fase == _Item.RODANDO:
                self._encerrar(item, "OWNERSHIP_LOST")
            item.motivo = "OWNERSHIP_LOST"
        if res.conexao_incerta:
            self.conexao.fechar()

    # ---------------------------------------------------- orquestrador e claim

    def _ciclo_orquestrador(self):
        agente = self.cfg.agent
        conn = self._conn()
        self.ambientes_ativos, _inexistentes = self.repo.ambientes_ativos(conn, agente.ambientes_atendidos)
        criticos = sss_config.config_criticos(self.cfg)
        for codigo, outra in self.repo.conferir_config(conn, self.agente_id, criticos, agente.node_offline_timeout_s):
            self.log.error("CONFIG_DIVERGENTE: agente %s local=%s remoto=%s", codigo, criticos, outra,
                           extra={"acao": "CONFIG"})
        self._node_offline()
        self._desdobro()
        self._claims()

    def _node_offline(self):
        """Deteccao de no offline (README §8.8; F8.4c): so com o proprio heartbeat em dia (menos de
        fence_timeout_s / 2), fora do modo cercado e fora da suspensao por salto de relogio, que tambem e
        conferido na propria transacao (CR-008, R-10)."""
        agente = self.cfg.agent
        agora = self.relogio()
        if self.cercado or self.ultimo_hb_ok is None or agora - self.ultimo_hb_ok >= agente.fence_timeout_s / 2.0:
            return
        if self._node_offline_suspenso_ate is not None:
            if agora < self._node_offline_suspenso_ate:
                return
            self._node_offline_suspenso_ate = None
        marcados = self.repo.marcar_node_offline(self._conn(), self.agente_id, agente.node_offline_timeout_s,
                                                 self._salto_de_relogio)
        if marcados:
            self.log.info("NODE_OFFLINE: ticket(s) %s marcado(s) (heartbeat de outro agente vencido ha mais de %d s)",
                          ", ".join(str(i) for i in marcados), agente.node_offline_timeout_s,
                          extra={"acao": "NODE_OFFLINE"})

    def _desdobro(self):
        """Desdobro dos agendamentos (README §7.5; F8.4b): uma transacao por regra, com orcamento de tempo.
        Suspenso na parada (e, no F8.4c, em modo cercado)."""
        if self._parando or self.cercado:
            return
        if self.desdobro is None:
            self.desdobro = desdobro.Desdobro(self.repo_agenda, self.repo, self.agente_id, self.cfg.agent,
                                              self.relogio)
        stats = self.desdobro.executar(self._conn(), continuar=self._pode_seguir)
        if stats["regras"]:
            self.log.info("desdobro: %(regras)d regra(s), %(tickets)d ticket(s), %(pausas)d pausa(s), "
                          "%(puladas)d com outro agente", stats, extra={"acao": "DESDOBRO"})

    def _pode_seguir(self):
        """Entre chamadas ao banco do desdobro e do claim: para se o fence venceu (e cerca) ou se ha parada."""
        self._conferir_fence()
        return not (self._parando or self.cercado)

    def _claims(self):
        agente = self.cfg.agent
        vagas = agente.max_parallel_jobs - len(self.execucoes)
        if vagas <= 0 or not self.ambientes_ativos or not self._pode_seguir():
            return
        livre = self.plat.espaco_livre_mb(self.cfg.logging.log_dir)
        if livre < agente.log_dir_min_livre_mb:
            agora = self.relogio()
            if self._ultimo_aviso_disco is None or agora - self._ultimo_aviso_disco >= INTERVALO_AVISO_DISCO_S:
                self._ultimo_aviso_disco = agora
                self.log.warning("DISCO_LOG: %d MB livres em log_dir (minimo %d): sem claim", livre,
                                 agente.log_dir_min_livre_mb, extra={"acao": "CLAIM"})
            return
        if agente.saida_dir:
            livre_saida = self.plat.espaco_livre_mb(agente.saida_dir)
            if livre_saida < agente.log_dir_min_livre_mb:
                agora = self.relogio()
                if self._ultimo_aviso_disco is None or agora - self._ultimo_aviso_disco >= INTERVALO_AVISO_DISCO_S:
                    self._ultimo_aviso_disco = agora
                    self.log.warning("DISCO_SAIDA: %d MB livres em saida_dir (minimo %d): sem claim", livre_saida,
                                     agente.log_dir_min_livre_mb, extra={"acao": "CLAIM"})
                return
        inicio = self.relogio()
        orcamento = agente.heartbeat_interval_s / 2.0
        conn = self._conn()
        interpretadores = [k for k, _v in agente.interpretadores]
        for cand in self.repo.candidatos(conn, self.ambientes_ativos, interpretadores, vagas,
                                         agente.fila_envelhecimento_min):
            if len(self.execucoes) >= agente.max_parallel_jobs or self.relogio() - inicio > orcamento \
                    or not self._pode_seguir():
                break
            ok, motivo, started_at = self.repo.claim(conn, cand["id"], cand["script_id"], cand["ambiente"],
                                                     self.agente_id)
            if not ok:
                continue
            # CR-007, R-03: no mapa local logo depois do COMMIT do claim, antes de qualquer outra operacao.
            item = _Item(cand["id"], started_at, _Log(_log, {"agente": self.agente_id, "ticket": cand["id"],
                                                             "acao": "SPAWN"}))
            self.execucoes[item.tid] = item
            self._iniciar(item)

    # ---------------------------------------------------- pre-validacao e spawn

    def _iniciar(self, item):
        """Pre-validacao (README §8.4 passo 1), releitura do cancelamento, spawn e registro do PID."""
        try:
            pre = self._prevalidar(item)
        except Exception as exc:  # noqa: BLE001
            return self._erro_antes_do_spawn(item, exc)
        if pre is None:
            return
        snap, argv, script_real, contexto = pre
        try:
            if self.repo.cancelamento_pedido(self._conn(), item.tid):
                return self._finalizar_sem_spawn(item, ("CANCELLED", "CANCEL_USER", -1), None)
        except Exception as exc:  # noqa: BLE001
            return self._erro_antes_do_spawn(item, exc)
        self._spawn(item, snap, argv, script_real, contexto)

    def _prevalidar(self, item):
        """Devolve (snap, argv, script_real, contexto) ou None (ticket ja finalizado PRECHECK_FAILED).

        CR-011: o conteudo do arquivo nao e conferido (sem hash); o caminho pode ter link simbolico."""
        conn = self._conn()
        ticket = self.repo.obter_ticket(conn, item.tid)
        item.ticket = ticket
        contexto = self.repo.contexto_execucao(conn, ticket)
        script, ambiente = contexto["script"], contexto["ambiente"]
        try:
            snap, argv, script_real = params_compiler.validar_snapshot(ticket["parametros_enviados"],
                                                                       self._cfg_snapshot())
        except params_compiler.SnapshotErro as exc:
            codigo = exc.motivo[len("PATH_GUARD_"):] if exc.motivo.startswith("PATH_GUARD_") else exc.motivo
            return self._recusar(item, codigo)
        if script is None or snap["path_file"] != script["path_file"] or snap["interpretador"] != script["interpretador"]:
            return self._recusar(item, "CADASTRO_MUDOU")
        if script.get("ativo") != "S":
            return self._recusar(item, "SCRIPT_INATIVO")
        if not self.repo.script_ativo_homologado(conn, script["id"], ticket["ambiente"]):
            return self._recusar(item, "NAO_HOMOLOGADO")
        if ambiente is None or ambiente.get("ativo") != "S":
            return self._recusar(item, "AMBIENTE_INATIVO")
        ok, _motivo = rbac.pode_executar(contexto["ctx"], script, ambiente, contexto["homologacoes"])
        if not ok:
            return self._recusar(item, "SEM_PERMISSAO")
        return snap, argv, script_real, contexto

    def _cfg_snapshot(self):
        agente = self.cfg.agent

        class _Cfg(object):
            interpretadores = dict(agente.interpretadores)
            dirs_sss = tuple(d for d in (self.cfg.logging.log_dir, agente.work_dir, agente.exec_work_dir) if d)
        return _Cfg()

    def _recusar(self, item, codigo):
        item.log.warning("pre-validacao recusada: %s", codigo, extra={"acao": "PRECHECK"})
        self._finalizar_sem_spawn(item, _PRECHECK, "pre-validacao recusada: %s (agente %s)" % (codigo, self.agente_id))
        return None

    def _erro_antes_do_spawn(self, item, exc):
        """Erro de banco antes do spawn (CR-008, R-07): rede ou prazo devolvem; o resto e PRECHECK_FAILED."""
        if db_conn.eh_erro_rede(exc) or db_conn.eh_tempo_esgotado(exc):
            item.log.warning("banco indisponivel antes do spawn: devolucao (%s)", exc.__class__.__name__,
                             extra={"acao": "PRECHECK"})
            self.conexao.notificar_erro(exc)
            self.execucoes.pop(item.tid, None)
            self.devolucoes_pendentes.add(item.tid)
            if self.conexao.obter_conexao() is not None:
                self._devolver(item.tid, item.log)
            return None
        pfx, num = db_conn.classificar_erro(exc)
        if pfx:
            linha = "ERRO_BANCO: %s-%05d" % (pfx, num)
        else:
            linha = "pre-validacao recusada: %s (agente %s)" % (exc.__class__.__name__, self.agente_id)
        item.log.error("falha antes do spawn: %s", linha, exc_info=not pfx, extra={"acao": "PRECHECK"})
        self._finalizar_sem_spawn(item, _PRECHECK, linha)
        return None

    def _finalizar_sem_spawn(self, item, resultado, linha_sss):
        """Finaliza o ticket que nao chegou a iniciar (PRECHECK_FAILED ou CANCELLED), com a linha [SSS]."""
        conn = self._conn()
        if linha_sss:
            self._linha_sss(conn, item.tid, linha_sss)
        item.resultado = resultado
        item.fase = _Item.FINALIZAR
        item.flush_ok = True
        self._finalizar_execucao_sem_processo(item)

    def _finalizar_execucao_sem_processo(self, item):
        try:
            gravou = self.repo.finalizar(self._conn(), item.tid, self.agente_id, *item.resultado)
        except Exception as exc:  # noqa: BLE001 - finalizacao pendente
            item.finalizacao_pendente = True
            item.log.warning("finalizacao pendente (%s)", exc.__class__.__name__, extra={"acao": "FINALIZAR"})
            self.conexao.notificar_erro(exc)
            return
        if not gravou:
            item.log.error("OWNERSHIP_LOST: o ticket ja nao e deste agente", extra={"acao": "FINALIZAR"})
        else:
            item.log.info("ticket finalizado sem execucao: %s/%s", item.resultado[0], item.resultado[1],
                          extra={"acao": "FINALIZAR"})
        self.execucoes.pop(item.tid, None)
        if item.execucao is not None:
            self._limpar(item.tid, item.execucao.work_dir_ticket, item.execucao)

    def _spawn(self, item, snap, argv, script_real, contexto):
        agente = self.cfg.agent
        ticket = item.ticket
        usuario = env_builder.usuario_execucao(self.cfg, ticket["ambiente"])
        rotulo = "SSS-%s-%s" % (self.agente_id, item.tid)
        try:
            work_dir_ticket = executor.preparar_diretorio(agente.work_dir, item.tid, startup_concluido=True)
            fd, caminho = executor.abrir_log(self.cfg.logging.log_dir, ticket["ambiente"], snap["script_nome"],
                                             item.started_at, item.tid, snap.get("script_id"))
        except Exception as exc:  # noqa: BLE001 - CR-007 R-17: sem arquivo de log, a causa vai para o CLOB
            item.log.error("falha antes do spawn: %s", exc, extra={"acao": "SPAWN"})
            return self._finalizar_sem_spawn(item, _FINAL["SPAWN_ERROR"], "falha ao iniciar: %s (agente %s)" % (
                exc.__class__.__name__, self.agente_id))
        timeout = contexto["script"].get("timeout_seg") or agente.script_timeout_s
        conexao = None
        saida = None
        try:
            if agente.saida_dir:
                # CR-012 (README §8.13): pasta de saida com as partes do log e o mesmo minuto.
                base, relativo = pastas_log.pasta_saida(agente.saida_dir, ticket["ambiente"], snap["script_nome"],
                                                        item.started_at, item.tid, snap.get("script_id"))
                saida = fase_saida.Saida(item.tid, base, relativo, usuario, work_dir_ticket)
            ticket_env = dict(ticket, started_at=item.started_at)
            env = env_builder.construir(self.cfg, self.segredos, ticket_env, contexto["ambiente"], script_real,
                                        work_dir_ticket, dict(os.environ), self.plat.NOME, snapshot=snap,
                                        agendamento=contexto["agendamento"], caminho_log=caminho,
                                        timeout_seg=timeout, hostname=self.hostname, versao=sss_config.VERSAO_SSS,
                                        pasta_saida=saida.pasta if saida else None)
            conexao = env.get(env_builder.VAR_CONEXAO)
        except Exception as exc:  # noqa: BLE001 - CR-007 R-17: SPAWN_ERROR
            ex = executor.falha_antes_do_spawn(fd, item.tid, exc, rotulo, work_dir_ticket)
            return self._apos_iniciar(item, ex, snap, conexao)
        ex = executor.iniciar(item.tid, argv, fd, env, work_dir_ticket, usuario, agente.exec_work_dir,
                              dict(self.plat.RLIMITS_PADRAO), rotulo,
                              saida=(saida.base, saida.relativo) if saida else None)
        if not ex.spawn_error:
            item.saida = saida
        item.timeout_s = timeout
        self._apos_iniciar(item, ex, snap, conexao)

    def _apos_iniciar(self, item, ex, snap, conexao):
        item.execucao = ex
        item.inicio = self.relogio()
        if ex.caminho_log:
            item.bomba = log_pump.Bomba(
                ex.caminho_log, item.tid, log_pump.mascarador_do_ticket(self._mascarador_fixo, conexao, snap),
                self.cfg.logging.max_log_size_bytes, self.cfg.logging.max_local_log_size_bytes, 0,
                self.unidade_suplementar)
            self.bombas[item.tid] = item.bomba
        if ex.spawn_error and not ex.falhou_apos_spawn:
            item.motivo = "SPAWN_ERROR"
            item.fase = _Item.FINALIZAR
            return
        if ex.falhou_apos_spawn:
            # CR-008, R-01: o grupo ja recebeu SIGTERM; acompanhado ate morrer, sem registrar_pid.
            item.motivo = "SPAWN_ERROR"
            item.fase = _Item.ENCERRANDO
            return
        item.fase = _Item.RODANDO
        item.pid_pendente = True
        self._registrar_pid(item)

    def _registrar_pid(self, item):
        ex = item.execucao
        try:
            ok = self.repo.registrar_pid(self._conn(), item.tid, self.agente_id, ex.pid, ex.identidade)
        except Exception as exc:  # noqa: BLE001 - PID pendente (CR-008, R-08)
            if not item.avisou_pid:
                item.avisou_pid = True
                item.log.warning("PID pendente (%s)", exc.__class__.__name__, extra={"acao": "SPAWN"})
            self.conexao.notificar_erro(exc)
            return
        item.pid_pendente = False
        if not ok:
            self._encerrar(item, "OWNERSHIP_LOST")
        else:
            item.log.info("script iniciado (pid %s)", ex.pid, extra={"acao": "SPAWN"})

    # ---------------------------------------------------- parada

    def encerrar_tudo(self, modo, registro_perdido=False):
        """Fim da parada (README §8.11): TERMINATE nos grupos que restarem (todos, no TERMINATE; os que passaram
        de shutdown_grace_s, no DRAIN), finalizados SHUTDOWN; flush dos logs, PARADO com AGENTE_FIM, remocao
        do .stop, recursos liberados e saida 0."""
        self.log.warning("encerramento %s: %d execucao(oes) local(is)", modo, len(self.execucoes),
                         extra={"acao": "PARADA"})
        # CR-012: a saida em andamento e abandonada (a pasta fica no disco; GRAVANDO vira FALHOU na subida).
        self._parando = True
        self._terminando = True
        for tid, (_saida, ex, log) in sorted(getattr(self, "saidas", {}).items()):
            log.warning("saida abandonada na parada", extra={"acao": "PARADA"})
            self._limpar(tid, ex.work_dir_ticket, ex)
        if hasattr(self, "saidas"):
            self.saidas.clear()
        for item in list(self.execucoes.values()):
            self._encerrar(item, "SHUTDOWN")
        limite = self.relogio() + self.cfg.agent.kill_grace_s + 5
        while (self.execucoes or self.encerrando) and self.relogio() < limite:
            self._iteracao()
            if self.execucoes or self.encerrando:
                self._esperar(0.05)
        conn = self._conn() if self.conexao.garantir() else None
        if conn is not None and not registro_perdido:
            try:
                self.repo.encerrar_agente(conn, self.agente_id, self.hostname, self.pid, modo)
            except Exception as exc:  # noqa: BLE001 - a parada segue
                self.log.error("registro de parada falhou: %s", exc, extra={"acao": "PARADA"})
        stop = os.path.join(self.cfg.agent.work_dir, "sss-%s.stop" % self.agente_id)
        if os.path.exists(stop):
            os.unlink(stop)
        self.liberar_recursos()
        return 0



class _Item(object):
    """Um ticket no mapa local do agente (README §8.7)."""

    RESERVADO = "RESERVADO"
    RODANDO = "RODANDO"
    ENCERRANDO = "ENCERRANDO"
    FINALIZAR = "FINALIZAR"

    def __init__(self, tid, started_at, log):
        self.tid = tid
        self.started_at = started_at
        self.log = log
        self.fase = _Item.RESERVADO
        self.ticket = None
        self.execucao = None
        self.bomba = None
        self.motivo = None
        self.resultado = None
        self.inicio = None
        self.timeout_s = None
        self.flush_ok = False
        self.pid_pendente = False
        self.avisou_pid = False
        self.finalizacao_pendente = False
        self.saida = None  # CR-012: fase_saida.Saida quando o agente tem saida_dir
