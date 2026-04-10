"""RSS cron job — fetch hot topics and store to Bitable.

Run manually:
    cd backend && python -m app.cron.rss_cron

Or schedule with system cron:
    0 12,19 * * * cd /path/to/backend && python -m app.cron.rss_cron
"""

import asyncio
import logging
from datetime import date

from ..services.rss_service import fetch_all_sources
from ..services.hot_topic_service import score_and_filter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def run():
    logger.info("Starting RSS hot topic fetch job")

    # Step 1: Fetch all RSS sources
    articles = await fetch_all_sources()
    logger.info(f"Fetched {len(articles)} articles from RSS sources")

    if not articles:
        logger.warning("No articles fetched — check RSS source connectivity")
        return

    # Step 2: Score and filter
    topics = await score_and_filter(articles)
    logger.info(f"Scored {len(articles)} articles, {len(topics)} qualify (score >= 6)")

    if not topics:
        logger.warning("No qualifying topics found today")
        return

    # Step 3: Store to Bitable (Phase 2 — wired up after bitable_client is built)
    try:
        from ..services.hot_topic_store import save_topics, mark_expired
        await mark_expired(date.today())
        await save_topics(topics)
        logger.info(f"Saved {len(topics)} hot topics to Bitable")
    except ImportError:
        # hot_topic_store not yet available — log topics instead
        logger.info("hot_topic_store not yet available, printing topics:")
        for i, topic in enumerate(topics[:5], 1):
            logger.info(
                f"  {i}. [{topic.score}/10] {topic.hot_topic[:60]}"
                f" | {topic.topic_category.value}"
                f" | 推荐角度: {topic.ai_angle[:50]}..."
            )


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
