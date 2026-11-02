"""Authentication and role/clearance checks (NFR-02)."""
import hashlib
import hmac
import os
from dataclasses import dataclass, field
from typing import List, Optional

from .exceptions import AuthenticationError, PermissionDenied

ROLE_STAFF = "staff"
ROLE_MANAGER = "manager"


@dataclass
class User:
    username: str
    full_name: str
    role: str
    clearance: List[str] = field(default_factory=list)  # confidential fields staff may see/edit

    @property
    def is_manager(self):
        return self.role == ROLE_MANAGER


def hash_password(password, salt=None):
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000)
    return digest.hex(), salt


def require_login(user):
    """Block all access unless a user is logged in (NFR-02)."""
    if user is None:
        raise AuthenticationError("You must be logged in to do this.")


def require_manager(user):
    require_login(user)
    if not user.is_manager:
        raise PermissionDenied("Only the clinic manager can do this.")


class AuthService:
    def __init__(self, user_repo, audit_repo):
        self.users = user_repo
        self.audit = audit_repo

    def seed_default_users(self):
        """Create synthetic demo accounts on first run."""
        if self.users.count() == 0:
            self.users.add("manager1", "Dana Manager", ROLE_MANAGER, "manager123", [])
            self.users.add("staff1", "Sam Staff", ROLE_STAFF, "staff123", [])
            self.users.add("staff2", "Riley Staff", ROLE_STAFF, "staff456", [])

    def login(self, username, password) -> User:
        record = self.users.get_record(username)
        if record is None:
            raise AuthenticationError("Invalid username or password.")
        attempt, _ = hash_password(password, record["salt"])
        if not hmac.compare_digest(attempt, record["password_hash"]):
            raise AuthenticationError("Invalid username or password.")
        user = self.users.get(username)
        self.audit.log(username, "LOGIN", username, "")
        return user

    def set_clearance(self, manager: User, username: str, fields: List[str]):
        """Manager decides which confidential fields a staff member may view/edit."""
        require_manager(manager)
        self.users.set_clearance(username, fields)
        self.audit.log(manager.username, "SET_CLEARANCE", username, ",".join(fields))
