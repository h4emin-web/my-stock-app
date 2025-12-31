import streamlit as st
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta
import requests

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
    .rate-box {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 10px;
        font-weight: bold;
        font-size: 16px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 환율 데이터 가져오기 ---
def get_usd_krw():
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        response = requests.get(url)
        data = response.json()
        return data['rates']['KRW']
    except:
        return None

# --- 유틸리티 함수 ---
def format_korean_unit(val):
    if pd.isna(val) or val == 0: return "0"
    if val >= 1000000000000:
        return f"{int(val // 1000000000000)}조"
    return f"{int(val // 100000000):,}억"

@st.cache_data(ttl=600, show_spinner=False)
def get_data(mode, date_s, market):
    try:
        start_search = (datetime.strptime(date_s, "%Y%m%d") - timedelta(days=60)).strftime("%Y%m%d")
        ohlcv_sample = stock.get_market_ohlcv_by_date(start_search, date_s, "005930")
        days = ohlcv_sample.index.strftime("%Y%m%d").tolist()
        
        if mode == "역헤드앤숄더":
            df_top = stock.get_market_ohlcv_by_ticker(date_s, market=market).sort_values(by='거래대금', ascending=False).head(100)
            df_cap = stock.get_market_cap_by_ticker(date_s, market=market)
            res = []
            for t in df_top.index:
                try:
                    df_hist = stock.get_market_ohlcv_by_date(days[-30], date_s, t)['종가']
                    if len(df_hist) < 25: continue
                    part1, part2, part3 = df_hist[:10], df_hist[10:20], df_hist[20:]
                    low1, low2, low3 = part1.min(), part2.min(), part3.min()
                    if low2 < low1 and low2 < low3:
                        current_price = df_hist.iloc[-1]
                        if low3 <= current_price <= low3 * 1.07:
                            res.append({'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': df_top.loc[t, '등락률'], '대금_v': df_top.loc[t, '거래대금']})
                except: continue
            return pd.DataFrame(res).sort_values(by='대금_v', ascending=False)

        elif "연속 거래대금" in mode:
            n = 3 if "3일" in mode else 5
            if len(days) < n: return pd.DataFrame()
            target_days = days[-n:]
            valid_tickers = None
            stats_df = pd.DataFrame() 
            for d in target_days:
                df_day = stock.get_market_ohlcv_by_ticker(d, market=market)
                cond_1000b = df_day[df_day['거래대금'] >= 100000000000].index
                valid_tickers = set(cond_1000b) if valid_tickers is None else valid_tickers.intersection(set(cond_1000b))
                if stats_df.empty: stats_df = df_day[['등락률', '거래대금']]
                else:
                    stats_df['등락률'] += df_day['등락률']
                    stats_df['거래대금'] += df_day['거래대금']
            if not valid_tickers: return pd.DataFrame()
            df_cap = stock.get_market_cap_by_ticker(date_s, market=market)
            res = [{'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': stats_df.loc[t, '등락률'] / n, '대금_v': stats_df.loc[t, '거래대금'] / n} for t in list(valid_tickers)]
            return pd.DataFrame(res).sort_values(by='대금_v', ascending=False)

        elif mode == "고가놀이":
            if len(days) < 4: return pd.DataFrame()
            base_df = stock.get_market_ohlcv_by_ticker(days[-4], market=market)
            targets = base_df[(base_df['거래대금'] >= 50000000000) & (base_df['등락률'] >= 15)].index
            df_cap = stock.get_market_cap_by_ticker(date_s, market=market)
            res = []
            for t in targets:
                try:
                    rates = [stock.get_market_ohlcv_by_ticker(d, market=market).loc[t, '등락률'] for d in days[-3:]]
                    if abs(sum(rates)/3) <= 5:
                        res.append({'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': rates[-1], '대금_v': stock.get_market_ohlcv_by_ticker(date_s, market=market).loc[t, '거래대금']})
                except: continue
            return pd.DataFrame(res).sort_values(by='대금_v', ascending=False)

        elif mode in ["상한가", "하한가"]:
            df = stock.get_market_ohlcv_by_ticker(date_s, market=market)
            df_cap = stock.get_market_cap_by_ticker(date_s, market=market)
            cond = (df['등락률'] >= 29.5) if mode == "상한가" else (df['등락률'] <= -29.5)
            limit_df = df[cond]
            res = [{'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': limit_df.loc[t, '등락률'], '대금_v': limit_df.loc[t, '거래대금']} for t in limit_df.index]
            return pd.DataFrame(res).sort_values(by='대금_v', ascending=False)
        
        else: # 거래대금 상위
            df = stock.get_market_ohlcv_by_ticker(date_s, market=market).sort_values(by='거래대금', ascending=False).head(50)
            df_cap = stock.get_market_cap_by_ticker(date_s, market=market)
            res = [{'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': df.loc[t, '등락률'], '대금_v': df.loc[t, '거래대금']} for t in df.index]
            return pd.DataFrame(res)
    except: return pd.DataFrame()

# --- 앱 메인 UI ---
st.title("해민증권🧑‍💼")

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
    mode = st.selectbox("분석 모드", ["거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "상한가", "하한가", "고가놀이", "역헤드앤숄더"])

# 환율 정보 표시 영역
usd_rate = get_usd_krw()
if usd_rate:
    st.markdown(f"""<div class="rate-box">💵 현재 환율: 1$ = {usd_rate:,.2f}원</div>""", unsafe_allow_html=True)

st.divider()

t1, t2 = st.tabs(["KOSPI", "KOSDAQ"])

for tab, mkt in zip([t1, t2], ["KOSPI", "KOSDAQ"]):
    with tab:
        with st.spinner("데이터 불러오는 중..."):
            data = get_data(mode, date_s, mkt)
        
        if data.empty:
            st.info("조건에 맞는 종목이 없습니다.")
        else:
            data.insert(0, 'No', range(1, len(data) + 1))
            data['시총'] = data['시총_v'].apply(format_korean_unit)
            data['대금'] = data['대금_v'].apply(format_korean_unit)
            l_rate, l_amt = ("평균등락", "평균대금") if "연속" in mode else ("등락률", "거래대금")
            st.dataframe(
                data[['No', '기업명', '시총', '등락률', '대금']].rename(columns={'등락률': l_rate, '대금': l_amt}).style.map(
                    lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''), subset=[l_rate]
                ).format({l_rate: '{:.1f}%'}),
                use_container_width=True, height=600, hide_index=True
            )
