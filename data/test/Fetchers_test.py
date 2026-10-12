import os
from dotenv import load_dotenv

from common.Fetchers import SemasStoreClient, build_session

def require_env(name:str):
    load_dotenv()
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} 환경 변수가 필요합니다.")
    return value

session = build_session()
semas = SemasStoreClient(require_env("SEMAS_STORE_API_KEY"),session)
seoul_nail_shop = semas.fetch_seoul_nail_shop()
print(seoul_nail_shop)
