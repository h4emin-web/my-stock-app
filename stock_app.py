import requests
import pandas as pd
import time
from datetime import datetime, timedelta

# --- [정보 설정] ---
APP_KEY = "PSmBdpWduaskTXxqbcT6PuBTneKitnWiXnrL"
APP_SECRET = "adyZ3eYxXM74UlaErGZWe1SEJ9RPNo2wOD/mDWkJqkKfB0re+zVtKNiZM5loyVumtm5It+jTdgplqbimwqnyboerycmQWrlgA/Uwm8u4K66LB6+PhIoO6kf8zS196RO570kjshkBBecQzUUfwLlDWBIlTu/Mvu4qYYi5dstnsjgZh3Ic2Sw="
URL_BASE = "https://openapi.koreainvestment.com:9443"

def get_access_token():
    """접근 토큰 발급"""
    url = f"{URL_BASE}/oauth2/tokenP"
    payload = {"grant_type": "client_credentials", "appkey": APP_KEY, "secretkey": APP_SECRET}
    res = requests.post(url, json=payload)
    if res.status_code == 200:
        return res.json().get('access_token')
    else:
        print("토큰 발급 실패:", res.json())
        return None

def get_stock_list(token):
    """1. 거래대금 순위 상위 100종목 조회"""
    path = "/uapi/domestic-stock/v1/ranking/trade-value"
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY, "appsecret": APP_SECRET,
        "tr_id": "FHPST01710000"
    }
    params = {
        "fid_cond_scr_div_code": "20171",
        "fid_cond_rank_sort_code": "0",
        "fid_input_cntstr_000": "",
        "fid_input_iscd_000": "0000"
    }
    res = requests.get(f"{URL_BASE}{path}", headers=headers, params=params)
    return res.json().get('output', [])

def get_daily_ohlcv(code, target_date, token):
    """2. 종목별 일자별 시세 조회"""
    path = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    headers = {
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY, "appsecret": APP_SECRET,
        "tr_id": "FHKST03010100"
    }
    # 넉넉하게 최근 20일치 데이터를 가져옴
    start_date = (datetime.strptime(target_date, "%Y%m%d") - timedelta(days=30)).strftime("%Y%m%d")
    params = {
        "fid_cond_scr_div_code": "J",
        "fid_input_iscd": code,
        "fid_input_date_1": start_date,
        "fid_input_date_2": target_date,
        "fid_period_div_code": "D",
        "fid_org_adj_prc": "1"
    }
    res = requests.get(f"{URL_BASE}{path}", headers=headers, params=params)
    if res.status_code == 200:
        df = pd.DataFrame(res.json().get('output2', []))
        if df.empty: return None
        # 데이터 정제 (최신순 -> 과거순 정렬)
        df = df[['stck_clpr', 'stck_hgpr', 'stck_lwpr', 'acml_tr_pbmn', 'prdy_ctrt']].apply(pd.to_numeric)
        return df.iloc[::-1].reset_index(drop=True) # 과거부터 현재 순으로 정렬
    return None

# --- [메인 로직] ---
def run_scanner(target_date_str):
    token = get_access_token()
    if not token: return
    
    print(f"🚀 {target_date_str} 기준 분석 시작 (약 1~2분 소요)...")
    top_100 = get_stock_list(token)
    
    final_list = []
    
    for i, stock in enumerate(top_100):
        code = stock['mksc_shrn_iscd']
        name = stock['hts_kor_isnm']
        
        # API 과부하 방지 (초당 호출 제한 준수)
        time.sleep(0.15) 
        
        df = get_daily_ohlcv(code, target_date_str, token)
        if df is None or len(df) < 10: continue
        
        # --- 조건 계산 ---
        # A. 거래대금 조건 (단위: 원 -> 1000억 이상 체크)
        avg_val_3 = df['acml_tr_pbmn'].iloc[-3:].mean()
        avg_val_5 = df['acml_tr_pbmn'].iloc[-5:].mean()
        is_high_volume = (avg_val_3 >= 100_000_000_000) or (avg_val_5 >= 100_000_000_000)
        
        # B. 고가놀이 패턴 조건
        # 1) 기준봉(T-3 또는 T-4)에서 15% 이상 급등했는가?
        spike_found = False
        base_idx = -1
        for idx in range(-5, -2): # 최근 3~5일 전 탐색
            if df['prdy_ctrt'].iloc[idx] >= 15:
                spike_found = True
                base_idx = idx
                break
        
        is_high_play = False
        if spike_found:
            base_price = df['stck_clpr'].iloc[base_idx]
            # 기준봉 이후 현재까지 고가/저가가 기준봉 종가 대비 5% 내외 유지
            post_days = df.iloc[base_idx+1:]
            if not post_days.empty:
                max_high = post_days['stck_hgpr'].max()
                min_low = post_days['stck_lwpr'].min()
                if (max_high <= base_price * 1.05) and (min_low >= base_price * 0.95):
                    is_high_play = True

        # --- 결과 취합 ---
        if is_high_volume or is_high_play:
            final_list.append({
                "종목명": name,
                "3일평균(억)": round(avg_val_3 / 1e8, 1),
                "5일평균(억)": round(avg_val_5 / 1e8, 1),
                "고가놀이": "✅" if is_high_play else "-"
            })
            
    # 결과 출력
    result_df = pd.DataFrame(final_list)
    if not result_df.empty:
        print("\n=== 검색 결과 ===")
        print(result_df)
    else:
        print("\n조건에 부합하는 종목이 없습니다.")

# 실행 (원하는 날짜 입력)
run_scanner("20240522")
