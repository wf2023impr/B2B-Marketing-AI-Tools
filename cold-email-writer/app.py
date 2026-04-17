"""
Cold Email Writer — AI-powered B2B cold email generator
========================================================
Generate personalized cold emails in 3 styles (Direct / Story / Data-driven).
Supports OpenAI, Claude, and DeepSeek APIs.
"""

import gradio as gr
import json
import httpx
import os

# ── Version ──
VERSION = "1.0.0"

# ── API Providers ──
PROVIDERS = {
    "OpenAI (GPT-4o)": {
        "url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o",
        "header_key": "Authorization",
        "header_fmt": "Bearer {key}",
    },
    "OpenAI (GPT-4o-mini)": {
        "url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
        "header_key": "Authorization",
        "header_fmt": "Bearer {key}",
    },
    "Claude (Sonnet)": {
        "url": "https://api.anthropic.com/v1/messages",
        "model": "claude-sonnet-4-20250514",
        "header_key": "x-api-key",
        "header_fmt": "{key}",
        "is_claude": True,
    },
    "DeepSeek": {
        "url": "https://api.deepseek.com/v1/chat/completions",
        "model": "deepseek-chat",
        "header_key": "Authorization",
        "header_fmt": "Bearer {key}",
    },
}

# ── System prompt ──
SYSTEM_PROMPT = """You are an expert B2B cold email copywriter. You write concise, personalized emails that get replies.

Rules:
- Subject line must be under 60 characters, curiosity-driven, no clickbait
- Email body under 150 words
- Always include a specific reason for reaching out (based on the company/role info)
- End with a low-friction CTA (e.g., "Worth a quick chat?" not "Book a 30-min demo")
- No generic flattery ("I love your company!")
- Sound human, not like a template
- Write in the language specified by the user (default: English)"""

USER_PROMPT_TEMPLATE = """Generate 3 cold emails for the following prospect:

**Target Company:** {company}
**Target Role/Title:** {role}
**What they likely care about:** {pain_points}

**My Product/Service:** {product}
**Key Value Proposition:** {value_prop}

**Language:** {language}

Generate exactly 3 versions:
1. **Direct** — Get straight to the point. Lead with the value.
2. **Story** — Open with a brief relatable scenario or customer success.
3. **Data-driven** — Lead with a compelling stat or metric.

For each version, output in this exact format:

## Version 1: Direct

**Subject:** [subject line]

[email body]

---

## Version 2: Story

**Subject:** [subject line]

[email body]

---

## Version 3: Data-driven

**Subject:** [subject line]

[email body]"""


def call_openai_compatible(url: str, model: str, api_key: str, header_key: str, header_fmt: str, messages: list, **kwargs) -> str:
    """Call OpenAI-compatible API (OpenAI, DeepSeek, etc.)"""
    headers = {
        "Content-Type": "application/json",
        header_key: header_fmt.format(key=api_key),
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 2000,
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def call_claude(url: str, model: str, api_key: str, messages: list, **kwargs) -> str:
    """Call Claude API"""
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    # Extract system message
    system = ""
    user_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system = msg["content"]
        else:
            user_messages.append(msg)

    payload = {
        "model": model,
        "max_tokens": 2000,
        "temperature": 0.8,
        "system": system,
        "messages": user_messages,
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def generate_emails(provider_name, api_key, company, role, pain_points, product, value_prop, language):
    """Main generation function"""
    # Validate inputs
    if not api_key.strip():
        return "**Error:** Please enter your API key."
    if not company.strip():
        return "**Error:** Please enter the target company name."
    if not product.strip():
        return "**Error:** Please describe your product/service."

    provider = PROVIDERS[provider_name]
    user_prompt = USER_PROMPT_TEMPLATE.format(
        company=company.strip(),
        role=role.strip() or "Decision maker",
        pain_points=pain_points.strip() or "Improving efficiency and reducing costs",
        product=product.strip(),
        value_prop=value_prop.strip() or product.strip(),
        language=language,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        if provider.get("is_claude"):
            result = call_claude(
                url=provider["url"],
                model=provider["model"],
                api_key=api_key.strip(),
                messages=messages,
            )
        else:
            result = call_openai_compatible(
                url=provider["url"],
                model=provider["model"],
                api_key=api_key.strip(),
                header_key=provider["header_key"],
                header_fmt=provider["header_fmt"],
                messages=messages,
            )
        return result
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return "**Error:** Invalid API key. Please check and try again."
        elif e.response.status_code == 429:
            return "**Error:** Rate limit exceeded. Please wait a moment and try again."
        else:
            return f"**Error:** API returned status {e.response.status_code}.\n\n```\n{e.response.text[:500]}\n```"
    except httpx.ConnectError:
        return "**Error:** Cannot connect to the API. Please check your network or try a different provider."
    except Exception as e:
        return f"**Error:** {type(e).__name__}: {e}"


# ── Gradio UI ──

THEME = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="slate",
)

CSS = """
.output-markdown { min-height: 400px; }
footer { display: none !important; }
"""

def build_ui():
    with gr.Blocks(theme=THEME, css=CSS, title="Cold Email Writer") as app:
        gr.Markdown("# Cold Email Writer\nGenerate personalized B2B cold emails in seconds. Bring your own API key.")

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### Settings")
                provider = gr.Dropdown(
                    choices=list(PROVIDERS.keys()),
                    value="OpenAI (GPT-4o-mini)",
                    label="AI Provider",
                )
                api_key = gr.Textbox(
                    label="API Key",
                    type="password",
                    placeholder="sk-... or your API key",
                )
                language = gr.Dropdown(
                    choices=["English", "Chinese (简体中文)", "Japanese (日本語)", "Korean (한국어)", "Spanish", "French", "German"],
                    value="English",
                    label="Output Language",
                )

                gr.Markdown("### About the Prospect")
                company = gr.Textbox(
                    label="Target Company *",
                    placeholder="e.g., Stripe, Shopify, Salesforce",
                )
                role = gr.Textbox(
                    label="Target Role / Title",
                    placeholder="e.g., VP of Marketing, CTO (optional)",
                )
                pain_points = gr.Textbox(
                    label="What they likely care about",
                    placeholder="e.g., Scaling outbound, reducing CAC (optional)",
                    lines=2,
                )

                gr.Markdown("### About Your Product")
                product = gr.Textbox(
                    label="Your Product / Service *",
                    placeholder="e.g., AI-powered email outreach platform",
                )
                value_prop = gr.Textbox(
                    label="Key Value Proposition",
                    placeholder="e.g., 3x reply rates with AI personalization (optional)",
                    lines=2,
                )

                btn = gr.Button("Generate Emails", variant="primary", size="lg")

            with gr.Column(scale=1):
                gr.Markdown("### Generated Emails")
                output = gr.Markdown(
                    value="*Your emails will appear here. Fill in the form and click Generate.*",
                    elem_classes="output-markdown",
                )

        btn.click(
            fn=generate_emails,
            inputs=[provider, api_key, company, role, pain_points, product, value_prop, language],
            outputs=output,
        )

        gr.Markdown(f"---\n*Cold Email Writer v{VERSION} — [B2B Marketing AI Tools](https://github.com/wf2023impr/B2B-Marketing-AI-Tools)*")

    return app


if __name__ == "__main__":
    app = build_ui()
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        inbrowser=True,
        show_api=False,
    )
