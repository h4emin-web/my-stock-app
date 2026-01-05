import streamlit as st
import pandas as pd
import requests
import json
import time
from datetime import datetime, timedelta

# --- 1. 앱 설정 ---
st.set_page_config(page_title="KIS 주식/코인 분석기", layout="wide")

# --- 2. 인증 정보 (제공해주신 키 사용) ---
APP_KEY = "PSmBdpWduaskTXxqbcT6PuBTneKitnWiXnrL"
APP_SECRET = "adyZ3eYxXM74UlaErGZWe1SEJ9RPNo2wOD/mDWkJqkKfB0re+zVtKNiZM5loyVumtm5It+jTdgplqbimwqnyboerycmQWrlgA/Uwm8u4K66LB6+PhIoO6kf8zS196RO570kjshkBBecQzUUfwLlDWBIlTu/Mvu4qYYi5dstnsjgZh3Ic2Sw="
URL_BASE = "https://openapi.koreainvestment.com:9443"

# --- 3. 핵심 함수 (토큰 및 API 호출) ---
@st.cache_data(ttl=3600*12)
def get_token():
    try:
        url = f"{URL_BASE}/oauth2/tokenP"
        body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
        res = requests.post(url, data=json.dumps(body))
        return res.json().get('access_token')
    except:
        return None

def fetch_kis(path, tr_id, params):
    token = get_token()
    if not token: return None
    headers = {
        "Content-Type": "application/json", "authorization": f"Bearer {token}",
        "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": tr_id, "custtype": "P"
    }
    try:
        res = requests.get(f"{URL_BASE}{path}", headers=headers, params=params)
        return res.json()
    except:
        return None

# --- 4. 분석 로직 (날짜 매칭 및 조건 검사) ---
def analyze_stocks(mkt_id, target_date, mode):
    target_date_str = target_date.strftime("%Y%m%d")
    
    # [Step 1] 기준이 될 종목 리스트 가져오기 (거래대금 상위 30개)
    p = {
        "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": mkt_id, "FID_DIV_CLS_CODE": "0", "FID_BLNG_CLS_CODE": "0",
        "FID_TRGT_CLS_CODE": "0", "FID_TRGT_EXLS_CLS_CODE": "0", "FID_INPUT_PRICE_1": "0",
        "FID_INPUT_PRICE_2": "0", "FID_VOL_CNT": "0"
    }
    raw_data = fetch_kis("/uapi/domestic-stock/v1/ranking/trade-value", "FHPST01710000", p)
    
    if not raw_data or 'output' not in raw_data:
        st.error("API로부터 종목 리스트를 불러오지 못했습니다.")
        return pd.DataFrame()

    items = raw_data['output']
    results = []
    
    prog = st.progress(0)
    status = st.empty()

    for i, item in enumerate(items[:30]): # 상위 30개만 정밀 분석 (속도/제한 고려)
        ticker = item['mksc_shrn_iscd']
        name = item['hts_kor_isnm']
        status.text(f"🔍 '{name}' 분석 중... ({i+1}/30)")
        prog.progress((i+1)/30)

        # [Step 2] 종목별 과거 일봉 데이터 조회
        p_hist = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker, "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0"}
        hist = fetch_kis("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100", p_hist)
        
        if hist and 'output2' in hist:
            days = hist['output2']
            # 선택한 날짜의 데이터 위치 찾기
            idx = next((i for i, d in enumerate(days) if d['stck_bsop_date'] == target_date_str), None)
            
            if idx is not None:
                d = days[idx]
                curr_val = float(d['acml_tr_pbmn']) # 거래대금
                curr_rate = float(d['prdy_ctrt'])   # 등락률
                
                match = False
                if mode == "전체 보기":
                    match = True
                elif mode == "3일 연속 거래대금 500억↑":
                    if len(days) >= idx + 3:
                        check = [float(days[idx+j]['acml_tr_pbmn']) >= 50000000000 for j in range(3)]
                        if all(check): match = True
                elif mode == "고가놀이(급등 후 횡보)":
                    if len(days) >= idx + 4:
                        big_up = float(days[idx+3]['prdy_ctrt']) >= 15 # 4일전 급등
                        side_move = abs(sum(float(days[idx+j]['prdy_ctrt']) for j in range(3))/3) <= 5
                        if big_up and side_move: match = True
                
                if match:
                    results.append({
                        "종목명": name,
                        "날짜": d['stck_bsop_date'],
                        "종가": f"{int(d['stck_clpr']):,}원",
                        "등락률": f"{curr_rate}%",
                        "거래대금": f"{int(curr_val//100000000):,}억"
                    })
        
        time.sleep(0.05) # 초당 호출 제한 준수

    status.empty()
    prog.empty()
    return pd.DataFrame(results)

# --- 5. 메인 화면 구성 ---
st.title("📈 주식 & 코인 스마트 분석기")

with st.sidebar:
    st.header("설정")
    target_date = st.date_input("분석 기준 날짜", datetime.now())
    mkt = st.radio("시장 선택", ["KOSPI", "KOSDAQ"])
    mkt_id = "0001" if mkt == "KOSPI" else "1001"
    mode = st.selectbox("분석 조건", ["전체 보기", "3일 연속 거래대금 500억↑", "고가놀이(급등 후 횡보)", "암호화폐(업비트)"])

if st.button("분석 실행"):
    if mode == "암호화폐(업비트)":
        with st.spinner("코인 시세 조회 중..."):
            coins = "KRW-BTC,KRW-ETH,KRW-SOL,KRW-XRP,KRW-DOGE"
            res = requests.get(f"https://api.upbit.com/v1/ticker?markets={coins}").json()
            c_df = pd.DataFrame(res)
            c_df = c_df[['market', 'trade_price', 'signed_change_rate', 'acc_trade_price_24h']]
            c_df.columns = ['코인', '현재가', '등락률', '24H 거래대금']
            c_df['등락률'] = (c_df['등락률']*100).round(2).astype(str) + "%"
            c_df['현재가'] = c_df['현재가'].apply(lambda x: f"{x:,.0f}원")
            st.table(c_df)
    else:
        with st.spinner(f"{mkt} 시장 분석 중..."):
            df = analyze_stocks(mkt_id, target_date, mode)
            if not df.empty:
                st.success(f"{len(df)}개의 종목을 찾았습니다.")
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("조건에 맞는 종목이 없습니다. 날짜를 변경하거나 조건을 완화해보세요.")

st.info("※ 한국투자증권 API 특성상 주말/공휴일은 데이터가 조회되지 않을 수 있습니다.")
