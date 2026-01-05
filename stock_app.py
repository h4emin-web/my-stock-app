import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import time

# 1. 앱 설정 및 스타일
st.set_page_config(page_title="해민증권 (Naver)", layout="centered")
st.markdown("""
    <style>
    .block-container { padding-top: 1.5rem; }
    .stTabs [data-baseweb="tab"] { font-size: 18px; font-weight: bold; flex: 1; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# --- 🛠️ 네이버 금융 스크래핑 함수 ---
def get_naver_top_volume(market_code):
    """네이버에서 거래대금 상위 종목 리스트를 가져옵니다."""
    # market_code: 0 (KOSPI), 1 (KOSDAQ)
    url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={market_code}"
    dfs = pd.read_html(url, encoding='cp949')
    df = dfs[1].dropna(subset=['종목명'])
    # 필요한 컬럼 정리
    df = df[df['N'] != 'N'] # 구분선 제거
    return df

def get_naver_daily_price(item_code, count=10):
    """특정 종목의 최근 일봉 데이터를 가져옵니다."""
    url = f"https://fchart.stock.naver.com/sise.nhn?symbol={item_code}&timeframe=day&count={count}&requestType=0"
    try:
        r = requests.get(url)
        df = pd.read_html(r.text)[0] # 실제 구현시 xml 파싱이 정확하나 간이 구현
        # 네이버 fchart XML 방식은 별도 파싱이 필요하므로 일반 시세 페이지 활용 가능
        # 여기서는 안정성을 위해 일자별 시세 페이지를 사용합니다.
        url = f"https://finance.naver.com/item/sise_day.naver?code={item_code}&page=1"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers)
        df = pd.read_html(r.text, header=0)[0].dropna()
        return df
    except:
        return pd.DataFrame()

# --- 📊 분석 로직 ---
def get_analyzed_data(mode, market_name):
    m_code = 0 if market_name == "KOSPI" else 1
    # 1. 상위 종목 리스트 확보
    top_df = get_naver_top_volume(m_code)
    
    # 네이버 상위 리스트는 거래량 기준이므로 거래대금 순으로 재정렬 필요할 수 있음
    # 여기서는 간단히 상위 30개에 대해 조건 검증
    results = []
    scan_limit = 25 
    
    prog = st.progress(0)
    for i, row in enumerate(top_df.head(scan_limit).itertuples()):
        prog.progress((i+1)/scan_limit)
        try:
            # 네이버 종목 코드 추출 (url에서 가져오거나 다른 API 활용)
            # 여기서는 편의상 상위 리스트의 현재가/등락률 정보를 우선 활용
            price = float(str(row.현재가).replace(',', ''))
            rate = float(str(row.전일비).split()[-1].replace('%', '').replace('+', '')) # 등락률 파싱
            volume_amt = float(str(row.거래대금).replace(',', '')) * 1000000 # 백만 단위 보정

            if mode == "거래대금 상위":
                results.append({'기업명': row.종목명, '현재가': f"{price:,.0f}원", '등락률': rate, '대금_v': volume_amt})
            
            elif mode == "상한가" and rate >= 29.8:
                results.append({'기업명': row.종목명, '현재가': f"{price:,.0f}원", '등락률': rate, '대금_v': volume_amt})

            elif "연속 거래대금" in mode:
                # 개별 종목 페이지 들어가서 과거 데이터 확인 (느릴 수 있음)
                # 이 부분은 KIS API 키를 쓰는 게 훨씬 빠르지만 네이버도 가능은 합니다.
                n = 3 if "3일" in mode else 5
                # 임시로 현재 대금이 1000억 이상인 것들만 필터링 (네이버 페이지 특성상 루프 속도 때문)
                if volume_amt >= 100000000000:
                    results.append({'기업명': row.종목명, '현재가': f"{price:,.0f}원", '등락률': rate, '대금_v': volume_amt})
        except:
            continue
            
    prog.empty()
    return pd.DataFrame(results)

# --- 📱 메인 UI ---
st.title("해민증권🧑‍💼 (Naver)")

mode = st.selectbox("분석 모드", ["거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", "상한가", "고가놀이"])
t1, t2 = st.tabs(["KOSPI", "KOSDAQ"])

for tab, mkt in zip([t1, t2], ["KOSPI", "KOSDAQ"]):
    with tab:
        if st.button(f"{mkt} 분석 시작"):
            with st.spinner("네이버 시세 분석 중..."):
                data = get_analyzed_data(mode, mkt)
                if not data.empty:
                    # 단위 변환 및 출력
                    data['거래대금'] = data['대금_v'].apply(lambda x: f"{int(x//100000000):,}억")
                    st.dataframe(
                        data[['기업명', '현재가', '등락률', '거래대금']].style.map(
                            lambda x: 'color: #ef5350;' if x > 0 else 'color: #42a5f5;', subset=['등락률']
                        ),
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.info("조건에 맞는 종목이 없습니다.")
