"""Tiny local DeepSeek-compatible server for launch smoke tests.

Usage:
    python -m scripts.mock_deepseek_server --port 1081

Then run the backend with:
    DEEPSEEK_BASE_URL=http://127.0.0.1:1081/v1

The server implements the OpenAI-compatible chat completions response shape used
by the DeepSeek client. It is intended only for local/CI smoke validation.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _response_for_prompt(prompt: str) -> str:
    if "图文排版助手" in prompt or '"pages"' in prompt or "分页正文" in prompt:
        return json.dumps(
            {
                "pages": [
                    "顺发把选题、起稿、预览和发布压成一条不断点的路径，让第一次发出去更容易。",
                    "当用户发布后立刻看到连胜和积分变化，表达会从偶尔行动变成可持续反馈。",
                ],
                "title": "先发出去才有习惯",
                "tags": ["顺发", "表达", "习惯", "AI", "发布"],
            },
            ensure_ascii=False,
        )

    if "事实校验器" in prompt or "分析深度审核员" in prompt or "内容质量审核员" in prompt:
        return json.dumps({"pass": True, "issues": []}, ensure_ascii=False)

    if "社交媒体内容策略师" in prompt and "讨论空间" in prompt:
        return json.dumps([{"index": 0, "score": 9, "category": "industry"}], ensure_ascii=False)

    if "热点内容策略师" in prompt and "ai_angle" in prompt:
        return json.dumps(
            {
                "ai_angle": "降低发布摩擦比追求完美表达更能帮助用户建立习惯。",
                "ai_counter_angle": "过度压缩流程可能牺牲内容质量，需要保留编辑空间。",
            },
            ensure_ascii=False,
        )

    return (
        "顺发真正降低的是发布前的心理摩擦。用户不需要先想清楚完整文章，只要选一个热点，"
        "沿着一个明确角度生成初稿，再在预览页确认发布。\n"
        "这个路径的关键不是让内容一次完美，而是让表达动作持续发生。发布后积分和连胜立即更新，"
        "用户会看到今天没有中断，这个反馈比单纯的文案润色更接近习惯养成。\n"
        "如果工具能稳定保护用户自带 Key、避免重复计分，并在超时时给出可恢复提示，"
        "第一次发布成功率就会更高，后续连续表达才有基础。"
    )


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in {"/health", "/v1/health"}:
            self._write_json({"status": "ok"})
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if not self.path.endswith("/chat/completions"):
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        payload = json.loads(body or b"{}")
        messages = payload.get("messages", [])
        prompt = "\n".join(str(message.get("content", "")) for message in messages)
        content = _response_for_prompt(prompt)
        self._write_json(
            {
                "id": "chatcmpl-local-smoke",
                "object": "chat.completion",
                "created": 0,
                "model": payload.get("model", "deepseek-chat"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        )

    def log_message(self, format: str, *args: object) -> None:
        return

    def _write_json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1081)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"mock DeepSeek listening on http://{args.host}:{args.port}/v1")
    server.serve_forever()


if __name__ == "__main__":
    main()
