<div align="center">

**macOS Apple Silicon（arm64）原生版 · 中文文档**

[![Release](https://img.shields.io/github/v/release/FTZ-OPUS/antigravity-macos-patcher?style=for-the-badge)](https://github.com/FTZ-OPUS/antigravity-macos-patcher/releases/latest)
<img src="https://img.shields.io/badge/platform-macOS%20arm64-000000?style=for-the-badge&logo=apple" alt="macOS arm64">
<img src="https://img.shields.io/badge/python-3.9%2B-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54" alt="Python">
<a href="./LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue?style=for-the-badge" alt="GPL-3.0"></a>

</div>

# 🔑 反重力补丁（Open AG Patcher · macOS 增强版）

针对 **Antigravity 2.0 桌面版 / Antigravity IDE / Antigravity CLI（`agy`）/ VS Code 的 Google Antigravity 扩展** 的开源补丁工具：**无需 VPN、无需更换 Google 账号地区** 即可解除地区限制。

本仓库是 [AvenCores/open-antigravity-patcher](https://github.com/AvenCores/open-antigravity-patcher) `v1.3.8` 的**二次开发分支**：把上游文档完整译为中文，并补上 macOS Apple Silicon 的原生支持（双击即用，不需要装 Python、不需要敲命令）。

> 俄文原版文档保留在 [`README.ru.md`](./README.ru.md)，macOS 改造细节见 [`MACOS_APPLE_SILICON_zh.md`](./MACOS_APPLE_SILICON_zh.md)。

---

## 🌟 本分支的二次开发内容

上游只有 Windows / Linux 的成品二进制，macOS 只能自己开终端跑源码。本分支补齐了这些：

| 改动 | 说明 |
|---|---|
| **macOS 原生 App（arm64）** | `反重力补丁.app`：图形界面，两个按钮（开启 / 关闭），点完直接显示「开启成功 / 开启失败 / 关闭成功 / 关闭失败」 |
| **一键补丁开关** | `反重力补丁开关.app`：终端菜单版开关，适合多账号切换（受支持地区用原版、不支持地区用补丁） |
| **完整版 App** | `Open AG Patcher.app`：保留上游全部 12 项功能（IDE / 2.0 / CLI / VS Code 四项补丁 + 四项还原 + 工具） |
| **构建脚本** | `source/build_macos.sh`：一条命令产出上面三个 App（venv → icns → PyInstaller arm64 → .app → ad-hoc 签名 → 去 quarantine） |
| **中文文档** | 本文件 + `MACOS_APPLE_SILICON_zh.md` |

顺手修掉的上游问题：

1. **桌面版找不到**：`Antigravity.app` 从 DMG 拖到桌面/下载/文稿时，上游只扫 `/Applications`，会报「Antigravity 2.0 → 未找到」。现在会扫 `~/Desktop`、`~/Downloads`、`~/Documents`。
2. **整包签名被写坏**：上游先重签 `.app` 再重签内部二进制，后者会让整包密封（`_CodeSignature/CodeResources`）失配，`codesign --verify --deep --strict` 报 `a sealed resource is missing or invalid`。现在改为**先内部二进制、后整包**。
3. **双击启动抛异常**：stdin 关闭时 `input()` 抛 `EOFError`，被顶层捕获成「Unexpected error: EOF when reading a line」。现在按 Ctrl-D 或没有输入时干净退出。
4. **Finder 启动扫全盘**：启动时 `cwd` 是 `/`，便携版搜索会 `os.walk("/")` 白等很久。现在跳过根目录类路径。
5. **构建命令不可用**：上游 `--target-arch universal2` 在 arm64-only 的 Python（python.org / Homebrew）上必然失败，脚本改为直接出 arm64。

---

## 📦 下载与使用

**成品在 [Releases](https://github.com/FTZ-OPUS/antigravity-macos-patcher/releases/latest) 页面**：

| 附件 | 说明 |
|---|---|
| `反重力补丁.app` | ⭐ 推荐：图形界面，两个按钮，最简单 |
| `反重力补丁开关.app` | 终端菜单版开关（多账号切换用） |
| `Open AG Patcher.app` | 完整版（含 IDE / CLI / VS Code 扩展补丁） |

**图形版怎么用（小白向）**

1. 先 `Cmd+Q` 完全退出 Antigravity（Dock 里不能有小圆点）
2. 双击 `反重力补丁.app`
3. 顶部会显示当前状态：`● 已打补丁（开启）` 或 `○ 原版（未打补丁）`
4. 点 **开启补丁**（登不支持地区的账号）或 **关闭补丁**（登支持地区的账号）
5. 下方立刻显示结果：
   - `开启成功` / `关闭成功`（绿色）
   - `开启失败` / `关闭失败`（红色，并说明原因）

> 每次操作都会做**四项独立复核**才敢报成功：补丁状态、二进制签名、应用签名密封、原版备份。

**首次打开被 macOS 拦住**（提示"无法验证开发者"）：**右键 → 打开** 一次即可；或者

```bash
xattr -dr com.apple.quarantine "/Applications/反重力补丁.app"
```

---

## 🎯 支持的目标

| 目标 | 被修改的文件 | 作用 |
|---|---|---|
| **Antigravity IDE** | `…/Antigravity IDE.app/Contents/Resources/app/out/main.js` | 绕过 `isGoogleInternal` 地区判定 |
| **Antigravity 2.0 桌面版** | `…/Antigravity.app/Contents/Resources/bin/language_server` | 强制 `hasValidAuth = true` |
| **Antigravity CLI** | `agy` / `agy.exe` | 去掉「Eligibility Check」屏与 `Account ineligible` |
| **VS Code 扩展** | `google.google-antigravity-*/extension.js` + `~/.gemini/bin/antigravity` | 阻止重新下载覆盖 + 关闭 release 频道变更检查 |

---

## 🚀 完整版菜单

启动 `Open AG Patcher.app`（或命令 `./OpenAGPatcher`）后：

### PATCH（打补丁）

| 选项 | 说明 |
|---|---|
| `1` Antigravity IDE patch | 改 `main.js`，解除地区限制 |
| `2` Antigravity 2.0 patch | 改 `language_server`（桌面版后端） |
| `3` Antigravity CLI (agy) patch | 改 `agy` 二进制，去掉资格检查 |
| `4` Antigravity VS Code Patch | 改扩展 `extension.js` + 下载的二进制 |

### RESTORE（还原）

| 选项 | 说明 |
|---|---|
| `5` Antigravity IDE | 从 `main.js.bak` 还原 |
| `6` Antigravity 2.0 | 从 `language_server.agybak` 还原 |
| `7` Antigravity CLI | 从 `agy.agybak` 还原 |
| `8` Antigravity VS Code 扩展 | 从 `extension.js.vscodebak` 还原 |

### TOOLS（工具）

| 选项 | 说明 |
|---|---|
| `9` 检查更新 | 查 GitHub 最新版本 |
| `10` 打开 GitHub 仓库 | 浏览器打开项目页 |
| `11` 手动选择路径 | 自动搜索失败时手工指定 |
| `12` 关于 | 版本与作者信息 |
| `0` 退出 | — |

### 命令行用法

```bash
# macOS
./OpenAGPatcher                                            # 自动搜索
./OpenAGPatcher "/Applications/Antigravity IDE.app"        # 指定 IDE
./OpenAGPatcher "/Applications/Antigravity.app"            # 指定桌面版
./OpenAGPatcher "/usr/local/bin/agy"                       # 指定 CLI

# 构建后从源码运行
python3 main.py
```

> 如果补丁脚本所在目录里恰好有别的 `main.js`，自动搜索可能挑错文件 —— 用 `11` 或命令行参数显式指定路径。

---

## ⚠️ 常见错误与处理

### HTTP 500 Internal Server Error
说明 Google 服务端拒绝，与本地补丁无关。换账号（最好用官方支持地区的账号或有订阅的账号）。付费工具也解决不了。

### HTTP 403 / `SUBSCRIPTION_REQUIRED` (#3501) / `Agent execution terminated due to error`
不是补丁的问题，也不是「资格检查」页。这是 Google API 对该账号的**许可判定**，补丁只改本地文件，无法给账号发许可证。

处理：① 换到官方支持地区的账号；② 或购买 Google AI Plus / Pro / Ultra 订阅。

### HTTP 400 `User location is not supported for the API use`
Google 判定你的位置不受支持。

1. 先打补丁（`PATCH → 1`），它会在代码层绕过 `isGoogleInternal`
2. 已打补丁还报错 → 换账号或换 VPN
3. 也可以试专门的反限制 DNS（如 Xbox DNS、dns.malw.link、GeoHide）

> 使用 VPN / 代理本身可能被 Google 识别并触发此错误。

### HTTP 429 Too Many Requests / `RESOURCE_EXHAUSTED`
配额用尽。解决办法是**重置 Antigravity 数据目录**（得到干净配置 + 新 token），可选从备份恢复对话。

> 数据目录名：Antigravity 2.0 是 `Antigravity`，IDE 是 `Antigravity IDE`。

**macOS**

```bash
# 1. 完全退出
Cmd+Q（确认 Dock 里没有小圆点）

# 2. 把数据目录移到安全位置
mv ~/Library/Application\ Support/Antigravity ~/Desktop/Antigravity-backup

# 3. 重新打开、登录、发一条测试消息（429 应消失），然后再退出

# 4.（可选）只恢复对话
rm -rf ~/Library/Application\ Support/Antigravity/User/globalStorage
rm -rf ~/Library/Application\ Support/Antigravity/User/workspaceStorage
cp -a ~/Desktop/Antigravity-backup/User/globalStorage ~/Library/Application\ Support/Antigravity/User/
cp -a ~/Desktop/Antigravity-backup/User/workspaceStorage ~/Library/Application\ Support/Antigravity/User/

# 5. 一切正常后删除备份
rm -rf ~/Desktop/Antigravity-backup
```

⚠️ **不要**从备份里把 `settings.json` 拷回去，否则会把旧的问题配置带回来。

**Windows**

```powershell
Move-Item "$env:APPDATA\Antigravity" "$env:USERPROFILE\Desktop\Antigravity-backup"
# 重新打开、登录、测试后退出
Remove-Item -Recurse -Force "$env:APPDATA\Antigravity\User\globalStorage"
Remove-Item -Recurse -Force "$env:APPDATA\Antigravity\User\workspaceStorage"
Copy-Item -Recurse "$env:USERPROFILE\Desktop\Antigravity-backup\User\globalStorage" "$env:APPDATA\Antigravity\User\"
Copy-Item -Recurse "$env:USERPROFILE\Desktop\Antigravity-backup\User\workspaceStorage" "$env:APPDATA\Antigravity\User\"
```

**Linux**

```bash
pkill -f -i antigravity; sleep 2; pgrep -a -i antigravity || echo "closed"
mv ~/.config/Antigravity ~/Antigravity-backup
# 重新打开、登录、测试后退出
rm -rf ~/.config/Antigravity/User/globalStorage
rm -rf ~/.config/Antigravity/User/workspaceStorage
cp -a ~/Antigravity-backup/User/globalStorage ~/.config/Antigravity/User/
cp -a ~/Antigravity-backup/User/workspaceStorage ~/.config/Antigravity/User/
```

> **原理**：数据目录被移走后，Antigravity 会从零创建配置 —— 新 token、干净配额，旧的配额绑定被重置。
> 补丁改的是安装目录里的 `main.js` / 二进制，**不在这两个目录里**，所以移动数据目录不会影响补丁，不需要重新打。

### Antigravity CLI 报「You do not have a valid license of this product (#3501)」
同样是 Google 服务端的许可判定，补丁无能为力 —— 换地区账号或买订阅。

### 补丁报 `✗ isGoogleInternal -> true (auth) — pattern not found`
99% 的情况是**补丁工具找错了 `main.js`**（找到了别的 Electron 应用的 `main.js`）。

1. 看菜单顶部打印的目标路径，应该是：
   - Windows：`%LOCALAPPDATA%\Programs\Antigravity IDE\resources\app\out\main.js`
   - Linux：`/usr/share/antigravity-ide/resources/app/out/main.js`
   - macOS：`/Applications/Antigravity IDE.app/Contents/Resources/app/out/main.js`
2. 路径不对就用 **TOOLS → `11`** 手动指定
3. 也确认补丁程序所在目录里没有多余的 `main.js`

---

## 🔍 文件查找逻辑

### `main.js`（Antigravity IDE）

1. 命令行参数（目录或 `main.js` 本身）
2. 当前目录 `./main.js`
3. 标准路径：
   - Windows：`%LOCALAPPDATA%\Programs\Antigravity IDE`
   - Linux：`/usr/share/antigravity-ide`、`/opt/Antigravity IDE`、`/opt/Antigravity IDE/resources/app/out`
   - macOS：`/Applications/Antigravity IDE.app/Contents/Resources/app`、`~/Applications/...`
4. Windows 注册表 `{AA73B3E3-C6C8-45C8-B1DC-4AE56C751432}_is1`

目录内依次检查：`resources/app/out/main.js` → `resources/app/main.js` → `out/main.js` → `main.js`。
macOS 也接受直接传 `.app` 路径。

### `agy`（Antigravity CLI）

先看命令行参数 / `11 → 3`，再 `PATH`，最后标准目录：

- Windows：`%LOCALAPPDATA%`、`%PROGRAMFILES%`、`%ProgramData%`、`%APPDATA%`、scoop
- Linux/macOS：`/usr/local/bin`、`/usr/bin`、`/opt/antigravity/bin`、`~/.local/bin`、`~/bin`

多份副本时取 mtime 最新的那份。

### VS Code 扩展

`~/.vscode/extensions` → `~/.vscode-insiders/extensions` → `~/.vscode-oss/extensions` → `~/.vscode-server/extensions`（可用环境变量 `VSCODE_EXTENSIONS` 覆盖），按 `google.google-antigravity-*` 匹配，多版本取最新。

### `~/.gemini/bin`

扩展下载的二进制：Windows 是 `antigravity.exe`/`agy.exe`，POSIX 是 `antigravity`/`agy`。没有的话，说明扩展还没跑过 —— 先在 VS Code 里启动一次扩展让它下载。

---

## 🔎 版本判定

| 平台 | 方式 |
|---|---|
| Windows | 注册表 `DisplayVersion` |
| Linux (deb) | `dpkg-query -W antigravity-ide` |
| Linux (rpm) | `rpm -q --queryformat %{VERSION} antigravity-ide` |
| Linux (portable/snap/flatpak) | `main.js` 同目录的 `package.json` |
| macOS | `Info.plist` 的 `CFBundleShortVersionString`（回退 `package.json`） |

最低版本：Antigravity 2.0 ≥ `2.5.5`、Antigravity IDE ≥ `2.1.1`。检测不到会提示确认后继续。

---

## 🔒 已打补丁检测

打之前会先判断：`if (this.X.isGoogleInternal)` 已被替换为 `if (true)`、且不存在未修改的 `isGoogleInternal`，就认为**已经打过**，询问是否再打一次。

---

## 🛡️ 权限

- **Windows**：自动 UAC 提权（`ShellExecuteW` + `runas`）
- **Linux**：非 root 时建议 `sudo` 重启；拒绝则以当前用户继续（会警告）
- **macOS**：同 POSIX 分支；写 `/Applications` 需要 `sudo`，写 `~/Applications` 不需要

---

## 🍎 macOS 专项说明

### 打完补丁为什么要重签
Electron 应用启用 Hardened Runtime 后，`.app` 内任何文件被改动都会破坏签名，直接启动失败。所以补丁后会自动执行：

```bash
codesign --force --deep --sign - /path/to/Antigravity.app    # ad-hoc 签名
xattr -dr com.apple.quarantine /path/to/Antigravity.app
```

ad-hoc（`--sign -`）足够本机启动，不需要 Apple 开发者证书，也不需要公证。
需要系统里有 `codesign`（Xcode Command Line Tools：`xcode-select --install`）。

> 顺序很重要：必须**先重签内部二进制，再重签整个 `.app`**，否则整包密封会失配。

### `Operation not permitted`
写 `.app` 内部被系统拦截时：

1. 给终端（或补丁 App 所在的 Terminal）开「系统设置 → 隐私与安全性 → 完全磁盘访问权限」
2. 或先手工去隔离：`sudo xattr -rd com.apple.quarantine /path/to/X.app`

### Apple Silicon 为什么必须重签
M 系列芯片在 `exec` 时强制校验 Mach-O 签名，签名与内容不符会被内核直接 `SIGKILL`（表现为"点开就消失"，连报错都没有）。

### 打补丁后打不开
1. `which codesign` 确认存在
2. `codesign -dv /path/to/X.app 2>&1 | grep Signature` 应为 `Signature=adhoc`
3. 仍被拦：系统设置 → 隐私与安全性 → 底部「仍要打开」

---

## ⚙️ 环境要求

- **Python** 3.9+（仅源码运行/自建需要）
- **依赖**：`packaging`
- **macOS**：11.0+，Apple Silicon（arm64）；Intel 可自行用 universal2 Python 重打包
- **最低版本**：Antigravity 2.0 `2.5.5`、Antigravity IDE `2.1.1`

---

## 🛠️ 构建

### macOS（本分支新增，一条命令出三个 App）

```bash
cd source
PYTHON=/usr/local/bin/python3.12 ./build_macos.sh
# 依赖已装好时会跳过 pip；国内建议加镜像：
# PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple PYTHON=... ./build_macos.sh
```

产出：

| 文件 | 说明 |
|---|---|
| `dist/反重力补丁.app` | 图形界面（两个按钮） |
| `dist/反重力补丁开关.app` | 终端菜单开关 |
| `dist/Open AG Patcher.app` | 完整版菜单 |
| `dist/OpenAGPatcher`、`dist/AGToggle` | 对应的命令行版（Mach-O arm64） |

### Windows

```bash
pip install -r requirements.txt
pyinstaller --onefile --uac-admin --icon=icon.ico --name="Open_AG_Patcher_Windows" --noupx --clean --version-file=version.txt main.py
```

### Linux

```bash
pyinstaller --onefile --icon=icon.ico --name="Open_AG_Patcher_Linux" \
  --hidden-import=packaging --hidden-import=packaging.version \
  --hidden-import=packaging.specifiers --hidden-import=packaging.requirements main.py
```

---

## 📁 项目结构

```
source/
├── main.py             # 完整版入口（终端菜单）
├── toggle_main.py      # 一键开关入口（终端）
├── gui_main.py         # 图形界面入口（Tkinter，两个按钮）
├── patch_ops.py        # 补丁核心操作（GUI/终端共用，无界面代码）
├── build_macos.sh      # macOS 一键构建（产出 3 个 .app）
├── icon.ico / icon.icns
└── patcher/
    ├── cli.py          # 终端菜单与输入
    ├── constants.py    # 版本、颜色、Windows 注册表 GUID
    ├── ide/            # main.js 查找与补丁
    ├── agy/            # agy 二进制字节签名补丁
    ├── manager/        # language_server（桌面版后端）补丁
    ├── vscode/         # VS Code 扩展补丁
    └── utils/          # 控制台、权限、原子替换、macOS 重签、更新检查
```

---

## 📜 许可证与致谢

本项目遵循 **GPL-3.0**（见 [`LICENSE`](./LICENSE)）。

- 上游：[AvenCores/open-antigravity-patcher](https://github.com/AvenCores/open-antigravity-patcher)（GPL-3.0）
- 上游参考：[QNIX-Dev/eligibility-antigravity-patcher](https://github.com/QNIX-Dev/eligibility-antigravity-patcher)（MIT）
- 本分支：macOS Apple Silicon 适配、图形界面、中文文档（2026-11）

> 本项目只修改本地安装的客户端文件，不涉及任何账号凭据、不上传数据、不与服务器通信（除检查更新）。
> 请自行确认所在地区与服务条款的适用性。
