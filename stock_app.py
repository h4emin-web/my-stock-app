import streamlit as st
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta
import requests
import time

# 1. 모바일 앱 환경 설정
st.set_page_config(
    page_title="해민증권",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 모바일용 UI 스타일링
st.markdown("""
    <style>
    .block-container { padding-top: 1.5rem; padding-left: 1rem; padding-right: 1rem; }
    .stTabs [data-baseweb="tab"] { font-size: 18px; font-weight: bold; flex: 1; text-align: center; }
    .stSelectbox label { font-size: 14px; font-weight: bold; }
    [data-testid="stDataFrame"] td { height: 45px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 유틸리티 함수 ---
def format_korean_unit(val):
    if pd.isna(val) or val == 0: return "-"
    if val >= 1000000000000: return f"{int(val // 1000000000000)}조"
    return f"{int(val // 100000000):,}억"

# --- 암호화폐 데이터 (업비트) ---
@st.cache_data(ttl=30)
def get_crypto_data():
    try:
        # 업비트 KRW 마켓 전체 조회
        m_url = "https://api.upbit.com/v1/market/all"
        m_res = requests.get(m_url, timeout=5)
        m_data = m_res.json()
        
        # 주요 시총 상위권 코인 리스트 (수동 지정하여 안정성 확보)
        target_list = ["KRW-BTC", "KRW-ETH", "KRW-SOL", "KRW-XRP", "KRW-STX", "KRW-DOGE", "KRW-AVAX", "KRW-ADA", "KRW-LINK", "KRW-SHIB", "KRW-DOT", "KRW-TRX", "KRW-NEAR", "KRW-MATIC", "KRW-ETC", "KRW-ALGO", "KRW-AAVE", "KRW-EGLD", "KRW-SAND", "KRW-EOS"]
        
        name_dict = {d['market']: d['korean_name'] for d in m_data if d['market'] in target_list}
        t_url = f"https://api.upbit.com/v1/ticker?markets={','.join(target_list)}"
        t_res = requests.get(t_url, timeout=5)
        t_data = t_res.json()
        
        res = []
        for d in t_data:
            res.append({
                '코인명': name_dict.get(d['market'], d['market']),
                '현재가': d['trade_price'],
                '전일대비': d['signed_change_rate'] * 100,
                '거래대금': d['acc_trade_price_24h']
            })
        
        df = pd.DataFrame(res).sort_values(by='거래대금', ascending=False)
        df.insert(0, 'No', range(1, len(df) + 1))
        return df
    except Exception as e:
        return pd.DataFrame()

# --- 주식 데이터 (pykrx) ---
@st.cache_data(ttl=600)
def get_stock_data(mode, date_s, market):
    try:
        # 1. 지정한 날짜의 전체 시세 정보 가져오기
        df = stock.get_market_ohlcv_by_ticker(date_s, market=market)
        if df.empty:
            # 해당 날짜 데이터가 없으면 전날 데이터 시도
            prev_date = (datetime.strptime(date_s, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
            df = stock.get_market_ohlcv_by_ticker(prev_date, market=market)
            date_s = prev_date
            
        df_cap = stock.get_market_cap_by_ticker(date_s, market=market)
        
        if mode == "거래대금 상위":
            df = df.sort_values(by='거래대금', ascending=False).head(50)
        elif mode == "상한가":
            df = df[df['등락률'] >= 29.5]
        elif mode == "하한가":
            df = df[df['등락률'] <= -29.5]
        
        # 결과 리스트 생성
        res = []
        for t in df.index:
            try:
                res.append({
                    '기업명': stock.get_market_ticker_name(t),
                    '시총_v': df_cap.loc[t, '시가총액'],
                    '등락률': df.loc[t, '등락률'],
                    '대금_v': df.loc[t, '거래대금']
                })
            except: continue
            
        return pd.DataFrame(res).sort_values(by='대금_v', ascending=False)
    except:
        return pd.DataFrame()

# --- 앱 메인 UI ---
st.title("해민증권🧑‍💼")

# 날짜 설정 (최근 영업일 자동 탐색)
try:
    init_date = stock.get_nearest_business_day_in_a_week()
except:
    init_date = datetime.now().strftime("%Y%m%d")

col1, col2 = st.columns([1, 1.2])
with col1:
    d_input = st.date_input("날짜", datetime.strptime(init_date, "%Y%m%d"))
    date_s = d_input.strftime("%Y%m%d")
with col2:
    mode = st.selectbox("분석 모드", ["거래대금 상위", "상한가", "하한가", "암호화폐"])

st.divider()

if mode == "암호화폐":
    with st.spinner("코인 시세 불러오는 중..."):
        c_data = get_crypto_data()
    
    if c_data.empty:
        st.error("암호화폐 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요.")
    else:
        c_data['현재가'] = c_data['현재가'].apply(lambda x: f"{x:,.0f}" if x >= 100 else f"{x:,.2f}")
        c_data['거래대금'] = c_data['거래대금'].apply(format_korean_unit)
        st.dataframe(
            c_data.style.map(lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''), subset=['전일대비'])
            .format({'전일대비': '{:.1f}%'}),
            use_container_width=True, height=750, hide_index=True
        )
else:
    t1, t2 = st.tabs(["KOSPI", "KOSDAQ"])
    for tab, mkt in zip([t1, t2], ["KOSPI", "KOSDAQ"]):
        with tab:
            with st.spinner(f"{mkt} 데이터 로드 중..."):
                data = get_stock_data(mode, date_s, mkt)
            
            if data.empty:
                st.info("선택하신 날짜는 장이 열리지 않았거나 데이터가 없습니다.")
            else:
                data.insert(0, 'No', range(1, len(data) + 1))
                data['시총'] = data['시총_v'].apply(format_korean_unit)
                data['대금'] = data['대금_v'].apply(format_korean_unit)
                st.dataframe(
                    data[['No', '기업명', '시총', '등락률', '대금']].style.map(lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''), subset=['등락률'])
                    .format({'등락률': '{:.1f}%'}),
                    use_container_width=True, height=600, hide_index=True
                )
