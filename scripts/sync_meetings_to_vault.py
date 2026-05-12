from dotenv import load_dotenv

from data_backend.ingest import IngestionService
from data_backend.settings import load_settings
from data_backend.storage import MetadataStore


def main():
    load_dotenv()
    settings = load_settings()
    store = MetadataStore(settings.sqlite_path)
    ingestor = IngestionService(settings, store)

    from pathlib import Path

    meetings_dir = Path("meetings")
    if not meetings_dir.exists():
        print("No meetings directory found.")
        return

    ingested = 0
    for folder in sorted(meetings_dir.iterdir()):
        if not folder.is_dir():
            continue
        for filename in ["transcript.txt", "summary.md", "notes.json"]:
            fp = folder / filename
            if not fp.exists():
                continue
            ingestor.ingest_file(fp.read_bytes(), f"{folder.name}_{filename}", source_type="meeting")
            ingested += 1

    print(f"Ingested meeting artifacts: {ingested}")


if __name__ == "__main__":
    main()
