from pathlib import Path

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

# ---------------------------------------------------------------------------
# 1) 행정동 경계 ← AdmBoundaryLoader
# ---------------------------------------------------------------------------
class AdmBoundaryRepository:
    TABLE = "source.adm-boundaries"

    def __init__(self, db:Database):
        self.db = db

    def save(self, df:pd.DataFrame) -> int:
