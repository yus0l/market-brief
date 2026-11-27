"""AI 생성물 검사기 — 02-UX §5 + 기획 v4 §2·v4.1·v4.3 규칙을 코드로.
통과 못 한 항목은 그 항목만 빼고(화면: "데이터가 들어오면 보여드려요"), 이유를 로그에 남긴다."""
import re, json, pathlib
CFG = json.loads((pathlib.Path(__file__).resolve().parent.parent / "config" / "graph.json").read_text(encoding="utf-8"))
EDGES = {(a, b) for a, b, *r in CFG["edges"]} | {(b, a) for a, b, *r in CFG["edges"] if r == ["both"]}
NODES = set(CFG["nodes"])
# 금지어: 종목 매매 권유, 단정적 예측, "판정"(서비스는 판단하지 않는다 — UX 11/26)
BANNED = ["매수", "매도", "사세요", "파세요", "될 거예요", "될 것", "유력", "확실", "반드시", "판정", "추천 종목"]
TICKER_WORDS = ["삼성전자", "SK하이닉스", "엔비디아 주식", "테슬라 주식", "애플 주식"]   # 종목명 (사건 이름 "엔비디아 실적"은 허용)
EXPECT = {"예상보다 높음", "예상대로", "예상보다 낮음"}
ISO = re.compile(r"\d{4}-\d{2}-\d{2}(?:T[\d:+]+)?")   # 일정 날짜(YYYY-MM-DD)는 숫자 검사 제외
NUM = re.compile(r"(?<![\d/])[-+−]?\d[\d,]*(?:\.\d+)?(?![\d/]|년|개월|월|일|순위|단계|명|개|위)")   # 날짜·기간·순서 표현은 제외

def texts(obj):
    if isinstance(obj, str): yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k not in ("url", "id", "sources"): yield from texts(v)
    elif isinstance(obj, list):
        for v in obj: yield from texts(v)

def check_words(obj, where, errs):
    for t in texts(obj):
        for w in BANNED + TICKER_WORDS:
            if w in t: errs.append(f"{where}: 금지어 '{w}' — {t[:40]}")

def check_numbers(obj, allowed, where, errs):
    """문장 속 숫자는 수집값(facts)·출처 있는 값 목록에 있어야 한다."""
    for t in texts(obj):
        for n in NUM.findall(ISO.sub("", t)):
            k = n.replace(",", "").replace("−", "-").lstrip("+")
            if len(k.strip("-.")) <= 1: continue          # 1자리(1순위, 2단계 등)는 제외
            if k not in allowed: errs.append(f"{where}: 출처 없는 숫자 {n} — {t[:40]}")

def check_paths(e, errs):
    for name, path in [("realPath", e.get("realPath", []))] + [(f"opts.{k}.path", o.get("path", [])) for k, o in e.get("opts", {}).items()]:
        for a, b in path:
            if (a, b) not in EDGES: errs.append(f"{e['id']} {name}: 기본 관계 밖의 선 {a}→{b}")
    for k in list(e.get("real", {})) + [n for o in e.get("opts", {}).values() for n in o.get("state", {})] + e.get("next", []):
        if k not in NODES: errs.append(f"{e['id']}: 없는 칸 {k}")

REQ = {"id": str, "chip": str, "head": str, "kind": str, "opts": dict, "real": dict, "realPath": list, "sources": list}
def check_shape(e, errs):
    """형식 검사 — API 구조화 출력 없이(예약 실행 등) 만든 draft도 같은 기준으로 거른다."""
    for k, t in REQ.items():
        if not isinstance(e.get(k), t): errs.append(f"{e.get('id', '?')}: 형식 오류 '{k}'"); return False
    if e["kind"] not in ("done", "upcoming"): errs.append(f"{e['id']}: kind 값 오류"); return False
    for k, o in e["opts"].items():
        if not (isinstance(o.get("path"), list) and isinstance(o.get("state"), dict) and isinstance(o.get("cond"), list) and isinstance(o.get("label"), str)):
            errs.append(f"{e['id']} opts.{k}: 형식 오류"); return False
        if any(not (isinstance(c, list) and c and isinstance(c[0], str)) for c in o["cond"]): errs.append(f"{e['id']} opts.{k}: 조건 칩 형식 오류"); return False
    return True

