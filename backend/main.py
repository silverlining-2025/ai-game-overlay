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

import numpy as np

from backend.capture import create_capture
from backend.config import CAPTURE_FPS, DIFF_THRESHOLD, GAMES, AI, ROI
from backend.processors import MinesweeperProcessor
from backend.solver.minesweeper import MinesweeperSolver
from backend.state import GameState
from backend.server import OverlayServer
from backend.ai import MoondreamEngine

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
    parser.add_argument("--no-vlm", action="store_true", help="Disable Moondream VLM")
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
        enable_vlm: bool = True,
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

        # Tier 3: Moondream VLM (async worker thread)
        self._enable_vlm = enable_vlm
        self._vlm: MoondreamEngine | None = None
        self._vlm_interval = AI.moondream.query_interval
        self._vlm_last_query = 0.0
        self._vlm_prompt = AI.moondream.default_prompt
        self._latest_frame: np.ndarray | None = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Start the capture loop in a background thread."""
        self._running = True
        self._loop = loop

        # Start VLM worker (lazy — model loads on first query)
        if self._enable_vlm:
            cfg = AI.moondream
            self._vlm = MoondreamEngine(
                model_id=cfg.model_id,
                device=cfg.device,
                revision=cfg.revision,
            )
            self._vlm.start()
            logger.info("VLM enabled (query every %.1fs)", self._vlm_interval)

        thread = threading.Thread(target=self._run, daemon=True, name="capture-loop")
        thread.start()
        logger.info("Capture loop started (%s, %.1f FPS)", self.game, 1.0 / self.interval)

    def stop(self) -> None:
        self._running = False
        if self._vlm:
            self._vlm.stop()
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

            # Tier 3: periodic VLM query (non-blocking — runs in worker thread)
            self._latest_frame = frame
            now = time.perf_counter()
            if (
                self._vlm is not None
                and now - self._vlm_last_query >= self._vlm_interval
            ):
                self._vlm_last_query = now
                self._vlm.query(
                    frame.copy(),
                    self._vlm_prompt,
                    self._on_vlm_result,
                    request_type="query",
                )

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

    def _on_vlm_result(self, result: dict) -> None:
        """Callback from Moondream worker thread — broadcast as suggestion."""
        suggestion = {
            "type": "suggestion",
            "ts": int(time.time() * 1000),
            "game": self.game,
            "data": {
                "source": "vlm",
                "reasoning": result.get("answer", ""),
                "question": result.get("question", ""),
                "elapsed_ms": result.get("elapsed_ms", 0),
                "confidence": 1.0,
            },
        }
        self._schedule(self.server.send_suggestion(suggestion))
        logger.info(
            "VLM insight (%.0fms): %s",
            result.get("elapsed_ms", 0),
            result.get("answer", "")[:120],
        )

    def handle_request_suggestion(self, data: dict) -> None:
        """Handle on-demand VLM query from frontend (Alt+C hotkey)."""
        if self._vlm is None:
            logger.warning("VLM not enabled — ignoring suggestion request")
            return
        if self._latest_frame is None:
            logger.warning("No frame captured yet — ignoring suggestion request")
            return

        prompt = data.get("prompt", self._vlm_prompt)
        self._vlm.query(
            self._latest_frame.copy(),
            prompt,
            self._on_vlm_result,
            request_type="query",
        )
        logger.info("On-demand VLM query submitted: %s", prompt[:80])

    def handle_config(self, data: dict) -> None:
        """Handle config update from frontend."""
        if "capture_fps" in data:
            self.interval = 1.0 / data["capture_fps"]
            logger.info("FPS updated to %d", data["capture_fps"])
        if "vlm_interval" in data:
            self._vlm_interval = float(data["vlm_interval"])
            logger.info("VLM interval updated to %.1fs", self._vlm_interval)
        if "vlm_prompt" in data:
            self._vlm_prompt = data["vlm_prompt"]
            logger.info("VLM prompt updated")

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
    pipeline = Pipeline(
        game=args.game,
        fps=args.fps,
        server=server,
        enable_vlm=not args.no_vlm,
    )

    server.on_config(pipeline.handle_config)
    server.on_set_region(pipeline.handle_set_region)
    server.on_request_suggestion(pipeline.handle_request_suggestion)

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
