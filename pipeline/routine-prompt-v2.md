# v2 수동 1회 실행 — 지시문 (01-정보설계.md v3)

매일 실행(v1, routine-prompt.md)과 별개. **web/today.json은 건드리지 않는다.** 결과는 web/today-v2.json 하나.

1. `git fetch origin main && git checkout -B main origin/main`. `data/facts-*.json` 중 가장 최근 것을 쓴다(지표 값은 거기 있음, 다시 찾지 않음).
2. 열 파일: `config/draft-schema-v2.json`(틀·설명), `config/graph.json`(기본 관계 edges·nodes), `config/sidetags.json`(K표), `config/schedule-2027.json`, 최근 facts. 그 밖 파일은 열지 않는다.
3. 웹 검색 **최대 18회** — 배분:
   - 관심사 찾기·언급·주목 이유 4회: 최근 3일 시장 뉴스에서 주목받는 **키워드**를 요소별로 넓게(경제 지표·중앙은행 / 기업 소식 / 정책·정치·지정학 / 한국 시장). 키워드는 고정 목록이 아니다 — 물가·금리일 수도, 회사·규제·전쟁일 수도 있다. 후보 최대 5개, 각각 서로 다른 매체 기사 URL 3개 이상.
   - 기준 지표 예상치 2회: 7일 안 발표가 있는 관심사만, 서로 다른 매체 2개.
   - 칸마다 이번에 왜 6회: 경로 위 실제로 움직인 칸이 왜 움직였나 "[원인] 때문이라고 봐요", 매체 2개. 못 찾으면 null, link_prev=unknown.
   - 기사 연결 경로 4회: **하루 1개 관심사만**(기업 소식·정책·지정학 중 가장 언급 많은 것). 기본 관계에 없는 연결(예: 회사 → 업종 → 지수)마다 서로 다른 매체 2개, 수집값 없는 칸(co:·sector:·idx:·px:)은 매체 2개가 같은 숫자일 때만 num.
   - 읽는 법 기사 근거 2회: K표에 맞는 유형이 없는 관심사만 "기사들이 호재/악재로 보는지"(갈리면 갈래별) 매체 2개.
4. `data/archive/draft-v2-YYYY-MM-DD.json`을 스키마 그대로 쓴다. date = 한국 오늘 날짜(`TZ=Asia/Seoul date +%F`).
   - 경로: 관심사 칸에서 시작해 시장 칸(stock·kospi·rate·fx·sector:·idx:)에서 끝. 최대 6칸. 미국 경로의 다음 날 코스피는 코드가 붙인다(넣지 않음).
   - 경제 지표·중앙은행·공포 요소는 기본 관계(graph.json edges)를 따라 칸을 잇는다(link_sources 빈 배열).
   - 지어내지 않는다. 못 찾은 건 null/빈 배열. 문장에 숫자 쓰지 않는다(num.value만 숫자). 종목 추천처럼 보이는 말 금지.
5. `python3 pipeline/v2.py run data/archive/draft-v2-YYYY-MM-DD.json` — 검사에서 빠진 것은 고치지 않는다.
6. `git add data/archive/draft-v2-*.json web/today-v2.json && git commit -m "v2 수동 1회 YYYY-MM-DD" && git pull --rebase origin main && git push origin HEAD:main`
7. 결과로 v2.py가 출력한 한 줄(JSON)을 그대로 남긴다.
