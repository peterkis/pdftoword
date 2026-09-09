#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx

MONKEY_LAYOUT_PROMPT = (
    "Please output the categories and coordinates of the document "
    "elements in reading order."
)

OVIS_REVIEW_PROMPT = (
    "Extract all readable content from the image in natural human reading "
    "order and output the result as a single Markdown document. "
    "For charts or images, represent them using an HTML image tag with "
    "bounding box coordinates scaled to [0, 1000). "
    "Format formulas as LaTeX and tables as HTML. "
    "Preserve the original text, numbers, units, spelling and symbols. "
    "Do not translate, correct, summarize, paraphrase or infer missing content."
)


def get_headers(api_key_env: str) -> dict[str, str]:
    api_key = os.getenv(api_key_env, "").strip()
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}"
        )
    return value


def encode_image(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(data).decode("ascii")
    return encoded, f"data:{mime_type};base64,{encoded}"


def save_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def extract_chat_content(response: dict[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            "OpenAI-compatible response does not contain "
            "choices[0].message.content"
        ) from exc

    if isinstance(content, str):
        return content

    return json.dumps(content, ensure_ascii=False, indent=2)


def call_openai_compatible(
    client: httpx.Client,
    *,
    url: str,
    model: str,
    prompt: str,
    image_data_url: str,
    api_key_env: str,
    max_tokens: int,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url},
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    }

    response = client.post(
        url,
        headers=get_headers(api_key_env),
        json=payload,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test PDF2Word model endpoints."
    )
    parser.add_argument("image", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tmp/model-smoke/results"),
    )
    args = parser.parse_args()

    image_path = args.image.resolve()
    if not image_path.is_file():
        raise SystemExit(f"Image does not exist: {image_path}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    monkey_url = require_env("MONKEY_CHAT_URL")
    monkey_model = os.getenv("MONKEY_MODEL", "MonkeyOCRv2")

    ovis_url = require_env("OVIS_CHAT_URL")
    ovis_model = os.getenv("OVIS_MODEL", "ovis-ocr2")

    paddle_url = require_env("PP_STRUCTURE_URL")

    image_base64, image_data_url = encode_image(image_path)

    timeout = httpx.Timeout(
        connect=10.0,
        read=600.0,
        write=120.0,
        pool=10.0,
    )

    # 顺序调用，避免单张 16GB GPU 被三个任务同时占用。
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        print("[1/3] Calling MonkeyOCRv2...")

        monkey_response = call_openai_compatible(
            client,
            url=monkey_url,
            model=monkey_model,
            prompt=MONKEY_LAYOUT_PROMPT,
            image_data_url=image_data_url,
            api_key_env="MONKEY_API_KEY",
            max_tokens=4096,
        )
        save_json(output_dir / "monkey.raw.json", monkey_response)
        (output_dir / "monkey.content.txt").write_text(
            extract_chat_content(monkey_response),
            encoding="utf-8",
        )

        print("[2/3] Calling OvisOCR2...")

        ovis_response = call_openai_compatible(
            client,
            url=ovis_url,
            model=ovis_model,
            prompt=OVIS_REVIEW_PROMPT,
            image_data_url=image_data_url,
            api_key_env="OVIS_API_KEY",
            max_tokens=8192,
        )
        save_json(output_dir / "ovis.raw.json", ovis_response)
        (output_dir / "ovis.content.md").write_text(
            extract_chat_content(ovis_response),
            encoding="utf-8",
        )

        print("[3/3] Calling PP-StructureV3...")

        paddle_payload = {
            "file": image_base64,
            "fileType": 1,
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useTextlineOrientation": False,
            "useSealRecognition": False,
            "useTableRecognition": True,
            "useFormulaRecognition": True,
            "useChartRecognition": False,
            "useRegionDetection": True,
            "formatBlockContent": False,
            "visualize": False,
        }

        paddle_response = client.post(
            paddle_url,
            headers=get_headers("PADDLE_API_KEY"),
            json=paddle_payload,
        )
        paddle_response.raise_for_status()
        paddle_json = paddle_response.json()
        save_json(output_dir / "pp-structure.raw.json", paddle_json)

    # 输出 PP-StructureV3 结构摘要。
    try:
        page = paddle_json["result"]["layoutParsingResults"][0]
        pruned = page["prunedResult"]

        summary = {
            "pruned_result_keys": sorted(pruned.keys()),
            "parsing_block_count": len(
                pruned.get("parsing_res_list", [])
            ),
            "ocr_text_count": len(
                pruned.get("overall_ocr_res", {}).get("rec_texts", [])
            ),
            "table_count": len(pruned.get("table_res_list", [])),
            "formula_count": len(pruned.get("formula_res_list", [])),
        }
        save_json(output_dir / "pp-structure.summary.json", summary)
    except (KeyError, IndexError, TypeError):
        print(
            "WARNING: PP-StructureV3 returned HTTP 200, but the response "
            "shape differs from the expected official structure."
        )

    print()
    print("Smoke tests completed.")
    print(f"Results: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
