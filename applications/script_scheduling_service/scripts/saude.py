# -*- coding: utf-8 -*-
"""Verificacao de saude no padrao Nagios (README §13; F9.1b; CR-007 R-18; CR-008 E3, R-15, R-16).

Roda com a conta so de leitura do papel monitor ([monitor] user e password no secrets.cfg; a conta do agente
nao le tbsss_auditoria). Uso:

    python scripts/saude.py [--config <config.ini>] [--sem-pid-min 2] [--fila-warn 500] [--fila-crit 5000]
                            [--espera-warn-min 30] [--espera-crit-min 120] [--purge-dias 2]

Saida: a primeira linha e "SSS <ESTADO> - <n> problema(s) | <dados de desempenho>", depois uma linha por
problema. Codigo: 0 OK, 1 WARNING, 2 CRITICAL, 3 UNKNOWN (configuracao, segredos, conexao ou erro de banco).
Sem log em arquivo: a saida do plugin fica registrada pelo monitoramento.
"""
import argparse
import os
import sys

_BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(_BASE, "modules"))

import agentes_service  # noqa: E402
import db_conn  # noqa: E402
import sql_ident  # noqa: E402
import sss_config  # noqa: E402
from repo_oracle import saude as saude_sql  # noqa: E402

OK, WARNING, CRITICAL, UNKNOWN = 0, 1, 2, 3
ESTADOS = ("OK", "WARNING", "CRITICAL", "UNKNOWN")
_SAUDAVEIS = (agentes_service.OK, agentes_service.ATRASADO)


