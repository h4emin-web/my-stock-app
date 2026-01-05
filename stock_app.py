import streamlit as st
import pandas as pd
import requests
import json
import time

# --- 1. 인증 정보 ---
APP_KEY = "PSmBdpWduaskTXxqbcT6PuBTneKitnWiXnrL"
APP_SECRET = "adyZ3eYxXM74UlaErGZWe1SEJ9RPNo2wOD/mDWkJqkKfB0re+zVtKNiZM5loyVumtm5It+jTdgplqbimwqnyboerycmQWrlgA/Uwm8u4K66LB6+PhIoO6kf8zS196RO570kjshkBBecQzUUfwLlDWBIlTu/Mvu4qYYi5dstnsjgZh3Ic2Sw="
URL_BASE = "https://openapi.koreainvestment.com:9443"

# 토큰 발급 (에러 방지를 위해 캐시 제거 버전)
def get_token():
    url = f"{URL_BASE}/oauth2/tokenP"
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    res = requests.post(url, data=json.dumps(body))
    if res.status_code == 200:
        return res.json().get('access_token')
    else:
        st.error(f"토큰 발급 실패: {res.text}")
        return None

# API 호출 함수 (JSON 에러 예외 처리 추가)
def fetch_kis(path, tr_id, params):
    token = get_token()
    if not token: return None
    
    headers = {
        "Content-Type": "application/json", 
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY, 
        "appsecret": APP_SECRET, 
        "tr_id": tr_id, 
        "custtype": "P"
    }
    
    res = requests.get(f"{URL_BASE}{path}", headers=headers, params=params)
    
    try:
        return res.json()
    except Exception as e:
        st.error(f"API 응답 해석 실패 (JSON 에러): {res.status_code} - {res.text[:100]}")
        return None

# --- 2. 분석 로직 ---
def get_analyzed_data(mode, mkt_id):
    # 거래대금 상위 50개 리스트
    p = {
        "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": mkt_id, "FID_DIV_CLS_CODE": "0", "FID_BLNG_CLS_CODE": "0",
        "FID_TRGT_CLS_CODE": "0", "FID_TRGT_EXLS_CLS_CODE": "0", "FID_INPUT_PRICE_1": "0",
        "FID_INPUT_PRICE_2": "0", "FID_VOL_CNT": "0"
    }
    raw = fetch_kis("/uapi/domestic-stock/v1/ranking/trade-value", "FHPST01710000", p)
    
    if not raw or 'output' not in raw:
        return pd.DataFrame()
    
    results = []
    prog = st.progress(0)
    
    # 상위 20개만 정밀 분석 (속도 및 안정성)
    for i, item in enumerate(raw['output'][:20]):
        prog.progress((i+1)/20)
        ticker = item['mksc_shrn_iscd']
        name = item['hts_kor_isnm']
        
        # 일봉 데이터 조회
        p_hist = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker, "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0"}
        hist = fetch_kis("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100", p_hist)
        
        if hist and 'output2' in hist:
            days = hist['output2']
            if not days: continue
            
            curr_amt = float(days[0]['acml_tr_pbmn'])
            curr_rate = float(days[0]['prdy_ctrt'])
            
            match = False
            if mode == "거래대금 상위":
                match = True
            elif "연속 거래대금" in mode:
                n = 3 if "3일" in mode else 5
                if len(days) >= n:
                    # 기준: n일 연속 거래대금 300억 이상
                    check = [float(days[j]['acml_tr_pbmn']) >= 30000000000 for j in range(n)]
                    if all(check): match = True
            elif mode == "고가놀이":
                # 기준: 4일 전 급등(15%↑) 후 3일간 횡보
                if len(days) >= 4 and float(days[3]['prdy_ctrt']) >= 15:
                    avg_3d = sum(float(days[j]['prdy_ctrt']) for j in range(3)) / 3
                    if abs(avg_3d) <= 5: match = True
            
            if match:
                results.append({
                    "종목명": name,
                    "현재가": f"{int(float(days[0]['stck_clpr'])):,}원",
                    "등락률": curr_rate,
                    "거래대금": curr_amt,
                    "거래대금(억)": f"{int(curr_amt//100000000):,}억"
                })
        time.sleep(0.1) # TPS 제한 방지

    prog.empty()
    # 결과를 거래대금 높은 순으로 정렬
    df = pd.DataFrame(results)
    return df.sort_values(by="거래대금", ascending=False) if not df.empty else df

# --- 3. 메인 UI ---
st.title("해민증권 📈")

mode = st.selectbox("분석 모드", ["거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "고가놀이"])
mkt = st.radio("시장", ["KOSPI", "KOSDAQ"], horizontal=True)
mkt_id = "0001" if mkt == "KOSPI" else "1001"

if st.button("분석 실행"):
    with st.spinner("데이터 분석 중..."):
        df = get_analyzed_data(mode, mkt_id)
        if not df.empty:
            st.dataframe(
                df[['종목명', '현재가', '등락률', '거래대금(억)']].style.map(
                    lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''), subset=['등락률']
                ).format({'등락률': '{:.2f}%'}),
                use_container_width=True, hide_index=True
            )
        else:
            st.info("조건에 맞는 종목이 없습니다.")
