import streamlit as st
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta

# 1. 페이지 설정
st.set_page_config(page_title="주식 분석기 PRO", layout="wide")

# --- 유틸리티 함수 ---
def format_korean_unit(val):
    if pd.isna(val) or val == 0: return "0원"
    if val >= 1000000000000:
        cho, uk = val // 1000000000000, (val % 1000000000000) // 100000000
        return f"{int(cho):,}조 {int(uk):,}억" if uk > 0 else f"{int(cho):,}조"
    return f"{int(val // 100000000):,}억"

# --- [신규] 고가놀이 종목 발굴 함수 ---
@st.cache_data(ttl=600)
def find_high_tight_flag(date_str, market):
    try:
        # 1. 영업일 리스트 확보 (최근 10일치)
        start_search = (datetime.strptime(date_str, "%Y%m%d") - timedelta(days=15)).strftime("%Y%m%d")
        ohlcv_days = stock.get_market_ohlcv_by_date(start_search, date_str, "005930")
        days = ohlcv_days.index.strftime("%Y%m%d").tolist()
        
        if len(days) < 4: return pd.DataFrame()
        
        # 분석 대상일 설정
        target_day = days[-1]   # 오늘(기준일)
        prev_1 = days[-2]       # 1일 전
        prev_2 = days[-3]       # 2일 전
        base_day = days[-4]     # 3일 전 (장대양봉 기준일)
        
        # 2. 기준일(3일 전) 데이터: 거래대금 500억 이상 & 15% 이상 상승
        base_df = stock.get_market_ohlcv_by_ticker(base_day, market=market)
        condition_stocks = base_df[(base_df['거래대금'] >= 50000000000) & (base_df['등락률'] >= 15)].index
        
        if len(condition_stocks) == 0: return pd.DataFrame()
        
        # 3. 이후 3일간(prev_2, prev_1, target_day)의 데이터 추적
        res = []
        df_cap = stock.get_market_cap_by_ticker(target_day, market=market)
        
        for ticker in condition_stocks:
            try:
                # 3일간의 등락률 합산 평균 계산
                r1 = stock.get_market_ohlcv_by_ticker(prev_2, market=market).loc[ticker, '등락률']
                r2 = stock.get_market_ohlcv_by_ticker(prev_1, market=market).loc[ticker, '등락률']
                r3 = base_df.loc[ticker, '등락률'] # 여기서는 기준일 이후의 흐름이므로 오늘 등락률 사용
                r3_actual = stock.get_market_ohlcv_by_ticker(target_day, market=market).loc[ticker, '등락률']
                
                avg_rate = abs(r1 + r2 + r3_actual) / 3
                
                # 평균 등락률이 5% 이하인 종목 필터링
                if avg_rate <= 5:
                    res.append({
                        '기업명': stock.get_market_ticker_name(ticker),
                        '시가총액_v': df_cap.loc[ticker, '시가총액'] if ticker in df_cap.index else 0,
                        '주가': stock.get_market_ohlcv_by_ticker(target_day, market=market).loc[ticker, '종가'],
                        '등락률': r3_actual,
                        '거래대금_v': stock.get_market_ohlcv_by_ticker(target_day, market=market).loc[ticker, '거래대금'],
                        '패턴': '고가놀이'
                    })
            except: continue
            
        final_df = pd.DataFrame(res).sort_values(by='거래대금_v', ascending=False)
        if not final_df.empty: final_df.insert(0, '순위', range(1, len(final_df) + 1))
        return final_df
    except: return pd.DataFrame()

# --- 기존 분석 함수 (생략/유지) ---
@st.cache_data(ttl=600)
def get_limit_price_stocks(date_str, market, limit_type="UP"):
    # (이전 코드와 동일 - 시가총액 포함 버전)
    try:
        df = stock.get_market_ohlcv_by_ticker(date_str, market=market)
        df_cap = stock.get_market_cap_by_ticker(date_str, market=market)
        limit_df = df[df['등락률'] >= 29.5].copy() if limit_type == "UP" else df[df['등락률'] <= -29.5].copy()
        res = []
        for t in limit_df.index:
            res.append({'기업명': stock.get_market_ticker_name(t), '시가총액_v': df_cap.loc[t, '시가총액'], '주가': limit_df.loc[t, '종가'], '등락률': limit_df.loc[t, '등락률'], '거래대금_v': limit_df.loc[t, '거래대금'], '연속 기록': '분석중'})
        df_res = pd.DataFrame(res); df_res.insert(0, '순위', range(1, len(df_res)+1))
        return df_res
    except: return pd.DataFrame()

