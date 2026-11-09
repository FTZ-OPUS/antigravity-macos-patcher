#!/bin/bash
# ---------------------------------------------------------------------------
# Open AG Patcher — нативная сборка под macOS Apple Silicon (arm64).
#
# Что делает:
#   1. создаёт отдельный venv для сборки (.venv-build) и ставит PyInstaller;
#   2. конвертирует icon.ico -> icon.icns;
#   3. собирает one-file arm64 бинарь (Mach-O arm64, ad-hoc подпись);
#   4. упаковывает его в .app-бандл с иконкой и запуском в Terminal;
#   5. подписывает бандл ad-hoc и снимает quarantine.
#
# Использование:
#   cd source && ./build_macos.sh
#   PYTHON=/path/to/python3 ./build_macos.sh     # свой интерпретатор
#
# Результат:  ../dist/Open AG Patcher.app  и  ../dist/OpenAGPatcher (CLI)
# ---------------------------------------------------------------------------
set -euo pipefail

NAME="OpenAGPatcher"
APP_NAME="Open AG Patcher"

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SOURCE_DIR/.." && pwd)"
VERSION="$(sed -n 's/^VERSION *= *"\([^"]*\)".*/\1/p' "$SOURCE_DIR/patcher/constants.py" | head -1)"
VERSION="${VERSION:-1.0.0}"
VENV="$REPO_DIR/.venv-build"
DIST="$REPO_DIR/dist"
APP="$DIST/$APP_NAME.app"
PYTHON="${PYTHON:-python3}"

echo "==> Python: $($PYTHON -V 2>&1)"
ARCH="$($PYTHON -c 'import platform;print(platform.machine())')"
if [ "$ARCH" != "arm64" ]; then
  echo "!!  Этот интерпретатор $ARCH, а нужен arm64 (Apple Silicon)."
  echo "   Укажите PYTHON=/путь/к/arm64/python3 (например, python.org 3.12/3.13 arm64)."
  exit 1
fi

echo "==> venv: $VENV"
if [ ! -x "$VENV/bin/python" ]; then
  "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet pyinstaller "packaging"

echo "==> icon.ico -> icon.icns"
ICNS="$SOURCE_DIR/icon.icns"
if [ ! -f "$ICNS" ] || [ "$SOURCE_DIR/icon.ico" -nt "$ICNS" ]; then
  TMP_ICONSET="$(mktemp -d)/icon.iconset"
  mkdir -p "$TMP_ICONSET"
  PNG="$(mktemp -d)/icon.png"
  sips -s format png "$SOURCE_DIR/icon.ico" --out "$PNG" >/dev/null
  for s in 16 32 128 256 512; do
    sips -z "$s" "$s" "$PNG" --out "$TMP_ICONSET/icon_${s}x${s}.png" >/dev/null
    sips -z "$((s * 2))" "$((s * 2))" "$PNG" --out "$TMP_ICONSET/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$TMP_ICONSET" -o "$ICNS"
fi

echo "==> PyInstaller (arm64, onefile)"
cd "$REPO_DIR"
mkdir -p "$DIST" "$REPO_DIR/build"
rm -rf "$DIST/$NAME" "$REPO_DIR/build/$NAME"
"$VENV/bin/python" -m PyInstaller \
  --noconfirm --clean --onefile \
  --target-arch arm64 \
  --name "$NAME" \
  --icon "$ICNS" \
  --distpath "$DIST" \
  --workpath "$REPO_DIR/build" \
  --specpath "$REPO_DIR/build" \
  --hidden-import=packaging \
  --hidden-import=packaging.version \
  --hidden-import=packaging.specifiers \
  --hidden-import=packaging.requirements \
  "$SOURCE_DIR/main.py" > "$REPO_DIR/build/pyinstaller.log" 2>&1 || {
    echo "!! Сборка упала, лог: $REPO_DIR/build/pyinstaller.log"; tail -30 "$REPO_DIR/build/pyinstaller.log"; exit 1; }

BIN="$DIST/$NAME"
[ -f "$BIN" ] || { echo "!! Не найден $BIN"; exit 1; }

echo "==> .app bundle"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/Resources/$NAME.bin"
cp "$ICNS" "$APP/Contents/Resources/app.icns"

cat > "$APP/Contents/Resources/run.command" <<'LAUNCH'
#!/bin/bash
# Запускается в Terminal из .app: рабочая папка = home (чтобы автопоиск
# не сканировал "/"), PATH берётся из login-shell.
cd "$HOME" || cd /
BIN="$(cd "$(dirname "$0")" && pwd)/OpenAGPatcher.bin"
"$BIN" "$@"
status=$?
echo
echo "[i] Готово (код $status). Нажмите любую клавишу, чтобы закрыть окно."
read -n 1 -s 2>/dev/null || true
exit $status
LAUNCH
chmod +x "$APP/Contents/Resources/run.command"

cat > "$APP/Contents/MacOS/$NAME" <<'STUB'
#!/bin/bash
# Двойной клик по .app -> показываем меню патчера в отдельном окне Terminal.
# (Сам бинарь интерактивный: ему нужен настоящий TTY для sudo и ожидания клавиш.)
HERE="$(cd "$(dirname "$0")" && pwd)"
RUN="$HERE/../Resources/run.command"
chmod +x "$RUN" 2>/dev/null

if /usr/bin/open -a Terminal "$RUN" >/dev/null 2>&1; then
    exit 0
fi

# Terminal недоступен (крайний случай) — запускаем в текущем терминале.
exec "$HERE/../Resources/$NAME.bin" "$@"
STUB
chmod +x "$APP/Contents/MacOS/$NAME"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>$APP_NAME</string>
    <key>CFBundleDisplayName</key><string>$APP_NAME</string>
    <key>CFBundleIdentifier</key><string>ru.avencores.openagpatcher</string>
    <key>CFBundleExecutable</key><string>$NAME</string>
    <key>CFBundleIconFile</key><string>app.icns</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>$VERSION</string>
    <key>CFBundleVersion</key><string>$VERSION</string>
    <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSAppleEventsUsageDescription</key>
    <string>Открывает Terminal, чтобы показать меню патчера.</string>
</dict>
</plist>
PLIST

echo "==> codesign (ad-hoc) + quarantine"
/usr/bin/codesign --force --deep --sign - "$BIN" >/dev/null 2>&1 || true
/usr/bin/codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
/usr/bin/xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
/usr/bin/xattr -dr com.apple.quarantine "$BIN" 2>/dev/null || true

echo
echo "OK:"
echo "  $APP"
echo "  $BIN"
/usr/bin/file "$BIN"
/usr/bin/codesign -dv "$APP" 2>&1 | /usr/bin/grep -i "Signature" || true
