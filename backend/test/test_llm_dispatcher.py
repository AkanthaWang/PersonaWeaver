import json
from pathlib import Path

from backend import llm_dispatcher as dispatcher


def test_resolve_llm_config_supports_vivo_provider(monkeypatch):
    config = {
        "llm": {
            "provider": "vivo",
            "temperature": 0.5,
            "timeout_seconds": 60,
            "vivo": {
                "base_url_env": "VIVO_AIGC_BASE_URL",
                "api_key_env": "VIVO_AIGC_API_KEY",
                "app_id_env": "VIVO_AIGC_APP_ID",
                "model_name_env": "VIVO_AIGC_MODEL",
                "base_url": "https://api-ai.vivo.com.cn/v1/chat/completions",
                "model_name": "Volc-DeepSeek-V3.2",
                "temperature": 0.1,
                "timeout_seconds": 300,
                "fallback_providers": ["remote_api"],
            },
        }
    }
    monkeypatch.setenv("VIVO_AIGC_BASE_URL", "https://api-ai.vivo.com.cn/v1/chat/completions")
    monkeypatch.setenv("VIVO_AIGC_API_KEY", "vivo-token")
    monkeypatch.setenv("VIVO_AIGC_APP_ID", "2026945506")
    monkeypatch.setenv("VIVO_AIGC_MODEL", "Volc-DeepSeek-V3.2")

    llm_cfg = dispatcher._resolve_llm_config(config)

    assert llm_cfg["provider"] == "vivo"
    assert llm_cfg["base_url"] == "https://api-ai.vivo.com.cn/v1/chat/completions"
    assert llm_cfg["api_key"] == "vivo-token"
    assert llm_cfg["app_id"] == "2026945506"
    assert llm_cfg["model"] == "Volc-DeepSeek-V3.2"
    assert llm_cfg["fallback_providers"] == ["remote_api"]


def test_dispatch_summary_prompts_writes_json_and_md(monkeypatch, tmp_path):
    chapter_dir = tmp_path / "book_cache" / "extraction_json"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    (chapter_dir / "sf_test_001_chapter_0001.json").write_text(
        '{"chapter_title":"第1章","chapter_info":{"chapter_no":"1"},"noise":"ignore me"}',
        encoding="utf-8",
    )
    (chapter_dir / "sf_test_001_chapter_0002.json").write_text(
        '{"chapter_title":"第2章","plot":{"chapter_summary":"发生冲突"},"noise":"ignore me too"}',
        encoding="utf-8",
    )

    calls = []

    def fake_call_ollama_json(**kwargs):
        calls.append(kwargs)
        prompt = kwargs["prompt_description"]
        if "角色总表" in prompt:
            return {
                "characters": [
                    {
                        "name": "石野",
                        "summary": "主角",
                        "identity": "学生",
                        "appearance": "普通少年",
                        "personality": "谨慎",
                    }
                ]
            }
        if "物品总表" in prompt:
            return {"items": [{"name": "青冥镜", "summary": "古镜"}]}
        if "剧情时间线" in prompt:
            return {"timeline": ["第1章", "第2章"]}
        if "世界观地图表" in prompt:
            return {"world_locations": ["山神庙"]}
        return {}

    def fake_call_llm_text(**kwargs):
        calls.append(kwargs)
        prompt = kwargs["prompt_description"]
        if "剧情时间线" in prompt:
            return "- 第1章\n- 第2章"
        if "世界观" in prompt or "地点" in prompt:
            return "- 山神庙"
        return "- 测试内容"

    monkeypatch.setattr(dispatcher, "call_ollama_json", fake_call_ollama_json)
    monkeypatch.setattr(dispatcher, "call_llm_text", fake_call_llm_text)

    result = dispatcher.dispatch_summary_prompts(
        chapter_json_dir=chapter_dir,
        source_file_id="sf_test_001",
        book_title="测试书名",
    )

    assert len(result["summary_rows"]) == 4
    assert len(calls) == 4
    assert all("ignore me" not in call["text_or_documents"] for call in calls)
    assert any("chapter_info" in call["text_or_documents"] for call in calls)
    assert any("chapter_title" in call["text_or_documents"] for call in calls)
    assert Path(result["summary_root_dir"]).exists()
    characters_index_path = chapter_dir.parent / "summary" / "characters" / "all_characters.json"
    character_detail_path = chapter_dir.parent / "summary" / "characters" / "character_json" / "石野.json"
    items_path = chapter_dir.parent / "summary" / "items" / "items.json"
    assert characters_index_path.exists()
    assert character_detail_path.exists()
    assert items_path.exists()
    characters_index = json.loads(characters_index_path.read_text(encoding="utf-8"))
    character_detail = json.loads(character_detail_path.read_text(encoding="utf-8"))
    items = json.loads(items_path.read_text(encoding="utf-8"))
    assert characters_index == [
        {
            "name": "石野",
            "summary": "主角",
            "identity": "学生",
            "summary_local_url": character_detail_path.as_posix(),
            "summary_oss_url": "",
        }
    ]
    assert character_detail["appearance"] == "普通少年"
    assert items == [{"name": "青冥镜", "summary": "古镜"}]
    assert (chapter_dir.parent / "summary" / "storyline_events" / "storyline_events.md").exists()
    assert (chapter_dir.parent / "summary" / "world_locations" / "world_locations.md").exists()


