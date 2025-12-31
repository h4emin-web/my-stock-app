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
    </style>
    """, unsafe_allow_html=True)

# --- 외부 데이터 함수 ---
@st.cache_data(ttl=60)
def get_crypto_data():
    try:
        # 1. 업비트 전체 마켓 조회
        m_url = "https://api.upbit.com/v1/market/all"
        m_data = requests.get(m_url).json()
        krw_markets = [d for d in m_data if d['market'].startswith("KRW-")]
        
        # 2. 시가총액 대용으로 '24시간 거래대금' 상위 20개를 먼저 가져온 후 상세 정보 조회
        # (업비트 API는 시가총액 순 정렬 필터를 직접 제공하지 않으므로 거래대금 상위 20개로 구성하거나, 
        # 특정 주요 코인 20개를 지정하는 것이 안정적입니다.)
        target_tickers = [
            "KRW-BTC", "KRW-ETH", "KRW-SOL", "KRW-XRP", "KRW-STX", 
            "KRW-DOGE", "KRW-AVAX", "KRW-ADA", "KRW-LINK", "KRW-SHIB",
            "KRW-DOT", "KRW-TRX", "KRW-NEAR", "KRW-MATIC", "KRW-ETC",
            "KRW-ALGO", "KRW-AAVE", "KRW-EGLD", "KRW-SAND", "KRW-EOS"
        ]
        
        t_url = f"https://api.upbit.com/v1/ticker?markets={','.join(target_tickers)}"
        t_data = requests.get(t_url).json()
        
        name_dict = {d['market']: d['korean_name'] for d in krw_markets}
        
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
    except: return pd.DataFrame()

# --- 유틸리티 함수 ---
def format_korean_unit(val):
    if pd.isna(val) or val == 0: return "-"
    if val >= 1000000000000: return f"{int(val // 1000000000000)}조"
    return f"{int(val // 100000000):,}억"

@st.cache_data(ttl=600, show_spinner=False)
def get_data(mode, date_s, market):
    try:
        # 날짜 데이터 안정성 확보
        end_date = date_s
        start_date = (datetime.strptime(date_s, "%Y%m%d") - timedelta(days=60)).strftime("%Y%m%d")
        
        # 주식 데이터 가져오기 전처리
        df_ohlcv = stock.get_market_ohlcv_by_ticker(end_date, market=market)
        df_cap = stock.get_market_cap_by_ticker(end_date, market=market)
        
        if mode == "역헤드앤숄더":
            df_top = df_ohlcv.sort_values(by='거래대금', ascending=False).head(100)
            res = []
            for t in df_top.index:
                try:
                    df_hist = stock.get_market_ohlcv_by_date(start_date, end_date, t)['종가']
                    if len(df_hist) < 25: continue
                    p1, p2, p3 = df_hist[-30:-20], df_hist[-20:-10], df_hist[-10:]
                    l1, l2, l3 = p1.min(), p2.min(), p3.min()
                    if l2 < l1 and l2 < l3:
                        curr = df_hist.iloc[-1]
                        if l3 <= curr <= l3 * 1.07:
                            res.append({'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': df_top.loc[t, '등락률'], '대금_v': df_top.loc[t, '거래대금']})
                except: continue
            return pd.DataFrame(res).sort_values(by='대금_v', ascending=False)

        elif "연속 거래대금" in mode:
            n = 3 if "3일" in mode else 5
            # 실제 거래일 리스트 확보
            ohlcv_sample = stock.get_market_ohlcv_by_date(start_date, end_date, "005930")
            valid_days = ohlcv_sample.index.strftime("%Y%m%d").tolist()[-n:]
            
            valid_tickers = None
            stats_df = pd.DataFrame()
            for d in valid_days:
                df_day = stock.get_market_ohlcv_by_ticker(d, market=market)
                cond = df_day[df_day['거래대금'] >= 100000000000].index
                valid_tickers = set(cond) if valid_tickers is None else valid_tickers.intersection(set(cond))
                if stats_df.empty: stats_df = df_day[['등락률', '거래대금']]
                else:
                    stats_df['등락률'] += df_day['등락률']
                    stats_df['거래대금'] += df_day['거래대금']
            
            if not valid_tickers: return pd.DataFrame()
            res = [{'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': stats_df.loc[t, '등락률']/n, '대금_v': stats_df.loc[t, '거래대금']/n} for t in list(valid_tickers)]
            return pd.DataFrame(res).sort_values(by='대금_v', ascending=False)

        elif mode == "고가놀이":
            ohlcv_sample = stock.get_market_ohlcv_by_date(start_date, end_date, "005930")
            valid_days = ohlcv_sample.index.strftime("%Y%m%d").tolist()
            if len(valid_days) < 4: return pd.DataFrame()
            
            base_df = stock.get_market_ohlcv_by_ticker(valid_days[-4], market=market)
            targets = base_df[(base_df['거래대금'] >= 50000000000) & (base_df['등락률'] >= 15)].index
            res = []
            for t in targets:
                try:
                    rates = [stock.get_market_ohlcv_by_ticker(d, market=market).loc[t, '등락률'] for d in valid_days[-3:]]
                    if abs(sum(rates)/3) <= 5:
                        res.append({'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': rates[-1], '대금_v': df_ohlcv.loc[t, '거래대금']})
                except: continue
            return pd.DataFrame(res).sort_values(by='대금_v', ascending=False)
            
        else: # 상/하한가, 거래대금 상위
            df = df_ohlcv.copy()
            if mode == "상한가": df = df[df['등락률'] >= 29.5]
            elif mode == "하한가": df = df[df['등락률'] <= -29.5]
            else: df = df.sort_values(by='거래대금', ascending=False).head(50)
            
            res = [{'기업명': stock.get_market_ticker_name(t), '시총_v': df_cap.loc[t, '시가총액'], '등락률': df.loc[t, '등락률'], '대금_v': df.loc[t, '거래대금']} for t in df.index]
            return pd.DataFrame(res).sort_values(by='대금_v', ascending=False)
    except Exception as e:
        return pd.DataFrame()

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
    mode = st.selectbox("분석 모드", [
        "거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "상한가", "하한가", "고가놀이", "역헤드앤숄더", "암호화폐"
    ])

st.divider()

if mode == "암호화폐":
    with st.spinner("코인 시총 TOP 20 불러오는 중..."):
        c_data = get_crypto_data()
    
    if c_data.empty:
        st.info("데이터를 불러올 수 없습니다.")
    else:
        c_data['현재가'] = c_data['현재가'].apply(lambda x: f"{x:,.0f}" if x >= 100 else f"{x:,.2f}")
        c_data['거래대금'] = c_data['거래대금'].apply(format_korean_unit)
        st.dataframe(
            c_data.style.map(
                lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''), subset=['전일대비']
            ).format({'전일대비': '{:.1f}%'}),
            use_container_width=True, height=750, hide_index=True
        )
else:
    t1, t2 = st.tabs(["KOSPI", "KOSDAQ"])
    for tab, mkt in zip([t1, t2], ["KOSPI", "KOSDAQ"]):
        with tab:
            with st.spinner(f"{mkt} 분석 중..."):
                data = get_data(mode, date_s, mkt)
            
            if data is None or data.empty:
                st.info("해당 날짜에 데이터가 없거나 분석 조건에 맞는 종목이 없습니다.")
            else:
                data.insert(0, 'No', range(1, len(data) + 1))
                data['시총'] = data['시총_v'].apply(format_korean_unit)
                data['대금'] = data['대금_v'].apply(format_korean_unit)
                
                l_rate = "평균등락" if "연속" in mode else "등락률"
                l_amt = "평균대금" if "연속" in mode else "거래대금"
                
                st.dataframe(
                    data[['No', '기업명', '시총', '등락률', '대금']].rename(columns={'등락률': l_rate, '대금': l_amt}).style.map(
                        lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''), subset=[l_rate]
                    ).format({l_rate: '{:.1f}%'}),
                    use_container_width=True, height=600, hide_index=True
                )
