import re
from typing import List, Tuple
from app.core.exceptions import (
    InvalidSQLError,
    MultiStatementSQLError,
    UnsafeSQLError,
)

# Explicitly rejected DDL, DML, maintenance, and administrative keywords
REJECTED_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "GRANT",
    "REVOKE",
    "VACUUM",
    "CALL",
    "DO",
    "COPY",
    "REINDEX",
    "CLUSTER",
    "REFRESH",
    "COMMENT",
    "DISCARD",
    "SET",
    "RESET",
    "LOCK",
    "EXECUTE",
    "PREPARE",
    "MERGE",
}

DOLLAR_QUOTE_REGEX = re.compile(r"^\$([a-zA-Z0-9_]*)\$")


def tokenize_sql(query: str) -> List[Tuple[str, str]]:
    """Lexically tokenizes SQL into (token_type, value) pairs.

    Types:
        - KEYWORD_OR_ID: Bare words and identifiers
        - STRING_LITERAL: Single-quoted or dollar-quoted string values
        - QUOTED_ID: Double-quoted identifiers
        - SEMICOLON: Semicolon character ';'
        - COMMENT: Single-line (--) or block (/* */) comments
        - SYMBOL: Operators and punctuation
    """
    tokens: List[Tuple[str, str]] = []
    i = 0
    n = len(query)

    while i < n:
        c = query[i]

        # 1. Skip whitespace
        if c.isspace():
            i += 1
            continue

        # 2. Single-line comment (-- ...)
        if c == "-" and i + 1 < n and query[i + 1] == "-":
            start = i
            while i < n and query[i] != "\n":
                i += 1
            tokens.append(("COMMENT", query[start:i]))
            continue

        # 3. Multi-line comment (/* ... */)
        if c == "/" and i + 1 < n and query[i + 1] == "*":
            start = i
            i += 2
            while i + 1 < n and not (query[i] == "*" and query[i + 1] == "/"):
                i += 1
            if i + 1 >= n:
                raise InvalidSQLError("Unclosed block comment in SQL query.")
            i += 2
            tokens.append(("COMMENT", query[start:i]))
            continue

        # 4. Standard string literal (' ... ')
        if c == "'":
            start = i
            i += 1
            while i < n:
                if query[i] == "'":
                    if i + 1 < n and query[i + 1] == "'":
                        i += 2  # Escaped quote ''
                    else:
                        i += 1
                        break
                else:
                    i += 1
            else:
                raise InvalidSQLError("Unclosed single-quoted string literal.")
            tokens.append(("STRING_LITERAL", query[start:i]))
            continue

        # 5. Dollar-quoted string ($tag$ ... $tag$)
        if c == "$":
            match = DOLLAR_QUOTE_REGEX.match(query[i:])
            if match:
                tag = match.group(0)
                start = i
                i += len(tag)
                closing_idx = query.find(tag, i)
                if closing_idx == -1:
                    raise InvalidSQLError(f"Unclosed dollar-quoted string matching {tag}.")
                i = closing_idx + len(tag)
                tokens.append(("STRING_LITERAL", query[start:i]))
                continue

        # 6. Quoted identifier (" ... ")
        if c == '"':
            start = i
            i += 1
            while i < n:
                if query[i] == '"':
                    if i + 1 < n and query[i + 1] == '"':
                        i += 2  # Escaped double quote ""
                    else:
                        i += 1
                        break
                else:
                    i += 1
            else:
                raise InvalidSQLError("Unclosed double-quoted identifier.")
            tokens.append(("QUOTED_ID", query[start:i]))
            continue

        # 7. Semicolon
        if c == ";":
            tokens.append(("SEMICOLON", ";"))
            i += 1
            continue

        # 8. Keywords and identifiers ([a-zA-Z_][a-zA-Z0-9_]*)
        if c.isalpha() or c == "_":
            start = i
            while i < n and (query[i].isalnum() or query[i] == "_"):
                i += 1
            tokens.append(("KEYWORD_OR_ID", query[start:i]))
            continue

        # 9. Symbols and other characters
        tokens.append(("SYMBOL", c))
        i += 1

    return tokens


def validate_read_only_query(query: str) -> str:
    """Validates that a SQL query is strictly a single, safe, read-only SELECT or WITH statement.

    Rejects:
      - Destructive / Modifying commands (INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, etc.)
      - Multi-statement requests or embedded semicolons
      - Empty or whitespace-only queries
      - Comments-only queries

    Returns:
      Cleaned SQL string stripped of trailing semicolons, safe for EXPLAIN.
    """
    if not query or not query.strip():
        raise InvalidSQLError("Query cannot be empty or whitespace.")

    tokens = tokenize_sql(query)

    # Filter out comments
    meaningful_tokens = [t for t in tokens if t[0] != "COMMENT"]
    if not meaningful_tokens:
        raise InvalidSQLError("Query contains only comments.")

    # Check for semicolons / multiple statements
    semicolons = [idx for idx, t in enumerate(meaningful_tokens) if t[0] == "SEMICOLON"]
    if semicolons:
        # Only a single trailing semicolon at the very end is permissible
        if len(semicolons) > 1 or semicolons[0] != len(meaningful_tokens) - 1:
            raise MultiStatementSQLError("Multiple SQL statements or embedded semicolons are not permitted.")

    # Remove the trailing semicolon token for further analysis
    code_tokens = [t for t in meaningful_tokens if t[0] != "SEMICOLON"]
    if not code_tokens:
        raise InvalidSQLError("Query contains no executable statements.")

    # Inspect the leading command keyword
    leading_type, leading_val = code_tokens[0]
    leading_upper = leading_val.upper()

    if leading_type != "KEYWORD_OR_ID" or leading_upper not in ("SELECT", "WITH"):
        raise UnsafeSQLError(
            f"Destructive or unsupported command '{leading_upper}'. Only read-only SELECT queries are allowed."
        )

    # Check all code tokens for disallowed keywords
    for t_type, t_val in code_tokens:
        if t_type == "KEYWORD_OR_ID":
            token_upper = t_val.upper()
            if token_upper in REJECTED_KEYWORDS:
                raise UnsafeSQLError(f"Destructive or modifying SQL keyword '{token_upper}' is not permitted.")

    # For CTE queries starting with WITH, verify a main SELECT exists
    if leading_upper == "WITH":
        has_select = any(t[0] == "KEYWORD_OR_ID" and t[1].upper() == "SELECT" for t in code_tokens)
        if not has_select:
            raise UnsafeSQLError("WITH query must conclude with a SELECT statement.")

    # Return normalized query stripped of any trailing semicolon and surrounding whitespace
    cleaned = query.strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()

    return cleaned
