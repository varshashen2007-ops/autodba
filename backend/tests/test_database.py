from app.db.database import get_db, SessionLocal


def test_session_lifecycle():
    gen = get_db()
    session = next(gen)
    assert session is not None
    try:
        # Closing via generator exit
        gen.close()
    except StopIteration:
        pass
