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

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 200000
SALT_BYTES = 16
PASSWORD_MIN = 12
CSRF_BYTES = 32

_RE_HASH = re.compile(r"pbkdf2_sha256\$([0-9]{1,7})\$([0-9a-f]{32})\$([0-9a-f]{64})")
# Host (nome DNS/IPv4 ou IPv6 entre colchetes) e porta opcional; userinfo ('@') e rejeitado.
_RE_NETLOC = re.compile(r"([a-z0-9.\-]+|\[[0-9a-f:.]+\])(?::([0-9]{1,5}))?")
_DEFAULT_PORTS = {"http": 80, "https": 443}
_RE_COOKIE_ASCII = re.compile(r"[\x21-\x7e]*")
_RE_NEXT = re.compile(r"[\x21-\x7e]{1,512}")
APP_PREFIX = "/script_scheduling_service/"
IP_MAX = 45


def _derive(senha, salt, iteracoes):
    return hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, iteracoes)


def _split_hash(armazenado):
    if not isinstance(armazenado, str):
        return None
    m = _RE_HASH.fullmatch(armazenado)
    if not m:
        return None
    iteracoes = int(m.group(1))
    if iteracoes < 1:
        return None
    return iteracoes, bytes.fromhex(m.group(2)), bytes.fromhex(m.group(3))


def hash_password(senha):
    """Gera o hash 'pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>' da senha."""
    if not isinstance(senha, str):
        raise TypeError("senha deve ser str")
    salt = secrets.token_bytes(SALT_BYTES)
    dk = _derive(senha, salt, ITERATIONS)
    return "%s$%d$%s$%s" % (ALGORITHM, ITERATIONS, salt.hex(), dk.hex())


def verify_password(senha, armazenado):
    """True se a senha confere com o hash armazenado; formato invalido ou '!' resulta em False."""
    if not isinstance(senha, str):
        return False
    partes = _split_hash(armazenado)
    if partes is None:
        return False
    iteracoes, salt, esperado = partes
    return hmac.compare_digest(_derive(senha, salt, iteracoes), esperado)


def is_known_hash(armazenado):
    """True se o valor armazenado tem o formato de hash vigente (senha utilizavel)."""
    return _split_hash(armazenado) is not None


def needs_rehash(armazenado):
    """True se o hash e valido mas usa menos iteracoes que o vigente."""
    partes = _split_hash(armazenado)
    return partes is not None and partes[0] < ITERATIONS


_DUMMY_HASH = hash_password(secrets.token_hex(16))


def dummy_hash():
    """Hash pre-computado para equalizar o tempo de resposta de login inexistente."""
    return _DUMMY_HASH


def validate_password_policy(senha):
    """Lista de mensagens de violacao da politica de senha (vazia se valida)."""
    if not isinstance(senha, str) or len(senha) < PASSWORD_MIN:
        return [u"A senha deve ter no mínimo %d caracteres." % PASSWORD_MIN]
    return []


def strip_passwords(origens, campos):
    """Remove os campos de senha de todos os dicts de variaveis da requisicao e devolve seus valores.

    O ticket de erro do web2py grava request.vars/post_vars: as senhas saem deles assim que lidas.
    origens: dicts na ordem de prioridade (ex.: post_vars, vars); valor nao str (ou lista) vira None.
    """
    senhas = {}
    for campo in campos:
        valor = None
        for origem in origens:
            achado = origem.pop(campo, None)
            if valor is None:
                valor = achado
        if isinstance(valor, list):
            valor = valor[-1] if valor else None
        senhas[campo] = valor if isinstance(valor, str) else None
    return senhas


def generate_csrf_token():
    """Token sincronizador CSRF (32 bytes aleatorios, urlsafe)."""
    return secrets.token_urlsafe(CSRF_BYTES)


