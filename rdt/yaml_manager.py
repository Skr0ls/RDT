"""
Read and write docker-compose.yml through ruamel.yaml.
Preserves comments, key order, and formatting.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from rdt.strategies.base import NETWORK_NAME

DEFAULT_COMPOSE_FILE = "docker-compose.yml"
COMMON_COMPOSE_FILENAMES = (
    "compose.yml",
    "compose.yaml",
    "docker-compose.yaml",
    DEFAULT_COMPOSE_FILE,
)

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


def find_existing_compose_file(project_dir: Path | None = None) -> Path | None:
    """Return the first existing Compose file matching common naming conventions."""
    base = project_dir or Path.cwd()
    for filename in COMMON_COMPOSE_FILENAMES:
        candidate = base / filename
        if candidate.is_file():
            return candidate
    return None


def resolve_default_compose_file(file: Path) -> Path:
    """Resolve the default compose path to an existing common Compose filename."""
    if file.exists() or file.name != DEFAULT_COMPOSE_FILE:
        return file
    return find_existing_compose_file(file.parent) or file


def load_compose(path: Path) -> CommentedMap:
    """Load docker-compose.yml; return an empty structure when the file is missing."""
    y = _make_yaml()
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = y.load(f)
        if data is None:
            data = CommentedMap()
        return data
    return CommentedMap()


def save_compose(path: Path, data: CommentedMap) -> None:
    """Save docker-compose.yml and create the parent directory when needed."""
    import re
    import io
    # Ensure the parent directory exists for --file infra/docker-compose.yml.
    path.parent.mkdir(parents=True, exist_ok=True)
    _normalize_healthcheck_test_flow_style(data)
    y = _make_yaml()
    buf = io.StringIO()
    y.dump(data, buf)
    # Normalize accumulated blank lines: ≥3 newlines → exactly 2 (= one blank line).
    content = re.sub(r'\n{3,}', '\n\n', buf.getvalue())
    with path.open("w", encoding="utf-8") as f:
        f.write(content)


def make_base_compose(network_config: dict | None = None) -> CommentedMap:
    """Create the base docker-compose.yml structure.

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
    """Insert a new service into the services section without breaking structure.

    network_config: {"type": "bridge"|"external"|"host"|"none", "name": str}
    """
    if "services" not in data:
        data["services"] = CommentedMap()
    if "volumes" not in data:
        data["volumes"] = CommentedMap()

    net_type = (network_config or {}).get("type", "bridge")
    net_name = (network_config or {}).get("name", NETWORK_NAME)

    # Manage the networks section depending on the network type.
    if net_type in ("bridge", "external"):
        if "networks" not in data:
            data["networks"] = CommentedMap()
        if net_name not in data["networks"]:
            if net_type == "bridge":
                data["networks"][net_name] = CommentedMap({"driver": "bridge"})
            else:
                data["networks"][net_name] = CommentedMap({"external": True})
    # host / none do not need a networks section for this network.

    # Convert to CommentedMap to preserve order.
    svc_map = _dict_to_commented(service_def)
    data["services"][service_name] = svc_map

    # Add a blank line before each service except the first.
    if len(data["services"]) > 1:
        data["services"].yaml_set_comment_before_after_key(service_name, before="\n")

    # Register named volumes.
    for vol in service_def.get("volumes", []):
        vol_str = str(vol)
        if ":" in vol_str:
            source = vol_str.split(":")[0]
            # Named volumes do not start with . or /.
            if not source.startswith(".") and not source.startswith("/"):
                if source not in data["volumes"]:
                    data["volumes"][source] = None  # type: ignore[assignment]

    # Blank line before top-level networks and volumes.
    _ensure_section_spacing(data)

    return data


def _ensure_section_spacing(data: CommentedMap) -> None:
    """Ensure a blank line before top-level networks and volumes."""
    for key in ("networks", "volumes"):
        if key in data:
            data.yaml_set_comment_before_after_key(key, before="\n")


