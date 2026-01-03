import streamlit as st
import pandas as pd
import requests
import json
import time

# 1. 앱 설정
st.set_page_config(page_title="Stock & Crypto Manager", layout="centered")

# --- 🔑 사용자 설정 (보내주신 정보를 여기에 입력하세요) ---
APP_KEY = "PSmBdpWduaskTXxqbcT6PuBTneKitnWiXnrL"
APP_SECRET = "adyZ3eYxXM74UlaErGZWe1SEJ9RPNo2wOD/mDWkJqkKfB0re+zVtKNiZM5loyVumtm5It+jTdgplqbimwqnyboerycmQWrlgA/Uwm8u4K66LB6+PhIoO6kf8zS196RO570kjshkBBecQzUUfwLlDWBIlTu/Mvu4qYYi5dstnsjgZh3Ic2Sw="
ACC_NO = "72590134"  # 보내주신 이미지 속 계좌번호 8자리
ACC_PROD = "01"      # 종합계좌 상품코드 (기본값 01)

URL_BASE = "https://openapi.koreainvestment.com:9443" # 실전투자 주소

# --- 🔐 [인증] 토큰 발급 (보안 강화) ---
@st.cache_data(ttl=3600*12)
def get_kis_token():
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    try:
        res = requests.post(f"{URL_BASE}/oauth2/tokenP", headers=headers, data=json.dumps(body), timeout=10)
        if res.status_code == 200:
            return res.json().get('access_token')
        else:
            st.error(f"❌ 인증 실패: {res.json().get('error_description')}")
            return None
    except Exception as e:
        st.error(f"🔌 접속 불가: {str(e)}")
        return None

# --- 📊 [데이터] KIS API 호출 함수 ---
def fetch_kis(path, tr_id, params):
    token = get_kis_token()
    if not token: return None
    
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P", # 개인고객
    }
    
    try:
        res = requests.get(f"{URL_BASE}{path}", headers=headers, params=params, timeout=10)
        # JSON 파싱 전 빈 응답 체크
        if not res.text.strip():
            st.error("⚠️ 증권사 서버에서 빈 데이터를 보냈습니다. IP 차단 여부를 확인하세요.")
            return None
        return res.json()
    except Exception as e:
        st.error(f"📡 네트워크 오류: {str(e)}")
        return None

# --- [유틸리티] 단위 변환 ---
def format_unit(val):
    try:
        val = float(val)
        if val >= 1000000000000: return f"{int(val // 1000000000000)}조"
        if val >= 100000000: return f"{int(val // 100000000):,}억"
        return f"{int(val):,}"
    except: return "0"

# --- 🛠️ [주식] 분석 로직 ---
def get_kis_analyzed(mode, mkt_code):
    # 거래대금 상위 랭킹 (전 종목 대상)
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": mkt_code, # 0001:코스피, 1001:코스닥
        "FID_DIV_CLS_CODE": "0",
        "FID_BLNG_CLS_CODE": "0",
        "FID_TRGT_CLS_CODE": "0",
        "FID_TRGT_EXLS_CLS_CODE": "0",
        "FID_INPUT_PRICE_1": "0",
        "FID_INPUT_PRICE_2": "0",
        "FID_VOL_CNT": "0"
    }
    
    raw = fetch_kis("/uapi/domestic-stock/v1/ranking/trade-value", "FHPST01710000", params)
    if not raw or 'output' not in raw: return pd.DataFrame()
    
    df = pd.DataFrame(raw['output'])
    
    if mode == "거래대금 상위":
        return df.head(50)

    # 3일/5일 연속 거래대금 로직
    res = []
    n = 3 if "3일" in mode else 5
    bar = st.progress(0)
    
    target_stocks = df.head(15) # 속도와 안정성을 위해 상위 15개 집중 분석
    for i, (_, row) in enumerate(target_stocks.iterrows()):
        bar.progress((i+1)/len(target_stocks))
        p = {
            "FID_COND_MRKT_DIV_CODE": "J", 
            "FID_INPUT_ISCD": row['mksc_shrn_iscd'], 
            "FID_PERIOD_DIV_CODE": "D", 
            "FID_ORG_ADJ_PRC": "0"
        }
        hist = fetch_kis("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100", p)
        
        if hist and 'output2' in hist:
            days = hist['output2'][:n]
            # 최근 n일간 모든 거래대금이 1,000억 이상인지 체크
            if all(float(d['acml_tr_pbmn']) >= 100000000000 for d in days):
                res.append(row)
        time.sleep(0.1) # 초당 호출 제한 방지
    
    bar.empty()
    return pd.DataFrame(res)

# --- 🪙 [코인] 업비트 실시간 조회 ---
def get_upbit_data():
    try:
        url = "https://api.upbit.com/v1/market/all"
        m_list = requests.get(url).json()
        krw_m = [m['market'] for m in m_list if m['market'].startswith("KRW-")]
        m_names = {m['market']: m['korean_name'] for m in m_list}
        
        t_url = f"https://api.upbit.com/v1/ticker?markets={','.join(krw_m[:50])}"
        tickers = requests.get(t_url).json()
        res = []
        for t in tickers:
            res.append({
                '종목명': m_names[t['market']], 
                '현재가': t['trade_price'], 
                '등락률': t['signed_change_rate']*100, 
                '거래대금': t['acc_trade_price_24h']
            })
        return pd.DataFrame(res).sort_values(by='거래대금', ascending=False)
    except: return pd.DataFrame()

# --- 📱 메인 화면 UI ---
st.title("🚀 Stock & Crypto Manager")

mode = st.selectbox("분석 모드 선택", ["거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "암호화폐"])

if mode == "암호화폐":
    if st.button("🌕 코인 시세 불러오기"):
        with st.spinner("업비트 서버 연결 중..."):
            df = get_upbit_data()
            if not df.empty:
                df.insert(0, 'No', range(1, len(df)+1))
                df['거래대금'] = df['거래대금'].apply(format_unit)
                st.dataframe(df.style.format({'등락률': '{:.2f}%'}), use_container_width=True, hide_index=True)
else:
    mkt = st.radio("시장 선택", ["KOSPI", "KOSDAQ"], horizontal=True)
    mkt_code = "0001" if mkt == "KOSPI" else "1001"
    
    if st.button("🔥 주식 분석 시작"):
        with st.spinner(f"{mkt} 데이터 분석 중..."):
            res_df = get_kis_analyzed(mode, mkt_code)
            if not res_df.empty:
                # 출력 컬럼 정리
                out = res_df[['hts_kor_isnm', 'stck_prpr', 'prdy_ctrt', 'tr_pbmn']].copy()
                out.columns = ['종목명', '현재가', '등락률', '거래대금']
                out.insert(0, 'No', range(1, len(out)+1))
                out['현재가'] = out['현재가'].apply(lambda x: f"{int(x):,}")
                out['거래대금'] = out['거래대금'].apply(format_unit)
                st.dataframe(out, use_container_width=True, hide_index=True)
            else:
                st.warning("조건에 맞는 종목이 없습니다. (1,000억 이상 연속 발생 종목 없음)")

st.sidebar.markdown(f"**연결 계좌:** {ACC_NO}-{ACC_PROD}")
