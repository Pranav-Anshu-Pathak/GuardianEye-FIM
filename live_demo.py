"""
=============================================================================
  SentinelFIM — LIVE ALERT DEMO
=============================================================================

  Runs everything in ONE terminal window:

    • Background thread scans files every 3 seconds
    • Main thread tampers one file at a time with pauses
    • Each tampering instantly triggers a live alert on screen

  Usage:
    python live_demo.py

  Press Ctrl+C at any time to stop.
=============================================================================
"""

import os
import sys
import json
import hashlib
import time
import threading
from datetime import datetime

# ── Windows UTF-8 fix ────────────────────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── ANSI colours ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
MAGENTA= "\033[95m"
WHITE  = "\033[97m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
VALID_FOLDER   = os.path.join(BASE_DIR, "ValidFiles")
TAMPER_FOLDER  = os.path.join(BASE_DIR, "TamperedFiles")
MONITOR_DIRS   = [VALID_FOLDER, TAMPER_FOLDER]
LOG_FILE       = os.path.join(BASE_DIR, "fim_live.log")

SCAN_INTERVAL  = 3      # seconds between each background scan
_baseline      = {}     # in-memory baseline (hash map)
_lock          = threading.Lock()   # protect shared baseline
_alert_count   = 0
_stop_event    = threading.Event()


# =============================================================================
# HASHING
# =============================================================================

def hash_file(filepath):
    """Returns {sha256, md5} for a file, reading in chunks."""
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                sha.update(chunk)
                md5.update(chunk)
        return sha.hexdigest(), md5.hexdigest()
    except OSError:
        return None, None


# =============================================================================
# SCAN — walk directories and return snapshot dict
# =============================================================================

def take_snapshot():
    """
    Walks all monitored directories and returns a dict:
      { "relative/path": {"sha256": "...", "md5": "..."} }
    """
    snapshot = {}
    for folder in MONITOR_DIRS:
        if not os.path.isdir(folder):
            continue
        for root, dirs, files in os.walk(folder):
            dirs.sort()
            for fname in sorted(files):
                full  = os.path.join(root, fname)
                rel   = os.path.relpath(full, BASE_DIR)
                sha, md5 = hash_file(full)
                if sha:
                    snapshot[rel] = {"sha256": sha, "md5": md5}
    return snapshot


# =============================================================================
# COMPARE — find what changed between two snapshots
# =============================================================================

def compare_snapshots(old, new):
    """
    Returns lists of (label, path, extra_info) tuples for every change.
    Labels:  MODIFIED | DELETED | NEW FILE | RENAMED
    """
    alerts = []

    # Build reverse map for rename detection
    old_hash_to_path = {}
    for path, info in old.items():
        h = info["sha256"]
        old_hash_to_path.setdefault(h, []).append(path)

    accounted = set()

    for path, info in new.items():
        h = info["sha256"]
        if path in old:
            accounted.add(path)
            if old[path]["sha256"] != h:
                alerts.append(("MODIFIED", path,
                    f"sha256 changed → {h[:20]}..."))
        else:
            # Could be a rename
            if h in old_hash_to_path:
                for old_path in old_hash_to_path[h]:
                    if old_path not in accounted:
                        alerts.append(("RENAMED", old_path,
                            f"→  {path}"))
                        accounted.add(old_path)
                        break
                else:
                    alerts.append(("NEW FILE", path,
                        f"sha256={h[:20]}..."))
            else:
                alerts.append(("NEW FILE", path,
                    f"sha256={h[:20]}..."))

    renamed_old = {a[1] for a in alerts if a[0] == "RENAMED"}
    for path in old:
        if path not in accounted and path not in renamed_old:
            alerts.append(("DELETED", path, "file no longer exists"))

    return alerts


# =============================================================================
# ALERT DISPLAY
# =============================================================================

def alert_colour(label):
    return {
        "MODIFIED": RED,
        "DELETED":  RED,
        "NEW FILE": YELLOW,
        "RENAMED":  CYAN,
    }.get(label, WHITE)


