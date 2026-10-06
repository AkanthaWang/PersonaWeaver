from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.llm_dispatch.llm_client import call_llm_json, call_llm_text

try:
    from backend.remote_persistence import _upload_file_to_oss
except Exception:  # pragma: no cover - OSS dependency is optional in local tests
    _upload_file_to_oss = None


def _load_dotenv_simple() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key not in os.environ:
            os.environ[key] = value


def _provider_config(provider: str) -> dict[str, str]:
    normalized = provider.strip().lower()
    if normalized in {"vivo", "vivo_aigc"}:
        return {
            "provider": "vivo",
            "base_url": os.getenv("VIVO_AIGC_BASE_URL", "https://api-ai.vivo.com.cn/v1/chat/completions"),
            "api_key": os.getenv("VIVO_AIGC_API_KEY", ""),
            "model": os.getenv("VIVO_AIGC_MODEL", "Volc-DeepSeek-V3.2"),
        }
    if normalized in {"remote_api", "ecnu"}:
        return {
            "provider": "remote_api",
            "base_url": os.getenv("ECNU_API_BASE_URL", "https://chat.ecnu.edu.cn/open/api/v1/chat/completions"),
            "api_key": os.getenv("ECNU_API_KEY", ""),
            "model": os.getenv("ECNU_MODEL_NAME", "ecnu-max"),
        }
    raise ValueError(f"Unsupported provider: {provider}")


def _read_sample_text(sample_path: str | None, max_chars: int) -> str:
    if not sample_path:
        return "第一章 初遇\n林澈在雨后的旧书店里发现一本手札。店主阿宁提醒他，这本书只会记录读者真正关心的人与事。"
    path = Path(sample_path)
    if path.is_dir():
        parts: list[str] = []
        for file_path in sorted(path.glob("*.txt"))[:10]:
            parts.append(f"【{file_path.name}】\n{file_path.read_text(encoding='utf-8', errors='ignore')}")
        text = "\n\n".join(parts)
    else:
        text = path.read_text(encoding="utf-8", errors="ignore")
    return text[:max_chars]


def run_smoke(provider: str, sample_path: str | None, mode: str, max_chars: int) -> dict[str, Any]:
    cfg = _provider_config(provider)
    if not cfg["api_key"]:
        raise RuntimeError(f"{cfg['provider']} 缺少 api_key，请先在 .env 中配置")

    sample_text = _read_sample_text(sample_path, max_chars=max_chars)
    if mode == "json":
        result = call_llm_json(
            text_or_documents=sample_text,
            prompt_description="从样本文本中提取角色名称和关键事件。请输出 JSON 对象，字段包括 characters 和 events。",
            model=cfg["model"],
            base_url=cfg["base_url"],
            provider=cfg["provider"],
            api_key=cfg["api_key"],
            temperature=0.1,
            timeout_seconds=120,
        )
        return {
            "ok": True,
            "provider": cfg["provider"],
            "model": cfg["model"],
            "mode": mode,
            "sample_chars": len(sample_text),
            "result": result,
        }

    text = call_llm_text(
        text_or_documents=sample_text,
        prompt_description="用不超过 120 字概括样本文本，并列出出现的角色名。",
        model=cfg["model"],
        base_url=cfg["base_url"],
        provider=cfg["provider"],
        api_key=cfg["api_key"],
        temperature=0.1,
        timeout_seconds=120,
    )
    return {
        "ok": True,
        "provider": cfg["provider"],
        "model": cfg["model"],
        "mode": mode,
        "sample_chars": len(sample_text),
        "result": text,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="vivo / 校园 API 联通 smoke test")
    parser.add_argument("--provider", default="vivo", choices=["vivo", "remote_api", "ecnu"])
    parser.add_argument("--sample-path", default=None, help="可选：10章样本目录或单个文本文件")
    parser.add_argument("--mode", default="text", choices=["text", "json"])
    parser.add_argument("--max-chars", type=int, default=3000)
    parser.add_argument("--output", default="local_cache/smoke/vivo_provider_smoke_result.json")
    parser.add_argument("--upload-oss", action="store_true", help="将 smoke 输出 JSON 上传到 OSS，用于验证远程文件上传链路")
    parser.add_argument("--oss-prefix", default="smoke/vivo-provider", help="OSS 对象前缀")
    args = parser.parse_args()

    _load_dotenv_simple()
    result = run_smoke(args.provider, args.sample_path, args.mode, args.max_chars)

    output_path = ROOT_DIR / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    oss_url = None
    if args.upload_oss:
        if _upload_file_to_oss is None:
            raise RuntimeError("OSS 上传不可用，请确认已安装 oss2 且配置 OSS_* 环境变量")
        object_key = f"{args.oss_prefix.strip('/')}/{output_path.name}"
        oss_url = _upload_file_to_oss(output_path, object_key)

    print(json.dumps({"ok": True, "output": output_path.as_posix(), "oss_url": oss_url, "provider": result["provider"], "model": result["model"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
