# MNQ 15분봉 BB Basis × EMA200 백테스트 앱

한국투자증권 해외선물 분봉조회 API를 사용한 개인용 Streamlit 백테스팅 웹앱입니다.

## 설치 및 실행

```bash
cd kis_backtest
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 로 접속합니다.

## Streamlit Cloud 배포 (개인 URL)

1. GitHub에 이 폴더를 올립니다.
2. https://share.streamlit.io 접속 후 GitHub 연동
3. 해당 레포의 `app.py` 선택 → Deploy
4. 생성된 URL로 어디서든 접속 가능

## 주의사항

- APP Key / Secret은 사이드바에 직접 입력하세요. 코드에 넣지 마세요.
- MNQ는 월물 코드가 필요합니다 (예: MNQU6, MNQZ6). HTS에서 확인하세요.
- 5년치 연속 15분봉은 API 제한으로 현실적으로 어렵습니다. 최근 데이터 위주로 테스트하세요.
- CME 시세는 유료일 수 있습니다.
- 이 앱은 개인 연구용이며 투자 조언이 아닙니다.
