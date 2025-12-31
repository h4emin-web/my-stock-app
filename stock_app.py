import streamlit as st
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta

# 1. 모바일 앱 환경 설정 및 테마 주입
st.set_page_config(
    page_title="해민증권",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 고급스러운 다크 테마 및 디자인 커스텀 CSS
st.markdown("""
    <style>
    /* 전체 배경색 및 폰트 설정 */
    [data-testid="stAppViewContainer"] {
        background-color: #0E1117;
    }
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
    }
    
    /* 헤더 디자인 */
    h1 {
        color: #FFFFFF;
        font-size: 24px !important;
        font-weight: 800;
        text-align: center;
        padding-bottom: 1rem;
    }

    /* 탭(KOSPI/KOSDAQ) 디자인 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #0E1117;
    }
    .stTabs [data-baseweb="tab"] {
        height: 45px;
        background-color: #1E2129;
        border-radius: 8px 8px 0px 0px;
        color: #808495;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #FF4B4B !important;
        color: white !important;
    }

    /* 데이터프레임 배경 및 가독성 */
    [data-testid="stDataFrame"] {
        background-color: #1E2129;
        border-radius: 12px;
        padding: 5px;
    }
    
    /* 필터 박스 디자인 */
    .stSelectbox, .stDateInput {
        background-color: #1E2129;
        border-radius: 10px;
    }
    label {
        color: #AEB3C7 !important;
        font-weight: 500 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 데이터 로직 (기존과 동일) ---
def format_korean_unit(val):
    if pd.isna(val) or val == 0: return "0"
    if val >= 1000000000000: return f"{int(val // 1000000000000)}조"
    return f"{int(val // 100000000):,}억"

@st.cache_data(ttl=600, show_spinner=False)
def get_data(mode, date_s, market):
    try:
        start_search = (datetime.strptime(date_s, "%Y%m%d") - timedelta(days=40)).strftime("%Y%m%d")
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
                    p1, p2, p3 = df_hist[:10], df_hist[10:20], df_hist[20:]
                    l1, l2, l3 = p1.min(), p2.min(), p3.min()
                    if l2 < l1 and l2 < l3:
                        curr = df_hist.iloc[-1]
                        if l3 <= curr <= l3 * 1.07:
                            res.append({'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': df_top.loc[t, '등락률'], '대금_v': df_top.loc[t, '거래대금']})
                except: continue
            return pd.DataFrame(res).sort_values(by='대금_v', ascending=False)

        elif "연속 거래대금" in mode:
            n = 3 if "3일" in mode else 5
            target_days = days[-n:]
            valid_tickers = None
            stats_df = pd.DataFrame() 
            for d in target_days:
                df_day = stock.get_market_ohlcv_by_ticker(d, market=market)
                cond_1000b = df_day[df_day['거래대금'] >= 100000000000].index
                valid_tickers = set(cond_1000b) if valid_tickers is None else valid_tickers.intersection(set(cond_1000b))
                stats_df = df_day[['등락률', '거래대금']] if stats_df.empty else stats_df + df_day[['등락률', '거래대금']]
            if not valid_tickers: return pd.DataFrame()
            df_cap = stock.get_market_cap_by_ticker(date_s, market=market)
            res = [{'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': stats_df.loc[t, '등락률']/n, '대금_v': stats_df.loc[t, '거래대금']/n} for t in list(valid_tickers)]
            return pd.DataFrame(res).sort_values(by='대금_v', ascending=False)

        elif mode == "고가놀이":
            base_df = stock.get_market_ohlcv_by_ticker(days[-4], market=market)
            targets = base_df[(base_df['거래대금'] >= 50000000000) & (base_df['등락률'] >= 15)].index
            df_cap = stock.get_market_cap_by_ticker(date_s, market=market)
            res = []
            for t in targets:
                try:
                    rates = [stock.get_market_ohlcv_by_ticker(d, market=market).loc[t, '등락률'] for d in days[-3:]]
                    if abs(sum(rates)/3) <= 5:
                        res.append({'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': rates[-1], '대금_v': stock.get_market_ohlcv_by_ticker(date_s, market=market).loc[t, '종가']})
                except: continue
            return pd.DataFrame(res).sort_values(by='대금_v', ascending=False)
            
        else: # 상한가, 하한가, 거래대금 상위
            df = stock.get_market_ohlcv_by_ticker(date_s, market=market)
            df_cap = stock.get_market_cap_by_ticker(date_s, market=market)
            if mode == "상한가": df = df[df['등락률'] >= 29.5]
            elif mode == "하한가": df = df[df['등락률'] <= -29.5]
            else: df = df.sort_values(by='거래대금', ascending=False).head(50)
            res = [{'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': df.loc[t, '등락률'], '대금_v': df.loc[t, '거래대금']} for t in df.index]
            return pd.DataFrame(res).sort_values(by='대금_v', ascending=False)
    except: return pd.DataFrame()

# --- 앱 메인 UI ---
st.title("해민증권 🧑‍💼")

try:
    init_date_str = stock.get_nearest_business_day_in_a_week()
    default_d = datetime.strptime(init_date_str, "%Y%m%d")
except:
    default_d = datetime.now()

c1, c2 = st.columns([1, 1.2])
with c1:
    d_input = st.date_input("날짜", default_d)
    date_s = d_input.strftime("%Y%m%d")
with c2:
    mode = st.selectbox("분석 모드", ["거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "상한가", "하한가", "고가놀이", "역헤드앤숄더"])

st.divider()

t1, t2 = st.tabs(["KOSPI", "KOSDAQ"])

for tab, mkt in zip([t1, t2], ["KOSPI", "KOSDAQ"]):
    with tab:
        with st.spinner("데이터 분석 중..."):
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
                    lambda x: 'color: #FF4B4B;' if x > 0 else ('color: #5F85FF;' if x < 0 else 'color: #FFFFFF;'), subset=[l_rate]
                ).format({l_rate: '{:.1f}%'}),
                use_container_width=True, height=600, hide_index=True
            )
