# -*- coding: utf-8 -*-
"""multipart/form-data em fluxo (CR-021d1): leitura correta e recusa de corpo malformado ou grande demais."""
import io
import unittest

from tests.support import _testenv  # noqa: F401 - ajusta sys.path sem importar gluon
from sss.web.framework import multipart
from sss.web.framework.errors import HTTP

BOUNDARY = "----sssBoundary7MA4YWxk"
CONTENT_TYPE = "multipart/form-data; boundary=%s" % BOUNDARY
LIMITS = multipart.Limits(max_body_bytes=1 << 20, max_parts=10, max_header_bytes=1024, max_field_bytes=4096,
                          spool_memory_bytes=1024)


def _body(*parts, closing=True):
    """Corpo multipart a partir de (cabecalhos, conteudo) em bytes."""
    out = b""
    for headers, content in parts:
        out += b"--" + BOUNDARY.encode() + b"\r\n" + headers + b"\r\n\r\n" + content + b"\r\n"
    if closing:
        out += b"--" + BOUNDARY.encode() + b"--\r\n"
    return out


def _field(name, value):
    return (b'Content-Disposition: form-data; name="' + name + b'"', value)


def _file(name, filename, content):
    return (b'Content-Disposition: form-data; name="' + name + b'"; filename="' + filename + b'"\r\n'
            b"Content-Type: text/plain", content)


class _Drip(io.RawIOBase):
    """Fluxo que entrega no maximo ``size`` bytes por leitura (marcador cortado entre blocos)."""

    def __init__(self, data, size):
        self._data, self._size = data, size

    def readable(self):
        return True

    def read(self, n=-1):
        chunk, self._data = self._data[:self._size], self._data[self._size:]
        return chunk


def _parse(body, content_type=CONTENT_TYPE, length=None, limits=LIMITS, stream=None):
    stream = stream if stream is not None else io.BytesIO(body)
    return multipart.parse(stream, content_type, len(body) if length is None else length, limits)


class ParseTest(unittest.TestCase):
    """Corpo valido."""

    def test_fields_and_file(self):
        """Campos de texto em UTF-8, repetidos em ordem, e o arquivo com o nome preservado."""
        fields = _parse(_body(_field(b"environment", "PRODUÇÃO".encode()), _field(b"env", b"a"),
                              _field(b"env", b"b"), _file(b"file", "relatório final.csv".encode(), b"x;y\r\n1;2")))
        self.assertEqual([(k, v) for k, v in fields[:3]], [("environment", "PRODUÇÃO"), ("env", "a"), ("env", "b")])
        upload = fields[3][1]
        self.assertIsInstance(upload, multipart.UploadedFile)
        self.assertEqual((upload.name, upload.filename, upload.content_type),
                         ("file", "relatório final.csv", "text/plain"))
        self.assertEqual(upload.file.read(), b"x;y\r\n1;2")

    def test_boundary_split_between_chunks(self):
        """O delimitador cortado entre leituras de 1, 3 e 7 bytes e achado; conteudo com '--' parcial fica."""
        content = b"--" + BOUNDARY.encode()[:-1] + b"\r\n--quase"
        body = _body(_file(b"file", b"a.bin", content), _field(b"z", b"1"))
        for size in (1, 3, 7):
            with self.subTest(size=size):
                fields = _parse(body, stream=_Drip(body, size))
                self.assertEqual(fields[0][1].file.read(), content)
                self.assertEqual(fields[1], ("z", "1"))

    def test_large_file_goes_to_disk_without_whole_body_in_memory(self):
        """Arquivo maior que o spool vai para o temporario em disco, com o conteudo integro."""
        content = bytes(range(256)) * 400
        upload = _parse(_body(_file(b"file", b"big.bin", content)))[0][1]
        self.assertEqual(upload.file.read(), content)
        # _rolled e do SpooledTemporaryFile em todas as versoes (3.6 a 3.13): True = foi para o disco.
        self.assertTrue(upload.file._rolled, "passou do spool de 1 KiB")

    def test_empty_filename_is_still_a_file(self):
        """Formulario enviado sem escolher arquivo: filename vazio (o service recusa com a mensagem dele)."""
        upload = _parse(_body(_file(b"file", b"", b"")))[0][1]
        self.assertEqual((upload.filename, upload.file.read()), ("", b""))

    def test_quoted_name_with_semicolon_and_escaped_quote(self):
        """Parametro entre aspas com ';' e aspas escapadas."""
        headers = b'Content-Disposition: form-data; name="a;b"; filename="x\\"y.txt"'
        upload = _parse(_body((headers, b"1")))[0][1]
        self.assertEqual((upload.name, upload.filename), ("a;b", 'x"y.txt'))


