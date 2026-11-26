import os
import sys
import glob
import shutil
import struct
import json
import string
from collections import deque

_LAST_FOUND_MANAGER = ""


def clean_path(raw_path):
    return raw_path.strip().strip('"').strip("'")


def _dedup_newest(paths):
    seen = set()
    out = []
    existing = {p for p in paths if p and os.path.exists(p)}
    for p in sorted(existing, key=lambda x: os.path.getmtime(x), reverse=True):
        key = os.path.normcase(os.path.realpath(p))
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _extract_dir_from_reg_value(val):
    """从注册表 DisplayIcon / UninstallString / InstallLocation 中提取安装目录。"""
    if not val or not isinstance(val, str):
        return ""
    s = val.strip()
    if not s:
        return ""
    # 处理带引号的路径，例如 '"D:\\Apps\\Antigravity\\Uninstall.exe" /S'
    if s.startswith('"'):
        end = s.find('"', 1)
        if end > 1:
            s = s[1:end]
    else:
        # 去掉 DisplayIcon 末尾的 ",0" 或命令行参数
        if "," in s:
            s = s.split(",", 1)[0].strip()
        low = s.lower()
        for ext in (".exe", ".msi", ".bat", ".cmd"):
            idx = low.find(ext)
            if idx != -1:
                s = s[:idx + len(ext)]
                break
    s = s.strip().strip('"').strip("'")
    if not s:
        return ""
    if os.path.isdir(s):
        return s
    parent = os.path.dirname(s)
    if parent and os.path.isdir(parent):
        return parent
    return ""


def _win_logical_drives():
    """返回 Windows 上所有可用的本地/可移动盘符（如 ['C:\\', 'D:\\', ...]），避免触碰空光驱或断开的网络盘。"""
    drives = []
    try:
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        get_drive_type = ctypes.windll.kernel32.GetDriveTypeW
        # 2 = DRIVE_REMOVABLE, 3 = DRIVE_FIXED
        for i, letter in enumerate(string.ascii_uppercase):
            if bitmask & (1 << i):
                root = f"{letter}:\\"
                try:
                    dtype = get_drive_type(root)
                except Exception:
                    dtype = 3
                if dtype in (2, 3) and os.path.isdir(root):
                    drives.append(root)
    except Exception:
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if os.path.isdir(root):
                drives.append(root)
    return drives


