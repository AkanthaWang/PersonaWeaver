"""Isolated local model endpoints used only by the browser regression script."""

from backend.app.application import create_app


app = create_app()


@app.post("/mock/v1/chat/completions")
def chat(payload: dict):
    return {"id": "test", "object": "chat.completion", "created": 0, "model": payload["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


@app.post("/mock/v1/embeddings")
def embeddings(payload: dict):
    texts = payload["input"]
    return {"data": [{"index": index, "embedding": [1.0, 0.5, 0.25]} for index, _ in enumerate(texts)]}


@app.post("/mock/v1/rerank")
def rerank(payload: dict):
    return {"results": [{"index": index, "relevance_score": 1.0 / (index + 1)}
                        for index in range(min(payload["top_n"], len(payload["documents"])))]}
