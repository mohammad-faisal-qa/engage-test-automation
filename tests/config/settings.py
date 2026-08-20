"""Test-suite settings.

The one place the test code reads the environment. Values come from this
repository's own `.env` and fall back to localhost, which means a fresh clone
runs against a local server with no setup at all.

`TEST_API_KEY` is duplicated here rather than shared. The application lives in a
separate repository (`engage-app`), so this suite cannot read its `.env`, and the
two copies have to be kept in step by hand — a stale copy is the likeliest reason
for a sudden wall of failures.

Environment variables win over `.env`, which is what lets CI point the same
suite at a service container or the deployed demo by exporting `API_BASE_URL`.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# settings.py -> config/ -> tests/ -> engage/   (the .env lives at the repo root)
REPO_ROOT = Path(__file__).resolve().parents[2]

# Roles, ranked. The application enforces viewer < editor < admin.
ROLES = ("viewer", "editor", "admin")

# The two seeded tenants.
TENANTS = ("acme", "globex")


class TestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- targets ---
    api_base_url: str = "http://127.0.0.1:8000"
    # localhost, not 127.0.0.1: Vite's dev server binds to ::1 by default, so
    # the numeric form never answers even though the port is open. Anyone who
    # copied the API's 127.0.0.1 style here would get connection refused and
    # blame Playwright.
    web_base_url: str = "http://localhost:5173"

    # --- credentials ---
    # Every seeded user shares one password; see api/app/seed.py in engage-app.
    seed_password: str = "Password123!"
    # Seeded logins are role@tenant.example.com.
    seed_email_domain: str = "example.com"

    # Guards /api/test/reset. Read from this repo's .env; without it the suite
    # cannot put the database into a known state and says so loudly.
    test_api_key: str = ""
    webhook_secret: str = ""

    # --- behaviour ---
    request_timeout: float = 30.0

    # Polling defaults for asynchronous work (campaign sends, Phase 2).
    poll_timeout: float = 30.0
    poll_interval: float = 0.25

    # Set RESET_DATABASE=false to run against an environment that must not be
    # wiped — a shared demo, or someone else's session.
    reset_database: bool = True

    # --- the database assertion layer (Phase 9) ---
    # Its own variable, never the application's DATABASE_URL. Unset means the
    # db-marked tests skip, so a fresh clone runs green with no database at all.
    # In CI this points at the Postgres service container and never at Neon.
    test_database_url: str = ""

    # --- protecting the live demo ---
    # A reset is total, so the suite has to be able to recognise the one target
    # it must never perform one against. See utils/safety.py and DEF-005.
    production_endpoint_id: str = "ep-round-snow-axyc70lw"
    production_api_hosts: str = "engage-api-b6yg.onrender.com"
    # The deliberate override. Named rather than a bare boolean so that reading
    # a CI file makes it obvious what was switched off.
    allow_production_reset: bool = False

    @property
    def production_api_host_list(self) -> tuple[str, ...]:
        return tuple(h.strip() for h in self.production_api_hosts.split(",") if h.strip())

    # --- provenance ---
    # Which commit of the application was tested. CI knows this exactly: it
    # checks engage-app out and can pass the SHA in. Locally it is discovered
    # from a sibling checkout, and if there isn't one the report says "unknown"
    # rather than guessing — a wrong SHA is worse than an absent one.
    app_commit_sha: str = ""
    app_repo_path: str = "../engage-app"

    def user_email(self, role: str, tenant: str) -> str:
        """The seeded login for a role within a tenant."""
        if role not in ROLES:
            raise ValueError(f"Unknown role {role!r}; expected one of {ROLES}")
        if tenant not in TENANTS:
            raise ValueError(f"Unknown tenant {tenant!r}; expected one of {TENANTS}")
        return f"{role}@{tenant}.{self.seed_email_domain}"


@lru_cache(maxsize=1)
def get_settings() -> TestSettings:
    """Cached so every import sees one instance, and .env is parsed once."""
    return TestSettings()
