# -*- coding: utf-8 -*-
"""Pacote de migracoes versionadas de esquema Oracle do SSS (CR-007, D4).

Contrato de cada modulo src/sss/cli/migrations/m<NNNN>_<descricao>.py (CR-022b8; antes scripts/migrations/):
- Constante inteira: VERSAO = N
- Funcao de execucao: aplicar(conn, nomes, log)
Onde:
  conn: conexao ativa aberta com o dono do esquema
  nomes: dicionario de identificadores expandidos sql_ident.names(prefixo)
  log: callable para registro de mensagens
"""
