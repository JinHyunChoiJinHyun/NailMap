# 수집 계층 - API를 호출에 DataFrame을 반환
from dataclasses import dataclass

import logging
import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Any

import pandas as pd
import json
from pathlib import Path

log = logging.getLogger("collector")

SEOUL_CODE = "11"
NAIL_KEYWORD = "네일"
BASE_PATH = Path(__file__).resolve().parent.parent

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
    session = requests.Session() # HTTP 통신 세션 객체 생성
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session

def request_json(session:requests.Session, url:str, params:dict | None = None, label:str = "") -> dict:
    res = session.get(url, params=params, timeout=60)
    res.raise_for_status
    try:
        return res.json()
    except ValueError:
        raise ApiError(f"[{label}] JSON 형식이 아닙니다: {res.text[:300]}")

# 입력된 오류 발생
class ApiError(RuntimeError):
    pass

# ---------------------------------------------------------------------------
# 1) SEMAS (소상공인시장진흥공단) 상가 정보 API (업소 목록, 업종 분류, 좌표 등)
# ---------------------------------------------------------------------------

class SemasStoreClient:
    BASE_URL = "https://apis.data.go.kr/B553077/api/open/sdsc2"
    PAGE_SIZE = 1000
    NAIL_SHOP_CODE = "S20703" # 추후 다른 업종으로 확장 시 dict로 모든 코드 저장 후 조회 예정

    def __init__(self, api_key:str, session: requests.Session | None = None):
        self.key = api_key
        self.session = session or build_session() # 하나의 세션을 재사용하거나 새로 생성

    def _get(self, endpoint:str, **params:Any) -> dict:
        # 요청
        params = {
            "serviceKey": self.key,
            "type": "json",
            **params # 여러 키워드 인자를 dict로 수령
        }
        url = f"{self.BASE_URL}/{endpoint}"

        data = request_json(self.session, url, params, endpoint)

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

    def fetch_all_rows(self, div_id:str, key:str, **filters:str) -> pd.DataFrame:
        rows, page = [], 1
        while True:
            body = self._get("storeListInDong", div_id=div_id, key=key,pageNo=page,
                             numOfRows=self.PAGE_SIZE, **filters)
            rows += body.get("items", [])
            totalCount = int(body.get("totalCount", 0))

            # 페이지의 모든 항목을 조회했거나 더 이상 조회할 항목이 없으면 반복 종료
            if page * self.PAGE_SIZE >= totalCount:
                break

            page += 1
            time.sleep(0.2)
        return pd.DataFrame(rows)

    def fetch_seoul_nail_shop(self) -> pd.DataFrame:
        # rows = list(self.iter_stores("ctprvnCd", SEOUL_CODE, indsSclsCd=self.NAIL_SHOP_CODE))
        df = self.fetch_all_rows("ctprvnCd", SEOUL_CODE, indsSclsCd=self.NAIL_SHOP_CODE)
        if df.empty:
            return df
        df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
        df["lat"] = pd.to_numeric(df["lat"], errors="coerce")

        return df.drop_duplicates("bizesId").reset_index(drop=True)

# ---------------------------------------------------------------------------
# 2) 서울 열린데이터광장 상권분석서비스 API (추정 매출, 유동·상주·직장인구, 점포 수, 개·폐업 등)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SeoulDataset:
    name:str
    endpoint: str
    quarterly: bool
    nail_only: bool

