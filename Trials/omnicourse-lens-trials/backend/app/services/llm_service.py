from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..config import settings


@dataclass
class AzureCredentials:
    endpoint: str | None = None
    api_key: str | None = None
    deployment: str = "gpt-4o"
    api_version: str = "2024-12-01-preview"


class LLMService:
    def __init__(self) -> None:
        self.credentials = self._load_credentials()
        self._client = None

    def is_available(self) -> bool:
        return bool(self.credentials.endpoint and self.credentials.api_key)

    def describe_provider(self) -> dict[str, Any]:
        return {
            "provider": "azure_openai_gpt4o",
            "available": self.is_available(),
            "endpoint_configured": bool(self.credentials.endpoint),
            "api_key_present": bool(self.credentials.api_key),
            "api_key_suffix": self.credentials.api_key[-4:] if self.credentials.api_key else None,
            "deployment": self.credentials.deployment,
            "api_version": self.credentials.api_version,
            "credential_file_detected": settings.credential_file.exists(),
        }

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: int = 4096) -> str:
        if not self.is_available():
            return ""
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=1.0,
                model=self.credentials.deployment,
            )
            return response.choices[0].message.content or ""
        except Exception:
            return ""

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.1, max_tokens: int = 4096) -> dict[str, Any]:
        text = self.chat(system_prompt, user_prompt, temperature=temperature, max_tokens=max_tokens)
        if not text:
            return {"raw_text": "", "parse_error": "llm_unavailable_or_empty"}
        cleaned = self._strip_code_fence(text)
        try:
            data = json.loads(cleaned)
            return data if isinstance(data, dict) else {"raw_text": text, "parse_error": "json_root_not_object"}
        except Exception as exc:
            return {"raw_text": text, "parse_error": type(exc).__name__}

    def _get_client(self):
        if self._client is not None:
            return self._client
        from openai import AzureOpenAI

        self._client = AzureOpenAI(
            api_version=self.credentials.api_version,
            azure_endpoint=self.credentials.endpoint,
            api_key=self.credentials.api_key,
        )
        return self._client

    def _load_credentials(self) -> AzureCredentials:
        creds = AzureCredentials(
            endpoint=os.getenv("AZURE_OPENAI_ENDPOINT") or None,
            api_key=os.getenv("AZURE_OPENAI_API_KEY") or None,
            deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT") or "gpt-4o",
            api_version=os.getenv("AZURE_OPENAI_API_VERSION") or "2024-12-01-preview",
        )
        if creds.endpoint and creds.api_key:
            return self._normalize_endpoint(creds)
        if settings.credential_file.exists():
            text = settings.credential_file.read_text(encoding="utf-8", errors="ignore")
            file_creds = self._parse_credential_text(text)
            creds.endpoint = creds.endpoint or file_creds.endpoint
            creds.api_key = creds.api_key or file_creds.api_key
            creds.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT") or file_creds.deployment or creds.deployment
            creds.api_version = os.getenv("AZURE_OPENAI_API_VERSION") or file_creds.api_version or creds.api_version
        return self._normalize_endpoint(creds)

    def _parse_credential_text(self, text: str) -> AzureCredentials:
        endpoint = self._first_match(
            text,
            [
                r"AZURE_OPENAI_ENDPOINT\s*=\s*[\"']?([^\"'\n]+)",
                r"\bendpoint\s*=\s*[\"']([^\"']+)",
                r"(https://[^\s\"']+/openai/deployments/[^\s\"']+)",
                r"(https://[^\s\"']+\.openai\.azure\.com[^\s\"']*)",
                r"(https://[^\s\"']+\.cognitiveservices\.azure\.com[^\s\"']*)",
            ],
        )
        api_key = self._first_match(
            text,
            [
                r"AZURE_OPENAI_API_KEY\s*=\s*[\"']?([^\"'\n]+)",
                r"\bsubscription_key\s*=\s*[\"']([^\"']+)",
                r"\bapi_key\s*=\s*[\"']([^\"']+)",
                r"\bkey\s*=\s*[\"']([^\"']+)",
            ],
        )
        deployment = self._first_match(
            text,
            [
                r"AZURE_OPENAI_DEPLOYMENT\s*=\s*[\"']?([^\"'\n]+)",
                r"\bdeployment\s*=\s*[\"']([^\"']+)",
                r"/deployments/([^/]+)/",
            ],
        )
        api_version = self._first_match(
            text,
            [
                r"AZURE_OPENAI_API_VERSION\s*=\s*[\"']?([^\"'\n]+)",
                r"\bapi_version\s*=\s*[\"']([^\"']+)",
                r"api-version=([A-Za-z0-9._-]+)",
            ],
        )
        return AzureCredentials(endpoint=endpoint, api_key=api_key, deployment=deployment or "gpt-4o", api_version=api_version or "2024-12-01-preview")

    def _normalize_endpoint(self, creds: AzureCredentials) -> AzureCredentials:
        if not creds.endpoint:
            return creds
        parsed = urlparse(creds.endpoint.strip())
        if "/openai/" in parsed.path:
            deployment_match = re.search(r"/deployments/([^/]+)", parsed.path)
            if deployment_match:
                creds.deployment = creds.deployment or deployment_match.group(1)
            query_version = parse_qs(parsed.query).get("api-version", [None])[0]
            if query_version:
                creds.api_version = query_version
            creds.endpoint = f"{parsed.scheme}://{parsed.netloc}"
        else:
            creds.endpoint = creds.endpoint.rstrip("/")
        return creds

    def _first_match(self, text: str, patterns: list[str]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return None

    def _strip_code_fence(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        return text.strip()
