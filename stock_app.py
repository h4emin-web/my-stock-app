import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime
import time

# 1. 앱 설정
st.set_page_config(page_title="Stock & Crypto Manager", layout="centered")

# --- 🔑 한국투자증권 실전투자 키 설정 ---
APP_KEY = "PSmBdpWduaskTXxqbcT6PuBTneKitnWiXnrL"
APP_SECRET = "adyZ3eYxXM74UlaErGZWe1SEJ9RPNo2wOD/mDWkJqkKfB0re+zVtKNiZM5loyVumtm5It+jTdgplqbimwqnyboerycmQWrlgA/Uwm8u4K66LB6+PhIoO6kf8zS196RO570kjshkBBecQzUUfwLlDWBIlTu/Mvu4qYYi5dstnsjgZh3Ic2Sw="
URL_BASE = "https://openapi.koreainvestment.com:9443"

# --- [공통] 단위 변환 함수 ---
def format_korean_unit(val):
    try:
        val = float(val)
        if val >= 1000000000000: return f"{int(val // 1000000000000)}조"
        if val >= 100000000: return f"{int(val // 100000000):,}억"
        return f"{int(val):,}"
    except: return "0"

# --- [주식] KIS API 관련 함수 ---
@st.cache_data(ttl=3600*12)
def get_kis_token():
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    res = requests.post(f"{URL_BASE}/oauth2/tokenP", headers=headers, data=json.dumps(body))
    return res.json().get('access_token')

def fetch_kis(path, tr_id, params):
    token = get_kis_token()
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY, "appsecret": APP_SECRET,
        "tr_id": tr_id, "custtype": "P"
    }
    res = requests.get(f"{URL_BASE}{path}", headers=headers, params=params)
    return res.json() if res.status_code == 200 else None

# --- [코인] 업비트 API 관련 함수 ---
@st.cache_data(ttl=30)
def get_upbit_data():
    try:
        # 1. 마켓 목록 조회 (KRW 시장)
        m_url = "https://api.upbit.com/v1/market/all"
        markets = requests.get(m_url).json()
        krw_markets = [m['market'] for m in markets if m['market'].startswith("KRW-")]
        market_names = {m['market']: m['korean_name'] for m in markets}
        
        # 2. 시세 조회 (상위 30개만)
        t_url = f"https://api.upbit.com/v1/ticker?markets={','.join(krw_markets[:50])}"
        tickers = requests.get(t_url).json()
        
        res = []
        for t in tickers:
            res.append({
                '코인명': market_names[t['market']],
                '현재가': t['trade_price'],
                '등락률': t['signed_change_rate'] * 100,
                '거래대금': t['acc_trade_price_24h']
            })
        df = pd.DataFrame(res).sort_values(by='거래대금', ascending=False)
        return df
    except: return pd.DataFrame()

# --- [주식] 분석 로직 ---
def get_kis_analyzed(mode, mkt_code):
    # 거래대금 상위 랭킹 호출
    params = {
        "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": mkt_code, "FID_DIV_CLS_CODE": "0",
        "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "0",
        "FID_TRGT_EXLS_CLS_CODE": "0", "FID_INPUT_PRICE_1": "0",
        "FID_INPUT_PRICE_2": "0", "FID_VOL_CNT": "0"
    }
    raw = fetch_kis("/uapi/domestic-stock/v1/ranking/trade-value", "FHPST01710000", params)
    if not raw or 'output' not in raw: return pd.DataFrame()
    
    df = pd.DataFrame(raw['output'])
    
    if mode == "거래대금 상위":
        return df.head(50)
    
    # 3일/5일 연속 및 고가놀이는 상세 시세 조회가 필요하므로 상위 20개만 정밀 분석
    res = []
    n = 3 if "3일" in mode else (5 if "5일" in mode else 0)
    
    for _, row in df.head(20).iterrows():
        if n > 0: # 연속 거래대금 로직
            p = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": row['mksc_shrn_iscd'], "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0"}
            hist = fetch_kis("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100", p)
            if hist and 'output2' in hist:
                days = hist['output2'][:n]
                # 한투 API의 거래대금 단위(acml_tr_pbmn) 확인 필요 (보통 원 단위)
                if all(float(d['acml_tr_pbmn']) >= 100000000000 for d in days):
                    res.append(row)
        elif mode == "상한가":
            if float(row['prdy_ctrt']) >= 29.5:
                res.append(row)
                
    return pd.DataFrame(res) if res else (df.head(50) if mode == "거래대금 상위" else pd.DataFrame())

# --- 📱 메인 화면 ---
st.title("📈 Stock & Crypto Manager")

mode = st.selectbox("분석 모드", ["거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "상한가", "암호화폐"])

if mode == "암호화폐":
    with st.spinner("업비트 실시간 시세 조회 중..."):
        df = get_upbit_data()
        if not df.empty:
            df.insert(0, 'No', range(1, len(df) + 1))
            df['현재가'] = df['현재가'].apply(lambda x: f"{x:,.0f}" if x >= 100 else f"{x:,.2f}")
            df['거래대금'] = df['거래대금'].apply(format_korean_unit)
            
            st.dataframe(df.style.map(lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''), subset=['등락률']).format({'등락률': '{:.2f}%'}),
                         use_container_width=True, hide_index=True)
else:
    mkt = st.radio("시장 선택", ["KOSPI", "KOSDAQ"], horizontal=True)
    mkt_code = "0001" if mkt == "KOSPI" else "1001"
    
    if st.button("🚀 데이터 분석 시작"):
        with st.spinner(f"증권사 서버에서 {mkt} 데이터 분석 중..."):
            df = get_kis_analyzed(mode, mkt_code)
            
            if not df.empty:
                res_df = df[['hts_kor_isnm', 'stck_prpr', 'prdy_ctrt', 'tr_pbmn']].copy()
                res_df.columns = ['종목명', '현재가', '등락률', '거래대금']
                res_df.insert(0, 'No', range(1, len(res_df) + 1))
                res_df['현재가'] = res_df['현재가'].apply(lambda x: f"{int(x):,}")
                res_df['거래대금'] = res_df['거래대금'].apply(format_korean_unit)
                
                st.dataframe(res_df.style.map(lambda x: 'color: #ef5350;' if float(x) > 0 else ('color: #42a5f5;' if float(x) < 0 else ''), subset=['등락률']),
                             use_container_width=True, hide_index=True)
            else:
                st.warning("조건에 맞는 종목이 없거나 데이터 로드 실패입니다.")

st.sidebar.markdown("---")
st.sidebar.write("✅ **KIS API (Stock)** & **Upbit API (Crypto)**")