class Verificacao(object):
    """As verificacoes do README §13 sobre uma conexao ja aberta; um unico agora_banco() para todas."""

    def __init__(self, cfg, conn, args, repo=None):
        self.cfg = cfg
        self.conn = conn
        self.args = args
        self.repo = repo or saude_sql.RepoSaude.da_config(cfg)
        agente = cfg.agent
        self.limiares = agentes_service.Limiares(agente.heartbeat_interval_s, agente.fence_timeout_s,
                                                 agente.node_offline_timeout_s)
        self.problemas = []  # (nivel, texto)
        self.desempenho = []

    def _problema(self, nivel, texto):
        self.problemas.append((nivel, texto))

    def executar(self):
        agora = db_conn.agora_banco(self.conn)
        self._versao()
        agentes = self.repo.agentes(self.conn)
        self._agentes(agentes, agora)
        self._ambientes(agentes, agora)
        self._fila(agentes, agora)
        self._sem_pid(agora)
        self._config(agentes)
        self._purge(agora)
        return max([nivel for nivel, _t in self.problemas] or [OK])

    def _versao(self):
        versao = self.repo.versao_esquema(self.conn)
        if versao != sql_ident.VERSAO_ESQUEMA:
            self._problema(CRITICAL, "versao do esquema %s, esperada %d (README §11.1)"
                           % (versao, sql_ident.VERSAO_ESQUEMA))

    def _agentes(self, agentes, agora):
        saudaveis = 0
        for ag in agentes:
            if ag["status"] != "ATIVO":
                continue
            saude = agentes_service.saude(ag, agora, self.limiares)
            if saude in _SAUDAVEIS:
                saudaveis += 1
            elif saude == agentes_service.EM_RISCO:
                self._problema(WARNING, "agente %s em risco: heartbeat ha %s (fence %d s)" % (
                    ag["codigo"], self._idade(ag, agora), self.limiares.fence_timeout_s))
            else:
                self._problema(CRITICAL, "agente %s ATIVO sem heartbeat ha %s (node_offline %d s)" % (
                    ag["codigo"], self._idade(ag, agora), self.limiares.node_offline_timeout_s))
        self.desempenho.append("agentes_saudaveis=%d" % saudaveis)

    @staticmethod
    def _idade(ag, agora):
        hb = ag.get("heartbeat_at")
        return "-" if hb is None else "%d s" % max(0, int((agora - hb).total_seconds()))

    def _ambientes(self, agentes, agora):
        atendidos = set()
        for ag in agentes:
            if ag["status"] == "ATIVO" and agentes_service.saude(ag, agora, self.limiares) in _SAUDAVEIS:
                atendidos.update(a.strip() for a in (ag.get("ambientes") or "").split(",") if a.strip())
        for nome in self.repo.ambientes_ativos(self.conn):
            if nome not in atendidos:
                self._problema(CRITICAL, "ambiente %s ativo sem nenhum agente saudavel" % nome)

    def _fila(self, agentes, agora):
        atendidos = saude_sql.pares_atendidos(agentes, agora, self.limiares)
        for g in saude_sql.fila_sem_atendente(self.repo.fila_por_par(self.conn, agora), atendidos):
            self._problema(CRITICAL, "fila sem atendente: %d tickets de %s/%s, o mais antigo desde %s" % (
                g["quantidade"], g["ambiente"], g["interpretador"], g["mais_antigo"].strftime("%Y-%m-%d %H:%M:%S")))
        qtd, antigo = self.repo.fila_vencida(self.conn, agora)
        espera_min = 0 if antigo is None else max(0, int((agora - antigo).total_seconds()) // 60)
        a = self.args
        if qtd >= a.fila_crit or espera_min >= a.espera_crit_min:
            nivel = CRITICAL
        elif qtd >= a.fila_warn or espera_min >= a.espera_warn_min:
            nivel = WARNING
        else:
            nivel = OK
        if nivel != OK:
            self._problema(nivel, "fila vencida: %d tickets PENDING, espera maxima %d min" % (qtd, espera_min))
        self.desempenho.append("fila_vencida=%d;%d;%d" % (qtd, a.fila_warn, a.fila_crit))
        self.desempenho.append("espera_max_min=%d;%d;%d" % (espera_min, a.espera_warn_min, a.espera_crit_min))

    def _sem_pid(self, agora):
        for t in self.repo.rodando_sem_pid(self.conn, agora, self.args.sem_pid_min):
            self._problema(WARNING, "ticket %d RUNNING sem PID no agente %s desde %s" % (
                t["id"], t["agente_id"], t["started_at"].strftime("%Y-%m-%d %H:%M:%S")))

    def _config(self, agentes):
        local = sss_config.config_criticos(self.cfg)
        for ag in agentes:
            if ag["status"] == "ATIVO" and ag.get("config_criticos") and ag["config_criticos"] != local:
                self._problema(WARNING, "agente %s com configuracao divergente: %s (local: %s)" % (
                    ag["codigo"], ag["config_criticos"], local))

    def _purge(self, agora):
        if self.repo.ultimo_purge(self.conn, agora, self.args.purge_dias) is None:
            self._problema(WARNING, "nenhum PURGE auditado nos ultimos %d dias (README §11.3)" % self.args.purge_dias)

    def saida(self, codigo):
        n = len(self.problemas)
        linhas = ["SSS %s - %d problema%s | %s" % (ESTADOS[codigo], n, "" if n == 1 else "s",
                                                  " ".join(self.desempenho))]
        ordenados = sorted(self.problemas, key=lambda p: -p[0])
        linhas.extend("%s: %s" % (ESTADOS[nivel], texto) for nivel, texto in ordenados)
        return "\n".join(linhas) + "\n"


def _argumentos(argv):
    parser = argparse.ArgumentParser(description="Saude do SSS no padrao Nagios (README §13)")
    parser.add_argument("--config", default=None, help="config.ini (padrao: instance/)")
    parser.add_argument("--sem-pid-min", type=int, default=2, help="RUNNING sem PID ha mais de N minutos")
    parser.add_argument("--fila-warn", type=int, default=500, help="PENDING vencidos para WARNING")
    parser.add_argument("--fila-crit", type=int, default=5000, help="PENDING vencidos para CRITICAL")
    parser.add_argument("--espera-warn-min", type=int, default=30, help="espera maxima (min) para WARNING")
    parser.add_argument("--espera-crit-min", type=int, default=120, help="espera maxima (min) para CRITICAL")
    parser.add_argument("--purge-dias", type=int, default=2, help="dias sem PURGE auditado para WARNING")
    return parser.parse_args(argv)


def _desconhecido(saida, motivo):
    saida.write("SSS UNKNOWN - %s\n" % motivo)
    return UNKNOWN


def main(argv=None, conectar=None, saida=None):
    """conectar(cfg, segredos) e o ponto de injecao dos testes; saida recebe o texto do plugin (stdout)."""
    saida = saida or sys.stdout
    args = _argumentos(argv)
    try:
        cfg = sss_config.obter_config(nome_log="saude", caminho=args.config)
        segredos = sss_config.carregar_segredos(cfg.secrets.secrets_file, cfg=cfg, papel="monitor")
    except sss_config.ConfigErro as exc:
        return _desconhecido(saida, "configuracao invalida: %s" % exc)
    try:
        conn = (conectar or _conectar)(cfg, segredos)
    except Exception as exc:
        return _desconhecido(saida, "falha ao conectar no Oracle: %s" % db_conn.traduzir_erro(exc))
    try:
        verificacao = Verificacao(cfg, conn, args)
        codigo = verificacao.executar()
    except Exception as exc:
        return _desconhecido(saida, "falha de banco: %s" % db_conn.traduzir_erro(exc))
    finally:
        conn.close()
    saida.write(verificacao.saida(codigo))
    return codigo


def _conectar(cfg, segredos):
    return db_conn.conectar(cfg, segredos, papel="monitor")


if __name__ == "__main__":
    sys.exit(main())
