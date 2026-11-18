"""Tests sin red del vigilante: python -m unittest discover -s tests -v"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path[:0] = [os.path.join(RAIZ, "nube")]
import vigilante_pc as v  # noqa: E402

T0 = 1_800_000_000


def _sin_red(*a, **k):
    raise AssertionError("un test intento usar la red real (urlopen)")


_patch_red = mock.patch("urllib.request.urlopen", _sin_red)


def setUpModule():
    _patch_red.start()


def tearDownModule():
    _patch_red.stop()


class FakeTG:
    """Doble de api.telegram.org: guarda la descripcion y los mensajes enviados."""
    def __init__(self, desc="", falla_envio=0):
        self.desc, self.enviados, self.falla, self.intentos = desc, [], falla_envio, 0

    def __call__(self, *a):  # (token, metodo, datos) en la nube; (metodo, datos) en el PC
        a = list(a)
        if a and a[0] == "TOK":
            a.pop(0)
        metodo, datos = a[0], (a[1] if len(a) > 1 else None)
        if metodo == "getMyDescription":
            return {"ok": True, "result": {"description": self.desc}}
        if metodo == "setMyDescription":
            self.desc = datos["description"]
            return {"ok": True, "result": True}
        if metodo == "sendMessage":
            self.intentos += 1
            if self.falla:
                self.falla -= 1
                raise OSError("red caida")
            self.enviados.append(datos["text"])
            return {"ok": True, "result": {}}
        raise AssertionError(metodo)




def estado(p=None, n=None):
    return "ESTADO " + json.dumps({"p": p or {}, "n": n or {}}, separators=(",", ":"))


def correr(tg, ahora, **kw):
    out = []
    with mock.patch("time.sleep"):
        rc = v.ejecutar("TOK", "1", ahora, api_fn=tg, salida=out.append, **kw)
    return rc, out


PCAIDO = {"a": T0, "f": 72, "s": 40, "rf": T0 + 3600, "rs": T0 + 86400}


class Nube(unittest.TestCase):
    def test_pc_vivo_no_avisa(self):
        tg = FakeTG(estado({**PCAIDO, "a": T0 + 600}))
        rc, _ = correr(tg, T0 + 900)
        self.assertEqual((rc, tg.enviados), (0, []))

    def test_pc_caido_avisa_una_vez_y_no_repite(self):
        tg = FakeTG(estado(PCAIDO))
        rc, _ = correr(tg, T0 + 30 * 60)
        self.assertEqual((rc, len(tg.enviados)), (0, 1))
        m = tg.enviados[0]
        for t in ("PC sin se", "Ventana 5 h:", "72 %", "Semanal:", "40 %", "hace 30 min", v.AMBAR, v.VERDE):
            self.assertIn(t, m)
        self.assertEqual(json.loads(tg.desc[7:])["n"]["av"], T0)
        correr(tg, T0 + 60 * 60)  # segunda ejecucion
        self.assertEqual(len(tg.enviados), 1)

    def test_vuelta_una_sola_vez(self):
        tg = FakeTG(estado({**PCAIDO, "a": T0 + 7200}, {"av": T0}))
        correr(tg, T0 + 7300)
        self.assertEqual(tg.enviados, [v.MENSAJE_VUELTA])
        self.assertNotIn("av", json.loads(tg.desc[7:])["n"])
        correr(tg, T0 + 7400)
        self.assertEqual(len(tg.enviados), 1)

    def test_nuevo_apagado_tras_vuelta_avisa_de_nuevo(self):
        tg = FakeTG(estado({**PCAIDO, "a": T0 + 7200}, {"av": T0}))
        correr(tg, T0 + 7300)
        correr(tg, T0 + 7200 + 3600)
        self.assertEqual(len(tg.enviados), 2)

    def test_porcentaje_nulo(self):
        tg = FakeTG(estado({"a": T0, "f": None, "s": None, "rf": 0, "rs": 0}))
        correr(tg, T0 + 3600)
        self.assertEqual(tg.enviados[0].count("sin dato"), 2)
        self.assertNotIn("None", tg.enviados[0])

    def test_mensaje_con_lectura_antigua(self):
        tg = FakeTG(estado({**PCAIDO, "t": T0 - 1800}))
        correr(tg, T0 + 3000)
        m = tg.enviados[0]
        self.assertIn("72 %", m)
        self.assertIn("leída a las %s" % v.hm(T0 - 1800), m)
        self.assertNotIn("sin dato", m)

    def test_porcentaje_caducado(self):
        tg = FakeTG(estado({**PCAIDO, "rf": T0 + 60}))
        correr(tg, T0 + 3600)
        m = tg.enviados[0]
        self.assertIn("ventana reiniciada", m)
        self.assertNotIn("72 %", m)
        self.assertIn("40 %", m)

    def test_estado_500_caracteres(self):
        n = {"av": T0 - 5, "al": ["x" * 30] * 8, "matinal": "2026-11-18"}
        tg = FakeTG(estado(PCAIDO, n))
        self.assertLessEqual(len(tg.desc), 500)
        correr(tg, T0 + 3600)
        est = json.loads(tg.desc[7:])  # JSON entero y valido
        self.assertEqual(est["n"]["av"], T0)
        self.assertEqual(est["n"]["matinal"], "2026-11-18")

    def test_dry_run_no_envia_ni_escribe(self):
        tg = FakeTG(estado(PCAIDO))
        antes = tg.desc
        rc, out = correr(tg, T0 + 3600, dry=True)
        self.assertEqual((rc, tg.enviados, tg.desc), (0, [], antes))
        self.assertIn("dry-run", out[0])

    def test_reintenta_y_falla_con_codigo_1(self):
        tg = FakeTG(estado(PCAIDO), falla_envio=5)
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "TOK", "TELEGRAM_CHAT_ID": "1"}), \
                mock.patch.object(v, "api", tg), mock.patch("time.sleep"):
            self.assertEqual(v.main(["--ahora", str(T0 + 3600)]), 1)
        self.assertEqual(tg.intentos, 3)  # exactamente 3 reintentos
        self.assertNotIn("av", json.loads(tg.desc[7:])["n"])  # sin marca: reintentara
        tg2 = FakeTG(estado(PCAIDO), falla_envio=2)  # 2 fallos y el 3.er intento funciona
        rc, _ = correr(tg2, T0 + 3600)
        self.assertEqual((rc, len(tg2.enviados)), (0, 1))

    def test_sin_estado_no_avisa(self):
        tg = FakeTG("")
        correr(tg, T0)
        self.assertEqual(tg.enviados, [])



class Silencio(unittest.TestCase):
    def test_silencioso_no_imprime_nada_informativo(self):
        import io, contextlib
        tg = FakeTG(estado({**PCAIDO, "a": T0 + 600}))
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "TOK", "TELEGRAM_CHAT_ID": "1"}),                 mock.patch.object(v, "api", tg), contextlib.redirect_stdout(buf):
            rc = v.main(["--silencioso", "--ahora", str(T0 + 900)])
        self.assertEqual((rc, buf.getvalue()), (0, ""))

    def test_error_no_filtra_token_ni_chat(self):
        import io, contextlib
        err = io.StringIO()
        def mala(*a, **k):
            raise OSError("fallo con TOKSECRETO y CHAT99")
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "TOKSECRETO", "TELEGRAM_CHAT_ID": "CHAT99"}),                 mock.patch.object(v, "api", mala), mock.patch("time.sleep"), contextlib.redirect_stderr(err):
            rc = v.main(["--silencioso"])
        self.assertEqual(rc, 1)
        self.assertNotIn("TOKSECRETO", err.getvalue())
        self.assertNotIn("CHAT99", err.getvalue())


if __name__ == "__main__":
    unittest.main()
