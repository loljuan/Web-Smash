"""Servidor local de la interfaz (http://127.0.0.1:7860)."""

from __future__ import annotations

import io
import tempfile
import threading
import traceback
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
from PIL import Image
from werkzeug.exceptions import HTTPException

from . import core

WEB_DIR = core.TOOL_DIR / "web"
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

FIGHTERS = [
    "mario", "donkey", "link", "samus", "samusd", "yoshi", "kirby", "fox", "pikachu", "luigi", "ness",
    "captain", "purin", "peach", "daisy", "koopa", "ice_climber", "sheik", "zelda", "mariod", "pichu",
    "falco", "marth", "lucina", "younglink", "ganon", "mewtwo", "roy", "chrom", "gamewatch", "metaknight",
    "pit", "pitb", "szerosuit", "wario", "snake", "ike", "ptrainer", "pzenigame", "pfushigisou", "plizardon",
    "diddy", "lucas", "sonic", "dedede", "pikmin", "lucario", "robot", "toonlink", "wolf", "murabito",
    "rockman", "wiifit", "rosetta", "littlemac", "gekkouga", "palutena", "pacman", "reflet", "shulk",
    "koopajr", "duckhunt", "ryu", "ken", "cloud", "kamui", "bayonetta", "inkling", "ridley", "simon",
    "richter", "krool", "shizue", "gaogaen", "miifighter", "miiswordsman", "miigunner", "packun", "jack",
    "brave", "buddy", "dolly", "master", "tantan", "pickel", "edge", "eflame", "elight", "demon", "trail",
]


def ok(data=None, **extra):
    payload = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return jsonify(payload)


@app.errorhandler(Exception)
def on_error(exc):
    if isinstance(exc, HTTPException):
        return exc
    traceback.print_exc()
    status = 404 if isinstance(exc, FileNotFoundError) else 400 if isinstance(exc, ValueError) else 500
    return jsonify({"ok": False, "error": str(exc)}), status


def png_response(img: Image.Image, name: str = "imagen.png"):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    resp = send_file(buf, mimetype="image/png", download_name=name)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def project_payload(p: core.Project) -> dict:
    presets = core.load_presets()["charas"]
    return {
        **p.data,
        "tamano": list(p.original.size),
        "presets": {c: presets[c] for c in p.data["charas"]},
        "nombres": {c: p.file_name(c) for c in p.data["charas"]},
        "referencias": {c: bool(core.reference_path(c)) for c in p.data["charas"]},
        "analisis": p.analysis(),
    }


# ------------------------------------------------------------------ páginas


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/web/<path:name>")
def web_file(name):
    resp = send_from_directory(WEB_DIR, name)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ------------------------------------------------------------------ estado


@app.get("/api/estado")
def estado():
    try:
        core.charatex_path()
        charatex = True
    except RuntimeError:
        charatex = False
    return ok(
        {
            "presets": core.load_presets(),
            "modelos": core.BG_MODELS,
            "modelo_defecto": core.DEFAULT_MODEL,
            "luchadores": FIGHTERS,
            "proyectos": core.list_projects(),
            "charatex": charatex,
            "referencias": {c: bool(core.reference_path(c)) for c in core.chara_ids()},
        }
    )


@app.post("/api/presets")
def guardar_presets():
    body = request.get_json(force=True)
    data = core.load_presets()
    for c, values in body.get("charas", {}).items():
        if c not in data["charas"]:
            continue
        for key in ("width", "height", "mipmaps"):
            if key in values:
                v = int(values[key])
                if key != "mipmaps" and (v < 4 or v > 4096 or v % 4):
                    raise ValueError(f"chara_{c}: {key} debe ser múltiplo de 4 entre 4 y 4096")
                data["charas"][c][key] = v
        for key in ("format", "encuadre", "guia", "nombre"):
            if key in values:
                data["charas"][c][key] = str(values[key])
        if "sombra" in values:
            data["charas"][c]["sombra"] = values["sombra"]
    core.save_presets(data)
    return ok(data)


# ------------------------------------------------------------------ proyectos


@app.post("/api/proyectos")
def crear_proyecto():
    f = request.files.get("imagen")
    if not f:
        raise ValueError("Falta la imagen")
    charas = [c for c in request.form.get("charas", "").split(",") if c] or None
    p = core.Project.create(
        f.read(),
        fighter=request.form.get("fighter", ""),
        slot=int(request.form.get("slot", 0)),
        charas=charas,
        model=request.form.get("modelo", core.DEFAULT_MODEL),
        remove_bg=request.form.get("fondo", "auto"),
        name=request.form.get("nombre") or None,
    )
    return ok(project_payload(p))


@app.get("/api/proyectos/<pid>")
def ver_proyecto(pid):
    return ok(project_payload(core.Project(pid)))


