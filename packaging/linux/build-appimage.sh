#!/usr/bin/env bash
set -euo pipefail

VERSION="$1"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APPDIR="$ROOT/build/AppDir"
OUT="$ROOT/dist/ScriptCompilerBridge-${VERSION}-x86_64.AppImage"
TOOL="$ROOT/build/appimagetool-x86_64.AppImage"

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib"
cp -a "$ROOT/dist/ScriptCompilerBridge" "$APPDIR/usr/lib/scriptcompiler-bridge"
install -m 755 "$ROOT/packaging/linux/AppRun" "$APPDIR/AppRun"
cp "$ROOT/packaging/linux/scriptcompiler-bridge.desktop" "$APPDIR/"
python -c "import sys; from PIL import Image; Image.open(sys.argv[1]).resize((256, 256)).save(sys.argv[2])" \
  "$ROOT/favicon.png" "$APPDIR/scriptcompiler-bridge.png"

if [ ! -x "$TOOL" ]; then
  mkdir -p "$(dirname "$TOOL")"
  curl -fsSL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$TOOL"
fi

ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" "$APPDIR" "$OUT"
echo "Built $OUT"