def alert_icon(label):
    return {
        "MODIFIED": "[M]",
        "DELETED":  "[-]",
        "NEW FILE": "[+]",
        "RENAMED":  "[R]",
    }.get(label, "[?]")


def print_alert(label, path, extra):
    global _alert_count
    _alert_count += 1
    ts     = datetime.now().strftime("%H:%M:%S")
    colour = alert_colour(label)
    icon   = alert_icon(label)

    # Prominent live alert banner
    print(f"\n  {colour}{BOLD}{'─' * 62}{RESET}")
    print(f"  {colour}{BOLD}  {icon} LIVE ALERT #{_alert_count}  [{ts}]{RESET}")
    print(f"  {colour}{BOLD}      {label:<12}  {path}{RESET}")
    if extra:
        print(f"  {colour}      {extra}{RESET}")
    print(f"  {colour}{BOLD}{'─' * 62}{RESET}\n")

    # Log to file
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] [{label}]  {path}  |  {extra}\n")


# =============================================================================
# BACKGROUND MONITOR THREAD
# =============================================================================

def monitor_loop():
    """
    Runs in a background thread.
    Every SCAN_INTERVAL seconds it takes a new snapshot and compares
    it against the in-memory baseline. Any changes trigger live alerts.
    """
    global _baseline

    while not _stop_event.is_set():
        time.sleep(SCAN_INTERVAL)

        if _stop_event.is_set():
            break

        new_snapshot = take_snapshot()

        with _lock:
            current_base = dict(_baseline)

        if not current_base:
            # Baseline not ready yet
            continue

        alerts = compare_snapshots(current_base, new_snapshot)

        if alerts:
            for label, path, extra in alerts:
                print_alert(label, path, extra)

            # Update baseline so the same change isn't re-reported
            with _lock:
                _baseline = new_snapshot


# =============================================================================
# RESTORE — put files back to clean originals
# =============================================================================

def restore_all_files():
    """Rewrites every sample file to its original, pristine content."""
    originals = {
        os.path.join(VALID_FOLDER, "security_policy.txt"): (
            "CORPORATE SECURITY POLICY — v3.2\n"
            "Last reviewed: 2026-06-01\n\n"
            "1. All passwords must be >= 12 characters.\n"
            "2. MFA is mandatory for all admin accounts.\n"
            "3. Access logs are retained for 90 days.\n"
            "4. Encryption at rest is required for PII data.\n"
        ),
        os.path.join(VALID_FOLDER, "server_config.ini"): (
            "[database]\n"
            "host     = 10.0.0.5\n"
            "port     = 5432\n"
            "name     = prod_db\n"
            "ssl_mode = require\n\n"
            "[cache]\n"
            "host = 10.0.0.6\n"
            "port = 6379\n"
        ),
        os.path.join(VALID_FOLDER, "checksums.txt"): (
            "# Official release checksums — do not edit\n"
            "app_v2.1.tar.gz  sha256=a3f1...\n"
            "agent_v1.0.deb   sha256=b9c2...\n"
        ),
        os.path.join(os.path.join(VALID_FOLDER, "subdir"), "audit_log.csv"): (
            "timestamp,user,action,result\n"
            "2026-07-01 08:00:00,admin,login,success\n"
            "2026-07-01 08:05:12,admin,export_report,success\n"
            "2026-07-01 09:30:00,analyst,view_alerts,success\n"
        ),
        os.path.join(TAMPER_FOLDER, "employee_data.csv"): (
            "id,name,salary,department\n"
            "1,Alice Johnson,75000,Engineering\n"
            "2,Bob Smith,68000,Marketing\n"
            "3,Carol Lee,82000,Security\n"
        ),
        os.path.join(TAMPER_FOLDER, "firewall_rules.txt"): (
            "# Firewall Ruleset — PRODUCTION\n"
            "ALLOW  10.0.0.0/8  ANY   ANY\n"
            "ALLOW  192.168.1.0/24 TCP 443\n"
            "DENY   0.0.0.0/0   ANY   ANY\n"
        ),
        os.path.join(TAMPER_FOLDER, "api_keys.txt"): (
            "# API Keys — CONFIDENTIAL\n"
            "stripe_key = sk_live_XXXXXXXXXXXXXXXXXXXX\n"
            "sendgrid   = SG.XXXXXXXXXXXXXXXXXXXXXXXX\n"
            "maps_api   = AIzaSyXXXXXXXXXXXXXXXXXXXX\n"
        ),
        os.path.join(TAMPER_FOLDER, "access_control.json"): (
            '{\n'
            '  "admin": {"level": 5, "can_delete": true},\n'
            '  "analyst": {"level": 2, "can_delete": false},\n'
            '  "readonly": {"level": 1, "can_delete": false}\n'
            '}\n'
        ),
    }

    for leftover_name in [
        "malware_payload.exe.txt", "security_policy.txt.bak",
        "ransomware_note.txt", "update.exe.txt",
        "access_control.json.bak", "suspicious_script.py"
    ]:
        for folder in [VALID_FOLDER, TAMPER_FOLDER]:
            lp = os.path.join(folder, leftover_name)
            if os.path.exists(lp):
                os.remove(lp)

    for filepath, content in originals.items():
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)


