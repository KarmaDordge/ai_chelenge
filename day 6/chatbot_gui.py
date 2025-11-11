"""
Веб-чат с GigaChat и Hugging Face на Flask.
"""

from __future__ import annotations

import json
import os
import re
from collections import OrderedDict
from typing import Dict, List, Tuple

import requests
import time
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from huggingface_hub import InferenceClient

# Настраиваем переменные окружения
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
PROMPTS_FILE_PATH = os.path.join(CONFIG_DIR, "preset_prompts.json")
PROMPT_NAMES_FILE_PATH = os.path.join(CONFIG_DIR, "preset_prompt_names.json")

os.makedirs(CONFIG_DIR, exist_ok=True)

DEFAULT_PRESET_PROMPTS = OrderedDict(
    {
        "no_settings": "Ты — полезный AI-ассистент. Помогай пользователю решать его задачи максимально эффективно."
    }
)

DEFAULT_PRESET_NAMES = OrderedDict(
    {
        "no_settings": "Без настроек",
    }
)

DEFAULT_PRESET_KEY = "no_settings"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_PROVIDER = "gigachat"

AVAILABLE_PROVIDERS = OrderedDict(
    {
        "gigachat": {
            "title": "GigaChat API",
            "models": OrderedDict(
                {
                    "GigaChat": {"label": "GigaChat Lite", "task": "chat", "mode": "chat-completion"},
                    "GigaChat-Pro": {"label": "GigaChat Pro", "task": "chat", "mode": "chat-completion"},
                    "GigaChat-Pro-Max": {"label": "GigaChat Pro Max", "task": "chat", "mode": "chat-completion"},
                }
            ),
        },
        "huggingface": {
            "title": "Hugging Face API",
            "models": OrderedDict(
                {
                    "deepseek-ai/DeepSeek-R1": {
                        "label": "DeepSeek R1",
                        "task": "text-generation",
                        "mode": "chat-completion",
                    },
                    "katanemo/Arch-Router-1.5B": {
                        "label": "Arch Router 1.5B",
                        "task": "text-generation",
                        "mode": "chat-completion",
                    },
                    "Sao10K/L3-8B-Stheno-v3.2": {
                        "label": "L3-8B Stheno v3.2",
                        "task": "text-generation",
                        "mode": "chat-completion",
                    },
                }
            ),
        },
    }
)
SESSION_KEY = "chat_state"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "change-me")


# ---------------------------------------------------------------------------
# Утилиты для загрузки и подготовки промптов
# ---------------------------------------------------------------------------

def _load_json_mapping(file_path: str) -> OrderedDict[str, str]:
    if not os.path.exists(file_path):
        return OrderedDict()
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                return OrderedDict(data)
    except Exception:
        pass
    return OrderedDict()


def load_raw_preset_files() -> Tuple[OrderedDict[str, str], OrderedDict[str, str]]:
    prompts = _load_json_mapping(PROMPTS_FILE_PATH)
    names = _load_json_mapping(PROMPT_NAMES_FILE_PATH)

    if not prompts:
        prompts = OrderedDict(DEFAULT_PRESET_PROMPTS)
    if not names:
        names = OrderedDict(DEFAULT_PRESET_NAMES)

    return prompts, names


def load_presets() -> OrderedDict[str, Dict[str, str]]:
    prompts, names = load_raw_preset_files()
    presets = OrderedDict()

    for key, title in names.items():
        if key in prompts:
            presets[key] = {"name": title, "prompt": prompts[key]}

    for key, prompt in prompts.items():
        if key not in presets:
            presets[key] = {"name": key, "prompt": prompt}

    if not presets:
        presets[DEFAULT_PRESET_KEY] = {
            "name": DEFAULT_PRESET_NAMES[DEFAULT_PRESET_KEY],
            "prompt": DEFAULT_PRESET_PROMPTS[DEFAULT_PRESET_KEY],
        }

    return presets


def write_presets(prompts: OrderedDict[str, str], names: OrderedDict[str, str]) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(PROMPTS_FILE_PATH, "w", encoding="utf-8") as prompts_file:
        json.dump(prompts, prompts_file, ensure_ascii=False, indent=2)
    with open(PROMPT_NAMES_FILE_PATH, "w", encoding="utf-8") as names_file:
        json.dump(names, names_file, ensure_ascii=False, indent=2)


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower()
    return slug or "preset"


