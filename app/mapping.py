from __future__ import annotations
import hashlib
import uuid
from app.database import get_db


def derive_fingerprint_seed(consumer_id: str) -> int:
    return int.from_bytes(hashlib.sha256(consumer_id.encode()).digest()[:4], "big") % (2**31)


async def get_or_create_profile(consumer_id: str) -> tuple[str, bool]:
    """Returns (profile_id, is_new)."""
    db = get_db()
    row = await db.execute_fetchall(
        "SELECT profile_id FROM consumer_profiles WHERE consumer_id = ?",
        (consumer_id,),
    )
    if row:
        return row[0][0], False
    profile_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO consumer_profiles (consumer_id, profile_id) VALUES (?, ?)",
        (consumer_id, profile_id),
    )
    await db.commit()
    return profile_id, True


async def reset_consumer(consumer_id: str) -> str | None:
    """Delete mapping, return old profile_id or None."""
    db = get_db()
    row = await db.execute_fetchall(
        "SELECT profile_id FROM consumer_profiles WHERE consumer_id = ?",
        (consumer_id,),
    )
    if not row:
        return None
    profile_id = row[0][0]
    await db.execute("DELETE FROM consumer_profiles WHERE consumer_id = ?", (consumer_id,))
    await db.commit()
    return profile_id
