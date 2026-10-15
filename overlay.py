#!/usr/bin/env python3
"""
NetPulse Desktop System Overlay
A frameless, draggable HUD with live 3-tier network stability monitoring.
Features:
- Downdetector-style live spike & stability timeline graphs
- Pin / Unpin (Always-on-top toggle)
- Translucency / Opacity toggle (Solid, Translucent, Glass)
- 1-Click Minimize / Expand Ticker Pill
- Right-click customization menu
- Settings persistence
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
SETTINGS_FILE = os.path.join(APP_DIR, 'settings.json')
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

OPACITY_LEVELS = [0.85, 0.65, 1.0]
OPACITY_LABELS = {0.85: "Translucent (85%)", 0.65: "Glass (65%)", 1.0: "Solid (100%)"}

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
COLOR_GRAPH_BG = "#0d1322"

class TargetManager:
    def __init__(self, filepath):
        self.filepath = filepath
        self.lock = threading.Lock()
        self.targets = []
        self.history = {}  # tid -> list of {'latency': int, 'status': str}
        self.total_spikes = 0
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
                if tid in self.history:
                    del self.history[tid]
                return True
        return False

    def record_probe(self, tid, status, latency):
        with self.lock:
            if tid not in self.history:
                self.history[tid] = []
            self.history[tid].append({"status": status, "latency": latency})
            if len(self.history[tid]) > 25:
                self.history[tid].pop(0)

            if status in ("timeout", "error"):
                self.total_spikes += 1

    def get_history(self, tid):
        with self.lock:
            return list(self.history.get(tid, []))

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

        self.load_settings()

        # Window settings
        self.root.title("NetPulse Overlay")
        self.root.overrideredirect(True)          # Frameless HUD
        self.apply_pin_state()
        self.apply_opacity()
        self.root.configure(bg=COLOR_BORDER)

        # Default size and position
        self.full_width = 350
        self.mini_width = 480
        self.mini_height = 34

        self.root.geometry(f"{self.full_width}x320+{self.win_x}+{self.win_y}")

        self.drag_x = 0
        self.drag_y = 0

        self.setup_ui()
        self.setup_context_menu()

        self.root.update_idletasks()
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        if not self.is_pinned:
            self.root.after(800, lambda: self.root.attributes("-topmost", False))

        # Polling thread
        self.poll_thread = threading.Thread(target=self.background_poll_loop, daemon=True)
        self.poll_thread.start()
        log("NetPulse Desktop HUD initialized with Downdetector-style spike graphs")

    def load_settings(self):
        self.is_pinned = True
        self.opacity_index = 0
        self.win_x = 180
        self.win_y = 120
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.is_pinned = data.get("pinned", True)
                    op = data.get("opacity", 0.85)
                    if op in OPACITY_LEVELS:
                        self.opacity_index = OPACITY_LEVELS.index(op)
                    self.win_x = int(data.get("x", 180))
                    self.win_y = int(data.get("y", 120))
            except Exception as e:
                log(f"Settings load error: {e}")

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "pinned": self.is_pinned,
                    "opacity": OPACITY_LEVELS[self.opacity_index],
                    "x": self.win_x,
                    "y": self.win_y
                }, f, indent=2)
        except Exception as e:
            log(f"Settings save error: {e}")

    def apply_pin_state(self):
        self.root.attributes("-topmost", self.is_pinned)

    def apply_opacity(self):
        alpha = OPACITY_LEVELS[self.opacity_index]
        try:
            self.root.attributes("-alpha", alpha)
        except Exception:
            pass

    def toggle_pin(self):
        self.is_pinned = not self.is_pinned
        self.apply_pin_state()
        self.save_settings()
        self.update_pin_buttons()

    def toggle_opacity(self):
        self.opacity_index = (self.opacity_index + 1) % len(OPACITY_LEVELS)
        self.apply_opacity()
        self.save_settings()

    def update_pin_buttons(self):
        pin_char = "📌" if self.is_pinned else "📍"
        pin_color = COLOR_ACCENT if self.is_pinned else COLOR_MUTED
        if hasattr(self, 'btn_pin_full'):
            self.btn_pin_full.config(text=pin_char, fg=pin_color)

    def setup_ui(self):
        self.container = tk.Frame(self.root, bg=COLOR_BG, bd=0)
        self.container.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Header Bar (Draggable)
        self.header = tk.Frame(self.container, bg=COLOR_HEADER, height=32)
        self.header.pack(fill=tk.X, side=tk.TOP)
        self.header.pack_propagate(False)

        self.header.bind("<Button-1>", self.on_drag_start)
        self.header.bind("<B1-Motion>", self.on_drag_motion)
        self.header.bind("<ButtonRelease-1>", self.on_drag_end)
        self.header.bind("<Button-3>", self.show_context_menu)

        # Pulse indicator
        self.pulse_canvas = tk.Canvas(self.header, width=12, height=12, bg=COLOR_HEADER, highlightthickness=0)
        self.pulse_circle = self.pulse_canvas.create_oval(2, 2, 10, 10, fill=COLOR_GREEN, outline="")
        self.pulse_canvas.pack(side=tk.LEFT, padx=(8, 4))
        self.pulse_canvas.bind("<Button-1>", self.on_drag_start)
        self.pulse_canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.pulse_canvas.bind("<ButtonRelease-1>", self.on_drag_end)

        # Title
        self.title_lbl = tk.Label(
            self.header, text="NetPulse Overlay", bg=COLOR_HEADER, fg=COLOR_TEXT,
            font=("Segoe UI", 9, "bold")
        )
        self.title_lbl.pack(side=tk.LEFT)
        self.title_lbl.bind("<Button-1>", self.on_drag_start)
        self.title_lbl.bind("<B1-Motion>", self.on_drag_motion)
        self.title_lbl.bind("<ButtonRelease-1>", self.on_drag_end)

        # Compact Ticker Area (visible only when minimized)
        self.mini_ticker_frame = tk.Frame(self.header, bg=COLOR_HEADER)
        self.mini_ticker_frame.bind("<Button-1>", self.on_drag_start)
        self.mini_ticker_frame.bind("<B1-Motion>", self.on_drag_motion)
        self.mini_ticker_frame.bind("<ButtonRelease-1>", self.on_drag_end)

        # Controls
        self.btn_close = tk.Label(
            self.header, text="✕", bg=COLOR_HEADER, fg=COLOR_MUTED,
            font=("Segoe UI", 9), cursor="hand2", width=2
        )
        self.btn_close.pack(side=tk.RIGHT, padx=(0, 4))
        self.btn_close.bind("<Button-1>", lambda e: self.close_app())
        self.btn_close.bind("<Enter>", lambda e: self.btn_close.config(fg=COLOR_RED))
        self.btn_close.bind("<Leave>", lambda e: self.btn_close.config(fg=COLOR_MUTED))

        self.btn_minimize = tk.Label(
            self.header, text="─", bg=COLOR_HEADER, fg=COLOR_MUTED,
            font=("Segoe UI", 10, "bold"), cursor="hand2", width=2
        )
        self.btn_minimize.pack(side=tk.RIGHT, padx=1)
        self.btn_minimize.bind("<Button-1>", lambda e: self.toggle_minimize())
        self.btn_minimize.bind("<Enter>", lambda e: self.btn_minimize.config(fg=COLOR_TEXT))
        self.btn_minimize.bind("<Leave>", lambda e: self.btn_minimize.config(fg=COLOR_MUTED))

        pin_char = "📌" if self.is_pinned else "📍"
        pin_color = COLOR_ACCENT if self.is_pinned else COLOR_MUTED
        self.btn_pin_full = tk.Label(
            self.header, text=pin_char, bg=COLOR_HEADER, fg=pin_color,
            font=("Segoe UI", 9), cursor="hand2", width=2
        )
        self.btn_pin_full.pack(side=tk.RIGHT, padx=1)
        self.btn_pin_full.bind("<Button-1>", lambda e: self.toggle_pin())
        self.btn_pin_full.bind("<Enter>", lambda e: self.btn_pin_full.config(fg=COLOR_ACCENT))

        self.btn_trans_full = tk.Label(
            self.header, text="🌓", bg=COLOR_HEADER, fg=COLOR_MUTED,
            font=("Segoe UI", 9), cursor="hand2", width=2
        )
        self.btn_trans_full.pack(side=tk.RIGHT, padx=1)
        self.btn_trans_full.bind("<Button-1>", lambda e: self.toggle_opacity())
        self.btn_trans_full.bind("<Enter>", lambda e: self.btn_trans_full.config(fg=COLOR_TEXT))
        self.btn_trans_full.bind("<Leave>", lambda e: self.btn_trans_full.config(fg=COLOR_MUTED))

        self.btn_add = tk.Label(
            self.header, text="+", bg=COLOR_HEADER, fg=COLOR_MUTED,
            font=("Segoe UI", 10, "bold"), cursor="hand2", width=2
        )
        self.btn_add.pack(side=tk.RIGHT, padx=1)
        self.btn_add.bind("<Button-1>", lambda e: self.open_add_dialog())
        self.btn_add.bind("<Enter>", lambda e: self.btn_add.config(fg=COLOR_ACCENT))
        self.btn_add.bind("<Leave>", lambda e: self.btn_add.config(fg=COLOR_MUTED))

        # Content frame for full view cards
        self.content_frame = tk.Frame(self.container, bg=COLOR_BG)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        self.content_frame.bind("<Button-3>", self.show_context_menu)

        # Global Spike / Outage Timeline (Downdetector style)
        self.timeline_frame = tk.Frame(self.content_frame, bg=COLOR_CARD, bd=1, relief="solid")
        self.timeline_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(6, 2))
        self.timeline_frame.bind("<Button-3>", self.show_context_menu)

        self.timeline_header = tk.Frame(self.timeline_frame, bg=COLOR_CARD)
        self.timeline_header.pack(fill=tk.X, padx=6, pady=(4, 2))

        self.timeline_title = tk.Label(
            self.timeline_header, text="OUTAGE & SPIKE TIMELINE (LAST 25 CHECKS)",
            bg=COLOR_CARD, fg=COLOR_MUTED, font=("Segoe UI", 7, "bold")
        )
        self.timeline_title.pack(side=tk.LEFT)

        self.spike_stat_lbl = tk.Label(
            self.timeline_header, text="0 Spikes Detected",
            bg=COLOR_CARD, fg=COLOR_GREEN, font=("Segoe UI", 7, "bold")
        )
        self.spike_stat_lbl.pack(side=tk.RIGHT)

        # Downdetector-style spike timeline canvas
        self.timeline_canvas = tk.Canvas(
            self.timeline_frame, height=28, bg=COLOR_GRAPH_BG, highlightthickness=0
        )
        self.timeline_canvas.pack(fill=tk.X, padx=6, pady=(0, 4))
        self.timeline_canvas.bind("<Button-3>", self.show_context_menu)

        # Cards container
        self.cards_frame = tk.Frame(self.content_frame, bg=COLOR_BG)
        self.cards_frame.pack(fill=tk.BOTH, expand=True)
        self.cards_frame.bind("<Button-3>", self.show_context_menu)

        self.render_target_list()
        self.setup_mini_ticker()

    def setup_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0, bg=COLOR_CARD, fg=COLOR_TEXT, activebackground=COLOR_ACCENT, activeforeground="white")
        self.context_menu.add_command(label="📌 Toggle Pin (Always On Top)", command=self.toggle_pin)
        self.context_menu.add_command(label="🌓 Cycle Translucency", command=self.toggle_opacity)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="➕ Add New Target...", command=self.open_add_dialog)
        self.context_menu.add_command(label="─ Minimize / Expand", command=self.toggle_minimize)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="✕ Close Overlay", command=self.close_app)

    def show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def on_drag_start(self, event):
        self.drag_x = event.x_root - self.root.winfo_x()
        self.drag_y = event.y_root - self.root.winfo_y()

    def on_drag_motion(self, event):
        x = event.x_root - self.drag_x
        y = event.y_root - self.drag_y
        self.win_x = x
        self.win_y = y
        self.root.geometry(f"+{x}+{y}")

    def on_drag_end(self, event):
        self.save_settings()

    def toggle_minimize(self):
        self.is_minimized = not self.is_minimized
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        if x <= 0 and y <= 0:
            x, y = self.win_x, self.win_y

        if self.is_minimized:
            self.btn_minimize.config(text="□")
            self.title_lbl.pack_forget()
            self.content_frame.pack_forget()
            self.mini_ticker_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 6))
            self.root.geometry(f"{self.mini_width}x{self.mini_height}+{x}+{y}")
        else:
            self.btn_minimize.config(text="─")
            self.mini_ticker_frame.pack_forget()
            self.title_lbl.pack(side=tk.LEFT)
            self.content_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
            self.update_full_height()

        if self.is_pinned:
            self.root.lift()

    def update_full_height(self):
        targets = self.target_mgr.get_targets()
        calc_h = 36 + (len(targets) * 38) + 64
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        if x <= 0 and y <= 0:
            x, y = self.win_x, self.win_y
        self.root.geometry(f"{self.full_width}x{calc_h}+{x}+{y}")

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
            box.bind("<Button-3>", self.show_context_menu)

            c = tk.Canvas(box, width=7, height=7, bg=COLOR_HEADER, highlightthickness=0)
            dot = c.create_oval(1, 1, 6, 6, fill=COLOR_MUTED, outline="")
            c.pack(side=tk.LEFT, padx=(0, 2))
            c.bind("<Button-1>", self.on_drag_start)
            c.bind("<B1-Motion>", self.on_drag_motion)
            c.bind("<Button-3>", self.show_context_menu)

            short = t.get("short", t["name"][:4])
            lbl = tk.Label(box, text=f"{short}:--", bg=COLOR_HEADER, fg=COLOR_TEXT, font=("Segoe UI", 7))
            lbl.pack(side=tk.LEFT)
            lbl.bind("<Button-1>", self.on_drag_start)
            lbl.bind("<B1-Motion>", self.on_drag_motion)
            lbl.bind("<Button-3>", self.show_context_menu)

            self.pill_widgets[tid] = {"dot": dot, "canvas": c, "lbl": lbl, "short": short}

            if idx < len(targets) - 1:
                sep = tk.Label(self.mini_ticker_frame, text="|", bg=COLOR_HEADER, fg=COLOR_BORDER, font=("Segoe UI", 7))
                sep.pack(side=tk.LEFT, padx=1)
                sep.bind("<Button-1>", self.on_drag_start)
                sep.bind("<B1-Motion>", self.on_drag_motion)
                sep.bind("<Button-3>", self.show_context_menu)

    def render_target_list(self):
        for widget in self.cards_frame.winfo_children():
            widget.destroy()
        self.target_widgets.clear()

        targets = self.target_mgr.get_targets()
        for t in targets:
            tid = t["id"]
            row = tk.Frame(self.cards_frame, bg=COLOR_CARD, bd=1, relief="solid")
            row.pack(fill=tk.X, pady=2, ipady=2)
            row.bind("<Button-3>", self.show_context_menu)

            # Status dot
            canvas = tk.Canvas(row, width=10, height=10, bg=COLOR_CARD, highlightthickness=0)
            dot = canvas.create_oval(1, 1, 9, 9, fill=COLOR_MUTED, outline="")
            canvas.pack(side=tk.LEFT, padx=(6, 4))

            # Info block
            info_frame = tk.Frame(row, bg=COLOR_CARD)
            info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
            info_frame.bind("<Button-3>", self.show_context_menu)

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

            # Mini sparkline canvas (Downdetector style)
            spark_canvas = tk.Canvas(row, width=64, height=18, bg=COLOR_GRAPH_BG, highlightthickness=0)
            spark_canvas.pack(side=tk.LEFT, padx=(4, 6))

            # Right metrics
            right_frame = tk.Frame(row, bg=COLOR_CARD)
            right_frame.pack(side=tk.RIGHT, padx=(2, 6))

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
                del_btn.pack(side=tk.RIGHT, padx=(0, 4))
                del_btn.bind("<Button-1>", lambda e, target_id=tid: self.delete_target(target_id))
                del_btn.bind("<Enter>", lambda e, b=del_btn: b.config(fg=COLOR_RED))
                del_btn.bind("<Leave>", lambda e, b=del_btn: b.config(fg=COLOR_MUTED))

            self.target_widgets[tid] = {
                "canvas": canvas,
                "dot": dot,
                "spark_canvas": spark_canvas,
                "lat_lbl": lat_lbl,
                "detail_lbl": detail_lbl,
                "row": row
            }

        if not self.is_minimized:
            self.update_full_height()

    def draw_sparkline(self, canvas, history):
        canvas.delete("all")
        if not history:
            return

        w = canvas.winfo_width() or 64
        h = canvas.winfo_height() or 18
        bar_w = max(2, w / 25)

        for i, item in enumerate(history[-25:]):
            x0 = i * bar_w
            x1 = x0 + bar_w - 1
            status = item.get("status")
            lat = item.get("latency")

            if status in ("timeout", "error"):
                # Downdetector-style RED OUTAGE SPIKE (reaches top)
                canvas.create_rectangle(x0, 1, x1, h, fill=COLOR_RED, outline="")
            else:
                lat_val = lat if lat is not None else 10
                bar_h = max(2, min(h - 2, int((lat_val / 150) * (h - 2))))
                y0 = h - bar_h
                color = COLOR_GREEN if lat_val < 80 else COLOR_YELLOW
                canvas.create_rectangle(x0, y0, x1, h, fill=color, outline="")

    def draw_aggregate_timeline(self):
        canvas = self.timeline_canvas
        canvas.delete("all")

        w = canvas.winfo_width() or 300
        h = canvas.winfo_height() or 28

        # Draw baseline indicator line
        canvas.create_line(0, h - 6, w, h - 6, fill="#1c2842", dash=(2, 2))

        targets = self.target_mgr.get_targets()
        bar_w = max(4, w / 25)
        any_spike_in_window = 0

        for col in range(25):
            x0 = col * bar_w
            x1 = x0 + bar_w - 1

            # Aggregate status across all targets for this time column
            col_has_timeout = False
            col_max_lat = 0

            for t in targets:
                hist = self.target_mgr.get_history(t["id"])
                idx = len(hist) - 25 + col
                if 0 <= idx < len(hist):
                    item = hist[idx]
                    if item.get("status") in ("timeout", "error"):
                        col_has_timeout = True
                    lat = item.get("latency") or 0
                    if lat > col_max_lat:
                        col_max_lat = lat

            if col_has_timeout:
                # Big Downdetector spike bar
                canvas.create_rectangle(x0, 2, x1, h, fill=COLOR_RED, outline="")
                any_spike_in_window += 1
            elif col_max_lat > 0:
                bar_h = max(3, min(h - 4, int((col_max_lat / 120) * (h - 4))))
                y0 = h - bar_h
                color = COLOR_GREEN if col_max_lat < 70 else COLOR_YELLOW
                canvas.create_rectangle(x0, y0, x1, h, fill=color, outline="")
            else:
                canvas.create_rectangle(x0, h - 3, x1, h, fill="#1f293d", outline="")

        total_spikes = self.target_mgr.total_spikes
        if total_spikes > 0:
            self.spike_stat_lbl.config(text=f"{total_spikes} Total Spikes", fg=COLOR_RED)
        else:
            self.spike_stat_lbl.config(text="100% Stable (0 Spikes)", fg=COLOR_GREEN)

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
                res = probe_target(t)
                results[t["id"]] = res
                self.target_mgr.record_probe(t["id"], res["status"], res["latency"])
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

            # Full view card update
            if tid in self.target_widgets:
                w = self.target_widgets[tid]
                w["canvas"].itemconfig(w["dot"], fill=color)
                w["lat_lbl"].config(text=text, fg=color)
                w["detail_lbl"].config(text=res.get("detail", ""))
                # Draw sparkline
                hist = self.target_mgr.get_history(tid)
                self.draw_sparkline(w["spark_canvas"], hist)

            # Minimized view update
            if tid in self.pill_widgets:
                pw = self.pill_widgets[tid]
                pw["canvas"].itemconfig(pw["dot"], fill=color)
                pw["lbl"].config(text=f"{pw['short']}:{text}", fg=color if status != 'ok' else COLOR_TEXT)

        # Update Aggregate Timeline
        if not self.is_minimized:
            self.draw_aggregate_timeline()

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
    log("Starting NetPulse Desktop HUD main() with Downdetector graphs")
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
