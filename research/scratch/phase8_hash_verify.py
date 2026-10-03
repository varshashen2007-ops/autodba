"""
Phase 8 static verification: compute T9 canonical template and hash.
READ-ONLY. No database access, no file writes, no production code import.
Runs entirely from stdlib — copies the canonicalize_sql logic inline.
"""
import hashlib
import re


def canonicalize_sql(sql: str) -> str:
    if not sql:
        return ""
    s = re.sub(r"--[^\n]*", " ", sql)
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.DOTALL)
    s = re.sub(r"\s+", " ", s.strip()).lower()
    s = re.sub(r"'([^']|'')*'", "?", s)
    s = re.sub(r"\b\d+(?:\.\d+)?\b", "?", s)
    s = re.sub(r"\$\d+", "?", s)
    s = re.sub(r"\b(true|false)\b", "?", s)
    s = re.sub(r"\bin\s*\(\s*\?(?:\s*,\s*\?)*\s*\)", "in (?)", s)
    s = re.sub(r"\s*([,()=<>])\s*", r" \1 ", s)
    s = re.sub(r"<\s*>", "<>", s)
    s = re.sub(r"<\s*=", "<=", s)
    s = re.sub(r">\s*=", ">=", s)
    s = re.sub(r"!\s*=", "!=", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.rstrip(";").strip()
    return s


def compute_template_hash(sql: str) -> str:
    canonical = canonicalize_sql(sql)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── T9: New Phase 8 query ────────────────────────────────────────────────────
T9_SQL = "SELECT * FROM orders WHERE customer_id = 42 AND total_amount >= 450.00"
t9_canonical = canonicalize_sql(T9_SQL)
t9_hash = compute_template_hash(T9_SQL)

# ── T3 (DEV): for comparison ──────────────────────────────────────────────────
T3_SQL = "SELECT * FROM orders WHERE customer_id = 278 AND total_amount > 200.00"
t3_canonical = canonicalize_sql(T3_SQL)
t3_hash = compute_template_hash(T3_SQL)

# ── T1 / T2 (TRAIN) ──────────────────────────────────────────────────────────
T1_SQL = "SELECT * FROM orders WHERE customer_id = 42"
T2_SQL = "SELECT * FROM orders WHERE total_amount > 450.00"
t1_hash = compute_template_hash(T1_SQL)
t2_hash = compute_template_hash(T2_SQL)

# ── Locked Phase 6C hashes ───────────────────────────────────────────────────
LOCKED_T1_HASH = "036cb1ede04b97e1c6f74baa1d4fdce5cbfb6cca2ad7c64a8018d1c4f608a636"
LOCKED_T2_HASH = "f5bbbbeea30650c2c997aeadc2230f1b37fe979559019aba0304bf15730e563c"
LOCKED_T3_HASH = "30a0565175c281388d71d94a46e18432d582b204efaa478e88d86c3166ce39b2"

print("=" * 70)
print("PHASE 8 STATIC VERIFICATION — canonicalize_sql + SHA-256 hashes")
print("=" * 70)
print()

print(f"T9 canonical template : {t9_canonical!r}")
print(f"T9 SHA-256 hash       : {t9_hash}")
print()

print(f"T3 canonical template : {t3_canonical!r}")
print(f"T3 SHA-256 hash       : {t3_hash}")
print()

print("Locked Phase 6C hashes (for cross-check):")
print(f"  T1 locked : {LOCKED_T1_HASH}")
print(f"  T1 actual : {t1_hash}")
print(f"  T1 match  : {t1_hash == LOCKED_T1_HASH}")
print()
print(f"  T2 locked : {LOCKED_T2_HASH}")
print(f"  T2 actual : {t2_hash}")
print(f"  T2 match  : {t2_hash == LOCKED_T2_HASH}")
print()
print(f"  T3 locked : {LOCKED_T3_HASH}")
print(f"  T3 actual : {t3_hash}")
print(f"  T3 match  : {t3_hash == LOCKED_T3_HASH}")
print()

print("Disjointness checks:")
print(f"  T9 != T1  : {t9_hash != t1_hash}")
print(f"  T9 != T2  : {t9_hash != t2_hash}")
print(f"  T9 != T3  : {t9_hash != t3_hash}")
print()
print(f"  T9 absent from TRAIN   : {t9_hash not in (t1_hash, t2_hash)}")
print(f"  T9 absent from DEV(T3) : {t9_hash != t3_hash}")
print()

# Known hashes from Phase 7 / Phase 6D manifests for additional checks
T7_HASH = "03fe9bcb608dbc9323c5744caf0518171dd12a199fc66d8af319daf545ae6b64"
T8_HASH = "3c098f93b8db0d86bd20843c7d4361b26048ab6e3484d8a878418d05e2e0556c"
T5_HASH_MANIFEST = "6bcb778b583d7913410164211ea7137d5bd13ddf49daa252854435e899666b58"

print(f"  T9 absent from TEST(T7): {t9_hash != T7_HASH}")
print(f"  T9 absent from TEST(T8): {t9_hash != T8_HASH}")
print(f"  T9 absent from DEV (T5): {t9_hash != T5_HASH_MANIFEST}")
print()

all_existing = [LOCKED_T1_HASH, LOCKED_T2_HASH, LOCKED_T3_HASH, T5_HASH_MANIFEST, T7_HASH, T8_HASH]
t9_clean = t9_hash not in all_existing
print(f"T9 disjoint from ALL existing templates: {t9_clean}")
print()

if t9_clean and (t1_hash == LOCKED_T1_HASH) and (t2_hash == LOCKED_T2_HASH) and (t3_hash == LOCKED_T3_HASH):
    print("VERDICT: T9 is a genuinely unseen template. Safe for Phase 8 TEST assignment.")
else:
    print("VERDICT: FAILED — investigate mismatches above before proceeding.")
