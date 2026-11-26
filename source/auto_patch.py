"""自动检测 Antigravity 更新并自动重新打补丁。

核心机制：
  1. 监控目标 language_server 的文件指纹（大小 + 修改时间）与补丁状态；
  2. 当 Antigravity 自动更新覆盖了 language_server（变回未打补丁原版）时，
     先等待文件写入稳定，再自动退出 → 打补丁 → 复核 →（如原本在运行则）重新打开；
  3. 对失败/无法识别的新版本记录指纹，避免死循环重试；文件再次变更后自动恢复检测；
  4. 支持注册系统级开机自启后台守护（macOS LaunchAgent / Windows 注册表 Run + 后台进程）。
"""

import json
import os
import plistlib
import signal
import subprocess
import sys
import time

import patch_ops as ops

IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"

LAUNCH_AGENT_LABEL = "ru.avencores.agpatch.autowatch"
WIN_RUN_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
WIN_RUN_VALUE_NAME = "AGPatchAutoWatch"
DEFAULT_INTERVAL = 15


# --------------------------------------------------------------- 路径与配置 ----------
def app_data_dir():
    if IS_MAC:
        base = os.path.expanduser("~/Library/Application Support/AGPatch")
    elif IS_WIN:
        base = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "AGPatch",
        )
    else:
        base = os.path.expanduser("~/.config/agpatch")
    return base


def config_path():
    return os.path.join(app_data_dir(), "auto_patch.json")


def pid_file_path():
    return os.path.join(app_data_dir(), "watcher.pid")


def watcher_log_path():
    if IS_MAC:
        return os.path.expanduser("~/Library/Logs/反重力补丁-自动监控.log")
    return os.path.join(app_data_dir(), "auto_patch.log")


def launch_agent_path():
    return os.path.expanduser(f"~/Library/LaunchAgents/{LAUNCH_AGENT_LABEL}.plist")


def _default_config():
    return {
        "enabled": False,
        "auto_reopen": True,
        "interval": DEFAULT_INTERVAL,
        "target": "",
        "failed_fingerprint": "",
        "last_result": None,
    }


def load_config():
    cfg = _default_config()
    p = config_path()
    try:
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
    except Exception:
        pass
    return cfg


def save_config(cfg):
    p = config_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)
    return cfg


def _log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        lp = watcher_log_path()
        os.makedirs(os.path.dirname(lp), exist_ok=True)
        with open(lp, "a", encoding="utf-8", errors="replace") as f:
            f.write(line + "\n")
    except Exception:
        pass


# --------------------------------------------------------------- 系统通知 ----------
def notify(title, message):
    """发送非阻塞系统通知（尽力而为，失败不影响主流程）。"""
    try:
        if IS_MAC:
            t = title.replace("\\", "\\\\").replace('"', '\\"')
            m = message.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(
                ["/usr/bin/osascript", "-e", f'display notification "{m}" with title "{t}"'],
                capture_output=True,
                timeout=10,
            )
        elif IS_WIN:
            # 仅在 Windows 上轻量气泡提示（不阻塞），若失败静默忽略
            ps_title = title.replace("'", "''")
            ps_msg = message.replace("'", "''")
            script = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "$n = New-Object System.Windows.Forms.NotifyIcon;"
                "$n.Icon = [System.Drawing.SystemIcons]::Information;"
                "$n.BalloonTipTitle = '" + ps_title + "';"
                "$n.BalloonTipText = '" + ps_msg + "';"
                "$n.Visible = $true;"
                "$n.ShowBalloonTip(4000);"
                "Start-Sleep -Seconds 4;"
                "$n.Dispose();"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    except Exception:
        pass


# --------------------------------------------------------------- 文件指纹与防抖 ----------
def file_fingerprint(path):
    """返回基于路径、文件大小与纳秒级修改时间的指纹字符串。"""
    try:
        st = os.stat(path)
        return f"{os.path.abspath(path)}|{st.st_size}|{st.st_mtime_ns}"
    except OSError:
        return ""


def wait_file_stable(path, checks=3, delay=1.0):
    """等待文件大小与 mtime 连续 checks 次保持不变，防止更新写入中途打补丁。"""
    prev = file_fingerprint(path)
    if not prev:
        return False
    for _ in range(checks):
        time.sleep(delay)
        curr = file_fingerprint(path)
        if not curr:
            return False
        if curr != prev:
            prev = curr
            # 文件还在变动，额外再等一轮确认
            time.sleep(delay)
            curr2 = file_fingerprint(path)
            if curr2 != prev:
                return False
    return True


