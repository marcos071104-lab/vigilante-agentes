#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vigilante del PC (nube, solo stdlib, 0 tokens). Si el PC no da latido, avisa UNA vez por Telegram con el % de Claude.

Estado compartido: descripcion del bot, `ESTADO {"p":{a,f,s,rf,rs},"n":{av}}` (<500 caracteres). El PC escribe SOLO "p";
este script SOLO "n" (n.av = valor de p.a ya avisado). Variables: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
  python3 vigilante_pc.py [--tolerancia 25] [--dry-run] [--ahora <epoch>]
Salida: 0 ok / sin novedad; 1 si no pudo enviar o leer el estado.
"""
import argparse, html, json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TOL_MIN = 25
MADRID = ZoneInfo("Europe/Madrid")
VERDE, AMBAR, ROJO = "\U0001F7E2", "\U0001F7E1", "\U0001F534"


def barra(p, n=10):
    k = round(max(0.0, min(100.0, float(p))) / 100 * n)
    return "\u25B0" * k + "\u25B1" * (n - k)


def semaforo(p, ambar=60, rojo=85):
    return ROJO if p >= rojo else AMBAR if p >= ambar else VERDE


def hm(ts):
    return datetime.fromtimestamp(ts, MADRID).strftime("%H:%M")


def cuando(ts, ref):
    d, r = datetime.fromtimestamp(ts, MADRID), datetime.fromtimestamp(ref, MADRID)
    if d.date() == r.date():
        return d.strftime("%H:%M")
    dias = ("lun", "mar", "mi\u00e9", "jue", "vie", "s\u00e1b", "dom")
    return "%s %s" % (dias[d.weekday()], d.strftime("%d/%m %H:%M"))


def api(token, metodo, datos=None, timeout=30):
    cuerpo = urllib.parse.urlencode(datos).encode() if datos is not None else None
    with urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{token}/{metodo}", data=cuerpo), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def con_reintentos(fn, intentos=3, espera=2):
    for i in range(intentos):
        try:
            return fn()
        except Exception:
            if i == intentos - 1:
                raise
            time.sleep(espera * (i + 1))


def leer_estado(token, api_fn=None):
    api_fn = api_fn or api  # se resuelve al llamar (permite parchear v.api)
    d = con_reintentos(lambda: api_fn(token, "getMyDescription")).get("result", {}).get("description", "") or ""
    m = re.search(r"ESTADO (\{.*\})", d)
    try:
        est = json.loads(m.group(1)) if m else {}
    except ValueError:
        est = {}
    return {"p": dict(est.get("p") or {}), "n": dict(est.get("n") or {})}


def descripcion(est):
    return "ESTADO " + json.dumps(est, separators=(",", ":"), ensure_ascii=False)


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def linea(etq, pct, reset, ahora, t=None):
    """Fila con barra, semaforo y hora de la ultima lectura (t); si el reset ya paso, 'ventana reiniciada';
    'sin dato' solo si nunca hubo lectura."""
    pct, reset, t = _num(pct), _num(reset) or 0, _num(t)
    if pct is None:
        return "%s sin dato" % etq
    if reset and reset <= ahora:
        return "%s \u267B ventana reiniciada" % etq
    extra = []
    if t:
        extra.append("le\u00EDda a las %s" % cuando(t, ahora))
    if reset:
        extra.append("se reinicia a las %s" % cuando(reset, ahora))
    return "%s %s %s %d %%%s" % (etq, semaforo(pct), barra(pct), round(pct), " (%s)" % ", ".join(extra) if extra else "")


def mensaje_caido(p, ahora):
    a = float(p["a"])
    return "\n".join([
        "\U0001F50C <b>PC sin se\u00f1al desde %s</b> (Madrid)" % hm(a), "",
        html.escape(linea("Ventana 5 h:", p.get("f"), p.get("rf"), ahora, p.get("t")), quote=False),
        html.escape(linea("Semanal:", p.get("s"), p.get("rs"), ahora, p.get("t")), quote=False), "",
        "\u23F1 \u00daltima lectura hace %d min" % max(0, int((ahora - a) // 60))])


MENSAJE_VUELTA = "\u2705 <b>PC de vuelta</b>"


def decidir(est, ahora, tol_min=TOL_MIN):
    """('caido', msg) | ('vuelta', msg) | (None, motivo)."""
    a, av = _num(est["p"].get("a")), _num(est["n"].get("av"))
    if a is None:
        return None, "sin latido del PC en el estado (nunca escribio): no se avisa"
    if ahora - a > tol_min * 60:
        if av == a:
            return None, "ya avisado de este apagado"
        return "caido", mensaje_caido(est["p"], ahora)
    if av is not None and a > av:
        return "vuelta", MENSAJE_VUELTA
    return None, "PC vivo (latido hace %d min)" % int((ahora - a) // 60)


def _ok(r):
    if not r.get("ok"):
        raise RuntimeError("Telegram: %s" % r.get("description"))
    return r


def ejecutar(token, chat, ahora, tol_min=TOL_MIN, dry=False, api_fn=None, salida=print):
    api_fn = api_fn or api
    est = leer_estado(token, api_fn)
    accion, txt = decidir(est, ahora, tol_min)
    if accion is None:
        salida("Sin aviso: " + txt)
        return 0
    if dry:
        salida("[dry-run] %s:\n%s" % (accion, txt))
        return 0
    # una sola llamada por intento: si falla lanza, no se marca y la siguiente ejecucion reintenta
    con_reintentos(lambda: _ok(api_fn(token, "sendMessage", {"chat_id": chat, "text": txt, "parse_mode": "HTML",
                                                              "disable_web_page_preview": "true"})))
    est = leer_estado(token, api_fn)  # relee: el PC puede haber escrito "p" mientras tanto
    if accion == "caido":
        a = _num(est["p"].get("a"))
        est["n"]["av"] = int(a) if a is not None else 0
    else:
        est["n"].pop("av", None)
    con_reintentos(lambda: _ok(api_fn(token, "setMyDescription", {"description": descripcion(est)})))
    salida("Enviado: " + accion)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tolerancia", type=float, default=TOL_MIN, help="minutos sin latido antes de avisar (25)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--silencioso", action="store_true", help="repo publico: no imprime nada informativo en los logs")
    ap.add_argument("--ahora", type=float, default=None, help="epoch (para pruebas)")
    a = ap.parse_args(argv)
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or (not chat and not a.dry_run):
        print("Faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID", file=sys.stderr)
        return 1
    try:
        salida = (lambda *_a: None) if a.silencioso else print
        return ejecutar(token, chat, a.ahora if a.ahora is not None else time.time(), a.tolerancia, a.dry_run, salida=salida)
    except Exception as e:
        txt = str(e).replace(token, "***")
        if chat:
            txt = txt.replace(chat, "***")
        print("Error: %s" % txt, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
