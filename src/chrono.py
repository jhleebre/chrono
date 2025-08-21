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
   Simply import the pre-initialized 'chrono' instance. It automatically onfigures
   itself to your system's timezone on the first import (requires 'tzlocal' library).

   from src.chrono import chrono, now, timestamp

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

   from src.chrono import reconfigure_chrono, now

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
    """Detects the system's IANA timezone name using the 'tzlocal' library.

    This function attempts to find the local timezone to provide a sensible
    default for Chrono's initialization. If 'tzlocal' is not installed or
    fails to determine the timezone, it logs a warning and safely falls
    back to "UTC".

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
        within a lock to ensure thread safety. Otherwise, it returns the
        existing instance.

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
    mode.
    """

    def __init__(self) -> None:
        """
        Initializes the Chrono singleton instance with default values.

        This constructor is called only once due to the SingletonMeta metaclass.
        It sets up the initial state, including default timezone, cache
        settings, and thread management objects. It also registers the
        shutdown method to be called on program exit.
        """
        # Prevent re-initialization if accessed directly after creation
        if hasattr(self, "_initialized") and self._initialized:
            return

        # Core configuration
        self._timezone_str: str = "UTC"
        self._tz: ZoneInfo = ZoneInfo("UTC")
        self._cache_interval_ms: int = 10
        self._cache_interval_sec: float = 0.01
        self._background_update: bool = True

        # Cached time values
        self._cached_datetime: datetime = datetime.fromtimestamp(0)
        self._cached_timestamp: float = 0.0
        self._last_monotonic_time: float = 0.0

        # Threading and safety
        self._lock: threading.RLock = threading.RLock()
        self._update_thread: Optional[threading.Thread] = None
        self._shutdown_event: threading.Event = threading.Event()

        # Statistics and state
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._last_update_time: Optional[datetime] = None
        self._initialized: bool = False

        # Register cleanup hook
        atexit.register(self.shutdown)

    def initialize(
        self,
        timezone_str: str = "UTC",
        cache_interval_ms: int = 10,
        background_update: bool = True,
    ) -> "Chrono":
        """
        Configures or re-configures the Chrono instance.

        This is the main method for setting up Chrono's behavior. It is
        thread-safe and can be called at any time to change the configuration.

        Args:
            timezone_str (str): The IANA timezone name (e.g., 'Asia/Seoul', 'UTC').
            cache_interval_ms (int): The interval in milliseconds at which the
                internal time cache is updated. Clamped between 1 and 1000.
            background_update (bool): If True, a background thread will
                proactively update the cache. If False, the cache is updated
                on-demand when it's considered stale.

        Returns:
            Chrono: The configured instance of the class, allowing for chaining.
        """
        with self._lock:
            self._stop_background_update()

            self._setup_timezone(timezone_str)
            self._cache_interval_ms = max(1, min(1000, cache_interval_ms))
            self._cache_interval_sec = self._cache_interval_ms / 1000.0
            self._background_update = background_update

            # Perform an immediate update to populate the cache
            self._update_cached_time()

            if self._background_update:
                self._start_background_update()

            self._initialized = True
            return self

    def _setup_timezone(self, timezone_str: str) -> None:
        """
        Initializes the `zoneinfo.ZoneInfo` object from a timezone string.

        If the provided string is invalid, it logs an error and safely falls
        back to using UTC.

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

        This method is the only one that makes a system call to get the
        current time. It fetches the current datetime, converts it to a
        timestamp, and stores both along with the current monotonic time.
        It also increments the cache miss counter for statistics.

        Note: This method should be called within a lock.
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

        Note: This method should be called within a lock.
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
        joins the thread with a timeout.

        Note: This method should be called within a lock.
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

    def _check_and_update_on_demand(self) -> None:
        """
        Updates the cache if it's stale (for non-background mode).

        This method checks if the time elapsed since the last cache update
        exceeds the configured interval. If it does, it acquires a lock and
        updates the cache. This is used when `background_update` is False.
        """
        if time.monotonic() - self._last_monotonic_time > self._cache_interval_sec:
            with self._lock:
                # Double-check inside the lock to prevent redundant updates from
                # multiple threads waiting for the lock.
                if (
                    time.monotonic() - self._last_monotonic_time
                    > self._cache_interval_sec
                ):
                    self._update_cached_time()

    def now(self) -> datetime:
        """
        Returns the current timezone-aware datetime object.

        This is the primary method for getting the current time. It calculates
        the time by taking the last cached datetime and adding the elapsed
        monotonic time, avoiding a system call. This provides high accuracy
        with very low overhead.

        Returns:
            datetime: The current timezone-aware datetime.
        """
        if not self._initialized:
            # Auto-initialize on first use with system timezone
            self.initialize(_get_system_timezone())

        if not self._background_update:
            self._check_and_update_on_demand()

        # Reading these attributes is thread-safe in Python
        last_mono_time = self._last_monotonic_time
        cached_dt = self._cached_datetime

        # Calculate precise time using monotonic clock delta
        elapsed_seconds = time.monotonic() - last_mono_time
        self._cache_hits += 1
        return cached_dt + timedelta(seconds=elapsed_seconds)

    def timestamp(self) -> float:
        """
        Returns the current Unix timestamp as a float.

        Similar to `now()`, this method calculates the current timestamp by
        taking the last cached timestamp and adding the elapsed monotonic
        time. This is much faster than `datetime.now().timestamp()`.

        Returns:
            float: The current Unix timestamp (e.g., 1678886400.123456).
        """
        if not self._initialized:
            # Auto-initialize on first use with system timezone
            self.initialize(_get_system_timezone())

        if not self._background_update:
            self._check_and_update_on_demand()

        # Reading these attributes is thread-safe in Python
        last_mono_time = self._last_monotonic_time
        cached_ts = self._cached_timestamp

        # Calculate precise timestamp using monotonic clock delta
        elapsed_seconds = time.monotonic() - last_mono_time
        self._cache_hits += 1
        return cached_ts + elapsed_seconds

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

    def reconfigure(
        self,
        timezone_str: Optional[str] = None,
        cache_interval_ms: Optional[int] = None,
        background_update: Optional[bool] = None,
    ) -> None:
        """
        Atomically reconfigures the Chrono instance at runtime.

        This method allows changing any of the core configuration parameters
        safely. If a parameter is not provided, its current value is retained.

        Args:
            timezone_str (Optional[str]): The new IANA timezone name.
            cache_interval_ms (Optional[int]): The new cache update interval.
            background_update (Optional[bool]): The new background update mode.
        """
        with self._lock:
            # Use existing values as defaults if new ones aren't provided
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

    def get_stats(self) -> Dict[str, Any]:
        """
        Retrieves performance and configuration statistics.

        This method provides a snapshot of the current state and performance
        metrics of the Chrono instance in a thread-safe manner.

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
        """
        Resets the cache hit and miss counters to zero.

        This can be useful for monitoring performance over specific periods
        without restarting the application.
        """
        with self._lock:
            self._cache_hits = 0
            self._cache_misses = 0

    def is_initialized(self) -> bool:
        """
        Checks if the Chrono instance has been explicitly initialized.

        Returns:
            bool: True if `initialize()` has been called, False otherwise.
        """
        return self._initialized

    def shutdown(self) -> None:
        """
        Gracefully shuts down the Chrono instance.

        This method stops the background update thread. It is automatically
        registered with `atexit` to be called on program termination.
        """
        with self._lock:
            self._stop_background_update()


