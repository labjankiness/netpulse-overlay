#!/usr/bin/env python3
"""
NetPulse Desktop System Overlay
A real-time, always-on-top, 3-tier network stability overlay HUD written in pure Python (Tkinter).
Guaranteed persistent desktop presence - never hides behind Firefox or full-screen apps.
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
        "desc": "Local Wi-Fi / Router Link",
        "host": GATEWAY_IP,
        "type": "dns_ip",
        "tier": "Tier 1: LAN",
        "deletable": False
    },
    {
        "id": "cf_dns",
        "name": "Cloudflare DNS",
        "desc": "Primary Name Resolution",
        "host": "1.1.1.1",
        "port": 53,
        "type": "dns_ip",
        "tier": "Tier 2: DNS",
        "deletable": False
    },
    {
        "id": "google_dns",
        "name": "Google DNS",
        "desc": "Backup Name Resolution",
        "host": "8.8.8.8",
        "port": 53,
        "type": "dns_ip",
        "tier": "Tier 2: DNS",
        "deletable": False
    },
    {
        "id": "ddg",
        "name": "DuckDuckGo",
        "desc": "Search Engine Endpoint",
        "host": "duckduckgo.com",
        "url": "https://duckduckgo.com",
        "type": "web",
        "tier": "Tier 3: Web",
        "deletable": False
    },
    {
        "id": "github",
        "name": "GitHub (Baseline)",
        "desc": "Global Internet Reachability",
        "host": "github.com",
        "url": "https://github.com",
        "type": "web",
        "tier": "Tier 3: Web",
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

            new_target = {
                "id": tid,
                "name": name.strip() or clean_host,
                "desc": "Custom Target",
                "host": clean_host,
                "type": target_type,
                "tier": "Tier 3: Web",
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

# Networking checks
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


class NetPulseOverlayApp:
    def __init__(self, root):
        self.root = root
        self.target_mgr = TargetManager(CONFIG_FILE)
        self.running = True
        self.target_widgets = {}

        # Guaranteed-visible Windows Top-Level Window
        self.root.title("NetPulse Overlay - 24/7 Monitor")
        self.root.attributes("-topmost", True)      # Floats on top of Firefox and games
        self.root.configure(bg=COLOR_BG)

        # Compact, sleek HUD window geometry (width 360, height 260)
        self.root.geometry("360x260+100+100")
        self.root.minsize(320, 220)

        self.setup_ui()

        # Bring forward & register in taskbar
        self.root.update_idletasks()
        self.root.lift()
        self.root.focus_force()

        # Polling thread
        self.poll_thread = threading.Thread(target=self.background_poll_loop, daemon=True)
        self.poll_thread.start()
        log("NetPulse persistent top-level HUD initialized")

    def setup_ui(self):
        # Header Toolbar
        self.header = tk.Frame(self.root, bg=COLOR_HEADER, height=34)
        self.header.pack(fill=tk.X, side=tk.TOP)
        self.header.pack_propagate(False)

        # Pulse circle
        self.pulse_canvas = tk.Canvas(self.header, width=12, height=12, bg=COLOR_HEADER, highlightthickness=0)
        self.pulse_circle = self.pulse_canvas.create_oval(1, 1, 11, 11, fill=COLOR_GREEN, outline="")
        self.pulse_canvas.pack(side=tk.LEFT, padx=(10, 6))

        # Title
        self.title_lbl = tk.Label(
            self.header, text="NetPulse 3-Tier Monitor", bg=COLOR_HEADER, fg=COLOR_TEXT,
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

        # Container for target cards
        self.content_frame = tk.Frame(self.root, bg=COLOR_BG)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # Bottom status bar
        self.status_bar = tk.Label(
            self.root, text=f"Gateway: {GATEWAY_IP} | Always-on-top | 24/7 Live",
            bg=COLOR_HEADER, fg=COLOR_MUTED, font=("Segoe UI", 7), anchor="w", padx=10, pady=3
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.render_target_list()

    def render_target_list(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        self.target_widgets.clear()

        targets = self.target_mgr.get_targets()
        for t in targets:
            tid = t["id"]
            row = tk.Frame(self.content_frame, bg=COLOR_CARD, bd=1, relief="solid")
            row.pack(fill=tk.X, pady=2, ipady=2)

            # Left status dot
            canvas = tk.Canvas(row, width=10, height=10, bg=COLOR_CARD, highlightthickness=0)
            dot = canvas.create_oval(1, 1, 9, 9, fill=COLOR_MUTED, outline="")
            canvas.pack(side=tk.LEFT, padx=(8, 6))

            # Info block
            info_frame = tk.Frame(row, bg=COLOR_CARD)
            info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

            tier_tag = ""
            if tid == "lan":
                tier_tag = "[LAN] "
            elif t.get("tier") == "Tier 2: DNS":
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

        # Dynamic window height adjustment
        calc_height = 34 + (len(targets) * 38) + 24
        self.root.geometry(f"{self.root.winfo_width()}x{calc_height}")

    def delete_target(self, tid):
        if messagebox.askyesno("NetPulse", "Remove target from monitor?"):
            self.target_mgr.delete_target(tid)
            self.render_target_list()

    def open_add_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Monitoring Target")
        dialog.attributes("-topmost", True)
        dialog.configure(bg=COLOR_BG)
        dialog.geometry("280x210+150+150")
        dialog.resizable(False, False)

        tk.Label(dialog, text="Add Target", bg=COLOR_BG, fg=COLOR_TEXT, font=("Segoe UI", 9, "bold")).pack(pady=(10, 4))

        tk.Label(dialog, text="Display Name:", bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=14)
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
    log("Starting NetPulse Overlay main()")
    try:
        root = tk.Tk()
        app = NetPulseOverlayApp(root)
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
