"""
Internationalisation (i18n) module for RDT.

Language resolution order (highest priority first):
  1. RDT_LANG environment variable
  2. ~/.rdt/config.json  →  {"lang": "<code>"}
  3. Built-in default: "ru"

Usage:
    from rdt.i18n import t
    print(t("msg.service_added", name="postgres", file="docker-compose.yml"))

Adding a new locale:
    Drop a  rdt/locales/<code>.json  file with the same keys as ru.json.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_LOCALES_DIR = Path(__file__).parent / "locales"
_CONFIG_FILE = Path.home() / ".rdt" / "config.json"
_DEFAULT_LANG = "en"

_translations: dict[str, str] = {}
_fallback_translations: dict[str, str] = {}
_current_lang: str = _DEFAULT_LANG
_initialized: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_lang(lang: str) -> dict[str, str]:
    """Load a locale JSON file. Returns empty dict if not found."""
    locale_file = _LOCALES_DIR / f"{lang}.json"
    if not locale_file.exists():
        return {}
    try:
        with locale_file.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _get_configured_lang() -> str:
    """Determine the active language from env / config file / default."""
    # 1. Environment variable takes priority
    env_lang = os.environ.get("RDT_LANG", "").strip().lower()
    if env_lang:
        return env_lang

    # 2. Persistent config file
    if _CONFIG_FILE.exists():
        try:
            cfg = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            lang = cfg.get("lang", "").strip().lower()
            if lang:
                return lang
        except Exception:
            pass

    return _DEFAULT_LANG


def _ensure_init() -> None:
    global _initialized
    if not _initialized:
        init()


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def init() -> None:
    """Initialise (or reinitialise) the translation engine."""
    global _translations, _fallback_translations, _current_lang, _initialized
    _current_lang = _get_configured_lang()
    _translations = _load_lang(_current_lang)
    # Always keep the default locale as a fallback for missing keys
    if _current_lang != _DEFAULT_LANG:
        _fallback_translations = _load_lang(_DEFAULT_LANG)
    else:
        _fallback_translations = {}
    _initialized = True


def reload() -> None:
    """Reload translations after a language change (in-session switch)."""
    global _initialized
    _initialized = False
    init()


def t(key: str, **kwargs: object) -> str:
    """Return the translated string for *key*, interpolating **kwargs."""
    _ensure_init()
    text = _translations.get(key) or _fallback_translations.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


def current_lang() -> str:
    """Return the active language code."""
    _ensure_init()
    return _current_lang


def available_langs() -> list[str]:
    """Return list of available language codes (detected from locale files)."""
    return sorted(f.stem for f in _LOCALES_DIR.glob("*.json"))


def set_lang(lang: str) -> bool:
    """
    Persist *lang* to ~/.rdt/config.json.
    Returns True on success, False if the locale file does not exist.
    """
    locale_file = _LOCALES_DIR / f"{lang}.json"
    if not locale_file.exists():
        return False

    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    cfg: dict = {}
    if _CONFIG_FILE.exists():
        try:
            cfg = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    cfg["lang"] = lang
    _CONFIG_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return True

