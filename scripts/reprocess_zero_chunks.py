import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_backend.ingest import IngestionService
from data_backend.settings import load_settings
from data_backend.storage import MetadataStore


def main():
    settings = load_settings()
    store = MetadataStore(settings.sqlite_path)
    ingestor = IngestionService(settings, store)

    with sqlite3.connect(settings.sqlite_path) as conn:
        cur = conn.execute(
            """
            SELECT id, name
            FROM assets
            WHERE deleted_at IS NULL
              AND (chunk_count = 0 OR text_length = 0)
            ORDER BY created_at DESC
            """
        )
        rows = cur.fetchall()

    if not rows:
        print("No zero-chunk/zero-text assets found.")
        return

    print(f"Found {len(rows)} assets to reprocess")
    for asset_id, name in rows:
        item = ingestor.reprocess_asset(asset_id)
        if item:
            print(f"[OK] {name} -> text={item['text_length']} chunks={item['chunk_count']}")
        else:
            print(f"[FAIL] {name}")


if __name__ == "__main__":
    main()
