# macOS Apple Silicon（M 系列芯片）适配说明

这个 fork 把上游的 Open AG Patcher 改造成**能在 Apple Silicon 上直接双击运行的原生程序**，不再需要手动装 Python、建 venv、敲命令。

---

## 1. 成品

| 文件 | 说明 |
|---|---|
| `dist/反重力补丁.app` | ⭐ **图形界面**：两个按钮（开启/关闭），点完直接显示成功/失败，小白可用 |
| `dist/反重力补丁开关.app` | 终端菜单版开关，适合多账号切换 |
| `dist/Open AG Patcher.app` | 完整版（12 项功能：IDE / 2.0 / CLI / VS Code 补丁与还原） |
| `dist/OpenAGPatcher` / `dist/AGToggle` / `dist/AGPatchGUI` | 对应的命令行版，纯 Mach-O **arm64** |
| `source/icon.icns` | 由 `icon.ico` 转换来的 macOS 图标 |
| `source/build_macos.sh` | 一键重建脚本（跑一次产出上面三个 App） |

---

## 1.2 图形界面（推荐）

双击 `反重力补丁.app`，只有一个窗口：

```
┌────────────────────────────────────┐
│            反重力补丁               │
│         Antigravity 桌面版          │
│ ┌────────────────────────────────┐ │
│ │ ● 已打补丁（开启）              │ │
│ └────────────────────────────────┘ │
│                                    │
│         ┌──────────────┐           │
│         │   开启补丁    │           │
│         └──────────────┘           │
│         ┌──────────────┐           │
│         │   关闭补丁    │           │
│         └──────────────┘           │
│                                    │
│           开启成功                  │
│   请重新打开 Antigravity 才会生效    │
│                                    │
│  [打开 Antigravity]      [刷新状态] │
└────────────────────────────────────┘
```

- 点按钮 → 先自动退出 Antigravity → 改文件 → 复核 → 显示结果（绿=成功 / 红=失败 + 原因）
- 成功后左下角「打开 Antigravity」变蓝，一键重新打开
- 状态本来就对时也照样给 `开启成功 / 关闭成功` 并注明「本次未改动文件」
- 日志：`~/Library/Logs/反重力补丁.log`

---

## 1.5 一键开关（终端版，多账号场景）

有**两个账号**（一个地区受支持、一个不受支持）时，别每次翻完整菜单——用 `反重力补丁开关.app`：

```
══════════════════════════════════════════════════
  反重力补丁开关
  目标：…/Antigravity.app/Contents/Resources/bin/language_server
  应用：Antigravity.app
  备份：language_server.agybak (162.6 MB)

  当前状态：● 已打补丁（开启）
  登「支持地区」的账号 → 建议按 2 关闭，还原原版

  [1] 开启补丁  （不支持地区的账号用）
  [2] 关闭补丁  （还原原版，支持地区的账号用）
  [0] 退出
```

它会自动判断当前状态、回车默认选"相反的那一个"，并在写入前帮你退出 Antigravity、写入后问你要不要重新打开。

**典型切换流程**

| 要登的账号 | 操作 |
|---|---|
| 地区**不支持**的那个 | 双击 → `1` 开启补丁 → 打开 Antigravity 登录 |
| 地区**支持**的那个 | 双击 → `2` 关闭补丁（还原原版）→ 打开 Antigravity 登录 |

设计取向：**支持地区的账号尽量用原版**，少一次二进制改动就少一分被风控关注的可能。
补丁只改本地 `language_server` 一个函数的判定，不动账号、不联网。

> 写入时是原子替换（`os.replace`），中途断电最坏也只是回到旧文件；`language_server.agybak` 备份永远保留。

---

## 2. 用法

**方式 A：双击**

1. 先完全退出 Antigravity（`Cmd+Q`，Dock 里不能有小圆点）；
2. 双击 `Open AG Patcher.app` → 会自动弹出一个终端窗口跑菜单；
3. 输入 `1` 打 IDE 补丁、`3` 打 `agy` 补丁、`5`/`7` 回滚；
4. 菜单会问是否需要 `sudo`（因为要写 `/Applications/Antigravity IDE.app`），输入密码即可。

**方式 B：命令行（推荐排查问题时用）**

```bash
sudo "/Users/…/dist/OpenAGPatcher"
# 或者直接指定目标
sudo "/Users/…/dist/OpenAGPatcher" "/Applications/Antigravity IDE.app"
```

---

## 3. 首次打开被 macOS 拦住怎么办

因为这个 App 只有 ad-hoc 签名（不是 Apple 开发者签名的公证版本），Gatekeeper 第一次会提示"无法验证开发者"：

- **右键 → 打开 → 再点"打开"**（推荐，只需一次）；
- 或者命令行解除隔离：
  ```bash
  xattr -dr com.apple.quarantine "/Applications/Open AG Patcher.app"
  ```