# --------------------------------------------------------------- 核心检测与打补丁 ----------
def check_and_auto_patch(
    target="",
    auto_reopen=True,
    wait_stable=True,
    force=False,
    send_notification=True,
    manage_app_lifecycle=True,
):
    """检测目标二进制并在发现更新（变回原版）时自动打补丁。

    返回 (status, detail):
      - "missing": 未找到 Antigravity
      - "already_patched": 已经是补丁状态，无需处理
      - "skipped_failed": 与上次失败的是同一文件，跳过重试
      - "unstable": 文件正在写入中，本次延后
      - "patched": 检测到更新并自动打补丁成功
      - "failed": 自动打补丁失败（含未知版本/权限不足/复核未通过）
    """
    cfg = load_config()
    effective_target = (target or "").strip() or cfg.get("target", "")
    path = ops.find_target(effective_target)
    if not path or not os.path.isfile(path):
        return "missing", "未找到 Antigravity"

    fp = file_fingerprint(path)
    st = ops.state_of(path)

    if st == "patched":
        if cfg.get("failed_fingerprint"):
            cfg["failed_fingerprint"] = ""
            save_config(cfg)
        return "already_patched", "已打补丁"

    if not force and fp and cfg.get("failed_fingerprint") == fp:
        return "skipped_failed", "同一文件上次自动补丁失败，等待下次更新"

    if st == "unknown":
        detail = "检测到未知版本的 language_server（签名未匹配，请更新补丁工具）"
        _log(f"[warn] {detail}: {path}")
        cfg["failed_fingerprint"] = fp
        cfg["last_result"] = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ok": False,
            "status": "failed",
            "detail": detail,
        }
        save_config(cfg)
        if send_notification:
            notify("反重力补丁", detail)
        return "failed", detail

    # st == "unpatched"：检测到原版（可能是更新后覆盖）
    _log(f"[info] 检测到未打补丁的 language_server，准备自动打补丁: {path}")
    if wait_stable and not wait_file_stable(path):
        _log("[info] 目标文件仍在变动，稍后重试")
        return "unstable", "文件正在更新写入中"

    # 稳定后重新确认状态
    if ops.state_of(path) != "unpatched":
        return "already_patched", "已打补丁"

    bundle = ops.app_bundle(path)
    reopen_target = bundle or ops.app_exe(path)
    was_running = False
    if manage_app_lifecycle:
        was_running = ops.is_running()
        if was_running and not ops.quit_app():
            _log("[warn] Antigravity 未能自动退出，继续尝试打补丁")

    ok, detail = ops.apply_patch(path)
    rows = ops.verify(path, "patched", bundle) if ok else []
    all_ok = ok and all(r[2] for r in rows)

    if all_ok:
        cfg["failed_fingerprint"] = ""
        cfg["last_result"] = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ok": True,
            "status": "patched",
            "detail": detail,
        }
        save_config(cfg)
        _log(f"[ok] 自动打补丁成功: {detail}")

        if manage_app_lifecycle and was_running and auto_reopen and reopen_target:
            re_ok, re_msg = ops.reopen_app(reopen_target)
            _log(f"[info] 重新打开 Antigravity: {re_ok} ({re_msg})")

        if send_notification:
            msg = "检测到 Antigravity 更新，已自动重新打补丁"
            if manage_app_lifecycle and was_running and auto_reopen and reopen_target:
                msg += "并重启应用"
            notify("反重力补丁", msg)
        return "patched", detail

    bad = "、".join(r[0] for r in rows if not r[2]) if rows else ""
    full_detail = f"{detail}（未通过：{bad}）" if bad else (detail or "未知原因")
    cfg["failed_fingerprint"] = fp
    cfg["last_result"] = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ok": False,
        "status": "failed",
        "detail": full_detail,
    }
    save_config(cfg)
    _log(f"[error] 自动打补丁失败: {full_detail}")
    if send_notification:
        notify("反重力补丁", f"自动打补丁失败：{full_detail}")
    return "failed", full_detail


