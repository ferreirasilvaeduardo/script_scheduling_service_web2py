# -*- coding: utf-8 -*-
"""Primitivas de seguranca do SSS (README §4.2): hash de senha, CSRF, Origin e cookies.

Modulo puro: nao importa gluon (AGENTS §7.1).
"""
import hashlib
import hmac
import http.cookies
import ipaddress
import re
import secrets
import urllib.parse

ALGORITMO = "pbkdf2_sha256"
ITERACOES = 200000
SALT_BYTES = 16
SENHA_MIN = 12
CSRF_BYTES = 32

_RE_HASH = re.compile(r"pbkdf2_sha256\$([0-9]{1,7})\$([0-9a-f]{32})\$([0-9a-f]{64})")
# Host (nome DNS/IPv4 ou IPv6 entre colchetes) e porta opcional; userinfo ('@') e rejeitado.
_RE_NETLOC = re.compile(r"([a-z0-9.\-]+|\[[0-9a-f:.]+\])(?::([0-9]{1,5}))?")
_PORTA_PADRAO = {"http": 80, "https": 443}
_RE_COOKIE_ASCII = re.compile(r"[\x21-\x7e]*")
_RE_NEXT = re.compile(r"[\x21-\x7e]{1,512}")
PREFIXO_APP = "/script_scheduling_service/"
IP_MAX = 45


def _derivar(senha, salt, iteracoes):
    return hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, iteracoes)


def _decompor(armazenado):
    if not isinstance(armazenado, str):
        return None
    m = _RE_HASH.fullmatch(armazenado)
    if not m:
        return None
    iteracoes = int(m.group(1))
    if iteracoes < 1:
        return None
    return iteracoes, bytes.fromhex(m.group(2)), bytes.fromhex(m.group(3))


def hash_senha(senha):
    """Gera o hash 'pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>' da senha."""
    if not isinstance(senha, str):
        raise TypeError("senha deve ser str")
    salt = secrets.token_bytes(SALT_BYTES)
    dk = _derivar(senha, salt, ITERACOES)
    return "%s$%d$%s$%s" % (ALGORITMO, ITERACOES, salt.hex(), dk.hex())


def verificar_senha(senha, armazenado):
    """True se a senha confere com o hash armazenado; formato invalido ou '!' resulta em False."""
    if not isinstance(senha, str):
        return False
    partes = _decompor(armazenado)
    if partes is None:
        return False
    iteracoes, salt, esperado = partes
    return hmac.compare_digest(_derivar(senha, salt, iteracoes), esperado)


def hash_reconhecido(armazenado):
    """True se o valor armazenado tem o formato de hash vigente (senha utilizavel)."""
    return _decompor(armazenado) is not None


def precisa_rehash(armazenado):
    """True se o hash e valido mas usa menos iteracoes que o vigente."""
    partes = _decompor(armazenado)
    return partes is not None and partes[0] < ITERACOES


_HASH_FICTICIO = hash_senha(secrets.token_hex(16))


def hash_ficticio():
    """Hash pre-computado para equalizar o tempo de resposta de login inexistente."""
    return _HASH_FICTICIO


def validar_politica_senha(senha):
    """Lista de mensagens de violacao da politica de senha (vazia se valida)."""
    if not isinstance(senha, str) or len(senha) < SENHA_MIN:
        return [u"A senha deve ter no mínimo %d caracteres." % SENHA_MIN]
    return []


def gerar_token_csrf():
    """Token sincronizador CSRF (32 bytes aleatorios, urlsafe)."""
    return secrets.token_urlsafe(CSRF_BYTES)


def validar_token_csrf(esperado, recebido):
    """Compara os tokens em tempo constante; ausentes ou vazios resultam em False."""
    if not isinstance(esperado, str) or not isinstance(recebido, str):
        return False
    if not esperado or not recebido:
        return False
    return hmac.compare_digest(esperado.encode("utf-8"), recebido.encode("utf-8"))


def normalizar_origem(url):
    """Retorna (esquema, host, porta) de uma URL http(s) ou None se invalida."""
    if not isinstance(url, str) or not url:
        return None
    partes = urllib.parse.urlsplit(url.strip())
    esquema = partes.scheme.lower()
    if esquema not in _PORTA_PADRAO:
        return None
    m = _RE_NETLOC.fullmatch(partes.netloc.lower())
    if not m:
        return None
    porta = int(m.group(2)) if m.group(2) else _PORTA_PADRAO[esquema]
    if not 1 <= porta <= 65535:
        return None
    return esquema, m.group(1), porta


