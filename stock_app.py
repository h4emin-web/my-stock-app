import streamlit as st
import pandas as pd
import requests
import json

# 1. 앱 설정
st.set_page_config(page_title="Stock (KIS)", layout="centered")

# --- 🔑 여기에 발급받은 키를 정확히 입력하세요 ---
APP_KEY = "PSmBdpWduaskTXxqbcT6PuBTneKitnWiXnrL"  # 예: "PSf9kX..."
APP_SECRET = "adyZ3eYxXM74UlaErGZWe1SEJ9RPNo2wOD/mDWkJqkKfB0re+zVtKNiZM5loyVumtm5It+jTdgplqbimwqnyboerycmQWrlgA/Uwm8u4K66LB6+PhIoO6kf8zS196RO570kjshkBBecQzUUfwLlDWBIlTu/Mvu4qYYi5dstnsjgZh3Ic2Sw="  # 예: "abcde..."

# --- 🛠️ 실전/모의 자동 판별 및 주소 설정 ---
# 보통 실전 키는 'P'로 시작하거나 모의 키보다 깁니다. 
# 안전하게 선택할 수 있도록 사이드바 메뉴를 사용합니다.
with st.sidebar:
    st.header("⚙️ 접속 설정")
    acc_type = st.radio("계좌 종류를 선택하세요", ["실전투자", "모의투자"])
    
    if acc_type == "실전투자":
        URL_BASE = "https://openapi.koreainvestment.com:9443"
    else:
        URL_BASE = "https://openapivts.koreainvestment.com:29443"

# --- 🔐 토큰 발급 함수 ---
def get_access_token():
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    try:
        res = requests.post(f"{URL_BASE}/oauth2/tokenP", headers=headers, data=json.dumps(body))
        if res.status_code == 200:
            return res.json().get('access_token'), None
        else:
            # 상세 에러 메시지 반환
            return None, res.json().get('error_description', '키 설정을 다시 확인해주세요.')
    except Exception as e:
        return None, str(e)

# --- 📊 데이터 조회 함수 ---
def get_stock_ranking(mkt_code):
    token, err = get_access_token()
    if err: return None, err
    
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHPST01710000", # 거래대금 상위 TR
        "custtype": "P"
    }
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
    
    res = requests.get(f"{URL_BASE}/uapi/domestic-stock/v1/ranking/trade-value", headers=headers, params=params)
    if res.status_code == 200:
        return pd.DataFrame(res.json().get('output', [])), None
    return None, "데이터를 불러오지 못했습니다."

# --- 📱 화면 구성 ---
st.title("📈 Stock Manager")

# 연결 테스트용
if st.sidebar.button("🔌 연결 상태 확인"):
    token, err = get_access_token()
    if token: st.sidebar.success("정상적으로 연결되었습니다!")
    else: st.sidebar.error(f"연결 실패: {err}")

mkt = st.radio("시장 선택", ["KOSPI", "KOSDAQ"], horizontal=True)
mkt_code = "0001" if mkt == "KOSPI" else "1001"

if st.button("🚀 데이터 불러오기"):
    with st.spinner("증권사 서버에서 실시간 데이터 수신 중..."):
        df, err = get_stock_ranking(mkt_code)
        if err:
            st.error(f"❌ 오류 발생: {err}")
        elif df is not None:
            # 보기 좋게 가공
            df = df[['hts_kor_isnm', 'stck_prpr', 'prdy_ctrt', 'tr_pbmn']].copy()
            df.columns = ['종목명', '현재가', '등락률', '거래대금(억)']
            st.dataframe(df, use_container_width=True, hide_index=True)
