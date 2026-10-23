# -*- coding: utf-8 -*-
"""Retencao de dados (README §11.3; F9.1a; CR-005; CR-007 R-21, R-22, R-32; CR-008 R-16, R-27; CR-012; CR-019).

Roda no servidor do agente, agendado pelo cron, com a conta Oracle de purge ([retention] purge_user e
[purge] password). Uso:

    python scripts/purge.py [--config <config.ini>] [--dry-run] [--target tickets|audit|local_logs|output|script_work|all]
                            [--export-audit <pasta>]

* tickets e auditoria: so com a concessao em tbsss_control (um no por vez), DELETE em lotes com COMMIT por lote
  (a excecao do AGENTS §4.9), concessao renovada a cada lote e liberada no fim; uma linha PURGE por tabela,
  inclusive com 0 linhas. Sem a concessao: INFO e saida 0.
* local_logs: pastas de minuto de log_dir/<environment>/<script>/AAAA/MM/DD/HH/MI vencidas, menos as de tickets
  RUNNING; nunca log_dir/internal/. Em todo agente, sem concessao.
* output: pastas de minuto de output_dir/<environment>/... vencidas, pelo helper purge-output. Sem concessao.
* script_work: idem para script_work_dir/<environment>/... (CR-019), com script_work_retention_days.
* --dry-run: so SELECT e listagem; um unico agora_banco() para todos os limites; nada e travado nem gravado.

Saida: 0 sucesso (inclusive "outro no esta purgando"), 1 falha de banco, 2 configuracao invalida, 3 falha na
remocao de logs locais, de pastas de saida ou de pastas de trabalho.
"""
import argparse
import csv
import datetime
import io
import logging
import os
import sys

_BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(_BASE, "modules"))

import audit_service  # noqa: E402
import db_conn  # noqa: E402
import masking  # noqa: E402
import log_paths  # noqa: E402
import os_platform  # noqa: E402
import sss_config  # noqa: E402
import sss_logging  # noqa: E402
from repo_oracle.purge import RepoPurge  # noqa: E402

EXIT_OK = 0
EXIT_DATABASE = 1
EXIT_CONFIG = 2
EXIT_LOCAL = 3

TARGETS = ("tickets", "audit", "local_logs", "output", "script_work")
# Valores do --target (CR-016b); "all" roda todos os TARGETS.
CLI_TARGETS = ("tickets", "audit", "local_logs", "output", "script_work", "all")
LOCK_NAME = "sss-purge.lock"
_PURGE_LOGGERS = ("sss_db_conn", "sss_config")
_EXTRA = {"agent": "-", "ticket": "-", "action": "PURGE"}


class LeaseLost(Exception):
    """A renovacao da concessao nao achou mais este no como dono (outro no a tomou depois de vencida)."""


class AuditExport(object):
    """CSV 0600 do --export-audit (mesmo formato da exportacao do README §4.4). Cada lote e gravado e
    sincronizado no disco antes do COMMIT que apaga as linhas (CR-007, R-22)."""

    def __init__(self, folder, now):
        self.path = os.path.join(folder, "auditoria_purge_%s.csv" % now.strftime("%Y%m%d_%H%M%S"))
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self._file = io.open(fd, "w", encoding="utf-8", newline="")
        self._writer = csv.writer(self._file, delimiter=";", lineterminator="\r\n")
        self._file.write(u"﻿")
        self._writer.writerow(audit_service.CSV_HEADER)
        self.rows = 0

    def write(self, records):
        for reg in records:
            self._writer.writerow(audit_service.csv_row(reg))
        self._file.flush()
        os.fsync(self._file.fileno())
        self.rows += len(records)

    def close(self):
        self._file.close()


