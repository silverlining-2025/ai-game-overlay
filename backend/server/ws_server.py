"""WebSocket server for backend ↔ frontend communication."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol

from backend.config import WS_HOST, WS_PORT

logger = logging.getLogger(__name__)


class OverlayServer:
    """WebSocket server that broadcasts game state to connected overlay clients."""

    def __init__(self, host: str = WS_HOST, port: int = WS_PORT) -> None:
        self.host = host
        self.port = port
        self.clients: set[WebSocketServerProtocol] = set()
        self._config_callback: Any = None
        self._region_callback: Any = None
        self._suggestion_callback: Any = None

    def on_config(self, callback: Any) -> None:
        """Register handler for config messages from frontend."""
        self._config_callback = callback

    def on_set_region(self, callback: Any) -> None:
        """Register handler for set_region messages from frontend."""
        self._region_callback = callback

    def on_request_suggestion(self, callback: Any) -> None:
        """Register handler for request_suggestion messages from frontend."""
        self._suggestion_callback = callback

    async def broadcast(self, message: dict) -> None:
        """Send a message to all connected clients."""
        if not self.clients:
            return
        data = json.dumps(message)
        disconnected = set()
        for client in self.clients:
            try:
                await client.send(data)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
        self.clients -= disconnected

    async def send_state(self, state_message: dict) -> None:
        """Broadcast a state_update message."""
        await self.broadcast(state_message)

    async def send_suggestion(self, suggestion: dict) -> None:
        """Broadcast an AI suggestion."""
        await self.broadcast(suggestion)

    async def send_status(self, fps: float, processing_ms: float, capture_ms: float) -> None:
        """Broadcast performance status."""
        import time
        await self.broadcast({
            "type": "status",
            "ts": int(time.time() * 1000),
            "data": {
                "fps": round(fps, 1),
                "processing_ms": round(processing_ms, 1),
                "capture_ms": round(capture_ms, 1),
            },
        })

    async def _handle_client(self, websocket: WebSocketServerProtocol) -> None:
        """Handle a single client connection."""
        self.clients.add(websocket)
        remote = websocket.remote_address
        logger.info("Client connected: %s", remote)

        try:
            async for raw in websocket:
                try:
                    message = json.loads(raw)
                    msg_type = message.get("type")
                    data = message.get("data", {})

                    if msg_type == "config" and self._config_callback:
                        self._config_callback(data)
                    elif msg_type == "set_region" and self._region_callback:
                        self._region_callback(data)
                    elif msg_type == "request_suggestion" and self._suggestion_callback:
                        self._suggestion_callback(data)
                    else:
                        logger.warning("Unknown message type: %s", msg_type)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from client: %s", raw[:100])
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.discard(websocket)
            logger.info("Client disconnected: %s", remote)

    async def start(self) -> None:
        """Start the WebSocket server."""
        logger.info("WebSocket server starting on ws://%s:%d", self.host, self.port)
        async with websockets.serve(self._handle_client, self.host, self.port):
            await asyncio.Future()  # run forever