SEOUL_DATASETS = [
    # ── 공간 경계 ─────────────────────────────────────────────────────────────
    # SeoulDataset("trdar_area",      "TbgisTrdarRelm",         quarterly=False, nail_only=False),  # 영역-상권 (상권 경계·좌표)

    # ── 행정동 단위: 서울 전체를 빈틈없이 비교하는 기본 단위 ──────────────────
    SeoulDataset("adstrd_sales",    "VwsmAdstrdSelngW",       quarterly=True,  nail_only=True),   # 추정매출-행정동
    SeoulDataset("adstrd_stores",   "VwsmAdstrdStorW",        quarterly=True,  nail_only=True),   # 점포-행정동 (점포수·개폐업·프랜차이즈)
    SeoulDataset("adstrd_flpop",    "VwsmAdstrdFlpopW",       quarterly=True,  nail_only=False),  # 길단위인구-행정동
    SeoulDataset("adstrd_repop",    "VwsmAdstrdRepopW",       quarterly=True,  nail_only=False),  # 상주인구-행정동
    SeoulDataset("adstrd_wrcpop",   "VwsmAdstrdWrcPopltnW",   quarterly=True,  nail_only=False),  # 직장인구-행정동
    SeoulDataset("adstrd_income",   "VwsmAdstrdNcmCnsmpW",    quarterly=True,  nail_only=False),  # 소득소비-행정동
    SeoulDataset("adstrd_fclty",    "VwsmAdstrdFcltyW",       quarterly=True,  nail_only=False),  # 집객시설-행정동
    SeoulDataset("adstrd_change_ix", "VwsmAdstrdIxQq",        quarterly=True,  nail_only=False),  # 상권변화지표-행정동 (성장/쇠퇴 등급)
    SeoulDataset("adstrd_apt",       "VwsmAdstrdAptW",        quarterly=True,  nail_only=False),  # 아파트-행정동
    
    # ── 상권 단위: 지정 상권이 있는 곳의 상세 분석용 ─────────────────────────
    # SeoulDataset("trdar_sales",     "VwsmTrdarSelngQq",       quarterly=True,  nail_only=True),   # 추정매출-상권
    # SeoulDataset("trdar_stores",    "VwsmTrdarStorQq",        quarterly=True,  nail_only=True),   # 점포-상권 (점포수·개폐업·프랜차이즈)
    # SeoulDataset("trdar_flpop",     "VwsmTrdarFlpopQq",       quarterly=True,  nail_only=False),  # 길단위인구-상권
    # SeoulDataset("trdar_repop",     "VwsmTrdarRepopQq",       quarterly=True,  nail_only=False),  # 상주인구-상권
    # SeoulDataset("trdar_wrcpop",    "VwsmTrdarWrcPopltnQq",   quarterly=True,  nail_only=False),  # 직장인구-상권
    # SeoulDataset("trdar_income",    "VwsmTrdarNcmCnsmpQq",    quarterly=True,  nail_only=False),  # 소득소비-상권
    # SeoulDataset("trdar_facility",  "VwsmTrdarFcltyQq",       quarterly=True,  nail_only=False),  # 집객시설-상권 (지하철역·대학·백화점 등)
    # SeoulDataset("trdar_change_ix", "VwsmTrdarIxQq",          quarterly=True,  nail_only=False),  # 상권변화지표-상권 (성장/쇠퇴 등급)
    # SeoulDataset("trdar_apt",       "InfoTrdarAptQq",         quarterly=True,  nail_only=False),  # 아파트-상권
]

class SeoulOpenApiClient:
    BASE_URL = "http://openapi.seoul.go.kr:8088"
    PAGE_SIZE = 1000

    def __init__(self, api_key:str, session:requests.Session | None = None):
        self.key = api_key
        self.session = session or build_session()

    def _get(self, endpoint:str, start:int, end:int, *path_args:str) -> dict:
        # 요청
        url = "/".join([self.BASE_URL, self.key, "json", endpoint, str(start), str(end), *path_args])
        data = request_json(session=self.session, url=url, label=endpoint)

        # 오류 발생 처리
        if endpoint not in data: # 오류 발생 시 서비스 키워드 없이 RESULT만 반환
            res = data.get("RESULT", {})
            # 해당 데이터가 없는 경우
            if res.get("CODE") == "INFO-200": 
                return {"list_total_count": 0, "row": []}
            raise ApiError(f"[{endpoint}] {res.get("CODE")} {res.get("MESSAGE")}")

        # 정상 처리
        return data[endpoint]

    # API 전체 데이터 조회 함수
    def fetch_all_rows(self, endpoint:str, *path_args:str) -> pd.DataFrame:
        rows, start = [], 1
        while True:
            body = self._get(endpoint, start, start + self.PAGE_SIZE - 1, *path_args)
            rows += body.get("row", [])
            total_count = int(body.get("list_total_count", 0))

            log.info("SEOUL %s %s (%d/%d)", endpoint, "/".join(path_args) or "-", min(start + self.PAGE_SIZE - 1, total_count), total_count)

            # 전체 데이터 조회 완료 시 반복 종료
            start += self.PAGE_SIZE
            if start > total_count:
                break
            time.sleep(0.1)

        return pd.DataFrame(rows)

    # 데이터 필터링 함수
    def fetch_dataset(self, dataset:SeoulDataset, quarter:str | None) -> pd.DataFrame:
        # 분기별 데이터인 경우 분기 파라미터 생성
        args = (quarter,) if (dataset.quarterly and quarter) else () 
        df = self.fetch_all_rows(dataset.endpoint, *args)

        # 조회 결과가 없으면 빈 df 반환
        if df.empty:
            return df

        # 요청한 분기와 일치하는 데이터만 필터링
        if dataset.quarterly and quarter and "STDR_YYQU_CD" in df.columns:
            df = df[df["STDR_YYQU_CD"].astype(str) == quarter]

        # 네일 업종 데이터만 필터링
        if dataset.nail_only and "SVC_INDUTY_CD_NM" in df.columns:
            df = df[df["SVC_INDUTY_CD_NM"].str.contains(NAIL_KEYWORD, na=False)]

        # 필터링 데이터 반환
        return df.reset_index(drop=True)