class AttackTest(unittest.TestCase):
    """Corpo malformado ou grande demais."""

    def assertStatus(self, status, body, **kwargs):
        with self.assertRaises(HTTP) as ctx:
            _parse(body, **kwargs)
        self.assertEqual(ctx.exception.status, status)

    def test_body_above_limit_is_refused_before_reading(self):
        """Content-Length acima do limite: 413 sem ler nada do fluxo."""
        stream = io.BytesIO(b"nunca lido")
        with self.assertRaises(HTTP) as ctx:
            multipart.parse(stream, CONTENT_TYPE, LIMITS.max_body_bytes + 1, LIMITS)
        self.assertEqual((ctx.exception.status, stream.tell()), (413, 0))

    def test_content_length_shorter_than_body(self):
        """Content-Length menor que o corpo: le so o declarado e o corpo fica truncado (400)."""
        body = _body(_field(b"a", b"1"))
        self.assertStatus(400, body, length=len(body) - 10)

    def test_content_length_longer_than_body(self):
        """Content-Length maior que o que chegou: corpo truncado (400), sem esperar para sempre."""
        body = _body(_field(b"a", b"1"))
        self.assertStatus(400, body, length=len(body) + 100)

    def test_missing_closing_delimiter(self):
        """Sem o delimitador final: 400."""
        self.assertStatus(400, _body(_field(b"a", b"1"), closing=False))

    def test_bad_or_missing_boundary(self):
        """Boundary ausente, vazio, longo demais ou com caractere proibido: 400."""
        for content_type in ("multipart/form-data", "multipart/form-data; boundary=",
                             "multipart/form-data; boundary=%s" % ("x" * 71),
                             "multipart/form-data; boundary=a<b", "text/plain; boundary=abc"):
            with self.subTest(content_type=content_type):
                self.assertStatus(400, _body(_field(b"a", b"1")), content_type=content_type)

    def test_too_many_parts(self):
        """Mais partes que o limite: 413."""
        self.assertStatus(413, _body(*[_field(b"f", b"1")] * (LIMITS.max_parts + 1)))

    def test_huge_part_header(self):
        """Cabecalho de parte acima do limite: 400 sem acumular o resto."""
        headers = b'Content-Disposition: form-data; name="a"\r\nX-Junk: ' + b"j" * 5000
        self.assertStatus(400, _body((headers, b"1")))

    def test_text_field_above_limit(self):
        """Campo de texto acima do limite: 413 (arquivo nao tem esse teto, so o do corpo)."""
        self.assertStatus(413, _body(_field(b"a", b"x" * (LIMITS.max_field_bytes + 1))))

    def test_part_without_name_or_disposition(self):
        """Parte sem Content-Disposition form-data ou sem name: 400."""
        for headers in (b"Content-Type: text/plain", b'Content-Disposition: attachment; name="a"',
                        b"Content-Disposition: form-data"):
            with self.subTest(headers=headers):
                self.assertStatus(400, _body((headers, b"1")))

    def test_invalid_utf8(self):
        """UTF-8 invalido no campo ou no cabecalho da parte: 400."""
        self.assertStatus(400, _body(_field(b"a", b"\xff\xfe")))
        self.assertStatus(400, _body(_file(b"file", b"\xff.txt", b"1")))

    def test_garbage_after_delimiter(self):
        """Delimitador seguido de algo que nao e fim de linha nem '--': 400."""
        body = b"--" + BOUNDARY.encode() + b"XX\r\n" + _body(_field(b"a", b"1"))
        self.assertStatus(400, body)


if __name__ == "__main__":
    unittest.main()
