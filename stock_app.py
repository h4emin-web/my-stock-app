import streamlit as st
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta
import requests
import time

# 1. 앱 설정 및 스타일
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

# --- 주식 데이터 로딩 로직 (강제 리트라이 및 딜레이 추가) ---
@st.cache_data(ttl=300, show_spinner=False)
def get_data(mode, date_s, market):
    try:
        # 지정된 날짜의 기본 시세 가져오기
        df_today = stock.get_market_ohlcv_by_ticker(date_s, market=market)
        
        # 데이터가 비어있으면 가장 최근 영업일 자동 탐색
        if df_today.empty:
            date_s = stock.get_nearest_business_day_in_a_week()
            df_today = stock.get_market_ohlcv_by_ticker(date_s, market=market)
            if df_today.empty: return pd.DataFrame()

        df_cap = stock.get_market_cap_by_ticker(date_s, market=market)
        
        # 과거 영업일 리스트 확보 (충분한 기간 확보를 위해 60일 전부터 탐색)
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
            total_amt_series = pd.Series(0, index=df_today.index)
            
            for d in target_days:
                df_day = stock.get_market_ohlcv_by_ticker(d, market=market)
                time.sleep(0.05) # 과부하 방지 딜레이
                cond = df_day[df_day['거래대금'] >= 100000000000].index
                valid_tickers = set(cond) if valid_tickers is None else valid_tickers.intersection(set(cond))
                total_amt_series += df_day['거래대금']
            
            if not valid_tickers: return pd.DataFrame()
            
            first_day_df = stock.get_market_ohlcv_by_ticker(target_days[0], market=market)
            last_day_df = df_today # 오늘 기준 데이터
            
            res = []
            for t in list(valid_tickers):
                try:
                    f_c, l_c = first_day_df.loc[t, '종가'], last_day_df.loc[t, '종가']
                    res.append({
                        '기업명': stock.get_market_ticker_name(t),
                        '시총_v': df_cap.loc[t, '시가총액'],
                        '등락률': ((l_c - f_c) / f_c) * 100,
                        '대금_v': total_amt_series.loc[t] / n
                    })
                except: continue
            return pd.DataFrame(res)

        elif mode == "고가놀이":
            # 4일 전 기준봉 검색
            if len(days) < 4: return pd.DataFrame()
            base_date = days[-4]
            df_base = stock.get_market_ohlcv_by_ticker(base_date, market=market)
            targets = df_base[(df_base['거래대금'] >= 50000000000) & (df_base['등락률'] >= 15)].index
            
            res = []
            for t in targets:
                try:
                    # 이후 3일간 데이터 확인
                    rates = []
                    for d in days[-3:]:
                        d_data = stock.get_market_ohlcv_by_ticker(d, market=market)
                        rates.append(d_data.loc[t, '등락률'])
                    if abs(sum(rates) / 3) <= 5:
                        res.append({'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': df_today.loc[t, '등락률'], '대금_v': df_today.loc[t, '거래대금']})
                except: continue
            return pd.DataFrame(res)
        
        elif mode == "역헤드앤숄더":
            df_top = df_today.sort_values(by='거래대금', ascending=False).head(100)
            res = []
            for t in df_top.index:
                try:
                    df_hist = stock.get_market_ohlcv_by_date(days[-30], date_s, t)['종가']
                    if len(df_hist) < 25: continue
                    p1, p2, p3 = df_hist[:10], df_hist[10:20], df_hist[20:]
                    l1, l2, l3 = p1.min(), p2.min(), p3.min()
                    if l2 < l1 and l2 < l3 and l3 <= df_hist.iloc[-1] <= l3 * 1.07:
                        res.append({'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': df_today.loc[t, '등락률'], '대금_v': df_today.loc[t, '거래대금']})
                except: continue
            return pd.DataFrame(res)

        elif mode in ["상한가", "하한가"]:
            cond = (df_today['등락률'] >= 29.5) if mode == "상한가" else (df_today['등락률'] <= -29.5)
            limit_df = df_today[cond]
            res = [{'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': limit_df.loc[t, '등락률'], '대금_v': limit_df.loc[t, '거래대금']} for t in limit_df.index]
            return pd.DataFrame(res)
        
        else: # 거래대금 상위
            df = df_today.sort_values(by='거래대금', ascending=False).head(50)
            res = [{'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': df.loc[t, '등락률'], '대금_v': df.loc[t, '거래대금']} for t in df.index]
            return pd.DataFrame(res)
            
    except Exception as e:
        st.error(f"데이터 연동 중 오류 발생: {e}")
        return pd.DataFrame()

# --- 암호화폐 데이터 ---
@st.cache_data(ttl=30)
def get_crypto_data():
    try:
        m_url = "https://api.upbit.com/v1/market/all"
        m_data = requests.get(m_url, timeout=5).json()
        krw_markets = {d['market']: d['korean_name'] for d in m_data if d['market'].startswith("KRW-")}
        t_url = f"https://api.upbit.com/v1/ticker?markets={','.join(krw_markets.keys())}"
        t_data = requests.get(t_url, timeout=5).json()
        res = []
        for d in t_data:
            res.append({'코인명': krw_markets[d['market']], '현재가': d['trade_price'], '전일대비': d['signed_change_rate'] * 100, '거래대금': d['acc_trade_price_24h']})
        df = pd.DataFrame(res).sort_values(by='거래대금', ascending=False).head(20)
        df.insert(0, 'No', range(1, len(df) + 1))
        return df
    except: return pd.DataFrame()

# --- 앱 메인 UI ---
st.title("Stock")

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
    if not data.empty:
        data['현재가'] = data['현재가'].apply(lambda x: f"{x:,.0f}" if x >= 100 else f"{x:,.2f}")
        data['거래대금'] = data['거래대금'].apply(format_korean_unit)
        st.dataframe(data.style.map(lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''), subset=['전일대비']).format({'전일대비': '{:.1f}%'}), use_container_width=True, height=750, hide_index=True)
else:
    t1, t2 = st.tabs(["KOSPI", "KOSDAQ"])
    for tab, mkt in zip([t1, t2], ["KOSPI", "KOSDAQ"]):
        with tab:
            with st.spinner(f"{mkt} 데이터를 분석 중입니다..."):
                data = get_data(mode, date_s, mkt)
            
            if data is None or data.empty:
                st.warning("데이터가 없거나 분석 조건에 맞는 종목이 없습니다.")
                st.button("다시 시도", key=f"retry_{mkt}")
            else:
                data = data.sort_values(by='대금_v', ascending=False)
                data.insert(0, 'No', range(1, len(data) + 1))
                data['시총'] = data['시총_v'].apply(format_korean_unit)
                data['대금'] = data['대금_v'].apply(format_korean_unit)
                
                if "3일 연속" in mode: l_rate, l_amt = "3일 누적 변동", "3일 평균 대금"
                elif "5일 연속" in mode: l_rate, l_amt = "5일 누적 변동", "5일 평균 대금"
                else: l_rate, l_amt = "등락률", "거래대금"
                
                st.dataframe(
                    data[['No', '기업명', '시총', '등락률', '대금']].rename(columns={'등락률': l_rate, '대금': l_amt}).style.map(
                        lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''), subset=[l_rate]
                    ).format({l_rate: '{:.1f}%'}),
                    use_container_width=True, height=600, hide_index=True
                )
