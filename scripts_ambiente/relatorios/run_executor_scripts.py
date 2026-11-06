#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v.1.0.0.0011 (Compatível com Python 3.6+)

Executa scripts SQL, PL/SQL ou Python com parâmetros configuráveis. SQL e PL/SQL
podem usar SQL*Plus ou a biblioteca Python (oracledb/cx_Oracle); scripts .py são
carregados como módulos e devem expor main(configuracoes_dados, logger). Consultas
e DBMS_OUTPUT podem gerar arquivos de saída, opcionalmente compactados em ZIP.
"""
import argparse  # parsing dos argumentos de linha de comando (--tags, --help)
import csv  # escrita do CSV exportado quando a execução usa driver Python
import logging  # geração de logs em arquivo e console
import os  # leitura de variáveis de ambiente e operações de caminho
import re  # expressões regulares para tags, credenciais e validações
import shutil  # cópia de arquivos (script original e arquivos de controle)
import subprocess  # execução do sqlplus como processo externo
import sys  # acesso a argv, path de módulos e stdout/stderr
import traceback  # formatação do stack trace em falhas não tratadas
import uuid  # geração do identificador único de execução e sufixo aleatório
import zipfile  # compactação do arquivo exportado em ZIP
from copy import deepcopy  # cópia independente da lista de arquivos de controle
from datetime import datetime  # timestamps de início de execução e do arquivo exportado
from pathlib import Path  # manipulação orientada a objetos de caminhos de arquivo
from typing import List, Optional, Pattern, Tuple, Any  # anotações de tipo usadas nas assinaturas

AJUDA_DESCRICAO = """\
Executa SQL/PLSQL pelo SQL*Plus ou por driver Python e carrega módulos .py que
exponham main(configuracoes_dados, logger). Resultados SQL/PLSQL, quando gerados,
podem ser divididos em partes e compactados em ZIP.

Uso: ./%(prog)s.py [-h] [--tipo_controle {TERMINAL,INPUT,CONFIG}] [--nome_arquivo_entrada NOME_ARQUIVO_ENTRADA] [--tags CHAVE=VALOR [CHAVE=VALOR ...]]
                            
Modos de Operação:
    1. Direto (CLI): exige ao menos uma --tags e combina tags com variáveis de ambiente.
    2. Lote (arquivo): lê arquivos de controle encontrados pelo prefixo configurado.

Tags:
    --tags CHAVE="VALOR" outra_chave="outro_valor"  # define várias tags em uma ocorrência
Tags podem ser usadas para parametrizar a execução do script. A opção --tags também pode ser repetida.
Exemplo com várias tags em uma única ocorrência:
    --tags trscript="consulta.sql" trcx="usuario/senha@host/servico" trtpex="SQL" data_ini="2026-01-01" data_fim="2026-01-31"
    
Tags reservadas:
 - > trcx : credenciais de conexão no formato (usuario/senha@host/servico).
 - > trscript : nome do arquivo SQL/PLSQL a ser executado (ex: consulta.sql).
 - > trdirscript : diretório onde o script está localizado (ex: /caminho/para/scripts).
 - > trrel : nome do relatório de saida (ex: relatorio.csv).
 - > trdirrel : diretório do relatório de saida (ex: /caminho/para/relatorios)
 - > trst : indica se as tags são estritamente necessárias para a execução (S/N) (ex: S)
 - > trzip : indica se o resultado deve ser compactado em ZIP (S/N) (ex: S)
 - > trkp : indica se o arquivo compactado deve ser mantido (S/N) (ex: S)
 - > trdl : delimitador usado para os relatórios de saída (ex: ;).
 - > trtpex : tipo de execução (ex: SQL, PLSQL).
 - > trfertpex : tipo de ferramenta usada para a execução do script (ex: PYTHON, SQLPLUS ).
 - > trnlsl : idioma/nls usado na execução do script (ex: AMERICAN_AMERICA.AL32UTF8)
 - > trql : quantidade de linhas para quebra do arquivo de saída/relatório. Exemplo: 1000
 - > troraclilib : diretório das bibliotecas do cliente Oracle . Exemplo: /caminho/para/oracle/client/lib

Variáveis de Ambiente: Utilizadas pelo script para determinar valores default/padrão.
    PADRAO_VALOR_RUN_TIPO_CONTROLE                                 # PADRÃO de VALOR Principal : tipo de controle usado para execução em lote (ex: INPUT, CONFIG)
    PADRAO_VALOR_RUN_TEMPO_TIMEOUT_CONEXAO_DADOS_EXPORTACAO        # PADRÃO de VALOR Principal : segundos de timeout ao validar a conexão via sqlplus
    PADRAO_VALOR_RUN_ESPACO_MINIMO_MB_DADOS_EXPORTACAO             # PADRÃO de VALOR Principal : espaço mínimo (MB) sugerido, não validado automaticamente
    PADRAO_VALOR_RUN_TAMANHO_LOTE_FETCH_DADOS_EXPORTACAO           # PADRÃO de VALOR Principal : tamanho do lote usado em fetchmany/arraysize/DBMS_OUTPUT
    PADRAO_VALOR_RUN_BD_CONN_FILE                                  # PADRÃO de VALOR Principal : arquivo de conexão com o banco de dados
    PADRAO_VALOR_RUN_DELIMITADOR                                   # PADRÃO de VALOR Principal : delimitador usado nos arquivos de controle em lote
    PADRAO_VALOR_RUN_TIPO_EXECUCAO_SCRIPT                          # PADRÃO de VALOR Principal : tipo de execução do script (ex: SQL, PLSQL)
    PADRAO_VALOR_RUN_FERRAMENTA_TIPO_EXECUCAO_SCRIPT               # PADRÃO de VALOR Principal : ferramenta usada para a execução do script (ex: PYTHON, SQLPLUS)
    PADRAO_VALOR_RUN_TAGS_ESTRICTAS                                # PADRÃO de VALOR Principal : indica se apenas as tags definidas devem ser aceitas (S/N)
    PADRAO_VALOR_RUN_COMPACTAR_ARQUIVO_DADOS_EXPORTACAO            # PADRÃO de VALOR Principal : indica se os arquivos de dados exportados devem ser compactados (S/N)
    PADRAO_VALOR_RUN_MANTER_ORIGINAL                               # PADRÃO de VALOR Principal : indica se os arquivos originais devem ser mantidos após a compactação (S/N)
    PADRAO_VALOR_RUN_IDIOMA_NLS                                    # PADRÃO de VALOR Principal : define o idioma/nls para a execução do script (ex: AMERICAN_AMERICA.AL32UTF8)
    PADRAO_VALOR_RUN_QUANTIDADE_LINHAS_QUEBRA_ARQUIVO              # PADRÃO de VALOR Principal : quantidade de linhas após a qual o arquivo deve ser quebrado
    PADRAO_VALOR_RUN_ORACLE_CLIENT_LIB_DIR                         # PADRÃO de VALOR Principal : diretório das bibliotecas do cliente Oracle
    PADRAO_VALOR_RUN_NIVEL_LOG                                     # PADRÃO de VALOR Principal : nível de log a ser usado na execução (ex: DEBUG, INFO, WARNING, ERROR)
    PADRAO_VALOR_RUN_ID_EXECUCAO                                   # PADRÃO de VALOR Principal : identificador único da execução
    PADRAO_VALOR_RUN_FLAG_INDICADOR_RAIZ_SCRIPT                    # PADRÃO de VALOR Principal : indica se o script está localizado no diretório raiz dos scripts (S/N)
    PADRAO_VALOR_RUN_DIRETORIO_SCRIPT                              # PADRÃO de VALOR Principal : diretório onde os scripts estão localizados
    PADRAO_VALOR_RUN_NOME_ARQUIVO_SCRIPT                           # PADRÃO de VALOR Principal : nome do arquivo de script a ser executado
    PADRAO_VALOR_RUN_DIRETORIO_SAIDA                               # PADRÃO de VALOR Principal : diretório onde os arquivos de saída serão armazenados
    PADRAO_VALOR_RUN_DIRETORIO_SAIDA_RELATORIO                     # PADRÃO de VALOR Principal : diretório onde os relatórios de saída serão armazenados
    PADRAO_VALOR_RUN_NOME_ARQUIVO_RELATORIO                        # PADRÃO de VALOR Principal : nome do arquivo de relatório a ser gerado
    PADRAO_VALOR_RUN_DIRETORIO_LOG                                 # PADRÃO de VALOR Principal : diretório onde os arquivos de log serão armazenados
    PADRAO_VALOR_RUN_NOME_ARQUIVO_LOG                              # PADRÃO de VALOR Principal : nome do arquivo de log a ser gerado
    PADRAO_VALOR_RUN_DIRETORIO_ENTRADA                             # PADRÃO de VALOR Principal : diretório onde os arquivos de entrada estão localizados
    PADRAO_VALOR_RUN_NOME_ARQUIVO_ENTRADA                          # PADRÃO de VALOR Principal : nome do arquivo de entrada a ser processado
    PADRAO_VALOR_RUN_CONEXAO_BD                                    # PADRÃO de VALOR Principal : string de conexão com o banco de dados (ex: "usuario/senha@host/servico")
"""
AJUDA_EXEMPLOS = """\
Exemplos de Uso:

1 ) caso de teste com sucesso testando via terminal com sqlplus
python3 ./%(prog)s.py --tags trscript="exemplo_consulta.sql" b="b" a="1"
python3 ./%(prog)s.py --tags trscript="exemplo_plsql.sql" trtpex="PLSQL" b="b" a="1"
2 ) caso de teste com sucesso testando via terminal com acionando via python customizado
python3 ./%(prog)s.py --tags trscript="exemplo_script.py"
3 ) caso de teste com sucesso testando via terminal com acionando via python, executando a consulta
python3 ./%(prog)s.py --tags trscript="exemplo_consulta.sql" trfertpex="PY" trtpex="SQL" trdl=";" b="b" a="1"
python3 ./%(prog)s.py --tags trscript="exemplo_plsql.sql" trfertpex="PY" trtpex="PLSQL" trdl=";" b="b" a="1"
4 ) caso de testes acionando pipeline 1 arquivo em config python customizado
python3 ./%(prog)s.py --tipo_controle="CONFIG" --nome_arquivo_entrada="PIPELINE_EXEMPLO_A_REL_JAMES_WEB.config"
5 ) caso de testes acionando pipeline 2 arquivo em entrada/input
python3 ./%(prog)s.py --tipo_controle="INPUT" --nome_arquivo_entrada="PIPELINE_EXEMPLO_A_000"

