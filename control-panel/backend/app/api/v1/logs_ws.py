import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.log_tailer import LogTailer
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

    level = websocket.query_params.get("level")
    keyword = websocket.query_params.get("keyword")
    component_id = websocket.query_params.get("component_id")
    name = websocket.query_params.get("name")

    tailer = LogTailer(
        ws=websocket,
        level=level,
        keyword=keyword,
    )

    if component_id and name:
        from app.services.log_tailer import add_file_for_component
        await add_file_for_component(
            tailer, component_id, name, token_data.username
        )
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
                new_keyword = data.get("keyword")
                if new_level is not None:
                    tailer.level = new_level
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
