import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests
import json
import time

# 1. 앱 설정 및 스타일
st.set_page_config(page_title="해민증권", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stDataFrame { font-size: 14px; }
</style>
""", unsafe_allow_html=True)

# --- 한국투자증권 API 클래스 ---
class KISApi:
    def __init__(self, app_key, app_secret):
        self.app_key = app_key
        self.app_secret = app_secret
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
    
    def get_volume_rank(self, market="0", date=""):
        """거래량 순위 조회 - 상위 200개"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/volume-rank"
        tr_id = "FHPST01710000"
        headers = self.get_headers(tr_id)
        
        if not headers:
            return pd.DataFrame()
        
        # market: 0=전체, 1=코스피, 2=코스닥
        fid_cond_mrkt_div_code = "J"
        fid_blng_cls_code = market
        
        params = {
            "fid_cond_mrkt_div_code": fid_cond_mrkt_div_code,
            "fid_cond_scr_div_code": "20171",
            "fid_input_iscd": "0000",
            "fid_div_cls_code": "0",
            "fid_blng_cls_code": fid_blng_cls_code,
            "fid_trgt_cls_code": "111111111",
            "fid_trgt_exls_cls_code": "0000000000",
            "fid_input_price_1": "",
            "fid_input_price_2": "",
            "fid_vol_cnt": "",
            "fid_input_date_1": date
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                data = res.json()
                outputs = data.get('output', [])
                
                result_list = []
                for item in outputs:
                    result_list.append({
                        '종목코드': item['mksc_shrn_iscd'],
                        '종목명': item['hts_kor_isnm'],
                        '현재가': int(item['stck_prpr']),
                        '전일대비': int(item['prdy_vrss']),
                        '등락률': float(item['prdy_ctrt']),
                        '거래량': int(item['acml_vol']),
                        '거래대금': int(item['acml_tr_pbmn']),
                        '시가총액': int(item['stck_prpr']) * int(item['lstn_stcn']) if item.get('lstn_stcn') else 0
                    })
                
                return pd.DataFrame(result_list)
        except Exception as e:
            st.error(f"거래량 순위 조회 오류: {e}")
        
        return pd.DataFrame()
    
    def get_price_by_day(self, stock_code, date):
        """특정일 주식 시세 조회"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        tr_id = "FHKST03010100"
        headers = self.get_headers(tr_id)
        
        if not headers:
            return None
        
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code,
            "fid_input_date_1": date,
            "fid_input_date_2": date,
            "fid_period_div_code": "D",
            "fid_org_adj_prc": "0"
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                data = res.json()
                output = data.get('output2', [])
                if output:
                    return output[0]
        except:
            pass
        
        return None
    
    def get_price_range(self, stock_code, start_date, end_date):
        """기간별 주식 시세 조회"""
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
    
    def get_current_price(self, stock_code):
        """현재가 조회"""
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
        
        # 1. 거래대금 상위
        if mode == "거래대금 상위":
            df = kis_api.get_volume_rank(market_code, date_s)
            
            if df.empty:
                return pd.DataFrame()
            
            # 거래대금 순으로 정렬하고 상위 50개
            df = df.sort_values(by='거래대금', ascending=False).head(50)
            
            res = []
            for _, row in df.iterrows():
                res.append({
                    '기업명': row['종목명'],
                    '시총_v': row['시가총액'],
                    '등락률': row['등락률'],
                    '대금_v': row['거래대금']
                })
            
            return pd.DataFrame(res)
        
        # 2. 3일/5일 연속 거래대금
        elif "연속 거래대금" in mode:
            n = 3 if "3일" in mode else 5
            business_days = get_business_days(end_date, n)
            
            st.info(f"조회 기간: {business_days[0]} ~ {business_days[-1]}")
            
            # 첫날 거래량 순위로 종목 리스트 가져오기
            df_base = kis_api.get_volume_rank(market_code, business_days[-1])
            
            if df_base.empty:
                return pd.DataFrame()
            
            # 상위 100개 종목만 체크
            stock_list = df_base.head(100)['종목코드'].tolist()
            
            valid_stocks = []
            stock_data = {}
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for idx, stock_code in enumerate(stock_list):
                status_text.text(f"분석 중: {idx+1}/{len(stock_list)} ({stock_code})")
                progress_bar.progress((idx + 1) / len(stock_list))
                
                # n일간 데이터 조회
                daily_amounts = []
                daily_prices = []
                stock_name = ""
                market_cap = 0
                
                for day in business_days:
                    time.sleep(0.05)  # API 호출 제한 대응
                    
                    price_data = kis_api.get_price_by_day(stock_code, day)
                    
                    if price_data:
                        amount = int(price_data.get('acml_tr_pbmn', 0))
                        close = int(price_data.get('stck_clpr', 0))
                        
                        daily_amounts.append(amount)
                        daily_prices.append(close)
                        
                        if not stock_name:
                            stock_name = price_data.get('hts_kor_isnm', '')
                            lstn_stcn = int(price_data.get('lstn_stcn', 0))
                            market_cap = close * lstn_stcn
                
                # n일 모두 거래대금 1000억 이상인지 체크
                if len(daily_amounts) == n and all(amt >= 100000000000 for amt in daily_amounts):
                    avg_amount = sum(daily_amounts) / n
                    
                    # 누적 변동률 계산
                    if len(daily_prices) == n:
                        accum_rate = ((daily_prices[-1] - daily_prices[0]) / daily_prices[0]) * 100
                        
                        stock_data[stock_code] = {
                            '기업명': stock_name,
                            '시총_v': market_cap,
                            '등락률': accum_rate,
                            '대금_v': avg_amount
                        }
                        valid_stocks.append(stock_code)
            
            progress_bar.empty()
            status_text.empty()
            
            if not valid_stocks:
                return pd.DataFrame()
            
            res = [stock_data[code] for code in valid_stocks]
            return pd.DataFrame(res)
        
        # 3. 상한가/하한가
        elif mode in ["상한가", "하한가"]:
            df = kis_api.get_volume_rank(market_code, date_s)
            
            if df.empty:
                return pd.DataFrame()
            
            if mode == "상한가":
                condition = df['등락률'] >= 29.5
            else:
                condition = df['등락률'] <= -29.5
            
            result_df = df[condition]
            
            res = []
            for _, row in result_df.iterrows():
                res.append({
                    '기업명': row['종목명'],
                    '시총_v': row['시가총액'],
                    '등락률': row['등락률'],
                    '대금_v': row['거래대금']
                })
            
            return pd.DataFrame(res)
        
        # 4. 고가놀이
        elif mode == "고가놀이":
            business_days = get_business_days(end_date, 4)
            
            st.info(f"조회 기간: {business_days[0]} ~ {business_days[-1]}")
            
            # 4일 전 거래량 순위
            df_base = kis_api.get_volume_rank(market_code, business_days[0])
            
            if df_base.empty:
                return pd.DataFrame()
            
            # 4일전에 500억 이상, 15% 이상 상승한 종목
            targets = df_base[(df_base['거래대금'] >= 50000000000) & (df_base['등락률'] >= 15)]
            
            res = []
            recent_3days = business_days[-3:]
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for idx, (_, row) in enumerate(targets.iterrows()):
                stock_code = row['종목코드']
                status_text.text(f"분석 중: {idx+1}/{len(targets)} ({stock_code})")
                progress_bar.progress((idx + 1) / len(targets))
                
                # 최근 3일 등락률 확인
                rates = []
                
                for day in recent_3days:
                    time.sleep(0.05)
                    price_data = kis_api.get_price_by_day(stock_code, day)
                    if price_data:
                        rates.append(float(price_data.get('prdy_ctrt', 0)))
                
                # 3일 평균 등락률이 ±5% 이내 (횡보)
                if len(rates) == 3 and abs(sum(rates) / 3) <= 5:
                    # 마지막 날 데이터
                    last_data = kis_api.get_price_by_day(stock_code, business_days[-1])
                    
                    if last_data:
                        res.append({
                            '기업명': last_data.get('hts_kor_isnm', ''),
                            '시총_v': int(last_data.get('stck_clpr', 0)) * int(last_data.get('lstn_stcn', 0)),
                            '등락률': float(last_data.get('prdy_ctrt', 0)),
                            '대금_v': int(last_data.get('acml_tr_pbmn', 0))
                        })
            
            progress_bar.empty()
            status_text.empty()
            
            return pd.DataFrame(res)
        
        # 5. 역헤드앤숄더
        elif mode == "역헤드앤숄더":
            business_days = get_business_days(end_date, 30)
            
            st.info(f"조회 기간: {business_days[0]} ~ {business_days[-1]}")
            
            # 거래대금 상위 100개
            df_today = kis_api.get_volume_rank(market_code, date_s)
            
            if df_today.empty:
                return pd.DataFrame()
            
            top_stocks = df_today.head(100)
            
            res = []
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for idx, (_, row) in enumerate(top_stocks.iterrows()):
                stock_code = row['종목코드']
                status_text.text(f"패턴 분석 중: {idx+1}/{len(top_stocks)} ({stock_code})")
                progress_bar.progress((idx + 1) / len(top_stocks))
                
                time.sleep(0.05)
                
                # 30일간 데이터 조회
                price_range = kis_api.get_price_range(stock_code, business_days[0], business_days[-1])
                
                if len(price_range) >= 30:
                    # 최신순으로 정렬되어 있으므로 역순으로
                    closes = [int(d.get('stck_clpr', 0)) for d in reversed(price_range)]
                    
                    # 3구간으로 나누기
                    p1 = closes[:10]
                    p2 = closes[10:20]
                    p3 = closes[20:]
                    
                    l1, l2, l3 = min(p1), min(p2), min(p3)
                    
                    # 역헤드앤숄더 패턴: l2가 가장 낮고, l3 근처에서 형성 중
                    if l2 < l1 and l2 < l3 and l3 <= closes[-1] <= l3 * 1.07:
                        res.append({
                            '기업명': row['종목명'],
                            '시총_v': row['시가총액'],
                            '등락률': row['등락률'],
                            '대금_v': row['거래대금']
                        })
            
            progress_bar.empty()
            status_text.empty()
            
            return pd.DataFrame(res)
        
        else:
            return pd.DataFrame()
    
    except Exception as e:
        st.error(f"데이터 조회 오류: {e}")
        import traceback
        st.error(traceback.format_exc())
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
    
    **참고:**
    - 3일/5일 연속: 시간이 다소 소요됩니다
    - API 제한으로 상위 100개 종목만 분석
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
