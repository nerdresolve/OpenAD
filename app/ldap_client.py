"""
ldap_client.py — Low-level LDAP connection factory.

Responsible for building Server and Connection objects according to the
configured transport mode (plain, StartTLS, or LDAPS). No business logic lives
here — only connection construction and lifecycle helpers.
"""
import logging
import re
import ssl

import ldap3
from ldap3 import Connection, Server, Tls
from ldap3.core.exceptions import LDAPException

from app.config import settings

logger = logging.getLogger("openad")


def _build_tls() -> Tls | None:
    """
    Build a Tls object for StartTLS or LDAPS connections.
    Returns None when neither mode is active.
    """
    if not (settings.LDAP_USE_SSL or settings.LDAP_USE_TLS):
        return None

    if settings.CA_CERT_PATH:
        return Tls(
            validate=ssl.CERT_REQUIRED,
            ca_certs_file=settings.CA_CERT_PATH,
            version=ssl.PROTOCOL_TLS_CLIENT,
        )

    # No CA cert provided — disable peer validation.
    # Acceptable on isolated internal networks; not recommended for production
    # with routable addresses. Set CA_CERT_PATH to enable full validation.
    return Tls(validate=ssl.CERT_NONE)


def build_server() -> Server:
    """
    Create a reusable ldap3 Server object.
    get_info=NONE prevents anonymous schema queries on bind.
    """
    tls = _build_tls()
    return Server(
        settings.LDAP_SERVER,
        port=settings.LDAP_PORT,
        use_ssl=settings.LDAP_USE_SSL,
        tls=tls,
        get_info=ldap3.NONE,
        connect_timeout=5,
    )


def open_connection(
    server: Server,
    user: str,
    password: str,
    read_only: bool = False,
) -> Connection:
    """
    Open and bind an LDAP connection for the given credentials.

    Applies StartTLS upgrade before bind when LDAP_USE_TLS is true.
    Raises LDAPException subclasses on any failure — callers handle them.
    """
    conn = Connection(
        server,
        user=user,
        password=password,
        authentication=ldap3.SIMPLE,
        raise_exceptions=True,
        read_only=read_only,
        receive_timeout=10,
    )

    if settings.LDAP_USE_TLS:
        conn.open()
        conn.start_tls()

    conn.bind()
    return conn


def extract_ad_error_code(message: str) -> str | None:
    """
    Parse the AD-specific sub-error code from an LDAP error string.
    AD error messages follow the pattern: '... data <hex_code>, ...'
    Example: '80090308: LdapErr: DSID-0C09044E, comment: AcceptSecurityContext
              error, data 52e, v2580'
    """
    match = re.search(r",\s*data\s+([0-9a-fA-F]+)", message)
    return match.group(1).lower() if match else None


def probe_service_account() -> tuple[bool, str]:
    """
    Verify the service account can bind to the directory.
    Used at startup and by the /health endpoint.
    Returns (ok: bool, detail: str).
    """
    server = build_server()
    try:
        conn = open_connection(
            server,
            user=settings.LDAP_BIND_USER,
            password=settings.LDAP_BIND_PASSWORD,
            read_only=True,
        )
        conn.unbind()
        logger.info("ldap.probe status=ok server=%s port=%d", settings.LDAP_SERVER, settings.LDAP_PORT)
        return True, "LDAP connection successful."
    except LDAPException as exc:
        logger.error(
            "ldap.probe status=failed server=%s port=%d error=%s",
            settings.LDAP_SERVER, settings.LDAP_PORT, type(exc).__name__,
        )
        return False, "LDAP connection failed: %s" % type(exc).__name__
