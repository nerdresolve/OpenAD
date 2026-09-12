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
    # LDAPS has been disabled in this application.
    # LDAP_USE_TLS=true  → StartTLS upgrade on plain connection (port 389)
    # When false         → plain LDAP (port 389, dev/internal only)
    LDAP_USE_SSL: bool = False
    LDAP_USE_TLS: bool = os.getenv("LDAP_USE_TLS", "false").lower() == "true"

    # Path to CA certificate file — used when LDAP_USE_TLS is true
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

    # Branding — the portal carries the operator's identity, not the vendor's.
    # Served by GET /api/branding and applied by the page at load time, so a
    # deployment rebrands itself without editing HTML or rebuilding the image.
    BRAND_NAME: str = os.getenv("BRAND_NAME", "OpenAD")
    BRAND_LOGO_URL: str = os.getenv("BRAND_LOGO_URL", "/static/brand-mark.svg")
    BRAND_COLOR: str = os.getenv("BRAND_COLOR", "#7C3AED")
    BRAND_COLOR_ACCENT: str = os.getenv("BRAND_COLOR_ACCENT", "#A855F7")
    BRAND_FOOTER: str = os.getenv("BRAND_FOOTER", "")

    # Example UPN shown in the username field placeholder. Set it to your own
    # domain so users are not left guessing the expected format.
    BRAND_UPN_EXAMPLE: str = os.getenv("BRAND_UPN_EXAMPLE", "usuario@empresa.local")

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
        return missing


settings = Settings()
