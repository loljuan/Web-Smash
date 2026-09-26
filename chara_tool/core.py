"""Núcleo del generador de charas: recorte de fondo, encuadre, sombra y BNTX.

Todo lo que hace la interfaz web y la línea de comandos pasa por aquí.
"""

from __future__ import annotations

import io
import json
import math
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
TOOL_DIR = ROOT / "chara_tool"
PRESETS_FILE = TOOL_DIR / "presets.json"
REFS_DIR = TOOL_DIR / "referencias"
PROJECTS_DIR = ROOT / "proyectos"
BIN_DIR = ROOT / "bin"

# La imagen de trabajo se limita a este lado máximo: el chara más grande es
# mucho menor, así que no se pierde calidad y todo va más rápido.
WORK_MAX_SIDE = 2048

BG_MODELS = {
    "isnet-general-use": "General (renders 3D y fotos) · recomendado",
    "isnet-anime": "Anime / ilustraciones 2D",
    "u2net": "u2net (clásico)",
    "birefnet-general": "BiRefNet (máxima calidad, lento, descarga ~1 GB)",
}
DEFAULT_MODEL = "isnet-general-use"

FIGHTER_RE = re.compile(r"^[a-z0-9_]+$")


# ---------------------------------------------------------------- presets


def load_presets() -> dict:
    return json.loads(PRESETS_FILE.read_text(encoding="utf-8"))


def save_presets(data: dict) -> None:
    PRESETS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def chara_ids() -> list[str]:
    return sorted(load_presets()["charas"].keys(), key=int)


def preset(chara: str) -> dict:
    return load_presets()["charas"][str(chara)]


# ---------------------------------------------------------------- charatex


def charatex_path() -> str:
    env = os.environ.get("CHARATEX")
    if env:
        return env
    system = platform.system()
    candidates = [BIN_DIR / "charatex.exe"] if system == "Windows" else [BIN_DIR / "charatex-linux", BIN_DIR / "charatex"]
    for c in candidates:
        if c.exists():
            if system != "Windows":
                c.chmod(c.stat().st_mode | 0o111)
            return str(c)
    found = shutil.which("charatex")
    if found:
        return found
    raise RuntimeError(
        "No encuentro charatex. En Windows debe estar en bin/charatex.exe; en otros sistemas "
        "compílalo con tools/charatex/build.sh o define la variable CHARATEX."
    )


def run_charatex(*args: str) -> dict:
    proc = subprocess.run([charatex_path(), *args], capture_output=True, text=True)
    out = (proc.stdout or "").strip().splitlines()
    try:
        data = json.loads(out[-1]) if out else {}
    except json.JSONDecodeError:
        data = {"ok": False, "error": proc.stdout + proc.stderr}
    if proc.returncode != 0 or data.get("ok") is False:
        raise RuntimeError(data.get("error") or proc.stderr or "charatex falló")
    return data


def bntx_info(path: str | Path) -> dict:
    return run_charatex("info", str(path))


def bntx_to_png(src: str | Path, dst: str | Path) -> None:
    run_charatex("decode", str(src), str(dst))


def png_to_bntx(img: Image.Image, dst: Path, fmt: str, mipmaps: int) -> dict:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "entrada.png"
        img.save(png)
        return run_charatex("encode", str(png), str(dst), "--format", fmt, "--mipmaps", str(mipmaps), "--quality", "slow")


# ---------------------------------------------------------------- imagen


def fit_work_size(img: Image.Image) -> Image.Image:
    w, h = img.size
    side = max(w, h)
    if side <= WORK_MAX_SIDE:
        return img
    k = WORK_MAX_SIDE / side
    return img.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)


def content_box(mask: Image.Image, size: tuple[int, int], margin: float = 0.04) -> tuple[int, int, int, int]:
    bbox = mask.point(lambda v: 255 if v > 8 else 0).getbbox()
    if not bbox:
        return (0, 0, *size)
    x0, y0, x1, y1 = bbox
    m = int(max(x1 - x0, y1 - y0) * margin) + 2
    return (max(0, x0 - m), max(0, y0 - m), min(size[0], x1 + m), min(size[1], y1 + m))


