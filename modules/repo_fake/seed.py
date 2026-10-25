# -*- coding: utf-8 -*-
"""Carga deterministica de seed para o backend FAKE (README §2.5, §4.3.D, §10, §11).

Totalmente deterministico, sem aleatoriedade, compativel com Python 3.6.
"""
import datetime
import io
import json
import zipfile

from sss.core import params_compiler
from sss.core import recurrence
from sss.core import security
from sss.core import sql_ident

# Contas de demonstracao que permanecem sem senha utilizavel mesmo em DEV.
_NO_PASSWORD_DEV = ("inativo", "bloqueado")

# Marcador final do log truncado no banco (README §8.10).
MARKER_TRUNCATED = "[SSS] log truncado no banco; arquivo integral no agente\n"

# Segundos por etapa do log simulado dos RUNNING (o 16 nao tem log, ver _TICKET_NO_PID): na carga ja decorreram 5 min desde started_at;
# o ticket 13 termina ~100 s depois e os demais entre 15 e 25 min depois.
_STEP_LOG_S = {11: 24, 12: 30, 13: 8, 14: 36, 15: 30, 16: 36}
_LINES_LOG_LARGE = 27000
# Idade inicial do heartbeat congelado do agt-host02: com os limiares padrao (10/90/180 s) ele
# comeca DELAYED, fica AT_RISK ~1 min depois e OFFLINE ~2,5 min depois (README §13).
_HB_FROZEN_S = 30
_TICKET_LOG_LARGE = 17
# Quadros de atencao da tela de agentes (CR-007, R-18): o ticket 4 (SH em HOMOLOGACAO) ja venceu e
# so o agt-host02 atende o par, entao aparece em "Fila sem atendente" quando ele sai de DELAYED;
# o RUNNING 16 foi reservado sem PID ("Rodando sem PID", sem log simulado).
_TICKET_QUEUE_NO_SERVER = 4
_TICKET_NO_PID = 16


