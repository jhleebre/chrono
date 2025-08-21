# Chrono: 고성능 Python 시간 유틸리티

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Chrono는 잦은 시간 조회가 필요하지만 반복적인 시스템 콜로 인한 성능 저하를 피하고 싶은 애플리케이션을 위해 설계된 고성능, 스레드 안전(thread-safe) 시간 유틸리티입니다. 표준 라이브러리의 시간 함수를 대체하여, 지능적인 캐싱을 통해 더 높은 정확성과 속도를 제공합니다.

## 주요 특징

-   **고성능**: `time.monotonic()`과 시간 캐시를 활용하여 시스템 콜을 최소화함으로써, `now()`와 `timestamp()` 호출을 매우 빠르게 만듭니다.
-   **싱글톤 패턴**: 애플리케이션 전체에 걸쳐 일관된 단일 시간 소스를 보장합니다.
-   **스레드 안전성**: 모든 연산은 완벽히 스레드로부터 안전하여, 멀티스레드 환경에 적합합니다.
-   **자동 타임존 감지**: 첫 임포트 시 시스템의 로컬 타임존으로 자동 초기화됩니다 (`tzlocal` 필요). 감지 실패 시 안전하게 'UTC'를 기본값으로 사용합니다.
-   **실시간 재설정**: 애플리케이션 재시작 없이 타임존, 캐시 주기, 업데이트 전략을 실시간으로 변경할 수 있습니다.
-   **선제적 캐싱**: 선택적인 백그라운드 스레드가 시간 캐시를 항상 최신으로 유지하여, 시간 요청에 대한 지연 시간을 거의 0으로 만듭니다.
-   **내장 통계**: 캐시 히트율, 미스, 업데이트 시간 등 성능 관련 통계를 모니터링할 수 있습니다.

## 프로젝트 구조

```
.
├── requirements.txt      # 프로젝트 의존성 파일
├── src                   # 소스 코드 디렉토리
│   ├── __init__.py
│   └── chrono.py     # Chrono 모듈 구현체
└── tests                 # 테스트 스위트
    └── test_chrono.py  # Chrono 모듈을 위한 단위/통합 테스트
```

## 설치 방법

이 모듈은 **Python 3.9 이상**을 필요로 합니다 (`zoneinfo` 라이브러리 사용).

1.  저장소를 클론합니다:
    ```bash
    git clone <your-repo-url>
    cd <your-repo-name>
    ```

2.  필요한 의존성을 설치합니다. 자동 타임존 감지를 위해 `tzlocal` 설치를 권장합니다.
    ```bash
    pip install -r requirements.txt
    ```

## 빠른 시작

Chrono는 바로 사용할 수 있도록 설계되었습니다. 미리 초기화된 `chrono` 인스턴스를 임포트하기만 하면 됩니다.

```python
from src.chrono import chrono, now, timestamp

# 'chrono' 인스턴스는 시스템 타임존으로 자동 설정됩니다.

# 1. 현재 시간을 datetime 객체로 얻기
current_datetime = chrono.now()
print(f"현재 시각: {current_datetime}")

# 2. 현재 시간을 유닉스 타임스탬프로 얻기
current_ts = chrono.timestamp()
print(f"현재 타임스탬프: {current_ts}")

# 3. 전역 편의 함수 사용하기
print(f"전역 now() 함수: {now()}")
```

## 고급 사용법

### 명시적 설정 (서버 환경에 권장)

운영 환경에서는 동작의 일관성을 보장하기 위해 타임존을 명시적으로 설정하는 것이 가장 좋습니다.

```python
from src.chrono import reconfigure_chrono, now

# 애플리케이션 시작 시점에 재설정
reconfigure_chrono(
    timezone_str="UTC",
    cache_interval_ms=20,
    background_update=True
)

print(f"서버 시각 (UTC): {now()}")
```

### 통계 모니터링

언제든지 성능 및 설정 관련 통계 정보를 조회할 수 있습니다.

```python
from src.chrono import get_chrono_stats
import json

stats = get_chrono_stats()
print(json.dumps(stats, indent=2, ensure_ascii=False))

# 출력 예시:
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

## 테스트 실행

모듈의 안정성과 성능을 보장하기 위해 종합적인 테스트 스위트가 포함되어 있습니다.

```bash
# 프로젝트 최상위 디렉토리에서 실행
python tests/test_chrono.py
```
