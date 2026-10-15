#!/usr/bin/env python3
"""
NetPulse Desktop System Overlay
A frameless, draggable, always-on-top system overlay HUD written in pure Python (Tkinter).
Runs natively on your desktop without needing a web browser.
"""

import os
import sys
import json
import time
import socket
import threading
import urllib.request
import urllib.parse
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'targets.json')

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
COLOR_BG = "#0d111a"
COLOR_HEADER = "#151c2c"
COLOR_CARD = "#121824"
COLOR_BORDER = "#253046"
COLOR_TEXT = "#f1f5f9"
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
                    print(f"Error loading {self.filepath}: {e}")
            self.targets = [dict(t) for t in DEFAULT_TARGETS]
            self.save_unlocked()

    def save(self):
        with self.lock:
            self.save_unlocked()

    def save_unlocked(self):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.targets, f, indent=2)
        except Exception as e:
            print(f"Error saving {self.filepath}: {e}")

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

# Networking helpers
def check_dns(host):
    t0 = time.time()
    try:
        ip = socket.gethostbyname(host)
        return {"status": "ok", "time": round((time.time() - t0) * 1000), "ip": ip}
    except Exception as e:
        return {"status": "error", "time": round((time.time() - t0) * 1000), "error": str(e)}

def check_tcp(host, port, timeout_sec=2.5):
    t0 = time.time()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout_sec)
    try:
        s.connect((host, port))
        s.close()
        return {"status": "ok", "time": round((time.time() - t0) * 1000)}
    except socket.timeout:
        s.close()
        return {"status": "timeout", "time": round(timeout_sec * 1000), "error": "Timeout"}
    except Exception as e:
        s.close()
        return {"status": "error", "time": round((time.time() - t0) * 1000), "error": str(e)}

def check_http(url, timeout_sec=3.0):
    t0 = time.time()
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NetPulseOverlay/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            dur = round((time.time() - t0) * 1000)
            return {"status": "ok" if resp.status < 400 else "warn", "time": dur, "code": resp.status}
    except urllib.error.HTTPError as e:
        return {"status": "warn", "time": round((time.time() - t0) * 1000), "code": e.code}
    except urllib.error.URLError as e:
        if isinstance(e.reason, socket.timeout):
            return {"status": "timeout", "time": round(timeout_sec * 1000), "error": "Timeout"}
        return {"status": "error", "time": round((time.time() - t0) * 1000), "error": str(e.reason)}
    except Exception as e:
        return {"status": "error", "time": round((time.time() - t0) * 1000), "error": str(e)}

def probe_target(target):
    t_type = target.get("type", "web")
    if t_type in ("web", "api"):
        dns_res = check_dns(target["host"])
        if dns_res["status"] == "error":
            return {"status": "error", "latency": dns_res["time"], "detail": "DNS Failure"}
        http_url = target.get("url", f"https://{target['host']}")
        http_res = check_http(http_url)
        lat = http_res["time"]
        if http_res["status"] == "timeout":
            return {"status": "timeout", "latency": lat, "detail": "Timeout"}
        elif http_res["status"] == "error":
            return {"status": "error", "latency": lat, "detail": http_res.get("error", "Error")[:16]}
        else:
            status = "slow" if lat > 250 else "ok"
            return {"status": status, "latency": lat, "detail": f"HTTP {http_res['code']}"}
    elif t_type == "dns_ip":
        port = target.get("port", 53)
        tcp_res = check_tcp(target["host"], port)
        lat = tcp_res["time"]
        if tcp_res["status"] == "timeout":
            return {"status": "timeout", "latency": lat, "detail": "Timeout"}
        elif tcp_res["status"] == "error":
            return {"status": "error", "latency": lat, "detail": "Conn Refused"}
        else:
            status = "slow" if lat > 180 else "ok"
            return {"status": status, "latency": lat, "detail": f"{port}/TCP"}
    return {"status": "ok", "latency": 0, "detail": "OK"}


