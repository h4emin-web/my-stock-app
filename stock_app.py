import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests
import json
import time

# 1. 앱 설정 및 스타일
st.set_page_config(page_title="Stock", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stDataFrame { font-size: 14px; }
</style>
""", unsafe_allow_html=True)

# --- 한국투자증권 API 클래스 ---
class KISApi:
    def __init__(self, app_key, app_secret):
        self.app_key = "PSmBdpWduaskTXxqbcT6PuBTneKitnWiXnrL"
        self.app_secret = "adyZ3eYxXM74UlaErGZWe1SEJ9RPNo2wOD/mDWkJqkKfB0re+zVtKNiZM5loyVumtm5It+jTdgplqbimwqnyboerycmQWrlgA/Uwm8u4K66LB6+PhIoO6kf8zS196RO570kjshkBBecQzUUfwLlDWBIlTu/Mvu4qYYi5dstnsjgZh3Ic2Sw="
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.token = None
        self.token_expires = None
        
    def get_token(self):
        """접근 토큰 발급"""
        if self.token and self.token_expires and datetime.now() < self.token_expires:
            return self.token
            
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        data = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        
        try:
            res = requests.post(url, headers=headers, data=json.dumps(data))
            if res.status_code == 200:
                result = res.json()
                self.token = result['access_token']
                expires_in = int(result.get('expires_in', 86400))
                self.token_expires = datetime.now() + timedelta(seconds=expires_in - 60)
                return self.token
        except Exception as e:
            st.error(f"토큰 발급 실패: {e}")
        return None
    
    def get_headers(self, tr_id):
        """API 요청 헤더 생성"""
        token = self.get_token()
        if not token:
            return None
            
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id
        }
    
    def get_stock_price(self, stock_code):
        """개별 종목 현재가 조회"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = "FHKST01010100"
        headers = self.get_headers(tr_id)
        
        if not headers:
            return None
        
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                return res.json()['output']
        except:
            pass
        return None
    
    def get_daily_price(self, stock_code, start_date, end_date):
        """일별 시세 조회"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        tr_id = "FHKST03010100"
        headers = self.get_headers(tr_id)
        
        if not headers:
            return []
        
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code,
            "fid_input_date_1": start_date,
            "fid_input_date_2": end_date,
            "fid_period_div_code": "D",
            "fid_org_adj_prc": "0"
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                data = res.json()
                return data.get('output2', [])
        except:
            pass
        return []
    
    def get_market_cap(self, stock_code):
        """시가총액 조회"""
        data = self.get_stock_price(stock_code)
        if data:
            # 시가총액 = 현재가 * 상장주식수
            price = int(data.get('stck_prpr', 0))
            vol = int(data.get('lstn_stcn', 0))
            return price * vol
        return 0
    
    def get_all_stocks(self, market="0"):
        """전체 종목 코드 조회 (거래량 상위 종목)"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/volume-rank"
        tr_id = "FHPST01710000"
        headers = self.get_headers(tr_id)
        
        if not headers:
            return []
        
        # market: 0=전체, 1=코스피, 2=코스닥
        fid_cond_mrkt_div_code = "J" if market in ["0", "1"] else "Q"
        
        all_stocks = []
        
        params = {
            "fid_cond_mrkt_div_code": fid_cond_mrkt_div_code,
            "fid_cond_scr_div_code": "20171",
            "fid_input_iscd": "0000",
            "fid_div_cls_code": "0",
            "fid_blng_cls_code": market,
            "fid_trgt_cls_code": "111111111",
            "fid_trgt_exls_cls_code": "0000000000",
            "fid_input_price_1": "",
            "fid_input_price_2": "",
            "fid_vol_cnt": "",
            "fid_input_date_1": ""
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                data = res.json()
                outputs = data.get('output', [])
                for item in outputs[:200]:  # 상위 200개 종목
                    all_stocks.append(item['mksc_shrn_iscd'])
        except Exception as e:
            st.error(f"종목 조회 오류: {e}")
        
        return all_stocks
    
    def get_market_data_bulk(self, stock_list, date):
        """여러 종목의 시세를 한번에 조회"""
        result_list = []
        
        for i, stock_code in enumerate(stock_list):
            if i > 0 and i % 20 == 0:  # API 호출 제한 (초당 20건)
                time.sleep(1)
            
            daily_data = self.get_daily_price(stock_code, date, date)
            
            if daily_data and len(daily_data) > 0:
                output = daily_data[0]
                
                try:
                    result_list.append({
                        '종목코드': stock_code,
                        '종목명': output.get('hts_kor_isnm', ''),
                        '종가': int(output.get('stck_clpr', 0)),
                        '시가': int(output.get('stck_oprc', 0)),
                        '고가': int(output.get('stck_hgpr', 0)),
                        '저가': int(output.get('stck_lwpr', 0)),
                        '거래량': int(output.get('acml_vol', 0)),
                        '거래대금': int(output.get('acml_tr_pbmn', 0)),
                        '등락률': float(output.get('prdy_ctrt', 0)),
                        '시가총액': int(output.get('stck_prpr', 0)) * int(output.get('lstn_stcn', 0)) if output.get('lstn_stcn') else 0
                    })
                except:
                    continue
        
        return pd.DataFrame(result_list)

# --- 유틸리티 함수 ---
def format_korean_unit(val):
    if pd.isna(val) or val == 0:
        return "0"
    if val >= 1000000000000:
        return f"{int(val // 1000000000000)}조"
    return f"{int(val // 100000000):,}억"

def get_business_days(end_date, n_days):
    """영업일 계산 (간단 버전 - 주말만 제외)"""
    dates = []
    current = end_date
    count = 0
    
    while count < n_days:
        if current.weekday() < 5:  # 월~금
            dates.append(current.strftime("%Y%m%d"))
            count += 1
        current = current - timedelta(days=1)
    
    return list(reversed(dates))

# --- 암호화폐 데이터 ---
@st.cache_data(ttl=30)
def get_crypto_data():
    try:
        m_url = "https://api.upbit.com/v1/market/all"
        m_data = requests.get(m_url, timeout=5).json()
        krw_markets = {d['market']: d['korean_name'] for d in m_data if d['market'].startswith("KRW-")}
        
        t_url = f"https://api.upbit.com/v1/ticker?markets={','.join(krw_markets.keys())}"
        t_data = requests.get(t_url, timeout=5).json()
        
        res = []
        for d in t_data:
            res.append({
                '코인명': krw_markets[d['market']],
                '현재가': d['trade_price'],
                '전일대비': d['signed_change_rate'] * 100,
                '거래대금': d['acc_trade_price_24h']
            })
        
        df = pd.DataFrame(res).sort_values(by='거래대금', ascending=False).head(20)
        df.insert(0, 'No', range(1, len(df) + 1))
        return df
    except:
        return pd.DataFrame()

# --- 주식 데이터 및 분석 로직 ---
def get_data(mode, date_s, market, kis_api):
    if kis_api is None:
        return pd.DataFrame()
    
    try:
        end_date = datetime.strptime(date_s, "%Y%m%d")
        market_code = "1" if market == "KOSPI" else "2"
        
        # 종목 리스트 조회
        with st.spinner(f"{market} 종목 리스트 조회 중..."):
            stock_list = kis_api.get_all_stocks(market_code)
        
        if not stock_list:
            return pd.DataFrame()
        
        # 1. 연속 거래대금
        if "연속 거래대금" in mode:
            n = 3 if "3일" in mode else 5
            business_days = get_business_days(end_date, n)
            
            # n일간 데이터 수집
            all_data = {}
            for day in business_days:
                with st.spinner(f"{day} 데이터 조회 중..."):
                    df_day = kis_api.get_market_data_bulk(stock_list, day)
                    all_data[day] = df_day
            
            # 조건 검사: 모든 날짜에 1000억 이상 거래대금
            valid_stocks = None
            total_amt = {}
            first_price = {}
            last_price = {}
            
            for i, (day, df) in enumerate(all_data.items()):
                if df.empty:
                    continue
                
                cond_stocks = set(df[df['거래대금'] >= 100000000000]['종목코드'].tolist())
                
                if valid_stocks is None:
                    valid_stocks = cond_stocks
                else:
                    valid_stocks = valid_stocks.intersection(cond_stocks)
                
                # 거래대금 누적
                for _, row in df.iterrows():
                    code = row['종목코드']
                    total_amt[code] = total_amt.get(code, 0) + row['거래대금']
                    
                    if i == 0:
                        first_price[code] = row['종가']
                    if i == len(business_days) - 1:
                        last_price[code] = row['종가']
            
            if not valid_stocks:
                return pd.DataFrame()
            
            res = []
            last_df = all_data[business_days[-1]]
            
            for code in valid_stocks:
                if code in first_price and code in last_price:
                    accum_rate = ((last_price[code] - first_price[code]) / first_price[code]) * 100
                    
                    stock_row = last_df[last_df['종목코드'] == code].iloc[0]
                    
                    res.append({
                        '기업명': stock_row['종목명'],
                        '시총_v': stock_row['시가총액'],
                        '등락률': accum_rate,
                        '대금_v': total_amt[code] / n
                    })
            
            return pd.DataFrame(res)
        
        # 2. 고가놀이
        elif mode == "고가놀이":
            business_days = get_business_days(end_date, 4)
            
            # 4일전 데이터 (500억, 15% 이상)
            with st.spinner("4일전 데이터 조회 중..."):
                df_base = kis_api.get_market_data_bulk(stock_list, business_days[0])
            
            if df_base.empty:
                return pd.DataFrame()
            
            targets = df_base[(df_base['거래대금'] >= 50000000000) & (df_base['등락률'] >= 15)]['종목코드'].tolist()
            
            # 최근 3일 등락률 확인
            recent_3days = business_days[-3:]
            res = []
            
            for code in targets:
                rates = []
                stock_name = ""
                
                for day in recent_3days:
                    daily_data = kis_api.get_daily_price(code, day, day)
                    if daily_data:
                        rates.append(float(daily_data[0].get('prdy_ctrt', 0)))
                        stock_name = daily_data[0].get('hts_kor_isnm', '')
                
                if len(rates) == 3 and abs(sum(rates) / 3) <= 5:
                    last_data = kis_api.get_daily_price(code, business_days[-1], business_days[-1])
                    if last_data:
                        output = last_data[0]
                        res.append({
                            '기업명': stock_name,
                            '시총_v': int(output.get('stck_prpr', 0)) * int(output.get('lstn_stcn', 0)),
                            '등락률': float(output.get('prdy_ctrt', 0)),
                            '대금_v': int(output.get('acml_tr_pbmn', 0))
                        })
            
            return pd.DataFrame(res)
        
        # 3. 역헤드앤숄더
        elif mode == "역헤드앤숄더":
            with st.spinner("거래대금 상위 종목 조회 중..."):
                df_today = kis_api.get_market_data_bulk(stock_list, date_s)
            
            if df_today.empty:
                return pd.DataFrame()
            
            top_stocks = df_today.sort_values(by='거래대금', ascending=False).head(100)['종목코드'].tolist()
            
            business_days = get_business_days(end_date, 30)
            res = []
            
            for code in top_stocks:
                with st.spinner(f"{code} 패턴 분석 중..."):
                    daily_data = kis_api.get_daily_price(code, business_days[0], business_days[-1])
                
                if len(daily_data) >= 30:
                    closes = [int(d.get('stck_clpr', 0)) for d in reversed(daily_data)]
                    
                    p1, p2, p3 = closes[:10], closes[10:20], closes[20:]
                    l1, l2, l3 = min(p1), min(p2), min(p3)
                    
                    if l2 < l1 and l2 < l3 and l3 <= closes[-1] <= l3 * 1.07:
                        stock_row = df_today[df_today['종목코드'] == code].iloc[0]
                        res.append({
                            '기업명': stock_row['종목명'],
                            '시총_v': stock_row['시가총액'],
                            '등락률': stock_row['등락률'],
                            '대금_v': stock_row['거래대금']
                        })
            
            return pd.DataFrame(res)
        
        # 4. 상한가/하한가
        elif mode in ["상한가", "하한가"]:
            with st.spinner(f"{mode} 종목 조회 중..."):
                df_today = kis_api.get_market_data_bulk(stock_list, date_s)
            
            if df_today.empty:
                return pd.DataFrame()
            
            if mode == "상한가":
                condition = df_today['등락률'] >= 29.5
            else:
                condition = df_today['등락률'] <= -29.5
            
            result_df = df_today[condition]
            
            res = []
            for _, row in result_df.iterrows():
                res.append({
                    '기업명': row['종목명'],
                    '시총_v': row['시가총액'],
                    '등락률': row['등락률'],
                    '대금_v': row['거래대금']
                })
            
            return pd.DataFrame(res)
        
        # 5. 거래대금 상위
        else:
            with st.spinner("거래대금 상위 종목 조회 중..."):
                df_today = kis_api.get_market_data_bulk(stock_list, date_s)
            
            if df_today.empty:
                return pd.DataFrame()
            
            top_df = df_today.sort_values(by='거래대금', ascending=False).head(50)
            
            res = []
            for _, row in top_df.iterrows():
                res.append({
                    '기업명': row['종목명'],
                    '시총_v': row['시가총액'],
                    '등락률': row['등락률'],
                    '대금_v': row['거래대금']
                })
            
            return pd.DataFrame(res)
    
    except Exception as e:
        st.error(f"데이터 조회 오류: {e}")
        return pd.DataFrame()

# --- 앱 메인 UI ---
st.title("해민증권🧑‍💼")

# 세션 상태 초기화
if 'kis_api' not in st.session_state:
    st.session_state.kis_api = None
    st.session_state.api_connected = False

# API 키 설정 (사이드바)
with st.sidebar:
    st.header("🔑 한국투자증권 API 설정")
    st.markdown("*실전투자 계좌용*")
    
    app_key = st.text_input("APP KEY", type="password", key="app_key_input")
    app_secret = st.text_input("APP SECRET", type="password", key="app_secret_input")
    
    if st.button("🔗 API 연결", use_container_width=True):
        if app_key and app_secret:
            with st.spinner("API 연결 중..."):
                st.session_state.kis_api = KISApi(app_key, app_secret)
                token = st.session_state.kis_api.get_token()
                
                if token:
                    st.session_state.api_connected = True
                    st.success("✅ API 연결 성공!")
                else:
                    st.session_state.api_connected = False
                    st.error("❌ API 연결 실패. 키를 확인해주세요.")
        else:
            st.warning("⚠️ APP KEY와 APP SECRET을 모두 입력해주세요.")
    
    if st.session_state.api_connected:
        st.success("🟢 연결됨")
    else:
        st.error("🔴 연결 안됨")
    
    st.divider()
    st.markdown("""
    **사용 방법:**
    1. APP KEY와 SECRET 입력
    2. API 연결 버튼 클릭
    3. 날짜와 분석 모드 선택
    4. 데이터 조회
    """)

# API 연결 확인
if not st.session_state.api_connected:
    st.warning("⚠️ 좌측 사이드바에서 한국투자증권 API를 먼저 연결해주세요.")
    st.info("""
    **한국투자증권 Open API 발급 방법:**
    1. 한국투자증권 홈페이지 로그인
    2. [트레이딩] > [오픈API] 메뉴
    3. 실전투자용 앱 등록
    4. APP KEY와 APP SECRET 발급
    """)
    st.stop()

# 날짜 및 모드 선택
col1, col2 = st.columns([1, 1.2])

with col1:
    d_input = st.date_input("📅 날짜", datetime.now())
    date_s = d_input.strftime("%Y%m%d")

with col2:
    mode = st.selectbox("📊 분석 모드", 
                       ["거래대금 상위", "3일 연속 거래대금", "5일 연속 거래대금", 
                        "상한가", "하한가", "고가놀이", "역헤드앤숄더", "암호화폐"])

st.divider()

# 데이터 표시
if mode == "암호화폐":
    with st.spinner("코인 시세를 불러오는 중..."):
        data = get_crypto_data()
        
        if not data.empty:
            data['현재가'] = data['현재가'].apply(lambda x: f"{x:,.0f}" if x >= 100 else f"{x:,.2f}")
            data['거래대금'] = data['거래대금'].apply(format_korean_unit)
            
            st.dataframe(
                data.style.map(
                    lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''),
                    subset=['전일대비']
                ).format({'전일대비': '{:.1f}%'}),
                use_container_width=True,
                height=750,
                hide_index=True
            )
else:
    t1, t2 = st.tabs(["📈 KOSPI", "📊 KOSDAQ"])
    
    for tab, mkt in zip([t1, t2], ["KOSPI", "KOSDAQ"]):
        with tab:
            data = get_data(mode, date_s, mkt, st.session_state.kis_api)
            
            if data is None or data.empty:
                st.info("조건에 맞는 종목이 없습니다.")
            else:
                data = data.sort_values(by='대금_v', ascending=False)
                data.insert(0, 'No', range(1, len(data) + 1))
                data['시총'] = data['시총_v'].apply(format_korean_unit)
                data['대금'] = data['대금_v'].apply(format_korean_unit)
                
                # 라벨 설정
                if "3일 연속" in mode:
                    l_rate, l_amt = "3일 누적 변동", "3일 평균 대금"
                elif "5일 연속" in mode:
                    l_rate, l_amt = "5일 누적 변동", "5일 평균 대금"
                else:
                    l_rate, l_amt = "등락률", "거래대금"
                
                st.dataframe(
                    data[['No', '기업명', '시총', '등락률', '대금']].rename(
                        columns={'등락률': l_rate, '대금': l_amt}
                    ).style.map(
                        lambda x: 'color: #ef5350;' if x > 0 else ('color: #42a5f5;' if x < 0 else ''),
                        subset=[l_rate]
                    ).format({l_rate: '{:.1f}%'}),
                    use_container_width=True,
                    height=600,
                    hide_index=True
                )
