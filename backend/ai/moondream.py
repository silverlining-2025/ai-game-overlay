"""Moondream2 vision-language model engine with lazy initialization.

Provides game screen understanding via visual question answering,
captioning, and object detection. Runs as Tier 3 (~1-3s per query)
in a dedicated worker thread to avoid blocking the capture loop.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable

import numpy as np

logger = logging.getLogger(__name__)


class MoondreamEngine:
    """Lazy-loaded Moondream2 wrapper for game screen understanding.

    The model is loaded on first use (~5-10s cold start) and kept in memory.
    All inference runs in a background worker thread. Results are delivered
    via a callback to avoid blocking the caller.
    """

    def __init__(
        self,
        model_id: str = "vikhyatk/moondream2",
        device: str = "cuda",
        revision: str | None = None,
    ) -> None:
        self._model_id = model_id
        self._device = device
        self._revision = revision
        self._model: Any = None
        self._lock = threading.Lock()
        self._queue: queue.Queue[tuple[np.ndarray, str, str, Callable] | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        """Start the background worker thread."""
        if self._worker is not None:
            return
        self._running = True
        self._worker = threading.Thread(
            target=self._worker_loop, daemon=True, name="moondream-worker"
        )
        self._worker.start()
        logger.info("Moondream worker started")

    def stop(self) -> None:
        """Stop the background worker thread."""
        self._running = False
        self._queue.put(None)  # sentinel to unblock
        if self._worker:
            self._worker.join(timeout=5)
            self._worker = None
        logger.info("Moondream worker stopped")

    def _ensure_model(self) -> None:
        """Load the model on first use (thread-safe)."""
        if self._model is not None:
            return

        with self._lock:
            if self._model is not None:
                return

            logger.info("Loading Moondream2 (%s) on %s...", self._model_id, self._device)
            t0 = time.perf_counter()

            from transformers import AutoModelForCausalLM
            import torch

            kwargs: dict[str, Any] = {
                "trust_remote_code": True,
                "dtype": torch.float16,
            }
            if self._revision:
                kwargs["revision"] = self._revision

            self._model = AutoModelForCausalLM.from_pretrained(
                self._model_id, **kwargs
            )
            # Move to GPU manually (avoids device_map compatibility issues)
            if self._device == "cuda" and torch.cuda.is_available():
                self._model = self._model.to(self._device)

            load_s = time.perf_counter() - t0
            logger.info("Moondream2 loaded in %.1fs", load_s)

    def query(
        self,
        frame: np.ndarray,
        question: str,
        callback: Callable[[dict], None],
        request_type: str = "query",
    ) -> None:
        """Submit a visual question for async processing.

        Args:
            frame:        BGR numpy array (screenshot or cropped region).
            question:     Natural language question about the image.
            callback:     Called with result dict when inference completes.
            request_type: "query", "caption", or "detect".
        """
        self._queue.put((frame, question, request_type, callback))

    def query_sync(self, frame: np.ndarray, question: str) -> str:
        """Synchronous single-image VQA. Blocks until answer is ready.

        Use this for testing/calibration. For production, use query().
        """
        self._ensure_model()
        image = self._frame_to_pil(frame)
        t0 = time.perf_counter()
        result = self._model.query(image, question)
        elapsed = time.perf_counter() - t0
        answer = result["answer"] if isinstance(result, dict) else str(result)
        logger.debug("query_sync took %.1fs: %s", elapsed, answer[:100])
        return answer

    def caption_sync(self, frame: np.ndarray, length: str = "short") -> str:
        """Synchronous captioning. Returns a description of the image."""
        self._ensure_model()
        image = self._frame_to_pil(frame)
        result = self._model.caption(image, length=length)
        return result["caption"] if isinstance(result, dict) else str(result)

    def _worker_loop(self) -> None:
        """Background thread: pull requests from queue, run inference."""
        self._ensure_model()

        while self._running:
            try:
                item = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if item is None:
                break  # shutdown sentinel

            frame, question, request_type, callback = item
            try:
                t0 = time.perf_counter()
                image = self._frame_to_pil(frame)

                if request_type == "caption":
                    raw = self._model.caption(image, length="short")
                    answer = raw["caption"] if isinstance(raw, dict) else str(raw)
                elif request_type == "detect":
                    raw = self._model.detect(image, question)
                    answer = str(raw.get("objects", []) if isinstance(raw, dict) else raw)
                else:
                    raw = self._model.query(image, question)
                    answer = raw["answer"] if isinstance(raw, dict) else str(raw)

                elapsed_ms = (time.perf_counter() - t0) * 1000
                logger.debug(
                    "Moondream %s (%.0fms): %s → %s",
                    request_type, elapsed_ms, question[:50], answer[:100],
                )

                callback({
                    "type": request_type,
                    "question": question,
                    "answer": answer,
                    "elapsed_ms": elapsed_ms,
                })

            except Exception:
                logger.exception("Moondream inference failed")
                callback({
                    "type": request_type,
                    "question": question,
                    "answer": "Error: inference failed",
                    "elapsed_ms": 0,
                })

    @staticmethod
    def _frame_to_pil(frame: np.ndarray):
        """Convert BGR numpy array to PIL Image (RGB)."""
        import cv2
        from PIL import Image

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)
