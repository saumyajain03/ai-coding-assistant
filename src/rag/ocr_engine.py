"""
Lazy Local OCR Engine
Executes on-demand, local OCR extraction exclusively for scanned or mixed pages.
Includes per-page concurrency locking, disk caching, prompt-injection sanitization,
and graceful degradation if the system OCR binary is unavailable.
"""

import json
import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.rag.canonical_page import OCRStatus, get_canonical_page_store
from src.rag.guardrails import sanitize_content_for_context, scan_for_prompt_injection

logger = logging.getLogger(__name__)


class LazyOCREngine:
    def __init__(self, cache_dir: Path | None = None):
        self.settings = get_settings()
        self.cache_dir = cache_dir or self.settings.OCR_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._page_locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        self._tesseract_available = self._detect_tesseract()

    def _detect_tesseract(self) -> bool:
        """Checks if local tesseract binary is installed and executable."""
        return shutil.which("tesseract") is not None

    def is_ocr_available(self) -> bool:
        return self.settings.ENABLE_OCR and self._tesseract_available

    def _get_page_lock(self, page_key: str) -> threading.Lock:
        with self._global_lock:
            if page_key not in self._page_locks:
                self._page_locks[page_key] = threading.Lock()
            return self._page_locks[page_key]

    def _get_cache_path(self, doc_id: str, page_number: int) -> Path:
        return self.cache_dir / f"{doc_id}_p{page_number}.json"

    def get_cached_ocr(self, doc_id: str, page_number: int) -> dict[str, Any] | None:
        path = self._get_cache_path(doc_id, page_number)
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to read OCR cache file %s: %s", path, e)
        return None

    def _save_cache(self, doc_id: str, page_number: int, data: dict[str, Any]) -> None:
        path = self._get_cache_path(doc_id, page_number)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning("Failed to write OCR cache file %s: %s", path, e)

    def clear_cache(self, doc_id: str | None = None) -> int:
        count = 0
        pattern = f"{doc_id}_p*.json" if doc_id else "*.json"
        for f in self.cache_dir.glob(pattern):
            try:
                f.unlink(missing_ok=True)
                count += 1
            except Exception:
                pass
        return count

    def process_page_ocr(
        self,
        doc_id: str,
        filename: str,
        page_number: int,
        page_images: list[Any] | None = None,
        raw_pdf_bytes: bytes | None = None,
        custom_ocr_text: str | None = None,
    ) -> dict[str, Any]:
        """
        Lazily executes OCR for a specific page with concurrency locking and caching.

        Returns:
            {
                "status": OCRStatus,
                "text": str,
                "sanitized_context": str,
                "confidence": float,
                "warnings": list[str],
                "cached": bool,
                "duration_ms": float,
            }
        """
        page_key = f"{filename}:{page_number}"
        lock = self._get_page_lock(page_key)

        with lock:
            # 1. Check cache first
            cached = self.get_cached_ocr(doc_id, page_number)
            if cached is not None:
                cached["cached"] = True
                return cached

            start_time = time.time()
            warnings: list[str] = []

            # 2. Check if OCR is disabled
            if not self.settings.ENABLE_OCR:
                res = {
                    "status": OCRStatus.NOT_REQUIRED.value,
                    "text": "",
                    "sanitized_context": "",
                    "confidence": 0.0,
                    "warnings": ["OCR is disabled in settings (ENABLE_OCR=False)."],
                    "cached": False,
                    "duration_ms": 0.0,
                }
                return res

            # 3. If custom/simulated OCR text is provided (for test suites or injected runs)
            if custom_ocr_text is not None:
                ocr_text = custom_ocr_text
                confidence = 0.95
                status = OCRStatus.COMPLETED
            elif not self._tesseract_available:
                # 4. Graceful fallback when system binary is missing
                warnings.append(
                    "Local OCR binary (tesseract) is not installed on this system. "
                    "Operating in graceful fallback mode with standard text extraction."
                )
                res = {
                    "status": OCRStatus.UNAVAILABLE.value,
                    "text": "",
                    "sanitized_context": "",
                    "confidence": 0.0,
                    "warnings": warnings,
                    "cached": False,
                    "duration_ms": round((time.time() - start_time) * 1000, 2),
                }
                # Update store
                store = get_canonical_page_store()
                store.update_page_ocr(filename, page_number, OCRStatus.UNAVAILABLE, warnings=warnings)
                return res
            else:
                # 5. Real Tesseract execution on page images
                ocr_text, confidence, ocr_warns = self._run_tesseract(page_images)
                warnings.extend(ocr_warns)
                status = OCRStatus.COMPLETED if ocr_text else OCRStatus.FAILED

            # 6. Security: Anti-injection scan & defensive sanitization
            is_malicious, threats, risk_score = scan_for_prompt_injection(ocr_text)
            if is_malicious:
                warnings.append(f"Prompt injection pattern detected in OCR text: {threats}")

            citation = f"{filename}:Page {page_number} [OCR]"
            sanitized_context = sanitize_content_for_context(
                raw_content=ocr_text,
                source_citation=citation,
                score=confidence,
            )

            duration_ms = round((time.time() - start_time) * 1000, 2)
            result = {
                "status": status.value,
                "text": ocr_text,
                "sanitized_context": sanitized_context,
                "confidence": confidence,
                "warnings": warnings,
                "cached": False,
                "duration_ms": duration_ms,
            }

            # 7. Update disk cache & CanonicalPageStore
            self._save_cache(doc_id, page_number, result)
            store = get_canonical_page_store()
            store.update_page_ocr(
                filename,
                page_number,
                status,
                ocr_text=ocr_text,
                warnings=warnings,
            )

            return result

    def _run_tesseract(self, page_images: list[Any] | None) -> tuple[str, float, list[str]]:
        """Executes pytesseract or local tesseract subprocess."""
        if not page_images:
            return "", 0.0, ["No embedded images found on page to OCR."]
        try:
            import subprocess
            from io import BytesIO

            all_text: list[str] = []
            for img in page_images[:3]:
                # Extract image bytes
                img_data = getattr(img, "data", None)
                if not img_data and hasattr(img, "save"):
                    buf = BytesIO()
                    img.save(buf, format="PNG")
                    img_data = buf.getvalue()

                if img_data:
                    proc = subprocess.run(
                        ["tesseract", "stdin", "stdout", "--oem", "1", "-l", "eng"],
                        input=img_data,
                        capture_output=True,
                        timeout=self.settings.OCR_TIMEOUT_SEC,
                    )
                    if proc.returncode == 0:
                        all_text.append(proc.stdout.decode("utf-8", errors="replace"))

            combined = "\n".join(all_text).strip()
            return combined, 0.85 if combined else 0.0, []
        except Exception as e:
            return "", 0.0, [f"Tesseract execution error: {e}"]


_ocr_engine_instance: LazyOCREngine | None = None


def get_ocr_engine() -> LazyOCREngine:
    global _ocr_engine_instance
    if _ocr_engine_instance is None:
        _ocr_engine_instance = LazyOCREngine()
    return _ocr_engine_instance
