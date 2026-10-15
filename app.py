#!/usr/bin/env python3
"""
NetPulse Overlay - Real-Time DNS & Network Stability Overlay HUD
Zero-dependency, Python 3 standard library only.
"""

import os
import sys
import json
import time
import socket
import urllib.request
import urllib.parse
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor
import threading

PORT = 4920
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'targets.json')

# Lock for thread-safe target updates
data_lock = threading.Lock()
targets_data = []
history_data = {}  # target_id -> list of {'time': float, 'latency': float, 'status': str}

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
        "name": "GitHub (Baseline Check)",
        "host": "github.com",
        "url": "https://github.com",
        "type": "web",
        "deletable": False
    }
]

def load_targets():
    global targets_data
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                targets_data = json.load(f)
                return
        except Exception as e:
            print(f"[Warning] Failed to read {CONFIG_FILE}: {e}")
    targets_data = list(DEFAULT_TARGETS)
    save_targets()

def save_targets():
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(targets_data, f, indent=2)
    except Exception as e:
        print(f"[Warning] Failed to write {CONFIG_FILE}: {e}")

def check_dns(host):
    t0 = time.time()
    try:
        ip = socket.gethostbyname(host)
        duration = round((time.time() - t0) * 1000)
        return {"status": "ok", "time": duration, "ip": ip}
    except Exception as err:
        duration = round((time.time() - t0) * 1000)
        return {"status": "error", "time": duration, "error": str(err)}

def check_tcp(host, port, timeout_sec=2.5):
    t0 = time.time()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout_sec)
    try:
        s.connect((host, port))
        duration = round((time.time() - t0) * 1000)
        s.close()
        return {"status": "ok", "time": duration}
    except socket.timeout:
        s.close()
        return {"status": "timeout", "time": round(timeout_sec * 1000), "error": "Connection timed out"}
    except Exception as err:
        duration = round((time.time() - t0) * 1000)
        s.close()
        return {"status": "error", "time": duration, "error": str(err)}