"""

PADRAO_ERRO_ORACLE_DADOS_EXPORTACAO: Pattern[str] = re.compile(r"(^|\s)(ORA-|SP2-|PLS-)\d+")  # detecta mensagens de erro do Oracle/SQL*Plus na saída capturada
PADRAO_CREDENCIAL_DADOS_EXPORTACAO: Pattern[str] = re.compile(r"(?i)\b([a-z0-9_\-\.]+)/([^@\s]+)@", re.MULTILINE)  # localiza "usuario/senha@" para mascarar em logs
PADRAO_TAG_DADOS_EXPORTACAO: Pattern[str] = re.compile(r"\[([A-Za-z_][A-Za-z0-9_]*)\]")  # localiza tags no formato [NOME] dentro do script
TEMPO_TIMEOUT_CONEXAO_DADOS_EXPORTACAO: int = int(os.getenv("PADRAO_VALOR_RUN_TEMPO_TIMEOUT_CONEXAO_DADOS_EXPORTACAO", 30))  # segundos de timeout ao validar a conexão via sqlplus
ESPACO_MINIMO_MB_DADOS_EXPORTACAO: int = int(os.getenv("PADRAO_VALOR_RUN_ESPACO_MINIMO_MB_DADOS_EXPORTACAO", 100))  # espaço mínimo (MB) sugerido, não validado automaticamente
TAMANHO_LOTE_FETCH_DADOS_EXPORTACAO: int = int(os.getenv("PADRAO_VALOR_RUN_TAMANHO_LOTE_FETCH_DADOS_EXPORTACAO", 15000))  # tamanho do lote usado em fetchmany/arraysize/DBMS_OUTPUT
NOME_LOGGER_DADOS_EXPORTACAO: str = Path(__file__).resolve().stem  # nome do logger derivado do nome do arquivo do script


class ArgumentParserTraduzido(argparse.ArgumentParser):
    def error(self, message):
        """Sobrescreve o método de erro padrão para fornecer mensagens traduzidas."""
        # Traduções comuns de erros do argparse
        traducoes = {
            "expected one argument": "esperava um valor obrigatório a seguir",
            "not allowed with argument": "não é permitido em conjunto com o parâmetro",
            "unrecognized arguments": "parâmetros não reconhecidos",
            "invalid choice": "valor inválido",
            "the following arguments are required": "os seguintes parâmetros são obrigatórios",
            "ambiguous option": "opção ambígua",
            "could match": "pode corresponder a",
            "argument": "parâmetro",
            "choose from": "escolha entre"
        }
        
        # Procura a mensagem em inglês e substitui pela portuguesa
        for en, pt in traducoes.items():
            if en in message:
                message = message.replace(en, pt)
        
        # Exibe a sintaxe de uso e a mensagem de erro traduzida
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: erro: {message}\n")


class Configuracoes:
    """Armazena o estado completo da rotina de dados_exportacao (compatível com Python 3.6)."""

    def __init__(self,
                 tipo_controle: str = str(os.getenv("PADRAO_VALOR_RUN_TIPO_CONTROLE") or "TERMINAL").strip().upper(),
                 nome_arquivo_entrada: str = str(os.getenv("PADRAO_VALOR_RUN_NOME_ARQUIVO_ENTRADA") or NOME_LOGGER_DADOS_EXPORTACAO).strip()) -> None:
        """Lê variáveis de ambiente, calcula caminhos derivados e cria os diretórios necessários."""
        self.nome_logger_dados_exportacao: str = NOME_LOGGER_DADOS_EXPORTACAO  # nome usado em logging.getLogger
        self.tempo_timeout_conexao_dados_exportacao: int = TEMPO_TIMEOUT_CONEXAO_DADOS_EXPORTACAO  # segundos de timeout ao validar a conexão via sqlplus
        self.tamanho_lote_fetch_dados_exportacao: int = TAMANHO_LOTE_FETCH_DADOS_EXPORTACAO # tamanho do lote usado em fetchmany/arraysize/DBMS_OUTPUT
        self.padrao_erro_oracle_dados_exportacao: Pattern[str] = PADRAO_ERRO_ORACLE_DADOS_EXPORTACAO  # detecta mensagens de erro do Oracle/SQL*Plus na saída capturada
        self.padrao_credencial_dados_exportacao: Pattern[str] = PADRAO_CREDENCIAL_DADOS_EXPORTACAO  # localiza "usuario/senha@" para mascarar em logs
        self.padrao_tag_dados_exportacao: Pattern[str] = PADRAO_TAG_DADOS_EXPORTACAO  # localiza tags no formato [NOME] dentro do script
        self.nivel_log: int = logging.DEBUG  # nível padrão; pode ser sobrescrito por NIVEL_LOG abaixo
        self.pasta_script: Path = Path(__file__).resolve().parent  # diretório onde este arquivo .py está localizado
        self.raiz_script_inicial: Path = Path(__file__).resolve().parent.parent  # raiz do projeto (um nível acima da pasta do script)
        self.nome_script_sem_extensao: str = Path(__file__).resolve().stem  # nome do arquivo atual sem extensão
        self.nome_script: str = Path(__file__).resolve().name  # nome do arquivo atual com extensão
        self.id_execucao: str = uuid.uuid4().hex[:8]  # identificador único padrão desta execução (8 hex chars)
        self.data_inicio_execucao: str = datetime.now().strftime("%Y%m%d")  # data de início no formato AAAAMMDD
        self.hora_inicio_execucao: str = datetime.now().strftime("%H%M%S")  # hora de início no formato HHMMSS
        self.tipo_controle: str = tipo_controle  # tipo de controle (TERMINAL, INPUT, etc.)
        self.nome_arquivo_entrada: str = nome_arquivo_entrada  # nome do arquivo de entrada
        self.nome_pasta_saida = 'saida'
        self.nome_pasta_entrada = 'entrada'
        # Lista todos os nomes de arquivos e pastas
        try:
            self.apenas_pastas_diretorio_atual = [
                pasta.name for pasta in self.raiz_script_inicial.iterdir() if pasta.is_dir() and pasta.name != self.pasta_script.name
            ]
            if 'outputs' in self.apenas_pastas_diretorio_atual:
                self.nome_pasta_saida = 'outputs'
            if 'inputs' in self.apenas_pastas_diretorio_atual:
                self.nome_pasta_entrada = 'inputs'
        except Exception as e:
            self.apenas_pastas_diretorio_atual = []
        self.tipo_controle: str = tipo_controle  # "TERMINAL" ou "INPUT" ou "CONFIG"; define onde buscar arquivos de controle
        self.bd_conn_file: Path = Path(os.getenv("PADRAO_VALOR_RUN_BD_CONN_FILE") or (Path("/arquivos/CONNET_SH/DB_conn.txt")))  # arquivo de conexão usado como fallback
        self.delimitador: str = os.getenv("PADRAO_VALOR_RUN_DELIMITADOR") or ";"  # delimitador de colunas do CSV exportado
        self.tipo_execucao_script: str = os.getenv("PADRAO_VALOR_RUN_TIPO_EXECUCAO_SCRIPT") or "SQL"  # "SQL" ou "PLSQL"
        self.ferramenta_tipo_execucao_script: str = os.getenv("PADRAO_VALOR_RUN_FERRAMENTA_TIPO_EXECUCAO_SCRIPT") or "SQLPLUS"  # "SQLPLUS" ou "PYTHON" (normalizado abaixo)
        self.tags_estritas: str = os.getenv("PADRAO_VALOR_RUN_TAGS_ESTRICTAS") or "S"  # "S" faz falhar se sobrarem tags [X] não substituídas
        self.compactar_arquivo_dados_exportacao: str = os.getenv("PADRAO_VALOR_RUN_COMPACTAR_ARQUIVO_DADOS_EXPORTACAO") or "N"  # "S" compacta a saída em ZIP
        self.manter_original: str = os.getenv("PADRAO_VALOR_RUN_MANTER_ORIGINAL") or "N"  # "S" mantém o arquivo original após compactar
        self.idioma_nls: str = os.getenv("PADRAO_VALOR_RUN_IDIOMA_NLS") or "AMERICAN_AMERICA.AL32UTF8"  # idioma/charset da sessão Oracle (NLS_LANG)
        self.quantidade_linhas_quebra_arquivo: int = int(os.getenv("PADRAO_VALOR_RUN_QUANTIDADE_LINHAS_QUEBRA_ARQUIVO") or 0)  # linhas por parte; 0 desativa a divisão
        self.lista_parametros: List[Tuple[str, str]] = []  # pares (tag, valor) de tags dinâmicas a substituir no script
        self.arquivos_ok: List[Path] = []  # arquivos de controle processados com sucesso (modo lote)
        self.arquivos_erro: List[Path] = []  # arquivos de controle que falharam (modo lote)
        self.arquivos_gerados: List[Path] = []  # arquivos de saída (CSV/ZIP) gerados na execução
        self.entradas: List[Path] = []  # reservado para arquivos de entrada usados no processo
        self.status_processo: int = 0  # código de saída final: 0 = sucesso, 1 = falha
        self.objeto_conexao: Any = None  # conexão oracledb/cx_Oracle quando a ferramenta é PYTHON
        self.objeto_cursor: Any = None  # cursor associado a objeto_conexao
        self.oracle_client_lib_dir: str = os.getenv("PADRAO_VALOR_RUN_ORACLE_CLIENT_LIB_DIR", os.getenv("ORACLE_CLIENT_LIB_DIR", os.getenv("ORACLE_HOME"))) or ''  # apenas capturado/logado, não aplicado ao driver

        # Se NIVEL_LOG for uma string válida, sobrescreve o nível padrão DEBUG.
        nivel = os.getenv("PADRAO_VALOR_RUN_NIVEL_LOG", False)
        if nivel and isinstance(nivel, str) and nivel.strip().upper() in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            niveis_map = {
                "DEBUG": logging.DEBUG,
                "INFO": logging.INFO,
                "WARNING": logging.WARNING,
                "ERROR": logging.ERROR,
                "CRITICAL": logging.CRITICAL
            }
            self.nivel_log = niveis_map.get(nivel.strip().upper(), logging.DEBUG)  # mapeia o texto para a constante do logging
        # Normaliza o nome da ferramenta de execução para um dos dois valores aceitos.
        if str(self.ferramenta_tipo_execucao_script).strip().upper() in ["PYTHON", "PY"]:
            self.ferramenta_tipo_execucao_script = "PYTHON"
        else:
            self.ferramenta_tipo_execucao_script = "SQLPLUS"
        self.id_execucao = os.getenv("PADRAO_VALOR_RUN_ID_EXECUCAO") if os.getenv("PADRAO_VALOR_RUN_ID_EXECUCAO", False) else self.id_execucao  # PADRAO_VALOR_RUN_ID_EXECUCAO sobrescreve o UUID gerado
        self.raiz_script = self.pasta_script if os.getenv("PADRAO_VALOR_RUN_FLAG_INDICADOR_RAIZ_SCRIPT") else self.raiz_script_inicial  # PADRAO_VALOR_RUN_FLAG_INDICADOR_RAIZ_SCRIPT definida troca a raiz para a pasta do script
        self.diretorio_script = Path(os.getenv("PADRAO_VALOR_RUN_DIRETORIO_SCRIPT") or (self.raiz_script / "sql" if self.raiz_script_inicial == self.raiz_script else self.raiz_script))  # se a raiz não foi sobrescrita, os scripts ficam em <raiz>/sql
        self.nome_arquivo_script = os.getenv("PADRAO_VALOR_RUN_NOME_ARQUIVO_SCRIPT") or f"{self.nome_script_sem_extensao}.sql"  # nome do script a executar; padrão é o nome deste .py com extensão .sql
        self.diretorio_saida = Path(os.getenv("PADRAO_VALOR_RUN_DIRETORIO_SAIDA") or self.raiz_script / self.nome_pasta_saida/ str(self.nome_script_sem_extensao).lower().replace(" ","").strip() / self.data_inicio_execucao / self.hora_inicio_execucao / self.id_execucao)  # diretório de trabalho único desta execução
        self.diretorio_relatorio = Path(os.getenv("PADRAO_VALOR_RUN_DIRETORIO_SAIDA_RELATORIO") or self.diretorio_saida)  # diretório do relatório final; por padrão é o mesmo de saída
        self.nome_arquivo_relatorio = os.getenv("PADRAO_VALOR_RUN_NOME_ARQUIVO_RELATORIO") or f"{self.nome_script_sem_extensao}.csv"  # nome-base/extensão do arquivo de relatório
        self.diretorio_log = Path(os.getenv("PADRAO_VALOR_RUN_DIRETORIO_LOG") or self.raiz_script / "logs" / str(self.nome_script_sem_extensao).lower().replace(" ","").strip() / self.data_inicio_execucao / self.hora_inicio_execucao / self.id_execucao)  # diretório de logs único desta execução
        self.nome_arquivo_log = os.getenv("PADRAO_VALOR_RUN_NOME_ARQUIVO_LOG") or f"{self.nome_script_sem_extensao}.log"  # nome do arquivo de log
        self.diretorio_entrada = Path(os.getenv("PADRAO_VALOR_RUN_DIRETORIO_ENTRADA") or (self.raiz_script / self.nome_pasta_entrada if str(self.tipo_controle).strip().upper() in ["INPUT"] else self.raiz_script / "config"))  # diretório de busca dos arquivos de controle (modo lote)
        self.conexao_bd = os.getenv("PADRAO_VALOR_RUN_CONEXAO_BD") or (open(self.bd_conn_file).read().strip() if os.path.exists(self.bd_conn_file) else "")  # CONEXAO_BD tem prioridade; senão lê do arquivo de fallback
        # Snapshot dos valores padrão, usado por resetar_padroes() entre arquivos de controle no modo lote.
        self._conexao_bd_padrao = self.conexao_bd
        self._nome_arquivo_script_padrao = self.nome_arquivo_script
        self._nome_arquivo_relatorio_padrao = self.nome_arquivo_relatorio
        self._diretorio_relatorio_padrao = self.diretorio_relatorio
        self._diretorio_script_padrao = self.diretorio_script
        self._tags_estritas_padrao = self.tags_estritas
        self._compactar_arquivo_dados_exportacao_padrao = self.compactar_arquivo_dados_exportacao
        self._manter_original_padrao = self.manter_original
        self._delimitador_padrao = self.delimitador
        self._tipo_execucao_script_padrao = self.tipo_execucao_script
        self._idioma_nls_padrao = self.idioma_nls
        self._ferramenta_tipo_execucao_script_padrao = self.ferramenta_tipo_execucao_script
        self._objeto_conexao_padrao = self.objeto_conexao
        self._objeto_cursor_padrao = self.objeto_cursor
        self._oracle_client_lib_dir_padrao = self.oracle_client_lib_dir
        self._quantidade_linhas_quebra_arquivo_padrao = self.quantidade_linhas_quebra_arquivo

        # Cria os diretórios de trabalho (log, saída, relatório) já na inicialização.
        for diretorio in (self.diretorio_log, self.diretorio_saida, self.diretorio_relatorio):
            diretorio.mkdir(parents=True, exist_ok=True)

    def fechar_conexoes(self) -> None:
        """Fecha cursor e conexão Oracle abertos pela ferramenta PYTHON, ignorando erros."""
        try:
            self.objeto_cursor.close()  # fecha o cursor, se existir e estiver aberto
        except:
            pass  # cursor pode ser None ou já estar fechado; ignora silenciosamente
        try:
            self.objeto_conexao.close()  # fecha a conexão, se existir e estiver aberta
        except:
            pass  # conexão pode ser None ou já estar fechada; ignora silenciosamente
        try:
            self.objeto_cursor = None
        except:
            pass
        try:
            self.objeto_conexao = None
        except:
            pass

    def resetar_padroes(self) -> None:
        """Restaura os campos configuráveis para os valores padrão antes de processar um novo arquivo de controle."""
        self.lista_parametros = []  # limpa as tags dinâmicas acumuladas do arquivo anterior
        self.conexao_bd = self._conexao_bd_padrao
        self.nome_arquivo_script = self._nome_arquivo_script_padrao
        self.nome_arquivo_relatorio = self._nome_arquivo_relatorio_padrao
        self.diretorio_relatorio = self._diretorio_relatorio_padrao
        self.diretorio_script = self._diretorio_script_padrao
        self.tags_estritas = self._tags_estritas_padrao
        self.compactar_arquivo_dados_exportacao = self._compactar_arquivo_dados_exportacao_padrao
        self.manter_original = self._manter_original_padrao
        self.delimitador = self._delimitador_padrao
        self.tipo_execucao_script = self._tipo_execucao_script_padrao
        self.idioma_nls = self._idioma_nls_padrao
        self.ferramenta_tipo_execucao_script = self._ferramenta_tipo_execucao_script_padrao
        self.quantidade_linhas_quebra_arquivo = self._quantidade_linhas_quebra_arquivo_padrao
        try:
            self.fechar_conexoes()  # fecha qualquer conexão aberta pelo arquivo de controle anterior
        except:
            pass
        self.objeto_conexao = self._objeto_conexao_padrao
        self.objeto_cursor = self._objeto_cursor_padrao
        self.oracle_client_lib_dir = self._oracle_client_lib_dir_padrao


def partir_arquivo_linhas(caminho_origem: Path, linhas_por_parte: int = 1_000_000) -> List[Path]:
    """Divide um arquivo texto em partes de até `linhas_por_parte` linhas, repetindo o cabeçalho em cada parte.

    Args:
        caminho_origem: Arquivo de dados a ser dividido (ex.: CSV exportado).
        linhas_por_parte: Quantidade máxima de linhas de dados por arquivo gerado.

    Returns:
        Lista de caminhos das partes geradas, na ordem em que foram criadas.
    """
    arquivos_gerados = []  # acumula os caminhos das partes criadas
    with caminho_origem.open("r", encoding="utf-8", errors="replace", buffering=2 * 1024 * 1024) as f_in:
        cabecalho = f_in.readline()  # primeira linha é tratada como cabeçalho e repetida em cada parte
        if not cabecalho:
            return arquivos_gerados  # arquivo vazio: nada a dividir
        indice_parte = 1  # numeração da parte atual (V001, V002, ...)
        contador_linhas = 0  # linhas de dados já escritas na parte atual
        quantidade_linhas_totais = 0  # total de linhas de dados processadas no arquivo inteiro
        sufixo = caminho_origem.suffix  # extensão original (ex.: .csv), preservada em cada parte
        nome_base = caminho_origem.stem  # nome sem extensão, usado para montar o nome de cada parte
        f_out = None  # arquivo de saída da parte atual (aberto sob demanda)
        try:
            for linha in f_in:
                # Abre uma nova parte quando ainda não há arquivo aberto ou o limite foi atingido.
                if f_out is None or contador_linhas >= linhas_por_parte:
                    if f_out:
                        f_out.close()  # fecha a parte anterior antes de abrir a próxima
                    caminho_parte = caminho_origem.with_name(f"{nome_base}_V{indice_parte:03d}{sufixo}")
                    arquivos_gerados.append(caminho_parte)
                    f_out = caminho_parte.open("w", encoding="utf-8", newline="", buffering=2 * 1024 * 1024)
                    f_out.write(cabecalho)  # repete o cabeçalho no início da nova parte
                    contador_linhas = 0
                    indice_parte += 1
                f_out.write(linha)  # grava a linha de dados atual na parte aberta
                contador_linhas += 1
                quantidade_linhas_totais += 1
            if quantidade_linhas_totais == 0:
                # Arquivo só tinha cabeçalho: gera uma única parte contendo apenas o cabeçalho.
                caminho_parte = caminho_origem.with_name(f"{nome_base}_V{indice_parte:03d}{sufixo}")
                arquivos_gerados.append(caminho_parte)
                f_out = caminho_parte.open("w", encoding="utf-8", newline="", buffering=2 * 1024 * 1024)
                f_out.write(cabecalho)
        finally:
            if f_out:
                f_out.close()  # garante o fechamento da última parte aberta, mesmo em caso de exceção
    return arquivos_gerados


def remover_arquivo_seguro(caminho_dados_exportacao: Path) -> None:
    """Remove um arquivo do disco, ignorando o erro caso ele já não exista.

    Args:
        caminho_dados_exportacao: Caminho do arquivo a ser removido.
    """
    try:
        caminho_dados_exportacao.unlink()  # remove o arquivo
    except FileNotFoundError:
        pass  # já não existe; nada a fazer


def configurar_logger(configuracoes_dados: Configuracoes) -> logging.Logger:
    """Cria o logger da execução com handlers de arquivo e console, removendo handlers antigos.

    Args:
        configuracoes_dados: Estado com diretório/nome do arquivo de log e o nível configurado.

    Returns:
        Logger pronto para uso, com saída simultânea em arquivo e console.
    """
    arquivo_log = configuracoes_dados.diretorio_log / configuracoes_dados.nome_arquivo_log  # caminho completo do arquivo de log
    logger = logging.getLogger(configuracoes_dados.nome_logger_dados_exportacao)  # obtém (ou cria) o logger pelo nome do script
    logger.setLevel(configuracoes_dados.nivel_log)  # aplica o nível configurado (DEBUG por padrão)
    for handler in list(logger.handlers):
        handler.close()  # fecha handlers de execuções anteriores para não vazar descritores de arquivo
    logger.handlers = []  # remove os handlers antigos da lista do logger

    formato = logging.Formatter(
        "[%(asctime)s] [PID:%(process)d] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )  # layout comum das mensagens: timestamp, PID, nível e mensagem

    handler_arquivo = logging.FileHandler(str(arquivo_log), encoding="utf-8")  # grava as mensagens no arquivo de log
    handler_arquivo.setFormatter(formato)

    handler_console = logging.StreamHandler(sys.stdout)  # também exibe as mensagens no console (stdout)
    handler_console.setFormatter(formato)

    logger.addHandler(handler_arquivo)
    logger.addHandler(handler_console)
    return logger


def mascarar_credenciais(texto: str) -> str:
    """Substitui a senha em strings de conexão "usuario/senha@..." por "usuario/****@..." antes de logar.

    Args:
        texto: Texto que pode conter uma ou mais credenciais no formato usuario/senha@host.

    Returns:
        Texto com as senhas mascaradas; texto sem credenciais é retornado inalterado.
    """
    return PADRAO_CREDENCIAL_DADOS_EXPORTACAO.sub(r"\1/****@", texto)  # troca o grupo da senha por "****", preservando o usuário


def analisar_linha_parametro(linha: str, origem: str = "Linha") -> Optional[Tuple[str, str]]:
    """Converte uma linha "chave=valor" (ou "chave valor") em uma tupla (chave, valor) normalizada.

    Args:
        linha: Linha bruta lida de um arquivo de controle (.ini) ou de um argumento --tags.
        origem: "Linha" para arquivos de controle (aceita "chave: valor"); "Argumento" para --tags.

    Returns:
        Tupla (chave normalizada em minúsculas, valor) ou None se a linha for vazia, comentário ou inválida.
    """
    linha = linha.rstrip("\r\n")  # remove quebras de linha ao final
    if not linha.strip() or linha.lstrip().startswith("#"):
        return None  # ignora linhas vazias ou comentários iniciados por "#"
    linha = re.sub(r"\s+#.*$", "", linha).strip()  # remove comentário inline após o valor, se houver
    if not linha:
        return None  # nada restou após remover o comentário
    if origem != "Argumento":
        match = re.match(r"^([^\s:=]+)\s*[:=]\s*(.*)$", linha)  # tenta o formato "chave=valor" ou "chave: valor"
        if match:
            return match.group(1).strip().lower().lstrip("-").strip("[]"), match.group(2).strip()
    partes = linha.split(None, 1)  # fallback: divide em no máximo 2 partes pelo primeiro espaço
    if len(partes) < 2:
        return None  # não há separador reconhecível entre chave e valor
    return partes[0].strip().lower().lstrip("-").strip("[]"), partes[1].strip()


def verifica_dados_exportacao(configuracoes_dados: Configuracoes, logger: logging.Logger) -> bool:
    """Valida se o script configurado existe, não está vazio, e ajusta a ferramenta de execução para arquivos .py.

    Args:
        configuracoes_dados: Estado da execução com diretório e nome do script a validar.
        logger: Logger usado para registrar o resultado da validação.

    Returns:
        True se o script existe e é válido; False se houve erro de validação ou inesperado.
    """
    try:
        if not configuracoes_dados.diretorio_script:
            raise ValueError("Diretório do script não definido.")
        if not configuracoes_dados.nome_arquivo_script:
            raise ValueError("Nome do arquivo do script não definido.")
        origem_script = configuracoes_dados.diretorio_script / configuracoes_dados.nome_arquivo_script  # caminho completo do script a executar
        if not origem_script.is_file():
            raise ValueError("Arquivo não encontrado: %s" % origem_script)
        conteudo = origem_script.read_text(encoding="utf-8").rstrip()  # lê o conteúdo para checar se está vazio
        if not conteudo:
            raise ValueError(f"Arquivo vazio: {origem_script}")
        extensao = origem_script.suffix  # extensão do arquivo (.sql, .py, etc.)
        if str(extensao).lower().strip() == '.py':
            if str(configuracoes_dados.ferramenta_tipo_execucao_script).lower().strip() not in ["python", "py"]:
                logger.info("Extensão do script não compatível com a ferramenta de execução. Alterando para PYTHON.")
            configuracoes_dados.ferramenta_tipo_execucao_script = "PYTHON"  # força PYTHON sempre que o script for .py
        return True
    except ValueError as e:
        logger.error("Erro de validação ao verificar dados de exportação: %s", str(e))
        return False
    except Exception as e:
        logger.error("Erro inesperado ao verificar dados de exportação: %s", str(e))
        return False


def imprimir_dados_exportacao(configuracoes_dados: Configuracoes, logger: logging.Logger) -> None:
    """Registra no log, em nível INFO, o estado atual das configurações (com a conexão mascarada).

    Args:
        configuracoes_dados: Estado atual da execução a ser exibido no log.
        logger: Logger usado para registrar as informações.
    """
    logger.info("--------------------------------------------------")
    logger.info("Estado atual dos dados de exportação:")
    logger.info("Conexão BD: %s", mascarar_credenciais(configuracoes_dados.conexao_bd))  # nunca loga a senha em texto puro
    logger.info("Arquivo de conexão (fallback quando CONEXAO_BD não definida): %s", configuracoes_dados.bd_conn_file)
    logger.info("Tipo de execução: %s", configuracoes_dados.tipo_execucao_script)
    logger.info("Tipo de execução da ferramenta: %s", configuracoes_dados.ferramenta_tipo_execucao_script)
    logger.info("Diretório da biblioteca do cliente Oracle: %s", configuracoes_dados.oracle_client_lib_dir)
    logger.info("Diretório: %s", configuracoes_dados.diretorio_script)
    logger.info("Nome do arquivo: %s", configuracoes_dados.nome_arquivo_script)
    logger.info("Diretório do relatório: %s", configuracoes_dados.diretorio_relatorio)
    logger.info("Nome do arquivo de relatório: %s", configuracoes_dados.nome_arquivo_relatorio)
    logger.info("Tags estritas: %s", configuracoes_dados.tags_estritas)
    logger.info("Compactar arquivo de exportação: %s", configuracoes_dados.compactar_arquivo_dados_exportacao)
    logger.info("Manter arquivo original: %s", configuracoes_dados.manter_original)
    logger.info("Delimitador: %s", configuracoes_dados.delimitador)
    logger.info("Idioma NLS: %s", configuracoes_dados.idioma_nls)
    logger.info("Quantidade de linhas para quebra de arquivo: %s", configuracoes_dados.quantidade_linhas_quebra_arquivo)
    for lista_parametros in configuracoes_dados.lista_parametros:
        logger.info("Parâmetro: %s", mascarar_credenciais(str(lista_parametros)))  # cada tupla (tag, valor) também é mascarada
    logger.info("--------------------------------------------------")


def aplicar_parametro_dados(configuracoes_dados: Configuracoes, chave: str, valor: str, logger: logging.Logger) -> None:
    """Aplica uma tag reservada (tr*) a um campo de configuracoes_dados, ou registra uma tag dinâmica.

    Args:
        configuracoes_dados: Estado da execução que será atualizado com o valor informado.
        chave: Nome da tag (reservada "tr*" ou dinâmica), já recebida sem colchetes.
        valor: Valor textual associado à tag.
        logger: Logger usado para registrar tags dinâmicas aplicadas.

    Raises:
    """
    chave_normalizada = str(chave).lower()  # comparação case-insensitive com os nomes das tags reservadas
    # logger.debug("Aplicando parâmetro: chave=%s, valor=%s", chave_normalizada, valor)
    # """
    # chave_normalizada = chave.lower()  # comparação case-insensitive com os nomes das tags reservadas
    if chave_normalizada == "trcx":
        configuracoes_dados.conexao_bd = valor  # sobrescreve a string de conexão Oracle
    elif chave_normalizada == "trscript":
        if not re.match(r"^[^/\\\s\"\r\n]+$", valor):
            raise ValueError(f"Nome de arquivo inválido: {valor!r}")  # bloqueia separadores de caminho/aspas/quebras de linha
        configuracoes_dados.nome_arquivo_script = valor  # troca apenas o nome do script (mantém o diretório atual)
    elif chave_normalizada in ("trdirscript"):
        caminho = Path(valor).expanduser()  # expande "~" para o home do usuário, se presente
        if not caminho.is_dir():
            raise FileNotFoundError(f"Diretório base não existe: {caminho}")
        configuracoes_dados.diretorio_script = caminho  # troca o diretório onde o script será buscado
    elif chave_normalizada == "trrel":
        if not re.match(r"^[^/\\\s\"\r\n]+$", valor):
            raise ValueError(f"Nome de arquivo de saída relatório inválido: {valor!r}")
        configuracoes_dados.nome_arquivo_relatorio = valor  # troca apenas o nome do arquivo de relatório
    elif chave_normalizada == "trdirrel":
        caminho = Path(valor).expanduser()
        caminho.mkdir(parents=True, exist_ok=True)  # cria o diretório de destino do relatório, se necessário
        configuracoes_dados.diretorio_relatorio = caminho
    elif chave_normalizada == "trst":
        configuracoes_dados.tags_estritas = "S" if valor.upper() in ("1", "S", "SIM", "T", "TRUE") else "N"  # normaliza para "S"/"N"
    elif chave_normalizada == "trzip":
        configuracoes_dados.compactar_arquivo_dados_exportacao = "S" if valor.upper() in ("1", "S", "SIM", "T", "TRUE", "YES") else "N"
    elif chave_normalizada == "trkp":
        configuracoes_dados.manter_original = "S" if valor.upper() in ("1", "S", "SIM", "T", "TRUE", "YES") else "N"
    elif chave_normalizada == "trdl":
        if len(valor) != 1:
            raise ValueError(f"Delimitador deve ter 1 caractere: {valor!r}")  # delimitador de CSV precisa ser exatamente 1 caractere
        configuracoes_dados.delimitador = valor
    elif chave_normalizada == "trtpex":
        tipo = valor.upper().replace("_", "").replace(" ", "")  # normaliza "pl_sql"/"pl sql" para "PLSQL"
        if tipo not in ("SQL", "PLSQL"):
            raise ValueError(f"Tipo inválido: {valor!r}. Use SQL ou PLSQL.")
        configuracoes_dados.tipo_execucao_script = tipo
    elif chave_normalizada == "trfertpex":
        ferramenta_tipo_execucao_script = str(valor).upper().replace("_", "").replace(" ", "")
        if str(ferramenta_tipo_execucao_script).strip().upper() in ["PYTHON", "PY"]:
            configuracoes_dados.ferramenta_tipo_execucao_script = "PYTHON"
        else:
            configuracoes_dados.ferramenta_tipo_execucao_script = "SQLPLUS"  # qualquer outro valor cai no padrão SQLPLUS
    elif chave_normalizada == "trnlsl":
        configuracoes_dados.idioma_nls = valor  # idioma/charset NLS usado na sessão Oracle
    elif chave_normalizada == "trql":
        configuracoes_dados.quantidade_linhas_quebra_arquivo = int(valor)  # pode levantar ValueError se não for número
    elif chave_normalizada == "troraclilib":
        configuracoes_dados.oracle_client_lib_dir = valor
    else:
        # Chave não reconhecida: trata como tag dinâmica do tipo [CHAVE], registrada para substituição no script.
        tag = f"[{chave}]"
        configuracoes_dados.lista_parametros.append((tag, valor))
        logger.info("Tag registrada: %s", mascarar_credenciais(tag))


