import sqlite3
import re
from pathlib import Path


DB_PATH = Path("data_vault/sqlite/aria_memory.db")
RAW_DIR = Path("data_vault/raw")


def safe_filename(name: str) -> str:
    base = (name or "file").strip().replace("\\", "_").replace("/", "_")
    base = re.sub(r"[^\w\-. ()]+", "_", base)
    base = re.sub(r"\s+", " ", base).strip()
    return base[:180] if base else "file"


def main():
    if not DB_PATH.exists():
        print("DB not found.")
        return
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """
            SELECT id, name, path_or_url, source_type
            FROM assets
            WHERE deleted_at IS NULL AND source_type IN ('file', 'meeting', 'text')
            """
        )
        rows = cur.fetchall()

        renamed = 0
        for asset_id, name, path_or_url, source_type in rows:
            p = Path(path_or_url)
            if not p.exists():
                continue
            # Skip links and already-migrated names.
            if "__" in p.name:
                continue

            suffix = p.suffix
            if source_type == "text" and not suffix:
                suffix = ".txt"
            new_name = f"{asset_id}__{safe_filename(name)}"
            if suffix and not new_name.endswith(suffix):
                new_name += suffix
            new_path = RAW_DIR / new_name
            if new_path.exists():
                continue
            p.rename(new_path)
            conn.execute("UPDATE assets SET path_or_url = ? WHERE id = ?", (str(new_path), asset_id))
            renamed += 1
            print(f"Renamed: {p.name} -> {new_path.name}")

    print(f"Done. Renamed {renamed} file(s).")


if __name__ == "__main__":
    main()