def test_dispatch_card_prompts_writes_md_only(monkeypatch, tmp_path):
    chapter_dir = tmp_path / "book_cache" / "extraction_json"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    (chapter_dir / "sf_test_001_chapter_0001.json").write_text(
        '{"chapter_title":"第1章","characters":{"characters":[{"name":"石野","behavior":["大喊"],"speech":["我不信！"]}]}}',
        encoding="utf-8",
    )
    (chapter_dir / "sf_test_001_chapter_0002.json").write_text(
        '{"chapter_title":"第2章","characters":{"characters":[{"name":"游方","behavior":["观察"]}]}}',
        encoding="utf-8",
    )

    calls = []

    def fake_call_llm_text(**kwargs):
        calls.append(kwargs)
        return (
            "# 石野\n\n"
            "## 简介\n"
            "主角角色卡\n\n"
            "## 形象特征\n"
            "沉稳，常带着警惕神情。\n\n"
            "## 性格特点\n"
            "谨慎、执拗。\n\n"
            "## 关键经历\n"
            "- 第1章：第一次正面冲突。\n\n"
            "## 经典台词\n"
            "- 我不信！\n\n"
            "## 与其他角色关系\n"
            "与游方存在明显对立。\n"
        )

    monkeypatch.setattr(dispatcher, "call_llm_text", fake_call_llm_text)

    result = dispatcher.dispatch_card_prompts(
        chapter_json_dir=chapter_dir,
        source_file_id="sf_test_001",
        character_name="石野",
        book_title="测试书名",
    )

    assert len(result["card_rows"]) == 1
    assert len(calls) == 1
    assert "石野" in calls[0]["text_or_documents"]
    assert "第1章" in calls[0]["text_or_documents"]
    assert Path(result["card_root_dir"]).exists()
    assert (tmp_path / "book_cache" / "card" / "sf_test_001_石野_character_card.md").exists()
    assert result["card_rows"][0]["content_kind"] == "md"
    assert result["card_rows"][0]["content_url"].endswith("sf_test_001_石野_character_card.md")
    written = (tmp_path / "book_cache" / "card" / "sf_test_001_石野_character_card.md").read_text(encoding="utf-8")
    assert "## 简介" in written
    assert "## 形象特征" in written


def test_build_chapter_dispatch_respects_max_chapters(monkeypatch, tmp_path):
    source_path = tmp_path / "source.txt"
    source_path.write_text(
        "001回 第一章\n第一章内容\n\n002回 第二章\n第二章内容\n\n003回 第三章\n第三章内容",
        encoding="utf-8",
    )

    seen = {}

    def fake_dispatch_chapter_prompts(**kwargs):
        chapters = kwargs["chapters"]
        seen["chapter_count"] = len(chapters)
        return {
            "chapter_extraction_rows": [
                {
                    "chapter_no": chapter["chapter_no"],
                    "chapter_title": chapter["chapter_title"],
                    "extraction_json_url": f"fake_{chapter['chapter_no']}.json",
                }
                for chapter in chapters
            ],
            "chapter_extraction_cache_dir": (tmp_path / "extraction_json").as_posix(),
            "llm": {"provider": "test"},
        }

    monkeypatch.setattr(dispatcher, "dispatch_chapter_prompts", fake_dispatch_chapter_prompts)

    result = dispatcher.build_chapter_dispatch_from_source(
        source_path=source_path.as_posix(),
        source_type="txt",
        source_file_id="sf_limit_test",
        file_name="source.txt",
        book_id="b_limit_test",
        book_title="limit_test",
        max_chapters=2,
    )

    assert seen["chapter_count"] == 2
    assert len(result["chapter_rows"]) == 2
    assert len(result["chapter_extraction_rows"]) == 2


def test_dispatch_summary_prompts_falls_back_to_l2_entries_when_json_empty(monkeypatch, tmp_path):
    chapter_dir = tmp_path / "book_cache" / "extraction_json"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    (chapter_dir / "sf_test_001_chapter_0001.json").write_text(
        json.dumps(
            {
                "chapter_title": "第1章",
                "characters": {
                    "characters": [
                        {
                            "name": "林婉",
                            "behavior": ["烧毁药方"],
                            "personality": "冷静",
                        }
                    ]
                },
                "items": {
                    "items": [
                        {
                            "name": "错误药方",
                            "description": "导致医馆失火的药方",
                        }
                    ]
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fake_call_ollama_json(**kwargs):
        return {}

    def fake_call_llm_text(**kwargs):
        return "- 占位"

    monkeypatch.setattr(dispatcher, "call_ollama_json", fake_call_ollama_json)
    monkeypatch.setattr(dispatcher, "call_llm_text", fake_call_llm_text)

    dispatcher.dispatch_summary_prompts(
        chapter_json_dir=chapter_dir,
        source_file_id="sf_test_001",
        book_title="测试书名",
        enabled_dimensions=["characters", "items"],
    )

    characters_index_path = chapter_dir.parent / "summary" / "characters" / "all_characters.json"
    character_detail_path = chapter_dir.parent / "summary" / "characters" / "character_json" / "林婉.json"
    items_path = chapter_dir.parent / "summary" / "items" / "items.json"

    characters_index = json.loads(characters_index_path.read_text(encoding="utf-8"))
    character_detail = json.loads(character_detail_path.read_text(encoding="utf-8"))
    items = json.loads(items_path.read_text(encoding="utf-8"))

    assert characters_index[0]["name"] == "林婉"
    assert "烧毁药方" in character_detail["summary"]
    assert character_detail["personality"] == "冷静"
    assert items[0]["name"] == "错误药方"
    assert items[0]["summary"] == "导致医馆失火的药方"
