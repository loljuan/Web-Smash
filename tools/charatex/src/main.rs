//! charatex: conversor PNG <-> BNTX para los chara de Smash Ultimate.
//!
//! charatex encode <entrada.png> <salida.bntx> [--format BC7RgbaUnorm] [--mipmaps 1] [--quality slow]
//! charatex decode <entrada.bntx> <salida.png>
//! charatex info   <archivo.bntx>            (imprime JSON)
//!
//! El nombre interno de la textura es el nombre del archivo sin extensión
//! (por ejemplo chara_3_mario_00), igual que en los archivos del juego.

use std::{path::Path, str::FromStr};

use anyhow::{anyhow, bail, Context, Result};
use bntx::Bntx;
use image_dds::{ImageFormat, Mipmaps, Quality};

fn arg_value(args: &[String], name: &str) -> Option<String> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1).cloned())
}

fn texture_name(path: &Path) -> String {
    path.file_stem().unwrap_or_default().to_string_lossy().to_string()
}

fn encode(args: &[String]) -> Result<()> {
    let input = args.first().context("falta el PNG de entrada")?;
    let output = args.get(1).context("falta el BNTX de salida")?;
    let format_name = arg_value(args, "--format").unwrap_or_else(|| "BC7RgbaUnorm".to_string());
    let format = ImageFormat::from_str(&format_name).map_err(|_| anyhow!("formato desconocido: {format_name}"))?;
    let mips: u32 = arg_value(args, "--mipmaps").map(|m| m.parse()).transpose()?.unwrap_or(1);
    let quality = match arg_value(args, "--quality").as_deref() {
        Some("fast") => Quality::Fast,
        Some("normal") => Quality::Normal,
        _ => Quality::Slow,
    };
    let mipmaps = if mips <= 1 { Mipmaps::Disabled } else { Mipmaps::GeneratedExact(mips) };

    let image = image::open(input).with_context(|| format!("no se pudo abrir {input}"))?.to_rgba8();
    let (w, h) = image.dimensions();
    if format_name.starts_with("BC") && (w % 4 != 0 || h % 4 != 0) {
        bail!("para {format_name} el ancho y el alto deben ser múltiplos de 4 (es {w}x{h})");
    }
    let dds = image_dds::dds_from_image(&image, format, quality, mipmaps)?;
    let output_path = Path::new(output);
    let bntx = Bntx::from_dds(&dds, &texture_name(output_path))?;
    bntx.save(output_path)?;
    println!("{{\"ok\":true,\"output\":{:?},\"width\":{w},\"height\":{h},\"format\":{:?},\"mipmaps\":{}}}", output, format_name, bntx.mipmap_count());
    Ok(())
}

fn decode(args: &[String]) -> Result<()> {
    let input = args.first().context("falta el BNTX de entrada")?;
    let output = args.get(1).context("falta el PNG de salida")?;
    let bntx = Bntx::from_file(input).with_context(|| format!("no se pudo leer {input}"))?;
    let dds = bntx.to_dds()?;
    let image = image_dds::image_from_dds(&dds, 0)?;
    image.save(output)?;
    println!("{{\"ok\":true,\"output\":{:?}}}", output);
    Ok(())
}

fn info(args: &[String]) -> Result<()> {
    let input = args.first().context("falta el BNTX")?;
    let bntx = Bntx::from_file(input).with_context(|| format!("no se pudo leer {input}"))?;
    let format = format!("{:?}", bntx.image_format());
    let dds_format = bntx
        .to_dds()
        .ok()
        .and_then(|d| image_dds::dds_image_format(&d).ok())
        .map(|f| format!("{f:?}"))
        .unwrap_or_default();
    let name = Path::new(input).file_stem().unwrap_or_default().to_string_lossy().to_string();
    println!(
        "{{\"file\":{:?},\"name\":{:?},\"width\":{},\"height\":{},\"surface_format\":{:?},\"format\":{:?},\"mipmaps\":{},\"layers\":{}}}",
        input,
        name,
        bntx.width(),
        bntx.height(),
        format,
        dds_format,
        bntx.mipmap_count(),
        bntx.layer_count()
    );
    Ok(())
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let result = match args.first().map(String::as_str) {
        Some("encode") => encode(&args[1..]),
        Some("decode") => decode(&args[1..]),
        Some("info") => info(&args[1..]),
        _ => {
            eprintln!("Uso:\n  charatex encode <entrada.png> <salida.bntx> [--format BC7RgbaUnorm] [--mipmaps 1] [--quality slow|normal|fast]\n  charatex decode <entrada.bntx> <salida.png>\n  charatex info <archivo.bntx>");
            std::process::exit(2);
        }
    };
    if let Err(e) = result {
        println!("{{\"ok\":false,\"error\":{:?}}}", format!("{e:#}"));
        std::process::exit(1);
    }
}