# =============================================================================
# COUNTDOWN HELPER
# =============================================================================

def countdown(seconds, message):
    """Prints a live countdown so you know when the next attack fires."""
    for i in range(seconds, 0, -1):
        sys.stdout.write(f"\r  {DIM}  {message} in {i}s...  {RESET}")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\r" + " " * 60 + "\r")   # clear the line


# =============================================================================
# ATTACK SEQUENCE — fired one at a time with pauses
# =============================================================================

def run_attacks():
    """
    Applies 6 attacks one at a time, with a countdown between each.
    The background monitor thread will catch and display each one live.
    """
    attacks = [
        # (delay_before, description, function)
        (
            5,
            "Attack 1/6 — File Modification: weakening security_policy.txt",
            lambda: _write(
                os.path.join(VALID_FOLDER, "security_policy.txt"),
                "CORPORATE SECURITY POLICY — TAMPERED!\n"
                "Passwords: 1 character minimum.\n"
                "MFA: disabled.\n"
                "Logs: deleted daily.\n"
            )
        ),
        (
            6,
            "Attack 2/6 — Firewall Misconfiguration: opening all ports",
            lambda: _write(
                os.path.join(TAMPER_FOLDER, "firewall_rules.txt"),
                "# FIREWALL RULES — COMPROMISED\n"
                "ALLOW 0.0.0.0/0 ANY ANY\n"
                "# All deny rules removed!\n"
            )
        ),
        (
            6,
            "Attack 3/6 — File Deletion: removing api_keys.txt (exfiltration)",
            lambda: _delete(os.path.join(TAMPER_FOLDER, "api_keys.txt"))
        ),
        (
            6,
            "Attack 4/6 — Malware Drop: creating malware_payload.exe.txt",
            lambda: _write(
                os.path.join(VALID_FOLDER, "malware_payload.exe.txt"),
                "# SIMULATED MALWARE\n"
                "cmd.exe /c net user hacker P@ss /add\n"
                "cmd.exe /c net localgroup administrators hacker /add\n"
            )
        ),
        (
            6,
            "Attack 5/6 — Insider Threat: injecting row into employee_data.csv",
            lambda: _append(
                os.path.join(TAMPER_FOLDER, "employee_data.csv"),
                "99,GHOST_USER,999999,Hidden\n"
            )
        ),
        (
            6,
            "Attack 6/6 — File Rename: hiding access_control.json as .bak",
            lambda: _rename(
                os.path.join(TAMPER_FOLDER, "access_control.json"),
                os.path.join(TAMPER_FOLDER, "access_control.json.bak"),
            )
        ),
    ]

    for delay, description, attack_fn in attacks:
        countdown(delay, description)
        print(f"\n  {MAGENTA}{BOLD}  ⚡ ATTACKING: {description}{RESET}")
        attack_fn()
        # Give the monitor thread time to pick it up
        time.sleep(0.5)


