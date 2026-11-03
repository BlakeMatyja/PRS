"""SQLite persistence: database setup and repositories (Patient, Visit, User, Audit)."""
import sqlite3
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from .authentication import User, hash_password
from .exceptions import ValidationError
from .patient import ALL_FIELDS, Patient
from .visit import VisitNote

# only these columns may be written by update_fields; patient_id is never one of them
UPDATABLE_PATIENT_FIELDS = ALL_FIELDS


def now() -> str:
    """Return the current local time as an ISO-8601 string (seconds)."""
    return datetime.now().isoformat(timespec="seconds")


class Database:
    """Owns the SQLite connection and creates the schema."""

    def __init__(self, path: str = "prs.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()

    def _create_tables(self) -> None:
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
            CREATE TRIGGER IF NOT EXISTS patients_id_immutable
            BEFORE UPDATE OF patient_id ON patients
            WHEN NEW.patient_id IS NOT OLD.patient_id
            BEGIN
                SELECT RAISE(ABORT, 'patient_id is immutable');
            END;
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

    def next_patient_id(self) -> str:
        """Return a new ID like P-000001 from an AUTOINCREMENT sequence.

        AUTOINCREMENT never reuses a number, even after a patient is deleted.
        """
        cur = self.conn.execute("INSERT INTO patient_id_seq DEFAULT VALUES")
        return "P-%06d" % cur.lastrowid


class UserRepository:
    """Stores staff accounts."""

    def __init__(self, db: Database):
        self.db = db

    def count(self) -> int:
        """Return the number of stored accounts."""
        return self.db.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def add(self, username: str, full_name: str, role: str, password: str,
            clearance: List[str]) -> None:
        """Store a new account with a hashed password."""
        pw_hash, salt = hash_password(password)
        self.db.conn.execute(
            "INSERT INTO users VALUES (?,?,?,?,?,?)",
            (username, full_name, role, pw_hash, salt, ",".join(clearance)),
        )
        self.db.conn.commit()

    def get_record(self, username: str) -> Optional[sqlite3.Row]:
        """Return the raw row, including password hash and salt, or None."""
        return self.db.conn.execute(
            "SELECT * FROM users WHERE username=?", (username,)).fetchone()

    def get(self, username: str) -> Optional[User]:
        """Return the User for this username, or None."""
        row = self.get_record(username)
        if row is None:
            return None
        clearance = [c for c in row["clearance"].split(",") if c]
        return User(row["username"], row["full_name"], row["role"], clearance)

    def set_clearance(self, username: str, fields: List[str]) -> None:
        """Replace an account's clearance list."""
        self.db.conn.execute(
            "UPDATE users SET clearance=? WHERE username=?", (",".join(fields), username))
        self.db.conn.commit()


class AuditRepository:
    """Append-only log of who did what."""

    _INSERT = ("INSERT INTO audit_log (timestamp, username, action, target, details) "
               "VALUES (?,?,?,?,?)")

    def __init__(self, db: Database):
        self.db = db

    def log(self, username: str, action: str, target: str, details: str) -> None:
        """Write one audit entry."""
        self.log_many(username, action, target, [details])

    def log_many(self, username: str, action: str, target: str,
                 details_list: Iterable[str]) -> None:
        """Write several entries for one action in a single commit."""
        stamp = now()
        self.db.conn.executemany(
            self._INSERT, [(stamp, username, action, target, d) for d in details_list])
        self.db.conn.commit()

    def list_all(self) -> List[sqlite3.Row]:
        """Return every entry, oldest first."""
        return self.db.conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()


class PatientRepository:
    """Stores and loads patient records."""

    _COLUMNS = ("patient_id",) + ALL_FIELDS + ("created_at",)

    def __init__(self, db: Database):
        self.db = db

    def add(self, name: str, info: Dict[str, str]) -> Patient:
        """Insert a new patient with a fresh ID and return it."""
        pid = self.db.next_patient_id()
        values = {"patient_id": pid, "name": name, "created_at": now()}
        values.update({f: info.get(f) for f in ALL_FIELDS if f != "name"})
        self.db.conn.execute(
            "INSERT INTO patients (%s) VALUES (%s)"
            % (", ".join(self._COLUMNS), ", ".join("?" * len(self._COLUMNS))),
            [values[c] for c in self._COLUMNS],
        )
        self.db.conn.commit()
        return self.get(pid)

    def get(self, patient_id: str) -> Optional[Patient]:
        """Return the patient with this ID, or None."""
        row = self.db.conn.execute(
            "SELECT * FROM patients WHERE patient_id=?", (patient_id,)).fetchone()
        return Patient(**dict(row)) if row else None

    def update_fields(self, patient_id: str, changes: Dict[str, Optional[str]]) -> None:
        """Update several fields with one UPDATE statement.

        Raises:
            ValidationError: If a field is not in UPDATABLE_PATIENT_FIELDS.
        """
        unknown = [f for f in changes if f not in UPDATABLE_PATIENT_FIELDS]
        if unknown:
            raise ValidationError("Field(s) cannot be updated: %s" % ", ".join(unknown))
        if not changes:
            return
        # column names come from the whitelist, values are bound parameters
        columns = [f for f in UPDATABLE_PATIENT_FIELDS if f in changes]
        assignments = ", ".join("%s=?" % c for c in columns)
        self.db.conn.execute(
            "UPDATE patients SET %s WHERE patient_id=?" % assignments,
            [changes[c] for c in columns] + [patient_id],
        )
        self.db.conn.commit()

    def delete(self, patient_id: str) -> None:
        """Delete a patient; their notes are removed by ON DELETE CASCADE."""
        self.db.conn.execute("DELETE FROM patients WHERE patient_id=?", (patient_id,))
        self.db.conn.commit()


class VisitRepository:
    """Stores visit notes and AI feedback."""

    def __init__(self, db: Database):
        self.db = db

    def add(self, patient_id: str, created_by: str, reason: str) -> VisitNote:
        """Insert a dated note and return it."""
        cur = self.db.conn.execute(
            "INSERT INTO visit_notes (patient_id, created_by, created_at, reason) "
            "VALUES (?,?,?,?)",
            (patient_id, created_by, now(), reason),
        )
        self.db.conn.commit()
        return self.get(cur.lastrowid)

    def get(self, note_id: int) -> Optional[VisitNote]:
        """Return the note with this ID, or None."""
        row = self.db.conn.execute(
            "SELECT * FROM visit_notes WHERE note_id=?", (note_id,)).fetchone()
        return VisitNote(**dict(row)) if row else None

    def list_for_patient(self, patient_id: str) -> List[VisitNote]:
        """Return a patient's notes, oldest first."""
        rows = self.db.conn.execute(
            "SELECT * FROM visit_notes WHERE patient_id=? ORDER BY created_at, note_id",
            (patient_id,),
        ).fetchall()
        return [VisitNote(**dict(r)) for r in rows]

    def set_category(self, note_id: int, category: str, source: str) -> None:
        """Store a note's category and where it came from."""
        self.db.conn.execute(
            "UPDATE visit_notes SET category=?, category_source=? WHERE note_id=?",
            (category, source, note_id),
        )
        self.db.conn.commit()

    def add_feedback(self, note_id: int, rating: str) -> None:
        """Store a rating for a category suggestion."""
        self.db.conn.execute(
            "INSERT INTO ai_feedback (note_id, rating, created_at) VALUES (?,?,?)",
            (note_id, rating, now()),
        )
        self.db.conn.commit()