def _win_running_antigravity_dirs():
    """如果 Antigravity 正在运行，直接从进程路径获取安装目录（跨盘秒定位）。"""
    dirs = []
    try:
        import subprocess
        ps_cmd = (
            "Get-Process -Name 'Antigravity','language_server' -ErrorAction SilentlyContinue "
            "| ForEach-Object { try { $_.Path } catch {} }"
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for line in (r.stdout or "").splitlines():
            p = line.strip()
            if p and os.path.isfile(p):
                d = os.path.dirname(p)
                dirs.append(d)
                # 如果是 resources\bin\language_server.exe，往上回两层拿到安装根目录
                parent2 = os.path.dirname(os.path.dirname(d))
                if parent2 and os.path.isdir(parent2):
                    dirs.append(parent2)
    except Exception:
        pass
    return dirs


def _win_candidate_roots():
    out = []
    for var in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "ProgramData", "APPDATA"):
        p = os.environ.get(var)
        if not p:
            continue
        out.append(os.path.join(p, "Programs"))
        out.append(p)
    up = os.environ.get("USERPROFILE", "")
    if up:
        out.append(os.path.join(up, "scoop", "apps"))
    scoop = os.environ.get("SCOOP", "")
    if scoop:
        out.append(os.path.join(scoop, "apps"))

    # 注册表（同时检查 InstallLocation / DisplayIcon / UninstallString 与 App Paths）
    try:
        import winreg
        hives = [(winreg.HKEY_CURRENT_USER, 'HKCU'), (winreg.HKEY_LOCAL_MACHINE, 'HKLM')]
        subkeys = [
            r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
            r'SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
        ]
        for hive, _ in hives:
            for subkey in subkeys:
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        info_key = winreg.QueryInfoKey(key)
                        for i in range(info_key[0]):
                            try:
                                name = winreg.EnumKey(key, i)
                                with winreg.OpenKey(key, name) as sub:
                                    disp = ''
                                    try:
                                        disp, _ = winreg.QueryValueEx(sub, 'DisplayName')
                                    except OSError:
                                        pass
                                    if (disp and 'antigravity' in disp.lower()) or ('antigravity' in name.lower()):
                                        for val_name in ('InstallLocation', 'DisplayIcon', 'UninstallString'):
                                            try:
                                                raw_val, _ = winreg.QueryValueEx(sub, val_name)
                                                extracted = _extract_dir_from_reg_value(raw_val)
                                                if extracted:
                                                    out.append(extracted)
                                            except OSError:
                                                pass
                            except OSError:
                                pass
                except OSError:
                    pass
            # App Paths
            try:
                with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Antigravity.exe') as ap:
                    for val_name in ('', 'Path'):
                        try:
                            raw_val, _ = winreg.QueryValueEx(ap, val_name)
                            extracted = _extract_dir_from_reg_value(raw_val)
                            if extracted:
                                out.append(extracted)
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass

    # 所有盘符的根目录与常见软件目录（覆盖 D:\、E:\ 等任意盘符）
    common_sub = ("", "Program Files", "Program Files (x86)", "Programs", "Software", "Apps", "App", "Tools", "Soft")
    for drive in _win_logical_drives():
        for sub in common_sub:
            p = os.path.join(drive, sub) if sub else drive
            if os.path.isdir(p):
                out.append(p)

    # 去重并保留顺序
    seen = set()
    unique = []
    for p in out:
        if not p or not os.path.isdir(p):
            continue
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def _win_scan_all_drives_for_manager(rel, max_depth=4, max_dirs=4000):
    """当快速路径未命中时，对所有本地盘符做带剪枝的广度优先搜索（BFS）。"""
    prune_common = {
        "$recycle.bin", "system volume information", "windows", "recovery",
        "perflogs", "msocache", "config.msi", "node_modules", ".git",
        "__pycache__", ".venv", "venv", ".idea", ".vscode", "appdata",
        "winsxs", "installer", "temp", "tmp",
    }
    drives = _win_logical_drives()
    # 优先扫描非 C 盘（C 盘常规路径前面已经查过），再扫描 C 盘兜底
    drives.sort(key=lambda d: (d.upper().startswith("C:"), d.upper()))

    hits = []
    visited = 0
    queue = deque((d, 0) for d in drives)

    while queue and visited < max_dirs:
        cur, depth = queue.popleft()
        visited += 1

        # 检查当前目录是否直接包含 resources\bin\language_server.exe
        cand = os.path.join(cur, rel)
        if os.path.isfile(cand):
            hits.append(cand)
            continue

        if depth >= max_depth:
            continue

        try:
            with os.scandir(cur) as it:
                sub_priority = []
                sub_normal = []
                for entry in it:
                    try:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                    except OSError:
                        continue
                    name_low = entry.name.lower()
                    if name_low.startswith(".") or name_low in prune_common:
                        continue
                    if "antigravity" in name_low:
                        sub_priority.append(entry.path)
                    else:
                        sub_normal.append(entry.path)
                # 目录名带 antigravity 的放队首优先检查
                for p in reversed(sub_priority):
                    queue.appendleft((p, depth + 1))
                for p in sub_normal:
                    queue.append((p, depth + 1))
        except OSError:
            continue

    return hits


def _posix_candidate_roots():
    from patcher.utils.file import get_posix_invoking_user_home
    user_home = get_posix_invoking_user_home()
    out = ["/opt", "/usr/share", "/usr/lib", "/usr/local/share", "/usr/local/lib"]
    if sys.platform == "darwin":
        out.append("/Applications")
        if user_home:
            out.append(os.path.join(user_home, "Applications"))
            # .app, скопированный из DMG, часто лежит прямо на Рабочем столе /
            # в Загрузках / Документах (особенно когда /Applications недоступен)
            for sub in ("Desktop", "Downloads", "Documents"):
                p = os.path.join(user_home, sub)
                if os.path.isdir(p):
                    out.append(p)
        else:
            out.append(os.path.expanduser("~/Applications"))
            for sub in ("Desktop", "Downloads", "Documents"):
                out.append(os.path.expanduser("~/" + sub))
    
    if user_home:
        out.append(os.path.join(user_home, ".local/share"))
    else:
        out.append(os.path.expanduser("~/.local/share"))
    return [p for p in out if p and os.path.isdir(p)]


