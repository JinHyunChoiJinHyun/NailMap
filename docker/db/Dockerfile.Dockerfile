# PostGIS 이미지에 pgvector 확정을 추가한 DB 이미지
FROM postgis/postgis:17-3.5

# pgvector 패키지 설치 및 APT 패키지 목록 정리
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-pgvector \
    && rm -rf /var/lib/apt/lists/*

# 환경변수 설정
ENV TZ=Asia/Seoul