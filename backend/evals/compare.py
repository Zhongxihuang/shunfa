#!/usr/bin/env python3
"""
Compare two eval run outputs side by side.

Usage:
    cd backend
    python -m evals.compare <version-A> <version-B>
    python -m evals.compare <version-A>              # compare latest two runs in that version
    python -m evals.compare <version-A> --case case-001
"""

import argparse
import json
import sys
from pathlib import Path

RUNS_DIR = Path(__file__).parent / "runs"


def latest_run(version_dir: Path) -> Path | None:
    runs = sorted(version_dir.glob("*.json"), reverse=True)
    return runs[0] if runs else None


def load_run(version: str) -> dict:
    version_dir = RUNS_DIR / version
    if not version_dir.exists():
        print(f"ERROR: No runs found for version '{version}'", file=sys.stderr)
        sys.exit(1)
    path = latest_run(version_dir)
    if path is None:
        print(f"ERROR: No run files in {version_dir}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def print_diff(case_a: dict, case_b: dict, label_a: str, label_b: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"CASE: [{case_a['case_id']}] {case_a['title'][:55]}")
    print(f"{'=' * 70}")

    for attr, label in [
        ("draft_char_count", "字数"),
        ("compose_title", "标题"),
    ]:
        va = case_a.get(attr, "")
        vb = case_b.get(attr, "")
        changed = "  ← CHANGED" if va != vb else ""
        print(f"\n{label}:")
        print(f"  [{label_a}] {va}")
        print(f"  [{label_b}] {vb}{changed}")

    pages_a = case_a.get("compose_pages", [])
    pages_b = case_b.get("compose_pages", [])
    print(f"\n页数: [{label_a}] {len(pages_a)} 页  |  [{label_b}] {len(pages_b)} 页")

    print(f"\n--- [{label_a}] 完整初稿 ---")
    print(case_a.get("draft", ""))

    print(f"\n--- [{label_b}] 完整初稿 ---")
    print(case_b.get("draft", ""))

    print(f"\n--- [{label_a}] 卡片分页 ---")
    for i, p in enumerate(pages_a, 1):
        print(f"  第{i}页 ({len(p.replace(' ', ''))}字): {p[:80]}{'...' if len(p) > 80 else ''}")

    print(f"\n--- [{label_b}] 卡片分页 ---")
    for i, p in enumerate(pages_b, 1):
        print(f"  第{i}页 ({len(p.replace(' ', ''))}字): {p[:80]}{'...' if len(p) > 80 else ''}")

    tags_a = ", ".join(case_a.get("compose_tags", []))
    tags_b = ", ".join(case_b.get("compose_tags", []))
    if tags_a != tags_b:
        print(f"\n标签 [{label_a}]: {tags_a}")
        print(f"标签 [{label_b}]: {tags_b}  ← CHANGED")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two eval run versions")
    parser.add_argument("version_a", help="First version to compare")
    parser.add_argument("version_b", nargs="?", default=None, help="Second version (optional)")
    parser.add_argument("--case", default="", help="Compare only this case ID")
    args = parser.parse_args()

    run_a = load_run(args.version_a)
    label_a = args.version_a

    if args.version_b:
        run_b = load_run(args.version_b)
        label_b = args.version_b
    else:
        # Compare latest two runs within the same version
        version_dir = RUNS_DIR / args.version_a
        all_runs = sorted(version_dir.glob("*.json"), reverse=True)
        if len(all_runs) < 2:
            print("ERROR: Need at least 2 runs in that version to compare within. Provide a second version.", file=sys.stderr)
            sys.exit(1)
        with open(all_runs[1], encoding="utf-8") as f:
            run_b = json.load(f)
        label_a = f"{args.version_a} (latest)"
        label_b = f"{args.version_a} (previous)"

    results_a = {r["case_id"]: r for r in run_a["results"]}
    results_b = {r["case_id"]: r for r in run_b["results"]}

    common_ids = sorted(set(results_a) & set(results_b))
    if args.case:
        common_ids = [args.case] if args.case in common_ids else []

    if not common_ids:
        print("No matching cases found.", file=sys.stderr)
        sys.exit(1)

    print(f"Comparing: [{label_a}] vs [{label_b}]")
    print(f"Cases: {len(common_ids)}")

    for case_id in common_ids:
        print_diff(results_a[case_id], results_b[case_id], label_a, label_b)

    print(f"\n{'=' * 70}")
    print("DONE. Review the diffs above and judge:")
    print("  1. 三层结构是否清晰（现象→机制→影响）")
    print("  2. 分析深度是否有实质提升")
    print("  3. 语气是否从参与者转向观察者")
    print("  4. 字数是否在 300-520 字区间")
    print("  5. 是否仍有事实编造或过度断言")


if __name__ == "__main__":
    main()
