#!/usr/bin/env python3
"""
Run prompt evaluation across all eval cases.

Usage:
    cd backend
    DEEPSEEK_API_KEY=<key> python -m evals.run_eval
    DEEPSEEK_API_KEY=<key> python -m evals.run_eval --version my-experiment
    DEEPSEEK_API_KEY=<key> python -m evals.run_eval --cases case-001,case-003

Output is written to evals/runs/<version>/<timestamp>.json
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Allow running from the backend directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.ai_service import chat_completion
from app.services.draft_service import build_quick_generate_context
from app.services.generation_context import build_discussion_brief, format_discussion_brief
from app.services.prompt_templates import prompts

EVAL_DIR = Path(__file__).parent
CASES_FILE = EVAL_DIR / "eval_cases.jsonl"
RUNS_DIR = EVAL_DIR / "runs"


def load_cases(filter_ids: list[str] | None = None) -> list[dict]:
    cases = []
    with open(CASES_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                case = json.loads(line)
                if filter_ids is None or case["id"] in filter_ids:
                    cases.append(case)
    return cases


async def run_case(case: dict, api_key: str) -> dict:
    fact_block = build_quick_generate_context(
        hot_topic=case["title"],
        summary=case.get("summary", ""),
        source=case.get("source", ""),
        published_at=case.get("published_at"),
    )
    angle = case.get("ai_angle", "")
    brief = build_discussion_brief(
        topic=case["title"],
        fact_block=fact_block,
        angle=angle,
        platform="xiaohongshu",
    )
    discussion_brief_text = format_discussion_brief(brief)

    prompt_text = prompts.system_prompt_quick.format(
        hot_topic=case["title"],
        angle=angle,
        platform="xiaohongshu",
        fact_block=fact_block,
        discussion_brief=discussion_brief_text,
    )
    messages = [{"role": "user", "content": prompt_text}]

    draft = await chat_completion(messages, temperature=0.45, max_tokens=900, api_key=api_key)

    compose_prompt = prompts.compose_post_assets_prompt.format(content=draft)
    compose_messages = [{"role": "user", "content": compose_prompt}]
    compose_raw = await chat_completion(compose_messages, temperature=0.7, max_tokens=800, api_key=api_key)

    try:
        text = compose_raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        compose_data = json.loads(text)
    except Exception:
        compose_data = {"pages": [draft], "title": "", "tags": []}

    return {
        "case_id": case["id"],
        "title": case["title"],
        "angle": angle,
        "fact_block": fact_block,
        "discussion_brief": discussion_brief_text,
        "draft": draft,
        "draft_char_count": len(draft.replace(" ", "")),
        "compose_pages": compose_data.get("pages", []),
        "compose_title": compose_data.get("title", ""),
        "compose_tags": compose_data.get("tags", []),
    }


async def main(version: str, filter_ids: list[str] | None = None) -> None:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    cases = load_cases(filter_ids)
    if not cases:
        print("No cases found matching filter.", file=sys.stderr)
        sys.exit(1)

    print(f"Running {len(cases)} case(s) with prompt version: {prompts.version}")
    results = []
    for case in cases:
        print(f"  [{case['id']}] {case['title'][:50]}...")
        result = await run_case(case, api_key)
        results.append(result)

    run_version = version or prompts.version
    run_dir = RUNS_DIR / run_version
    run_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_file = run_dir / f"{timestamp}.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(
            {"prompt_version": prompts.version, "run_version": run_version, "results": results},
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\nResults written to {out_file}")
    print(f"Run `python -m evals.compare {run_version}` to compare with another run.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run prompt evaluation")
    parser.add_argument("--version", default="", help="Label for this run (defaults to prompt version)")
    parser.add_argument("--cases", default="", help="Comma-separated case IDs to run (default: all)")
    args = parser.parse_args()

    filter_ids = [c.strip() for c in args.cases.split(",") if c.strip()] or None
    asyncio.run(main(args.version, filter_ids))
