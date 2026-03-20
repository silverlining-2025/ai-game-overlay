"""SQLite-backed game memory database. One DB per game at training_data/<game>/game_memory.db.
Thread-safe (threading.Lock), WAL mode. Drop-in replacement for CompanionMemory + SessionRecorder.
"""
from __future__ import annotations
import json, random, sqlite3, sys, threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if getattr(sys, "frozen", False):
    _REPO = Path(sys.executable).parent
else:
    _REPO = Path(__file__).resolve().parents[2]
_DATA = _REPO / "training_data"
_SCHEMA_VERSION = 1
_SCHEMA = """\
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
  ended_at TEXT, duration_s REAL, character TEXT DEFAULT '',
  locale TEXT DEFAULT 'ko', tier TEXT DEFAULT 'free',
  summary TEXT DEFAULT '', playstyle TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS cv_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL REFERENCES sessions(id),
  ts_offset REAL NOT NULL, label TEXT DEFAULT '', score REAL DEFAULT 0,
  data_json TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS ai_responses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL REFERENCES sessions(id),
  ts_offset REAL NOT NULL, cycle INTEGER DEFAULT 0,
  text TEXT DEFAULT '', mood TEXT DEFAULT '', face TEXT DEFAULT '',
  mode TEXT DEFAULT '', event_label TEXT DEFAULT '', event_score REAL DEFAULT 0,
  provider TEXT DEFAULT '', model TEXT DEFAULT '',
  input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,
  cost_usd REAL DEFAULT 0, elapsed_ms REAL DEFAULT 0,
  screenshot_path TEXT DEFAULT '', thumbnail BLOB, feedback_score INTEGER);
CREATE TABLE IF NOT EXISTS game_state_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL REFERENCES sessions(id),
  ts_offset REAL NOT NULL, location TEXT DEFAULT '', activity TEXT DEFAULT '',
  quest TEXT DEFAULT '', mood_trend TEXT DEFAULT '', event_text TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS behavior_summaries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL REFERENCES sessions(id),
  death_count INTEGER DEFAULT 0, playstyle TEXT DEFAULT '',
  activity_time TEXT DEFAULT '{}', data_json TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS knowledge_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category TEXT NOT NULL, subject TEXT NOT NULL, fact TEXT NOT NULL,
  times_observed INTEGER DEFAULT 1, first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL, session_id INTEGER,
  UNIQUE(category, subject, fact));
CREATE TABLE IF NOT EXISTS effective_tips (
  id INTEGER PRIMARY KEY AUTOINCREMENT, tip_text TEXT NOT NULL UNIQUE,
  upvotes INTEGER DEFAULT 0, downvotes INTEGER DEFAULT 0,
  first_used TEXT NOT NULL, last_used TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS player_profile (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  name TEXT DEFAULT '', level_range TEXT DEFAULT '', play_style TEXT DEFAULT '',
  notable_pals TEXT DEFAULT '[]', sessions_together INTEGER DEFAULT 0,
  total_reactions INTEGER DEFAULT 0, favorite_topics TEXT DEFAULT '[]',
  last_session_date TEXT DEFAULT '', last_session_summary TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS moments (
  id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
  text TEXT NOT NULL, type TEXT DEFAULT 'notable',
  emotional_weight REAL DEFAULT 1.0, session_id INTEGER);
CREATE INDEX IF NOT EXISTS idx_cv_session ON cv_events(session_id);
CREATE INDEX IF NOT EXISTS idx_resp_session ON ai_responses(session_id);
CREATE INDEX IF NOT EXISTS idx_resp_cycle ON ai_responses(session_id, cycle);
CREATE INDEX IF NOT EXISTS idx_snap_session ON game_state_snapshots(session_id);
CREATE INDEX IF NOT EXISTS idx_moments_ts ON moments(timestamp);
CREATE INDEX IF NOT EXISTS idx_knowledge_cat ON knowledge_facts(category);
"""

def _now() -> str: return datetime.now(timezone.utc).isoformat()

