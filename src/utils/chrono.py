"""
Chrono: A high-performance, singleton-based time utility.

This module provides a solution for frequent time lookups in an application,
combining the best features of various implementations:
- Thread-safe singleton pattern using a metaclass.
- Utilizes the standard `zoneinfo` library (Python 3.9+).
- Provides highly accurate time by calculating elapsed monotonic time.
- Features an optional background thread for proactive cache updates.
- Supports runtime reconfiguration without restarting the application.
- Ensures complete thread safety for all operations.
- Includes statistics for monitoring and performance tuning.

--- Quick Start Guide ---

1. Basic Usage (Automatic Initialization)
   Simply import the pre-initialized 'chrono' instance. It automatically configures
   itself to your system's timezone on the first import (requires 'tzlocal' library).

   from src.utils.chrono import chrono, now, timestamp

   # Get the current time as a datetime object
   current_datetime = chrono.now() # or simply now()
   print(f"Current System Time: {current_datetime}")

   # Get the current time as a Unix timestamp (float)
   current_ts = chrono.timestamp() # or simply timestamp()
   print(f"Current Timestamp: {current_ts}")


2. Reconfiguration (Best Practice for Production)
   For production servers, it is *highly recommended* to explicitly set the
   timezone to avoid ambiguity. Call reconfigure() or initialize_chrono()
   once when your application starts.

   from src.utils.chrono import reconfigure_chrono, now

   if __name__ == "__main__":
       # Reconfigure once at startup for a specific timezone
       reconfigure_chrono(
           timezone_str='Asia/Seoul',
           cache_interval_ms=50
       )

       # Now you can use the functions anywhere in your app
       print(f"Seoul Time: {now()}")

"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import time
import threading
import atexit
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Optional, Dict, Any, Type, List, Tuple
from src.utils.logger import get_logger

logger = get_logger(__name__)

# --- System Timezone Detection ---
try:
    from tzlocal import get_localzone_name

    TZLOCAL_AVAILABLE = True
except ImportError:
    TZLOCAL_AVAILABLE = False


def _get_system_timezone() -> str:
    """
    Tries to get the system's IANA timezone name using 'tzlocal'.
    Falls back to 'UTC' if the library is missing or fails.
    """
    if TZLOCAL_AVAILABLE:
        try:
            tz_name = get_localzone_name()
            if not tz_name:
                raise ValueError("tzlocal returned an empty timezone name.")
            return tz_name
        except Exception as e:
            logger.warning(
                "Chrono WARNING: Could not determine system timezone from 'tzlocal' (Error: %s). "
                "Defaulting to 'UTC' timezone.",
                e,
            )
    else:
        logger.warning(
            "\n"
            "======================================================================================\n"
            "Chrono WARNING: 'tzlocal' library not found. Defaulting to 'UTC' timezone.\n"
            "For automatic system timezone detection, please install it by running:\n"
            "  pip install tzlocal\n"
            "======================================================================================"
        )
    return "UTC"


class SingletonMeta(type):
    _instances: Dict[Type, Any] = {}
    _lock: threading.RLock = threading.RLock()

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]


class Chrono(metaclass=SingletonMeta):
    """
    A singleton time utility that minimizes system calls.
    (class implementation remains the same)
    """

    def __init__(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._timezone_str: str = "UTC"
        self._tz: ZoneInfo = ZoneInfo("UTC")
        self._cache_interval_ms: int = 10
        self._cache_interval_sec: float = 0.01
        self._background_update: bool = True
        self._cached_datetime: datetime = datetime.fromtimestamp(0)
        self._cached_timestamp: float = 0.0
        self._last_monotonic_time: float = 0.0
        self._lock: threading.RLock = threading.RLock()
        self._update_thread: Optional[threading.Thread] = None
        self._shutdown_event: threading.Event = threading.Event()
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._last_update_time: Optional[datetime] = None
        self._initialized: bool = False
        atexit.register(self.shutdown)

    def initialize(
        self,
        timezone_str: str = "UTC",
        cache_interval_ms: int = 10,
        background_update: bool = True,
    ) -> "Chrono":
        with self._lock:
            self._stop_background_update()
            self._setup_timezone(timezone_str)
            self._cache_interval_ms = max(1, min(1000, cache_interval_ms))
            self._cache_interval_sec = self._cache_interval_ms / 1000.0
            self._background_update = background_update
            self._update_cached_time()
            if self._background_update:
                self._start_background_update()
            self._initialized = True
            logger.info(
                f"Chrono initialized - "
                f"Timezone: {self._timezone_str}, "
                f"Cache Interval: {self._cache_interval_ms}ms, "
                f"Background Update: {self._background_update}"
            )
            return self

    def _setup_timezone(self, timezone_str: str) -> None:
        try:
            self._tz = ZoneInfo(timezone_str)
            self._timezone_str = timezone_str
        except ZoneInfoNotFoundError:
            logger.warning(f"Timezone '{timezone_str}' not found. Falling back to UTC.")
            self._tz = ZoneInfo("UTC")
            self._timezone_str = "UTC"

    def _update_cached_time(self) -> None:
        current_monotonic = time.monotonic()
        current_datetime = datetime.now(self._tz)
        self._cached_datetime = current_datetime
        self._cached_timestamp = current_datetime.timestamp()
        self._last_monotonic_time = current_monotonic
        self._last_update_time = current_datetime
        self._cache_misses += 1

    def _start_background_update(self) -> None:
        if self._update_thread and self._update_thread.is_alive():
            return
        self._shutdown_event.clear()
        self._update_thread = threading.Thread(
            target=self._background_update_worker,
            daemon=True,
            name="ChronoUpdater",
        )
        self._update_thread.start()
        logger.info("Chrono background update thread started.")

    def _stop_background_update(self) -> None:
        if self._update_thread and self._update_thread.is_alive():
            self._shutdown_event.set()
            self._update_thread.join(timeout=1.0)
            logger.info("Chrono background update thread stopped.")
            self._update_thread = None

    def _background_update_worker(self) -> None:
        while not self._shutdown_event.wait(self._cache_interval_sec):
            try:
                with self._lock:
                    self._update_cached_time()
            except Exception as e:
                logger.error(f"Error in Chrono background update: {e}", exc_info=True)

    def _check_and_update_on_demand(self) -> None:
        if time.monotonic() - self._last_monotonic_time > self._cache_interval_sec:
            with self._lock:
                if (
                    time.monotonic() - self._last_monotonic_time
                    > self._cache_interval_sec
                ):
                    self._update_cached_time()

    def now(self) -> datetime:
        if not self._initialized:
            # This path is now less likely due to pre-initialization,
            # but kept for robustness.
            self.initialize(_get_system_timezone())
        if not self._background_update:
            self._check_and_update_on_demand()
        last_mono_time = self._last_monotonic_time
        cached_dt = self._cached_datetime
        elapsed_seconds = time.monotonic() - last_mono_time
        self._cache_hits += 1
        return cached_dt + timedelta(seconds=elapsed_seconds)

    def timestamp(self) -> float:
        if not self._initialized:
            self.initialize(_get_system_timezone())
        if not self._background_update:
            self._check_and_update_on_demand()
        last_mono_time = self._last_monotonic_time
        cached_ts = self._cached_timestamp
        elapsed_seconds = time.monotonic() - last_mono_time
        self._cache_hits += 1
        return cached_ts + elapsed_seconds

    def strftime(self, format_string: str) -> str:
        return self.now().strftime(format_string)

    def reconfigure(
        self,
        timezone_str: Optional[str] = None,
        cache_interval_ms: Optional[int] = None,
        background_update: Optional[bool] = None,
    ) -> None:
        with self._lock:
            new_tz = timezone_str if timezone_str is not None else self._timezone_str
            new_interval = (
                cache_interval_ms
                if cache_interval_ms is not None
                else self._cache_interval_ms
            )
            new_bg_update = (
                background_update
                if background_update is not None
                else self._background_update
            )
            self.initialize(new_tz, new_interval, new_bg_update)
            logger.info("Chrono reconfigured.")

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total_calls = self._cache_hits + self._cache_misses
            hit_ratio = (self._cache_hits / total_calls * 100) if total_calls > 0 else 0
            return {
                "timezone": self._timezone_str,
                "cache_interval_ms": self._cache_interval_ms,
                "background_update_enabled": self._background_update,
                "is_initialized": self._initialized,
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "cache_hit_ratio": f"{hit_ratio:.2f}%",
                "last_cache_update_time": (
                    self._last_update_time.isoformat()
                    if self._last_update_time
                    else None
                ),
                "background_thread_alive": (
                    self._update_thread.is_alive() if self._update_thread else False
                ),
            }

    def reset_stats(self) -> None:
        with self._lock:
            self._cache_hits = 0
            self._cache_misses = 0
            logger.info("Chrono statistics have been reset.")

    def is_initialized(self) -> bool:
        return self._initialized

    def shutdown(self) -> None:
        with self._lock:
            self._stop_background_update()
            logger.info("Chrono has been shut down.")


# --- Convenience Functions for Easy Global Access ---


def get_chrono() -> Chrono:
    return Chrono()


def initialize_chrono(
    timezone_str: Optional[str] = None,
    cache_interval_ms: int = 10,
    background_update: bool = True,
) -> Chrono:
    tz = timezone_str if timezone_str is not None else _get_system_timezone()
    return get_chrono().initialize(
        timezone_str=tz,
        cache_interval_ms=cache_interval_ms,
        background_update=background_update,
    )


def reconfigure_chrono(
    timezone_str: Optional[str] = None,
    cache_interval_ms: Optional[int] = None,
    background_update: Optional[bool] = None,
) -> None:
    get_chrono().reconfigure(
        timezone_str=timezone_str,
        cache_interval_ms=cache_interval_ms,
        background_update=background_update,
    )


def now() -> datetime:
    return get_chrono().now()


def timestamp() -> float:
    return get_chrono().timestamp()


def strftime(format_string: str) -> str:
    return get_chrono().strftime(format_string)


def get_chrono_stats() -> Dict[str, Any]:
    return get_chrono().get_stats()


def reset_chrono_stats() -> None:
    get_chrono().reset_stats()


def shutdown_chrono() -> None:
    get_chrono().shutdown()


# --- Pre-initialized instance for convenient access ---
# This instance is created and initialized once when the module is first imported.
chrono = Chrono()
if not chrono.is_initialized():
    default_timezone = _get_system_timezone()
    chrono.initialize(timezone_str=default_timezone)


# --- Example Usage Demonstration ---
if __name__ == "__main__":
    """
    Running this module directly demonstrates various usage examples.
    """

    # For demonstration, explicitly reconfigure for a server environment (e.g., 'Asia/Seoul').
    # If this block is commented out, the examples will use the auto-detected system timezone.
    reconfigure_chrono(
        timezone_str="Asia/Seoul", cache_interval_ms=50, background_update=True
    )

    print("=" * 60)
    print(f"  Chrono Usage Showcase (Timezone: {get_chrono_stats()['timezone']})")
    print("=" * 60)

    # Basic Usage
    current_time = now()
    current_ts = timestamp()
    print(f"[Basic Usage]")
    print(f"  - now()      : {current_time}")
    print(f"  - isoformat(): {current_time.isoformat()}")
    print(f"  - timestamp(): {current_ts}")
    print("-" * 60)

    print(f"[strftime Formatting Examples]")
    # Example 1: ISO 8601 format, suitable for log files.
    log_format = strftime("%Y-%m-%dT%H:%M:%S%z")
    print(f"  - Log Format : {log_format}")
    # Example output: Log Format : 2025-08-21T12:00:00+0900

    # Example 2: A more human-readable format.
    readable_format = strftime("%B %d, %Y (%a) %I:%M:%S %p")
    print(f"  - Readable   : {readable_format}")
    # Example output: Readable   : August 21, 2025 (Thu) 12:00:00 PM

    # Example 3: For when only the date is needed.
    date_only = strftime("%Y/%m/%d")
    print(f"  - Date Only  : {date_only}")
    # Example output: Date Only  : 2025/08/21

    # Example 4: For when only the time and timezone info are needed.
    time_with_timezone = strftime("%H:%M:%S %Z")
    print(f"  - Time & Zone: {time_with_timezone}")
    # Example output: Time & Zone: 12:00:00 KST

    print("=" * 60)
