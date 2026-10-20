# -*- coding: utf-8 -*-
"""Testes do bin/sss-helper (README §8.0, AGENTS §7.4; CR-008 R-01 e R-36), executado direto com o proprio
usuario (sem sudo): validacao de argumentos, identidade do grupo, pasta_base, limpeza sem seguir links e
o run com cwd, umask e entrada padrao nula."""
import _testenv  # noqa: F401

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

WEB2PY = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
HELPER = os.path.join(WEB2PY, "bin", "sss-helper")


_COPIA = {}


def setUpModule():
    # O helper nao tem sufixo .py: uma copia numa pasta temporaria permite importa-lo para os dubles.
    _COPIA["pasta"] = tempfile.mkdtemp(prefix="sss_helper_mod_")
    shutil.copy(HELPER, os.path.join(_COPIA["pasta"], "sss_helper_copia.py"))
    sys.path.insert(0, _COPIA["pasta"])


def tearDownModule():
    sys.path.remove(_COPIA["pasta"])
    sys.modules.pop("sss_helper_copia", None)
    shutil.rmtree(_COPIA["pasta"], ignore_errors=True)


def _carregar_helper():
    import sss_helper_copia
    return sss_helper_copia


def _helper(*args, **kw):
    """Executa o helper; devolve (codigo, stderr)."""
    p = subprocess.run([sys.executable, HELPER] + [str(a) for a in args], input=kw.get("entrada", b""),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    return p.returncode, p.stderr.decode("utf-8", "replace")


def _vivo(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            conteudo = f.read()
    except OSError:
        return False
    return conteudo[conteudo.rindex(")") + 2:].split()[0] != "Z"


def _esperar(condicao, prazo=10.0):
    limite = time.monotonic() + prazo
    while time.monotonic() < limite:
        if condicao():
            return True
        time.sleep(0.05)
    return condicao()


@unittest.skipIf(os.geteuid() == 0, "o helper roda como usuario de execucao, nunca root")
class TestSssHelper(unittest.TestCase):

    def setUp(self):
        self.raiz = os.path.realpath(tempfile.mkdtemp(prefix="sss_helper_"))
        self.base = os.path.join(self.raiz, "exec1")
        os.mkdir(self.base, 0o700)
        self.popens = []

    def tearDown(self):
        for p in self.popens:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
            p.wait()
        shutil.rmtree(self.raiz, ignore_errors=True)

    def grupo(self, cwd=None):
        p = subprocess.Popen(["sleep", "300"], start_new_session=True, cwd=cwd or self.raiz)
        self.popens.append(p)
        return p

    # -- uso invalido ---------------------------------------------------------

    def test_uso_invalido(self):
        for args in ((), ("xyz",), ("term",), ("term", "abc", "1"), ("term", "1", "1"), ("kill", "-5", "1"),
                     ("term", "100", "1", "extra"), ("limpar", self.base), ("limpar", self.base, "0"),
                     ("encerrar-ticket", self.base, "1"), ("encerrar-ticket", self.base, "1", "999"),
                     ("run", "extra")):
            codigo, erro = _helper(*args)
            self.assertEqual(codigo, 2, args)
            self.assertTrue(erro.startswith("sss-helper: "), erro)
            self.assertNotIn("Traceback", erro)

    def test_especificacao_invalida(self):
        valida = {"ticket_id": 1, "argv": ["/bin/true"], "env": {}, "pasta_base": self.base}
        casos = [b"nao e json", b"[1, 2]", b"\xff\xfe",
                 json.dumps(dict(valida, ticket_id=0)), json.dumps(dict(valida, ticket_id=True)),
                 json.dumps(dict(valida, argv=[])), json.dumps(dict(valida, argv=["true"])),
                 json.dumps(dict(valida, argv=["/bin/true", 3])), json.dumps(dict(valida, env={"A": 1})),
                 json.dumps(dict(valida, rlimits={"RLIMIT_RTPRIO": [0, 0]})),
                 json.dumps(dict(valida, rlimits={"RLIMIT_CORE": [0]})),
                 json.dumps(dict(valida, pasta_base="relativa")),
                 json.dumps(dict(valida, pasta_base=self.base + "/../exec1")),
                 b"{" + b" " * (1024 * 1024) + b"}"]
        for entrada in casos:
            entrada = entrada if isinstance(entrada, bytes) else entrada.encode("utf-8")
            self.assertEqual(_helper("run", entrada=entrada)[0], 2, entrada[:80])
        self.assertFalse(os.path.exists(os.path.join(self.base, "ticket_1")))

    # -- term / kill ------------------------------------------------------------

    def test_term_kill_com_identidade_divergente(self):
        helper = _carregar_helper()
        p = self.grupo()
        inicio = helper._identidade(p.pid)
        self.assertIsNotNone(inicio)
        for sub in ("term", "kill"):
            codigo, erro = _helper(sub, p.pid, inicio + 1)
            self.assertEqual(codigo, 3, sub)
            self.assertIn("identidade", erro)
        self.assertTrue(_vivo(p.pid))
        self.assertEqual(_helper("term", p.pid, inicio)[0], 0)
        p.wait(10)
        self.assertEqual(p.returncode, -signal.SIGTERM)
        q = self.grupo()
        self.assertEqual(_helper("kill", q.pid, helper._identidade(q.pid))[0], 0)
        q.wait(10)
        self.assertEqual(q.returncode, -signal.SIGKILL)

    def test_term_kill_com_grupo_vazio(self):
        p = self.grupo()
        os.killpg(p.pid, signal.SIGKILL)
        p.wait()
        for sub in ("term", "kill"):
            self.assertEqual(_helper(sub, p.pid, 12345)[0], 0, sub)

    def test_term_kill_recusam_grupo_de_outro_usuario(self):
        helper = _carregar_helper()
        for sub in (helper._term, helper._kill):
            with mock.patch.object(helper.os, "kill", side_effect=PermissionError()), \
                    mock.patch.object(helper.os, "killpg") as killpg:
                with self.assertRaises(helper.Falha) as ctx:
                    sub(4242, 1)
            self.assertEqual(ctx.exception.codigo, 3)
            killpg.assert_not_called()

    def test_identidade_com_parenteses_no_nome(self):
        helper = _carregar_helper()
        campos = " ".join(["S"] + [str(i) for i in range(4, 60)])
        with mock.patch("builtins.open", mock.mock_open(read_data="77 (a) b)) %s" % campos)):
            self.assertEqual(helper._identidade(77), 22)
        self.assertIsNone(helper._identidade(2 ** 31 - 2))

    # -- pasta_base -------------------------------------------------------------

    def _pastas_invalidas(self):
        link = os.path.join(self.raiz, "link_base")
        os.symlink(self.base, link)
        arquivo = os.path.join(self.raiz, "arquivo")
        open(arquivo, "w").close()
        return ("exec1", self.base + "/", os.path.join(self.base, "..", "exec1"), link,
                os.path.join(self.raiz, "nao_existe"), arquivo, "/")

    def test_limpar_e_encerrar_ticket_com_pasta_base_invalida(self):
        alvo = os.path.join(self.base, "ticket_4")
        os.mkdir(alvo)
        for pasta in self._pastas_invalidas():
            self.assertEqual(_helper("limpar", pasta, 4)[0], 2, pasta)
            self.assertEqual(_helper("encerrar-ticket", pasta, 4, 1)[0], 2, pasta)
        self.assertTrue(os.path.isdir(alvo), "nada removido pela pasta recusada")

    def test_pasta_base_de_outro_dono(self):
        helper = _carregar_helper()
        with mock.patch.object(helper.os, "geteuid", return_value=os.geteuid() + 1):
            with self.assertRaises(helper.Falha) as ctx:
                helper._pasta_base(self.base)
        self.assertEqual(ctx.exception.codigo, 2)

    def test_limpar_sem_seguir_links(self):
        fora = os.path.join(self.raiz, "fora")
        os.mkdir(fora)
        with open(os.path.join(fora, "precioso.txt"), "w") as f:
            f.write("x")
        pasta = os.path.join(self.base, "ticket_9")
        os.makedirs(os.path.join(pasta, "tmp"))
        os.symlink(fora, os.path.join(pasta, "tmp", "link_fora"))
        os.symlink(os.path.join(fora, "precioso.txt"), os.path.join(pasta, "link_arq"))
        self.assertEqual(_helper("limpar", self.base, 9)[0], 0)
        self.assertFalse(os.path.lexists(pasta))
        self.assertTrue(os.path.isfile(os.path.join(fora, "precioso.txt")))
        self.assertEqual(_helper("limpar", self.base, 9)[0], 0, "pasta ja ausente")
        os.symlink(fora, os.path.join(self.base, "ticket_10"))
        self.assertEqual(_helper("limpar", self.base, 10)[0], 2, "ticket_<id> que e link")
        self.assertTrue(os.path.isfile(os.path.join(fora, "precioso.txt")))

    # -- encerrar-ticket --------------------------------------------------------

    def test_encerrar_ticket_so_na_pasta_do_ticket(self):
        pasta = os.path.join(self.base, "ticket_3", "tmp")
        os.makedirs(pasta)
        vizinha = os.path.join(self.base, "ticket_30")
        os.mkdir(vizinha)
        dentro, fora = self.grupo(cwd=pasta), self.grupo(cwd=vizinha)
        self.assertTrue(_esperar(lambda: os.path.realpath("/proc/%d/cwd" % dentro.pid) == pasta))
        self.assertEqual(_helper("encerrar-ticket", self.base, 3, 2)[0], 0)
        dentro.wait(10)
        self.assertEqual(dentro.returncode, -signal.SIGTERM)
        self.assertTrue(_vivo(fora.pid))

    def test_encerrar_ticket_nao_suportado(self):
        helper = _carregar_helper()
        os.mkdir(os.path.join(self.base, "ticket_5"))
        isdir, exists, isfile = os.path.isdir, os.path.exists, os.path.isfile

        def _sem_proc(f):
            return lambda c: False if c.startswith("/proc") or c.endswith("pwdx") else f(c)

        with mock.patch.object(helper.os.path, "isdir", _sem_proc(isdir)), \
                mock.patch.object(helper.os.path, "exists", _sem_proc(exists)), \
                mock.patch.object(helper.os.path, "isfile", _sem_proc(isfile)), \
                mock.patch.object(helper.sys, "argv", ["sss-helper", "encerrar-ticket", self.base, "5", "1"]), \
                mock.patch.object(helper.sys, "stderr") as stderr:
            self.assertEqual(helper.main(), 5)
        self.assertIn("nem pwdx", "".join(c[0][0] for c in stderr.write.call_args_list))

    # -- run --------------------------------------------------------------------

    def test_run_direto_com_cwd_umask_e_entrada_nula(self):
        script = os.path.join(self.raiz, "script.py")
        with open(script, "w") as f:
            f.write("import os, resource, sys\n"
                    "m = os.umask(0)\n"
                    "import json\n"
                    "open('saida.txt', 'w').write(json.dumps([os.getcwd(), '%o' % m, sys.stdin.read(),\n"
                    "    resource.getrlimit(resource.RLIMIT_CORE)[0], resource.getrlimit(resource.RLIMIT_NOFILE)[0],\n"
                    "    os.environ.get('SSS_X'), sys.argv[1:]]))\n")
        spec = {"ticket_id": 12, "argv": [sys.executable, script, "a b"], "env": {"SSS_X": "1"},
                "rlimits": {"RLIMIT_NOFILE": [512, 512]}, "pasta_base": self.base}
        codigo, erro = _helper("run", entrada=json.dumps(spec).encode("utf-8"))
        self.assertEqual(codigo, 0, erro)
        pasta = os.path.join(self.base, "ticket_12")
        with open(os.path.join(pasta, "saida.txt")) as f:
            cwd, umask, entrada, core, nofile, env, args = json.load(f)
        self.assertEqual((cwd, umask, entrada, core, nofile, env, args), (pasta, "77", "", 0, 512, "1", ["a b"]))
        self.assertEqual(os.stat(pasta).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(os.path.join(pasta, "tmp")).st_mode & 0o777, 0o700)

    def test_run_execve_falho(self):
        spec = {"ticket_id": 2, "argv": [os.path.join(self.raiz, "nao_existe")], "env": {}, "pasta_base": self.base}
        codigo, erro = _helper("run", entrada=json.dumps(spec).encode("utf-8"))
        self.assertEqual(codigo, 4)
        self.assertIn("execve falhou", erro)

    def test_helper_compila_e_nao_importa_a_aplicacao(self):
        with open(HELPER, encoding="utf-8") as f:
            fonte = f.read()
        compile(fonte, HELPER, "exec")
        self.assertTrue(fonte.startswith("#!/usr/bin/env python3\n"))
        for proibido in ("import gluon", "import sss_", "import plataforma", "config.ini\""):
            self.assertNotIn(proibido, fonte)
        self.assertTrue(os.stat(HELPER).st_mode & 0o111, "helper executavel")


if __name__ == "__main__":
    unittest.main()