# ---------------------------------------------------------------------------
# 3) 한국부동산원 R-ONE 부동산통계 OpenAPI — 상업용부동산 임대동향조사 (임대료, 공실률 등)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RealEstateStat:
    name: str
    table_id: str

REAL_ESTATE_STATS = [
    RealEstateStat("real_estate_rent_small", "T248223134698125"), # 소규모 상가 임대료
    RealEstateStat("real_estate_vacancy_small", "T241833134686576"), # 소규모 상가 공실률
    RealEstateStat("real_estate_rent_midlarge", "T244363134858603"), # 중대형 상가 임대료
    RealEstateStat("real_estate_vacancy_midlarge", "T249633134845544"), # 중대형 상가 공실률
    RealEstateStat("real_estate_rent_aggregate", "T244913134948657"), # 집합 상가 임대료
    RealEstateStat("real_estate_vacancy_aggregate", "T243283134931290"), # 집합 상가 공실률
]

class RealEstateClient:
    """
    R-ONE OpenAPI 클라이언트.
        통계표 목록 : SttsApiTbl.do       (STATBL_ID, STATBL_NM ...)
        통계 데이터 : SttsApiTblData.do   (WRTTIME_IDTFR_ID, CLS_FULLNM, ITM_NM, DTA_VAL ...)
    응답 구조: {"<서비스>": [{"head": [{"list_total_count": N}, {"RESULT": {...}}]}, {"row": [...]}]}
    """

    BASE_URL = "https://www.reb.or.kr/r-one/openapi"
    PAGE_SIZE = 1000

    def __init__(self, api_key:str, session: requests.Session | None=None):
        self.key = api_key
        self.session = session or build_session()

    def _get(self, endpoint:str, page:int, **params: Any) -> tuple:
        # 요청
        params = {
            "KEY": self.key,
            "Type": "json",
            "pIndex": page,
            "pSize": self.PAGE_SIZE,
            **params
        }

        url = f"{self.BASE_URL}/{endpoint}.do"
        data = request_json(self.session, url, params, endpoint)

        # 오류 발생 처리
        if endpoint not in data:
            res = data.get("RESULT", {}) # 오류 시 RESULT만 반환
            # 해당 데이터가 없는 경우
            if res.get("CODE") == "INFO-200":
                return 0, []
            raise ApiError(f"[{endpoint}] {res.get("CODE")} {res.get("MESSAGE")}")
        head = data[endpoint][0]
        body = data[endpoint][1]
        return head.get("head"), body

    def fetch_all_rows(self, endpoint:str, **params:str) -> pd.DataFrame:
        rows, page = [], 1
        while True:
            head, body = self._get(endpoint, page, **params)
            rows += body.get("row",[])
            total_count = int(head[0].get("list_total_count", 0))
            log.info("Real Estate %s %s page %d (%d/%d)", 
                     endpoint, page, params.get("table_id"), min(page * self.PAGE_SIZE, total_count), total_count)
            if not body or page * self.PAGE_SIZE >= total_count:
                break
            page += 1
            time.sleep(0.2)
        return pd.DataFrame(rows)

    def fetch_dataset(self, stat:RealEstateStat, region:str = "서울", recent_period_count:int | None=None) -> pd.DataFrame:
        df = self.fetch_all_rows("SttsApiTblData", STATBL_ID=stat.table_id, DTACYCLE_CD="QY")

        # 조회 결과가 없으면 빈 df 반환
        if df.empty:
            return df

        # 입력한 region으로 시작하는 데이터만 반환 (예: "서울>도심>광화문")
        if region:
            df = df[df["CLS_FULLNM"].fillna("").str.startswith(region)]

        # 최근 N개 시점(분기)의 데이터만 반환
        if recent_period_count:
            periods = df["WRTTIME_IDTFR_ID"].astype(str) 
            recent_periods = sorted(periods.unique())[-recent_period_count:]
            df = df[periods.isin(recent_periods)]

        # DTA_VAL 값을 숫자로 변환
        df["DTA_VAL"] = pd.to_numeric(df["DTA_VAL"], errors="coerce")

        return df.reset_index(drop=True)

