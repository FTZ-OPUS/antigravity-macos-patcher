"""反重力补丁开关 —— 一键 开启 / 关闭（还原）Antigravity 桌面版的 language_server 补丁。

为什么需要它：
  * 补丁本质是改本地二进制，只在"地区不支持"的账号上才需要用；
  * 登支持地区的账号时最好保持原版，避免被风控盯上。

用法：双击「反重力补丁开关.app」→ 按 1 开启 / 2 关闭 / 0 退出。
不传参时自动找桌面版 Antigravity；可用 AG_TARGET 环境变量指定 language_server 路径。
"""

import os
import sys
import time
import subprocess

from patcher.constants import (
    COLOR_BOLD, COLOR_CYAN, COLOR_DIM, COLOR_GREEN, COLOR_RED, COLOR_YELLOW, COLOR_WHITE,
)
from patcher.utils.console import (
    color, setup_console, info, ok, warn, err, hint,
)
from patcher.utils.file import (
    file_hash, file_size, format_bytes,
    resign_macos_binary, resign_macos_bundle, ensure_macos_writable,
)
from patcher.utils.atomic import atomic_replace_posix, apply_patches_to_data
from patcher.manager.discovery import find_manager_binary
from patcher.manager.patcher import MANAGER_GATE, get_status, _make_backup

APP_NAME = "Antigravity"
BAK_EXT = ".agybak"
W = 50


def _rule(ch="─"):
    print(f"  {color(ch * W, COLOR_DIM)}")


def _title(text):
    print()
    _rule("═")
    print(f"  {color(text, COLOR_BOLD, COLOR_CYAN)}")
    _rule("═")


