"""OpenCode history provider.

Verified against OpenCode 1.18.34 (see docs/OPENCODE_HISTORY.md).
Storage: SQLite database located via the official `opencode db path` command,
falling back to the known data directory. Access is strictly READ-ONLY; the
official `opencode export <id>` CLI is used for full transcripts.
"""
import json
import sqlite3
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

from ..execution.process import run_command
from .base import (
    HistoryHit,
    HistoryProvider,
    HistoryProviderError,
    SessionInfo,
    tokenize_query,
)

_DEFAULT_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def _to_uri(path: Path) -> str:
    # mode=ro: the connection is enforced read-only by SQLite itself —
    # AIOS can never write opencode.db, -wal, or -shm through this handle.
    return "file:" + quote(path.as_posix(), safe="/:") + "?mode=ro"


class OpenCodeHistoryProvider(HistoryProvider):
    name = "opencode"

    def __init__(self, config: dict = None, db_path: str = ""):
        self.config = config or {}
        self._db_path = self._resolve_db_path(db_path)

    # ------------------------------------------------------------------ setup
    def _resolve_db_path(self, configured: str) -> Path:
        candidates = []
        if configured:
            candidates.append(Path(configured))
        # Official CLI is the source of truth for the current installation.
        try:
            r = run_command(["opencode", "db", "path"], timeout=20)
            if r.success and r.stdout.strip():
                candidates.append(Path(r.stdout.strip().splitlines()[-1]))
        except Exception:
            pass
        candidates.append(_DEFAULT_DB)

        for p in candidates:
            try:
                if p.exists():
                    return p
            except OSError:
                continue
        raise HistoryProviderError(
            "OpenCode history database not found. Tried: "
            + ", ".join(str(p) for p in candidates)
            + ". Run `opencode db path` to confirm the installation."
        )

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(_to_uri(self._db_path), uri=True, timeout=10)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            raise HistoryProviderError(
                f"Cannot open OpenCode history read-only at {self._db_path}: {e}"
            )

    # ---------------------------------------------------------------- queries
    def list_sessions(self, limit: Optional[int] = None) -> List[SessionInfo]:
        sql = (
            "SELECT id, title, slug, directory, project_id, version, "
            "time_created, time_updated FROM session "
            "ORDER BY time_updated DESC"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        try:
            with self._connect() as conn:
                rows = conn.execute(sql).fetchall()
        except sqlite3.Error as e:
            raise HistoryProviderError(f"list_sessions failed: {e}")
        return [self._row_to_session(r) for r in rows]

    @staticmethod
    def _row_to_session(r) -> SessionInfo:
        return SessionInfo(
            id=r["id"],
            title=r["title"] or "",
            slug=r["slug"] or "",
            directory=r["directory"] or "",
            project_id=r["project_id"] or "",
            version=r["version"] or "",
            time_created=r["time_created"] or 0,
            time_updated=r["time_updated"] or 0,
        )

    def get_session(self, session_id: str) -> dict:
        try:
            with self._connect() as conn:
                srow = conn.execute(
                    "SELECT id, title, slug, directory, project_id, version, "
                    "time_created, time_updated FROM session WHERE id=?",
                    (session_id,),
                ).fetchone()
                if not srow:
                    raise HistoryProviderError(f"Session not found: {session_id}")
                msgs = conn.execute(
                    "SELECT id, data, time_created FROM message "
                    "WHERE session_id=? ORDER BY time_created",
                    (session_id,),
                ).fetchall()
                parts = conn.execute(
                    "SELECT id, message_id, data, time_created FROM part "
                    "WHERE session_id=? ORDER BY time_created",
                    (session_id,),
                ).fetchall()
        except sqlite3.Error as e:
            raise HistoryProviderError(f"get_session failed: {e}")

        parts_by_msg: dict = {}
        for p in parts:
            try:
                pdata = json.loads(p["data"])
            except (ValueError, TypeError):
                continue
            parts_by_msg.setdefault(p["message_id"], []).append({
                "id": p["id"],
                "type": pdata.get("type", "unknown"),
                "text": pdata.get("text") or "",
                "time": p["time_created"],
            })

        messages = []
        for m in msgs:
            try:
                mdata = json.loads(m["data"])
            except (ValueError, TypeError):
                mdata = {}
            messages.append({
                "id": m["id"],
                "role": mdata.get("role", "unknown"),
                "time": m["time_created"],
                "parts": parts_by_msg.get(m["id"], []),
            })
        return {"info": self._row_to_session(srow), "messages": messages}

    def search_messages(self, query: str, limit: int = 100) -> List[HistoryHit]:
        terms = tokenize_query(query)
        if not terms:
            return []

        def esc(t: str) -> str:
            return (t.replace("\\", "\\\\").replace("%", "\\%")
                     .replace("_", "\\_"))

        like = " OR ".join(["p.data LIKE ? ESCAPE '\\'"] * len(terms))
        sql = (
            "SELECT p.id, p.message_id, p.session_id, p.time_created, "
            "p.data, m.data AS mdata "
            "FROM part p LEFT JOIN message m ON m.id = p.message_id "
            f"WHERE {like} "
            "ORDER BY p.time_created DESC LIMIT 5000"
        )
        try:
            with self._connect() as conn:
                rows = conn.execute(sql, [f"%{esc(t)}%" for t in terms]).fetchall()
        except sqlite3.Error as e:
            raise HistoryProviderError(f"search_messages failed: {e}")

        hits: List[HistoryHit] = []
        for r in rows:
            try:
                pdata = json.loads(r["data"])
            except (ValueError, TypeError):
                continue
            if pdata.get("type") != "text":
                continue  # keep only actual conversation prose
            text = (pdata.get("text") or "").strip()
            if not text:
                continue
            low = text.lower()
            matched = [t for t in terms if t in low]
            if not matched:
                continue  # JSON escaping split the term; not real prose match
            try:
                role = json.loads(r["mdata"] or "{}").get("role", "")
            except (ValueError, TypeError):
                role = ""
            hits.append(HistoryHit(
                session_id=r["session_id"],
                part_id=r["id"],
                message_id=r["message_id"] or "",
                time=r["time_created"] or 0,
                role=role,
                text=text,
                score=len(matched),
                matched_terms=matched,
            ))
        hits.sort(key=lambda h: (-h.score, -h.time))
        return hits[:limit]

    # -------------------------------------------------------------- transcript
    def _transcript(self, session_id: str, max_chars: int = 12000):
        data = self.get_session(session_id)
        lines = []
        for msg in data["messages"]:
            role = (msg["role"] or "unknown").upper()
            for part in msg["parts"]:
                if part["type"] != "text" or not part["text"].strip():
                    continue
                body = part["text"].strip()
                lines.append(f"{role}: {body}")
        text = "\n\n".join(lines)
        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars] + (
                f"\n\n... [TRUNCATED by AIOS: session {session_id} "
                f"exceeds {max_chars} chars]"
            )
            truncated = True
        return text, truncated

    # ------------------------------------------------------------ official CLI
    def export_session(self, session_id: str, dest_path) -> str:
        """Official export via `opencode export <id>` (JSON on stdout)."""
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = run_command(["opencode", "export", session_id], timeout=120)
        if not r.success:
            raise HistoryProviderError(
                f"opencode export failed for {session_id}: "
                f"{r.stderr.strip() or r.stdout.strip()}"
            )
        stdout = r.stdout or ""
        start = stdout.find("{")
        if start < 0:
            raise HistoryProviderError(
                f"opencode export produced no JSON for {session_id}"
            )
        payload = stdout[start:]
        try:
            json.loads(payload)  # validate before persisting
        except ValueError as e:
            raise HistoryProviderError(
                f"opencode export JSON invalid for {session_id}: {e}"
            )
        dest.write_text(payload, encoding="utf-8")
        return str(dest)
