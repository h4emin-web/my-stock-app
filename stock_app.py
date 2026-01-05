import streamlit as st
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta

# 페이지 설정
st.set_page_config(page_title="주식 거래대금 상위 50", layout="wide")
st.title("📊 코스피/코스닥 거래대금 상위 50위")

@st.cache_data
def get_valid_date():
    target_date = datetime.now()
    for _ in range(10):
        date_str = target_date.strftime("%Y%m%d")
        tickers = stock.get_market_ticker_list(date_str, market="KOSPI")
        if len(tickers) > 0:
            return date_str
        target_date -= timedelta(days=1)
    return datetime.now().strftime("%Y%m%d")

def get_market_data(market_name, search_date):
    df = stock.get_market_ohlcv_by_ticker(search_date, market=market_name)
    if df.empty:
        return pd.DataFrame()

    # 종목명 추가
    df['종목명'] = [stock.get_market_ticker_name(ticker) for ticker in df.index]
    
    # 거래대금 상위 50위
    df = df.sort_values(by='거래대금', ascending=False).head(50)
    
    # 가공
    df['거래대금(억원)'] = (df['거래대금'] / 100_000_000).astype(int)
    df['등락률'] = df['등락률'].round(2)
    
    return df[['종목명', '종가', '등락률', '거래대금(억원)']].reset_index(drop=True)

# 실행 파트
search_date = get_valid_date()
st.info(f"데이터 기준일: {search_date}")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🏢 KOSPI 상위 50")
    kospi_df = get_market_data("KOSPI", search_date)
    if not kospi_df.empty:
        st.dataframe(kospi_df, height=600, use_container_width=True)

with col2:
    st.subheader("🚀 KOSDAQ 상위 50")
    kosdaq_df = get_market_data("KOSDAQ", search_date)
    if not kosdaq_df.empty:
        st.dataframe(kosdaq_df, height=600, use_container_width=True)
