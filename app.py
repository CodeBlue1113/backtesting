"""
MNQ 15분봉 BB Basis × EMA200 전략 개인용 백테스팅 앱
한국투자증권 해외선물 분봉조회 API (HHDFC55020400) 사용

사용법:
1. pip install -r requirements.txt
2. streamlit run app.py
3. (선택) Streamlit Community Cloud에 올려 개인 URL로 접속
"""

import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings("ignore")

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

# =========================
# 페이지 설정
# =========================
st.set_page_config(
    page_title="MNQ BB×EMA200 백테스트",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================
# 한국투자증권 API 클래스
# =========================
class KISAPI:
    def __init__(self, app_key: str, app_secret: str):
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.access_token = None
        self.token_expired = None

    def get_access_token(self) -> bool:
        """Access Token 발급"""
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        try:
            res = requests.post(url, headers=headers, json=body, timeout=10)
            text_preview = res.text[:400] if res.text else "(빈 응답)"
            
            try:
                data = res.json()
            except Exception:
                st.error("토큰 발급 응답이 JSON이 아닙니다.")
                st.code(text_preview, language="text")
                return False
                
            if "access_token" in data:
                self.access_token = data["access_token"]
                self.token_expired = data.get("access_token_token_expired", "")
                return True
            else:
                st.error(f"토큰 발급 실패: {data.get('error_description') or data.get('msg1') or data}")
                st.code(str(data), language="json")
                return False
        except Exception as e:
            st.error(f"토큰 발급 중 오류: {e}")
            return False

    def fetch_minute_bars(
        self,
        srs_cd: str,
        exch_cd: str = "CME",
        close_date: str = None,          # YYYYMMDD
        qry_gap: str = "15",             # 분 간격
        max_bars: int = 3000,            # 최대 수집 봉 수
        sleep_sec: float = 0.25
    ) -> pd.DataFrame:
        """
        해외선물 분봉 조회 (연속 조회 지원)
        - START_DATE_TIME: 공백
        - CLOSE_DATE_TIME: 조회 종료일
        - QRY_TP: 처음 "" → 이후 "P"
        - INDEX_KEY: 이전 응답의 index_key
        - QRY_CNT: 120 (최대)
        """
        if not self.access_token:
            if not self.get_access_token():
                return pd.DataFrame()

        if close_date is None:
            close_date = datetime.now().strftime("%Y%m%d")

        url = f"{self.base_url}/uapi/overseas-futureoption/v1/quotations/inquire-time-futurechartprice"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "HHDFC55020400",
            "custtype": "P"
        }

        all_rows = []
        qry_tp = ""          # 최초 조회 (문서 개요: 공백)
        index_key = ""
        fetched = 0

        progress = st.progress(0)
        status = st.empty()

        while fetched < max_bars:
            params = {
                "SRS_CD": srs_cd,
                "EXCH_CD": exch_cd,
                "START_DATE_TIME": "",
                "CLOSE_DATE_TIME": close_date,
                "QRY_TP": qry_tp,
                "QRY_CNT": "120",
                "QRY_GAP": qry_gap,
                "INDEX_KEY": index_key
            }

            try:
                res = requests.get(url, headers=headers, params=params, timeout=15)
                
                content_type = res.headers.get("Content-Type", "")
                text_preview = res.text[:800] if res.text else "(빈 응답)"
                
                if res.status_code != 200:
                    st.error(f"HTTP 오류 {res.status_code}")
                    st.code(text_preview, language="text")
                    break
                
                try:
                    data = res.json()
                except Exception:
                    st.error("서버가 JSON이 아닌 응답을 반환했습니다.")
                    st.write("**응답 미리보기:**")
                    st.code(text_preview, language="text")
                    st.write(f"Content-Type: {content_type}")
                    break
                    
            except Exception as e:
                st.warning(f"API 호출 오류: {e}")
                break

            # 디버그: 첫 응답은 항상 출력
            if fetched == 0:
                st.write("🔍 **첫 번째 API 응답 (디버그):**")
                st.json(data)

            if data.get("rt_cd") != "0":
                msg = data.get("msg1", "알 수 없는 오류")
                msg_cd = data.get("msg_cd", "")
                st.error(f"조회 실패: {msg} (msg_cd={msg_cd})")
                if "기간" in msg or "조회" in msg or "종목" in msg:
                    st.info("종목코드(SRS_CD)가 정확한 월물 코드인지 HTS에서 다시 확인하세요.")
                if "인증" in msg or "토큰" in msg or "권한" in msg or "key" in str(msg).lower():
                    st.info("APP Key / Secret이 맞는지, 재발급이 필요한지 확인하세요.")
                break

            output1 = data.get("output1", [])
            output2 = data.get("output2", {})

            if not output1:
                if fetched == 0:
                    st.warning("API는 성공했으나 분봉 데이터(output1)가 비어 있습니다.")
                    st.info("가능한 원인: ① 해당 월물에 데이터 없음  ② 조회 종료일 문제  ③ CME 시세 권한 없음")
                break

            for row in output1:
                all_rows.append({
                    "date": row.get("data_date", ""),
                    "time": row.get("data_time", ""),
                    "open": float(row.get("open_price", 0) or 0),
                    "high": float(row.get("high_price", 0) or 0),
                    "low": float(row.get("low_price", 0) or 0),
                    "close": float(row.get("last_price", 0) or 0),
                    "volume": float(row.get("vol", 0) or 0),
                    "last_qntt": float(row.get("last_qntt", 0) or 0),
                })

            fetched = len(all_rows)
            progress.progress(min(fetched / max_bars, 1.0))
            status.text(f"수집 중... {fetched}개 봉")

            # 다음 조회 키
            next_key = output2.get("index_key", "").strip()
            if not next_key or next_key == index_key:
                break

            index_key = next_key
            qry_tp = "P"
            time.sleep(sleep_sec)

        progress.empty()
        status.empty()

        if not all_rows:
            return pd.DataFrame()

        df = pd.DataFrame(all_rows)
        # datetime 생성
        df["datetime"] = pd.to_datetime(
            df["date"] + df["time"].str.zfill(6),
            format="%Y%m%d%H%M%S",
            errors="coerce"
        )
        df = df.dropna(subset=["datetime"])
        df = df.sort_values("datetime").drop_duplicates(subset=["datetime"]).reset_index(drop=True)
        df = df[["datetime", "open", "high", "low", "close", "volume"]]
        return df


