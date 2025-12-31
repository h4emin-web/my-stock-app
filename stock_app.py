import streamlit as st
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta
import requests

# 1. 앱 설정 및 로딩 메시지(Running...) 숨기기
st.set_page_config(page_title="해민증권", layout="centered", initial_sidebar_state="collapsed")
st.markdown("""
    <style>
    /* 로딩 아이콘 및 Status Widget 숨기기 */
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

# --- 데이터 포맷 함수 ---
def format_korean_unit(val):
    if pd.isna(val) or val == 0: return "-"
    if val >= 1000000000000: return f"{int(val // 1000000000000)}조"
    return f"{int(val // 100000000):,}억"

# --- 암호화폐: 시가총액/거래대금 기준 상위 20개 ---
@st.cache_data(ttl=30)
def get_crypto_data():
    try:
        # 1. 업비트 종목 리스트 (한글명 매칭)
        m_url = "https://api.upbit.com/v1/market/all"
        m_data = requests.get(m_url, timeout=5).json()
        krw_markets = {d['market']: d['korean_name'] for d in m_data if d['market'].startswith("KRW-")}
        
        # 2. 티커 정보 조회
        t_url = f"https://api.upbit.com/v1/ticker?markets={','.join(krw_markets.keys())}"
        t_data = requests.get(t_url, timeout=5).json()
        
        res = []
        for d in t_data:
            res.append({
                '코인명': krw_markets[d['market']],
                '현재가': d['trade_price'],
                '전일대비': d['signed_change_rate'] * 100,
                '거래대금': d['acc_trade_price_24h']
            })
        
        # 거래대금 상위 20개 (시총 상위주와 대부분 일치)
        df = pd.DataFrame(res).sort_values(by='거래대금', ascending=False).head(20)
        df.insert(0, 'No', range(1, len(df) + 1))
        return df
    except:
        return pd.DataFrame()

# --- 주식 분석 로직 (전체 모드 복구) ---
@st.cache_data(ttl=600, show_spinner=False)
def get_analyzed_stock(mode, date_s, market):
    try:
        # 영업일 데이터 확보
        start_search = (datetime.strptime(date_s, "%Y%m%d") - timedelta(days=60)).strftime("%Y%m%d")
        ohlcv_sample = stock.get_market_ohlcv_by_date(start_search, date_s, "005930")
        days = ohlcv_sample.index.strftime("%Y%m%d").tolist()
        if not days: return pd.DataFrame()
        
        df_today = stock.get_market_ohlcv_by_ticker(date_s, market=market)
        df_cap = stock.get_market_cap_by_ticker(date_s, market=market)

        if mode == "역헤드앤숄더":
            res = []
            tickers = df_today.sort_values(by='거래대금', ascending=False).head(100).index
            for t in tickers:
                try:
                    hist = stock.get_market_ohlcv_by_date(days[-30], date_s, t)['종가']
                    if len(hist) < 25: continue
                    p1, p2, p3 = hist[:10], hist[10:20], hist[20:]
                    if p2.min() < p1.min() and p2.min() < p3.min() and hist.iloc[-1] <= p3.min() * 1.07:
                        res.append({'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': df_today.loc[t, '등락률'], '대금_v': df_today.loc[t, '거래대금']})
                except: continue
            return pd.DataFrame(res)

        elif "연속 거래대금" in mode:
            n = 3 if "3일" in mode else 5
            target_days = days[-n:]
            valid_tickers = None
            for d in target_days:
                curr_df = stock.get_market_ohlcv_by_ticker(d, market=market)
                cond = curr_df[curr_df['거래대금'] >= 100000000000].index # 1000억 기준
                valid_tickers = set(cond) if valid_tickers is None else valid_tickers.intersection(set(cond))
            if not valid_tickers: return pd.DataFrame()
            res = [{'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': df_today.loc[t, '등락률'], '대금_v': df_today.loc[t, '거래대금']} for t in valid_tickers]
            return pd.DataFrame(res)

        elif mode == "고가놀이":
            base_df = stock.get_market_ohlcv_by_ticker(days[-4], market=market)
            targets = base_df[(base_df['등락률'] >= 15) & (base_df['거래대금'] >= 50000000000)].index
            res = []
            for t in targets:
                try:
                    rates = [stock.get_market_ohlcv_by_ticker(d, market=market).loc[t, '등락률'] for d in days[-3:]]
                    if all(abs(r) < 7 for r in rates):
                        res.append({'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': df_today.loc[t, '등락률'], '대금_v': df_today.loc[t, '거래대금']})
                except: continue
            return pd.DataFrame(res)

        else: # 상/하한가, 거래대금 상위
            df = df_today.copy()
            if mode == "상한가": df = df[df['등락률'] >= 29.5]
            elif mode == "하한가": df = df[df['등락률'] <= -29.5]
            else: df = df.sort_values(by='거래대금', ascending=False).head(50)
            res = [{'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': df.loc[t, '등락률'], '대금_v': df.loc[t, '거래대금']} for t in df.index]
            return pd.DataFrame(res)
    except: return pd.DataFrame()

# --- 메인 UI 구성 ---
st.title("해민증권🧑‍💼")

try:
    init_date = stock.get_nearest_business_day_in_a_week()
    default_d = datetime.strptime(init_date, "%Y%m%d")
except:
    default_d = datetime.now()

c1, c2 = st.columns([1, 1.2])
with c1:
    d_input = st.date_input("날짜", default_d)
    date_s = d_input.strftime("%Y%m%d")
with c2:
    mode = st.selectbox("분석 모드", [
        "거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "상한가", "하한가", "고가놀이", "역헤드앤숄더", "암호화폐"
    ])

st.divider()

if mode == "암호화폐":
    c_data = get_crypto_data()
    if c_data.empty:
        st.error("현재 업비트 데이터를 불러올 수 없습니다.")
    else:
        # 출력 포맷팅
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
            res_df = get_analyzed_stock(mode, date_s, mkt)
            if res_df.empty:
                st.info("조건에 맞는 종목이 없습니다.")
            else:
                res_df = res_df.sort_values(by='대금_v', ascending=False)
                res_df.insert(0, 'No', range(1, len(res_df) + 1))
                res_df['시총'] = res_df['시총_v'].apply(format_korean_unit)
                res_df['대금'] = res_df['대금_v'].apply(format_korean_unit)
                st.dataframe(
                    res_df[['No', '기업명', '시총', '등락률', '대금']].rename(columns={'대금': '거래대금'}).style.map(
                        lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''), subset=['등락률']
                    ).format({'등락률': '{:.1f}%'}),
                    use_container_width=True, height=600, hide_index=True
                )
