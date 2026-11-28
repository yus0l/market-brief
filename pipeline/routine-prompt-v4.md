# v4 사례 생성 — 지시문 (?b=1, 01-정보설계.md v4 · 02-화면.md)

아직 매일 예약 실행에 연결하지 않음. 사용자가 `?b=1` 화면을 확인한 뒤 연결한다. 그 전엔 수동으로 돌린다.
저장소 루트(service/)에서 순서대로. **웹 검색 최대 12회, 모델 Sonnet.** 값·날짜·출처를 지어내지 않는다. 못 찾으면 비운다.

0. `git fetch origin main && git checkout -B main origin/main`. `data/v4/history.json`의 date가 오늘 또는 어제인지 본다. 아니면 멈춘다(07:10 수집이 안 돈 날).
1. **사건 후보** (검색 4회): 최근 24시간 미국·한국 주요 매체에서 크게 다뤄진 일 중 범위 안의 것, 최대 4개.
   - 범위: 거시 경제(물가·금리·고용·경기·유가·환율·중앙은행·지정학의 경제 영향) / 기업 펀더멘털은 **엔비디아만**(실적·매출·영업이익·현금흐름·부채)
   - `web/v4/cases.json`에서 status가 `live`인 사례는 **모두** 후보에 다시 넣고 `same_as`에 그 id를 쓴다(계속 진행 중인지 코드가 다시 판단)
   - 후보마다: `key`(영문 소문자-하이픈), `name`(사건 이름만, 해석·예측 없이. 예: "중동 전쟁 시작"), `kind`(`macro`/`firm`), `date`(사건이 처음 일어난 날, YYYY-MM-DD), `sources`(서로 다른 매체 2곳 이상 `{name,url}`), `gdelt_query`(GDELT 검색어, 영어. 예: `(Iran OR Israel) (oil OR crude)`)
   - `data/v4/draft-YYYY-MM-DD.json`에 `{"date": …, "candidates": […]}`로 쓴다
2. `python3 pipeline/v4_data.py attention data/v4/draft-YYYY-MM-DD.json` → `python3 pipeline/v4.py precheck data/v4/draft-YYYY-MM-DD.json`
   - `write_flow: true`인 후보만 3단계로. 하나도 없으면 4단계(build)만 돌린다 — 진행 중 사례가 `기록`으로 바뀐다
3. **흐름** (검색 8회, 후보마다): 같은 파일 `flows.{key}`에 쓴다
   - `start_reason`: 사건이 왜 시장에 퍼졌나 한 줄, 과거형 "…했어요/…퍼졌어요" + 서로 다른 매체 2곳
   - `nodes`: 사건 뒤 실제로 움직인 칸. 각 `{id, cell 또는 media, parents, reason, reason_sources, link}`
     - `cell` = `pipeline/v4_cells.py` CELLS 키(값·방향·날짜는 코드가 채움). 거기 없는 칸(금·업종 지수 등)은 `media: {name, grp(gold/sector/…), value(화면 표기 그대로, 예: "온스당 $2,610"), dir(up/down/flat), country(us/kr), sources(서로 다른 매체 2곳이 같은 숫자)}`
     - `reason`: 그 칸이 **왜 움직였나** 과거형 한 줄(40자 안팎, "…해서 …했어요"). 근거는 **서로 다른 매체 2곳(`reason_sources`)만** 인정 — 연결표(`config/links-v4.json`)는 이유의 근거가 아니다(칸 사이 연결·앞으로 칸에만). 매체 2곳을 못 찾으면 그 칸을 쓰지 않는다
     - 칸 하나가 여러 칸으로 갈라지고(`parents` 같은 칸), 여러 칸이 하나로 합쳐질 수 있다(`parents` 여럿 — 이유에 두 원인을 같이 씀)
   - `future`: 앞으로 = 하나의 흐름
     - `release_code`: `config/schedule-2027.json`에서 흐름 칸과 관련된 30일 안 `verified` 발표 코드(없으면 null)
     - `header`: 발표 결과 조건, 의문형 "…나온다면?" (발표 없으면 끝 칸 상태 "원화가 더 약해진다면?")
     - `start`: `{cell, dir}` 조건이 가리키는 칸과 방향
     - `nodes`: `{id, cell 또는 media, parent(위 칸 id, 첫 칸은 "fstart"), link(연결표 번호 — 필수), reason, unknown_why}`. 중간 칸 이유는 "…해서 더 오르기/내리기 쉬워요", 끝 칸은 "…해서요". 연결의 '깨지는 때'에 지금 해당하면(매체 2곳) `unknown_why`에 왜 모르는지 한 줄
   - 문장 공통: 전문용어 대신 풀어서. 숫자는 칸 값에만(코드가 채움). 매수·매도 권유, 목표가, 주가 전망 금지
4. `python3 pipeline/v4.py build data/v4/draft-YYYY-MM-DD.json` → `web/v4/cases.json`, `data/v4/log-YYYY-MM-DD.json`. **검사에서 빠진 칸은 고치지 않고 그대로 둔다.**
5. `git add data/v4 web/v4 && git commit -m "v4 YYYY-MM-DD" && git push origin HEAD:main`. 끝나면 log의 passed·errors 개수를 한 줄로 남긴다.

지난 초안(`data/v4/draft-*.json`)을 복사하지 않는다. 오늘 검색한 것만 쓴다.
