#!/usr/bin/env python3
"""Verify that the live Qwen endpoint returns safe, executable Python code."""

from __future__ import annotations

import ast
import json
import time
import urllib.request


URL = "http://127.0.0.1:8081/v1/chat/completions"
PROMPT = (
    "Write only valid Python code, with no Markdown and no explanation. "
    "Implement def clamp(value, low, high): using only if statements and "
    "return statements. Do not call any function and do not import anything."
)


def extract_code(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines.pop()
        text = "\n".join(lines)
    return text.strip()


def main() -> None:
    payload = json.dumps(
        {
            "model": "qwen3-coder-480b-q4km",
            "messages": [{"role": "user", "content": PROMPT}],
            "temperature": 0.0,
            "max_tokens": 160,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        URL, payload, {"Content-Type": "application/json"}, method="POST"
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=900) as response:
        body = json.load(response)
    elapsed = time.monotonic() - started
    content = body["choices"][0]["message"]["content"]
    code = extract_code(content)
    tree = ast.parse(code)

    allowed = {
        ast.Module,
        ast.FunctionDef,
        ast.arguments,
        ast.arg,
        ast.If,
        ast.Compare,
        ast.Name,
        ast.Load,
        ast.Return,
        ast.Constant,
        ast.Lt,
        ast.Gt,
        ast.LtE,
        ast.GtE,
    }
    rejected = sorted({type(node).__name__ for node in ast.walk(tree) if type(node) not in allowed})
    if rejected:
        raise RuntimeError(f"generated code used rejected AST nodes: {rejected}")
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    if len(functions) != 1 or functions[0].name != "clamp":
        raise RuntimeError("generated code did not define exactly one clamp function")

    namespace: dict[str, object] = {}
    exec(compile(tree, "<qwen-generated>", "exec"), {"__builtins__": {}}, namespace)
    clamp = namespace["clamp"]
    cases = [
        ((5, 0, 10), 5),
        ((-3, 0, 10), 0),
        ((15, 0, 10), 10),
        ((2.5, 2.5, 9.0), 2.5),
    ]
    for args, expected in cases:
        actual = clamp(*args)  # type: ignore[operator]
        if actual != expected:
            raise AssertionError((args, actual, expected))

    print(
        json.dumps(
            {
                "status": "PASS",
                "model": body.get("model"),
                "elapsed_seconds": round(elapsed, 3),
                "tests_passed": len(cases),
                "generated_code": code,
                "usage": body.get("usage"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
