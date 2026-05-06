import base64
import json
import uuid
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List

import httpx

from .config import settings


class LLMClient(ABC):
    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]]) -> str:
        raise NotImplementedError

    async def stream_chat(self, messages: List[Dict[str, str]]) -> AsyncIterator[str]:
        text = await self.chat(messages)
        yield text


class OpenAICompatibleClient(LLMClient):
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model, "messages": messages, "temperature": 0.2}
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", headers=headers, json=payload
            )
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def stream_chat(self, messages: List[Dict[str, str]]) -> AsyncIterator[str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_line = line[6:]
                    if data_line.strip() == "[DONE]":
                        break
                    try:
                        item = json.loads(data_line)
                    except json.JSONDecodeError:
                        continue
                    delta = (
                        item.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content")
                    )
                    if delta:
                        yield str(delta)


class GigaChatClient(LLMClient):
    def __init__(self):
        self.auth_url = settings.gigachat_auth_url
        self.api_url = settings.gigachat_api_url
        self.scope = settings.gigachat_scope
        self.client_id = settings.gigachat_client_id
        self.client_secret = settings.gigachat_client_secret
        self.model = settings.gigachat_model

    async def _get_token(self) -> str:
        if not self.client_id or not self.client_secret:
            raise RuntimeError("GigaChat credentials are not configured")
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"scope": self.scope}
        async with httpx.AsyncClient(timeout=60, verify=False) as client:
            resp = await client.post(self.auth_url, headers=headers, data=data)
            resp.raise_for_status()
            token_json = resp.json()
        return token_json["access_token"]

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        token = await self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=90, verify=False) as client:
            resp = await client.post(self.api_url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def stream_chat(self, messages: List[Dict[str, str]]) -> AsyncIterator[str]:
        token = await self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120, verify=False) as client:
            async with client.stream("POST", self.api_url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                streamed = False
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    streamed = True
                    data_line = line[6:]
                    if data_line.strip() == "[DONE]":
                        break
                    try:
                        item = json.loads(data_line)
                    except json.JSONDecodeError:
                        continue
                    delta = (
                        item.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content")
                    )
                    if delta:
                        yield str(delta)
                if not streamed:
                    # Graceful fallback if stream mode is unsupported in current API tier.
                    yield await self.chat(messages)


def get_client(provider: str) -> LLMClient:
    provider = provider.lower()
    if provider == "openai":
        return OpenAICompatibleClient(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
    if provider == "ollama":
        return OpenAICompatibleClient(
            base_url=f"{settings.ollama_base_url}/v1",
            api_key="",
            model=settings.ollama_model,
        )
    if provider == "gigachat":
        return GigaChatClient()
    raise ValueError(f"Unsupported provider: {provider}")
