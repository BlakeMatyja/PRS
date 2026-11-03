"""Patient model and PatientService (FR-01 to FR-04)."""
from typing import Dict, Optional

from .authentication import User, require_login, require_manager
from .exceptions import ImmutableFieldError, NotFoundError, PermissionDenied, ValidationError

BASIC_FIELDS = ("name", "date_of_birth", "phone", "email", "address")
CONFIDENTIAL_FIELDS = ("insurance_id", "confidential_notes")
ALL_FIELDS = BASIC_FIELDS + CONFIDENTIAL_FIELDS
RESTRICTED = "[RESTRICTED]"
_ID_NAMES = ("patient_id", "_patient_id")


class Patient:
    """A patient record whose Patient ID is fixed when the object is created."""

    __slots__ = ("_patient_id", "created_at") + ALL_FIELDS

    def __init__(self, patient_id: str, name: str, created_at: str,
                 date_of_birth: Optional[str] = None, phone: Optional[str] = None,
                 email: Optional[str] = None, address: Optional[str] = None,
                 insurance_id: Optional[str] = None,
                 confidential_notes: Optional[str] = None):
        # bypass the guard in __setattr__ for the one allowed assignment
        object.__setattr__(self, "_patient_id", patient_id)
        self.name = name
        self.created_at = created_at
        self.date_of_birth = date_of_birth
        self.phone = phone
        self.email = email
        self.address = address
        self.insurance_id = insurance_id
        self.confidential_notes = confidential_notes

    @property
    def patient_id(self) -> str:
        """The permanent, system-generated Patient ID (read-only)."""
        return self._patient_id

    def __setattr__(self, name: str, value) -> None:
        if name in _ID_NAMES:
            raise ImmutableFieldError("The Patient ID can never be changed.")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in _ID_NAMES:
            raise ImmutableFieldError("The Patient ID can never be removed.")
        object.__delattr__(self, name)

    def to_dict(self) -> Dict[str, Optional[str]]:
        """Return the record's fields in display order."""
        data = {"patient_id": self._patient_id, "name": self.name,
                "created_at": self.created_at}
        data.update({f: getattr(self, f) for f in ALL_FIELDS if f != "name"})
        return data

    def __repr__(self) -> str:
        return "Patient(patient_id=%r, name=%r)" % (self._patient_id, self.name)


def can_access_field(user: User, field_name: str) -> bool:
    """Return True if the user may view and edit this field.

    Basic fields are open to all staff; confidential fields need clearance.
    """
    if field_name in BASIC_FIELDS:
        return True
    return user.is_manager or field_name in user.clearance


class PatientService:
    """Registers, retrieves, edits and deletes patient records."""

    def __init__(self, patient_repo, audit_repo):
        self.patients = patient_repo
        self.audit = audit_repo

    def register_patient(self, user: User, name: str, **info: str) -> Patient:
        """Create a record with a system-generated unique ID (FR-01, FR-02).

        Args:
            user: The logged-in staff member.
            name: Patient's full name (required).
            **info: Optional fields from ALL_FIELDS.

        Returns:
            The newly stored Patient.

        Raises:
            ValidationError: If the name is blank or a field is unknown.
        """
        require_login(user)
        name = (name or "").strip()
        if not name:
            raise ValidationError("Patient name is required.")
        _check_known_fields(info)
        patient = self.patients.add(name, info)
        self.audit.log(user.username, "REGISTER_PATIENT", patient.patient_id, name)
        return patient

    def get_patient(self, user: User, patient_id: str) -> Patient:
        """Retrieve a patient by ID (FR-03).

        Confidential fields are replaced with RESTRICTED if the user lacks clearance.

        Raises:
            NotFoundError: If no patient has this ID.
        """
        require_login(user)
        patient = self._require_patient(patient_id)
        for field_name in CONFIDENTIAL_FIELDS:
            if not can_access_field(user, field_name):
                setattr(patient, field_name, RESTRICTED)
        return patient

    def update_patient(self, user: User, patient_id: str, changes: Dict[str, str]) -> None:
        """Edit permitted fields and log each change (FR-04). The ID is never editable.

        Args:
            user: The logged-in staff member.
            patient_id: ID of the record to edit.
            changes: Field name to new value.

        Raises:
            ImmutableFieldError: If changes include the Patient ID.
            ValidationError: If a field is unknown or the name is blank.
            PermissionDenied: If the user lacks clearance for a field.
            NotFoundError: If no patient has this ID.
        """
        require_login(user)
        if "patient_id" in changes:
            raise ImmutableFieldError("The Patient ID can never be changed.")
        _check_known_fields(changes)
        for field_name in changes:
            if not can_access_field(user, field_name):
                raise PermissionDenied("You are not cleared to edit '%s'." % field_name)
        if "name" in changes and not (changes["name"] or "").strip():
            raise ValidationError("Patient name cannot be blank.")
        current = self._require_patient(patient_id)
        self.patients.update_fields(patient_id, changes)
        details = ["%s: %r -> %r" % (f, getattr(current, f), v) for f, v in changes.items()]
        self.audit.log_many(user.username, "UPDATE_PATIENT", patient_id, details)

    def delete_patient(self, user: User, patient_id: str) -> None:
        """Delete a patient and their notes. Manager only.

        Raises:
            PermissionDenied: If the user is not a manager.
            NotFoundError: If no patient has this ID.
        """
        require_manager(user)
        self._require_patient(patient_id)
        self.patients.delete(patient_id)
        self.audit.log(user.username, "DELETE_PATIENT", patient_id, "")

    def _require_patient(self, patient_id: str) -> Patient:
        patient = self.patients.get(patient_id)
        if patient is None:
            raise NotFoundError("No patient was found with ID '%s'." % patient_id)
        return patient


def _check_known_fields(fields) -> None:
    unknown = [f for f in fields if f not in ALL_FIELDS]
    if unknown:
        raise ValidationError("Unknown field: %s" % ", ".join(unknown))