def substituir_tags_dados(configuracoes_dados: Configuracoes, caminho_script: Path, logger: logging.Logger) -> None:
    """Substitui no script as tags dinâmicas e as tags reservadas ([trcx], [trscript], etc.).

    Args:
        configuracoes_dados: Estado da execução com a lista de tags dinâmicas e os valores atuais.
        caminho_script: Caminho do arquivo (cópia de trabalho) que será lido e regravado.
        logger: Logger usado para registrar cada tag substituída.

    Raises:
        KeyError: Uma tag dinâmica da lista não foi encontrada no conteúdo do script.
        ValueError: `tags_estritas` está ativo e restaram tags [X] sem substituição.
    """
    conteudo = caminho_script.read_text(encoding="utf-8")  # lê o conteúdo completo da cópia de trabalho

    for tag, valor in configuracoes_dados.lista_parametros:
        padrao = re.compile(re.escape(tag), re.IGNORECASE)  # busca a tag literal, ignorando maiúsculas/minúsculas
        conteudo, total_subs = padrao.subn(lambda m: valor, conteudo)  # função de substituição evita interpretar \1 etc. no valor
        if total_subs == 0:
            raise KeyError(f"Tag dinâmica não encontrada no script: {tag}")  # tag informada mas ausente no script é erro
        logger.info("Tag dinâmica substituída: %s", tag)

    # Tags reservadas refletem o próprio estado da configuração (ex.: [trcx] vira a string de conexão atual).
    tags_parametros_atuais = {
        "[trcx]": str(configuracoes_dados.conexao_bd or ""),
        "[trscript]": str(configuracoes_dados.nome_arquivo_script or ""),
        "[trdirscript]": str(configuracoes_dados.diretorio_script or ""),
        "[trrel]": str(configuracoes_dados.nome_arquivo_relatorio or ""),
        "[trdirrel]": str(configuracoes_dados.diretorio_relatorio or ""),
        "[trst]": str(configuracoes_dados.tags_estritas or ""),
        "[trzip]": str(configuracoes_dados.compactar_arquivo_dados_exportacao or ""),
        "[trkp]": str(configuracoes_dados.manter_original or ""),
        "[trdl]": str(configuracoes_dados.delimitador or ""),
        "[trtpex]": str(configuracoes_dados.tipo_execucao_script or ""),
        "[trfertpex]": str(configuracoes_dados.ferramenta_tipo_execucao_script or ""),
        "[trnlsl]": str(configuracoes_dados.idioma_nls or ""),
        "[trql]": str(configuracoes_dados.quantidade_linhas_quebra_arquivo or 0),
        "[troraclilib]": str(configuracoes_dados.oracle_client_lib_dir or ""),
    }

    for tag_res, val_res in tags_parametros_atuais.items():
        padrao_res = re.compile(re.escape(tag_res), re.IGNORECASE)
        conteudo, total_subs = padrao_res.subn(lambda m: val_res, conteudo)
        if total_subs > 0:
            logger.info("Tag de parâmetro atual substituída: %s", tag_res)  # tags reservadas são opcionais; ausência não é erro

    if configuracoes_dados.tags_estritas == "S":
        pendentes = PADRAO_TAG_DADOS_EXPORTACAO.findall(conteudo)  # procura qualquer [X] que ainda reste no conteúdo
        if pendentes:
            raise ValueError(f"Tags sem substituição: {sorted(set(pendentes))}")  # falha explícita quando modo estrito está ativo

    caminho_script.write_text(conteudo, encoding="utf-8")  # regrava a cópia de trabalho com as substituições aplicadas


