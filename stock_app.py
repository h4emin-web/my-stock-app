import streamlit as st
import pandas as pd
import requests
import json
import time

# --- 인증 정보 (한국투자증권 실전투자용) ---
APP_KEY = "PSmBdpWduaskTXxqbcT6PuBTneKitnWiXnrL".strip()
APP_SECRET = "adyZ3eYxXM74UlaErGZWe1SEJ9RPNo2wOD/mDWkJqkKfB0re+zVtKNiZM5loyVumtm5It+jTdgplqbimwqnyboerycmQWrlgA/Uwm8u4K66LB6+PhIoO6kf8zS196RO570kjshkBBecQzUUfwLlDWBIlTu/Mvu4qYYi5dstnsjgZh3Ic2Sw=".strip()
URL_BASE = "https://openapi.koreainvestment.com:9443"

def get_token():
    url = f"{URL_BASE}/oauth2/tokenP"
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    res = requests.post(url, data=json.dumps(body))
    return res.json().get('access_token')

def fetch_kis(path, tr_id, params):
    headers = {
        "Content-Type": "application/json", "authorization": f"Bearer {get_token()}",
        "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": tr_id, "custtype": "P"
    }
    res = requests.get(f"{URL_BASE}{path}", headers=headers, params=params)
    return res.json()

def analyze_high_pattern(mkt_id):
    # 1. 일단 시장에서 거래대금이 많이 터지는 종목 50개를 먼저 가져옴
    p = {
        "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": mkt_id, "FID_DIV_CLS_CODE": "0", "FID_BLNG_CLS_CODE": "0",
        "FID_TRGT_CLS_CODE": "0", "FID_TRGT_EXLS_CLS_CODE": "0", "FID_INPUT_PRICE_1": "",
        "FID_INPUT_PRICE_2": "", "FID_VOL_CNT": ""
    }
    raw = fetch_kis("/uapi/domestic-stock/v1/ranking/trade-value", "FHPST01710000", p)
    
    if not raw or 'output' not in raw:
        st.error("데이터를 불러오지 못했습니다. API 키나 서버 상태를 확인하세요.")
        return pd.DataFrame()
    
    results = []
    items = raw['output'][:30] # 상위 30개 집중 분석
    
    prog = st.progress(0)
    status_text = st.empty()

    for i, item in enumerate(items):
        ticker = item['mksc_shrn_iscd']
        name = item['hts_kor_isnm']
        status_text.text(f"🔍 {name} 패턴 분석 중...")
        prog.progress((i+1)/len(items))
        
        # 2. 각 종목의 최근 10일치 차트 데이터 조회
        p_hist = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker, "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0"}
        hist = fetch_kis("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100", p_hist)
        
        if hist and 'output2' in hist and len(hist['output2']) > 5:
            days = hist['output2']
            
            # [조건 1] 최근 10일 이내에 하루라도 15% 이상 급등한 적이 있는가?
            spike_day = [float(d['prdy_ctrt']) >= 15 for d in days[1:10]]
            
            # [조건 2] 오늘 등락률이 -5% ~ +5% 사이로 횡보 중인가? (고가에서 버티기)
            today_rate = float(days[0]['prdy_ctrt'])
            is_sideways = -5.0 <= today_rate <= 5.0
            
            # [조건 3] 오늘 거래대금이 최소 200억 이상인가? (관심이 살아있는가)
            today_amt = float(days[0]['acml_tr_pbmn'])
            has_volume = today_amt >= 20000000000
            
            if any(spike_day) and is_sideways and has_volume:
                results.append({
                    "종목명": name,
                    "현재가": f"{int(float(days[0]['stck_clpr'])):,}원",
                    "등락률": f"{today_rate:.2f}%",
                    "거래대금": f"{int(today_amt//100000000):,}억",
                    "최고등락(10일내)": f"{max([float(d['prdy_ctrt']) for d in days[1:10]]):.1f}%"
                })
        
        time.sleep(0.1) # API 차단 방지

    prog.empty()
    status_text.empty()
    return pd.DataFrame(results)

# --- UI ---
st.title("🔥 고가놀이 종목 발굴기")
st.caption("최근 급등 후 고점에서 매물을 소화하며 횡보하는 종목을 찾습니다.")

mkt = st.radio("분석 시장 선택", ["KOSPI", "KOSDAQ"], horizontal=True)
mkt_id = "0001" if mkt == "KOSPI" else "1001"

if st.button("고가놀이 종목 찾기"):
    with st.spinner("최근 10일간의 차트를 전수 분석 중..."):
        df = analyze_high_pattern(mkt_id)
        
        if not df.empty:
            st.success(f"조건에 딱 맞는 종목을 {len(df)}개 발견했습니다!")
            st.table(df) # 깔끔하게 표로 출력
        else:
            st.warning("현재 고가놀이 패턴을 보이는 종목이 없습니다. 시장을 변경해보세요.")
