"""③ AI 생성. 운영은 Claude Code 클라우드 예약 실행(PM 결정 11/26) → routine-prompt.md 참고.
이 파일의 API 경로는 예비용이고, SCHEMA·RULES는 예약 실행도 같이 쓴다.
(API 경로) 두 번 부른다.
  A. 조사: 웹 검색으로 오늘 사건·예상치·관심사 언급 기사·금 가격·ISM을 찾고 URL과 함께 적는다.
  B. 정리: 조사 메모 + 수집값을 정해진 JSON 형태(구조화 출력)로 옮긴다. 칸·선·쪽은 목록 안에서만 고른다.
숫자는 여기서 확정하지 않는다 — build.py가 수집값으로 채우고 validate.py가 검사한다.
환경변수: ANTHROPIC_API_KEY (또는 ant auth login)."""
import json, pathlib, datetime as dt

HERE = pathlib.Path(__file__).resolve().parent
CFG = json.loads((HERE.parent / "config" / "graph.json").read_text(encoding="utf-8"))
MODEL = "claude-sonnet-5-5"   # 토큰 절약 (PM 11/26)

RULES = """규칙 (서비스 원칙 — 어기면 그 항목은 화면에 안 나간다)
- 서비스는 좋고 나쁨을 판단하지 않는다. 화면 글에 '호재' '악재' '보통 ○○ 쪽' 단어를 쓰지 않는다(쪽 해석은 코드가 "지금은 주식에 부담/도움"으로 붙임, 02-UX 11/28). '판정' '매수' '매도' '유력' '확실' '~될 거예요' 금지. 종목명 금지(사건 이름 '엔비디아 실적'은 가능).
- 모든 사실·수치에는 출처 URL. 못 찾으면 null로 두고 지어내지 않는다.
- 예상 대비는 '예상보다 높음' / '예상대로' / '예상보다 낮음' 중 하나. 실제값·예상치 출처가 둘 다 있어야 한다. 조사가 갈리면 다수 의견 + spread=true.
- 경로는 아래 기본 관계 목록의 선만 쓴다. 새 연결을 만들지 않는다.
- 시나리오 조건은 확인 가능한 지표·일정만('투자 심리가 회복되면' 같은 것 금지).
- '물가 ▼'는 '물가 오름세 둔화'로 쓴다.
- 문장 기준(명세 §3-6): 문장은 두 칸 = [사실: 무슨 일이 있었다/있다] + [시장: 시장은 그걸 어떻게 하고 있다]. 관심사 박스 = 사실(S1/S3) + 시장(M2 근거 있으면 M2, 없으면 M1, M3 금지). 시점은 날짜 'M/D'로('어제·이번 주·최근·N일 뒤·곧' 금지). 두 문장이 같은 지표를 반복하지 않음. 해요체, 한 문장 40자 안쪽, 주어를 숨기지 않음. 근거가 없으면 시장 칸은 null(사실 한 문장만).
- 지난 사건 질문형 제목(question) = '[M/D] [다음 지표]가 [방향]할까요?' 지표 이름 필수, 날짜는 일정표 공식만(없으면 뺌). 방향 말은 최근 값 기준: 최근 ▼면 '다시 오를까요?', ▲면 '더 오를까요?'. 예: '12/2 한국 소비자물가가 다시 오를까요?'
- 사건 유형(명세 §3-10): 일정표 정기 발표·금리 결정·실적 = T1(숫자 1개로 갈림, 시나리오 a/b = 그 숫자가 예상보다 높으면/낮으면). 일정표 밖 사건 중 기사들이 결과를 두 갈래로 나눠 보는 것 = T2(하루 1개, 시나리오 a/b label = 확인할 수 있는 내용 조건, t2에 갈래 이름·기사 견해·확인할 일·집계 기사). 어느 쪽에도 안 맞으면 고르지 않는다.
- 기사 N개 = 서로 다른 매체 N개(통신사 기사를 옮겨 실은 건 1개).
- outlook(앞으로 한 줄)은 금리 결정이 예상대로일 때만. size(크기를 바꾸는 것)는 최대 2개, '다만…/게다가…' 틀.
- 칸 kospi(한국 주식)와 관계 주식→kospi(다음 날)는 미국 사건에서만, 경로 끝에 쓴다. 미국 사건의 환율→주식은 화면에서 원/달러→코스피로 그려진다.
- ▲▼는 실제 움직임에만. 가정·시나리오 문장은 '오름 쪽/내림 쪽' 글자로. watch.high/low는 화면에 안 나오지만 시나리오 방향 확인용으로 짧게.
- 사건마다 watch(다음에 볼 지표) 하나: 사건과 같은 나라 지표. 시나리오 a = watch가 예상보다 높을 때, b = 낮을 때. 시나리오 조건 첫 칸·결과 확인 첫 단계는 그 지표(시스템이 채움). 시나리오 state는 그 지표가 말하는 칸만 바꾸고, 이미 일어난 사실(real)의 방향을 뒤집지 않는다.
- 관심사 박스 둘째 문장(watch)의 지표는 사건 watch 지표나 '판단할 때 같이 볼 것' 지표 중에서만.
- 관심사 계기(trigger)는 출처 기사 2개 이상일 때만.
- 관심사 박스 첫 문장(fact) = 왜 지금 이 관심사를 보는지: 직전 숫자·흐름(S1 지난 발표 / S3 지표 움직임). '…발표가 있어요' 같은 발표 예정 문장은 쓰지 않는다. 이유 문장을 못 만들면 null(그 관심사는 숨김).
- 숫자는 수집값 우선. 수집값에 없는 숫자는 서로 다른 매체 2개에 같은 숫자가 있을 때만 쓰고 extra_numbers에 값과 두 출처를 적는다. 7일 안 발표 때문이면 trigger·fact는 null로 둬도 된다(시스템이 'D-n'과 날짜 문장을 만든다)."""

