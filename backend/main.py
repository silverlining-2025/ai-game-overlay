"""AI Game Overlay — Backend entry point.

Starts the capture loop, CV processing pipeline, and WebSocket server.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import time
import threading

from backend.capture import create_capture
from backend.config import CAPTURE_FPS, DIFF_THRESHOLD, GAMES, ROI
from backend.processors import MinesweeperProcessor
from backend.solver.minesweeper import MinesweeperSolver
from backend.state import GameState
from backend.server import OverlayServer

logger = logging.getLogger("overlay")

# --- Processor registry ---
PROCESSORS = {
    "minesweeper": lambda: MinesweeperProcessor(GAMES["minesweeper"]),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Game Overlay Backend")
    parser.add_argument(
        "--game", choices=list(PROCESSORS.keys()), default="minesweeper",
        help="Target game (default: minesweeper)",
    )
    parser.add_argument("--fps", type=int, default=CAPTURE_FPS, help="Capture FPS")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


class Pipeline:
    """Main capture → process → broadcast pipeline."""

    def __init__(
        self,
        game: str,
        fps: int,
        server: OverlayServer,
    ) -> None:
        self.game = game
        self.interval = 1.0 / fps
        self.server = server
        self.capture = create_capture()
        self.processor = PROCESSORS[game]()
        self.solver = MinesweeperSolver() if game == "minesweeper" else None
        self.state = GameState(game)
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Start the capture loop in a background thread."""
        self._running = True
        self._loop = loop
        thread = threading.Thread(target=self._run, daemon=True, name="capture-loop")
        thread.start()
        logger.info("Capture loop started (%s, %.1f FPS)", self.game, 1.0 / self.interval)

    def stop(self) -> None:
        self._running = False
        self.capture.release()
        logger.info("Capture loop stopped")

    def _run(self) -> None:
        """Capture loop running in a background thread."""
        while self._running:
            t0 = time.perf_counter()

            frame = self.capture.grab()
            if frame is None:
                time.sleep(self.interval)
                continue

            capture_ms = (time.perf_counter() - t0) * 1000

            # Frame differencing gate
            if not self.capture.has_changed(frame, DIFF_THRESHOLD):
                time.sleep(self.interval)
                continue

            t1 = time.perf_counter()
            result = self.processor.process(frame)
            processing_ms = (time.perf_counter() - t1) * 1000

            # Update state and broadcast if changed
            if self.state.update(result):
                msg = self.state.to_message()

                # Run solver if applicable
                if self.solver and result.get("grid") and result["grid"].get("cells"):
                    solver_result = self.solver.solve(result["grid"]["cells"])
                    if solver_result.safe_cells or solver_result.mine_cells:
                        suggestion = {
                            "type": "suggestion",
                            "ts": int(time.time() * 1000),
                            "game": self.game,
                            "data": {
                                "safe_cells": solver_result.safe_cells,
                                "mine_cells": solver_result.mine_cells,
                                "confidence": solver_result.confidence,
                                "reasoning": self._format_reasoning(solver_result),
                            },
                        }
                        self._schedule(self.server.send_suggestion(suggestion))

                self._schedule(self.server.send_state(msg))

            # Periodic status broadcast
            fps = 1000.0 / max(capture_ms + processing_ms, 1)
            self._schedule(self.server.send_status(fps, processing_ms, capture_ms))

            # Sleep to maintain target FPS
            elapsed = time.perf_counter() - t0
            sleep_time = self.interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _schedule(self, coro) -> None:
        """Schedule a coroutine on the asyncio event loop from the capture thread."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _format_reasoning(self, result) -> str:
        """Format solver result as Korean reasoning text."""
        parts = []
        if result.safe_cells:
            cells = ", ".join(f"({r},{c})" for r, c in result.safe_cells[:5])
            parts.append(f"안전한 셀: {cells}")
        if result.mine_cells:
            cells = ", ".join(f"({r},{c})" for r, c in result.mine_cells[:5])
            parts.append(f"지뢰 셀: {cells}")
        return " | ".join(parts) if parts else "분석 중..."

    def handle_config(self, data: dict) -> None:
        """Handle config update from frontend."""
        if "capture_fps" in data:
            self.interval = 1.0 / data["capture_fps"]
            logger.info("FPS updated to %d", data["capture_fps"])

    def handle_set_region(self, data: dict) -> None:
        """Handle ROI update from frontend."""
        roi = ROI(x=data["x"], y=data["y"], w=data["w"], h=data["h"])
        if hasattr(self.processor, "set_grid_roi"):
            self.processor.set_grid_roi(roi)
            logger.info("Grid ROI updated: %s", roi)


async def main() -> None:
    args = parse_args()
    setup_logging(args.debug)

    logger.info("=== AI Game Overlay Backend ===")
    logger.info("Game: %s | FPS: %d", args.game, args.fps)

    server = OverlayServer()
    pipeline = Pipeline(game=args.game, fps=args.fps, server=server)

    server.on_config(pipeline.handle_config)
    server.on_set_region(pipeline.handle_set_region)

    loop = asyncio.get_running_loop()
    pipeline.start(loop)

    # Graceful shutdown
    def shutdown():
        pipeline.stop()
        logger.info("Shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, lambda *_: shutdown())

    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
