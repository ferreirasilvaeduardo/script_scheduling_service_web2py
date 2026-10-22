# -*- coding: utf-8 -*-
"""Verificacao de saude no padrao Nagios (README §13; F9.1b; CR-007 R-18; CR-008 E3, R-15, R-16).

Roda com a conta so de leitura do papel monitor ([monitor] user e password no secrets.cfg; a conta do agente
nao le tbsss_audit). Uso:

    python scripts/health.py [--config <config.ini>] [--no-pid-min 2] [--queue-warn 500] [--queue-crit 5000]
                            [--wait-warn-min 30] [--wait-crit-min 120] [--purge-days 2]

Saida: a primeira linha e "SSS <ESTADO> - <n> problema(s) | <dados de desempenho>", depois uma linha por
problema. Codigo: 0 OK, 1 WARNING, 2 CRITICAL, 3 UNKNOWN (configuracao, segredos, conexao ou erro de banco).
Sem log em arquivo: a saida do plugin fica registrada pelo monitoramento.
"""
import argparse
import os
import sys

_BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(_BASE, "modules"))

import agents_service  # noqa: E402
import db_conn  # noqa: E402
import sql_ident  # noqa: E402
import sss_config  # noqa: E402
from repo_oracle import health as saude_sql  # noqa: E402

OK, WARNING, CRITICAL, UNKNOWN = 0, 1, 2, 3
STATES = ("OK", "WARNING", "CRITICAL", "UNKNOWN")
_HEALTHY = (agents_service.OK, agents_service.DELAYED)


