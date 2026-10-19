# -*- coding: utf-8 -*-
"""Construtor puro de DDL e seed Oracle 11gR2 a partir de sql_ident (F7.1).

Gera instrucoes DDL fase a fase, sem importar drivers Oracle nem depender do web2py.
Totalmente idempotente e aderente ao README §9, §10, §11.1 e AGENTS §4.
"""
import collections

import sql_ident

# Estrutura representativa de uma instrucao DDL
ItemDDL = collections.namedtuple("ItemDDL", [
    "fase", "tipo", "nome", "sql", "entidade"
])

# Catalogo canonico de funcionalidades (README §4.3.D)
# Tuplas: (modulo, codigo, nome_exibicao, finalidade)
CATALOGO_FUNCIONALIDADES = (
    ("OPERACAO", "EXEC_SCRIPT", "Disparar Scripts", "Preencher questionários e abrir tickets"),
    ("OPERACAO", "VER_LOGS", "Consultar Logs", "Visualizar logs e histórico em tempo quase real"),
    ("OPERACAO", "CANC_TICKET", "Cancelar Tickets", "Cancelar tickets de terceiros em ambientes autorizados"),
    ("ADMIN", "CAD_USUARIOS", "Gestão de Usuários", "Gerenciar operadores e credenciais"),
    ("ADMIN", "CAD_PERFIS", "Gestão de Perfis", "Gerenciar perfis e matrizes de permissão"),
    ("ADMIN", "CAD_AMBIENTES", "Gestão de Ambientes", "Gerenciar ambientes e DSNs"),
    ("ADMIN", "CAD_SCRIPTS", "Gestão de Scripts", "Cadastrar rotinas e homologação por ambiente"),
    ("ADMIN", "CAD_PARAMETROS", "Dicionário de Parâmetros", "Gerenciar perguntas e flags reutilizáveis"),
    ("ADMIN", "CAD_AGENDAMENTOS", "Regras de Agendamento", "Criar e gerenciar recorrências"),
    ("ADMIN", "VER_AUDITORIA", "Auditoria", "Consultar a trilha de auditoria e os agentes"),
)


def _formatar_coluna(col_nome, col_info):
    """Formata a declaracao de uma coluna em CREATE TABLE."""
    partes = [col_nome, col_info["tipo"]]
    if col_info.get("default") is not None:
        partes.append("DEFAULT {}".format(col_info["default"]))
    if col_info.get("not_null"):
        partes.append("NOT NULL")
    return "    {}".format(" ".join(partes))