def crop_to_content(img: Image.Image, mask: Image.Image) -> Image.Image:
    return img.crop(content_box(mask, img.size))


def has_transparency(img: Image.Image) -> bool:
    if img.mode != "RGBA":
        return False
    a = np.asarray(img.getchannel("A"))
    return (a < 250).mean() > 0.02


_sessions: dict = {}


def remove_background(img: Image.Image, model: str = DEFAULT_MODEL) -> Image.Image:
    """Devuelve la máscara (modo L) del personaje usando rembg."""
    try:
        from rembg import new_session, remove
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Falta rembg. Ejecuta: pip install -r requirements.txt") from exc
    if model not in _sessions:
        _sessions[model] = new_session(model)
    mask = remove(img.convert("RGB"), session=_sessions[model], only_mask=True, post_process_mask=True)
    return mask.convert("L")


def clean_colors(rgb: Image.Image, mask: Image.Image) -> Image.Image:
    """Quita el halo del fondo antiguo en los bordes semitransparentes."""
    try:
        from pymatting import estimate_foreground_ml
    except ImportError:
        return rgb
    arr = np.asarray(rgb.convert("RGB"), dtype=np.float64) / 255.0
    alpha = np.asarray(mask, dtype=np.float64) / 255.0
    if not ((alpha > 0.02) & (alpha < 0.98)).any():
        return rgb
    fg = estimate_foreground_ml(arr, alpha)
    return Image.fromarray(np.clip(fg * 255 + 0.5, 0, 255).astype(np.uint8), "RGB")


# ---------------------------------------------------------------- máscara


def mask_ops(mask: Image.Image, ops: dict) -> Image.Image:
    """Operaciones de corrección de la máscara.

    ops admite: erase_rects / restore_rects [[x,y,w,h],...], erase_circles /
    restore_circles [[cx,cy,r],...], fill_holes (bool), remove_islands (fracción
    del trozo más grande, p. ej. 0.02), grow (px, negativo = contraer),
    feather (px de suavizado), hard (0..1 endurecer bordes).
    Coordenadas en píxeles de la imagen de trabajo.
    """
    m = mask.copy()
    draw = ImageDraw.Draw(m)
    for x, y, w, h in ops.get("erase_rects", []):
        draw.rectangle([x, y, x + w, y + h], fill=0)
    for x, y, w, h in ops.get("restore_rects", []):
        draw.rectangle([x, y, x + w, y + h], fill=255)
    for cx, cy, r in ops.get("erase_circles", []):
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
    for cx, cy, r in ops.get("restore_circles", []):
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)

    if ops.get("fill_holes") or ops.get("remove_islands"):
        from scipy import ndimage

        arr = np.asarray(m).copy()
        solid = arr > 127
        if ops.get("remove_islands"):
            labels, n = ndimage.label(solid)
            if n > 1:
                sizes = ndimage.sum(solid, labels, range(1, n + 1))
                keep = sizes >= float(ops["remove_islands"]) * sizes.max()
                bad = ~keep[labels - 1] & (labels > 0)
                arr[bad] = 0
                solid = arr > 127
        if ops.get("fill_holes"):
            filled = ndimage.binary_fill_holes(solid)
            arr[filled & ~solid] = 255
        m = Image.fromarray(arr, "L")

    grow = int(ops.get("grow", 0))
    if grow > 0:
        m = m.filter(ImageFilter.MaxFilter(2 * grow + 1))
    elif grow < 0:
        m = m.filter(ImageFilter.MinFilter(2 * -grow + 1))
    hard = float(ops.get("hard", 0))
    if hard > 0:
        arr = np.asarray(m, dtype=np.float32) / 255.0
        k = 1 + hard * 12
        arr = np.clip((arr - 0.5) * k + 0.5, 0, 1)
        m = Image.fromarray((arr * 255 + 0.5).astype(np.uint8), "L")
    feather = float(ops.get("feather", 0))
    if feather > 0:
        m = m.filter(ImageFilter.GaussianBlur(feather))
    return m


