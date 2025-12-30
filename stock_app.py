import streamlit as st
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta

# 1. 모바일 앱 환경 설정
st.set_page_config(
    page_title="주식 분석기 App",
    layout="centered",  # 모바일은 중앙 집중형이 보기 편함
    initial_sidebar_state="collapsed"
)

# 모바일용 UI 스타일링 (글자 크기 및 간격 최적화)
st.markdown("""
    <style>
    .block-container { padding-top: 1.5rem; padding-left: 1rem; padding-right: 1rem; }
    .stTabs [data-baseweb="tab"] { font-size: 18px; font-weight: bold; flex: 1; text-align: center; }
    .stSelectbox label { font-size: 14px; font-weight: bold; }
    /* 테이블 행 높이 조절 */
    [data-testid="stDataFrame"] td { height: 45px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 데이터 로직 (기능 유지) ---
def format_korean_unit(val):
    if pd.isna(val) or val == 0: return "0"
    if val >= 1000000000000:
        return f"{int(val // 1000000000000)}조"
    return f"{int(val // 100000000):,}억"

@st.cache_data(ttl=600)
def get_data(mode, date_s, market):
    try:
        if mode == "고가놀이":
            # 3일 전 기준 (영업일 기준 4일치 데이터 필요)
            start_search = (datetime.strptime(date_s, "%Y%m%d") - timedelta(days=15)).strftime("%Y%m%d")
            ohlcv_days = stock.get_market_ohlcv_by_date(start_search, date_s, "005930")
            days = ohlcv_days.index.strftime("%Y%m%d").tolist()
            if len(days) < 4: return pd.DataFrame()
            
            base_df = stock.get_market_ohlcv_by_ticker(days[-4], market=market)
            targets = base_df[(base_df['거래대금'] >= 50000000000) & (base_df['등락률'] >= 15)].index
            
            res = []
            df_cap = stock.get_market_cap_by_ticker(date_s, market=market)
            for t in targets:
                try:
                    r1 = stock.get_market_ohlcv_by_ticker(days[-3], market=market).loc[t, '등락률']
                    r2 = stock.get_market_ohlcv_by_ticker(days[-2], market=market).loc[t, '등락률']
                    r3 = stock.get_market_ohlcv_by_ticker(days[-1], market=market).loc[t, '등락률']
                    if (abs(r1+r2+r3)/3) <= 5:
                        res.append({'기업명': stock.get_market_ticker_name(t), '시가총액_v': df_cap.loc[t, '시가총액'], '주가': stock.get_market_ohlcv_by_ticker(date_s, market=market).loc[t, '종가'], '등락률': r3, '거래대금_v': stock.get_market_ohlcv_by_ticker(date_s, market=market).loc[t, '거래대금'], '코드': t})
                except: continue
            return pd.DataFrame(res).sort_values(by='거래대금_v', ascending=False)

        elif mode in ["상한가", "하한가"]:
            df = stock.get_market_ohlcv_by_ticker(date_s, market=market)
            df_cap = stock.get_market_cap_by_ticker(date_s, market=market)
            cond = (df['등락률'] >= 29.5) if mode == "상한가" else (df['등락률'] <= -29.5)
            limit_df = df[cond]
            res = [{'기업명': stock.get_market_ticker_name(t), '시가총액_v': df_cap.loc[t, '시가총액'], '주가': limit_df.loc[t, '종가'], '등락률': limit_df.loc[t, '등락률'], '거래대금_v': limit_df.loc[t, '거래대금'], '코드': t} for t in limit_df.index]
            return pd.DataFrame(res).sort_values(by='거래대금_v', ascending=False)
        
        else: # 거래대금 상위 및 연속
            n = 3 if mode == "3일 연속" else (5 if mode == "5일 연속" else 1)
            # (기존 fetch_stock_data 로직과 동일하되 코드 포함)
            df = stock.get_market_ohlcv_by_ticker(date_s, market=market)
            df = df.sort_values(by='거래대금', ascending=False).head(50) # 모바일은 50개만
            df_cap = stock.get_market_cap_by_ticker(date_s, market=market)
            res = [{'기업명': stock.get_market_ticker_name(t), '시가총액_v': df_cap.loc[t, '시가총액'], '주가': df.loc[t, '종가'], '등락률': df.loc[t, '등락률'], '거래대금_v': df.loc[t, '거래대금'], '코드': t} for t in df.index]
            return pd.DataFrame(res)
    except: return pd.DataFrame()

# --- 앱 메인 UI ---
st.title("📲 분석기 Mobile")

# 1. 상단 필터 (탭 형태)
try:
    init_date = stock.get_nearest_business_day_in_a_week()
    default_d = datetime.strptime(init_date, "%Y%m%d")
except: default_d = datetime.now()

col1, col2 = st.columns([1, 1])
with col1:
    d_input = st.date_input("날짜", default_d)
    date_s = d_input.strftime("%Y%m%d")
with col2:
    mode = st.selectbox("분석 모드", ["거래대금 상위", "3일 연속", "5일 연속", "상한가", "하한가", "고가놀이"])

st.divider()

# 2. 메인 리스트
t1, t2 = st.tabs(["KOSPI", "KOSDAQ"])

for tab, mkt in zip([t1, t2], ["KOSPI", "KOSDAQ"]):
    with tab:
        data = get_data(mode, date_s, mkt)
        
        if data.empty:
            st.info("데이터가 없습니다.")
        else:
            # 순위 부여 및 포맷팅
            data.insert(0, 'No', range(1, len(data) + 1))
            data['시총'] = data['시가총액_v'].apply(format_korean_unit)
            data['대금'] = data['거래대금_v'].apply(format_korean_unit)
            
            # 모바일 최적화 표 출력
            st.dataframe(
                data[['No', '기업명', '시총', '등락률', '대금']].style.map(
                    lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''), subset=['등락률']
                ).format({'등락률': '{:.1f}%'}),
                use_container_width=True,
                height=500,
                hide_index=True,
                column_config={
                    "No": st.column_config.Column(width=30),
                    "기업명": st.column_config.Column(width=100),
                    "시총": st.column_config.Column(width=60),
                    "등락률": st.column_config.Column(width=60),
                    "대금": st.column_config.Column(width=60),
                }
            )
            
            # 차트 바로가기 (모바일은 클릭이 편해야 함)
            st.caption("💡 아래에서 종목을 선택하면 차트로 이동합니다.")
            selected_stock = st.selectbox("차트 보기", ["선택하세요"] + data['기업명'].tolist(), key=f"select_{mkt}")
            if selected_stock != "선택하세요":
                code = data[data['기업명'] == selected_stock]['코드'].values[0]
                url = f"https://m.stock.naver.com/domestic/stock/{code}/total"
                st.link_button(f"🚀 {selected_stock} 네이버 차트 열기", url, use_container_width=True)