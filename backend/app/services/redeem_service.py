"""Diamond sink / 积分钻石出口 (W3.9).

Until now diamonds were a dead number: ``user.diamonds`` was recomputed as
``3 + points // 100`` on every publish, so there was nothing to spend them on
and no way to spend them without the next publish overwriting the balance.

We fix that with a persistent ``diamonds_spent`` ledger on the user:

    effective_balance = earned(points) − diamonds_spent

Earning still derives from points (monotonic), but spending now *sticks*. The
first real sink is buying a streak-freeze card — which directly feeds the
W3.8 retention hook.
"""

from sqlalchemy.orm import Session

from ..models import User
from .analytics import track

# Redemption catalog. Keep tiny and obvious — this is a "make the number mean
# something" MVP, not a shop. `effect` is handled in `_apply_effect`.
CATALOG: dict[str, dict] = {
    "streak_freeze": {
        "cost": 5,
        "name": "断签保护卡",
        "desc": "断签当天自动消耗，连胜不归零",
    },
}


class RedeemError(Exception):
    """Raised when a redemption can't proceed. `code` maps to an API error_code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def diamonds_earned(points: int) -> int:
    """Diamonds earned from lifetime points (mirror of points_service formula)."""
    return 3 + (points // 100)


def effective_diamonds(user: User) -> int:
    """Spendable balance = earned − already spent."""
    return diamonds_earned(user.points) - (user.diamonds_spent or 0)


def _apply_effect(user: User, item: str) -> None:
    if item == "streak_freeze":
        user.streak_freezes = (user.streak_freezes or 0) + 1


def redeem(db: Session, user: User, item: str) -> dict:
    """Spend diamonds on a catalog item. Commits on success.

    Raises RedeemError("unknown_item") or RedeemError("insufficient_diamonds").
    """
    entry = CATALOG.get(item)
    if entry is None:
        raise RedeemError("unknown_item", f"未知的兑换项：{item}")

    cost = entry["cost"]
    if effective_diamonds(user) < cost:
        raise RedeemError("insufficient_diamonds", "钻石不足，再坚持几天就能兑换啦")

    user.diamonds_spent = (user.diamonds_spent or 0) + cost
    _apply_effect(user, item)
    # Keep the cached balance field consistent with the ledger.
    user.diamonds = effective_diamonds(user)
    db.commit()
    db.refresh(user)

    track(
        "redeem",
        user_id=user.id,
        props={"item": item, "cost": cost, "diamonds_left": user.diamonds},
    )

    return {
        "item": item,
        "cost": cost,
        "diamonds": user.diamonds,
        "streak_freezes": user.streak_freezes or 0,
    }
