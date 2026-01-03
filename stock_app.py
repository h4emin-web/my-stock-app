import streamlit as st
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta
import requests
import time

# 1. 앱 설정
st.set_page_config(page_title="Stock", layout="centered", initial_sidebar_state="collapsed")
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    div[data-testid="stStatusWidget"] {display: none !important;}
    .block-container { padding-top: 1.5rem; padding-left: 1rem; padding-right: 1rem; }
    .stTabs [data-baseweb="tab"] { font-size: 18px; font-weight: bold; flex: 1; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# --- 유틸리티 함수 ---
def format_korean_unit(val):
    if pd.isna(val) or val == 0: return "0"
    if val >= 1000000000000: return f"{int(val // 1000000000000)}조"
    return f"{int(val // 100000000):,}억"

# 데이터가 유효한지(시가/고가 등 컬럼이 있는지) 확인하는 함수
def validate_stock_df(df):
    required = ['시가', '고가', '저가', '종가']
    if df is None or df.empty:
        return False
    return all(col in df.columns for col in required)

# --- 주식 데이터 로딩 로직 ---
@st.cache_data(ttl=600, show_spinner=False)
def get_stock_data(mode, date_s, market):
    try:
        # 1. 1차 시도: 사용자가 선택한 날짜
        df = stock.get_market_ohlcv_by_ticker(date_s, market=market)
        
        # 2. 2차 시도: 데이터가 없으면 최근 영업일 자동 탐색
        if not validate_stock_df(df):
            date_s = stock.get_nearest_business_day_in_a_week()
            df = stock.get_market_ohlcv_by_ticker(date_s, market=market)
            
        # 여전히 없다면 실패 반환
        if not validate_stock_df(df):
            return None, "거래소 서버에서 데이터를 가져올 수 없습니다. 잠시 후 다시 시도해 주세요."

        df_cap = stock.get_market_cap_by_ticker(date_s, market=market)

        # --- 분석 모드: 연속 거래대금 (누적 변동) ---
        if "연속 거래대금" in mode:
            n = 3 if "3일" in mode else 5
            # 과거 영업일 리스트 확보
            start_search = (datetime.strptime(date_s, "%Y%m%d") - timedelta(days=60)).strftime("%Y%m%d")
            ohlcv_sample = stock.get_market_ohlcv_by_date(start_search, date_s, "005930")
            days = ohlcv_sample.index.strftime("%Y%m%d").tolist()
            
            if len(days) < n: return None, "분석에 필요한 과거 데이터가 부족합니다."
            
            target_days = days[-n:]
            valid_tickers = None
            total_amt = pd.Series(0.0, index=df.index)
            
            for d in target_days:
                time.sleep(0.1) # 요청 간격 조절
                df_day = stock.get_market_ohlcv_by_ticker(d, market=market)
                if validate_stock_df(df_day):
                    cond = df_day[df_day['거래대금'] >= 100000000000].index
                    valid_tickers = set(cond) if valid_tickers is None else valid_tickers.intersection(set(cond))
                    total_amt += df_day['거래대금']
            
            if not valid_tickers: return None, "조건(대금 1천억 이상)을 만족하는 종목이 없습니다."
            
            first_day_df = stock.get_market_ohlcv_by_ticker(target_days[0], market=market)
            res = []
            for t in list(valid_tickers):
                try:
                    f_c, l_c = first_day_df.loc[t, '종가'], df.loc[t, '종가']
                    res.append({
                        '기업명': stock.get_market_ticker_name(t),
                        '시총_v': df_cap.loc[t, '시가총액'],
                        '등락률': ((l_c - f_c) / f_c) * 100,
                        '대금_v': total_amt.loc[t] / n
                    })
                except: continue
            return pd.DataFrame(res), None

        # --- 분석 모드: 거래대금 상위 ---
        else:
            top_df = df.sort_values(by='거래대금', ascending=False).head(50)
            res = [{'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': top_df.loc[t, '등락률'], '대금_v': top_df.loc[t, '거래대금']} for t in top_df.index]
            return pd.DataFrame(res), None

    except Exception as e:
        return None, f"시스템 오류: {str(e)}"

# --- UI 부분 ---
st.title("Stock")

try:
    init_date = stock.get_nearest_business_day_in_a_week()
    default_date = datetime.strptime(init_date, "%Y%m%d")
except:
    default_date = datetime.now()

col1, col2 = st.columns([1, 1.2])
with col1:
    d_input = st.date_input("날짜", default_date)
    date_s = d_input.strftime("%Y%m%d")
with col2:
    mode = st.selectbox("분석 모드", ["거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "암호화폐"])

st.divider()

if mode == "암호화폐":
    st.info("암호화폐 모드는 준비 중입니다.") # 기존 암호화폐 코드 유지 가능
else:
    t1, t2 = st.tabs(["KOSPI", "KOSDAQ"])
    for tab, mkt in zip([t1, t2], ["KOSPI", "KOSDAQ"]):
        with tab:
            with st.spinner(f"{mkt} 분석 중..."):
                data, err = get_stock_data(mode, date_s, mkt)
            
            if err:
                st.warning(f"💡 {err}")
            elif data is not None and not data.empty:
                data.insert(0, 'No', range(1, len(data) + 1))
                data['시총'] = data['시총_v'].apply(format_korean_unit)
                data['대금'] = data['대금_v'].apply(format_korean_unit)
                
                l_rate = "누적 변동" if "연속" in mode else "등락률"
                l_amt = "평균 대금" if "연속" in mode else "거래대금"
                
                st.dataframe(
                    data[['No', '기업명', '시총', '등락률', '대금']].rename(columns={'등락률': l_rate, '대금': l_amt}).style.map(lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''), subset=[l_rate]).format({l_rate: '{:.1f}%'}),
                    use_container_width=True, height=500, hide_index=True
                )