def gerar_instrucoes_ddl(owner, prefixo, lob_storage="SECUREFILE"):
    """Gera todas as instrucoes DDL em ordem estrita de fases (README §11.1).

    Fases:
      1. Sequences (sq_*)
      2. Tabelas sem FK (com LOB configurado)
      3. PK, UK e CK
      4. FKs
      5. Indices (incluindo FBIs e UNIQUE FBIs)
      6. Triggers (_bi e _bu de imutabilidade)

    Retorna lista de ItemDDL(fase, tipo, nome, sql, entidade).
    """
    sql_ident.validar_owner(owner)
    sql_ident.validar_prefixo(prefixo)
    esquema = sql_ident.nomes(prefixo)
    instrucoes = []

    # -------------------------------------------------------------------------
    # FASE 1: Sequences
    # -------------------------------------------------------------------------
    for entidade, t in esquema.items():
        seq_nome = t["sequence"]
        sql = "CREATE SEQUENCE {}.{} START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE".format(
            owner, seq_nome
        )
        instrucoes.append(ItemDDL(1, "SEQUENCE", seq_nome, sql, entidade))

    # -------------------------------------------------------------------------
    # FASE 2: Tabelas
    # -------------------------------------------------------------------------
    for entidade, t in esquema.items():
        tabela_nome = t["tabela"]
        linhas_cols = [_formatar_coluna(c_nome, c_info) for c_nome, c_info in t["colunas"].items()]
        corpo = ",\n".join(linhas_cols)

        # Clausula LOB
        colunas_lob = t.get("colunas_lob", ())
        clausula_lob = ""
        if colunas_lob:
            lobs_str = ", ".join(colunas_lob)
            if lob_storage == "BASICFILE":
                clausula_lob = "\nLOB ({}) STORE AS BASICFILE".format(lobs_str)
            else:
                clausula_lob = "\nLOB ({}) STORE AS SECUREFILE (CACHE)".format(lobs_str)

        sql = "CREATE TABLE {}.{} (\n{}{}\n)".format(owner, tabela_nome, corpo, clausula_lob)
        instrucoes.append(ItemDDL(2, "TABLE", tabela_nome, sql, entidade))

    # -------------------------------------------------------------------------
    # FASE 3: Constraints (PK, UK, CK)
    # -------------------------------------------------------------------------
    for entidade, t in esquema.items():
        tabela_nome = t["tabela"]

        # PK
        pk_nome = t["pk"]
        colunas_pk = ", ".join(sql_ident.TABELAS[entidade]["pk"]["colunas"])
        sql_pk = "ALTER TABLE {}.{} ADD CONSTRAINT {} PRIMARY KEY ({})".format(
            owner, tabela_nome, pk_nome, colunas_pk
        )
        instrucoes.append(ItemDDL(3, "CONSTRAINT", pk_nome, sql_pk, entidade))

        # UKs
        for uk_nome, uk_def in t["uks"].items():
            colunas_uk = ", ".join(uk_def["colunas"])
            sql_uk = "ALTER TABLE {}.{} ADD CONSTRAINT {} UNIQUE ({})".format(
                owner, tabela_nome, uk_nome, colunas_uk
            )
            instrucoes.append(ItemDDL(3, "CONSTRAINT", uk_nome, sql_uk, entidade))

        # CKs
        for ck_nome, ck_def in t["cks"].items():
            expr_ck = ck_def["expr"]
            sql_ck = "ALTER TABLE {}.{} ADD CONSTRAINT {} CHECK ({})".format(
                owner, tabela_nome, ck_nome, expr_ck
            )
            instrucoes.append(ItemDDL(3, "CONSTRAINT", ck_nome, sql_ck, entidade))

    # -------------------------------------------------------------------------
    # FASE 4: Constraints (FK)
    # -------------------------------------------------------------------------
    for entidade, t in esquema.items():
        tabela_nome = t["tabela"]
        for fk_nome, fk_def in t["fks"].items():
            cols_fk = ", ".join(fk_def["colunas"])
            ref_tabela = fk_def["ref_tabela"]
            ref_cols = ", ".join(fk_def["ref_colunas"])
            on_del = " ON DELETE {}".format(fk_def["on_delete"]) if fk_def.get("on_delete") else ""
            sql_fk = "ALTER TABLE {}.{} ADD CONSTRAINT {} FOREIGN KEY ({}) REFERENCES {}.{} ({}){}".format(
                owner, tabela_nome, fk_nome, cols_fk, owner, ref_tabela, ref_cols, on_del
            )
            instrucoes.append(ItemDDL(4, "CONSTRAINT", fk_nome, sql_fk, entidade))

    # -------------------------------------------------------------------------
    # FASE 5: Indices
    # -------------------------------------------------------------------------
    for entidade, t in esquema.items():
        tabela_nome = t["tabela"]
        for ix_nome, ix_def in t["indices"].items():
            is_fbi = ix_def.get("fbi", False)
            is_unico = ix_def.get("unico", False)

            if is_fbi:
                expr = ix_def["expr"]
                if is_unico:
                    sql_ix = "CREATE UNIQUE INDEX {}.{} ON {}.{} {}".format(
                        owner, ix_nome, owner, tabela_nome, expr
                    )
                else:
                    sql_ix = "CREATE INDEX {}.{} ON {}.{} {}".format(
                        owner, ix_nome, owner, tabela_nome, expr
                    )
            else:
                cols_ix = ", ".join(ix_def["colunas"])
                sql_ix = "CREATE INDEX {}.{} ON {}.{} ({})".format(
                    owner, ix_nome, owner, tabela_nome, cols_ix
                )

            instrucoes.append(ItemDDL(5, "INDEX", ix_nome, sql_ix, entidade))

    # -------------------------------------------------------------------------
    # FASE 6: Triggers (_bi e _bu)
    # -------------------------------------------------------------------------
    for entidade, t in esquema.items():
        tabela_nome = t["tabela"]
        seq_nome = t["sequence"]
        tr_bi_nome = t["trigger_bi"]

        # Trigger BEFORE INSERT condicional (template literal AGENTS §4.2)
        sql_tr_bi = (
            "CREATE OR REPLACE TRIGGER {owner}.{trigger_name}\n"
            "BEFORE INSERT ON {owner}.{table_name}\n"
            "FOR EACH ROW\n"
            "BEGIN\n"
            "    IF :NEW.id IS NULL THEN\n"
            "        SELECT {owner}.{sequence_name}.NEXTVAL INTO :NEW.id FROM DUAL;\n"
            "    END IF;\n"
            "END;"
        ).format(
            owner=owner,
            trigger_name=tr_bi_nome,
            table_name=tabela_nome,
            sequence_name=seq_nome,
        )
        instrucoes.append(ItemDDL(6, "TRIGGER", tr_bi_nome, sql_tr_bi, entidade))

        # Trigger BEFORE UPDATE imutavel (quando configurada)
        if t.get("trigger_bu") and t.get("trigger_extra"):
            tr_bu_nome = t["trigger_bu"]
            col_imutavel = t["trigger_extra"]["coluna_imutavel"]
            sql_tr_bu = (
                "CREATE OR REPLACE TRIGGER {owner}.{trigger_name}\n"
                "BEFORE UPDATE ON {owner}.{table_name}\n"
                "FOR EACH ROW\n"
                "BEGIN\n"
                "    IF :NEW.{coluna} <> :OLD.{coluna} THEN\n"
                "        RAISE_APPLICATION_ERROR(-20001, '{coluna} é imutável');\n"
                "    END IF;\n"
                "END;"
            ).format(
                owner=owner,
                trigger_name=tr_bu_nome,
                table_name=tabela_nome,
                coluna=col_imutavel,
            )
            instrucoes.append(ItemDDL(6, "TRIGGER", tr_bu_nome, sql_tr_bu, entidade))

    return instrucoes