def validar_conexao_sqlplus(configuracoes_dados: Configuracoes, logger: logging.Logger) -> bool:
    """Testa a conexão Oracle via SQL*Plus executando um SELECT 1 FROM DUAL.

    Args:
        configuracoes_dados: Estado da execução com a string de conexão, idioma NLS e arquivo de fallback.
        logger: Logger usado para registrar o progresso e o resultado do teste.

    Returns:
        True se a conexão foi validada com sucesso; False em caso de erro, timeout ou sqlplus ausente.
    """
    conexao = configuracoes_dados.conexao_bd.strip()  # string de conexão informada via CONEXAO_BD/trcx

    if not conexao:
        # Sem conexão explícita: tenta carregar do arquivo de fallback (BD_CONN_FILE).
        bd_conn_file = configuracoes_dados.bd_conn_file
        if bd_conn_file.exists():
            logger.info("Lendo string de conexão do arquivo: %s", bd_conn_file)
            conexao = bd_conn_file.read_text(encoding="utf-8").strip()
        if not conexao:
            logger.error("String de conexão vazia ou não informada")
            return False  # nem CONEXAO_BD nem o arquivo de fallback forneceram uma conexão
        else:
            logger.warning("Arquivo de conexão encontrado: %s - será usado para conexão.", bd_conn_file)
            configuracoes_dados.conexao_bd = conexao  # propaga a conexão lida do arquivo para o restante da execução

    logger.info("Testando conexão: %s", mascarar_credenciais(conexao))

    script_dados = "\n".join(
        [
            "WHENEVER SQLERROR EXIT FAILURE ROLLBACK",  # qualquer erro SQL encerra o sqlplus com código de falha
            "WHENEVER OSERROR EXIT FAILURE ROLLBACK",  # idem para erros do sistema operacional
            f"CONNECT {conexao}",  # tenta autenticar com a string de conexão informada
            "SET PAGESIZE 0 FEEDBACK OFF VERIFY OFF HEADING OFF ECHO OFF",  # suprime ruído na saída do sqlplus
            "SELECT 1 FROM DUAL;",  # consulta mínima para confirmar que a sessão está ativa
            "EXIT SUCCESS",
        ]
    )  # script minimalista enviado via stdin ao sqlplus apenas para validar a conexão

    try:
        ambiente = {**os.environ, "NLS_LANG": configuracoes_dados.idioma_nls}  # herda o ambiente atual e fixa o NLS_LANG
        processo = subprocess.run(
            ["sqlplus", "-L", "-silent", "/nolog"],  # -L evita retry de senha; -silent remove o banner; /nolog não conecta antes do CONNECT
            input=script_dados,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # une stderr ao stdout para capturar toda a saída em um único buffer
            universal_newlines=True,
            timeout=TEMPO_TIMEOUT_CONEXAO_DADOS_EXPORTACAO,
            env=ambiente,
        )
    except subprocess.TimeoutExpired:
        logger.error("Timeout (%ds) ao conectar.", TEMPO_TIMEOUT_CONEXAO_DADOS_EXPORTACAO)
        return False
    except FileNotFoundError:
        logger.error("Comando sqlplus não encontrado no PATH.")
        return False  # o executável sqlplus precisa estar disponível no PATH do processo

    saida = processo.stdout or ""
    if processo.returncode != 0 or PADRAO_ERRO_ORACLE_DADOS_EXPORTACAO.search(saida):
        logger.error("Falha na conexão. Saída:\n%s", mascarar_credenciais(saida))
        return False  # código de retorno diferente de zero ou mensagem ORA-/SP2-/PLS- na saída indicam falha

    logger.info("Conexão validada com sucesso.")
    return True