# --- Convenience Functions for Easy Global Access ---


def get_chrono() -> Chrono:
    """
    Returns the global singleton instance of the Chrono class.

    Returns:
        Chrono: The singleton Chrono object.
    """
    return Chrono()


def initialize_chrono(
    timezone_str: Optional[str] = None,
    cache_interval_ms: int = 10,
    background_update: bool = True,
) -> Chrono:
    """
    A convenience function to initialize the global Chrono instance.

    If no timezone is provided, it attempts to detect the system timezone.

    Args:
        timezone_str (Optional[str]): IANA timezone name. Defaults to system TZ.
        cache_interval_ms (int): Cache update interval in milliseconds.
        background_update (bool): Enable or disable the background thread.

    Returns:
        Chrono: The configured singleton instance.
    """
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
    """
    A convenience function to reconfigure the global Chrono instance.

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
    A convenience function to get the current datetime from the global Chrono instance.

    Returns:
        datetime: The current timezone-aware datetime.
    """
    return get_chrono().now()


def timestamp() -> float:
    """
    A convenience function to get the current timestamp from the global Chrono instance.

    Returns:
        float: The current Unix timestamp.
    """
    return get_chrono().timestamp()


def strftime(format_string: str) -> str:
    """
    A convenience function to format the current time using the global Chrono instance.

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