# ---------------------------------------------------------------------------
# 4) amddongkor - 행정동 경계 데이터 로드 (네일숍이 위치한 행정동 이름 조회)
# 출처: https://github.com/vuski/admdongkor
# ---------------------------------------------------------------------------
class AdmBoundaryLoader:
    """ admdongkor 패키지로 서울 행정동 경계 데이터 로드 """
    def __init__(self, version:str | None = None):
        import admdongkor as adk
        self.adk = adk
        self.version = version or self.adk.versions()[-1] # 재현성을 위해 버전 명시 권장 (기본값은 가장 최신 버전)

    def fetch_seoul_dong_boundaries(self) -> pd.DataFrame:
        import shapely # 공간 데이터 처리 모듈
        df = self.adk.get(self.version, "emd", crs="EPSG:4326") # emd=읍/면/동의 약자 crs=좌표계 설정

        # 서울 지역만 필터링
        df = df[df["sidocd"].astype(str) == SEOUL_CODE]

        return pd.DataFrame({
            "adm_code": df["emdcd"].astype(str).str[:8], # 행안부 행정동 코드 기준 8자리 (상권 분석과 join할 키)
            "mois_adm_code": df["emdcd"].astype(str), # 행안부 행정동 코드 (10자리)
            "stat_adm_code": df["emd8"].astype(str), # 통계청 행정동 코드 (8자리)
            "adm_name": df["emdnm"],
            "gu_name": df["sggnm"],
            "base_version": str(self.version),
            "geometry": shapely.to_geojson(df.geometry.values) # GeoJSON 문자열로 저장
        })

