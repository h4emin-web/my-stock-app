import streamlit as st
import pandas as pd
import requests
import json
import time

# 1. 앱 설정
st.set_page_config(page_title="Stock & Crypto Manager", layout="centered")

# --- 🔑 1. 키 설정 (복사해서 넣으세요) ---
APP_KEY = "PSmBdpWduaskTXxqbcT6PuBTneKitnWiXnrL"
APP_SECRET = "adyZ3eYxXM74UlaErGZWe1SEJ9RPNo2wOD/mDWkJqkKfB0re+zVtKNiZM5loyVumtm5It+jTdgplqbimwqnyboerycmQWrlgA/Uwm8u4K66LB6+PhIoO6kf8zS196RO570kjshkBBecQzUUfwLlDWBIlTu/Mvu4qYYi5dstnsjgZh3Ic2Sw="
# 스크린샷에 있는 계좌번호 8자리
ACC_NO = "72590134" 

URL_BASE = "https://openapi.koreainvestment.com:9443"

# --- 🔐 2. 토큰 발급 (상세 에러 출력) ---
@st.cache_data(ttl=3600*12)
def get_kis_token():
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    res = requests.post(f"{URL_BASE}/oauth2/tokenP", headers=headers, data=json.dumps(body))
    if res.status_code == 200:
        return res.json().get('access_token')
    else:
        st.error(f"토큰 발급 실패: {res.json().get('error_description')}")
        return None

# --- 📊 3. 데이터 호출 함수 (헤더 보정) ---
def fetch_kis(path, tr_id, params):
    token = get_kis_token()
    if not token: return None
    
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P", # 개인
        "hashkey": "" # 조회용은 비워둬도 됨
    }
    
    try:
        res = requests.get(f"{URL_BASE}{path}", headers=headers, params=params)
        data = res.json()
        if res.status_code != 200 or data.get('rt_cd') != '0':
            # 한투에서 보내주는 실제 에러 메시지를 화면에 띄움
            st.error(f"⚠️ API 에러: {data.get('msg1')} ({data.get('msg_cd')})")
            return None
        return data
    except Exception as e:
        st.error(f"연결 오류: {str(e)}")
        return None

# --- [유틸리티] 단위 변환 ---
def format_unit(val):
    try:
        val = float(val)
        if val >= 1000000000000: return f"{int(val // 1000000000000)}조"
        if val >= 100000000: return f"{int(val // 100000000):,}억"
        return f"{int(val):,}"
    except: return "0"

# --- 🛠️ 4. 주식 분석 로직 ---
def get_kis_analyzed(mode, mkt_code):
    # 거래대금 상위 랭킹 (TR: FHPST01710000)
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": mkt_code,
        "FID_DIV_CLS_CODE": "0",
        "FID_BLNG_CLS_CODE": "0",
        "FID_TRGT_CLS_CODE": "0",
        "FID_TRGT_EXLS_CLS_CODE": "0",
        "FID_INPUT_PRICE_1": "0",
        "FID_INPUT_PRICE_2": "0",
        "FID_VOL_CNT": "0"
    }
    
    raw = fetch_kis("/uapi/domestic-stock/v1/ranking/trade-value", "FHPST01710000", params)
    if not raw: return pd.DataFrame()
    
    df = pd.DataFrame(raw.get('output', []))
    if df.empty: return df

    if mode == "거래대금 상위":
        return df.head(50)

    # 3일/5일 연속 로직 (상세 시세 조회 API 사용)
    res = []
    n = 3 if "3일" in mode else 5
    bar = st.progress(0)
    
    for i, (_, row) in enumerate(df.head(15).iterrows()): # 속도를 위해 상위 15개만 정밀분석
        bar.progress((i+1)/15)
        p = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": row['mksc_shrn_iscd'], "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0"}
        hist = fetch_kis("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100", p)
        
        if hist and 'output2' in hist:
            days_data = hist['output2'][:n]
            # 거래대금 1000억 이상 체크 (한투 일봉 대금은 '원' 단위일 수 있어 체크 필요)
            if all(float(d['acml_tr_pbmn']) >= 100000000000 for d in days_data):
                res.append(row)
        time.sleep(0.05) # 호출 제한 방지
    
    bar.empty()
    return pd.DataFrame(res)

# --- 🪙 5. 업비트 코인 로직 ---
def get_upbit():
    try:
        url = "https://api.upbit.com/v1/market/all"
        m_list = requests.get(url).json()
        krw_m = [m['market'] for m in m_list if m['market'].startswith("KRW-")]
        m_names = {m['market']: m['korean_name'] for m in m_list}
        
        t_url = f"https://api.upbit.com/v1/ticker?markets={','.join(krw_m[:50])}"
        tickers = requests.get(t_url).json()
        res = [{'코인명': m_names[t['market']], '현재가': t['trade_price'], '등락률': t['signed_change_rate']*100, '거래대금': t['acc_trade_price_24h']} for t in tickers]
        return pd.DataFrame(res).sort_values(by='거래대금', ascending=False)
    except: return pd.DataFrame()

# --- 📱 6. 메인 화면 ---
st.title("📈 Stock & Crypto Manager")

mode = st.selectbox("분석 모드", ["거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "암호화폐"])

if mode == "암호화폐":
    df = get_upbit()
    if not df.empty:
        df.insert(0, 'No', range(1, len(df)+1))
        df['거래대금'] = df['거래대금'].apply(format_unit)
        st.dataframe(df.style.format({'등락률': '{:.2f}%'}), use_container_width=True, hide_index=True)
else:
    mkt = st.radio("시장", ["KOSPI", "KOSDAQ"], horizontal=True)
    mkt_code = "0001" if mkt == "KOSPI" else "1001"
    
    if st.button("🚀 분석 시작"):
        with st.spinner("증권사 서버 연결 중..."):
            res_df = get_kis_analyzed(mode, mkt_code)
            if not res_df.empty:
                out = res_df[['hts_kor_isnm', 'stck_prpr', 'prdy_ctrt', 'tr_pbmn']].copy()
                out.columns = ['종목명', '현재가', '등락률', '거래대금']
                out.insert(0, 'No', range(1, len(out)+1))
                out['거래대금'] = out['거래대금'].apply(format_unit)
                st.dataframe(out, use_container_width=True, hide_index=True)
            else:
                st.warning("조건에 맞는 종목이 없거나 조회가 차단되었습니다.")
