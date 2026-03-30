import os


class Settings:
    """
    Application configuration loaded exclusively from environment variables.
    No secrets are stored in source code or default values.
    """

    # LDAP server address
    LDAP_SERVER: str = os.getenv("LDAP_SERVER", "")
    LDAP_PORT: int = int(os.getenv("LDAP_PORT", "389"))
    LDAP_DOMAIN: str = os.getenv("LDAP_DOMAIN", "")
    LDAP_BASE_DN: str = os.getenv("LDAP_BASE_DN", "")

    # Transport security
    # LDAP_USE_SSL=true  → LDAPS (implicit TLS, port 636)
    # LDAP_USE_TLS=true  → StartTLS upgrade on plain connection (port 389)
    # Both false         → plain LDAP (port 389, dev/internal only)
    LDAP_USE_SSL: bool = os.getenv("LDAP_USE_SSL", "false").lower() == "true"
    LDAP_USE_TLS: bool = os.getenv("LDAP_USE_TLS", "false").lower() == "true"

    # Path to CA certificate file — required when LDAP_USE_SSL or LDAP_USE_TLS is true
    # and the server uses a self-signed or internal CA certificate.
    CA_CERT_PATH: str = os.getenv("CA_CERT_PATH", "")

    # Service account — used for read-only DN lookup only
    LDAP_BIND_USER: str = os.getenv("LDAP_BIND_USER", "")
    LDAP_BIND_PASSWORD: str = os.getenv("LDAP_BIND_PASSWORD", "")

    # Rate limiting
    RATE_LIMIT_MAX: int = int(os.getenv("RATE_LIMIT_MAX", "5"))
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", "300"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    def validate(self) -> list[str]:
        """Return list of missing or invalid required configuration fields."""
        missing = []
        if not self.LDAP_SERVER:
            missing.append("LDAP_SERVER")
        if not self.LDAP_DOMAIN:
            missing.append("LDAP_DOMAIN")
        if not self.LDAP_BASE_DN:
            missing.append("LDAP_BASE_DN")
        if not self.LDAP_BIND_USER:
            missing.append("LDAP_BIND_USER")
        if not self.LDAP_BIND_PASSWORD:
            missing.append("LDAP_BIND_PASSWORD")
        if self.LDAP_USE_SSL and self.LDAP_USE_TLS:
            missing.append("LDAP_USE_SSL and LDAP_USE_TLS cannot both be true")
        return missing


settings = Settings()
