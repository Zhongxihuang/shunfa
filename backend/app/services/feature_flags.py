"""Feature flags for product experiments.

Currently hosts the **subtraction experiment** (W2.7): a stable, deterministic
slice of users has ALL gamification UI (streak / points / level / diamonds /
achievements) hidden, so Week-3 can measure whether gamification actually
creates retention — the heaviest assumption in the product.

Bucketing must be:
- **stable**: the same user always lands in the same bucket, across process
  restarts and multiple workers (so we can't use Python's salted ``hash()``).
- **monotonic in pct**: raising the rollout percentage only ever moves users
  INTO the experiment, never out — so a ramp doesn't reshuffle cohorts.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from ..config import settings

if TYPE_CHECKING:
    from ..models import User

_BUCKETS = 100


def user_bucket(user_id: int) -> int:
    """Return a stable bucket in ``[0, 100)`` for this user id."""
    digest = hashlib.md5(f"subtraction:{user_id}".encode()).hexdigest()
    return int(digest, 16) % _BUCKETS


def in_subtraction_experiment(user_id: int) -> bool:
    """True when this user is in the gamification-removed group."""
    pct = settings.subtraction_experiment_pct
    if pct <= 0:
        return False
    if pct >= _BUCKETS:
        return True
    return user_bucket(user_id) < pct


def gamification_enabled(user_id: int) -> bool:
    """True when this user should SEE gamification UI (the inverse of the experiment)."""
    return not in_subtraction_experiment(user_id)


def resolve_gamification_enabled(user: "User") -> bool:
    """Gamification visibility for a user, honouring the within-subject override.

    Priority:
      1. user.gamification_override == "on"  → always show gamification
      2. user.gamification_override == "off" → always hide gamification
      3. NULL (default)                      → fall back to the stable md5 bucket

    Only path 3 touches in_subtraction_experiment, so users without an override
    behave exactly as before. The override exists for the Ring-0 ABAB self
    experiment, where the same user is flipped on/off over time windows.
    """
    override = getattr(user, "gamification_override", None)
    if override == "on":
        return True
    if override == "off":
        return False
    return gamification_enabled(user.id)
