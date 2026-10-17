# -*- coding: utf-8 -*-
"""Carga deterministica de seed para o backend FAKE (README §2.5, §4.3.D, §10, §11).

Totalmente deterministico, sem aleatoriedade, compativel com Python 3.6.
"""
import datetime
import json

import params_compiler
import recurrence
import security
import sql_ident

# Contas de demonstracao que permanecem sem senha utilizavel mesmo em DEV.
_SEM_SENHA_DEV = ("inativo", "bloqueado")

# Marcador final do log truncado no banco (README §8.10).
MARCADOR_TRUNCADO = "[SSS] log truncado no banco; arquivo integral no agente\n"

# Segundos por etapa do log simulado dos RUNNING (o 16 nao tem log, ver _TICKET_SEM_PID): na carga ja decorreram 5 min desde started_at;
# o ticket 13 termina ~100 s depois e os demais entre 15 e 25 min depois.
_PASSO_LOG_S = {11: 24, 12: 30, 13: 8, 14: 36, 15: 30, 16: 36}
_LINHAS_LOG_VOLUMOSO = 27000
# Idade inicial do heartbeat congelado do agt-host02: com os limiares padrao (10/90/180 s) ele
# comeca ATRASADO, fica EM_RISCO ~1 min depois e OFFLINE ~2,5 min depois (README §13).
_HB_CONGELADO_S = 30
_TICKET_LOG_VOLUMOSO = 17
# Quadros de atencao da tela de agentes (CR-007, R-18): o ticket 4 (SH em HOMOLOGACAO) ja venceu e
# so o agt-host02 atende o par, entao aparece em "Fila sem atendente" quando ele sai de ATRASADO;
# o RUNNING 16 foi reservado sem PID ("Rodando sem PID", sem log simulado).
_TICKET_FILA_SEM_ATENDENTE = 4
_TICKET_SEM_PID = 16


