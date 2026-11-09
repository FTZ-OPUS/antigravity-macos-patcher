"""反重力补丁 —— 图形界面版（Tkinter，无终端窗口）。

窗口里只有两个按钮：
  [开启补丁]  给不支持地区的账号用
  [关闭补丁]  还原原版，给支持地区的账号用
点完立刻在下方显示「开启成功 / 开启失败 / 关闭成功 / 关闭失败」，
并在成功前做四项独立复核（状态 / 二进制签名 / 应用签名密封 / 备份）。
"""

import os
import sys
import time
import queue
import threading
import tkinter as tk
from tkinter import font as tkfont

import patch_ops as ops

LOG_PATH = os.path.expanduser("~/Library/Logs/反重力补丁.log")

BG     = "#FFFFFF"
TEXT   = "#1D1D1F"
SUB    = "#8A8A8E"
LINE   = "#E5E5EA"
GREEN  = "#30B15A"
GREEN2 = "#289B4D"
BLUE   = "#0A84FF"
RED    = "#E5484D"
GRAY   = "#EFEFF3"
GRAY2  = "#E3E3E8"


def setup_log():
    """--windowed 打包后 sys.stdout 是 None，所有 print 都要有地方去。"""
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        f = open(LOG_PATH, "a", encoding="utf-8", errors="replace")
        f.write("\n" + "=" * 56 + "\n")
        f.write(time.strftime("==== %Y-%m-%d %H:%M:%S ====\n"))
        f.flush()
        sys.stdout = sys.stderr = f
    except Exception:
        pass


def pick_font(root):
    families = set(tkfont.families(root))
    for name in ("PingFang SC", "Hiragino Sans GB", "Heiti SC", "STHeiti", "Arial Unicode MS"):
        if name in families:
            return name
    return "Helvetica"


class RoundButton(tk.Canvas):
    """Canvas 手绘圆角按钮 —— tk.Button 在 macOS 上不吃自定义配色。"""

    def __init__(self, master, text, command, family, width=392, height=58,
                 fill=GREEN, fill_hover=GREEN2, fg="#FFFFFF", size=19):
        super().__init__(master, width=width, height=height,
                         bg=BG, highlightthickness=0, bd=0)
        self.command = command
        self.fill, self.fill_hover, self.fg = fill, fill_hover, fg
        self.enabled = True
        self.cw, self.ch = width, height   # 注意：不能叫 _w，那会覆盖 Tkinter 内部的控件路径

        self.rect = self._round_rect(1, 1, width - 1, height - 1, height / 2.4,
                                     fill=fill, outline="")
        self.label = self.create_text(width / 2, height / 2 + 1, text=text,
                                      fill=fg, font=(family, size, "bold"))
        self.configure(cursor="pointinghand")
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(pts, smooth=True, **kw)

    def _on_enter(self, _=None):
        if self.enabled:
            self.itemconfigure(self.rect, fill=self.fill_hover)

    def _on_leave(self, _=None):
        if self.enabled:
            self.itemconfigure(self.rect, fill=self.fill)

    def _on_click(self, _=None):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, on, fill=None, fill_hover=None, fg=None):
        self.enabled = bool(on)
        if fill:
            self.fill, self.fill_hover = fill, (fill_hover or fill)
        if fg:
            self.fg = fg
        self.itemconfigure(self.rect, fill=self.fill if on else GRAY)
        self.itemconfigure(self.label, fill=self.fg if on else "#B9B9BF")
        self.configure(cursor="pointinghand" if on else "arrow")


