"""全文提取基准化测试：逐章提取 vs 全文直提，使用同一 GLM 模型做公平对比。

用法：
    python -m backend.benchmark_fulltext --source-path data/神游.txt --max-chapters 5

输出：
    - benchmark/ 目录下的逐章结果、全文结果、对比报告
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.llm_dispatcher import (
    build_chapter_dispatch_from_source,
    build_fulltext_dispatch_from_source,
    dispatch_summary_prompts,
)


def _char_name_set(characters: Any) -> set[str]:
    """从各种格式中提取角色名称集合。"""
    names: set[str] = set()

    if isinstance(characters, list):
        for item in characters:
            if isinstance(item, dict):
                for key in ("name", "character_name"):
                    v = str(item.get(key) or "").strip()
                    if v:
                        names.add(v)
            elif isinstance(item, str):
                names.add(item.strip())
    elif isinstance(characters, dict):
        for key in ("characters", "items"):
            subset = _char_name_set(characters.get(key))
            names.update(subset)
        name = str(characters.get("name") or "").strip()
        if name:
            names.add(name)

    return {n for n in names if n}


def _count_items(value: Any) -> int:
    """安全计数。"""
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        total = 0
        for v in value.values():
            if isinstance(v, list):
                total += len(v)
        return total
    return 0


def _compare_characters(chunked: Any, fulltext: Any) -> dict[str, Any]:
    """对比两种方式提取的角色。"""
    chunked_names = _char_name_set(chunked)
    ft_names = _char_name_set(fulltext)

    common = chunked_names & ft_names
    only_chunked = chunked_names - ft_names
    only_fulltext = ft_names - chunked_names

    total = chunked_names | ft_names
    overlap_pct = round(len(common) / len(total) * 100, 1) if total else 0

    return {
        "chunked_count": len(chunked_names),
        "fulltext_count": len(ft_names),
        "common_count": len(common),
        "overlap_pct": overlap_pct,
        "only_in_chunked": sorted(only_chunked),
        "only_in_fulltext": sorted(only_fulltext),
        "common_names": sorted(common),
    }


def _extract_summary_dim(summary_result: dict | None, dimension: str) -> Any:
    """从 summary 结果中提取指定维度的内容。"""
    if not summary_result:
        return None
    for row in summary_result.get("summary_rows", []) or []:
        if row.get("dimension") == dimension:
            content_url = row.get("content_url", "")
            path = Path(content_url)
            if not path.is_absolute():
                path = ROOT_DIR / content_url
            if path.exists():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    return path.read_text(encoding="utf-8")
    return None


def run_benchmark(
    *,
    source_path: str,
    source_type: str = "txt",
    max_chapters: int | None = None,
    source_file_id: str | None = None,
    book_title: str | None = None,
    model: str | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """运行完整基准化测试：逐章 pipeline + 全文直提，输出对比报告。"""

    resolved_id = source_file_id or f"bench_{Path(source_path).stem}"
    title = book_title or Path(source_path).stem
    bench_dir = Path(output_dir or ROOT_DIR / "benchmark")
    bench_dir.mkdir(parents=True, exist_ok=True)

    provider = "glm"
    print(f"{'='*60}")
    print(f"🔬 全文提取基准化测试")
    print(f"   源文件: {source_path}")
    print(f"   章节限制: {max_chapters or '全部'}")
    print(f"   模型: {model or 'glm-4.5-air (config.json)'}")
    print(f"   Provider: {provider}")
    print(f"{'='*60}")

    # ── 第一轮：逐章 Pipeline ──
    print(f"\n📋 第一轮：逐章提取 Pipeline（L0→L2→Summary）")
    t0 = time.time()

    chunked_result = build_chapter_dispatch_from_source(
        source_path=source_path,
        source_type=source_type,
        source_file_id=resolved_id,
        book_title=title,
        provider=provider,
        model=model,
        max_chapters=max_chapters,
    )

    chapter_dir = Path(chunked_result["chapter_extraction_cache_dir"])
    summary_result = dispatch_summary_prompts(
        chapter_json_dir=chapter_dir,
        source_file_id=resolved_id,
        book_title=title,
        provider=provider,
        model=model,
    )

    chunked_time = round(time.time() - t0, 1)
    chunked_chars = _extract_summary_dim(summary_result, "characters")
    chunked_items = _extract_summary_dim(summary_result, "items")

    print(f"   ✅ 逐章 Pipeline 完成 ({chunked_time}s)")
    print(f"      角色数: {_count_items(chunked_chars)}")
    print(f"      物品数: {_count_items(chunked_items)}")

    # ── 第二轮：全文直提 ──
    print(f"\n📋 第二轮：全文一次性提取（GLM Fulltext）")
    t0 = time.time()

    fulltext_result = build_fulltext_dispatch_from_source(
        source_path=source_path,
        source_type=source_type,
        source_file_id=resolved_id,
        book_title=title,
        model=model,
        max_chapters=max_chapters,
    )

    ft_time = round(time.time() - t0, 1)
    ft_data = fulltext_result.get("fulltext_result", {})

    print(f"   ✅ 全文直提完成 ({ft_time}s)")
    print(f"      角色数: {_count_items(ft_data.get('characters'))}")
    print(f"      物品数: {_count_items(ft_data.get('items'))}")
    print(f"      事件数: {_count_items(ft_data.get('storyline_events'))}")
    print(f"      地点数: {_count_items(ft_data.get('world_locations'))}")

    # ── 对比分析 ──
    print(f"\n{'='*60}")
    print(f"📊 对比分析")
    print(f"{'='*60}")

    char_comparison = _compare_characters(chunked_chars, ft_data.get("characters"))
    print(f"\n  🧑 角色提取对比:")
    print(f"     逐章 Pipeline: {char_comparison['chunked_count']} 人")
    print(f"     全文直提:       {char_comparison['fulltext_count']} 人")
    print(f"     重叠:           {char_comparison['common_count']} 人 ({char_comparison['overlap_pct']}%)")
    if char_comparison["only_in_chunked"]:
        print(f"     仅逐章发现:     {', '.join(char_comparison['only_in_chunked'][:10])}")
    if char_comparison["only_in_fulltext"]:
        print(f"     仅全文发现:     {', '.join(char_comparison['only_in_fulltext'][:10])}")

    chunked_items_count = _count_items(chunked_items)
    ft_items_count = _count_items(ft_data.get("items"))
    print(f"\n  📦 物品提取对比:")
    print(f"     逐章 Pipeline: {chunked_items_count} 件")
    print(f"     全文直提:       {ft_items_count} 件")

    ft_events_count = _count_items(ft_data.get("storyline_events"))
    ft_locations_count = _count_items(ft_data.get("world_locations"))
    print(f"\n  📖 事件提取（仅全文直提支持）: {ft_events_count} 个")
    print(f"  🌍 地点提取（仅全文直提支持）: {ft_locations_count} 个")

    # ── Book Info 对比 ──
    ft_book_info = ft_data.get("book_info", {})
    if ft_book_info:
        print(f"\n  📕 书籍信息（全文直提）:")
        for k, v in ft_book_info.items():
            if v:
                print(f"     {k}: {v}")

    print(f"\n  ⏱️ 耗时对比:")
    print(f"     逐章 Pipeline: {chunked_time}s")
    print(f"     全文直提:       {ft_time}s")
    print(f"     效率比:         {round(chunked_time / ft_time, 1)}x" if ft_time else "     N/A")

    # ── 输出文件 ──
    chunked_output = bench_dir / f"{resolved_id}_chunked_summary.json"
    fulltext_output = bench_dir / f"{resolved_id}_fulltext.json"
    report_output = bench_dir / f"{resolved_id}_benchmark_report.json"

    chunked_output.write_text(
        json.dumps(summary_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # 全文结果已在 cache 中，复制引用
    ft_json_path = fulltext_result.get("fulltext_json_path", "")
    fulltext_output.write_text(
        json.dumps({"fulltext_result": ft_data, "source_path": ft_json_path}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = {
        "benchmark_config": {
            "source_path": source_path,
            "max_chapters": max_chapters,
            "model": model or "glm-4.5-air",
            "provider": provider,
        },
        "chunked_pipeline": {
            "time_seconds": chunked_time,
            "characters_count": char_comparison["chunked_count"],
            "items_count": chunked_items_count,
            "output_file": str(chunked_output),
        },
        "fulltext_pipeline": {
            "time_seconds": ft_time,
            "characters_count": char_comparison["fulltext_count"],
            "items_count": ft_items_count,
            "events_count": ft_events_count,
            "locations_count": ft_locations_count,
            "book_info": ft_book_info,
            "output_file": str(fulltext_output),
        },
        "comparison": {
            "characters": char_comparison,
            "efficiency_ratio": round(chunked_time / ft_time, 1) if ft_time else None,
        },
    }

    report_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n📁 输出文件:")
    print(f"   逐章结果: {chunked_output}")
    print(f"   全文结果: {fulltext_output}")
    print(f"   对比报告: {report_output}")
    print(f"\n✅ 基准化测试完成！")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="全文提取基准化测试：逐章 Pipeline vs 全文直提（GLM）"
    )
    parser.add_argument("--source-path", required=True, help="源文件路径")
    parser.add_argument("--source-type", default="txt")
    parser.add_argument("--max-chapters", type=int, default=None, help="限制章节数（小规模测试用）")
    parser.add_argument("--source-file-id", default=None)
    parser.add_argument("--book-title", default=None)
    parser.add_argument("--model", default=None, help="GLM 模型名，默认使用 config.json 中的 glm.model")
    parser.add_argument("--output-dir", default=None, help="输出目录，默认 benchmark/")
    args = parser.parse_args()

    result = run_benchmark(
        source_path=args.source_path,
        source_type=args.source_type,
        max_chapters=args.max_chapters,
        source_file_id=args.source_file_id,
        book_title=args.book_title,
        model=args.model,
        output_dir=args.output_dir,
    )

    # 返回对比结论
    comparison = result.get("comparison", {})
    char_cmp = comparison.get("characters", {})
    print(f"\n{'='*60}")
    print(f"📊 最终结论")
    print(f"{'='*60}")
    print(f"   角色重叠率: {char_cmp.get('overlap_pct', 'N/A')}%")
    print(f"   效率比:     {comparison.get('efficiency_ratio', 'N/A')}x (逐章耗时/全文耗时)")
    print(f"   逐章提取了 {char_cmp.get('only_in_chunked_count', len(char_cmp.get('only_in_chunked', [])))} 个独有角色")
    print(f"   全文提取了 {char_cmp.get('only_in_fulltext_count', len(char_cmp.get('only_in_fulltext', [])))} 个独有角色")


if __name__ == "__main__":
    main()
