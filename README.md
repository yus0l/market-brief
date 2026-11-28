# 서비스 v1 — 매일 아침 시장 관심사 브리핑

설계: `../서비스-v1-설계.md` · 기준: `02-UX.md` 서비스 v1 · `01-기획.md` v4~v4.3

## 인계 (2026-11-28, 이전 개발 창)
- **돌아가는 것**: 07:10 collect.yml(FRED·ECOS → data/facts-날짜.json) → 07:30 예약 실행 trig_01VcBarWwXQYRNVVyzZGRDRR(Sonnet, pipeline/routine-prompt.md, v1) → build.py → web/today.json → push = Pages 배포(daily.yml, node --check). 기본 화면 = v1 흐름도, `?b=1` = B v4 타임라인.
- **B v4 (`?b=1`)**: homeB(). web/today-v2.json이 있으면 그걸, 없으면 v1 데이터를 topicsFromV1()로 바꿔 그림. `?b=1&v2mock=1` = web/mock/v2-topics.json 목업. 사실 = 흰 바탕, 해석 = 회색 박스, 호재/악재는 이유(sidetags.json reason) 있을 때만.
- **반쯤 된 것**: pipeline/v2.py(정보설계 v3 스키마·검사기·조립, `python3 pipeline/v2.py run 초안`) + routine-prompt-v2.md. 매일 실행엔 미연결(전환 = B를 기본 화면으로 올리는 날). 11/28 수동 1회 결과: 관심사 1개(엔비디아), 회사 주가 매체 2개 못 찾아 경로 없음 → 기업 숫자 검색 보강 필요.
- **안 끝난 것**: 02-UX.md "B v4 전체 점검" 11개(잘림·실제로는 조건·"다음 날" 날짜·✓→점·선 연속 등) 미착수. #10 "최신 값 확인 전"은 합의 규칙(데이터 나라 휴일 제외 2영업일)상 11/24 S&P는 정상.
- **주의**: 키는 GitHub Secrets만(FRED_API_KEY·ECOS_API_KEY). 키 없이 로컬에서 build.py 그냥 돌리면 오늘 날짜 빈 파일 생김 → 과거 날짜 재조립은 날짜 고정 실행기로. 스키마 바꾸면 `python3 pipeline/generate.py`·`python3 pipeline/v2.py`로 다시 내보내기. 큰 변경 전 versions/에 백업. 검사 `python3 pipeline/test_build.py`("bad:" 줄은 정상 부정 예시)·`test_v2.py`.
- **결정 대기**: BANNED "매도"가 사실 "외국인 순매도"도 막음(PM). holidays.json 2027 미입력.

## v4 사례 화면 (`?b=1`, 11/28 개발 착수)
기준: `../../01-정보설계.md` 맨 위 v4 · `../../02-화면.md` · `../../01-연결표.md`. v1 매일 실행·기본 화면은 그대로.
- **화면**: `web/v4.html` (index.html이 `?b=1`이면 여기로 넘김. 예전 B 타임라인은 `?b=v3`). 데이터 `web/v4/cases.json`, `?mock=1` = `web/v4/mock.json`(02-화면 금 사례 목업)
- **칸·연결표**: `pipeline/v4_cells.py` — 수집 칸 목록(CELLS)·연결표 번호 ↔ 칸 묶음·방향(LINK_MAP). `01-연결표.md`가 바뀌면 `python3 pipeline/v4_cells.py links` → `config/links-v4.json` (로컬에서만, 원본 md가 저장소 밖)
- **수집**: `pipeline/v4_data.py` — `history`(FRED·ECOS 1년+ 일별 → 표준편차 2배 '크게' 날짜), `sec`(엔비디아, Secrets `SEC_USER_AGENT`), `attention`(GDELT 기사 양, US·KS, 1년치 안 되면 3개월), `gdelt-check`. collect.yml 07:10 뒤 단계로 붙음(실패해도 v1 무관)
- **검사·조립**: `pipeline/v4.py` — `precheck`(①주목도 ②영향도) → `build`(칸 검사·③한국 영향·앞으로·태그·사례 상태 → cases.json + `data/v4/log-날짜.json`)
- **AI 지시문**: `pipeline/routine-prompt-v4.md` — 아직 예약 실행 미연결(사용자 화면 확인 뒤)
- **시험**: `python3 pipeline/test_v4.py` (키·네트워크 없이 14개)
- **정한 것**: 금·업종 지수는 media 칸(매체 2곳 같은 숫자), '크게' 판단 안 함. 기업 주가 칸 없음. 연결표 1(WGC 한 곳)·11(⚠)은 약함 → 앞으로 끝 칸이면 미지수
- **모르는 것**: GDELT 1년치가 GitHub에서 받아지는지(`data/v4/gdelt-check.json`), 기사 양 기준으로 실제 사례가 몇 개 나오는지

