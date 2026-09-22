class AutoDBAException(Exception):
    """Base exception for all AutoDBA application errors."""

    def __init__(self, message: str, error_code: str = "INTERNAL_ERROR"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class SQLValidationError(AutoDBAException):
    """Base exception for SQL validation failures."""

    def __init__(self, message: str, error_code: str = "SQL_VALIDATION_ERROR"):
        super().__init__(message, error_code=error_code)


class UnsafeSQLError(SQLValidationError):
    """Raised when a query contains modifying, DDL, or destructive operations."""

    def __init__(self, message: str):
        super().__init__(message, error_code="UNSAFE_QUERY_REJECTED")


class MultiStatementSQLError(SQLValidationError):
    """Raised when multiple SQL statements are submitted in a single request."""

    def __init__(self, message: str = "Multiple SQL statements or embedded semicolons are not permitted."):
        super().__init__(message, error_code="MULTI_STATEMENT_REJECTED")


class InvalidSQLError(SQLValidationError):
    """Raised when query is empty, whitespace, or structurally malformed."""

    def __init__(self, message: str = "Query is empty or invalid."):
        super().__init__(message, error_code="INVALID_QUERY")


class DatabaseExecutionError(AutoDBAException):
    """Raised when a database query fails during execution."""

    def __init__(self, message: str, error_code: str = "DATABASE_ERROR"):
        super().__init__(message, error_code=error_code)
