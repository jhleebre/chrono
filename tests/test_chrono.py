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

# Ensure the source directory is in the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import the refactored module's components
from src.chrono import (
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
    Tests if Chrono correctly follows the singleton pattern.

    This test verifies two key behaviors:
    1. Accessing the instance in any way always returns the same object.
    2. Calling the constructor `Chrono(...)` after the first instantiation
       does not re-initialize or re-configure the singleton.
    """
    print("\n--- 1. Singleton Pattern Test ---")

    # 1. Get all handles to the singleton instance
    instance1 = chrono  # The pre-initialized instance
    instance2 = get_chrono()  # Access via the helper function
    instance3 = Chrono()  # Access by calling the class constructor again

    print(f"  - Pre-initialized instance ID: {id(instance1)}")
    print(f"  - get_chrono() instance ID:    {id(instance2)}")
    print(f"  - Chrono() instance ID:        {id(instance3)}")

    assert id(instance1) == id(instance2) == id(instance3)
    print("  - SUCCESS: All instances are identical.")

    # 2. Verify that subsequent constructor calls with arguments are ignored
    original_tz = get_chrono_stats()["timezone"]
    print(f"  - Original timezone is '{original_tz}'.")

    # This call should be ignored, as the singleton already exists
    instance4 = Chrono(timezone_str="This/Should_Be_Ignored", cache_interval_ms=999)

    new_stats = get_chrono_stats()
    assert id(instance4) == id(instance1)
    assert new_stats["timezone"] == original_tz
    assert new_stats["cache_interval_ms"] != 999
    print(f"  - SUCCESS: Calling Chrono() again did not change the configuration.")


def test_auto_initialization():
    """
    Tests if the chrono instance is automatically configured with the system
    timezone upon module import via its constructor.
    """
    print("\n--- 2. Automatic Initialization Test ---")
    stats = get_chrono_stats()

    assert stats["is_configured"] is True
    print(f"  - SUCCESS: Instance is configured automatically on import.")

    assert stats["timezone"] is not None and stats["timezone"] != ""
    print(f"  - SUCCESS: Initialized with a valid timezone: '{stats['timezone']}'.")


def test_accuracy():
    """
    Tests the accuracy of the time returned by now().
    The difference from the real time should be within the cache interval,
    plus a small margin for execution delay.
    """
    print("\n--- 3. Accuracy Test ---")
    reconfigure_chrono(timezone_str="Asia/Seoul", cache_interval_ms=20)

    for i in range(3):
        cached_time = now()
        real_time = datetime.now(ZoneInfo("Asia/Seoul"))
        diff = abs((cached_time - real_time).total_seconds())

        # The difference should be less than the cache interval (0.02s)
        # plus a small 10ms margin for code execution.
        assert diff < 0.03
        print(f"  - Iteration {i+1}: Difference is {diff * 1e6:.3f} microseconds. (OK)")
        time.sleep(0.05)


def test_performance():
    """
    Compares the performance of the standard library's datetime.now()
    with Chrono's high-speed timestamp() method.
    """
    print("\n--- 4. Performance Test ---")
    reconfigure_chrono(timezone_str="UTC", cache_interval_ms=10)

    ITERATIONS = 200_000
    tz_utc = ZoneInfo("UTC")

    # Measure standard library performance (system calls)
    start_std = time.perf_counter()
    for _ in range(ITERATIONS):
        datetime.now(tz_utc)
    end_std = time.perf_counter()
    std_time = end_std - start_std
    print(
        f"  - Standard `datetime.now()` ({ITERATIONS:,} calls): {std_time:.4f} seconds"
    )

    # Measure Chrono performance (memory access + arithmetic)
    start_chrono = time.perf_counter()
    for _ in range(ITERATIONS):
        timestamp()
    end_chrono = time.perf_counter()
    chrono_time = end_chrono - start_chrono
    print(
        f"  - Chrono `timestamp()` ({ITERATIONS:,} calls):      {chrono_time:.4f} seconds"
    )

    assert chrono_time < std_time
    print(f"  - SUCCESS: Chrono is {std_time / chrono_time:.1f}x faster.")


def test_multithreading_safety():
    """
    Tests if the Chrono instance is thread-safe when accessed from multiple
    threads simultaneously, ensuring no race conditions or deadlocks.
    """
    print("\n--- 5. Multithreading Safety Test ---")

    results: List[Tuple[int, int, float]] = []

    def worker(worker_id: int):
        """A simple worker that rapidly calls timestamp()."""
        timestamps = []
        for _ in range(1000):
            timestamps.append(timestamp())
            time.sleep(0.0001)  # 0.1ms sleep to allow thread interleaving
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
    print("  - SUCCESS: All threads completed without errors or deadlocks.")


def test_runtime_reconfiguration():
    """
    Tests if the configuration can be changed at runtime using reconfigure_chrono(),
    and that the changes take effect immediately.
    """
    print("\n--- 6. Runtime Reconfiguration Test ---")

    # 1. Change to UTC and set a new interval
    reconfigure_chrono(timezone_str="UTC", cache_interval_ms=100)
    stats_utc = get_chrono_stats()
    assert stats_utc["timezone"] == "UTC"
    assert stats_utc["cache_interval_ms"] == 100
    print(f"  - SUCCESS: Reconfigured to UTC, 100ms. Current time: {now()}")

    # 2. Change to New York and disable background updates
    reconfigure_chrono(timezone_str="America/New_York", background_update=False)
    stats_nyc = get_chrono_stats()
    assert stats_nyc["timezone"] == "America/New_York"
    assert stats_nyc["background_update_enabled"] is False
    print(
        f"  - SUCCESS: Reconfigured to New York (BG Update OFF). Current time: {now()}"
    )


def test_statistics_and_reset():
    """
    Tests if performance statistics are collected correctly and can be
    reset to zero on demand.
    """
    print("\n--- 7. Statistics and Reset Test ---")
    reset_chrono_stats()

    # Induce a cache miss by using on-demand updates and waiting for the
    # cache to become stale.
    reconfigure_chrono(cache_interval_ms=10, background_update=False)
    timestamp()  # First call, likely a miss
    time.sleep(0.02)  # Wait longer than the 10ms interval
    timestamp()  # Second call, should be another miss

    stats = get_chrono_stats()
    assert stats["cache_misses"] > 0
    print(f"  - SUCCESS: Cache misses correctly recorded ({stats['cache_misses']}).")

    reset_chrono_stats()
    stats_after_reset = get_chrono_stats()
    assert stats_after_reset["cache_hits"] == 0
    assert stats_after_reset["cache_misses"] == 0
    print(f"  - SUCCESS: Stats correctly reset to zero.")


def test_shutdown():
    """
    Tests if shutdown_chrono() correctly stops the background update thread.
    """
    print("\n--- 8. Shutdown Test ---")

    # 1. Start the background thread by reconfiguring.
    reconfigure_chrono(background_update=True)
    time.sleep(0.1)  # Give the thread a moment to start.
    stats_before = get_chrono_stats()

    # This check handles cases where the test runner might be slow.
    if not stats_before["background_thread_alive"]:
        reconfigure_chrono(background_update=True)
        time.sleep(0.1)
        stats_before = get_chrono_stats()

    assert stats_before["background_update_enabled"] is True
    assert stats_before["background_thread_alive"] is True
    print("  - Verified: Background thread is running.")

    # 2. Call shutdown.
    shutdown_chrono()

    # 3. Check if the thread has been stopped.
    stats_after = get_chrono_stats()
    assert stats_after["background_thread_alive"] is False
    print("  - SUCCESS: Background thread has been shut down.")


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
