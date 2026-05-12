from __future__ import annotations

import html
from typing import Any


def reason_for_item(item: Any) -> str:
    return item.llm_selection_reason or item.selection_reason or "Selected by transparent score."


def markdown_to_html(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    rendered: list[str] = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                rendered.append("</ul>")
                in_list = False
            continue
        if stripped.startswith("# "):
            if in_list:
                rendered.append("</ul>")
                in_list = False
            rendered.append(f"<h1>{html.escape(stripped[2:])}</h1>")
        elif stripped.startswith("- ") or stripped[:3].lstrip().startswith("- "):
            if not in_list:
                rendered.append("<ul>")
                in_list = True
            content = stripped[2:] if stripped.startswith("- ") else stripped.split("- ", 1)[1]
            rendered.append(f"<li>{_inline_markdown(content)}</li>")
        elif stripped[:2].isdigit() and ". " in stripped[:5]:
            if in_list:
                rendered.append("</ul>")
                in_list = False
            rendered.append(f"<p><strong>{_inline_markdown(stripped)}</strong></p>")
        else:
            if in_list:
                rendered.append("</ul>")
                in_list = False
            rendered.append(f"<p>{_inline_markdown(stripped)}</p>")
    if in_list:
        rendered.append("</ul>")
    return "\n".join(rendered)


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    parts = escaped.split("**")
    if len(parts) == 1:
        return escaped
    output: list[str] = []
    strong = False
    for part in parts:
        if strong:
            output.append(f"<strong>{part}</strong>")
        else:
            output.append(part)
        strong = not strong
    return "".join(output)


def digest_email_html(digest: Any) -> str:
    body = [f"<h1>{html.escape(digest.title)}</h1>"]
    if digest.summary_html:
        body.append(digest.summary_html)
    body.append("<hr>")
    for item in digest.items:
        paper = item.paper
        body.append(f"<h2>{item.rank}. {html.escape(paper.title)}</h2>")
        body.append(f"<p><strong>Reason:</strong> {html.escape(reason_for_item(item))}</p>")
        body.append(f"<p><strong>Score:</strong> {item.score:.2f}</p>")
        if item.short_explanation:
            body.append(f"<p>{html.escape(item.short_explanation)}</p>")
        body.append(f'<p><a href="{html.escape(paper.url)}">Open paper</a></p>')
    return "\n".join(body)
