from fastapi import WebSocket, WebSocketDisconnect

from core.state import clients, latest_state
from services.logger import push_log


def register_websocket(app) -> None:
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        clients.add(ws)
        push_log(latest_state, "WebSocket: browser connected")

        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            clients.discard(ws)
            push_log(latest_state, "WebSocket: browser disconnected")