def check_http(target_url, timeout_sec=3.5):
    t0 = time.time()
    req = urllib.request.Request(
        target_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NetPulse/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            duration = round((time.time() - t0) * 1000)
            status_code = resp.status
            return {
                "status": "ok" if status_code < 400 else "warn",
                "time": duration,
                "code": status_code
            }
    except urllib.error.HTTPError as e:
        duration = round((time.time() - t0) * 1000)
        return {"status": "warn", "time": duration, "code": e.code}
    except urllib.error.URLError as e:
        duration = round((time.time() - t0) * 1000)
        if isinstance(e.reason, socket.timeout):
            return {"status": "timeout", "time": duration, "error": "HTTP Request timed out"}
        return {"status": "error", "time": duration, "error": str(e.reason)}
    except Exception as e:
        duration = round((time.time() - t0) * 1000)
        return {"status": "error", "time": duration, "error": str(e)}

def probe_single_target(target):
    tid = target["id"]
    res = {
        "id": tid,
        "name": target["name"],
        "host": target["host"],
        "type": target["type"],
        "deletable": target.get("deletable", True),
        "timestamp": int(time.time() * 1000),
        "dns": None,
        "latency": None,
        "status": "ok",
        "message": ""
    }

    if target["type"] in ("web", "api"):
        dns_res = check_dns(target["host"])
        res["dns"] = dns_res
        if dns_res["status"] == "error":
            res["status"] = "error"
            res["message"] = f"DNS failed: {dns_res['error']}"
            res["latency"] = dns_res["time"]
        else:
            url_to_test = target.get("url", f"https://{target['host']}")
            http_res = check_http(url_to_test)
            res["http"] = http_res
            res["latency"] = http_res["time"]
            if http_res["status"] == "timeout":
                res["status"] = "timeout"
                res["message"] = "Connection timed out"
            elif http_res["status"] == "error":
                res["status"] = "error"
                res["message"] = http_res["error"]
            else:
                res["status"] = "slow" if http_res["time"] > 250 else "ok"
                res["message"] = f"HTTP {http_res['code']} ({http_res['time']}ms, DNS: {dns_res['time']}ms)"

    elif target["type"] == "dns_ip":
        port = target.get("port", 53)
        tcp_res = check_tcp(target["host"], port)
        res["latency"] = tcp_res["time"]
        if tcp_res["status"] == "timeout":
            res["status"] = "timeout"
            res["message"] = f"Port {port} timed out"
        elif tcp_res["status"] == "error":
            res["status"] = "error"
            res["message"] = tcp_res["error"]
        else:
            res["status"] = "slow" if tcp_res["time"] > 200 else "ok"
            res["message"] = f"Port {port} ({tcp_res['time']}ms)"

    with data_lock:
        if tid not in history_data:
            history_data[tid] = []
        history_data[tid].append({
            "time": res["timestamp"],
            "latency": res["latency"] or 0,
            "status": res["status"]
        })
        if len(history_data[tid]) > 30:
            history_data[tid].pop(0)
        res["history"] = list(history_data[tid])

    return res

latest_probe_results = []

def polling_worker():
    global latest_probe_results
    executor = ThreadPoolExecutor(max_workers=8)
    while True:
        with data_lock:
            current_targets = list(targets_data)
        
        futures = [executor.submit(probe_single_target, t) for t in current_targets]
        results = [f.result() for f in futures]

        with data_lock:
            latest_probe_results = results

        time.sleep(3.0)

def deep_diagnose_ddg():
    steps = []
    t0 = time.time()

    # Step 1: IPv4 DNS
    t_dns = time.time()
    try:
        ip = socket.gethostbyname('duckduckgo.com')
        duration = round((time.time() - t_dns) * 1000)
        steps.append({
            "step": "DNS Resolution (IPv4)",
            "status": "ok",
            "duration": duration,
            "detail": f"Resolved to {ip}"
        })
    except Exception as e:
        steps.append({
            "step": "DNS Resolution (IPv4)",
            "status": "error",
            "duration": round((time.time() - t_dns) * 1000),
            "detail": f"Failed: {e}"
        })

    # Step 2: IPv6 check
    t_dns6 = time.time()
    try:
        res6 = socket.getaddrinfo('duckduckgo.com', 443, socket.AF_INET6)
        duration6 = round((time.time() - t_dns6) * 1000)
        steps.append({
            "step": "IPv6 Resolution (AAAA)",
            "status": "ok",
            "duration": duration6,
            "detail": f"Found IPv6 address: {res6[0][4][0]}"
        })
    except Exception:
        steps.append({
            "step": "IPv6 Resolution (AAAA)",
            "status": "info",
            "duration": 0,
            "detail": "No IPv6 AAAA record configured (Standard for DuckDuckGo)"
        })

    # Step 3: TCP port 443 handshake
    tcp_res = check_tcp('duckduckgo.com', 443, timeout_sec=4.0)
    steps.append({
        "step": "TCP Handshake (Port 443)",
        "status": tcp_res["status"],
        "duration": tcp_res["time"],
        "detail": f"Connected in {tcp_res['time']}ms" if tcp_res["status"] == "ok" else tcp_res["error"]
    })

    # Step 4: Full TLS & HTTP GET
    http_res = check_http('https://duckduckgo.com', timeout_sec=5.0)
    steps.append({
        "step": "TLS Handshake & HTTP GET",
        "status": http_res["status"],
        "duration": http_res["time"],
        "detail": f"HTTP {http_res['code']} in {http_res['time']}ms" if http_res["status"] == "ok" else http_res.get("error", "Error")
    })

    total_time = round((time.time() - t0) * 1000)
    return {"steps": steps, "totalTime": total_time}

class NetPulseHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence default HTTP access logs to keep terminal clean
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            with data_lock:
                data = {
                    "timestamp": int(time.time() * 1000),
                    "targets": latest_probe_results
                }
            self.wfile.write(json.dumps(data).encode('utf-8'))
            return

        if parsed.path == '/api/diagnose':
            diag = deep_diagnose_ddg()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(diag).encode('utf-8'))
            return

        # Main HTML
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(HTML_UI.encode('utf-8'))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == '/api/targets':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                body = json.loads(post_data.decode('utf-8'))
                name = body.get('name', '').strip()
                host = body.get('host', '').strip()
                target_type = body.get('type', 'web')
                port = int(body.get('port', 53))

                if not host:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'{"error": "Host is required"}')
                    return

                clean_host = host
                target_url = None
                if host.startswith('http://') or host.startswith('https://'):
                    target_url = host
                    clean_host = urllib.parse.urlparse(host).hostname or host
                elif target_type in ('web', 'api'):
                    target_url = f"https://{clean_host}"

                new_target = {
                    "id": f"custom_{int(time.time() * 1000)}",
                    "name": name or clean_host,
                    "host": clean_host,
                    "type": target_type,
                    "deletable": True
                }
                if target_url:
                    new_target["url"] = target_url
                if target_type == 'dns_ip':
                    new_target["port"] = port

                with data_lock:
                    targets_data.append(new_target)
                    save_targets()

                # Immediately probe
                threading.Thread(target=probe_single_target, args=(new_target,), daemon=True).start()

                self.send_response(201)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "target": new_target}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith('/api/targets/'):
            target_id = parsed.path.split('/')[-1]
            with data_lock:
                initial_count = len(targets_data)
                filtered = [t for t in targets_data if not (t["id"] == target_id and t.get("deletable", True))]
                if len(filtered) < initial_count:
                    targets_data.clear()
                    targets_data.extend(filtered)
                    save_targets()
                    if target_id in history_data:
                        del history_data[target_id]

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"success": true}')
            return

