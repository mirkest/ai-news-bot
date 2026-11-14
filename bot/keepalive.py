"""Держит репозиторий «живым», чтобы GitHub не отключил расписание.

GitHub выключает cron в репозитории, где 60 дней не было коммитов.
Файл .keepalive обновляется раз в месяц — этого достаточно.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKER = ROOT / ".keepalive"


def main():
    stamp = time.strftime("%Y-%m")
    current = MARKER.read_text(encoding="utf-8").strip() if MARKER.exists() else ""
    if current == stamp:
        print(f"[keepalive] {stamp} уже записан")
        return
    MARKER.write_text(stamp + "\n", encoding="utf-8")
    print(f"[keepalive] обновлён: {stamp}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