def validar_conexao_python(configuracoes_dados: Configuracoes, logger: logging.Logger) -> bool:
    """Testa a conexão Oracle via driver Python, tentando primeiro oracledb e depois cx_Oracle.

    Args:
        configuracoes_dados: Estado da execução com a string de conexão; recebe o objeto de conexão/cursor abertos.
        logger: Logger usado para registrar o progresso e o resultado do teste.

    Returns:
        True se algum dos drivers conseguiu conectar e executar SELECT 1 FROM DUAL; False caso contrário.
    """
    conexao = configuracoes_dados.conexao_bd.strip()
    if not conexao:
        logger.error("String de conexão vazia ou não informada")
        return False
    logger.info("Testando conexão: %s", mascarar_credenciais(conexao))
    match = re.match(r"^([^/]+)/([^@]+)@(.+)$", conexao)  # separa usuario / senha / dsn(host:porta/serviço)
    if not match:
        logger.error("Formato inválido de conexão")
        return False
    usuario, senha, dsn = match.groups()
    script_dados = "SELECT 1 FROM DUAL"  # consulta mínima para validar a sessão aberta
    quantidade_tentativas = 2
    try:
        tentativa_atual = 1  # tentativa com oracledb
        import oracledb  # driver preferencial (modo thin, sem Oracle Client obrigatório)
        while tentativa_atual <= quantidade_tentativas:
            try:
                if tentativa_atual == 1:
                    try:
                        configuracoes_dados.objeto_conexao = oracledb.connect(user=usuario, password=senha, dsn=dsn)
                    except Exception as e:
                        logger.warning("Falha [1.1] ao conectar com Oracle Client: %s", mascarar_credenciais(str(e)))
                        try:
                            configuracoes_dados.objeto_conexao = oracledb.connect(conexao)
                        except Exception as e:
                            logger.warning("Falha [1.2] ao conectar com Oracle Client: %s", mascarar_credenciais(str(e)))
                elif tentativa_atual == 2:
                    try:
                        if configuracoes_dados.oracle_client_lib_dir:
                            oracledb.init_oracle_client(lib_dir=configuracoes_dados.oracle_client_lib_dir)
                        else:
                            oracledb.init_oracle_client()
                    except Exception as e:
                        logger.warning("Falha [2.1] ao inicializar Oracle Client: %s", mascarar_credenciais(str(e)))
                        try:
                            oracledb.init_oracle_client()
                        except Exception as e:
                            logger.warning("Falha [2.2] ao inicializar Oracle Client: %s", mascarar_credenciais(str(e)))
                    try:
                        configuracoes_dados.objeto_conexao = oracledb.connect(user=usuario, password=senha, dsn=dsn)
                    except Exception as e:
                        logger.warning("Falha [2.3] ao conectar com Oracle Client: %s", mascarar_credenciais(str(e)))
                        try:
                            configuracoes_dados.objeto_conexao = oracledb.connect(conexao)
                        except Exception as e:
                            logger.warning("Falha [2.4] ao conectar com Oracle Client: %s", mascarar_credenciais(str(e)))
                else:
                    raise RuntimeError("Tentativa inválida de conexão")
                configuracoes_dados.objeto_cursor = configuracoes_dados.objeto_conexao.cursor()
                cursor = configuracoes_dados.objeto_cursor
                cursor.execute(script_dados)
                logger.info("Conexão [1] validada com sucesso. (tentativa %d)", tentativa_atual)
                break
            except Exception as e:
                logger.info("Falha [1] ao validar conexão: %s (tentativa %d)", mascarar_credenciais(str(e)), tentativa_atual)
                configuracoes_dados.fechar_conexoes()
            tentativa_atual += 1
        if not configuracoes_dados.objeto_conexao or not configuracoes_dados.objeto_cursor:
            raise RuntimeError("Falha [1] ao validar conexão após todas as tentativas")
    except Exception as e:
        logger.info("Falha [1] ao validar conexão: %s", mascarar_credenciais(str(e)))
        try:
            import cx_Oracle  # driver alternativo, usado quando oracledb não está disponível ou falhou
            configuracoes_dados.objeto_conexao = cx_Oracle.connect(user=usuario, password=senha, dsn=dsn)
            configuracoes_dados.objeto_cursor = configuracoes_dados.objeto_conexao.cursor()
            cursor = configuracoes_dados.objeto_cursor
            cursor.execute(script_dados)
            logger.info("Conexão [2] validada com sucesso.")
        except Exception as e:
            logger.error("Falha [2] ao validar conexão: %s", mascarar_credenciais(str(e)))
            return False  # ambos os drivers falharam
    logger.info("Conexão validada com sucesso.")
    return True


def construir_script_sqlplus(conexao: str, nome_sql: str, caminho_spool: Path, delimitador: str, plsql: bool) -> str:
    """Monta o script sqlplus que conecta, executa o SQL/PLSQL via @arquivo e faz SPOOL do resultado.

    Args:
        conexao: String de conexão Oracle usada no CONNECT.
        nome_sql: Nome do arquivo de script a ser executado com "@" (relativo ao cwd do subprocesso).
        caminho_spool: Caminho absoluto do arquivo onde o SPOOL vai gravar a saída.
        delimitador: Caractere delimitador do CSV (usado apenas quando plsql=False).
        plsql: True para configurar a sessão para bloco PL/SQL; False para SELECT tabular em CSV.

    Returns:
        Texto completo do script, pronto para ser enviado via stdin ao sqlplus.
    """
    cabecalho_comum = [
        "WHENEVER SQLERROR EXIT FAILURE ROLLBACK",  # erro de SQL interrompe com falha e desfaz a transação
        "WHENEVER OSERROR EXIT 1 ROLLBACK",  # erro de SO também interrompe com falha
        f"CONNECT {conexao}",  # autentica com a string de conexão fornecida
        "SET LINESIZE 32767",  # evita quebra de linha prematura em linhas longas
        "SET TRIMSPOOL ON",  # remove espaços em branco à direita no arquivo de SPOOL
        "SET TRIMOUT ON",  # remove espaços em branco à direita na saída do terminal
        "SET FEEDBACK OFF",  # não exibe "N rows selected"
        "SET VERIFY OFF",  # não exibe substituição de variáveis "old"/"new"
        "SET ECHO OFF",  # não ecoa os comandos executados
        "SET PAGESIZE 0",  # desativa quebras de página (cabeçalhos repetidos)
    ]

    if plsql:
        # Bloco PL/SQL: habilita DBMS_OUTPUT (mensagens de PUT_LINE) e desativa qualquer formatação CSV.
        cabecalho = cabecalho_comum + ["SET SERVEROUTPUT ON SIZE UNLIMITED", "SET HEADING OFF", "SET MARKUP CSV OFF"]
    else:
        # SELECT tabular: configura buscas em lote e formata a saída como CSV com o delimitador escolhido.
        cabecalho = cabecalho_comum + [
            "SET NEWPAGE NONE",  # não insere caractere de nova página entre seções
            "SET ARRAYSIZE 5000",  # linhas buscadas por vez do servidor (desempenho)
            "SET ROWPREFETCH 5000",  # linhas pré-buscadas na primeira ida ao servidor
            "SET LONG 1000000",  # tamanho máximo exibido de colunas LONG
            "SET LONGCHUNKSIZE 1000000",  # tamanho do bloco de leitura de colunas LONG
            "SET UNDERLINE OFF",  # não desenha linha de sublinhado sob os cabeçalhos
            "SET COLSEP ''",  # remove separador padrão de coluna (o CSV usa DELIMITER abaixo)
            "SET TERMOUT OFF",  # não exibe a saída no terminal, apenas no SPOOL
            "SET HEADING ON",  # mantém o cabeçalho de colunas na primeira linha do CSV
            "SET SERVEROUTPUT OFF",  # DBMS_OUTPUT não se aplica a SELECT tabular
            f'SET MARKUP CSV ON DELIMITER "{delimitador}" QUOTE ON',  # ativa a formatação CSV nativa do sqlplus
        ]

    corpo = [f'SPOOL "{caminho_spool}"', f'@"{nome_sql}"', "SPOOL OFF", "EXIT SUCCESS"]  # grava a saída, executa o script e encerra
    return "\n".join(cabecalho + corpo)


def garantir_terminador_dados(caminho_script: Path, tipo: str, logger: logging.Logger, ferramenta_tipo_execucao_script: str) -> None:
    """Ajusta o terminador final do script conforme o mecanismo de execução: SQLPLUS exige ';' ou '/'; driver Python não usa nenhum.

    Args:
        caminho_script: Caminho do arquivo (cópia de trabalho) a validar/corrigir.
        tipo: "SQL" ou "PLSQL"; define se o terminador esperado é ';' ou '/'.
        logger: Logger usado para avisar quando o terminador foi adicionado ou removido.
        ferramenta_tipo_execucao_script: "SQLPLUS" exige o terminador; qualquer outro valor remove.

    Raises:
        ValueError: O arquivo está vazio após remover espaços em branco.
    """
    conteudo = caminho_script.read_text(encoding="utf-8").rstrip()  # remove espaços/quebras de linha ao final antes de checar
    if not conteudo:
        raise ValueError(f"Arquivo vazio: {caminho_script}")
    ultimo_caractere = conteudo[-1]  # último caractere não branco do conteúdo
    if ferramenta_tipo_execucao_script == "SQLPLUS":
        if tipo == "PLSQL" and ultimo_caractere != "/":
            logger.warning("PLSQL sem '/'. Adicionando no fim do arquivo.")
            caminho_script.write_text(conteudo + "\n/\n", encoding="utf-8")  # bloco PL/SQL precisa do "/" para ser executado pelo sqlplus
        elif tipo == "SQL" and ultimo_caractere != ";":
            logger.warning("SQL sem ';'. Adicionando no fim do arquivo.")
            caminho_script.write_text(conteudo + ";\n", encoding="utf-8")  # instrução SQL precisa do ";" final
    else:
        # Driver Python (oracledb/cx_Oracle) não aceita terminador ao final do texto executado.
        if tipo == "PLSQL" and ultimo_caractere == "/":
            logger.warning("PLSQL com '/' no fim do arquivo. Removendo.")
            caminho_script.write_text(conteudo[:-1], encoding="utf-8")
        elif tipo == "SQL" and ultimo_caractere == ";":
            logger.warning("SQL com ';' no fim do arquivo. Removendo.")
            caminho_script.write_text(conteudo[:-1], encoding="utf-8")


def _normalizar_valor_lob(valor: Any) -> Any:
    """Lê o conteúdo de uma coluna LOB (cx_Oracle/oracledb) antes de gravá-la no CSV.

    Args:
        valor: Valor retornado pelo cursor; pode ser um LOB (objeto com método read) ou um tipo simples.

    Returns:
        Conteúdo já lido do LOB, ou o próprio valor caso não seja um LOB.
    """
    return valor.read() if hasattr(valor, "read") else valor  # LOBs expõem .read(); outros tipos retornam como estão