def gerar_script_ddl(owner, prefixo, lob_storage="SECUREFILE"):
    """Gera script SQL completo pronto para visualizacao ou execucao via cliente."""
    instrucoes = gerar_instrucoes_ddl(owner, prefixo, lob_storage=lob_storage)
    fases_titulos = {
        1: "FASE 1: SEQUENCES",
        2: "FASE 2: TABELAS",
        3: "FASE 3: CONSTRAINTS (PK, UK, CK)",
        4: "FASE 4: CONSTRAINTS (FK)",
        5: "FASE 5: INDICES",
        6: "FASE 6: TRIGGERS",
    }

    linhas = [
        "-- ==============================================================================",
        "-- Script Scheduling Service (SSS) - DDL Oracle 11gR2",
        "-- Gerado automaticamente a partir do registro sql_ident.py (F7.1)",
        "-- Owner: {}".format(owner),
        "-- Prefixo: {}".format(prefixo),
        "-- LOB Storage: {}".format(lob_storage),
        "-- ==============================================================================",
        "",
    ]

    fase_atual = None
    for item in instrucoes:
        if item.fase != fase_atual:
            fase_atual = item.fase
            linhas.extend([
                "-- ------------------------------------------------------------------------------",
                "-- {}".format(fases_titulos.get(fase_atual, "FASE %d" % fase_atual)),
                "-- ------------------------------------------------------------------------------",
                "",
            ])

        if item.tipo == "TRIGGER":
            linhas.append(item.sql)
            linhas.append("/")
            linhas.append("")
        else:
            linhas.append(item.sql + ";")
            linhas.append("")

    return "\n".join(linhas)