class DesktopOverlayApp:
    def __init__(self, root):
        self.root = root
        self.target_mgr = TargetManager(CONFIG_FILE)
        self.is_compact = False
        self.running = True
        self.target_results = {}  # tid -> probe dict
        self.target_widgets = {}  # tid -> dict of widgets

        # Window settings for real system overlay
        self.root.title("NetPulse System Overlay")
        self.root.overrideredirect(True)          # Frameless overlay
        self.root.attributes("-topmost", True)      # Always on top of all windows
        try:
            self.root.attributes("-alpha", 0.93)    # Modern glass semi-transparency
        except Exception:
            pass
        self.root.configure(bg=COLOR_BORDER)

        # Position top-right corner of screen by default
        screen_w = self.root.winfo_screenwidth()
        overlay_w = 280
        overlay_h = 240
        x_pos = max(20, screen_w - overlay_w - 30)
        y_pos = 40
        self.root.geometry(f"{overlay_w}x{overlay_h}+{x_pos}+{y_pos}")

        # Dragging variables
        self.drag_x = 0
        self.drag_y = 0

        self.setup_ui()

        # Start background polling thread
        self.poll_thread = threading.Thread(target=self.background_poll_loop, daemon=True)
        self.poll_thread.start()

    def setup_ui(self):
        # Outer container with sleek border
        self.main_frame = tk.Frame(self.root, bg=COLOR_BG, bd=0)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Top Header Bar (Draggable handle)
        self.header = tk.Frame(self.main_frame, bg=COLOR_HEADER, height=32)
        self.header.pack(fill=tk.X, side=tk.TOP)
        self.header.pack_propagate(False)

        # Enable dragging anywhere on the header
        self.header.bind("<Button-1>", self.on_drag_start)
        self.header.bind("<B1-Motion>", self.on_drag_motion)

        # Status pulse icon
        self.pulse_canvas = tk.Canvas(self.header, width=12, height=12, bg=COLOR_HEADER, highlightthickness=0)
        self.pulse_circle = self.pulse_canvas.create_oval(2, 2, 10, 10, fill=COLOR_GREEN, outline="")
        self.pulse_canvas.pack(side=tk.LEFT, padx=(10, 6))
        self.pulse_canvas.bind("<Button-1>", self.on_drag_start)
        self.pulse_canvas.bind("<B1-Motion>", self.on_drag_motion)

        # Title
        self.title_label = tk.Label(
            self.header, text="NetPulse Overlay", bg=COLOR_HEADER, fg=COLOR_TEXT,
            font=("Segoe UI", 9, "bold")
        )
        self.title_label.pack(side=tk.LEFT)
        self.title_label.bind("<Button-1>", self.on_drag_start)
        self.title_label.bind("<B1-Motion>", self.on_drag_motion)

        # Window Controls: Add (+), Compact (_), Close (X)
        self.btn_close = tk.Label(
            self.header, text="✕", bg=COLOR_HEADER, fg=COLOR_MUTED,
            font=("Segoe UI", 9), cursor="hand2", width=3
        )
        self.btn_close.pack(side=tk.RIGHT, padx=2)
        self.btn_close.bind("<Button-1>", lambda e: self.close_app())
        self.btn_close.bind("<Enter>", lambda e: self.btn_close.config(fg=COLOR_RED))
        self.btn_close.bind("<Leave>", lambda e: self.btn_close.config(fg=COLOR_MUTED))

        self.btn_compact = tk.Label(
            self.header, text="─", bg=COLOR_HEADER, fg=COLOR_MUTED,
            font=("Segoe UI", 9), cursor="hand2", width=3
        )
        self.btn_compact.pack(side=tk.RIGHT, padx=2)
        self.btn_compact.bind("<Button-1>", lambda e: self.toggle_compact())
        self.btn_compact.bind("<Enter>", lambda e: self.btn_compact.config(fg=COLOR_TEXT))
        self.btn_compact.bind("<Leave>", lambda e: self.btn_compact.config(fg=COLOR_MUTED))

        self.btn_add = tk.Label(
            self.header, text="+", bg=COLOR_HEADER, fg=COLOR_MUTED,
            font=("Segoe UI", 11, "bold"), cursor="hand2", width=3
        )
        self.btn_add.pack(side=tk.RIGHT, padx=2)
        self.btn_add.bind("<Button-1>", lambda e: self.open_add_dialog())
        self.btn_add.bind("<Enter>", lambda e: self.btn_add.config(fg=COLOR_ACCENT))
        self.btn_add.bind("<Leave>", lambda e: self.btn_add.config(fg=COLOR_MUTED))

        # Targets container
        self.content_frame = tk.Frame(self.main_frame, bg=COLOR_BG)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.render_target_list()

    def on_drag_start(self, event):
        self.drag_x = event.x
        self.drag_y = event.y

    def on_drag_motion(self, event):
        x = self.root.winfo_x() + (event.x - self.drag_x)
        y = self.root.winfo_y() + (event.y - self.drag_y)
        self.root.geometry(f"+{x}+{y}")

    def toggle_compact(self):
        self.is_compact = not self.is_compact
        if self.is_compact:
            self.content_frame.pack_forget()
            self.root.geometry(f"{self.root.winfo_width()}x32")
            self.btn_compact.config(text="□")
        else:
            self.content_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
            self.update_window_height()
            self.btn_compact.config(text="─")

    def update_window_height(self):
        if not self.is_compact:
            targets = self.target_mgr.get_targets()
            calculated_height = 36 + (len(targets) * 36) + 16
            self.root.geometry(f"{self.root.winfo_width()}x{calculated_height}")

    def render_target_list(self):
        # Clear existing widgets
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        self.target_widgets.clear()

        targets = self.target_mgr.get_targets()
        for t in targets:
            tid = t["id"]
            row = tk.Frame(self.content_frame, bg=COLOR_CARD, bd=0)
            row.pack(fill=tk.X, pady=2, ipady=4)

            # Left indicator dot
            canvas = tk.Canvas(row, width=10, height=10, bg=COLOR_CARD, highlightthickness=0)
            dot = canvas.create_oval(1, 1, 9, 9, fill=COLOR_MUTED, outline="")
            canvas.pack(side=tk.LEFT, padx=(8, 8))

            # Target Name
            name_lbl = tk.Label(
                row, text=t["name"], bg=COLOR_CARD, fg=COLOR_TEXT,
                font=("Segoe UI", 8, "bold"), anchor="w"
            )
            name_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

            # Right actions / metrics
            right_box = tk.Frame(row, bg=COLOR_CARD)
            right_box.pack(side=tk.RIGHT, padx=(4, 8))

            lat_lbl = tk.Label(
                right_box, text="--ms", bg=COLOR_CARD, fg=COLOR_MUTED,
                font=("Segoe UI", 8, "bold")
            )
            lat_lbl.pack(side=tk.RIGHT)

            # Delete button for custom targets
            if t.get("deletable", False):
                del_btn = tk.Label(
                    right_box, text="×", bg=COLOR_CARD, fg=COLOR_MUTED,
                    font=("Segoe UI", 9), cursor="hand2"
                )
                del_btn.pack(side=tk.RIGHT, padx=(0, 6))
                del_btn.bind("<Button-1>", lambda e, target_id=tid: self.delete_target(target_id))
                del_btn.bind("<Enter>", lambda e, b=del_btn: b.config(fg=COLOR_RED))
                del_btn.bind("<Leave>", lambda e, b=del_btn: b.config(fg=COLOR_MUTED))

            self.target_widgets[tid] = {
                "canvas": canvas,
                "dot": dot,
                "lat_lbl": lat_lbl,
                "row": row
            }

        self.update_window_height()

    def delete_target(self, tid):
        if messagebox.askyesno("NetPulse", "Remove target from overlay?"):
            self.target_mgr.delete_target(tid)
            self.render_target_list()

    def open_add_dialog(self):
        # Native Toplevel popup to add a target
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Target")
        dialog.attributes("-topmost", True)
        dialog.configure(bg=COLOR_BG)
        dialog.geometry("280x230")
        dialog.resizable(False, False)

        tk.Label(dialog, text="Add Target to Monitor", bg=COLOR_BG, fg=COLOR_TEXT, font=("Segoe UI", 10, "bold")).pack(pady=(12, 8))

        # Name
        tk.Label(dialog, text="Display Name:", bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=16)
        entry_name = tk.Entry(dialog, bg=COLOR_CARD, fg=COLOR_TEXT, insertbackground="white", bd=1, relief="solid")
        entry_name.pack(fill=tk.X, padx=16, pady=(2, 8))

        # Host / URL
        tk.Label(dialog, text="Domain / URL / IP (e.g. 9.9.9.9):", bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=16)
        entry_host = tk.Entry(dialog, bg=COLOR_CARD, fg=COLOR_TEXT, insertbackground="white", bd=1, relief="solid")
        entry_host.pack(fill=tk.X, padx=16, pady=(2, 8))

        # Type
        tk.Label(dialog, text="Target Type:", bg=COLOR_BG, fg=COLOR_MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=16)
        type_var = tk.StringVar(value="web")
        combo = ttk.Combobox(dialog, textvariable=type_var, values=["web", "dns_ip"], state="readonly")
        combo.pack(fill=tk.X, padx=16, pady=(2, 14))

        def on_save():
            name = entry_name.get().strip()
            host = entry_host.get().strip()
            t_type = type_var.get()
            if not host:
                messagebox.showerror("Error", "Please provide a domain or IP address.", parent=dialog)
                return
            self.target_mgr.add_target(name, host, target_type=t_type)
            dialog.destroy()
            self.render_target_list()

        btn_box = tk.Frame(dialog, bg=COLOR_BG)
        btn_box.pack(fill=tk.X, padx=16)
        tk.Button(btn_box, text="Cancel", bg=COLOR_CARD, fg=COLOR_TEXT, bd=0, padx=10, pady=4, command=dialog.destroy).pack(side=tk.LEFT)
        tk.Button(btn_box, text="Add", bg=COLOR_ACCENT, fg="white", bd=0, padx=16, pady=4, command=on_save).pack(side=tk.RIGHT)

    def background_poll_loop(self):
        while self.running:
            targets = self.target_mgr.get_targets()
            results = {}
            for t in targets:
                if not self.running:
                    break
                res = probe_target(t)
                results[t["id"]] = res

            if self.running:
                # Update UI safely on the main Tkinter thread
                self.root.after(0, lambda r=results: self.update_probe_ui(r))

            time.sleep(3.0)

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
                text = f"{lat}ms"
            elif status == "slow":
                color = COLOR_YELLOW
                text = f"{lat}ms"
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

        # Update Master Pulse
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
    root = tk.Tk()
    app = DesktopOverlayApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
