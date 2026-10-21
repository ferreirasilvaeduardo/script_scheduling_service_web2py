# -*- coding: utf-8 -*-
"""Pacote de migracoes versionadas de esquema Oracle do SSS (CR-007, D4).

Contrato de cada modulo scripts/migrations/m<NNNN>_<descricao>.py:
- Constante inteira: VERSAO = N
- Funcao de execucao: aplicar(conn, nomes, log)
Onde:
  conn: conexao ativa aberta com o dono do esquema
  nomes: dicionario de identificadores expandidos sql_ident.nomes(prefixo)
  log: callable para registro de mensagens
"""