def _sanitizar_campo(valor: Any) -> Any:
    """Normaliza LOBs e remove quebras de linha internas de campos de texto antes da exportação em CSV.

    Args:
        valor: Valor de uma célula do resultado (pode ser LOB, string ou outro tipo).

    Returns:
        Valor pronto para ser escrito no CSV (string sem \\r/\\n, ou o valor original se não for string).
    """
    val = _normalizar_valor_lob(valor)  # primeiro resolve o LOB, se houver
    if isinstance(val, str):
        return val.replace("\r", " ").replace("\n", " ").strip()  # evita quebrar o layout de uma linha do CSV
    return val


def _salvar_dbms_output(cursor: Any, caminho_dados_exportacao: Path, logger: logging.Logger) -> int:
    """Grava em arquivo, em lotes, as linhas acumuladas em DBMS_OUTPUT após a execução do bloco PL/SQL.

    Args:
        cursor: Cursor com dbms_output.enable já chamado e o bloco PL/SQL já executado.
        caminho_dados_exportacao: Caminho do arquivo onde as linhas de saída serão gravadas.
        logger: Logger usado para registrar a conclusão da gravação.

    Returns:
        Quantidade total de linhas gravadas no arquivo.
    """
    total_linhas = 0  # contador de linhas efetivamente gravadas
    tamanho_lote = min(TAMANHO_LOTE_FETCH_DADOS_EXPORTACAO, 5000)  # limita o lote a 5000 (limite prático do DBMS_OUTPUT.GET_LINES)
    linhas_var = cursor.arrayvar(str, tamanho_lote)  # variável de bind do tipo array de strings, usada como buffer de saída
    qtd_var = cursor.var(int)  # variável de bind que recebe a quantidade de linhas retornadas por chamada
    plsql_bloco = """
    BEGIN
        DBMS_OUTPUT.GET_LINES(:lines, :numlines);
    END;
    """  # bloco anônimo chamado repetidamente para drenar o buffer do DBMS_OUTPUT em lotes
    with caminho_dados_exportacao.open("w", encoding="utf-8", buffering=2 * 1024 * 1024) as arquivo_saida:
        while True:
            qtd_var.setvalue(0, tamanho_lote)  # informa ao Oracle quantas linhas no máximo podem ser retornadas desta vez
            cursor.execute(plsql_bloco, lines=linhas_var, numlines=qtd_var)
            qtd = qtd_var.getvalue() or 0  # quantidade de linhas efetivamente retornadas nesta chamada
            if not qtd:
                break  # buffer do DBMS_OUTPUT esgotado
            linhas = linhas_var.getvalue()[:qtd]  # apenas as posições preenchidas do array são válidas
            for linha in linhas:
                arquivo_saida.write((linha or "") + "\n")  # trata None como linha vazia
            total_linhas += qtd
            if qtd < tamanho_lote:
                break  # retorno menor que o lote solicitado indica que não há mais linhas
    logger.debug("DBMS_OUTPUT gravado em: %s (Total: %d linhas)", caminho_dados_exportacao, total_linhas)
    return total_linhas


def executar_script_dados(configuracoes_dados: Configuracoes, logger: logging.Logger) -> bool:
    """Copia o script, substitui tags, garante o terminador e executa SQL/PLSQL/Python, exportando e compactando o resultado.

    Args:
        configuracoes_dados: Estado completo da execução (script, tags, conexão, flags de exportação).
        logger: Logger usado para registrar cada etapa da execução.

    Returns:
        True se a execução (e exportação/compactação, quando aplicável) foi bem-sucedida; False caso contrário.
    """
    logger.info("Iniciando execução do script.")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")  # usado para nomear a cópia do script e o arquivo exportado
    logger.info("Timestamp da execução: %s", timestamp)
    sufixo_aleatorio = uuid.uuid4().int % 1001  # evita colisão de nomes entre execuções no mesmo segundo
    logger.info("Sufixo aleatório da execução: %s", sufixo_aleatorio)
    origem_script = configuracoes_dados.diretorio_script / configuracoes_dados.nome_arquivo_script  # caminho do script original configurado
    if not origem_script.is_file():
        logger.error("Arquivo não encontrado: %s", origem_script)
        return False

    caminho_script_copia_bkp = configuracoes_dados.diretorio_saida / f"{configuracoes_dados.nome_arquivo_script}.bkp.{timestamp}_{sufixo_aleatorio}"
    shutil.copy2(str(origem_script), str(caminho_script_copia_bkp))  # backup do script original, antes de qualquer substituição
    logger.info("Script BKP copiado: %s -> %s", origem_script, caminho_script_copia_bkp)

    extensao = origem_script.suffix  # extensão do script original (.sql, .py, etc.)
    caminho_script_copia = configuracoes_dados.diretorio_saida / f"{timestamp}_{sufixo_aleatorio}{extensao}"
    shutil.copy2(str(origem_script), str(caminho_script_copia))  # cópia de trabalho que será modificada (tags/terminador)
    logger.info("Script copiado: %s -> %s", origem_script, caminho_script_copia)

    if not caminho_script_copia.is_file() or caminho_script_copia.stat().st_size == 0:
        logger.error("Script copiado ausente ou vazio: %s", caminho_script_copia)
        return False
    logger.info("Cópia do script validada com sucesso: %s", caminho_script_copia)
    logger.debug("Preparando para substituir tags no script: %s", caminho_script_copia)
    try:
        substituir_tags_dados(configuracoes_dados, caminho_script_copia, logger)  # aplica tags dinâmicas e reservadas na cópia
    except (KeyError, ValueError) as erro:
        logger.error("Falha na substituição de tags: %s", erro)
        return False
    logger.debug("Substituição de tags concluída com sucesso: %s", caminho_script_copia)

    if extensao.lower().strip() != ".py":
        # Scripts .py não usam terminador de bloco SQL/PLSQL; a checagem só se aplica a .sql e afins.
        logger.debug("Garantindo terminador no script: %s", caminho_script_copia)
        try:
            garantir_terminador_dados(caminho_script_copia, configuracoes_dados.tipo_execucao_script, logger, configuracoes_dados.ferramenta_tipo_execucao_script)
        except ValueError as erro:
            logger.error("Falha ao garantir terminador no script: %s - Arquivo: %s", erro, caminho_script_copia)
            return False
        logger.debug("Terminador garantido no script com sucesso: %s", caminho_script_copia)

    conteudo_script = caminho_script_copia.read_text(encoding="utf-8")  # conteúdo final, já com tags e terminador aplicados
    logger.debug("Conteúdo do script %s:\n%s", caminho_script_copia.name, mascarar_credenciais(conteudo_script))

    if extensao.lower().strip() == ".py":
        # Ramo Python: carrega o arquivo como módulo e delega a execução à função main() nele definida.
        logger.debug("Script Python carregado com sucesso: %s", caminho_script_copia)
        try:
            import importlib.util  # import local para não impactar o carregamento do módulo quando não usado
            nome_modulo = caminho_script_copia.stem  # nome do módulo, baseado no nome do arquivo copiado
            spec = importlib.util.spec_from_file_location(nome_modulo, str(caminho_script_copia))  # especificação de carregamento a partir do caminho
            if spec is None or spec.loader is None:
                raise ImportError(f"Não foi possível criar spec para o script: {caminho_script_copia}")
            modulo = importlib.util.module_from_spec(spec)  # cria o objeto de módulo vazio, ainda não executado
            pasta_script_exec = str(caminho_script_copia.parent)  # diretório da cópia, para permitir imports locais do script
            remover_sys_path = False
            if pasta_script_exec not in sys.path:
                sys.path.insert(0, pasta_script_exec)  # adiciona temporariamente ao sys.path
                remover_sys_path = True
            try:
                spec.loader.exec_module(modulo)  # executa o corpo do módulo (define funções, incluindo main)
                if not hasattr(modulo, "main") or not callable(getattr(modulo, "main")):
                    raise AttributeError(f"O script Python {caminho_script_copia.name} não possui uma função 'main()'.")
                logger.info("Invocando main(configuracoes_dados, logger) do script: %s", caminho_script_copia.name)
                resultado = modulo.main(configuracoes_dados, logger)  # delega a execução ao script carregado
                if resultado not in (True, 0, None):
                    logger.error("A função main() do script Python retornou código de falha: %r", resultado)
                    return False  # qualquer retorno diferente de True/0/None é tratado como falha
            finally:
                if remover_sys_path and pasta_script_exec in sys.path:
                    sys.path.remove(pasta_script_exec)  # remove do sys.path para não vazar entre execuções
            logger.info("Execução do script Python concluída com sucesso: %s", caminho_script_copia)
            return True  # ramo Python encerra aqui; não passa pela exportação/compactação abaixo
        except Exception as erro:
            txt_erro = traceback.format_exc()
            logger.error("Falha na execução do script Python: %s - Arquivo: %s\n%s", erro, caminho_script_copia, txt_erro)
            return False
    else:
        # Ramo SQL/PLSQL: monta o caminho de exportação e executa via SQLPLUS ou driver Python.
        logger.debug("Preparando caminho de exportação de dados: %s", configuracoes_dados.diretorio_relatorio)
        extensao = (configuracoes_dados.nome_arquivo_relatorio or "").rsplit(".", 1)[-1] or "csv"  # extensão do relatório, com fallback para "csv"
        nome_base = (configuracoes_dados.nome_arquivo_relatorio or configuracoes_dados.nome_arquivo_script).rsplit(".", 1)[0]  # nome sem extensão
        caminho_dados_exportacao = configuracoes_dados.diretorio_relatorio / f"{nome_base}_{timestamp}.{extensao}"  # arquivo final de exportação, com timestamp único
        logger.debug("Caminho de exportação de dados definido: %s", caminho_dados_exportacao)
        logger.debug("Removendo arquivo de exportação de dados, se existir: %s", caminho_dados_exportacao)
        remover_arquivo_seguro(caminho_dados_exportacao)  # evita conflito com um arquivo remanescente de execução anterior
        logger.debug("Arquivo de exportação de dados removido com sucesso, se existia: %s", caminho_dados_exportacao)

        if configuracoes_dados.ferramenta_tipo_execucao_script == "SQLPLUS":
            # Executa o SQL/PLSQL via subprocesso sqlplus, com SPOOL para o arquivo de exportação.
            logger.debug("Construindo script SQL*Plus para execução: %s", caminho_script_copia)
            script_sqlplus = construir_script_sqlplus(
                configuracoes_dados.conexao_bd, caminho_script_copia.name, caminho_dados_exportacao.resolve(), configuracoes_dados.delimitador, configuracoes_dados.tipo_execucao_script == "PLSQL"
            )
            logger.debug("Script SQL*Plus:\n%s", mascarar_credenciais(script_sqlplus))
            logger.info("Iniciando execução do SQL*Plus: %s", caminho_script_copia)
            try:
                ambiente = {**os.environ, "NLS_LANG": configuracoes_dados.idioma_nls}  # fixa o idioma/charset da sessão Oracle
                processo = subprocess.run(
                    ["sqlplus", "-L", "-silent", "/nolog"],
                    input=script_sqlplus,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    cwd=str(caminho_script_copia.parent),  # executa no diretório da cópia, para o "@arquivo" relativo funcionar
                    timeout=172800,  # 48 horas: limite alto para consultas/relatórios longos
                    env=ambiente,
                )
                logger.info("Execução do SQL*Plus finalizada: %s", caminho_script_copia)
            except subprocess.TimeoutExpired:
                logger.error("Timeout na execução do script: %s", caminho_script_copia)
                return False
            saida = processo.stdout or ""
            if PADRAO_ERRO_ORACLE_DADOS_EXPORTACAO.search(saida):
                logger.error("Erros Oracle detectados:\n%s", mascarar_credenciais(saida))
                return False  # mensagens ORA-/SP2-/PLS- na saída indicam falha, mesmo com returncode 0
            if processo.returncode != 0:
                logger.error("Execução do script retornou %d:\n%s", processo.returncode, mascarar_credenciais(saida))
                return False
            logger.info("Execução do script SQL*Plus concluída com sucesso.")
            if caminho_dados_exportacao.is_file():
                # SELECT tabular pode deixar linhas em branco antes do cabeçalho; PLSQL deixa uma mensagem de sucesso no rodapé.
                logger.debug("Limpando cabeçalho do arquivo de exportação de dados: %s", caminho_dados_exportacao)
                limpar_arquivo_dados_topo(caminho_dados_exportacao, logger)
                logger.debug("Arquivo de exportação de dados limpo no cabeçalho: %s", caminho_dados_exportacao)
                if configuracoes_dados.tipo_execucao_script == "PLSQL":
                    logger.debug("Limpando rodapé do arquivo de exportação de dados: %s", caminho_dados_exportacao)
                    limpar_arquivo_dados_rodape(caminho_dados_exportacao, logger)
                    logger.debug("Arquivo de exportação de dados limpo no rodapé: %s", caminho_dados_exportacao)
        else:
            # Executa o SQL/PLSQL usando o driver Python (oracledb/cx_Oracle) já conectado por validar_conexao_python.
            logger.info("Executando via biblioteca Python (oracledb/cx_Oracle): %s", caminho_script_copia)
            cursor = configuracoes_dados.objeto_cursor
            try:
                if configuracoes_dados.tipo_execucao_script == "PLSQL":
                    cursor.callproc("dbms_output.enable", [None])  # habilita o buffer de DBMS_OUTPUT sem limite explícito
                    cursor.execute(conteudo_script)  # executa o bloco PL/SQL
                    configuracoes_dados.objeto_conexao.commit()  # confirma eventuais alterações feitas pelo bloco
                    total_linhas = _salvar_dbms_output(cursor, caminho_dados_exportacao, logger)  # drena o DBMS_OUTPUT para o arquivo
                    logger.info("Linhas do DBMS_OUTPUT exportadas: %d", total_linhas)
                else:
                    cursor.arraysize = TAMANHO_LOTE_FETCH_DADOS_EXPORTACAO  # tamanho do lote de fetch (desempenho)
                    cursor.prefetchrows = TAMANHO_LOTE_FETCH_DADOS_EXPORTACAO  # linhas pré-buscadas na primeira ida ao servidor
                    cursor.execute(conteudo_script)  # executa o SELECT
                    colunas = [descricao[0] for descricao in (cursor.description or [])]  # nomes das colunas do resultado
                    total_linhas = 0
                    with caminho_dados_exportacao.open("w", newline="", encoding="utf-8", buffering=2 * 1024 * 1024) as arquivo_saida:
                        escritor = csv.writer(arquivo_saida, delimiter=configuracoes_dados.delimitador, quoting=csv.QUOTE_ALL)
                        if colunas:
                            escritor.writerow(colunas)  # grava o cabeçalho com os nomes das colunas
                        while True:
                            lote = cursor.fetchmany(TAMANHO_LOTE_FETCH_DADOS_EXPORTACAO)  # busca em lotes, sem acumular o result set inteiro
                            if not lote:
                                break
                            escritor.writerows([[_sanitizar_campo(valor) for valor in linha] for linha in lote])  # sanitiza LOBs/quebras de linha antes de escrever
                            total_linhas += len(lote)
                    logger.info("Linhas exportadas via Python: %d", total_linhas)
            except Exception as erro:
                logger.error("Falha na execução do PYTHON: %s - %s", caminho_script_copia, mascarar_credenciais(str(erro)))
                return False

        logger.info("Verificação de existência do arquivo de exportação de dados: %s", caminho_dados_exportacao)
        if not caminho_dados_exportacao.is_file():
            if configuracoes_dados.tipo_execucao_script == "PLSQL":
                logger.warning("PLSQL executado sem gerar ARQUIVO EXPORTADO (comportamento esperado para DML puro).")
                return True  # DML puro (INSERT/UPDATE/DELETE) legitimamente não gera arquivo de saída
            logger.error("ARQUIVO EXPORTADO não foi gerado: %s", caminho_dados_exportacao)
            return False

        realizado_particionamento = False
        falha_compactacao = False
        if configuracoes_dados.quantidade_linhas_quebra_arquivo and configuracoes_dados.quantidade_linhas_quebra_arquivo > 0 and caminho_dados_exportacao.is_file():
            # Quebra o arquivo exportado em partes menores, conforme a quantidade de linhas configurada.
            arquivos_particionados = partir_arquivo_linhas(caminho_dados_exportacao, configuracoes_dados.quantidade_linhas_quebra_arquivo)
            if arquivos_particionados and len(arquivos_particionados) > 0:
                falha = any(not arq.is_file() for arq in arquivos_particionados)  # confere se todas as partes foram realmente criadas
                if not falha:
                    realizado_particionamento = True
                    remover_arquivo_seguro(caminho_dados_exportacao)  # remove o arquivo original, já substituído pelas partes

        arquivos_finais = arquivos_particionados if realizado_particionamento else [caminho_dados_exportacao]  # lista única ou partes, conforme o particionamento

        for arquivo in arquivos_finais:
            if configuracoes_dados.compactar_arquivo_dados_exportacao == "S":
                logger.info("Compactando arquivo: %s", arquivo)
                caminho_zip = compactar_em_zip(arquivo, logger=logger, remover_original=(configuracoes_dados.manter_original != "S"))
                configuracoes_dados.arquivos_gerados.append(caminho_zip if caminho_zip else arquivo)  # registra o ZIP, ou o original se a compactação falhou
                if caminho_zip:
                    logger.info("Arquivo compactado: %s", configuracoes_dados.arquivos_gerados[-1])
                else:
                    falha_compactacao = True
                    logger.error("Falha ao compactar; arquivo original preservado: %s", arquivo)
            else:
                configuracoes_dados.arquivos_gerados.append(arquivo)
                logger.info("Arquivo mantido sem compactação: %s", arquivo)

        if falha_compactacao:
            logger.error("Exportação concluída parcialmente; falha na compactação.")
            return False  # pelo menos um arquivo não pôde ser compactado; trata como falha da execução

        logger.info("Exportação concluída: %s", configuracoes_dados.arquivos_gerados[-1])
    return True


