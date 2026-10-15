# NetPulse Overlay

A lightweight, zero-dependency, real-time DNS & Network Stability System Overlay written in pure Python.

Monitors connectivity, latency trends, and DNS resolution to endpoints like DuckDuckGo, Cloudflare, Google DNS, and your own custom targets as a **native, frameless, draggable, always-on-top desktop system overlay HUD**.

---

## Features

- **Native System Desktop Overlay (`overlay.py`)**:
  - **Frameless & Draggable**: Seamlessly drag and place the overlay anywhere on your screens.
  - **Always-on-Top**: Floats over all other windows, full-screen apps, code editors, and browsers.
  - **Dark Glassmorphic UI**: High-contrast, semi-transparent HUD design that stays out of your way.
  - **Compact Mode**: Click `─` to collapse into a minimal status bar or `□` to expand.
  - **Custom Target Manager**: Click `+` to add your own DNS IPs, websites, or APIs directly from the overlay, with automatic persistence to `targets.json`.
  - **Zero Third-Party Pip Packages**: Uses Python's built-in standard library (`tkinter`, `socket`, `threading`, `urllib`).

- **Web / Picture-in-Picture Alternative (`app.py`)**:
  - Also includes a browser-based option with Document PiP and multi-stage DuckDuckGo connection tracer.

---

## Quickstart

### Option 1: Native Desktop System Overlay (Recommended)

#### On Windows:
Double-click:
```
run_overlay.bat
```
*(Or in Command Prompt / PowerShell: `pythonw overlay.py`)*

#### On macOS / Linux:
```bash
python3 overlay.py
```

- **Move it**: Click and drag the top title bar to reposition the overlay anywhere on your screen.
- **Add targets**: Click the **`+`** button in the header.
- **Remove targets**: Click the **`×`** next to any custom target.
- **Minimize**: Click **`─`** to toggle compact mode.
- **Close**: Click **`✕`** to exit.

---

### Option 2: Browser HUD / Web Overlay

If you prefer a browser dashboard:
```bash
python3 app.py
```
Open [http://localhost:4920](http://localhost:4920) in Chrome or Edge.

---

## Custom Target Configuration (`targets.json`)

Targets are saved in `targets.json` and can be edited directly or through the overlay UI:
```json
[
  {
    "id": "ddg",
    "name": "DuckDuckGo Web",
    "host": "duckduckgo.com",
    "url": "https://duckduckgo.com",
    "type": "web",
    "deletable": false
  },
  {
    "id": "cf_dns",
    "name": "Cloudflare DNS",
    "host": "1.1.1.1",
    "port": 53,
    "type": "dns_ip",
    "deletable": false
  },
  {
    "id": "google_dns",
    "name": "Google DNS",
    "host": "8.8.8.8",
    "port": 53,
    "type": "dns_ip",
    "deletable": false
  }
]
```

---

## License

MIT License
