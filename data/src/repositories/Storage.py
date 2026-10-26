from pathlib import Path
from typing import Literal

import psycopg
import os
import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).parent.parent / "sql" / "schema.sql"

# ---------------------------------------------------------------------------
# DB 연결 + 공통 기능
# ---------------------------------------------------------------------------
class Database:
    def __init__(self):
        #   로컬에서 실행 → localhost:5432 (도커 DB가 내 PC의 5432 포트로 열려 있음)
        #   도커에서 실행 → docker-compose.yml이 DB_HOST=db 로 바꿔줌
        self.conn = psycopg.connect(
            # 기본값 사용 가능
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            # 필수 환경변수
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            dbname=os.environ["POSTGRES_DB"],
            autocommit=True,
        )
        log.info("DB 연결 완료 (%s)", self.conn.info.host)

    def create_tables(self) -> None:
        """schema.sql 실행"""
        self.conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
        log.info("테이블 준비 완료")

    def upsert(
            self,
            table:str,
            df:pd.DataFrame,
            key_columns: list[str],
            sql_expressions: dict[str, str] | None=None,
            method: Literal["insert", "copy"] = "insert"
    ) -> int:
        """ 
        df를 테이블에 저장

        method:
            "insert" - 기본값
            "copy" - 대량 데이터 적재 시 사용 임시 테이블에 넣고 한번에 최종 테이블에 반영
        """

        # df가 빈 경우
        if df is None or df.empty:
            log.warning("%s: 저장할 데이터가 없습니다", table)
            return 0

        sql_expressions = sql_expressions or {}

        # key column 존재 여부 검증
        columns = list(df.columns)
        missing_keys = [key for key in key_columns if key not in columns]
        if missing_keys:
            raise ValueError(f"{table}: 키 컬럼 {missing_keys}이(가) 데이터에 없습니다.")
        if method == "copy" and sql_expressions:
            raise ValueError("copy 방식은 sql_expression을 지원하지 않습니다.")
        
        rows = 
    
    def _prepare_upsert_rows(
            table:str, 
            df:pd.DataFrame, 
            columns:list[str],
            key_columns:list[str]
        ) -> list[list]:
        """
        upsert에 넣을 행 준비
        - 값 정리 (_clean)
        - PK가 NULL인 행 제외 - NOT NULL 에러로 같은 transaction의 저장 전체가 취소되는 것을 방지
        - 같은 PK는 마지막 행만 남김 - 원본 데이터 중복을 로그로 확인하기 위함
        """

        # 중복 키 및 null key 제거
        key_idx = [columns.index(key) for key in key_columns] # 필요한 key index를 미리 추출해 행마다 반복 연산 감소
        unique_rows:dict[tuple,list] = {} # key를 기준으로 행 저장 (덮어쓰기로 중복 제거)
        total_rows = null_key_rows = 0

        for raw in df.itertuples(index=False, name=None): # df의 각 행을 tuple 형태로 반환
            total_rows += 1
            row = []

    def _prepare_db_value(value):
        """ 
        pandas 값을 DB에 입력할 수 있게 파이썬 자료형으로 변환 
        - 문자열 앞뒤 공백 제거 및 빈 문자열을 None으로 변환
        - 결측치를 None으로 변환
        - pandas, NumPy 자료형을 일반 파이썬 자료형으로 변환
        - 정수로 표현 가능한 실수는 정수로 변환
        """
        # 값이 None이면 별도 검사 없이 그대로 None 반환
        if value is None:
            return None

        # 문자열 앞뒤 공백 제거
        if isinstance(value, str):
            value = value.strip()
            return value or None

        # 결측치 None으로 변환 (NaN, pd.NA, NaT 등)
        if pd.api.types.is_scalar(value) and pd.isna(value): # 값이 단일 값인지 확인 후 결측값 확인
            return None

        # pandas Timestamp를 파이썬 datetime으로 변환
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime()

        # NumPy 자료형을 일반 파이썬 자료형으로 변환 (추후 작업이 필요하므로 return으로 종료 x)
        if isinstance(value, np.generic):
            value = value.item()


        

# ---------------------------------------------------------------------------
# 1) 행정동 경계 ← AdmBoundaryLoader
# ---------------------------------------------------------------------------
class AdmBoundaryRepository:
    TABLE = "source.adm-boundaries"

    def __init__(self, db:Database):
        self.db = db

    def save(self, df:pd.DataFrame) -> int:
        return self.db. 