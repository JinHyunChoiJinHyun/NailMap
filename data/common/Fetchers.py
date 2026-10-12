# 수집 계층 - API를 호출에 DataFrame을 반환
import logging
import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Any, Iterator

import pandas as pd

log = logging.getLogger("collector")

SEOUL_CODE = "11"

# ---------------------------------------------------------------------------
# 공통 HTTP 세션 (재시도 + 타임아웃)
# ---------------------------------------------------------------------------
def build_session() -> requests.Session:
    retry = Retry(
        total=5, # 재시도 횟수 설정
        backoff_factor=1.0, # 재시도 사이 대기시간 설정
        status_forcelist=(429,500,502,503,504), # 재시도 대상 HTTP 상태 코드
        allowed_methods=("GET",),
    )
    s = requests.Session() # HTTP 통신 세션 객체 생성
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s

# 입력된 오류 발생
class ApiError(RuntimeError):
    pass

# ---------------------------------------------------------------------------
# 1) 소상공인시장진흥공단 상가(상권)정보 API (상가 좌표 정보)
# ---------------------------------------------------------------------------

class SemasStoreClient:
    BASE = "https://apis.data.go.kr/B553077/api/open/sdsc2"
    PAGE_SIZE = 1000
    NAIL_SHOP_CODE = "S20703" # 추후 다른 업종으로 확장 시 dict로 모든 코드 저장 후 조회 예정

    def __init__(self, service_key:str, session: requests.Session | None = None):
        self.key = service_key
        self.s = session or build_session() # 하나의 세션을 재사용하거나 새로 생성

    def _get(self, endpoint:str, **params:Any) -> dict:
        params = {
            "serviceKey": self.key,
            "type": "json",
            **params # 여러 키워드 인자를 dict로 수령
        }

        res = self.s.get(f"{self.BASE}/{endpoint}", params=params, timeout=30)
        res.raise_for_status()

        try:
            data = res.json()
        except ValueError:
            raise ApiError(f"[{endpoint}] JSON 형식이 아닙니다: {res.text[:300]}")

        # 상태 코드 조회
        header = data.get("header", {})
        code = header.get("resultCode")

        # 데이터가 빈 경우 03 반환
        if code == "03": 
            return {"items": [], "totalCount": 0}

        # 정상 반환인 경우 00 반환
        if code != "00": 
            raise ApiError(f"[{endpoint}] {code} {header.get("resultMsg")}")

        return data.get("body", {})

    def iter_stores(self, div_id:str, key:str, **filters:str) -> Iterator[dict]:
        page = 1
        while True:
            body = self._get("storeListInDong", div_id=div_id, key=key,pageNo=page,
                             numOfRows=self.PAGE_SIZE, **filters)
            items = body.get("items", [])
            yield from items # 요소를 하나하나씩 반환
            totalCount = int(body.get("totalCount", 0))

            # 페이지의 모든 항목을 조회했거나 더 이상 조회할 항목이 없으면 반복 종료
            if page * self.PAGE_SIZE >- totalCount or not items:
                break

            page += 1
            time.sleep(0.2)

    def fetch_seoul_nail_shop(self) -> pd.DataFrame:
        rows = list(self.iter_stores("ctprvnCd", SEOUL_CODE, indsSclsCd=self.NAIL_SHOP_CODE))
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
        df["lat"] = pd.to_numeric(df["lat"], errors="coerce")

        return df.drop_duplicates("bizesId").reset_index(drop=True)

# ---------------------------------------------------------------------------
# 2) 서울 열린데이터광장 상권분석서비스 API (상권 매출, 수, 유동인구 등 집계)
# ---------------------------------------------------------------------------



