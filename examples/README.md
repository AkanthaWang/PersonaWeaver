# Examples

本目录用于保存 PersonaWeaver 公开仓库中的最小演示样例，和本地运行数据目录 `data/` 分离。

## 目录约定

- `inputs/`: 可公开、脱敏、小规模的输入样例。
- `requests/`: API 或函数调用请求样例。
- `outputs/`: 小规模演示输出样例或结构说明。

## 与 data/ 的区别

- `data/` 是本地运行数据目录，默认不提交，适合放完整小说、临时测试文本或较大的实验数据。
- `examples/` 是公开演示目录，只放可以提交到远程仓库的样例。
- 当前后端已经支持通过 `source_path`、`file_url` 等输入路径调用，不要求演示数据必须放在 `data/`。

## 最小调用示例

```python
from backend.workflow_runner import run_l0_to_l2_pipeline

result = run_l0_to_l2_pipeline(
    source_path="examples/inputs/demo_short_story.txt",
    source_type="txt",
    source_file_id="sf_demo_public_001",
    file_name="demo_short_story.txt",
    book_id="book_demo_public_001",
    book_title="公开演示短篇",
    upload_chapters_to_remote=False,
    upload_summary_to_remote=False,
    upload_card_to_remote=False,
)

print(result["source_file_row"])
```
