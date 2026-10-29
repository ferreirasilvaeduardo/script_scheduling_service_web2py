# -*- coding: utf-8 -*-
"""Pasta de Arquivos (CR-037, README §5.11): files_service com catalogo, agentes e auditoria falsos
e o disco de verdade, numa pasta temporaria."""
from tests.support import _testenv  # noqa: F401
import hashlib
import io
import os
import shutil
import tempfile
import unittest
import zipfile

from sss.persistence.repo_errors import RepoNotFound
from sss.services import admin_crud
from sss.services import files_service as fs


class _Catalog(object):
    def environments_list(self, page=1, size=1000):
        return {"items": [{"name": "PRODUCAO", "description": "prod", "active": "Y"},
                          {"name": "HML", "description": "hml", "active": "Y"},
                          {"name": "VELHO", "description": "inativo", "active": "N"}]}

    def scripts_list(self, page=1, size=1000):
        return {"items": [{"id": 1, "name": u"Carga Diária", "active": "Y",
                           "homologated_environments": ["PRODUCAO", "HML"]},
                          {"id": 2, "name": "relatorio", "active": "Y",
                           "homologated_environments": ["HML"]}]}


class _Agents(object):
    def __init__(self, rows):
        self.rows = rows

    def list(self):
        return self.rows


class _Audit(object):
    def __init__(self):
        self.lines = []

    def register(self, actor, ip, action, entity, entity_id=None, detail=None):
        self.lines.append((actor, ip, action, entity, detail))


class _Log(object):
    def __init__(self):
        self.lines = []

    def info(self, *a, **k):
        self.lines.append(("INFO",) + a)

    def warning(self, *a, **k):
        self.lines.append(("WARNING",) + a)


def _ctx(features=("FILES_UPLOAD", "FILES_DOWNLOAD"), envs=("PRODUCAO",), scripts=(1,)):
    return {"login": "op.prod", "is_admin": False, "active_user": True, "active_profile": True,
            "features": list(features), "environments": list(envs), "scripts": list(scripts)}


