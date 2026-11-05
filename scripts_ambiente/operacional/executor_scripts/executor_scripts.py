#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
Executor Operacional de Scripts (SQL, PL/SQL e Python) — v.1.0.0.0014
Compatível com Python 3.6+ (biblioteca padrão + driver Oracle opcional)
================================================================================

Finalidade:
  Orquestra a execução padronizada de rotinas em banco de dados Oracle (via
  SQL*Plus ou driver Python python-oracledb / cx_Oracle) e módulos Python (.py)
  que exponham a função `main(configuracoes_dados, logger)`.

Integração Nativa com o Script Scheduling Service (SSS):
  - Lê automaticamente as variáveis de ambiente injetadas pelo agente do SSS:
      * SSS_INPUT_DIR / SSS_FILES_INPUTS_DIR   -> Diretório de entrada
      * SSS_OUTPUT_DIR / SSS_FILES_OUTPUTS_DIR -> Diretório de relatórios/saída
      * SSS_WORK_DIR                           -> Diretório de trabalho temporário
      * SSS_LOG_DIR                            -> Diretório de logs
      * SSS_ENVIRONMENT_CONNECTION / PADRAO_VALOR_RUN_CONEXAO_BD -> Conexão Oracle
  - Quando executado fora do SSS (modo autônomo/terminal), resolve diretórios
    locais de fallback na árvore do script e lê `/arquivos/CONNET_SH/DB_conn.txt`.

Modos de Operação (--tipo_controle):
  - TERMINAL : Recebe parâmetros e tags diretamente via CLI (`--tags CHAVE=VALOR`).
  - CONFIG   : Processa em lote arquivos de configuração no diretório de entrada,
               preservando os arquivos originais de entrada.
  - INPUT    : Processa em lote arquivos no diretório de entrada e remove o arquivo
               de entrada original após copiá-lo para o diretório de trabalho.

Tags Reservadas de Configuração:
  [trcx]        String de conexão Oracle (usuario/senha@dsn)
  [trscript]    Nome do arquivo de script (.sql ou .py) a executar
  [trdirscript] Diretório onde reside o arquivo de script
  [trrel]       Nome base do arquivo de relatório de saída (.csv, .txt, etc.)
  [trdirrel]    Diretório onde o relatório final será gravado
  [trst]        Validação estrita de tags não substituídas (S/N, padrão: S)
  [trzip]       Compactar arquivo(s) de saída em .zip (S/N, padrão: N)
  [trkp]        Manter arquivo original após compactar em .zip (S/N, padrão: N)
  [trdl]        Caractere delimitador de colunas no CSV (padrão: ;)
  [trtpex]      Tipo de bloco de banco: SQL ou PLSQL (padrão: SQL)
  [trfertpex]   Ferramenta de execução: SQLPLUS ou PYTHON (padrão: SQLPLUS)
  [trnlsl]      Configuração de idioma NLS_LANG (padrão: AMERICAN_AMERICA.AL32UTF8)
  [trql]        Quantidade máxima de linhas por arquivo para particionamento (0 = sem quebra)
  [troraclilib] Caminho da biblioteca do Oracle Instant Client (LD_LIBRARY_PATH)
  
    1 ) caso de teste com sucesso testando via terminal com sqlplus
python3 ./executor_scripts.py --tags trscript="exemplo_consulta.sql" b="b" a="1"
python3 ./executor_scripts.py --tags trscript="exemplo_plsql.sql" trtpex="PLSQL" b="b" a="1"
    2 ) caso de teste com sucesso testando via terminal com acionando via python customizado
python3 ./executor_scripts.py --tags trscript="exemplo_script.py"
    3 ) caso de teste com sucesso testando via terminal com acionando via python, executando a consulta
python3 ./executor_scripts.py --tags trscript="exemplo_consulta.sql" trfertpex="PY" trtpex="SQL" trdl=";" b="b" a="1"
python3 ./executor_scripts.py --tags trscript="exemplo_plsql.sql" trfertpex="PY" trtpex="PLSQL" trdl=";" b="b" a="1"
    4 ) caso de testes acionando pipeline 1 arquivo em config python customizado
python3 ./executor_scripts.py --tipo_controle="CONFIG" --nome_arquivo_entrada="PIPELINE_EXEMPLO_A_REL_JAMES_WEB.config"
    5 ) caso de testes acionando pipeline 2 arquivo em entrada/input
python3 ./executor_scripts.py --tipo_controle="INPUT" --nome_arquivo_entrada="PIPELINE_EXEMPLO_A_000"

