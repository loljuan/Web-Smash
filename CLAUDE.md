# Chara Maker — guía para Claude

Herramienta local (Windows) que convierte una imagen de un personaje en los charas de Smash
Ultimate (`chara_0` … `chara_7`) en formato BNTX. Tiene interfaz web (`INICIAR.bat`) y una
CLI pensada para ti: **todas las órdenes imprimen JSON** con rutas a los archivos creados y a
imágenes de vista previa que puedes abrir para revisar el resultado.

## Preparación (una vez)

- Si no existe `.venv`, ejecuta `INICIAR.bat` una vez (o pide al usuario que le dé doble clic). Si
  no hay Python en el PC, descarga `uv` en `tools\uv\` y este instala un Python 3.12 propio en
  `tools\python\`, sin tocar el sistema. Con Python ya instalado equivale a:
  `py -3.12 -m venv .venv && .venv\Scripts\python -m pip install -r requirements.txt`
- Usa siempre `chara.bat …` (o `.venv\Scripts\python chara.py …`).
- El conversor BNTX es `bin\charatex.exe`. En Linux o macOS: `bin/charatex-linux` o compílalo con
  `tools/charatex/build.sh`.

## Flujo recomendado

1. **Calibrar primero, si hay archivos originales.** Busca en el PC del usuario BNTX de chara
   reales (carpetas de mods: `…\ui\replace\chara\chara_N\chara_N_<luchador>_<slot>.bntx`) y ejecuta:
   `chara.bat calibrar "<carpeta o archivos>"`
   Copia medidas, formato y mipmaps exactos a `chara_tool/presets.json` y guarda referencias
   visuales en `chara_tool/referencias/`. Sin calibrar, solo `chara_2` (64×64) está verificado;
   el resto de tamaños son estimados.
2. **Crear el proyecto:**
   `chara.bat crear <imagen> --fighter <nombre_interno> --slot <n> [--charas 0,1,2,3,4,5,6,7] [--fondo auto|si|no] [--modelo isnet-general-use|isnet-anime|u2net|birefnet-general]`
   - `--fondo auto`: si la imagen ya es transparente no quita nada; si no, usa IA.
   - Para personajes de anime o ilustración 2D usa `--modelo isnet-anime`.
   - Devuelve `proyecto` (id) y `hoja` (PNG con todos los charas). **Abre la hoja y revísala.**
3. **Revisar el recorte:** `chara.bat mascara <id>` sin opciones genera `vista_recorte.png`.
   Correcciones disponibles, en píxeles de la imagen de trabajo (`chara.bat estado <id>` da
   `tamano_imagen`):
   - `--borrar-rect x,y,w,h` / `--recuperar-rect x,y,w,h` (repetibles)
   - `--borrar-circulo cx,cy,r` / `--recuperar-circulo cx,cy,r`
   - `--rellenar-huecos` · `--quitar-islas 0.02` · `--crecer -1` (contraer) · `--suavizar 1` · `--endurecer 0.5`
   - `--rehacer <modelo>` · `--sin-fondo` · `--mascara-png ruta.png` (blanco = personaje)
4. **Cabeza:** los charas de cara (0, 2, 4, 6, 7) se encuadran con la cabeza detectada
   (`estado` → `analisis.metodo_cabeza`: "cara detectada", "silueta" o "manual"). Si falla (pasa
   con monstruos o personajes no humanos), márcala: `chara.bat cabeza <id> cx,cy,tamaño`
   (tamaño = diámetro de la cabeza en px). Se reencuadran todos los charas.
5. **Ajustar cada chara:**
   `chara.bat ajustar <id> --chara N [--zoom 1.1] [--zoom-abs z] [--mover dx,dy] [--centro fx,fy] [--flip] [--rot grados] [--auto]`
   - `--zoom` multiplica el tamaño, alrededor del centro del chara.
   - `--mover` va en píxeles del chara (x+ derecha, y+ abajo).
   - `--centro 0.5,0.5` pone la cabeza en el centro.
   - Sombra: `--sombra contorno|caida|ninguna|defecto --sombra-opacidad 0.5 --sombra-grosor 2 --sombra-desenfoque 2 --sombra-dx 0 --sombra-dy 0` (tamaños en % del lado corto).
   - Devuelve `vista` (PNG del chara a tamaño real). Ábrelo y repite hasta que quede bien.
6. **Exportar:** `chara.bat exportar <id>` genera
   `proyectos/<id>/salida/ui/replace/chara/chara_N/chara_N_<fighter>_<slot>.bntx`, los PNG en
   `salida/png/` y un ZIP. Comprueba un BNTX con `chara.bat info <archivo>`.

## Qué es cada chara

| N | Uso | Encuadre por defecto |
|---|---|---|
| 0 | Retrato de récord | cara centrada |
| 1 | Panel de selección (CSS) / pósters del Ring | cuerpo grande, abajo a la derecha |
| 2 | Icono de stock (64×64) | cabeza, con contorno oscuro semitransparente |
| 3 | VS / resultados | cuerpo entero, abajo a la izquierda |
| 4 | Retrato de combate (se ve dentro de un rombo) | cara centrada |
| 5 | Espíritu (solo `_00`) | cuerpo entero centrado |
| 6 | Smash Final (ojos, 2:1) | franja de los ojos |
| 7 | Casilla del CSS (solo `_00`) | cabeza y hombros |

Los charas 5 y 7 no tienen alts: siempre se guardan como `_00`.

## Reglas

- El nombre interno (`--fighter`) solo admite `a-z`, `0-9` y `_`. Es el del juego (`koopa` = Bowser,
  `purin` = Jigglypuff…) o el del mod.
- El nombre interno de la textura dentro del BNTX es el nombre del archivo sin extensión (lo hace
  `charatex` solo). No renombres los BNTX después de crearlos.
- Los tamaños deben ser múltiplos de 4 (BC7).
- No borres `proyectos/` sin preguntar al usuario: ahí están sus trabajos.
- Otras utilidades: `chara.bat a-png <bntx> <png>`, `chara.bat a-bntx <png> <chara_X_nombre_00.bntx>`,
  `chara.bat presets`, `chara.bat proyectos`, `chara.bat hoja <id>`.