def default_model_for(provider: str) -> str:
    models = AVAILABLE_PROVIDERS[provider]["models"]
    return next(iter(models))


def default_chat_state(presets: OrderedDict[str, Dict[str, str]]) -> Dict[str, object]:
    preset_key = DEFAULT_PRESET_KEY if DEFAULT_PRESET_KEY in presets else next(iter(presets))
    provider_key = DEFAULT_PROVIDER if DEFAULT_PROVIDER in AVAILABLE_PROVIDERS else next(iter(AVAILABLE_PROVIDERS))
    return {
        "preset_key": preset_key,
        "temperature": DEFAULT_TEMPERATURE,
        "provider": provider_key,
        "model": default_model_for(provider_key),
        "history": [],
    }


def parse_temperature(raw_value: str | None, fallback: float) -> float:
    if raw_value is None:
        return fallback
    try:
        temp = float(raw_value)
    except ValueError:
        return fallback
    temp = max(0.0, min(2.0, round(temp, 2)))
    return temp


# ---------------------------------------------------------------------------
# GigaChat interaction
# ---------------------------------------------------------------------------

def ask_gigachat(
    system_prompt: str,
    history: List[Dict[str, str]],
    user_message: str,
    temperature: float,
    model: str | None = None,
) -> Tuple[str, int | None, float]:
    credentials = os.getenv("GIGACHAT_CREDENTIALS")
    if not credentials:
        raise RuntimeError(
            "Не найден GIGACHAT_CREDENTIALS. "
            "Добавьте ключ авторизации в .env или переменные окружения."
        )

    if not model:
        model = default_model_for("gigachat")

    messages: List[Messages] = [
        Messages(role=MessagesRole.SYSTEM, content=system_prompt),
    ]

    for entry in history:
        role = MessagesRole.USER if entry["role"] == "user" else MessagesRole.ASSISTANT
        messages.append(Messages(role=role, content=entry["content"]))

    messages.append(Messages(role=MessagesRole.USER, content=user_message))

    chat = Chat(
        messages=messages,
        model=model,
        temperature=temperature,
        flags=["no_cache"],
    )

    with GigaChat(credentials=credentials, verify_ssl_certs=False) as client:
        start = time.perf_counter()
        response = client.chat(chat)
        elapsed = time.perf_counter() - start

    usage = getattr(response, "usage", None)
    total_tokens = None
    if usage is not None:
        total_tokens = getattr(usage, "total_tokens", None)
        if total_tokens is None:
            prompt_tokens = getattr(usage, "prompt_tokens", None)
            completion_tokens = getattr(usage, "completion_tokens", None)
            if prompt_tokens is not None and completion_tokens is not None:
                total_tokens = prompt_tokens + completion_tokens
        if total_tokens is not None:
            try:
                total_tokens = int(total_tokens)
            except (TypeError, ValueError):
                total_tokens = None

    return response.choices[0].message.content, total_tokens, elapsed


