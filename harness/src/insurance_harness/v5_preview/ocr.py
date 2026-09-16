"""Bounded Bailian OCR adapter used by local V5 provider trials."""

from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path
from typing import Annotated, Literal

import httpx
import pdfplumber
from pydantic import BaseModel, ConfigDict, Field

BAILIAN_OCR_MODEL = "qwen-vl-ocr-2025-11-20"


class OcrError(ValueError):
    """The OCR provider response cannot be used as source text."""


class OcrPageReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    file_name: Annotated[str, Field(min_length=1)]
    document_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    page_number: Annotated[int, Field(ge=1)]
    provider: Literal["bailian"] = "bailian"
    model: Literal["qwen-vl-ocr-2025-11-20"] = BAILIAN_OCR_MODEL
    response_id: Annotated[str, Field(min_length=1)]
    text_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    character_count: Annotated[int, Field(ge=1)]


class BailianOcrClient:
    """OCR only empty PDF pages and retain a bounded identity receipt."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        max_calls: int = 2,
        timeout_seconds: float = 180.0,
    ) -> None:
        if max_calls < 1:
            raise ValueError("M146_OCR_CALL_BUDGET_INVALID")
        self._base_url = base_url.rstrip("/")
        self._max_calls = max_calls
        self._call_count = 0
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
        )
        self._receipts: list[OcrPageReceipt] = []

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def receipts(self) -> tuple[OcrPageReceipt, ...]:
        return tuple(self._receipts)

    def close(self) -> None:
        self._client.close()

    def extract_pdf_page(self, path: Path, page_number: int) -> str:
        if self._call_count >= self._max_calls:
            raise OcrError("M146_OCR_CALL_BUDGET_EXHAUSTED")
        with pdfplumber.open(path) as document:
            if not 1 <= page_number <= len(document.pages):
                raise OcrError("M146_OCR_PAGE_OUT_OF_RANGE")
            image = document.pages[page_number - 1].to_image(resolution=180).original
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=92, optimize=True)
        image_url = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
        self._call_count += 1
        response = self._client.post(
            f"{self._base_url}/chat/completions",
            json={
                "model": BAILIAN_OCR_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "按页面从上到下、从左到右识别全部中文、英文、数字和表格。"
                                    "保留标题、条目和换行，只输出识别文本，不解释、不总结、不补写。"
                                ),
                            },
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    }
                ],
                "max_tokens": 8192,
                "temperature": 0,
            },
        )
        response.raise_for_status()
        try:
            payload = response.json()
            choice = payload["choices"][0]
            content = choice["message"]["content"]
            finish_reason = choice.get("finish_reason")
            response_id = str(payload["id"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise OcrError("M146_OCR_RESPONSE_INVALID") from exc
        if finish_reason not in {"stop", None}:
            raise OcrError("M146_OCR_RESPONSE_INCOMPLETE")
        if not isinstance(content, str) or not content.strip():
            raise OcrError("M146_OCR_TEXT_EMPTY")
        text = content.strip()
        document_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        self._receipts.append(
            OcrPageReceipt(
                file_name=path.name,
                document_sha256=document_sha256,
                page_number=page_number,
                response_id=response_id,
                text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                character_count=len(text),
            )
        )
        return text


__all__ = [
    "BAILIAN_OCR_MODEL",
    "BailianOcrClient",
    "OcrError",
    "OcrPageReceipt",
]