def origem_permitida(origin, referer, allowed_origins):
    """Valida Origin (ou, na sua ausencia, a origem do Referer) contra a lista permitida.

    Compara esquema, host e porta exatos. Sem nenhum dos dois cabecalhos, rejeita.
    """
    fonte = origin if origin else referer
    alvo = normalizar_origem(fonte)
    if alvo is None:
        return False
    for permitida in allowed_origins or ():
        if normalizar_origem(permitida) == alvo:
            return True
    return False


def sessao_expirada(ultimo_acesso, agora, timeout_s):
    """True se a sessao esta ociosa ha mais de timeout_s segundos (ou sem marca valida)."""
    if not isinstance(ultimo_acesso, (int, float)) or isinstance(ultimo_acesso, bool):
        return True
    return (agora - ultimo_acesso) > timeout_s


class CookiesSeguros(http.cookies.SimpleCookie):
    """SimpleCookie que marca HttpOnly (e Secure, se pedido) em todo cookie atribuido.

    SameSite nao e tratado aqui: no Python 3.6 o Morsel rejeita o atributo (README §4.2).
    """

    def __init__(self, secure=True, input=None):
        self.secure = secure
        super(CookiesSeguros, self).__init__(input)

    def _proteger(self, morsel):
        morsel["httponly"] = True
        if self.secure:
            morsel["secure"] = True

    def __setitem__(self, key, value):
        # secure_dumps do web2py devolve bytes; sem decodificar, o cookie sairia como "b'...'".
        if isinstance(value, bytes):
            value = value.decode("ascii")
        super(CookiesSeguros, self).__setitem__(key, value)
        self._proteger(dict.__getitem__(self, key))

    def adotar(self, cookies):
        """Copia os morsels de outro SimpleCookie aplicando as protecoes."""
        for chave, morsel in cookies.items():
            dict.__setitem__(self, chave, morsel)
            self._proteger(morsel)


def adaptar_cookie_sessao(cookies, nome):
    """Converte para bytes o valor do cookie de sessao recebido, formato que o secure_loads exige.

    Valor fora de ASCII imprimivel e descartado (sessao vazia) em vez de gerar erro.
    """
    morsel = cookies.get(nome)
    if morsel is None or not isinstance(morsel.value, str):
        return
    if _RE_COOKIE_ASCII.fullmatch(morsel.value):
        morsel.set(morsel.key, morsel.value.encode("ascii"), morsel.coded_value)
    else:
        del cookies[nome]


def validar_next(valor, prefixo=PREFIXO_APP):
    """Retorna o destino pos-login se for caminho local da aplicacao; senao None (open redirect)."""
    if not isinstance(valor, str) or not _RE_NEXT.fullmatch(valor):
        return None
    if "\\" in valor or "//" in valor or not valor.startswith(prefixo):
        return None
    partes = urllib.parse.urlsplit(valor)
    if partes.scheme or partes.netloc:
        return None
    caminho = urllib.parse.unquote(partes.path)
    if "\\" in caminho or "//" in caminho or ".." in caminho.split("/") or not caminho.startswith(prefixo):
        return None
    return valor


def _ip_normalizado(texto):
    if not isinstance(texto, str):
        return None
    try:
        return str(ipaddress.ip_address(texto.strip()))
    except ValueError:
        return None


def ip_origem(remote_addr, x_forwarded_for, trusted_proxies):
    """IP do cliente: remote_addr, ou o X-Forwarded-For quando remote_addr e proxy confiavel.

    No XFF, percorre da direita para a esquerda e devolve o primeiro IP nao confiavel.
    """
    confiaveis = frozenset(ip for ip in (_ip_normalizado(t) for t in (trusted_proxies or ())) if ip)
    remoto = _ip_normalizado(remote_addr)
    if remoto is None:
        return None
    if remoto not in confiaveis or not isinstance(x_forwarded_for, str):
        return remoto[:IP_MAX]
    for item in reversed(x_forwarded_for.split(",")):
        ip = _ip_normalizado(item)
        if ip is None:
            return remoto[:IP_MAX]
        if ip not in confiaveis:
            return ip[:IP_MAX]
    return remoto[:IP_MAX]
