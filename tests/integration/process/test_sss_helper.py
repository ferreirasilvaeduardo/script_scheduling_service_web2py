# -*- coding: utf-8 -*-
"""Testes do bin/sss-helper (README §8.0, AGENTS §7.4; CR-008 R-01 e R-36), executado direto com o proprio
usuario (sem sudo): validacao de argumentos, identidade do grupo, base_dir, limpeza sem seguir links e
o run com cwd, umask e entrada padrao nula."""
from tests.support import _testenv  # noqa: F401

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

REPO_ROOT = _testenv.APP_DIR
HELPER = os.path.join(REPO_ROOT, "bin", "sss-helper")


_COPY = {}


def setUpModule():
    # O helper nao tem sufixo .py: uma copia numa pasta temporaria permite importa-lo para os dubles.
    _COPY["pasta"] = tempfile.mkdtemp(prefix="sss_helper_mod_")
    shutil.copy(HELPER, os.path.join(_COPY["pasta"], "sss_helper_copia.py"))
    sys.path.insert(0, _COPY["pasta"])


def tearDownModule():
    sys.path.remove(_COPY["pasta"])
    sys.modules.pop("sss_helper_copia", None)
    shutil.rmtree(_COPY["pasta"], ignore_errors=True)


def _load_helper():
    import sss_helper_copia
    return sss_helper_copia