HTML_UI = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NetPulse - DNS & Network Stability Overlay</title>
<style>
  :root {
    --bg: #090d16;
    --card: rgba(18, 24, 38, 0.85);
    --card-border: rgba(255, 255, 255, 0.08);
    --text: #f8fafc;
    --text-dim: #94a3b8;
    --green: #10b981;
    --yellow: #f59e0b;
    --red: #ef4444;
    --blue: #3b82f6;
    --accent: #6366f1;
    --accent-hover: #4f46e5;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
  body {
    background: radial-gradient(circle at top, #151d2f 0%, var(--bg) 100%);
    color: var(--text);
    min-height: 100vh;
    padding: 20px 16px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  .container {
    width: 100%;
    max-width: 840px;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--card-border);
  }
  .logo-group {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .pulse-indicator {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 12px var(--green);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }
  h1 { font-size: 1.35rem; font-weight: 700; letter-spacing: -0.5px; }
  .actions { display: flex; gap: 8px; align-items: center; }
  button {
    background: rgba(255,255,255,0.07);
    border: 1px solid var(--card-border);
    color: var(--text);
    padding: 7px 14px;
    border-radius: 8px;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  button:hover {
    background: rgba(255,255,255,0.13);
    border-color: rgba(255,255,255,0.2);
    transform: translateY(-1px);
  }
  button.primary {
    background: var(--accent);
    border-color: var(--accent);
  }
  button.primary:hover {
    background: var(--accent-hover);
  }
  .btn-audio {
    padding: 7px 10px;
    font-size: 1rem;
  }

  .stat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 12px;
    margin-bottom: 20px;
  }
  .stat-card {
    background: var(--card);
    backdrop-filter: blur(14px);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 14px 18px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.3);
  }
  .stat-card .label { font-size: 0.72rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.7px; font-weight: 600; }
  .stat-card .value { font-size: 1.4rem; font-weight: 700; margin-top: 4px; display: flex; align-items: baseline; gap: 6px; }
  .stat-card .sub { font-size: 0.75rem; color: var(--text-dim); margin-top: 2px; }

  .target-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 20px;
  }
  .target-row {
    background: var(--card);
    backdrop-filter: blur(14px);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 12px 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 4px 16px rgba(0,0,0,0.2);
    transition: all 0.2s ease;
  }
  .target-row:hover {
    border-color: rgba(255,255,255,0.18);
  }
  .target-row.ddg-card {
    border-color: rgba(99, 102, 241, 0.45);
    background: linear-gradient(90deg, rgba(99, 102, 241, 0.1) 0%, rgba(18, 24, 38, 0.9) 100%);
  }
  .target-left {
    display: flex;
    align-items: center;
    gap: 14px;
    min-width: 230px;
  }
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .dot-ok { background: var(--green); box-shadow: 0 0 8px var(--green); }
  .dot-slow { background: var(--yellow); box-shadow: 0 0 8px var(--yellow); }
  .dot-error, .dot-timeout { background: var(--red); box-shadow: 0 0 10px var(--red); animation: blink 1s infinite; }
  @keyframes blink { 50% { opacity: 0.3; } }

  .name-block { display: flex; flex-direction: column; }
  .target-title { font-weight: 600; font-size: 0.95rem; }
  .target-detail { font-size: 0.75rem; color: var(--text-dim); margin-top: 2px; }

  .target-sparkline {
    flex-grow: 1;
    max-width: 220px;
    height: 28px;
    margin: 0 16px;
    display: flex;
    align-items: flex-end;
    gap: 3px;
  }
  .spark-bar {
    width: 4px;
    border-radius: 2px;
    background: rgba(255,255,255,0.15);
    min-height: 3px;
    transition: height 0.2s;
  }
  .spark-bar.ok { background: var(--green); }
  .spark-bar.slow { background: var(--yellow); }
  .spark-bar.err { background: var(--red); }

  .target-right {
    display: flex;
    align-items: center;
    gap: 14px;
    text-align: right;
  }
  .metric-ms {
    font-size: 1.15rem;
    font-weight: 700;
  }
  .metric-status {
    font-size: 0.72rem;
    color: var(--text-dim);
    margin-top: 1px;
    font-weight: 500;
  }
  .delete-btn {
    background: transparent;
    border: none;
    color: var(--text-dim);
    padding: 6px;
    font-size: 0.9rem;
    cursor: pointer;
    border-radius: 6px;
  }
  .delete-btn:hover {
    color: var(--red);
    background: rgba(239, 68, 68, 0.12);
    transform: none;
  }

  /* Diagnostics Panel */
  .diag-box {
    background: rgba(15, 23, 42, 0.95);
    border: 1px solid rgba(99, 102, 241, 0.3);
    border-radius: 12px;
    padding: 18px;
    margin-top: 16px;
    display: none;
  }
  .diag-box.open { display: block; }
  .diag-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; font-weight: 600; font-size: 0.95rem; }
  .step-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 9px 12px;
    background: rgba(255,255,255,0.03);
    border-radius: 6px;
    margin-bottom: 6px;
    font-size: 0.85rem;
  }

  /* Add Target Modal */
  .modal-backdrop {
    position: fixed;
    top: 0; left: 0; width: 100vw; height: 100vh;
    background: rgba(0,0,0,0.65);
    backdrop-filter: blur(6px);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .modal-backdrop.open { display: flex; }
  .modal-card {
    background: #141c2c;
    border: 1px solid var(--card-border);
    border-radius: 14px;
    width: 90%;
    max-width: 440px;
    padding: 22px;
    box-shadow: 0 20px 40px rgba(0,0,0,0.6);
  }
  .modal-card h2 { font-size: 1.15rem; margin-bottom: 16px; }
  .form-group { margin-bottom: 14px; }
  .form-group label { display: block; font-size: 0.78rem; color: var(--text-dim); margin-bottom: 6px; font-weight: 600; }
  .form-group input, .form-group select {
    width: 100%;
    background: rgba(255,255,255,0.06);
    border: 1px solid var(--card-border);
    border-radius: 8px;
    padding: 9px 12px;
    color: var(--text);
    font-size: 0.9rem;
    outline: none;
  }
  .form-group input:focus, .form-group select:focus {
    border-color: var(--accent);
  }
  .modal-btns { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }

  /* Compact / PiP Mode */
  body.pip-mode {
    padding: 10px;
    background: #090d16;
  }
  body.pip-mode header, body.pip-mode .stat-grid, body.pip-mode .diag-box, body.pip-mode .modal-backdrop {
    display: none !important;
  }
  body.pip-mode .container { max-width: 100%; }
  body.pip-mode .target-row {
    padding: 8px 12px;
    margin-bottom: 6px;
  }
  body.pip-mode .target-sparkline { max-width: 90px; }
  body.pip-mode .target-left { min-width: 140px; }
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="logo-group">
      <div id="masterPulse" class="pulse-indicator"></div>
      <div>
        <h1>NetPulse Overlay</h1>
        <div style="font-size:0.75rem; color:var(--text-dim)">Real-time DNS & Endpoint Monitor</div>
      </div>
    </div>
    <div class="actions">
      <button class="btn-audio" id="audioBtn" onclick="toggleAudio()" title="Toggle audio chime alert on connection drop">
        🔔
      </button>
      <button onclick="openModal()" title="Add custom domain, IP, or DNS resolver">
        <span>+</span> Add Target
      </button>
      <button onclick="popoutPip()" title="Float on top of any app/browser using Picture-in-Picture">
        <span>⧉</span> Pop-out Overlay
      </button>
      <button class="primary" onclick="runDiagnostics()">
        <span>⚡</span> Deep Test DDG
      </button>
    </div>
  </header>

  <div class="stat-grid">
    <div class="stat-card">
      <div class="label">DuckDuckGo</div>
      <div class="value" id="statDdg">Checking...</div>
      <div class="sub" id="statDdgSub">DNS & HTTPS Probe</div>
    </div>
    <div class="stat-card">
      <div class="label">Primary DNS Latency</div>
      <div class="value" id="statDns">--</div>
      <div class="sub">1.1.1.1 & 8.8.8.8 average</div>
    </div>
    <div class="stat-card">
      <div class="label">Connection Drops / Timeouts</div>
      <div class="value" id="statAlerts" style="color:var(--green)">0</div>
      <div class="sub">Recorded this session</div>
    </div>
  </div>

  <div class="target-list" id="targetList">
    <!-- Target rows rendered by JS -->
  </div>

  <div class="diag-box" id="diagBox">
    <div class="diag-header">
      <span>DuckDuckGo Step-by-Step Connection Trace</span>
      <button onclick="document.getElementById('diagBox').classList.remove('open')" style="padding:3px 8px">✕</button>
    </div>
    <div id="diagList">Running multi-stage trace...</div>
  </div>
</div>

<!-- Modal -->
<div class="modal-backdrop" id="addModal">
  <div class="modal-card">
    <h2>Add Monitoring Target</h2>
    <div class="form-group">
      <label>Target Name (e.g., Quad9 DNS, My Server)</label>
      <input type="text" id="targetName" placeholder="My DNS / Service">
    </div>
    <div class="form-group">
      <label>Type</label>
      <select id="targetType" onchange="handleTypeChange()">
        <option value="web">Web Endpoint (HTTPS/HTTP)</option>
        <option value="api">API Endpoint</option>
        <option value="dns_ip">Direct DNS IP / TCP Port</option>
      </select>
    </div>
    <div class="form-group">
      <label id="hostLabel">Domain or URL (e.g. quad9.net or https://google.com)</label>
      <input type="text" id="targetHost" placeholder="e.g. quad9.net or 9.9.9.9">
    </div>
    <div class="form-group" id="portGroup" style="display:none;">
      <label>Port</label>
      <input type="number" id="targetPort" value="53">
    </div>
    <div class="modal-btns">
      <button onclick="closeModal()">Cancel</button>
      <button class="primary" onclick="submitTarget()">Add & Monitor</button>
    </div>
  </div>
</div>

<script>
let alertCount = 0;
let audioEnabled = false;
let audioCtx = null;

function toggleAudio() {
  audioEnabled = !audioEnabled;
  document.getElementById('audioBtn').innerText = audioEnabled ? '🔊' : '🔔';
  if (audioEnabled && !audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
}

function playAlertChime() {
  if (!audioEnabled || !audioCtx) return;
  try {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(440, audioCtx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(880, audioCtx.currentTime + 0.2);
    gain.gain.setValueAtTime(0.2, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.3);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.3);
  } catch (e) {}
}

async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    renderTargets(data.targets);
  } catch (e) {
    console.error('Fetch status error:', e);
  }
}

function renderTargets(targets) {
  const container = document.getElementById('targetList');
  container.innerHTML = '';

  let hasError = false;
  let hasSlow = false;
  let ddgObj = null;
  let dnsSpeeds = [];

  targets.forEach(t => {
    if (t.id === 'ddg') ddgObj = t;
    if (t.id.includes('dns') && t.latency) dnsSpeeds.push(t.latency);

    const isErr = t.status === 'timeout' || t.status === 'error';
    const isSlow = t.status === 'slow';
    if (isErr) {
      hasError = true;
      alertCount++;
      playAlertChime();
    }
    if (isSlow) hasSlow = true;

    const row = document.createElement('div');
    row.className = 'target-row' + (t.id.startsWith('ddg') ? ' ddg-card' : '');

    let dotClass = 'dot-ok';
    if (t.status === 'slow') dotClass = 'dot-slow';
    if (t.status === 'timeout') dotClass = 'dot-timeout';
    if (t.status === 'error') dotClass = 'dot-error';

    // Sparkline history
    let sparkBars = '';
    const hist = t.history || [];
    for (let i = 0; i < 20; i++) {
      const idx = hist.length - 20 + i;
      if (idx >= 0 && idx < hist.length) {
        const item = hist[idx];
        const hPct = Math.min(100, Math.max(10, (item.latency / 300) * 100));
        let barClass = item.status === 'ok' ? 'ok' : (item.status === 'slow' ? 'slow' : 'err');
        sparkBars += '<div class="spark-bar ' + barClass + '" style="height:' + hPct + '%" title="' + item.latency + 'ms"></div>';
      } else {
        sparkBars += '<div class="spark-bar" style="height:10%"></div>';
      }
    }

    const deleteBtnHtml = t.deletable
      ? '<button class="delete-btn" onclick="deleteTarget(\\'' + t.id + '\\')" title="Remove target">✕</button>'
      : '';

    row.innerHTML = `
      <div class="target-left">
        <div class="dot ${dotClass}"></div>
        <div class="name-block">
          <div class="target-title">${t.name}</div>
          <div class="target-detail">${t.message || t.host}</div>
        </div>
      </div>
      <div class="target-sparkline">${sparkBars}</div>
      <div class="target-right">
        <div>
          <div class="metric-ms" style="color: ${isErr ? 'var(--red)' : (isSlow ? 'var(--yellow)' : 'var(--green)')}">
            ${t.latency !== null ? t.latency + 'ms' : '--'}
          </div>
          <div class="metric-status">${t.status.toUpperCase()}</div>
        </div>
        ${deleteBtnHtml}
      </div>
    `;
    container.appendChild(row);
  });

  // Top indicator pulse
  const pulse = document.getElementById('masterPulse');
  if (hasError) {
    pulse.style.background = 'var(--red)';
    pulse.style.boxShadow = '0 0 12px var(--red)';
  } else if (hasSlow) {
    pulse.style.background = 'var(--yellow)';
    pulse.style.boxShadow = '0 0 12px var(--yellow)';
  } else {
    pulse.style.background = 'var(--green)';
    pulse.style.boxShadow = '0 0 12px var(--green)';
  }

  // Stat cards
  if (ddgObj) {
    const isDDGOk = ddgObj.status === 'ok';
    const ddgEl = document.getElementById('statDdg');
    ddgEl.innerText = isDDGOk ? ddgObj.latency + 'ms' : ddgObj.status.toUpperCase();
    ddgEl.style.color = isDDGOk ? 'var(--green)' : 'var(--red)';
    document.getElementById('statDdgSub').innerText = ddgObj.message || 'Operational';
  }

  if (dnsSpeeds.length) {
    const avg = Math.round(dnsSpeeds.reduce((a,b)=>a+b, 0) / dnsSpeeds.length);
    document.getElementById('statDns').innerText = avg + 'ms avg';
  }

  const alertEl = document.getElementById('statAlerts');
  alertEl.innerText = alertCount;
  if (alertCount > 0) alertEl.style.color = 'var(--red)';
}

async function runDiagnostics() {
  const box = document.getElementById('diagBox');
  box.classList.add('open');
  const list = document.getElementById('diagList');
  list.innerHTML = '<div style="color:var(--text-dim)">Running multi-stage DNS & Handshake trace...</div>';

  try {
    const res = await fetch('/api/diagnose');
    const data = await res.json();
    let html = '';
    data.steps.forEach(s => {
      const color = s.status === 'ok' ? 'var(--green)' : (s.status === 'info' ? 'var(--blue)' : 'var(--red)');
      html += `
        <div class="step-row">
          <div>
            <strong>${s.step}</strong>
            <div style="color:var(--text-dim);font-size:0.75rem">${s.detail}</div>
          </div>
          <div style="color:${color};font-weight:600">${s.duration ? s.duration + 'ms' : ''} [${s.status.toUpperCase()}]</div>
        </div>
      `;
    });
    html += `<div style="text-align:right;font-size:0.75rem;color:var(--text-dim);margin-top:6px">Total diagnostic time: ${data.totalTime}ms</div>`;
    list.innerHTML = html;
  } catch (e) {
    list.innerHTML = '<div style="color:var(--red)">Failed to complete diagnostic trace</div>';
  }
}

// Modal handling
function openModal() { document.getElementById('addModal').classList.add('open'); }
function closeModal() { document.getElementById('addModal').classList.remove('open'); }
function handleTypeChange() {
  const type = document.getElementById('targetType').value;
  const isDns = type === 'dns_ip';
  document.getElementById('portGroup').style.display = isDns ? 'block' : 'none';
  document.getElementById('hostLabel').innerText = isDns ? 'IP Address (e.g. 9.9.9.9)' : 'Domain or URL (e.g. quad9.net or https://google.com)';
}

async function submitTarget() {
  const name = document.getElementById('targetName').value;
  const type = document.getElementById('targetType').value;
  const host = document.getElementById('targetHost').value;
  const port = document.getElementById('targetPort').value;

  if (!host) {
    alert('Please provide a host or IP');
    return;
  }

  await fetch('/api/targets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, type, host, port })
  });

  closeModal();
  document.getElementById('targetName').value = '';
  document.getElementById('targetHost').value = '';
  fetchStatus();
}

