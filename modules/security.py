# -*- coding: utf-8 -*-
"""Primitivas de seguranca do SSS (README §4.2): hash de senha, CSRF, Origin, next e IP do cliente.

Modulo puro: nao importa gluon (AGENTS §7.1).
"""
import hashlib
import hmac
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
_RE_NEXT = re.compile(r"[\x21-\x7e]{1,512}")
APP_PREFIX = "/script_scheduling_service/"
IP_MAX = 45


def _derive(password_value, salt, iterations):
    return hashlib.pbkdf2_hmac("sha256", password_value.encode("utf-8"), salt, iterations)


def _split_hash(stored):
    if not isinstance(stored, str):
        return None
    m = _RE_HASH.fullmatch(stored)
    if not m:
        return None
    iterations = int(m.group(1))
    if iterations < 1:
        return None
    return iterations, bytes.fromhex(m.group(2)), bytes.fromhex(m.group(3))


def hash_password(password_value):
    """Gera o hash 'pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>' da senha."""
    if not isinstance(password_value, str):
        raise TypeError("senha deve ser str")
    salt = secrets.token_bytes(SALT_BYTES)
    dk = _derive(password_value, salt, ITERATIONS)
    return "%s$%d$%s$%s" % (ALGORITHM, ITERATIONS, salt.hex(), dk.hex())


def verify_password(password_value, stored):
    """True se a senha confere com o hash armazenado; formato invalido ou '!' resulta em False."""
    if not isinstance(password_value, str):
        return False
    parts = _split_hash(stored)
    if parts is None:
        return False
    iterations, salt, expected = parts
    return hmac.compare_digest(_derive(password_value, salt, iterations), expected)


def is_known_hash(stored):
    """True se o valor armazenado tem o formato de hash vigente (senha utilizavel)."""
    return _split_hash(stored) is not None


def needs_rehash(stored):
    """True se o hash e valido mas usa menos iteracoes que o vigente."""
    parts = _split_hash(stored)
    return parts is not None and parts[0] < ITERATIONS


_DUMMY_HASH = hash_password(secrets.token_hex(16))


def dummy_hash():
    """Hash pre-computado para equalizar o tempo de resposta de login inexistente."""
    return _DUMMY_HASH


def validate_password_policy(password_value):
    """Lista de mensagens de violacao da politica de senha (vazia se valida)."""
    if not isinstance(password_value, str) or len(password_value) < PASSWORD_MIN:
        return [u"A senha deve ter no mínimo %d caracteres." % PASSWORD_MIN]
    return []


def strip_passwords(sources, fields):
    """Remove os campos de senha de todos os dicts de variaveis da requisicao e devolve seus valores.

    Defesa em profundidade: as senhas saem de request.vars/post_vars assim que lidas, para nenhum
    registro de erro ou depuracao as encontrar (era o ticket de erro do web2py ate o CR-021e).
    origens: dicts na ordem de prioridade (ex.: post_vars, vars); valor nao str (ou lista) vira None.
    """
    passwords = {}
    for field in fields:
        value = None
        for source in sources:
            found = source.pop(field, None)
            if value is None:
                value = found
        if isinstance(value, list):
            value = value[-1] if value else None
        passwords[field] = value if isinstance(value, str) else None
    return passwords


def generate_csrf_token():
    """Token sincronizador CSRF (32 bytes aleatorios, urlsafe)."""
    return secrets.token_urlsafe(CSRF_BYTES)


def validate_csrf_token(expected, received):
    """Compara os tokens em tempo constante; ausentes ou vazios resultam em False."""
    if not isinstance(expected, str) or not isinstance(received, str):
        return False
    if not expected or not received:
        return False
    return hmac.compare_digest(expected.encode("utf-8"), received.encode("utf-8"))


def normalize_origin(url):
    """Retorna (esquema, host, porta) de uma URL http(s) ou None se invalida."""
    if not isinstance(url, str) or not url:
        return None
    parts = urllib.parse.urlsplit(url.strip())
    schema = parts.scheme.lower()
    if schema not in _DEFAULT_PORTS:
        return None
    m = _RE_NETLOC.fullmatch(parts.netloc.lower())
    if not m:
        return None
    port = int(m.group(2)) if m.group(2) else _DEFAULT_PORTS[schema]
    if not 1 <= port <= 65535:
        return None
    return schema, m.group(1), port


def is_allowed_origin(origin, referer, allowed_origins):
    """Valida Origin (ou, na sua ausencia, a origem do Referer) contra a lista permitida.

    Compara esquema, host e porta exatos. Sem nenhum dos dois cabecalhos, rejeita.
    """
    source = origin if origin else referer
    target = normalize_origin(source)
    if target is None:
        return False
    for allowed in allowed_origins or ():
        if normalize_origin(allowed) == target:
            return True
    return False


def is_session_expired(last_access, now, timeout_s):
    """True se a sessao esta ociosa ha mais de timeout_s segundos (ou sem marca valida)."""
    if not isinstance(last_access, (int, float)) or isinstance(last_access, bool):
        return True
    return (now - last_access) > timeout_s


def validate_next(value, prefix=APP_PREFIX):
    """Retorna o destino pos-login se for caminho local da aplicacao; senao None (open redirect)."""
    if not isinstance(value, str) or not _RE_NEXT.fullmatch(value):
        return None
    if "\\" in value or "//" in value or not value.startswith(prefix):
        return None
    parts = urllib.parse.urlsplit(value)
    if parts.scheme or parts.netloc:
        return None
    path = urllib.parse.unquote(parts.path)
    if "\\" in path or "//" in path or ".." in path.split("/") or not path.startswith(prefix):
        return None
    return value


def _normalized_ip(text):
    if not isinstance(text, str):
        return None
    try:
        return str(ipaddress.ip_address(text.strip()))
    except ValueError:
        return None


def client_ip(remote_addr, x_forwarded_for, trusted_proxies):
    """IP do cliente: remote_addr, ou o X-Forwarded-For quando remote_addr e proxy confiavel.

    No XFF, percorre da direita para a esquerda e devolve o primeiro IP nao confiavel.
    """
    trusted = frozenset(ip for ip in (_normalized_ip(t) for t in (trusted_proxies or ())) if ip)
    remote = _normalized_ip(remote_addr)
    if remote is None:
        return None
    if remote not in trusted or not isinstance(x_forwarded_for, str):
        return remote[:IP_MAX]
    for item in reversed(x_forwarded_for.split(",")):
        ip = _normalized_ip(item)
        if ip is None:
            return remote[:IP_MAX]
        if ip not in trusted:
            return ip[:IP_MAX]
    return remote[:IP_MAX]