class Check(object):
    """As verificacoes do README §13 sobre uma conexao ja aberta; um unico agora_banco() para todas."""

    def __init__(self, cfg, conn, args, repo=None):
        self.cfg = cfg
        self.conn = conn
        self.args = args
        self.repo = repo or saude_sql.RepoHealth.from_config(cfg)
        agente = cfg.agent
        self.thresholds = agents_service.Thresholds(agente.heartbeat_interval_s, agente.fence_timeout_s,
                                                 agente.node_offline_timeout_s)
        self.problems = []  # (nivel, texto)
        self.performance = []

    def _problem(self, level, text):
        self.problems.append((level, text))

    def run(self):
        agora = db_conn.db_now(self.conn)
        self._version()
        agentes = self.repo.agents(self.conn)
        self._agents(agentes, agora)
        self._environments(agentes, agora)
        self._queue(agentes, agora)
        self._no_pid(agora)
        self._config(agentes)
        self._purge(agora)
        return max([nivel for nivel, _t in self.problems] or [OK])

    def _version(self):
        versao = self.repo.schema_version(self.conn)
        if versao != sql_ident.SCHEMA_VERSION:
            self._problem(CRITICAL, "versao do esquema %s, esperada %d (README §11.1)"
                           % (versao, sql_ident.SCHEMA_VERSION))

    def _agents(self, agents, now):
        saudaveis = 0
        for ag in agents:
            if ag["status"] != "ACTIVE":
                continue
            saude = agents_service.health(ag, now, self.thresholds)
            if saude in _HEALTHY:
                saudaveis += 1
            elif saude == agents_service.AT_RISK:
                self._problem(WARNING, "agente %s em risco: heartbeat ha %s (fence %d s)" % (
                    ag["code"], self._age(ag, now), self.thresholds.fence_timeout_s))
            else:
                self._problem(CRITICAL, "agente %s ATIVO sem heartbeat ha %s (node_offline %d s)" % (
                    ag["code"], self._age(ag, now), self.thresholds.node_offline_timeout_s))
        self.performance.append("healthy_agents=%d" % saudaveis)

    @staticmethod
    def _age(ag, now):
        hb = ag.get("heartbeat_at")
        return "-" if hb is None else "%d s" % max(0, int((now - hb).total_seconds()))

    def _environments(self, agents, now):
        atendidos = set()
        for ag in agents:
            if ag["status"] == "ACTIVE" and agents_service.health(ag, now, self.thresholds) in _HEALTHY:
                atendidos.update(a.strip() for a in (ag.get("environments") or "").split(",") if a.strip())
        for nome in self.repo.active_environments(self.conn):
            if nome not in atendidos:
                self._problem(CRITICAL, "ambiente %s ativo sem nenhum agente saudavel" % nome)

    def _queue(self, agents, now):
        atendidos = saude_sql.served_pairs(agents, now, self.thresholds)
        for g in saude_sql.unattended_queue(self.repo.queue_by_pair(self.conn, now), atendidos):
            self._problem(CRITICAL, "fila sem atendente: %d tickets de %s/%s, o mais antigo desde %s" % (
                g["quantidade"], g["environment"], g["interpreter"], g["mais_antigo"].strftime("%Y-%m-%d %H:%M:%S")))
        qtd, antigo = self.repo.overdue_queue(self.conn, now)
        espera_min = 0 if antigo is None else max(0, int((now - antigo).total_seconds()) // 60)
        a = self.args
        if qtd >= a.fila_crit or espera_min >= a.espera_crit_min:
            nivel = CRITICAL
        elif qtd >= a.fila_warn or espera_min >= a.espera_warn_min:
            nivel = WARNING
        else:
            nivel = OK
        if nivel != OK:
            self._problem(nivel, "fila vencida: %d tickets PENDING, espera maxima %d min" % (qtd, espera_min))
        self.performance.append("overdue_queue=%d;%d;%d" % (qtd, a.fila_warn, a.fila_crit))
        self.performance.append("max_wait_min=%d;%d;%d" % (espera_min, a.espera_warn_min, a.espera_crit_min))

    def _no_pid(self, now):
        for t in self.repo.running_without_pid(self.conn, now, self.args.sem_pid_min):
            self._problem(WARNING, "ticket %d RUNNING sem PID no agente %s desde %s" % (
                t["id"], t["agent_id"], t["started_at"].strftime("%Y-%m-%d %H:%M:%S")))

    def _config(self, agents):
        local = sss_config.critical_config(self.cfg)
        for ag in agents:
            if ag["status"] == "ACTIVE" and ag.get("critical_config") and ag["critical_config"] != local:
                self._problem(WARNING, "agente %s com configuracao divergente: %s (local: %s)" % (
                    ag["code"], ag["critical_config"], local))

    def _purge(self, now):
        if self.repo.last_purge(self.conn, now, self.args.purge_dias) is None:
            self._problem(WARNING, "nenhum PURGE auditado nos ultimos %d dias (README §11.3)" % self.args.purge_dias)

    def output(self, code):
        n = len(self.problems)
        linhas = ["SSS %s - %d problema%s | %s" % (STATES[code], n, "" if n == 1 else "s",
                                                  " ".join(self.performance))]
        ordenados = sorted(self.problems, key=lambda p: -p[0])
        linhas.extend("%s: %s" % (STATES[nivel], texto) for nivel, texto in ordenados)
        return "\n".join(linhas) + "\n"


def _arguments(argv):
    parser = argparse.ArgumentParser(description="Saude do SSS no padrao Nagios (README §13)")
    parser.add_argument("--config", default=None, help="config.ini (padrao: instance/)")
    parser.add_argument("--no-pid-min", dest="sem_pid_min", type=int, default=2, help="RUNNING sem PID ha mais de N minutos")
    parser.add_argument("--queue-warn", dest="fila_warn", type=int, default=500, help="PENDING vencidos para WARNING")
    parser.add_argument("--queue-crit", dest="fila_crit", type=int, default=5000, help="PENDING vencidos para CRITICAL")
    parser.add_argument("--wait-warn-min", dest="espera_warn_min", type=int, default=30, help="espera maxima (min) para WARNING")
    parser.add_argument("--wait-crit-min", dest="espera_crit_min", type=int, default=120, help="espera maxima (min) para CRITICAL")
    parser.add_argument("--purge-days", dest="purge_dias", type=int, default=2, help="dias sem PURGE auditado para WARNING")
    return parser.parse_args(argv)


def _unknown(output, reason):
    output.write("SSS UNKNOWN - %s\n" % reason)
    return UNKNOWN


def main(argv=None, connect=None, output=None):
    """conectar(cfg, segredos) e o ponto de injecao dos testes; saida recebe o texto do plugin (stdout)."""
    output = output or sys.stdout
    args = _arguments(argv)
    try:
        cfg = sss_config.get_config(log_name="health", path=args.config)
        segredos = sss_config.load_secrets(cfg.secrets.secrets_file, cfg=cfg, role="monitor")
    except sss_config.ConfigError as exc:
        return _unknown(output, "configuracao invalida: %s" % exc)
    try:
        conn = (connect or _connect)(cfg, segredos)
    except Exception as exc:
        return _unknown(output, "falha ao conectar no Oracle: %s" % db_conn.translate_error(exc))
    try:
        verificacao = Check(cfg, conn, args)
        codigo = verificacao.run()
    except Exception as exc:
        return _unknown(output, "falha de banco: %s" % db_conn.translate_error(exc))
    finally:
        conn.close()
    output.write(verificacao.output(codigo))
    return codigo


def _connect(cfg, secrets):
    return db_conn.connect(cfg, secrets, role="monitor")


if __name__ == "__main__":
    sys.exit(main())
