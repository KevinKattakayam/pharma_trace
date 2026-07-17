"""
Custom exception hierarchy for structured error handling and observability across PharmaTrace.
"""

class PharmaTraceError(Exception):
    """Base class for all PharmaTrace application exceptions."""
    pass


class PharmaTraceDataError(PharmaTraceError):
    """Base class for all data access and persistence layer exceptions."""
    pass


class DatabaseConnectionError(PharmaTraceDataError):
    """Raised when establishing or pooling a connection to Supabase/PostgreSQL fails."""
    pass


class DatabaseReadError(PharmaTraceDataError):
    """Raised when querying or reading records from the database fails."""
    pass


class DatabaseWriteError(PharmaTraceDataError):
    """Raised when inserting, updating, or deleting database records fails or returns zero affected rows."""
    pass


class ExternalServiceError(PharmaTraceError):
    """Raised when an external clinical API (OpenFDA, RxNav, OpenRouter, Open-Meteo) times out or returns an error."""
    pass