# ── File operation helpers ────────────────────────────────────────────────────

def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def _append(path, content):
    if os.path.exists(path):
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)

def _delete(path):
    if os.path.exists(path):
        os.remove(path)

def _rename(src, dst):
    if os.path.exists(src) and not os.path.exists(dst):
        os.rename(src, dst)


# =============================================================================
# MAIN
# =============================================================================

def main():
    global _baseline

    print()
    print(f"  {CYAN}{'═' * 62}{RESET}")
    print(f"  {BOLD}{WHITE}   SentinelFIM — LIVE INTEGRITY MONITOR + ATTACK DEMO{RESET}")
    print(f"  {CYAN}{'═' * 62}{RESET}")
    print()
    print(f"  {DIM}  Scan interval : every {SCAN_INTERVAL} seconds{RESET}")
    print(f"  {DIM}  Log file      : fim_live.log{RESET}")
    print(f"  {DIM}  Press Ctrl+C to stop at any time{RESET}")
    print()

    # ── Step 1: Ensure sample folders exist and are clean ────────────────────
    print(f"  {CYAN}[SETUP]{RESET} Restoring files to clean state...")
    os.makedirs(VALID_FOLDER,  exist_ok=True)
    os.makedirs(TAMPER_FOLDER, exist_ok=True)
    os.makedirs(os.path.join(VALID_FOLDER, "subdir"), exist_ok=True)
    restore_all_files()
    print(f"  {GREEN}[OK]{RESET}    Files restored.\n")

    # ── Step 2: Take initial baseline snapshot ───────────────────────────────
    print(f"  {CYAN}[BASELINE]{RESET} Scanning files and creating in-memory baseline...")
    with _lock:
        _baseline = take_snapshot()
    total = len(_baseline)
    print(f"  {GREEN}[OK]{RESET}       Baseline set with {BOLD}{total}{RESET} file(s).\n")

    for rel_path in sorted(_baseline):
        sha = _baseline[rel_path]["sha256"][:20]
        folder_tag = f"{GREEN}VALID   {RESET}" if "ValidFiles" in rel_path else f"{YELLOW}TAMPERED{RESET}"
        print(f"   {folder_tag}  {DIM}{rel_path:<44}{RESET}  sha256: {sha}...")
    print()

    # ── Step 3: Start background monitor ─────────────────────────────────────
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()

    print(f"  {GREEN}{BOLD}  ✔ Live monitor started! Watching for changes...{RESET}")
    print(f"  {DIM}  (Scanner checks every {SCAN_INTERVAL}s — alerts appear within {SCAN_INTERVAL} seconds of tampering){RESET}")
    print()
    print(f"  {CYAN}{'─' * 62}{RESET}")
    print(f"  {BOLD}  STARTING ATTACK SEQUENCE — 6 attacks incoming...{RESET}")
    print(f"  {CYAN}{'─' * 62}{RESET}\n")

    # ── Step 4: Fire attacks one by one ──────────────────────────────────────
    try:
        run_attacks()

        # Wait for last scan to catch the final attack
        print(f"\n  {DIM}  Waiting for monitor to catch final attack...{RESET}")
        time.sleep(SCAN_INTERVAL + 1)

        print(f"\n  {CYAN}{'═' * 62}{RESET}")
        print(f"  {GREEN}{BOLD}  DEMO COMPLETE{RESET}")
        print(f"  {BOLD}  Total alerts triggered: {_alert_count}{RESET}")
        print(f"  {DIM}  Full log saved → {LOG_FILE}{RESET}")
        print(f"  {CYAN}{'═' * 62}{RESET}\n")

    except KeyboardInterrupt:
        pass
    finally:
        _stop_event.set()
        print(f"\n  {YELLOW}Monitor stopped. {_alert_count} alert(s) detected this session.{RESET}\n")


if __name__ == "__main__":
    main()