# --------------------------------------------------------------- 进程管理（单实例） ----------
def _is_pid_alive(pid):
    if not pid or pid <= 0:
        return False
    if IS_WIN:
        try:
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return str(pid) in (r.stdout or "")
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _read_watcher_pid():
    p = pid_file_path()
    try:
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                return int(f.read().strip())
    except Exception:
        pass
    return 0


def _write_watcher_pid(pid):
    p = pid_file_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(str(pid))


def _clear_watcher_pid():
    p = pid_file_path()
    try:
        if os.path.isfile(p):
            os.remove(p)
    except OSError:
        pass


def is_watcher_running():
    pid = _read_watcher_pid()
    if pid and pid != os.getpid() and _is_pid_alive(pid):
        return True
    if pid and not _is_pid_alive(pid):
        _clear_watcher_pid()
    return False


def stop_watcher():
    """停止正在运行的后台监控进程。"""
    pid = _read_watcher_pid()
    if not pid or pid == os.getpid():
        _clear_watcher_pid()
        return True
    if not _is_pid_alive(pid):
        _clear_watcher_pid()
        return True
    try:
        if IS_WIN:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                if not _is_pid_alive(pid):
                    break
                time.sleep(0.2)
            if _is_pid_alive(pid):
                os.kill(pid, signal.SIGKILL)
    except Exception:
        pass
    _clear_watcher_pid()
    return not _is_pid_alive(pid)


# --------------------------------------------------------------- 后台守护主循环 ----------
def run_watch_loop(target="", interval=None):
    """后台常驻监控循环：轻量检测文件变化并在更新变回原版时自动补丁。"""
    existing = _read_watcher_pid()
    if existing and existing != os.getpid() and _is_pid_alive(existing):
        _log(f"[info] 后台监控已在运行 (PID={existing})，退出重复实例")
        return 0

    _write_watcher_pid(os.getpid())
    _log(f"[info] 自动补丁后台监控已启动 (PID={os.getpid()})")

    stop_flag = {"stop": False}

    def _on_signal(_sig, _frame):
        stop_flag["stop"] = True

    try:
        signal.signal(signal.SIGTERM, _on_signal)
        signal.signal(signal.SIGINT, _on_signal)
    except Exception:
        pass

    last_checked_fp = ""
    try:
        while not stop_flag["stop"]:
            cfg = load_config()
            if not cfg.get("enabled", False):
                _log("[info] 检测到自动补丁已关闭，后台监控退出")
                break

            eff_target = (target or "").strip() or cfg.get("target", "")
            poll_sec = max(5, int(interval or cfg.get("interval") or DEFAULT_INTERVAL))
            auto_reopen = bool(cfg.get("auto_reopen", True))

            path = ops.find_target(eff_target)
            if path and os.path.isfile(path):
                fp = file_fingerprint(path)
                # 只有首次启动或文件指纹发生变化时才扫描二进制，平时仅 os.stat，零开销
                if fp and fp != last_checked_fp:
                    status, _ = check_and_auto_patch(
                        target=eff_target,
                        auto_reopen=auto_reopen,
                        wait_stable=True,
                        force=False,
                        send_notification=True,
                        manage_app_lifecycle=not bool(eff_target),
                    )
                    if status != "unstable":
                        last_checked_fp = file_fingerprint(path) or fp
            else:
                last_checked_fp = ""

            # 分段睡眠以便快速响应退出信号或配置变更
            for _ in range(poll_sec):
                if stop_flag["stop"]:
                    break
                time.sleep(1)
    finally:
        if _read_watcher_pid() == os.getpid():
            _clear_watcher_pid()
        _log("[info] 自动补丁后台监控已停止")
    return 0


# --------------------------------------------------------------- 开机自启安装/卸载 ----------
def _watch_command(target=""):
    """构造用于开机自启与后台拉起的命令行参数列表。"""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--watch"]
    else:
        gui_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui_main.py")
        py = sys.executable
        if IS_WIN and py.lower().endswith("python.exe"):
            pyw = py[:-10] + "pythonw.exe"
            if os.path.isfile(pyw):
                py = pyw
        cmd = [py, gui_script, "--watch"]
    if target and target.strip():
        cmd.append(target.strip())
    return cmd


def is_autostart_installed():
    if IS_MAC:
        return os.path.isfile(launch_agent_path())
    if IS_WIN:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_REG_PATH, 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, WIN_RUN_VALUE_NAME)
                return bool(val)
        except OSError:
            return False
    return False