def check_event(e, allowed_nums, today, errs):
    before = len(errs)
    if not check_shape(e, errs): return False
    if len(e.get("sources", [])) < 2: errs.append(f"{e['id']}: 출처 URL 2개 미만")
    if set(e.get("opts", {})) != {"a", "b"}: errs.append(f"{e['id']}: 시나리오 2개가 아님")
    for k, o in e.get("opts", {}).items():
        if not 1 <= len(o.get("cond", [])) <= 3: errs.append(f"{e['id']} opts.{k}: 조건 칩 1~3개 아님")
    r = e.get("result")
    if r and r.get("expect") and r["expect"] not in EXPECT: errs.append(f"{e['id']}: 예상 대비 문구가 3개 중 하나가 아님")
    if r and r.get("expect") and not (r.get("actual_src") and r.get("expect_src")): errs.append(f"{e['id']}: 예상 대비에 실제값·예상치 출처가 둘 다 있어야 함")
    check_paths(e, errs); check_words(e, e["id"], errs); check_numbers(e, allowed_nums, e["id"], errs)
    return len(errs) == before

TIMEWORD = re.compile(r"어제|오늘|내일|그제|요즘|최근|이번 주|지난주|\d+일 뒤|\d{1,2}/\d{1,2}")
def bad_words(t): return [w for w in BANNED if w in t]
def nums_ok(t, allowed): return all(n.replace(",", "").lstrip("+-−") in allowed for n in NUM.findall(ISO.sub("", t)))

def check_interests(ints, errs, allowed=frozenset()):
    """02-UX "관심사 칩 = 오늘의 이슈 순위 + 박스 문장 형식". 계기·사실 문장은 틀리면 그 부분만 빼고, 보는 것 문장이 틀리면 관심사를 뺀다."""
    ok = []
    for x in ints:
        k = x["key"]; x = dict(x, reason=dict(x.get("reason") or {}))
        if k not in CFG["interests"]: errs.append(f"관심사 후보 밖: {k}"); continue
        if x["reason"].get("type") == "mention" and len(x.get("sources", [])) < 3:
            errs.append(f"관심사 {k}: 언급량 근거 기사 URL 3개 미만"); continue
        w = x.get("watch") or ""
        if not (w.startswith("시장은") and w.rstrip(". ").endswith("보고 있어요")) or len(w) > 45 or bad_words(w) or re.search(r"호재|악재|걱정", w) or not nums_ok(w, allowed):
            errs.append(f"관심사 {k}: 둘째 문장(시장이 보는 것) 규칙 위반 — {w}"); continue
        lb = x["reason"].get("label")
        if lb and (len(lb) > 12 or re.search(r"[▲▼]|실시간|언급", lb) or bad_words(lb)
                   or (x["reason"].get("type") == "mention" and len(x.get("trigger_sources") or []) < 2)):
            errs.append(f"관심사 {k}: 계기 '{lb}' 빠짐(출처 2개 미만·길이·금지 글자)"); x["reason"]["label"] = None
        f = x.get("fact")
        if f and (not TIMEWORD.search(f) or not x.get("fact_sources") or len(f) > 45 or bad_words(f) or re.search(r"호재|악재", f) or not nums_ok(f, allowed)):
            errs.append(f"관심사 {k}: 첫 문장(사실) 빠짐(날짜 말·출처·길이·숫자) — {f}"); f = None
        x["fact"] = f; x["sentence"] = " ".join(t for t in (f, w) if t)
        ok.append(x)
    return ok

def sub_for(d, today):
    """칩 날짜 글자 = 사건 날짜 "11/26" (today 인자는 호환용)."""
    import datetime as dt
    d, t = dt.date.fromisoformat(d[:10]), dt.date.fromisoformat(today[:10]); n = (d - t).days
    return f"{d.month}/{d.day}"   # 날짜만 (02-UX 11/27: 오늘·어제·D-n 안 씀)

def check_sub(e, today, errs):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(e.get("date") or "")): errs.append(f"{e.get('id')}: 사건 날짜(date) 없음"); return False
    if e.get("sub") != sub_for(e["date"], today): errs.append(f"{e['id']}: 날짜 글자 '{e.get('sub')}'가 date {e['date']}와 안 맞음"); return False
    return True

def validate(today, facts):
    """today(생성본)를 검사해서 통과한 것만 남긴 사본과 오류 목록을 돌려준다."""
    errs = []
    allowed = {str(v).replace(",", "") for v in facts.get("allowed_numbers", [])}
    out = dict(today)
    out["interests"] = check_interests(today.get("interests", []), errs, allowed)
    out["events"] = [e for e in today.get("events", []) if check_sub(e, today.get("date"), errs) and check_event(e, allowed, today.get("date"), errs)][:3]
    return out, errs

if __name__ == "__main__":
    import sys
    t = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    f = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")) if len(sys.argv) > 2 else {}
    o, e = validate(t, f)
    print(f"통과 사건 {len(o['events'])}/{len(t.get('events', []))}, 관심사 {len(o['interests'])}/{len(t.get('interests', []))}")
    print("\n".join(e) or "오류 없음")
