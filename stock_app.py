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
    .stSelectbox label { font-size: 14px; font-weight: bold; }
    [data-testid="stDataFrame"] td { height: 45px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 유틸리티 함수 ---
def format_korean_unit(val):
    if pd.isna(val) or val == 0: return "0"
    if val >= 1000000000000: return f"{int(val // 1000000000000)}조"
    return f"{int(val // 100000000):,}억"

# --- 데이터 유효성 검사 함수 ---
def is_valid_df(df):
    """필요한 컬럼이 모두 포함되어 있는지 확인"""
    required = ['시가', '고가', '저가', '종가']
    return all(col in df.columns for col in required) and not df.empty

# --- 주식 데이터 로딩 로직 (오류 처리 강화) ---
@st.cache_data(ttl=300, show_spinner=False)
def get_data(mode, date_s, market):
    try:
        # 1. 메인 데이터 로드 및 휴장일 체크
        df_today = stock.get_market_ohlcv_by_ticker(date_s, market=market)
        
        if not is_valid_df(df_today):
            # 데이터가 없으면 가장 가까운 영업일 자동 탐색
            date_s = stock.get_nearest_business_day_in_a_week()
            df_today = stock.get_market_ohlcv_by_ticker(date_s, market=market)
            if not is_valid_df(df_today): return pd.DataFrame()

        df_cap = stock.get_market_cap_by_ticker(date_s, market=market)
        
        # 2. 영업일 리스트 확보
        start_search = (datetime.strptime(date_s, "%Y%m%d") - timedelta(days=60)).strftime("%Y%m%d")
        ohlcv_sample = stock.get_market_ohlcv_by_date(start_search, date_s, "005930")
        days = ohlcv_sample.index.strftime("%Y%m%d").tolist()
        if not days: return pd.DataFrame()

        # --- 분석 모드별 로직 ---
        if "연속 거래대금" in mode:
            n = 3 if "3일" in mode else 5
            if len(days) < n: return pd.DataFrame()
            target_days = days[-n:]
            valid_tickers = None
            total_amt_series = pd.Series(0.0, index=df_today.index)
            
            for d in target_days:
                df_day = stock.get_market_ohlcv_by_ticker(d, market=market)
                time.sleep(0.05)
                if not df_day.empty:
                    cond = df_day[df_day['거래대금'] >= 100000000000].index
                    valid_tickers = set(cond) if valid_tickers is None else valid_tickers.intersection(set(cond))
                    total_amt_series += df_day['거래대금']
            
            if not valid_tickers: return pd.DataFrame()
            
            first_day_df = stock.get_market_ohlcv_by_ticker(target_days[0], market=market)
            res = []
            for t in list(valid_tickers):
                try:
                    f_c, l_c = first_day_df.loc[t, '종가'], df_today.loc[t, '종가']
                    res.append({
                        '기업명': stock.get_market_ticker_name(t),
                        '시총_v': df_cap.loc[t, '시가총액'],
                        '등락률': ((l_c - f_c) / f_c) * 100,
                        '대금_v': total_amt_series.loc[t] / n
                    })
                except: continue
            return pd.DataFrame(res)

        elif mode == "고가놀이":
            if len(days) < 4: return pd.DataFrame()
            base_date = days[-4]
            df_base = stock.get_market_ohlcv_by_ticker(base_date, market=market)
            if not is_valid_df(df_base): return pd.DataFrame()
            
            targets = df_base[(df_base['거래대금'] >= 50000000000) & (df_base['등락률'] >= 15)].index
            res = []
            for t in targets:
                try:
                    rates = []
                    for d in days[-3:]:
                        d_data = stock.get_market_ohlcv_by_ticker(d, market=market)
                        rates.append(d_data.loc[t, '등락률'])
                    if abs(sum(rates) / 3) <= 5:
                        res.append({'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': df_today.loc[t, '등락률'], '대금_v': df_today.loc[t, '거래대금']})
                except: continue
            return pd.DataFrame(res)
        
        # ... (역헤드앤숄더, 상하한가 로직 동일) ...
        
        else: # 거래대금 상위
            df = df_today.sort_values(by='거래대금', ascending=False).head(50)
            res = [{'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': df.loc[t, '등락률'], '대금_v': df.loc[t, '거래대금']} for t in df.index]
            return pd.DataFrame(res)
            
    except Exception:
        return pd.DataFrame()

# --- 앱 메인 UI ---
st.title("Stock")

# 초기 날짜 설정
try:
    init_date_str = stock.get_nearest_business_day_in_a_week()
    default_d = datetime.strptime(init_date_str, "%Y%m%d")
except:
    default_d = datetime.now()

col1, col2 = st.columns([1, 1.2])
with col1:
    d_input = st.date_input("날짜", default_d)
    date_s = d_input.strftime("%Y%m%d")
with col2:
    mode = st.selectbox("분석 모드", ["거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "상한가", "하한가", "고가놀이", "역헤드앤숄더", "암호화폐"])

st.divider()

if mode == "암호화폐":
    with st.spinner("코인 시세를 불러오는 중..."):
        data = get_crypto_data()
    # (암호화폐 렌더링 코드 동일)
else:
    t1, t2 = st.tabs(["KOSPI", "KOSDAQ"])
    for tab, mkt in zip([t1, t2], ["KOSPI", "KOSDAQ"]):
        with tab:
            with st.spinner(f"{mkt} 데이터를 분석 중입니다..."):
                data = get_data(mode, date_s, mkt)
            
            if data is None or data.empty:
                st.warning("데이터가 없거나 분석 조건에 맞는 종목이 없습니다. (휴장일 혹은 데이터 수집 중)")
            else:
                # (데이터 테이블 렌더링 코드 동일)
                # ...
