"""
=============================================================================
  SentinelFIM — Tamper Demo Script
=============================================================================
  Run this script AFTER the baseline has been created to simulate
  real-world file integrity attacks. Then run fim_scanner.py to catch them.

  Simulates:
    1. File Modification  — change content of an existing file
    2. File Deletion      — delete a file entirely
    3. New File Created   — drop a suspicious new file (like malware)
    4. File Rename        — rename a file to hide it

  Usage:
    python tamper_demo.py          → tamper ValidFiles (see alerts on good folder)
    python tamper_demo.py --reset  → restore files to their original clean state
=============================================================================
"""

import os
import sys
import shutil
import argparse
from datetime import datetime

# Fix Windows console UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
VALID_FOLDER  = os.path.join(BASE_DIR, "ValidFiles")
TAMPER_FOLDER = os.path.join(BASE_DIR, "TamperedFiles")

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"


# ─────────────────────────────────────────────────────────────────────────────
# RESTORE: Put files back to their original clean state
# ─────────────────────────────────────────────────────────────────────────────

def restore_files():
    """Rewrites all sample files back to their original clean content."""

    # Original content map — same as what fim_scanner.py creates
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
        os.path.join(VALID_FOLDER, "subdir", "audit_log.csv"): (
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

    print(f"\n  {CYAN}Restoring files to original clean state...{RESET}\n")

    # Remove leftover tamper artifacts
    for leftover in [
        os.path.join(VALID_FOLDER,  "malware_payload.exe.txt"),
        os.path.join(VALID_FOLDER,  "security_policy.txt.bak"),
        os.path.join(TAMPER_FOLDER, "update.exe.txt"),
        os.path.join(TAMPER_FOLDER, "access_control.json.bak"),
        os.path.join(TAMPER_FOLDER, "ransomware_note.txt"),
    ]:
        if os.path.exists(leftover):
            os.remove(leftover)
            print(f"  {RED}[-]{RESET} Removed leftover: {os.path.basename(leftover)}")

    # Rewrite every file to its original content
    for filepath, content in originals.items():
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  {GREEN}[✔]{RESET} Restored: {os.path.relpath(filepath, BASE_DIR)}")

    print(f"\n  {GREEN}All files restored to clean state.{RESET}")
    print(f"  {YELLOW}Run 'python fim_scanner.py --reset' then 'python fim_scanner.py'{RESET}")
    print(f"  {YELLOW}to create a fresh baseline.{RESET}\n")


# ─────────────────────────────────────────────────────────────────────────────
# TAMPER ATTACKS — each function simulates one type of attack
# ─────────────────────────────────────────────────────────────────────────────

def attack_modify_file():
    """
    ATTACK TYPE 1 — File Modification
    Simulates: an attacker editing a config/policy file to weaken security.
    Expected alert: [ALERT] File Modified
    """
    targets = [
        (
            os.path.join(VALID_FOLDER, "security_policy.txt"),
            (
                "CORPORATE SECURITY POLICY — v3.2 [TAMPERED]\n"
                "Last reviewed: 2026-07-21 (UNAUTHORIZED EDIT)\n\n"
                "1. Passwords must be >= 4 characters.\n"     # weakened!
                "2. MFA is now optional.\n"                   # disabled MFA!
                "3. Access logs retained for 1 day only.\n"   # shortened!
                "4. Encryption is optional.\n"                # removed!
            )
        ),
        (
            os.path.join(TAMPER_FOLDER, "firewall_rules.txt"),
            (
                "# Firewall Ruleset — MODIFIED BY ATTACKER\n"
                "ALLOW  0.0.0.0/0   ANY   ANY\n"   # allow everything!
                "# All DENY rules removed by attacker\n"
            )
        ),
    ]
    for filepath, new_content in targets:
        if os.path.exists(filepath):
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"  {RED}[M]{RESET} Modified : {os.path.relpath(filepath, BASE_DIR)}")


def attack_delete_file():
    """
    ATTACK TYPE 2 — File Deletion
    Simulates: an attacker deleting sensitive files (e.g. after exfiltration).
    Expected alert: [ALERT] File Deleted
    """
    targets = [
        os.path.join(TAMPER_FOLDER, "api_keys.txt"),        # deleted after stealing
        os.path.join(VALID_FOLDER,  "checksums.txt"),       # deleted to prevent verification
    ]
    for filepath in targets:
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"  {RED}[-]{RESET} Deleted  : {os.path.relpath(filepath, BASE_DIR)}")


