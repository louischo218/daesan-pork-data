# 대산에프앤비 경락 데이터 파이프라인

축평원 OpenAPI에서 경락 데이터를 매 평일 오전 자동 수집해 `data.json`으로 발행합니다.
판가 운영프로그램이 이 파일을 읽습니다. 화면(대시보드)은 없습니다 — 데이터 전용.

## 설치 (GitHub 웹에서 10분, 코딩 불필요)

1. **저장소 만들기**: github.com 로그인 → New repository → 이름 예: `daesan-pork-data` → **Public** 선택 → Create
   (Public이어야 판가 프로그램이 읽을 수 있습니다. 인증키는 코드에 없으니 안전합니다)
2. **파일 3개 올리기**: Add file → Upload files 로 `collector.py`, `README.md` 업로드.
   `update.yml`은 Add file → **Create new file** → 파일명 칸에 `.github/workflows/update.yml` 그대로 입력 → 내용 붙여넣기 → Commit
3. **인증키 등록**: Settings → Secrets and variables → Actions → New repository secret
   - Name: `EKAPE_KEY`
   - Secret: 발급받은 인증키 (URL 인코딩된 형태 그대로, %2F 포함)
4. **첫 실행**: Actions 탭 → "경락 데이터 자동 수집" → Run workflow → 1~2분 후 초록 체크 확인
   (첫 실행 시 과거 이력을 더 모으려면 Run 전에 collector.py의 FETCH_DAYS 환경변수를 늘려 실행: 선택사항)
5. **확인**: 저장소 첫 화면에 `data.json`이 생겼는지 확인. 주소는
   `https://raw.githubusercontent.com/<계정명>/<저장소명>/main/data.json`
   → 이 주소를 판가 프로그램 연동에 사용합니다.

이후로는 아무것도 안 해도 평일 오전 9:30(한국시간)에 자동 갱신됩니다.

## data.json 구조
- `daily`: {날짜(YYYYMMDD): 전국(제주제외) 탕박·등외제외 두수가중 평균가}
- `regional`: 권역별 가격·두수 / `representative`: 돈육대표가격 / `markets`: 도매시장별
- `updated`: 마지막 갱신 시각(UTC) / `basis`: 산출 기준 명세
