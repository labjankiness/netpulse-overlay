#!/usr/bin/env python3
"""
NetPulse Desktop System Overlay
A frameless, draggable, always-on-top HUD overlay with a 1-click minimize/collapse button.
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

def get_default_gateway():
    try:
        if IS_WINDOWS:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            out = subprocess.check_output(
                'ipconfig',
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
                text=True
            )
            matches = re.findall(r'Default Gateway[ .]*:\s*(?:[a-f0-9:]+%\d+\s+)?([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)', out)
            for gw in matches:
                if gw and gw != '0.0.0.0':
                    return gw
        else:
            out = subprocess.check_output(['ip', 'route', 'show', 'default'], text=True)
            m = re.search(r'default via ([0-9.]+)', out)
            if m:
                return m.group(1)
    except Exception as e:
        log(f"Gateway detection fallback: {e}")
    return '10.21.5.100'

GATEWAY_IP = get_default_gateway()

DEFAULT_TARGETS = [
    {
        "id": "lan",
        "name": "Router (LAN)",
        "short": "LAN",
        "host": GATEWAY_IP,
        "type": "dns_ip",
        "tier": "tier1",
        "deletable": False
    },
    {
        "id": "cf_dns",
        "name": "Cloudflare DNS",
        "short": "DNS",
        "host": "1.1.1.1",
        "port": 53,
        "type": "dns_ip",
        "tier": "tier2",
        "deletable": False
    },
    {
        "id": "google_dns",
        "name": "Google DNS",
        "short": "Google",
        "host": "8.8.8.8",
        "port": 53,
        "type": "dns_ip",
        "tier": "tier2",
        "deletable": False
    },
    {
        "id": "ddg",
        "name": "DuckDuckGo",
        "short": "DDG",
        "host": "duckduckgo.com",
        "url": "https://duckduckgo.com",
        "type": "web",
        "tier": "tier3",
        "deletable": False
    },
    {
        "id": "github",
        "name": "GitHub (Baseline)",
        "short": "Web",
        "host": "github.com",
        "url": "https://github.com",
        "type": "web",
        "tier": "tier3",
        "deletable": False
    }
]

# Color Palette
COLOR_BG = "#0b0f19"
COLOR_HEADER = "#151e32"
COLOR_CARD = "#131b2e"
COLOR_BORDER = "#25334e"
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
                        loaded = json.load(f)
                        has_lan = any(t.get('id') == 'lan' for t in loaded)
                        if not has_lan:
                            lan_target = dict(DEFAULT_TARGETS[0])
                            lan_target['host'] = GATEWAY_IP
                            loaded.insert(0, lan_target)
                        self.targets = loaded
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

            short = name.strip()[:6] or clean_host[:6]
            new_target = {
                "id": tid,
                "name": name.strip() or clean_host,
                "short": short,
                "host": clean_host,
                "type": target_type,
                "tier": "tier3",
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

# Network checks
def check_dns(host):
    t0 = time.time()
    try:
        ip = socket.gethostbyname(host)
        return {"status": "ok", "time": round((time.time() - t0) * 1000), "ip": ip}
    except Exception as e:
        return {"status": "error", "time": round((time.time() - t0) * 1000), "error": str(e)}

def ping_host(host, timeout_ms=800):
    t0 = time.time()
    try:
        if IS_WINDOWS:
            cmd = ['ping', '-n', '1', '-w', str(timeout_ms), host]
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            creationflags = subprocess.CREATE_NO_WINDOW
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1.2,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
        else:
            cmd = ['ping', '-c', '1', '-W', '1', host]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.2)

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

def check_tcp(host, port, timeout_sec=1.2):
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
    is_ip = bool(re.match(r'^\d+\.\d+\.\d+\.\d+$', host))

    dns_time = None
    if not is_ip:
        dns_res = check_dns(host)
        if dns_res["status"] == "ok":
            dns_time = dns_res["time"]
        else:
            return {"status": "error", "latency": dns_res["time"], "detail": "DNS Fail"}

    ping_res = ping_host(host)
    if ping_res["status"] == "ok":
        lat = ping_res["latency"]
        status = "slow" if lat > 180 else "ok"
        detail = f"Ping {lat}ms"
        if dns_time is not None:
            detail += f" | DNS {dns_time}ms"
        return {"status": status, "latency": lat, "detail": detail}

    port = target.get("port", 443 if target.get("type") in ("web", "api") else 53)
    tcp_res = check_tcp(host, port)
    if tcp_res["status"] == "ok":
        lat = tcp_res["time"]
        status = "slow" if lat > 200 else "ok"
        return {"status": status, "latency": lat, "detail": f"TCP {port} ({lat}ms)"}

    return {"status": "timeout", "latency": None, "detail": "Timeout"}


class DesktopOverlayHUD:
    def __init__(self, root):
        self.root = root
        self.target_mgr = TargetManager(CONFIG_FILE)
        self.running = True
        self.is_minimized = False
        self.target_widgets = {}
        self.pill_widgets = {}

        # Window settings: True frameless floating overlay
        self.root.title("NetPulse Overlay")
        self.root.overrideredirect(True)          # Frameless HUD
        self.root.attributes("-topmost", True)      # Always on top
        try:
            self.root.attributes("-alpha", 0.94)    # Sleek dark glass
        except Exception:
            pass
        self.root.configure(bg=COLOR_BORDER)

        # Default size and position
        self.full_width = 320
        self.mini_width = 460
        self.mini_height = 34

        # Position at (150, 150) for immediate visibility
        self.root.geometry(f"{self.full_width}x240+150+150")

        # Dragging variables
        self.drag_x = 0
        self.drag_y = 0

        self.setup_ui()

        # Lift & maintain topmost
        self.root.update_idletasks()
        self.root.lift()

        # Polling thread
        self.poll_thread = threading.Thread(target=self.background_poll_loop, daemon=True)
        self.poll_thread.start()
        log("NetPulse Desktop HUD initialized with minimize control")

    def setup_ui(self):
        # Outer container with border
        self.container = tk.Frame(self.root, bg=COLOR_BG, bd=0)
        self.container.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Header Bar (Draggable)
        self.header = tk.Frame(self.container, bg=COLOR_HEADER, height=32)
        self.header.pack(fill=tk.X, side=tk.TOP)
        self.header.pack_propagate(False)

        self.header.bind("<Button-1>", self.on_drag_start)
        self.header.bind("<B1-Motion>", self.on_drag_motion)

        # Status pulse dot
        self.pulse_canvas = tk.Canvas(self.header, width=12, height=12, bg=COLOR_HEADER, highlightthickness=0)
        self.pulse_circle = self.pulse_canvas.create_oval(2, 2, 10, 10, fill=COLOR_GREEN, outline="")
        self.pulse_canvas.pack(side=tk.LEFT, padx=(8, 4))
        self.pulse_canvas.bind("<Button-1>", self.on_drag_start)
        self.pulse_canvas.bind("<B1-Motion>", self.on_drag_motion)

        # Title / Mini Ticker area
        self.title_lbl = tk.Label(
            self.header, text="NetPulse Overlay", bg=COLOR_HEADER, fg=COLOR_TEXT,
            font=("Segoe UI", 9, "bold")
        )
        self.title_lbl.pack(side=tk.LEFT)
        self.title_lbl.bind("<Button-1>", self.on_drag_start)
        self.title_lbl.bind("<B1-Motion>", self.on_drag_motion)

        # Compact Ticker items (visible only when minimized)
        self.mini_ticker_frame = tk.Frame(self.header, bg=COLOR_HEADER)
        self.mini_ticker_frame.bind("<Button-1>", self.on_drag_start)
        self.mini_ticker_frame.bind("<B1-Motion>", self.on_drag_motion)

        # Window Controls: Close (✕), Minimize (─), Add (+)
        self.btn_close = tk.Label(
            self.header, text="✕", bg=COLOR_HEADER, fg=COLOR_MUTED,
            font=("Segoe UI", 9), cursor="hand2", width=3
        )
        self.btn_close.pack(side=tk.RIGHT, padx=(0, 4))
        self.btn_close.bind("<Button-1>", lambda e: self.close_app())
        self.btn_close.bind("<Enter>", lambda e: self.btn_close.config(fg=COLOR_RED))
        self.btn_close.bind("<Leave>", lambda e: self.btn_close.config(fg=COLOR_MUTED))

        # Minimize / Collapse Button
        self.btn_minimize = tk.Label(
            self.header, text="─", bg=COLOR_HEADER, fg=COLOR_MUTED,
            font=("Segoe UI", 10, "bold"), cursor="hand2", width=3
        )
        self.btn_minimize.pack(side=tk.RIGHT, padx=2)
        self.btn_minimize.bind("<Button-1>", lambda e: self.toggle_minimize())
        self.btn_minimize.bind("<Enter>", lambda e: self.btn_minimize.config(fg=COLOR_TEXT))
        self.btn_minimize.bind("<Leave>", lambda e: self.btn_minimize.config(fg=COLOR_MUTED))

        # Add target button (+)
        self.btn_add = tk.Label(
            self.header, text="+", bg=COLOR_HEADER, fg=COLOR_MUTED,
            font=("Segoe UI", 11, "bold"), cursor="hand2", width=3
        )
        self.btn_add.pack(side=tk.RIGHT, padx=2)
        self.btn_add.bind("<Button-1>", lambda e: self.open_add_dialog())
        self.btn_add.bind("<Enter>", lambda e: self.btn_add.config(fg=COLOR_ACCENT))
        self.btn_add.bind("<Leave>", lambda e: self.btn_add.config(fg=COLOR_MUTED))

        # Content frame for full view cards
        self.content_frame = tk.Frame(self.container, bg=COLOR_BG)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        self.render_target_list()
        self.setup_mini_ticker()

    def on_drag_start(self, event):
        self.drag_x = event.x_root - self.root.winfo_x()
        self.drag_y = event.y_root - self.root.winfo_y()

    def on_drag_motion(self, event):
        x = event.x_root - self.drag_x
        y = event.y_root - self.drag_y
        self.root.geometry(f"+{x}+{y}")

    def toggle_minimize(self):
        self.is_minimized = not self.is_minimized
        if self.is_minimized:
            # Collapse to minimal floating ticker pill
            self.btn_minimize.config(text="□")
            self.title_lbl.pack_forget()
            self.content_frame.pack_forget()
            self.mini_ticker_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 8))
            self.root.geometry(f"{self.mini_width}x{self.mini_height}")
        else:
            # Expand to full cards view
            self.btn_minimize.config(text="─")
            self.mini_ticker_frame.pack_forget()
            self.title_lbl.pack(side=tk.LEFT)
            self.content_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
            self.update_full_height()

        self.root.lift()

    def update_full_height(self):
        targets = self.target_mgr.get_targets()
        calc_h = 36 + (len(targets) * 38) + 12
        self.root.geometry(f"{self.full_width}x{calc_h}")

    def setup_mini_ticker(self):
        for w in self.mini_ticker_frame.winfo_children():
            w.destroy()
        self.pill_widgets.clear()

        targets = self.target_mgr.get_targets()
        for idx, t in enumerate(targets):
            tid = t["id"]
            box = tk.Frame(self.mini_ticker_frame, bg=COLOR_HEADER)
            box.pack(side=tk.LEFT, padx=3)
            box.bind("<Button-1>", self.on_drag_start)
            box.bind("<B1-Motion>", self.on_drag_motion)

            c = tk.Canvas(box, width=7, height=7, bg=COLOR_HEADER, highlightthickness=0)
            dot = c.create_oval(1, 1, 6, 6, fill=COLOR_MUTED, outline="")
            c.pack(side=tk.LEFT, padx=(0, 2))
            c.bind("<Button-1>", self.on_drag_start)
            c.bind("<B1-Motion>", self.on_drag_motion)

            short = t.get("short", t["name"][:4])
            lbl = tk.Label(box, text=f"{short}:--", bg=COLOR_HEADER, fg=COLOR_TEXT, font=("Segoe UI", 7))
            lbl.pack(side=tk.LEFT)
            lbl.bind("<Button-1>", self.on_drag_start)
            lbl.bind("<B1-Motion>", self.on_drag_motion)

            self.pill_widgets[tid] = {"dot": dot, "canvas": c, "lbl": lbl, "short": short}

            if idx < len(targets) - 1:
                sep = tk.Label(self.mini_ticker_frame, text="|", bg=COLOR_HEADER, fg=COLOR_BORDER, font=("Segoe UI", 7))
                sep.pack(side=tk.LEFT, padx=1)
                sep.bind("<Button-1>", self.on_drag_start)
                sep.bind("<B1-Motion>", self.on_drag_motion)

    def render_target_list(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        self.target_widgets.clear()

        targets = self.target_mgr.get_targets()
        for t in targets:
            tid = t["id"]
            row = tk.Frame(self.content_frame, bg=COLOR_CARD, bd=1, relief="solid")
            row.pack(fill=tk.X, pady=2, ipady=3)

            # Left dot
            canvas = tk.Canvas(row, width=10, height=10, bg=COLOR_CARD, highlightthickness=0)
            dot = canvas.create_oval(1, 1, 9, 9, fill=COLOR_MUTED, outline="")
            canvas.pack(side=tk.LEFT, padx=(8, 6))

            # Info block
            info_frame = tk.Frame(row, bg=COLOR_CARD)
            info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

            tier_tag = ""
            if tid == "lan":
                tier_tag = "[LAN] "
            elif t.get("tier") == "tier2":
                tier_tag = "[DNS] "

            name_lbl = tk.Label(
                info_frame, text=f"{tier_tag}{t['name']}", bg=COLOR_CARD, fg=COLOR_TEXT,
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
                font=("Segoe UI", 8, "bold")
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

        if not self.is_minimized:
            self.update_full_height()

    def delete_target(self, tid):
        if messagebox.askyesno("NetPulse", "Remove target from monitor?"):
            self.target_mgr.delete_target(tid)
            self.render_target_list()
            self.setup_mini_ticker()

    def open_add_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Target")
        dialog.attributes("-topmost", True)
        dialog.configure(bg=COLOR_BG)
        dialog.geometry("280x210+200+200")
        dialog.resizable(False, False)

        tk.Label(dialog, text="Add Target", bg=COLOR_BG, fg=COLOR_TEXT, font=("Segoe UI", 9, "bold")).pack(pady=(10, 4))

        tk.Label(dialog, text="Name:", bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=14)
        entry_name = tk.Entry(dialog, bg=COLOR_CARD, fg=COLOR_TEXT, insertbackground="white", bd=1)
        entry_name.pack(fill=tk.X, padx=14, pady=(1, 4))

        tk.Label(dialog, text="Domain / IP / URL:", bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=14)
        entry_host = tk.Entry(dialog, bg=COLOR_CARD, fg=COLOR_TEXT, insertbackground="white", bd=1)
        entry_host.pack(fill=tk.X, padx=14, pady=(1, 4))

        tk.Label(dialog, text="Type:", bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=14)
        type_var = tk.StringVar(value="web")
        combo = ttk.Combobox(dialog, textvariable=type_var, values=["web", "dns_ip"], state="readonly")
        combo.pack(fill=tk.X, padx=14, pady=(1, 10))

        def on_save():
            name = entry_name.get().strip()
            host = entry_host.get().strip()
            if not host:
                return
            self.target_mgr.add_target(name, host, target_type=type_var.get())
            dialog.destroy()
            self.render_target_list()
            self.setup_mini_ticker()

        btn_box = tk.Frame(dialog, bg=COLOR_BG)
        btn_box.pack(fill=tk.X, padx=14)
        tk.Button(btn_box, text="Cancel", bg=COLOR_CARD, fg=COLOR_TEXT, bd=0, padx=8, command=dialog.destroy).pack(side=tk.LEFT)
        tk.Button(btn_box, text="Save", bg=COLOR_ACCENT, fg="white", bd=0, padx=12, command=on_save).pack(side=tk.RIGHT)

    def background_poll_loop(self):
        while self.running:
            targets = self.target_mgr.get_targets()
            results = {}
            for t in targets:
                if not self.running:
                    break
                results[t["id"]] = probe_target(t)
                time.sleep(0.08)

            if self.running:
                self.root.after(0, lambda r=results: self.update_probe_ui(r))

            time.sleep(3.5)

    def update_probe_ui(self, results):
        has_error = False
        has_slow = False

        for tid, res in results.items():
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

            # Full view update
            if tid in self.target_widgets:
                w = self.target_widgets[tid]
                w["canvas"].itemconfig(w["dot"], fill=color)
                w["lat_lbl"].config(text=text, fg=color)
                w["detail_lbl"].config(text=res.get("detail", ""))

            # Minimized view update
            if tid in self.pill_widgets:
                pw = self.pill_widgets[tid]
                pw["canvas"].itemconfig(pw["dot"], fill=color)
                pw["lbl"].config(text=f"{pw['short']}:{text}", fg=color if status != 'ok' else COLOR_TEXT)

        if has_error:
            self.pulse_canvas.itemconfig(self.pulse_circle, fill=COLOR_RED)
        elif has_slow:
            self.pulse_canvas.itemconfig(self.pulse_circle, fill=COLOR_YELLOW)
        else:
            self.pulse_canvas.itemconfig(self.pulse_circle, fill=COLOR_GREEN)

    def close_app(self):
        self.running = False
        self.root.destroy()


def main():
    log("Starting NetPulse Desktop HUD main()")
    try:
        root = tk.Tk()
        app = DesktopOverlayHUD(root)
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
