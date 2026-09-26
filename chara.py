#!/usr/bin/env python3
"""Generador de charas de Smash Ultimate · línea de comandos.

Pensado para usarlo a mano o desde otro Claude. Todas las órdenes imprimen JSON.

  python chara.py app                                   abre la interfaz en el navegador
  python chara.py crear foto.png --fighter mario --slot 0 [--charas 0,1,2,3,4,5,6,7]
                          [--modelo isnet-general-use] [--fondo auto|si|no] [--nombre x]
  python chara.py ajustar <proyecto> --chara 3 [--zoom 1.1] [--mover 20,-10] [--centro 0.5,0.6]
                          [--flip] [--rot 5] [--auto] [--sombra contorno|caida|ninguna]
                          [--sombra-opacidad 0.5] [--sombra-grosor 2] [--sombra-desenfoque 2]
                          [--sombra-dx 0] [--sombra-dy 0]
  python chara.py mascara <proyecto> [--borrar-rect x,y,w,h ...] [--recuperar-rect x,y,w,h ...]
                          [--borrar-circulo cx,cy,r ...] [--recuperar-circulo cx,cy,r ...]
                          [--rellenar-huecos] [--quitar-islas 0.02] [--crecer -1] [--suavizar 1]
                          [--endurecer 0.5] [--rehacer isnet-anime] [--sin-fondo]
  python chara.py cabeza <proyecto> cx,cy,tamaño | --auto   corrige dónde está la cabeza
  python chara.py exportar <proyecto> [--charas 0,2]    crea BNTX + PNG (y ZIP)
  python chara.py hoja <proyecto>                       PNG con todos los charas para revisar
  python chara.py estado <proyecto>                     ajustes actuales
  python chara.py proyectos                             lista de proyectos
  python chara.py calibrar <bntx o carpeta> [...]       copia medidas/formato de originales
  python chara.py info <archivo.bntx>
  python chara.py a-png <archivo.bntx> <salida.png>
  python chara.py a-bntx <entrada.png> <chara_X_nombre_00.bntx> [--formato BC7RgbaUnorm]
  python chara.py presets                               muestra la configuración de cada chara
"""

import argparse
import json
import sys
from pathlib import Path

from chara_tool import core


