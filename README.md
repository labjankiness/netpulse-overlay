# NetPulse Overlay

A lightweight, zero-dependency, real-time DNS & Network Stability Overlay HUD written in pure Python.

Monitors connectivity, latency trends, and DNS resolution to endpoints like DuckDuckGo, Cloudflare, Google DNS, and your own custom targets with a floating always-on-top Picture-in-Picture desktop overlay.

---

## Features

- **Zero External Dependencies**: Pure Python 3 standard library (`http.server`, `urllib`, `socket`, `threading`). No `pip install` required.
- **Dedicated DuckDuckGo Stability Monitoring**: Real-time probes of DuckDuckGo Web & API endpoints with a single-click 4-stage deep handshake tracer (IPv4 DNS → IPv6 → TCP 443 → TLS/HTTPS).
- **DNS Health Tracking**: Continuous TCP/DNS probes to Cloudflare (`1.1.1.1`), Google (`8.8.8.8`), and custom resolvers.
- **Always-on-Top Floating Overlay (PiP)**: Leverages the Document Picture-in-Picture API to float on top of browser windows, code editors, and full-screen games without installing third-party overlay software.
- **Interactive Target Management**: Easily add and remove custom targets (Web, API, or direct DNS/TCP ports) directly from the UI or via `targets.json`.
- **Live Sparkline Graphs**: Visualizes latency jitter and highlights packet drops or timeouts over the past 30 probe cycles.
- **Sound Alerts**: Web Audio API synthesized audio chime when a connection timeout or drop is detected.

---

## Quickstart

### 1. Run the Monitor
```bash
python3 app.py
```

### 2. Open the Overlay
Open your browser (Chrome or Edge recommended for Picture-in-Picture support):
```
http://localhost:4920
```

### 3. Pop-out Floating Overlay
Click the **⧉ Pop-out Overlay** button in the header. The overlay pops into a sleek, floating desktop window that stays on top while you browse or work.

---

## Adding Custom Targets

### Via the Web UI
1. Click **+ Add Target** in the top header.
2. Select target type:
   - **Web Endpoint**: Monitors HTTPS status and DNS resolution (e.g. `https://your-api.com`).
   - **API Endpoint**: Tests REST API availability.
   - **Direct DNS IP / TCP Port**: Tests specific DNS servers (e.g. Quad9 `9.9.9.9`, OpenDNS `208.67.222.222`, or internal routers) on port 53.
3. Click **Add & Monitor**.

### Via Configuration (`targets.json`)
You can edit `targets.json` directly. New entries will load automatically:
```json
{
  "id": "quad9",
  "name": "Quad9 DNS",
  "host": "9.9.9.9",
  "port": 53,
  "type": "dns_ip",
  "deletable": true
}
```

---

## Deep Diagnostics

Click **⚡ Deep Test DDG** to perform an instant live diagnostic trace:
1. **DNS Resolution (IPv4)**: Measures lookup duration to `duckduckgo.com`.
2. **IPv6 Resolution (AAAA)**: Verifies whether IPv6 lookup delays are present.
3. **TCP Handshake (Port 443)**: Verifies TCP SYN-ACK round-trip time.
4. **TLS Handshake & HTTP GET**: Measures complete SSL negotiation and HTTP status response.

---

## License

MIT License
