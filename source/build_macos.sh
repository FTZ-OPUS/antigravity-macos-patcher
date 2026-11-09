#!/bin/bash
# ---------------------------------------------------------------------------
# Open AG Patcher — нативная сборка под macOS Apple Silicon (arm64).
#
# Собирает ДВА .app:
#   1. dist/Open AG Patcher.app    — полный патчер (меню 1..12, patch/restore)
#   2. dist/反重力补丁开关.app      — переключатель вкл/выкл для одного бинаря
#
# Что делает скрипт:
#   venv -> icon.ico→icon.icns -> PyInstaller onefile arm64 -> .app bundle
#   -> ad-hoc подпись -> снятие quarantine
#
# Использование:
#   cd source && ./build_macos.sh
#   PYTHON=/path/to/arm64/python3 ./build_macos.sh
# ---------------------------------------------------------------------------
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SOURCE_DIR/.." && pwd)"
VERSION="$(sed -n 's/^VERSION *= *"\([^"]*\)".*/\1/p' "$SOURCE_DIR/patcher/constants.py" | head -1)"
VERSION="${VERSION:-1.0.0}"
VENV="$REPO_DIR/.venv-build"
DIST="$REPO_DIR/dist"
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
# 依赖已装好就跳过 pip（国内网络经常卡 SSL 重试，重打包时没必要每次联网）
if ! "$VENV/bin/python" -c "import PyInstaller, packaging" 2>/dev/null; then
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet pyinstaller "packaging"
fi
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

mkdir -p "$DIST" "$REPO_DIR/build"
cd "$REPO_DIR"

# build_one <entry.py> <bin_name> <app_dir_name> <bundle_id> <display_name>
build_one() {
  local entry="$1" bin_name="$2" app_dir="$3" bundle_id="$4" display="$5"
  local log="$REPO_DIR/build/pyinstaller-$bin_name.log"

  echo "==> PyInstaller: $bin_name (arm64, onefile)"
  /bin/rm -rf "$DIST/$bin_name" "$REPO_DIR/build/$bin_name"
  "$VENV/bin/python" -m PyInstaller \
    --noconfirm --clean --onefile \
    --target-arch arm64 \
    --name "$bin_name" \
    --icon "$ICNS" \
    --distpath "$DIST" \
    --workpath "$REPO_DIR/build" \
    --specpath "$REPO_DIR/build" \
    --paths "$SOURCE_DIR" \
    --hidden-import=packaging \
    --hidden-import=packaging.version \
    --hidden-import=packaging.specifiers \
    --hidden-import=packaging.requirements \
    "$SOURCE_DIR/$entry" > "$log" 2>&1 || {
      echo "!! Сборка $bin_name упала, лог: $log"; tail -30 "$log"; exit 1; }

  local bin="$DIST/$bin_name"
  [ -f "$bin" ] || { echo "!! Не найден $bin"; exit 1; }

  local app="$DIST/$app_dir"
  echo "==> .app: $app_dir"
  /bin/rm -rf "$app"
  mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
  cp "$bin" "$app/Contents/Resources/app.bin"
  cp "$ICNS" "$app/Contents/Resources/app.icns"

  # Запускается в Terminal: рабочая папка = home (иначе автопоиск сканирует "/"),
  # PATH берётся из login-shell, окно остаётся открытым до нажатия клавиши.
  cat > "$app/Contents/Resources/run.command" <<'LAUNCH'
#!/bin/bash
cd "$HOME" || cd /
BIN="$(cd "$(dirname "$0")" && pwd)/app.bin"
"$BIN" "$@"
status=$?
echo
echo "[i] Готово (код $status). Нажмите любую клавишу, чтобы закрыть окно."
read -n 1 -s 2>/dev/null || true
exit $status
LAUNCH
  chmod +x "$app/Contents/Resources/run.command"

  # Двойной клик по .app -> меню в отдельном окне Terminal
  # (бинарник интерактивный: ему нужен настоящий TTY для sudo и ожидания клавиш).
  cat > "$app/Contents/MacOS/launcher" <<'STUB'
#!/bin/bash
HERE="$(cd "$(dirname "$0")" && pwd)"
RUN="$HERE/../Resources/run.command"
chmod +x "$RUN" 2>/dev/null
if /usr/bin/open -a Terminal "$RUN" >/dev/null 2>&1; then
    exit 0
fi
exec "$HERE/../Resources/app.bin" "$@"
STUB
  chmod +x "$app/Contents/MacOS/launcher"

  cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>$display</string>
    <key>CFBundleDisplayName</key><string>$display</string>
    <key>CFBundleIdentifier</key><string>$bundle_id</string>
    <key>CFBundleExecutable</key><string>launcher</string>
    <key>CFBundleIconFile</key><string>app.icns</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>$VERSION</string>
    <key>CFBundleVersion</key><string>$VERSION</string>
    <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
    <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

  echo "==> codesign (ad-hoc) + quarantine: $app_dir"
  /usr/bin/codesign --force --deep --sign - "$bin" >/dev/null 2>&1 || true
  /usr/bin/codesign --force --deep --sign - "$app" >/dev/null 2>&1 || true
  /usr/bin/xattr -dr com.apple.quarantine "$app" 2>/dev/null || true
  /usr/bin/xattr -dr com.apple.quarantine "$bin" 2>/dev/null || true

  echo "    $app"
  echo "    $bin"
  /usr/bin/file "$bin" | sed 's/^/    /'
}

build_one "main.py"        "OpenAGPatcher" "Open AG Patcher.app"     "ru.avencores.openagpatcher" "Open AG Patcher"
build_one "toggle_main.py" "AGToggle"      "反重力补丁开关.app"       "ru.avencores.agtoggle"      "反重力补丁开关"

# 图形界面版：PyInstaller 自己产出 .app（--windowed 不弹终端），再改名成中文
# 注意：Tk 在 onefile 模式下常报 "Tcl wasn't installed properly"，图形版必须用 onedir。
build_gui() {
  local name="AGPatchGUI" app_dir="反重力补丁.app"
  local log="$REPO_DIR/build/pyinstaller-$name.log"
  echo "==> PyInstaller: $name (arm64, onedir, windowed)"
  /bin/rm -rf "$DIST/$name.app" "$DIST/$app_dir" "$REPO_DIR/build/$name"
  "$VENV/bin/python" -m PyInstaller \
    --noconfirm --clean --onedir --windowed \
    --target-arch arm64 \
    --name "$name" \
    --icon "$ICNS" \
    --osx-bundle-identifier "ru.avencores.agpatchgui" \
    --distpath "$DIST" \
    --workpath "$REPO_DIR/build" \
    --specpath "$REPO_DIR/build" \
    --paths "$SOURCE_DIR" \
    --hidden-import=packaging \
    --hidden-import=packaging.version \
    "$SOURCE_DIR/gui_main.py" > "$log" 2>&1 || {
      echo "!! Сборка $name упала, лог: $log"; tail -30 "$log"; exit 1; }

  [ -d "$DIST/$name.app" ] || { echo "!! Не найден $DIST/$name.app"; exit 1; }
  mv "$DIST/$name.app" "$DIST/$app_dir"
  /usr/libexec/PlistBuddy -c "Set :CFBundleName 反重力补丁" "$DIST/$app_dir/Contents/Info.plist" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string 反重力补丁" "$DIST/$app_dir/Contents/Info.plist" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 反重力补丁" "$DIST/$app_dir/Contents/Info.plist" 2>/dev/null || true
  /usr/bin/codesign --force --deep --sign - "$DIST/$app_dir" >/dev/null 2>&1 || true
  /usr/bin/xattr -dr com.apple.quarantine "$DIST/$app_dir" 2>/dev/null || true
  echo "    $DIST/$app_dir"
}

build_gui

echo
echo "OK:"
ls -d "$DIST"/*.app
echo
/usr/bin/codesign -dv "$DIST/Open AG Patcher.app" 2>&1 | /usr/bin/grep -i "Signature" || true
/usr/bin/codesign --verify --deep --strict "$DIST/反重力补丁.app" && echo "反重力补丁.app 签名校验通过"
