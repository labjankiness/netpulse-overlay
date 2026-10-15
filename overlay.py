#!/usr/bin/env python3
"""
NetPulse Desktop System Overlay
A real-time, always-on-top network & DNS stability overlay HUD written in pure Python (Tkinter).
Runs natively on your desktop without needing a web browser.
"""

import os
import sys
import json
import time
import socket
import threading
import traceback
import subprocess
import re
import platform
import urllib.request
import urllib.parse
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, 'targets.json')
LOG_FILE = os.path.join(APP_DIR, 'overlay.log')
IS_WINDOWS = platform.system().lower() == 'windows'

def log(msg):
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

DEFAULT_TARGETS = [
    {
        "id": "ddg",
        "name": "DuckDuckGo Web",
        "host": "duckduckgo.com",
        "url": "https://duckduckgo.com",
        "type": "web",
        "deletable": False
    },
    {
        "id": "ddg_api",
        "name": "DuckDuckGo API",
        "host": "api.duckduckgo.com",
        "url": "https://api.duckduckgo.com/?q=test&format=json",
        "type": "api",
        "deletable": False
    },
    {
        "id": "cf_dns",
        "name": "Cloudflare DNS",
        "host": "1.1.1.1",
        "port": 53,
        "type": "dns_ip",
        "deletable": False
    },
    {
        "id": "google_dns",
        "name": "Google DNS",
        "host": "8.8.8.8",
        "port": 53,
        "type": "dns_ip",
        "deletable": False
    },
    {
        "id": "github",
        "name": "GitHub (Baseline)",
        "host": "github.com",
        "url": "https://github.com",
        "type": "web",
        "deletable": False
    }
]

# Color Palette
COLOR_BG = "#0f172a"
COLOR_HEADER = "#1e293b"
COLOR_CARD = "#1e293b"
COLOR_BORDER = "#334155"
COLOR_TEXT = "#f8fafc"
COLOR_MUTED = "#94a3b8"
COLOR_GREEN = "#10b981"
COLOR_YELLOW = "#f59e0b"
COLOR_RED = "#ef4444"
COLOR_ACCENT = "#6366f1"

class TargetManager:
    def __init__(self, filepath):
        self.filepath = filepath
        self.lock = threading.Lock()
        self.targets = []
        self.load()

    def load(self):
        with self.lock:
            if os.path.exists(self.filepath):
                try:
                    with open(self.filepath, 'r', encoding='utf-8') as f:
                        self.targets = json.load(f)
                        return
                except Exception as e:
                    log(f"Error loading targets: {e}")
            self.targets = [dict(t) for t in DEFAULT_TARGETS]
            self.save_unlocked()

    def save_unlocked(self):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.targets, f, indent=2)
        except Exception as e:
            log(f"Error saving targets: {e}")

    def get_targets(self):
        with self.lock:
            return [dict(t) for t in self.targets]

    def add_target(self, name, host, target_type="web", port=53):
        with self.lock:
            tid = f"custom_{int(time.time() * 1000)}"
            clean_host = host.strip()
            target_url = None
            if clean_host.startswith("http://") or clean_host.startswith("https://"):
                target_url = clean_host
                clean_host = urllib.parse.urlparse(clean_host).hostname or clean_host
            elif target_type in ("web", "api"):
                target_url = f"https://{clean_host}"

            new_target = {
                "id": tid,
                "name": name.strip() or clean_host,
                "host": clean_host,
                "type": target_type,
                "deletable": True
            }
            if target_url:
                new_target["url"] = target_url
            if target_type == "dns_ip":
                new_target["port"] = int(port)

            self.targets.append(new_target)
            self.save_unlocked()
            return new_target

    def delete_target(self, tid):
        with self.lock:
            initial = len(self.targets)
            self.targets = [t for t in self.targets if not (t["id"] == tid and t.get("deletable", True))]
            if len(self.targets) < initial:
                self.save_unlocked()
                return True
        return False

# DNS resolution check
def check_dns(host):
    t0 = time.time()
    try:
        ip = socket.gethostbyname(host)
        return {"status": "ok", "time": round((time.time() - t0) * 1000), "ip": ip}
    except Exception as e:
        return {"status": "error", "time": round((time.time() - t0) * 1000), "error": str(e)}

