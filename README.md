# GuardianEye — File Integrity Monitor

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/Standard%20Library%20Only-green?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/SHA--256-Hashing-orange?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/GUI-tkinter-purple?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge"/>
</p>

> Real-time file integrity monitoring tool — detects modified, deleted, and new files using SHA-256 cryptographic fingerprinting. Includes both a CLI engine and a dark-themed GUI.

---

## 📸 Demo

```
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          GuardianEye — File Integrity Watcher
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  What do you want to do?

    1  →  Build a fresh trust store (fingerprint files now)
    2  →  Start watching (compare against saved trust store)

  Enter 1 or 2:  2

  ✔  Trust store loaded — 5 file(s) enrolled.
     Watching for changes... Press Ctrl+C to stop.

  [~] MODIFIED  •  16:05:42
      a.txt
      stored:  f715b9eeb9260d91f66d...
      current: 30a827acf5634be6b341...

  [-] DELETED  •  16:05:45
      b.txt
      file no longer exists on disk

  [+] NEW FILE  •  16:05:48
      malware_payload.exe.txt
      sha256: d0e482fb6a9413b935d8...
```

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔒 **SHA-256 Fingerprinting** | Every file is hashed — even 1 byte change is detected |
| 🔴 **Modified Detection** | Alerts when file content changes |
| 🗑️ **Deleted Detection** | Alerts when a file disappears from disk |
| 🆕 **New File Detection** | Alerts when an unknown file appears |
| 🖥️ **Dark GUI** | Full tkinter GUI with live colour-coded alert feed |
| 📋 **Audit Log** | Every event timestamped to `guardian_events.log` |
| 🔁 **One-alert-per-change** | Each change fires exactly once — no repeated noise |
| 🐍 **Zero Dependencies** | Standard Python library only — no pip install needed |

---

## 🗂️ Project Structure

```
GuardianEye/
│
├── fim_scanner.py          ← Core engine (hashing, scanning, I/O)
├── guardian_gui.py         ← GUI layer (tkinter dark interface)
├── tamper_demo.py          ← Simulate 5 attack types for testing
├── live_demo.py            ← Live attack simulation with countdown
├── make_ppt.py             ← Auto-generate project presentation
├── Start-SentinelFIM.bat   ← One-click Windows launcher
│
├── watched_files/          ← Monitored folder (created at runtime)
├── trust_store.json        ← SHA-256 baseline (generated at runtime)
└── guardian_events.log     ← Audit trail (generated at runtime)
```

---

## 🚀 Quick Start

### Option 1 — GUI (Recommended)
```bash
python guardian_gui.py
```
1. Click **🔒 Build Trust Store** — fingerprints all files
2. Click **▶ Start Watching** — live monitoring begins
3. Edit any file in `watched_files/` — alert appears instantly

### Option 2 — Command Line
```bash
python fim_scanner.py
```
```
Enter 1 or 2:  1    ← build trust store
Enter 1 or 2:  2    ← start watching
```

### Option 3 — Windows Launcher
```
Double-click  Start-SentinelFIM.bat
```

---

## 🧪 Testing — Simulate Attacks

### Automated demo (5 attacks with countdown)
```bash
python live_demo.py
```

### Manual tamper + scan
```bash
# Step 1 — apply 5 attack types
python tamper_demo.py

# Step 2 — scan to catch them all
python fim_scanner.py   →  enter 2

# Step 3 — restore clean files
python tamper_demo.py --reset
```

### Attack types simulated

| Attack | What happens |
|---|---|
| `MODIFIED` | File content weakened (firewall rules, policy) |
| `DELETED` | File removed after exfiltration (api_keys.txt) |
| `NEW FILE` | Malware dropped into monitored folder |
| `RENAMED` | File disguised by changing extension |
| `CSV INJECT` | Fraudulent row added to employee database |

---

## 🔐 How It Works

```
Build Trust Store:
  walk watched_files/ → SHA-256 hash each file → save to trust_store.json

Start Watching (every 1 second):
  re-hash all files → compare with baseline
  ├── hash changed?     → MODIFIED alert
  ├── file gone?        → DELETED alert
  └── file not in base? → NEW FILE alert
  
  After each cycle: self.trusted = dict(live)
  → Same alert never fires twice
```

---

## 🛠️ Technology Stack

| Module | Role |
|---|---|
| `hashlib` | SHA-256 cryptographic fingerprinting |
| `tkinter` | Full GUI framework |
| `threading` | Background watcher thread (non-blocking) |
| `queue.Queue` | Thread-safe alert passing to GUI |
| `json` | Human-readable trust store storage |
| `os` / `shutil` | File system traversal and restoration |
| `time` | 1-second polling interval |
| `datetime` | Timestamps on all alerts and logs |

---

## 📊 GUI Overview

```
┌─────────────────────────────────────────────────────────┐
│  🛡️ GuardianEye — File Integrity Watcher        ● Watching │
├──────────────┬──────────────────────────────────────────┤
│ TRUST STORE  │  🔔 Live Alerts │ 📁 Files │ 📄 Log      │
│ ◉ 5 enrolled │ ─────────────────────────────────────── │
│              │  [~] MODIFIED • 16:05:42                 │
│ 🔒 Build     │      a.txt                               │
│ ▶ Start      │      stored:  f715b9ee...                │
│ ■ Stop       │      current: 30a827ac...                │
│              │                                          │
│ STATS        │  [-] DELETED  • 16:05:45                 │
│ Modified  2  │      b.txt                               │
│ Deleted   1  │                                          │
│ New File  1  │  [+] NEW FILE • 16:05:48                 │
│              │      malware_payload.exe.txt             │
│ 🗑 Clear     │                                          │
│ 📄 View Log  │                                          │
├──────────────┴──────────────────────────────────────────┤
│  All files intact — last check 16:06:00    2026-07-30   │
└─────────────────────────────────────────────────────────┘
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE)

---

## 🙏 Inspiration

Concept inspired by [joshmadakor1/PowerShell-Integrity-FIM](https://github.com/joshmadakor1/PowerShell-Integrity-FIM) — ported and significantly extended to Python with GUI, JSON baseline, rename detection, live demo scripts, and presentation generator.

---

<p align="center">Made with Python 🐍 | No dependencies | Standard library only</p>