class TestFilesService(unittest.TestCase):

    def setUp(self):
        self.var = tempfile.mkdtemp(prefix="sss_files_")
        self.addCleanup(shutil.rmtree, self.var, True)
        os.makedirs(os.path.join(self.var, "agente0001", "files"), 0o755)
        self.audit = _Audit()
        self.log = _Log()
        self.agents = _Agents([{"code": "agente0001", "environments": "PRODUCAO,HML"},
                               {"code": "outro_servidor", "environments": "PRODUCAO"}])
        self.svc = fs.FilesService(_Catalog(), self.agents, self.audit, self.log, 1024, self.var)
        self.base = os.path.join(self.var, "agente0001", "files", "producao", "carga_diaria")

    def _write(self, rel, data=b"x"):
        path = os.path.join(self.base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path

    # ------------------------------------------------------------------ escopo

    def test_areas_pelas_funcionalidades(self):
        self.assertEqual(self.svc.areas(_ctx()), ["inputs", "outputs"])
        self.assertEqual(self.svc.areas(_ctx(features=("FILES_DOWNLOAD",))), ["outputs"])
        self.assertEqual(self.svc.areas(_ctx(features=("UPLOAD_INPUT",))), [])
        with self.assertRaises(admin_crud.AccessDenied):
            self.svc.environments(_ctx(features=("UPLOAD_INPUT",)))
        admin = dict(_ctx(features=()), is_admin=True)
        self.assertEqual(self.svc.areas(admin), ["inputs", "outputs"])
        self.assertEqual([e["name"] for e in self.svc.environments(admin)], ["HML", "PRODUCAO"],
                         "so ambientes ativos")

    def test_escopo_de_ambiente_e_script(self):
        self.assertEqual([e["name"] for e in self.svc.environments(_ctx())], ["PRODUCAO"])
        self.assertEqual([s["id"] for s in self.svc.scripts(_ctx(), "PRODUCAO")], [1])
        with self.assertRaises(RepoNotFound):
            self.svc.scripts(_ctx(), "HML")
        with self.assertRaises(RepoNotFound):
            self.svc.folder(_ctx(), "PRODUCAO", 2, "inputs", None)

    def test_agentes_so_com_a_pasta_neste_servidor(self):
        # outro_servidor atende PRODUCAO, mas a pasta dele nao existe aqui (outro servidor, D2)
        self.assertEqual(self.svc.agents("PRODUCAO"), ["agente0001"])
        self.assertEqual(self.svc.agents("CLONE9"), [])
        os.makedirs(os.path.join(self.var, "outro_servidor", "files"))
        self.assertEqual(self.svc.agents("PRODUCAO"), ["agente0001", "outro_servidor"])
        with self.assertRaises(fs.InvalidRequest):
            self.svc.folder(_ctx(), "PRODUCAO", 1, "inputs", None)
        view = self.svc.folder(_ctx(), "PRODUCAO", 1, "inputs", "outro_servidor")
        self.assertEqual(view["agent"], "outro_servidor")
        with self.assertRaises(fs.InvalidRequest):
            self.svc.folder(_ctx(), "PRODUCAO", 1, "inputs", "nao_existe")

    def test_sem_agente_com_a_pasta(self):
        self.agents.rows = [{"code": "outro_servidor", "environments": "PRODUCAO"}]
        with self.assertRaises(fs.NoAgent):
            self.svc.folder(_ctx(), "PRODUCAO", 1, "inputs", None)

    # ------------------------------------------------------------------ pasta

    def test_pasta_vazia_subpastas_e_arquivos(self):
        view = self.svc.folder(_ctx(), "PRODUCAO", 1, "outputs", None)
        self.assertEqual((view["subfolders"], view["files"]),
                         ([], []), "pasta que nao existe: vazia")
        self._write("outputs/lote/a.csv", b"12345")
        self._write("outputs/b.txt")
        self._write("outputs/.sss_files_1_x.tmp")
        view = self.svc.folder(_ctx(), "PRODUCAO", 1, "outputs", None)
        self.assertEqual([s["path"] for s in view["subfolders"]], ["lote"])
        self.assertEqual([f["name"] for f in view["files"]], [
                         "b.txt"], "sem o temporario do envio")
        inner = self.svc.folder(_ctx(), "PRODUCAO", 1, "outputs", None, "lote")
        self.assertEqual([(f["path"], f["size"]) for f in inner["files"]], [("lote/a.csv", 5)])
        self.assertEqual(inner["crumbs"], [{"name": "lote", "path": "lote"}])

    def test_area_sem_permissao_e_parametros_invalidos(self):
        with self.assertRaises(RepoNotFound):
            self.svc.folder(_ctx(features=("FILES_DOWNLOAD",)), "PRODUCAO", 1, "inputs", None)
        for bad in ("../x", "a/../b", ".oculto", "a//b"):
            with self.assertRaises(fs.InvalidRequest, msg=bad):
                self.svc.folder(_ctx(), "PRODUCAO", 1, "outputs", None, bad)
        with self.assertRaises(fs.InvalidRequest):
            self.svc.folder(_ctx(), "PRODUCAO", 1, "outros", None)
        with self.assertRaises(fs.InvalidRequest):
            self.svc.folder(_ctx(), "PRODUCAO", "abc", "outputs", None)

    def test_link_simbolico_nunca_e_seguido(self):
        outside = tempfile.mkdtemp(prefix="sss_fora_")
        self.addCleanup(shutil.rmtree, outside, True)
        with open(os.path.join(outside, "segredo.txt"), "w") as f:
            f.write("nao")
        os.makedirs(os.path.join(self.base, "outputs"))
        os.symlink(outside, os.path.join(self.base, "outputs", "ligada"))
        target = os.path.join(outside, "segredo.txt")
        os.symlink(target, os.path.join(self.base, "outputs", "s.txt"))
        view = self.svc.folder(_ctx(), "PRODUCAO", 1, "outputs", None)
        self.assertEqual((view["subfolders"], view["files"]), ([], []), "links fora da lista")
        with self.assertRaises(RepoNotFound):
            self.svc.folder(_ctx(), "PRODUCAO", 1, "outputs", None, "ligada")
        with self.assertRaises(RepoNotFound):
            self.svc.download(_ctx(), "10.0.0.1", "PRODUCAO", 1, None, "s.txt")
        with self.assertRaises(RepoNotFound):
            self.svc.download_zip(_ctx(), "10.0.0.1", "PRODUCAO", 1, None, "ligada")
        os.makedirs(os.path.join(self.base, "inputs"))
        os.symlink(outside, os.path.join(self.base, "inputs", "ligada"))
        with self.assertRaises(RepoNotFound):
            self.svc.upload(_ctx(), "10.0.0.1", "PRODUCAO", 1, None, "ligada", "a.txt",
                            io.BytesIO(b"1"), False)
        self.assertEqual(os.listdir(outside), ["segredo.txt"], "nada gravado fora da pasta")
        self.assertEqual(self.audit.lines, [], "nada auditado nas recusas")

    # ------------------------------------------------------------------ envio

    def test_envio_grava_audita_e_nao_deixa_temporario(self):
        browser_name = u"C:\\Users\\eu\\relatório.csv"
        result, errors = self.svc.upload(_ctx(), "10.0.0.1", "PRODUCAO", 1, None, "lote/2026",
                                         browser_name, io.BytesIO(b"a;b\n"), False)
        self.assertEqual(errors, {})
        self.assertEqual(result, {"path": u"lote/2026/relatório.csv",
                         "size": 4, "agent": "agente0001"})
        folder = os.path.join(self.base, "inputs", "lote", "2026")
        self.assertEqual(os.listdir(folder), [u"relatório.csv"], "sem temporario")
        with open(os.path.join(folder, u"relatório.csv"), "rb") as f:
            self.assertEqual(f.read(), b"a;b\n")
        self.assertEqual(os.stat(folder).st_mode & 0o777, 0o700)
        actor, ip, action, entity, detail = self.audit.lines[0]
        self.assertEqual((actor, ip, action, entity),
                         ("op.prod", "10.0.0.1", "FILES_UPLOAD", "files"))
        self.assertIn(hashlib.sha256(b"a;b\n").hexdigest(), detail)
        self.assertIn(u"PRODUCAO/Carga Diária/inputs/lote/2026/relatório.csv (4 bytes", detail)

    def test_ja_existe_substituir_e_limite(self):
        args = (_ctx(), "10.0.0.1", "PRODUCAO", 1, None, "")
        self.assertEqual(self.svc.upload(*args, "a.txt", io.BytesIO(b"um"), False)[1], {})
        result, errors = self.svc.upload(*args, "a.txt", io.BytesIO(b"dois"), False)
        self.assertEqual((result, errors), (None, {"file": fs.MSG_EXISTS}))
        self.assertEqual(self.svc.upload(*args, "a.txt", io.BytesIO(b"dois"), True)[1], {})
        with open(os.path.join(self.base, "inputs", "a.txt"), "rb") as f:
            self.assertEqual(f.read(), b"dois")
        self.assertIn(u"substituído", self.audit.lines[-1][4])
        result, errors = self.svc.upload(*args, "grande.bin", io.BytesIO(b"x" * 1025), False)
        self.assertIsNone(result)
        self.assertIn("tamanho máximo", errors["file"])
        self.assertEqual(sorted(os.listdir(os.path.join(self.base, "inputs"))), ["a.txt"],
                         "acima do limite: nada fica, nem o temporario")
        self.assertEqual(len(self.audit.lines), 2, "so os envios gravados sao auditados")

    def test_envio_com_nome_ou_subpasta_invalidos(self):
        args = (_ctx(), "10.0.0.1", "PRODUCAO", 1, None)
        self.assertEqual(self.svc.upload(*args, "", ".oculto", io.BytesIO(b"1"), False)[1],
                         {"file": fs.MSG_NAME})
        self.assertEqual(self.svc.upload(*args, "../fora", "a.txt", io.BytesIO(b"1"), False)[1],
                         {"relative_dir": fs.MSG_FOLDER})
        self.assertEqual(self.svc.upload(*args, "", "a.txt", None, False)
                         [1], {"file": fs.MSG_FILE})
        with self.assertRaises(RepoNotFound):
            self.svc.upload(_ctx(features=("FILES_DOWNLOAD",)), "10.0.0.1", "PRODUCAO", 1, None,
                            "", "a.txt", io.BytesIO(b"1"), False)
        self.assertFalse(os.path.exists(os.path.join(self.base, "inputs", "a.txt")))

    # ------------------------------------------------------------------ download

    def test_download_de_um_arquivo_auditado(self):
        self._write("outputs/lote/r.csv", b"r" * 3000000)
        name, size, parts = self.svc.download(_ctx(), "10.0.0.2", "PRODUCAO", 1, None,
                                              "lote/r.csv")
        self.assertEqual((name, size), ("r.csv", 3000000))
        self.assertEqual(b"".join(parts), b"r" * 3000000)
        self.assertEqual(self.audit.lines[0][2], "FILES_DOWNLOAD")
        self.assertIn("outputs/lote/r.csv (3000000 bytes", self.audit.lines[0][4])
        with self.assertRaises(RepoNotFound):
            self.svc.download(_ctx(), "10.0.0.2", "PRODUCAO", 1, None, "lote/nao.csv")
        with self.assertRaises(RepoNotFound):
            self.svc.download(_ctx(features=("FILES_UPLOAD",)), "10.0.0.2", "PRODUCAO", 1, None,
                              "lote/r.csv")

    def test_zip_da_pasta_em_fluxo(self):
        self._write("outputs/a.txt", b"aaa")
        self._write("outputs/sub/b.txt", b"bbb" * 400000)
        self._write("outputs/.sss_files_9_y.tmp", b"temporario")
        os.symlink("/etc/passwd", os.path.join(self.base, "outputs", "ligado"))
        name, parts = self.svc.download_zip(_ctx(), "10.0.0.3", "PRODUCAO", 1, None, "")
        self.assertEqual(name, u"Carga Diária_outputs.zip")
        chunks = list(parts)
        self.assertGreater(len(chunks), 1, "enviado em fatias")
        with zipfile.ZipFile(io.BytesIO(b"".join(chunks))) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(sorted(z.namelist()), ["a.txt", "sub/b.txt"],
                             "sem link nem temporario")
            self.assertEqual(z.read("sub/b.txt"), b"bbb" * 400000)
        self.assertIn("zip da pasta", self.audit.lines[0][4])
        sub_name, sub_parts = self.svc.download_zip(_ctx(), "10.0.0.3", "PRODUCAO", 1, None, "sub")
        self.assertEqual(sub_name, u"Carga Diária_sub_outputs.zip")
        with zipfile.ZipFile(io.BytesIO(b"".join(sub_parts))) as z:
            self.assertEqual(z.namelist(), ["b.txt"])


if __name__ == "__main__":
    unittest.main()
