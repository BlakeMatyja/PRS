"""Authentication and role/clearance checks (NFR-02)."""
import hashlib
import hmac
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .exceptions import AuthenticationError, PermissionDenied

ROLE_STAFF = "staff"
ROLE_MANAGER = "manager"
PBKDF2_ITERATIONS = 100_000


@dataclass
class User:
    """A staff account and the confidential fields it is cleared to use."""

    username: str
    full_name: str
    role: str
    clearance: List[str] = field(default_factory=list)

    @property
    def is_manager(self) -> bool:
        """Return True if this user has the manager role."""
        return self.role == ROLE_MANAGER


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Hash a password with PBKDF2-SHA256.

    Args:
        password: Plain-text password.
        salt: Hex salt to reuse, or None to generate a new one.

    Returns:
        A (hash_hex, salt_hex) pair.
    """
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt),
                                 PBKDF2_ITERATIONS)
    return digest.hex(), salt


def require_login(user: Optional[User]) -> None:
    """Block access unless a user is logged in (NFR-02).

    Raises:
        AuthenticationError: If no user is logged in.
    """
    if user is None:
        raise AuthenticationError("You must be logged in to do this.")


def require_manager(user: Optional[User]) -> None:
    """Block access unless the logged-in user is a manager.

    Raises:
        AuthenticationError: If no user is logged in.
        PermissionDenied: If the user is not a manager.
    """
    require_login(user)
    if not user.is_manager:
        raise PermissionDenied("Only the clinic manager can do this.")


class AuthService:
    """Logs staff in and manages their confidential-field clearance."""

    def __init__(self, user_repo, audit_repo):
        self.users = user_repo
        self.audit = audit_repo

    def seed_default_users(self) -> None:
        """Create synthetic demo accounts on first run."""
        if self.users.count() == 0:
            self.users.add("manager1", "Dana Manager", ROLE_MANAGER, "manager123", [])
            self.users.add("staff1", "Sam Staff", ROLE_STAFF, "staff123", [])
            self.users.add("staff2", "Riley Staff", ROLE_STAFF, "staff456", [])

    def login(self, username: str, password: str) -> User:
        """Check a username and password and return the matching user.

        Args:
            username: Account name.
            password: Plain-text password.

        Returns:
            The logged-in User.

        Raises:
            AuthenticationError: If the username or password is wrong.
        """
        record = self.users.get_record(username)
        if record is None:
            raise AuthenticationError("Invalid username or password.")
        attempt, _ = hash_password(password, record["salt"])
        if not hmac.compare_digest(attempt, record["password_hash"]):
            raise AuthenticationError("Invalid username or password.")
        self.audit.log(username, "LOGIN", username, "")
        return self.users.get(username)

    def set_clearance(self, manager: User, username: str, fields: List[str]) -> None:
        """Set which confidential fields a staff member may view and edit.

        Args:
            manager: The logged-in manager making the change.
            username: Staff account to update.
            fields: Confidential field names to allow.

        Raises:
            PermissionDenied: If the caller is not a manager.
        """
        require_manager(manager)
        self.users.set_clearance(username, fields)
        self.audit.log(manager.username, "SET_CLEARANCE", username, ",".join(fields))