def gerar_grants_por_papel(owner, prefixo, papeis_usuarios):
    """Gera comandos GRANT para os usuarios informados por papel (README §11.1).

    papeis_usuarios: dict com mapeamento papel -> usuario_oracle, ex:
      {'web': 'sss_web', 'agente': 'sss_agente', 'purge': 'sss_purge', 'monitor': 'sss_monitor'}
    """
    sql_ident.validar_owner(owner)
    sql_ident.validar_prefixo(prefixo)
    esquema = sql_ident.nomes(prefixo)
    comandos = []

    # 1. PAPEL: web
    usr_web = papeis_usuarios.get("web")
    if usr_web:
        cadastros_e_agendamentos = (
            "ambientes", "perfis", "funcionalidades", "scripts",
            "usuarios", "parametros", "agendamentos"
        )
        for ent in cadastros_e_agendamentos:
            comandos.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
                owner, esquema[ent]["tabela"], usr_web
            ))

        associacoes = (
            "perfil_func", "perfil_amb", "perfil_scr", "script_amb", "script_param"
        )
        for ent in associacoes:
            comandos.append("GRANT SELECT, INSERT, UPDATE, DELETE ON {}.{} TO {};".format(
                owner, esquema[ent]["tabela"], usr_web
            ))

        comandos.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
            owner, esquema["tickets"]["tabela"], usr_web
        ))
        comandos.append("GRANT SELECT, INSERT ON {}.{} TO {};".format(
            owner, esquema["ticket_resp"]["tabela"], usr_web
        ))
        comandos.append("GRANT SELECT, INSERT ON {}.{} TO {};".format(
            owner, esquema["auditoria"]["tabela"], usr_web
        ))
        comandos.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, esquema["agentes"]["tabela"], usr_web
        ))
        comandos.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, esquema["controle"]["tabela"], usr_web
        ))

        # Sequences para web (todas exceto agentes e controle)
        for ent, t in esquema.items():
            if ent not in ("agentes", "controle"):
                comandos.append("GRANT SELECT ON {}.{} TO {};".format(
                    owner, t["sequence"], usr_web
                ))

    # 2. PAPEL: agente
    usr_agt = papeis_usuarios.get("agente")
    if usr_agt:
        cadastros_e_assoc = (
            "ambientes", "perfis", "funcionalidades", "perfil_func", "perfil_amb",
            "scripts", "perfil_scr", "script_amb", "usuarios", "parametros", "script_param"
        )
        for ent in cadastros_e_assoc:
            comandos.append("GRANT SELECT ON {}.{} TO {};".format(
                owner, esquema[ent]["tabela"], usr_agt
            ))

        comandos.append("GRANT SELECT, UPDATE ON {}.{} TO {};".format(
            owner, esquema["agendamentos"]["tabela"], usr_agt
        ))
        comandos.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
            owner, esquema["tickets"]["tabela"], usr_agt
        ))
        comandos.append("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {};".format(
            owner, esquema["agentes"]["tabela"], usr_agt
        ))
        comandos.append("GRANT SELECT, INSERT ON {}.{} TO {};".format(
            owner, esquema["ticket_resp"]["tabela"], usr_agt
        ))
        comandos.append("GRANT INSERT ON {}.{} TO {};".format(
            owner, esquema["auditoria"]["tabela"], usr_agt
        ))
        comandos.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, esquema["controle"]["tabela"], usr_agt
        ))

        # Sequences do agente: tickets, respostas, agentes e auditoria
        for ent in ("tickets", "ticket_resp", "agentes", "auditoria"):
            comandos.append("GRANT SELECT ON {}.{} TO {};".format(
                owner, esquema[ent]["sequence"], usr_agt
            ))

    # 3. PAPEL: purge
    usr_purge = papeis_usuarios.get("purge")
    if usr_purge:
        comandos.append("GRANT SELECT, DELETE ON {}.{} TO {};".format(
            owner, esquema["tickets"]["tabela"], usr_purge
        ))
        comandos.append("GRANT SELECT, INSERT, DELETE ON {}.{} TO {};".format(
            owner, esquema["auditoria"]["tabela"], usr_purge
        ))
        comandos.append("GRANT SELECT, UPDATE (purge_dono, purge_concessao_ate) ON {}.{} TO {};".format(
            owner, esquema["controle"]["tabela"], usr_purge
        ))
        comandos.append("GRANT SELECT ON {}.{} TO {};".format(
            owner, esquema["auditoria"]["sequence"], usr_purge
        ))

    # 4. PAPEL: monitor (CR-008, E3/R-04)
    # Somente SELECT nas 7 tabelas que saude.py consulta, zero sequences
    usr_mon = papeis_usuarios.get("monitor")
    if usr_mon:
        tabelas_monitor = (
            "agentes", "tickets", "agendamentos", "scripts",
            "ambientes", "controle", "auditoria"
        )
        for ent in tabelas_monitor:
            comandos.append("GRANT SELECT ON {}.{} TO {};".format(
                owner, esquema[ent]["tabela"], usr_mon
            ))

    return comandos
