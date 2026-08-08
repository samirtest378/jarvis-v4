"""
JARVIS Memory & Planning — persistent context, tasks, notes, and smart routing.

Three systems:
1. Memory — facts, preferences, project context JARVIS learns from conversations
2. Tasks — to-do items with priority, due dates, project association
3. Notes — freeform context tied to projects, people, or topics

Everything stored in SQLite. Relevant memories injected into every LLM call
so JARVIS gets smarter over time.
"""

import json
import logging
import math
import re
import sqlite3
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from config import DATA_DIR, LLM_MODEL

log = logging.getLogger("jarvis.memory")

DB_PATH = DATA_DIR / "jarvis.db"


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,          -- 'fact', 'preference', 'project', 'person', 'decision'
            content TEXT NOT NULL,
            source TEXT DEFAULT '',      -- what conversation/context it came from
            importance INTEGER DEFAULT 5, -- 1-10, higher = more important
            created_at REAL NOT NULL,
            last_accessed REAL,
            access_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            priority TEXT DEFAULT 'medium', -- 'high', 'medium', 'low'
            status TEXT DEFAULT 'open',     -- 'open', 'in_progress', 'done', 'cancelled'
            due_date TEXT,                  -- ISO date string
            due_time TEXT,                  -- HH:MM
            project TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',         -- JSON array
            notes TEXT DEFAULT '',
            created_at REAL NOT NULL,
            completed_at REAL
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '',
            content TEXT NOT NULL,
            topic TEXT DEFAULT '',       -- project name, person, or topic
            tags TEXT DEFAULT '[]',      -- JSON array
            created_at REAL NOT NULL,
            updated_at REAL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
            content, type, source,
            content='memories', content_rowid='id'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS task_fts USING fts5(
            title, description, project, notes,
            content='tasks', content_rowid='id'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5(
            title, content, topic,
            content='notes', content_rowid='id'
        );
    """)
    conn.close()
    log.info("Memory database initialized")


# ---------------------------------------------------------------------------
# Memories — facts JARVIS learns
# ---------------------------------------------------------------------------

def remember(content: str, mem_type: str = "fact", source: str = "", importance: int = 5) -> int:
    """Store a memory once and strengthen an existing duplicate."""
    normalized = _normalize_memory_text(content)
    if not normalized:
        raise ValueError("Memory content cannot be empty")
    conn = _get_db()
    existing = conn.execute(
        "SELECT id, content, importance FROM memories WHERE type = ? ORDER BY created_at DESC",
        (mem_type,),
    ).fetchall()
    duplicate = next(
        (row for row in existing if _normalize_memory_text(row["content"]) == normalized),
        None,
    )
    if duplicate:
        conn.execute(
            "UPDATE memories SET importance = ?, source = ?, last_accessed = ? WHERE id = ?",
            (max(int(duplicate["importance"]), max(1, min(10, int(importance)))), source, time.time(), duplicate["id"]),
        )
        conn.commit()
        conn.close()
        return int(duplicate["id"])
    cur = conn.execute(
        "INSERT INTO memories (type, content, source, importance, created_at) VALUES (?, ?, ?, ?, ?)",
        (mem_type, content.strip(), source, max(1, min(10, int(importance))), time.time())
    )
    mem_id = cur.lastrowid
    # Update FTS
    conn.execute(
        "INSERT INTO memory_fts (rowid, content, type, source) VALUES (?, ?, ?, ?)",
        (mem_id, content, mem_type, source)
    )
    conn.commit()
    conn.close()
    log.info(f"Stored memory [{mem_type}]: {content[:60]}")
    return mem_id


_MEMORY_STOP_WORDS = frozenset({
    "aber", "also", "and", "auch", "auf", "aus", "bei", "bin", "bitte", "das",
    "dass", "dem", "den", "der", "die", "ein", "eine", "einen", "einer", "es",
    "for", "für", "haben", "hat", "ich", "ist", "kann", "mal", "mein", "meine",
    "mit", "mir", "nicht", "oder", "sich", "sie", "the", "und", "von", "was",
    "wie", "wir", "you", "your", "zu",
})

_MEMORY_SYNONYMS = {
    "email": "mail", "emails": "mail", "e-mail": "mail", "mails": "mail",
    "kalender": "termin", "termine": "termin", "calendar": "termin",
    "arbeit": "projekt", "project": "projekt", "projects": "projekt",
    "favorite": "liebling", "favourite": "liebling", "bevorzuge": "liebling",
    "möchte": "ziel", "want": "ziel", "goal": "ziel",
}


def _normalize_memory_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return " ".join(re.findall(r"[a-zäöüß0-9]+", text))


def _memory_tokens(value: str) -> list[str]:
    words = re.findall(r"[a-zäöüß0-9]+", _normalize_memory_text(value))
    result: list[str] = []
    for word in words:
        if len(word) < 3 or word in _MEMORY_STOP_WORDS:
            continue
        token = _MEMORY_SYNONYMS.get(word, word)
        # A deliberately conservative bilingual stemmer catches common
        # German/English plural and case endings without mangling names.
        for suffix in ("ern", "em", "en", "er", "es", "ed", "s"):
            if token.endswith(suffix) and len(token) - len(suffix) >= 4:
                token = token[:-len(suffix)]
                break
        if token not in result:
            result.append(token)
    return result


def _sanitize_fts_query(query: str) -> str:
    """Build a safe, broad FTS query from meaningful bilingual terms."""
    words = _memory_tokens(query)
    if not words:
        return ""
    return " OR ".join(f'"{word}"*' for word in words[:8])


def recall(query: str, limit: int = 5) -> list[dict]:
    """Search memories with lexical, importance, and recency relevance."""
    query_tokens = set(_memory_tokens(query))
    if not query_tokens:
        return []
    fts_query = _sanitize_fts_query(query)
    conn = _get_db()
    try:
        results = conn.execute("""
            SELECT m.id, m.type, m.content, m.importance, m.created_at, m.access_count,
                   bm25(memory_fts) AS lexical_rank
            FROM memory_fts f
            JOIN memories m ON f.rowid = m.id
            WHERE memory_fts MATCH ?
            ORDER BY rank
            LIMIT 40
        """, (fts_query,)).fetchall()
    except Exception:
        results = []

    now = time.time()
    scored: list[tuple[float, sqlite3.Row]] = []
    for row in results:
        candidate_tokens = set(_memory_tokens(row["content"]))
        overlap = sum(
            1
            for query_token in query_tokens
            if any(
                query_token == candidate
                or (len(query_token) >= 4 and candidate.startswith(query_token))
                or (len(candidate) >= 4 and query_token.startswith(candidate))
                for candidate in candidate_tokens
            )
        )
        if overlap == 0:
            continue
        coverage = overlap / max(1, len(query_tokens))
        specificity = overlap / max(1, len(candidate_tokens))
        age_days = max(0.0, (now - float(row["created_at"])) / 86400)
        recency = math.exp(-age_days / 365)
        importance = max(1, min(10, int(row["importance"]))) / 10
        score = (coverage * 0.55) + (specificity * 0.25) + (importance * 0.12) + (recency * 0.08)
        scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [row for score, row in scored[:limit] if score >= 0.2]

    # Update access counts
    for r in selected:
        conn.execute(
            "UPDATE memories SET last_accessed = ?, access_count = access_count + 1 WHERE id = ?",
            (time.time(), r["id"])
        )
    conn.commit()
    conn.close()
    return [
        {key: row[key] for key in ("id", "type", "content", "importance", "created_at", "access_count")}
        for row in selected
    ]


def get_recent_memories(limit: int = 10) -> list[dict]:
    """Get most recent memories."""
    conn = _get_db()
    results = conn.execute(
        "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in results]


def get_important_memories(limit: int = 10) -> list[dict]:
    """Get highest importance memories."""
    conn = _get_db()
    results = conn.execute(
        "SELECT * FROM memories ORDER BY importance DESC, access_count DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in results]


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def create_task(title: str, description: str = "", priority: str = "medium",
                due_date: str = "", due_time: str = "", project: str = "",
                tags: list[str] = None) -> int:
    """Create a task. Returns task ID."""
    conn = _get_db()
    cur = conn.execute(
        """INSERT INTO tasks (title, description, priority, due_date, due_time,
           project, tags, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, description, priority, due_date, due_time,
         project, json.dumps(tags or []), time.time())
    )
    task_id = cur.lastrowid
    conn.execute(
        "INSERT INTO task_fts (rowid, title, description, project, notes) VALUES (?, ?, ?, ?, ?)",
        (task_id, title, description, project, "")
    )
    conn.commit()
    conn.close()
    log.info(f"Created task [{priority}]: {title}")
    return task_id


