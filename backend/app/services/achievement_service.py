from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..models import User, CheckIn, Achievement

# 成就定义
ACHIEVEMENTS = {
    "first_post":     {"name": "破冰",     "desc": "完成第一次发布"},
    "streak_3":       {"name": "三日坚持", "desc": "连续打卡3天"},
    "streak_7":       {"name": "一周英雄", "desc": "连续打卡7天"},
    "streak_30":      {"name": "月度传奇", "desc": "连续打卡30天"},
    "quality_writer": {"name": "言之有物", "desc": "经过3轮讨论后发布"},
    "century_points": {"name": "百分达人", "desc": "累计积分超过100分"},
}


def _unlock(user_id: int, achievement_type: str, db: Session) -> bool:
    """
    尝试解锁成就。已解锁则忽略，返回是否是新解锁。
    """
    try:
        achievement = Achievement(user_id=user_id, achievement_type=achievement_type)
        db.add(achievement)
        db.flush()  # 触发唯一约束，但不 commit
        return True
    except IntegrityError:
        db.rollback()
        return False


def check_and_unlock(user: User, checkin: CheckIn, db: Session) -> list[dict]:
    """
    在 confirm_publish 后调用，检查并解锁所有符合条件的成就。
    返回本次新解锁的成就列表（供前端展示庆祝）。
    """
    import json
    newly_unlocked = []

    def try_unlock(atype: str):
        if _unlock(user.id, atype, db):
            newly_unlocked.append({
                "type": atype,
                "name": ACHIEVEMENTS[atype]["name"],
                "desc": ACHIEVEMENTS[atype]["desc"],
            })

    # 已有成就类型（用于去重判断）
    existing = {a.achievement_type for a in user.achievements}

    # 首次发布
    if "first_post" not in existing:
        try_unlock("first_post")

    # 连胜成就
    for days, atype in [(3, "streak_3"), (7, "streak_7"), (30, "streak_30")]:
        if atype not in existing and user.streak >= days:
            try_unlock(atype)

    # 言之有物：3轮讨论
    if "quality_writer" not in existing:
        history = json.loads(checkin.conversation_history or "[]")
        user_rounds = sum(1 for m in history if m["role"] == "user")
        if user_rounds >= 3:
            try_unlock("quality_writer")

    # 百分达人
    if "century_points" not in existing and user.points >= 100:
        try_unlock("century_points")

    if newly_unlocked:
        db.commit()

    return newly_unlocked


def get_user_achievements(user: User) -> list[dict]:
    """返回用户已解锁的成就列表（含元数据）。"""
    result = []
    for a in user.achievements:
        meta = ACHIEVEMENTS.get(a.achievement_type, {})
        result.append({
            "type": a.achievement_type,
            "name": meta.get("name", a.achievement_type),
            "desc": meta.get("desc", ""),
            "unlocked_at": a.unlocked_at.isoformat() if a.unlocked_at else None,
        })
    return result
