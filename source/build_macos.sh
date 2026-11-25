#!/bin/bash
# ---------------------------------------------------------------------------
# 反重力补丁 (Open AG Patcher) — macOS 双架构原生构建脚本 (arm64 + x86_64)
#
# 每个目标架构产出三个 .app（位于 dist/<arch>/）及分发包（dist/release/）：
#   1. 反重力补丁.app          — 图形界面版（Tkinter，推荐下载）
#   2. 反重力补丁开关.app      — 终端一键开关（多账号切换用）
#   3. Open AG Patcher.app     — 完整版菜单（IDE / 桌面版 / CLI / VS Code）
#
# 用法：
#   cd source && ./build_macos.sh              # 默认构建本机架构
#   cd source && ./build_macos.sh arm64        # 仅 Apple Silicon
#   cd source && ./build_macos.sh x86_64       # 仅 Intel x86_64（需 Rosetta + universal2/x64 Python）
#   cd source && ./build_macos.sh all          # 同时构建 arm64 + x86_64 及全部 DMG/ZIP
#   PYTHON=/path/to/universal2/python3 ./build_macos.sh all
#   PACK=0 ./build_macos.sh all                # 仅构建 .app，不打包 DMG/ZIP
# ---------------------------------------------------------------------------
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SOURCE_DIR/.." && pwd)"
VERSION="$(sed -n 's/^VERSION *= *"\([^"]*\)".*/\1/p' "$SOURCE_DIR/patcher/constants.py" | head -1)"
VERSION="${VERSION:-1.4.0}"
DIST="$REPO_DIR/dist"
RELEASE_DIR="$DIST/release"
PACK="${PACK:-1}"
TARGET_ARG="${1:-${ARCH:-$(uname -m)}}"

if [ -z "${SSL_CERT_FILE:-}" ] && [ -f /etc/ssl/cert.pem ]; then
  export SSL_CERT_FILE="/etc/ssl/cert.pem"
fi

if [ -z "${PYTHON:-}" ]; then
  if [ -x "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3" ]; then
    PYTHON="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
  elif [ -x "/Library/Frameworks/Python.framework/Versions/Current/bin/python3" ]; then
    PYTHON="/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
  else
    PYTHON="python3"
  fi
fi

# 检查/转换 icon.ico -> icon.icns
ICNS="$SOURCE_DIR/icon.icns"
if [ ! -f "$ICNS" ] || [ "$SOURCE_DIR/icon.ico" -nt "$ICNS" ]; then
  echo "==> icon.ico -> icon.icns"
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

write_usage_doc() {
  local arch="$1" out="$2"
  if [ "$arch" = "x86_64" ]; then
    cat > "$out" <<TXT
反重力补丁 $VERSION · macOS Intel 芯片版 (x86_64)
=================================================

【这是什么】
专门适配 Intel 芯片 Mac（x86_64）的 Antigravity 桌面版地区补丁工具（兼容 macOS 10.15+；M 系列芯片电脑也可通过 Rosetta 运行，但更推荐直接下载 arm64 原生版）。
打开只有一个窗口，两个按钮（开启补丁 / 关闭补丁），无需安装 Python、无需敲命令。


【怎么装】
1. 把「反重力补丁.app」拖到「应用程序 (Applications)」文件夹（放桌面也可以）
2. 第一次打开若提示「无法验证开发者」或「已损坏，无法打开」：
   • 打开「终端」App，粘贴下面命令回车即可（把路径换成实际位置）：

   xattr -dr com.apple.quarantine "/Applications/反重力补丁.app"

   或者：右键「反重力补丁.app」→ 打开（老版 macOS），或 系统设置 → 隐私与安全性 → 仍要打开。


【怎么用】
1. 先彻底退出 Antigravity（Cmd+Q，确保 Dock 图标下方没有小圆点）
2. 双击运行「反重力补丁.app」
3. 看窗口顶部当前状态：
   ● 已打补丁（开启） → 登支持地区账号时可点「关闭补丁」还原原版
   ○ 原版（未打补丁） → 登不支持地区账号时点「开启补丁」
4. 下方显示绿色的「开启成功 / 关闭成功」后，点「打开 Antigravity」即可


【注意】
· 只改本地文件，不碰账号、不联网、不上传任何内容
· 原版文件会永久备份在 language_server.agybak
· 日志文件：~/Library/Logs/反重力补丁.log
TXT
  else
    cat > "$out" <<TXT
反重力补丁 $VERSION · macOS Apple Silicon (arm64)
=================================================

【这是什么】
专为 Apple Silicon（M1 / M2 / M3 / M4 / M5）Mac 打造的 Antigravity 桌面版地区补丁工具（macOS 11.0+）。
打开只有一个窗口，两个按钮（开启补丁 / 关闭补丁），无需安装 Python、无需敲命令。


【怎么装】
1. 把「反重力补丁.app」拖到「应用程序 (Applications)」文件夹（放桌面也可以）
2. 第一次打开若提示「无法验证开发者」或「已损坏，无法打开」：
   • 打开「终端」App，粘贴下面命令回车即可（把路径换成实际位置）：

   xattr -dr com.apple.quarantine "/Applications/反重力补丁.app"

   或者：右键「反重力补丁.app」→ 打开，或 系统设置 → 隐私与安全性 → 仍要打开。


【怎么用】
1. 先彻底退出 Antigravity（Cmd+Q，确保 Dock 图标下方没有小圆点）
2. 双击运行「反重力补丁.app」
3. 看窗口顶部当前状态：
   ● 已打补丁（开启） → 登支持地区账号时可点「关闭补丁」还原原版
   ○ 原版（未打补丁） → 登不支持地区账号时点「开启补丁」
4. 下方显示绿色的「开启成功 / 关闭成功」后，点「打开 Antigravity」即可


【注意】
· 本包为 Apple Silicon (arm64) 原生版；Intel 芯片老 Mac 请下载带 Intel-x86_64 标识的版本
· 只改本地文件，不碰账号、不联网、不上传任何内容
· 原版文件会永久备份在 language_server.agybak
· 日志文件：~/Library/Logs/反重力补丁.log
TXT
  fi
}

build_one() {
  local arch="$1" venv="$2" arch_dist="$3" arch_build="$4" min_os="$5"
  local entry="$6" bin_name="$7" app_dir="$8" bundle_id="$9" display="${10}"
  local log="$arch_build/pyinstaller-$bin_name.log"

  echo "==> [$arch] PyInstaller: $bin_name (onefile)"
  /bin/rm -rf "$arch_dist/$bin_name" "$arch_build/$bin_name"
  /usr/bin/arch -"$arch" "$venv/bin/python" -m PyInstaller \
    --noconfirm --clean --onefile \
    --target-arch "$arch" \
    --name "$bin_name" \
    --icon "$ICNS" \
    --distpath "$arch_dist" \
    --workpath "$arch_build" \
    --specpath "$arch_build" \
    --paths "$SOURCE_DIR" \
    --hidden-import=packaging \
    --hidden-import=packaging.version \
    --hidden-import=packaging.specifiers \
    --hidden-import=packaging.requirements \
    "$SOURCE_DIR/$entry" > "$log" 2>&1 || {
      echo "!! [$arch] 构建 $bin_name 失败，日志：$log"; tail -30 "$log"; exit 1; }

  local bin="$arch_dist/$bin_name"
  [ -f "$bin" ] || { echo "!! 未找到 $bin"; exit 1; }

  local app="$arch_dist/$app_dir"
  echo "==> [$arch] .app: $app_dir"
  /bin/rm -rf "$app"
  mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
  cp "$bin" "$app/Contents/Resources/app.bin"
  cp "$ICNS" "$app/Contents/Resources/app.icns"

  cat > "$app/Contents/Resources/run.command" <<'LAUNCH'
#!/bin/bash
cd "$HOME" || cd /
BIN="$(cd "$(dirname "$0")" && pwd)/app.bin"
"$BIN" "$@"
status=$?
echo
echo "[i] Done (code $status). Press any key to close."
read -n 1 -s 2>/dev/null || true
exit $status
LAUNCH
  chmod +x "$app/Contents/Resources/run.command"

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
    <key>LSMinimumSystemVersion</key><string>$min_os</string>
    <key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
    <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

  /usr/bin/codesign --force --deep --sign - "$bin" >/dev/null 2>&1 || true
  /usr/bin/codesign --force --sign - "$app/Contents/Resources/app.bin" >/dev/null 2>&1 || true
  /usr/bin/codesign --force --deep --sign - "$app" >/dev/null 2>&1 || true
  /usr/bin/xattr -dr com.apple.quarantine "$app" "$bin" 2>/dev/null || true

  echo "    [$arch] $app ($(/usr/bin/lipo -archs "$bin"))"
}

build_gui() {
  local arch="$1" venv="$2" arch_dist="$3" arch_build="$4" min_os="$5"
  local name="AGPatchGUI" app_dir="反重力补丁.app"
  local log="$arch_build/pyinstaller-$name.log"

  echo "==> [$arch] PyInstaller: $name (onedir, windowed)"
  /bin/rm -rf "$arch_dist/$name.app" "$arch_dist/$app_dir" "$arch_build/$name"
  /usr/bin/arch -"$arch" "$venv/bin/python" -m PyInstaller \
    --noconfirm --clean --onedir --windowed \
    --target-arch "$arch" \
    --name "$name" \
    --icon "$ICNS" \
    --osx-bundle-identifier "ru.avencores.agpatchgui" \
    --distpath "$arch_dist" \
    --workpath "$arch_build" \
    --specpath "$arch_build" \
    --paths "$SOURCE_DIR" \
    --hidden-import=packaging \
    --hidden-import=packaging.version \
    "$SOURCE_DIR/gui_main.py" > "$log" 2>&1 || {
      echo "!! [$arch] 构建 $name 失败，日志：$log"; tail -30 "$log"; exit 1; }

  [ -d "$arch_dist/$name.app" ] || { echo "!! 未找到 $arch_dist/$name.app"; exit 1; }
  mv "$arch_dist/$name.app" "$arch_dist/$app_dir"

  local plist="$arch_dist/$app_dir/Contents/Info.plist"
  /usr/libexec/PlistBuddy -c "Set :CFBundleName 反重力补丁" "$plist" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string 反重力补丁" "$plist" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 反重力补丁" "$plist" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$plist" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VERSION" "$plist" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$plist" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $VERSION" "$plist" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string $min_os" "$plist" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Set :LSMinimumSystemVersion $min_os" "$plist" 2>/dev/null || true

  /usr/bin/codesign --force --sign - "$arch_dist/$app_dir/Contents/MacOS/$name" >/dev/null 2>&1 || true
  /usr/bin/codesign --force --deep --sign - "$arch_dist/$app_dir" >/dev/null 2>&1 || true
  /usr/bin/xattr -dr com.apple.quarantine "$arch_dist/$app_dir" 2>/dev/null || true

  /usr/bin/codesign --verify --deep --strict "$arch_dist/$app_dir"
  echo "    [$arch] $arch_dist/$app_dir ($(/usr/bin/lipo -archs "$arch_dist/$app_dir/Contents/MacOS/$name")) [codesign OK]"
}

pack_arch() {
  local arch="$1" arch_dist="$2"
  local arch_label vol_name gui_zip gui_dmg toggle_zip full_zip
  if [ "$arch" = "x86_64" ]; then
    arch_label="Intel-x86_64"
    vol_name="反重力补丁-$VERSION-Intel"
  else
    arch_label="arm64"
    vol_name="反重力补丁-$VERSION"
  fi

  mkdir -p "$RELEASE_DIR"
  local stage_zip stage_dmg
  stage_zip="$(mktemp -d)"
  stage_dmg="$(mktemp -d)"

  local gui_folder="$stage_zip/反重力补丁-$VERSION-macOS"
  [ "$arch" = "x86_64" ] && gui_folder="$stage_zip/反重力补丁-$VERSION-macOS-Intel"
  mkdir -p "$gui_folder"
  /usr/bin/ditto "$arch_dist/反重力补丁.app" "$gui_folder/反重力补丁.app"
  write_usage_doc "$arch" "$gui_folder/使用说明.txt"
  /usr/bin/xattr -dr com.apple.quarantine "$gui_folder" 2>/dev/null || true

  gui_zip="$RELEASE_DIR/AGPatch-$VERSION-macOS-$arch_label.zip"
  /bin/rm -f "$gui_zip"
  /usr/bin/ditto -c -k --norsrc --keepParent "$gui_folder" "$gui_zip"

  mkdir -p "$stage_dmg"
  /usr/bin/ditto "$arch_dist/反重力补丁.app" "$stage_dmg/反重力补丁.app"
  write_usage_doc "$arch" "$stage_dmg/使用说明.txt"
  ln -s /Applications "$stage_dmg/Applications"
  /usr/bin/xattr -dr com.apple.quarantine "$stage_dmg" 2>/dev/null || true

  gui_dmg="$RELEASE_DIR/AGPatch-$VERSION-macOS-$arch_label.dmg"
  /bin/rm -f "$gui_dmg"
  /usr/bin/hdiutil create -volname "$vol_name" -srcfolder "$stage_dmg" -ov -format UDZO "$gui_dmg" >/dev/null

  toggle_zip="$RELEASE_DIR/AGPatch-Toggle-$VERSION-macOS-$arch_label.zip"
  full_zip="$RELEASE_DIR/OpenAGPatcher-$VERSION-macOS-$arch_label.zip"
  /bin/rm -f "$toggle_zip" "$full_zip"
  /usr/bin/ditto -c -k --norsrc --keepParent "$arch_dist/反重力补丁开关.app" "$toggle_zip"
  /usr/bin/ditto -c -k --norsrc --keepParent "$arch_dist/Open AG Patcher.app" "$full_zip"

  /bin/rm -rf "$stage_zip" "$stage_dmg"
  echo "==> [$arch] Release packages:"
  ls -lh "$gui_dmg" "$gui_zip" "$toggle_zip" "$full_zip"
}

build_arch() {
  local arch="$1"
  local min_os="11.0"
  [ "$arch" = "x86_64" ] && min_os="10.15.0"

  echo "============================================================"
  echo "==> Building macOS target arch: $arch (LSMinimumSystemVersion=$min_os)"
  local actual_arch
  actual_arch="$(/usr/bin/arch -"$arch" "$PYTHON" -c 'import platform, tkinter; print(platform.machine())' 2>/dev/null || true)"
  if [ "$actual_arch" != "$arch" ]; then
    echo "!! Python '$PYTHON' cannot run under arch '$arch' (got '$actual_arch')."
    echo "   Install python.org universal2 Python 3.12+ or pass PYTHON=/path/to/python3."
    exit 1
  fi
  echo "    Python: $(/usr/bin/arch -"$arch" "$PYTHON" -V 2>&1) ($actual_arch)"

  local venv="$REPO_DIR/.venv-build-$arch"
  local arch_dist="$DIST/$arch"
  local arch_build="$REPO_DIR/build/$arch"
  mkdir -p "$arch_dist" "$arch_build"
  cd "$REPO_DIR"

  if [ ! -x "$venv/bin/python" ]; then
    /usr/bin/arch -"$arch" "$PYTHON" -m venv "$venv"
  fi
  if ! /usr/bin/arch -"$arch" "$venv/bin/python" -c "import PyInstaller, packaging" 2>/dev/null; then
    /usr/bin/arch -"$arch" "$venv/bin/python" -m pip install --quiet --upgrade pip
    /usr/bin/arch -"$arch" "$venv/bin/python" -m pip install --quiet pyinstaller "packaging"
  fi

  build_one "$arch" "$venv" "$arch_dist" "$arch_build" "$min_os" \
    "main.py" "OpenAGPatcher" "Open AG Patcher.app" "ru.avencores.openagpatcher" "Open AG Patcher"
  build_one "$arch" "$venv" "$arch_dist" "$arch_build" "$min_os" \
    "toggle_main.py" "AGToggle" "反重力补丁开关.app" "ru.avencores.agtoggle" "反重力补丁开关"
  build_gui "$arch" "$venv" "$arch_dist" "$arch_build" "$min_os"

  if [ "$PACK" = "1" ]; then
    pack_arch "$arch" "$arch_dist"
  fi
}

case "$TARGET_ARG" in
  arm64|x86_64)
    build_arch "$TARGET_ARG"
    ;;
  all|both)
    build_arch arm64
    build_arch x86_64
    ;;
  *)
    echo "Usage: $0 [arm64|x86_64|all]"
    exit 1
    ;;
esac

echo
echo "OK! Build complete."
