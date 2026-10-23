"""
Check YouTube upload schedule to ensure strictly alternate-day posting,
while Facebook posts every day.
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

# Ensure UTF-8 stdout on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HISTORY_FILE = Path(__file__).parent / "youtube_history.json"


def should_upload_youtube() -> bool:
    # 1. Check manual override input from GitHub Actions workflow_dispatch
    manual_choice = os.getenv("INPUT_UPLOAD_YOUTUBE", "").strip().lower()
    if manual_choice == "true":
        print("[schedule] Manual override: YouTube upload forced to TRUE.")
        return True
    elif manual_choice == "false":
        print("[schedule] Manual override: YouTube upload forced to FALSE.")
        return False

    # 2. Check persistent history file
    today_utc = datetime.now(timezone.utc).date()
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            last_date_str = data.get("last_upload_date")
            if last_date_str:
                last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
                diff_days = (today_utc - last_date).days

                print(f"[schedule] Today (UTC): {today_utc} | Last YouTube upload: {last_date} ({diff_days} day(s) ago)")

                if diff_days <= 0:
                    print(f"[schedule] [PAUSE] Already uploaded to YouTube today ({today_utc}). Skipping duplicate.")
                    return False
                elif diff_days == 1:
                    print(f"[schedule] [PAUSE] YouTube was uploaded yesterday ({last_date}). Today is an alternate OFF-day.")
                    print("[schedule] Skipping YouTube upload (Facebook will still post).")
                    return False
                else:
                    print(f"[schedule] [GO] Last YouTube upload was {diff_days} day(s) ago. Today is an alternate ON-day!")
                    return True
        except Exception as e:
            print(f"[schedule] Notice reading {HISTORY_FILE}: {e}")

    # 3. Fallback: Day of year parity (odd days upload, even days off)
    day_of_year = today_utc.timetuple().tm_yday
    is_alternate = (day_of_year % 2 != 0)
    print(f"[schedule] Day of Year: {day_of_year} (Parity fallback: {is_alternate})")
    if is_alternate:
        print(f"[schedule] [GO] Today is an alternate upload day (Day {day_of_year}).")
    else:
        print(f"[schedule] [PAUSE] Today is an alternate off-day (Day {day_of_year}). Skipping YouTube upload (Facebook will still upload).")
    return is_alternate


if __name__ == "__main__":
    upload = should_upload_youtube()
    val = "true" if upload else "false"

    # Set GitHub Actions output
    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"should_upload={val}\n")

    print(f"OUTPUT: should_upload={val}")
