#!/usr/bin/env bash
# Compila charatex para Linux y para Windows (desde Linux, con MinGW).
# Requisitos: rustup target add x86_64-pc-windows-gnu ; apt install mingw-w64
set -euo pipefail
cd "$(dirname "$0")"
cargo build --release
cp target/release/charatex ../../bin/charatex-linux

# intel_tex_2 solo trae los kernels BC7 de Windows compilados para MSVC. MinGW puede
# enlazarlos si les damos el nombre que espera y un puente para __chkstk.
ISPC_DIR=$(ls -d ~/.cargo/registry/src/*/intel_tex_2-*/src/ispc | head -1)
LIBS=$(mktemp -d)
cp "$ISPC_DIR/kernelx86_64-pc-windows-msvc.lib" "$LIBS/libkernelx86_64-pc-windows-gnu.a"
cp "$ISPC_DIR/kernel_astcx86_64-pc-windows-msvc.lib" "$LIBS/libkernel_astcx86_64-pc-windows-gnu.a"
cp "$ISPC_DIR/ispc_texcomp_astcx86_64-pc-windows-msvc.lib" "$LIBS/libispc_texcomp_astcx86_64-pc-windows-gnu.a"
printf '    .text\n    .globl __chkstk\n__chkstk:\n    jmp ___chkstk_ms\n' > "$LIBS/chkstk.S"
x86_64-w64-mingw32-gcc -c "$LIBS/chkstk.S" -o "$LIBS/chkstk.o"
x86_64-w64-mingw32-ar rcs "$LIBS/libchkstk.a" "$LIBS/chkstk.o"
RUSTFLAGS="-L $LIBS -l static=chkstk" cargo build --release --target x86_64-pc-windows-gnu
cp target/x86_64-pc-windows-gnu/release/charatex.exe ../../bin/charatex.exe
echo "Listo: bin/charatex.exe y bin/charatex-linux"
