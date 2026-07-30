import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from app.config import settings

_FILE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="log-io")


def shutdown_file_executor():
    _FILE_EXECUTOR.shutdown(wait=True)


async def read_last_lines(
    file_path: str,
    n: int = 50,
) -> list[str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _FILE_EXECUTOR, _read_last_lines_sync, file_path, n
    )


def _read_last_lines_sync(file_path: str, n: int) -> list[str]:
    if not os.path.exists(file_path):
        return []

    try:
        with open(file_path, "rt", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return []

    lines = [_truncate_line(line) for line in lines[-n:]]
    return lines


async def read_new_lines(
    file_path: str,
    position: int,
) -> tuple[list[str], int]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _FILE_EXECUTOR, _read_new_lines_sync, file_path, position
    )


def _read_new_lines_sync(
    file_path: str, position: int
) -> tuple[list[str], int]:
    if not os.path.exists(file_path):
        return [], position

    try:
        with open(file_path, "rt", encoding="utf-8", errors="replace") as f:
            f.seek(position, os.SEEK_SET)
            lines = f.readlines()
            new_position = f.tell()
    except Exception:
        return [], position

    lines = [_truncate_line(line) for line in lines]
    return lines, new_position


def _truncate_line(line: str) -> str:
    if len(line) > settings.LOG_MAX_LINE_LENGTH:
        return line[: settings.LOG_MAX_LINE_LENGTH] + "\n"
    return line


def create_filter(
    level: str | None = None,
    keyword: str | None = None,
):
    def filter_line(line: str) -> dict | None:
        stripped = line.rstrip("\n\r")

        if level and level.upper() not in stripped.upper():
            return None

        if keyword and keyword not in stripped:
            return None

        return {"raw": stripped}

    return filter_line
