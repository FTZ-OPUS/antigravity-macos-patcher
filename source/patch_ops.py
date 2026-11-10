"""补丁的核心操作（GUI 与命令行共用）。只返回结果，不打印界面文字。

支持 macOS（Apple Silicon / Intel）与 Windows：
  * macOS  —— 原子替换 + 修改后 ad-hoc 重签（不给签名 M 芯片会 SIGKILL）
  * Windows —— 直接写文件（无需签名），需要时提示以管理员身份运行
"""

import os
import sys
import time
import subprocess

from patcher.manager.discovery import find_manager_binary
from patcher.manager.patcher import MANAGER_GATE, get_status, _make_backup
from patcher.utils.atomic import atomic_replace_posix, apply_patches_to_data
from patcher.utils.file import (
    file_size, format_bytes,
    resign_macos_binary, resign_macos_bundle, ensure_macos_writable,
)

APP_NAME = "Antigravity"
BAK_EXT = ".agybak"
IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"


def find_target(explicit=""):
    """显式参数 > AG_TARGET 环境变量 > 自动搜索（测试时指副本，绝不会误动真身）。"""
    if explicit and explicit.strip():
        return explicit.strip()
    env = os.environ.get("AG_TARGET", "").strip()
    if env:
        return env
    return find_manager_binary()


def state_of(path):
    """'patched' | 'unpatched' | 'unknown'"""
    try:
        return get_status(path)[0]
    except Exception:
        return "unknown"


def app_bundle(path):
    """macOS：从 language_server 往上找 .app；Windows 返回空串。"""
    if not IS_MAC:
        return ""
    p = os.path.abspath(path)
    while p and p != os.path.dirname(p):
        if p.endswith(".app"):
            return p
        p = os.path.dirname(p)
    return ""


def app_exe(path):
    """Windows：找到主程序 Antigravity.exe，用于「重新打开」。"""
    if not IS_WIN:
        return ""
    p = os.path.dirname(os.path.abspath(path))
    for _ in range(6):
        cand = os.path.join(p, "Antigravity.exe")
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    base = os.environ.get("LOCALAPPDATA", "")
    if base:
        cand = os.path.join(base, "Programs", "Antigravity", "Antigravity.exe")
        if os.path.isfile(cand):
            return cand
    return ""


def backup_path(path):
    return path + BAK_EXT


def has_backup(path):
    bak = backup_path(path)
    return os.path.exists(bak) and file_size(bak) > 1024 * 1024


# --------------------------------------------------------------- 进程 ----------
def is_running():
    try:
        if IS_WIN:
            r = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Antigravity.exe"],
                capture_output=True, text=True, timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return "antigravity.exe" in (r.stdout or "").lower()
        r = subprocess.run(["/usr/bin/pgrep", "-f", f"{APP_NAME}.app/Contents/MacOS"],
                           capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def quit_app(wait=20):
    """尝试优雅退出，超时再强杀。返回是否已退出。"""
    if not is_running():
        return True

    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/IM", "Antigravity.exe"],
                           capture_output=True, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            subprocess.run(["/usr/bin/osascript", "-e", f'tell application "{APP_NAME}" to quit'],
                           capture_output=True, timeout=20)
    except Exception:
        pass

    for _ in range(wait):
        if not is_running():
            return True
        time.sleep(0.5)

    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/F", "/IM", "Antigravity.exe"],
                           capture_output=True, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            subprocess.run(["/usr/bin/pkill", "-f", f"{APP_NAME}.app/Contents/MacOS"],
                           capture_output=True, timeout=10)
        time.sleep(1.0)
    except Exception:
        pass
    return not is_running()


def reopen_app(bundle_or_exe):
    """macOS 传 .app 路径，Windows 传 exe 路径。"""
    target = bundle_or_exe
    if not target:
        return False, "找不到 Antigravity 主程序"
    try:
        if IS_WIN:
            os.startfile(target)  # noqa: 仅 Windows 存在
            return True, "已重新打开"
        r = subprocess.run(["/usr/bin/open", "-a", target], capture_output=True, timeout=20)
        if r.returncode == 0:
            return True, "已重新打开"
        return False, (r.stderr or b"").decode(errors="replace").strip() or "open 失败"
    except Exception as e:
        return False, str(e)


# --------------------------------------------------------------- 写盘 ----------
def _write_bytes(path, data):
    """macOS 走原子替换 + 重签；Windows 直接写。"""
    if IS_WIN:
        with open(path, "r+b") as f:
            f.seek(0)
            f.write(data)
            f.truncate()
            f.flush()
            os.fsync(f.fileno())
        return
    ensure_macos_writable(path)
    atomic_replace_posix(path, data)
    resign_macos_binary(path)
    resign_macos_bundle(path)


def apply_patch(path):
    """改字节 + 写盘（macOS 额外重签）。返回 (ok, detail)。"""
    st = state_of(path)
    if st == "patched":
        return True, "已经是开启状态"
    if st != "unpatched":
        return False, "无法识别的二进制（签名没匹配上，可能是未知版本）"

    try:
        _make_backup(path)
        with open(path, "rb") as f:
            data = bytearray(f.read())
        kind, off, gate = MANAGER_GATE.resolve(bytes(data))
        new_data = apply_patches_to_data(data, [(off, gate)])
        _write_bytes(path, bytes(new_data))
        return True, f"{gate.desc} @ 0x{off:x}"
    except LookupError as e:
        return False, f"找不到补丁位置：{e}"
    except PermissionError:
        return False, "没有写入权限：请右键以管理员身份运行本程序"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def revert_patch(path):
    """从 .agybak 还原（macOS 额外重签）。返回 (ok, detail)。"""
    bak = backup_path(path)
    if not os.path.exists(bak):
        return False, f"缺少备份 {os.path.basename(bak)}"
    if not has_backup(path):
        return False, "备份文件不完整，已中止"

    st = state_of(path)
    if st == "unpatched":
        return True, "已经是原版"

    try:
        with open(bak, "rb") as f:
            bak_data = f.read()
        _write_bytes(path, bak_data)
        return True, "已还原为原版"
    except PermissionError:
        return False, "没有写入权限：请右键以管理员身份运行本程序"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# --------------------------------------------------------------- 复核 ----------
def verify(path, expect, bundle=""):
    """独立复核，返回 [(项目, 详情, 是否通过)]。"""
    rows = []

    st = state_of(path)
    label = {"patched": "已打补丁（开启）", "unpatched": "原版（未打补丁）"}.get(st, "无法识别")
    rows.append(("补丁状态", label, st == expect))

    if IS_MAC:
        ok_bin, _ = _codesign(path, deep=False)
        rows.append(("二进制签名", "有效" if ok_bin else "无效", ok_bin))
        if bundle:
            ok_app, _ = _codesign(bundle, deep=True)
            rows.append(("应用签名密封", "有效" if ok_app else "损坏", ok_app))
    else:
        rows.append(("文件大小", format_bytes(file_size(path)), file_size(path) > 1024 * 1024))

    rows.append(("原版备份", format_bytes(file_size(backup_path(path))) if has_backup(path) else "缺失",
                 has_backup(path)))
    return rows


def _codesign(p, deep=False):
    if not IS_MAC:
        return True, ""
    cmd = ["/usr/bin/codesign", "--verify", "--strict"]
    if deep:
        cmd.append("--deep")
    cmd.append(p)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return r.returncode == 0, (r.stderr or "").strip()
    except Exception as e:
        return False, str(e)
