import json
from datetime import datetime

from ai_handler import get_ai_make, get_ai_model


def _make_model_for(ai_key: str):
    """Resolve *ai_key* (an agent name OR a raw make) to ``(make, model)``.

    ``get_ai_make`` / ``get_ai_model`` alias-resolve, so this works for
    self-named agents (``anthropic``), multi-model agents (``anthropic-opus``),
    and keyless agents whose name differs from the make (``ollama-qwen`` →
    ``ollama`` / ``qwen2.5:0.5b``).  The old ``AI_HANDLER_REGISTRY.get(ai_key)``
    lookup only worked when the agent name happened to equal the make.
    """
    return get_ai_make(ai_key), get_ai_model(ai_key)


def get_speaking_tagline(make, model):
    today_date = datetime.today().strftime('%B %-d, %Y')  # On Mac and Linux, %#d on windows
    tagline = (f"This has been a Cross report, produced {today_date}.  "
               f"This report was generated using AI from {make} with the model {model}. "
               f"Feedback and questions are welcome at github dot com slash b202i slash cross."
               )
    return tagline


def get_tagline_for_reading(make, model):
    return "crossai.dev:" + json.dumps({"make": make, "model": model})


def get_ai_tag(ai_key: str):
    make, model = _make_model_for(ai_key)
    return "crossai.dev:" + json.dumps({"make": make, "model": model})


def get_ai_tag_mini(ai_key: str):
    make, model = _make_model_for(ai_key)
    return f"crossai.dev:{make}:{model}"


def get_ai_make_model(ai_key: str):
    make, model = _make_model_for(ai_key)
    return f"{make}:{model}"


def get_app_tag():
    return "crossai.dev:"
