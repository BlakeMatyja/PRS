"""Visit note model and VisitService (FR-05, FR-06, FR-07)."""
from dataclasses import dataclass
from typing import List, Optional, Sequence

from .authentication import User, require_login
from .exceptions import NotFoundError, ValidationError

RATINGS = ("bad", "good", "great")


@dataclass
class VisitNote:
    """One dated note attached to an existing patient."""

    note_id: int
    patient_id: str
    created_by: str
    created_at: str
    reason: str
    category: Optional[str] = None
    category_source: Optional[str] = None  # "ai", "fallback", or "staff"


class VisitService:
    """Adds visit notes, stores approved categories and returns visit history."""

    def __init__(self, visit_repo, patient_repo, audit_repo, valid_categories: Sequence[str]):
        self.visits = visit_repo
        self.patients = patient_repo
        self.audit = audit_repo
        self.valid_categories = valid_categories

    def add_note(self, user: User, patient_id: str, reason: str) -> VisitNote:
        """Save a dated note for an existing patient, without a category (FR-05, AIR-01).

        Raises:
            ValidationError: If the note is empty.
            NotFoundError: If the patient does not exist.
        """
        require_login(user)
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError("A visit note cannot be empty.")
        self._require_patient(patient_id, "Cannot add a note: patient '%s' does not exist.")
        note = self.visits.add(patient_id, user.username, reason)
        self.audit.log(user.username, "ADD_VISIT_NOTE", patient_id, "note %d" % note.note_id)
        return note

    def set_category(self, user: User, note_id: int, category: str, source: str) -> None:
        """Store a category that staff accepted or entered (FR-07).

        Args:
            user: The logged-in staff member.
            note_id: Note to update.
            category: One of the valid categories.
            source: "ai", "fallback" or "staff".

        Raises:
            ValidationError: If the category is not valid.
            NotFoundError: If the note does not exist.
        """
        require_login(user)
        if category not in self.valid_categories:
            raise ValidationError("Invalid category: %s" % category)
        if self.visits.get(note_id) is None:
            raise NotFoundError("Visit note %s not found." % note_id)
        self.visits.set_category(note_id, category, source)
        self.audit.log(user.username, "SET_CATEGORY", "note %d" % note_id,
                       "%s (%s)" % (category, source))

    def record_ai_rating(self, user: User, note_id: int, rating: str) -> None:
        """Store staff feedback on a category suggestion.

        Raises:
            ValidationError: If the rating is not one of RATINGS.
        """
        require_login(user)
        if rating not in RATINGS:
            raise ValidationError("Rating must be one of: %s" % ", ".join(RATINGS))
        self.visits.add_feedback(note_id, rating)

    def get_history(self, user: User, patient_id: str) -> List[VisitNote]:
        """Return all notes for an existing patient, oldest first (FR-06).

        Raises:
            NotFoundError: If the patient does not exist.
        """
        require_login(user)
        self._require_patient(patient_id, "No patient was found with ID '%s'.")
        return self.visits.list_for_patient(patient_id)

    def _require_patient(self, patient_id: str, message: str) -> None:
        if self.patients.get(patient_id) is None:
            raise NotFoundError(message % patient_id)
