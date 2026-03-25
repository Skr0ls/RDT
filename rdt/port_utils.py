"""
Утилиты проверки доступности портов на хосте.
"""
from __future__ import annotations
import socket


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    """Возвращает True, если порт свободен на хосте."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        try:
            s.connect((host, port))
            return False  # подключились — порт занят
        except (ConnectionRefusedError, OSError):
            return True   # не подключились — порт свободен


def find_free_port(start: int, max_tries: int = 20) -> int | None:
    """Найти ближайший свободный порт начиная с start."""
    for port in range(start, start + max_tries):
        if is_port_free(port):
            return port
    return None


def validate_port(port_str: str) -> tuple[bool, str]:
    """Валидация строки с номером порта."""
    try:
        port = int(port_str)
    except ValueError:
        return False, "Порт должен быть числом"
    if not (1 <= port <= 65535):
        return False, "Порт должен быть в диапазоне 1–65535"
    if not is_port_free(port):
        return False, f"Порт {port} уже занят"
    return True, ""

