# Chrono: A High-Performance Time Utility for Python

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Chrono is a high-performance, thread-safe time utility designed for applications that require frequent time lookups without the performance overhead of repeated system calls. It serves as a drop-in, enhanced alternative to standard library time functions, providing higher accuracy and speed through intelligent caching.

## Key Features

-   **High Performance**: Utilizes `time.monotonic()` and a time cache to minimize system calls, making `now()` and `timestamp()` calls extremely fast.
-   **Singleton Pattern**: Ensures a single, consistent time source across your entire application. The constructor runs only once.
-   **Thread-Safe**: All operations are fully thread-safe, making it suitable for multi-threaded, high-concurrency environments.
-   **Automatic Timezone Detection**: Automatically initializes to your system's local timezone on first import (requires `tzlocal`). Defaults safely to UTC if detection fails.
-   **Runtime Reconfiguration**: Easily change the timezone, cache interval, or update strategy on the fly with a single function call.
-   **Proactive Caching**: An optional background thread keeps the time cache warm, ensuring near-zero latency for time requests.
-   **Built-in Statistics**: Monitor performance with stats like cache hit ratio, misses, and update times.

## Project Structure

```
.
├── requirements.txt      # Project dependencies
├── src                   # Source code directory
│   ├── __init__.py
│   └── chrono.py         # The Chrono module implementation
└── tests                 # Test suite
    └── test_chrono.py    # Unit and integration tests for Chrono
```

## Installation

This module requires **Python 3.9+** (for the standard `zoneinfo` library).

1.  Clone the repository:
    ```bash
    git clone <your-repo-url>
    cd <your-repo-name>
    ```

2.  Install the required dependencies. `tzlocal` is recommended for automatic timezone detection.
    ```bash
    pip install -r requirements.txt
    ```

## Usage Patterns

Chrono's singleton design provides clear and distinct patterns for initialization and reconfiguration.

### 1. Default Initialization (Easiest)

For most use cases, simply import the pre-initialized `chrono` instance or the convenience functions. It automatically configures itself to your system's timezone.

```python
from src.chrono import now, timestamp, strftime

# The instance is configured automatically on the first import.

# Get the current time as a datetime object
current_datetime = now()
print(f"Current Datetime: {current_datetime.isoformat()}")

# Get the current time as a Unix timestamp
current_ts = timestamp()
print(f"Current Timestamp: {current_ts}")

# Format the current time
print(f"Formatted Time: {strftime('%Y-%m-%d %H:%M:%S %Z')}")
```

### 2. Custom Initialization (At Application Startup)

To start your application with a specific configuration (e.g., in a server environment), call the `Chrono` constructor with your desired settings.

**Important**: This only works on the **very first access** to the `Chrono` module in your application's lifecycle. Subsequent calls to `Chrono(...)` will be ignored.

```python
from src.chrono import Chrono, now

# This line should be run once at the very start of your application.
# It creates the singleton instance with a specific configuration.
chrono_instance = Chrono(
    timezone_str="Asia/Seoul",
    cache_interval_ms=50,
    background_update=True
)

print(f"Custom Initialized Time (Seoul): {now()}")
```

### 3. Runtime Reconfiguration (Recommended)

To change the configuration after initialization, **always** use the `reconfigure_chrono()` function. This is the correct and thread-safe way to alter the singleton's behavior at runtime.

```python
from src.chrono import reconfigure_chrono, now, get_chrono_stats

print(f"Original Timezone: {get_chrono_stats()['timezone']}")

# Reconfigure to a new timezone
reconfigure_chrono(timezone_str="America/New_York")

print(f"New Timezone: {get_chrono_stats()['timezone']}")
print(f"New York Time: {now().isoformat()}")
```

## Monitoring with Statistics

You can retrieve performance and configuration statistics at any time to monitor the utility's health and performance.

```python
from src.chrono import get_chrono_stats
import json

stats = get_chrono_stats()
print(json.dumps(stats, indent=2))

# Example output:
# {
#   "timezone": "America/New_York",
#   "cache_interval_ms": 50,
#   "background_update_enabled": true,
#   "is_configured": true,
#   "cache_hits": 1052,
#   "cache_misses": 5,
#   "cache_hit_ratio": "99.53%",
#   "last_cache_update_time": "2025-08-21T10:30:00.123456-04:00",
#   "background_thread_alive": true
# }
```

## Running Tests

The module includes a comprehensive test suite to ensure its reliability, thread safety, and performance.

```bash
# From the project root directory
python tests/test_chrono.py
```
