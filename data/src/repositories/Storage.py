from pathlib import Path
from typing import Literal

import psycopg
import os
import logging

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
        

# ---------------------------------------------------------------------------
# 1) 행정동 경계 ← AdmBoundaryLoader
# ---------------------------------------------------------------------------
class AdmBoundaryRepository:
    TABLE = "source.adm-boundaries"

    def __init__(self, db:Database):
        self.db = db

    def save(self, df:pd.DataFrame) -> int:
        return self.db.