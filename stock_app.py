import streamlit as st
import pandas as pd
import requests
import json
import time
from datetime import datetime

# 1. 인증 정보 (사용자님 키)
APP_KEY = "PSmBdpWduaskTXxqbcT6PuBTneKitnWiXnrL"
APP_SECRET = "adyZ3eYxXM74UlaErGZWe1SEJ9RPNo2wOD/mDWkJqkKfB0re+zVtKNiZM5loyVumtm5It+jTdgplqbimwqnyboerycmQWrlgA/Uwm8u4K66LB6+PhIoO6kf8zS196RO570kjshkBBecQzUUfwLlDWBIlTu/Mvu4qYYi5dstnsjgZh3Ic2Sw="
URL_BASE = "https://openapi.koreainvestment.com:9443"

@st.cache_data(ttl=3600)
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

# 2. 핵심 분석 함수
def get_analyzed_data(mode, mkt_id):
    # [Step 1] 실시간 거래대금 상위 50개 가져오기 (이미 거래대금순으로 정렬되어 옴)
    p = {
        "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": mkt_id, "FID_DIV_CLS_CODE": "0", "FID_BLNG_CLS_CODE": "0",
        "FID_TRGT_CLS_CODE": "0", "FID_TRGT_EXLS_CLS_CODE": "0", "FID_INPUT_PRICE_1": "0",
        "FID_INPUT_PRICE_2": "0", "FID_VOL_CNT": "0"
    }
    raw = fetch_kis("/uapi/domestic-stock/v1/ranking/trade-value", "FHPST01710000", p)
    if not raw or 'output' not in raw: return pd.DataFrame()
    
    top_items = raw['output']
    results = []
    
    prog = st.progress(0)
    status = st.empty()

    # 상위 30개 종목에 대해 조건 검증 (거래대금 순서 유지)
    for i, item in enumerate(top_items[:30]):
        ticker = item['mksc_shrn_iscd']
        name = item['hts_kor_isnm']
        status.text(f"🔍 '{name}' 조건 분석 중... ({i+1}/30)")
        prog.progress((i+1)/30)

        # 종목별 최근 일봉 데이터(10일치) 가져오기
        p_hist = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker, "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0"}
        hist = fetch_kis("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100", p_hist)
        
        if hist and 'output2' in hist:
            days = hist['output2'] # 0번이 오늘, 1번이 어제...
            
            # 데이터 추출
            today_amt = float(days[0]['acml_tr_pbmn'])
            today_rate = float(days[0]['prdy_ctrt'])
            
            is_match = False
            
            if mode == "거래대금 상위":
                is_match = True
            
            elif "연속 거래대금" in mode:
                n = 3 if "3일" in mode else 5
                # 기준 완화: 연속 n일 동안 거래대금이 300억 이상인지 체크
                if len(days) >= n:
                    check = [float(days[j]['acml_tr_pbmn']) >= 30000000000 for j in range(n)]
                    if all(check): is_match = True
            
            elif mode == "고가놀이":
                # 기준: 4일 전 15% 이상 급등 후, 최근 3일간 종가가 -5% ~ +5% 내에서 횡보
                if len(days) >= 4:
                    big_up = float(days[3]['prdy_ctrt']) >= 15
                    avg_move = sum(float(days[j]['prdy_ctrt']) for j in range(3)) / 3
                    if big_up and abs(avg_move) <= 5: is_match = True

            if is_match:
                results.append({
                    "종목명": name,
                    "현재가": f"{int(float(days[0]['stck_clpr'])):,}원",
                    "등락률": today_rate,
                    "거래대금": today_amt,
                    "순위": int(item['data_rank'])
                })
        
        time.sleep(0.05) # API 제한 준수

    prog.empty()
    status.empty()
    
    # 결과가 있으면 거래대금(또는 원래 순위) 순으로 정렬하여 반환
    res_df = pd.DataFrame(results)
    if not res_df.empty:
        return res_df.sort_values(by="거래대금", ascending=False)
    return res_df

# 3. UI 구성
st.title("📈 해민증권 실시간 분석")

mode = st.selectbox("분석 조건 선택", ["거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "고가놀이"])
mkt = st.radio("시장 선택", ["KOSPI", "KOSDAQ"], horizontal=True)
mkt_id = "0001" if mkt == "KOSPI" else "1001"

if st.button("🚀 조건 검색 시작"):
    with st.spinner("한국투자증권 API 정밀 분석 중..."):
        df = get_analyzed_data(mode, mkt_id)
        
        if not df.empty:
            # 출력용 가공
            df['거래대금(억)'] = df['거래대금'].apply(lambda x: f"{int(x//100000000):,}억")
            
            st.success(f"조건에 맞는 종목 {len(df)}개를 찾았습니다 (거래대금 순 정렬)")
            st.dataframe(
                df[['종목명', '현재가', '등락률', '거래대금(억)']].style.map(
                    lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''), 
                    subset=['등락률']
                ).format({'등락률': '{:.2f}%'}),
                use_container_width=True, hide_index=True, height=600
            )
        else:
            st.warning("조건에 맞는 종목이 없습니다. 기준을 더 낮추거나 시장을 변경해 보세요.")
