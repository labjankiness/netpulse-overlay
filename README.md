# NetPulse Overlay

A lightweight, zero-dependency, real-time DNS & Network Stability System Overlay written in pure Python.

Monitors connectivity, latency trends, and DNS resolution to your local gateway, DNS resolvers, DuckDuckGo, and custom targets as a **native, frameless, draggable, always-on-top desktop system overlay HUD**.

---

## Key Features

- **3-Tier Root-Cause Failure Detection**:
  Instantly identifies *what* broke when a web browser or application fails to load:
  - **Tier 1: [LAN] Local Router / Gateway**: Automatically detects and monitors your physical network interface and gateway (e.g. `10.21.5.100`) to detect Wi-Fi drops or cable disconnections.
  - **Tier 2: [DNS] Resolvers**: Probes Cloudflare (`1.1.1.1`) and Google DNS (`8.8.8.8`) to catch DNS stalls or ISP poisoning.
  - **Tier 3: [Web] Search & Internet**: Monitors DuckDuckGo and GitHub to distinguish single-service outages from whole-internet drops.

- **1-Click Minimize / Floating Ticker Pill**:
  - Click **`─`** in the header to collapse into an ultra-compact floating ticker bar (~30px high) showing live metrics across all tiers in one line:
    ```
    [●] LAN:1ms | DNS:20ms | Google:18ms | DDG:2ms | Web:20ms   [+] [□] [✕]
    ```
  - Click **`□`** to expand back into the full detailed card view.

- **True Frameless Floating HUD**:
  - **Frameless & Draggable**: Click and drag from anywhere on the header or ticker bar to place the overlay anywhere on your screens.
  - **Always-on-Top**: Floats pinned over Firefox, Chrome, games, and full-screen editors.
  - **Dark Glassmorphism**: Semi-transparent dark styling designed to stay out of your way.

- **Flicker-Free, Zero-GPU Impact Engine**:
  - Background ICMP and DNS checks are executed silently using native Windows flags (`CREATE_NO_WINDOW`, `SW_HIDE`).
  - Zero console windows, zero GPU context switching, and zero DWM micro-stutters in hardware-accelerated browsers like Firefox.

- **Interactive Target Manager**:
  - Click **`+`** on the overlay to add any domain, IP address, or URL on the fly.
  - Targets are saved with automatic persistence to `targets.json`.
  - Delete custom targets anytime with the **`✕`** button.

- **Zero External Dependencies**:
  - Pure Python 3 standard library (`tkinter`, `socket`, `threading`, `urllib`, `subprocess`). No `pip install` required.

---

## Quickstart

### Native Desktop System Overlay (Recommended)

#### On Windows:
Double-click:
```
run_overlay.bat
```
*(Or double-click the **NetPulse Overlay** shortcut on your Desktop / Start Menu).*

#### On macOS / Linux:
```bash
python3 overlay.py
```

### Controls:
- **Drag**: Click and drag anywhere on the header or minimized bar to move it across monitors.
- **Minimize / Expand**: Click **`─`** to collapse to the minimal ticker bar, or **`□`** to expand.
- **Add Target**: Click **`+`** in the header.
- **Delete Target**: Click **`✕`** next to any custom target.
- **Close**: Click **`✕`** in the top right.

---

### Windows Auto-Start (Runs on Boot)
To have NetPulse Overlay launch automatically in the background when turning on your PC:
* Double-click **`enable_autostart.bat`** (or copy `start_overlay.vbs` to your Windows Startup folder).
* To disable auto-start anytime, double-click **`disable_autostart.bat`**.

---

### Browser Alternative (`app.py`)
If you ever prefer a web-based dashboard with Document Picture-in-Picture:
```bash
python3 app.py
```
Navigate to [http://localhost:4920](http://localhost:4920) in Chrome or Edge.

---

## Custom Target Configuration (`targets.json`)

Targets are saved in `targets.json` and can be edited directly or through the overlay UI:
```json
[
  {
    "id": "lan",
    "name": "Router (LAN)",
    "short": "LAN",
    "host": "10.21.5.100",
    "type": "dns_ip",
    "tier": "tier1",
    "deletable": false
  },
  {
    "id": "cf_dns",
    "name": "Cloudflare DNS",
    "short": "DNS",
    "host": "1.1.1.1",
    "port": 53,
    "type": "dns_ip",
    "tier": "tier2",
    "deletable": false
  },
  {
    "id": "ddg",
    "name": "DuckDuckGo",
    "short": "DDG",
    "host": "duckduckgo.com",
    "url": "https://duckduckgo.com",
    "type": "web",
    "tier": "tier3",
    "deletable": false
  }
]
```

---

## License

MIT License
