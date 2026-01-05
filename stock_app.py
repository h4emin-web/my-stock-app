from pykrx import stock
import pandas as pd
from datetime import datetime

def get_top_50_by_amount(market_name):
    # 1. 오늘 날짜 확인 (YYYYMMDD 형식)
    # 장 중이거나 휴일일 경우 데이터가 없을 수 있으므로 최근 영업일 데이터를 가져옵니다.
    today = datetime.now().strftime("%Y%m%d")
    
    print(f"[{market_name}] 데이터를 불러오는 중...")
    
    # 2. 지정한 시장의 전종목 시세 정보 가져오기 (종가, 대비, 등락률, 거래량, 거래대금 등)
    df = stock.get_market_ohlcv_by_ticker(today, market=market_name)
    
    # 3. 종목명 추가 (티커만으로는 알기 어렵기 때문)
    # 데이터프레임의 인덱스(티커)를 기준으로 종목명을 매핑합니다.
    df['종목명'] = [stock.get_market_ticker_name(ticker) for ticker in df.index]
    
    # 4. 거래대금(Amount) 기준 내림차순 정렬 후 상위 50개 추출
    # pykrx의 '거래대금' 단위는 '원'입니다.
    top_50 = df.sort_values(by='거래대금', ascending=False).head(50)
    
    # 5. 보기 좋게 열 순서 변경 및 거래대금 단위 변경 (억원 단위)
    top_50['거래대금(억원)'] = (top_50['거래대금'] / 100_000_000).round(1)
    result = top_50[['종목명', '종가', '등락률', '거래대금(억원)']]
    
    return result

# 실행
if __name__ == "__main__":
    try:
        # 코스피 상위 50
        kospi_50 = get_top_50_by_amount("KOSPI")
        print("\n--- KOSPI 거래대금 상위 50 ---")
        print(kospi_50)

        # 코스닥 상위 50
        kosdaq_50 = get_top_50_by_amount("KOSDAQ")
        print("\n--- KOSDAQ 거래대금 상위 50 ---")
        print(kosdaq_50)
        
    except Exception as e:
        print(f"에러 발생: {e}. 장 마감 직후나 서버 점검 시간에는 데이터를 불러오지 못할 수 있습니다.")
