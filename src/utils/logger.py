import hashlib
import logging
import os
import sys
from datetime import datetime
from typing import Optional


_loggers = {}
_log_files = {}
_app_identifier = None


def _get_app_identifier():
    global _app_identifier

    if _app_identifier is not None:
        return _app_identifier

    main_script_path = os.path.abspath(sys.argv[0])
    app_hash = hashlib.md5(main_script_path.encode()).hexdigest()[:8]
    _app_identifier = app_hash

    return _app_identifier


def setup_logger(
    name: Optional[str] = None, prefix: str | None = None
) -> logging.Logger:
    global _loggers, _log_files

    log_key = f"{prefix}_{name}" if prefix else name if name else "default"
    app_id = _get_app_identifier()

    if log_key in _loggers:
        return _loggers[log_key]

    # Get project root directory (assuming this file is in src/utils/)
    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_file_dir))

    # Determine if this is a test client based on environment variable or prefix
    is_test_client = (
        os.getenv("IS_TEST_CLIENT", "").lower() == "true"
        or (prefix and "test" in prefix.lower())
        or (not prefix and "test_client" in sys.argv[0].lower())
    )

    # Set log directory - use test subdirectory for test clients
    if is_test_client:
        log_dir = os.path.join(project_root, "logs", "test")
    else:
        log_dir = os.path.join(project_root, "logs")

    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Use LOG_FILE_NAME if set, otherwise use date-based naming
    if "LOG_FILE_NAME" in os.environ:
        if is_test_client:
            # For test clients, prefix LOG_FILE_NAME with "test_"
            log_filename = os.path.join(
                log_dir, f"test_{os.environ['LOG_FILE_NAME']}.log"
            )
        else:
            log_filename = os.path.join(log_dir, f"{os.environ['LOG_FILE_NAME']}.log")
    else:
        current_date = datetime.now().strftime("%y%m%d_%H%M")
        if is_test_client:
            # For test clients, use "test_client_" prefix
            test_prefix = prefix if prefix else "test_client"
            log_filename = os.path.join(
                log_dir, f"{test_prefix}_{current_date}_{app_id}.log"
            )
        elif prefix:
            log_filename = os.path.join(
                log_dir, f"{prefix}_{current_date}_{app_id}.log"
            )
        else:
            log_filename = os.path.join(log_dir, f"app_{current_date}_{app_id}.log")

    formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d [%(levelname)s] %(filename)s:%(lineno)d %(funcName)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Determine log level from environment
    log_level_env = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_env, logging.INFO)

    # Console handler with environment-based level
    console_log_level = os.getenv("CONSOLE_LOG_LEVEL", log_level_env).upper()
    console_level = getattr(logging, console_log_level, log_level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(console_level)

    file_handler = None
    if log_filename in _log_files:
        file_handler = _log_files[log_filename]
    else:
        file_handler = logging.FileHandler(log_filename, encoding="utf-8")
        file_handler.setFormatter(formatter)
        # File handler uses main log level
        file_handler.setLevel(log_level)
        _log_files[log_filename] = file_handler

    logger = logging.getLogger(log_key)
    logger.setLevel(log_level)

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False

    _loggers[log_key] = logger

    return logger


def get_logger(name: Optional[str] = None, prefix: str | None = None) -> logging.Logger:
    return setup_logger(name, prefix)