def graph_text():
    n = CFG["nodes"]
    return "칸: " + ", ".join(f"{k}={v}" for k, v in n.items()) + "\n기본 관계: " + ", ".join(
        f"{n[a]}→{n[b]}" + (" (양방향)" if r else "") for a, b, *r in CFG["edges"])

def ask(messages, **kw):
    """refusal 대비 서버 쪽 대체 모델(fallbacks) 켬. pause_turn이면 이어서 돌린다."""
    import anthropic
    client = anthropic.Anthropic()
    while True:
        r = client.beta.messages.create(model=MODEL, max_tokens=16000, betas=["server-side-fallback-2026-07-01"],
                                        fallbacks="default", messages=messages, **kw)
        if r.stop_reason == "refusal": raise RuntimeError(f"refusal: {r.stop_details}")
        if r.stop_reason != "pause_turn": return r
        messages = messages + [{"role": "assistant", "content": r.content}]

def research(today, facts, upcoming):
    prompt = f"""오늘은 {today} (한국 시간 07:30). 한국 주식 초보용 아침 브리핑에 쓸 재료를 웹 검색으로 찾아 메모해줘.
{RULES}

1. 어제~오늘 나온 시장 사건(최대 5개): 아래 유형 중 하나에 해당하는 것만. 무슨 일이 있었는지, 실제 수치, 시장 예상치, 출처 URL 2개 이상.
   E1 금리▲ / E2 금리▼ / E3 유가▲ / E4 원화 약세 / E5 경기▲ / E6 경기▼ / E7 공포▲ / E8 AI·반도체 실적
2. 7일 안 발표 예정(아래 목록)의 시장 예상치(컨센서스)와 출처 URL. 못 찾으면 '못 찾음'.
{json.dumps(upcoming, ensure_ascii=False)}
3. 최근 3일 뉴스에서 '물가', '경기', '금리' 각각: 대표 기사 URL 3개 이상, 언급 정도(많음/보통/적음), 오르는 쪽인지 내리는 쪽인지, 순위를 올린 계기 한 마디(사건 이름이나 뉴스 주제, 출처 2개 이상), 박스 문장 2개(사실 + 시장이 보는 것).
4. 금 가격(전일 종가)과 출처 1곳 이상. 오늘이 ISM 발표 다음 날이면 ISM 제조업 PMI 값과 출처.
참고로 이미 공식 API로 모은 값(이 값들은 다시 찾지 않아도 됨): {json.dumps({k: [v['name'], v['value'], v['date']] for k, v in facts['series'].items()}, ensure_ascii=False)}
메모는 항목별로 짧게, URL은 빠짐없이."""
    r = ask([{"role": "user", "content": prompt}], tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 12}],
            output_config={"effort": "high"})
    return "\n".join(b.text for b in r.content if b.type == "text")

