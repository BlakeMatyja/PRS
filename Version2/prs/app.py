"""Builds the PRS object graph: database, repositories and services."""
from typing import Optional

from .ai_integration import CATEGORIES, CategorizationService
from .authentication import AuthService
from .patient import PatientService
from .persistence import (AuditRepository, Database, PatientRepository, UserRepository,
                          VisitRepository)
from .visit import VisitService


class PRSApplication:
    """Creates and connects every PRS component. Holds no user interface code."""

    def __init__(self, db_path: str = "prs.db",
                 categorizer: Optional[CategorizationService] = None):
        db = Database(db_path)
        patients = PatientRepository(db)
        visits = VisitRepository(db)
        self.audit = AuditRepository(db)
        self.auth = AuthService(UserRepository(db), self.audit)
        self.patients = PatientService(patients, self.audit)
        self.visits = VisitService(visits, patients, self.audit, CATEGORIES)
        self.categorizer = categorizer or CategorizationService.from_environment()
        self.auth.seed_default_users()
