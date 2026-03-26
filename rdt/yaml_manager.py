"""
Чтение и запись docker-compose.yml через ruamel.yaml
(сохраняет комментарии, порядок ключей, форматирование).
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from rdt.strategies.base import NETWORK_NAME

_yaml = YAML()
_yaml.default_flow_style = False
_yaml.best_sequence_indent = 2
_yaml.best_map_flow_style = False
_yaml.width = 120


def _make_yaml() -> YAML:
    y = YAML()
    y.default_flow_style = False
    y.best_sequence_indent = 2
    y.width = 120
    return y


def load_compose(path: Path) -> CommentedMap:
    """Загрузить docker-compose.yml; вернуть пустую структуру если файла нет."""
    y = _make_yaml()
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = y.load(f)
        if data is None:
            data = CommentedMap()
        return data
    return CommentedMap()


def save_compose(path: Path, data: CommentedMap) -> None:
    """Сохранить docker-compose.yml. Создаёт родительскую директорию при необходимости."""
    import re
    import io
    # Гарантировать существование родительской директории (для --file infra/docker-compose.yml)
    path.parent.mkdir(parents=True, exist_ok=True)
    y = _make_yaml()
    buf = io.StringIO()
    y.dump(data, buf)
    # Нормализуем накопившиеся пустые строки: ≥3 переноса → ровно 2 (= 1 пустая строка)
    content = re.sub(r'\n{3,}', '\n\n', buf.getvalue())
    with path.open("w", encoding="utf-8") as f:
        f.write(content)


def make_base_compose(network_config: dict | None = None) -> CommentedMap:
    """Создать базовую структуру docker-compose.yml.

    network_config: {"type": "bridge"|"external"|"host"|"none", "name": str}
    """
    data = CommentedMap()
    data["services"] = CommentedMap()

    net_type = (network_config or {}).get("type", "bridge")
    net_name = (network_config or {}).get("name", NETWORK_NAME)

    if net_type in ("bridge", "external"):
        data["networks"] = CommentedMap()
        if net_type == "bridge":
            data["networks"][net_name] = CommentedMap({"driver": "bridge"})
        else:
            data["networks"][net_name] = CommentedMap({"external": True})

    data["volumes"] = CommentedMap()
    return data


def inject_service(
    data: CommentedMap,
    service_name: str,
    service_def: dict[str, Any],
    network_config: dict | None = None,
) -> CommentedMap:
    """Вставить новый сервис в секцию services без нарушения структуры.

    network_config: {"type": "bridge"|"external"|"host"|"none", "name": str}
    """
    if "services" not in data:
        data["services"] = CommentedMap()
    if "volumes" not in data:
        data["volumes"] = CommentedMap()

    net_type = (network_config or {}).get("type", "bridge")
    net_name = (network_config or {}).get("name", NETWORK_NAME)

    # Управление секцией networks в зависимости от типа
    if net_type in ("bridge", "external"):
        if "networks" not in data:
            data["networks"] = CommentedMap()
        if net_name not in data["networks"]:
            if net_type == "bridge":
                data["networks"][net_name] = CommentedMap({"driver": "bridge"})
            else:
                data["networks"][net_name] = CommentedMap({"external": True})
    # host / none — секция networks для этой сети не нужна

    # Конвертируем в CommentedMap для сохранения порядка
    svc_map = _dict_to_commented(service_def)
    data["services"][service_name] = svc_map

    # Пустая строка перед каждым сервисом кроме первого
    if len(data["services"]) > 1:
        data["services"].yaml_set_comment_before_after_key(service_name, before="\n")

    # Регистрируем named volumes
    for vol in service_def.get("volumes", []):
        vol_str = str(vol)
        if ":" in vol_str:
            source = vol_str.split(":")[0]
            # Именованный volume — не начинается с . или /
            if not source.startswith(".") and not source.startswith("/"):
                if source not in data["volumes"]:
                    data["volumes"][source] = None  # type: ignore[assignment]

    # Пустая строка перед networks и volumes (верхний уровень)
    _ensure_section_spacing(data)

    return data


def _ensure_section_spacing(data: CommentedMap) -> None:
    """Гарантировать пустую строку перед networks и volumes на верхнем уровне."""
    for key in ("networks", "volumes"):
        if key in data:
            data.yaml_set_comment_before_after_key(key, before="\n")


def get_existing_services(data: CommentedMap) -> list[str]:
    """Вернуть список имён сервисов из docker-compose."""
    return list(data.get("services", {}).keys())


def get_services_with_healthcheck(data: CommentedMap) -> set[str]:
    """Вернуть множество имён сервисов, у которых задан healthcheck."""
    result: set[str] = set()
    for svc_name, svc_def in (data.get("services") or {}).items():
        if svc_def and "healthcheck" in svc_def:
            result.add(svc_name)
    return result


def _dict_to_commented(d: Any) -> Any:
    """Рекурсивно конвертировать dict → CommentedMap."""
    if isinstance(d, dict):
        cm = CommentedMap()
        for k, v in d.items():
            cm[k] = _dict_to_commented(v)
        return cm
    if isinstance(d, list):
        return [_dict_to_commented(i) for i in d]
    return d

