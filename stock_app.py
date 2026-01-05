import requests
import pandas as pd
import time

# --- [설정부] API 키 및 계정 정보 ---
APP_KEY = "PSmBdpWduaskTXxqbcT6PuBTneKitnWiXnrL"
APP_SECRET = "adyZ3eYxXM74UlaErGZWe1SEJ9RPNo2wOD/mDWkJqkKfB0re+zVtKNiZM5loyVumtm5It+jTdgplqbimwqnyboerycmQWrlgA/Uwm8u4K66LB6+PhIoO6kf8zS196RO570kjshkBBecQzUUfwLlDWBIlTu/Mvu4qYYi5dstnsjgZh3Ic2Sw="
URL_BASE = "https://openapi.koreainvestment.com:9443" # 실전계좌 기준

def get_access_token():
    """접근 토큰 발급"""
    url = f"{URL_BASE}/oauth2/tokenP"
    payload = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "secretkey": APP_SECRET
    }
    res = requests.post(url, json=payload)
    return res.json()['access_token']

ACCESS_TOKEN = get_access_token()

def get_top_100_by_value():
    """1. 거래대금 상위 100종목 가져오기 (당일 기준)"""
    path = "/uapi/domestic-stock/v1/ranking/trade-value"
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {ACCESS_TOKEN}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHPST01710000"
    }
    # FID_COND_SCR_DIV_CODE: 20171 (거래대금순위)
    params = {
        "fid_cond_scr_div_code": "20171",
        "fid_cond_rank_sort_code": "0", # 전체
        "fid_input_cntstr_000": "",
        "fid_input_iscd_000": "0000" # 0000: 전체, 0001: 코스피, 1001: 코스닥
    }
    res = requests.get(f"{URL_BASE}{path}", headers=headers, params=params)
    return pd.DataFrame(res.json()['output'])

def get_daily_price(code):
    """특정 종목의 최근 일봉 데이터 조회"""
    path = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {ACCESS_TOKEN}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST03010100"
    }
    params = {
        "fid_cond_scr_div_code": "J",
        "fid_input_iscd": code,
        "fid_input_date_1": "20230101", # 충분히 과거 날짜
        "fid_input_date_2": "20231231", # 조회할 날짜
        "fid_period_div_code": "D", # 일봉
        "fid_org_adj_prc": "1"
    }
    res = requests.get(f"{URL_BASE}{path}", headers=headers, params=params)
    df = pd.DataFrame(res.json()['output2'])
    # 숫자형 변환
    cols = ['stck_clpr', 'stck_hgpr', 'stck_lwpr', 'acml_tr_pbmn', 'prdy_ctrt']
    df[cols] = df[cols].apply(pd.to_numeric)
    return df

# --- [로직부] 조건 검색 실행 ---
def run_scanner():
    print("거래대금 상위 100개 종목 분석 중...")
    top_df = get_top_100_by_value()
    
    final_candidates = []

    for idx, row in top_df.iterrows():
        code = row['mksc_shrn_iscd']
        name = row['hts_kor_isnm']
        
        try:
            # 일봉 데이터 가져오기 (API 호출 제한 방지를 위해 간격 조절)
            df = get_daily_price(code)
            time.sleep(0.2) 
            
            # 최근 5일치 데이터 (최근일이 0번 인덱스일 수 있으므로 정렬 확인 필요)
            # 여기서는 최근일이 마지막 행이라고 가정(iloc)
            
            # 2. 거래대금 조건 (단위: 원, API 값은 보통 그대로 나옴)
            avg_val_3 = df['acml_tr_pbmn'].iloc[-3:].mean()
            avg_val_5 = df['acml_tr_pbmn'].iloc[-5:].mean()
            
            cond_val_3 = avg_val_3 >= 100_000_000_000
            cond_val_5 = avg_val_5 >= 100_000_000_000
            
            # 3. 고가놀이 패턴 조건
            # - 4일 전 혹은 3일 전에 15% 이상 상승 (기준봉)
            # - 그 후 3일간 변동폭이 기준봉 종가 대비 5% 내외 유지
            spike_row = df.iloc[-4] # 4일 전 기준봉 가정
            is_spike = spike_row['prdy_ctrt'] >= 15
            
            # 기준봉 이후 고가와 저가가 기준봉 종가의 ±5% 이내인지 확인
            post_spike_days = df.iloc[-3:]
            max_high = post_spike_days['stck_hgpr'].max()
            min_low = post_spike_days['stck_lwpr'].min()
            base_price = spike_row['stck_clpr']
            
            is_high_tight = (max_high <= base_price * 1.05) and (min_low >= base_price * 0.95)

            # 결과 저장
            if cond_val_3 or cond_val_5 or (is_spike and is_high_tight):
                final_candidates.append({
                    "종목명": name,
                    "3일평균대금": avg_val_3,
                    "5일평균대금": avg_val_5,
                    "고가놀이여부": "Y" if (is_spike and is_high_tight) else "N"
                })
        except:
            continue

    return pd.DataFrame(final_candidates)

# 실행
result = run_scanner()
print(result)