def out(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def pair(text, n):
    vals = [float(v) for v in text.split(",")]
    if len(vals) != n:
        raise SystemExit(f"Se esperaban {n} números separados por comas: {text}")
    return vals


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generador de charas de Smash Ultimate", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("app")
    a.add_argument("--puerto", type=int, default=7860)
    a.add_argument("--sin-navegador", action="store_true")

    c = sub.add_parser("crear")
    c.add_argument("imagen")
    c.add_argument("--fighter", required=True)
    c.add_argument("--slot", type=int, default=0)
    c.add_argument("--charas")
    c.add_argument("--modelo", default=core.DEFAULT_MODEL, choices=list(core.BG_MODELS))
    c.add_argument("--fondo", default="auto", choices=["auto", "si", "no"])
    c.add_argument("--nombre")
    c.add_argument("--exportar", action="store_true", help="exporta los BNTX al terminar")

    j = sub.add_parser("ajustar")
    j.add_argument("proyecto")
    j.add_argument("--chara", required=True)
    j.add_argument("--zoom", type=float, help="multiplica el zoom actual (1.1 = 10%% más grande)")
    j.add_argument("--zoom-abs", type=float, help="zoom absoluto (px del chara por px de la imagen)")
    j.add_argument("--mover", help="dx,dy en píxeles del chara")
    j.add_argument("--centro", help="fx,fy: pone el centro de la cabeza estimada en esa fracción del chara")
    j.add_argument("--flip", action="store_true", help="invierte horizontalmente (alterna)")
    j.add_argument("--rot", type=float)
    j.add_argument("--auto", action="store_true", help="vuelve al encuadre automático")
    j.add_argument("--sombra", choices=["contorno", "caida", "ninguna", "defecto"])
    for k in ("opacidad", "grosor", "desenfoque", "dx", "dy"):
        j.add_argument(f"--sombra-{k}", type=float)

    m = sub.add_parser("mascara")
    m.add_argument("proyecto")
    m.add_argument("--borrar-rect", action="append", default=[])
    m.add_argument("--recuperar-rect", action="append", default=[])
    m.add_argument("--borrar-circulo", action="append", default=[])
    m.add_argument("--recuperar-circulo", action="append", default=[])
    m.add_argument("--rellenar-huecos", action="store_true")
    m.add_argument("--quitar-islas", type=float)
    m.add_argument("--crecer", type=int, default=0)
    m.add_argument("--suavizar", type=float, default=0)
    m.add_argument("--endurecer", type=float, default=0)
    m.add_argument("--rehacer", choices=list(core.BG_MODELS), help="vuelve a quitar el fondo con ese modelo")
    m.add_argument("--sin-fondo", action="store_true", help="usa la imagen tal cual (sin quitar fondo)")
    m.add_argument("--mascara-png", help="sustituye la máscara por este PNG (blanco = personaje)")

    e = sub.add_parser("exportar")
    e.add_argument("proyecto")
    e.add_argument("--charas")

    h = sub.add_parser("cabeza", help="marca dónde está la cabeza y reencuadra todo")
    h.add_argument("proyecto")
    h.add_argument("posicion", nargs="?", help="cx,cy,tamaño en píxeles de la imagen de trabajo")
    h.add_argument("--auto", action="store_true", help="vuelve a la detección automática")

    for name in ("hoja", "estado"):
        s = sub.add_parser(name)
        s.add_argument("proyecto")
    sub.add_parser("proyectos")
    sub.add_parser("presets")

    k = sub.add_parser("calibrar")
    k.add_argument("rutas", nargs="+")

    i = sub.add_parser("info")
    i.add_argument("bntx")
    d = sub.add_parser("a-png")
    d.add_argument("bntx")
    d.add_argument("png")
    b = sub.add_parser("a-bntx")
    b.add_argument("png")
    b.add_argument("bntx")
    b.add_argument("--formato", default="BC7RgbaUnorm")
    b.add_argument("--mipmaps", type=int, default=1)

    args = ap.parse_args(argv)

    if args.cmd == "app":
        from chara_tool import server

        server.main(args.puerto, not args.sin_navegador)
        return

    if args.cmd == "crear":
        charas = args.charas.split(",") if args.charas else None
        p = core.Project.create(Path(args.imagen).read_bytes(), args.fighter, args.slot, charas, args.modelo, args.fondo, args.nombre)
        result = {"proyecto": p.id, "carpeta": str(p.dir), "fondo": p.data["fondo"], "charas": p.data["charas"], "hoja": str(p.contact_sheet())}
        if args.exportar:
            result["exportados"] = p.export_all()
            result["zip"] = str(p.zip_output())
        out(result)
        return

    if args.cmd == "ajustar":
        p = core.Project(args.proyecto)
        ch = str(args.chara)
        if args.auto:
            p.auto_frame(ch)
        s = dict(p.settings(ch))
        pr = core.preset(ch)
        W, H = pr["width"], pr["height"]
        if args.zoom_abs or args.zoom:
            new = args.zoom_abs or s["zoom"] * args.zoom
            # Escala alrededor del centro del chara para que no se desplace.
            cx, cy = W / 2, H / 2
            s["x"] = cx - (cx - s["x"]) * new / s["zoom"]
            s["y"] = cy - (cy - s["y"]) * new / s["zoom"]
            s["zoom"] = new
        if args.mover:
            dx, dy = pair(args.mover, 2)
            s["x"] += dx
            s["y"] += dy
        if args.centro:
            fx, fy = pair(args.centro, 2)
            hx, hy, _ = p.analysis()["head"]
            s["x"] = fx * W - hx * s["zoom"]
            s["y"] = fy * H - hy * s["zoom"]
        if args.flip:
            s["flip"] = not s.get("flip", False)
        if args.rot is not None:
            s["rot"] = args.rot
        if args.sombra == "defecto":
            s["sombra"] = None
        elif args.sombra or any(getattr(args, f"sombra_{k}") is not None for k in ("opacidad", "grosor", "desenfoque", "dx", "dy")):
            base = dict(s.get("sombra") or pr["sombra"])
            if args.sombra:
                base["modo"] = args.sombra
            for k in ("opacidad", "grosor", "desenfoque", "dx", "dy"):
                v = getattr(args, f"sombra_{k}")
                if v is not None:
                    base[k] = v
            s["sombra"] = base
        p.update(ch, **s)
        preview = p.dir / f"vista_chara_{ch}.png"
        p.render(ch).save(preview)
        out({"chara": ch, "ajustes": p.settings(ch), "vista": str(preview)})
        return

    if args.cmd == "mascara":
        p = core.Project(args.proyecto)
        if args.rehacer:
            p.compute_mask("si", args.rehacer)
        if args.sin_fondo:
            p.compute_mask("no")
        if args.mascara_png:
            from PIL import Image

            p.set_mask(Image.open(args.mascara_png).convert("L"))
        ops = {
            "erase_rects": [pair(r, 4) for r in args.borrar_rect],
            "restore_rects": [pair(r, 4) for r in args.recuperar_rect],
            "erase_circles": [pair(r, 3) for r in args.borrar_circulo],
            "restore_circles": [pair(r, 3) for r in args.recuperar_circulo],
            "fill_holes": args.rellenar_huecos,
            "remove_islands": args.quitar_islas,
            "grow": args.crecer,
            "feather": args.suavizar,
            "hard": args.endurecer,
        }
        p.set_mask(core.mask_ops(p.mask, ops))
        view = p.dir / "vista_recorte.png"
        cut = p.cutout()
        bg = core.checker(cut.size, 16)
        bg.alpha_composite(cut)
        bg.save(view)
        out({"proyecto": p.id, "tamano": list(cut.size), "vista": str(view), "mascara": str(p.dir / "mascara.png")})
        return

    if args.cmd == "exportar":
        p = core.Project(args.proyecto)
        charas = args.charas.split(",") if args.charas else p.data["charas"]
        res = [p.export(c) for c in charas]
        out({"exportados": res, "zip": str(p.zip_output()), "hoja": str(p.contact_sheet())})
        return

    if args.cmd == "cabeza":
        p = core.Project(args.proyecto)
        if args.auto or not args.posicion:
            p.set_head(None)
        else:
            p.set_head(pair(args.posicion, 3))
        out({"analisis": p.analysis(), "hoja": str(p.contact_sheet())})
        return

    if args.cmd == "hoja":
        out({"hoja": str(core.Project(args.proyecto).contact_sheet())})
        return
    if args.cmd == "estado":
        p = core.Project(args.proyecto)
        out({**p.data, "tamano_imagen": list(p.original.size), "analisis": p.analysis()})
        return
    if args.cmd == "proyectos":
        out(core.list_projects())
        return
    if args.cmd == "presets":
        out(core.load_presets())
        return
    if args.cmd == "calibrar":
        out(core.calibrate(args.rutas))
        return
    if args.cmd == "info":
        out(core.bntx_info(args.bntx))
        return
    if args.cmd == "a-png":
        core.bntx_to_png(args.bntx, args.png)
        out({"png": args.png})
        return
    if args.cmd == "a-bntx":
        from PIL import Image

        out(core.png_to_bntx(Image.open(args.png).convert("RGBA"), Path(args.bntx), args.formato, args.mipmaps))
        return


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