def _helper(*args, **kw):
    """Executa o helper; devolve (codigo, stderr)."""
    p = subprocess.run([sys.executable, HELPER] + [str(a) for a in args], input=kw.get("entrada", b""),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    return p.returncode, p.stderr.decode("utf-8", "replace")


def _alive(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            content = f.read()
    except OSError:
        return False
    return content[content.rindex(")") + 2:].split()[0] != "Z"


def _wait(condition, deadline=10.0):
    limit = time.monotonic() + deadline
    while time.monotonic() < limit:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


@unittest.skipIf(os.geteuid() == 0, "o helper roda como usuario de execucao, nunca root")
class TestSssHelper(unittest.TestCase):

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="sss_helper_"))
        self.base = os.path.join(self.root, "exec1")
        os.mkdir(self.base, 0o700)
        self.popens = []

    def tearDown(self):
        for p in self.popens:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
            p.wait()
        shutil.rmtree(self.root, ignore_errors=True)

    def group(self, cwd=None):
        p = subprocess.Popen(["sleep", "300"], start_new_session=True, cwd=cwd or self.root)
        self.popens.append(p)
        return p

    # -- uso invalido ---------------------------------------------------------

    def test_uso_invalido(self):
        for args in ((), ("xyz",), ("term",), ("term", "abc", "1"), ("term", "1", "1"), ("kill", "-5", "1"),
                     ("term", "100", "1", "extra"), ("clean", self.base), ("clean", self.base, "0"),
                     ("stop-ticket", self.base, "1"), ("stop-ticket", self.base, "1", "999"),
                     ("run", "extra")):
            code, error = _helper(*args)
            self.assertEqual(code, 2, args)
            self.assertTrue(error.startswith("sss-helper: "), error)
            self.assertNotIn("Traceback", error)

    def test_especificacao_invalida(self):
        valid = {"ticket_id": 1, "argv": ["/bin/true"], "env": {}, "base_dir": self.base}
        cases = [b"nao e json", b"[1, 2]", b"\xff\xfe",
                 json.dumps(dict(valid, ticket_id=0)), json.dumps(dict(valid, ticket_id=True)),
                 json.dumps(dict(valid, argv=[])), json.dumps(dict(valid, argv=["true"])),
                 json.dumps(dict(valid, argv=["/bin/true", 3])), json.dumps(dict(valid, env={"A": 1})),
                 json.dumps(dict(valid, rlimits={"RLIMIT_RTPRIO": [0, 0]})),
                 json.dumps(dict(valid, rlimits={"RLIMIT_CORE": [0]})),
                 json.dumps(dict(valid, base_dir="relativa")),
                 json.dumps(dict(valid, base_dir=self.base + "/../exec1")),
                 b"{" + b" " * (1024 * 1024) + b"}"]
        for input_value in cases:
            input_value = input_value if isinstance(input_value, bytes) else input_value.encode("utf-8")
            self.assertEqual(_helper("run", entrada=input_value)[0], 2, input_value[:80])
        self.assertFalse(os.path.exists(os.path.join(self.base, "ticket_1")))

    # -- term / kill ------------------------------------------------------------

    def test_term_kill_com_identidade_divergente(self):
        helper = _load_helper()
        p = self.group()
        start = helper._identity(p.pid)
        self.assertIsNotNone(start)
        for sub in ("term", "kill"):
            code, error = _helper(sub, p.pid, start + 1)
            self.assertEqual(code, 3, sub)
            self.assertIn("identidade", error)
        self.assertTrue(_alive(p.pid))
        self.assertEqual(_helper("term", p.pid, start)[0], 0)
        p.wait(10)
        self.assertEqual(p.returncode, -signal.SIGTERM)
        q = self.group()
        self.assertEqual(_helper("kill", q.pid, helper._identity(q.pid))[0], 0)
        q.wait(10)
        self.assertEqual(q.returncode, -signal.SIGKILL)

    def test_term_kill_com_grupo_vazio(self):
        p = self.group()
        os.killpg(p.pid, signal.SIGKILL)
        p.wait()
        for sub in ("term", "kill"):
            self.assertEqual(_helper(sub, p.pid, 12345)[0], 0, sub)

    def test_lider_sudo_de_root_com_identidade_certa_recebe_o_sinal(self):
        # Revisao de 2026-10-20: o lider do grupo e o sudo (root); EPERM na sondagem e o caso normal.
        helper = _load_helper()
        for sub, signal_value in ((helper._term, signal.SIGTERM), (helper._kill, signal.SIGKILL)):
            with mock.patch.object(helper.os, "kill", side_effect=PermissionError()), \
                    mock.patch.object(helper, "_identity", return_value=777), \
                    mock.patch.object(helper.os, "killpg") as killpg:
                self.assertEqual(sub(4242, 777), 0)
            killpg.assert_called_once_with(4242, signal_value)

    def test_lider_de_root_com_identidade_divergente_e_recusado(self):
        helper = _load_helper()
        for sub in (helper._term, helper._kill):
            with mock.patch.object(helper.os, "kill", side_effect=PermissionError()), \
                    mock.patch.object(helper, "_identity", return_value=778), \
                    mock.patch.object(helper.os, "killpg") as killpg:
                with self.assertRaises(helper.Failure) as ctx:
                    sub(4242, 777)
            self.assertEqual(ctx.exception.code, 3)
            killpg.assert_not_called()

    def test_grupo_so_com_o_sudo_e_sucesso(self):
        helper = _load_helper()
        with mock.patch.object(helper.os, "kill", side_effect=PermissionError()), \
                mock.patch.object(helper, "_identity", return_value=777), \
                mock.patch.object(helper.os, "killpg", side_effect=PermissionError()):
            self.assertEqual(helper._term(4242, 777), 0)
            self.assertEqual(helper._kill(4242, 777), 0)

    def test_identidade_com_parenteses_no_nome(self):
        helper = _load_helper()
        fields = " ".join(["Y"] + [str(i) for i in range(4, 60)])
        with mock.patch("builtins.open", mock.mock_open(read_data="77 (a) b)) %s" % fields)):
            self.assertEqual(helper._identity(77), 22)
        self.assertIsNone(helper._identity(2 ** 31 - 2))

    # -- base_dir -------------------------------------------------------------

    def _invalid_dirs(self):
        link = os.path.join(self.root, "link_base")
        os.symlink(self.base, link)
        file = os.path.join(self.root, "arquivo")
        open(file, "w").close()
        return ("exec1", self.base + "/", os.path.join(self.base, "..", "exec1"), link,
                os.path.join(self.root, "nao_existe"), file, "/")

    def test_limpar_e_encerrar_ticket_com_pasta_base_invalida(self):
        target = os.path.join(self.base, "ticket_4")
        os.mkdir(target)
        for dir_value in self._invalid_dirs():
            self.assertEqual(_helper("clean", dir_value, 4)[0], 2, dir_value)
            self.assertEqual(_helper("stop-ticket", dir_value, 4, 1)[0], 2, dir_value)
        self.assertTrue(os.path.isdir(target), "nada removido pela pasta recusada")

    def test_pasta_base_de_outro_dono(self):
        helper = _load_helper()
        with mock.patch.object(helper.os, "geteuid", return_value=os.geteuid() + 1):
            with self.assertRaises(helper.Failure) as ctx:
                helper._base_dir(self.base)
        self.assertEqual(ctx.exception.code, 2)

    def test_limpar_sem_seguir_links(self):
        outside = os.path.join(self.root, "fora")
        os.mkdir(outside)
        with open(os.path.join(outside, "precioso.txt"), "w") as f:
            f.write("x")
        dir_value = os.path.join(self.base, "ticket_9")
        os.makedirs(os.path.join(dir_value, "tmp"))
        os.symlink(outside, os.path.join(dir_value, "tmp", "link_fora"))
        os.symlink(os.path.join(outside, "precioso.txt"), os.path.join(dir_value, "link_arq"))
        self.assertEqual(_helper("clean", self.base, 9)[0], 0)
        self.assertFalse(os.path.lexists(dir_value))
        self.assertTrue(os.path.isfile(os.path.join(outside, "precioso.txt")))
        self.assertEqual(_helper("clean", self.base, 9)[0], 0, "pasta ja ausente")
        os.symlink(outside, os.path.join(self.base, "ticket_10"))
        self.assertEqual(_helper("clean", self.base, 10)[0], 2, "ticket_<id> que e link")
        self.assertTrue(os.path.isfile(os.path.join(outside, "precioso.txt")))

    # -- stop-ticket --------------------------------------------------------

    def test_encerrar_ticket_so_na_pasta_do_ticket(self):
        dir_value = os.path.join(self.base, "ticket_3", "tmp")
        os.makedirs(dir_value)
        neighbor = os.path.join(self.base, "ticket_30")
        os.mkdir(neighbor)
        inside, outside = self.group(cwd=dir_value), self.group(cwd=neighbor)
        self.assertTrue(_wait(lambda: os.path.realpath("/proc/%d/cwd" % inside.pid) == dir_value))
        self.assertEqual(_helper("stop-ticket", self.base, 3, 2)[0], 0)
        inside.wait(10)
        self.assertEqual(inside.returncode, -signal.SIGTERM)
        self.assertTrue(_alive(outside.pid))

    def test_encerrar_ticket_nao_suportado(self):
        helper = _load_helper()
        os.mkdir(os.path.join(self.base, "ticket_5"))
        isdir, exists, isfile = os.path.isdir, os.path.exists, os.path.isfile

        def _sem_proc(f):
            return lambda c: False if c.startswith("/proc") or c.endswith("pwdx") else f(c)

        with mock.patch.object(helper.os.path, "isdir", _sem_proc(isdir)), \
                mock.patch.object(helper.os.path, "exists", _sem_proc(exists)), \
                mock.patch.object(helper.os.path, "isfile", _sem_proc(isfile)), \
                mock.patch.object(helper.sys, "argv", ["sss-helper", "stop-ticket", self.base, "5", "1"]), \
                mock.patch.object(helper.sys, "stderr") as stderr:
            self.assertEqual(helper.main(), 5)
        self.assertIn("nem pwdx", "".join(c[0][0] for c in stderr.write.call_args_list))

    # -- run --------------------------------------------------------------------

    def test_run_direto_com_cwd_umask_e_entrada_nula(self):
        script = os.path.join(self.root, "script.py")
        with open(script, "w") as f:
            f.write("import os, resource, sys\n"
                    "m = os.umask(0)\n"
                    "import json\n"
                    "open('saida.txt', 'w').write(json.dumps([os.getcwd(), '%o' % m, sys.stdin.read(),\n"
                    "    resource.getrlimit(resource.RLIMIT_CORE)[0], resource.getrlimit(resource.RLIMIT_NOFILE)[0],\n"
                    "    os.environ.get('SSS_X'), sys.argv[1:]]))\n")
        spec = {"ticket_id": 12, "argv": [sys.executable, script, "a b"], "env": {"SSS_X": "1"},
                "rlimits": {"RLIMIT_NOFILE": [512, 512]}, "base_dir": self.base}
        code, error = _helper("run", entrada=json.dumps(spec).encode("utf-8"))
        self.assertEqual(code, 0, error)
        dir_value = os.path.join(self.base, "ticket_12")
        with open(os.path.join(dir_value, "saida.txt")) as f:
            cwd, umask, input_value, core, nofile, env, args = json.load(f)
        self.assertEqual((cwd, umask, input_value, core, nofile, env, args), (dir_value, "77", "", 0, 512, "1", ["a b"]))
        self.assertEqual(os.stat(dir_value).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(os.path.join(dir_value, "tmp")).st_mode & 0o777, 0o700)

    def test_run_execve_falho(self):
        spec = {"ticket_id": 2, "argv": [os.path.join(self.root, "nao_existe")], "env": {}, "base_dir": self.base}
        code, error = _helper("run", entrada=json.dumps(spec).encode("utf-8"))
        self.assertEqual(code, 4)
        self.assertIn("execve falhou", error)

    # -- pasta de saida (CR-012) ------------------------------------------------

    def _output_base(self):
        base = os.path.join(self.root, "output", "producao")
        os.makedirs(base, 0o700)
        return base

    def _helper_output(self, *args):
        """Executa o helper com a saida padrao capturada; devolve (codigo, stdout, stderr)."""
        p = subprocess.run([sys.executable, HELPER] + [str(a) for a in args], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=60)
        return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace")

    def test_run_cria_a_pasta_de_saida_do_ticket(self):
        base = self._output_base()
        rel = "carga_diaria/2026/10/20/14/05/ticket_12"
        script = os.path.join(self.root, "grava.py")
        with open(script, "w") as f:
            f.write("import os\nopen(os.path.join(os.environ['SSS_OUTPUT_DIR'], 'r.txt'), 'w').write('ok')\n")
        target = os.path.join(base, rel)
        spec = {"ticket_id": 12, "argv": [sys.executable, script], "env": {"SSS_OUTPUT_DIR": target},
                "base_dir": self.base, "output": {"base": base, "relativo": rel}}
        code, error = _helper("run", entrada=json.dumps(spec).encode("utf-8"))
        self.assertEqual(code, 0, error)
        with open(os.path.join(target, "r.txt")) as f:
            self.assertEqual(f.read(), "ok")
        current = base
        for part in rel.split("/"):
            current = os.path.join(current, part)
            self.assertEqual(os.stat(current).st_mode & 0o777, 0o700, current)

    def test_run_recusa_saida_invalida(self):
        base = self._output_base()
        valid = {"ticket_id": 12, "argv": ["/bin/true"], "env": {}, "base_dir": self.base}
        for output in ({"base": base}, {"base": base, "relativo": "x/2026/10/20/14/05/ticket_13"},
                      {"base": base, "relativo": "../2026/10/20/14/05/ticket_12"},
                      {"base": base, "relativo": "x/2026/10/20/14/ticket_12"},
                      {"base": base, "relativo": ".x/2026/10/20/14/05/ticket_12"},
                      {"base": "relativa", "relativo": "x/2026/10/20/14/05/ticket_12"},
                      {"base": base + "/../producao", "relativo": "x/2026/10/20/14/05/ticket_12"}):
            self.assertEqual(_helper("run", entrada=json.dumps(dict(valid, output=output)).encode("utf-8"))[0], 2,
                             output)
        # Link no caminho da saida (criado por terceiro): recusado sem seguir o link.
        outside = os.path.join(self.root, "fora")
        os.mkdir(outside)
        os.symlink(outside, os.path.join(base, "x"))
        spec = dict(valid, output={"base": base, "relativo": "x/2026/10/20/14/05/ticket_12"})
        self.assertEqual(_helper("run", entrada=json.dumps(spec).encode("utf-8"))[0], 2)
        self.assertEqual(os.listdir(outside), [])

    def test_cr019_run_cria_a_pasta_de_trabalho_que_fica(self):
        # CR-019 (README §8.15): criada antes do script com 0700 nivel a nivel; o helper nao a remove.
        base = os.path.join(self.root, "work_scripts", "producao")
        os.makedirs(base, 0o700)
        rel = "carga/2026/10/20/14/05/ticket_12"
        script = os.path.join(self.root, "trabalha.py")
        with open(script, "w") as f:
            f.write("import os\nopen(os.path.join(os.environ['SSS_WORK_DIR'], 't.txt'), 'w').write('ok')\n")
        target = os.path.join(base, rel)
        spec = {"ticket_id": 12, "argv": [sys.executable, script], "env": {"SSS_WORK_DIR": target},
                "base_dir": self.base, "work": {"base": base, "relativo": rel}}
        code, error = _helper("run", entrada=json.dumps(spec).encode("utf-8"))
        self.assertEqual(code, 0, error)
        with open(os.path.join(target, "t.txt")) as f:
            self.assertEqual(f.read(), "ok")
        current = base
        for part in rel.split("/"):
            current = os.path.join(current, part)
            self.assertEqual(os.stat(current).st_mode & 0o777, 0o700, current)

    def test_cr019_run_recusa_pasta_de_trabalho_invalida(self):
        base = os.path.join(self.root, "work_scripts", "producao")
        os.makedirs(base, 0o700)
        valid = {"ticket_id": 12, "argv": ["/bin/true"], "env": {}, "base_dir": self.base}
        for work in ({"base": base}, {"base": base, "relativo": "x/2026/10/20/14/05/ticket_13"},
                     {"base": base, "relativo": "x/2026/10/20/14/ticket_12"},
                     {"base": "relativa", "relativo": "x/2026/10/20/14/05/ticket_12"}):
            self.assertEqual(_helper("run", entrada=json.dumps(dict(valid, work=work)).encode("utf-8"))[0], 2, work)
        outside = os.path.join(self.root, "fora_trabalho")
        os.mkdir(outside)
        os.symlink(outside, os.path.join(base, "x"))
        spec = dict(valid, work={"base": base, "relativo": "x/2026/10/20/14/05/ticket_12"})
        self.assertEqual(_helper("run", entrada=json.dumps(spec).encode("utf-8"))[0], 2, "link recusado")
        self.assertEqual(os.listdir(outside), [])

    # ------------------------------------------------------------ CR-020c: put-input e list-input

    def _input_base(self):
        base = os.path.join(self.root, "input", "producao")
        os.makedirs(base, 0o700, exist_ok=True)
        return base

    def _put(self, base, data, relative="lotes/2026", name="cliente.csv", replace="N", sha=None, size=None):
        import hashlib
        sha = sha or hashlib.sha256(data).hexdigest()
        return _helper("put-input", base, "carga_diaria", relative, name, replace, sha,
                       len(data) if size is None else size, entrada=data)

    def test_cr020_put_input_grava_cria_subpastas_e_nao_substitui(self):
        base = self._input_base()
        code, error = self._put(base, b"a;b\n1;2\n")
        self.assertEqual(code, 0, error)
        final = os.path.join(base, "carga_diaria", "lotes", "2026", "cliente.csv")
        with open(final, "rb") as f:
            self.assertEqual(f.read(), b"a;b\n1;2\n")
        self.assertEqual(os.stat(final).st_mode & 0o777, 0o600)
        for folder in ("carga_diaria", "carga_diaria/lotes", "carga_diaria/lotes/2026"):
            self.assertEqual(os.stat(os.path.join(base, folder)).st_mode & 0o777, 0o700, folder)
        # sem substituir: o existente fica, codigo 9
        self.assertEqual(self._put(base, b"novo")[0], 9)
        with open(final, "rb") as f:
            self.assertEqual(f.read(), b"a;b\n1;2\n")
        # substituindo
        self.assertEqual(self._put(base, b"novo", replace="Y")[0], 0)
        with open(final, "rb") as f:
            self.assertEqual(f.read(), b"novo")
        # sem subpasta
        self.assertEqual(self._put(base, b"x", relative="-", name="raiz.txt")[0], 0)
        self.assertTrue(os.path.isfile(os.path.join(base, "carga_diaria", "raiz.txt")))
        leftovers = [n for n in os.listdir(os.path.join(base, "carga_diaria", "lotes", "2026")) if n.startswith(".")]
        self.assertEqual(leftovers, [], "nenhum temporario fica no destino")

    def test_cr020_put_input_hash_tamanho_e_nomes_invalidos(self):
        base = self._input_base()
        self.assertEqual(self._put(base, b"conteudo", sha="0" * 64)[0], 11, "hash divergente")
        self.assertEqual(self._put(base, b"conteudo", size=3)[0], 11, "tamanho divergente")
        self.assertFalse(os.path.exists(os.path.join(base, "carga_diaria", "lotes", "2026", "cliente.csv")))
        for relative, name in (("../fora", "a.txt"), ("lotes", "../a.txt"), ("lotes", ".oculto"),
                               ("a/./b", "x.txt"), ("lotes", "a\tb"), ("/".join(["n"] * 11), "x.txt"),
                               ("lotes", "x" * 256)):
            self.assertEqual(self._put(base, b"x", relative=relative, name=name)[0], 2, (relative, name))
        self.assertEqual(_helper("put-input", base, "Maiuscula", "-", "a.txt", "N", "0" * 64, 1, entrada=b"x")[0], 2)
        self.assertEqual(_helper("put-input", base, "carga_diaria", "-", "a.txt", "S", "0" * 64, 1, entrada=b"x")[0], 2)

    def test_cr020_put_input_recusa_link_e_destino_que_nao_e_arquivo(self):
        base = self._input_base()
        outside = os.path.join(self.root, "fora_entrada_tela")
        os.mkdir(outside)
        os.makedirs(os.path.join(base, "carga_diaria"), 0o700)
        os.symlink(outside, os.path.join(base, "carga_diaria", "ligada"))
        self.assertEqual(self._put(base, b"x", relative="ligada")[0], 2, "link na subpasta")
        self.assertEqual(os.listdir(outside), [])
        os.makedirs(os.path.join(base, "carga_diaria", "pasta.txt"))
        self.assertEqual(self._put(base, b"x", relative="-", name="pasta.txt", replace="Y")[0], 2,
                         "substituir uma pasta")
        self.assertEqual(self._put(base, b"x", relative="-", name="pasta.txt")[0], 9, "sem substituir: ja existe")

    def test_cr020_list_input_sem_links_sem_temporarios_e_com_teto(self):
        import json
        base = self._input_base()
        self.assertEqual(json.loads(self._helper_output("list-input", base, "carga_diaria", 10)[1]),
                         {"files": [], "count": 0, "truncated": False}, "pasta ainda inexistente")
        folder = os.path.join(base, "carga_diaria")
        os.makedirs(os.path.join(folder, "sub"), 0o700)
        for name in ("a.txt", "sub/b.txt", ".sss_upload_99.tmp", "c.txt"):
            with open(os.path.join(folder, name), "w") as f:
                f.write("12345")
        outside = os.path.join(self.root, "fora_lista")
        os.makedirs(outside)
        open(os.path.join(outside, "segredo.txt"), "w").close()
        os.symlink(outside, os.path.join(folder, "ligada"))
        os.symlink(os.path.join(outside, "segredo.txt"), os.path.join(folder, "link.txt"))
        code, out, error = self._helper_output("list-input", base, "carga_diaria", 10)
        self.assertEqual(code, 0, error)
        data = json.loads(out)
        self.assertEqual([f["path"] for f in data["files"]], ["a.txt", "c.txt", "sub/b.txt"])
        self.assertEqual((data["count"], data["truncated"], data["files"][0]["size"]), (3, False, 5))
        data = json.loads(self._helper_output("list-input", base, "carga_diaria", 2)[1])
        self.assertEqual((len(data["files"]), data["count"], data["truncated"]), (2, 3, True))
        self.assertEqual(self._helper_output("list-input", base, "carga_diaria", 0)[0], 2)

    def test_run_cria_a_pasta_de_entrada_e_preserva_o_conteudo(self):
        # CR-014 (README §8.14): permanente; o script le, grava e apaga; a existente fica como esta.
        base = os.path.join(self.root, "input", "producao")
        os.makedirs(base, 0o700)
        script = os.path.join(self.root, "consome.py")
        with open(script, "w") as f:
            f.write("import os\nd = os.environ['SSS_INPUT_DIR']\n"
                    "n = len(os.listdir(d))\nopen(os.path.join(d, 'lido_%d.txt' % n), 'w').write('ok')\n")
        target = os.path.join(base, "carga_diaria")
        for ticket in (21, 22):
            spec = {"ticket_id": ticket, "argv": [sys.executable, script], "env": {"SSS_INPUT_DIR": target},
                    "base_dir": self.base, "input": {"base": base, "relativo": "carga_diaria"}}
            code, error = _helper("run", entrada=json.dumps(spec).encode("utf-8"))
            self.assertEqual(code, 0, error)
            if ticket == 21:
                self.assertEqual(os.stat(target).st_mode & 0o777, 0o700)
                os.chmod(target, 0o750)
        self.assertEqual(sorted(os.listdir(target)), ["lido_0.txt", "lido_1.txt"], "persiste entre tickets")
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o750, "a existente fica como esta")

    def test_run_recusa_entrada_invalida(self):
        base = os.path.join(self.root, "input", "producao")
        os.makedirs(base, 0o700)
        valid = {"ticket_id": 12, "argv": ["/bin/true"], "env": {}, "base_dir": self.base}
        for input_value in ({"base": base}, {"base": base, "relativo": "a/b"}, {"base": base, "relativo": ".."},
                        {"base": base, "relativo": ".x"}, {"base": base, "relativo": "Maiuscula"},
                        {"base": "relativa", "relativo": "x"}, {"base": base + "/../producao", "relativo": "x"}):
            self.assertEqual(_helper("run", entrada=json.dumps(dict(valid, input=input_value)).encode("utf-8"))[0],
                             2, input_value)
        outside = os.path.join(self.root, "fora_entrada")
        os.mkdir(outside)
        os.symlink(outside, os.path.join(base, "x"))
        spec = dict(valid, input={"base": base, "relativo": "x"})
        self.assertEqual(_helper("run", entrada=json.dumps(spec).encode("utf-8"))[0], 2, "link recusado")

    def _fill(self, base, rel, files):
        dir_value = os.path.join(base, rel)
        os.makedirs(dir_value, 0o700)
        for name, data in files.items():
            path = os.path.join(dir_value, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        return dir_value

    def test_relativo_de_pastas_log_passa_no_helper(self):
        import datetime
        from sss.config import log_paths
        helper = _load_helper()
        dt = datetime.datetime(2026, 1, 2, 3, 4)
        for name in (u"Carga Diária", u"-x-", u"a.b_c", u"!!!", u"x" * 60, u"Relatório 2026 (v2)"):
            _base, rel = log_paths.output_dir("/s", "PRODUCAO", name, dt, 99, script_id=5)
            self.assertEqual(len(helper._relative_parts(rel)), 7, rel)

    def test_empacotar_so_arquivos_regulares_sem_seguir_links(self):
        import io
        import zipfile
        base = self._output_base()
        rel = "carga/2026/10/20/14/05/ticket_7"
        dir_value = self._fill(base, rel, {"a.txt": b"um", "sub/b.csv": b"x;y\n" * 1000})
        secret = os.path.join(self.root, "segredo.txt")
        with open(secret, "w") as f:
            f.write("nao pode sair")
        os.symlink(secret, os.path.join(dir_value, "link.txt"))
        os.symlink(self.root, os.path.join(dir_value, "link_pasta"))
        os.mkfifo(os.path.join(dir_value, "fifo"))
        code, zip_, error = self._helper_output("pack", base, rel, 1048576, 10)
        self.assertEqual(code, 0, error)
        z = zipfile.ZipFile(io.BytesIO(zip_))
        self.assertEqual(sorted(z.namelist()), ["a.txt", "sub/b.csv"])
        self.assertEqual(z.read("sub/b.csv"), b"x;y\n" * 1000)
        self.assertIsNone(z.testzip())

    def test_empacotar_vazia_e_limites(self):
        base = self._output_base()
        rel = "carga/2026/10/20/14/05/ticket_8"
        self.assertEqual(self._helper_output("pack", base, rel, 1048576, 10)[0], 6, "inexistente")
        dir_value = self._fill(base, rel, {})
        os.makedirs(os.path.join(dir_value, "so_pastas"))
        self.assertEqual(self._helper_output("pack", base, rel, 1048576, 10)[0], 6, "vazia")
        self._fill(base, "carga/2026/10/20/14/05/ticket_9", dict(("f%02d" % i, b"x") for i in range(11)))
        code, _zip, error = self._helper_output("pack", base, "carga/2026/10/20/14/05/ticket_9", 1048576, 10)
        self.assertEqual(code, 7, error)
        self.assertIn("arquivos", error)
        self.assertEqual(self._helper_output("pack", base, "carga/2026/10/20/14/05/ticket_9", 1048576, 11)[0], 0)
        self._fill(base, "carga/2026/10/20/14/05/ticket_10", {"grande.bin": os.urandom(2 * 1024 * 1024)})
        code, _zip, error = self._helper_output("pack", base, "carga/2026/10/20/14/05/ticket_10", 1048576, 10)
        self.assertEqual(code, 8, error)
        self.assertIn("bytes", error)
        for args in (("pack", base, rel, 0, 10), ("pack", base, rel, 1048576, 0),
                     ("pack", base, rel, 209715201, 10), ("pack", base, rel, 1, 10001),
                     ("pack", base, "../x/2026/10/20/14/05/ticket_8", 1048576, 10),
                     ("pack", base, rel, 1048576), ("clean-output", base), ("purge-output", base, "0"),
                     ("purge-output", base, "7", "remover")):
            self.assertEqual(self._helper_output(*args)[0], 2, args)

    def test_limpar_saida_sem_seguir_links(self):
        base = self._output_base()
        rel = "carga/2026/10/20/14/05/ticket_11"
        dir_value = self._fill(base, rel, {"a.txt": b"1"})
        outside = os.path.join(self.root, "fora2")
        os.mkdir(outside)
        with open(os.path.join(outside, "manter.txt"), "w") as f:
            f.write("x")
        os.symlink(outside, os.path.join(dir_value, "link"))
        self.assertEqual(self._helper_output("clean-output", base, rel)[0], 0)
        self.assertFalse(os.path.exists(dir_value))
        self.assertTrue(os.path.exists(os.path.join(outside, "manter.txt")))
        self.assertTrue(os.path.isdir(os.path.dirname(dir_value)), "as pastas acima ficam para o purge")
        self.assertEqual(self._helper_output("clean-output", base, rel)[0], 0, "ja removida")

    def test_purgar_saida_pela_data_do_caminho(self):
        helper = _load_helper()
        base = self._output_base()
        old = self._fill(base, "carga/2026/09/01/10/00/ticket_1", {"a": b"1"})
        new = self._fill(base, "carga/2026/10/19/10/00/ticket_2", {"a": b"1"})
        odd = os.path.join(base, "carga", "2026", "09", "lixo")
        os.makedirs(odd)
        import datetime
        import io
        count = io.StringIO()
        with mock.patch.object(helper.sys, "stdout", count):  # --dry-run do purge: so conta
            self.assertEqual(helper._purge_output(base, 7, today=datetime.date(2026, 10, 20), count_only=True), 0)
        self.assertEqual(count.getvalue(), "removidas=1\n")
        self.assertTrue(os.path.exists(old), "contar nao remove")
        output = io.StringIO()
        with mock.patch.object(helper.sys, "stdout", output):
            self.assertEqual(helper._purge_output(base, 7, today=datetime.date(2026, 10, 20)), 0)
        self.assertEqual(output.getvalue(), "removidas=1\n")
        self.assertFalse(os.path.exists(os.path.join(base, "carga", "2026", "09", "01")))
        self.assertTrue(os.path.exists(new))
        self.assertTrue(os.path.isdir(odd), "fora do formato e ignorado")
        self.assertFalse(os.path.exists(old))

    def test_helper_compila_e_nao_importa_a_aplicacao(self):
        with open(HELPER, encoding="utf-8") as f:
            source = f.read()
        compile(source, HELPER, "exec")
        self.assertTrue(source.startswith("#!/usr/bin/env python3\n"))
        for forbidden in ("import gluon", "import sss_", "import os_platform", "config.ini\""):
            self.assertNotIn(forbidden, source)
        self.assertTrue(os.stat(HELPER).st_mode & 0o111, "helper executavel")


if __name__ == "__main__":
    unittest.main()