# =========================
# 전략 로직 (Pine Script 포팅)
# =========================
def run_strategy(
    df: pd.DataFrame,
    ema_length: int = 200,
    bb_length: int = 20,
    bb_mult: float = 2.0,
    initial_capital: float = 10000.0,
    qty: float = 1.0,          # 계약 수 (MNQ 1계약)
    point_value: float = 2.0,  # MNQ $2 per point
    commission_per_side: float = 0.85  # 대략적인 편도 수수료 (달러)
) -> tuple[pd.DataFrame, dict]:
    """
    Pine Script 전략 재현:
    - 롱 진입: BB Basis가 EMA200 상향 돌파 + 포지션 없음
    - 숏 진입: BB Basis가 EMA200 하향 돌파 + 포지션 없음
    - 롱 청산: 종가가 EMA200 하향 돌파
    - 숏 청산: 종가가 EMA200 상향 돌파
    """
    if len(df) < max(ema_length, bb_length) + 5:
        return df, {"error": "데이터가 너무 적습니다."}

    data = df.copy()
    data["ema"] = data["close"].ewm(span=ema_length, adjust=False).mean()
    mid = data["close"].rolling(bb_length).mean()
    std = data["close"].rolling(bb_length).std()
    data["bb_basis"] = mid
    data["bb_upper"] = mid + bb_mult * std
    data["bb_lower"] = mid - bb_mult * std

    # 크로스 신호
    data["basis_above_ema"] = data["bb_basis"] > data["ema"]
    data["basis_cross_up"] = (data["basis_above_ema"] != data["basis_above_ema"].shift(1)) & data["basis_above_ema"]
    data["basis_cross_down"] = (data["basis_above_ema"] != data["basis_above_ema"].shift(1)) & (~data["basis_above_ema"])

    data["close_above_ema"] = data["close"] > data["ema"]
    data["close_cross_down"] = (data["close_above_ema"] != data["close_above_ema"].shift(1)) & (~data["close_above_ema"])
    data["close_cross_up"] = (data["close_above_ema"] != data["close_above_ema"].shift(1)) & data["close_above_ema"]

    # 백테스트 시뮬레이션
    position = 0          # 1=롱, -1=숏, 0=없음
    entry_price = 0.0
    equity = initial_capital
    equity_curve = []
    trades = []
    position_size = []

    for i in range(len(data)):
        row = data.iloc[i]
        price = row["close"]

        # 청산 먼저
        if position > 0 and row["close_cross_down"]:
            pnl = (price - entry_price) * point_value * qty - commission_per_side * 2
            equity += pnl
            trades.append({
                "entry_time": entry_time,
                "exit_time": row["datetime"],
                "side": "Long",
                "entry_price": entry_price,
                "exit_price": price,
                "pnl": pnl,
                "equity": equity
            })
            position = 0

        elif position < 0 and row["close_cross_up"]:
            pnl = (entry_price - price) * point_value * qty - commission_per_side * 2
            equity += pnl
            trades.append({
                "entry_time": entry_time,
                "exit_time": row["datetime"],
                "side": "Short",
                "entry_price": entry_price,
                "exit_price": price,
                "pnl": pnl,
                "equity": equity
            })
            position = 0

        # 진입 (포지션 없을 때만)
        if position == 0:
            if row["basis_cross_up"]:
                position = 1
                entry_price = price
                entry_time = row["datetime"]
                equity -= commission_per_side   # 진입 수수료
            elif row["basis_cross_down"]:
                position = -1
                entry_price = price
                entry_time = row["datetime"]
                equity -= commission_per_side

        equity_curve.append(equity)
        position_size.append(position)

    data["equity"] = equity_curve
    data["position"] = position_size

    # 성과 지표
    trades_df = pd.DataFrame(trades)
    if len(trades_df) > 0:
        wins = trades_df[trades_df["pnl"] > 0]
        win_rate = len(wins) / len(trades_df) * 100
        total_pnl = trades_df["pnl"].sum()
        avg_pnl = trades_df["pnl"].mean()
        max_dd = 0.0
        peak = initial_capital
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd
    else:
        win_rate = 0.0
        total_pnl = 0.0
        avg_pnl = 0.0
        max_dd = 0.0

    stats = {
        "initial_capital": initial_capital,
        "final_equity": equity_curve[-1] if equity_curve else initial_capital,
        "total_return_pct": (equity_curve[-1] / initial_capital - 1) * 100 if equity_curve else 0,
        "total_trades": len(trades_df),
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_pnl": avg_pnl,
        "max_drawdown_pct": max_dd,
        "trades_df": trades_df
    }
    return data, stats


