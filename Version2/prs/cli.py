"""Command-line interface for the PRS: reads input, calls services, prints results."""
import getpass
from typing import Callable, Dict, Optional, Tuple

from .ai_integration import CATEGORIES, Suggestion
from .app import PRSApplication
from .authentication import User
from .exceptions import AuthenticationError, PRSError
from .formatting import format_audit_row, format_note, format_patient
from .patient import ALL_FIELDS, CONFIDENTIAL_FIELDS, can_access_field
from .visit import RATINGS, VisitNote

MAX_LOGIN_ATTEMPTS = 3
Action = Tuple[str, Callable[[], None]]


class PRSConsole:
    """Menu-driven console. Input and output functions can be swapped for scripted runs."""

    def __init__(self, app: PRSApplication, read: Callable[[str], str] = input,
                 read_secret: Callable[[str], str] = getpass.getpass,
                 write: Callable[..., None] = print):
        self.app = app
        self._read = read
        self._read_secret = read_secret
        self._write = write
        self.user: Optional[User] = None

    # session

    def run(self) -> None:
        """Log in, then show the menu until the user exits."""
        if not self.login():
            self._write("Too many failed attempts.")
            return
        actions = self._menu_actions()
        while True:
            self._write("\n=== PRS Menu ===")
            for key, (label, _) in actions.items():
                self._write("%s) %s" % (key, label))
            self._write("0) Exit")
            choice = self._ask("> ")
            if choice == "0":
                break
            if choice not in actions:
                self._write("Invalid choice.")
                continue
            try:
                actions[choice][1]()
            except PRSError as exc:
                self._write("Warning:", exc)

    def login(self) -> bool:
        """Prompt for credentials up to MAX_LOGIN_ATTEMPTS times. Return True on success."""
        for _ in range(MAX_LOGIN_ATTEMPTS):
            username = self._ask("Username: ")
            password = self._read_secret("Password: ")
            try:
                self.user = self.app.auth.login(username, password)
            except AuthenticationError as exc:
                self._write("Warning:", exc)
                continue
            self._write("Welcome, %s (%s)." % (self.user.full_name, self.user.role))
            return True
        return False

    def _menu_actions(self) -> Dict[str, Action]:
        actions = {
            "1": ("Register patient", self.register_patient),
            "2": ("Search patient by ID", self.show_patient),
            "3": ("Edit patient", self.edit_patient),
            "4": ("Add visit note", self.add_visit_note),
            "5": ("View visit history", self.show_history),
        }
        if self.user.is_manager:
            actions["6"] = ("Delete patient", self.delete_patient)
            actions["7"] = ("Set staff clearance", self.set_clearance)
            actions["8"] = ("View audit log", self.show_audit_log)
        return actions

    # patient screens

    def register_patient(self) -> None:
        """Collect patient details and register a new patient."""
        name = self._read("Patient name (required): ")
        info = {}
        for field_name in ALL_FIELDS:
            if field_name == "name" or not can_access_field(self.user, field_name):
                continue
            value = self._ask("%s (optional): " % field_name)
            if value:
                info[field_name] = value
        patient = self.app.patients.register_patient(self.user, name, **info)
        self._write("Registered. Patient ID: %s" % patient.patient_id)

    def show_patient(self) -> None:
        """Look up and print one patient record."""
        patient = self.app.patients.get_patient(self.user, self._ask("Patient ID: "))
        self._write(format_patient(patient))

    def edit_patient(self) -> None:
        """Change one field of a patient record."""
        pid = self._ask("Patient ID: ")
        field_name = self._ask("Field to edit (%s): " % ", ".join(ALL_FIELDS))
        value = self._ask("New value: ")
        self.app.patients.update_patient(self.user, pid, {field_name: value})
        self._write("Updated.")

    def delete_patient(self) -> None:
        """Delete a patient after typed confirmation."""
        pid = self._ask("Patient ID to delete: ")
        if self._read("Type YES to confirm: ") == "YES":
            self.app.patients.delete_patient(self.user, pid)
            self._write("Patient deleted.")

    # visit screens

    def add_visit_note(self) -> None:
        """Save a visit note first, then offer a category suggestion."""
        pid = self._ask("Patient ID: ")
        reason = self._read("Reason for visit / note: ")
        note = self.app.visits.add_note(self.user, pid, reason)
        self._write("Note %d saved (%s by %s)." % (note.note_id, note.created_at,
                                                   note.created_by))
        self._categorize(note)

    def show_history(self) -> None:
        """Print every visit note for a patient."""
        notes = self.app.visits.get_history(self.user, self._ask("Patient ID: "))
        if not notes:
            self._write("No visit notes for this patient.")
        for note in notes:
            self._write(format_note(note))

    def _categorize(self, note: VisitNote) -> None:
        suggestion = self.app.categorizer.suggest(note.reason)
        if suggestion.category is None:
            self._write(suggestion.message)
        elif self._offer_suggestion(note, suggestion):
            return
        self._manual_category(note.note_id)

    def _offer_suggestion(self, note: VisitNote, suggestion: Suggestion) -> bool:
        """Show a suggestion and ask for a rating. Return True if it was accepted."""
        self._write("Suggested category: %s  [%s]" % (suggestion.category, suggestion.message))
        self._write("(A suggested filing label only - not a diagnosis.)")
        accepted = self._ask("Accept (a) / Reject (r)? ").lower() == "a"
        if accepted:
            self.app.visits.set_category(self.user, note.note_id, suggestion.category,
                                         suggestion.source)
            self._write("Category saved.")
        self._ask_rating(note.note_id)
        return accepted

    def _ask_rating(self, note_id: int) -> None:
        prompt = "Rate this suggestion (%s) or Enter to skip: " % "/".join(RATINGS)
        rating = self._ask(prompt).lower()
        if rating:
            self.app.visits.record_ai_rating(self.user, note_id, rating)

    def _manual_category(self, note_id: int) -> None:
        self._write("Enter a category yourself, or press Enter to save without one:")
        for number, category in enumerate(CATEGORIES, 1):
            self._write("  %d) %s" % (number, category))
        choice = self._ask("> ")
        if choice.isdigit() and 1 <= int(choice) <= len(CATEGORIES):
            self.app.visits.set_category(self.user, note_id, CATEGORIES[int(choice) - 1],
                                         "staff")
            self._write("Category saved.")
        else:
            self._write("Note kept without a category.")

    # manager screens

    def set_clearance(self) -> None:
        """Choose which confidential fields a staff member may use."""
        username = self._ask("Staff username: ")
        raw = self._read("Confidential fields to allow (%s), comma-separated: "
                         % ", ".join(CONFIDENTIAL_FIELDS))
        fields = [f.strip() for f in raw.split(",") if f.strip()]
        self.app.auth.set_clearance(self.user, username, fields)
        self._write("Clearance updated.")

    def show_audit_log(self) -> None:
        """Print the full audit log."""
        for row in self.app.audit.list_all():
            self._write(format_audit_row(row))

    def _ask(self, prompt: str) -> str:
        return self._read(prompt).strip()
