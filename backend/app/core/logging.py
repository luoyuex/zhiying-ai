import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import settings

_FORMATTER = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# backend 目录：app/core/logging.py → parents[2]
_BACKEND_DIR = Path(__file__).resolve().parents[2]

# API 与 worker 分文件写，避免 Windows 上多进程同时轮转同一文件报错
_process_filename = "app.log"


def _file_handler() -> RotatingFileHandler | None:
    log_dir = Path(settings.log_dir)
    if not log_dir.is_absolute():
        log_dir = _BACKEND_DIR / log_dir
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / _process_filename,
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
            delay=True,
        )
    except OSError:
        return None
    handler.setFormatter(_FORMATTER)
    return handler


def setup_logging(debug: bool = False, *, filename: str | None = None) -> None:
    """stdout + 滚动文件双输出；filename 用于区分 API（app.log）与 worker（worker.log）。"""
    global _process_filename
    if filename:
        _process_filename = filename

    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_FORMATTER)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    file_handler = _file_handler()
    if file_handler is not None:
        root.addHandler(file_handler)
    root.setLevel(level)

    logging.getLogger("uvicorn.access").setLevel(logging.INFO if debug else logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    # httpx 默认在 INFO 打印完整 URL；代理提取链接带 vkey，不能让密钥进日志
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