def attack_create_file():
    """
    ATTACK TYPE 3 — New File Creation (Unauthorised)
    Simulates: malware dropped into a monitored directory.
    Expected alert: [ALERT] New File Detected
    """
    drops = {
        os.path.join(VALID_FOLDER,  "malware_payload.exe.txt"):
            "# SIMULATED MALWARE — this file should not exist here!\n"
            "cmd.exe /c net user hacker P@ssw0rd /add\n"
            "cmd.exe /c net localgroup administrators hacker /add\n",

        os.path.join(TAMPER_FOLDER, "ransomware_note.txt"):
            "YOUR FILES HAVE BEEN ENCRYPTED!\n"
            "Send 0.5 BTC to: 1FakeAddressXXXXXXXXXXXXX\n"
            "Contact: evil@example.com\n",
    }
    for filepath, content in drops.items():
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  {YELLOW}[+]{RESET} Created  : {os.path.relpath(filepath, BASE_DIR)}")


def attack_rename_file():
    """
    ATTACK TYPE 4 — File Rename
    Simulates: an attacker renaming a file to hide or disguise it.
    Expected alert: [ALERT] File Renamed
    """
    renames = [
        (
            os.path.join(VALID_FOLDER,  "security_policy.txt"),
            os.path.join(VALID_FOLDER,  "security_policy.txt.bak"),
        ),
        (
            os.path.join(TAMPER_FOLDER, "access_control.json"),
            os.path.join(TAMPER_FOLDER, "access_control.json.bak"),
        ),
    ]
    for src, dst in renames:
        if os.path.exists(src) and not os.path.exists(dst):
            os.rename(src, dst)
            print(f"  {CYAN}[R]{RESET} Renamed  : {os.path.basename(src)}  →  {os.path.basename(dst)}")


def attack_modify_database_csv():
    """
    ATTACK TYPE 5 — Insider Threat (database/CSV tampering)
    Simulates: an insider adding a fraudulent record to employee data.
    Expected alert: [ALERT] File Modified
    """
    target = os.path.join(TAMPER_FOLDER, "employee_data.csv")
    if os.path.exists(target):
        with open(target, "a", encoding="utf-8") as f:
            f.write("99,GHOST_USER,999999,Hidden\n")
        print(f"  {RED}[M]{RESET} Modified : {os.path.relpath(target, BASE_DIR)}  (fraudulent row added)")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SentinelFIM Tamper Demo — simulate file integrity attacks"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Restore all files to their original clean state."
    )
    args = parser.parse_args()

    print()
    print(f"  {CYAN}{'═' * 60}{RESET}")
    print(f"  {BOLD}   SentinelFIM — Attack Simulation Demo{RESET}")
    print(f"  {CYAN}{'═' * 60}{RESET}")
    print()

    if args.reset:
        restore_files()
        return

    # Check baseline exists before tampering
    baseline_path = os.path.join(BASE_DIR, "fim_baseline.json")
    if not os.path.exists(baseline_path):
        print(f"  {YELLOW}[!] No baseline found!{RESET}")
        print(f"      Run 'python fim_scanner.py' first to create a baseline.")
        print(f"      Then run this script to simulate attacks.\n")
        return

    # Run all attack simulations
    print(f"  {BOLD}Simulating 5 types of integrity attacks...{RESET}\n")

    print(f"  {RED}Attack 1 — File Modification (policy/config weakening){RESET}")
    attack_modify_file()
    print()

    print(f"  {RED}Attack 2 — File Deletion (post-exfiltration cleanup){RESET}")
    attack_delete_file()
    print()

    print(f"  {YELLOW}Attack 3 — Malicious File Creation (malware drop){RESET}")
    attack_create_file()
    print()

    print(f"  {CYAN}Attack 4 — File Rename (hiding/disguising files){RESET}")
    attack_rename_file()
    print()

    print(f"  {RED}Attack 5 — CSV Tampering (insider data fraud){RESET}")
    attack_modify_database_csv()
    print()

    print(f"  {CYAN}{'═' * 60}{RESET}")
    print(f"  {GREEN}{BOLD}All attacks applied!{RESET}")
    print()
    print(f"  Now run the scanner to catch them all:")
    print(f"  {BOLD}    python fim_scanner.py{RESET}")
    print()
    print(f"  Or use --quiet for alerts only:")
    print(f"  {BOLD}    python fim_scanner.py --quiet{RESET}")
    print(f"  {CYAN}{'═' * 60}{RESET}")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n  {YELLOW}Cancelled.{RESET}")
        sys.exit(0)
    except Exception as e:
        print(f"\n  {RED}[ERROR]{RESET} {e}")
        sys.exit(1)
