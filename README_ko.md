# Chrono: 파이썬을 위한 고성능 시간 유틸리티

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Chrono는 빈번한 시간 조회가 필요하지만, 반복적인 시스템 콜(system call)로 인한 성능 저하를 피하고 싶은 애플리케이션을 위해 설계된 고성능, 스레드-세이프(thread-safe) 시간 유틸리티입니다. 지능적인 캐싱 전략을 통해 표준 라이브러리의 시간 함수를 대체하며, 더 높은 정확성과 속도를 제공합니다.

## 주요 특징

-   **고성능**: `time.monotonic()`과 시간 캐시를 활용하여 시스템 콜을 최소화하고, `now()`와 `timestamp()` 호출을 극도로 빠르게 만듭니다.
-   **싱글턴 패턴**: 애플리케이션 전체에서 단 하나의 일관된 시간 소스를 보장합니다. 생성자는 단 한 번만 실행됩니다.
-   **스레드-세이프 (Thread-Safe)**: 모든 연산이 스레드에 안전하여, 멀티스레드 및 동시성(concurrency) 환경에 완벽하게 적합합니다.
-   **자동 타임존 감지**: 첫 `import` 시 시스템의 로컬 타임존으로 자동 초기화됩니다 (`tzlocal` 필요). 감지 실패 시 안전하게 'UTC'로 대체됩니다.
-   **런타임 재구성**: 애플리케이션 재시작 없이 단일 함수 호출로 타임존, 캐시 주기, 업데이트 전략을 즉시 변경할 수 있습니다.
-   **선제적 캐싱**: 백그라운드 스레드 옵션을 통해 시간 캐시를 항상 최신 상태로 유지하여, 시간 요청에 대한 지연 시간(latency)을 거의 0에 가깝게 만듭니다.
-   **내장된 통계 기능**: 캐시 히트 비율, 실패 횟수, 마지막 업데이트 시간 등 성능 관련 통계를 쉽게 모니터링할 수 있습니다.

## 프로젝트 구조

```
.
├── requirements.txt      # 프로젝트 의존성 파일
├── src                   # 소스 코드 디렉토리
│   ├── __init__.py
│   └── chrono.py         # Chrono 모듈 구현체
└── tests                 # 테스트 스위트
    └── test_chrono.py    # Chrono 모듈에 대한 단위/통합 테스트
```

## 설치

이 모듈은 **Python 3.9 이상** 버전이 필요합니다 (표준 라이브러리 `zoneinfo` 사용).

1.  저장소를 클론합니다:
    ```bash
    git clone <your-repo-url>
    cd <your-repo-name>
    ```

2.  필요한 의존성을 설치합니다. 자동 타임존 감지를 위해 `tzlocal` 설치를 권장합니다.
    ```bash
    pip install -r requirements.txt
    ```

## 사용 패턴

Chrono의 싱글턴 디자인은 초기화와 재구성을 위한 명확하고 직관적인 패턴을 제공합니다.

### 1. 기본 초기화 (가장 쉬운 방법)

대부분의 경우, 미리 초기화된 `chrono` 인스턴스나 편의 함수를 `import`하여 바로 사용하면 됩니다. 시스템 타임존으로 자동 설정됩니다.

```python
from src.chrono import now, timestamp, strftime

# 첫 import 시 인스턴스가 자동으로 생성 및 설정됩니다.

# 현재 시간을 datetime 객체로 가져오기
current_datetime = now()
print(f"현재 Datetime: {current_datetime.isoformat()}")

# 현재 시간을 Unix 타임스탬프로 가져오기
current_ts = timestamp()
print(f"현재 Timestamp: {current_ts}")

# 현재 시간 포맷팅하기
print(f"포맷팅된 시간: {strftime('%Y-%m-%d %H:%M:%S %Z')}")
```

### 2. 사용자 정의 초기화 (애플리케이션 시작 시)

서버 환경 등 특정 설정으로 애플리케이션을 시작하고 싶을 때, `Chrono` 생성자를 원하는 설정값과 함께 호출합니다.

**중요**: 이 방식은 애플리케이션 생명주기에서 `Chrono` 모듈에 **가장 처음 접근할 때 단 한 번만** 동작합니다. 이후의 `Chrono(...)` 호출은 무시됩니다.

```python
from src.chrono import Chrono, now

# 이 코드는 애플리케이션 시작점에 단 한 번만 실행되어야 합니다.
# 특정 설정으로 싱글턴 인스턴스를 생성합니다.
chrono_instance = Chrono(
    timezone_str="Asia/Seoul",
    cache_interval_ms=50,
    background_update=True
)

print(f"사용자 정의 초기화 시간 (서울): {now()}")
```

### 3. 런타임 재구성 (권장 방식)

초기화 이후 설정을 변경하려면, **항상** `reconfigure_chrono()` 함수를 사용하세요. 이 방법이 런타임에 싱글턴의 동작을 변경하는 가장 정확하고 스레드-세이프한 방법입니다.

```python
from src.chrono import reconfigure_chrono, now, get_chrono_stats

print(f"기존 타임존: {get_chrono_stats()['timezone']}")

# 새로운 타임존으로 재구성
reconfigure_chrono(timezone_str="America/New_York")

print(f"새 타임존: {get_chrono_stats()['timezone']}")
print(f"뉴욕 시간: {now().isoformat()}")
```

## 통계 기능으로 모니터링

언제든지 성능 및 설정 통계를 조회하여 유틸리티의 상태와 성능을 모니터링할 수 있습니다.

```python
from src.chrono import get_chrono_stats
import json

stats = get_chrono_stats()
print(json.dumps(stats, indent=2, ensure_ascii=False))

# 출력 예시:
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

## 테스트 실행

이 모듈은 신뢰성, 스레드 안전성, 성능을 보장하기 위한 포괄적인 테스트 스위트를 포함하고 있습니다.

```bash
# 프로젝트 최상위 디렉토리에서 실행
python tests/test_chrono.py
```
