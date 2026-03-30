"""
validators.py — Input validation for password change requests.

Validates UPN format and password constraints before any LDAP operation.
Also guards against LDAP injection in the UPN field.
"""
import re


# Accepts standard internet UPNs (user@domain.tld) and
# internal AD UPNs with single-label domains (user@domain.local)
_UPN_PATTERN = re.compile(
    r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+(\.[a-zA-Z0-9\-]+)*$"
)

# Characters that have special meaning in LDAP filter syntax
_LDAP_INJECTION_CHARS = re.compile(r"[\\*()\x00/]")

_MIN_PASSWORD_LENGTH = 12
_MAX_PASSWORD_LENGTH = 128
_MAX_UPN_LENGTH = 256


def validate_upn(upn: str) -> str | None:
    """Validate UPN format. Returns an error message or None if valid."""
    if not upn:
        return "O usuario (UPN) e obrigatorio."
    if len(upn) > _MAX_UPN_LENGTH:
        return "O usuario excede o comprimento maximo permitido."
    if not _UPN_PATTERN.match(upn):
        return "Formato de usuario invalido. Use: usuario@dominio.local"
    if _LDAP_INJECTION_CHARS.search(upn):
        return "O usuario contem caracteres invalidos."
    return None


def _validate_password(password: str, label: str) -> str | None:
    """Validate a single password field. Returns an error message or None."""
    if not password:
        return "%s e obrigatoria." % label
    if len(password) < _MIN_PASSWORD_LENGTH:
        return "%s deve ter no minimo %d caracteres." % (label, _MIN_PASSWORD_LENGTH)
    if len(password) > _MAX_PASSWORD_LENGTH:
        return "%s excede o comprimento maximo permitido." % label
    return None


def validate_change_request(
    upn: str,
    current_password: str,
    new_password: str,
) -> str | None:
    """
    Validate all fields of a password change request.
    Returns the first validation error found, or None if all fields are valid.
    """
    error = validate_upn(upn)
    if error:
        return error

    error = _validate_password(current_password, "A senha atual")
    if error:
        return error

    error = _validate_password(new_password, "A nova senha")
    if error:
        return error

    if current_password == new_password:
        return "A nova senha deve ser diferente da senha atual."

    return None
