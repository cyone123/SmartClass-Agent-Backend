from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fastapi import Request

from app.config import (
    get_stt_api_key,
    get_stt_base_url,
    get_stt_language,
    get_stt_model,
)

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - provided transitively in runtime installs
    AsyncOpenAI = None


@dataclass(frozen=True)
class SpeechClientConfig:
    model: str | None
    base_url: str | None
    api_key: str | None
    language: str | None = None


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str | None = None


class SpeechRuntime(Protocol):
    async def transcribe(
        self,
        *,
        file_path: Path,
        filename: str,
        mime_type: str | None = None,
    ) -> TranscriptionResult: ...


def get_speech_client_config() -> SpeechClientConfig:
    return SpeechClientConfig(
        model=get_stt_model(),
        base_url=get_stt_base_url(),
        api_key=get_stt_api_key(),
        language=get_stt_language(),
    )


class OpenAICompatibleSpeechRuntime:
    def __init__(self, client_config: SpeechClientConfig | None = None) -> None:
        self.client_config = client_config or get_speech_client_config()
        self._client = None
        if AsyncOpenAI is not None and self.client_config.api_key and self.client_config.base_url:
            self._client = AsyncOpenAI(
                api_key=self.client_config.api_key,
                base_url=self.client_config.base_url,
            )

    async def transcribe(
        self,
        *,
        file_path: Path,
        filename: str,
        mime_type: str | None = None,
    ) -> TranscriptionResult:
        if AsyncOpenAI is None:
            raise RuntimeError("The openai package is required for speech transcription support.")
        if not self.client_config.model:
            raise RuntimeError("Speech transcription is not configured. Set STT_MODEL or MODEL.")
        if self._client is None:
            raise RuntimeError(
                "Speech transcription is not configured. Set STT_BASE_URL/STT_API_KEY or BASE_URL/API_KEY."
            )

        try:
            with file_path.open("rb") as audio_file:
                response = await self._client.audio.transcriptions.create(
                    model=self.client_config.model,
                    file=audio_file,
                    # language=self.client_config.language,
                    response_format="verbose_json",
                )
                print(f"语音转文本success: {str(response)}")
        except Exception as exc:  
            message = str(exc).strip() or exc.__class__.__name__
            print(f"语音转文本error: {message}")
            lowered = message.lower()
            if any(token in lowered for token in ("transcription", "audio", "unsupported", "not found")):
                raise RuntimeError("Current speech provider does not support transcription.") from exc
            raise RuntimeError(f"Speech transcription failed: {message}") from exc

        text = None
        language = self.client_config.language
        if isinstance(response, str):
            text = response
        elif isinstance(response, dict):
            text = response.get("text")
            language = response.get("language") or language
        else:
            text = getattr(response, "text", None)
            language = getattr(response, "language", None) or language

        normalized_text = text.strip() if isinstance(text, str) else ""
        if not normalized_text:
            raise RuntimeError("Speech transcription returned empty text.")

        _ = filename, mime_type
        return TranscriptionResult(text=normalized_text, language=language)


def create_speech_runtime() -> SpeechRuntime:
    return OpenAICompatibleSpeechRuntime()


def get_speech_runtime(request: Request) -> SpeechRuntime:
    runtime = getattr(request.app.state, "speech_runtime", None)
    if runtime is None:
        raise RuntimeError("Speech runtime is not initialized.")
    return runtime
