from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta

def get_valid_date():
    # 데이터가 있을 때까지 하루씩 뒤로 가며 영업일을 찾습니다.
    target_date = datetime.now()
    for _ in range(10):  # 최대 10일 전까지 탐색
        date_str = target_date.strftime("%Y%m%d")
        # 해당 날짜에 코스피 종목 리스트가 있는지 확인
        tickers = stock.get_market_ticker_list(date_str, market="KOSPI")
        if len(tickers) > 0:
            return date_str
        target_date -= timedelta(days=1)
    return datetime.now().strftime("%Y%m%d")

def save_market_data():
    search_date = get_valid_date()
    print(f"[{search_date}] 기준 데이터를 수집합니다...")

    markets = ["KOSPI", "KOSDAQ"]
    writer = pd.ExcelWriter(f'주식_거래대금_순위_{search_date}.xlsx', engine='xlsxwriter')

    for mnt in markets:
        # 데이터 가져오기
        df = stock.get_market_ohlcv_by_ticker(search_date, market=mnt)
        
        if df.empty:
            print(f"{mnt} 데이터를 가져오지 못했습니다.")
            continue

        # 종목명 매핑
        df['종목명'] = [stock.get_market_ticker_name(ticker) for ticker in df.index]
        
        # 거래대금 상위 50위 정렬
        df = df.sort_values(by='거래대금', ascending=False).head(50)
        
        # 보기 좋게 가공
        df['거래대금(억원)'] = (df['거래대금'] / 100_000_000).astype(int)
        df['등락률'] = df['등락률'].round(2)
        
        # 필요한 컬럼만 선택
        result = df[['종목명', '종가', '등락률', '거래대금(억원)']]
        
        # 터미널 화면에 출력
        print(f"\n--- {mnt} 상위 50위 ---")
        print(result)
        
        # 엑셀 시트로 저장
        result.to_excel(writer, sheet_name=mnt)

    writer.close()
    print(f"\n✅ 파일 저장 완료: 주식_거래대금_순위_{search_date}.xlsx")

if __name__ == "__main__":
    save_market_data()