class App:
    def __init__(self, root, target=""):
        self.root = root
        self.family = pick_font(root)
        self.busy = False
        self.bundle = ""
        self.path = ""
        self._target = (target or "").strip()   # 记住用户/测试指定的目标，刷新时不要重新猜
        self.q = queue.Queue()      # 后台线程 → 主线程 的结果队列（Tk 不允许跨线程直接改界面）

        root.title("反重力补丁")
        root.configure(bg=BG)
        root.geometry("440x486")
        root.resizable(False, False)
        root.lift()
        try:
            root.attributes("-topmost", True)
            root.after(600, lambda: root.attributes("-topmost", False))
        except Exception:
            pass

        pad = tk.Frame(root, bg=BG, height=22)
        pad.pack(fill="x")

        tk.Label(root, text="反重力补丁", bg=BG, fg=TEXT,
                 font=(self.family, 24, "bold")).pack()
        tk.Label(root, text="Antigravity 桌面版", bg=BG, fg=SUB,
                 font=(self.family, 12)).pack(pady=(2, 0))

        # 当前状态
        state_box = tk.Frame(root, bg="#F7F7FA")
        state_box.pack(fill="x", padx=24, pady=(18, 0), ipady=11)
        self.dot = tk.Canvas(state_box, width=14, height=14, bg="#F7F7FA",
                             highlightthickness=0, bd=0)
        self.dot.pack(side="left", padx=(16, 8))
        self.dot_id = self.dot.create_oval(1, 1, 13, 13, fill=SUB, outline="")
        self.state_label = tk.Label(state_box, text="检测中…", bg="#F7F7FA", fg=TEXT,
                                    font=(self.family, 14, "bold"))
        self.state_label.pack(side="left")

        # 两个按钮
        self.btn_on = RoundButton(root, "开启补丁", self.do_enable, self.family,
                                  fill=GREEN, fill_hover=GREEN2)
        self.btn_on.pack(pady=(20, 10))
        self.btn_off = RoundButton(root, "关闭补丁", self.do_disable, self.family,
                                   fill="#4A4A4F", fill_hover="#3A3A3F")
        self.btn_off.pack()

        # 结果区
        self.result = tk.Label(root, text="", bg=BG, fg=SUB,
                               font=(self.family, 21, "bold"))
        self.result.pack(pady=(20, 0))
        self.detail = tk.Label(root, text="", bg=BG, fg=SUB,
                               font=(self.family, 12), wraplength=380, justify="center")
        self.detail.pack(pady=(6, 0))

        # 底部工具行
        bottom = tk.Frame(root, bg=BG)
        bottom.pack(side="bottom", fill="x", padx=24, pady=(0, 14))
        self.btn_open = RoundButton(bottom, "打开 Antigravity", self.do_open, self.family,
                                    width=196, height=40, fill=GRAY, fill_hover=GRAY2,
                                    fg="#3A3A3F", size=13)
        self.btn_open.pack(side="left")
        self.btn_refresh = RoundButton(bottom, "刷新状态", self.refresh, self.family,
                                       width=150, height=40, fill=GRAY, fill_hover=GRAY2,
                                       fg="#3A3A3F", size=13)
        self.btn_refresh.pack(side="right")
        self.btn_open.set_enabled(False, fg="#3A3A3F")

        tk.Frame(root, bg=LINE, height=1).pack(side="bottom", fill="x", padx=24, pady=(0, 8))

        self.refresh(initial=True)

    # ---------- 状态 ----------
    def set_state(self, state):
        if state == "patched":
            self.dot.itemconfigure(self.dot_id, fill=GREEN)
            self.state_label.configure(text="已打补丁（开启）", fg=TEXT)
        elif state == "unpatched":
            self.dot.itemconfigure(self.dot_id, fill=SUB)
            self.state_label.configure(text="原版（未打补丁）", fg=TEXT)
        else:
            self.dot.itemconfigure(self.dot_id, fill=RED)
            self.state_label.configure(text="未找到 Antigravity", fg=RED)

    def set_result(self, text, color, detail=""):
        self.result.configure(text=text, fg=color)
        self.detail.configure(text=detail)

    def set_busy(self, busy):
        self.busy = busy
        for b in (self.btn_on, self.btn_off, self.btn_refresh):
            b.set_enabled(not busy)
        if busy:
            self.btn_open.set_enabled(False)

    def refresh(self, initial=False):
        path = ops.find_target(self._target)
        self.path = path
        if not path or not os.path.isfile(path):
            self.set_state("missing")
            self.btn_on.set_enabled(False)
            self.btn_off.set_enabled(False)
            if initial:
                self.set_result("", SUB,
                                "没有找到 Antigravity 桌面版。请确认 Antigravity.app 已安装。")
            return
        self.bundle = ops.app_bundle(path)
        st = ops.state_of(path)
        self.set_state(st)
        # 两个按钮始终可点（已经是该状态时点了也会给出"关闭成功/开启成功"确认）
        self.btn_on.set_enabled(not self.busy)
        self.btn_off.set_enabled(not self.busy)
        if initial:
            self.set_result("", SUB, "")

    # ---------- 动作 ----------
    def do_enable(self):
        self._run("on")

    def do_disable(self):
        self._run("off")

    def do_open(self):
        if self.bundle:
            ok, msg = ops.reopen_app(self.bundle)
            if not ok:
                self.set_result("打开失败", RED, msg)

    def _run(self, mode):
        if self.busy:
            return
        word = "开启" if mode == "on" else "关闭"
        self.set_busy(True)
        self.set_result("", SUB, f"正在{word}补丁…（会先退出 Antigravity，约 5-15 秒）")

        def worker():
            # 后台线程只做文件操作和检测，绝不动界面；结果放进队列由主线程取。
            try:
                if ops.is_running() and not ops.quit_app():
                    print("[warn] Antigravity 未能退出，继续尝试改写")
                if mode == "on":
                    ok, detail = ops.apply_patch(self.path)
                    expect = "patched"
                else:
                    ok, detail = ops.revert_patch(self.path)
                    expect = "unpatched"

                rows = ops.verify(self.path, expect, self.bundle) if ok else []
                all_ok = ok and all(r[2] for r in rows)
                self.q.put((mode, all_ok, detail, rows))
            except Exception as e:
                print(f"[error] {e}")
                self.q.put((mode, False, f"{type(e).__name__}: {e}", []))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(120, self._poll)

    def _poll(self):
        """主线程轮询结果队列（Tk 不能从别的线程碰控件）。"""
        try:
            mode, ok, detail, rows = self.q.get_nowait()
        except queue.Empty:
            if self.busy:
                self.root.after(120, self._poll)
            return
        self._finish(mode, ok, detail, rows)

    def _finish(self, mode, ok, detail, rows):
        word = "开启" if mode == "on" else "关闭"
        self.set_busy(False)
        self.refresh()

        if ok:
            untouched = detail.startswith("已经")
            if untouched:
                self.set_result(f"{word}成功", GREEN,
                                "（本来就处于该状态，本次未改动文件）")
            else:
                self.set_result(f"{word}成功", GREEN,
                                "请重新打开 Antigravity 才会生效。" if self.bundle else "已生效。")
                self.btn_open.set_enabled(bool(self.bundle), fill=BLUE, fill_hover="#0A6FD8",
                                          fg="#FFFFFF")
        else:
            self.set_result(f"{word}失败", RED, detail or "未知原因")
            if rows:
                bad = "、".join(r[0] for r in rows if not r[2])
                self.detail.configure(text=f"{detail}\n未通过：{bad}")
        print(f"[result] {word}{'成功' if ok else '失败'} | {detail} | "
              f"{[(r[0], r[1], r[2]) for r in rows]}")


def main():
    setup_log()
    target = os.environ.get("AG_TARGET", "")
    if len(sys.argv) > 1:
        target = sys.argv[1]
    root = tk.Tk()
    App(root, target)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