- 如果提示"已损坏""无法打开"，说明下载/拷贝过程带了 quarantine 属性，跑上面的 `xattr` 命令即可。

> 打完补丁后，被修改的 Antigravity 也会自动重新做 ad-hoc 签名（`codesign --force --deep --sign -`），这是 macOS 上 Electron 应用被改过还能启动的必要步骤，程序里已内置。

---

## 4. 相比上游改了什么

上游 v1.3.8 的代码本身已含 macOS 分支（`.app` 定位、`codesign` 重签、`chflags` 去不可变位、arm64 字节签名门），但**没有 macOS 的可执行产物**，只能自己开终端跑源码。本 fork 的改动：

### 4.1 代码修的三处

| 文件 | 改动 | 解决什么 |
|---|---|---|
| `source/patcher/cli.py` | 新增 `ask_line()`，菜单/路径提示全部改用它；捕获 `EOFError` / `KeyboardInterrupt` 后干净退出 | 以前 stdin 关闭（双击启动、`Ctrl-D`）会抛 `[!] Unexpected error: EOF when reading a line` |
| `source/patcher/ide/discovery.py` | 便携版搜索跳过 `cwd = /`、`/System`、`/Library`、`/usr` | 从 Finder 启动时 `cwd` 是 `/`，旧逻辑会去 `os.walk("/")` 找 `main.js`，白等很久 |
| `source/patcher/manager/discovery.py` | darwin 候选根目录追加 `~/Desktop`、`~/Downloads`、`~/Documents` | 从 DMG 拖出来的 `Antigravity.app` 常常就躺在桌面，旧逻辑只找 `/Applications`，会显示 "Antigravity 2.0 → Not found" |
| `source/patcher/manager/patcher.py`、`source/patcher/agy/patcher.py` | 重签顺序改为 **先 `resign_macos_binary` 再 `resign_macos_bundle`** | 原来是先签整包再签内部二进制，签完内部二进制会把整包密封（`_CodeSignature/CodeResources`）写坏，`codesign --verify --deep --strict` 报 "a sealed resource is missing or invalid" |
| `source/build_macos.sh` | 新增 | 上游 `build.txt` 只给 `--target-arch universal2`，在 apple-silicon-only 的 Python（python.org 3.13 / Homebrew）上会直接失败 |

### 4.2 打包链

```
icon.ico ──sips──> icon.icns
main.py ──PyInstaller(arm64, onefile)──> dist/OpenAGPatcher
dist/OpenAGPatcher ──组装──> Open AG Patcher.app
    Contents/MacOS/OpenAGPatcher      ← 壳：open -a Terminal run.command
    Contents/Resources/OpenAGPatcher.bin ← 真正的 arm64 二进制
    Contents/Resources/run.command    ← 先 cd $HOME，再跑二进制，结束后等按键
    Contents/Resources/app.icns
    Contents/Info.plist               ← LSMinimumSystemVersion 11.0
```

App 里故意不直接跑二进制，而是转一手 Terminal：这个工具是**交互式菜单**，需要真正的 TTY（`sudo` 密码输入、`getch` 式等待也依赖 TTY）。

---

## 5. 重新打包

```bash
cd source
PYTHON=/usr/local/bin/python3.12 ./build_macos.sh     # 必须是 arm64 的 python
```

脚本会：建 `.venv-build` → 装 `pyinstaller` + `packaging` → 生成/复用 `icon.icns` → 打 arm64 onefile → 组装 `.app` → ad-hoc 签名 → 去 quarantine。

国内网络建议加镜像：

```bash
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
PYTHON=/usr/local/bin/python3.12 ./build_macos.sh
```

---

## 6. 为什么不打 universal2

`--target-arch universal2` 要求 Python 本身是 universal2 版本。python.org 官方 macOS 安装包、Homebrew 的 `python@3.1x` 在现代 arm64 Mac 上都是 **arm64-only**，universal2 会在 "Converting EXE to target arch" 阶段失败。本机就是 M 系列，直接出 arm64 更快更稳；真要 Intel 兼容，得换 universal2 Python 再改 `--target-arch universal2`。

---

## 7. 已知限制

- 启动时的"检查更新"要走 GitHub，国内需代理，失败只会显示一个黄色提示框，不影响使用。
- 打 `/Applications` 下的 App 需要 `sudo`（这是 macOS 权限，不是本程序的限制）；装在 `~/Applications` 则不用。
- 若遇到 `Operation not permitted` 写不进 `.app`：给终端（或本 App 所在的 Terminal）开 **系统设置 → 隐私与安全性 → 完全磁盘访问权限**。
- 上游更新后如需同步：`git pull` 再跑一次 `./build_macos.sh` 即可，`build_macos.sh` 不依赖任何写死的版本号（版本从 `patcher/constants.py` 的 `VERSION` 读）。
