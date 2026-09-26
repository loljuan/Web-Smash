# Chara Maker · Smash Ultimate

Programa para Windows que convierte **un PNG de un personaje** en sus **charas de Smash Ultimate** (`chara_0` … `chara_7`), ya en **BNTX** y listos para el mod:

1. **Quita el fondo** con IA y te deja **corregirlo** con un pincel (borrar / recuperar), rellenar huecos, quitar trozos sueltos, contraer o suavizar el borde, o repetirlo con otro modelo.
2. **Encuadra cada chara uno por uno** con su tamaño y su proporción: arrastras para mover, usas la rueda para acercar, y ves en todo momento el **resultado exacto**.
3. Añade la **sombra semitransparente** alrededor del personaje, como en los charas del juego. Se puede ajustar o quitar en cada chara.
4. **Crea el BNTX** de cada chara con su nombre interno correcto (`chara_3_mario_00`). Puedes descargarlos uno a uno o todos en un **ZIP** con la estructura `ui/replace/chara/chara_N/…`.

## Cómo abrirlo

1. Descarga el repositorio: **Code → Download ZIP**, y descomprímelo.
2. Doble clic en **`INICIAR.bat`**.
   - La primera vez instala todo lo necesario (unos minutos).
   - No hace falta tener Python: si no lo encuentra, descarga uno propio dentro de la carpeta del programa.
3. Se abre el navegador en `http://127.0.0.1:7860`. Para apagarlo, cierra la ventana negra.

La primera vez que quites un fondo se descarga el modelo de IA (≈170 MB). A partir de ahí funciona sin internet.

## Cómo se usa

**1 · Imagen** → arrastra el PNG, escribe el **nombre interno** del luchador (`mario`, `koopa` para Bowser, `dragon_king`…) y el **slot** (00–07…), elige los charas y pulsa **Crear charas**.

**2 · Recorte** → revisa el recorte.
- **Borrar** (B) y **Recuperar** (R) pintan sobre la máscara. Tienes deshacer (Ctrl+Z).
- La vista **Máscara** marca en rojo lo que se ha quitado.
- **◎ Cabeza** (H): arrastra desde el centro de la cara hasta el borde de la cabeza. Todos los charas de cara se reencuadran solos.

**3 · Charas** → ve chara por chara:
- **Arrastra** para mover y usa la **rueda** para cambiar el tamaño (o las flechas y `+`/`-`).
- Tienes **Voltear**, **Giro**, **Encuadre automático** y **Centrar cabeza**.
- La **Sombra** se ajusta en cada chara: tipo, opacidad, grosor, desenfoque y desplazamiento.
- **Descargar BNTX** para ese chara, o **Descargar todos (ZIP)**.

## Los charas

| Chara | Para qué es | Tamaño | Sombra |
|---|---|---|---|
| `chara_0` | Retrato de récord (cara) | 128×128 · *estimado* | contorno |
| `chara_1` | Retrato de selección (CSS) / pósters del Ring | 512×512 · *estimado* | contorno |
| `chara_2` | Icono de stock | **64×64 · comprobado** | contorno oscuro (como el juego) |
| `chara_3` | Retrato de VS y resultados | 512×512 · *estimado* | contorno |
| `chara_4` | Retrato de combate (cara en rombo) | 128×128 · *estimado* | contorno |
| `chara_5` | Retrato de espíritu (solo `_00`) | 256×256 · *estimado* | contorno |
| `chara_6` | Smash Final (franja de los ojos, 2:1) | 512×256 · *estimado* | ninguna |
| `chara_7` | Casilla de la cuadrícula de selección (solo `_00`) | 256×152 · *estimado* | contorno |

Formato de todos: **BC7 Unorm sin mipmaps**, el que usa la comunidad para los chara (ultimate_tex).

### ⚠ Calibra con tus archivos (recomendado)

No he podido comprobar las medidas originales de todos los charas. Por eso el programa trae **Ajustes → Calibrar**:
1. Elige BNTX originales del juego o de cualquier mod (`chara_3_mario_00.bntx`…), o escribe la ruta de una carpeta, por ejemplo `…\ui\replace\chara`.
2. El programa copia sus **medidas, formato y mipmaps exactos** y los marca como *verificado*.
3. Además guarda una **imagen de referencia**. En la pantalla de charas, activa **"Referencia original"** para superponerla y clavar la misma proporción.

También puedes cambiar las medidas a mano en la tabla de **Ajustes**.

## Para usarlo desde la línea de comandos (o que lo use otro Claude)

```bat
chara.bat crear foto.png --fighter mario --slot 0 --exportar
chara.bat ajustar mario-c00 --chara 3 --zoom 1.1 --mover 20,-10
chara.bat mascara mario-c00 --borrar-rect 0,0,120,80 --rellenar-huecos
chara.bat exportar mario-c00
chara.bat calibrar "C:\ruta\a\ui\replace\chara"
```

La guía completa para otro Claude está en **`CLAUDE.md`**.

## Carpetas

| Qué | Dónde |
|---|---|
| Tus proyectos y los BNTX creados | `proyectos/<proyecto>/salida/` |
| Configuración de cada chara | `chara_tool/presets.json` |
| Conversor PNG ↔ BNTX | `bin/charatex.exe` (código en `tools/charatex`) |
| Detector de caras (para encuadrar) | `chara_tool/modelos/` (YuNet, licencia MIT) |

Créditos: conversión BNTX con las librerías [`bntx`](https://github.com/ScanMountGoat/bntx) e [`image_dds`](https://github.com/ScanMountGoat/image_dds) de ScanMountGoat. Recorte con [`rembg`](https://github.com/danielgatis/rembg). Detección de caras con [YuNet (OpenCV Zoo)](https://github.com/opencv/opencv_zoo).
