from backend.source_preprocess import process_source_file


def test_process_source_file_txt_smoke():
    result = process_source_file(
        source_path="data/神游.txt",
        source_type="txt",
        source_file_id="sf_test_001",
        filter_noise=True,
    )
    assert "unified_format_url" in result
    assert isinstance(result.get("chapters"), list)