def _log_volumoso(inicio):
    # ~2 MB em UTF-8, com acentos, para exercitar a leitura por offset e o download.
    linhas = []
    for i in range(1, _LINHAS_LOG_VOLUMOSO + 1):
        quando = inicio + datetime.timedelta(seconds=i // 100)
        linhas.append(u"[%s] lote %06d/%06d: registros validados \u2014 situa\u00e7\u00e3o OK\n"
                      % (quando, i, _LINHAS_LOG_VOLUMOSO))
    return u"".join(linhas)


def _vinculos_compilador(store, script_id):
    """Vinculos ativos do script no formato do compilador (parametro + ordem, obrigatorio e sub)."""
    vinculos = []
    for v in sorted((v for v in store.script_param.values() if v["script_id"] == script_id), key=lambda v: v["ordem"]):
        prm = store.parametros[v["parametro_id"]]
        if prm["ativo"] == "S":
            vinculos.append(dict(prm, parametro_id=prm["id"], ordem=v["ordem"], obrigatorio=v["obrigatorio"],
                                 valor_padrao_sub=v.get("valor_padrao_sub")))
    return vinculos


def _compilar_seed(store, script_id, agora):
    """Snapshot e respostas resolvidas reais do script (README §2.5: seed coerente com as regras)."""
    vinculos = _vinculos_compilador(store, script_id)
    snapshot, resolvidos, erros = params_compiler.compilar_snapshot(store.scripts[script_id], vinculos, {}, agora)
    if erros:
        raise ValueError("seed incoerente: script %s nao compila (%s)" % (script_id, sorted(erros)))
    return snapshot, resolvidos, vinculos


def _parametros_json(resolvidos):
    """parametros_json de agendamento: respostas resolvidas, nulos omitidos, CHECKBOX como texto (README §7.6)."""
    obj = {}
    for codigo, valor in resolvidos.items():
        if valor is None:
            continue
        obj[codigo] = ("true" if valor else "false") if isinstance(valor, bool) else valor
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_ATOR_SEED = "SYSTEM:seed"
_CADASTROS = ("ambientes", "perfis", "funcionalidades", "perfil_func", "perfil_amb", "scripts", "perfil_scr",
              "script_amb", "usuarios", "parametros", "script_param", "agendamentos")


def _entre(valor, minimo, maximo):
    return max(minimo, min(valor, maximo))


def _carimbar_registro(store, base_dt):
    """Colunas de registro coerentes com o README §10 e §2.5 (CR-006).

    Cadastros e vinculos: criados por SYSTEM:seed; updated_* so onde o estado implica alteracao
    (registro inativo, regra pausada). Tickets: solicitante ou o agente do desdobro; fora de PENDING,
    a ultima mudanca de situacao. Agentes: o proprio agente. Sempre entre created_at e base_dt.
    """
    for nome in _CADASTROS:
        for reg in getattr(store, nome).values():
            reg.setdefault("created_at", base_dt - datetime.timedelta(days=90))
            reg.update(created_by=_ATOR_SEED, updated_at=None, updated_by=None)
            if reg.get("ativo") == "N":
                reg["updated_at"] = _entre(reg["created_at"] + datetime.timedelta(days=1), reg["created_at"], base_dt)
                reg["updated_by"] = _ATOR_SEED
    for a in store.agendamentos.values():
        if a["ativo"] == "N":
            if a.get("pausa_motivo") == "MANUAL":
                a["updated_by"] = store.usuarios[a["usuario_id"]]["login"]
            else:
                a["updated_by"] = "SYSTEM:agt-host01"
            a["updated_at"] = _entre(a.get("ultima_execucao") or a["created_at"], a["created_at"], base_dt)
    for ag in store.agentes.values():
        ag.update(created_by="SYSTEM:%s" % ag["codigo"], updated_at=None, updated_by=None)
    for t in store.tickets.values():
        if t.get("agendamento_id") is not None:
            t["created_by"] = "SYSTEM:%s" % (t.get("agente_id") or "agt-host01")
        else:
            t["created_by"] = t["solicitante"]
        t["updated_at"] = t["updated_by"] = None
        if t["status"] == "PENDING":
            continue
        if t["status"] == "CANCELLED" and t.get("started_at") is None:
            # Cancelado na fila pelo administrador (trilha do seed: TICKET_CANCELAR por admin).
            t["updated_by"] = "admin"
            quando = t.get("finished_at")
        elif t["status"] == "RUNNING":
            t["updated_by"] = "SYSTEM:%s" % t["agente_id"]
            quando = t.get("started_at")
        else:
            t["updated_by"] = "SYSTEM:%s" % t["agente_id"]
            quando = t.get("finished_at") or t.get("started_at")
        t["updated_at"] = _entre(quando or t["created_at"], t["created_at"], base_dt)
    for r in store.ticket_resp.values():
        r.update(created_by=store.tickets[r["ticket_id"]]["created_by"], updated_at=None, updated_by=None)


def carregar_seed(store, forcar=False, senha_dev=None):
    """Carrega dados iniciais deterministicos no store FAKE de forma idempotente.

    senha_dev: senha comum dos usuarios de demonstracao (exceto inativo e bloqueado),
    com hash e salt individuais. Sem ela, as senhas ficam inutilizaveis ('!').
    """
    with store.lock_usuarios:
        with store.lock_rbac:
            with store.lock_catalogo:
                with store.lock_tickets:
                    with store.lock_agendamentos:
                        with store.lock_auditoria:
                            with store.lock_agentes:
                                if store.ambientes and not forcar:
                                    return

                                store.reset()
                                base_dt = store.agora()

                                # ---------------------------------------------------------
                                # 1. Ambientes (3)
                                # ---------------------------------------------------------
                                ambs = [
                                    {"id": 1, "nome": "PRODUCAO", "descricao": "Ambiente de Producao Oficial", "conexao": "db-producao.local:1521/svc", "ativo": "S"},
                                    {"id": 2, "nome": "HOMOLOGACAO", "descricao": "Ambiente de Homologacao e Testes", "conexao": "db-homologacao.local:1521/svc", "ativo": "S"},
                                    {"id": 3, "nome": "DESENV", "descricao": "Ambiente de Desenvolvimento", "conexao": "db-desenv.local:1521/svc", "ativo": "N"},
                                ]
                                for a in ambs:
                                    a["created_at"] = base_dt - datetime.timedelta(days=90)
                                    store.ambientes[a["id"]] = a
                                store.seqs["tbsss_ambientes"] = 3

                                # ---------------------------------------------------------
                                # 2. Funcionalidades canonicas (10) - README §4.3.D
                                # ---------------------------------------------------------
                                funcs = [
                                    {"id": 1, "codigo": "EXEC_SCRIPT", "nome": "Disparar Scripts", "modulo": "OPERACAO", "descricao": "Preencher questionários e abrir tickets", "ativo": "S"},
                                    {"id": 2, "codigo": "VER_LOGS", "nome": "Consultar Logs", "modulo": "OPERACAO", "descricao": "Visualizar logs e histórico em tempo quase real", "ativo": "S"},
                                    {"id": 3, "codigo": "CANC_TICKET", "nome": "Cancelar Tickets", "modulo": "OPERACAO", "descricao": "Cancelar tickets de terceiros em ambientes autorizados", "ativo": "S"},
                                    {"id": 4, "codigo": "CAD_USUARIOS", "nome": "Gestão de Usuários", "modulo": "ADMIN", "descricao": "Gerenciar operadores e credenciais", "ativo": "S"},
                                    {"id": 5, "codigo": "CAD_PERFIS", "nome": "Gestão de Perfis", "modulo": "ADMIN", "descricao": "Gerenciar perfis e matrizes de permissão", "ativo": "S"},
                                    {"id": 6, "codigo": "CAD_AMBIENTES", "nome": "Gestão de Ambientes", "modulo": "ADMIN", "descricao": "Gerenciar ambientes e DSNs", "ativo": "S"},
                                    {"id": 7, "codigo": "CAD_SCRIPTS", "nome": "Gestão de Scripts", "modulo": "ADMIN", "descricao": "Cadastrar rotinas e homologação por ambiente", "ativo": "S"},
                                    {"id": 8, "codigo": "CAD_PARAMETROS", "nome": "Dicionário de Parâmetros", "modulo": "ADMIN", "descricao": "Gerenciar perguntas e flags reutilizáveis", "ativo": "S"},
                                    {"id": 9, "codigo": "CAD_AGENDAMENTOS", "nome": "Regras de Agendamento", "modulo": "ADMIN", "descricao": "Criar e gerenciar recorrências", "ativo": "S"},
                                    {"id": 10, "codigo": "VER_AUDITORIA", "nome": "Auditoria", "modulo": "ADMIN", "descricao": "Consultar a trilha de auditoria e os agentes", "ativo": "S"},
                                ]
                                for f in funcs:
                                    store.funcionalidades[f["id"]] = f
                                store.seqs["tbsss_funcionalidades"] = 10

                                # ---------------------------------------------------------
                                # 3. Perfis (4)
                                # ---------------------------------------------------------
                                perfis = [
                                    {"id": 1, "nome": "ADMINISTRADOR", "descricao": "Administrador Geral do Sistema", "is_admin": "S", "perm_versao": 1, "ativo": "S"},
                                    {"id": 2, "nome": "OPERADOR_PROD", "descricao": "Operador de Ambientes de Producao", "is_admin": "N", "perm_versao": 1, "ativo": "S"},
                                    {"id": 3, "nome": "OPERADOR_HML", "descricao": "Operador de Ambientes de Homologacao", "is_admin": "N", "perm_versao": 1, "ativo": "S"},
                                    {"id": 4, "nome": "CONSULTA", "descricao": "Perfil de Apenas Leitura e Consulta", "is_admin": "N", "perm_versao": 1, "ativo": "S"},
                                ]
                                for p in perfis:
                                    store.perfis[p["id"]] = p
                                store.seqs["tbsss_perfis"] = 4

                                # ---------------------------------------------------------
                                # 4. Usuarios (6)
                                # ---------------------------------------------------------
                                usuarios = [
                                    {"id": 1, "login": "admin", "nome": "Administrador Geral", "senha_hash": "!", "perfil_id": 1, "tentativas_falha": 0, "bloqueado_ate": None, "ultimo_login": base_dt - datetime.timedelta(hours=1), "senha_alterada_em": base_dt - datetime.timedelta(days=30), "ativo": "S"},
                                    {"id": 2, "login": "op.prod", "nome": "Operador Producao", "senha_hash": "!", "perfil_id": 2, "tentativas_falha": 0, "bloqueado_ate": None, "ultimo_login": base_dt - datetime.timedelta(hours=2), "senha_alterada_em": base_dt - datetime.timedelta(days=20), "ativo": "S"},
                                    {"id": 3, "login": "op.hml", "nome": "Operador Homologacao", "senha_hash": "!", "perfil_id": 3, "tentativas_falha": 0, "bloqueado_ate": None, "ultimo_login": base_dt - datetime.timedelta(hours=3), "senha_alterada_em": base_dt - datetime.timedelta(days=15), "ativo": "S"},
                                    {"id": 4, "login": "consulta", "nome": "Auditor e Consulta", "senha_hash": "!", "perfil_id": 4, "tentativas_falha": 0, "bloqueado_ate": None, "ultimo_login": base_dt - datetime.timedelta(days=1), "senha_alterada_em": base_dt - datetime.timedelta(days=10), "ativo": "S"},
                                    {"id": 5, "login": "inativo", "nome": "Usuario Desativado", "senha_hash": "!", "perfil_id": 4, "tentativas_falha": 0, "bloqueado_ate": None, "ultimo_login": base_dt - datetime.timedelta(days=60), "senha_alterada_em": base_dt - datetime.timedelta(days=60), "ativo": "N"},
                                    {"id": 6, "login": "bloqueado", "nome": "Usuario Temporariamente Bloqueado", "senha_hash": "!", "perfil_id": 2, "tentativas_falha": 5, "bloqueado_ate": base_dt + datetime.timedelta(minutes=30), "ultimo_login": base_dt - datetime.timedelta(hours=4), "senha_alterada_em": base_dt - datetime.timedelta(days=5), "ativo": "S"},
                                ]
                                for u in usuarios:
                                    u["created_at"] = base_dt - datetime.timedelta(days=60)
                                    u["sessao_epoch"] = 0
                                    if senha_dev is not None and u["login"] not in _SEM_SENHA_DEV:
                                        u["senha_hash"] = security.hash_senha(senha_dev)
                                    store.usuarios[u["id"]] = u
                                store.seqs["tbsss_usuarios"] = 6

                                # ---------------------------------------------------------
                                # 5. Scripts (6)
                                # ---------------------------------------------------------
                                scripts = [
                                    {"id": 1, "nome": "carga_diaria", "descricao": "Carga diaria de movimentacoes", "grupo": "CARGAS", "categoria": "DIARIA", "etapa": "PROCESSAMENTO", "interpretador": "PYTHON3", "path_file": "/opt/automacoes/scripts/carga_diaria.py", "tipo_param": "NOMEADO", "max_qtd_parallel_env": 1, "timeout_seg": 3600, "ativo": "S"},
                                    {"id": 2, "nome": "relatorio_mensal", "descricao": "Extracao financeira consolidada", "grupo": "RELATORIOS", "categoria": "FINANCEIRO", "etapa": "EXTRACAO", "interpretador": "PYTHON3", "path_file": "/opt/automacoes/scripts/relatorio_mensal.py", "tipo_param": "SEQUENCIAL", "max_qtd_parallel_env": 2, "timeout_seg": 1800, "ativo": "S"},
                                    {"id": 3, "nome": "cleanup_tmp", "descricao": "Limpeza de arquivos temporarios", "grupo": "MANUTENCAO", "categoria": "LIMPEZA", "etapa": "PURGE", "interpretador": "BASH", "path_file": "/opt/automacoes/scripts/cleanup_tmp.sh", "tipo_param": "NENHUM", "max_qtd_parallel_env": 1, "timeout_seg": 600, "ativo": "S"},
                                    {"id": 4, "nome": "sync_tabelas", "descricao": "Sincronizacao de tabelas auxiliares", "grupo": "INTEGRACAO", "categoria": "SYNC", "etapa": "CARGA", "interpretador": "SH", "path_file": "/opt/automacoes/scripts/sync_tabelas.sh", "tipo_param": "NOMEADO", "max_qtd_parallel_env": 1, "timeout_seg": 1200, "ativo": "S"},
                                    {"id": 5, "nome": "backup_extra", "descricao": "Rotina de backup extraordinario (legado)", "grupo": "BACKUP", "categoria": "SISTEMA", "etapa": "DUMP", "interpretador": "BASH", "path_file": "/opt/automacoes/scripts/backup_extra.sh", "tipo_param": "SEQUENCIAL", "max_qtd_parallel_env": 1, "timeout_seg": 7200, "ativo": "N"},
                                    {"id": 6, "nome": "validacao_fiscal", "descricao": "Checagem de consistencia de SPED", "grupo": "FISCAL", "categoria": "SPED", "etapa": "VALIDACAO", "interpretador": "PYTHON3", "path_file": "/opt/automacoes/scripts/validacao_fiscal.py", "tipo_param": "NOMEADO", "max_qtd_parallel_env": 1, "timeout_seg": 900, "ativo": "S"},
                                ]
                                for s in scripts:
                                    store.scripts[s["id"]] = s
                                store.seqs["tbsss_scripts"] = 6

                                # ---------------------------------------------------------
                                # 6. Homologacao de Scripts por Ambiente (tbsss_script_amb)
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
                                    nid = store.proximo_id("tbsss_script_amb")
                                    store.script_amb[nid] = {"id": nid, "script_id": sid, "ambiente_id": aid}

                                # ---------------------------------------------------------
                                # 7. Matrizes de Perfil (tbsss_perfil_func, amb, scr)
                                # ---------------------------------------------------------
                                # ADMINISTRADOR (id 1)
                                for f in funcs:
                                    nid = store.proximo_id("tbsss_perfil_func")
                                    store.perfil_func[nid] = {"id": nid, "perfil_id": 1, "funcionalidade_id": f["id"]}
                                for a in ambs:
                                    nid = store.proximo_id("tbsss_perfil_amb")
                                    store.perfil_amb[nid] = {"id": nid, "perfil_id": 1, "ambiente_id": a["id"]}
                                for s in scripts:
                                    nid = store.proximo_id("tbsss_perfil_scr")
                                    store.perfil_scr[nid] = {"id": nid, "perfil_id": 1, "script_id": s["id"]}

                                # OPERADOR_PROD (id 2) -> EXEC_SCRIPT(1), VER_LOGS(2), CANC_TICKET(3)
                                for fid in (1, 2, 3):
                                    nid = store.proximo_id("tbsss_perfil_func")
                                    store.perfil_func[nid] = {"id": nid, "perfil_id": 2, "funcionalidade_id": fid}
                                for aid in (1, 2):
                                    nid = store.proximo_id("tbsss_perfil_amb")
                                    store.perfil_amb[nid] = {"id": nid, "perfil_id": 2, "ambiente_id": aid}
                                for sid in (1, 2, 3, 6):
                                    nid = store.proximo_id("tbsss_perfil_scr")
                                    store.perfil_scr[nid] = {"id": nid, "perfil_id": 2, "script_id": sid}

                                # OPERADOR_HML (id 3) -> EXEC_SCRIPT(1), VER_LOGS(2), CANC_TICKET(3)
                                for fid in (1, 2, 3):
                                    nid = store.proximo_id("tbsss_perfil_func")
                                    store.perfil_func[nid] = {"id": nid, "perfil_id": 3, "funcionalidade_id": fid}
                                for aid in (2, 3):
                                    nid = store.proximo_id("tbsss_perfil_amb")
                                    store.perfil_amb[nid] = {"id": nid, "perfil_id": 3, "ambiente_id": aid}
                                for sid in (1, 2, 3, 4):
                                    nid = store.proximo_id("tbsss_perfil_scr")
                                    store.perfil_scr[nid] = {"id": nid, "perfil_id": 3, "script_id": sid}

                                # CONSULTA (id 4) -> VER_LOGS(2)
                                nid = store.proximo_id("tbsss_perfil_func")
                                store.perfil_func[nid] = {"id": nid, "perfil_id": 4, "funcionalidade_id": 2}
                                for aid in (1, 2):
                                    nid = store.proximo_id("tbsss_perfil_amb")
                                    store.perfil_amb[nid] = {"id": nid, "perfil_id": 4, "ambiente_id": aid}
                                for sid in (1, 2, 3, 4, 6):
                                    nid = store.proximo_id("tbsss_perfil_scr")
                                    store.perfil_scr[nid] = {"id": nid, "perfil_id": 4, "script_id": sid}

                                # ---------------------------------------------------------
                                # 8. Parametros (10)
                                # ---------------------------------------------------------
                                params = [
                                    {"id": 1, "codigo": "data_ref", "param_nomeado": "--data-ref", "label": "Data de Referencia", "descricao": "Data base para execucao da rotina", "tipo_componente": "DATE", "opcoes_json": None, "valor_padrao": None, "regex_validacao": None, "sensivel": "N", "ativo": "S"},
                                    {"id": 2, "codigo": "limite_linhas", "param_nomeado": "-n", "label": "Limite de Registros", "descricao": "Quantidade maxima de linhas processadas", "tipo_componente": "NUMBER", "opcoes_json": None, "valor_padrao": "1000", "regex_validacao": None, "sensivel": "N", "ativo": "S"},
                                    {"id": 3, "codigo": "modo_exec", "param_nomeado": "--modo", "label": "Modo de Operacao", "descricao": "Define se o processamento e simulacao ou real", "tipo_componente": "SELECT", "opcoes_json": '{"SIMULACAO":"Simulacao","REAL":"Execucao Real"}', "valor_padrao": "SIMULACAO", "regex_validacao": None, "sensivel": "N", "ativo": "S"},
                                    {"id": 4, "codigo": "verbose", "param_nomeado": "--verbose", "label": "Log Detalhado", "descricao": "Ativa impressao detalhada de passos", "tipo_componente": "CHECKBOX", "opcoes_json": None, "valor_padrao": "false", "regex_validacao": None, "sensivel": "N", "ativo": "S"},
                                    {"id": 5, "codigo": "codigo_filial", "param_nomeado": "--filial", "label": "Codigo da Filial", "descricao": "Identificador numerico de 4 digitos da filial", "tipo_componente": "TEXT", "opcoes_json": None, "valor_padrao": "0001", "regex_validacao": r"^[0-9]{4}$", "sensivel": "N", "ativo": "S"},
                                    {"id": 6, "codigo": "documento_cliente", "param_nomeado": "--documento", "label": "Documento do cliente (CPF)", "descricao": "Dado pessoal: mascarado na tela e nos logs; nunca use para senha ou credencial", "tipo_componente": "TEXT", "opcoes_json": None, "valor_padrao": None, "regex_validacao": None, "sensivel": "S", "ativo": "S"},
                                    {"id": 7, "codigo": "formato_saida", "param_nomeado": "-f", "label": "Formato de Arquivo", "descricao": "Extensao de exportacao do relatorio", "tipo_componente": "SELECT", "opcoes_json": '{"CSV":"Arquivo CSV","JSON":"Arquivo JSON"}', "valor_padrao": "CSV", "regex_validacao": None, "sensivel": "N", "ativo": "S"},
                                    {"id": 8, "codigo": "notificar_email", "param_nomeado": "-m", "label": "Disparar Alerta", "descricao": "Envia email aos gestores no encerramento", "tipo_componente": "CHECKBOX", "opcoes_json": None, "valor_padrao": "false", "regex_validacao": None, "sensivel": "N", "ativo": "S"},
                                    {"id": 9, "codigo": "taxa_ajuste", "param_nomeado": "--taxa", "label": "Fator de Correcao", "descricao": "Multiplicador financeiro", "tipo_componente": "NUMBER", "opcoes_json": None, "valor_padrao": "1.0", "regex_validacao": None, "sensivel": "N", "ativo": "S"},
                                    {"id": 10, "codigo": "descricao_lote", "param_nomeado": "--descricao", "label": "Descricao do Lote", "descricao": "Anotacao textual para rastreabilidade", "tipo_componente": "TEXT", "opcoes_json": None, "valor_padrao": None, "regex_validacao": None, "sensivel": "N", "ativo": "S"},
                                ]
                                for p in params:
                                    store.parametros[p["id"]] = p
                                store.seqs["tbsss_parametros"] = 10

                                # ---------------------------------------------------------
                                # 9. Vinculos de Parametros (tbsss_script_param)
                                # ---------------------------------------------------------
                                vinculos = [
                                    # carga_diaria (sid 1, NOMEADO)
                                    {"script_id": 1, "parametro_id": 1, "ordem": 1, "obrigatorio": "S", "valor_padrao_sub": "2026-10-14"},
                                    {"script_id": 1, "parametro_id": 2, "ordem": 2, "obrigatorio": "N", "valor_padrao_sub": "5000"},
                                    {"script_id": 1, "parametro_id": 3, "ordem": 3, "obrigatorio": "S", "valor_padrao_sub": "REAL"},
                                    {"script_id": 1, "parametro_id": 4, "ordem": 4, "obrigatorio": "N", "valor_padrao_sub": "true"},
                                    {"script_id": 1, "parametro_id": 6, "ordem": 5, "obrigatorio": "N", "valor_padrao_sub": "00011122233"},
                                    # relatorio_mensal (sid 2, SEQUENCIAL)
                                    {"script_id": 2, "parametro_id": 1, "ordem": 1, "obrigatorio": "S", "valor_padrao_sub": "2026-10-01"},
                                    {"script_id": 2, "parametro_id": 7, "ordem": 2, "obrigatorio": "S", "valor_padrao_sub": "CSV"},
                                    {"script_id": 2, "parametro_id": 8, "ordem": 3, "obrigatorio": "N", "valor_padrao_sub": "false"},
                                    # validacao_fiscal (sid 6, NOMEADO)
                                    {"script_id": 6, "parametro_id": 5, "ordem": 1, "obrigatorio": "S", "valor_padrao_sub": "0001"},
                                    {"script_id": 6, "parametro_id": 9, "ordem": 2, "obrigatorio": "N", "valor_padrao_sub": "1.05"},
                                    {"script_id": 6, "parametro_id": 10, "ordem": 3, "obrigatorio": "N", "valor_padrao_sub": "Lote Outubro 2026"},
                                ]
                                for v in vinculos:
                                    nid = store.proximo_id("tbsss_script_param")
                                    v["id"] = nid
                                    store.script_param[nid] = v

                                # ---------------------------------------------------------
                                # 10. Agentes (2)
                                # ---------------------------------------------------------
                                agentes = [
                                    {"id": 1, "codigo": "agt-host01", "hostname": "worker01.internal", "pid_daemon": 1001, "versao": "1.0.0", "ambientes": "PRODUCAO,HOMOLOGACAO", "plataforma": "LINUX", "interpretadores": "PYTHON3,BASH", "status": "ATIVO", "iniciado_em": base_dt - datetime.timedelta(days=3), "heartbeat_at": base_dt, "created_at": base_dt - datetime.timedelta(days=3)},
                                    {"id": 2, "codigo": "agt-host02", "hostname": "worker02.internal", "pid_daemon": 1002, "versao": "1.0.0", "ambientes": "HOMOLOGACAO,DESENV", "plataforma": "UNIX", "interpretadores": "PYTHON3,SH", "status": "ATIVO", "iniciado_em": base_dt - datetime.timedelta(days=2), "heartbeat_at": base_dt - datetime.timedelta(seconds=_HB_CONGELADO_S), "created_at": base_dt - datetime.timedelta(days=2)},
                                ]
                                # Quadros de atencao do painel (CR-007, R-18): o agt-host02 ficou com a configuracao
                                # antiga (kill=10) e e o unico que atende SH em HOMOLOGACAO.
                                for ag in agentes:
                                    ag["config_criticos"] = ("hb=10;fence=90;offline=180;call=30;kill=%d;"
                                                              "misfire=RUN_ONCE;tol=300;horizonte=1461;envelhecimento=60"
                                                              % (10 if ag["id"] == 2 else 5))
                                    store.agentes[ag["id"]] = ag
                                # agt-host01 renova o heartbeat; agt-host02 envelhece com o relogio (F6.1).
                                store.agentes_hb_sim.add("agt-host01")
                                store.seqs["tbsss_agentes"] = 2

                                # ---------------------------------------------------------
                                # 11. Agendamentos (5)
                                # ---------------------------------------------------------
                                agds = [
                                    {"id": 1, "nome": "Execucao Avulsa Carga", "script_id": 1, "ambiente": "PRODUCAO", "usuario_id": 1, "prioridade": 2, "tipo_recorrencia": "UNICA", "expressao_cron": None, "hora_execucao": None, "dias_semana": None, "dia_mes": None, "parametros_json": '{"data_ref":"2026-10-15"}', "data_inicio": base_dt + datetime.timedelta(days=1), "data_fim": None, "proxima_execucao": base_dt + datetime.timedelta(days=1), "ultima_execucao": None, "ultimo_ticket_id": 31, "pausa_motivo": None, "ativo": "S"},
                                    {"id": 2, "nome": "Carga Diaria Madrugada", "script_id": 1, "ambiente": "HOMOLOGACAO", "usuario_id": 2, "prioridade": 2, "tipo_recorrencia": "DIARIA", "expressao_cron": None, "hora_execucao": "03:00", "dias_semana": None, "dia_mes": None, "parametros_json": '{"modo_exec":"SIMULACAO"}', "data_inicio": base_dt - datetime.timedelta(days=5), "data_fim": None, "proxima_execucao": base_dt + datetime.timedelta(days=1), "ultima_execucao": base_dt - datetime.timedelta(hours=5), "ultimo_ticket_id": 32, "pausa_motivo": None, "ativo": "S"},
                                    {"id": 3, "nome": "Relatorio Semanal Seg/Qua/Sex", "script_id": 2, "ambiente": "PRODUCAO", "usuario_id": 1, "prioridade": 1, "tipo_recorrencia": "SEMANAL", "expressao_cron": None, "hora_execucao": "04:00", "dias_semana": "1,3,5", "dia_mes": None, "parametros_json": '{"formato_saida":"CSV"}', "data_inicio": base_dt - datetime.timedelta(days=10), "data_fim": None, "proxima_execucao": base_dt + datetime.timedelta(days=2), "ultima_execucao": base_dt - datetime.timedelta(days=2), "ultimo_ticket_id": 33, "pausa_motivo": None, "ativo": "S"},
                                    {"id": 4, "nome": "Fechamento Mensal Dia 1", "script_id": 2, "ambiente": "HOMOLOGACAO", "usuario_id": 3, "prioridade": 3, "tipo_recorrencia": "MENSAL", "expressao_cron": None, "hora_execucao": "01:00", "dias_semana": None, "dia_mes": 1, "parametros_json": '{"formato_saida":"JSON"}', "data_inicio": base_dt - datetime.timedelta(days=30), "data_fim": None, "proxima_execucao": base_dt + datetime.timedelta(days=15), "ultima_execucao": base_dt - datetime.timedelta(days=15), "ultimo_ticket_id": 34, "pausa_motivo": None, "ativo": "S"},
                                    {"id": 5, "nome": "Limpeza Cron Periódica (Pausado)", "script_id": 3, "ambiente": "PRODUCAO", "usuario_id": 1, "prioridade": 2, "tipo_recorrencia": "CRON", "expressao_cron": "0 */4 * * *", "hora_execucao": None, "dias_semana": None, "dia_mes": None, "parametros_json": "{}", "data_inicio": base_dt - datetime.timedelta(days=2), "data_fim": None, "proxima_execucao": base_dt + datetime.timedelta(hours=4), "ultima_execucao": base_dt, "ultimo_ticket_id": 35, "pausa_motivo": "MANUAL", "ativo": "N"},
                                ]
                                agora_agd = recurrence.truncar_segundos(base_dt)
                                for a in agds:
                                    a["created_at"] = base_dt - datetime.timedelta(days=20)
                                    # Coerente com as regras (README §2.5, §7.2, §7.6): minuto exato, proxima pelo
                                    # recurrence e parametros_json com as respostas resolvidas completas.
                                    a["data_inicio"] = recurrence.truncar_segundos(a["data_inicio"])
                                    a["proxima_execucao"] = recurrence.proxima_execucao(a, agora_agd, 1461)
                                    _snap, resolvidos, _v = _compilar_seed(store, a["script_id"], agora_agd)
                                    respostas = dict(json.loads(a["parametros_json"]))
                                    for codigo, valor in resolvidos.items():
                                        respostas.setdefault(codigo, valor)
                                    a["parametros_json"] = _parametros_json(respostas)
                                    store.agendamentos[a["id"]] = a
                                store.seqs["tbsss_agendamentos"] = 5

                                # ---------------------------------------------------------
                                # 12. Tickets (40) e Respostas (tbsss_tickets, tbsss_ticket_resp)
                                # ---------------------------------------------------------
                                # 10 PENDING (1..10)
                                # 6 RUNNING (11..16)
                                # 12 SUCCESS (17..28)
                                # 8 FAILED (29..36)
                                # 4 CANCELLED (37..40)
                                compilados = {}
                                sensiveis_por_script = {}
                                for v in store.script_param.values():
                                    prm = store.parametros.get(v["parametro_id"])
                                    if prm and prm["sensivel"] == "S" and v.get("valor_padrao_sub"):
                                        sensiveis_por_script.setdefault(v["script_id"], []).append(
                                            (prm["codigo"], v["valor_padrao_sub"]))

                                for tid in range(1, 41):
                                    script_id = ((tid - 1) % 4) + 1  # rotaciona scripts 1..4
                                    scr = store.scripts[script_id]
                                    amb = "PRODUCAO" if tid % 2 == 1 else "HOMOLOGACAO"
                                    solicitante = "admin" if tid % 3 == 0 else ("op.prod" if tid % 2 == 1 else "op.hml")
                                    prio = ((tid - 1) % 4) + 1
                                    if prio == 1 and solicitante != "admin":
                                        prio = 2  # prioridade 1 e reservada a admin (README §5.3)

                                    # Status e motivos
                                    agente_id = None
                                    pid_proc = None
                                    pstart = None
                                    smotivo = None
                                    ret_code = None
                                    canc_req = "N"
                                    trunc = "N"
                                    started = None
                                    heartbeat = None
                                    finished = None
                                    log_out = ""

                                    if tid <= 10:
                                        status = "PENDING"
                                        sched = base_dt + datetime.timedelta(minutes=tid * 5)
                                        if tid == _TICKET_FILA_SEM_ATENDENTE:
                                            sched = base_dt - datetime.timedelta(minutes=3)
                                    elif tid <= 16:
                                        status = "RUNNING"
                                        sched = base_dt - datetime.timedelta(minutes=10)
                                        started = base_dt - datetime.timedelta(minutes=5)
                                        heartbeat = base_dt - datetime.timedelta(seconds=10)
                                        agente_id = "agt-host01" if tid % 2 == 1 else "agt-host02"
                                        if tid != _TICKET_SEM_PID:
                                            pid_proc = 2000 + tid
                                            pstart = 1700000000 + tid
                                            log_out = "[%s] Script %s iniciado em %s.\nEtapa 1 concluida com sucesso.\n" % (
                                                str(started), scr["nome"], amb
                                            )
                                            store.log_sim[tid] = {
                                                "passo_s": _PASSO_LOG_S[tid],
                                                "emitidos": 0,
                                                "sensiveis": list(sensiveis_por_script.get(script_id, [])),
                                            }
                                    elif tid <= 28:
                                        status = "SUCCESS"
                                        smotivo = "EXIT_OK"
                                        ret_code = 0
                                        sched = base_dt - datetime.timedelta(hours=tid)
                                        started = sched + datetime.timedelta(minutes=1)
                                        heartbeat = started + datetime.timedelta(minutes=4)
                                        finished = started + datetime.timedelta(minutes=5)
                                        agente_id = "agt-host01"
                                        pid_proc = 3000 + tid
                                        pstart = 1700000000 + tid
                                        log_out = "[%s] Script concluido com retorno 0.\n" % str(finished)
                                        if tid == _TICKET_LOG_VOLUMOSO:
                                            log_out = _log_volumoso(started) + log_out
                                    elif tid <= 36:
                                        status = "FAILED"
                                        sched = base_dt - datetime.timedelta(hours=tid * 2)
                                        started = sched + datetime.timedelta(minutes=1)
                                        finished = started + datetime.timedelta(minutes=2)
                                        agente_id = "agt-host01" if tid % 2 == 0 else "agt-host02"
                                        pid_proc = 4000 + tid
                                        pstart = 1700000000 + tid

                                        falhas_map = {
                                            29: ("EXIT_ERROR", 1),
                                            30: ("TIMEOUT", -3),
                                            31: ("NODE_OFFLINE", -2),
                                            32: ("PRECHECK_FAILED", -4),
                                            33: ("KILLED_SIGNAL", 137),
                                            34: ("SPAWN_ERROR", -4),
                                            35: ("LOG_LIMIT", -5),
                                            36: ("SHUTDOWN", -6),
                                        }
                                        smotivo, ret_code = falhas_map.get(tid, ("EXIT_ERROR", 1))
                                        if smotivo == "LOG_LIMIT":
                                            trunc = "S"
                                        log_out = "[%s] Falha na execucao: %s (code=%s)\n" % (
                                            str(finished), smotivo, ret_code
                                        )
                                        if trunc == "S":
                                            log_out += MARCADOR_TRUNCADO
                                    else:
                                        status = "CANCELLED"
                                        smotivo = "CANCEL_USER"
                                        ret_code = -1
                                        canc_req = "S"
                                        sched = base_dt - datetime.timedelta(hours=tid)
                                        finished = sched + datetime.timedelta(minutes=1)
                                        log_out = "Cancelado pelo usuario antes ou durante o processamento.\n"

                                    parent_id = None
                                    if tid == 25:
                                        parent_id = 17
                                    elif tid == 26:
                                        parent_id = 18

                                    agd_id = None
                                    if tid in (31, 32, 33, 34, 35):
                                        agd_id = tid - 30

                                    # Snapshot v3 e respostas compilados de verdade (README §6.5, §2.5).
                                    if script_id not in compilados:
                                        compilados[script_id] = _compilar_seed(
                                            store, script_id, base_dt - datetime.timedelta(minutes=30))
                                    snapshot_json, resolvidos, vinc_scr = compilados[script_id]

                                    t_obj = {
                                        "id": tid,
                                        "script_id": scr["id"],
                                        "ambiente": amb,
                                        "solicitante": solicitante,
                                        "ip_origem": "127.0.0.1",
                                        "agente_id": agente_id,
                                        "process_id": pid_proc,
                                        "process_start": pstart,
                                        "status": status,
                                        "prioridade": prio,
                                        "cancel_requested": canc_req,
                                        "status_motivo": smotivo,
                                        "parent_ticket_id": parent_id,
                                        "agendamento_id": agd_id,
                                        "parametros_enviados": snapshot_json,
                                        "log_output": log_out,
                                        "log_truncado": trunc,
                                        "return_code": ret_code,
                                        "scheduled_at": sched,
                                        "started_at": started,
                                        "heartbeat_at": heartbeat,
                                        "finished_at": finished,
                                        # created_at nunca no futuro (README §2.5): o agendado foi pedido antes.
                                        "created_at": min(sched, base_dt - datetime.timedelta(minutes=tid)),
                                    }
                                    store.tickets[tid] = t_obj

                                    # Respostas resolvidas (tbsss_ticket_resp, README §5.4): None omitido, CHECKBOX em texto.
                                    for v in vinc_scr:
                                        valor = resolvidos.get(v["codigo"])
                                        if valor is None:
                                            continue
                                        rid = store.proximo_id("tbsss_ticket_resp")
                                        store.ticket_resp[rid] = {
                                            "id": rid,
                                            "ticket_id": tid,
                                            "parametro_id": v["parametro_id"],
                                            "valor_resposta": ("true" if valor else "false") if isinstance(valor, bool) else valor,
                                            "created_at": t_obj["created_at"],
                                        }

                                store.seqs["tbsss_tickets"] = 40

                                # ---------------------------------------------------------
                                # 13. Auditoria (30 linhas)
                                # ---------------------------------------------------------
                                acoes = [
                                    ("admin", "LOGIN_OK", "tbsss_usuarios", 1, "Login bem-sucedido via web"),
                                    ("op.prod", "LOGIN_OK", "tbsss_usuarios", 2, "Login bem-sucedido via web"),
                                    ("op.hml", "LOGIN_OK", "tbsss_usuarios", 3, "Login bem-sucedido via web"),
                                    ("consulta", "LOGIN_OK", "tbsss_usuarios", 4, "Login bem-sucedido via web"),
                                    ("bloqueado", "LOGIN_FALHA", "tbsss_usuarios", 6, "Tentativa de login com senha incorreta"),
                                    ("bloqueado", "LOGIN_BLOQUEIO", "tbsss_usuarios", 6, "Conta bloqueada apos atingir limite de falhas"),
                                    ("admin", "CAD_INSERIR", "tbsss_ambientes", 1, "Ambiente PRODUCAO cadastrado"),
                                    ("admin", "CAD_INSERIR", "tbsss_ambientes", 2, "Ambiente HOMOLOGACAO cadastrado"),
                                    ("admin", "CAD_INSERIR", "tbsss_ambientes", 3, "Ambiente DESENV cadastrado"),
                                    ("admin", "CAD_DESATIVAR", "tbsss_ambientes", 3, "Ambiente DESENV desativado"),
                                    ("admin", "CAD_INSERIR", "tbsss_perfis", 1, "Perfil ADMINISTRADOR cadastrado"),
                                    ("admin", "CAD_INSERIR", "tbsss_perfis", 2, "Perfil OPERADOR_PROD cadastrado"),
                                    ("admin", "PERM_ALTERAR", "tbsss_perfis", 2, "Matriz de permissoes atualizada: +EXEC_SCRIPT, +VER_LOGS"),
                                    ("admin", "CAD_INSERIR", "tbsss_scripts", 1, "Script carga_diaria cadastrado"),
                                    ("admin", "CAD_INSERIR", "tbsss_scripts", 2, "Script relatorio_mensal cadastrado"),
                                    ("admin", "CAD_INSERIR", "tbsss_scripts", 3, "Script cleanup_tmp cadastrado"),
                                    ("admin", "CAD_INSERIR", "tbsss_parametros", 1, "Parametro data_ref cadastrado"),
                                    ("admin", "CAD_INSERIR", "tbsss_parametros", 2, "Parametro limite_linhas cadastrado"),
                                    ("admin", "CAD_ALTERAR", "tbsss_parametros", 2, "Valor padrao atualizado para 1000"),
                                    ("admin", "CAD_INSERIR", "tbsss_agendamentos", 1, "Regra Execucao Avulsa Carga cadastrada"),
                                    ("admin", "CAD_INSERIR", "tbsss_agendamentos", 5, "Regra Limpeza Cron Periodica cadastrada"),
                                    ("admin", "AGD_PAUSAR", "tbsss_agendamentos", 5, "Agendamento pausado manualmente"),
                                    ("op.prod", "TICKET_CRIAR", "tbsss_tickets", 1, "Ticket criado para carga_diaria em PRODUCAO"),
                                    ("op.hml", "TICKET_CRIAR", "tbsss_tickets", 2, "Ticket criado para relatorio_mensal em HOMOLOGACAO"),
                                    ("op.prod", "TICKET_CRIAR", "tbsss_tickets", 11, "Ticket criado para carga_diaria em PRODUCAO"),
                                    ("admin", "TICKET_CANCELAR", "tbsss_tickets", 37, "Cancelamento solicitado para ticket 37"),
                                    ("admin", "TICKET_CANCELAR", "tbsss_tickets", 38, "Cancelamento solicitado para ticket 38"),
                                    ("SYSTEM:agt-host01", "AGENTE_INICIO", "tbsss_agentes", 1, "Agente agt-host01 iniciado no host worker01.internal"),
                                    ("SYSTEM:agt-host02", "AGENTE_INICIO", "tbsss_agentes", 2, "Agente agt-host02 iniciado no host worker02.internal"),
                                    ("admin", "CAD_ALTERAR", "tbsss_usuarios", 6, "Conta desbloqueada pelo administrador"),
                                ]
                                for i, (ator, acao, ent, ent_id, det) in enumerate(acoes, 1):
                                    store.auditoria[i] = {
                                        "id": i,
                                        "ator": ator,
                                        "ip_origem": "127.0.0.1",
                                        "acao": acao,
                                        "entidade": ent,
                                        "entidade_id": ent_id,
                                        "detalhe": det,
                                        "created_at": base_dt - datetime.timedelta(hours=35 - i),
                                    }
                                store.seqs["tbsss_auditoria"] = 30

                                _carimbar_registro(store, base_dt)

                                # Controle (tabela 17, CR-007 D4): o FAKE nasce na versao do esquema do codigo.
                                store.controle[1] = {"id": 1, "versao_esquema": sql_ident.VERSAO_ESQUEMA,
                                                     "versao_aplicada_em": base_dt - datetime.timedelta(days=90),
                                                     "versao_aplicada_por": "SYSTEM:seed", "purge_dono": None,
                                                     "purge_concessao_ate": None}
                                store.seqs["tbsss_controle"] = 1