class GameMemoryDB:
    """SQLite-backed game memory database. One DB per game."""

    def __init__(self, game: str) -> None:
        self.game = game
        db_dir = _DATA / game
        db_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._cv_buf: list[tuple] = []
        self._conn = sqlite3.connect(str(db_dir / "game_memory.db"), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.cursor().executescript(_SCHEMA)
        self._conn.execute("INSERT OR IGNORE INTO player_profile (id) VALUES (1)")
        self._conn.execute("INSERT OR IGNORE INTO meta (key,value) VALUES ('schema_version',?)",
                           (str(_SCHEMA_VERSION),))
        self._conn.commit()

    def _exec(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._conn.execute(sql, params); self._conn.commit()

    # --- Session lifecycle ---
    def start_session(self, character: str = "", locale: str = "ko", tier: str = "free") -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO sessions (started_at,character,locale,tier) VALUES (?,?,?,?)",
                (_now(), character, locale, tier))
            self._conn.commit()
            return cur.lastrowid  # type: ignore[return-value]

    def end_session(self, session_id: int, summary: str = "", playstyle: str = "") -> None:
        now = _now()
        with self._lock:
            self._flush_cv()
            self._conn.execute(
                "UPDATE sessions SET ended_at=?, summary=?, playstyle=?, "
                "duration_s=(julianday(?)-julianday(started_at))*86400 WHERE id=?",
                (now, summary, playstyle, now, session_id))
            self._conn.execute(
                "UPDATE player_profile SET last_session_date=?, last_session_summary=? WHERE id=1",
                (now[:10], summary))
            self._conn.commit()

    # --- CV events (buffered, flushes every 10) ---
    def record_cv_event(self, session_id: int, ts_offset: float, signal_dict: dict) -> None:
        row = (session_id, ts_offset, signal_dict.get("label", ""),
               signal_dict.get("score", 0.0), json.dumps(signal_dict, ensure_ascii=False))
        with self._lock:
            self._cv_buf.append(row)
            if len(self._cv_buf) >= 10:
                self._flush_cv()

    def _flush_cv(self) -> None:
        if not self._cv_buf:
            return
        self._conn.executemany(
            "INSERT INTO cv_events (session_id,ts_offset,label,score,data_json) VALUES (?,?,?,?,?)",
            self._cv_buf)
        self._conn.commit()
        self._cv_buf.clear()

    # --- AI responses ---
    def record_response(self, session_id: int, ts_offset: float, cycle: int,
                        text: str, mood: str, face: str, mode: str,
                        event_label: str, event_score: float,
                        provider: str, model: str,
                        input_tokens: int, output_tokens: int, cost_usd: float,
                        elapsed_ms: float, screenshot_path: str = "",
                        thumbnail: bytes | None = None) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO ai_responses (session_id,ts_offset,cycle,text,mood,face,mode,"
                "event_label,event_score,provider,model,input_tokens,output_tokens,"
                "cost_usd,elapsed_ms,screenshot_path,thumbnail) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (session_id, ts_offset, cycle, text, mood, face, mode,
                 event_label, event_score, provider, model,
                 input_tokens, output_tokens, cost_usd, elapsed_ms,
                 screenshot_path, thumbnail))
            self._conn.commit()
            return cur.lastrowid  # type: ignore[return-value]

    def record_feedback(self, session_id: int, cycle: int, score: int, text: str = "") -> None:
        self._exec("UPDATE ai_responses SET feedback_score=? WHERE session_id=? AND cycle=?",
                   (score, session_id, cycle))

    # --- Game state ---
    def record_state_snapshot(self, session_id: int, ts_offset: float,
                              location: str, activity: str, quest: str = "",
                              mood_trend: str = "", event_text: str = "") -> None:
        self._exec("INSERT INTO game_state_snapshots (session_id,ts_offset,location,activity,quest,mood_trend,event_text) VALUES (?,?,?,?,?,?,?)",
                   (session_id, ts_offset, location, activity, quest, mood_trend, event_text))

    # --- Behavior ---
    def save_behavior(self, session_id: int, tracker_data: dict) -> None:
        d = tracker_data
        self._exec("INSERT INTO behavior_summaries (session_id,death_count,playstyle,activity_time,data_json) VALUES (?,?,?,?,?)",
                   (session_id, d.get("death_count", 0), d.get("playstyle", ""),
                    json.dumps(d.get("activity_time", {}), ensure_ascii=False),
                    json.dumps(d, ensure_ascii=False)))

    # --- Game knowledge ---
    def add_knowledge(self, category: str, subject: str, fact: str,
                      session_id: int | None = None) -> None:
        now = _now()
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM knowledge_facts WHERE category=? AND subject=? AND fact=?",
                (category, subject, fact)).fetchone()
            if row:
                self._conn.execute(
                    "UPDATE knowledge_facts SET times_observed=times_observed+1, last_seen=? WHERE id=?",
                    (now, row[0]))
            else:
                self._conn.execute(
                    "INSERT INTO knowledge_facts (category,subject,fact,first_seen,last_seen,session_id) "
                    "VALUES (?,?,?,?,?,?)", (category, subject, fact, now, now, session_id))
            self._conn.commit()

    def update_tip_feedback(self, tip_text: str, upvote: bool) -> None:
        now, col = _now(), "upvotes" if upvote else "downvotes"
        with self._lock:
            row = self._conn.execute("SELECT id FROM effective_tips WHERE tip_text=?", (tip_text,)).fetchone()
            if row:
                self._conn.execute(f"UPDATE effective_tips SET {col}={col}+1, last_used=? WHERE id=?", (now, row[0]))
            else:
                ups, downs = (1, 0) if upvote else (0, 1)
                self._conn.execute(
                    "INSERT INTO effective_tips (tip_text,upvotes,downvotes,first_used,last_used) VALUES (?,?,?,?,?)",
                    (tip_text, ups, downs, now, now))
            self._conn.commit()

    # --- Player profile (replaces CompanionMemory player section) ---
    def get_player_profile(self) -> dict[str, Any]:
        with self._lock:
            r = self._conn.execute(
                "SELECT name,level_range,play_style,notable_pals,sessions_together,"
                "total_reactions,favorite_topics,last_session_date,last_session_summary "
                "FROM player_profile WHERE id=1").fetchone()
        if not r:
            return {}
        return {"name": r[0], "level_range": r[1], "play_style": r[2],
                "notable_pals": json.loads(r[3]), "sessions_together": r[4],
                "total_reactions": r[5], "favorite_topics": json.loads(r[6]),
                "last_session_date": r[7], "last_session_summary": r[8]}

    def update_player_profile(self, **kwargs: Any) -> None:
        allowed = {"name", "level_range", "play_style", "notable_pals", "favorite_topics"}
        sets, vals = [], []
        for k, v in kwargs.items():
            if k not in allowed:
                continue
            if isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False)
            sets.append(f"{k}=?"); vals.append(v)
        if not sets:
            return
        with self._lock:
            self._conn.execute(f"UPDATE player_profile SET {','.join(sets)} WHERE id=1", vals)
            self._conn.commit()

    def increment_session_count(self) -> None:
        self._exec("UPDATE player_profile SET sessions_together=sessions_together+1 WHERE id=1")

    def increment_reactions(self, count: int = 1) -> None:
        self._exec("UPDATE player_profile SET total_reactions=total_reactions+? WHERE id=1", (count,))

    # --- Moments (no FIFO cap -- all preserved) ---
    def add_moment(self, text: str, moment_type: str = "notable",
                   emotional_weight: float = 1.0, session_id: int | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO moments (timestamp,text,type,emotional_weight,session_id) VALUES (?,?,?,?,?)",
                (_now(), text, moment_type, emotional_weight, session_id))
            self._conn.commit()

    def get_recent_moments(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT timestamp,text,type,emotional_weight FROM moments ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
        return [{"timestamp": r[0], "text": r[1], "type": r[2], "emotional_weight": r[3]}
                for r in reversed(rows)]

    def get_fuzzy_recall(self, context: str, locale: str = "ko") -> str | None:
        """Find a relevant past moment via keyword matching (same logic as CompanionMemory)."""
        moments = self.get_recent_moments(limit=50)
        if not moments:
            return None
        ctx_words = set(context.lower().split())
        best, best_sc = None, 0
        for m in moments:
            sc = len(ctx_words & set(m["text"].lower().split()))
            if sc > best_sc:
                best_sc, best = sc, m
        if best and best_sc >= 1:
            return self._fuzzify(best, locale)
        if random.random() < 0.1 and moments:
            return self._fuzzify(random.choice(moments), locale)
        return None

    @staticmethod
    def _fuzzify(moment: dict, locale: str = "ko") -> str:
        t, roll = moment["text"], random.random()
        if locale == "ko":
            if roll < 0.7:
                pool = [f"전에 {t}... 맞지?", f"이거 전에도... {t} 비슷한 거 있었는데", f"어디서 봤는데... {t}... 맞나?"]
            elif roll < 0.9:
                pool = ["전에 뭔가... 이 비슷한 게 있었는데, 기억이 가물가물",
                        f"이거 어제였나... 그제였나... 하여튼 전에 {t[:15]}...",
                        "확실하진 않은데, 예전에 이 비슷한 데서..."]
            else:
                pool = ["전에도 이런 적 있었는데... 뭐였더라", "어디서 본 것 같은데, 기억이 안 나네"]
        else:
            if roll < 0.7:
                pool = [f"Didn't something like {t}... happen before?",
                        f"This reminds me of... {t}... I think?",
                        f"Wait, wasn't there a time when {t}...?"]
            elif roll < 0.9:
                pool = ["Something like this happened before... can't quite remember",
                        f"Was it yesterday or... anyway, {t[:15]}..."]
            else:
                pool = ["This feels familiar... what was it",
                        "I've seen something like this before... or have I?"]
        return random.choice(pool)

    # --- Context for prompts (same narrative style as CompanionMemory) ---
    def get_context_for_prompt(self, locale: str = "ko") -> str:
        profile = self.get_player_profile()
        moments = self.get_recent_moments(limit=5)
        n = profile.get("sessions_together", 0)
        prev = profile.get("last_session_summary", "")
        en = locale == "en"
        parts: list[str] = []
        # Session line
        line = f"This is session #{n} with this player." if en else f"이 플레이어와 {n}번째 세션이야."
        if prev:
            line += (f" Last time: {prev}" if en else f" 저번에 {prev}")
        parts.append(line)
        # Player info
        bits = []
        if en:
            if profile.get("name"): bits.append(f"Name: {profile['name']}")
            if profile.get("level_range"): bits.append(f"Level: {profile['level_range']}")
            if profile.get("play_style"): bits.append(f"Style: {profile['play_style']}")
        else:
            if profile.get("name"): bits.append(f"이름은 {profile['name']}")
            if profile.get("level_range"): bits.append(f"레벨대는 {profile['level_range']}")
            if profile.get("play_style"): bits.append(f"{profile['play_style']} 스타일")
        if bits:
            parts.append(("Player: " if en else "플레이어 정보: ") + ", ".join(bits) + ".")
        # Moments narrative
        if moments:
            narr = [self._narrate_moment(m, en) for m in moments]
            sep = ". Also, " if en else ". 그리고 "
            prefix = "From before: " if en else "예전에 "
            parts.append(f"{prefix}{sep.join(narr)}.")
        return "\n".join(parts)

    @staticmethod
    def _narrate_moment(m: dict, en: bool) -> str:
        w, tp, tx = m.get("emotional_weight", 1.0), m.get("type", "notable"), m["text"]
        heavy = w >= 1.5
        if en:
            if tp in ("fail", "funny"):
                return f"remember when {tx}? That was rough" if heavy else f"remember {tx}"
            if tp in ("achievement", "epic"):
                return f"{tx} was amazing" if heavy else f"remember pulling off {tx}"
            return f"there was that time with {tx}"
        if tp in ("fail", "funny"):
            return f"{tx} 때 진짜 힘들었잖아" if heavy else f"{tx} 했던 거 기억나"
        if tp in ("achievement", "epic"):
            return f"{tx} 성공했을 때 진짜 좋아했잖아" if heavy else f"{tx} 해냈던 거 기억나"
        return f"{tx} 있었잖아"

    # --- Training data export ---
    def export_training_pairs(self, min_feedback: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT r.screenshot_path, r.text, r.feedback_score, r.event_label, "
                "r.mood, r.provider, r.model, s.character, s.locale "
                "FROM ai_responses r JOIN sessions s ON r.session_id=s.id "
                "WHERE r.feedback_score IS NOT NULL AND r.feedback_score>=? "
                "AND r.screenshot_path!='' ORDER BY r.id", (min_feedback,)).fetchall()
        return [{"screenshot": r[0], "response": r[1], "feedback_score": r[2],
                 "event_label": r[3], "mood": r[4], "provider": r[5], "model": r[6],
                 "character": r[7], "locale": r[8]} for r in rows]

    # --- Stats ---
    def _q(self, sql: str, params: tuple = ()) -> tuple | None:
        return self._conn.execute(sql, params).fetchone()

    def get_session_stats(self, session_id: int) -> dict[str, Any]:
        with self._lock:
            r = self._q("SELECT COUNT(*),SUM(cost_usd),AVG(elapsed_ms) FROM ai_responses WHERE session_id=?", (session_id,))
            ev = self._q("SELECT COUNT(*) FROM cv_events WHERE session_id=?", (session_id,))
            s = self._q("SELECT started_at,ended_at,duration_s,summary FROM sessions WHERE id=?", (session_id,))
        return {"session_id": session_id, "responses": r[0] if r else 0,
                "total_cost_usd": round(r[1] or 0, 6) if r else 0,
                "avg_elapsed_ms": round(r[2] or 0, 1) if r else 0, "cv_events": ev[0] if ev else 0,
                "started_at": s[0] if s else "", "ended_at": s[1] if s else "",
                "duration_s": s[2] if s else 0, "summary": s[3] if s else ""}

    def get_lifetime_stats(self) -> dict[str, Any]:
        with self._lock:
            s = self._q("SELECT COUNT(*),SUM(duration_s) FROM sessions")
            r = self._q("SELECT COUNT(*),SUM(cost_usd),SUM(input_tokens),SUM(output_tokens) FROM ai_responses")
            mc = self._q("SELECT COUNT(*) FROM moments")
            kc = self._q("SELECT COUNT(*) FROM knowledge_facts")
        return {"total_sessions": s[0] if s else 0, "total_playtime_s": round(s[1] or 0, 1) if s else 0,
                "total_responses": r[0] if r else 0, "total_cost_usd": round(r[1] or 0, 6) if r else 0,
                "total_input_tokens": r[2] or 0 if r else 0, "total_output_tokens": r[3] or 0 if r else 0,
                "total_moments": mc[0] if mc else 0, "total_knowledge_facts": kc[0] if kc else 0}

    # --- Cleanup ---
    def close(self) -> None:
        with self._lock:
            self._flush_cv()
            self._conn.close()
