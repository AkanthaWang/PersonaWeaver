from backend.llm_chapter_extraction import chapter_structured_extractor as extractor


def test_extract_chapter_structured_merges_dimensions_and_strips_empty_fields(monkeypatch):
    calls = []

    def fake_call_ollama_json(**kwargs):
        calls.append(kwargs)
        prompt = kwargs["prompt_description"]
        if "章节信息" in prompt:
            return {
                "chapter_no": "010",
                "chapter_title": "010回 仗义多草莽，跳脚喝神僧",
                "chapter_time": "",
                "characters": ["石野", ""]
            }
        if "本章剧情" in prompt:
            return {
                "chapter_summary": "山神庙前遭遇和尚，风君子与之周旋。",
                "key_events": ["", "和尚登场", "风君子出手"]
            }
        if "本章角色" in prompt:
            return {
                "characters": [
                    {
                        "name": "风君子",
                        "behavior": ["插科打诨", ""],
                        "speech": [],
                    }
                ]
            }
        if "本章关键物品" in prompt:
            return {"items": [{"name": "青冥镜", "description": "", "owner": "石野"}]}
        if "本章地点" in prompt:
            return {"worldview": ["山神庙", ""]}
        if "场景描述" in prompt:
            return {"scene_name": "山神庙", "atmosphere": "", "sensory": ["昏暗", ""]}
        return {}

    monkeypatch.setattr(extractor, "call_ollama_json", fake_call_ollama_json)

    result = extractor.extract_chapter_structured(
        chapter_title="010回 仗义多草莽，跳脚喝神僧",
        chapter_text="章节正文内容",
    )

    assert result["chapter_title"] == "010回 仗义多草莽，跳脚喝神僧"
    assert result["chapter_info"]["chapter_no"] == "010"
    assert result["chapter_info"]["chapter_title"] == "010回 仗义多草莽，跳脚喝神僧"
    assert "chapter_time" not in result["chapter_info"]
    assert result["chapter_info"]["characters"] == ["石野"]
    assert result["plot"]["chapter_summary"] == "山神庙前遭遇和尚，风君子与之周旋。"
    assert result["plot"]["key_events"] == ["和尚登场", "风君子出手"]
    assert result["characters"]["characters"][0]["name"] == "风君子"
    assert result["characters"]["characters"][0]["behavior"] == ["插科打诨"]
    assert result["items"]["items"][0]["name"] == "青冥镜"
    assert result["world"]["worldview"] == ["山神庙"]
    assert result["scene_description"]["scene_name"] == "山神庙"
    assert result["scene_description"]["sensory"] == ["昏暗"]
    assert len(calls) == 6


def test_extract_chapter_structured_records_llm_errors(monkeypatch):
    def fake_call_ollama_json(**kwargs):
        prompt = kwargs["prompt_description"]
        if "章节信息" in prompt:
            return {"chapter_no": "011"}
        raise RuntimeError("ollama unavailable")

    monkeypatch.setattr(extractor, "call_ollama_json", fake_call_ollama_json)

    result = extractor.extract_chapter_structured(
        chapter_title="011回 一阳常生动，阴神初入梦",
        chapter_text="章节正文内容",
        enabled_dimensions=["chapter_info", "plot"],
    )

    assert result["chapter_title"] == "011回 一阳常生动，阴神初入梦"
    assert result["chapter_info"]["chapter_no"] == "011"
    assert result["errors"][0]["dimension"] == "plot"
    assert "ollama unavailable" in result["errors"][0]["error"]