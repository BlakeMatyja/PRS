"""Turns PRS objects into display text for the console."""
import sqlite3

from .patient import Patient
from .visit import VisitNote

DIVIDER = "-" * 40


def format_patient(patient: Patient) -> str:
    """Return a patient record as aligned label/value lines."""
    lines = ["%-20s %s" % (key, value) for key, value in patient.to_dict().items()]
    return "\n".join([DIVIDER] + lines + [DIVIDER])


def format_note(note: VisitNote) -> str:
    """Return one visit note as a single history line."""
    return "[%s] #%d by %s | %s | %s" % (note.created_at, note.note_id, note.created_by,
                                         note.category or "no category", note.reason)


def format_audit_row(row: sqlite3.Row) -> str:
    """Return one audit log entry as a single line."""
    return "%s | %-8s | %-16s | %s | %s" % (row["timestamp"], row["username"], row["action"],
                                            row["target"], row["details"])
