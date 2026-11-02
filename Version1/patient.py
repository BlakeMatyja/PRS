"""Patient model and PatientService (FR-01 to FR-04)."""
from dataclasses import dataclass
from typing import Dict, Optional

from .authentication import require_login, require_manager
from .exceptions import NotFoundError, PermissionDenied, ValidationError

BASIC_FIELDS = ("name", "date_of_birth", "phone", "email", "address")
CONFIDENTIAL_FIELDS = ("insurance_id", "confidential_notes")
ALL_FIELDS = BASIC_FIELDS + CONFIDENTIAL_FIELDS
RESTRICTED = "[RESTRICTED]"


@dataclass
class Patient:
    patient_id: str
    name: str
    created_at: str
    date_of_birth: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    insurance_id: Optional[str] = None
    confidential_notes: Optional[str] = None


def can_access_field(user, field_name):
    """Basic fields are visible to all users; confidential ones need clearance."""
    if field_name in BASIC_FIELDS:
        return True
    return user.is_manager or field_name in user.clearance


class PatientService:
    def __init__(self, patient_repo, audit_repo):
        self.patients = patient_repo
        self.audit = audit_repo

    def register_patient(self, user, name, **info) -> Patient:
        """FR-01, FR-02: create a record with a system-generated unique ID."""
        require_login(user)
        name = (name or "").strip()
        if not name:
            raise ValidationError("Patient name is required.")
        for key in info:
            if key not in ALL_FIELDS:
                raise ValidationError("Unknown field: %s" % key)
        patient = self.patients.add(name, info)
        self.audit.log(user.username, "REGISTER_PATIENT", patient.patient_id, name)
        return patient

    def get_patient(self, user, patient_id) -> Patient:
        """FR-03: retrieve by ID; confidential fields hidden without clearance."""
        require_login(user)
        patient = self.patients.get(patient_id)
        if patient is None:
            raise NotFoundError("No patient was found with ID '%s'." % patient_id)
        for field_name in CONFIDENTIAL_FIELDS:
            if not can_access_field(user, field_name):
                setattr(patient, field_name, RESTRICTED)
        return patient

    def update_patient(self, user, patient_id, changes: Dict[str, str]):
        """FR-04: edit permitted fields (never the Patient ID) and log each change."""
        require_login(user)
        if "patient_id" in changes:
            raise PermissionDenied("The Patient ID can never be changed.")
        current = self.patients.get(patient_id)
        if current is None:
            raise NotFoundError("No patient was found with ID '%s'." % patient_id)
        for field_name, value in changes.items():
            if field_name not in ALL_FIELDS:
                raise ValidationError("Unknown field: %s" % field_name)
            if not can_access_field(user, field_name):
                raise PermissionDenied("You are not cleared to edit '%s'." % field_name)
        if "name" in changes and not (changes["name"] or "").strip():
            raise ValidationError("Patient name cannot be blank.")
        self.patients.update_fields(patient_id, changes)
        for field_name, value in changes.items():
            old = getattr(current, field_name)
            self.audit.log(user.username, "UPDATE_PATIENT", patient_id,
                           "%s: %r -> %r" % (field_name, old, value))

    def delete_patient(self, user, patient_id):
        """Only the clinic manager may delete a patient."""
        require_manager(user)
        if self.patients.get(patient_id) is None:
            raise NotFoundError("No patient was found with ID '%s'." % patient_id)
        self.patients.delete(patient_id)
        self.audit.log(user.username, "DELETE_PATIENT", patient_id, "")
