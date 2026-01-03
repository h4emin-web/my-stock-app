import streamlit as st
import pandas as pd
import requests
import json
import time

# 1. 앱 설정
st.set_page_config(page_title="Stock & Crypto Manager", layout="centered")

# --- 🔑 [사용자 설정] 보내주신 설정 파일 내용 반영 ---
CONFIG = {
    "my_app": "PSmBdpWduaskTXxqbcT6PuBTneKitnWiXnrL",
    "my_sec": "adyZ3eYxXM74UlaErGZWe1SEJ9RPNo2wOD/mDWkJqkKfB0re+zVtKNiZM5loyVumtm5It+jTdgplqbimwqnyboerycmQWrlgA/Uwm8u4K66LB6+PhIoO6kf8zS196RO570kjshkBBecQzUUfwLlDWBIlTu/Mvu4qYYi5dstnsjgZh3Ic2Sw=",
    "my_acct": "72590134", # 계좌번호 8자리
    "my_prod": "01",       # 상품코드 2자리
    "url_base": "https://openapi.koreainvestment.com:9443"
}

# --- 🔐 [인증] 접근 토큰 발급 ---
@st.cache_data(ttl=3600*12)
def get_access_token():
    url = f"{CONFIG['url_base']}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": CONFIG['my_app'],
        "appsecret": CONFIG['my_sec']
    }
    res = requests.post(url, headers=headers, data=json.dumps(body))
    return res.json().get('access_token')

# --- 📊 [주식] KIS API 호출 함수 (공식 규격 헤더) ---
def fetch_stock(path, tr_id, params):
    token = get_access_token()
    if not token: return None
    
    # 공식 라이브러리 권장 헤더 구성
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": CONFIG['my_app'],
        "appsecret": CONFIG['my_sec'],
        "tr_id": tr_id,
        "custtype": "P",      # 개인(P), 법인(B)
        "tr_cont": "",        # 연속 거래 여부
    }
    
    try:
        res = requests.get(f"{CONFIG['url_base']}{path}", headers=headers, params=params)
        if res.status_code == 200:
            return res.json()
        return None
    except:
        return None

# --- 🛠️ [로직] 주식 분석 기능 ---
def analyze_stocks(mode, market_code):
    # 1. 거래대금 상위 조회 (TR: FHPST01710000)
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": market_code, # 0000(전체), 0001(코스피), 1001(코스닥)
        "FID_DIV_CLS_CODE": "0", "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "0",
        "FID_TRGT_EXLS_CLS_CODE": "0", "FID_INPUT_PRICE_1": "0", "FID_INPUT_PRICE_2": "0", "FID_VOL_CNT": "0"
    }
    
    data = fetch_stock("/uapi/domestic-stock/v1/ranking/trade-value", "FHPST01710000", params)
    if not data or 'output' not in data: return pd.DataFrame()
    
    all_df = pd.DataFrame(data['output'])
    
    if mode == "거래대금 상위":
        return all_df.head(30)
    
    # 2. 연속 거래대금 / 고가놀이 로직 (일봉 데이터 분석)
    res = []
    n_days = 3 if "3일" in mode else 5
    
    bar = st.progress(0)
    # 효율성을 위해 상위 20개 종목만 일봉 분석 진행
    for i, (_, row) in enumerate(all_df.head(20).iterrows()):
        bar.progress((i+1)/20)
        p = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": row['mksc_shrn_iscd'],
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0"
        }
        hist = fetch_stock("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100", p)
        
        if hist and 'output2' in hist:
            days = hist['output2'][:n_days]
            # 거래대금 500억 이상 조건 (테스트용으로 완화)
            if all(float(d['acml_tr_pbmn']) >= 50000000000 for d in days):
                res.append(row)
        time.sleep(0.1) # 호출 제한 방지
    
    bar.empty()
    return pd.DataFrame(res)

# --- 🪙 [코인] 업비트 데이터 ---
def get_upbit():
    try:
        url = "https://api.upbit.com/v1/market/all"
        m_list = requests.get(url).json()
        krw_m = [m['market'] for m in m_list if m['market'].startswith("KRW-")]
        m_names = {m['market']: m['korean_name'] for m in m_list}
        
        t_url = f"https://api.upbit.com/v1/ticker?markets={','.join(krw_m[:30])}"
        tickers = requests.get(t_url).json()
        res = [{'종목명': m_names[t['market']], '현재가': t['trade_price'], '등락률': t['signed_change_rate']*100, '거래대금': t['acc_trade_price_24h']} for t in tickers]
        return pd.DataFrame(res).sort_values(by='거래대금', ascending=False)
    except: return pd.DataFrame()

# --- 📱 [UI] 메인 화면 ---
st.title("📈 Stock & Crypto Dashboard")

menu = st.selectbox("분석 모드", ["거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "암호화폐"])

if menu == "암호화폐":
    if st.button("데이터 불러오기"):
        df = get_upbit()
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
else:
    mkt = st.radio("시장", ["KOSPI", "KOSDAQ"], horizontal=True)
    mkt_code = "0001" if mkt == "KOSPI" else "1001"
    
    if st.button("실시간 분석 시작"):
        with st.spinner("증권사 API 연결 및 데이터 분석 중..."):
            res_df = analyze_stocks(menu, mkt_code)
            if not res_df.empty:
                out = res_df[['hts_kor_isnm', 'stck_prpr', 'prdy_ctrt', 'tr_pbmn']].copy()
                out.columns = ['종목명', '현재가', '등락률', '거래대금']
                # 거래대금 가독성 처리 (단위: 억)
                out['거래대금'] = out['거래대금'].apply(lambda x: f"{int(float(x)//100000000):,}억")
                st.dataframe(out, use_container_width=True, hide_index=True)
            else:
                st.warning("조건에 맞는 종목이 없거나 API 응답이 비어있습니다. (IP 설정 확인 필요)")

st.sidebar.write(f"📡 API 상태: {'연결됨' if get_access_token() else '연결 안됨'}")