def _install_autostart_mac(target=""):
    plist_file = launch_agent_path()
    os.makedirs(os.path.dirname(plist_file), exist_ok=True)
    log_file = watcher_log_path()
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    plist_data = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": _watch_command(target),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "StandardOutPath": log_file,
        "StandardErrorPath": log_file,
    }
    with open(plist_file, "wb") as f:
        plistlib.dump(plist_data, f)

    uid = os.getuid()
    # 先尝试卸载旧任务再加载
    subprocess.run(
        ["/bin/launchctl", "bootout", f"gui/{uid}/{LAUNCH_AGENT_LABEL}"],
        capture_output=True,
        timeout=15,
    )
    r = subprocess.run(
        ["/bin/launchctl", "bootstrap", f"gui/{uid}", plist_file],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if r.returncode != 0:
        # 兼容较老 macOS
        r2 = subprocess.run(
            ["/bin/launchctl", "load", "-w", plist_file],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r2.returncode != 0:
            return False, (r2.stderr or r.stderr or "launchctl 加载失败").strip()
    return True, "已注册 macOS 开机自启后台监控"


def _uninstall_autostart_mac():
    plist_file = launch_agent_path()
    uid = os.getuid()
    subprocess.run(
        ["/bin/launchctl", "bootout", f"gui/{uid}/{LAUNCH_AGENT_LABEL}"],
        capture_output=True,
        timeout=15,
    )
    if os.path.isfile(plist_file):
        subprocess.run(
            ["/bin/launchctl", "unload", "-w", plist_file],
            capture_output=True,
            timeout=15,
        )
        try:
            os.remove(plist_file)
        except OSError:
            pass
    stop_watcher()
    return True, "已关闭 macOS 后台监控"


def _install_autostart_win(target=""):
    import winreg
    cmd = _watch_command(target)
    cmd_str = subprocess.list2cmdline(cmd)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, WIN_RUN_VALUE_NAME, 0, winreg.REG_SZ, cmd_str)
    start_watcher_background(target)
    return True, "已注册 Windows 开机自启后台监控"


def _uninstall_autostart_win():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, WIN_RUN_VALUE_NAME)
    except FileNotFoundError:
        pass
    except OSError:
        pass
    stop_watcher()
    return True, "已关闭 Windows 后台监控"


def start_watcher_background(target=""):
    """在后台启动独立监控进程（若尚未运行）。"""
    if is_watcher_running():
        return True
    cmd = _watch_command(target)
    try:
        if IS_WIN:
            flags = (
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=flags,
            )
        else:
            subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
        return True
    except Exception as e:
        _log(f"[error] 启动后台监控进程失败: {e}")
        return False


def enable_auto_patch(target=""):
    """开启自动补丁：保存配置 + 注册开机自启 + 启动后台守护。"""
    cfg = load_config()
    cfg["enabled"] = True
    cfg["failed_fingerprint"] = ""
    if target and target.strip():
        cfg["target"] = target.strip()
    save_config(cfg)

    try:
        if IS_MAC:
            return _install_autostart_mac(cfg.get("target", ""))
        if IS_WIN:
            return _install_autostart_win(cfg.get("target", ""))
        start_watcher_background(cfg.get("target", ""))
        return True, "已开启后台监控"
    except Exception as e:
        _log(f"[error] 开启自动补丁失败: {e}")
        return False, f"注册开机自启失败：{e}"


def disable_auto_patch():
    """关闭自动补丁：更新配置 + 卸载开机自启 + 停止后台守护。"""
    cfg = load_config()
    cfg["enabled"] = False
    save_config(cfg)

    try:
        if IS_MAC:
            return _uninstall_autostart_mac()
        if IS_WIN:
            return _uninstall_autostart_win()
        stop_watcher()
        return True, "已关闭后台监控"
    except Exception as e:
        _log(f"[error] 关闭自动补丁失败: {e}")
        return False, f"卸载开机自启失败：{e}"


def get_auto_status():
    """返回供 GUI / CLI 展示的自动补丁摘要字典。"""
    cfg = load_config()
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "autostart": is_autostart_installed(),
        "running": is_watcher_running(),
        "last_result": cfg.get("last_result"),
    }
