from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
ROOT_STR = str(ROOT_DIR)
if ROOT_STR not in sys.path:
    sys.path.insert(0, ROOT_STR)

from backend.workflow_runner import run_l0_to_l2_pipeline


def main() -> None:
    result = run_l0_to_l2_pipeline(
        source_path="data/神游.txt",
        source_type="txt",
        source_file_id="sf_test_001",
        file_name="神游.txt",
        filter_noise=True,
        upload_chapters_to_remote=False,
    )

    summary = {
        "source_file_row": result.get("source_file_row"),
        "chapter_count": len(result.get("chapter_rows", [])),
        "extraction_count": len(result.get("chapter_extraction_rows", [])),
        "remote_persist": result.get("remote_persist"),
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()