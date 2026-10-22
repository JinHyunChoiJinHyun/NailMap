import os
from dotenv import load_dotenv

from clients.Fetchers import build_session, SemasStoreClient, SeoulOpenApiClient, SEOUL_DATASETS, RealEstateClient, REAL_ESTATE_STATS, AdmBoundaryLoader, SeoulBuildingRegisterFileLoader, JusoDbLoader, ParkingLoader

def require_env(name:str):
    load_dotenv()
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} 환경 변수가 필요합니다.")
    return value

def main():

    session = build_session()
    # semas = SemasStoreClient(require_env("SEMAS_STORE_API_KEY"),session)
    # seoul_nail_shop = semas.fetch_seoul_nail_shop()
    # print(seoul_nail_shop)

    # seoul = SeoulOpenApiClient(require_env("SEOUL_DATA_API_KEY"), session)
    # for dataset in SEOUL_DATASETS:
    #     seoul_data = seoul.fetch_dataset(dataset,"20262")
    #     print(dataset.name)
    #     print(seoul_data)

    # real_estate = RealEstateClient(require_env("REAL_ESTATE_API_KEY"), session)
    # for dataset in REAL_ESTATE_STATS:
    #     real_estate_data = real_estate.fetch_dataset(dataset,"서울",2)
    #     print(dataset.name)
    #     print(real_estate_data)

    # boundary = AdmBoundaryLoader("20260701")
    # print(boundary.fetch_seoul_dong_boundaries())

    # building = SeoulBuildingRegisterFileLoader("서울시_건축물대장_표제부.csv","CP949")
    # print(building.fetch_seoul_buildings())

    # juso = JusoDbLoader()
    # print(juso.build_address())

    parking = ParkingLoader("parking.csv")
    print(parking.fetch_seoul_parking_lots())

if __name__ == "__main__":
    main()