def ask_huggingface(
    system_prompt: str,
    history: List[Dict[str, str]],
    user_message: str,
    temperature: float,
    model: str,
    task: str = "text-generation",
    mode: str = "chat-completion",
) -> Tuple[str, int | None, float]:
    token = os.getenv("HUGGINGFACE_API_TOKEN")
    if not token:
        raise RuntimeError(
            "Не найден HUGGINGFACE_API_TOKEN. "
            "Добавьте ключ авторизации в .env или переменные окружения."
        )

    client = InferenceClient(token=token)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if mode == "chat-completion":
        messages = [
            {
                "role": "system",
                "content": system_prompt.strip() or "You are a helpful assistant.",
            }
        ]
        for entry in history:
            if entry["role"] == "user":
                messages.append({"role": "user", "content": entry["content"]})
            elif entry["role"] == "assistant":
                messages.append({"role": "assistant", "content": entry["content"]})
        messages.append({"role": "user", "content": user_message})

        try:
            start = time.perf_counter()
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=512,
                temperature=temperature,
            )
            elapsed = time.perf_counter() - start
        except requests.HTTPError as http_err:
            status = http_err.response.status_code if http_err.response else "?"
            detail = http_err.response.text if http_err.response else str(http_err)
            if status == 404:
                raise RuntimeError(
                    "Модель недоступна через Hugging Face Inference API. Проверьте, опубликована ли она для Inference и не приватна."
                ) from http_err
            if status == 429:
                raise RuntimeError("Превышен лимит запросов к Hugging Face Inference API.") from http_err
            raise RuntimeError(
                f"Hugging Face вернул ошибку {status}: {detail}"
            ) from http_err

        choices = getattr(completion, "choices", [])
        if not choices:
            raise RuntimeError(f"Пустой ответ от Hugging Face: {completion}")
        message = choices[0].message
        content = getattr(message, "content", "").strip()
        if not content:
            raise RuntimeError(f"Пустой ответ от Hugging Face: {completion}")
        usage = getattr(completion, "usage", None)
        total_tokens = None
        if usage is not None:
            total_tokens = getattr(usage, "total_tokens", None)
            if total_tokens is None:
                prompt_tokens = getattr(usage, "prompt_tokens", None)
                completion_tokens = getattr(usage, "completion_tokens", None)
                if prompt_tokens is not None and completion_tokens is not None:
                    total_tokens = prompt_tokens + completion_tokens
            if total_tokens is not None:
                try:
                    total_tokens = int(total_tokens)
                except (TypeError, ValueError):
                    total_tokens = None
        return content, total_tokens, elapsed

    # Fallback to text-generation endpoint
    lines = [system_prompt.strip()]
    for entry in history:
        role = "User" if entry["role"] == "user" else "Assistant"
        lines.append(f"{role}: {entry['content']}")
    lines.append(f"User: {user_message}")
    lines.append("Assistant:")
    prompt_text = "\n".join(lines)

    payload = {
        "model": model,
        "task": task,
        "inputs": prompt_text,
        "parameters": {
            "temperature": temperature,
            "max_new_tokens": 256,
            "return_full_text": True,
        },
    }

    start = time.perf_counter()
    response = requests.post(
        "https://router.huggingface.co/hf-inference/text-generation",
        headers=headers,
        params={"model": model},
        json=payload,
        timeout=60,
    )
    elapsed = time.perf_counter() - start

    if response.status_code == 404:
        raise RuntimeError(
            "Модель недоступна через Hugging Face Inference API. Проверьте, опубликована ли она для Inference и не приватна."
        )
    if response.status_code == 429:
        raise RuntimeError("Превышен лимит запросов к Hugging Face Inference API.")
    if response.status_code >= 400:
        raise RuntimeError(
            f"Hugging Face вернул ошибку {response.status_code}: {response.text}"
        )

    data = response.json()
    generated_text = ""

    if isinstance(data, list) and data:
        item = data[0]
        if isinstance(item, dict):
            generated_text = item.get("generated_text") or item.get("translation_text") or ""
        elif isinstance(item, str):
            generated_text = item
    elif isinstance(data, dict):
        generated_text = data.get("generated_text") or data.get("translation_text") or ""

    if not generated_text:
        raise RuntimeError(f"Пустой ответ от Hugging Face: {data}")

    if generated_text.startswith(prompt_text):
        generated_text = generated_text[len(prompt_text):]

    return generated_text.strip() or "Не удалось получить содержательный ответ от модели Hugging Face.", None, elapsed