def validate_csrf_token(esperado, recebido):
    """Compara os tokens em tempo constante; ausentes ou vazios resultam em False."""
    if not isinstance(esperado, str) or not isinstance(recebido, str):
        return False
    if not esperado or not recebido:
        return False
    return hmac.compare_digest(esperado.encode("utf-8"), recebido.encode("utf-8"))


def normalize_origin(url):
    """Retorna (esquema, host, porta) de uma URL http(s) ou None se invalida."""
    if not isinstance(url, str) or not url:
        return None
    partes = urllib.parse.urlsplit(url.strip())
    esquema = partes.scheme.lower()
    if esquema not in _DEFAULT_PORTS:
        return None
    m = _RE_NETLOC.fullmatch(partes.netloc.lower())
    if not m:
        return None
    porta = int(m.group(2)) if m.group(2) else _DEFAULT_PORTS[esquema]
    if not 1 <= porta <= 65535:
        return None
    return esquema, m.group(1), porta


def is_allowed_origin(origin, referer, allowed_origins):
    """Valida Origin (ou, na sua ausencia, a origem do Referer) contra a lista permitida.

    Compara esquema, host e porta exatos. Sem nenhum dos dois cabecalhos, rejeita.
    """
    fonte = origin if origin else referer
    alvo = normalize_origin(fonte)
    if alvo is None:
        return False
    for permitida in allowed_origins or ():
        if normalize_origin(permitida) == alvo:
            return True
    return False


def is_session_expired(ultimo_acesso, agora, timeout_s):
    """True se a sessao esta ociosa ha mais de timeout_s segundos (ou sem marca valida)."""
    if not isinstance(ultimo_acesso, (int, float)) or isinstance(ultimo_acesso, bool):
        return True
    return (agora - ultimo_acesso) > timeout_s


class SecureCookies(http.cookies.SimpleCookie):
    """SimpleCookie que marca HttpOnly (e Secure, se pedido) em todo cookie atribuido.

    SameSite nao e tratado aqui: no Python 3.6 o Morsel rejeita o atributo (README §4.2).
    """

    def __init__(self, secure=True, input=None):
        self.secure = secure
        super(SecureCookies, self).__init__(input)

    def _protect(self, morsel):
        morsel["httponly"] = True
        if self.secure:
            morsel["secure"] = True

    def __setitem__(self, key, value):
        # secure_dumps do web2py devolve bytes; sem decodificar, o cookie sairia como "b'...'".
        if isinstance(value, bytes):
            value = value.decode("ascii")
        super(SecureCookies, self).__setitem__(key, value)
        self._protect(dict.__getitem__(self, key))

    def adopt(self, cookies):
        """Copia os morsels de outro SimpleCookie aplicando as protecoes."""
        for chave, morsel in cookies.items():
            dict.__setitem__(self, chave, morsel)
            self._protect(morsel)


def adapt_session_cookie(cookies, nome):
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


def validate_next(valor, prefixo=APP_PREFIX):
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


def _normalized_ip(texto):
    if not isinstance(texto, str):
        return None
    try:
        return str(ipaddress.ip_address(texto.strip()))
    except ValueError:
        return None


def client_ip(remote_addr, x_forwarded_for, trusted_proxies):
    """IP do cliente: remote_addr, ou o X-Forwarded-For quando remote_addr e proxy confiavel.

    No XFF, percorre da direita para a esquerda e devolve o primeiro IP nao confiavel.
    """
    confiaveis = frozenset(ip for ip in (_normalized_ip(t) for t in (trusted_proxies or ())) if ip)
    remoto = _normalized_ip(remote_addr)
    if remoto is None:
        return None
    if remoto not in confiaveis or not isinstance(x_forwarded_for, str):
        return remoto[:IP_MAX]
    for item in reversed(x_forwarded_for.split(",")):
        ip = _normalized_ip(item)
        if ip is None:
            return remoto[:IP_MAX]
        if ip not in confiaveis:
            return ip[:IP_MAX]
    return remoto[:IP_MAX]
