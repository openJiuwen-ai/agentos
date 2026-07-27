import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.log_tailer import LogTailer, load_components_for_tailer, add_files_for_tailer
from app.iam.tokens import TokenData

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="/api/v1")


async def validate_ws_admin(websocket: WebSocket) -> TokenData | None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="MISSING_TOKEN")
        return None

    from app.iam.tokens import TokenService

    try:
        token_data = TokenService.verify_access_token(token)
        if not token_data:
            raise ValueError("invalid token")
    except Exception:
        await websocket.close(code=4001, reason="INVALID_TOKEN")
        return None

    if token_data.role != "admin":
        await websocket.close(code=4003, reason="FORBIDDEN")
        return None

    return token_data


@ws_router.websocket("/logs/stream")
async def ws_log_stream(websocket: WebSocket):
    await websocket.accept()
    token_data = await validate_ws_admin(websocket)
    if token_data is None:
        return

    component_ids_str = websocket.query_params.get("component_ids", "")
    paths_str = websocket.query_params.get("paths", "")
    session_id = websocket.query_params.get("session_id")
    level = websocket.query_params.get("level")
    keyword = websocket.query_params.get("keyword")

    component_ids = [c.strip() for c in component_ids_str.split(",") if c.strip()]
    paths = [p.strip() for p in paths_str.split(",") if p.strip()]

    tailer = LogTailer(
        ws=websocket,
        level=level,
        session_id=session_id,
        keyword=keyword,
    )

    if component_ids:
        await load_components_for_tailer(tailer, component_ids)
    if paths:
        await add_files_for_tailer(tailer, paths)
    await tailer.start()

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            if action == "pause":
                tailer.pause()
                await websocket.send_json({"type": "control", "action": "paused"})
            elif action == "resume":
                await tailer.resume()
                await websocket.send_json({"type": "control", "action": "resumed"})
            elif action == "change_filter":
                new_level = data.get("level")
                new_session = data.get("session_id")
                new_keyword = data.get("keyword")
                if new_level is not None:
                    tailer.level = new_level
                if new_session is not None:
                    tailer.session_id = new_session
                if new_keyword is not None:
                    tailer.keyword = new_keyword
                tailer.rebuild_filters()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("WS log stream receive error: %s", e)
        pass
    finally:
        await tailer.stop()
