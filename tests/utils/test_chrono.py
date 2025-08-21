"""
Unit tests for the Chrono time utility module.

This test suite verifies the functionality, performance, and thread safety
of the Chrono module. It can be run directly as a script or with a test
runner like pytest.
"""

import os
import sys
import threading
import time
from datetime import datetime
from typing import List, Tuple
from zoneinfo import ZoneInfo

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.utils.chrono import (
    Chrono,
    chrono,
    get_chrono,
    get_chrono_stats,
    now,
    reconfigure_chrono,
    reset_chrono_stats,
    shutdown_chrono,
    timestamp,
)


def test_singleton_pattern():
    """
    Tests if the Chrono instance correctly follows the singleton pattern.
    Accessing it in any way should always return the same object instance.
    """
    print("\n--- 1. Singleton Pattern Test ---")

    # 1. The pre-initialized instance created on module load.
    instance1 = chrono

    # 2. Access via the get_chrono() helper function.
    instance2 = get_chrono()

    # 3. Access by calling the class directly.
    instance3 = Chrono()

    print(f"  - Pre-initialized instance ID: {id(instance1)}")
    print(f"  - get_chrono() instance ID:    {id(instance2)}")
    print(f"  - Chrono() instance ID:        {id(instance3)}")

    assert id(instance1) == id(instance2) == id(instance3)
    print("  - SUCCESS: All instances are identical.")


def test_auto_initialization():
    """
    Tests if the chrono instance is automatically initialized with the system
    timezone upon module import.
    """
    print("\n--- 2. Automatic Initialization Test ---")
    stats = get_chrono_stats()

    assert stats["is_initialized"] is True
    print(f"  - SUCCESS: Instance is initialized automatically.")

    assert stats["timezone"] is not None and stats["timezone"] != ""
    print(f"  - SUCCESS: Initialized with timezone '{stats['timezone']}'.")


def test_accuracy():
    """
    Tests the accuracy of the time returned by now().
    The difference from the real time should be within the cache interval.
    """
    print("\n--- 3. Accuracy Test ---")
    reconfigure_chrono(timezone_str="Asia/Seoul", cache_interval_ms=20)

    for i in range(3):
        cached_time = now()
        real_time = datetime.now(ZoneInfo("Asia/Seoul"))
        diff = abs((cached_time - real_time).total_seconds())

        # The difference should be within the cache interval (0.02s) plus a small margin of error.
        assert diff < 0.03
        print(f"  - Difference: {diff * 1e6:.3f} microseconds. (OK)")
        time.sleep(0.05)


def test_performance():
    """
    Compares the performance of the standard library's datetime.now()
    with Chrono's timestamp().
    """
    print("\n--- 4. Performance Test ---")
    reconfigure_chrono(timezone_str="Asia/Seoul", cache_interval_ms=10)

    ITERATIONS = 200_000
    tz_seoul = ZoneInfo("Asia/Seoul")

    # Measure standard library performance.
    start_std = time.perf_counter()
    for _ in range(ITERATIONS):
        datetime.now(tz_seoul)
    end_std = time.perf_counter()
    std_time = end_std - start_std
    print(
        f"  - Standard `datetime.now()` ({ITERATIONS:,} calls): {std_time:.4f} seconds"
    )

    # Measure Chrono performance.
    start_chrono = time.perf_counter()
    for _ in range(ITERATIONS):
        timestamp()
    end_chrono = time.perf_counter()
    chrono_time = end_chrono - start_chrono
    print(
        f"  - Chrono `timestamp()` ({ITERATIONS:,} calls):   {chrono_time:.4f} seconds"
    )

    assert chrono_time < std_time
    print(f"  - SUCCESS: Chrono is {std_time / chrono_time:.1f}x faster.")