def limpar_arquivo_dados_rodape(caminho_dados_exportacao: Path, logger: logging.Logger) -> None:
    """Remove, via truncate binário, a mensagem final do PL/SQL e linhas vazias no rodapé do arquivo exportado.

    Args:
        caminho_dados_exportacao: Caminho do arquivo exportado a ser limpo.
        logger: Logger usado para registrar a conclusão da limpeza.

    Raises:
        Exception: Repassada após logar o erro, caso a leitura/escrita do arquivo falhe.
    """
    termo_busca = b"PL/SQL procedure successfully completed."  # mensagem padrão do sqlplus ao final de um bloco PL/SQL
    tamanho_bloco = 24_576  # 24 KB lidos do final do arquivo; suficiente para cobrir a mensagem e linhas vazias

    try:
        tamanho_total = caminho_dados_exportacao.stat().st_size
        if tamanho_total == 0:
            return  # arquivo vazio: nada a limpar

        with caminho_dados_exportacao.open("r+b") as f:
            offset = max(0, tamanho_total - tamanho_bloco)  # início do bloco final a examinar (nunca negativo)
            f.seek(offset)
            bloco_final = f.read()  # lê apenas o final do arquivo, evitando carregar o arquivo inteiro em memória

            pos_msg = bloco_final.rfind(termo_busca)  # procura a última ocorrência da mensagem de sucesso
            if pos_msg != -1:
                pos_corte = bloco_final.rfind(b"\n", 0, pos_msg)  # localiza o início da linha onde a mensagem aparece
                bloco_final = bloco_final[: pos_corte + 1 if pos_corte != -1 else 0]  # descarta a mensagem e tudo após ela

            while bloco_final and bloco_final[-1:] in (b"\n", b"\r", b" ", b"\t"):
                bloco_final = bloco_final[:-1]  # remove espaços em branco/quebras de linha residuais no final

            if bloco_final:
                bloco_final += b"\n"  # garante uma única quebra de linha final no arquivo resultante

            novo_tamanho = offset + len(bloco_final)  # tamanho final do arquivo após o corte
            f.seek(novo_tamanho)
            f.truncate()  # descarta fisicamente tudo após o novo tamanho calculado

        logger.debug("ARQUIVO EXPORTADO limpo via truncate com sucesso: %s", caminho_dados_exportacao)
    except Exception as erro:
        logger.error("Erro ao limpar arquivo de dados %s: %s", caminho_dados_exportacao, erro)
        raise


def limpar_arquivo_dados_topo(caminho_dados_exportacao: Path, logger: logging.Logger) -> None:
    """Remove, deslocando bytes internamente, linhas em branco que o sqlplus deixou antes do cabeçalho.

    Args:
        caminho_dados_exportacao: Caminho do arquivo exportado a ser verificado e limpo.
        logger: Logger usado para registrar a limpeza realizada.

    Raises:
        Exception: Repassada após logar o erro, caso a leitura/escrita do arquivo falhe.
    """
    try:
        tamanho_total = caminho_dados_exportacao.stat().st_size
        if tamanho_total == 0:
            return  # arquivo vazio: nada a limpar

        with caminho_dados_exportacao.open("r+b") as f:
            amostra = f.read(min(24_576, tamanho_total))  # lê apenas uma amostra inicial para verificar se há sujeira
            if not amostra:
                return

            pos_cabecalho = 0
            while pos_cabecalho < len(amostra) and amostra[pos_cabecalho:pos_cabecalho + 1] in (b"\r", b"\n", b" ", b"\t"):
                pos_cabecalho += 1  # avança enquanto encontrar espaço em branco antes do cabeçalho real

            if pos_cabecalho == 0:
                return  # início do arquivo já está limpo; nada a fazer

            logger.debug("Removendo %d byte(s) em branco antes do cabeçalho: %s", pos_cabecalho, caminho_dados_exportacao)

            tamanho_chunk = 1024 * 1024  # 1 MB por bloco copiado, para não carregar o arquivo inteiro em memória
            pos_escrita = 0  # posição de escrita no início do arquivo (já sem o lixo)
            pos_leitura = pos_cabecalho  # posição de leitura, logo após o trecho em branco

            while pos_leitura < tamanho_total:
                f.seek(pos_leitura)
                bloco = f.read(tamanho_chunk)
                if not bloco:
                    break
                f.seek(pos_escrita)
                f.write(bloco)  # desloca o conteúdo útil para o início do arquivo
                pos_escrita += len(bloco)
                pos_leitura += len(bloco)

            f.seek(pos_escrita)
            f.truncate()  # remove o restante do arquivo após o conteúdo já deslocado

        logger.debug("Cabeçalho reposicionado no topo com sucesso: %s", caminho_dados_exportacao)
    except Exception as erro:
        logger.error("Erro ao validar/limpar topo do arquivo %s: %s", caminho_dados_exportacao, erro)
        raise


def compactar_em_zip(caminho_arquivo: Path, logger: logging.Logger, remover_original: bool = True) -> Optional[Path]:
    """Cria um arquivo .zip contendo o arquivo exportado, opcionalmente removendo o original após o sucesso.

    Args:
        caminho_arquivo: Caminho do arquivo a ser compactado.
        logger: Logger usado para registrar falhas de compressão.
        remover_original: Se True, remove o arquivo original somente após compactar com sucesso.

    Returns:
        Caminho do arquivo .zip gerado, ou None se a compactação falhar.
    """
    caminho_zip = caminho_arquivo.with_suffix(caminho_arquivo.suffix + ".zip")  # ex.: dados.csv -> dados.csv.zip
    try:
        # Sem compresslevel para compatibilidade com Python 3.6
        with zipfile.ZipFile(str(caminho_zip), "w", zipfile.ZIP_DEFLATED) as zip_handle:
            zip_handle.write(str(caminho_arquivo), arcname=caminho_arquivo.name)  # grava apenas o nome do arquivo dentro do ZIP
        if remover_original:
            remover_arquivo_seguro(caminho_arquivo)  # remove o arquivo original somente após o ZIP ter sido criado
        return caminho_zip
    except (OSError, zipfile.BadZipFile) as erro:
        logger.error("Falha ao comprimir %s: %s", caminho_arquivo, erro)
        return None  # o chamador decide como tratar a falha de compactação


