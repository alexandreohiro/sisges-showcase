from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session


_DEPTH_KEY = "sisges_atomic_depth"


@contextmanager
def atomic(db: Session) -> Iterator[Session]:
    """
    Transaction boundary for application services and HTTP use cases.

    Repositories must not call commit. They can add/flush/refresh objects; this
    context decides when a unit of work is committed or rolled back.
    """
    depth = int(db.info.get(_DEPTH_KEY, 0))
    db.info[_DEPTH_KEY] = depth + 1

    try:
        yield db
        if depth == 0:
            db.commit()
        else:
            db.flush()
    except Exception:
        db.rollback()
        raise
    finally:
        if depth == 0:
            db.info.pop(_DEPTH_KEY, None)
        else:
            db.info[_DEPTH_KEY] = depth