@app.post("/api/proyectos/<pid>/datos")
def editar_datos(pid):
    p = core.Project(pid)
    body = request.get_json(force=True)
    if "fighter" in body:
        fighter = str(body["fighter"]).strip().lower()
        if not core.FIGHTER_RE.match(fighter):
            raise ValueError("Nombre interno no válido (solo a-z, 0-9 y _).")
        p.data["fighter"] = fighter
    if "slot" in body:
        p.data["slot"] = int(body["slot"])
    if "charas" in body:
        p.data["charas"] = [str(c) for c in body["charas"]]
        for c in p.data["charas"]:
            p.settings(c)
    p.save()
    return ok(project_payload(p))


@app.get("/api/proyectos/<pid>/imagen/<kind>")
def imagen(pid, kind):
    p = core.Project(pid)
    if kind == "original":
        return png_response(p.original)
    if kind == "mascara":
        return png_response(p.mask)
    if kind == "recorte":
        return png_response(p.cutout())
    raise FileNotFoundError(kind)


@app.post("/api/proyectos/<pid>/mascara")
def subir_mascara(pid):
    p = core.Project(pid)
    f = request.files.get("mascara")
    if not f:
        raise ValueError("Falta la máscara")
    mask = Image.open(f.stream).convert("RGBA")
    # La interfaz pinta la máscara en el canal rojo.
    p.set_mask(mask.getchannel("R"))
    return ok(project_payload(p))


@app.post("/api/proyectos/<pid>/mascara/ops")
def operar_mascara(pid):
    p = core.Project(pid)
    p.set_mask(core.mask_ops(p.mask, request.get_json(force=True)))
    return ok(project_payload(p))


@app.post("/api/proyectos/<pid>/fondo")
def rehacer_fondo(pid):
    p = core.Project(pid)
    body = request.get_json(force=True)
    how = p.compute_mask(remove_bg=body.get("fondo", "si"), model=body.get("modelo"))
    return ok(project_payload(p), metodo=how)


@app.post("/api/proyectos/<pid>/cabeza")
def cabeza(pid):
    p = core.Project(pid)
    body = request.get_json(force=True)
    p.set_head(body.get("cabeza"))
    return ok(project_payload(p))


@app.get("/api/proyectos/<pid>/chara/<c>/preview")
def preview(pid, c):
    p = core.Project(pid)
    return png_response(p.render(c))


@app.post("/api/proyectos/<pid>/chara/<c>")
def ajustar(pid, c):
    p = core.Project(pid)
    body = request.get_json(force=True)
    allowed = {k: body[k] for k in ("zoom", "x", "y", "flip", "rot", "sombra") if k in body}
    return ok(p.update(c, **allowed))


@app.post("/api/proyectos/<pid>/chara/<c>/auto")
def auto(pid, c):
    p = core.Project(pid)
    s = p.auto_frame(c)
    p.save()
    return ok(s)


@app.post("/api/proyectos/<pid>/chara/<c>/exportar")
def exportar(pid, c):
    return ok(core.Project(pid).export(c))


@app.get("/api/proyectos/<pid>/chara/<c>/descargar")
def descargar(pid, c):
    p = core.Project(pid)
    info = p.export(c)
    kind = request.args.get("tipo", "bntx")
    path = Path(info["bntx"] if kind == "bntx" else info["png"])
    return send_file(path, as_attachment=True, download_name=path.name)


@app.get("/api/proyectos/<pid>/zip")
def zip_all(pid):
    p = core.Project(pid)
    p.export_all()
    z = p.zip_output()
    return send_file(z, as_attachment=True, download_name=z.name)


@app.get("/api/proyectos/<pid>/hoja")
def hoja(pid):
    p = core.Project(pid)
    return send_file(p.contact_sheet(), mimetype="image/png")


# ------------------------------------------------------------------ calibración y utilidades


@app.post("/api/calibrar")
def calibrar():
    files = request.files.getlist("archivos")
    folder = request.form.get("carpeta")
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for f in files:
            dst = Path(tmp) / Path(f.filename).name
            f.save(dst)
            paths.append(dst)
        if folder:
            paths.append(Path(folder))
        if not paths:
            raise ValueError("Sube algún BNTX original o indica una carpeta.")
        return ok(core.calibrate(paths))


@app.get("/api/referencia/<c>")
def referencia(c):
    path = core.reference_path(c)
    if not path:
        raise FileNotFoundError("Sin referencia")
    resp = send_file(path, mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.post("/api/bntx/info")
def info_bntx():
    f = request.files.get("archivo")
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / Path(f.filename).name
        f.save(dst)
        return ok(core.bntx_info(dst))


@app.post("/api/bntx/a-png")
def bntx_a_png():
    f = request.files.get("archivo")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / Path(f.filename).name
        f.save(src)
        dst = Path(tmp) / (src.stem + ".png")
        core.bntx_to_png(src, dst)
        return png_response(Image.open(dst).copy(), dst.name)


def main(port: int = 7860, open_browser: bool = True):
    url = f"http://127.0.0.1:{port}"
    print(f"\n  Generador de charas listo en {url}\n  (cierra esta ventana para apagarlo)\n")
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        from waitress import serve

        serve(app, host="127.0.0.1", port=port, threads=4)
    except ImportError:
        app.run(host="127.0.0.1", port=port, threaded=True)