class Purge(object):
    """Uma execucao do purge sobre uma conexao ja aberta. Devolve o codigo de saida e preenche self.resumo."""

    def __init__(self, cfg, conn, repo=None, plat=os_platform, logger=None):
        self.cfg = cfg
        self.conn = conn
        self.repo = repo or RepoPurge.from_config(cfg)
        self.plat = plat
        self.log = logger or logging.getLogger("purge")
        self.owner = cfg.agent.agent_id
        self.summary = []

    def run(self, targets, dry_run=False, export=None):
        now = db_conn.db_now(self.conn)  # uma vez: todos os limites partem deste instante
        self.log.info("purge iniciado (alvos=%s dry_run=%s agora_banco=%s)", ",".join(targets), dry_run,
                      now.strftime("%Y-%m-%d %H:%M:%S"), extra=_EXTRA)
        tables = [a for a in ("tickets", "audit") if a in targets]
        try:
            if tables:
                if dry_run:
                    self._count_tables(tables, now)
                else:
                    self._purge_tables(tables, now, export)
            code = EXIT_OK
            if "local_logs" in targets and not self._local_logs(now, dry_run):
                code = EXIT_LOCAL
        except LeaseLost:
            self.log.error("concessao do purge perdida durante a execucao; parado", extra=_EXTRA)
            return EXIT_DATABASE
        except Exception as exc:  # erro do driver: ja houve rollback do lote em andamento
            self.log.error("falha de banco no purge: %s", db_conn.translate_error(exc), extra=_EXTRA)
            return EXIT_DATABASE
        finally:
            if dry_run:
                self._undo()
        if "output" in targets and not self._output(dry_run):
            code = EXIT_LOCAL
        if "script_work" in targets and not self._script_work(dry_run):
            code = EXIT_LOCAL
        return code

    def _undo(self):
        try:
            self.conn.rollback()
        except Exception as exc:  # conexao ja perdida: o banco desfaz sozinho
            self.log.warning("rollback do purge falhou: %s", exc, extra=_EXTRA)

    # ------------------------------------------------------------------ tickets e auditoria

    def _cutoff(self, table, now):
        days = (self.cfg.retention.ticket_retention_days if table == "tickets"
                else self.cfg.retention.audit_retention_days)
        return now - datetime.timedelta(days=days)

    def _count_tables(self, tables, now):
        for table in tables:
            count = self.repo.count_tickets if table == "tickets" else self.repo.count_audit
            n = count(self.conn, self._cutoff(table, now))
            self.summary.append("%s: %d linhas elegiveis (estimativa)" % (table, n))

    def _purge_tables(self, tables, now, export):
        if not self.repo.take_lease(self.conn, self.owner):
            self._undo()
            self.log.info("outro no esta purgando (concessao em tbsss_control); tickets e auditoria pulados",
                          extra=_EXTRA)
            for table in tables:
                self.summary.append("%s: pulado (outro no esta purgando)" % table)
            return
        self.conn.commit()
        try:
            for table in tables:
                file = AuditExport(export, now) if table == "audit" and export else None
                try:
                    total = self._purge_table(table, self._cutoff(table, now), file)
                finally:
                    if file is not None:
                        file.close()
                self.repo.audit(self.conn, table, total)
                self.conn.commit()
                self.log.info("purge de tbsss_%s: %d linhas", table, total, extra=_EXTRA)
                self.summary.append("%s: %d linhas apagadas" % (table, total))
                if file is not None:
                    self.summary.append("auditoria exportada: %s (%d linhas)" % (file.path, file.rows))
        except Exception:
            self._undo()
            raise
        finally:
            self._release()

    def _purge_table(self, table, limit, file):
        batch = self.cfg.retention.purge_batch_size
        total = 0
        while True:
            if file is not None:
                records = self.repo.read_and_delete_audit(self.conn, limit, batch)
                file.write(records)  # no disco antes do COMMIT que apaga
                n = len(records)
            elif table == "tickets":
                n = self.repo.delete_tickets(self.conn, limit, batch)
            else:
                n = self.repo.delete_audit(self.conn, limit, batch)
            if not n:
                self.conn.rollback()
                return total
            if not self.repo.take_lease(self.conn, self.owner):  # renovada a cada lote, na mesma transacao
                self.conn.rollback()
                raise LeaseLost()
            self.conn.commit()
            total += n

    def _release(self):
        try:
            self.repo.release_lease(self.conn, self.owner)
            self.conn.commit()
        except Exception as exc:  # vence sozinha em 1 hora
            self.log.warning("concessao do purge nao liberada: %s", exc, extra=_EXTRA)

    # ------------------------------------------------------------------ logs locais e saida

    def _local_logs(self, now, dry_run):
        log_dir = self.cfg.logging.log_dir
        keep = [log_paths.run_log_dir(log_dir, env, name, start, script_id=sid)
                  for env, name, sid, start in self.repo.running_for_logs(self.conn) if name]
        failures = []
        dirs = log_paths.clean_run_retention(log_dir, self.cfg.logging.local_log_retention_days, now,
                                                     keep=keep, dry_run=dry_run, failures=failures,
                                                     final_path=self.plat.final_path)
        for failure in failures:
            self.log.error("retencao dos logs locais: %s", failure, extra=_EXTRA)
        self.log.info("logs locais: %d pastas de minuto %s (%d mantidas por ticket RUNNING)", len(dirs),
                      "elegiveis" if dry_run else "removidas", len(keep), extra=_EXTRA)
        self.summary.append("local_logs: %d pastas de minuto %s" % (
            len(dirs), "elegiveis (estimativa)" if dry_run else "removidas"))
        return not failures

    def _output(self, dry_run):
        return self._minute_dirs("output", "output_dir", self.cfg.agent.output_dir,
                                 self.cfg.logging.output_retention_days, "saida", dry_run)

    def _script_work(self, dry_run):
        """CR-019 (README §8.15): pastas de trabalho, no mesmo formato de minuto da saida."""
        return self._minute_dirs("script_work", "script_work_dir", getattr(self.cfg.agent, "script_work_dir", None),
                                 getattr(self.cfg.logging, "script_work_retention_days", 7), "pasta de trabalho",
                                 dry_run)

    def _minute_dirs(self, target, key, folder, days, name, dry_run):
        """Pastas de minuto vencidas de <folder>/<environment>/..., pelo helper purge-output (como o usuario de
        execucao do ambiente fora de DEV)."""
        if not folder:
            self.summary.append("%s: desligada (%s vazio)" % (target, key))
            return True
        users = dict(self.cfg.agent.exec_users or ())
        total, ok = 0, True
        for env in self.cfg.agent.environments:
            base = os.path.join(folder, log_paths.environment_dir(env))
            if not os.path.isdir(base):
                continue
            try:
                total += self.plat.purge_output(base, days, users.get(env) or None, count_only=dry_run)
            except (RuntimeError, OSError) as exc:
                ok = False
                self.log.error("retencao da %s de %s: %s", name, env, exc, extra=_EXTRA)
        self.log.info("%s: %d pastas de minuto %s", target, total, "elegiveis" if dry_run else "removidas",
                      extra=_EXTRA)
        self.summary.append("%s: %d pastas de minuto %s" % (target, total,
                                                            "elegiveis (estimativa)" if dry_run else "removidas"))
        return ok


