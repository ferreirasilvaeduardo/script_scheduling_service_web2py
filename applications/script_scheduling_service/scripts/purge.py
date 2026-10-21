# -*- coding: utf-8 -*-
"""Retencao de dados (README §11.3; F9.1a; CR-005; CR-007 R-21, R-22, R-32; CR-008 R-16, R-27; CR-012).

Roda no servidor do agente, agendado pelo cron, com a conta Oracle de purge ([retention] purge_user e
[purge] password). Uso:

    python scripts/purge.py [--config <config.ini>] [--dry-run] [--target tickets|auditoria|logs_locais|saida|todos]
                            [--export-audit <pasta>]

* tickets e auditoria: so com a concessao em tbsss_control (um no por vez), DELETE em lotes com COMMIT por lote
  (a excecao do AGENTS §4.9), concessao renovada a cada lote e liberada no fim; uma linha PURGE por tabela,
  inclusive com 0 linhas. Sem a concessao: INFO e saida 0.
* logs_locais: pastas de minuto de log_dir/<environment>/<script>/AAAA/MM/DD/HH/MI vencidas, menos as de tickets
  RUNNING; nunca log_dir/interno/. Em todo agente, sem concessao.
* saida: pastas de minuto de output_dir/<environment>/... vencidas, pelo helper purge-output. Sem concessao.
* --dry-run: so SELECT e listagem; um unico agora_banco() para todos os limites; nada e travado nem gravado.

Saida: 0 sucesso (inclusive "outro no esta purgando"), 1 falha de banco, 2 configuracao invalida, 3 falha na
remocao de logs locais ou de pastas de saida.
"""
import argparse
import collections
import csv
import datetime
import io
import logging
import os
import sys

_BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(_BASE, "modules"))

import auditoria_service  # noqa: E402
import db_conn  # noqa: E402
import masking  # noqa: E402
import pastas_log  # noqa: E402
import plataforma  # noqa: E402
import sss_config  # noqa: E402
import sss_logging  # noqa: E402
from repo_oracle.purge import RepoPurge  # noqa: E402

SAIDA_OK = 0
SAIDA_BANCO = 1
SAIDA_CONFIG = 2
SAIDA_LOCAIS = 3

ALVOS = ("tickets", "auditoria", "logs_locais", "saida")
# Valores do --target (CR-016b) -> alvo interno.
ALVOS_CLI = collections.OrderedDict([("tickets", "tickets"), ("audit", "auditoria"), ("local_logs", "logs_locais"),
                                     ("output", "saida"), ("all", "todos")])
NOME_TRAVA = "sss-purge.lock"
_LOGGERS_DO_PURGE = ("sss_db_conn", "sss_config")
_EXTRA = {"agente": "-", "ticket": "-", "acao": "PURGE"}


class ConcessaoPerdida(Exception):
    """A renovacao da concessao nao achou mais este no como dono (outro no a tomou depois de vencida)."""


