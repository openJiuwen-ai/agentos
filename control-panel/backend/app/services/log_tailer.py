import asyncio
import os
import uuid
from dataclasses import dataclass, field

from fastapi import WebSocket
from sqlalchemy import select
from watchfiles import awatch, Change

from app.config import settings
from app.models.log import LogComponent
from app.services.log_reader import create_filter, read_last_lines, read_new_lines


@dataclass
class TailerConfig:
    component_name: str
    file_path: str


@dataclass
class TailerState:
    config: TailerConfig
    position: int = 0
    inode: int | None = None
    paused: bool = False
    buffer: list[dict] = field(default_factory=list)
    filter_fn = None


class LogTailer:
    MAX_FILES_PER_WS = settings.LOG_MAX_FILES_PER_WS
    INITIAL_TAIL_LINES = settings.LOG_INITIAL_TAIL_LINES

    def __init__(
        self,
        ws: WebSocket,
        level: str | None = None,
        session_id: str | None = None,
        keyword: str | None = None,
    ):
        self.ws = ws
        self.level = level
        self.session_id = session_id
        self.keyword = keyword
        self.states: list[TailerState] = []
        self._watch_task: asyncio.Task | None = None
        self._running = False

    async def add_file(
        self,
        component_name: str,
        file_path: str,
    ) -> int:
        if len(self.states) >= self.MAX_FILES_PER_WS:
            return 0

        if not os.path.isfile(file_path):
            return 0

        config = TailerConfig(
            component_name=component_name,
            file_path=file_path,
        )
        self.states.append(TailerState(config=config))
        return 1

    async def start(self) -> None:
        self._running = True
        self.rebuild_filters()

        for state in self.states:
            lines = await read_last_lines(
                state.config.file_path, self.INITIAL_TAIL_LINES
            )
            filtered = self._apply_filter(state, lines)
            if filtered:
                await self._push_lines(state.config.component_name, filtered, "init")
            try:
                state.position = os.path.getsize(state.config.file_path)
            except OSError:
                pass

        self._watch_task = asyncio.create_task(self._watch_inotify())

    def rebuild_filters(self) -> None:
        for state in self.states:
            state.filter_fn = create_filter(
                level=self.level,
                session_id=self.session_id,
                keyword=self.keyword,
            )

    @staticmethod
    def _apply_filter(state: TailerState, lines: list[str]) -> list[dict]:
        if state.filter_fn is None:
            return [{"raw": line.rstrip("\n\r")} for line in lines]
        result = []
        for line in lines:
            parsed = state.filter_fn(line)
            if parsed is not None:
                result.append(parsed)
        return result

    async def stop(self) -> None:
        self._running = False
        if self._watch_task and not self._watch_task.done():
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass

    def pause(self) -> None:
        for state in self.states:
            state.paused = True

    async def resume(self) -> None:
        for state in self.states:
            state.paused = False
            if state.buffer:
                await self._push_lines(state.config.component_name, state.buffer, "new_line")
                state.buffer.clear()

    async def _watch_inotify(self) -> None:
        path_to_state: dict[str, TailerState] = {}

        while self._running:
            path_to_state = {s.config.file_path: s for s in self.states}
            paths = list(path_to_state.keys())

            if not paths:
                await asyncio.sleep(0.5)
                continue

            try:
                async for changes in awatch(*paths, debounce=200, recursive=False):
                    if not self._running:
                        return
                    for change, path in changes:
                        if change != Change.modified:
                            continue
                        state = path_to_state.get(path)
                        if not state or state.paused:
                            continue
                        try:
                            cur_ino = os.stat(path).st_ino
                            if state.inode is not None and cur_ino != state.inode:
                                state.position = 0
                            state.inode = cur_ino
                        except OSError:
                            continue
                        await self._read_and_push(state)
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                if self._running:
                    await asyncio.sleep(1)

    async def _read_and_push(self, state: TailerState) -> None:
        new_lines, new_pos = await read_new_lines(
            state.config.file_path, state.position
        )
        state.position = new_pos
        if not new_lines:
            return

        filtered = self._apply_filter(state, new_lines)
        if not filtered:
            return

        if state.paused:
            state.buffer.extend(filtered)
        else:
            await self._push_lines(state.config.component_name, filtered, "new_line")

    async def _push_lines(
        self, component: str, lines: list[dict], msg_type: str
    ) -> None:
        try:
            await self.ws.send_json(
                {"type": msg_type, "component": component, "lines": lines}
            )
        except Exception:
            self._running = False


async def load_components_for_tailer(
    tailer: LogTailer, component_ids: list[str],
) -> None:
    import app.database as _db
    async with _db.async_session_maker() as session:
        for cid in component_ids:
            try:
                component_uuid = uuid.UUID(cid)
            except ValueError:
                continue
            result = await session.execute(
                select(LogComponent).where(
                    LogComponent.id == component_uuid
                )
            )
            component = result.scalars().first()
            if component:
                await tailer.add_file(
                    component_name=component.name,
                    file_path=component.log_path,
                )


async def add_files_for_tailer(
    tailer: LogTailer, paths: list[str],
) -> None:
    log_dir = os.path.realpath(settings.LOG_DIR)
    for path in paths:
        if not os.path.isabs(path):
            continue
        safe_path = os.path.realpath(path)
        if not safe_path.startswith(log_dir + os.sep) and safe_path != log_dir:
            continue
        if os.path.isfile(safe_path):
            name = os.path.basename(safe_path)
            await tailer.add_file(
                component_name=name,
                file_path=safe_path,
            )
