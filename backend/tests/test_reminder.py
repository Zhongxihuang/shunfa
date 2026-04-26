import pytest
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.models import User, ReminderDelivery
from app.routers.user import create_jwt_token
from app.services import reminder_service


def test_reminder_status_exposes_wechat_push_configured(client, db):
    user = User(openid="reminder_status_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_jwt_token(user.id)
    with patch("app.routers.reminder.is_wechat_reminder_configured", return_value=True):
        response = client.get(
            "/api/reminder_status",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["wechat_push_configured"] is True


def test_trigger_due_reminders_requires_web_admin(client, db):
    user = User(openid="normal_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_jwt_token(user.id)
    response = client.post(
        "/api/reminder/send_due",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_trigger_due_reminders_for_web_admin(client, db):
    admin = User(openid="web_admin")
    db.add(admin)
    db.commit()
    db.refresh(admin)

    token = create_jwt_token(admin.id)
    with patch("app.routers.reminder.send_due_reminders", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {
            "checked": 2,
            "sent": 1,
            "skipped": 1,
            "failed": 0,
            "reason_counts": {"sent": 1, "not_due": 1},
        }
        response = client.post(
            "/api/reminder/send_due",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["sent"] == 1
    assert response.json()["reason_counts"] == {"sent": 1, "not_due": 1}


@pytest.mark.asyncio
async def test_send_wechat_reminder_skips_when_not_configured(db):
    user = User(openid="wechat_skip_user", reminder_enabled=True, reminder_time="21:00")
    db.add(user)
    db.commit()
    db.refresh(user)

    with patch("app.services.reminder_service.is_wechat_reminder_configured", return_value=False):
        result = await reminder_service.send_wechat_reminder(user, db)

    assert result["status"] == "skipped"
    assert result["reason"] == "not_configured"


@pytest.mark.asyncio
async def test_send_wechat_reminder_records_delivery(db):
    user = User(openid="wechat_send_user", reminder_enabled=True, reminder_time="21:00")
    db.add(user)
    db.commit()
    db.refresh(user)

    original_values = (
        settings.wechat_app_id,
        settings.wechat_app_secret,
        settings.wechat_subscribe_template_id,
        settings.wechat_subscribe_page,
        settings.wechat_subscribe_thing_key,
        settings.wechat_subscribe_time_key,
        settings.wechat_subscribe_phrase_key,
        settings.wechat_subscribe_project_key,
    )
    settings.wechat_app_id = "wx-app"
    settings.wechat_app_secret = "wx-secret"
    settings.wechat_subscribe_template_id = "tmpl-id"
    settings.wechat_subscribe_page = "pages/index/index"
    settings.wechat_subscribe_thing_key = "thing3"
    settings.wechat_subscribe_time_key = "time1"
    settings.wechat_subscribe_phrase_key = "thing2"
    settings.wechat_subscribe_project_key = "thing15"

    try:
        with patch("app.services.reminder_service.check_reminder_needed", return_value=True), \
             patch("app.services.reminder_service.get_wechat_access_token", new_callable=AsyncMock) as mock_token, \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_token.return_value = "token"
            mock_post.return_value = type(
                "MockResponse",
                (),
                {
                    "raise_for_status": lambda self: None,
                    "json": lambda self: {"errcode": 0, "errmsg": "ok"},
                },
            )()

            result = await reminder_service.send_wechat_reminder(user, db)

        assert result["sent"] is True
        _, post_kwargs = mock_post.call_args
        assert post_kwargs["json"]["data"]["thing3"]["value"] == "今天这条还没发"
        assert post_kwargs["json"]["data"]["time1"]["value"] == "21:00"
        assert post_kwargs["json"]["data"]["thing2"]["value"] == "先发了再说"
        assert post_kwargs["json"]["data"]["thing15"]["value"] == "顺发"
        delivery = db.query(ReminderDelivery).filter_by(user_id=user.id).first()
        assert delivery is not None
        assert delivery.status == "sent"
    finally:
        (
            settings.wechat_app_id,
            settings.wechat_app_secret,
            settings.wechat_subscribe_template_id,
            settings.wechat_subscribe_page,
            settings.wechat_subscribe_thing_key,
            settings.wechat_subscribe_time_key,
            settings.wechat_subscribe_phrase_key,
            settings.wechat_subscribe_project_key,
        ) = original_values


@pytest.mark.asyncio
async def test_send_due_reminders_aggregates_reason_counts(db):
    user = User(openid="wechat_reason_user", reminder_enabled=True, reminder_time="21:00")
    db.add(user)
    db.commit()
    db.refresh(user)

    with patch("app.services.reminder_service.send_wechat_reminder", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {
            "sent": False,
            "status": "skipped",
            "reason": "not_due",
            "error_message": None,
        }
        result = await reminder_service.send_due_reminders(db)

    assert result == {
        "checked": 1,
        "sent": 0,
        "skipped": 1,
        "failed": 0,
        "reason_counts": {"not_due": 1},
    }
