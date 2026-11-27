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
- 서비스는 호재·악재를 판단하지 않는다. "보통 ○○ 쪽"까지만. '판정' '매수' '매도' '유력' '확실' '~될 거예요' 금지. 종목명 금지(사건 이름 '엔비디아 실적'은 가능).
- 모든 사실·수치에는 출처 URL. 못 찾으면 null로 두고 지어내지 않는다.
- 예상 대비는 '예상보다 높음' / '예상대로' / '예상보다 낮음' 중 하나. 실제값·예상치 출처가 둘 다 있어야 한다. 조사가 갈리면 다수 의견 + spread=true.
- 경로는 아래 기본 관계 목록의 선만 쓴다. 새 연결을 만들지 않는다.
- 시나리오 조건은 확인 가능한 지표·일정만('투자 심리가 회복되면' 같은 것 금지).
- '물가 ▼'는 '물가 오름세 둔화'로 쓴다."""

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
3. 최근 3일 뉴스에서 '물가', '경기', '금리' 중 시장이 무엇을 가장 많이 걱정하는지: 후보별 대표 기사 URL 3개 이상과 대략적 언급 정도(많음/보통/적음). 각 관심사가 지금 오르는 쪽 걱정인지 내리는 쪽 걱정인지.
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
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["interests", "events"], "properties": {
  "interests": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["key", "mention", "dir", "sources"], "properties": {
      "key": {"type": "string", "enum": list(CFG["interests"])}, "mention": {"type": "string", "enum": ["많음", "보통", "적음"]},
      "dir": {"type": "string", "enum": ["up", "down"]}, "sources": SRC}}},
  "events": {"type": "array", "maxItems": 3, "items": {"type": "object", "additionalProperties": False,
      "required": ["id", "type", "chip", "head", "kind", "schedule_code", "expect", "actual_src", "expect_src", "spread", "real", "realPath", "next", "opts", "judge_keys", "confirm", "sources"],
      "properties": {
        "id": {"type": "string"}, "type": {"type": "string", "enum": CFG["event_types"]}, "chip": {"type": "string"}, "head": {"type": "string"},
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