## 폴더
| 경로 | 내용 |
|---|---|
| `web/index.html` | 화면. `today.json`만 읽음. 디자인 시스템 v0.7 토큰을 안에 복사 |
| `web/today.json` | 오늘 공개본 (지금은 샘플, `mock: true`) |
| `web/mock/*.json` | 상태별 샘플 (조용한 날·발표 당일·갈라짐·지연·휴장·1순위 변경·관심사 1개) — `?dev=1`로 열면 위 바에서 바꿔 봄 |
| `config/graph.json` | 칸 8개·기본 관계 13개·관심사 후보 3개(규칙·문장 템플릿). 화면 `E` 목록과 같아야 함 |
| `config/schedule-2027.json` | 발표 일정 (기획 표에서 자동 생성, ET→KST 변환, "확인 필요"는 verified=false) |
| `config/sectors.json` | 사건 유형 E1~E8 × 업종 (기획 표에서 자동 생성) |
| `pipeline/collect.py` | ① FRED·ECOS 수집 → `data/facts-날짜.json` |
| `pipeline/routine-prompt.md` | ③ AI 생성 = Claude Code 클라우드 예약 실행 지시문 (PM 결정 11/26) |
| `pipeline/generate.py` | 형식·규칙 내보내기(`config/draft-schema.json`, `draft-rules.md`) + 예비용 API 경로 |
| `pipeline/validate.py` | ④ 검사기 (금지어·출처·숫자·기본 관계·템플릿) |
| `pipeline/build.py` | 전체 실행: 수집 → 생성 → 조립(순위·상태 계산) → 검사 → `web/today.json` + `data/archive/` |
| `pipeline/test_build.py` | 키 없이 조립·검사 확인 |
| `.github/workflows/daily.yml` | `web/` push되면 GitHub Pages 공개 (생성은 예약 실행이 함) |

## 실행
```
python3 pipeline/schedule_from_md.py   # 기획 일정 표가 바뀌면
python3 pipeline/sectors_from_md.py    # 기획 업종 표가 바뀌면
python3 pipeline/test_build.py         # 키 없이 테스트
FRED_API_KEY=… ECOS_API_KEY=… python3 pipeline/build.py --draft data/archive/draft-날짜.json
```

## 키 발급 (사용자)
- FRED: https://fred.stlouisfed.org/docs/api/api_key.html (무료, 회원가입)
- 한국은행 ECOS: https://ecos.bok.or.kr/api/ (무료, 회원가입 → 인증키 신청)
- 키는 파일에 쓰지 말고 GitHub 저장소 Settings → Secrets에만 넣는다

## 첫 실행 때 확인할 것
- ECOS 통계표·항목 코드(`collect.py` ECOS 표)가 화면 값과 맞는지 한 번 대조
- 2026년 12월 일정(CPI·고용·FOMC 12월)은 아직 표에 없음 → 기획에 요청
- 금 가격·ISM은 웹 검색 값이라 출처가 매일 남는지 로그(`data/archive/log-날짜.json`) 확인
- "예상치 찾은 비율"(`expect_found/expect_total`)을 2주 기록 (기획 v4 미확정 1)
