"""Run the deterministic showcase evaluation and optionally save a JSON report."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation import evaluate_service  # noqa: E402
from app.standalone_rag import StandaloneRAGService  # noqa: E402


async def run(dataset: Path, output: Path | None, top_k: int) -> dict:
    service = StandaloneRAGService()
    await service.seed_directory(PROJECT_ROOT / "examples")
    report = await evaluate_service(service, dataset, top_k=top_k)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "examples" / "eval_dataset.jsonl",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(run(args.dataset, args.output, args.top_k))


if __name__ == "__main__":
    main()