def ask(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def target_path():
    p = os.environ.get("AG_TARGET", "").strip()
    if p:
        return p
    return find_manager_binary()


def app_bundle(path):
    """从 language_server 往上找 .app，没有就返回空串。"""
    p = os.path.abspath(path)
    while p and p != os.path.dirname(p):
        if p.endswith(".app"):
            return p
        p = os.path.dirname(p)
    return ""


def is_running():
    try:
        r = subprocess.run(["/usr/bin/pgrep", "-f", f"{APP_NAME}.app/Contents/MacOS"],
                           capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def quit_app():
    if not is_running():
        return True
    info(f"正在退出 {APP_NAME} …")
    try:
        subprocess.run(["/usr/bin/osascript", "-e", f'tell application "{APP_NAME}" to quit'],
                       capture_output=True, timeout=20)
    except Exception:
        pass
    for _ in range(20):
        if not is_running():
            ok(f"{APP_NAME} 已退出")
            return True
        time.sleep(0.5)
    warn("仍在运行，强制结束")
    try:
        subprocess.run(["/usr/bin/pkill", "-f", f"{APP_NAME}.app/Contents/MacOS"],
                       capture_output=True, timeout=10)
        time.sleep(1.0)
    except Exception:
        pass
    return not is_running()


def reopen_app(bundle):
    if not bundle:
        return
    try:
        subprocess.run(["/usr/bin/open", "-a", bundle], capture_output=True, timeout=20)
        ok(f"已重新打开 {os.path.basename(bundle)}")
    except Exception as e:
        warn(f"自动打开失败，请手动启动：{e}")


def do_patch(path):
    """备份 → 改字节 → 原子替换 → 重签（先二进制再整包）。"""
    state = get_status(path)[0]
    if state == "patched":
        ok("已经是开启状态，无需重复打补丁。")
        return True
    if state != "unpatched":
        err("无法识别该二进制（签名没匹配上，可能是未知版本）。")
        hint("请先用完整的 Open AG Patcher 检查，或更新本项目。")
        return False

    before = file_hash(path)
    _make_backup(path)                      # 自动创建/刷新 .agybak

    with open(path, "rb") as f:
        data = bytearray(f.read())

    try:
        kind, off, gate = MANAGER_GATE.resolve(bytes(data))
    except LookupError as e:
        err(f"找不到补丁位置：{e}")
        return False

    new_data = apply_patches_to_data(data, [(off, gate)])
    ensure_macos_writable(path)
    atomic_replace_posix(path, bytes(new_data))

    resign_macos_binary(path)
    resign_macos_bundle(path)               # 顺序不能反，否则整包密封失效

    after = file_hash(path)
    ok(f"补丁已开启  ({gate.desc} @ 0x{off:x})")
    print(f"      before {before[:8]}…  after {after[:8]}…")
    return True


def do_restore(path):
    """从 .agybak 还原 → 重签。"""
    bak = path + BAK_EXT
    if not os.path.exists(bak):
        err(f"找不到备份 {os.path.basename(bak)}，无法还原。")
        hint("可以用完整版 Open AG Patcher 重新打一次补丁，它会生成新备份。")
        return False

    if get_status(path)[0] == "unpatched":
        ok("当前已经是原版（未打补丁），无需还原。")
        return True

    with open(bak, "rb") as f:
        bak_data = f.read()
    if len(bak_data) < 1024 * 1024:
        err(f"备份看起来不完整（{format_bytes(len(bak_data))}），已中止。")
        return False

    ensure_macos_writable(path)
    atomic_replace_posix(path, bak_data)
    resign_macos_binary(path)
    resign_macos_bundle(path)
    ok("已还原为原版（补丁关闭）")
    return True


def show_status(path):
    state = get_status(path)[0]
    bundle = app_bundle(path)

    _title("反重力补丁开关")
    print(f"  目标：{color(path, COLOR_CYAN)}")
    if bundle:
        print(f"  应用：{color(os.path.basename(bundle), COLOR_CYAN)}")
    print(f"  大小：{color(format_bytes(file_size(path)), COLOR_CYAN)}")
    if os.path.exists(path + BAK_EXT):
        print(f"  备份：{color(os.path.basename(path) + BAK_EXT, COLOR_DIM)}"
              f" ({format_bytes(file_size(path + BAK_EXT))})")
    else:
        print(f"  备份：{color('无（首次开启时会自动创建）', COLOR_DIM)}")

    print()
    if state == "patched":
        print(f"  当前状态：{color('● 已打补丁（开启）', COLOR_GREEN, COLOR_BOLD)}")
        print(f"  {color('登「支持地区」的账号 → 建议按 2 关闭，还原原版', COLOR_YELLOW)}")
        default = "2"
    elif state == "unpatched":
        print(f"  当前状态：{color('○ 原版（未打补丁 / 关闭）', COLOR_WHITE)}")
        print(f"  {color('登「不支持地区」的账号 → 按 1 开启', COLOR_YELLOW)}")
        default = "1"
    else:
        print(f"  当前状态：{color('？ 无法识别', COLOR_RED)}")
        default = "0"

    print()
    _rule()
    print(f"  {color('[1]', COLOR_GREEN, COLOR_BOLD)} 开启补丁  "
          f"{color('（不支持地区的账号用）', COLOR_DIM)}")
    print(f"  {color('[2]', COLOR_YELLOW, COLOR_BOLD)} 关闭补丁  "
          f"{color('（还原原版，支持地区的账号用）', COLOR_DIM)}")
    print(f"  {color('[0]', COLOR_RED, COLOR_BOLD)} 退出")
    _rule()
    return state, bundle, default


def main():
    setup_console()

    path = target_path()
    if not path or not os.path.isfile(path):
        _title("反重力补丁开关")
        err("没有找到 Antigravity 桌面版的 language_server。")
        hint("请确认 Antigravity.app 已安装（/Applications 或桌面），")
        hint("或设置环境变量 AG_TARGET 指向 language_server 文件。")
        print()
        ask("按回车退出…")
        return 1

    state, bundle, default = show_status(path)
    if state == "unknown":
        ask("\n  按回车退出…")
        return 1

    choice = ask(f"\n  选择（直接回车 = {default}）> ") or default

    if choice == "0":
        print("  已取消。")
        return 0

    if choice not in ("1", "2"):
        err("无效选项。")
        ask("按回车退出…")
        return 1

    # 目标状态与当前一致 → 直接返回
    if (choice == "1" and state == "patched") or (choice == "2" and state == "unpatched"):
        print()
        ok("当前状态已经符合要求，无需操作。")
        ask("\n  按回车退出…")
        return 0

    print()
    # 测试模式（AG_TARGET 指定了副本）不要去动用户真正在跑的 Antigravity
    test_mode = bool(os.environ.get("AG_TARGET", "").strip())
    if not test_mode and not quit_app():
        warn("没能自动退出应用，仍可继续（补丁在下次启动时生效）。")

    print()
    changed = do_patch(path) if choice == "1" else do_restore(path)

    print()
    if changed and bundle and not test_mode:
        print(f"  {color('改动已写入，需要重启 Antigravity 才生效。', COLOR_BOLD)}")
        if ask("  现在重新打开 Antigravity？(y/n) > ").lower().startswith("y"):
            reopen_app(bundle)
    print()
    ask("  按回车退出…")
    return 0 if changed else 1


if __name__ == "__main__":
    sys.exit(main())