def ler_arquivo_configuracao_dados(configuracoes_dados: Configuracoes, caminho_arquivo_configuracao: Path, logger: logging.Logger) -> None:
    """Restaura os valores padrão e aplica, linha a linha, os parâmetros de um arquivo de controle (.ini).

    Args:
        configuracoes_dados: Estado da execução que será restaurado e então atualizado.
        caminho_arquivo_configuracao: Caminho do arquivo de controle a ser lido.
        logger: Logger usado para registrar erros linha a linha.

    Raises:
        ValueError: Repassada de aplicar_parametro_dados para um valor inválido.
        FileNotFoundError: Repassada de aplicar_parametro_dados para diretório inexistente.
    """
    configuracoes_dados.resetar_padroes()  # evita que a configuração de um arquivo anterior "vaze" para este
    for numero_linha, linha in enumerate(caminho_arquivo_configuracao.read_text(encoding="utf-8").splitlines(), 1):
        parametro = analisar_linha_parametro(linha, origem="Linha")  # interpreta a linha como chave=valor
        if not parametro:
            continue  # linha vazia, comentário ou sem formato reconhecido
        chave, valor = parametro
        if not chave or not str(chave).strip() or valor is None or not str(valor).strip():
            continue  # ignora pares com chave ou valor vazios
        try:
            aplicar_parametro_dados(configuracoes_dados, chave, valor, logger)
        except (ValueError, FileNotFoundError) as erro:
            logger.error("Linha %d: %s", numero_linha, erro)
            raise  # interrompe o processamento deste arquivo; erro é tratado pelo chamador


def main(argv: Optional[List[str]] = None) -> int:
    """Ponto de entrada da rotina: escolhe entre modo direto (CLI) e modo lote (arquivos de controle).

    Args:
        argv: Lista de argumentos de linha de comando; usa sys.argv[1:] quando None.

    Returns:
        Código de saída do processo: 0 = sucesso, 1 = alguma falha ocorreu.
    """
    logger = None  # inicializado como None para permitir fallback a print() no except externo
    configuracoes_dados = None  # idem, para permitir fechar_conexoes() com segurança no except externo
    try:
        # args_lista = list(sys.argv[1:] if argv is None else argv)  # argumentos brutos recebidos pela CLI
        # args_sanitizados = []  # lista final que será passada ao argparse
        # i = 0
        # while i < len(args_lista):
        #     arg = args_lista[i]
        #     if arg == "--tags":
        #         if i + 1 < len(args_lista) and not args_lista[i + 1].startswith("-"):
        #             args_sanitizados.append(arg)
        #             args_sanitizados.append(args_lista[i + 1])  # mantém --tags junto do seu valor
        #             i += 2
        #             continue
        #         else:
        #             i += 1  # descarta "--tags" órfão, sem valor associado (ex.: seguido de outra flag ou no fim)
        #             continue
        #     args_sanitizados.append(arg)
        #     i += 1
        # parser = argparse.ArgumentParser(
        #     prog=NOME_LOGGER_DADOS_EXPORTACAO,
        #     description=AJUDA_DESCRICAO,
        #     epilog=AJUDA_EXEMPLOS,
        #     formatter_class=argparse.RawDescriptionHelpFormatter,  # preserva a formatação manual do texto de ajuda
        # )
        parser = ArgumentParserTraduzido(
            prog=NOME_LOGGER_DADOS_EXPORTACAO,
            description=AJUDA_DESCRICAO,
            epilog=AJUDA_EXEMPLOS,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument(
            "--tipo_controle",
            default=str(os.getenv("PADRAO_VALOR_RUN_TIPO_CONTROLE") or "TERMINAL").strip().upper(),
            help="Define onde buscar arquivos de controle. Pode ser 'TERMINAL', 'INPUT' ou 'CONFIG'.",
            choices=["TERMINAL", "INPUT", "CONFIG"],
        )
        parser.add_argument(
            "--nome_arquivo_entrada",
            default=str(os.getenv("PADRAO_VALOR_RUN_NOME_ARQUIVO_ENTRADA") or NOME_LOGGER_DADOS_EXPORTACAO).strip(),
            help="Define o nome do arquivo de entrada.",
        )
        parser.add_argument(
            "--tags",
            action="append",  # permite repetir --tags várias vezes, acumulando em uma lista
            nargs="+",  # permite informar vários pares CHAVE=VALOR após uma única ocorrência
            default=[],
            metavar="CHAVE=VALOR",
            help="Substitui [CHAVE] no SCRIPT ou altera tags reservadas. Aceita vários pares e pode ser repetido.",
        )
        argumentos = parser.parse_args(sys.argv[1:])  # usa os argumentos da linha de comando diretamente
        argumentos.tags = [tag for grupo_tags in argumentos.tags for tag in grupo_tags]  # mantém uma lista simples para o processamento existente
        configuracoes_dados = Configuracoes(argumentos.tipo_controle, argumentos.nome_arquivo_entrada)  # lê o ambiente e monta o estado inicial da execução
        logger = configurar_logger(configuracoes_dados)
        logger.info("---------------------------------------")
        logger.info(" - ARGS: %s", mascarar_credenciais(str(sys.argv)))
        logger.info(" - TAGs: %s ", argumentos.tags)
        logger.info(" - TIPO_CONTROLE: %s ", configuracoes_dados.tipo_controle)
        logger.info(" - ID de EXECUCAO: %s", configuracoes_dados.id_execucao)
        logger.info(" - DIRETORIO de LOG: %s", configuracoes_dados.diretorio_log)
        logger.info(" - DIRETORIO de SAIDA: %s", configuracoes_dados.diretorio_saida)
        logger.info(" - NOME de LOG: %s", configuracoes_dados.nome_arquivo_log)
        logger.info(" - NIVEL do LOG: %s", configuracoes_dados.nivel_log)
        logger.info(" - DIRETORIO de ENTRADA: %s", configuracoes_dados.diretorio_entrada)
        logger.info(" - NOME do ARQUIVO de ENTRADA: %s", configuracoes_dados.nome_arquivo_entrada)
        logger.info(" - PASTA do SCRIPT: %s", configuracoes_dados.pasta_script)
        logger.info(" - RAIZ do SCRIPT: %s", configuracoes_dados.raiz_script)
        logger.info(" - DATA de INICIO da EXECUCAO: %s", configuracoes_dados.data_inicio_execucao)
        logger.info(" - HORA de INICIO da EXECUCAO: %s", configuracoes_dados.hora_inicio_execucao)
        logger.info("---------------------------------------")
        if configuracoes_dados.tipo_controle  == 'TERMINAL':
            processar_argumentos_tag = True  # controla se a execução deve prosseguir (falso quando não há --tags)
            logger.debug("Processando argumentos de tag: %s", argumentos.tags)
            try:
                if argumentos.tags:
                    for tag in argumentos.tags:
                        # logger.debug("Processando tag: %s", tag)
                        chave, separador, valor = tag.partition("=")  # divide "chave=valor" no primeiro "="
                        # logger.debug("Chave: %s, Separador: %s, Valor: %s", chave, separador, mascarar_credenciais(valor))
                        if not separador or not str(chave).strip():
                            raise ValueError(f"Tag inválida no argumento: {tag!r}")  # "=" ausente indica formato inválido
                        aplicar_parametro_dados(configuracoes_dados, chave, valor, logger)
                else:
                    processar_argumentos_tag = False
                    configuracoes_dados.status_processo = 1
                    logger.error("Modo direto selecionado sem --tags; nenhuma execução foi realizada.")
                    logger.info("Processamento finalizado. Status: %d", configuracoes_dados.status_processo)
                    return configuracoes_dados.status_processo
            except Exception as erro:
                configuracoes_dados.status_processo = 1
                logger.error("Erro ao processar tags: %s", mascarar_credenciais(str(erro)))
                raise ValueError(f"Erro ao processar tags: {erro}")  # propaga para o except externo, que finaliza com status 1
            if not verifica_dados_exportacao(configuracoes_dados, logger):
                configuracoes_dados.status_processo = 1
                logger.error("Dados de exportação inválidos.")
                return configuracoes_dados.status_processo
            imprimir_dados_exportacao(configuracoes_dados, logger)
            if processar_argumentos_tag:
                # Só tenta validar conexão e executar o script se pelo menos uma --tags foi fornecida.
                if configuracoes_dados.ferramenta_tipo_execucao_script == "SQLPLUS" and not validar_conexao_sqlplus(configuracoes_dados, logger):
                    configuracoes_dados.status_processo = 1
                    return configuracoes_dados.status_processo
                if configuracoes_dados.ferramenta_tipo_execucao_script == "PYTHON" and not validar_conexao_python(configuracoes_dados, logger):
                    configuracoes_dados.status_processo = 1
                    return configuracoes_dados.status_processo
                if not executar_script_dados(configuracoes_dados, logger):
                    configuracoes_dados.status_processo = 1
                    return configuracoes_dados.status_processo
            logger.info("Processamento finalizado. Status: %d", configuracoes_dados.status_processo)
            return configuracoes_dados.status_processo

        diretorio_origem = configuracoes_dados.diretorio_entrada
        prefixo = configuracoes_dados.nome_arquivo_entrada
        arquivos_config = list(sorted(
            arq for arq in diretorio_origem.glob(f"{prefixo}*")  # todos os arquivos cujo nome começa com o prefixo configurado
            if arq.name != configuracoes_dados.nome_script  # exclui o próprio script, caso o glob o capture por coincidência
        ))

        if not arquivos_config:
            logger.warning("Nenhum arquivo encontrado em %s com prefixo %s", diretorio_origem, prefixo)
            return configuracoes_dados.status_processo

        copias_config = []
        for arq_config in arquivos_config:
            copia = configuracoes_dados.diretorio_saida / arq_config.name
            shutil.copy2(str(arq_config), str(copia))  # preserva o original copiando-o para a pasta de saída antes de processar
            copias_config.append(copia)
            if str(configuracoes_dados.tipo_controle).strip().upper() == "INPUT":
                remover_arquivo_seguro(arq_config)  # modo "INPUT" consome o arquivo original após copiá-lo

        for copia_config in copias_config:
            logger.info("=" * 60)
            logger.info("Processando: %s", copia_config.name)
            try:
                ler_arquivo_configuracao_dados(configuracoes_dados, copia_config, logger)  # restaura padrões e aplica as linhas do arquivo
            except Exception as erro:
                logger.error("Falha ao ler %s: %s", copia_config.name, mascarar_credenciais(str(erro)))
                configuracoes_dados.arquivos_erro.append(copia_config)
                configuracoes_dados.status_processo = 1
                continue  # segue para o próximo arquivo de controle, sem interromper o lote inteiro

            if not verifica_dados_exportacao(configuracoes_dados, logger):
                configuracoes_dados.status_processo = 1
                configuracoes_dados.arquivos_erro.append(copia_config)
                continue

            imprimir_dados_exportacao(configuracoes_dados, logger)
            if configuracoes_dados.ferramenta_tipo_execucao_script == "SQLPLUS" and not validar_conexao_sqlplus(configuracoes_dados, logger):
                configuracoes_dados.arquivos_erro.append(copia_config)
                configuracoes_dados.status_processo = 1
                continue
            if configuracoes_dados.ferramenta_tipo_execucao_script == "PYTHON" and not validar_conexao_python(configuracoes_dados, logger):
                configuracoes_dados.arquivos_erro.append(copia_config)
                configuracoes_dados.status_processo = 1
                continue
            if executar_script_dados(configuracoes_dados, logger):
                configuracoes_dados.arquivos_ok.append(copia_config)
            else:
                configuracoes_dados.arquivos_erro.append(copia_config)
                configuracoes_dados.status_processo = 1
            logger.info("=" * 60)

        configuracoes_dados.fechar_conexoes()  # fecha a conexão Oracle aberta pela última iteração do loop, se houver
        logger.info("RESUMO: OK=%d | ERRO=%d | GERADOS=%d", len(configuracoes_dados.arquivos_ok), len(configuracoes_dados.arquivos_erro), len(configuracoes_dados.arquivos_gerados))
        return configuracoes_dados.status_processo

    except Exception as erro:
        # Captura qualquer exceção não tratada nos ramos acima, garantindo que o processo sempre retorne um código de saída.
        txt = traceback.format_exc()
        if logger is not None:
            logger.error("Falha não tratada: %s\n%s", mascarar_credenciais(str(erro)), mascarar_credenciais(txt))
        else:
            print(mascarar_credenciais(f"Falha não tratada: {erro}\n{txt}"), file=sys.stderr)  # logger ainda não existia; usa stderr
        if configuracoes_dados:
            configuracoes_dados.fechar_conexoes()  # garante o fechamento de conexões mesmo em falha inesperada
        return 1


if __name__ == "__main__":
    sys.exit(main())  # código de saída do processo é o retorno de main(): 0 = sucesso, 1 = falha