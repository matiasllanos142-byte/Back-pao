import json
import re

import requests


TEXT_KEYWORDS = ("llama", "qwen", "mistral", "gemma", "instruct", "chat", "nemotron")
REASONING_KEYWORDS = ("reason", "deepseek-r1", "r1", "thinking", "nemotron")
CODE_KEYWORDS = ("code", "coder", "codellama", "codegemma")
VISION_KEYWORDS = ("vision", "vlm", "llava", "parse", "ocr", "visual")
IMAGE_KEYWORDS = ("flux", "stable-diffusion", "sdxl", "qwen-image", "image")
EMBEDDING_KEYWORDS = ("embed", "embedding", "rerank", "retriever")

ROLE_PRIORITY = {
    "orchestrator": ("reasoning", "text"),
    "planner": ("text", "reasoning"),
    "builder": ("text", "reasoning"),
    "vision": ("vision",),
    "image": ("image",),
    "code": ("code", "reasoning", "text"),
}


def classify_model(model_id):
    value = str(model_id or "").lower()
    roles = set()
    if any(keyword in value for keyword in EMBEDDING_KEYWORDS):
        roles.add("embedding")
    if any(keyword in value for keyword in IMAGE_KEYWORDS):
        roles.add("image")
    if any(keyword in value for keyword in VISION_KEYWORDS):
        roles.add("vision")
    if any(keyword in value for keyword in CODE_KEYWORDS):
        roles.add("code")
    if any(keyword in value for keyword in REASONING_KEYWORDS):
        roles.add("reasoning")
    if any(keyword in value for keyword in TEXT_KEYWORDS):
        roles.add("text")

    if not roles or roles == {"reasoning"}:
        roles.add("text")
    return sorted(roles)


def _display_name(model):
    return model.get("name") or model.get("id") or model.get("model") or ""


def normalize_models(raw_models):
    normalized = []
    for raw in raw_models or []:
        if not isinstance(raw, dict):
            continue
        model_id = str(raw.get("id") or raw.get("model") or raw.get("name") or "").strip()
        if not model_id:
            continue
        roles = classify_model(model_id)
        normalized.append(
            {
                "id": model_id,
                "name": _display_name(raw),
                "roles": roles,
                "ownedBy": raw.get("owned_by") or raw.get("ownedBy") or "",
                "available": True,
            }
        )
    return sorted(normalized, key=lambda item: item["id"].lower())


def _score_model_for_role(model, wanted_roles):
    roles = set(model.get("roles") or [])
    model_id = model.get("id", "").lower()
    score = 0
    for index, role in enumerate(wanted_roles):
        if role in roles:
            score += (len(wanted_roles) - index) * 100
    if "latest" in model_id:
        score += 8
    if "70b" in model_id or "405b" in model_id:
        score += 7
    if "8b" in model_id or "mini" in model_id:
        score += 2
    if "embed" in roles or "image" in roles:
        score -= 80
    return score


def choose_model_for_role(models, role):
    wanted_roles = ROLE_PRIORITY.get(role, ("text",))
    candidates = [
        model
        for model in models
        if any(wanted in set(model.get("roles") or []) for wanted in wanted_roles)
    ]
    if not candidates:
        return ""
    return max(candidates, key=lambda model: _score_model_for_role(model, wanted_roles)).get("id", "")


def build_roles(models, existing_roles=None):
    existing_roles = existing_roles or {}
    roles = {}
    for role in ROLE_PRIORITY:
        roles[role] = existing_roles.get(role) or choose_model_for_role(models, role)
    return roles


def list_nvidia_models(base_url, api_key):
    response = requests.get(
        f"{base_url.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    raw_models = data.get("data") if isinstance(data, dict) else []
    return normalize_models(raw_models if isinstance(raw_models, list) else [])


def extract_json_object(text):
    value = str(text or "").strip()
    if not value:
        return None

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", value, re.DOTALL | re.IGNORECASE)
    if fenced:
        value = fenced.group(1).strip()
    else:
        start = value.find("{")
        end = value.rfind("}")
        if start >= 0 and end > start:
            value = value[start : end + 1]

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def chat_completion(base_url, api_key, model, messages, temperature=0.2, max_tokens=2200):
    if not model:
        raise ValueError("Falta modelo NVIDIA.")

    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") if isinstance(data, dict) else []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return message.get("content") or ""
