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
   itself to your system's timezone on the first import.

   from src.chrono import chrono, now, timestamp

   # Get the current time as a datetime object
   current_datetime = chrono.now() # or simply now()
   print(f"Current System Time: {current_datetime}")


2. Custom Initialization (At Application Start)
   For explicit control, create the instance with custom settings. This only
   works the very first time Chrono is accessed in your application.

   from src.chrono import Chrono

   # This line should be run once when your application starts.
   chrono = Chrono(timezone_str='Asia/Seoul', cache_interval_ms=50)


3. Reconfiguration (Recommended Practice)
   To change settings after initialization, always use reconfigure().

   from src.chrono import reconfigure_chrono, now

   reconfigure_chrono(timezone_str='America/New_York')
   print(f"New York Time: {now()}")

"""

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import time
import threading
import atexit
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Optional, Dict, Any, Type

# --- System Timezone Detection ---
try:
    from tzlocal import get_localzone_name

    TZLOCAL_AVAILABLE = True
except ImportError:
    TZLOCAL_AVAILABLE = False


def _get_system_timezone() -> str:
    """
    Detects the system's IANA timezone name using the 'tzlocal' library.

    This function attempts to find the local timezone to provide a sensible
    default for Chrono's initialization. If 'tzlocal' is not installed or
    fails to determine the timezone, it logs a warning and safely falls

    Returns:
        str: The IANA timezone name (e.g., 'America/New_York') or 'UTC'
             as a fallback.
    """
    if TZLOCAL_AVAILABLE:
        try:
            tz_name = get_localzone_name()
            if not tz_name:
                raise ValueError("tzlocal returned an empty timezone name.")
            return tz_name
        except Exception as e:
            print(
                f"Chrono WARNING: Could not determine system timezone from 'tzlocal' (Error: %s). "
                f"Defaulting to 'UTC' timezone.",
                e,
                file=sys.stderr,
            )
    else:
        print(
            f"\n"
            f"======================================================================================\n"
            f"Chrono WARNING: 'tzlocal' library not found. Defaulting to 'UTC' timezone.\n"
            f"For automatic system timezone detection, please install it by running:\n"
            f"  pip install tzlocal\n"
            f"======================================================================================",
            file=sys.stderr,
        )
    return "UTC"


class SingletonMeta(type):
    """
    A thread-safe metaclass for creating singleton classes.

    This metaclass ensures that only one instance of a class is ever created.
    It uses a dictionary to store created instances and a re-entrant lock
    to handle thread-safe access during the first instantiation.
    """

    _instances: Dict[Type, Any] = {}
    _lock: threading.RLock = threading.RLock()

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """
        Handles the creation of a class instance.

        If an instance of the class does not already exist, it creates one
        within a lock to ensure thread safety. The class's `__init__` method
        will only be called this one time. Subsequent calls to the constructor
        will return the existing instance without re-initializing it.

        Args:
            *args: Variable length argument list for the class constructor.
            **kwargs: Arbitrary keyword arguments for the class constructor.

        Returns:
            The singleton instance of the class.
        """
        if cls not in cls._instances:
            with cls._lock:
                # Double-checked locking pattern
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]


class Chrono(metaclass=SingletonMeta):
    """
    A high-performance, thread-safe singleton time utility.

    Chrono provides cached, timezone-aware datetime objects and timestamps
    with minimal overhead. It avoids frequent system calls by caching the time
    and calculating the precise current time using `time.monotonic()`. It can
    operate with a background thread for proactive updates or in an on-demand
    mode. This class is a singleton, meaning only one instance will ever exist.
    """

    def __init__(
        self,
        timezone_str: Optional[str] = None,
        cache_interval_ms: int = 10,
        background_update: bool = True,
    ) -> None:
        """
        Initializes the Chrono singleton instance.

        This constructor is guaranteed to run only once when the singleton is
        first created. Any subsequent calls to `Chrono()` will return the
        existing instance without re-running this method. To change settings
        after creation, you must use the `reconfigure()` method.

        Args:
            timezone_str (Optional[str]): The IANA timezone name (e.g., 'Asia/Seoul').
                If None, it defaults to the system's detected timezone or 'UTC'.
            cache_interval_ms (int): The interval in milliseconds at which the
                internal time cache is updated. Defaults to 10ms.
            background_update (bool): If True, a background thread proactively
                updates the cache. If False, updates are done on-demand.
                Defaults to True.
        """
        # This check prevents re-entry if the constructor is somehow accessed
        # after the instance is fully created.
        if hasattr(self, "_is_configured") and self._is_configured:
            return

        # Initialize thread-safety and state management attributes first
        self._lock = threading.RLock()
        self._shutdown_event = threading.Event()
        self._update_thread: Optional[threading.Thread] = None
        self._is_configured: bool = False

        # Initialize all other attributes to default values
        self._timezone_str: str = "UTC"
        self._tz: ZoneInfo = ZoneInfo("UTC")
        self._cache_interval_ms = 0
        self._cache_interval_sec = 0.0
        self._background_update = False
        self._cached_datetime = datetime.fromtimestamp(0)
        self._cached_timestamp = 0.0
        self._last_monotonic_time = 0.0
        self._last_update_time: Optional[datetime] = None
        self._cache_hits = 0
        self._cache_misses = 0

        # Determine the initial timezone, falling back to the system default
        initial_tz = (
            timezone_str if timezone_str is not None else _get_system_timezone()
        )

        # Use the central `reconfigure` method to set up the initial state
        self.reconfigure(
            timezone_str=initial_tz,
            cache_interval_ms=cache_interval_ms,
            background_update=background_update,
        )

        # Register the shutdown hook once to be called on program exit
        atexit.register(self.shutdown)

    def reconfigure(
        self,
        timezone_str: Optional[str] = None,
        cache_interval_ms: Optional[int] = None,
        background_update: Optional[bool] = None,
    ) -> None:
        """
        Atomically configures or reconfigures the Chrono instance.

        This is the central method for setting Chrono's behavior. It is
        thread-safe and is the correct way to change settings after
        initialization. If a parameter is not provided, its current value
        is retained.

        Args:
            timezone_str (Optional[str]): The new IANA timezone name.
            cache_interval_ms (Optional[int]): The new cache interval in milliseconds.
            background_update (Optional[bool]): The new background update mode.
        """
        with self._lock:
            # Always stop the background thread before changing settings
            self._stop_background_update()

            if timezone_str is not None:
                self._setup_timezone(timezone_str)

            if cache_interval_ms is not None:
                self._cache_interval_ms = max(1, min(1000, cache_interval_ms))
                self._cache_interval_sec = self._cache_interval_ms / 1000.0

            if background_update is not None:
                self._background_update = background_update

            # Perform an immediate cache update with the new settings
            self._update_cached_time()

            # Restart the background thread if it is enabled
            if self._background_update:
                self._start_background_update()

            self._is_configured = True

    def _setup_timezone(self, timezone_str: str) -> None:
        """
        Initializes the `zoneinfo.ZoneInfo` object from a timezone string.

        If the provided string is invalid, it logs an error and safely falls
        back to using UTC to prevent application crashes.

        Args:
            timezone_str (str): The IANA timezone name to use.
        """
        try:
            self._tz = ZoneInfo(timezone_str)
            self._timezone_str = timezone_str
        except ZoneInfoNotFoundError:
            print(
                f"Chrono WARNING: Timezone '{timezone_str}' not found. Falling back to UTC.",
                file=sys.stderr,
            )
            self._tz = ZoneInfo("UTC")
            self._timezone_str = "UTC"

    def _update_cached_time(self) -> None:
        """
        Performs a system call to update the internal time cache.

        This is the most performance-critical method, as it involves system
        calls. It fetches the current datetime, converts it to a timestamp,
        and stores both along with the current monotonic time. It also
        increments the cache miss counter for statistics.

        Note: This method must be called within a lock to ensure atomicity.
        """
        current_monotonic = time.monotonic()
        current_datetime = datetime.now(self._tz)

        self._cached_datetime = current_datetime
        self._cached_timestamp = current_datetime.timestamp()
        self._last_monotonic_time = current_monotonic
        self._last_update_time = current_datetime
        self._cache_misses += 1

    def _start_background_update(self) -> None:
        """
        Starts the background thread for proactive cache updates.

        If a thread is not already running, this method creates and starts a
        new daemon thread that will periodically call `_update_cached_time`.

        Note: This method must be called within a lock.
        """
        if self._update_thread and self._update_thread.is_alive():
            return
        self._shutdown_event.clear()
        self._update_thread = threading.Thread(
            target=self._background_update_worker,
            daemon=True,
            name="ChronoUpdater",
        )
        self._update_thread.start()

    def _stop_background_update(self) -> None:
        """
        Signals the background update thread to stop and waits for it to exit.

        This is a graceful shutdown procedure that sets an event and then
        joins the thread with a timeout to prevent hanging.

        Note: This method must be called within a lock.
        """
        if self._update_thread and self._update_thread.is_alive():
            self._shutdown_event.set()
            self._update_thread.join(timeout=1.0)
            self._update_thread = None

    def _background_update_worker(self) -> None:
        """
        The target method for the background update thread.

        This method runs in a loop, sleeping for the configured cache interval.
        On each wake-up, it acquires a lock and updates the cached time.
        It will exit gracefully when the shutdown event is set.
        """
        while not self._shutdown_event.wait(self._cache_interval_sec):
            try:
                with self._lock:
                    self._update_cached_time()
            except Exception as e:
                print(
                    f"Chrono ERROR: Unexpected error in background update: {e}",
                    file=sys.stderr,
                )

    def _update_if_stale(self) -> None:
        """
        Updates the cache if it's stale (for on-demand mode).

        This method checks if the time elapsed since the last cache update
        exceeds the configured interval. If it does, it acquires a lock and
        updates the cache. Used when `background_update` is False.
        """
        if time.monotonic() - self._last_monotonic_time > self._cache_interval_sec:
            with self._lock:
                # Double-check inside the lock to prevent redundant updates from
                # multiple threads that were waiting for the lock.
                if (
                    time.monotonic() - self._last_monotonic_time
                    > self._cache_interval_sec
                ):
                    self._update_cached_time()

    def now(self) -> datetime:
        """
        Returns the current timezone-aware datetime object with high performance.

        This is the primary method for getting the current time. It calculates
        the time by taking the last cached datetime and adding the elapsed
        monotonic time, which avoids a costly system call.

        Returns:
            datetime: The current timezone-aware datetime.
        """
        if not self._background_update:
            self._update_if_stale()

        elapsed_seconds = time.monotonic() - self._last_monotonic_time
        self._cache_hits += 1
        return self._cached_datetime + timedelta(seconds=elapsed_seconds)

    def timestamp(self) -> float:
        """
        Returns the current Unix timestamp as a float with high performance.

        Similar to `now()`, this method calculates the current timestamp by
        taking the last cached timestamp and adding the elapsed monotonic
        time. This is much faster than `datetime.now().timestamp()`.

        Returns:
            float: The current Unix timestamp (e.g., 1678886400.123456).
        """
        if not self._background_update:
            self._update_if_stale()

        elapsed_seconds = time.monotonic() - self._last_monotonic_time
        self._cache_hits += 1
        return self._cached_timestamp + elapsed_seconds

    def strftime(self, format_string: str) -> str:
        """
        Formats the current time into a string.

        This is a convenience method that calls `self.now()` and then formats
        the resulting datetime object using the provided format string.

        Args:
            format_string (str): The format string, as used by `datetime.strftime`.

        Returns:
            str: The formatted time string.
        """
        return self.now().strftime(format_string)

    def get_stats(self) -> Dict[str, Any]:
        """
        Retrieves performance and configuration statistics.

        This method provides a thread-safe snapshot of the current state and
        performance metrics of the Chrono instance, useful for monitoring.

        Returns:
            Dict[str, Any]: A dictionary containing statistics such as
            timezone, cache settings, hit/miss ratio, and thread status.
        """
        with self._lock:
            total_calls = self._cache_hits + self._cache_misses
            hit_ratio = (self._cache_hits / total_calls * 100) if total_calls > 0 else 0
            return {
                "timezone": self._timezone_str,
                "cache_interval_ms": self._cache_interval_ms,
                "background_update_enabled": self._background_update,
                "is_configured": self._is_configured,
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
        """
        Resets the cache hit and miss counters to zero.

        This can be useful for monitoring performance over specific periods
        without restarting the application.
        """
        with self._lock:
            self._cache_hits = 0
            self._cache_misses = 0

    def shutdown(self) -> None:
        """
        Gracefully shuts down the Chrono instance.

        This method stops the background update thread. It is automatically
        registered with `atexit` to be called on program termination, so manual
        calling is generally not necessary.
        """
        with self._lock:
            self._stop_background_update()


# --- Convenience Functions for Easy Global Access ---


def get_chrono() -> Chrono:
    """
    Returns the global singleton instance of the Chrono class.

    This function is the entry point for accessing the Chrono object.

    Returns:
        Chrono: The singleton Chrono object.
    """
    return Chrono()


def reconfigure_chrono(
    timezone_str: Optional[str] = None,
    cache_interval_ms: Optional[int] = None,
    background_update: Optional[bool] = None,
) -> None:
    """
    A convenience function to reconfigure the global Chrono instance.

    This is a wrapper around `chrono.reconfigure()`.

    Args:
        timezone_str (Optional[str]): The new IANA timezone name.
        cache_interval_ms (Optional[int]): The new cache update interval.
        background_update (Optional[bool]): The new background update mode.
    """
    get_chrono().reconfigure(
        timezone_str=timezone_str,
        cache_interval_ms=cache_interval_ms,
        background_update=background_update,
    )


def now() -> datetime:
    """
    A convenience function to get the current datetime from the global instance.

    Returns:
        datetime: The current timezone-aware datetime.
    """
    return get_chrono().now()


def timestamp() -> float:
    """
    A convenience function to get the current timestamp from the global instance.

    Returns:
        float: The current Unix timestamp.
    """
    return get_chrono().timestamp()


def strftime(format_string: str) -> str:
    """
    A convenience function to format the current time using the global instance.

    Args:
        format_string (str): The format string for the time.

    Returns:
        str: The formatted time string.
    """
    return get_chrono().strftime(format_string)


def get_chrono_stats() -> Dict[str, Any]:
    """
    A convenience function to get stats from the global Chrono instance.

    Returns:
        Dict[str, Any]: A dictionary of performance and configuration statistics.
    """
    return get_chrono().get_stats()


def reset_chrono_stats() -> None:
    """A convenience function to reset the stats of the global Chrono instance."""
    get_chrono().reset_stats()


def shutdown_chrono() -> None:
    """A convenience function to shut down the global Chrono instance."""
    get_chrono().shutdown()


# --- Pre-initialized instance for convenient access ---
# This creates and configures the singleton instance on first module import. It
# uses the default parameters of the `Chrono` constructor, which means it will
# auto-detect the system timezone.
chrono = Chrono()


# --- Example Usage Demonstration ---
if __name__ == "__main__":
    """
    Running this module directly demonstrates various usage examples.
    """
    print("=" * 60)
    print(f"  Chrono Initial State (from default __init__)")
    print("-" * 60)
    print(f"  - Timezone: {get_chrono_stats()['timezone']}")
    print(f"  - Current Time: {now().isoformat()}")
    print("=" * 60)

    # Reconfigure the existing instance for a different setting
    print("\nReconfiguring for 'America/New_York' with 100ms interval...\n")
    reconfigure_chrono(
        timezone_str="America/New_York", cache_interval_ms=100, background_update=True
    )

    print("=" * 60)
    print(f"  Chrono Reconfigured State")
    print("-" * 60)

    # Basic Usage
    current_time = now()
    current_ts = timestamp()
    print(f"[Basic Usage]")
    print(f"  - Timezone   : {get_chrono_stats()['timezone']}")
    print(f"  - now()      : {current_time}")
    print(f"  - isoformat(): {current_time.isoformat()}")
    print(f"  - timestamp(): {current_ts}")
    print("-" * 60)

    print(f"[strftime Formatting Examples]")
    readable_format = strftime("%B %d, %Y (%a) %I:%M:%S %p %Z")
    print(f"  - Readable   : {readable_format}")
    time_only = strftime("%H:%M:%S.%f")
    print(f"  - Time Only  : {time_only}")

    print("=" * 60)