# ---------------------------------------------------------------------------
# 5) 건축물대장 표제부 — CSV 파일 (건물 주차대수·용도 등)
# ---------------------------------------------------------------------------
class SeoulBuildingRegisterFileLoader:
    ENCODINGS = "UTF-8"

    # 원본 필드명(국토부 건축물대장 표준 필드) → 저장 컬럼명
    COLUMNS = {
        # 건축물 식별
        "건축물대장일련번호": "building_id",

        # 도로명주소 기반 매칭
        "새주소도로코드명": "road_code",                  # 도로명코드 12자리
        "새주소지상지하구분코드명": "road_underground_code",   # 0 지상, 1 지하
        "새주소주지번": "road_main_number",                   # 건물본번
        "새주소부지번": "road_sub_number",                    # 건물부번

        # 지번주소 기반 매칭
        "대지위치": "address_jibun",
        "시군구코드명": "sigungu_code",
        "법정동코드명": "legal_dong_code",
        "대지구분코드명": "land_type_code",                    # 0 대지, 1 산, 2 블록
        "주지번": "jibun_main_number",
        "부지번": "jibun_sub_number",

        # 건축물 구분 및 용도
        "주부속구분코드명": "building_role_code",              # 주건축물만 센다
        "주용도코드명": "main_purpose_code",
        "기타용도내용": "other_purpose",

        # 주차 정보
        "옥내자주식대수": "parking_indoor_self",
        "옥외자주식대수": "parking_outdoor_self",
        "옥내기계식대수": "parking_indoor_mech",
        "옥외기계식대수": "parking_outdoor_mech",

        # 건물 특성
        "지상층수": "floors_above",
        "지하층수": "floors_below",
        "연면적": "total_area_m2",
        "사용승인일자": "approval_date",

        # 데이터 관리
        "데이터수집일": "base_date",
    }

    PARKING_COLUMNS = [
        "parking_indoor_self",
        "parking_outdoor_self",
        "parking_indoor_mech",
        "parking_outdoor_mech",
    ]

    PARKING_PATH = BASE_PATH/"references"/"parking_lot"

    def __init__(self, path:str | Path, encoding:str | None=None, chunksize:int = 100_000):
        self.path = self.PARKING_PATH/path
        self.encoding = encoding or self.ENCODINGS
        self.chunksize = chunksize

    # 데이터 타입 변경 함수
    def _transform(self, raw_df:pd.DataFrame) -> pd.DataFrame:
        df = raw_df.rename(columns=self.COLUMNS) # 컬럼명 변환
        df = df.apply(lambda s: s.str.strip()) # 모든 행의 앞,뒤 공백 제거

        # 데이터 타입 변환
        df[self.PARKING_COLUMNS] = df[self.PARKING_COLUMNS].apply(pd.to_numeric, errors="coerce").fillna(0).astype("int32")
        df[["floors_above", "floors_below"]] = df[["floors_above", "floors_below"]].apply(pd.to_numeric, errors="coerce").astype("Int16") # 결측치 허용
        df["total_area_m2"] = pd.to_numeric(df["total_area_m2"], errors="coerce").astype("float32")
        
        return df
    
    # 빈 행 및 중복 행 제거
    def drop_invalid_rows(self, df:pd.DataFrame) -> pd.DataFrame:
        missing = df["building_id"].isna()
        if missing.any():
            log.warning("건축물대장: 일련번호 없는 행 %d건 제외", int(missing.sum()))

        return df[~missing].drop_duplicates()

    def fetch_seoul_buildings(self) -> pd.DataFrame:

        # 파일이 없거나 아닌 경우
        if not self.path.is_file():
            raise FileNotFoundError(f"건축물대장 CSV 파일이 없습니다: {self.path}")

        # 파일 불러오기
        chunks, total_row = [], 0
        reader = pd.read_csv(
            self.path,
            usecols=list(self.COLUMNS), # 키 값에 해당하는 컬럼만 반환
            dtype=str,
            encoding=self.encoding,
            chunksize=self.chunksize # 호출마다 지정한 행 수만큼 데이터를 나누어 읽음
        )

        # chunksize만큼만 읽어와서 데이터 반환
        for chunk_num, chunk in enumerate(reader, start=1):
            # chunk 데이터 타입 변환 후 리스트에 추가
            chunks.append(self._transform(chunk))
            total_row += len(chunk)
            log.info("건축물대장 %s: %d번째 조각, 누적 %d행", self.path.name, chunk_num, total_row)

        # chunk 데이터 결합
        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame(columns=list(self.COLUMNS.values()))

        # 데이터 검증
        df = self.drop_invalid_rows(df)

        # 데이터수집일 2026-09-30 → 20260930 변환
        df["base_date"] = df["base_date"].str.replace(r"\D", "", regex=True)

        # 파일 경로 저장
        df["source_file"] = self.path.name

        # 건물별 총 주차대수 계산
        df["parking_total"] = df[self.PARKING_COLUMNS].sum(axis=1).astype("int32")

        return df.reset_index(drop=True)

