"""tools/backup.py — 运行时数据备份（每日定时）。

打包：journal（盈亏真值 append-only）、market_data.db（sqlite backup API，
WAL 安全）、server_offset.json → shenjiMT5_backups/backup_YYYYMMDD_HHMMSS.zip。
保留最近 14 份。注册：
  schtasks /Create /TN "ShenjiBackup" /SC DAILY /ST 20:00 /TR "python D:\\...\\tools\\backup.py" /F
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

BACKUP_DIR = os.path.join(os.path.dirname(REPO_ROOT), "shenjiMT5_backups")
KEEP_N = 14


def main() -> int:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = os.path.join(BACKUP_DIR, f"backup_{stamp}.zip")

    # sqlite 安全快照（WAL 活跃时也能一致拷贝）
    from config import settings
    snap = os.path.join(BACKUP_DIR, f"_db_snapshot_{stamp}.db")
    src = sqlite3.connect(settings.DB_PATH)
    dst = sqlite3.connect(snap)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()

    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snap, "market_data.db")
            journal = os.path.join(settings.JOURNAL_DIR, "closed_trades.jsonl")
            if os.path.exists(journal):
                z.write(journal, "journal/closed_trades.jsonl")
            if os.path.exists(settings.SERVER_OFFSET_PATH):
                z.write(settings.SERVER_OFFSET_PATH, "server_offset.json")
        print(f"备份完成 → {out} ({os.path.getsize(out) / 1024:.0f} KB)")
    finally:
        if os.path.exists(snap):
            os.remove(snap)

    # 保留最近 KEEP_N 份
    backups = sorted(f for f in os.listdir(BACKUP_DIR)
                     if f.startswith("backup_") and f.endswith(".zip"))
    for old in backups[:-KEEP_N]:
        os.remove(os.path.join(BACKUP_DIR, old))
        print(f"清理旧备份: {old}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