def find_manager_binary():
    """Ищет бинарный файл language_server (language_server.exe на Windows)."""
    global _LAST_FOUND_MANAGER
    rel = os.path.join("resources", "bin", "language_server" + (".exe" if os.name == "nt" else ""))

    # 0. 复用上次已命中的有效路径（避免 GUI/后台监控轮询反复扫描磁盘）
    if _LAST_FOUND_MANAGER and os.path.isfile(_LAST_FOUND_MANAGER):
        return _LAST_FOUND_MANAGER

    # 1. Поиск в PATH через which
    w = shutil.which("language_server")
    if w:
        _LAST_FOUND_MANAGER = w
        return w

    cands = []

    # 2. Поиск в стандартных директориях (含所有盘符的根目录及常见软件目录)
    if os.name == "nt":
        for root in _win_candidate_roots():
            direct = os.path.join(root, rel)
            if os.path.isfile(direct):
                cands.append(direct)
            cands += glob.glob(os.path.join(root, "*ntigravity*", rel))
            cands += glob.glob(os.path.join(root, "*ntigravity*", "*", rel))

        # 3. 如果常规目录未命中，检查正在运行的 Antigravity 进程路径
        if not cands:
            for proc_dir in _win_running_antigravity_dirs():
                direct = os.path.join(proc_dir, rel)
                if os.path.isfile(direct):
                    cands.append(direct)
                direct_exe = os.path.join(proc_dir, "language_server.exe")
                if os.path.isfile(direct_exe):
                    cands.append(direct_exe)

        # 4. 兜底：对所有盘符做带剪枝的广度优先扫描（覆盖 D:\任意子目录\Antigravity 等自定义路径）
        if not cands:
            cands += _win_scan_all_drives_for_manager(rel)
    else:
        for root in _posix_candidate_roots():
            cands += glob.glob(os.path.join(root, "*ntigravity*", rel))
            cands += glob.glob(os.path.join(root, "*ntigravity*", "*", rel))
            # macOS .app support (Resources встречается и как resources —
            # см. /Applications/Antigravity.app/Contents/resources/bin/language_server)
            if sys.platform == "darwin":
                cands += glob.glob(os.path.join(root, "*ntigravity*.app", "Contents", "Resources", "bin", "language_server"))
                cands += glob.glob(os.path.join(root, "*ntigravity*.app", "Contents", "resources", "bin", "language_server"))
            direct = os.path.join(root, rel)
            if os.path.isfile(direct):
                cands.append(direct)

    deduped = _dedup_newest(cands)
    if deduped:
        _LAST_FOUND_MANAGER = deduped[0]
        return deduped[0]
    return ""


def resolve_manager_path(raw_path):
    if not raw_path:
        return ""
    cleaned = clean_path(raw_path)
    if not cleaned:
        return ""
    resolved = os.path.abspath(os.path.expandvars(os.path.expanduser(cleaned)))
    
    if os.path.isfile(resolved):
        name = os.path.basename(resolved).lower()
        if name in ("language_server", "language_server.exe"):
            return resolved
        return resolved
        
    if os.path.isdir(resolved):
        rel = os.path.join("resources", "bin", "language_server" + (".exe" if os.name == "nt" else ""))
        path1 = os.path.join(resolved, rel)
        if os.path.isfile(path1):
            return path1
        # macOS app contents (Resources/resources — разный регистр в сборках)
        if sys.platform == "darwin":
            for sub in ("Contents/Resources/bin/language_server", "Contents/resources/bin/language_server"):
                path2 = os.path.join(resolved, sub)
                if os.path.isfile(path2):
                    return path2
        # direct bin inside
        path3 = os.path.join(resolved, "language_server" + (".exe" if os.name == "nt" else ""))
        if os.path.isfile(path3):
            return path3
            
    return ""


def _read_asar_header(f):
    try:
        f.seek(0)
        _, header_size, _, json_size = struct.unpack('<IIII', f.read(16))
        json_bytes = f.read(json_size)
        header = json.loads(json_bytes.decode('utf-8'))
        payload_offset = 8 + header_size
        return header, payload_offset
    except Exception:
        return None, None


def read_package_json_from_asar(asar_path):
    if not os.path.exists(asar_path):
        return None
    try:
        with open(asar_path, 'rb') as f:
            header, payload_offset = _read_asar_header(f)
            if header is None:
                return None

            files = header.get('files', {})
            pkg_entry = files.get('package.json')
            if pkg_entry and 'offset' in pkg_entry and 'size' in pkg_entry:
                offset = int(pkg_entry['offset'])
                size = pkg_entry['size']
                f.seek(payload_offset + offset)
                data = f.read(size)
                pkg_data = json.loads(data.decode('utf-8'))
                return pkg_data.get('version')
    except Exception:
        pass
    return None


def find_asar_relative_to_manager(manager_path):
    parent = os.path.dirname(manager_path)
    for _ in range(4):
        if not parent or parent == os.path.dirname(parent):
            break
        for sub in ("resources/app.asar", "resources/app1.asar", "app.asar", "app1.asar", "Contents/Resources/app.asar", "Contents/Resources/app1.asar", "Contents/resources/app.asar", "Contents/resources/app1.asar"):
            p = os.path.join(parent, sub)
            if os.path.exists(p):
                return p
        parent = os.path.dirname(parent)
    return ""


def get_antigravity_version(manager_path):
    asar_path = find_asar_relative_to_manager(manager_path)
    if not asar_path:
        return None
    return read_package_json_from_asar(asar_path)
