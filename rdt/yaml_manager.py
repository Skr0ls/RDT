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
    """Сохранить docker-compose.yml."""
    y = _make_yaml()
    with path.open("w", encoding="utf-8") as f:
        y.dump(data, f)


def make_base_compose() -> CommentedMap:
    """Создать базовую структуру docker-compose.yml."""
    data = CommentedMap()
    data["services"] = CommentedMap()
    data["networks"] = CommentedMap()
    data["networks"][NETWORK_NAME] = CommentedMap({"driver": "bridge"})
    data["volumes"] = CommentedMap()
    return data


def inject_service(data: CommentedMap, service_name: str, service_def: dict[str, Any]) -> CommentedMap:
    """Вставить новый сервис в секцию services без нарушения структуры."""
    if "services" not in data:
        data["services"] = CommentedMap()
    if "networks" not in data:
        data["networks"] = CommentedMap()
        data["networks"][NETWORK_NAME] = CommentedMap({"driver": "bridge"})
    if "volumes" not in data:
        data["volumes"] = CommentedMap()

    # Убедимся, что сеть объявлена
    if NETWORK_NAME not in data["networks"]:
        data["networks"][NETWORK_NAME] = CommentedMap({"driver": "bridge"})

    # Конвертируем в CommentedMap для сохранения порядка
    svc_map = _dict_to_commented(service_def)
    data["services"][service_name] = svc_map

    # Регистрируем named volumes
    for vol in service_def.get("volumes", []):
        vol_str = str(vol)
        if ":" in vol_str:
            source = vol_str.split(":")[0]
            # Именованный volume — не начинается с . или /
            if not source.startswith(".") and not source.startswith("/"):
                if source not in data["volumes"]:
                    data["volumes"][source] = None  # type: ignore[assignment]

    return data


def get_existing_services(data: CommentedMap) -> list[str]:
    """Вернуть список имён сервисов из docker-compose."""
    return list(data.get("services", {}).keys())


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

