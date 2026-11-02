"""SQLite persistence: database setup and repositories (Patient, Visit, User, Audit)."""
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

from .authentication import User, hash_password
from .patient import Patient, ALL_FIELDS
from .visit import VisitNote


def now():
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, path="prs.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                clearance TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS patient_id_seq (
                id INTEGER PRIMARY KEY AUTOINCREMENT
            );
            CREATE TABLE IF NOT EXISTS patients (
                patient_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                date_of_birth TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                insurance_id TEXT,
                confidential_notes TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS visit_notes (
                note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                reason TEXT NOT NULL,
                category TEXT,
                category_source TEXT
            );
            CREATE TABLE IF NOT EXISTS ai_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_id INTEGER NOT NULL,
                rating TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                username TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT,
                details TEXT
            );
            """
        )
        self.conn.commit()

    def next_patient_id(self):
        """AUTOINCREMENT sequence so IDs are never reused, even after deletion."""
        cur = self.conn.execute("INSERT INTO patient_id_seq DEFAULT VALUES")
        return "P-%06d" % cur.lastrowid


class UserRepository:
    def __init__(self, db):
        self.db = db

    def count(self):
        return self.db.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def add(self, username, full_name, role, password, clearance):
        pw_hash, salt = hash_password(password)
        self.db.conn.execute(
            "INSERT INTO users VALUES (?,?,?,?,?,?)",
            (username, full_name, role, pw_hash, salt, ",".join(clearance)),
        )
        self.db.conn.commit()

    def get_record(self, username):
        return self.db.conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

    def get(self, username) -> Optional[User]:
        row = self.get_record(username)
        if row is None:
            return None
        clearance = [c for c in row["clearance"].split(",") if c]
        return User(row["username"], row["full_name"], row["role"], clearance)

    def set_clearance(self, username, fields):
        self.db.conn.execute(
            "UPDATE users SET clearance=? WHERE username=?", (",".join(fields), username)
        )
        self.db.conn.commit()


class AuditRepository:
    def __init__(self, db):
        self.db = db

    def log(self, username, action, target, details):
        self.db.conn.execute(
            "INSERT INTO audit_log (timestamp, username, action, target, details) VALUES (?,?,?,?,?)",
            (now(), username, action, target, details),
        )
        self.db.conn.commit()

    def list_all(self):
        return self.db.conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()


class PatientRepository:
    def __init__(self, db):
        self.db = db

    def add(self, name, info: Dict[str, str]) -> Patient:
        pid = self.db.next_patient_id()
        values = {f: info.get(f) for f in ALL_FIELDS if f != "name"}
        self.db.conn.execute(
            "INSERT INTO patients (patient_id, name, date_of_birth, phone, email, address, "
            "insurance_id, confidential_notes, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (pid, name, values["date_of_birth"], values["phone"], values["email"],
             values["address"], values["insurance_id"], values["confidential_notes"], now()),
        )
        self.db.conn.commit()
        return self.get(pid)

    def get(self, patient_id) -> Optional[Patient]:
        row = self.db.conn.execute(
            "SELECT * FROM patients WHERE patient_id=?", (patient_id,)
        ).fetchone()
        return Patient(**dict(row)) if row else None

    def update_fields(self, patient_id, changes: Dict[str, str]):
        for field_name, value in changes.items():
            self.db.conn.execute(
                "UPDATE patients SET %s=? WHERE patient_id=?" % field_name, (value, patient_id)
            )
        self.db.conn.commit()

    def delete(self, patient_id):
        self.db.conn.execute("DELETE FROM patients WHERE patient_id=?", (patient_id,))
        self.db.conn.commit()


class VisitRepository:
    def __init__(self, db):
        self.db = db

    def add(self, patient_id, created_by, reason) -> VisitNote:
        cur = self.db.conn.execute(
            "INSERT INTO visit_notes (patient_id, created_by, created_at, reason) VALUES (?,?,?,?)",
            (patient_id, created_by, now(), reason),
        )
        self.db.conn.commit()
        return self.get(cur.lastrowid)

    def get(self, note_id) -> Optional[VisitNote]:
        row = self.db.conn.execute("SELECT * FROM visit_notes WHERE note_id=?", (note_id,)).fetchone()
        return VisitNote(**dict(row)) if row else None

    def list_for_patient(self, patient_id) -> List[VisitNote]:
        rows = self.db.conn.execute(
            "SELECT * FROM visit_notes WHERE patient_id=? ORDER BY created_at, note_id", (patient_id,)
        ).fetchall()
        return [VisitNote(**dict(r)) for r in rows]

    def set_category(self, note_id, category, source):
        self.db.conn.execute(
            "UPDATE visit_notes SET category=?, category_source=? WHERE note_id=?",
            (category, source, note_id),
        )
        self.db.conn.commit()

    def add_feedback(self, note_id, rating):
        self.db.conn.execute(
            "INSERT INTO ai_feedback (note_id, rating, created_at) VALUES (?,?,?)",
            (note_id, rating, now()),
        )
        self.db.conn.commit()
