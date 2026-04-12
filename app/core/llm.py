from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


def get_model(*, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("MODEL"),
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"),
        streaming=streaming,
    )

def get_structured_output_model(*, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("STRUCTED_MDOEL"),
        api_key=os.getenv("STRUCTED_API_KEY"),
        base_url=os.getenv("STRUCTED_BASE_URL"),
        streaming=streaming,
    )

def get_small_model(*, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("SMALL_MDOEL"),
        api_key=os.getenv("SMALL_API_KEY"),
        base_url=os.getenv("SMALL_BASE_URL"),
        streaming=streaming,
    )

llm = get_model(streaming=True)
structured_output_llm = get_structured_output_model(streaming=False)