@st.cache_data(ttl=600)
def fetch_stock_data(date_str, market, n_days):
    # (이전 코드와 동일)
    df = stock.get_market_ohlcv_by_ticker(date_str, market=market)
    df = df.sort_values(by='거래대금', ascending=False).head(100)
    df_cap = stock.get_market_cap_by_ticker(date_str, market=market)
    res = [{'기업명': stock.get_market_ticker_name(t), '시가총액_v': df_cap.loc[t, '시가총액'], '주가': df.loc[t, '종가'], '등락률': df.loc[t, '등락률'], '거래대금_v': df.loc[t, '거래대금']} for t in df.index]
    df_res = pd.DataFrame(res); df_res.insert(0, '순위', range(1, len(df_res)+1))
    return df_res

# --- UI 설정 ---
st.sidebar.title("🔍 검색 설정")
try:
    init_date = stock.get_nearest_business_day_in_a_week()
    default_d = datetime.strptime(init_date, "%Y%m%d")
except: default_d = datetime.now()

selected_date = st.sidebar.date_input("조회 기준일", default_d)
date_s = selected_date.strftime("%Y%m%d")

st.sidebar.markdown("---")
st.sidebar.subheader("📅 거래대금 연속")
cont_choice = st.sidebar.pills("연속 기간", options=["3일 연속", "5일 연속"], selection_mode="single", key="cont")

st.sidebar.subheader("🚫 가격 제한폭 도달")
limit_choice = st.sidebar.pills("제한폭", options=["상한가", "하한가"], selection_mode="single", key="limit")

st.sidebar.subheader("🎯 종목 발굴")
discovery_choice = st.sidebar.pills("패턴 선택", options=["고가놀이"], selection_mode="single", key="discovery")

# 모드 결정 로직
current_mode = "거래대금 상위"
if st.session_state.discovery: current_mode = st.session_state.discovery
elif st.session_state.limit: current_mode = st.session_state.limit
elif st.session_state.cont: current_mode = st.session_state.cont

# 메인 화면
tab1, tab2 = st.tabs(["KOSPI", "KOSDAQ"])

for tab, mkt in zip([tab1, tab2], ["KOSPI", "KOSDAQ"]):
    with tab:
        if current_mode == "고가놀이":
            display_df = find_high_tight_flag(date_s, mkt)
            title = f"🚩 {mkt} 고가놀이 패턴 (장대양봉 후 횡보)"
        elif current_mode in ["상한가", "하한가"]:
            display_df = get_limit_price_stocks(date_s, mkt, "UP" if current_mode=="상한가" else "DOWN")
            title = f"🔥 {mkt} {current_mode}"
        else:
            n_days = 3 if current_mode == "3일 연속" else (5 if current_mode == "5일 연속" else 1)
            display_df = fetch_stock_data(date_s, mkt, n_days)
            title = f"📊 {mkt} {'상위 100' if current_mode == '거래대금 상위' else current_mode}"

        if display_df.empty:
            st.warning("조건에 부합하는 종목이 없습니다.")
        else:
            display_df['거래대금'] = display_df['거래대금_v'].apply(format_korean_unit)
            display_df['시가총액'] = display_df['시가총액_v'].apply(format_korean_unit)
            st.subheader(title)
            
            # PC 버전에 맞게 컬럼 너비 및 표시 최적화
            st.dataframe(
                display_df[['순위', '기업명', '시가총액', '주가', '등락률', '거래대금']].style.map(
                    lambda x: 'color: #ef5350; font-weight: bold;' if x > 0 else ('color: #42a5f5; font-weight: bold;' if x < 0 else ''), subset=['등락률']
                ).format({'등락률': '{:.2f}%', '주가': '{:,}원'}),
                column_config={
                    "순위": st.column_config.Column(width=60),
                    "기업명": st.column_config.Column(width=200),
                    "시가총액": st.column_config.Column(width=180),
                    "주가": st.column_config.Column(width=120),
                    "등락률": st.column_config.Column(width=100),
                    "거래대금": st.column_config.Column(width=180),
                },
                use_container_width=False, height=750, hide_index=True
            )