# ---------------------------------------------------------------------------
# Flask views
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET", "POST"])
def index():
    presets = load_presets()
    state = session.get(SESSION_KEY)

    if (
        not state
        or state.get("preset_key") not in presets
        or state.get("provider") not in AVAILABLE_PROVIDERS
        or state.get("model") not in AVAILABLE_PROVIDERS.get(state.get("provider", ""), {}).get("models", {})
    ):
        state = default_chat_state(presets)
    else:
        state.pop("custom_prompt", None)

    if request.method == "POST":
        action = request.form.get("action", "send")
        preset_key = request.form.get("preset") or state["preset_key"]
        if preset_key not in presets:
            preset_key = next(iter(presets))

        temperature = parse_temperature(
            request.form.get("temperature"),
            state.get("temperature", DEFAULT_TEMPERATURE),
        )
        provider = request.form.get("provider") or state.get("provider", DEFAULT_PROVIDER)
        if provider not in AVAILABLE_PROVIDERS:
            provider = DEFAULT_PROVIDER

        provider_models = AVAILABLE_PROVIDERS[provider]["models"]
        model = request.form.get("model") or state.get("model")
        if model not in provider_models:
            model = default_model_for(provider)

        if action == "save_preset":
            preset_title = request.form.get("preset_title", "").strip()
            preset_prompt_text = request.form.get("preset_prompt", "").strip()

            if not preset_title:
                flash("Укажите название предустановки.", "warning")
            elif not preset_prompt_text:
                flash("Введите текст промпта для сохранения.", "warning")
            else:
                raw_prompts, raw_names = load_raw_preset_files()
                base_slug = slugify(preset_title)
                slug = base_slug
                counter = 2
                while slug in raw_prompts or slug in raw_names:
                    slug = f"{base_slug}-{counter}"
                    counter += 1

                raw_prompts[slug] = preset_prompt_text
                raw_names[slug] = preset_title
                write_presets(raw_prompts, raw_names)

                presets = load_presets()
                state = {
                    "preset_key": slug,
                    "temperature": temperature,
                    "provider": provider,
                    "model": model,
                    "history": [],
                }
                session[SESSION_KEY] = state
                session.modified = True
                flash("Предустановка сохранена.", "info")
                return redirect(url_for("index"))

            # В случае ошибок выдаём flash и продолжаем с обновленными параметрами
            state.update(
                {
                    "preset_key": preset_key,
                    "temperature": temperature,
                    "provider": provider,
                    "model": model,
                }
            )
            session[SESSION_KEY] = state
            session.modified = True
            return redirect(url_for("index"))

        if action == "reset":
            state = {
                "preset_key": preset_key,
                "temperature": temperature,
                "provider": provider,
                "model": model,
                "history": [],
            }
            session[SESSION_KEY] = state
            session.modified = True
            flash("Диалог сброшен.", "info")
            return redirect(url_for("index"))

        message = request.form.get("message", "").strip()
        if not message:
            flash("Введите сообщение перед отправкой.", "warning")
            state.update(
                {
                    "preset_key": preset_key,
                    "temperature": temperature,
                    "provider": provider,
                    "model": model,
                }
            )
            session[SESSION_KEY] = state
            session.modified = True
            return redirect(url_for("index"))

        settings_changed = (
            state["preset_key"] != preset_key
            or state.get("provider", DEFAULT_PROVIDER) != provider
            or abs(state.get("temperature", DEFAULT_TEMPERATURE) - temperature) > 1e-6
            or state.get("model") != model
        )

        if settings_changed:
            state = {
                "preset_key": preset_key,
                "temperature": temperature,
                "provider": provider,
                "model": model,
                "history": [],
            }
        else:
            state.update(
                {
                    "preset_key": preset_key,
                    "temperature": temperature,
                    "provider": provider,
                    "model": model,
                }
            )

        system_prompt = presets[preset_key]["prompt"]

        try:
            if provider == "gigachat":
                assistant_text, total_tokens, elapsed = ask_gigachat(
                    system_prompt=system_prompt,
                    history=state["history"],
                    user_message=message,
                    temperature=temperature,
                    model=model,
                )
            else:
                model_meta = AVAILABLE_PROVIDERS[provider]["models"].get(model, {})
                task = model_meta.get("task", "text-generation")
                mode = model_meta.get("mode", "text-generation")
                assistant_text, total_tokens, elapsed = ask_huggingface(
                    system_prompt=system_prompt,
                    history=state["history"],
                    user_message=message,
                    temperature=temperature,
                    model=model,
                    task=task,
                    mode=mode,
                )
        except Exception as exc:  # noqa: BLE001
            flash(f"Не удалось получить ответ: {exc}", "error")
            session[SESSION_KEY] = state
            session.modified = True
            return redirect(url_for("index"))

        state["history"].append({"role": "user", "content": message})
        meta = {
            "provider": provider,
            "model": model,
            "elapsed": elapsed,
            "tokens": total_tokens,
        }
        state["history"].append({"role": "assistant", "content": assistant_text, "meta": meta})

        session[SESSION_KEY] = state
        session.modified = True

        return redirect(url_for("index"))

    session[SESSION_KEY] = state
    session.modified = True
    return render_template(
        "index.html",
        presets=presets,
        providers=AVAILABLE_PROVIDERS,
        state=state,
        history=state["history"],
        models=AVAILABLE_PROVIDERS[state["provider"]]["models"],
    )


def create_app() -> Flask:
    return app


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5050)), debug=os.getenv("FLASK_DEBUG") == "1")