def get_open_tasks(project: str = None) -> list[dict]:
    """Get all open/in-progress tasks, optionally filtered by project."""
    conn = _get_db()
    if project:
        results = conn.execute(
            "SELECT * FROM tasks WHERE status IN ('open','in_progress') AND project LIKE ? ORDER BY "
            "CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, due_date",
            (f"%{project}%",)
        ).fetchall()
    else:
        results = conn.execute(
            "SELECT * FROM tasks WHERE status IN ('open','in_progress') ORDER BY "
            "CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, due_date"
        ).fetchall()
    conn.close()
    return [dict(r) for r in results]


def get_tasks_for_date(date_str: str) -> list[dict]:
    """Get tasks due on a specific date (YYYY-MM-DD)."""
    conn = _get_db()
    results = conn.execute(
        "SELECT * FROM tasks WHERE due_date = ? AND status != 'cancelled' ORDER BY "
        "CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, due_time",
        (date_str,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in results]


def complete_task(task_id: int):
    """Mark a task as done."""
    conn = _get_db()
    conn.execute(
        "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
        (time.time(), task_id)
    )
    conn.commit()
    conn.close()


def search_tasks(query: str, limit: int = 10) -> list[dict]:
    """Search tasks by text."""
    fts_query = _sanitize_fts_query(query)
    if not fts_query:
        return []
    conn = _get_db()
    try:
        results = conn.execute("""
            SELECT t.* FROM task_fts f
            JOIN tasks t ON f.rowid = t.id
            WHERE task_fts MATCH ?
            ORDER BY rank LIMIT ?
        """, (fts_query, limit)).fetchall()
    except Exception:
        results = []
    conn.close()
    return [dict(r) for r in results]


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

def create_note(content: str, title: str = "", topic: str = "", tags: list[str] = None) -> int:
    """Create a note. Returns note ID."""
    conn = _get_db()
    now = time.time()
    cur = conn.execute(
        "INSERT INTO notes (title, content, topic, tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (title, content, topic, json.dumps(tags or []), now, now)
    )
    note_id = cur.lastrowid
    conn.execute(
        "INSERT INTO note_fts (rowid, title, content, topic) VALUES (?, ?, ?, ?)",
        (note_id, title, content, topic)
    )
    conn.commit()
    conn.close()
    log.info(f"Created note: {title or content[:40]}")
    return note_id


def search_notes(query: str, limit: int = 10) -> list[dict]:
    """Search notes by text."""
    fts_query = _sanitize_fts_query(query)
    if not fts_query:
        return []
    conn = _get_db()
    try:
        results = conn.execute("""
            SELECT n.* FROM note_fts f
            JOIN notes n ON f.rowid = n.id
            WHERE note_fts MATCH ?
            ORDER BY rank LIMIT ?
        """, (fts_query, limit)).fetchall()
    except Exception:
        results = []
    conn.close()
    return [dict(r) for r in results]


def get_notes_by_topic(topic: str) -> list[dict]:
    """Get all notes for a topic/project."""
    conn = _get_db()
    results = conn.execute(
        "SELECT * FROM notes WHERE topic LIKE ? ORDER BY updated_at DESC",
        (f"%{topic}%",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in results]


# ---------------------------------------------------------------------------
# Context Builder — smart context for LLM calls
# ---------------------------------------------------------------------------

def build_memory_context(user_message: str) -> str:
    """Build relevant context from memories, tasks, and notes for the LLM.

    Searches for relevant memories based on what the user is talking about.
    Fast — runs FTS queries, no heavy computation.
    """
    parts = []

    planning_intent = bool(re.search(
        r"\b(?:aufgabe|aufgaben|task|tasks|todo|to-do|plan|planung|heute|morgen|"
        r"priorität|priority|erledigen|schedule|day)\b",
        user_message,
        flags=re.IGNORECASE,
    ))
    high_tasks = [t for t in get_open_tasks() if t["priority"] == "high"] if planning_intent else []
    if high_tasks:
        task_lines = [f"  - [{t['priority']}] {t['title']}" +
                      (f" (due {t['due_date']})" if t["due_date"] else "")
                      for t in high_tasks[:5]]
        parts.append("HIGH PRIORITY TASKS:\n" + "\n".join(task_lines))

    # Search memories relevant to what user is saying
    if len(user_message) > 5:
        relevant = recall(user_message, limit=3)
        if relevant:
            mem_lines = [f"  - [{m['type']}] {m['content']}" for m in relevant]
            parts.append("RELEVANT MEMORIES:\n" + "\n".join(mem_lines))

    return "\n\n".join(parts) if parts else ""


def format_tasks_for_voice(tasks: list[dict], language: str = "en") -> str:
    """Format tasks for voice response."""
    german = language == "de"
    if not tasks:
        return "Ihre Aufgabenliste ist leer." if german else "No tasks on the list, sir."
    count = len(tasks)
    high = [t for t in tasks if t["priority"] == "high"]
    if count == 1:
        t = tasks[0]
        if german:
            return f"Eine Aufgabe: {t['title']}." + (f" Fällig am {t['due_date']}." if t["due_date"] else "")
        return f"One task: {t['title']}." + (f" Due {t['due_date']}." if t["due_date"] else "")
    result = f"Sie haben {count} offene Aufgaben." if german else f"You have {count} open tasks."
    if high:
        result += f" {len(high)} davon haben hohe Priorität." if german else f" {len(high)} are high priority."
    top = tasks[:3]
    for t in top:
        result += f" {t['title']}."
    if count > 3:
        result += f" Und {count - 3} weitere." if german else f" And {count - 3} more."
    return result


def format_plan_for_voice(tasks: list[dict], events: list[dict]) -> str:
    """Format a day plan combining tasks and calendar events."""
    if not tasks and not events:
        return "Your day looks clear, sir. No events or tasks scheduled."

    parts = []
    if events:
        parts.append(f"{len(events)} events on the calendar")
    if tasks:
        high = [t for t in tasks if t["priority"] == "high"]
        parts.append(f"{len(tasks)} tasks" + (f", {len(high)} high priority" if high else ""))

    result = f"For tomorrow: {', '.join(parts)}. "

    # List events first
    if events:
        for e in events[:3]:
            result += f"{e.get('start', '')} {e['title']}. "

    # Then high priority tasks
    if tasks:
        for t in [t for t in tasks if t["priority"] == "high"][:2]:
            result += f"Priority: {t['title']}. "

    result += "Shall I adjust anything?"
    return result


# ---------------------------------------------------------------------------
# Memory extraction — learn from conversations
# ---------------------------------------------------------------------------

_IMPLICIT_MEMORY_PATTERNS = tuple(
    re.compile(pattern, flags=re.IGNORECASE)
    for pattern in (
        # Identity and stable personal details.
        r"\b(?:mein name ist|ich hei(?:ß|ss)e|nenne mich|ich wohne in|mein geburtstag ist)\b",
        r"\b(?:my name is|call me|i live in|my birthday is)\b",
        # Durable preferences.
        r"\b(?:ich bevorzuge|ich mag|ich liebe|ich hasse|meine präferenz ist)\b",
        r"\b(?:i prefer|i like|i love|i hate|my preference is)\b",
        # Projects, goals, and decisions worth carrying into later sessions.
        r"\b(?:mein ziel ist|ich arbeite an|wir haben entschieden|in zukunft möchte ich)\b",
        r"\b(?:my goal is|i am working on|i'm working on|we decided|in the future i want)\b",
    )
)


def should_extract_memories(user_text: str) -> bool:
    """Return true only when a turn plausibly contains a durable personal fact.

    Generic knowledge questions must never trigger a second paid model call:
    that hidden request can contend with the user's next turn and makes a fast
    conversation feel progressively slower.
    """
    normalized = " ".join(user_text.strip().split())
    if len(normalized) < 8 or len(normalized) > 1000:
        return False
    return any(pattern.search(normalized) for pattern in _IMPLICIT_MEMORY_PATTERNS)


async def extract_memories(user_text: str, jarvis_response: str, anthropic_client) -> list[str]:
    """After a conversation turn, extract any facts worth remembering.

    Uses Haiku to decide if anything in the exchange is worth storing.
    Returns list of memories stored.
    """
    if not anthropic_client or not should_extract_memories(user_text):
        return []

    try:
        response = await anthropic_client.messages.create(
            model=LLM_MODEL,
            max_tokens=200,
            system=(
                "Extract facts worth remembering from this conversation. "
                "Only extract CONCRETE facts: preferences, decisions, names, dates, plans, goals. "
                "NOT opinions, greetings, or casual chat. "
                "Return JSON array of objects: [{\"type\": \"fact|preference|project|person|decision\", \"content\": \"...\", \"importance\": 1-10}] "
                "Return [] if nothing worth remembering. Be very selective."
            ),
            messages=[{"role": "user", "content": f"User: {user_text}\nJARVIS: {jarvis_response}"}],
        )

        text = response.content[0].text.strip()
        # Parse JSON
        if text.startswith("["):
            items = json.loads(text)
            stored = []
            for item in items:
                if isinstance(item, dict) and "content" in item:
                    remember(
                        content=item["content"],
                        mem_type=item.get("type", "fact"),
                        source=user_text[:50],
                        importance=item.get("importance", 5),
                    )
                    stored.append(item["content"])
            return stored
    except Exception as e:
        log.debug(f"Memory extraction failed: {e}")

    return []


# Initialize on import
init_db()