# Silent, zero-glitch Ping check (guaranteed no console creation or GPU DWM flicker)
def ping_host(host, timeout_ms=1000):
    t0 = time.time()
    try:
        if IS_WINDOWS:
            cmd = ['ping', '-n', '1', '-w', str(timeout_ms), host]
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1.5,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
        else:
            cmd = ['ping', '-c', '1', '-W', '1', host]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)

        out = res.stdout
        m = re.search(r'time[=<](\d+)ms', out, re.IGNORECASE)
        if m:
            return {"status": "ok", "latency": int(m.group(1))}
        if 'reply from' in out.lower() or 'bytes from' in out.lower():
            elapsed = max(1, round((time.time() - t0) * 1000))
            return {"status": "ok", "latency": elapsed}
    except Exception:
        pass
    return {"status": "timeout", "latency": timeout_ms}

def check_tcp(host, port, timeout_sec=1.5):
    t0 = time.time()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout_sec)
    try:
        s.connect((host, port))
        s.close()
        return {"status": "ok", "time": round((time.time() - t0) * 1000)}
    except socket.timeout:
        s.close()
        return {"status": "timeout", "time": round(timeout_sec * 1000)}
    except Exception:
        s.close()
        return {"status": "error", "time": round((time.time() - t0) * 1000)}

def probe_target(target):
    host = target["host"]

    # 1. DNS Resolution check
    dns_info = None
    if not re.match(r'^\d+\.\d+\.\d+\.\d+$', host):
        dns_res = check_dns(host)
        if dns_res["status"] == "ok":
            dns_info = f"DNS {dns_res['time']}ms"
        else:
            return {"status": "error", "latency": dns_res["time"], "detail": "DNS Failed"}

    # 2. Ping Reachability
    ping_res = ping_host(host)
    if ping_res["status"] == "ok":
        lat = ping_res["latency"]
        status = "slow" if lat > 180 else "ok"
        detail_parts = [f"Ping {lat}ms"]
        if dns_info:
            detail_parts.append(dns_info)
        return {"status": status, "latency": lat, "detail": " | ".join(detail_parts)}

    # Fallback to TCP if ping is filtered
    port = target.get("port", 443 if target.get("type") in ("web", "api") else 53)
    tcp_res = check_tcp(host, port)
    if tcp_res["status"] == "ok":
        lat = tcp_res["time"]
        status = "slow" if lat > 200 else "ok"
        return {"status": status, "latency": lat, "detail": f"TCP {port} ({lat}ms)"}

    return {"status": "timeout", "latency": None, "detail": "Host Unreachable / Timeout"}