# ---------------------------------------------------------------------------
# 6) 도로명주소 DB — txt 파일 (건축물대장 표제부의 건물 정보 → 행정동 매핑용)
# 출처: 행정안전부
# ---------------------------------------------------------------------------
class JusoDbLoader:
    """
        건축물대장 표제부의 주소 정보를 도로명주소 DB와 매핑해 해당 건물의 행정동 코드를 조회
        주소     : 도로명코드·지하여부·건물본번·부번  
        지번     : 법정동코드·산여부·본번·부번      
        부가정보  : 행정동 코드                      
    """
    JUSO_PATH = BASE_PATH/"references"/"juso"
    ENCODING = "cp949"

    # 도로명주소
    ROAD_ADDRESS_COLUMNS = {
        0: "management_no", # 관리번호 (pk)
        1: "road_code",     # 도로명 코드
        3: "underground_yn", # 지하 여부
        4: "building_main_no", # 건물 본번
        5: "building_sub_no", # 건물 부번
    }

    # 지번 (법정동)
    LOT_ADDRESS_COLUMNS = {
        0: "management_no", # 관리번호 (pk)
        2: "legal_dong_code", # 법정동 코드
        7: "mountain_yn", # 산 여부
        8: "lot_main_no", # 지번본번
        9: "lot_sub_no", # 지번부번
    }

    # 부가 정보 (행정동)
    ADDITIONAL_INFO_COLUMNS = {
        0: "management_no", # 관리번호 (pk)
        1: "admin_dong_code", # 행정동 코드
        2: "admin_dong_name", # 행정동 이름
    }

    # 파일명
    ROAD_ADDRESS_FILE = "road_seoul.txt"
    LOT_ADDRESS_FILE = "lot_seoul.txt"
    ADDITIONAL_INFO_FILE = "additional_info_seoul.txt"

    def __init__(self):
        self.path = self.JUSO_PATH

    def _read(self, file_name:str, columns: dict[int, str]) -> pd.DataFrame:
        path = self.path/file_name

        # 파일이 존재하지 않을 시
        if not path.is_file():
            raise FileNotFoundError(f"도로명주소 DB 파일이 없습니다: {path}")

        # with open(path, "rb") as f:
        #     data = f.read()
        #     start = 39
        #     end = 50
        #     print(data[start:end].decode("utf-8",errors="replace"))

        # 파일 존재할 시
        df = pd.read_csv(
            path,
            sep="|",
            header=None,
            usecols=list(columns),
            dtype=str,
            encoding=self.ENCODING
        )
        df = df.rename(columns=columns)

        if df.empty:
            log.warning("도로명주소 DB %s: 읽은 행이 없습니다", file_name)

        return df

    def _filter_seoul(self,file_name:str, columns:dict[int,str], code_column:str) -> pd.DataFrame:
        # 파일 read
        df = self._read(file_name, columns)
        
        # 서울 코드로 시작하는 행만 필터링
        df = df[df[code_column].str.startswith(SEOUL_CODE, na=False)]

        # 빈 값 검증
        if df.empty:
            raise ValueError(f"{file_name}: '{code_column}이 서울 코드로 시작하는 행이 없습니다. {columns}의 인덱스 번호를 확인하세요")
        return df

    # 건축물대장 건물의 도로명 주소와 매핑
    def fetch_road_address(self) -> pd.DataFrame:
        return self._filter_seoul(self.ROAD_ADDRESS_FILE, self.ROAD_ADDRESS_COLUMNS, "road_code")

    # 도로명 주소가 없는 건물일 경우 PNU(필지 고유번호)로 매핑
    def fetch_legal_dong(self) -> pd.DataFrame:
        return self._filter_seoul(self.LOT_ADDRESS_FILE, self.LOT_ADDRESS_COLUMNS, "legal_dong_code")

    def fetch_admin_dong(self) -> pd.DataFrame:
        return self._filter_seoul(self.ADDITIONAL_INFO_FILE, self.ADDITIONAL_INFO_COLUMNS, "admin_dong_code")

    def build_address(self) -> pd.DataFrame:
        road = self.fetch_road_address()
        legal = self.fetch_legal_dong()
        admin = self.fetch_admin_dong()

        df = road.merge(
            admin,
            on="management_no",
            how="left",
            validate="one_to_one" # 중복 없는 1:1 관계인지 검증
        )

        assert len(df) == len(road) # 조건이 거짓이면 에러 발생

        df = df.merge(
            legal,
            on="management_no",
            how="left",
            validate="one_to_many" # 오른쪽 key 중복 허용 (여러 지번 정보 연결 가능)
        )

        return df