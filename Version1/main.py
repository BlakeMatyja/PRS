"""Command-line interface for the PRS (Version 1)."""
import getpass
import sys

from prs.ai_integration import CATEGORIES, CategorizationService
from prs.authentication import AuthService
from prs.exceptions import AuthenticationError, PRSError
from prs.patient import ALL_FIELDS, CONFIDENTIAL_FIELDS, PatientService
from prs.persistence import (AuditRepository, Database, PatientRepository,
                             UserRepository, VisitRepository)
from prs.visit import RATINGS, VisitService


class PRSApp:
    def __init__(self, db_path="prs.db"):
        db = Database(db_path)
        self.users = UserRepository(db)
        audit = AuditRepository(db)
        patients = PatientRepository(db)
        visits = VisitRepository(db)
        self.audit = audit
        self.auth = AuthService(self.users, audit)
        self.patient_service = PatientService(patients, audit)
        self.visit_service = VisitService(visits, patients, audit, CATEGORIES)
        self.ai = CategorizationService.from_environment()
        self.user = None
        self.auth.seed_default_users()

    # ---- screens ----
    def login(self):
        for _ in range(3):
            username = input("Username: ").strip()
            password = getpass.getpass("Password: ")
            try:
                self.user = self.auth.login(username, password)
                print("Welcome, %s (%s)." % (self.user.full_name, self.user.role))
                return True
            except AuthenticationError as exc:
                print("Warning:", exc)
        return False

    def register_patient(self):
        name = input("Patient name (required): ")
        info = {}
        for f in ALL_FIELDS:
            if f == "name":
                continue
            if f in CONFIDENTIAL_FIELDS and not (self.user.is_manager or f in self.user.clearance):
                continue
            value = input("%s (optional): " % f).strip()
            if value:
                info[f] = value
        patient = self.patient_service.register_patient(self.user, name, **info)
        print("Registered. Patient ID: %s" % patient.patient_id)

    def show_patient(self):
        pid = input("Patient ID: ").strip()
        patient = self.patient_service.get_patient(self.user, pid)
        print("-" * 40)
        for key, value in vars(patient).items():
            print("%-20s %s" % (key, value))
        print("-" * 40)

    def edit_patient(self):
        pid = input("Patient ID: ").strip()
        field_name = input("Field to edit (%s): " % ", ".join(ALL_FIELDS)).strip()
        value = input("New value: ").strip()
        self.patient_service.update_patient(self.user, pid, {field_name: value})
        print("Updated.")

    def add_visit_note(self):
        pid = input("Patient ID: ").strip()
        reason = input("Reason for visit / note: ")
        note = self.visit_service.add_note(self.user, pid, reason)
        print("Note %d saved (%s by %s)." % (note.note_id, note.created_at, note.created_by))
        suggestion = self.ai.suggest(reason)
        if suggestion.category:
            print("Suggested category: %s  [%s]" % (suggestion.category, suggestion.message))
            print("(A suggested filing label only - not a diagnosis.)")
            choice = input("Accept (a) / Reject (r)? ").strip().lower()
            if choice == "a":
                self.visit_service.set_category(self.user, note.note_id, suggestion.category,
                                                suggestion.source)
                print("Category saved.")
                self._ask_rating(note.note_id)
                return
            self._ask_rating(note.note_id)
        else:
            print(suggestion.message)
        self._manual_category(note.note_id)

    def _ask_rating(self, note_id):
        rating = input("Rate this suggestion (%s) or Enter to skip: " % "/".join(RATINGS)).strip().lower()
        if rating:
            self.visit_service.record_ai_rating(self.user, note_id, rating)

    def _manual_category(self, note_id):
        print("Enter a category yourself, or press Enter to save without one:")
        for i, cat in enumerate(CATEGORIES, 1):
            print("  %d) %s" % (i, cat))
        choice = input("> ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(CATEGORIES):
            self.visit_service.set_category(self.user, note_id, CATEGORIES[int(choice) - 1], "staff")
            print("Category saved.")
        else:
            print("Note kept without a category.")

    def show_history(self):
        pid = input("Patient ID: ").strip()
        notes = self.visit_service.get_history(self.user, pid)
        if not notes:
            print("No visit notes for this patient.")
        for n in notes:
            print("[%s] #%d by %s | %s | %s" % (n.created_at, n.note_id, n.created_by,
                                               n.category or "no category", n.reason))

    def delete_patient(self):
        pid = input("Patient ID to delete: ").strip()
        if input("Type YES to confirm: ") == "YES":
            self.patient_service.delete_patient(self.user, pid)
            print("Patient deleted.")

    def set_clearance(self):
        username = input("Staff username: ").strip()
        raw = input("Confidential fields to allow (%s), comma-separated: " % ", ".join(CONFIDENTIAL_FIELDS))
        fields = [f.strip() for f in raw.split(",") if f.strip()]
        self.auth.set_clearance(self.user, username, fields)
        print("Clearance updated.")

    def show_audit_log(self):
        for row in self.audit.list_all():
            print("%s | %-8s | %-16s | %s | %s" % (row["timestamp"], row["username"], row["action"],
                                                    row["target"], row["details"]))

    # ---- main loop ----
    def run(self):
        if not self.login():
            print("Too many failed attempts.")
            return
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
        while True:
            print("\n=== PRS Menu ===")
            for key, (label, _) in actions.items():
                print("%s) %s" % (key, label))
            print("0) Exit")
            choice = input("> ").strip()
            if choice == "0":
                break
            if choice in actions:
                try:
                    actions[choice][1]()
                except PRSError as exc:
                    print("Warning:", exc)
            else:
                print("Invalid choice.")


if __name__ == "__main__":
    PRSApp().run()