# =========================
# Streamlit UI
# =========================
st.title("📈 MNQ 15분봉 BB Basis × EMA200 백테스트")
st.caption("개인용 백테스트 · 한국투자 API / Yahoo Finance 지원")

with st.sidebar:
    st.header("📂 데이터 소스")
    data_source = st.radio(
        "데이터 가져올 곳",
        ["Yahoo Finance (무료, 최근 데이터)", "한국투자증권 API (CME 권한 필요)"],
        index=0
    )

    if data_source.startswith("한국투자"):
        st.header("🔑 API 설정")
        st.warning("APP Key / Secret은 절대 공유하지 마세요.")
        app_key = st.text_input("APP Key", type="password")
        app_secret = st.text_input("APP Secret", type="password")
        srs_cd = st.text_input("종목코드 (SRS_CD)", value="MNQU26", help="예: MNQU26")
        exch_cd = st.text_input("거래소코드", value="CME")
        close_date = st.text_input("조회 종료일 (YYYYMMDD)", value=datetime.now().strftime("%Y%m%d"))
        max_bars = st.number_input("최대 수집 봉 수", min_value=120, max_value=10000, value=2000, step=120)
    else:
        app_key = app_secret = srs_cd = exch_cd = close_date = ""
        max_bars = 0
        st.info("Yahoo Finance는 API 키 없이 최근 약 5~7일 15분봉을 가져옵니다.")
        yf_symbol = st.text_input("Yahoo 심볼", value="MNQ=F", help="MNQ=F (연속), NQ=F 등")
        yf_period = st.selectbox("기간", ["5d", "7d", "1mo", "3mo", "6mo"], index=4)

    st.header("⚙️ 전략 파라미터")
    ema_length = st.number_input("EMA 기간", min_value=10, max_value=500, value=200)
    bb_length = st.number_input("BB 기간", min_value=5, max_value=100, value=20)
    bb_mult = st.number_input("BB 승수", min_value=0.5, max_value=5.0, value=2.0, step=0.1)
    initial_capital = st.number_input("초기 자본 ($)", min_value=1000.0, value=10000.0, step=1000.0)
    qty = st.number_input("계약 수", min_value=1.0, value=1.0, step=1.0)

    run_btn = st.button("🚀 백테스트 실행", type="primary", use_container_width=True)

