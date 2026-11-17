#!/usr/bin/env bash
# Build Linux packages: PyInstaller bundle -> AppImage + .deb  (output in dist/)
#   PYTHON=.venv/bin/python packaging/build_linux.sh
#   SKIP_APPIMAGE=1   -> only build the .deb (no appimagetool download)
#   SKIP_PYINSTALLER=1 -> reuse an existing dist/raja-capture bundle
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
PY=${PYTHON:-python3}
VERSION=$("$PY" -c "import raja_capture; print(raja_capture.__version__)")
ARCH=x86_64
echo "== Raja Capture $VERSION =="

"$PY" packaging/make_icons.py
[ "${SKIP_PYINSTALLER:-0}" = 1 ] || "$PY" -m PyInstaller --noconfirm --clean --distpath dist --workpath build/pyinstaller packaging/raja-capture.spec
BUNDLE="$ROOT/dist/raja-capture"
ICON_PNG="$ROOT/packaging/build/raja-capture.png"
ICON_SVG="$ROOT/raja_capture/assets/raja-capture.svg"

desktop_file() {  # $1 = Exec value
  cat <<EOF
[Desktop Entry]
Type=Application
Name=Raja Capture
GenericName=Screen Capture
Comment=Tangkap layar, anotasi, rekam layar dan OCR
Exec=$1 %F
Icon=raja-capture
Terminal=false
Categories=Graphics;Utility;
Keywords=screenshot;capture;screen;record;ocr;
MimeType=image/png;image/jpeg;image/bmp;image/webp;
StartupNotify=false
EOF
}

# ---------------------------------------------------------------- AppImage
APPIMAGE_OUT=""
if [ "${SKIP_APPIMAGE:-0}" != 1 ]; then
APPDIR="$ROOT/build/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp -a "$BUNDLE" "$APPDIR/usr/lib/raja-capture"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/raja-capture/raja-capture" "$@"
EOF
chmod +x "$APPDIR/AppRun"
desktop_file raja-capture > "$APPDIR/raja-capture.desktop"
cp "$ICON_PNG" "$APPDIR/raja-capture.png"
cp "$ICON_PNG" "$APPDIR/.DirIcon"
cp "$ICON_SVG" "$APPDIR/usr/share/icons/hicolor/scalable/apps/raja-capture.svg"

TOOL="$ROOT/build/tools/appimagetool-$ARCH.AppImage"
if [ ! -x "$TOOL" ]; then
  mkdir -p "$(dirname "$TOOL")"
  echo "Downloading appimagetool…"
  curl -fsSL -o "$TOOL" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
  chmod +x "$TOOL"
fi
APPIMAGE_OUT="$ROOT/dist/RajaCapture-$VERSION-$ARCH.AppImage"
ARCH=$ARCH "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$APPIMAGE_OUT"
fi

# ---------------------------------------------------------------- .deb
DEB="$ROOT/build/deb"
rm -rf "$DEB"
mkdir -p "$DEB/DEBIAN" "$DEB/opt" "$DEB/usr/bin" "$DEB/usr/share/applications" \
         "$DEB/usr/share/icons/hicolor/scalable/apps"
cp -a "$BUNDLE" "$DEB/opt/raja-capture"
ln -s /opt/raja-capture/raja-capture "$DEB/usr/bin/raja-capture"
desktop_file /opt/raja-capture/raja-capture > "$DEB/usr/share/applications/raja-capture.desktop"
cp "$ICON_SVG" "$DEB/usr/share/icons/hicolor/scalable/apps/raja-capture.svg"
SIZE=$(du -sk "$DEB" | cut -f1)
cat > "$DEB/DEBIAN/control" <<EOF
Package: raja-capture
Version: $VERSION
Section: graphics
Priority: optional
Architecture: amd64
Installed-Size: $SIZE
Depends: libc6, libegl1, libgl1, libxkbcommon0, libfontconfig1, libdbus-1-3, libxcb-cursor0
Recommends: xdg-desktop-portal, gstreamer1.0-tools, gstreamer1.0-pipewire, gstreamer1.0-plugins-good, gstreamer1.0-plugins-bad, gstreamer1.0-plugins-ugly, gstreamer1.0-pulseaudio, ffmpeg, tesseract-ocr, xdg-utils
Suggests: tesseract-ocr-ind
Maintainer: Raja Capture <noreply@users.noreply.github.com>
Homepage: https://github.com/firexsantos/raja-capture
Description: Screen capture, annotation, screen recording and OCR
 Raja Capture captures full screen, windows, regions and scrolling pages,
 annotates them (arrows, text, highlight, blur, step numbers), records the
 screen to MP4 with audio, picks colors, measures with a ruler and extracts
 text with OCR. Works on Wayland (xdg-desktop-portal) and X11.
EOF
DEB_OUT="$ROOT/dist/raja-capture_${VERSION}_amd64.deb"
chmod -R u+rwX,go+rX,go-w "$DEB"
dpkg-deb --build --root-owner-group "$DEB" "$DEB_OUT"

echo
echo "Selesai:"
ls -lh $APPIMAGE_OUT "$DEB_OUT"