def _large_log(start):
    # ~2 MB em UTF-8, com acentos, para exercitar a leitura por offset e o download.
    rows = []
    for i in range(1, _LINES_LOG_LARGE + 1):
        when = start + datetime.timedelta(seconds=i // 100)
        rows.append(u"[%s] lote %06d/%06d: registros validados \u2014 situa\u00e7\u00e3o OK\n"
                      % (when, i, _LINES_LOG_LARGE))
    return u"".join(rows)


def _compiler_links(store, script_id):
    """Vinculos ativos do script no formato do compilador (parametro + ordem, obrigatorio e sub)."""
    links = []
    for v in sorted((v for v in store.script_param.values() if v["script_id"] == script_id), key=lambda v: v["sort_order"]):
        prm = store.parameters[v["parameter_id"]]
        if prm["active"] == "Y":
            links.append(dict(prm, parameter_id=prm["id"], sort_order=v["sort_order"], required=v["required"],
                                 default_value_override=v.get("default_value_override")))
    return links


def _compile_seed(store, script_id, now):
    """Snapshot e respostas resolvidas reais do script (README §2.5: seed coerente com as regras)."""
    links = _compiler_links(store, script_id)
    snapshot, resolved, errors = params_compiler.compile_snapshot(store.scripts[script_id], links, {}, now)
    if errors:
        raise ValueError("seed incoerente: script %s nao compila (%s)" % (script_id, sorted(errors)))
    return snapshot, resolved, links


def _params_json(resolved):
    """parametros_json de agendamento: respostas resolvidas, nulos omitidos, CHECKBOX como texto (README §7.6)."""
    obj = {}
    for code, value in resolved.items():
        if value is None:
            continue
        obj[code] = ("true" if value else "false") if isinstance(value, bool) else value
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_ACTOR_SEED = "SYSTEM:seed"
_REGISTRIES = ("environments", "profiles", "features", "profile_feature", "profile_env", "scripts", "profile_script",
              "script_env", "users", "parameters", "script_param", "schedules")


def _between(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def _stamp_record(store, base_dt):
    """Colunas de registro coerentes com o README §10 e §2.5 (CR-006).

    Cadastros e vinculos: criados por SYSTEM:seed; updated_* so onde o estado implica alteracao
    (registro inativo, regra pausada). Tickets: solicitante ou o agente do desdobro; fora de PENDING,
    a ultima mudanca de situacao. Agentes: o proprio agente. Sempre entre created_at e base_dt.
    """
    for name in _REGISTRIES:
        for reg in getattr(store, name).values():
            reg.setdefault("created_at", base_dt - datetime.timedelta(days=90))
            reg.update(created_by=_ACTOR_SEED, updated_at=None, updated_by=None)
            if reg.get("active") == "N":
                reg["updated_at"] = _between(reg["created_at"] + datetime.timedelta(days=1), reg["created_at"], base_dt)
                reg["updated_by"] = _ACTOR_SEED
    for a in store.schedules.values():
        if a["active"] == "N":
            if a.get("pause_reason") == "MANUAL":
                a["updated_by"] = store.users[a["user_id"]]["login"]
            else:
                a["updated_by"] = "SYSTEM:agt-host01"
            a["updated_at"] = _between(a.get("last_run_at") or a["created_at"], a["created_at"], base_dt)
    for ag in store.agents.values():
        ag.update(created_by="SYSTEM:%s" % ag["code"], updated_at=None, updated_by=None)
    for t in store.tickets.values():
        if t.get("schedule_id") is not None:
            t["created_by"] = "SYSTEM:%s" % (t.get("agent_id") or "agt-host01")
        else:
            t["created_by"] = t["requested_by"]
        t["updated_at"] = t["updated_by"] = None
        if t["status"] == "PENDING":
            continue
        if t["status"] == "CANCELLED" and t.get("started_at") is None:
            # Cancelado na fila pelo administrador (trilha do seed: TICKET_CANCEL por admin).
            t["updated_by"] = "admin"
            when = t.get("finished_at")
        elif t["status"] == "RUNNING":
            t["updated_by"] = "SYSTEM:%s" % t["agent_id"]
            when = t.get("started_at")
        else:
            t["updated_by"] = "SYSTEM:%s" % t["agent_id"]
            when = t.get("finished_at") or t.get("started_at")
        t["updated_at"] = _between(when or t["created_at"], t["created_at"], base_dt)
    for r in store.ticket_answer.values():
        r.update(created_by=store.tickets[r["ticket_id"]]["created_by"], updated_at=None, updated_by=None)
    for tout in store.ticket_output.values():
        # A troca de GRAVANDO para a situacao final e alteracao de negocio do agente (README §10, tabela 18).
        t = store.tickets[tout["ticket_id"]]
        tout.update(created_at=t["finished_at"], created_by="SYSTEM:%s" % tout["agent_id"],
                 updated_at=t["finished_at"], updated_by="SYSTEM:%s" % tout["agent_id"])


def _seed_zip():
    """Zip pequeno de demonstracao da pasta de saida (CR-012), gerado em memoria."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("resumo.txt", "Carga concluida: 1200 linhas processadas.\n")
        z.writestr("rejeitados/linhas_rejeitadas.csv", "linha;motivo\n17;data invalida\n42;valor negativo\n")
    return buf.getvalue()


def _seed_outputs(store):
    """Saidas do ticket (tabela 18, CR-012): uma de cada situacao final, em tickets terminados."""
    content = _seed_zip()
    rows = (
        (17, "AVAILABLE", None, 2, len(content), content),
        (29, "EXCEEDED", "FILES", None, None, None),
        (30, "FAILED", "DEADLINE", None, None, None),
    )
    for sid, (ticket_id, state, reason, count, size, data) in enumerate(rows, 1):
        store.ticket_output[sid] = {
            "id": sid,
            "ticket_id": ticket_id,
            "state": state,
            "reason": reason,
            "agent_id": store.tickets[ticket_id]["agent_id"],
            "file_count": count,
            "size_bytes": size,
            "content": data,
        }
    store.seqs["tbsss_ticket_output"] = len(rows)


def _seed_inputs(store, base_dt):
    """Pasta de entrada pela tela (tabelas 19 a 21, CR-020b): dois envios, uma entrega de cada situacao e um
    retrato publicado pelo agt-host01."""
    import hashlib
    import json
    h = datetime.timedelta(hours=1)
    files = ((1, "PRODUCAO", 1, "lotes", "clientes_outubro.csv", b"cliente;valor\n1;10\n2;20\n", "op.prod", 3),
             (2, "HOMOLOGACAO", 2, None, "parametros.txt", b"modo=simulacao\n", "op.hml", 2))
    for uid, env, sid, folder, name, data, actor, hours in files:
        store.input_upload[uid] = {
            "id": uid, "environment": env, "script_id": sid, "relative_dir": folder, "file_name": name,
            "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "replace_existing": "N",
            "source_ip": "10.0.0.15", "content": data, "created_at": base_dt - hours * h, "created_by": actor,
            "updated_at": None, "updated_by": None}
    deliveries = ((1, 1, "agt-host01", "DELIVERED", None), (2, 2, "agt-host01", "PENDING", None),
                  (3, 2, "agt-host02", "FAILED", "EXISTS"))
    for did, uid, agent, state, reason in deliveries:
        up = store.input_upload[uid]
        done = state != "PENDING"
        when = up["created_at"] + datetime.timedelta(minutes=1)
        store.input_delivery[did] = {
            "id": did, "upload_id": uid, "agent_id": agent, "state": state, "reason": reason,
            "delivered_at": when if done else None, "created_at": up["created_at"], "created_by": up["created_by"],
            "updated_at": when if done else None, "updated_by": "SYSTEM:%s" % agent if done else None}
    listing = json.dumps([{"path": "lotes/clientes_outubro.csv", "size": 22, "mtime": (base_dt - 3 * h + datetime.timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")}])
    store.input_listing[1] = {
        "id": 1, "agent_id": "agt-host01", "environment": "PRODUCAO", "script_id": 1, "listing": listing,
        "file_count": 1, "truncated": "N", "listed_at": base_dt - h, "refresh_requested_at": base_dt - h,
        "created_at": base_dt - h, "created_by": "op.prod", "updated_at": None, "updated_by": None}
    store.seqs["tbsss_input_upload"] = 2
    store.seqs["tbsss_input_delivery"] = 3
    store.seqs["tbsss_input_listing"] = 1


def load_seed(store, force=False, dev_password=None):
    """Carrega dados iniciais deterministicos no store FAKE de forma idempotente.

    dev_password: senha comum dos usuarios de demonstracao (exceto inativo e bloqueado),
    com hash e salt individuais. Sem ela, as senhas ficam inutilizaveis ('!').
    """
    with store.lock_users:
        with store.lock_rbac:
            with store.lock_catalog:
                with store.lock_tickets:
                    with store.lock_schedules:
                        with store.lock_audit:
                            with store.lock_agents:
                                if store.environments and not force:
                                    return

                                store.reset()
                                base_dt = store.now()

                                # ---------------------------------------------------------
                                # 1. Ambientes (3)
                                # ---------------------------------------------------------
                                envs = [
                                    {"id": 1, "name": "PRODUCAO", "description": "Ambiente de Producao Oficial", "connection": "db-producao.local:1521/svc", "active": "Y"},
                                    {"id": 2, "name": "HOMOLOGACAO", "description": "Ambiente de Homologacao e Testes", "connection": "db-homologacao.local:1521/svc", "active": "Y"},
                                    {"id": 3, "name": "DESENV", "description": "Ambiente de Desenvolvimento", "connection": "db-desenv.local:1521/svc", "active": "N"},
                                    {"id": 4, "name": "CLONE2", "description": "BRTLVLTS1199PL (10.238.10.209)", "connection": "10.238.55.146/gfprod", "active": "Y"},
                                    {"id": 5, "name": "CLONE1", "description": "BRTLVLTS1198PL (10.238.10.208)", "connection": "10.238.55.145/gfprod", "active": "Y"},
                                    {"id": 6, "name": "CLONE6", "description": "BRTLVLTS3089SL (10.238.10.210)", "connection": "10.238.45.230/svc_gfprodc6", "active": "Y"},
                                    {"id": 7, "name": "CLONE7", "description": "BRTLVLTS1216PL (10.238.10.109)", "connection": "10.238.45.230/svc_gfprodc7", "active": "Y"},
                                    {"id": 8, "name": "GFPREPROD", "description": "BRTLVLTY3067SL (10.129.177.188)", "connection": "10.129.177.188/GFPR", "active": "Y"},
                                ]
                                for a in envs:
                                    # CR-017: HOMOLOGACAO e DESENV sao os casos de ambiente fora de producao.
                                    a["is_production"] = "N" if a["name"] in ("HOMOLOGACAO", "DESENV") else "Y"
                                    a["created_at"] = base_dt - datetime.timedelta(days=90)
                                    store.environments[a["id"]] = a
                                store.seqs["tbsss_environments"] = 8

                                # ---------------------------------------------------------
                                # 2. Funcionalidades canonicas (12) - README §4.3.D; DOWNLOAD_OUTPUT (CR-020a) e UPLOAD_INPUT (CR-020d) no fim
                                # ---------------------------------------------------------
                                features = [
                                    {"id": 1, "code": "EXEC_SCRIPT", "name": "Rodar Scripts", "module": "OPERATION", "description": "Preencher questionários e abrir tickets", "active": "Y"},
                                    {"id": 2, "code": "VIEW_LOGS", "name": "Consultar Tickets", "module": "OPERATION", "description": "Acompanhar os tickets e ler o log em tempo quase real", "active": "Y"},
                                    {"id": 3, "code": "CANCEL_TICKET", "name": "Cancelar Tickets", "module": "OPERATION", "description": "Cancelar tickets de terceiros nos ambientes consultados (com Consultar Tickets)", "active": "Y"},
                                    {"id": 4, "code": "MANAGE_USERS", "name": "Gestão de Usuários", "module": "ADMIN", "description": "Gerenciar operadores e credenciais", "active": "Y"},
                                    {"id": 5, "code": "MANAGE_PROFILES", "name": "Gestão de Perfis", "module": "ADMIN", "description": "Gerenciar perfis e matrizes de permissão", "active": "Y"},
                                    {"id": 6, "code": "MANAGE_ENVIRONMENTS", "name": "Gestão de Ambientes", "module": "ADMIN", "description": "Gerenciar ambientes e DSNs", "active": "Y"},
                                    {"id": 7, "code": "MANAGE_SCRIPTS", "name": "Gestão de Scripts", "module": "ADMIN", "description": "Cadastrar rotinas e homologação por ambiente", "active": "Y"},
                                    {"id": 8, "code": "MANAGE_PARAMETERS", "name": "Dicionário de Parâmetros", "module": "ADMIN", "description": "Gerenciar perguntas e flags reutilizáveis", "active": "Y"},
                                    {"id": 9, "code": "MANAGE_SCHEDULES", "name": "Regras de Agendamento", "module": "ADMIN", "description": "Criar e gerenciar recorrências", "active": "Y"},
                                    {"id": 10, "code": "VIEW_AUDIT", "name": "Auditoria", "module": "ADMIN", "description": "Consultar a trilha de auditoria e os agentes", "active": "Y"},
                                    {"id": 12, "code": "UPLOAD_INPUT", "name": "Enviar Arquivos", "module": "OPERATION", "description": "Enviar arquivos para a pasta de entrada dos scripts do perfil, nos ambientes do perfil", "active": "Y"},
                                    {"id": 11, "code": "DOWNLOAD_OUTPUT", "name": "Baixar Saídas", "module": "OPERATION", "description": "Navegar pelas saídas dos tickets nos ambientes do perfil e baixar o zip ou um arquivo", "active": "Y"},
                                ]
                                for f in features:
                                    store.features[f["id"]] = f
                                store.seqs["tbsss_features"] = 12

                                # ---------------------------------------------------------
                                # 3. Perfis (4)
                                # ---------------------------------------------------------
                                profiles = [
                                    {"id": 1, "name": "ADMINISTRATOR", "description": "Administrador Geral do Sistema", "is_admin": "Y", "perm_version": 1, "active": "Y"},
                                    {"id": 2, "name": "OPERATOR_PROD", "description": "Operador de Ambientes de Producao", "is_admin": "N", "perm_version": 1, "active": "Y"},
                                    {"id": 3, "name": "OPERATOR_HML", "description": "Operador de Ambientes de Homologacao", "is_admin": "N", "perm_version": 1, "active": "Y"},
                                    {"id": 4, "name": "READ_ONLY", "description": "Perfil de Apenas Leitura e Consulta", "is_admin": "N", "perm_version": 1, "active": "Y"},
                                ]
                                for p in profiles:
                                    store.profiles[p["id"]] = p
                                store.seqs["tbsss_profiles"] = 4

                                # ---------------------------------------------------------
                                # 4. Usuarios (6)
                                # ---------------------------------------------------------
                                users = [
                                    {"id": 1, "login": "admin", "name": "Administrador Geral", "password_hash": "!", "profile_id": 1, "failed_attempts": 0, "locked_until": None, "last_login_at": base_dt - datetime.timedelta(hours=1), "password_changed_at": base_dt - datetime.timedelta(days=30), "active": "Y"},
                                    {"id": 2, "login": "op.prod", "name": "Operador Producao", "password_hash": "!", "profile_id": 2, "failed_attempts": 0, "locked_until": None, "last_login_at": base_dt - datetime.timedelta(hours=2), "password_changed_at": base_dt - datetime.timedelta(days=20), "active": "Y"},
                                    {"id": 3, "login": "op.hml", "name": "Operador Homologacao", "password_hash": "!", "profile_id": 3, "failed_attempts": 0, "locked_until": None, "last_login_at": base_dt - datetime.timedelta(hours=3), "password_changed_at": base_dt - datetime.timedelta(days=15), "active": "Y"},
                                    {"id": 4, "login": "consulta", "name": "Auditor e Consulta", "password_hash": "!", "profile_id": 4, "failed_attempts": 0, "locked_until": None, "last_login_at": base_dt - datetime.timedelta(days=1), "password_changed_at": base_dt - datetime.timedelta(days=10), "active": "Y"},
                                    {"id": 5, "login": "inativo", "name": "Usuario Desativado", "password_hash": "!", "profile_id": 4, "failed_attempts": 0, "locked_until": None, "last_login_at": base_dt - datetime.timedelta(days=60), "password_changed_at": base_dt - datetime.timedelta(days=60), "active": "N"},
                                    {"id": 6, "login": "bloqueado", "name": "Usuario Temporariamente Bloqueado", "password_hash": "!", "profile_id": 2, "failed_attempts": 5, "locked_until": base_dt + datetime.timedelta(minutes=30), "last_login_at": base_dt - datetime.timedelta(hours=4), "password_changed_at": base_dt - datetime.timedelta(days=5), "active": "Y"},
                                ]
                                for u in users:
                                    u["created_at"] = base_dt - datetime.timedelta(days=60)
                                    u["session_epoch"] = 0
                                    if dev_password is not None and u["login"] not in _NO_PASSWORD_DEV:
                                        u["password_hash"] = security.hash_password(dev_password)
                                    store.users[u["id"]] = u
                                store.seqs["tbsss_users"] = 6

                                # ---------------------------------------------------------
                                # 5. Scripts (6)
                                # ---------------------------------------------------------
                                scripts = [
                                    {"id": 1, "name": "carga_diaria", "description": "Carga diaria de movimentacoes", "script_group": "CARGAS", "category": "DAILY", "stage": "PROCESSAMENTO", "interpreter": "PYTHON3", "path_file": "/opt/automacoes/scripts/carga_diaria.py", "param_type": "NAMED", "max_parallel_env": 1, "timeout_s": 3600, "active": "Y"},
                                    {"id": 2, "name": "relatorio_mensal", "description": "Extracao financeira consolidada", "script_group": "RELATORIOS", "category": "FINANCEIRO", "stage": "EXTRACAO", "interpreter": "PYTHON3", "path_file": "/opt/automacoes/scripts/relatorio_mensal.py", "param_type": "POSITIONAL", "max_parallel_env": 2, "timeout_s": 1800, "active": "Y"},
                                    {"id": 3, "name": "cleanup_tmp", "description": "Limpeza de arquivos temporarios", "script_group": "MANUTENCAO", "category": "LIMPEZA", "stage": "PURGE", "interpreter": "BASH", "path_file": "/opt/automacoes/scripts/cleanup_tmp.sh", "param_type": "NONE", "max_parallel_env": 1, "timeout_s": 600, "active": "Y"},
                                    {"id": 4, "name": "sync_tabelas", "description": "Sincronizacao de tabelas auxiliares", "script_group": "INTEGRACAO", "category": "SYNC", "stage": "CARGA", "interpreter": "SH", "path_file": "/opt/automacoes/scripts/sync_tabelas.sh", "param_type": "NAMED", "max_parallel_env": 1, "timeout_s": 1200, "active": "Y"},
                                    {"id": 5, "name": "backup_extra", "description": "Rotina de backup extraordinario (legado)", "script_group": "BACKUP", "category": "SISTEMA", "stage": "DUMP", "interpreter": "BASH", "path_file": "/opt/automacoes/scripts/backup_extra.sh", "param_type": "POSITIONAL", "max_parallel_env": 1, "timeout_s": 7200, "active": "N"},
                                    {"id": 6, "name": "validacao_fiscal", "description": "Checagem de consistencia de SPED", "script_group": "FISCAL", "category": "SPED", "stage": "VALIDACAO", "interpreter": "PYTHON3", "path_file": "/opt/automacoes/scripts/validacao_fiscal.py", "param_type": "NAMED", "max_parallel_env": 1, "timeout_s": 900, "active": "Y"},
                                ]
                                for s in scripts:
                                    store.scripts[s["id"]] = s
                                store.seqs["tbsss_scripts"] = 6

                                # ---------------------------------------------------------
                                # 6. Homologacao de Scripts por Ambiente (tbsss_script_env)
                                # ---------------------------------------------------------
                                homols = [
                                    (1, 1), (1, 2),        # carga_diaria -> PRODUCAO, HOMOLOGACAO
                                    (2, 1), (2, 2),        # relatorio_mensal -> PRODUCAO, HOMOLOGACAO
                                    (3, 1), (3, 2), (3, 3), # cleanup_tmp -> PRODUCAO, HOMOLOGACAO, DESENV
                                    (4, 2),                # sync_tabelas -> HOMOLOGACAO
                                    (5, 2),                # backup_extra -> HOMOLOGACAO
                                    (6, 1),                # validacao_fiscal -> PRODUCAO
                                ]
                                for sid, aid in homols:
                                    nid = store.next_id("tbsss_script_env")
                                    store.script_env[nid] = {"id": nid, "script_id": sid, "environment_id": aid}

                                # ---------------------------------------------------------
                                # 7. Matrizes de Perfil (tbsss_profile_feature, amb, scr)
                                # ---------------------------------------------------------
                                # ADMINISTRADOR (id 1)
                                for f in features:
                                    nid = store.next_id("tbsss_profile_feature")
                                    store.profile_feature[nid] = {"id": nid, "profile_id": 1, "feature_id": f["id"]}
                                for a in envs:
                                    nid = store.next_id("tbsss_profile_env")
                                    store.profile_env[nid] = {"id": nid, "profile_id": 1, "environment_id": a["id"]}
                                for s in scripts:
                                    nid = store.next_id("tbsss_profile_script")
                                    store.profile_script[nid] = {"id": nid, "profile_id": 1, "script_id": s["id"]}

                                # OPERATOR_PROD (id 2) -> EXEC_SCRIPT(1), VIEW_LOGS(2), CANCEL_TICKET(3), DOWNLOAD_OUTPUT(11), UPLOAD_INPUT(12)
                                for fid in (1, 2, 3, 11, 12):
                                    nid = store.next_id("tbsss_profile_feature")
                                    store.profile_feature[nid] = {"id": nid, "profile_id": 2, "feature_id": fid}
                                for aid in (1, 2):
                                    nid = store.next_id("tbsss_profile_env")
                                    store.profile_env[nid] = {"id": nid, "profile_id": 2, "environment_id": aid}
                                for sid in (1, 2, 3, 6):
                                    nid = store.next_id("tbsss_profile_script")
                                    store.profile_script[nid] = {"id": nid, "profile_id": 2, "script_id": sid}

                                # OPERATOR_HML (id 3) -> EXEC_SCRIPT(1), VIEW_LOGS(2), CANCEL_TICKET(3), DOWNLOAD_OUTPUT(11), UPLOAD_INPUT(12)
                                for fid in (1, 2, 3, 11, 12):
                                    nid = store.next_id("tbsss_profile_feature")
                                    store.profile_feature[nid] = {"id": nid, "profile_id": 3, "feature_id": fid}
                                for aid in (2, 3):
                                    nid = store.next_id("tbsss_profile_env")
                                    store.profile_env[nid] = {"id": nid, "profile_id": 3, "environment_id": aid}
                                for sid in (1, 2, 3, 4):
                                    nid = store.next_id("tbsss_profile_script")
                                    store.profile_script[nid] = {"id": nid, "profile_id": 3, "script_id": sid}

                                # CONSULTA (id 4) -> VIEW_LOGS(2)
                                nid = store.next_id("tbsss_profile_feature")
                                store.profile_feature[nid] = {"id": nid, "profile_id": 4, "feature_id": 2}
                                for aid in (1, 2):
                                    nid = store.next_id("tbsss_profile_env")
                                    store.profile_env[nid] = {"id": nid, "profile_id": 4, "environment_id": aid}
                                for sid in (1, 2, 3, 4, 6):
                                    nid = store.next_id("tbsss_profile_script")
                                    store.profile_script[nid] = {"id": nid, "profile_id": 4, "script_id": sid}

                                # ---------------------------------------------------------
                                # 8. Parametros (10)
                                # ---------------------------------------------------------
                                params = [
                                    {"id": 1, "code": "data_ref", "param_flag": "--data-ref", "label": "Data de Referencia", "description": "Data base para execucao da rotina", "component_type": "DATE", "options_json": None, "default_value": None, "validation_regex": None, "sensitive": "N", "active": "Y"},
                                    {"id": 2, "code": "limite_linhas", "param_flag": "-n", "label": "Limite de Registros", "description": "Quantidade maxima de linhas processadas", "component_type": "NUMBER", "options_json": None, "default_value": "1000", "validation_regex": None, "sensitive": "N", "active": "Y"},
                                    {"id": 3, "code": "modo_exec", "param_flag": "--modo", "label": "Modo de Operacao", "description": "Define se o processamento e simulacao ou real", "component_type": "SELECT", "options_json": '{"SIMULACAO":"Simulacao","REAL":"Execucao Real"}', "default_value": "SIMULACAO", "validation_regex": None, "sensitive": "N", "active": "Y"},
                                    {"id": 4, "code": "verbose", "param_flag": "--verbose", "label": "Log Detalhado", "description": "Ativa impressao detalhada de passos", "component_type": "CHECKBOX", "options_json": None, "default_value": "false", "validation_regex": None, "sensitive": "N", "active": "Y"},
                                    {"id": 5, "code": "codigo_filial", "param_flag": "--filial", "label": "Codigo da Filial", "description": "Identificador numerico de 4 digitos da filial", "component_type": "TEXT", "options_json": None, "default_value": "0001", "validation_regex": r"^[0-9]{4}$", "sensitive": "N", "active": "Y"},
                                    {"id": 6, "code": "documento_cliente", "param_flag": "--documento", "label": "Documento do cliente (CPF)", "description": "Dado pessoal: mascarado na tela e nos logs; nunca use para senha ou credencial", "component_type": "TEXT", "options_json": None, "default_value": None, "validation_regex": None, "sensitive": "Y", "active": "Y"},
                                    {"id": 7, "code": "formato_saida", "param_flag": "-f", "label": "Formato de Arquivo", "description": "Extensao de exportacao do relatorio", "component_type": "SELECT", "options_json": '{"CSV":"Arquivo CSV","JSON":"Arquivo JSON"}', "default_value": "CSV", "validation_regex": None, "sensitive": "N", "active": "Y"},
                                    {"id": 8, "code": "notificar_email", "param_flag": "-m", "label": "Disparar Alerta", "description": "Envia email aos gestores no encerramento", "component_type": "CHECKBOX", "options_json": None, "default_value": "false", "validation_regex": None, "sensitive": "N", "active": "Y"},
                                    {"id": 9, "code": "taxa_ajuste", "param_flag": "--taxa", "label": "Fator de Correcao", "description": "Multiplicador financeiro", "component_type": "NUMBER", "options_json": None, "default_value": "1.0", "validation_regex": None, "sensitive": "N", "active": "Y"},
                                    {"id": 10, "code": "descricao_lote", "param_flag": "--description", "label": "Descricao do Lote", "description": "Anotacao textual para rastreabilidade", "component_type": "TEXT", "options_json": None, "default_value": None, "validation_regex": None, "sensitive": "N", "active": "Y"},
                                ]
                                for p in params:
                                    store.parameters[p["id"]] = p
                                store.seqs["tbsss_parameters"] = 10

                                # ---------------------------------------------------------
                                # 9. Vinculos de Parametros (tbsss_script_param)
                                # ---------------------------------------------------------
                                links = [
                                    # carga_diaria (sid 1, NOMEADO)
                                    {"script_id": 1, "parameter_id": 1, "sort_order": 1, "required": "Y", "default_value_override": "2026-10-14"},
                                    {"script_id": 1, "parameter_id": 2, "sort_order": 2, "required": "N", "default_value_override": "5000"},
                                    {"script_id": 1, "parameter_id": 3, "sort_order": 3, "required": "Y", "default_value_override": "REAL"},
                                    {"script_id": 1, "parameter_id": 4, "sort_order": 4, "required": "N", "default_value_override": "true"},
                                    {"script_id": 1, "parameter_id": 6, "sort_order": 5, "required": "N", "default_value_override": "00011122233"},
                                    # relatorio_mensal (sid 2, SEQUENCIAL)
                                    {"script_id": 2, "parameter_id": 1, "sort_order": 1, "required": "Y", "default_value_override": "2026-10-01"},
                                    {"script_id": 2, "parameter_id": 7, "sort_order": 2, "required": "Y", "default_value_override": "CSV"},
                                    {"script_id": 2, "parameter_id": 8, "sort_order": 3, "required": "N", "default_value_override": "false"},
                                    # validacao_fiscal (sid 6, NOMEADO)
                                    {"script_id": 6, "parameter_id": 5, "sort_order": 1, "required": "Y", "default_value_override": "0001"},
                                    {"script_id": 6, "parameter_id": 9, "sort_order": 2, "required": "N", "default_value_override": "1.05"},
                                    {"script_id": 6, "parameter_id": 10, "sort_order": 3, "required": "N", "default_value_override": "Lote Outubro 2026"},
                                ]
                                for v in links:
                                    nid = store.next_id("tbsss_script_param")
                                    v["id"] = nid
                                    store.script_param[nid] = v

                                # ---------------------------------------------------------
                                # 10. Agentes (2)
                                # ---------------------------------------------------------
                                agents = [
                                    {"id": 1, "code": "agt-host01", "hostname": "worker01.internal", "daemon_pid": 1001, "version": "1.0.0", "environments": "PRODUCAO,HOMOLOGACAO", "platform": "LINUX", "interpreters": "PYTHON3,BASH", "status": "ACTIVE", "started_at": base_dt - datetime.timedelta(days=3), "heartbeat_at": base_dt, "created_at": base_dt - datetime.timedelta(days=3)},
                                    {"id": 2, "code": "agt-host02", "hostname": "worker02.internal", "daemon_pid": 1002, "version": "1.0.0", "environments": "HOMOLOGACAO,DESENV", "platform": "UNIX", "interpreters": "PYTHON3,SH", "status": "ACTIVE", "started_at": base_dt - datetime.timedelta(days=2), "heartbeat_at": base_dt - datetime.timedelta(seconds=_HB_FROZEN_S), "created_at": base_dt - datetime.timedelta(days=2)},
                                ]
                                # Quadros de atencao do painel (CR-007, R-18): o agt-host02 ficou com a configuracao
                                # antiga (kill=10) e e o unico que atende SH em HOMOLOGACAO.
                                for ag in agents:
                                    ag["critical_config"] = ("hb=10;fence=90;offline=180;call=30;kill=%d;"
                                                              "misfire=RUN_ONCE;tol=300;horizonte=1461;envelhecimento=60"
                                                              % (10 if ag["id"] == 2 else 5))
                                    store.agents[ag["id"]] = ag
                                # agt-host01 renova o heartbeat; agt-host02 envelhece com o relogio (F6.1).
                                store.agents_hb_simulated.add("agt-host01")
                                store.seqs["tbsss_agents"] = 2

                                # ---------------------------------------------------------
                                # 11. Agendamentos (5)
                                # ---------------------------------------------------------
                                agds = [
                                    {"id": 1, "name": "Execucao Avulsa Carga", "script_id": 1, "environment": "PRODUCAO", "user_id": 1, "priority": 2, "recurrence_type": "ONCE", "cron_expression": None, "run_time": None, "week_days": None, "month_day": None, "params_json": '{"data_ref":"2026-10-15"}', "start_date": base_dt + datetime.timedelta(days=1), "end_date": None, "next_run_at": base_dt + datetime.timedelta(days=1), "last_run_at": None, "last_ticket_id": 31, "pause_reason": None, "active": "Y"},
                                    {"id": 2, "name": "Carga Diaria Madrugada", "script_id": 1, "environment": "HOMOLOGACAO", "user_id": 2, "priority": 2, "recurrence_type": "DAILY", "cron_expression": None, "run_time": "03:00", "week_days": None, "month_day": None, "params_json": '{"modo_exec":"SIMULACAO"}', "start_date": base_dt - datetime.timedelta(days=5), "end_date": None, "next_run_at": base_dt + datetime.timedelta(days=1), "last_run_at": base_dt - datetime.timedelta(hours=5), "last_ticket_id": 32, "pause_reason": None, "active": "Y"},
                                    {"id": 3, "name": "Relatorio Semanal Seg/Qua/Sex", "script_id": 2, "environment": "PRODUCAO", "user_id": 1, "priority": 1, "recurrence_type": "WEEKLY", "cron_expression": None, "run_time": "04:00", "week_days": "1,3,5", "month_day": None, "params_json": '{"formato_saida":"CSV"}', "start_date": base_dt - datetime.timedelta(days=10), "end_date": None, "next_run_at": base_dt + datetime.timedelta(days=2), "last_run_at": base_dt - datetime.timedelta(days=2), "last_ticket_id": 33, "pause_reason": None, "active": "Y"},
                                    {"id": 4, "name": "Fechamento Mensal Dia 1", "script_id": 2, "environment": "HOMOLOGACAO", "user_id": 3, "priority": 3, "recurrence_type": "MONTHLY", "cron_expression": None, "run_time": "01:00", "week_days": None, "month_day": 1, "params_json": '{"formato_saida":"JSON"}', "start_date": base_dt - datetime.timedelta(days=30), "end_date": None, "next_run_at": base_dt + datetime.timedelta(days=15), "last_run_at": base_dt - datetime.timedelta(days=15), "last_ticket_id": 34, "pause_reason": None, "active": "Y"},
                                    {"id": 5, "name": "Limpeza Cron Periódica (Pausado)", "script_id": 3, "environment": "PRODUCAO", "user_id": 1, "priority": 2, "recurrence_type": "CRON", "cron_expression": "0 */4 * * *", "run_time": None, "week_days": None, "month_day": None, "params_json": "{}", "start_date": base_dt - datetime.timedelta(days=2), "end_date": None, "next_run_at": base_dt + datetime.timedelta(hours=4), "last_run_at": base_dt, "last_ticket_id": 35, "pause_reason": "MANUAL", "active": "N"},
                                ]
                                now_sch = recurrence.truncate_seconds(base_dt)
                                for a in agds:
                                    a["created_at"] = base_dt - datetime.timedelta(days=20)
                                    # Coerente com as regras (README §2.5, §7.2, §7.6): minuto exato, proxima pelo
                                    # recurrence e parametros_json com as respostas resolvidas completas.
                                    a["start_date"] = recurrence.truncate_seconds(a["start_date"])
                                    a["next_run_at"] = recurrence.next_run(a, now_sch, 1461)
                                    _snap, resolved, _v = _compile_seed(store, a["script_id"], now_sch)
                                    answers = dict(json.loads(a["params_json"]))
                                    for code, value in resolved.items():
                                        answers.setdefault(code, value)
                                    a["params_json"] = _params_json(answers)
                                    store.schedules[a["id"]] = a
                                store.seqs["tbsss_schedules"] = 5

                                # ---------------------------------------------------------
                                # 12. Tickets (40) e Respostas (tbsss_tickets, tbsss_ticket_answer)
                                # ---------------------------------------------------------
                                # 10 PENDING (1..10)
                                # 6 RUNNING (11..16)
                                # 12 SUCCESS (17..28)
                                # 8 FAILED (29..36)
                                # 4 CANCELLED (37..40)
                                compiled = {}
                                sensitive_by_script = {}
                                for v in store.script_param.values():
                                    prm = store.parameters.get(v["parameter_id"])
                                    if prm and prm["sensitive"] == "Y" and v.get("default_value_override"):
                                        sensitive_by_script.setdefault(v["script_id"], []).append(
                                            (prm["code"], v["default_value_override"]))

                                for tid in range(1, 41):
                                    script_id = ((tid - 1) % 4) + 1  # rotaciona scripts 1..4
                                    scr = store.scripts[script_id]
                                    env = "PRODUCAO" if tid % 2 == 1 else "HOMOLOGACAO"
                                    requester = "admin" if tid % 3 == 0 else ("op.prod" if tid % 2 == 1 else "op.hml")
                                    prio = ((tid - 1) % 4) + 1
                                    if prio == 1 and requester != "admin":
                                        prio = 2  # prioridade 1 e reservada a admin (README §5.3)

                                    # Status e motivos
                                    agent_id = None
                                    pid_proc = None
                                    pstart = None
                                    sreason = None
                                    ret_code = None
                                    cancel_req = "N"
                                    trunc = "N"
                                    started = None
                                    heartbeat = None
                                    finished = None
                                    log_out = ""

                                    if tid <= 10:
                                        status = "PENDING"
                                        sched = base_dt + datetime.timedelta(minutes=tid * 5)
                                        if tid == _TICKET_QUEUE_NO_SERVER:
                                            sched = base_dt - datetime.timedelta(minutes=3)
                                    elif tid <= 16:
                                        status = "RUNNING"
                                        sched = base_dt - datetime.timedelta(minutes=10)
                                        started = base_dt - datetime.timedelta(minutes=5)
                                        heartbeat = base_dt - datetime.timedelta(seconds=10)
                                        agent_id = "agt-host01" if tid % 2 == 1 else "agt-host02"
                                        if tid != _TICKET_NO_PID:
                                            pid_proc = 2000 + tid
                                            pstart = 1700000000 + tid
                                            log_out = "[%s] Script %s iniciado em %s.\nEtapa 1 concluida com sucesso.\n" % (
                                                str(started), scr["name"], env
                                            )
                                            store.log_simulated[tid] = {
                                                "step_s": _STEP_LOG_S[tid],
                                                "issued": 0,
                                                "sensitive_codes": list(sensitive_by_script.get(script_id, [])),
                                            }
                                    elif tid <= 28:
                                        status = "SUCCESS"
                                        sreason = "EXIT_OK"
                                        ret_code = 0
                                        sched = base_dt - datetime.timedelta(hours=tid)
                                        started = sched + datetime.timedelta(minutes=1)
                                        heartbeat = started + datetime.timedelta(minutes=4)
                                        finished = started + datetime.timedelta(minutes=5)
                                        agent_id = "agt-host01"
                                        pid_proc = 3000 + tid
                                        pstart = 1700000000 + tid
                                        log_out = "[%s] Script concluido com retorno 0.\n" % str(finished)
                                        if tid == _TICKET_LOG_LARGE:
                                            log_out = _large_log(started) + log_out
                                    elif tid <= 36:
                                        status = "FAILED"
                                        sched = base_dt - datetime.timedelta(hours=tid * 2)
                                        started = sched + datetime.timedelta(minutes=1)
                                        finished = started + datetime.timedelta(minutes=2)
                                        agent_id = "agt-host01" if tid % 2 == 0 else "agt-host02"
                                        pid_proc = 4000 + tid
                                        pstart = 1700000000 + tid

                                        failures_map = {
                                            29: ("EXIT_ERROR", 1),
                                            30: ("TIMEOUT", -3),
                                            31: ("NODE_OFFLINE", -2),
                                            32: ("PRECHECK_FAILED", -4),
                                            33: ("KILLED_SIGNAL", 137),
                                            34: ("SPAWN_ERROR", -4),
                                            35: ("LOG_LIMIT", -5),
                                            36: ("SHUTDOWN", -6),
                                        }
                                        sreason, ret_code = failures_map.get(tid, ("EXIT_ERROR", 1))
                                        if sreason == "LOG_LIMIT":
                                            trunc = "Y"
                                        log_out = "[%s] Falha na execucao: %s (code=%s)\n" % (
                                            str(finished), sreason, ret_code
                                        )
                                        if trunc == "Y":
                                            log_out += MARKER_TRUNCATED
                                    else:
                                        status = "CANCELLED"
                                        sreason = "CANCEL_USER"
                                        ret_code = -1
                                        cancel_req = "Y"
                                        sched = base_dt - datetime.timedelta(hours=tid)
                                        finished = sched + datetime.timedelta(minutes=1)
                                        log_out = "Cancelado pelo usuario antes ou durante o processamento.\n"

                                    parent_id = None
                                    if tid == 25:
                                        parent_id = 17
                                    elif tid == 26:
                                        parent_id = 18

                                    sch_id = None
                                    if tid in (31, 32, 33, 34, 35):
                                        sch_id = tid - 30

                                    # Snapshot v3 e respostas compilados de verdade (README §6.5, §2.5).
                                    if script_id not in compiled:
                                        compiled[script_id] = _compile_seed(
                                            store, script_id, base_dt - datetime.timedelta(minutes=30))
                                    snapshot_json, resolved, link_scr = compiled[script_id]

                                    t_obj = {
                                        "id": tid,
                                        "script_id": scr["id"],
                                        "environment": env,
                                        "requested_by": requester,
                                        "source_ip": "127.0.0.1",
                                        "agent_id": agent_id,
                                        "process_id": pid_proc,
                                        "process_start": pstart,
                                        "status": status,
                                        "priority": prio,
                                        "cancel_requested": cancel_req,
                                        "status_reason": sreason,
                                        "parent_ticket_id": parent_id,
                                        "schedule_id": sch_id,
                                        "submitted_params": snapshot_json,
                                        "log_output": log_out,
                                        "log_truncated": trunc,
                                        "return_code": ret_code,
                                        "scheduled_at": sched,
                                        "started_at": started,
                                        "heartbeat_at": heartbeat,
                                        "finished_at": finished,
                                        # created_at nunca no futuro (README §2.5): o agendado foi pedido antes.
                                        "created_at": min(sched, base_dt - datetime.timedelta(minutes=tid)),
                                    }
                                    store.tickets[tid] = t_obj

                                    # Respostas resolvidas (tbsss_ticket_answer, README §5.4): None omitido, CHECKBOX em texto.
                                    for v in link_scr:
                                        value = resolved.get(v["code"])
                                        if value is None:
                                            continue
                                        rid = store.next_id("tbsss_ticket_answer")
                                        store.ticket_answer[rid] = {
                                            "id": rid,
                                            "ticket_id": tid,
                                            "parameter_id": v["parameter_id"],
                                            "answer_value": ("true" if value else "false") if isinstance(value, bool) else value,
                                            "created_at": t_obj["created_at"],
                                        }

                                store.seqs["tbsss_tickets"] = 40
                                _seed_outputs(store)
                                _seed_inputs(store, base_dt)

                                # ---------------------------------------------------------
                                # 13. Auditoria (30 linhas)
                                # ---------------------------------------------------------
                                actions = [
                                    ("admin", "LOGIN_OK", "tbsss_users", 1, "Login bem-sucedido via web"),
                                    ("op.prod", "LOGIN_OK", "tbsss_users", 2, "Login bem-sucedido via web"),
                                    ("op.hml", "LOGIN_OK", "tbsss_users", 3, "Login bem-sucedido via web"),
                                    ("consulta", "LOGIN_OK", "tbsss_users", 4, "Login bem-sucedido via web"),
                                    ("bloqueado", "LOGIN_FAILED", "tbsss_users", 6, "Tentativa de login com senha incorreta"),
                                    ("bloqueado", "LOGIN_LOCKED", "tbsss_users", 6, "Conta bloqueada apos atingir limite de falhas"),
                                    ("admin", "CREATE", "tbsss_environments", 1, "Ambiente PRODUCAO cadastrado"),
                                    ("admin", "CREATE", "tbsss_environments", 2, "Ambiente HOMOLOGACAO cadastrado"),
                                    ("admin", "CREATE", "tbsss_environments", 3, "Ambiente DESENV cadastrado"),
                                    ("admin", "DEACTIVATE", "tbsss_environments", 3, "Ambiente DESENV desativado"),
                                    ("admin", "CREATE", "tbsss_profiles", 1, "Perfil ADMINISTRADOR cadastrado"),
                                    ("admin", "CREATE", "tbsss_profiles", 2, "Perfil OPERATOR_PROD cadastrado"),
                                    ("admin", "PERM_UPDATE", "tbsss_profiles", 2, "Matriz de permissoes atualizada: +EXEC_SCRIPT, +VIEW_LOGS"),
                                    ("admin", "CREATE", "tbsss_scripts", 1, "Script carga_diaria cadastrado"),
                                    ("admin", "CREATE", "tbsss_scripts", 2, "Script relatorio_mensal cadastrado"),
                                    ("admin", "CREATE", "tbsss_scripts", 3, "Script cleanup_tmp cadastrado"),
                                    ("admin", "CREATE", "tbsss_parameters", 1, "Parametro data_ref cadastrado"),
                                    ("admin", "CREATE", "tbsss_parameters", 2, "Parametro limite_linhas cadastrado"),
                                    ("admin", "UPDATE", "tbsss_parameters", 2, "Valor padrao atualizado para 1000"),
                                    ("admin", "CREATE", "tbsss_schedules", 1, "Regra Execucao Avulsa Carga cadastrada"),
                                    ("admin", "CREATE", "tbsss_schedules", 5, "Regra Limpeza Cron Periodica cadastrada"),
                                    ("admin", "SCHEDULE_PAUSE", "tbsss_schedules", 5, "Agendamento pausado manualmente"),
                                    ("op.prod", "TICKET_CREATE", "tbsss_tickets", 1, "Ticket criado para carga_diaria em PRODUCAO"),
                                    ("op.hml", "TICKET_CREATE", "tbsss_tickets", 2, "Ticket criado para relatorio_mensal em HOMOLOGACAO"),
                                    ("op.prod", "TICKET_CREATE", "tbsss_tickets", 11, "Ticket criado para carga_diaria em PRODUCAO"),
                                    ("admin", "TICKET_CANCEL", "tbsss_tickets", 37, "Cancelamento solicitado para ticket 37"),
                                    ("admin", "TICKET_CANCEL", "tbsss_tickets", 38, "Cancelamento solicitado para ticket 38"),
                                    ("SYSTEM:agt-host01", "AGENT_START", "tbsss_agents", 1, "Agente agt-host01 iniciado no host worker01.internal"),
                                    ("SYSTEM:agt-host02", "AGENT_START", "tbsss_agents", 2, "Agente agt-host02 iniciado no host worker02.internal"),
                                    ("admin", "UPDATE", "tbsss_users", 6, "Conta desbloqueada pelo administrador"),
                                ]
                                for i, (actor, action, ent, ent_id, det) in enumerate(actions, 1):
                                    store.audit[i] = {
                                        "id": i,
                                        "actor": actor,
                                        "source_ip": "127.0.0.1",
                                        "action": action,
                                        "entity": ent,
                                        "entity_id": ent_id,
                                        "detail": det,
                                        "created_at": base_dt - datetime.timedelta(hours=35 - i),
                                    }
                                store.seqs["tbsss_audit"] = 30

                                _stamp_record(store, base_dt)

                                # Controle (tabela 17, CR-007 D4): o FAKE nasce na versao do esquema do codigo.
                                store.control[1] = {"id": 1, "schema_version": sql_ident.SCHEMA_VERSION,
                                                     "version_applied_at": base_dt - datetime.timedelta(days=90),
                                                     "version_applied_by": "SYSTEM:seed", "purge_owner": None,
                                                     "purge_lease_until": None}
                                store.seqs["tbsss_control"] = 1