class DesktopOverlayApp:
    def __init__(self, root):
        self.root = root
        self.target_mgr = TargetManager(CONFIG_FILE)
        self.running = True
        self.frameless = False
        self.target_widgets = {}

        self.root.title("NetPulse Overlay")
        self.root.attributes("-topmost", True)
        self.root.configure(bg=COLOR_BG)

        self.root.geometry("340x380+100+100")
        self.root.minsize(300, 240)

        self.drag_x = 0
        self.drag_y = 0

        self.setup_ui()

        self.root.update_idletasks()
        self.root.lift()
        self.root.focus_force()

        # Polling thread
        self.poll_thread = threading.Thread(target=self.background_poll_loop, daemon=True)
        self.poll_thread.start()
        log("NetPulse UI initialized with zero-flicker background engine")

    def setup_ui(self):
        # Header toolbar
        self.header = tk.Frame(self.root, bg=COLOR_HEADER, height=36)
        self.header.pack(fill=tk.X, side=tk.TOP)
        self.header.pack_propagate(False)

        # Pulse circle
        self.pulse_canvas = tk.Canvas(self.header, width=14, height=14, bg=COLOR_HEADER, highlightthickness=0)
        self.pulse_circle = self.pulse_canvas.create_oval(2, 2, 12, 12, fill=COLOR_GREEN, outline="")
        self.pulse_canvas.pack(side=tk.LEFT, padx=(10, 6))

        # Title
        self.title_lbl = tk.Label(
            self.header, text="NetPulse Overlay", bg=COLOR_HEADER, fg=COLOR_TEXT,
            font=("Segoe UI", 9, "bold")
        )
        self.title_lbl.pack(side=tk.LEFT)

        # Action Buttons
        self.btn_add = tk.Button(
            self.header, text="+ Add", bg=COLOR_ACCENT, fg="white",
            font=("Segoe UI", 8, "bold"), bd=0, padx=8, pady=2, cursor="hand2",
            command=self.open_add_dialog
        )
        self.btn_add.pack(side=tk.RIGHT, padx=6)

        self.btn_border = tk.Button(
            self.header, text="Frameless", bg=COLOR_BORDER, fg=COLOR_TEXT,
            font=("Segoe UI", 8), bd=0, padx=6, pady=2, cursor="hand2",
            command=self.toggle_frameless
        )
        self.btn_border.pack(side=tk.RIGHT, padx=2)

        # Container for target cards
        self.content_frame = tk.Frame(self.root, bg=COLOR_BG)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Bottom status bar
        self.status_bar = tk.Label(
            self.root, text="Status: Real-time Ping & DNS probes active | Always-on-top",
            bg=COLOR_HEADER, fg=COLOR_MUTED, font=("Segoe UI", 7), anchor="w", padx=10, pady=4
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.render_target_list()

    def toggle_frameless(self):
        self.frameless = not self.frameless
        self.root.overrideredirect(self.frameless)
        if self.frameless:
            self.btn_border.config(text="Windowed")
            self.header.bind("<Button-1>", self.on_drag_start)
            self.header.bind("<B1-Motion>", self.on_drag_motion)
            self.title_lbl.bind("<Button-1>", self.on_drag_start)
            self.title_lbl.bind("<B1-Motion>", self.on_drag_motion)
        else:
            self.btn_border.config(text="Frameless")
            self.header.unbind("<Button-1>")
            self.header.unbind("<B1-Motion>")
            self.title_lbl.unbind("<Button-1>")
            self.title_lbl.unbind("<B1-Motion>")
        self.root.lift()

    def on_drag_start(self, event):
        self.drag_x = event.x
        self.drag_y = event.y

    def on_drag_motion(self, event):
        x = self.root.winfo_x() + (event.x - self.drag_x)
        y = self.root.winfo_y() + (event.y - self.drag_y)
        self.root.geometry(f"+{x}+{y}")

    def render_target_list(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        self.target_widgets.clear()

        targets = self.target_mgr.get_targets()
        for t in targets:
            tid = t["id"]
            row = tk.Frame(self.content_frame, bg=COLOR_CARD, bd=1, relief="solid")
            row.pack(fill=tk.X, pady=3, ipady=4)

            # Left dot
            canvas = tk.Canvas(row, width=12, height=12, bg=COLOR_CARD, highlightthickness=0)
            dot = canvas.create_oval(2, 2, 10, 10, fill=COLOR_MUTED, outline="")
            canvas.pack(side=tk.LEFT, padx=(8, 8))

            # Info block
            info_frame = tk.Frame(row, bg=COLOR_CARD)
            info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

            name_lbl = tk.Label(
                info_frame, text=t["name"], bg=COLOR_CARD, fg=COLOR_TEXT,
                font=("Segoe UI", 8, "bold"), anchor="w"
            )
            name_lbl.pack(anchor="w")

            detail_lbl = tk.Label(
                info_frame, text=t["host"], bg=COLOR_CARD, fg=COLOR_MUTED,
                font=("Segoe UI", 7), anchor="w"
            )
            detail_lbl.pack(anchor="w")

            # Right metrics
            right_frame = tk.Frame(row, bg=COLOR_CARD)
            right_frame.pack(side=tk.RIGHT, padx=(4, 8))

            lat_lbl = tk.Label(
                right_frame, text="--ms", bg=COLOR_CARD, fg=COLOR_MUTED,
                font=("Segoe UI", 9, "bold")
            )
            lat_lbl.pack(side=tk.RIGHT)

            if t.get("deletable", False):
                del_btn = tk.Label(
                    right_frame, text="✕", bg=COLOR_CARD, fg=COLOR_MUTED,
                    font=("Segoe UI", 8), cursor="hand2"
                )
                del_btn.pack(side=tk.RIGHT, padx=(0, 6))
                del_btn.bind("<Button-1>", lambda e, target_id=tid: self.delete_target(target_id))
                del_btn.bind("<Enter>", lambda e, b=del_btn: b.config(fg=COLOR_RED))
                del_btn.bind("<Leave>", lambda e, b=del_btn: b.config(fg=COLOR_MUTED))

            self.target_widgets[tid] = {
                "canvas": canvas,
                "dot": dot,
                "lat_lbl": lat_lbl,
                "detail_lbl": detail_lbl,
                "row": row
            }

    def delete_target(self, tid):
        if messagebox.askyesno("NetPulse", "Remove target from monitor?"):
            self.target_mgr.delete_target(tid)
            self.render_target_list()

    def open_add_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Monitoring Target")
        dialog.attributes("-topmost", True)
        dialog.configure(bg=COLOR_BG)
        dialog.geometry("300x240+150+150")
        dialog.resizable(False, False)

        tk.Label(dialog, text="Add Target", bg=COLOR_BG, fg=COLOR_TEXT, font=("Segoe UI", 10, "bold")).pack(pady=(12, 6))

        tk.Label(dialog, text="Display Name:", bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=16)
        entry_name = tk.Entry(dialog, bg=COLOR_CARD, fg=COLOR_TEXT, insertbackground="white", bd=1)
        entry_name.pack(fill=tk.X, padx=16, pady=(2, 6))

        tk.Label(dialog, text="Domain / IP / URL:", bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=16)
        entry_host = tk.Entry(dialog, bg=COLOR_CARD, fg=COLOR_TEXT, insertbackground="white", bd=1)
        entry_host.pack(fill=tk.X, padx=16, pady=(2, 6))

        tk.Label(dialog, text="Type:", bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=16)
        type_var = tk.StringVar(value="web")
        combo = ttk.Combobox(dialog, textvariable=type_var, values=["web", "dns_ip"], state="readonly")
        combo.pack(fill=tk.X, padx=16, pady=(2, 12))

        def on_save():
            name = entry_name.get().strip()
            host = entry_host.get().strip()
            if not host:
                messagebox.showerror("Error", "Please provide a domain or IP address.", parent=dialog)
                return
            self.target_mgr.add_target(name, host, target_type=type_var.get())
            dialog.destroy()
            self.render_target_list()

        btn_box = tk.Frame(dialog, bg=COLOR_BG)
        btn_box.pack(fill=tk.X, padx=16)
        tk.Button(btn_box, text="Cancel", bg=COLOR_CARD, fg=COLOR_TEXT, bd=0, padx=10, command=dialog.destroy).pack(side=tk.LEFT)
        tk.Button(btn_box, text="Save & Monitor", bg=COLOR_ACCENT, fg="white", bd=0, padx=12, command=on_save).pack(side=tk.RIGHT)

    def background_poll_loop(self):
        while self.running:
            targets = self.target_mgr.get_targets()
            results = {}
            for t in targets:
                if not self.running:
                    break
                results[t["id"]] = probe_target(t)
                time.sleep(0.1)  # Smooth spacing between probes

            if self.running:
                self.root.after(0, lambda r=results: self.update_probe_ui(r))

            time.sleep(4.0)

    def update_probe_ui(self, results):
        has_error = False
        has_slow = False

        for tid, res in results.items():
            if tid not in self.target_widgets:
                continue

            widgets = self.target_widgets[tid]
            status = res["status"]
            lat = res["latency"]

            if status == "ok":
                color = COLOR_GREEN
                text = f"{lat}ms" if lat is not None else "OK"
            elif status == "slow":
                color = COLOR_YELLOW
                text = f"{lat}ms" if lat is not None else "SLOW"
                has_slow = True
            elif status == "timeout":
                color = COLOR_RED
                text = "TIMEOUT"
                has_error = True
            else:
                color = COLOR_RED
                text = "ERROR"
                has_error = True

            widgets["canvas"].itemconfig(widgets["dot"], fill=color)
            widgets["lat_lbl"].config(text=text, fg=color)
            widgets["detail_lbl"].config(text=res.get("detail", ""))

        if has_error:
            self.pulse_canvas.itemconfig(self.pulse_circle, fill=COLOR_RED)
        elif has_slow:
            self.pulse_canvas.itemconfig(self.pulse_circle, fill=COLOR_YELLOW)
        else:
            self.pulse_canvas.itemconfig(self.pulse_circle, fill=COLOR_GREEN)


def main():
    log("Starting NetPulse Desktop Overlay main()")
    try:
        root = tk.Tk()
        app = DesktopOverlayApp(root)
        root.mainloop()
        log("NetPulse closed normally")
    except Exception as e:
        err = traceback.format_exc()
        log(f"CRASH: {err}")
        try:
            with open(os.path.join(APP_DIR, "overlay_crash.log"), "w", encoding="utf-8") as f:
                f.write(err)
        except Exception:
            pass

if __name__ == "__main__":
    main()