class ExportacaoAuditoria(object):
    """CSV 0600 do --export-audit (mesmo formato da exportacao do README §4.4). Cada lote e gravado e
    sincronizado no disco antes do COMMIT que apaga as linhas (CR-007, R-22)."""

    def __init__(self, pasta, agora):
        self.caminho = os.path.join(pasta, "auditoria_purge_%s.csv" % agora.strftime("%Y%m%d_%H%M%S"))
        fd = os.open(self.caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self._arquivo = io.open(fd, "w", encoding="utf-8", newline="")
        self._escritor = csv.writer(self._arquivo, delimiter=";", lineterminator="\r\n")
        self._arquivo.write(u"﻿")
        self._escritor.writerow(auditoria_service.CABECALHO_CSV)
        self.linhas = 0

    def gravar(self, registros):
        for reg in registros:
            self._escritor.writerow(auditoria_service.linha_csv(reg))
        self._arquivo.flush()
        os.fsync(self._arquivo.fileno())
        self.linhas += len(registros)

    def fechar(self):
        self._arquivo.close()


class Purge(object):
    """Uma execucao do purge sobre uma conexao ja aberta. Devolve o codigo de saida e preenche self.resumo."""

    def __init__(self, cfg, conn, repo=None, plat=plataforma, logger=None):
        self.cfg = cfg
        self.conn = conn
        self.repo = repo or RepoPurge.da_config(cfg)
        self.plat = plat
        self.log = logger or logging.getLogger("purge")
        self.dono = cfg.agent.agent_id
        self.resumo = []

    def executar(self, alvos, dry_run=False, exportar=None):
        agora = db_conn.agora_banco(self.conn)  # uma vez: todos os limites partem deste instante
        self.log.info("purge iniciado (alvos=%s dry_run=%s agora_banco=%s)", ",".join(alvos), dry_run,
                      agora.strftime("%Y-%m-%d %H:%M:%S"), extra=_EXTRA)
        tabelas = [a for a in ("tickets", "auditoria") if a in alvos]
        try:
            if tabelas:
                if dry_run:
                    self._contar_tabelas(tabelas, agora)
                else:
                    self._purgar_tabelas(tabelas, agora, exportar)
            codigo = SAIDA_OK
            if "logs_locais" in alvos and not self._logs_locais(agora, dry_run):
                codigo = SAIDA_LOCAIS
        except ConcessaoPerdida:
            self.log.error("concessao do purge perdida durante a execucao; parado", extra=_EXTRA)
            return SAIDA_BANCO
        except Exception as exc:  # erro do driver: ja houve rollback do lote em andamento
            self.log.error("falha de banco no purge: %s", db_conn.traduzir_erro(exc), extra=_EXTRA)
            return SAIDA_BANCO
        finally:
            if dry_run:
                self._desfazer()
        if "saida" in alvos and not self._saida(dry_run):
            codigo = SAIDA_LOCAIS
        return codigo

    def _desfazer(self):
        try:
            self.conn.rollback()
        except Exception as exc:  # conexao ja perdida: o banco desfaz sozinho
            self.log.warning("rollback do purge falhou: %s", exc, extra=_EXTRA)

    # ------------------------------------------------------------------ tickets e auditoria

    def _limite(self, tabela, agora):
        dias = (self.cfg.retention.ticket_retention_days if tabela == "tickets"
                else self.cfg.retention.audit_retention_days)
        return agora - datetime.timedelta(days=dias)

    def _contar_tabelas(self, tabelas, agora):
        for tabela in tabelas:
            contar = self.repo.contar_tickets if tabela == "tickets" else self.repo.contar_auditoria
            n = contar(self.conn, self._limite(tabela, agora))
            self.resumo.append("%s: %d linhas elegiveis (estimativa)" % (tabela, n))

    def _purgar_tabelas(self, tabelas, agora, exportar):
        if not self.repo.tomar_concessao(self.conn, self.dono):
            self._desfazer()
            self.log.info("outro no esta purgando (concessao em tbsss_control); tickets e auditoria pulados",
                          extra=_EXTRA)
            for tabela in tabelas:
                self.resumo.append("%s: pulado (outro no esta purgando)" % tabela)
            return
        self.conn.commit()
        try:
            for tabela in tabelas:
                arquivo = ExportacaoAuditoria(exportar, agora) if tabela == "auditoria" and exportar else None
                try:
                    total = self._purgar_tabela(tabela, self._limite(tabela, agora), arquivo)
                finally:
                    if arquivo is not None:
                        arquivo.fechar()
                self.repo.auditar(self.conn, tabela, total)
                self.conn.commit()
                self.log.info("purge de tbsss_%s: %d linhas", tabela, total, extra=_EXTRA)
                self.resumo.append("%s: %d linhas apagadas" % (tabela, total))
                if arquivo is not None:
                    self.resumo.append("auditoria exportada: %s (%d linhas)" % (arquivo.caminho, arquivo.linhas))
        except Exception:
            self._desfazer()
            raise
        finally:
            self._liberar()

    def _purgar_tabela(self, tabela, limite, arquivo):
        lote = self.cfg.retention.purge_batch_size
        total = 0
        while True:
            if arquivo is not None:
                registros = self.repo.ler_e_apagar_auditoria(self.conn, limite, lote)
                arquivo.gravar(registros)  # no disco antes do COMMIT que apaga
                n = len(registros)
            elif tabela == "tickets":
                n = self.repo.apagar_tickets(self.conn, limite, lote)
            else:
                n = self.repo.apagar_auditoria(self.conn, limite, lote)
            if not n:
                self.conn.rollback()
                return total
            if not self.repo.tomar_concessao(self.conn, self.dono):  # renovada a cada lote, na mesma transacao
                self.conn.rollback()
                raise ConcessaoPerdida()
            self.conn.commit()
            total += n

    def _liberar(self):
        try:
            self.repo.liberar_concessao(self.conn, self.dono)
            self.conn.commit()
        except Exception as exc:  # vence sozinha em 1 hora
            self.log.warning("concessao do purge nao liberada: %s", exc, extra=_EXTRA)

    # ------------------------------------------------------------------ logs locais e saida

    def _logs_locais(self, agora, dry_run):
        log_dir = self.cfg.logging.log_dir
        manter = [pastas_log.diretorio_log_execucao(log_dir, amb, nome, inicio, script_id=sid)
                  for amb, nome, sid, inicio in self.repo.running_para_logs(self.conn) if nome]
        falhas = []
        pastas = pastas_log.limpar_retencao_execucao(log_dir, self.cfg.logging.local_log_retention_days, agora,
                                                     manter=manter, dry_run=dry_run, falhas=falhas,
                                                     caminho_final=self.plat.caminho_final)
        for falha in falhas:
            self.log.error("retencao dos logs locais: %s", falha, extra=_EXTRA)
        self.log.info("logs locais: %d pastas de minuto %s (%d mantidas por ticket RUNNING)", len(pastas),
                      "elegiveis" if dry_run else "removidas", len(manter), extra=_EXTRA)
        self.resumo.append("logs_locais: %d pastas de minuto %s" % (
            len(pastas), "elegiveis (estimativa)" if dry_run else "removidas"))
        return not falhas

    def _saida(self, dry_run):
        agente = self.cfg.agent
        if not agente.output_dir:
            self.resumo.append("saida: desligada (output_dir vazio)")
            return True
        usuarios = dict(agente.exec_users or ())
        total, ok = 0, True
        for amb in agente.environments:
            base = os.path.join(agente.output_dir, pastas_log.pasta_ambiente(amb))
            if not os.path.isdir(base):
                continue
            try:
                total += self.plat.purgar_saida(base, self.cfg.logging.output_retention_days,
                                                usuarios.get(amb) or None, contar=dry_run)
            except (RuntimeError, OSError) as exc:
                ok = False
                self.log.error("retencao da saida de %s: %s", amb, exc, extra=_EXTRA)
        self.log.info("saida: %d pastas de minuto %s", total, "elegiveis" if dry_run else "removidas", extra=_EXTRA)
        self.resumo.append("saida: %d pastas de minuto %s" % (total, "elegiveis (estimativa)" if dry_run else "removidas"))
        return ok


def _argumentos(argv):
    parser = argparse.ArgumentParser(description="Retencao de dados do SSS (README §11.3)")
    parser.add_argument("--config", default=None, help="config.ini do agente (padrao: instance/)")
    parser.add_argument("--dry-run", action="store_true", help="so conta (estimativas), sem gravar nem remover")
    parser.add_argument("--target", dest="alvo", choices=tuple(ALVOS_CLI), default="all")
    parser.add_argument("--export-audit", dest="exportar_auditoria", default=None, metavar="PASTA",
                        help="grava as linhas da auditoria em CSV 0600 antes de apaga-las")
    args = parser.parse_args(argv)
    args.alvo = ALVOS_CLI[args.alvo]
    return args


def main(argv=None, conectar=None, plat=plataforma, saida=None):
    """conectar(cfg, segredos) e plat sao pontos de injecao dos testes; saida recebe o resumo (stdout)."""
    saida = saida or sys.stdout
    args = _argumentos(argv)
    alvos = ALVOS if args.alvo == "todos" else (args.alvo,)
    try:
        cfg = sss_config.obter_config(nome_log="purge", caminho=args.config)
    except sss_config.ConfigErro:  # o CRITICAL ja foi registrado (README §12.1)
        return SAIDA_CONFIG
    logger = sss_logging.configurar("purge", cfg)
    for nome in _LOGGERS_DO_PURGE:
        outro = logging.getLogger(nome)
        outro.setLevel(logger.level)
        for handler in logger.handlers:
            outro.addHandler(handler)
    masking.instalar_filtro_em_handlers()
    if not cfg.retention.purge_user:
        logger.critical("purge desligado: [retention] purge_user vazio (README §12.1)", extra=_EXTRA)
        return SAIDA_CONFIG
    if args.exportar_auditoria and not os.path.isdir(args.exportar_auditoria):
        logger.critical("--export-audit: pasta inexistente: %s", args.exportar_auditoria, extra=_EXTRA)
        return SAIDA_CONFIG
    try:
        segredos = sss_config.carregar_segredos(cfg.secrets.secrets_file, cfg=cfg, papel="agent")
    except sss_config.ConfigErro as exc:
        logger.critical("segredos invalidos: %s", exc, extra=_EXTRA)
        return SAIDA_CONFIG

    trava = None
    if not args.dry_run:
        try:
            trava = plat.travar_instancia(os.path.join(cfg.agent.work_dir, NOME_TRAVA))
        except plataforma.InstanciaJaEmExecucao:
            logger.info("outro purge ja esta em execucao neste servidor (%s)", NOME_TRAVA, extra=_EXTRA)
            return SAIDA_OK
    try:
        try:
            conn = (conectar or _conectar)(cfg, segredos)
        except Exception as exc:
            logger.error("falha ao conectar no Oracle: %s", db_conn.traduzir_erro(exc), extra=_EXTRA)
            return SAIDA_BANCO
        try:
            purge = Purge(cfg, conn, plat=plat, logger=logger)
            codigo = purge.executar(alvos, dry_run=args.dry_run, exportar=args.exportar_auditoria)
        finally:
            conn.close()
        if args.dry_run:
            purge.resumo.append("dry-run: contagens estimadas, sem trava; podem mudar antes da execucao real")
        for linha in purge.resumo:
            saida.write(linha + "\n")
        logger.info("purge encerrado (codigo %d)", codigo, extra=_EXTRA)
        return codigo
    finally:
        if trava is not None:
            plat.liberar_instancia(trava)


def _conectar(cfg, segredos):
    return db_conn.conectar(cfg, segredos, papel="purge")


if __name__ == "__main__":
    sys.exit(main())
