import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    data_vault_root: Path
    sqlite_path: Path
    chroma_path: Path
    embed_model: str
    max_chunk_tokens: int
    chunk_overlap: int


def load_settings() -> Settings:
    data_vault_root = Path(os.getenv("DATA_VAULT_ROOT", "D:/AI/Project_Aria/data_vault"))
    sqlite_path = Path(os.getenv("SQLITE_PATH", str(data_vault_root / "sqlite" / "aria_memory.db")))
    chroma_path = Path(os.getenv("CHROMA_PATH", str(data_vault_root / "chroma")))
    embed_model = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
    max_chunk_tokens = int(os.getenv("MAX_CHUNK_TOKENS", "700"))
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "120"))

    data_vault_root.mkdir(parents=True, exist_ok=True)
    (data_vault_root / "raw").mkdir(parents=True, exist_ok=True)
    (data_vault_root / "processed").mkdir(parents=True, exist_ok=True)
    chroma_path.mkdir(parents=True, exist_ok=True)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    return Settings(
        data_vault_root=data_vault_root,
        sqlite_path=sqlite_path,
        chroma_path=chroma_path,
        embed_model=embed_model,
        max_chunk_tokens=max_chunk_tokens,
        chunk_overlap=chunk_overlap,
    )