def _arguments(argv):
    parser = argparse.ArgumentParser(description="Retencao de dados do SSS (README §11.3)")
    parser.add_argument("--config", default=None, help="config.ini do agente (padrao: instance/)")
    parser.add_argument("--dry-run", action="store_true", help="so conta (estimativas), sem gravar nem remover")
    parser.add_argument("--target", dest="alvo", choices=CLI_TARGETS, default="all")
    parser.add_argument("--export-audit", dest="exportar_auditoria", default=None, metavar="PASTA",
                        help="grava as linhas da auditoria em CSV 0600 antes de apaga-las")
    return parser.parse_args(argv)


def main(argv=None, connect=None, plat=os_platform, output=None):
    """conectar(cfg, segredos) e plat sao pontos de injecao dos testes; saida recebe o resumo (stdout)."""
    output = output or sys.stdout
    args = _arguments(argv)
    targets = TARGETS if args.alvo == "all" else (args.alvo,)
    try:
        cfg = sss_config.get_config(log_name="purge", path=args.config)
    except sss_config.ConfigError:  # o CRITICAL ja foi registrado (README §12.1)
        return EXIT_CONFIG
    logger = sss_logging.configure("purge", cfg)
    for name in _PURGE_LOGGERS:
        other = logging.getLogger(name)
        other.setLevel(logger.level)
        for handler in logger.handlers:
            other.addHandler(handler)
    masking.install_filter_on_handlers()
    if not cfg.retention.purge_user:
        logger.critical("purge desligado: [retention] purge_user vazio (README §12.1)", extra=_EXTRA)
        return EXIT_CONFIG
    if args.exportar_auditoria and not os.path.isdir(args.exportar_auditoria):
        logger.critical("--export-audit: pasta inexistente: %s", args.exportar_auditoria, extra=_EXTRA)
        return EXIT_CONFIG
    try:
        secrets_value = sss_config.load_secrets(cfg.secrets.secrets_file, cfg=cfg, role="agent")
    except sss_config.ConfigError as exc:
        logger.critical("segredos invalidos: %s", exc, extra=_EXTRA)
        return EXIT_CONFIG

    lock = None
    if not args.dry_run:
        try:
            lock = plat.lock_instance(os.path.join(cfg.agent.work_dir, LOCK_NAME))
        except os_platform.InstanceAlreadyRunning:
            logger.info("outro purge ja esta em execucao neste servidor (%s)", LOCK_NAME, extra=_EXTRA)
            return EXIT_OK
    try:
        try:
            conn = (connect or _connect)(cfg, secrets_value)
        except Exception as exc:
            logger.error("falha ao conectar no Oracle: %s", db_conn.translate_error(exc), extra=_EXTRA)
            return EXIT_DATABASE
        try:
            purge = Purge(cfg, conn, plat=plat, logger=logger)
            code = purge.run(targets, dry_run=args.dry_run, export=args.exportar_auditoria)
        finally:
            conn.close()
        if args.dry_run:
            purge.summary.append("dry-run: contagens estimadas, sem trava; podem mudar antes da execucao real")
        for line in purge.summary:
            output.write(line + "\n")
        logger.info("purge encerrado (codigo %d)", code, extra=_EXTRA)
        return code
    finally:
        if lock is not None:
            plat.release_instance(lock)


def _connect(cfg, secrets):
    return db_conn.connect(cfg, secrets, role="purge")


if __name__ == "__main__":
    sys.exit(main())