# ---------------------------------------------------------------- proyectos


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "proyecto"


class Project:
    """Un personaje en proceso. Vive en proyectos/<id>/."""

    def __init__(self, pid: str):
        self.id = pid
        self.dir = PROJECTS_DIR / pid
        if not self.dir.exists():
            raise FileNotFoundError(f"No existe el proyecto {pid}")
        self.data = json.loads((self.dir / "proyecto.json").read_text(encoding="utf-8"))
        self._cutout = None
        self._cutout_key = None

    # ---- creación
    @classmethod
    def create(
        cls,
        image_bytes: bytes,
        fighter: str,
        slot: int = 0,
        charas: list[str] | None = None,
        model: str = DEFAULT_MODEL,
        remove_bg: str = "auto",
        name: str | None = None,
    ) -> "Project":
        fighter = fighter.strip().lower()
        if not FIGHTER_RE.match(fighter):
            raise ValueError("El nombre interno del luchador solo puede tener a-z, 0-9 y _ (ej: mario, pikachu, dragon_king).")
        if not 0 <= int(slot) <= 255:
            raise ValueError("El slot debe estar entre 0 y 255.")
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
        full = img.convert("RGBA")
        if has_transparency(full):
            full = crop_to_content(full, full.getchannel("A"))
        img = fit_work_size(full)
        PROJECTS_DIR.mkdir(exist_ok=True)
        base = slugify(name or f"{fighter}-c{int(slot):02d}")
        pid = base
        n = 2
        while (PROJECTS_DIR / pid).exists():
            pid = f"{base}-{n}"
            n += 1
        d = PROJECTS_DIR / pid
        d.mkdir(parents=True)
        img.save(d / "original.png")
        data = {
            "id": pid,
            "fighter": fighter,
            "slot": int(slot),
            "charas": charas or chara_ids(),
            "modelo": model,
            "creado": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ajustes": {},
            "fondo": "",
        }
        (d / "proyecto.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        p = cls(pid)
        p.compute_mask(remove_bg=remove_bg, model=model)
        # Si el personaje ocupa poca parte de una foto grande, se recorta la
        # imagen a resolución completa y se vuelve a quitar el fondo sobre ella.
        box = content_box(p.mask, img.size)
        area = (box[2] - box[0]) * (box[3] - box[1]) / (img.width * img.height)
        if area < 0.6 and full.size != img.size:
            k = full.width / img.width
            big_box = tuple(round(v * k) for v in box)
            fit_work_size(full.crop(big_box)).save(d / "original.png")
            p.compute_mask(remove_bg=remove_bg, model=model)
        p.crop_to_character()
        for c in p.data["charas"]:
            p.auto_frame(c)
        p.save()
        return p

    def save(self) -> None:
        (self.dir / "proyecto.json").write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- archivos
    @property
    def original(self) -> Image.Image:
        return Image.open(self.dir / "original.png").convert("RGBA")

    @property
    def mask(self) -> Image.Image:
        return Image.open(self.dir / "mascara.png").convert("L")

    def set_mask(self, mask: Image.Image, clean: bool = True) -> None:
        mask = mask.convert("L").resize(self.original.size) if mask.size != self.original.size else mask.convert("L")
        mask.save(self.dir / "mascara.png")
        if clean:
            rgb = clean_colors(self.original.convert("RGB"), mask)
            rgb.save(self.dir / "color_limpio.png")
        self._cutout = None

    def compute_mask(self, remove_bg: str = "auto", model: str | None = None) -> str:
        """remove_bg: 'auto' (solo si la imagen no es ya transparente), 'si' o 'no'."""
        img = self.original
        model = model or self.data.get("modelo", DEFAULT_MODEL)
        if remove_bg == "no" or (remove_bg == "auto" and has_transparency(img)):
            mask = img.getchannel("A")
            how = "transparencia de la imagen"
        else:
            mask = remove_background(img, model)
            if img.getchannel("A").getextrema()[0] < 255:
                mask = Image.fromarray(np.minimum(np.asarray(mask), np.asarray(img.getchannel("A"))), "L")
            how = f"IA ({model})"
        self.data["fondo"] = how
        self.data["modelo"] = model
        self.set_mask(mask)
        self.save()
        return how

    def crop_to_character(self) -> None:
        """Recorta la imagen de trabajo al personaje (con margen) para no
        desperdiciar resolución en zonas vacías."""
        mask = self.mask
        box = content_box(mask, self.original.size)
        if box == (0, 0, *self.original.size):
            return
        for name in ("original.png", "mascara.png", "color_limpio.png"):
            f = self.dir / name
            if f.exists():
                Image.open(f).crop(box).save(f)
        self._cutout = None

    def cutout(self) -> Image.Image:
        key = (self.dir / "mascara.png").stat().st_mtime_ns
        if self._cutout is not None and self._cutout_key == key:
            return self._cutout
        clean = self.dir / "color_limpio.png"
        rgb = Image.open(clean).convert("RGB") if clean.exists() else self.original.convert("RGB")
        out = rgb.convert("RGBA")
        out.putalpha(self.mask)
        self._cutout, self._cutout_key = out, key
        return out

    # ---- encuadre
    def analysis(self) -> dict:
        key = ((self.dir / "mascara.png").stat().st_mtime_ns, json.dumps(self.data.get("cabeza")))
        if getattr(self, "_analysis_key", None) != key:
            self._analysis = analyse(self.cutout(), self.data.get("cabeza"))
            self._analysis_key = key
        return self._analysis

    def set_head(self, head: list | None, reframe: bool = True) -> None:
        """Marca a mano la cabeza [cx, cy, tamaño] (None = automático) y reencuadra."""
        self.data["cabeza"] = [float(v) for v in head] if head else None
        if reframe:
            for c in self.data["charas"]:
                self.auto_frame(c)
        self.save()

    def settings(self, chara: str) -> dict:
        chara = str(chara)
        if chara not in self.data["ajustes"]:
            self.auto_frame(chara)
        return self.data["ajustes"][chara]

    def auto_frame(self, chara: str) -> dict:
        chara = str(chara)
        p = preset(chara)
        W, H = p["width"], p["height"]
        info = self.analysis()
        zoom, x, y = frame_for(p["encuadre"], W, H, info)
        self.data["ajustes"][chara] = {
            "zoom": zoom,
            "x": x,
            "y": y,
            "flip": False,
            "rot": 0,
            "sombra": None,
        }
        return self.data["ajustes"][chara]

    def update(self, chara: str, **changes) -> dict:
        s = self.settings(chara)
        for k, v in changes.items():
            if v is not None:
                s[k] = v
        self.save()
        return s

    # ---- render y exportación
    def render(self, chara: str, size: tuple[int, int] | None = None) -> Image.Image:
        chara = str(chara)
        p = preset(chara)
        s = self.settings(chara)
        W, H = size or (p["width"], p["height"])
        k = W / p["width"]
        base = self.cutout()
        src = transformed(base, s.get("flip", False), s.get("rot", 0))
        # Si al girar la imagen creció, se desplaza para que siga centrada donde estaba.
        ox = (src.width - base.width) / 2 * s["zoom"]
        oy = (src.height - base.height) / 2 * s["zoom"]
        canvas = place(src, W, H, s["zoom"] * k, (s["x"] - ox) * k, (s["y"] - oy) * k)
        shadow_cfg = s.get("sombra") or p["sombra"]
        return add_shadow(canvas, shadow_cfg)

    def file_name(self, chara: str) -> str:
        p = preset(chara)
        slot = self.data["slot"] if p.get("alts", True) else 0
        return f"chara_{chara}_{self.data['fighter']}_{slot:02d}"

    def export(self, chara: str) -> dict:
        chara = str(chara)
        p = preset(chara)
        img = self.render(chara)
        name = self.file_name(chara)
        out = self.dir / "salida"
        png_path = out / "png" / f"{name}.png"
        png_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(png_path)
        bntx_path = out / "ui" / "replace" / "chara" / f"chara_{chara}" / f"{name}.bntx"
        png_to_bntx(img, bntx_path, p["format"], int(p.get("mipmaps", 1)))
        return {"chara": chara, "nombre": name, "png": str(png_path), "bntx": str(bntx_path), "width": img.width, "height": img.height, "format": p["format"]}

    def export_all(self) -> list[dict]:
        return [self.export(c) for c in self.data["charas"]]

    def zip_output(self) -> Path:
        out = self.dir / "salida"
        zpath = self.dir / f"{self.id}_charas.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted((out / "ui").rglob("*.bntx")):
                z.write(f, f.relative_to(out))
        return zpath

    def contact_sheet(self) -> Path:
        path = self.dir / "hoja.png"
        sheet(self, path)
        return path


# ---------------------------------------------------------------- geometría


def analyse_silhouette(cutout: Image.Image) -> dict:
    """Caja del personaje y estimación de dónde está la cabeza por su silueta.

    La cabeza se busca como el círculo más grande que cabe dentro de la silueta
    en la parte alta del personaje (transformada de distancia), dando algo de
    preferencia a lo que está más arriba. Funciona bien con humanoides y con
    personajes redondos; si falla, se corrige a mano en el encuadre.
    """
    from scipy import ndimage

    full_w, full_h = cutout.size
    k = min(1.0, 400 / max(full_w, full_h))
    small = cutout.getchannel("A").resize((max(1, round(full_w * k)), max(1, round(full_h * k))), Image.BILINEAR)
    solid = np.asarray(small) > 90
    ys, xs = np.nonzero(solid)
    if len(xs) == 0:
        return {"bbox": [0, 0, full_w, full_h], "head": [full_w / 2, full_h / 4, min(full_w, full_h) / 3]}
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    bh = y1 - y0
    # Quita huecos pequeños para que el pelo o las orejas no partan la cabeza.
    solid = ndimage.binary_closing(solid, iterations=2)
    dist = ndimage.distance_transform_edt(solid)
    rows = np.arange(dist.shape[0])[:, None]
    rel = np.broadcast_to(np.clip((rows - y0) / max(bh, 1), 0, 1), dist.shape)
    score = dist * (1.0 - 0.9 * rel)
    score[rel > 0.6] = 0
    cy, cx = np.unravel_index(np.argmax(score), score.shape)
    r = float(dist[cy, cx])
    # La cabeza suele sobresalir un poco del círculo inscrito (pelo, orejas, casco).
    size = r * 2.3
    # Si el círculo toca casi el borde superior, centra un poco más abajo.
    top_gap = cy - r - y0
    if top_gap > r * 0.6:
        cy -= top_gap * 0.35
    return {
        "bbox": [int(x0 / k), int(y0 / k), int(x1 / k), int(y1 / k)],
        "head": [float(cx) / k, float(cy) / k, size / k],
    }


FACE_MODEL = TOOL_DIR / "modelos" / "face_detection_yunet_2023mar.onnx"


def detect_face(cutout: Image.Image) -> list[float] | None:
    """Busca una cara con YuNet (OpenCV). Devuelve [cx, cy, tamaño_cabeza] o None.
    Va muy bien con personajes humanos; con los que no lo son no encuentra nada
    y se usa la silueta."""
    try:
        import cv2
    except ImportError:
        return None
    if not FACE_MODEL.exists():
        return None
    bbox = cutout.getchannel("A").getbbox()
    if not bbox:
        return None
    crop = cutout.crop(bbox)
    k = min(1.0, 1024 / max(crop.size))
    if k < 1:
        crop = crop.resize((max(1, round(crop.width * k)), max(1, round(crop.height * k))), Image.LANCZOS)
    bg = Image.new("RGBA", crop.size, (128, 128, 128, 255))
    bg.alpha_composite(crop)
    arr = cv2.cvtColor(np.asarray(bg.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = arr.shape[:2]
    try:
        det = cv2.FaceDetectorYN.create(str(FACE_MODEL), "", (w, h), 0.8, 0.3, 20)
        _, faces = det.detect(arr)
    except cv2.error:
        return None
    if faces is None or len(faces) == 0:
        return None
    best = max(faces, key=lambda f: f[-1] * f[2] * f[3])
    x, y, fw, fh = (float(v) for v in best[:4])
    cx = bbox[0] + (x + fw / 2) / k
    cy = bbox[1] + (y + fh * 0.42) / k
    return [cx, cy, max(fw, fh) * 1.9 / k]


def analyse(cutout: Image.Image, head_override: list | None = None) -> dict:
    """Caja del personaje + cabeza (marcada a mano > cara detectada > silueta)."""
    info = analyse_silhouette(cutout)
    info["metodo_cabeza"] = "silueta"
    # Altura de los ojos (para el chara_6). Con la silueta el centro calculado
    # suele quedar en la frente, así que los ojos van algo más abajo.
    info["eyes"] = info["head"][1] + info["head"][2] * 0.12
    if head_override:
        info["head"] = [float(v) for v in head_override]
        info["eyes"] = info["head"][1]
        info["metodo_cabeza"] = "manual"
        return info
    face = detect_face(cutout)
    if face:
        info["head"] = face
        info["eyes"] = face[1]
        info["metodo_cabeza"] = "cara detectada"
    return info


def frame_for(kind: str, W: int, H: int, info: dict) -> tuple[float, float, float]:
    """Encuadre automático inicial. Devuelve (zoom, x, y): x,y es dónde cae la
    esquina superior izquierda de la imagen de trabajo dentro del chara."""
    x0, y0, x1, y1 = info["bbox"]
    bw, bh = x1 - x0, y1 - y0
    hx, hy, hs = info["head"]
    m = min(W, H)

    def at(zoom, sx, sy, tx, ty):
        return zoom, tx - sx * zoom, ty - sy * zoom

    if kind == "cara":
        zoom = 0.8 * m / hs
        return at(zoom, hx, hy, W * 0.5, H * 0.53)
    if kind == "cara_stock":
        zoom = 0.9 * m / hs
        return at(zoom, hx, hy, W * 0.5, H * 0.5)
    if kind == "ojos":
        zoom = 1.15 * W / hs
        return at(zoom, hx, info.get("eyes", hy), W * 0.5, H * 0.5)
    if kind == "casilla":
        zoom = 0.85 * H / hs
        return at(zoom, hx, hy, W * 0.5, H * 0.5)
    if kind == "cuerpo_abajo_derecha":
        zoom = 1.2 * H / bh
        zoom = min(zoom, 1.25 * W / bw)
        z, x, y = at(zoom, x0 + bw / 2, y0, W * 0.6, H * 0.04)
        return z, x, y
    if kind == "cuerpo_abajo_izquierda":
        zoom = min(0.96 * H / bh, 0.98 * W / bw)
        z, x, y = at(zoom, x0 + bw / 2, y1, W * 0.44, H)
        x = max(x, -x0 * z)  # que no se salga por la izquierda
        return z, x, y
    # cuerpo_centro y cualquier otro
    zoom = min(0.9 * W / bw, 0.9 * H / bh)
    return at(zoom, x0 + bw / 2, y0 + bh / 2, W * 0.5, H * 0.5)


_transform_cache: dict = {}


def transformed(img: Image.Image, flip: bool, rot: float) -> Image.Image:
    if not flip and not rot:
        return img
    key = (id(img), flip, round(float(rot), 2))
    if key in _transform_cache:
        return _transform_cache[key]
    out = img.transpose(Image.FLIP_LEFT_RIGHT) if flip else img
    if rot:
        # Gira alrededor del centro; render() compensa el aumento de tamaño.
        out = out.convert("RGBa").rotate(-float(rot), resample=Image.BICUBIC, expand=True).convert("RGBA")
    _transform_cache.clear()
    _transform_cache[key] = out
    return out


def place(src: Image.Image, W: int, H: int, zoom: float, x: float, y: float) -> Image.Image:
    """Coloca src escalada por zoom con su esquina en (x, y) en un lienzo W×H.
    Escala con alfa premultiplicado para que no aparezcan bordes sucios."""
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sw, sh = src.size
    if zoom <= 0:
        return canvas
    sx0 = max(0, math.floor(-x / zoom))
    sy0 = max(0, math.floor(-y / zoom))
    sx1 = min(sw, math.ceil((W - x) / zoom))
    sy1 = min(sh, math.ceil((H - y) / zoom))
    if sx1 <= sx0 or sy1 <= sy0:
        return canvas
    # Margen transparente para que la caja subpíxel nunca se salga del recorte.
    margin = int(math.ceil(1 / zoom)) + 2
    crop = src.crop((sx0 - margin, sy0 - margin, sx1 + margin, sy1 + margin))
    dx0, dy0 = x + sx0 * zoom, y + sy0 * zoom
    dx1, dy1 = x + sx1 * zoom, y + sy1 * zoom
    ix0, iy0 = math.floor(dx0), math.floor(dy0)
    ix1, iy1 = math.ceil(dx1), math.ceil(dy1)
    tw, th = max(1, ix1 - ix0), max(1, iy1 - iy0)
    # Ajuste subpíxel: la caja fuente que corresponde exactamente a la destino entera.
    bx = margin + (ix0 - dx0) / zoom
    by = margin + (iy0 - dy0) / zoom
    box = (bx, by, min(crop.width, bx + tw / zoom), min(crop.height, by + th / zoom))
    layer = crop.convert("RGBa").resize((tw, th), Image.LANCZOS, box=box).convert("RGBA")
    big = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    big.paste(layer, (ix0, iy0))
    canvas.alpha_composite(big)
    return canvas


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = (value or "#000000").lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def add_shadow(img: Image.Image, cfg: dict | None) -> Image.Image:
    """Sombra semitransparente detrás del personaje, como en los charas del juego.

    modo 'contorno': halo oscuro alrededor de la silueta (como los iconos de stock).
    modo 'caida': silueta desplazada (dx, dy) y desenfocada.
    Tamaños en % del lado más corto.
    """
    if not cfg or cfg.get("modo", "ninguna") == "ninguna" or float(cfg.get("opacidad", 0)) <= 0:
        return img
    W, H = img.size
    m = min(W, H)
    alpha = img.getchannel("A")
    grosor = float(cfg.get("grosor", 0)) * m / 100
    blur = float(cfg.get("desenfoque", 0)) * m / 100
    dx = round(float(cfg.get("dx", 0)) * m / 100)
    dy = round(float(cfg.get("dy", 0)) * m / 100)

    pad = int(math.ceil(grosor + blur * 3 + abs(dx) + abs(dy))) + 2
    a = Image.new("L", (W + 2 * pad, H + 2 * pad), 0)
    a.paste(alpha, (pad + dx, pad + dy))
    if grosor >= 0.5 and cfg.get("modo") == "contorno":
        r = max(1, int(round(grosor)))
        a = a.filter(ImageFilter.MaxFilter(2 * r + 1))
    if blur > 0.05:
        a = a.filter(ImageFilter.GaussianBlur(blur))
    a = a.crop((pad, pad, pad + W, pad + H))
    op = float(cfg.get("opacidad", 0.5))
    a = a.point(lambda v: int(v * op + 0.5))
    shadow = Image.new("RGBA", (W, H), (*hex_rgb(cfg.get("color", "#000000")), 0))
    shadow.putalpha(a)
    shadow.alpha_composite(img)
    return shadow


# ---------------------------------------------------------------- calibración


CHARA_NAME_RE = re.compile(r"chara_(\d+)_")


def calibrate(paths: list[str | Path]) -> dict:
    """Lee BNTX originales y copia sus medidas/formato a presets.json.
    Acepta archivos o carpetas (se buscan chara_N_*.bntx dentro)."""
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            files += [f for f in p.rglob("chara_*.bntx")]
        elif p.suffix.lower() == ".bntx":
            files.append(p)
    found: dict[str, list[tuple[dict, Path]]] = {}
    errors = []
    for f in files:
        m = CHARA_NAME_RE.search(f.name)
        if not m:
            continue
        try:
            info = bntx_info(f)
        except RuntimeError as e:
            errors.append(f"{f.name}: {e}")
            continue
        found.setdefault(m.group(1), []).append((info, f))

    data = load_presets()
    REFS_DIR.mkdir(exist_ok=True)
    summary = {}
    for chara, items in sorted(found.items(), key=lambda kv: int(kv[0])):
        if chara not in data["charas"]:
            continue
        counts = Counter((i["width"], i["height"], i["format"], i["mipmaps"]) for i, _ in items)
        (w, h, fmt, mips), n = counts.most_common(1)[0]
        c = data["charas"][chara]
        c.update({"width": w, "height": h, "format": fmt, "mipmaps": mips, "verificado": True})
        ref_src = next(f for i, f in items if (i["width"], i["height"], i["format"], i["mipmaps"]) == (w, h, fmt, mips))
        try:
            bntx_to_png(ref_src, REFS_DIR / f"chara_{chara}.png")
            ref = ref_src.name
        except RuntimeError:
            ref = None
        summary[chara] = {"width": w, "height": h, "format": fmt, "mipmaps": mips, "archivos": len(items), "coinciden": n, "referencia": ref}
    save_presets(data)
    return {"calibrados": summary, "archivos_leidos": len(files), "errores": errors}


def reference_path(chara: str) -> Path | None:
    p = REFS_DIR / f"chara_{chara}.png"
    return p if p.exists() else None


# ---------------------------------------------------------------- hoja de revisión


def checker(size: tuple[int, int], cell: int = 8) -> Image.Image:
    w, h = size
    img = Image.new("RGBA", size, (200, 200, 200, 255))
    d = ImageDraw.Draw(img)
    for yy in range(0, h, cell):
        for xx in range((yy // cell) % 2 * cell, w, cell * 2):
            d.rectangle([xx, yy, xx + cell - 1, yy + cell - 1], fill=(235, 235, 235, 255))
    return img


def sheet(project: Project, path: Path) -> None:
    """Hoja con todos los charas renderizados, para revisar de un vistazo."""
    tiles = []
    for c in project.data["charas"]:
        p = preset(c)
        img = project.render(c)
        scale = 256 / max(img.size)
        shown = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.NEAREST if scale >= 2 else Image.LANCZOS)
        tile = checker(shown.size)
        tile.alpha_composite(shown)
        tiles.append((c, p, img.size, tile))
    pad, label_h = 16, 40
    cols = min(4, len(tiles)) or 1
    rows = math.ceil(len(tiles) / cols)
    cw = 256 + pad
    out = Image.new("RGBA", (cols * cw + pad, rows * (256 + label_h + pad) + pad), (24, 24, 30, 255))
    d = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except OSError:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 13)
        except OSError:
            font = ImageFont.load_default()
    for i, (c, p, size, tile) in enumerate(tiles):
        col, row = i % cols, i // cols
        x = pad + col * cw
        y = pad + row * (256 + label_h + pad)
        out.alpha_composite(tile, (x + (256 - tile.width) // 2, y + (256 - tile.height) // 2))
        d.text((x, y + 260), f"chara_{c} · {size[0]}×{size[1]}", fill=(255, 255, 255, 255), font=font)
        d.text((x, y + 278), p["nombre"], fill=(170, 170, 185, 255), font=font)
    out.save(path)


def list_projects() -> list[dict]:
    if not PROJECTS_DIR.exists():
        return []
    items = []
    for d in sorted(PROJECTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        f = d / "proyecto.json"
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            items.append({k: data.get(k) for k in ("id", "fighter", "slot", "creado", "charas")})
    return items
