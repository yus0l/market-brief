# 서비스 v1 — 매일 아침 시장 관심사 브리핑

설계: `../서비스-v1-설계.md` · 기준: `02-UX.md` 서비스 v1 · `01-기획.md` v4~v4.3

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
