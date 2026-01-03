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
    [data-testid="stDataFrame"] td { height: 45px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 유틸리티 함수 ---
def format_korean_unit(val):
    if pd.isna(val) or val == 0: return "0"
    if val >= 1000000000000: return f"{int(val // 1000000000000)}조"
    return f"{int(val // 100000000):,}억"

# --- 주식 데이터 로딩 (안정성 극대화) ---
@st.cache_data(ttl=600, show_spinner=False)
def get_stock_data(mode, date_s, market):
    try:
        # [차단 회피] 데이터 요청 전 미세한 딜레이
        time.sleep(0.2)
        
        # 1. 기본 시세 로드
        df = stock.get_market_ohlcv_by_ticker(date_s, market=market)
        
        # 데이터가 없으면 최근 영업일로 한 번 더 시도
        if df is None or df.empty:
            recent_date = stock.get_nearest_business_day_in_a_week()
            df = stock.get_market_ohlcv_by_ticker(recent_date, market=market)
            date_s = recent_date
            
        if df is None or df.empty:
            return None, "거래소 서버 응답 없음 (IP 차단 의심)"

        df_cap = stock.get_market_cap_by_ticker(date_s, market=market)

        # --- 모드별 분석 ---
        if "연속 거래대금" in mode:
            n = 3 if "3일" in mode else 5
            # 과거 영업일 리스트 확보
            start_search = (datetime.strptime(date_s, "%Y%m%d") - timedelta(days=40)).strftime("%Y%m%d")
            ohlcv_sample = stock.get_market_ohlcv_by_date(start_search, date_s, "005930")
            days = ohlcv_sample.index.strftime("%Y%m%d").tolist()
            
            if len(days) < n: return None, "과거 데이터 부족"
            
            target_days = days[-n:]
            valid_tickers = None
            total_amt = pd.Series(0.0, index=df.index)
            
            for d in target_days:
                time.sleep(0.1) # 루프 내 딜레이 추가
                df_day = stock.get_market_ohlcv_by_ticker(d, market=market)
                if not df_day.empty:
                    cond = df_day[df_day['거래대금'] >= 100000000000].index
                    valid_tickers = set(cond) if valid_tickers is None else valid_tickers.intersection(set(cond))
                    total_amt += df_day['거래대금']
            
            if not valid_tickers: return None, "조건 일치 종목 없음"
            
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

        else: # 거래대금 상위
            top_df = df.sort_values(by='거래대금', ascending=False).head(50)
            res = [{'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': top_df.loc[t, '등락률'], '대금_v': top_df.loc[t, '거래대금']} for t in top_df.index]
            return pd.DataFrame(res), None

    except Exception as e:
        return None, f"오류 발생: {str(e)}"

# --- 암호화폐 데이터 ---
@st.cache_data(ttl=30)
def get_crypto_data():
    try:
        url = "https://api.upbit.com/v1/ticker?markets=KRW-BTC,KRW-ETH,KRW-SOL,KRW-XRP,KRW-DOGE,KRW-ADA,KRW-STX,KRW-AVAX,KRW-DOT" # 주요 코인 샘플
        # 실제로는 market/all로 가져오는 이전 로직 사용 가능
        m_url = "https://api.upbit.com/v1/market/all"
        m_data = requests.get(m_url, timeout=5).json()
        krw_markets = [d['market'] for d in m_data if d['market'].startswith("KRW-")]
        t_url = f"https://api.upbit.com/v1/ticker?markets={','.join(krw_markets[:30])}" # 상위 30개만
        t_data = requests.get(t_url, timeout=5).json()
        res = []
        for d in t_data:
            res.append({'코인명': d['market'], '현재가': d['trade_price'], '전일대비': d['signed_change_rate'] * 100, '거래대금': d['acc_trade_price_24h']})
        return pd.DataFrame(res).sort_values(by='거래대금', ascending=False)
    except: return pd.DataFrame()

# --- 앱 UI ---
st.title("Stock")

# 날짜 설정
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
    with st.spinner("코인 데이터 로드 중..."):
        c_data = get_crypto_data()
    if not c_data.empty:
        st.dataframe(c_data, use_container_width=True, hide_index=True)
else:
    t1, t2 = st.tabs(["KOSPI", "KOSDAQ"])
    for tab, mkt in zip([t1, t2], ["KOSPI", "KOSDAQ"]):
        with tab:
            with st.spinner(f"{mkt} 분석 중..."):
                data, err = get_stock_data(mode, date_s, mkt)
            
            if err:
                st.error(f"⚠️ {err}")
                if st.button("강제 새로고침", key=f"btn_{mkt}"):
                    st.cache_data.clear()
                    st.rerun()
            elif data is not None:
                data.insert(0, 'No', range(1, len(data) + 1))
                data['시총'] = data['시총_v'].apply(format_korean_unit)
                data['대금'] = data['대금_v'].apply(format_korean_unit)
                
                # 라벨
                l_rate = "누적 변동" if "연속" in mode else "등락률"
                l_amt = "평균 대금" if "연속" in mode else "거래대금"
                
                st.dataframe(
                    data[['No', '기업명', '시총', '등락률', '대금']].rename(columns={'등락률': l_rate, '대금': l_amt}).style.format({l_rate: '{:.1f}%'}),
                    use_container_width=True, height=500, hide_index=True
                )
