"""Probe ECNU transport without credentials, model calls, or database writes."""

import sys
from urllib.parse import urlsplit

import requests

from backend.app.core.config import ecnu_model_env
from backend.app.domains.settings.llm import error_diagnostics
from backend.app.domains.settings.schemas import ModelSettings
from backend.app.ai.providers.llm_client import _normalize_openai_base_url


def probe(url, trust_env=True):
    # Prepare directly to avoid implicit .netrc credentials; keep proxy/CA settings.
    with requests.Session() as session:
        session.trust_env = trust_env
        request = requests.Request("GET", url).prepare()
        settings = session.merge_environment_settings(url, {}, True, None, None)
        with session.send(
            request, timeout=(5, 10), allow_redirects=False, **settings,
        ) as response:
            return response.status_code


def main():
    stale = False
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.get("http://127.0.0.1:8000/health", timeout=(2, 3))
            response.raise_for_status()
            stale = response.json().get("model_config_version") != "ecnu-env-v1"
        print("Backend:", "OLD - stop the old backend and restart" if stale else "ECNU config supported")
    except (requests.RequestException, ValueError) as exc:
        print("Backend health unavailable:", error_diagnostics(exc))

    env = ecnu_model_env()
    if not env["ECNU_API_BASE_URL"] or not env["ECNU_MODEL_NAME"]:
        print("Missing ECNU_API_BASE_URL or ECNU_MODEL_NAME in .env/environment.")
        return 1
    try:
        config = ModelSettings(
            provider="remote_api", base_url=env["ECNU_API_BASE_URL"],
            model=env["ECNU_MODEL_NAME"],
        )
    except ValueError:
        print("Invalid ECNU URL/model configuration.")
        return 1
    endpoint = _normalize_openai_base_url(config.base_url)
    print("Target host:", urlsplit(endpoint).hostname)
    print("ECNU key configured:", bool(env["ECNU_API_KEY"]), "(not sent)")
    try:
        status = probe(endpoint)
    except requests.RequestException as exc:
        print("NETWORK FAILED:", error_diagnostics(exc))
        print("Run this command in your own terminal, not a restricted sandbox.")
        return 1
    print("HTTPS response:", status)
    print("Transport reachable; this GET does not validate the API key or model.")
    print("Next: restart if OLD, then use Save and Test Connection in Settings.")
    return 2 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
