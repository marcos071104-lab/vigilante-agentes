r"""Anti-secretos y lista blanca. Sin red. Ejecutar: python tests/test_sin_secretos.py

Revisa los archivos de las replicas `repo_privado_mercado/` y `repo_publico_vigilante/` si existen junto al proyecto;
si no (copia dentro de un repo), revisa la raiz del propio repo. Falla si encuentra:
  - token de Telegram (\d{8,10}:[A-Za-z0-9_-]{35}), claves sk-ant-..., ghp_/github_pat_/gho_/ghs_...
  - un chat_id numerico asignado, o un bot_token/token con valor real
  - archivos fuera de la lista blanca de su repo.
Es identico en las 3 ubicaciones (proyecto, privado, publico): al cambiarlo, copiarlo a las tres.
"""
import fnmatch
import re
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent

BLANCA_PRIVADO = [
    ".gitignore", "config.ejemplo.json", "config_alertas.json", "ejecutor.py", "libro_dia.py", "horario.py",
    "mensajes_telegram.py", "ia_informes.py", "alertas_ventanas.py", "alertas_mercado.py", "registro_envios.py",
    "datos_apertura.py", "datos_mercado.py", "nube/enviar_texto.py", "nube/probar_fuentes.py",
    ".github/workflows/bot.yml", ".github/workflows/probar_fuentes.yml", "tests/test_*.py",
]
BLANCA_PUBLICO = [
    ".gitignore", "README.md", "nube/vigilante_pc.py", ".github/workflows/vigilante_pc.yml",
    ".github/workflows/keepalive.yml", "tests/test_vigilante.py", "tests/test_sin_secretos.py",
]
IGNORAR_DIRS = {"__pycache__", ".git"}

PATRONES = {
    "token de Telegram": re.compile(r"\d{8,10}:[A-Za-z0-9_-]{35}"),
    "clave Anthropic (sk-ant-)": re.compile(r"sk-ant-[A-Za-z0-9_-]{6,}"),
    "token de GitHub": re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"),
    "chat_id numerico asignado": re.compile(r"""chat_?id["']?\s*[:=]\s*["']?-?\d{5,}""", re.I),
    "token asignado con valor": re.compile(r"""(?:bot_token|token)["']\s*:\s*["'][A-Za-z0-9:_-]{20,}["']""", re.I),
}


def _raices():
    pri, pub = RAIZ / "repo_privado_mercado", RAIZ / "repo_publico_vigilante"
    r = [(d, bl) for d, bl in ((pri, BLANCA_PRIVADO), (pub, BLANCA_PUBLICO)) if d.is_dir()]
    if r:
        return r
    return [(RAIZ, BLANCA_PRIVADO if (RAIZ / "ejecutor.py").exists() else BLANCA_PUBLICO)]


def _archivos(raiz):
    for p in sorted(raiz.rglob("*")):
        if p.is_file() and not (set(p.relative_to(raiz).parts) & IGNORAR_DIRS):
            yield p


class SinSecretos(unittest.TestCase):
    def test_hay_algo_que_revisar(self):
        self.assertTrue(any(True for r, _ in _raices() for _ in _archivos(r)))

    def test_lista_blanca(self):
        fuera = []
        for raiz, blanca in _raices():
            for p in _archivos(raiz):
                rel = p.relative_to(raiz).as_posix()
                if not any(fnmatch.fnmatchcase(rel, pat) for pat in blanca):
                    fuera.append(f"{raiz.name}/{rel}")
        self.assertEqual(fuera, [], "archivos fuera de la lista blanca")

    def test_sin_patrones_de_secretos(self):
        malos = []
        for raiz, _ in _raices():
            for p in _archivos(raiz):
                try:
                    txt = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for nombre, rx in PATRONES.items():
                    if rx.search(txt):
                        malos.append(f"{raiz.name}/{p.relative_to(raiz).as_posix()}: {nombre}")  # sin imprimir el valor
        self.assertEqual(malos, [], "posibles secretos")

    def test_detector_funciona(self):
        falso_tg = "12345678" + ":" + "A" * 35
        self.assertTrue(PATRONES["token de Telegram"].search("x " + falso_tg))
        self.assertTrue(PATRONES["clave Anthropic (sk-ant-)"].search("sk-ant-" + "abc123def"))
        self.assertTrue(PATRONES["token de GitHub"].search("ghp_" + "a" * 36))
        self.assertTrue(PATRONES["chat_id numerico asignado"].search('"chat_id": "' + "1" * 9 + '"'))
        self.assertFalse(PATRONES["chat_id numerico asignado"].search('"chat_id": ""'))


if __name__ == "__main__":
    unittest.main()