# 메인 영역
if run_btn:
    df = pd.DataFrame()

    if data_source.startswith("Yahoo"):
        if not YF_AVAILABLE:
            st.error("yfinance가 설치되지 않았습니다. requirements.txt에 yfinance를 추가하고 재배포하세요.")
            st.stop()
        with st.spinner("Yahoo Finance에서 15분봉 가져오는 중..."):
            try:
                ticker = yf.Ticker(yf_symbol.strip())
                hist = ticker.history(period=yf_period, interval="15m")
                if hist.empty:
                    st.error("Yahoo에서 데이터를 가져오지 못했습니다. 심볼을 확인하세요. (예: MNQ=F)")
                    st.stop()
                hist = hist.reset_index()
                # 컬럼 정리
                if "Datetime" in hist.columns:
                    hist = hist.rename(columns={"Datetime": "datetime"})
                elif "Date" in hist.columns:
                    hist = hist.rename(columns={"Date": "datetime"})
                hist.columns = [c.lower() for c in hist.columns]
                df = hist[["datetime", "open", "high", "low", "close", "volume"]].copy()
                df["datetime"] = pd.to_datetime(df["datetime"])
                # timezone 제거
                if df["datetime"].dt.tz is not None:
                    df["datetime"] = df["datetime"].dt.tz_localize(None)
                df = df.dropna().sort_values("datetime").reset_index(drop=True)
            except Exception as e:
                st.error(f"Yahoo Finance 오류: {e}")
                st.stop()
    else:
        # 한국투자증권 API
        if not app_key or not app_secret:
            st.error("APP Key와 APP Secret을 입력해주세요.")
            st.stop()
        with st.spinner("한국투자증권 API에서 데이터 수집 중..."):
            api = KISAPI(app_key, app_secret)
            if not api.get_access_token():
                st.stop()
            df = api.fetch_minute_bars(
                srs_cd=srs_cd.strip(),
                exch_cd=exch_cd.strip(),
                close_date=close_date.strip(),
                qry_gap="15",
                max_bars=int(max_bars)
            )

    if df.empty:
        st.error("데이터를 가져오지 못했습니다. 설정을 확인하세요.")
        st.stop()

    st.success(f"수집 완료: {len(df)}개 봉  ({df['datetime'].min()} ~ {df['datetime'].max()})")

    with st.spinner("전략 백테스트 실행 중..."):
        result_df, stats = run_strategy(
            df,
            ema_length=int(ema_length),
            bb_length=int(bb_length),
            bb_mult=float(bb_mult),
            initial_capital=float(initial_capital),
            qty=float(qty)
        )

    if "error" in stats:
        st.error(stats["error"])
    else:
        # 성과 요약
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("최종 자본", f"${stats['final_equity']:,.2f}")
        col2.metric("총 수익률", f"{stats['total_return_pct']:.2f}%")
        col3.metric("총 거래 수", f"{stats['total_trades']}")
        col4.metric("승률", f"{stats['win_rate']:.1f}%")
        col5.metric("최대 낙폭(MDD)", f"{stats['max_drawdown_pct']:.2f}%")

        # 차트
        st.subheader("가격 + 지표 + 신호")
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.7, 0.3],
            subplot_titles=("가격 / EMA / BB", "Equity Curve")
        )

        # 캔들
        fig.add_trace(go.Candlestick(
            x=result_df["datetime"],
            open=result_df["open"],
            high=result_df["high"],
            low=result_df["low"],
            close=result_df["close"],
            name="Price"
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=result_df["datetime"], y=result_df["ema"],
            name=f"EMA{ema_length}", line=dict(color="blue", width=1.5)
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=result_df["datetime"], y=result_df["bb_basis"],
            name="BB Basis", line=dict(color="orange", width=1.5)
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=result_df["datetime"], y=result_df["bb_upper"],
            name="BB Upper", line=dict(color="gray", width=1, dash="dot"), opacity=0.5
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=result_df["datetime"], y=result_df["bb_lower"],
            name="BB Lower", line=dict(color="gray", width=1, dash="dot"), opacity=0.5
        ), row=1, col=1)

        # 진입/청산 마커
        trades_df = stats["trades_df"]
        if not trades_df.empty:
            long_entries = trades_df[trades_df["side"] == "Long"]
            short_entries = trades_df[trades_df["side"] == "Short"]

            if not long_entries.empty:
                fig.add_trace(go.Scatter(
                    x=long_entries["entry_time"], y=long_entries["entry_price"],
                    mode="markers", name="Long Entry",
                    marker=dict(symbol="triangle-up", size=10, color="green")
                ), row=1, col=1)
                fig.add_trace(go.Scatter(
                    x=long_entries["exit_time"], y=long_entries["exit_price"],
                    mode="markers", name="Long Exit",
                    marker=dict(symbol="x", size=9, color="fuchsia")
                ), row=1, col=1)

            if not short_entries.empty:
                fig.add_trace(go.Scatter(
                    x=short_entries["entry_time"], y=short_entries["entry_price"],
                    mode="markers", name="Short Entry",
                    marker=dict(symbol="triangle-down", size=10, color="red")
                ), row=1, col=1)
                fig.add_trace(go.Scatter(
                    x=short_entries["exit_time"], y=short_entries["exit_price"],
                    mode="markers", name="Short Exit",
                    marker=dict(symbol="x", size=9, color="fuchsia")
                ), row=1, col=1)

        # Equity
        fig.add_trace(go.Scatter(
            x=result_df["datetime"], y=result_df["equity"],
            name="Equity", line=dict(color="purple", width=2), fill="tozeroy"
        ), row=2, col=1)

        fig.update_layout(
            height=800,
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02)
        )
        st.plotly_chart(fig, use_container_width=True)

        # 거래 내역
        if not trades_df.empty:
            st.subheader("거래 내역")
            st.dataframe(
                trades_df.style.format({
                    "entry_price": "{:.2f}",
                    "exit_price": "{:.2f}",
                    "pnl": "{:.2f}",
                    "equity": "{:.2f}"
                }),
                use_container_width=True
            )
        else:
            st.info("해당 기간에 발생한 거래가 없습니다.")

        # 데이터 다운로드
        csv = result_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "결과 데이터 CSV 다운로드",
            csv,
            file_name=f"MNQ_backtest_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

else:
    st.info("왼쪽 사이드바에서 데이터 소스를 선택하고 **백테스트 실행** 버튼을 눌러주세요.")
    st.markdown("""
    ### 사용 안내
    - **Yahoo Finance (추천)**: API 키 없이 최근 5~7일 15분봉을 무료로 가져옵니다. 심볼 예: `MNQ=F`
    - **한국투자증권 API**: CME 시세 권한이 있는 계좌만 사용 가능합니다.
    - EMA 기간이 200이라 데이터가 너무 짧으면 신호가 거의 안 나올 수 있습니다. 필요시 EMA를 20~50으로 줄여보세요.
    """)

st.markdown("---")
st.caption("Personal use only · Not financial advice")
