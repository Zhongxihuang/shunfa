"""WeChat reminder cron job.

Run manually:
    cd backend && python -m app.cron.wechat_reminder_cron
"""

import asyncio
import logging

from ..database import SessionLocal
from ..services.reminder_service import send_due_reminders

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def run():
    db = SessionLocal()
    try:
        result = await send_due_reminders(db)
        logger.info(
            "WeChat reminder job finished: checked=%s sent=%s skipped=%s failed=%s",
            result["checked"],
            result["sent"],
            result["skipped"],
            result["failed"],
        )
    finally:
        db.close()


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
