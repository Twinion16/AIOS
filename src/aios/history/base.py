"""Abstract history provider: retrieve prior agent conversations."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


class HistoryProviderError(Exception):
    """Raised when history storage cannot be accessed or parsed."""


@dataclass
class SessionInfo:
    id: str
    title: str
    slug: str = ""
    directory: str = ""
    project_id: str = ""
    version: str = ""
    time_created: int = 0   # epoch milliseconds (as stored by OpenCode)
    time_updated: int = 0

    @property
    def date_iso(self) -> str:
        if not self.time_created:
            return "UNKNOWN"
        from datetime import datetime
        try:
            return datetime.fromtimestamp(self.time_created / 1000).strftime(
                "%Y-%m-%d %H:%M"
            )
        except (OSError, OverflowError, ValueError):
            return "UNKNOWN"


@dataclass
class HistoryHit:
    session_id: str
    part_id: str
    message_id: str = ""
    time: int = 0
    role: str = ""
    text: str = ""
    score: int = 0
    matched_terms: List[str] = field(default_factory=list)


@dataclass
class SessionContext:
    """Everything AIOS needs to hand one historical session to an agent."""
    session: SessionInfo
    hits: List[HistoryHit] = field(default_factory=list)
    transcript: str = ""          # plain-text transcript (possibly truncated)
    truncated: bool = False
    total_score: int = 0
    matched_terms: List[str] = field(default_factory=list)


# Words that are useless for locating a conversation. Query terms are taken
# from the user's task text, so retrieval verbs are dropped too.
HISTORY_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is",
    "are", "be", "been", "being", "was", "were", "this", "that", "these",
    "those", "it", "its", "with", "from", "at", "by", "as", "we", "our",
    "my", "me", "you", "your", "i", "us", "them", "they", "he", "she",
    "what", "which", "who", "whom", "how", "why", "where", "when", "if",
    "then", "than", "so", "no", "not", "yes", "can", "could", "would",
    "should", "will", "shall", "may", "might", "must", "do", "does", "did",
    "done", "have", "has", "had", "get", "got", "please", "just", "also",
    "about", "into", "over", "under", "out", "up", "down", "all", "any",
    "some", "more", "most", "other", "another", "very", "here", "there",
    "find", "search", "look", "show", "give", "tell", "list", "retrieve",
    "extract", "read", "see", "want", "need", "like", "ever", "already",
    "still", "again", "one", "two", "first", "last", "new", "old",
    "aios", "ai", "agent", "task", "project", "file", "files",
    "sessions", "session", "conversation", "conversations",
    "things", "stuff", "something", "anything", "everything",
    "ones", "worth", "previous", "using", "used", "make", "made",
    "much", "many", "well", "way", "even", "back", "now", "then",
}


def tokenize_query(query: str) -> List[str]:
    """Lowercase word terms from a query, stopwords and short tokens removed."""
    import re
    raw = re.findall(r"[a-z0-9][a-z0-9_\-']+", (query or "").lower())
    terms = []
    seen = set()
    for t in raw:
        t = t.strip("-_'")
        if len(t) < 3 or t in HISTORY_STOPWORDS:
            continue
        if t not in seen:
            seen.add(t)
            terms.append(t)
    return terms


class HistoryProvider(ABC):
    """Interface for reading prior agent conversations.

    Implementations must be strictly read-only with respect to the underlying
    storage, and must never touch credential files.
    """

    name: str = "abstract"

    @abstractmethod
    def list_sessions(self, limit: Optional[int] = None) -> List[SessionInfo]:
        """Sessions newest-first."""

    @abstractmethod
    def get_session(self, session_id: str) -> dict:
        """Full session as {"info": SessionInfo, "messages": [...]}.
        messages: [{"id", "role", "time", "parts": [{"type", "text"}]}]."""

    @abstractmethod
    def search_messages(self, query: str, limit: int = 100) -> List[HistoryHit]:
        """Keyword search over message content, best matches first."""

    @abstractmethod
    def export_session(self, session_id: str, dest_path) -> str:
        """Write an official transcript export; returns path written."""

    def extract_relevant_context(
        self,
        query: str,
        max_sessions: int = 8,
        max_chars_per_session: int = 12000,
        title_matches: dict = None,
    ) -> List[SessionContext]:
        """Search, group hits by session, and build per-session context.

        Shared implementation: subclasses only provide search + transcripts.
        """
        hits = self.search_messages(query, limit=500)
        by_session: dict = {}
        for h in hits:
            by_session.setdefault(h.session_id, []).append(h)

        sessions = {s.id: s for s in self.list_sessions()}
        terms = set(tokenize_query(query))

        ranked = []
        for sid, s_hits in by_session.items():
            info = sessions.get(sid) or SessionInfo(id=sid, title="UNKNOWN")
            score = sum(h.score for h in s_hits)
            matched = sorted({t for h in s_hits for t in h.matched_terms})
            # session-title matches count as evidence too
            title_l = (info.title or "").lower()
            for t in terms:
                if t in title_l:
                    score += 3
                    matched.append(t)
            ranked.append((score, sid, info, s_hits, sorted(set(matched))))
        ranked.sort(key=lambda r: (-r[0], r[2].time_updated or 0))

        contexts = []
        for score, sid, info, s_hits, matched in ranked[:max_sessions]:
            transcript, truncated = self._transcript(
                sid, max_chars=max_chars_per_session
            )
            contexts.append(SessionContext(
                session=info,
                hits=sorted(s_hits, key=lambda h: -h.score),
                transcript=transcript,
                truncated=truncated,
                total_score=score,
                matched_terms=matched,
            ))
        return contexts

    @abstractmethod
    def _transcript(self, session_id: str, max_chars: int = 12000):
        """Plain-text transcript ("ROLE: text" lines), truncated flag."""
