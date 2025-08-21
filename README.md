# Chrono: A High-Performance Time Utility for Python

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Chrono is a high-performance, thread-safe time utility designed for applications that require frequent time lookups without the performance overhead of repeated system calls. It serves as a drop-in, enhanced alternative to standard library time functions, providing higher accuracy and speed through intelligent caching.

## Key Features

-   **High Performance**: Utilizes `time.monotonic()` and a time cache to minimize system calls, making `now()` and `timestamp()` calls extremely fast.
-   **Singleton Pattern**: Ensures a single, consistent time source across your entire application.
-   **Thread-Safe**: All operations are fully thread-safe, making it suitable for multi-threaded environments.
-   **Automatic Timezone Detection**: Automatically initializes to your system's local timezone on first import (requires `tzlocal`). Defaults safely to UTC if detection fails.
-   **Runtime Reconfiguration**: Easily change the timezone, cache interval, or update strategy on the fly without restarting the application.
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

## Quick Start

Chrono is designed for immediate use. Simply import the pre-initialized `chrono` instance.

```python
from src.chrono import chrono, now, timestamp

# The 'chrono' instance is automatically configured to your system's timezone.

# 1. Get the current time as a datetime object
current_datetime = chrono.now()
print(f"Current Datetime: {current_datetime}")

# 2. Get the current time as a Unix timestamp
current_ts = chrono.timestamp()
print(f"Current Timestamp: {current_ts}")

# 3. Use convenience functions for global access
print(f"Global now(): {now()}")
```

## Advanced Usage

### Explicit Configuration (Recommended for Servers)

For production environments, it's best practice to explicitly set the timezone to ensure consistent behavior.

```python
from src.chrono import reconfigure_chrono, now

# Reconfigure at application startup
reconfigure_chrono(
    timezone_str="UTC",
    cache_interval_ms=20,
    background_update=True
)

print(f"Server time (UTC): {now()}")
```

### Monitoring with Statistics

You can retrieve performance and configuration statistics at any time.

```python
from src.chrono import get_chrono_stats
import json

stats = get_chrono_stats()
print(json.dumps(stats, indent=2))

# Example output:
# {
#   "timezone": "UTC",
#   "cache_interval_ms": 20,
#   "background_update_enabled": true,
#   "is_initialized": true,
#   "cache_hits": 1052,
#   "cache_misses": 5,
#   "cache_hit_ratio": "99.53%",
#   ...
# }
```

## Running Tests

The module includes a comprehensive test suite to ensure its reliability and performance.

```bash
# From the project root directory
python tests/test_chrono.py
```
