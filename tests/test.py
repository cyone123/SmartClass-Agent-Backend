from pathlib import Path

from dotenv import load_dotenv
import os
load_dotenv()

from openai import OpenAI

def get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    return value

client = OpenAI(
    api_key=get_env("STT_API_KEY"),
    base_url=get_env("STT_BASE_URL")
)

file_path = Path("D:\\Learn\\langchain\\demo\\backend\\storage\\attachments\\5f269ddd9fe244c9be0b1bb4c0337a38\\voice_113315.webm")

try:
    with file_path.open("rb") as audio_file:
        response =  client.audio.transcriptions.create(
            model=get_env("STT_MODEL"),
            file=audio_file,
            # language=self.client_config.language,
            response_format="text",
        )
        print(f"语音转文本success: {response}")
except Exception as exc:  
    message = str(exc).strip() or exc.__class__.__name__
    print(f"语音转文本error: {message}")
    lowered = message.lower()
    if any(token in lowered for token in ("transcription", "audio", "unsupported", "not found")):
        raise RuntimeError("Current speech provider does not support transcription.") from exc
    raise RuntimeError(f"Speech transcription failed: {message}") from exc