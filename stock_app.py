import streamlit as st
import pandas as pd
import requests
import json
import time

# --- 1. 인증 정보 (공백이 없는지 꼭 확인하세요) ---
APP_KEY = "PSmBdpWduaskTXxqbcT6PuBTneKitnWiXnrL"
APP_SECRET = "adyZ3eYxXM74UlaErGZWe1SEJ9RPNo2wOD/mDWkJqkKfB0re+zVtKNiZM5loyVumtm5It+jTdgplqbimwqnyboerycmQWrlgA/Uwm8u4K66LB6+PhIoO6kf8zS196RO570kjshkBBecQzUUfwLlDWBIlTu/Mvu4qYYi5dstnsjgZh3Ic2Sw="
URL_BASE = "https://openapi.koreainvestment.com:9443"

def get_token():
    url = f"{URL_BASE}/oauth2/tokenP"
    body = {"grant_type": "client_credentials", "appkey": APP_KEY.strip(), "appsecret": APP_SECRET.strip()}
    res = requests.post(url, data=json.dumps(body))
    try:
        data = res.json()
        if res.status_code == 200:
            return data.get('access_token')
        else:
            st.error(f"❌ 토큰 발급 실패 (코드 {res.status_code}): {data.get('msg1', '알 수 없는 에러')}")
            return None
    except:
        st.error(f"❌ 서버 응답이 JSON 형식이 아닙니다 (HTML 응답): {res.text[:200]}")
        return None

def fetch_kis(path, tr_id, params):
    token = get_token()
    if not token: return None
    
    headers = {
        "Content-Type": "application/json", 
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY.strip(), 
        "appsecret": APP_SECRET.strip(), 
        "tr_id": tr_id, 
        "custtype": "P"
    }
    
    res = requests.get(f"{URL_BASE}{path}", headers=headers, params=params)
    
    try:
        return res.json()
    except Exception:
        # JSON이 아닌 경우 에러 상세 출력
        st.error(f"❌ 데이터 해석 실패! 서버에서 아래와 같이 응답했습니다:\n\n {res.text[:300]}")
        return None

# --- 2. 분석 로직 (거래대금순 정렬 보강) ---
def get_analyzed_data(mode, mkt_id):
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
    
    # 상위 25개 분석 (거래대금 순서 유지)
    for i, item in enumerate(raw['output'][:25]):
        prog.progress((i+1)/25)
        ticker = item['mksc_shrn_iscd']
        name = item['hts_kor_isnm']
        
        # 일봉 조회
        p_hist = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker, "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0"}
        hist = fetch_kis("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100", p_hist)
        
        if hist and 'output2' in hist and len(hist['output2']) > 0:
            days = hist['output2']
            amt = float(days[0]['acml_tr_pbmn'])
            rate = float(days[0]['prdy_ctrt'])
            
            match = False
            if mode == "거래대금 상위": match = True
            elif "연속 거래대금" in mode:
                n = 3 if "3일" in mode else 5
                if len(days) >= n:
                    # 완화된 기준: n일 연속 300억 이상
                    if all(float(days[j]['acml_tr_pbmn']) >= 30000000000 for j in range(n)):
                        match = True
            elif mode == "고가놀이":
                if len(days) >= 4 and float(days[3]['prdy_ctrt']) >= 15:
                    if abs(sum(float(days[j]['prdy_ctrt']) for j in range(3))/3) <= 5:
                        match = True
            
            if match:
                results.append({
                    "종목명": name,
                    "현재가": f"{int(float(days[0]['stck_clpr'])):,}원",
                    "등락률": rate,
                    "거래대금": amt,
                    "거래대금(억)": f"{int(amt//100000000):,}억"
                })
        time.sleep(0.05)

    prog.empty()
    df = pd.DataFrame(results)
    return df.sort_values(by="거래대금", ascending=False) if not df.empty else df

# --- 3. UI ---
st.title("📈 해민증권 실시간 분석기")

mode = st.selectbox("분석 모드", ["거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "고가놀이"])
mkt_name = st.radio("시장", ["KOSPI", "KOSDAQ"], horizontal=True)
mkt_id = "0001" if mkt_name == "KOSPI" else "1001"

if st.button("실시간 데이터 분석 시작"):
    with st.spinner("한국투자증권 서버와 통신 중..."):
        df = get_analyzed_data(mode, mkt_id)
        if not df.empty:
            st.dataframe(
                df[['종목명', '현재가', '등락률', '거래대금(억)']].style.map(
                    lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''), subset=['등락률']
                ).format({'등락률': '{:.2f}%'}),
                use_container_width=True, hide_index=True
            )
        else:
            st.warning("조건에 맞는 종목이 없거나 API 응답에 문제가 있습니다.")
