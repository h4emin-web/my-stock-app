import streamlit as st
import pandas as pd
import requests
import json
import time

# 1. 앱 설정 및 스타일
st.set_page_config(page_title="Stock Analyzer", layout="centered", initial_sidebar_state="collapsed")
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    .block-container { padding-top: 1.5rem; }
    .stTabs [data-baseweb="tab"] { font-size: 18px; font-weight: bold; flex: 1; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# --- 🔐 [인증 정보] ---
APP_KEY = "PSmBdpWduaskTXxqbcT6PuBTneKitnWiXnrL"
APP_SECRET = "adyZ3eYxXM74UlaErGZWe1SEJ9RPNo2wOD/mDWkJqkKfB0re+zVtKNiZM5loyVumtm5It+jTdgplqbimwqnyboerycmQWrlgA/Uwm8u4K66LB6+PhIoO6kf8zS196RO570kjshkBBecQzUUfwLlDWBIlTu/Mvu4qYYi5dstnsjgZh3Ic2Sw="
URL_BASE = "https://openapi.koreainvestment.com:9443"

# --- 🔐 [인증] 토큰 발급 (캐싱 처리로 효율화) ---
@st.cache_data(ttl=3600*12)
def get_token():
    url = f"{URL_BASE}/oauth2/tokenP"
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    res = requests.post(url, data=json.dumps(body))
    return res.json().get('access_token')

# --- 📊 [데이터] API 호출 공통 함수 ---
def fetch_kis(path, tr_id, params):
    token = get_token()
    headers = {
        "Content-Type": "application/json", "authorization": f"Bearer {token}",
        "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": tr_id, "custtype": "P"
    }
    res = requests.get(f"{URL_BASE}{path}", headers=headers, params=params)
    return res.json() if res.status_code == 200 else None

# --- 🛠️ [핵심 로직] 조건별 종목 스캔 ---
def get_analyzed_data(mode, mkt_code):
    # 1단계: 실시간 거래대금 상위 100개 추출 (모든 분석의 모수)
    p = {
        "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": mkt_code, "FID_DIV_CLS_CODE": "0", "FID_BLNG_CLS_CODE": "0",
        "FID_TRGT_CLS_CODE": "0", "FID_TRGT_EXLS_CLS_CODE": "0", "FID_INPUT_PRICE_1": "0",
        "FID_INPUT_PRICE_2": "0", "FID_VOL_CNT": "0"
    }
    raw = fetch_kis("/uapi/domestic-stock/v1/ranking/trade-value", "FHPST01710000", p)
    if not raw or 'output' not in raw: return pd.DataFrame()
    df_top = pd.DataFrame(raw['output'])

    if mode == "거래대금 상위":
        return df_top.head(50)

    # 2단계: 개별 종목 일봉 데이터를 가져와서 조건 검증 (노가다 분석)
    res = []
    # API 부하와 속도를 고려하여 상위 30개만 정밀 스캔
    scan_target = df_top.head(30)
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, (_, row) in enumerate(scan_target.iterrows()):
        ticker = row['mksc_shrn_iscd']
        name = row['hts_kor_isnm']
        status_text.text(f"🔍 분석 중: {name} ({i+1}/{len(scan_target)})")
        progress_bar.progress((i + 1) / len(scan_target))

        # 종목별 일봉 데이터 요청
        p_hist = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker, "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0"}
        hist = fetch_kis("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100", p_hist)
        
        if hist and 'output2' in hist:
            days = hist['output2'] # 0번이 오늘, 1번이 어제...
            if len(days) < 10: continue

            # [3일/5일 연속 거래대금 500억 이상]
            if "연속 거래대금" in mode:
                n = 3 if "3일" in mode else 5
                # 단위: API 데이터는 '원' 단위이므로 50,000,000,000 체크
                if all(float(d['acml_tr_pbmn']) >= 50000000000 for d in days[:n]):
                    res.append(row)
            
            # [고가놀이] 4일 전 15% 이상 급등 후 3일간 횡보
            elif mode == "고가놀이":
                base_day = days[3] # 4일 전 (오늘이 0일차)
                if float(base_day['prdy_ctrt']) >= 15:
                    recent_3_avg = sum(float(d['prdy_ctrt']) for d in days[:3]) / 3
                    if -5 <= recent_3_avg <= 5: res.append(row)

            # [역헤드앤숄더] 저점 패턴 분석
            elif mode == "역헤드앤숄더":
                l1 = min(float(d['stck_clpr']) for d in days[14:21]) # 왼쪽 어깨
                l2 = min(float(d['stck_clpr']) for d in days[7:14])  # 머리 (더 낮아야 함)
                l3 = min(float(d['stck_clpr']) for d in days[:7])   # 오른쪽 어깨
                if l2 < l1 and l2 < l3: res.append(row)

        time.sleep(0.05) # TPS 제한(20회/초) 준수

    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(res)

# --- 📱 메인 UI ---
st.title("Stock Analysis 📈")

mode = st.selectbox("분석 모드 선택", 
    ["거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "고가놀이", "역헤드앤숄더", "암호화폐"])

mkt = st.radio("시장 선택", ["KOSPI", "KOSDAQ"], horizontal=True)
mkt_id = "0001" if mkt == "KOSPI" else "1001"

st.divider()

if st.button("🚀 분석 시작"):
    if mode == "암호화폐":
        with st.spinner("업비트 시세 로드 중..."):
            res = requests.get("https://api.upbit.com/v1/ticker?markets=KRW-BTC,KRW-ETH,KRW-SOL,KRW-XRP,KRW-DOGE").json()
            st.dataframe(pd.DataFrame(res), use_container_width=True)
    else:
        with st.spinner(f"{mkt} 데이터를 분석하고 있습니다. 잠시만 기다려주세요..."):
            final_df = get_analyzed_data(mode, mkt_id)
            
            if not final_df.empty:
                # 결과 가공
                out = final_df[['hts_kor_isnm', 'stck_prpr', 'prdy_ctrt', 'acml_tr_pbmn']].copy()
                out.columns = ['종목명', '현재가', '등락률', '거래대금(억)']
                out['거래대금(억)'] = out['거래대금(억)'].apply(lambda x: f"{int(float(x)//100000000):,}억")
                
                # 색상 입히기 (등락률 기준)
                def color_rate(val):
                    color = '#ef5350' if float(val) > 0 else ('#42a5f5' if float(val) < 0 else 'white')
                    return f'color: {color}'

                st.dataframe(
                    out.style.map(color_rate, subset=['등락률']),
                    use_container_width=True, hide_index=True, height=600
                )
            else:
                st.info("검색 결과가 없습니다. 조건을 충족하는 종목이 현재 시장에 없습니다.")

st.caption("※ 본 데이터는 한국투자증권 공식 API를 통해 실시간으로 분석됩니다.")
