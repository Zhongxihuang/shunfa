"""RSS cron job — fetch hot topics and store to the local hot_topics table.

Run manually:
    cd backend && python -m app.cron.rss_cron

Or schedule with system cron:
    0 12,19 * * * cd /path/to/backend && python -m app.cron.rss_cron
"""

import asyncio
import logging

from ..services.hot_topic_refresh_service import refresh_hot_topic_supply

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def run():
    logger.info("Starting RSS hot topic fetch job")
    result = await refresh_hot_topic_supply()
    logger.info(f"Hot topic supply result: {result}")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
