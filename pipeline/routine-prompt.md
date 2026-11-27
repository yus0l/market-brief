# 매일 07:30 KST Claude Code 클라우드 예약 실행 — 지시문

저장소 루트(service/)에서 순서대로:

0. 오늘 파일(draft·today·log)이 이미 있어도 **새로 조사해서 덮어쓴다** (수동 재실행 = 규칙이 바뀌어 다시 만들라는 뜻).
1. `git fetch origin main && git checkout -B main origin/main` 후 `data/facts-오늘.json`이 있는지 본다 (07:10 GitHub Actions가 수집해 둠). 없으면 멈춘다 — 키는 여기 없다.
2. `config/schedule-2027.json`에서 오늘(한국 날짜)부터 7일 안의 `verified: true` 일정을 확인한다.
3. 웹 검색으로 조사한다 — **모델 Sonnet, 웹 검색 최대 12회**. AI는 사건·예상치·언급 정도만 찾는다(지표 값은 1단계 코드가 이미 모음, 다시 찾지 않음) (`pipeline/generate.py`의 research 프롬프트와 같은 항목):
   ① 어제~오늘 사건 최대 3개(E1~E8, 출처 URL 2개) ② 7일 안 발표 예상치(출처 URL, 못 찾으면 null) ③ 관심사 3개 각각 trigger(계기)·fact(사실 칸 S1/S3)·watch(시장 칸 M1/M2)·market_type·market_sources — 문장 기준은 draft-rules.md(명세 §3-6): 날짜는 M/D, M2는 같은 해석 기사 2개, M1은 일정표 공식 날짜, 근거 없으면 null. fact는 '왜 지금 보는지'(직전 숫자·흐름)만, 발표 예정 문장 금지. 수집값에 없는 숫자는 서로 다른 매체 2개 확인 후 extra_numbers에. 그리고 최근 3일 물가·경기·금리 언급 정도 + **관심사마다 서로 다른 기사 URL 3개 이상**(3개 못 채우면 그 관심사는 화면에서 빠짐. 물가·경기·금리 3개 모두 sources에 넣는다).
   검색 배분(합계 12회 이내): 관심사 3개에 각 2회(예: "inflation stocks this week", "물가 증시"), 사건·예상치에 나머지. 검색 결과 목록에 나온 기사 URL을 그대로 쓰면 된다(본문을 다 열 필요 없음). 같은 URL을 다른 관심사에 재사용하지 않는다. 금 가격·ISM은 v1에서 찾지 않음(화면에 "값 확인 전").
   파일은 필요한 것만 연다: config/draft-schema.json, config/draft-rules.md, data/facts-오늘.json. index.html·기획 문서는 열지 않는다.
4. `config/draft-schema.json` 형식 그대로 `data/archive/draft-YYYY-MM-DD.json`을 쓴다. `config/draft-rules.md` 규칙을 지킨다.
   - 문장에 숫자를 쓰지 않는다(시스템이 수집값으로 채움). 못 찾은 건 null. 지어내지 않는다.
5. `python3 pipeline/build.py --draft data/archive/draft-YYYY-MM-DD.json` — 조립·검사 후 `web/today.json` 갱신.
   검사에서 빠진 항목은 고치지 말고 그대로 둔다(로그에 남음).
6. `git add data/archive web/today.json && git commit -m "brief YYYY-MM-DD" && git push` → push로 Pages 배포.

실패하면(한도·오류) 아무것도 바꾸지 않는다 → 화면은 어제 파일 + "데이터 지연" 표시.
