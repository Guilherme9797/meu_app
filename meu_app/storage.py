import json, sqlite3
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .orchestrator import CaseFrame

DB_PATH = Path(__file__).parent / "state.db"

def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS cases (
      phone TEXT PRIMARY KEY,
      data TEXT NOT NULL
    )
    """)
    return conn

def load_case(phone: str) -> Optional['CaseFrame']:
    from .orchestrator import CaseFrame
    conn = _conn()
    cur = conn.execute("SELECT data FROM cases WHERE phone=?", (phone,))
    row = cur.fetchone()
    if not row: return None
    data = json.loads(row[0])
    case = CaseFrame(**data)
    return case

def save_case(case: 'CaseFrame') -> None:
    conn = _conn()
    data = json.dumps(case.__dict__, ensure_ascii=False)
    conn.execute("REPLACE INTO cases (phone, data) VALUES (?,?)", (case.phone, data))
    conn.commit()