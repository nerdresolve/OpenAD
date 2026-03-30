"""
ldap_service.py — AD password change business logic.

Orchestrates the two-step password change flow:
  1. Service account resolves the user's Distinguished Name (read-only lookup).
  2. User binds with their own credentials (authentication proof).
  3. unicodePwd modify (DELETE old + ADD new) enforces all AD GPO policies.
"""
import logging

import ldap3
from ldap3 import MODIFY_ADD, MODIFY_DELETE
from ldap3.core.exceptions import LDAPBindError, LDAPException
from ldap3.utils.conv import escape_filter_chars

from app.config import settings
from app.ldap_client import build_server, extract_ad_error_code, open_connection

logger = logging.getLogger("openad")

# Mapping of AD sub-error codes to user-facing Portuguese messages
_AD_ERROR_MESSAGES: dict[str, str] = {
    "52e": "Usuario ou senha atual incorretos.",
    "530": "Conta sem permissao de acesso neste horario.",
    "531": "Conta sem permissao de acesso nesta estacao de trabalho.",
    "532": "Senha expirada. Entre em contato com o suporte de TI.",
    "533": "Conta desabilitada. Entre em contato com o suporte de TI.",
    "701": "Conta expirada. Entre em contato com o suporte de TI.",
    "773": "A senha deve ser alterada no proximo logon. Utilize o Windows para esta operacao.",
    "775": "Conta bloqueada. Entre em contato com o suporte de TI.",
}

# Mapping of LDAP result description fragments to user-facing messages
_CONSTRAINT_MESSAGES: list[tuple[str, str]] = [
    ("check_password_restrictions", "A nova senha nao atende aos requisitos de complexidade."),
    ("will not perform", "Alteracao de senha recusada pela politica do servidor."),
    ("unwilling to perform", "Alteracao de senha recusada pela politica do servidor."),
    ("constraint violation", "A nova senha viola a politica do Active Directory (complexidade, historico ou tempo minimo)."),
    ("insufficient access rights", "Permissao insuficiente. Verifique as permissoes da conta de servico."),
]


def _user_facing_error(exc: Exception) -> str:
    """Map an LDAP exception to a safe, user-facing Portuguese message."""
    raw = str(exc)
    code = extract_ad_error_code(raw)
    if code and code in _AD_ERROR_MESSAGES:
        return _AD_ERROR_MESSAGES[code]

    lower = raw.lower()
    for fragment, message in _CONSTRAINT_MESSAGES:
        if fragment in lower:
            return message

    return "Falha ao alterar a senha. Verifique os dados informados e tente novamente."


def _lookup_user_dn(upn: str) -> str | None:
    """
    Resolve the user's Distinguished Name via the read-only service account.

    Using a service account for this lookup keeps DN resolution independent of
    the user's credential state (e.g. expired password, locked account) and
    avoids leaking directory structure through error messages.
    """
    server = build_server()
    safe_upn = escape_filter_chars(upn)
    try:
        conn = open_connection(
            server,
            user=settings.LDAP_BIND_USER,
            password=settings.LDAP_BIND_PASSWORD,
            read_only=True,
        )
        conn.search(
            search_base=settings.LDAP_BASE_DN,
            search_filter="(userPrincipalName=%s)" % safe_upn,
            search_scope=ldap3.SUBTREE,
            attributes=["distinguishedName"],
        )
        if not conn.entries:
            conn.unbind()
            logger.info("ldap.lookup status=not_found upn=%s", upn)
            return None
        dn = conn.entries[0].entry_dn
        conn.unbind()
        logger.info("ldap.lookup status=ok upn=%s", upn)
        return dn
    except LDAPException as exc:
        logger.error("ldap.lookup status=error upn=%s error=%s", upn, type(exc).__name__)
        return None


def change_password(
    upn: str,
    current_password: str,
    new_password: str,
) -> tuple[bool, str]:
    """
    Execute a user-initiated AD password change.

    Flow:
      1. Resolve DN via service account (read-only, no user credential needed).
      2. Bind as the user with their current password (authentication proof).
      3. Modify unicodePwd: DELETE encoded old password, ADD encoded new password
         in a single atomic operation — AD enforces history, complexity, and
         minimum age policies at this step.

    Returns:
        (True, success_message) or (False, user_facing_error_message)
    """
    # Step 1 — Resolve DN
    user_dn = _lookup_user_dn(upn)
    if not user_dn:
        return False, "Conta de usuario nao encontrada."

    server = build_server()

    # Step 2 — Authenticate as user
    try:
        conn = open_connection(
            server,
            user=upn,
            password=current_password,
            read_only=False,
        )
        logger.info("ldap.auth status=ok upn=%s", upn)
    except LDAPBindError as exc:
        logger.info("ldap.auth status=bind_failed upn=%s error=%s", upn, type(exc).__name__)
        return False, _user_facing_error(exc)
    except LDAPException as exc:
        logger.error("ldap.auth status=connection_error upn=%s error=%s", upn, type(exc).__name__)
        return False, "Nao foi possivel conectar ao servidor de autenticacao. Tente novamente mais tarde."

    # Step 3 — Change password
    try:
        # AD unicodePwd encoding: UTF-16-LE wrapped in double quotes
        encoded_old = ('"%s"' % current_password).encode("utf-16-le")
        encoded_new = ('"%s"' % new_password).encode("utf-16-le")

        result = conn.modify(
            user_dn,
            {
                "unicodePwd": [
                    (MODIFY_DELETE, [encoded_old]),
                    (MODIFY_ADD, [encoded_new]),
                ]
            },
        )

        if not result:
            description = conn.result.get("description", "unknown") if conn.result else "unknown"
            logger.info(
                "ldap.change_password status=failed upn=%s result_description=%s",
                upn, description,
            )
            conn.unbind()
            return False, _user_facing_error(Exception(str(conn.result)))

        conn.unbind()
        logger.info("ldap.change_password status=success upn=%s", upn)
        return True, "Senha alterada com sucesso."

    except LDAPException as exc:
        logger.info("ldap.change_password status=error upn=%s error=%s", upn, type(exc).__name__)
        try:
            conn.unbind()
        except Exception:
            pass
        return False, _user_facing_error(exc)
