"""
=============================================================================
  GuardianEye — File Integrity Watcher
  Author  : SentinelFIM Project
  Version : 1.0
  License : MIT
=============================================================================

  GuardianEye watches over your files and raises the alarm the moment
  anything changes — whether a file is quietly edited, deleted, or a
  suspicious new file appears out of nowhere.

  HOW IT WORKS
  ─────────────
  First run  →  Fingerprint every file with SHA-256 and record the
                snapshot as a JSON "trust store" (baseline.json)

  Later runs →  Re-fingerprint everything and compare against the
                trust store. Any mismatch is an integrity violation.

  WHAT IT CATCHES
  ────────────────
    ★  Modified files   — content changed since last snapshot
    ★  Deleted files    — file gone from the system
    ★  New files        — file that wasn't in the original snapshot
    ★  Live watch mode  — keeps re-checking every second until you stop it

  MENU
  ─────
    1 → Build a fresh trust store (fingerprint all files now)
    2 → Start watching (compare live state against trust store)

  Standard Python only — no third-party packages needed.
=============================================================================
"""

import os
import sys
import json
import hashlib
import time
from datetime import datetime

# ── Windows UTF-8 console fix ─────────────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# TERMINAL COLOUR PALETTE
# ─────────────────────────────────────────────────────────────────────────────
R   = "\033[91m"     # Red      → deleted / danger
Y   = "\033[93m"     # Yellow   → modified / warning
G   = "\033[92m"     # Green    → safe / new baseline
C   = "\033[96m"     # Cyan     → headers / info
W   = "\033[97m"     # White    → normal text
DIM = "\033[2m"      # Dim grey → secondary info
B   = "\033[1m"      # Bold
RST = "\033[0m"      # Reset all styles

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────
ROOT_DIR    = os.path.dirname(os.path.abspath(__file__))
WATCH_DIR   = os.path.join(ROOT_DIR, "watched_files")   # folder being monitored
STORE_FILE  = os.path.join(ROOT_DIR, "trust_store.json")  # saved fingerprints
EVENTS_LOG  = os.path.join(ROOT_DIR, "guardian_events.log")  # audit trail


# =============================================================================
# CORE — fingerprint a single file with SHA-256
# =============================================================================

def fingerprint(path):
    """
    Opens a file and computes its SHA-256 fingerprint.
    Reads in 64 KB blocks to handle files of any size without
    loading the whole thing into RAM at once.

    Returns the hex digest string, or None if the file is unreadable.
    """
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            while True:
                block = fh.read(65536)
                if not block:
                    break
                h.update(block)
        return h.hexdigest()
    except (IOError, OSError):
        return None


# =============================================================================
# CORE — walk the watched folder and fingerprint everything
# =============================================================================

