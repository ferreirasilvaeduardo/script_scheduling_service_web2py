# -*- coding: utf-8 -*-
"""Massa de teste da homologacao real (capture_evidence.js), no input_dir do agente do DEV.

Uso: python3 gerar_massa.py [--config <config.ini>] [--lote-mb 4608]
(padrao: instance/agente0001/config.ini, CR-028; sem input_dir no arquivo, var/<nome>/input)

Cria (o conteudo nao e conferido pelo roteiro, so o resultado da execucao):
  gfpreprod/contar_linhas_arquivo/clientes_20261022.txt   texto, 5.000 linhas
  clone6/contar_linhas_arquivo/notas_20261022.txt         texto, 3.000 linhas
  clone2/gerar_hash_arquivo/extrato_20261022.csv          CSV, 2.000 linhas
  gfpreprod/zipar_arquivos/lote_20261022/                 lote de texto do ticket longo
O lote padrao (4,5 GB) leva cerca de 4 minutos no zip nivel 9: as telas de "Rodando" e o
cancelamento em execucao precisam desse tempo. Pastas novas com 0700, arquivos com 0600 (como a
pasta de entrada do agente). Arquivo que ja existe e mantido: rodar de novo e barato.
Deterministico (mesma semente).
"""
import argparse
import configparser
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
WORDS = ("cliente", "nota", "fiscal", "valor", "saldo", "conta", "pedido", "item", "produto",
         "cidade", "estado", "codigo", "data", "pagamento", "boleto", "remessa", "retorno", "lote",
         "parcela", "imposto")
BLOCK_LINES = 20000


def input_dir(config):
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
    cp.read(config, encoding="utf-8")
    value = cp.get("agent", "input_dir", fallback=None)
    name = cp.get("app", "name", fallback="").strip()
    if value is None and name:
        # CR-028: sem a chave, a pasta sai do nome do processo (var/<nome>/input).
        value = os.path.join(APP, "var", name, "input")
    value = (value or "").strip()
    if not value:
        raise SystemExit("input_dir vazio no %s: a homologacao precisa da pasta de entrada"
                         % config)
    return value


def _line(rnd, n):
    words = " ".join(rnd.choice(WORDS) for _ in range(6))
    return "%08d;%s;%s;%d.%02d;%s\n" % (n, rnd.choice(WORDS), words, rnd.randint(1, 99999),
                                        rnd.randint(0, 99), rnd.choice(WORDS).upper())


def _file(path, lines, header=None):
    if os.path.isfile(path):
        return "mantido"
    os.makedirs(os.path.dirname(path), 0o700, exist_ok=True)
    rnd = random.Random(path)
    with open(path, "w", encoding="utf-8") as f:
        if header:
            f.write(header)
        for n in range(1, lines + 1):
            f.write(_line(rnd, n))
    os.chmod(path, 0o600)
    return "criado"


def _lote(folder, total_mb):
    """Arquivos de ~256 MB: um bloco de texto variado repetido com o numero do bloco (o deflate
    so enxerga 32 KB para tras, entao a repeticao do bloco nao acelera a compressao)."""
    os.makedirs(folder, 0o700, exist_ok=True)
    rnd = random.Random("lote")
    block = "".join(_line(rnd, n) for n in range(BLOCK_LINES)).encode("utf-8")
    per_file = 256 * 1024 * 1024
    files = max(1, (total_mb * 1024 * 1024) // per_file)
    states = []
    for i in range(files):
        path = os.path.join(folder, "parte_%03d.txt" % (i + 1))
        if os.path.isfile(path) and os.path.getsize(path) >= per_file:
            states.append("mantido")
            continue
        with open(path, "wb") as f:
            written, k = 0, 0
            while written < per_file:
                chunk = (b"# bloco %d\n" % k) + block
                f.write(chunk)
                written += len(chunk)
                k += 1
        os.chmod(path, 0o600)
        states.append("criado")
    return "%d arquivo(s): %d criado(s), %d mantido(s)" % (
        files, states.count("criado"), states.count("mantido"))


def main():
    parser = argparse.ArgumentParser(description="Massa de teste da homologacao real")
    parser.add_argument("--config",
                        default=os.path.join(APP, "instance", "agente0001", "config.ini"))
    parser.add_argument("--lote-mb", type=int, default=4608,
                        help="tamanho do lote do zipar_arquivos (MB)")
    args = parser.parse_args()
    base = input_dir(args.config)
    print("input_dir:", base)
    count = os.path.join(base, "gfpreprod", "contar_linhas_arquivo", "clientes_20261022.txt")
    print("clientes:", _file(count, 5000))
    notes = os.path.join(base, "clone6", "contar_linhas_arquivo", "notas_20261022.txt")
    print("notas:", _file(notes, 3000))
    statement = os.path.join(base, "clone2", "gerar_hash_arquivo", "extrato_20261022.csv")
    print("extrato:", _file(statement, 2000, header="id;tipo;descricao;valor;status\n"))
    lote = os.path.join(base, "gfpreprod", "zipar_arquivos", "lote_20261022")
    print("lote:", _lote(lote, args.lote_mb))


if __name__ == "__main__":
    main()
