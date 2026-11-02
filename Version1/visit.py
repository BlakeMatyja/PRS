"""Visit note model and VisitService (FR-05, FR-06, FR-07)."""
from dataclasses import dataclass
from typing import List, Optional

from .authentication import require_login
from .exceptions import NotFoundError, ValidationError

RATINGS = ("bad", "good", "great")


@dataclass
class VisitNote:
    note_id: int
    patient_id: str
    created_by: str
    created_at: str
    reason: str
    category: Optional[str] = None
    category_source: Optional[str] = None  # "ai", "fallback", or "staff"


class VisitService:
    def __init__(self, visit_repo, patient_repo, audit_repo, valid_categories):
        self.visits = visit_repo
        self.patients = patient_repo
        self.audit = audit_repo
        self.valid_categories = valid_categories

    def add_note(self, user, patient_id, reason) -> VisitNote:
        """FR-05: note is saved first, without a category (AIR-01)."""
        require_login(user)
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError("A visit note cannot be empty.")
        if self.patients.get(patient_id) is None:
            raise NotFoundError("Cannot add a note: patient '%s' does not exist." % patient_id)
        note = self.visits.add(patient_id, user.username, reason)
        self.audit.log(user.username, "ADD_VISIT_NOTE", patient_id, "note %d" % note.note_id)
        return note

    def set_category(self, user, note_id, category, source):
        """FR-07: store a category only after staff approved or entered it."""
        require_login(user)
        if category not in self.valid_categories:
            raise ValidationError("Invalid category: %s" % category)
        if self.visits.get(note_id) is None:
            raise NotFoundError("Visit note %s not found." % note_id)
        self.visits.set_category(note_id, category, source)
        self.audit.log(user.username, "SET_CATEGORY", "note %d" % note_id,
                       "%s (%s)" % (category, source))

    def record_ai_rating(self, user, note_id, rating):
        require_login(user)
        if rating not in RATINGS:
            raise ValidationError("Rating must be one of: %s" % ", ".join(RATINGS))
        self.visits.add_feedback(note_id, rating)

    def get_history(self, user, patient_id) -> List[VisitNote]:
        """FR-06: visit history for an existing patient."""
        require_login(user)
        if self.patients.get(patient_id) is None:
            raise NotFoundError("No patient was found with ID '%s'." % patient_id)
        return self.visits.list_for_patient(patient_id)