def snapshot_directory():
    """
    Walks WATCH_DIR recursively and fingerprints every file it finds.

    Returns a dict where each key is a relative file path and the value
    is another dict holding the SHA-256 hash, file size, and scan time.

        {
          "a.txt": {
              "sha256": "abc123...",
              "size":   1024,
              "seen":   "2026-07-22T21:00:00"
          },
          ...
        }
    """
    records = {}

    for root, dirs, files in os.walk(WATCH_DIR):
        dirs.sort()
        for name in sorted(files):
            full_path = os.path.join(root, name)
            rel_path  = os.path.relpath(full_path, WATCH_DIR)

            digest = fingerprint(full_path)
            if digest is None:
                continue

            try:
                size = os.path.getsize(full_path)
            except OSError:
                size = 0

            records[rel_path] = {
                "sha256": digest,
                "size":   size,
                "seen":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

    return records


# =============================================================================
# TRUST STORE — save / load the baseline fingerprints
# =============================================================================

def save_trust_store(records):
    """
    Writes the fingerprint snapshot to trust_store.json.
    The JSON is human-readable (indented) so you can open it
    in Notepad and inspect every hash manually.
    """
    payload = {
        "guardian_eye":  "1.0",
        "captured_at":   datetime.now().isoformat(),
        "total_files":   len(records),
        "fingerprints":  records,
    }
    with open(STORE_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def load_trust_store():
    """
    Reads trust_store.json from disk.

    Returns (fingerprints_dict, captured_at_str).
    Returns (None, None) if the store does not exist yet.
    """
    if not os.path.exists(STORE_FILE):
        return None, None

    try:
        with open(STORE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("fingerprints", {}), data.get("captured_at", "unknown")
    except (json.JSONDecodeError, IOError) as err:
        print(f"\n  {Y}[!] Trust store is corrupted: {err}{RST}")
        return None, None


# =============================================================================
# EVENTS LOG — write every violation to the audit trail
# =============================================================================

def record_event(kind, relative_path, detail=""):
    """
    Appends a single event line to guardian_events.log.

    Format:
      [2026-07-22 21:00:00]  MODIFIED   subdir/file.txt   sha256 changed
    """
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}]  {kind:<12}  {relative_path}"
    if detail:
        line += f"   {detail}"
    with open(EVENTS_LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# =============================================================================
# DISPLAY — print one integrity alert to the terminal
# =============================================================================

def show_alert(kind, rel_path, extra=""):
    """
    Prints a colour-coded alert banner to the terminal.

    Colour rules:
      MODIFIED  → yellow  (content tampered)
      DELETED   → red     (file gone)
      NEW FILE  → green   (unexpected addition)
    """
    ts = datetime.now().strftime("%H:%M:%S")

    colours = {
        "MODIFIED": Y,
        "DELETED":  R,
        "NEW FILE": G,
    }
    icons = {
        "MODIFIED": "~",
        "DELETED":  "-",
        "NEW FILE": "+",
    }
    col  = colours.get(kind, W)
    icon = icons.get(kind, "?")

    print(f"\n  {col}{B}  [{icon}] {kind}  •  {ts}{RST}")
    print(f"  {col}      {rel_path}{RST}")
    if extra:
        print(f"  {DIM}      {extra}{RST}")

    record_event(kind, rel_path, extra)


# =============================================================================
# OPTION 1 — Build a fresh trust store
# =============================================================================

def build_trust_store():
    """
    Fingerprints every file in watched_files/ and writes the results
    to trust_store.json, replacing any previous snapshot.

    This is the 'enrol' step — run it once on a known-good system
    state, then use Option 2 to watch for deviations.
    """
    print(f"\n  {C}  Scanning watched_files/ and computing SHA-256 fingerprints...{RST}\n")

    records = snapshot_directory()

    if not records:
        print(f"  {Y}[!] No files found in watched_files/.{RST}")
        print(f"      Put some files in there first, then try again.\n")
        return

    for rel_path, info in sorted(records.items()):
        print(f"  {G}  ✓{RST}  {rel_path}")
        print(f"      {DIM}sha256 : {info['sha256']}{RST}")
        print(f"      {DIM}size   : {info['size']} bytes{RST}")

    save_trust_store(records)

    print()
    print(f"  {G}{B}  Trust store saved → trust_store.json  ({len(records)} file(s)){RST}")
    print(f"  {DIM}  Run this tool again and choose option 2 to start watching.{RST}\n")


# =============================================================================
# OPTION 2 — Start watching (continuous integrity checking)
# =============================================================================

def start_watching():
    """
    Loads the trust store then enters an infinite loop that re-fingerprints
    every file every second and reports violations immediately.

    Three kinds of violations are detected per loop iteration:
      MODIFIED  — file exists but SHA-256 no longer matches the trust store
      DELETED   — file from the trust store is no longer present on disk
      NEW FILE  — file on disk was not present when the trust store was built

    Press Ctrl+C to stop.
    """
    trusted, captured_at = load_trust_store()

    if trusted is None:
        print(f"\n  {R}[!] No trust store found.{RST}")
        print(f"      Choose option 1 first to build a baseline.\n")
        return

    total = len(trusted)
    print(f"\n  {G}{B}  Trust store loaded — {total} file(s) enrolled.{RST}")
    print(f"  {DIM}  Snapshot taken at: {captured_at}{RST}")
    print(f"\n  {C}  Watching for changes... Press Ctrl+C to stop.{RST}")
    print(f"  {DIM}  (Checks every 1 second){RST}\n")
    print(f"  {'─'*54}")

    violations_total = 0

    try:
        while True:
            time.sleep(1)

            live = snapshot_directory()
            cycle_violations = 0

            # ── Check: MODIFIED and NEW FILE ─────────────────────────────────
            for rel_path, live_info in live.items():
                if rel_path in trusted:
                    if trusted[rel_path]["sha256"] != live_info["sha256"]:
                        show_alert(
                            "MODIFIED", rel_path,
                            f"stored: {trusted[rel_path]['sha256'][:32]}...  "
                            f"current: {live_info['sha256'][:32]}..."
                        )
                        cycle_violations += 1
                else:
                    show_alert(
                        "NEW FILE", rel_path,
                        f"sha256: {live_info['sha256'][:48]}..."
                    )
                    cycle_violations += 1

            # ── Check: DELETED ────────────────────────────────────────────────
            for rel_path in trusted:
                full_path = os.path.join(WATCH_DIR, rel_path)
                if not os.path.exists(full_path):
                    show_alert(
                        "DELETED", rel_path,
                        "file no longer exists on disk"
                    )
                    cycle_violations += 1

            violations_total += cycle_violations

            if cycle_violations == 0:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"\r  {DIM}  [{ts}]  All {total} file(s) intact. Watching...{RST}",
                      end="", flush=True)

    except KeyboardInterrupt:
        print(f"\n\n  {C}  Watcher stopped.{RST}")
        print(f"  {B}  Session summary: {violations_total} violation(s) detected.{RST}")
        print(f"  {DIM}  Full audit trail → guardian_events.log{RST}\n")


# =============================================================================
# FIRST-TIME SETUP — create watched_files/ with demonstration files
# =============================================================================

def ensure_watch_dir():
    """
    Creates the watched_files/ folder with a set of sample files the
    first time the tool is run, so there is something to monitor
    straight away.

    Files are only created if the folder does not already exist or is empty.
    """
    if os.path.exists(WATCH_DIR) and os.listdir(WATCH_DIR):
        return   # folder already populated — nothing to do

    os.makedirs(WATCH_DIR, exist_ok=True)

    demo_files = {
        "a.txt": (
            "System configuration — version 4.1\n"
            "hostname  = prod-server-01\n"
            "region    = us-east-1\n"
            "debug     = false\n"
        ),
        "b.txt": (
            "Access control list\n"
            "admin   ALLOW ALL\n"
            "analyst ALLOW READ\n"
            "guest   DENY  WRITE\n"
        ),
        "c.txt": (
            "Deployment manifest\n"
            "image   = registry.io/app:v2.5\n"
            "replicas = 3\n"
            "port    = 8443\n"
        ),
        "d.txt": (
            "Audit seed — do not modify\n"
            "created = 2026-07-22\n"
            "owner   = security-team\n"
        ),
        os.path.join("sensitive", "credentials.txt"): (
            "# Demo credentials — not real\n"
            "db_user = app_user\n"
            "db_pass = ChangeMe123!\n"
        ),
    }

    print(f"\n  {C}  First run — creating watched_files/ with sample files...{RST}\n")
    for rel, content in demo_files.items():
        full = os.path.join(WATCH_DIR, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"  {G}  +{RST}  watched_files/{rel}")
    print()


# =============================================================================
# MAIN — show menu, dispatch to chosen option
# =============================================================================

def main():
    ensure_watch_dir()

    # ── Header ────────────────────────────────────────────────────────────────
    print()
    print(f"  {C}{'━'*54}{RST}")
    print(f"  {B}{W}        GuardianEye — File Integrity Watcher{RST}")
    print(f"  {C}{'━'*54}{RST}")
    print(f"  {DIM}  Watching : watched_files/{RST}")
    print(f"  {DIM}  Store    : trust_store.json  (SHA-256 fingerprints){RST}")
    print(f"  {DIM}  Log      : guardian_events.log{RST}")
    print(f"  {C}{'━'*54}{RST}")
    print()

    # ── Menu ──────────────────────────────────────────────────────────────────
    print(f"  What do you want to do?\n")
    print(f"    {G}1{RST}  →  Build a fresh trust store (fingerprint files now)")
    print(f"    {C}2{RST}  →  Start watching (compare against saved trust store)")
    print()

    choice = input("  Enter 1 or 2:  ").strip()
    print()

    if choice == "1":
        build_trust_store()
    elif choice == "2":
        start_watching()
    else:
        print(f"  {R}[!] '{choice}' is not a valid option. Please enter 1 or 2.{RST}\n")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n  {Y}  Exited.{RST}\n")
        sys.exit(0)
    except Exception as err:
        print(f"\n  {R}[ERROR]{RST}  {err}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
