"""Invarians SDK — Exceptions"""


class InvariansError(Exception):
    """Base exception for all Invarians SDK errors."""


class AuthError(InvariansError):
    """Invalid or missing API key."""


class NotFoundError(InvariansError):
    """Unsupported chain or endpoint."""


class RateLimitError(InvariansError):
    """Daily quota exceeded (free tier: 20 req/day)."""


class StaleError(InvariansError):
    """Data is STALE and stale_policy='raise' is set."""

    def __init__(self, chain: str, data_age_seconds: float):
        self.chain = chain
        self.data_age_seconds = data_age_seconds
        super().__init__(
            f"Oracle data for '{chain}' is STALE "
            f"({data_age_seconds:.0f}s old, threshold 3600s)"
        )


class ServerError(InvariansError):
    """Unexpected server error (5xx)."""