NODE = {"type": "string", "enum": list(CFG["nodes"])}
EDGE = {"type": "array", "items": NODE, "minItems": 2, "maxItems": 2}
DIR = {"type": ["string", "null"], "enum": ["up", "down", None]}
SIDE = {"type": ["string", "null"], "enum": ["good", "bad", None]}
STATE = {"type": "object", "properties": {"node": NODE, "dir": DIR, "us": DIR, "kr": DIR}, "required": ["node", "dir", "us", "kr"], "additionalProperties": False}
COND = {"type": "object", "properties": {"text": {"type": "string"}, "dir": DIR, "done": {"type": "boolean"}}, "required": ["text", "dir", "done"], "additionalProperties": False}
OPT = {"type": "object", "properties": {"label": {"type": "string"}, "path": {"type": "array", "items": EDGE}, "state": {"type": "array", "items": STATE},
       "cond": {"type": "array", "items": COND, "minItems": 1, "maxItems": 3}, "out": {"type": "string"}},
       "required": ["label", "path", "state", "cond", "out"], "additionalProperties": False}
SRC = {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "url": {"type": "string"}}, "required": ["name", "url"], "additionalProperties": False}}
BR = {"type": "object", "additionalProperties": False, "required": ["short", "view", "view_sources"], "properties": {
      "short": {"type": "string", "description": "갈래 짧은 이름(정책·결과 내용, 후보 이름 금지). 예: '건설 제한'"},
      "view": {"type": "string", "description": "기사들은 이렇게 봐요: 한두 문장, 주어 = 기사('기사들은 …로 봐요'). 쪽 말 금지"},
      "view_sources": SRC}}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["interests", "events", "extra_numbers"], "properties": {
  "extra_numbers": {"type": "array", "description": "수집값에 없는데 문장에 쓴 숫자. 서로 다른 매체 2개에 같은 숫자가 있을 때만", "items": {"type": "object", "additionalProperties": False,
      "required": ["value", "sources"], "properties": {"value": {"type": "string"}, "sources": SRC}}},
  "interests": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["key", "mention", "dir", "sources", "trigger", "trigger_sources", "fact", "fact_sources", "watch", "market_type", "market_sources"], "properties": {
      "key": {"type": "string", "enum": list(CFG["interests"])}, "mention": {"type": "string", "enum": ["많음", "보통", "적음"]},
      "dir": {"type": "string", "enum": ["up", "down"]}, "sources": SRC,
      "trigger": {"type": ["string", "null"], "description": "칩 아랫줄 계기, 8자 안팎. 순위를 올린 사건·뉴스 주제 자체(예: '한은 금리 인상', '고용 둔화 뉴스'). '가장 많이 언급' 같은 집계 말 금지, ▲▼·'실시간' 금지. 못 만들면 null"},
      "trigger_sources": SRC,
      "fact": {"type": ["string", "null"], "description": "박스 첫 문장 = 사실 칸 S1(지난 발표: [M/D] [누가] [무엇을] [값]으로 [했어요]) 또는 S3(지표 움직임: [M/D] [지표]가 [수집값]으로 [올랐어요/내렸어요]). 날짜는 'M/D'로, '어제·이번 주·최근·N일 뒤·곧' 금지. 40자 안쪽. 예: '11/26 한국은행이 기준금리를 3.00%에서 3.25%로 올렸어요.' 근거 없으면 null"},
      "fact_sources": SRC,
      "watch": {"type": ["string", "null"], "description": "박스 둘째 문장 = 시장 칸, 주어 '시장은'. M1: '시장은 [M/D] [지표]가 [어떻게 될지] 지켜보고 있어요'(일정표 공식 날짜 필수) / M2: '시장은 [칸][방향]을 걱정하고·기대하고·보고 있어요'(같은 해석 기사 2개 이상, 칸 이름으로 말함, 관심사 기준 악재 쪽이면 걱정·호재 쪽이면 기대). 첫 문장과 같은 지표를 반복하지 않음. 40자 안쪽. 근거 없으면 null"},
      "market_type": {"type": ["string", "null"], "enum": ["M1", "M2", None]},
      "market_sources": SRC}}},
  "events": {"type": "array", "maxItems": 3, "items": {"type": "object", "additionalProperties": False,
      "required": ["id", "date", "etype", "t2", "outlook", "size", "question", "watch", "type", "chip", "head", "kind", "schedule_code", "expect", "actual_src", "expect_src", "spread", "real", "realPath", "next", "opts", "judge_keys", "confirm", "sources"],
      "properties": {
        "question": {"type": ["string", "null"], "description": "지난 사건 패널 제목 = 열린 질문, '…까요?'로 끝남. 예: '금리를 올린 뒤, 물가 부담이 이어질까요?'"},
        "etype": {"type": "string", "enum": ["T1", "T2"], "description": "T1 숫자로 갈림(일정표 정기 발표·금리 결정·실적은 무조건 T1) / T2 내용으로 갈림(일정표 밖, 기사들이 결과를 2갈래 이상으로 나눠 봄: 규제·관세·선거). T2는 하루 1개만"},
        "t2": {"type": ["object", "null"], "additionalProperties": False, "required": ["verify", "a", "b", "tally", "actual"], "description": "T2일 때만. T1이면 null",
               "properties": {"verify": {"type": "object", "additionalProperties": False, "required": ["what", "when", "source"], "properties": {"what": {"type": "string", "description": "확인할 일: 법안 발표·표결 등"}, "when": {"type": ["string", "null"], "description": "YYYY-MM-DD, 모르면 null"}, "source": {"type": ["object", "null"], "additionalProperties": False, "required": ["name", "url"], "properties": {"name": {"type": "string"}, "url": {"type": "string"}}}}},
                              "a": BR, "b": BR,
                              "tally": {"type": "array", "description": "갈래를 만든 기사(view_sources) 말고, 이 사건 결과를 어느 갈래로 보는지 말한 기사. 서로 다른 매체, 매체당 1개", "items": {"type": "object", "additionalProperties": False, "required": ["name", "url", "date", "branch"], "properties": {"name": {"type": "string"}, "url": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD"}, "branch": {"type": "string", "enum": ["a", "b"]}}}},
                              "actual": {"type": ["string", "null"], "enum": ["a", "b", None], "description": "결과가 나왔으면 실제 갈래"}}},
        "outlook": {"type": ["object", "null"], "additionalProperties": False, "required": ["text", "sources"], "description": "금리 결정이 '예상대로'일 때만: 앞으로 방향 한 문장(점도표·소수 의견 등). 쪽 말·▲▼ 금지. 서로 다른 매체 2개. 예: '점도표는 내년 인하 2번을 가리켜요'",
                    "properties": {"text": {"type": "string"}, "sources": SRC}},
        "size": {"type": "array", "maxItems": 2, "description": "크기를 바꾸는 것: 그 사건 자체에 붙은 요인만(이미 반영된 기대·다음 전망·경영진 이슈). 같은 날 다른 뉴스 금지. 줄이는 틀 '다만 [요인] 때문에 크게 [오르기/내리기] 어려울 수 있다고 봐요' / 키우는 틀 '게다가 [요인] 때문에 더 크게 [오를/내릴] 수 있다고 봐요'. 숫자 크기·쪽 말·▲▼ 금지, 서로 다른 매체 2개",
                 "items": {"type": "object", "additionalProperties": False, "required": ["text", "sources"], "properties": {"text": {"type": "string"}, "sources": SRC}}},
        "watch": {"type": ["object", "null"], "additionalProperties": False, "required": ["key", "high", "low", "expect", "expect_sources"], "description": "다음에 볼 지표 하나. 사건과 같은 나라 지표(한국 사건 → 한국 지표). 시나리오 a = high, b = low",
                  "properties": {"key": {"type": "string", "enum": sorted({**json.loads((HERE.parent / 'config' / 'graph.json').read_text(encoding='utf-8')).get('watch_series', {})})},
                                 "high": {"type": "string", "description": "예상보다 높게 나오면 → 어떤 방향인지 (쪽 말 금지). 예: '물가 부담이 이어지는 쪽'"},
                                 "low": {"type": "string", "description": "낮게 나오면 → 예: '오름세가 둔화되는 쪽'"},
                                 "expect": {"type": ["string", "null"], "description": "다음 발표 예상치(예: '2.6%'). 서로 다른 매체 2개에 같은 값일 때만, 없으면 null"},
                                 "expect_sources": SRC}},
        "id": {"type": "string"}, "date": {"type": "string", "description": "사건 날짜, 한국 날짜 YYYY-MM-DD (발표·결정이 있었던/있을 날)"}, "type": {"type": "string", "enum": CFG["event_types"]}, "chip": {"type": "string"}, "head": {"type": "string"},
        "kind": {"type": "string", "enum": ["done", "upcoming"]}, "schedule_code": {"type": ["string", "null"]},
        "expect": {"type": ["string", "null"], "enum": ["예상보다 높음", "예상대로", "예상보다 낮음", None]},
        "actual_src": {"type": ["string", "null"]}, "expect_src": {"type": ["string", "null"]}, "spread": {"type": "boolean"},
        "real": {"type": "array", "items": STATE}, "realPath": {"type": "array", "items": EDGE}, "next": {"type": "array", "items": NODE},
        "opts": {"type": "object", "properties": {"a": OPT, "b": OPT}, "required": ["a", "b"], "additionalProperties": False},
        "judge_keys": {"type": "array", "items": {"type": "object", "properties": {"key": {"type": "string"}, "side_if_up": SIDE}, "required": ["key", "side_if_up"], "additionalProperties": False}, "maxItems": 3},
        "confirm": {"type": "array", "maxItems": 2, "items": {"type": "object", "properties": {"label": {"type": "string", "enum": ["먼저", "최종"]}, "what": {"type": "string"}, "when": {"type": "string"}}, "required": ["label", "what", "when"], "additionalProperties": False}},
        "sources": SRC}}}}}

def structure(today, notes, facts, upcoming):
    prompt = f"""아래 조사 메모와 수집값으로 오늘 화면 데이터를 만들어줘. 정해진 형태로만.
{RULES}
{graph_text()}
- 사건은 최대 3개: 오늘 결과 나온 것 먼저, 그다음 곧 발표(7일 안). 발표 예정 목록에 있는 건 schedule_code를 그대로 쓴다.
- 시나리오 a는 왼쪽(◀, 보통 낮은 쪽/좋은 쪽), b는 오른쪽(▶). label은 '예상보다 높으면'처럼 짧게. out은 한 구절, 없으면 빈 문자열.
- judge_keys: 판단할 때 같이 볼 지표 최대 3개, 수집값의 key({', '.join(facts['series'])}) 중에서. side_if_up = 그 지표가 오르면 보통 어느 쪽인지.
- 문장에 숫자를 쓰지 마라. 숫자는 시스템이 수집값으로 채운다.
- 관심사 3개 모두: 언급 정도, 걱정하는 방향, 대표 기사 URL 3개 이상.
발표 예정: {json.dumps(upcoming, ensure_ascii=False)}
조사 메모:
{notes}"""
    r = ask([{"role": "user", "content": prompt}], output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}})
    return json.loads(next(b.text for b in r.content if b.type == "text"))

def generate(today, facts, upcoming):
    notes = research(today, facts, upcoming)
    draft = structure(today, notes, facts, upcoming)
    draft["_notes"] = notes
    return draft

if __name__ == "__main__":   # 예약 실행용: 형식(JSON Schema)·규칙을 파일로 내보냄
    out = HERE.parent / "config"
    (out / "draft-schema.json").write_text(json.dumps(SCHEMA, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "draft-rules.md").write_text(RULES + "\n\n" + graph_text() + "\n", encoding="utf-8")
    print("config/draft-schema.json, config/draft-rules.md")