def get_existing_services(data: CommentedMap) -> list[str]:
    """Return service names from docker-compose."""
    return list(data.get("services", {}).keys())


def get_dependents(data: CommentedMap, service_name: str) -> list[str]:
    """Return services that depend on service_name through depends_on."""
    result: list[str] = []
    for svc_name, svc_def in (data.get("services") or {}).items():
        if svc_name == service_name:
            continue
        depends = (svc_def or {}).get("depends_on", [])
        if isinstance(depends, dict):
            depends = list(depends.keys())
        if service_name in (depends or []):
            result.append(svc_name)
    return result


def get_service_named_volumes(data: CommentedMap, service_name: str) -> set[str]:
    """Return named volumes, not bind mounts, used by the specified service."""
    result: set[str] = set()
    svc_def = (data.get("services") or {}).get(service_name) or {}
    for vol in svc_def.get("volumes", []):
        vol_str = str(vol)
        if ":" in vol_str:
            source = vol_str.split(":")[0]
            if not source.startswith(".") and not source.startswith("/"):
                result.add(source)
    return result


def remove_service(data: CommentedMap, service_name: str) -> tuple[CommentedMap, list[str]]:
    """Remove a service from compose data.

    Returns updated data and a list of removed named volumes.
    A named volume is removed only when no other service uses it.
    """
    if "services" not in data or service_name not in data["services"]:
        return data, []

    # Remember named volumes used by the removed service.
    service_volumes = get_service_named_volumes(data, service_name)

    # Remove the service.
    del data["services"][service_name]

    # Find volumes that are still used by remaining services.
    still_used: set[str] = set()
    for _, svc_def in (data.get("services") or {}).items():
        for vol in (svc_def or {}).get("volumes", []):
            vol_str = str(vol)
            if ":" in vol_str:
                source = vol_str.split(":")[0]
                if not source.startswith(".") and not source.startswith("/"):
                    still_used.add(source)

    # Remove orphaned named volumes from the volumes section.
    removed_volumes: list[str] = []
    for vol_name in service_volumes:
        if vol_name not in still_used:
            if "volumes" in data and vol_name in data["volumes"]:
                del data["volumes"][vol_name]
                removed_volumes.append(vol_name)

    return data, removed_volumes


def get_services_with_healthcheck(data: CommentedMap) -> set[str]:
    """Return service names that define a healthcheck."""
    result: set[str] = set()
    for svc_name, svc_def in (data.get("services") or {}).items():
        if svc_def and "healthcheck" in svc_def:
            result.add(svc_name)
    return result


def _normalize_healthcheck_test_flow_style(d: Any, path: tuple[str, ...] = ()) -> Any:
    """Force all healthcheck.test lists to use inline flow style."""
    if isinstance(d, dict):
        for k, v in list(d.items()):
            child_path = path + (str(k),)
            if len(child_path) >= 2 and child_path[-2:] == ("healthcheck", "test") and isinstance(v, list):
                seq = v if isinstance(v, CommentedSeq) else CommentedSeq(v)
                seq.fa.set_flow_style()
                d[k] = seq
            else:
                d[k] = _normalize_healthcheck_test_flow_style(v, child_path)
        return d
    if isinstance(d, list):
        for idx, item in enumerate(d):
            d[idx] = _normalize_healthcheck_test_flow_style(item, path)
        return d
    return d


def _dict_to_commented(d: Any, path: tuple[str, ...] = ()) -> Any:
    """Recursively convert dict → CommentedMap and list → CommentedSeq.

    healthcheck.test lists are serialized in inline flow style because
    Docker Compose expects test: ["CMD-SHELL", "..."] or ["CMD", "..."].
    """
    if isinstance(d, dict):
        cm = CommentedMap()
        for k, v in d.items():
            cm[k] = _dict_to_commented(v, path + (k,))
        return cm
    if isinstance(d, list):
        seq = CommentedSeq([_dict_to_commented(i, path) for i in d])
        if len(path) >= 2 and path[-2:] == ("healthcheck", "test"):
            seq.fa.set_flow_style()
        return seq
    return d