def test_multithreading_safety():
    """
    Tests if the Chrono instance is thread-safe when accessed from multiple
    threads simultaneously.
    """
    print("\n--- 5. Multithreading Safety Test ---")

    results: List[Tuple[int, int, float]] = []

    def worker(worker_id: int):
        timestamps = []
        for _ in range(1000):
            timestamps.append(timestamp())
            time.sleep(0.0001)  # 0.1ms
        results.append((worker_id, len(timestamps), timestamps[-1] - timestamps[0]))

    threads = []
    start_time = time.perf_counter()
    for i in range(5):
        thread = threading.Thread(target=worker, args=(i,), name=f"Worker-{i}")
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    elapsed = time.perf_counter() - start_time
    print(f"  - 5 threads completed in: {elapsed:.3f} seconds")
    assert len(results) == 5
    print("  - SUCCESS: All threads completed without errors.")


def test_runtime_reconfiguration():
    """
    Tests if the configuration can be changed at runtime using reconfigure_chrono().
    """
    print("\n--- 6. Runtime Reconfiguration Test ---")

    # 1. Change to UTC.
    reconfigure_chrono(timezone_str="UTC", cache_interval_ms=100)
    stats_utc = get_chrono_stats()
    assert stats_utc["timezone"] == "UTC"
    assert stats_utc["cache_interval_ms"] == 100
    print(f"  - SUCCESS: Reconfigured to UTC, 100ms. Current time: {now()}")

    # 2. Change to New York and disable background updates.
    reconfigure_chrono(timezone_str="America/New_York", background_update=False)
    stats_nyc = get_chrono_stats()
    assert stats_nyc["timezone"] == "America/New_York"
    assert stats_nyc["background_update_enabled"] is False
    print(
        f"  - SUCCESS: Reconfigured to New York, BG-Update OFF. Current time: {now()}"
    )


def test_statistics_and_reset():
    """
    Tests if performance statistics are collected and can be reset correctly.
    """
    print("\n--- 7. Statistics and Reset Test ---")
    reset_chrono_stats()

    # Induce a cache miss by using on-demand updates and waiting.
    reconfigure_chrono(cache_interval_ms=10, background_update=False)
    timestamp()
    time.sleep(0.02)
    timestamp()

    stats = get_chrono_stats()
    assert stats["cache_misses"] > 0
    print(f"  - SUCCESS: Cache misses correctly recorded ({stats['cache_misses']}).")

    reset_chrono_stats()
    stats_after_reset = get_chrono_stats()
    assert stats_after_reset["cache_hits"] == 0
    assert stats_after_reset["cache_misses"] == 0
    print(f"  - SUCCESS: Stats correctly reset.")


def test_shutdown():
    """
    Tests if shutdown_chrono() correctly stops the background update thread.
    """
    print("\n--- 8. Shutdown Test ---")

    # 1. Check if the background thread is running.
    reconfigure_chrono(background_update=True)
    time.sleep(0.1)  # Give the thread time to start.
    stats_before = get_chrono_stats()
    if stats_before["background_thread_alive"] is False:
        # Retry in case it was already stopped or hasn't started yet.
        reconfigure_chrono(background_update=True)
        time.sleep(0.1)
        stats_before = get_chrono_stats()

    assert stats_before["background_update_enabled"] is True
    assert stats_before["background_thread_alive"] is True
    print("  - BG thread is running.")

    # 2. Call shutdown.
    shutdown_chrono()

    # 3. Check if the thread has been stopped.
    stats_after = get_chrono_stats()
    assert stats_after["background_thread_alive"] is False
    print("  - SUCCESS: BG thread has been shut down.")


if __name__ == "__main__":
    """Runs the entire test suite directly."""
    print("======== Running Chrono Test Suite ========")
    test_singleton_pattern()
    test_auto_initialization()
    test_accuracy()
    test_performance()
    test_multithreading_safety()
    test_runtime_reconfiguration()
    test_statistics_and_reset()
    test_shutdown()
    print("\n========= All tests passed successfully! =========")
