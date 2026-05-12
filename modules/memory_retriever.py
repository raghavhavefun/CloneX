import os
import sqlite3
import time
import re
from pathlib import Path
from rapidfuzz import fuzz


class MemoryRetriever:
    """
    Retrieves relevant chunks from the Data Vault Chroma index.
    Safe fallback: returns [] if index/model is unavailable.
    """

    def __init__(self, top_k=5):
        self.top_k = top_k
        self._ready = False
        self._collection = None
        self._embedder = None
        self._init_error = None
        self._profile_cache = ""
        self._profile_cache_ts = 0.0
        self._init()

    def _init(self):
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            from sentence_transformers import SentenceTransformer
        except Exception as e:
            self._init_error = f"import_error: {e}"
            return

        try:
            chroma_path = Path(os.getenv("CHROMA_PATH", "D:/AI/Project_Aria/data_vault/chroma"))
            if not chroma_path.exists():
                self._init_error = "chroma_path_missing"
                return

            embed_model = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
            client = chromadb.PersistentClient(
                path=str(chroma_path),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = client.get_or_create_collection(name="aria_memory")
            self._embedder = SentenceTransformer(embed_model)
            self._ready = True
        except Exception as e:
            self._init_error = f"init_error: {e}"
            self._ready = False

    def retrieve(self, query_text: str, top_k: int | None = None, owner_email: str | None = None):
        if not self._ready or not self._embedder or not self._collection or not query_text or not query_text.strip():
            return []

        try:
            qvec = self._embedder.encode([query_text], normalize_embeddings=True).tolist()  # type: ignore
            query_kwargs = {
                "query_embeddings": qvec,
                "n_results": top_k or self.top_k,
                "include": ["documents", "metadatas", "distances"],
            }
            if owner_email:
                query_kwargs["where"] = {"owner_email": owner_email}
            out = self._collection.query(
                **query_kwargs,
            )
            docs = out.get("documents", [[]])[0]  # type: ignore
            metas = out.get("metadatas", [[]])[0]  # type: ignore
            dists = out.get("distances", [[]])[0]  # type: ignore

            items = []
            for i, doc in enumerate(docs):
                meta = metas[i] if i < len(metas) and metas[i] else {}
                dist = dists[i] if i < len(dists) else None
                item = (
                    {
                        "text": doc or "",
                        "source_type": meta.get("source_type", ""),
                        "name": meta.get("name", ""),
                        "mime": meta.get("mime", ""),
                        "distance": dist,
                    }
                )
                items.append(item)
            return items
        except Exception:
            return []

    def get_profile_context(self, max_items: int = 8, cache_ttl_sec: int = 90, owner_email: str | None = None) -> str:
        """
        Lightweight always-on user context from SQLite metadata.
        Cached to avoid query overhead on every answer.
        """
        now = time.time()
        if self._profile_cache and (now - self._profile_cache_ts) < cache_ttl_sec:
            return self._profile_cache

        sqlite_path = Path(os.getenv("SQLITE_PATH", "D:/AI/Project_Aria/data_vault/sqlite/aria_memory.db"))
        if not sqlite_path.exists():
            return ""

        try:
            with sqlite3.connect(sqlite_path) as conn:
                if owner_email:
                    cur = conn.execute(
                        """
                        SELECT source_type, name, created_at
                        FROM assets
                        WHERE deleted_at IS NULL AND lower(owner_email)=lower(?)
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (owner_email, max_items),
                    )
                else:
                    cur = conn.execute(
                        """
                        SELECT source_type, name, created_at
                        FROM assets
                        WHERE deleted_at IS NULL
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (max_items,),
                    )
                rows = cur.fetchall()
            if not rows:
                return ""

            lines = []
            for idx, row in enumerate(rows, start=1):
                source_type, name, created_at = row
                lines.append(f"[{idx}] {source_type} | {name} | {created_at}")
            self._profile_cache = "\n".join(lines)
            self._profile_cache_ts = now
            return self._profile_cache
        except Exception:
            return ""

    def find_asset_ids_by_name(self, name_hint: str, max_items: int = 5, owner_email: str | None = None) -> list[str]:
        sqlite_path = Path(os.getenv("SQLITE_PATH", "D:/AI/Project_Aria/data_vault/sqlite/aria_memory.db"))
        if not sqlite_path.exists():
            return []
        hint = (name_hint or "").strip()
        if not hint:
            return []
        # Keep only readable filename-ish characters for safe LIKE query.
        hint = re.sub(r"[^a-zA-Z0-9._ -]+", "", hint)
        if not hint:
            return []
        try:
            with sqlite3.connect(sqlite_path) as conn:
                if owner_email:
                    cur = conn.execute(
                        """
                        SELECT id
                        FROM assets
                        WHERE deleted_at IS NULL
                          AND lower(owner_email)=lower(?)
                          AND lower(source_type) NOT LIKE 'automation%'
                          AND lower(name) LIKE '%' || lower(?) || '%'
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (owner_email, hint, max_items),
                    )
                else:
                    cur = conn.execute(
                        """
                        SELECT id
                        FROM assets
                        WHERE deleted_at IS NULL
                          AND lower(source_type) NOT LIKE 'automation%'
                          AND lower(name) LIKE '%' || lower(?) || '%'
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (hint, max_items),
                    )
                rows = cur.fetchall()
                ids = [r[0] for r in rows]
                if ids:
                    return ids

                # Fuzzy fallback when user says approximate filename.
                if owner_email:
                    cur = conn.execute(
                        """
                        SELECT id, name
                        FROM assets
                        WHERE deleted_at IS NULL
                          AND lower(owner_email)=lower(?)
                          AND lower(source_type) NOT LIKE 'automation%'
                        ORDER BY created_at DESC
                        LIMIT 200
                        """,
                        (owner_email,),
                    )
                else:
                    cur = conn.execute(
                        """
                        SELECT id, name
                        FROM assets
                        WHERE deleted_at IS NULL
                          AND lower(source_type) NOT LIKE 'automation%'
                        ORDER BY created_at DESC
                        LIMIT 200
                        """
                    )
                candidates = cur.fetchall()
            scored = []
            for aid, aname in candidates:
                score = fuzz.partial_ratio(hint.lower(), (aname or "").lower())
                if score >= 60:
                    scored.append((score, aid))
            scored.sort(reverse=True)
            return [aid for _, aid in scored[:max_items]]
        except Exception:
            return []

    def get_recent_asset_ids(self, max_items: int = 3, owner_email: str | None = None) -> list[str]:
        sqlite_path = Path(os.getenv("SQLITE_PATH", "D:/AI/Project_Aria/data_vault/sqlite/aria_memory.db"))
        if not sqlite_path.exists():
            return []
        try:
            with sqlite3.connect(sqlite_path) as conn:
                if owner_email:
                    cur = conn.execute(
                        """
                        SELECT id
                        FROM assets
                        WHERE deleted_at IS NULL
                          AND lower(owner_email)=lower(?)
                          AND lower(source_type) NOT LIKE 'automation%'
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (owner_email, max_items),
                    )
                else:
                    cur = conn.execute(
                        """
                        SELECT id
                        FROM assets
                        WHERE deleted_at IS NULL
                          AND lower(source_type) NOT LIKE 'automation%'
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (max_items,),
                    )
                rows = cur.fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    def get_recent_pdf_asset_ids(self, max_items: int = 8, owner_email: str | None = None) -> list[str]:
        sqlite_path = Path(os.getenv("SQLITE_PATH", "D:/AI/Project_Aria/data_vault/sqlite/aria_memory.db"))
        if not sqlite_path.exists():
            return []
        try:
            with sqlite3.connect(sqlite_path) as conn:
                if owner_email:
                    cur = conn.execute(
                        """
                        SELECT id
                        FROM assets
                        WHERE deleted_at IS NULL
                          AND lower(owner_email)=lower(?)
                          AND lower(source_type) NOT LIKE 'automation%'
                          AND (
                            lower(mime) LIKE 'application/pdf%'
                            OR lower(name) LIKE '%.pdf'
                          )
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (owner_email, max_items),
                    )
                else:
                    cur = conn.execute(
                        """
                        SELECT id
                        FROM assets
                        WHERE deleted_at IS NULL
                          AND lower(source_type) NOT LIKE 'automation%'
                          AND (
                            lower(mime) LIKE 'application/pdf%'
                            OR lower(name) LIKE '%.pdf'
                          )
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (max_items,),
                    )
                rows = cur.fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    def get_recent_image_asset_ids(self, max_items: int = 5, owner_email: str | None = None) -> list[str]:
        sqlite_path = Path(os.getenv("SQLITE_PATH", "D:/AI/Project_Aria/data_vault/sqlite/aria_memory.db"))
        if not sqlite_path.exists():
            return []
        try:
            with sqlite3.connect(sqlite_path) as conn:
                if owner_email:
                    cur = conn.execute(
                        """
                        SELECT id
                        FROM assets
                        WHERE deleted_at IS NULL
                          AND lower(owner_email)=lower(?)
                          AND lower(source_type) NOT LIKE 'automation%'
                          AND (
                            lower(mime) LIKE 'image/%'
                            OR lower(name) LIKE '%.png'
                            OR lower(name) LIKE '%.jpg'
                            OR lower(name) LIKE '%.jpeg'
                            OR lower(name) LIKE '%.webp'
                          )
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (owner_email, max_items),
                    )
                else:
                    cur = conn.execute(
                        """
                        SELECT id
                        FROM assets
                        WHERE deleted_at IS NULL
                          AND lower(source_type) NOT LIKE 'automation%'
                          AND (
                            lower(mime) LIKE 'image/%'
                            OR lower(name) LIKE '%.png'
                            OR lower(name) LIKE '%.jpg'
                            OR lower(name) LIKE '%.jpeg'
                            OR lower(name) LIKE '%.webp'
                          )
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (max_items,),
                    )
                rows = cur.fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    def retrieve_for_asset_ids(self, asset_ids: list[str], per_asset_limit: int = 3) -> list[dict]:
        if not self._ready or not self._collection or not asset_ids:
            return []
        items = []
        for aid in asset_ids:
            try:
                out = self._collection.get(
                    where={"asset_id": aid},
                    include=["ids", "documents", "metadatas"],  # type: ignore
                    limit=per_asset_limit,
                )
            except Exception:
                continue
            ids = out.get("ids", []) or []
            docs = out.get("documents", []) or []
            metas = out.get("metadatas", []) or []
            zipped = []
            for idx, doc in enumerate(docs):
                chunk_id = ids[idx] if idx < len(ids) else ""
                meta = metas[idx] if idx < len(metas) and metas[idx] else {}
                try:
                    chunk_idx = int(str(chunk_id).rsplit(":", 1)[-1])
                except Exception:
                    chunk_idx = idx
                zipped.append((chunk_idx, doc, meta))
            zipped.sort(key=lambda x: x[0])
            for chunk_idx, doc, meta in zipped:
                items.append(
                    {
                        "text": doc or "",
                        "source_type": meta.get("source_type", ""),
                        "name": meta.get("name", ""),
                        "mime": meta.get("mime", ""),
                        "chunk_index": chunk_idx,
                        "distance": None,
                    }
                )
        return items
