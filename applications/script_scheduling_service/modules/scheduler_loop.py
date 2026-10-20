# -*- coding: utf-8 -*-
"""Daemon do agente: inicializacao fail-fast e startup check (README §8.12; CR-007 R-01, R-11, R-17, R-23;
CR-008 R-01, R-02, R-17, R-26, E4). O laco (§8.1) entra no F8.3c.

Python puro (sem web2py): o processo inteiro precisa de uma unica thread antes do primeiro spawn, por causa
do preexec_fn (README §3.1, C10). Toda primitiva de SO vem de `plataforma`; o banco, do `db_conn` e dos
repositorios internos do daemon. Cada passo que falha registra CRITICAL e sai com um codigo proprio.
"""
import datetime
import logging
import os
import pwd
import socket
import threading
import time

import db_conn
import executor
import plataforma
import sss_config
from repo_oracle.scheduler_fila import AgenteDuplicado, RepoSchedulerFila
from repo_oracle.scheduler_log import RepoSchedulerLog

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

DIVERGENCIA_RELOGIO_S = 60
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
                 carregar_segredos=None):
        self.cfg = cfg
        self.segredos = segredos
        self.plat = plat or plataforma
        self.conexao = conexao
        self.repo = repo
        self.repo_log = repo_log
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
        if os.geteuid() in tuple(int(u) for u in agente.script_owner_uids or ()):
            self._falhar(SAIDA_USUARIO, "o UID do agente nao pode estar em script_owner_uids (CR-007, R-15)")
        try:
            sss_config.verificar_codificacao()
        except sss_config.ConfigErro as exc:
            self._falhar(SAIDA_CONFIG, "%s", exc)
        if not self.plat.locale_disponivel(agente.child_locale):
            self._falhar(SAIDA_CONFIG, "child_locale %s nao consta em locale -a (CR-007, R-17)", agente.child_locale)
        if self.cfg.app.sss_env != "DEV" and not agente.ambientes_exigem_hash:
            self.log.warning("SEM_EXIGENCIA_HASH: [agent] ambientes_exigem_hash vazio fora de DEV (CR-008, E4)")
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
        donos = tuple(int(u) for u in agente.script_owner_uids or ())
        proibidos = self._uids_proibidos()
        dirs_sss = tuple(d for d in (self.cfg.logging.log_dir, agente.work_dir, agente.exec_work_dir) if d)
        if not agente.interpretadores:
            self._falhar(SAIDA_DIRETORIOS, "[agent] interpretadores vazio: o agente nao executaria nada")
        for logico, caminho in agente.interpretadores:
            try:
                self.plat.validar_interpretador_executavel(caminho, donos, uids_proibidos=proibidos,
                                                           dirs_sss=dirs_sss)
            except Exception as exc:  # noqa: BLE001 - PathGuardErro e afins: CRITICAL com o codigo
                self._falhar(SAIDA_DIRETORIOS, "interpretador %s (%s) recusado: %s", logico, caminho,
                             getattr(exc, "codigo", exc.__class__.__name__))
        if self.cfg.app.sss_env != "DEV":
            falhas = self.plat.validar_execucao(agente.usuarios_execucao, agente.exec_work_dir, donos)
            for falha in falhas:
                self.log.critical("execucao fora de DEV: %s", falha)
            if falhas:
                self._falhar(SAIDA_DIRETORIOS, "%d falha(s) na conferencia do helper e do sudoers", len(falhas))

    def _uids_proibidos(self):
        uids = [os.geteuid()]
        for _amb, usuario in self.cfg.agent.usuarios_execucao or ():
            try:
                uids.append(pwd.getpwnam(usuario).pw_uid)
            except KeyError:  # usuario inexistente: o validar_execucao registra a falha
                continue
        return tuple(uids)

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
            self._limpar(tid, pasta)

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

    def _limpar(self, tid, pasta):
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
