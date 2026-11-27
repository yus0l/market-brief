# 매일 07:30 KST Claude Code 클라우드 예약 실행 — 지시문

저장소 루트(service/)에서 순서대로:

1. `git pull` 후 `data/facts-오늘.json`이 있는지 본다 (07:10 GitHub Actions가 수집해 둠). 없으면 멈춘다 — 키는 여기 없다.
2. `config/schedule-2027.json`에서 오늘(한국 날짜)부터 7일 안의 `verified: true` 일정을 확인한다.
3. 웹 검색으로 조사한다 — **모델 Sonnet, 웹 검색 최대 12회**. AI는 사건·예상치·언급 정도만 찾는다(지표 값은 1단계 코드가 이미 모음, 다시 찾지 않음) (`pipeline/generate.py`의 research 프롬프트와 같은 항목):
   ① 어제~오늘 사건 최대 3개(E1~E8, 출처 URL 2개) ② 7일 안 발표 예상치(출처 URL, 못 찾으면 null) ③ 최근 3일 물가·경기·금리 언급 정도 + 기사 URL 3개. 금 가격·ISM은 v1에서 찾지 않음(화면에 "값 확인 전").
   파일은 필요한 것만 연다: config/draft-schema.json, config/draft-rules.md, data/facts-오늘.json. index.html·기획 문서는 열지 않는다.
4. `config/draft-schema.json` 형식 그대로 `data/archive/draft-YYYY-MM-DD.json`을 쓴다. `config/draft-rules.md` 규칙을 지킨다.
   - 문장에 숫자를 쓰지 않는다(시스템이 수집값으로 채움). 못 찾은 건 null. 지어내지 않는다.
5. `python3 pipeline/build.py --draft data/archive/draft-YYYY-MM-DD.json` — 조립·검사 후 `web/today.json` 갱신.
   검사에서 빠진 항목은 고치지 말고 그대로 둔다(로그에 남음).
6. `git add data/archive web/today.json && git commit -m "brief YYYY-MM-DD" && git push` → push로 Pages 배포.

실패하면(한도·오류) 아무것도 바꾸지 않는다 → 화면은 어제 파일 + "데이터 지연" 표시.
