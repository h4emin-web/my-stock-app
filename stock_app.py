import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime, timedelta
import time

# 1. 앱 설정
st.set_page_config(page_title="Stock", layout="centered")

# --- 한투 API 인증 정보 (여기에 발급받으신 키를 넣으세요) ---
APP_KEY = "PSmBdpWduaskTXxqbcT6PuBTneKitnWiXnrL_APP_KEY"
APP_SECRET = "adyZ3eYxXM74UlaErGZWe1SEJ9RPNo2wOD/mDWkJqkKfB0re+zVtKNiZM5loyVumtm5It+jTdgplqbimwqnyboerycmQWrlgA/Uwm8u4K66LB6+PhIoO6kf8zS196RO570kjshkBBecQzUUfwLlDWBIlTu/Mvu4qYYi5dstnsjgZh3Ic2Sw=_APP_SECRET"
URL_BASE = "https://openapi.koreainvestment.com:9443" # 실전 투자용 주소

# --- 인증 토큰 발급 함수 ---
@st.cache_data(ttl=3600*24) # 토큰은 하루 동안 유효
def get_access_token():
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    res = requests.post(f"{URL_BASE}/oauth2/tokenP", headers=headers, data=json.dumps(body))
    return res.json().get('access_token')

# --- 유틸리티: 한국 단위 변환 ---
def format_korean_unit(val):
    val = float(val)
    if val >= 1000000000000: return f"{int(val // 1000000000000)}조"
    if val >= 100000000: return f"{int(val // 100000000):,}억"
    return f"{int(val):,}"

# --- 데이터 가져오기 (주요 로직) ---
def get_kis_stock_data(mode, market_code):
    token = get_access_token()
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST01010100" # 주식 현재가 시세 ID (예시)
    }
    
    # 실제 구현 시에는 전 종목 시세를 가져오는 'FHKST01010100' 또는 
    # '거래대금 상위' 전용 TR인 'FHPST01710000' 등을 사용합니다.
    
    # [예시] 거래대금 상위 30종목 가져오기 (TR: FHPST01710000)
    params = {
        "FID_COND_MRKT_DIV_CODE": "J", # 주식
        "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": market_code, # 0000(전체), 0001(코스피), 1001(코스닥)
        "FID_DIV_CLS_CODE": "0",
        "FID_BLNG_CLS_CODE": "0",
        "FID_TRGT_CLS_CODE": "0",
        "FID_TRGT_EXLS_CLS_CODE": "0",
        "FID_INPUT_PRICE_1": "0",
        "FID_INPUT_PRICE_2": "0",
        "FID_VOL_CNT": "0"
    }
    
    res = requests.get(f"{URL_BASE}/uapi/domestic-stock/v1/ranking/trade-value", 
                       headers={**headers, "tr_id": "FHPST01710000"}, params=params)
    
    if res.status_code == 200:
        output = res.json().get('output', [])
        df = pd.DataFrame(output)
        # 한투 API 결과 컬럼명 매핑 (hts_kor_isnm: 종목명, stck_prpr: 현재가, prdy_ctrt: 등락률, tr_pbmn: 거래대금)
        return df[['hts_kor_isnm', 'stck_prpr', 'prdy_ctrt', 'tr_pbmn']]
    return pd.DataFrame()

# --- 앱 UI ---
st.title("Stock (KIS API)")

mode = st.selectbox("분석 모드", ["거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "고가놀이", "암호화폐"])

if mode == "암호화폐":
    st.write("기존 업비트 로직 실행...")
else:
    mkt = st.radio("시장 선택", ["KOSPI", "KOSDAQ"], horizontal=True)
    mkt_code = "0001" if mkt == "KOSPI" else "1001"
    
    if st.button("데이터 불러오기"):
        with st.spinner("증권사 서버에서 직접 데이터를 가져오는 중..."):
            df = get_kis_stock_data(mode, mkt_code)
            
            if not df.empty:
                df.columns = ['기업명', '현재가', '등락률', '거래대금']
                df['거래대금'] = df['거래대금'].apply(format_korean_unit)
                st.dataframe(df, use_container_width=True)
            else:
                st.error("API 연결 실패. 키 설정을 확인하세요.")
