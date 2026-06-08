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

import hashlib

from ..config import settings

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