async function deleteTarget(id) {
  if (!confirm('Remove this target from monitoring?')) return;
  await fetch('/api/targets/' + id, { method: 'DELETE' });
  fetchStatus();
}

// Picture-in-Picture Floating Desktop Overlay
async function popoutPip() {
  if ('documentPictureInPicture' in window) {
    try {
      const pipWindow = await window.documentPictureInPicture.requestWindow({
        width: 360,
        height: 480
      });

      [...document.styleSheets].forEach(styleSheet => {
        try {
          const cssRules = [...styleSheet.cssRules].map(rule => rule.cssText).join('');
          const style = document.createElement('style');
          style.textContent = cssRules;
          pipWindow.document.head.appendChild(style);
        } catch (e) {}
      });

      pipWindow.document.body.className = 'pip-mode';
      const containerClone = document.querySelector('.container').cloneNode(true);
      pipWindow.document.body.appendChild(containerClone);

      setInterval(async () => {
        const pipTargetList = pipWindow.document.getElementById('targetList');
        if (pipTargetList) {
          pipTargetList.innerHTML = document.getElementById('targetList').innerHTML;
        }
      }, 3000);
      return;
    } catch (e) {
      console.warn('PiP requestWindow failed, falling back to popup', e);
    }
  }

  window.open(window.location.href, 'NetPulseHUD', 'width=380,height=520,menubar=no,toolbar=no,location=no');
}

fetchStatus();
setInterval(fetchStatus, 3000);
</script>
</body>
</html>
"""

def main():
    load_targets()
    threading.Thread(target=polling_worker, daemon=True).start()

    server = HTTPServer(('0.0.0.0', PORT), NetPulseHandler)
    print(f"[NetPulse] Overlay HUD running at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[NetPulse] Shutting down.")
        server.server_close()

if __name__ == '__main__':
    main()