================================================================================
"""
import argparse
import csv
import importlib.util
import logging
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import traceback
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern, Tuple

VERSAO_SCRIPT: str = "1.0.0.0015"

AJUDA_DESCRICAO = """\
Executa SQL/PLSQL pelo SQL*Plus ou por driver Python e carrega módulos .py que
exponham main(configuracoes_dados, logger). Resultados SQL/PLSQL, quando gerados,
podem ser divididos em partes e compactados em ZIP.
"""

# Identificadores únicos e carimbos de tempo desta execução
ID_EXECUCAO: str = uuid.uuid4().hex[:8]
DATA_INICIO: str = datetime.now().strftime("%Y%m%d")
HORA_INICIO: str = datetime.now().strftime("%H%M%S")

# Expressões regulares pré-compiladas para detecção de erros Oracle, mascaramento e tags
PADRAO_ERRO_ORACLE: Pattern[str] = re.compile(r"(^|\s)(ORA-|SP2-|PLS-)\d+")
PADRAO_CREDENCIAL: Pattern[str] = re.compile(
    r"(?i)\b([a-z0-9_\-\.]+)/([^@\s]+)@", re.MULTILINE
)
PADRAO_TAG: Pattern[str] = re.compile(r"\[([A-Za-z_][A-Za-z0-9_]*)\]")

# Constantes operacionais
TEMPO_TIMEOUT_CONEXAO: int = 30
TAMANHO_LOTE_FETCH: int = 15000
VALORES_VERDADEIROS = {"1", "S", "SIM", "T", "TRUE", "YES"}
PATH_DB_CONN: Path = Path("/arquivos/CONNET_SH/DB_conn.txt")
# Caminhos base do próprio script no sistema de arquivos
CAMINHO_ARQUIVO_ATUAL: Path = Path(__file__).resolve()
NOME_ARQUIVO_SEM_EXTENSAO: str = CAMINHO_ARQUIVO_ATUAL.stem
DIRETORIO_SCRIPT: Path = CAMINHO_ARQUIVO_ATUAL.parent
RAIZ_SCRIPT: Path = DIRETORIO_SCRIPT.parent.parent

# Leitura das variáveis de ambiente fornecidas pelo agente do SSS (com fallback)
SSS_INPUT_DIR: str = (
    os.getenv("SSS_INPUT_DIR", "").strip()
    or os.getenv("SSS_FILES_INPUTS_DIR", "").strip()
)
SSS_OUTPUT_DIR: str = (
    os.getenv("SSS_OUTPUT_DIR", "").strip()
    or os.getenv("SSS_FILES_OUTPUTS_DIR", "").strip()
)
SSS_WORK_DIR: str = os.getenv("SSS_WORK_DIR", "").strip()
SSS_ENVIRONMENT_CONNECTION: str = (
    os.getenv("SSS_ENVIRONMENT_CONNECTION", "").strip()
    or os.getenv("PADRAO_VALOR_RUN_CONEXAO_BD", "").strip()
)
DIRETORIO_LOG: str = os.getenv("SSS_LOG_DIR", "").strip()

# Fallback do diretório de entrada quando executado fora do SSS
FLAG_APAGA_ARQUIVO = False
if not SSS_INPUT_DIR:
    for _dir_name in ("inputs", "entrada", "input", "entradas"):
        _cand = RAIZ_SCRIPT / _dir_name
        if _cand.exists():
            SSS_INPUT_DIR = str(_cand)
            FLAG_APAGA_ARQUIVO = True
            break
    else:
        SSS_INPUT_DIR = str(DIRETORIO_SCRIPT)

# Fallback do diretório de saída/relatórios quando executado fora do SSS
if not SSS_OUTPUT_DIR:
    for _dir_name in ("outputs", "saida", "output", "saidas"):
        _cand = RAIZ_SCRIPT / _dir_name
        if _cand.exists():
            SSS_OUTPUT_DIR = str(
                _cand / NOME_ARQUIVO_SEM_EXTENSAO / DATA_INICIO / HORA_INICIO / ID_EXECUCAO
            )
            break
    else:
        SSS_OUTPUT_DIR = str(
            DIRETORIO_SCRIPT / "outputs" / DATA_INICIO / HORA_INICIO / ID_EXECUCAO
        )

# Fallback do diretório de trabalho temporário
if not SSS_WORK_DIR:
    SSS_WORK_DIR = str(SSS_OUTPUT_DIR)

# Fallback do diretório de log local do script
if not DIRETORIO_LOG:
    for _dir_name in ("logs", "log"):
        _cand = RAIZ_SCRIPT / _dir_name
        if _cand.exists():
            DIRETORIO_LOG = str(
                _cand / NOME_ARQUIVO_SEM_EXTENSAO / DATA_INICIO / HORA_INICIO / ID_EXECUCAO
            )
            break
    else:
        DIRETORIO_LOG = str(SSS_WORK_DIR)


class ArgumentParserTraduzido(argparse.ArgumentParser):
    """Substitui mensagens de erro padrão do argparse por mensagens claras em português."""

    def error(self, message: str) -> None:
        traducoes = {
            "expected one argument": "esperava um valor obrigatório a seguir",
            "not allowed with argument": "não é permitido em conjunto com o parâmetro",
            "unrecognized arguments": "parâmetros não reconhecidos",
            "invalid choice": "valor inválido",
            "the following arguments are required": "os seguintes parâmetros são obrigatórios",
            "argument": "parâmetro",
            "choose from": "escolha entre",
        }
        for en, pt in traducoes.items():
            message = message.replace(en, pt)
        self.print_usage(sys.stderr)
        self.exit(2, "{}: erro de parâmetros: {}\n".format(self.prog, message))


class Configuracoes:
    """Mantém o estado, diretórios, conexões e parâmetros da execução atual."""

    def __init__(
        self,
        tipo_controle: str = "TERMINAL",
        nome_arquivo_entrada: str = NOME_ARQUIVO_SEM_EXTENSAO,
    ) -> None:
        self.nome_logger: str = NOME_ARQUIVO_SEM_EXTENSAO
        self.nivel_log: int = logging.DEBUG
        self.pasta_script: Path = DIRETORIO_SCRIPT
        self.nome_script_sem_extensao: str = NOME_ARQUIVO_SEM_EXTENSAO
        self.nome_script: str = CAMINHO_ARQUIVO_ATUAL.name
        self.id_execucao: str = ID_EXECUCAO
        self.data_inicio: str = DATA_INICIO
        self.hora_inicio: str = HORA_INICIO
        self.tipo_controle: str = str(tipo_controle).strip().upper()
        self.nome_arquivo_entrada: str = str(nome_arquivo_entrada).strip()

        # Diretórios operacionais resolvidos (SSS ou fallback local)
        self.diretorio_script: Path = self.pasta_script
        self.diretorio_entrada: Path = Path(SSS_INPUT_DIR)
        self.diretorio_saida: Path = Path(SSS_WORK_DIR)
        self.diretorio_relatorio: Path = Path(SSS_OUTPUT_DIR)
        self.diretorio_log: Path = Path(DIRETORIO_LOG)
        self.origem: Any = None

        # Garante a existência de todos os diretórios de trabalho antes de abrir o log
        for diretorio in (
            self.diretorio_saida,
            self.diretorio_relatorio,
            self.diretorio_log,
        ):
            diretorio.mkdir(parents=True, exist_ok=True)

        self.nome_arquivo_log: str = "{}_{}_{}_{}.log".format(
            self.nome_script_sem_extensao,
            self.data_inicio,
            self.hora_inicio,
            self.id_execucao,
        )
        self.status_processo: int = 0
        self.arquivos_ok: List[Path] = []
        self.arquivos_erro: List[Path] = []
        self.arquivos_gerados: List[Path] = []
        self.objeto_conexao: Any = None
        self.objeto_cursor: Any = None

        # Identifica a origem da credencial de banco (SSS vs arquivo local DB_conn.txt)
        if SSS_ENVIRONMENT_CONNECTION:
            self.origem_conexao: str = "Variável de ambiente SSS"
            self.conexao_bd: str = SSS_ENVIRONMENT_CONNECTION
        else:
            conn_arquivo = self._ler_conexao_bd()
            self.origem_conexao = (
                "Arquivo {}".format(PATH_DB_CONN) if conn_arquivo else "Não definida"
            )
            self.conexao_bd = conn_arquivo

        # Parâmetros padrão redefiníveis via --tags ou arquivo de lote
        self.nome_arquivo_script: str = "{}.sql".format(self.nome_script_sem_extensao)
        self.nome_arquivo_relatorio: str = "{}_{}_{}_{}.csv".format(
            self.nome_script_sem_extensao,
            self.data_inicio,
            self.hora_inicio,
            self.id_execucao,
        )
        self.delimitador: str = ";"
        self.tipo_execucao_script: str = "SQL"
        self.ferramenta_tipo_execucao: str = "SQLPLUS"
        self.tags_estritas: str = "S"
        self.compactar_arquivo: str = "N"
        self.manter_original: str = "N"
        self.idioma_nls: str = os.getenv("NLS_LANG", "AMERICAN_AMERICA.AL32UTF8")
        self.quantidade_linhas_quebra: int = 0
        self.oracle_client_lib_dir: str = (
            os.getenv("LD_LIBRARY_PATH", os.getenv("ORACLE_HOME", "")) or ""
        )
        self.lista_parametros: List[Tuple[str, str]] = []

        # Snapshot inicial para restaurar padrões entre itens de um lote (CONFIG/INPUT)
        self._snapshot: Dict[str, Any] = self._gerar_snapshot()

    def __str__(self) -> str:
        variaveis = "\n".join(
            "  {}={!r}".format(nome, valor)
            for nome, valor in sorted(vars(self).items())
            if not nome.startswith("_")
        )
        return mascarar_credenciais("ExecutorScripts(\n{}\n)".format(variaveis))

    def _ler_conexao_bd(self) -> str:
        """Lê a string de conexão de contingência em PATH_DB_CONN, quando existente."""
        if PATH_DB_CONN.exists():
            with PATH_DB_CONN.open("r", encoding="utf-8", errors="replace") as f:
                return f.read().strip()
        return ""

    def _gerar_snapshot(self) -> Dict[str, Any]:
        """Captura os atributos padrão para restaurá-los a cada arquivo processado em lote."""
        return {
            "conexao_bd": self.conexao_bd,
            "origem_conexao": self.origem_conexao,
            "nome_arquivo_script": self.nome_arquivo_script,
            "nome_arquivo_relatorio": self.nome_arquivo_relatorio,
            "diretorio_relatorio": self.diretorio_relatorio,
            "diretorio_script": self.diretorio_script,
            "origem": self.origem,
            "delimitador": self.delimitador,
            "tipo_execucao_script": self.tipo_execucao_script,
            "ferramenta_tipo_execucao": self.ferramenta_tipo_execucao,
            "tags_estritas": self.tags_estritas,
            "compactar_arquivo": self.compactar_arquivo,
            "manter_original": self.manter_original,
            "idioma_nls": self.idioma_nls,
            "quantidade_linhas_quebra": self.quantidade_linhas_quebra,
            "oracle_client_lib_dir": self.oracle_client_lib_dir,
        }

    def fechar_conexoes(self) -> None:
        """Fecha cursores e conexões de banco abertos pelo driver Python sem propagar exceções."""
        for recurso in (self.objeto_cursor, self.objeto_conexao):
            if recurso:
                try:
                    recurso.close()
                except Exception:
                    pass
        self.objeto_cursor = None
        self.objeto_conexao = None

    def resetar_padroes(self) -> None:
        """Restaura as configurações iniciais antes de iniciar o próximo arquivo em modo lote."""
        self.fechar_conexoes()
        self.lista_parametros = []
        for chave, valor in self._snapshot.items():
            setattr(self, chave, valor)


def mascarar_credenciais(texto: str) -> str:
    """Oculta a senha em strings no formato `usuario/senha@dsn` para exibição segura em log."""
    return PADRAO_CREDENCIAL.sub(r"\1/****@", str(texto))


def formatar_bytes(tamanho: int) -> str:
    """Formata um tamanho em bytes para leitura humana (B, KiB, MiB, GiB)."""
    valor = float(max(tamanho, 0))
    for unidade in ("B", "KiB", "MiB", "GiB"):
        if valor < 1024.0 or unidade == "GiB":
            return "{:.2f} {}".format(valor, unidade) if unidade != "B" else "{} B".format(int(valor))
        valor /= 1024.0
    return "{} B".format(int(tamanho))


def configurar_logger(cfg: Configuracoes) -> logging.Logger:
    """Configura o logger duplo: grava simultaneamente no arquivo de log local e no stdout (SSS)."""
    caminho_log = cfg.diretorio_log / cfg.nome_arquivo_log
    logger = logging.getLogger(cfg.nome_logger)
    logger.setLevel(cfg.nivel_log)
    logger.propagate = False
    for h in list(logger.handlers):
        h.close()
    logger.handlers = []

    formato = logging.Formatter(
        "[%(asctime)s] [PID:%(process)d] [%(levelname)-7s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    h_file = logging.FileHandler(str(caminho_log), encoding="utf-8")
    h_file.setFormatter(formato)
    h_cli = logging.StreamHandler(sys.stdout)
    h_cli.setFormatter(formato)

    logger.addHandler(h_file)
    logger.addHandler(h_cli)
    return logger


def logar_cabecalho_execucao(cfg: Configuracoes, logger: logging.Logger) -> None:
    """Imprime no log o cabeçalho completo de diagnóstico da execução e variáveis do SSS."""
    sep = "=" * 88
    logger.info(sep)
    logger.info(
        "INÍCIO DA EXECUÇÃO - %s (v%s) | ID=%s",
        cfg.nome_script,
        VERSAO_SCRIPT,
        cfg.id_execucao,
    )
    logger.info(sep)
    logger.info(
        "Host / SO / Usuário  : host=%s | pid=%d | uid=%d | gid=%d",
        socket.gethostname(),
        os.getpid(),
        os.geteuid(),
        os.getegid(),
    )
    logger.info(
        "Interpretador Python : %s (Python %s)",
        sys.executable,
        sys.version.split()[0],
    )
    logger.info("Diretório Atual (cwd): %s", os.getcwd())
    logger.info("Modo de Controle     : %s", cfg.tipo_controle)

    # Contexto injetado pelo agente do SSS (quando executado via ticket)
    ticket_id = os.getenv("SSS_TICKET_ID", "<execução avulsa fora do SSS>")
    ambiente_sss = os.getenv("SSS_ENVIRONMENT", "<não definido>")
    tipo_exec_sss = os.getenv("SSS_EXECUTION_TYPE", "<não definido>")
    agente_sss = os.getenv("SSS_AGENT_ID", "<não definido>")
    timeout_sss = os.getenv("SSS_TIMEOUT_SECONDS", "<não definido>")
    logger.info(
        "Contexto SSS         : ticket=%s | ambiente=%s | origem=%s | agente=%s | timeout=%ss",
        ticket_id,
        ambiente_sss,
        tipo_exec_sss,
        agente_sss,
        timeout_sss,
    )
    logger.info("Diretório do Script  : %s", cfg.diretorio_script)
    logger.info("Diretório de Entrada : %s", cfg.diretorio_entrada)
    logger.info("Diretório de Trabalho: %s", cfg.diretorio_saida)
    logger.info("Diretório de Saída   : %s", cfg.diretorio_relatorio)
    logger.info(
        "Arquivo de Log Local : %s", cfg.diretorio_log / cfg.nome_arquivo_log
    )
    logger.info(
        "Conexão Oracle       : %s (origem: %s)",
        mascarar_credenciais(cfg.conexao_bd) if cfg.conexao_bd else "<vazia>",
        cfg.origem_conexao,
    )
    logger.info("-" * 88)


def logar_resumo_final(
    cfg: Configuracoes,
    logger: logging.Logger,
    inicio_monotonic: float,
    codigo_retorno: int,
) -> None:
    """Imprime o quadro resumo de encerramento com tempo total, arquivos gerados e status."""
    duracao = time.monotonic() - inicio_monotonic
    sep = "=" * 88
    logger.info(sep)
    logger.info(
        "RESUMO FINAL DA EXECUÇÃO | ID=%s | STATUS=%s (rc=%d) | DURAÇÃO=%.2fs",
        cfg.id_execucao,
        "SUCESSO" if codigo_retorno == 0 else "FALHA",
        codigo_retorno,
        duracao,
    )
    if cfg.tipo_controle in ("CONFIG", "INPUT"):
        logger.info(
            "Lote Processado      : OK=%d | ERRO=%d",
            len(cfg.arquivos_ok),
            len(cfg.arquivos_erro),
        )
    logger.info("Arquivos Gerados (%d) :", len(cfg.arquivos_gerados))
    for idx, arq in enumerate(cfg.arquivos_gerados, 1):
        tamanho = arq.stat().st_size if arq.is_file() else 0
        logger.info("  [%02d] %s (%s)", idx, arq, formatar_bytes(tamanho))
    logger.info(sep)


def remover_arquivo_seguro(caminho: Path) -> None:
    """Remove um arquivo se ele existir, ignorando ausência sem lançar erro."""
    try:
        caminho.unlink()
    except FileNotFoundError:
        pass


def aplicar_parametro(
    cfg: Configuracoes, chave: str, valor: str, logger: logging.Logger
) -> None:
    """Aplica chave/valor normalizando e limpando eventuais aspas residuais."""
    k = chave.lower().strip().lstrip("-").strip("[]")
    v = valor.strip().strip('"\'')  # Garante remoção de aspas duplas/simples nas pontas

    if k == "trcx":
        cfg.conexao_bd = v
        cfg.origem_conexao = "Parâmetro [trcx]"
        logger.info("Parâmetro [trcx] aplicado: %s", mascarar_credenciais(v))
    elif k == "trscript":
        if not re.match(r"^[^/\\\s\"\r\n]+$", v):
            raise ValueError("Nome de arquivo de script inválido: {!r}".format(v))
        cfg.nome_arquivo_script = v
        logger.info("Parâmetro [trscript] (script alvo): %s", v)
    elif k == "trdirscript":
        p = Path(v).expanduser()
        if not p.is_dir():
            raise FileNotFoundError("Diretório de script inexistente: {}".format(p))
        cfg.diretorio_script = p
        logger.info("Parâmetro [trdirscript] (pasta do script): %s", p)
    elif k == "trrel":
        if not re.match(r"^[^/\\\s\"\r\n]+$", v):
            raise ValueError("Nome de arquivo de relatório inválido: {!r}".format(v))
        cfg.nome_arquivo_relatorio = v
        logger.info("Parâmetro [trrel] (nome do relatório): %s", v)
    elif k == "trdirrel":
        p = Path(v).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        cfg.diretorio_relatorio = p
        logger.info("Parâmetro [trdirrel] (pasta do relatório): %s", p)
    elif k == "trst":
        cfg.tags_estritas = "S" if v.upper() in VALORES_VERDADEIROS else "N"
        logger.info("Parâmetro [trst] (tags estritas): %s", cfg.tags_estritas)
    elif k == "trzip":
        cfg.compactar_arquivo = "S" if v.upper() in VALORES_VERDADEIROS else "N"
        logger.info("Parâmetro [trzip] (compactar saída em ZIP): %s", cfg.compactar_arquivo)
    elif k == "trkp":
        cfg.manter_original = "S" if v.upper() in VALORES_VERDADEIROS else "N"
        logger.info("Parâmetro [trkp] (manter original após ZIP): %s", cfg.manter_original)
    elif k == "trdl":
        if len(v) != 1:
            raise ValueError("Delimitador [trdl] deve ter exatamente 1 caractere: {!r}".format(v))
        cfg.delimitador = v
        logger.info("Parâmetro [trdl] (delimitador CSV): %r", cfg.delimitador)
    elif k == "trtpex":
        tipo = v.upper().replace("_", "").replace(" ", "")
        if tipo not in ("SQL", "PLSQL"):
            raise ValueError("Tipo de execução [trtpex] inválido: {!r}. Use SQL ou PLSQL.".format(v))
        cfg.tipo_execucao_script = tipo
        logger.info("Parâmetro [trtpex] (tipo de execução): %s", cfg.tipo_execucao_script)
    elif k == "trfertpex":
        cfg.ferramenta_tipo_execucao = (
            "PYTHON" if v.upper() in ("PYTHON", "PY") else "SQLPLUS"
        )
        logger.info(
            "Parâmetro [trfertpex] (ferramenta de execução): %s",
            cfg.ferramenta_tipo_execucao,
        )
    elif k == "trnlsl":
        cfg.idioma_nls = v
        logger.info("Parâmetro [trnlsl] (NLS_LANG): %s", cfg.idioma_nls)
    elif k == "trql":
        cfg.quantidade_linhas_quebra = int(v)
        logger.info(
            "Parâmetro [trql] (quebra de linhas por arquivo): %d",
            cfg.quantidade_linhas_quebra,
        )
    elif k == "troraclilib":
        cfg.oracle_client_lib_dir = v
        logger.info("Parâmetro [troraclilib] (Oracle Client lib_dir): %s", v)
    else:
        tag_fmt = "[{}]".format(chave.strip())
        cfg.lista_parametros.append((tag_fmt, v))
        logger.info(
            "Tag dinâmica registrada: %s = %s",
            tag_fmt,
            mascarar_credenciais(v),
        )


def substituir_tags(cfg: Configuracoes, caminho_script: Path, logger: logging.Logger) -> None:
    """Substitui no arquivo de trabalho todas as tags dinâmicas `[TAG]` e reservadas `[tr*]`."""
    logger.info("Iniciando substituição de tags na cópia de trabalho: %s", caminho_script.name)
    conteudo = caminho_script.read_text(encoding="utf-8")

    # 1. Substitui as tags dinâmicas informadas pelo usuário
    for tag, val in cfg.lista_parametros:
        conteudo, count = re.subn(
            re.escape(tag), lambda _m: val, conteudo, flags=re.IGNORECASE
        )
        if count == 0:
            raise KeyError(
                "A tag dinâmica {} foi informada nos parâmetros, mas não existe no script {}.".format(
                    tag, cfg.nome_arquivo_script
                )
            )
        logger.info("  -> Tag dinâmica substituída: %s (%d ocorrência(s))", tag, count)

    # 2. Substitui as tags reservadas de ambiente/configuração caso estejam presentes no script
    mapa_reservadas = {
        "[trcx]": cfg.conexao_bd,
        "[trscript]": cfg.nome_arquivo_script,
        "[trdirscript]": str(cfg.diretorio_script),
        "[trrel]": cfg.nome_arquivo_relatorio,
        "[trdirrel]": str(cfg.diretorio_relatorio),
        "[trst]": cfg.tags_estritas,
        "[trzip]": cfg.compactar_arquivo,
        "[trkp]": cfg.manter_original,
        "[trdl]": cfg.delimitador,
        "[trtpex]": cfg.tipo_execucao_script,
        "[trfertpex]": cfg.ferramenta_tipo_execucao,
        "[trnlsl]": cfg.idioma_nls,
        "[trql]": str(cfg.quantidade_linhas_quebra),
        "[troraclilib]": cfg.oracle_client_lib_dir,
    }
    for tag_res, val_res in mapa_reservadas.items():
        conteudo, count = re.subn(
            re.escape(tag_res), lambda _m: val_res, conteudo, flags=re.IGNORECASE
        )
        if count > 0:
            logger.info(
                "  -> Tag reservada substituída: %s (%d ocorrência(s))", tag_res, count
            )

    # 3. Se tags_estritas='S', recusa a execução caso reste algum placeholder [TAG] sem valor
    if cfg.tags_estritas == "S":
        pendentes = PADRAO_TAG.findall(conteudo)
        if pendentes:
            raise ValueError(
                "Execução abortada (tags_estritas=S): tags sem valor no script: {}".format(
                    sorted(set(pendentes))
                )
            )

    caminho_script.write_text(conteudo, encoding="utf-8")


def obter_executavel_sqlplus(cfg: Optional[Configuracoes] = None) -> str:
    """Localiza o binário sqlplus no PATH, variáveis Oracle, ld.so.conf.d ou pastas padrão.

    Quando o script é acionado pelo agente do SSS, o PATH do processo filho é
    restrito por segurança a `/usr/bin:/bin:<pasta_python>` (README §8.6).
    Por isso, além do PATH, esta função inspeciona:
      1. `cfg.oracle_client_lib_dir` (tag `[troraclilib]`), `ORACLE_HOME` e `LD_LIBRARY_PATH`;
      2. Tanto `<dir>/sqlplus` (layout Instant Client) quanto `<dir>/bin/sqlplus` (Oracle Home);
      3. Arquivos `/etc/ld.so.conf.d/*.conf` e diretórios padrão `/opt/oracle/instantclient*`.
    """
    caminho = shutil.which("sqlplus")
    if caminho:
        return caminho

    diretorios_busca: List[Path] = []

    def _adicionar_dir(valor: str) -> None:
        for parte in valor.split(":"):
            limpo = parte.strip()
            if limpo:
                p = Path(limpo)
                if p not in diretorios_busca:
                    diretorios_busca.append(p)

    if cfg is not None and cfg.oracle_client_lib_dir:
        _adicionar_dir(cfg.oracle_client_lib_dir)
    _adicionar_dir(os.getenv("ORACLE_HOME", ""))
    _adicionar_dir(os.getenv("LD_LIBRARY_PATH", ""))

    # Inspeciona configurações do dynamic linker (/etc/ld.so.conf.d/*.conf)
    ld_conf_dir = Path("/etc/ld.so.conf.d")
    if ld_conf_dir.is_dir():
        for arq_conf in sorted(ld_conf_dir.glob("*.conf")):
            try:
                for linha in arq_conf.read_text(encoding="utf-8", errors="ignore").splitlines():
                    linha = linha.strip()
                    if linha and not linha.startswith("#") and not linha.startswith("include "):
                        _adicionar_dir(linha)
            except Exception:
                pass

    # Pastas padrão de instalação do Oracle Instant Client / Client no Linux
    for padrao in (
        "/opt/oracle/instantclient*",
        "/usr/lib/oracle/*/client*/bin",
        "/usr/lib/oracle/*/client*/lib",
    ):
        for encontrado in sorted(Path("/").glob(padrao.lstrip("/")), reverse=True):
            _adicionar_dir(str(encontrado))

    for base in diretorios_busca:
        for cand in (
            base / "sqlplus",
            base / "bin" / "sqlplus",
            base.parent / "bin" / "sqlplus",
        ):
            if cand.is_file() and os.access(str(cand), os.X_OK):
                return str(cand)

    return "sqlplus"


def montar_ambiente_sqlplus(cfg: Configuracoes, exec_sqlplus: str) -> Dict[str, str]:
    """Monta o dicionário de variáveis de ambiente para o subprocesso SQL*Plus,
    garantindo que PATH e LD_LIBRARY_PATH incluam o diretório do cliente Oracle."""
    env = dict(os.environ)
    env["NLS_LANG"] = cfg.idioma_nls

    if exec_sqlplus and exec_sqlplus != "sqlplus":
        pasta_exec = Path(exec_sqlplus).resolve().parent
        pasta_lib = (
            pasta_exec.parent / "lib"
            if pasta_exec.name == "bin" and (pasta_exec.parent / "lib").is_dir()
            else pasta_exec
        )
        path_atual = env.get("PATH", "")
        if str(pasta_exec) not in path_atual.split(":"):
            env["PATH"] = "{}:{}".format(pasta_exec, path_atual) if path_atual else str(pasta_exec)

        ld_partes = [p for p in env.get("LD_LIBRARY_PATH", "").split(":") if p.strip()]
        if cfg.oracle_client_lib_dir:
            for p_cfg in cfg.oracle_client_lib_dir.split(":"):
                if p_cfg.strip() and p_cfg.strip() not in ld_partes:
                    ld_partes.insert(0, p_cfg.strip())
        if str(pasta_lib) not in ld_partes:
            ld_partes.insert(0, str(pasta_lib))
        env["LD_LIBRARY_PATH"] = ":".join(ld_partes)

    return env


def validar_conexao_sqlplus(cfg: Configuracoes, logger: logging.Logger) -> bool:
    """Valida a conectividade com o banco Oracle via cliente de linha de comando SQL*Plus."""
    if not cfg.conexao_bd:
        logger.error("Validação SQL*Plus falhou: string de conexão Oracle está vazia.")
        return False
    t0 = time.monotonic()
    exec_sqlplus = obter_executavel_sqlplus(cfg)
    logger.info(
        "Testando conexão Oracle via SQL*Plus (%s | bin=%s | NLS_LANG=%s)...",
        mascarar_credenciais(cfg.conexao_bd),
        exec_sqlplus,
        cfg.idioma_nls,
    )
    script = (
        "WHENEVER SQLERROR EXIT FAILURE;\n"
        "CONNECT {}\n"
        "SELECT 1 FROM DUAL;\n"
        "EXIT SUCCESS;\n"
    ).format(cfg.conexao_bd)
    try:
        proc = subprocess.run(
            [exec_sqlplus, "-L", "-silent", "/nolog"],
            input=script,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            timeout=TEMPO_TIMEOUT_CONEXAO,
            env=montar_ambiente_sqlplus(cfg, exec_sqlplus),
        )
        if proc.returncode != 0 or PADRAO_ERRO_ORACLE.search(proc.stdout or ""):
            logger.error(
                "Falha na conexão SQL*Plus (rc=%d):\n%s",
                proc.returncode,
                mascarar_credenciais(proc.stdout or ""),
            )
            return False
        logger.info(
            "Conexão SQL*Plus validada com sucesso em %.2fs.", time.monotonic() - t0
        )
        return True
    except Exception as e:
        logger.error("Erro ao validar conexão via SQL*Plus: %s", mascarar_credenciais(str(e)))
        return False


def validar_conexao_python(cfg: Configuracoes, logger: logging.Logger) -> bool:
    """Valida e abre a conexão com o Oracle usando driver Python (oracledb ou cx_Oracle)."""
    if not cfg.conexao_bd:
        logger.error("Validação Python DB falhou: string de conexão Oracle está vazia.")
        return False
    match = re.match(r"^([^/]+)/([^@]+)@(.+)$", cfg.conexao_bd)
    if not match:
        logger.error(
            "Formato inválido de credencial Oracle (%s). Esperado: usuario/senha@dsn",
            mascarar_credenciais(cfg.conexao_bd),
        )
        return False
    user, pwd, dsn = match.groups()

    # Prioriza python-oracledb; utiliza cx_Oracle como contingência
    driver = None
    for mod_name in ("oracledb", "cx_Oracle"):
        try:
            driver = __import__(mod_name)
            break
        except ImportError:
            continue
    if not driver:
        logger.error(
            "Nenhum driver Python para Oracle (oracledb ou cx_Oracle) encontrado em %s.",
            sys.executable,
        )
        return False

    t0 = time.monotonic()
    try:
        if driver.__name__ == "oracledb":
            lib_dir = cfg.oracle_client_lib_dir.split(":")[0].strip() if cfg.oracle_client_lib_dir else ""
            try:
                if lib_dir and os.path.isdir(lib_dir):
                    driver.init_oracle_client(lib_dir=lib_dir)
                else:
                    driver.init_oracle_client()
            except Exception:
                pass
        cfg.objeto_conexao = driver.connect(user=user, password=pwd, dsn=dsn)
        cfg.objeto_cursor = cfg.objeto_conexao.cursor()
        cfg.objeto_cursor.execute("SELECT 1 FROM DUAL")
        logger.info(
            "Conexão Oracle validada via driver Python (%s) em %.2fs.",
            driver.__name__,
            time.monotonic() - t0,
        )
        return True
    except Exception as e:
        logger.error(
            "Falha ao conectar no Oracle via driver %s: %s",
            driver.__name__,
            mascarar_credenciais(str(e)),
        )
        cfg.fechar_conexoes()
        return False


def partir_arquivo_linhas(
    caminho: Path, linhas_por_parte: int, logger: logging.Logger
) -> List[Path]:
    """Divide um arquivo de saída grande em múltiplos arquivos numerados (_V001, _V002...),
    repetindo a linha de cabeçalho no topo de cada parte gerada."""
    gerados: List[Path] = []
    logger.info(
        "Particionando arquivo %s em blocos de até %d linhas...",
        caminho.name,
        linhas_por_parte,
    )
    with caminho.open(
        "r", encoding="utf-8", errors="replace", buffering=2 * 1024 * 1024
    ) as f_in:
        cabecalho = f_in.readline()
        if not cabecalho:
            return gerados
        idx, linhas, f_out = 1, 0, None
        try:
            for linha in f_in:
                if f_out is None or linhas >= linhas_por_parte:
                    if f_out:
                        f_out.close()
                    p = caminho.with_name(
                        "{}_V{:03d}{}".format(caminho.stem, idx, caminho.suffix)
                    )
                    gerados.append(p)
                    f_out = p.open(
                        "w", encoding="utf-8", newline="", buffering=2 * 1024 * 1024
                    )
                    f_out.write(cabecalho)
                    linhas, idx = 0, idx + 1
                f_out.write(linha)
                linhas += 1
        finally:
            if f_out:
                f_out.close()
    logger.info(
        "Particionamento concluído: %d parte(s) gerada(s) a partir de %s.",
        len(gerados),
        caminho.name,
    )
    return gerados


def compactar_em_zip(
    caminho: Path, logger: logging.Logger, remover_original: bool = True
) -> Optional[Path]:
    """Compacta o arquivo informado em um pacote `.zip` (DEFLATED) e opcionalmente remove o original."""
    caminho_zip = caminho.with_suffix(caminho.suffix + ".zip")
    tam_orig = caminho.stat().st_size if caminho.is_file() else 0
    try:
        with zipfile.ZipFile(
            str(caminho_zip), "w", zipfile.ZIP_DEFLATED
        ) as arquivo_zip:
            arquivo_zip.write(str(caminho), arcname=caminho.name)
        tam_zip = caminho_zip.stat().st_size if caminho_zip.is_file() else 0
        logger.info(
            "Arquivo compactado com sucesso: %s (%s -> %s)%s",
            caminho_zip.name,
            formatar_bytes(tam_orig),
            formatar_bytes(tam_zip),
            " [original removido]" if remover_original else " [original mantido]",
        )
        if remover_original:
            remover_arquivo_seguro(caminho)
        return caminho_zip
    except Exception as e:
        logger.error("Erro ao compactar %s em ZIP: %s", caminho, e)
        return None


def limpar_saida_sqlplus(caminho: Path) -> int:
    """Remove linhas em branco iniciais e o rodapé padrão 'PL/SQL procedure successfully completed'
    do arquivo gerado pelo SPOOL do SQL*Plus. Retorna o total de linhas úteis restantes."""
    if not caminho.is_file() or caminho.stat().st_size == 0:
        return 0
    linhas = caminho.read_text(encoding="utf-8", errors="replace").splitlines()
    while linhas and not linhas[0].strip():
        linhas.pop(0)
    while linhas:
        ultima = linhas[-1].strip().upper()
        if not ultima or (
            "SQL" in ultima
            and "PROCEDURE" in ultima
            and "SUCCESS" in ultima
            and "COMPLET" in ultima
        ):
            linhas.pop()
        else:
            break
    if linhas:
        caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    else:
        caminho.write_text("", encoding="utf-8")
    return len(linhas)


def executar_script(cfg: Configuracoes, logger: logging.Logger) -> bool:
    """Prepara a cópia temporária do script alvo, aplica tags e executa via Python, SQL*Plus ou Driver DB."""
    script_dir = cfg.diretorio_script
    cfg.origem = script_dir / cfg.nome_arquivo_script
    if not cfg.origem.is_file() or cfg.origem.stat().st_size == 0:
        logger.error(
            "Arquivo de script alvo inexistente ou vazio: %s", cfg.origem
        )
        if script_dir != cfg.pasta_script:
            script_dir = cfg.pasta_script
            cfg.origem = script_dir / cfg.nome_arquivo_script
            if not cfg.origem.is_file() or cfg.origem.stat().st_size == 0:
                logger.error(
                    "Arquivo de script alvo inexistente ou vazio: %s", cfg.origem
                )
    if not cfg.origem.is_file() or cfg.origem.stat().st_size == 0:
        return False
    logger.info("Arquivo de script alvo localizado na pasta de script: %s", cfg.origem)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    rand = uuid.uuid4().hex[:4]
    copia = cfg.diretorio_saida / "{}_{}{}".format(ts, rand, cfg.origem.suffix)
    shutil.copy2(str(cfg.origem), str(copia))
    logger.info(
        "Script de origem localizado: %s (%s) -> cópia de trabalho: %s",
        cfg.origem,
        formatar_bytes(cfg.origem.stat().st_size),
        copia.name,
    )

    try:
        substituir_tags(cfg, copia, logger)
    except Exception as e:
        logger.error("Falha na preparação/substituição de tags: %s", e)
        return False

    ext = cfg.origem.suffix.lower()
    t0_exec = time.monotonic()

    # -------------------------------------------------------------------------
    # Ramo 1: Execução de Módulo Python (.py) com função main(cfg, logger)
    # -------------------------------------------------------------------------
    if ext == ".py":
        logger.info("Carregando e executando módulo Python: %s", copia.name)
        try:
            spec = importlib.util.spec_from_file_location(copia.stem, str(copia))
            if not spec or not spec.loader:
                raise ImportError("Não foi possível criar spec para {}".format(copia))
            mod = importlib.util.module_from_spec(spec)
            sys.path.insert(0, str(copia.parent))
            try:
                spec.loader.exec_module(mod)
                if not hasattr(mod, "main"):
                    raise AttributeError(
                        "O módulo {} não define a função obrigatória main(configuracoes_dados, logger).".format(
                            cfg.origem.name
                        )
                    )
                res = mod.main(cfg, logger)
                ok = res in (True, 0, None)
                logger.info(
                    "Módulo Python %s finalizado em %.2fs (retorno=%r -> %s).",
                    cfg.origem.name,
                    time.monotonic() - t0_exec,
                    res,
                    "SUCESSO" if ok else "FALHA",
                )
                return ok
            finally:
                if str(copia.parent) in sys.path:
                    sys.path.remove(str(copia.parent))
        except Exception as e:
            logger.error(
                "Exceção durante a execução do módulo Python %s: %s\n%s",
                cfg.origem.name,
                e,
                traceback.format_exc(),
            )
            return False

    # -------------------------------------------------------------------------
    # Ramo 2: Execução de Script SQL ou PL/SQL (via SQL*Plus ou Driver Python)
    # -------------------------------------------------------------------------
    caminho_relatorio = cfg.diretorio_relatorio / "{}_{}.{}".format(
        Path(cfg.nome_arquivo_relatorio).stem,
        ts,
        Path(cfg.nome_arquivo_relatorio).suffix.lstrip(".") or "csv",
    )
    remover_arquivo_seguro(caminho_relatorio)
    logger.info(
        "Iniciando execução de banco: tipo=%s | ferramenta=%s | saída=%s",
        cfg.tipo_execucao_script,
        cfg.ferramenta_tipo_execucao,
        caminho_relatorio.name,
    )

    if cfg.ferramenta_tipo_execucao == "SQLPLUS":
        # Garante que o arquivo SQL/PLSQL termine com ';' ou '/' para não travar o SQL*Plus
        txt = copia.read_text(encoding="utf-8").rstrip()
        term = "/" if cfg.tipo_execucao_script == "PLSQL" else ";"
        if not txt.endswith(term):
            copia.write_text(txt + "\n" + term + "\n", encoding="utf-8")

        modo_plsql = cfg.tipo_execucao_script == "PLSQL"
        cmd_csv = (
            'SET MARKUP CSV ON DELIMITER "{}" QUOTE ON'.format(cfg.delimitador)
            if not modo_plsql
            else ""
        )
        script = """
        WHENEVER SQLERROR EXIT FAILURE ROLLBACK;
        CONNECT {cx}
        SET LINESIZE 32767 TRIMSPOOL ON FEEDBACK OFF PAGESIZE 0 {plsql_opts}
        {csv_opts}
        SPOOL "{out}"
        @"{arq}"
        SPOOL OFF
        EXIT SUCCESS;
        """.format(
            cx=cfg.conexao_bd,
            plsql_opts=(
                "SERVEROUTPUT ON SIZE UNLIMITED HEADING OFF"
                if modo_plsql
                else "HEADING ON"
            ),
            csv_opts=cmd_csv,
            out=caminho_relatorio.resolve(),
            arq=copia.name,
        )
        try:
            exec_sqlplus = obter_executavel_sqlplus(cfg)
            res = subprocess.run(
                [exec_sqlplus, "-L", "-silent", "/nolog"],
                input=script,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                cwd=str(copia.parent),
                env=montar_ambiente_sqlplus(cfg, exec_sqlplus),
            )
            if res.returncode != 0 or PADRAO_ERRO_ORACLE.search(res.stdout or ""):
                logger.error(
                    "Erro reportado pelo SQL*Plus (rc=%d):\n%s",
                    res.returncode,
                    mascarar_credenciais(res.stdout or ""),
                )
                return False
            linhas_uteis = limpar_saida_sqlplus(caminho_relatorio)
            logger.info(
                "Execução SQL*Plus concluída em %.2fs (%d linha(s) gravada(s) no spool).",
                time.monotonic() - t0_exec,
                linhas_uteis,
            )
        except Exception as e:
            logger.error("Falha ao executar subprocesso SQL*Plus: %s", e)
            return False
    else:
        # Execução direta pelo cursor do driver Python (oracledb / cx_Oracle)
        cur = cfg.objeto_cursor
        conteudo = copia.read_text(encoding="utf-8").rstrip(";/ \n\r")
        try:
            if cfg.tipo_execucao_script == "PLSQL":
                cur.callproc("dbms_output.enable", [None])
                cur.execute(conteudo)
                cfg.objeto_conexao.commit()
                # Drena o buffer do DBMS_OUTPUT em lotes de 5000 linhas
                linhas_var = cur.arrayvar(str, 5000)
                qtd_var = cur.var(int)
                total_linhas = 0
                with caminho_relatorio.open("w", encoding="utf-8") as f:
                    while True:
                        qtd_var.setvalue(0, 5000)
                        cur.execute(
                            "BEGIN DBMS_OUTPUT.GET_LINES(:l, :n); END;",
                            l=linhas_var,
                            n=qtd_var,
                        )
                        qtd = qtd_var.getvalue() or 0
                        if not qtd:
                            break
                        for linha in linhas_var.getvalue()[:qtd]:
                            f.write((linha or "") + "\n")
                            total_linhas += 1
                logger.info(
                    "Bloco PL/SQL executado via Python DB em %.2fs (%d linha(s) DBMS_OUTPUT).",
                    time.monotonic() - t0_exec,
                    total_linhas,
                )
            else:
                cur.arraysize = TAMANHO_LOTE_FETCH
                cur.execute(conteudo)
                colunas = [c[0] for c in (cur.description or [])]
                total_linhas = 0
                with caminho_relatorio.open("w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f, delimiter=cfg.delimitador, quoting=csv.QUOTE_ALL)
                    if colunas:
                        w.writerow(colunas)
                    while True:
                        rows = cur.fetchmany(TAMANHO_LOTE_FETCH)
                        if not rows:
                            break
                        w.writerows(rows)
                        total_linhas += len(rows)
                logger.info(
                    "Consulta SQL executada via Python DB em %.2fs (%d registro(s) exportado(s)).",
                    time.monotonic() - t0_exec,
                    total_linhas,
                )
        except Exception as e:
            logger.error(
                "Falha durante a execução SQL/PLSQL via Python DB: %s",
                mascarar_credenciais(str(e)),
            )
            return False

    if not caminho_relatorio.is_file() or caminho_relatorio.stat().st_size == 0:
        if caminho_relatorio.is_file():
            remover_arquivo_seguro(caminho_relatorio)
        logger.info("Nenhum arquivo de saída gerado (ou saída vazia).")
        return cfg.tipo_execucao_script == "PLSQL"

    # Pós-processamento: particionamento por número de linhas e compactação ZIP
    arquivos = [caminho_relatorio]
    if cfg.quantidade_linhas_quebra > 0:
        partes = partir_arquivo_linhas(
            caminho_relatorio, cfg.quantidade_linhas_quebra, logger
        )
        if partes:
            remover_arquivo_seguro(caminho_relatorio)
            arquivos = partes

    for arq in arquivos:
        if cfg.compactar_arquivo == "S":
            zip_ok = compactar_em_zip(
                arq, logger, remover_original=(cfg.manter_original != "S")
            )
            cfg.arquivos_gerados.append(zip_ok if zip_ok else arq)
        else:
            cfg.arquivos_gerados.append(arq)
            logger.info(
                "Arquivo de saída disponível: %s (%s)",
                arq.name,
                formatar_bytes(arq.stat().st_size),
            )
    return True


def executar_pipeline(cfg: Configuracoes, logger: logging.Logger) -> bool:
    """Valida a conexão com o banco (quando aplicável) e dispara a execução do script."""
    ext = Path(cfg.nome_arquivo_script).suffix.lower()
    # Se for SQL/PLSQL, valida a conexão antes; para .py, valida apenas se houver conexao_bd configurada
    if ext != ".py" or cfg.conexao_bd:
        if cfg.ferramenta_tipo_execucao == "SQLPLUS" and not validar_conexao_sqlplus(
            cfg, logger
        ):
            return False
        if cfg.ferramenta_tipo_execucao == "PYTHON" and not validar_conexao_python(
            cfg, logger
        ):
            return False
    return executar_script(cfg, logger)


def main(argv: Optional[List[str]] = None) -> int:
    """Ponto de entrada principal da CLI do executor de scripts."""
    global FLAG_APAGA_ARQUIVO
    inicio_monotonic = time.monotonic()
    parser = ArgumentParserTraduzido(
        prog=NOME_ARQUIVO_SEM_EXTENSAO,
        description=AJUDA_DESCRICAO,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tipo_controle",
        default="TERMINAL",
        choices=["TERMINAL", "INPUT", "CONFIG"],
        help="Modo de operação: TERMINAL (via --tags), INPUT (lote com remoção) ou CONFIG (lote preservado).",
    )
    parser.add_argument(
        "--nome_arquivo_entrada",
        default=NOME_ARQUIVO_SEM_EXTENSAO,
        help="Prefixo dos arquivos de entrada a buscar nos modos INPUT ou CONFIG.",
    )
    parser.add_argument(
        "--tags",
        action="append",
        nargs="+",
        default=[],
        metavar="CHAVE=VALOR",
        help="Parâmetros e tags no formato CHAVE=VALOR (ex.: --tags trscript=consulta.sql ANO=2026).",
    )

    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    tags_achatadas = [t for grupo in args.tags for t in grupo]

    cfg = Configuracoes(args.tipo_controle, args.nome_arquivo_entrada)
    logger = configurar_logger(cfg)
    logar_cabecalho_execucao(cfg, logger)

    codigo_retorno = 1
    try:
        # ---------------------------------------------------------------------
        # Modo 1: TERMINAL — Execução única parametrizada via linha de comando
        # ---------------------------------------------------------------------
        if cfg.tipo_controle == "TERMINAL":
            if not tags_achatadas:
                logger.error(
                    "Modo TERMINAL exige ao menos um argumento --tags (ex.: --tags trscript=meu_script.sql)."
                )
                return 1

            # Desmembra tags passadas agrupadas numa única string via shlex nativo
            lista_tags_processadas = []
            for item in tags_achatadas:
                item_str = str(item).strip()
                if " " in item_str and "=" in item_str:
                    try:
                        lista_tags_processadas.extend(shlex.split(item_str))
                    except Exception:
                        lista_tags_processadas.extend(item_str.split())
                else:
                    lista_tags_processadas.append(item_str)

            logger.info(
                "Processando %d parâmetro(s) recebido(s) via linha de comando (--tags)...",
                len(lista_tags_processadas),
            )
            for item in lista_tags_processadas:
                k, sep, v = item.partition("=")
                if not sep or not k.strip():
                    raise ValueError(
                        "Formato inválido em --tags: {!r}. Use CHAVE=VALOR.".format(item)
                    )
                aplicar_parametro(cfg, k, v, logger)

            sucesso = executar_pipeline(cfg, logger)
            if sucesso:
                if not cfg.origem:
                    cfg.arquivos_ok.append(cfg.diretorio_script / cfg.nome_arquivo_script)
                else:
                    cfg.arquivos_ok.append(cfg.origem)
                    
            else:
                if not cfg.origem:
                    cfg.arquivos_erro.append(cfg.diretorio_script / cfg.nome_arquivo_script)
                else:
                    cfg.arquivos_erro.append(cfg.origem)            
            codigo_retorno = 0 if sucesso else 1
            return codigo_retorno

        # ---------------------------------------------------------------------
        # Modos 2 e 3: CONFIG / INPUT — Processamento em lote por arquivos
        # ---------------------------------------------------------------------
        arquivos = sorted(
            f
            for f in cfg.diretorio_entrada.glob("{}*".format(cfg.nome_arquivo_entrada))
            if (f.is_file() 
                and (f.name != cfg.nome_script
                     and f.name != cfg.nome_arquivo_script
                     and f.name != cfg.nome_arquivo_relatorio
                     and not str(f.name).strip().lower().endswith('.py')
                     and not str(f.name).strip().lower().endswith('.log')
                     and not str(f.name).strip().lower().endswith('.sql')
                    )
                and (str(f.name).strip().lower().endswith('.ini')
                     or str(f.name).strip().lower().endswith('.txt')
                     or str(f.name).strip().lower().endswith('.csv')
                     or str(f.name).strip().lower().endswith('.config')
                     or str(f.name).strip().lower().endswith('.conf')
                     or str(f.name).strip().lower().endswith('.json')
                     or str(f.name).strip().lower().endswith('.yaml')
                     or str(f.name).strip().lower().endswith('.yml')
                    )
                )
        )
           
        if not arquivos:
            logger.warning(
                "Nenhum arquivo de entrada encontrado em %s com o prefixo %r.",
                cfg.diretorio_entrada,
                cfg.nome_arquivo_entrada,
            )            
            FLAG_APAGA_ARQUIVO = False
        
        if not arquivos and cfg.diretorio_entrada != cfg.diretorio_script:
            arquivos = sorted(
                f
                for f in cfg.diretorio_script.glob("{}*".format(cfg.nome_arquivo_entrada))
                if (f.is_file() 
                    and (f.name != cfg.nome_script
                         and f.name != cfg.nome_arquivo_script
                         and f.name != cfg.nome_arquivo_relatorio
                         and not str(f.name).strip().lower().endswith('.py')
                         and not str(f.name).strip().lower().endswith('.log')
                         and not str(f.name).strip().lower().endswith('.sql')
                        )
                    and (str(f.name).strip().lower().endswith('.ini')
                         or str(f.name).strip().lower().endswith('.txt')
                         or str(f.name).strip().lower().endswith('.csv')
                         or str(f.name).strip().lower().endswith('.config')
                         or str(f.name).strip().lower().endswith('.conf')
                         or str(f.name).strip().lower().endswith('.json')
                         or str(f.name).strip().lower().endswith('.yaml')
                         or str(f.name).strip().lower().endswith('.yml')
                        )
                    )
            )
            if not arquivos:
                logger.warning(
                    "Nenhum arquivo de entrada encontrado em %s com o prefixo %r.",
                    cfg.diretorio_script,
                    cfg.nome_arquivo_entrada,
                )   
        
        if not arquivos and cfg.pasta_script != cfg.diretorio_script:
            arquivos = sorted(
                f
                for f in cfg.pasta_script.glob("{}*".format(cfg.nome_arquivo_entrada))
                if (f.is_file() 
                    and (f.name != cfg.nome_script
                         and f.name != cfg.nome_arquivo_script
                         and f.name != cfg.nome_arquivo_relatorio
                         and not str(f.name).strip().lower().endswith('.py')
                         and not str(f.name).strip().lower().endswith('.log')
                         and not str(f.name).strip().lower().endswith('.sql')
                        )
                    and (str(f.name).strip().lower().endswith('.ini')
                         or str(f.name).strip().lower().endswith('.txt')
                         or str(f.name).strip().lower().endswith('.csv')
                         or str(f.name).strip().lower().endswith('.config')
                         or str(f.name).strip().lower().endswith('.conf')
                         or str(f.name).strip().lower().endswith('.json')
                         or str(f.name).strip().lower().endswith('.yaml')
                         or str(f.name).strip().lower().endswith('.yml')
                        )
                    )
            )
            if not arquivos:
                logger.warning(
                    "Nenhum arquivo de entrada encontrado em %s com o prefixo %r.",
                    cfg.pasta_script,
                    cfg.nome_arquivo_entrada,
                )   
        
        if not arquivos:
            codigo_retorno = 0
            return codigo_retorno

        logger.info(
            "Encontrados %d arquivo(s) de lote para processamento no modo %s.",
            len(arquivos),
            cfg.tipo_controle,
        )
        for idx, arq in enumerate(arquivos, 1):
            logger.info("-" * 88)
            logger.info(
                "[Lote %d/%d] Processando arquivo de parâmetros: %s",
                idx,
                len(arquivos),
                arq.name,
            )
            cfg.resetar_padroes()
            copia = cfg.diretorio_saida / arq.name
            shutil.copy2(str(arq), str(copia))
            if cfg.tipo_controle == "INPUT" and FLAG_APAGA_ARQUIVO:
                remover_arquivo_seguro(arq)
                logger.info(
                    "Arquivo original removido da pasta de entrada (modo INPUT): %s",
                    arq.name,
                )

            try:
                for num_linha, linha_bruta in enumerate(
                    copia.read_text(encoding="utf-8").splitlines(), 1
                ):
                    linha = linha_bruta.strip()
                    if not linha or linha.startswith("#"):
                        continue
                    k, sep, v = linha.partition("=" if "=" in linha else ":")
                    if sep and k.strip():
                        aplicar_parametro(cfg, k, v, logger)
                    else:
                        logger.warning(
                            "Linha %d ignorada em %s (sem separador '=' ou ':'): %r",
                            num_linha,
                            copia.name,
                            linha,
                        )
                if executar_pipeline(cfg, logger):
                    cfg.arquivos_ok.append(copia)
                    logger.info("[Lote %d/%d] Concluído com SUCESSO: %s", idx, len(arquivos), copia.name)
                else:
                    cfg.arquivos_erro.append(copia)
                    logger.error("[Lote %d/%d] Concluído com FALHA: %s", idx, len(arquivos), copia.name)
            except Exception as e:
                logger.error(
                    "[Lote %d/%d] Erro ao processar %s: %s",
                    idx,
                    len(arquivos),
                    copia.name,
                    e,
                )
                cfg.arquivos_erro.append(copia)

        codigo_retorno = 0 if not cfg.arquivos_erro else 1
        return codigo_retorno

    except Exception as e:
        logger.error(
            "Falha crítica não tratada na execução: %s\n%s",
            mascarar_credenciais(str(e)),
            traceback.format_exc(),
        )
        codigo_retorno = 1
        return codigo_retorno
    finally:
        cfg.fechar_conexoes()
        logar_resumo_final(cfg, logger, inicio_monotonic, codigo_retorno)


if __name__ == "__main__":
    sys.exit(main())