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
NUM = re.compile(r"(?<![\d/])[-+−]?\d[\d,]*(?:\.\d+)?(?![\d/]|년|개월|월|일|주|순위|단계|명|개|위)")   # 날짜·기간·순서 표현은 제외

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

TIMEWORD = re.compile(r"\d{1,2}/\d{1,2}")                       # 시점은 날짜로 (명세 §3-6 ④-1)
VAGUE = re.compile(r"이번 주|최근|\d+일 뒤|곧|요즘|어제|내일|지난주")   # 시점 금지어 (§3-6 ⑥)
MVERB = {"M1": ("지켜보고 있어요",), "M2": ("걱정하고 있어요", "기대하고 있어요", "보고 있어요")}   # B3는 M3(반응했어요) 안 씀
SCHED_DATES = None
def verified_dates():
    global SCHED_DATES
    if SCHED_DATES is None:
        SCHED_DATES = set()
        for p in (pathlib.Path(__file__).resolve().parent.parent / "config").glob("schedule-*.json"):
            for r in json.loads(p.read_text(encoding="utf-8"))["events"]:
                if r.get("verified"):
                    import datetime as _d; d = _d.date.fromisoformat((r.get("kst") or r["date"])[:10]); SCHED_DATES.add(f"{d.month}/{d.day}")
    return SCHED_DATES
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
        # 시장 칸 (§3-6 ②·⑥): 틀리면 시장 칸만 빼고 사실 한 문장으로
        w = (x.get("watch") or "").strip()
        if w:
            mt = next((t for t, vs in MVERB.items() if any(w.rstrip(". ").endswith(v) for v in vs)), None)
            why = ("'시장은'으로 시작 안 함" if not w.startswith("시장은") else "동사가 M1·M2 목록 밖" if not mt
                   else "시점 금지어" if VAGUE.search(w) else "금지어·호재/악재" if bad_words(w) or re.search(r"호재|악재", w)
                   else "출처 없는 숫자" if not nums_ok(w, allowed)
                   else "M2인데 기사 URL 2개 미만" if mt == "M2" and len(x.get("market_sources") or []) < 2
                   else "M1인데 일정표 공식 날짜 없음" if mt == "M1" and not any(d in verified_dates() for d in TIMEWORD.findall(w)) else "")
            side = x.get("upSide") if x.get("dir", "up") == "up" else {"good": "bad", "bad": "good"}.get(x.get("upSide"))
            if not why and ("걱정하고" in w and side == "good" or "기대하고" in w and side == "bad"): why = "걱정/기대가 쪽과 안 맞음"
            if why: errs.append(f"관심사 {k}: 시장 칸 빠짐({why}) — {w}"); w = ""
            elif len(w) > 40: errs.append(f"[경고] 관심사 {k}: 시장 칸 40자 초과 — {w}")
        x["watch"] = w or None
        lb = x["reason"].get("label")
        if lb and (len(lb) > 12 or re.search(r"[▲▼]|실시간|언급", lb) or bad_words(lb)
                   or (x["reason"].get("type") == "mention" and len(x.get("trigger_sources") or []) < 2)):
            errs.append(f"관심사 {k}: 계기 '{lb}' 빠짐(출처 2개 미만·길이·금지 글자)"); x["reason"]["label"] = None
        f = x.get("fact")
        if f and re.search(r"발표가 있어요|발표 예정|발표돼요", f): errs.append(f"관심사 {k}: 사실 칸이 발표 예정 문장(S2) — B3 첫 문장 금지"); f = None
        if f and (not TIMEWORD.search(f) or VAGUE.search(f) or not x.get("fact_sources") or bad_words(f) or re.search(r"호재|악재", f) or not nums_ok(f, allowed)):
            errs.append(f"관심사 {k}: 사실 칸 빠짐(날짜 M/D·시점 금지어·출처·숫자) — {f}"); f = None
        elif f and len(f) > 40: errs.append(f"[경고] 관심사 {k}: 사실 칸 40자 초과 — {f}")
        if f and w and watch_terms(f) & watch_terms(w): errs.append(f"관심사 {k}: 두 문장이 같은 지표 반복 — 시장 칸 뺌"); w = ""
        x["fact"] = f; x["watch"] = w or None; x["sentence"] = " ".join(t for t in (f, w) if t)
        if x["sentence"]: ok.append(x)
        else: errs.append(f"관심사 {k}: 남은 문장이 없어 뺌")
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

WS = CFG.get("watch_series", {})
def check_watch(e, errs):
    """02-UX 검사 3규칙: ① 시나리오 조건·결과 확인 첫 단계 = watch 지표 ② 지표 나라 = 사건 나라 ③ 시나리오가 이미 일어난 방향을 뒤집지 않음."""
    w = e.get("watch")
    if not w: return True
    name = w.get("name", "")
    for k, o in (e.get("opts") or {}).items():
        if not o.get("cond") or name not in o["cond"][0][0]: errs.append(f"{e['id']} opts.{k}: 조건 첫 칸이 보는 지표({name})가 아님"); return False
    if not e.get("confirm") or name not in e["confirm"][0].get("what", ""): errs.append(f"{e['id']}: 결과 확인 첫 단계가 보는 지표가 아님"); return False
    q = e.get("question")
    if q and w.get("dir") and ("더 오를" in q and w["dir"] == "down" or "다시 오를" in q and w["dir"] == "up"): q = None; errs.append(f"{e['id']}: 질문형 방향 말이 최근 값 방향과 안 맞음 → 사건 제목으로"); e["question"] = None
    if q and (w.get("name", "") not in q and w.get("short", "") not in q or VAGUE.search(q)): errs.append(f"{e['id']}: 질문형 제목에 지표 이름 없음·시점 금지어 → 사건 제목으로"); e["question"] = None
    real = e.get("real") or {}
    ctry = {m for v in real.values() for m in ("us", "kr") if v.get(m)}
    wc = WS.get(w.get("key"), {}).get("country")
    if ctry == {"kr"} and wc == "us" or ctry == {"us"} and wc == "kr": errs.append(f"{e['id']}: 보는 지표 나라({wc})가 사건 나라와 다름"); return False
    for k, o in (e.get("opts") or {}).items():
        if e.get("actual"): break
        for node, st in (o.get("state") or {}).items():
            r = real.get(node)
            if r and any(st.get(m) and r.get(m) and st[m] != r[m] for m in ("dir", "us", "kr")):
                errs.append(f"{e['id']} opts.{k}: 이미 일어난 {node} 방향을 뒤집음"); return False
    return True

def watch_terms(t):
    """문장에 나온 지표 키 (별칭 기준)."""
    return {k for k, c in WS.items() for a in c.get("alias", []) if a in t}

SER_OF = {"US_CPI": "us_cpi", "US_PPI": "us_ppi", "KR_CPI": "kr_cpi", "US_JOBS": "us_jobs"}   # 지표형 발표 → 수집 시리즈
def code_m1(x, today, facts):
    """관심사 관련 발표 중 가장 가까운 공식(verified) 발표 30일 안 → "시장은 [M/D] [발표]를 지켜보고 있어요".
    지표면 최근 값 기준 "다시/더 오를지"(고용은 늘지). 사실 칸과 같은 지표면 다음 후보. 없으면 None."""
    import datetime as _d
    t = _d.date.fromisoformat(today[:10]); rows = []
    for p in (pathlib.Path(__file__).resolve().parent.parent / "config").glob("schedule-*.json"):
        rows += json.loads(p.read_text(encoding="utf-8"))["events"]
    codes = CFG["interests"][x["key"]].get("events", [])
    cand = sorted((r for r in rows if r["code"] in codes and r.get("verified")), key=lambda r: (r.get("kst") or r["date"])[:10])
    for r in cand:
        d = _d.date.fromisoformat((r.get("kst") or r["date"])[:10]); n = (d - t).days
        if n < 0: continue
        if n > 30: break
        nm = {"BOK": "금통위 금리 결정", "FOMC": "FOMC 금리 결정"}.get(r["code"], r["name"])
        sk = SER_OF.get(r["code"]); s = (facts.get("series") or {}).get(sk) if sk else None
        if s:
            ch = (s["yoy"] - s["yoy_prev"]) if "yoy" in s else (s["value"] - s["prev"])
            verb = ("늘지" if sk == "us_jobs" else "오를지"); adv = "다시 " if ch < 0 else "더 " if ch > 0 else ""
            jo = "이" if (ord(nm[-1]) - 0xAC00) % 28 and 0xAC00 <= ord(nm[-1]) <= 0xD7A3 else "가"
            m = f"시장은 {d.month}/{d.day} {nm}{jo} {adv}{verb} 지켜보고 있어요"
        else:
            jo = "을" if (ord(nm[-1]) - 0xAC00) % 28 and 0xAC00 <= ord(nm[-1]) <= 0xD7A3 else "를"
            m = f"시장은 {d.month}/{d.day} {nm}{jo} 지켜보고 있어요"
        if watch_terms(x.get("fact") or "") & watch_terms(m) or nm in (x.get("fact") or ""): continue   # 두 문장 같은 지표 반복 금지
        code_m1.info = {"date": d.isoformat(), "md": f"{d.month}/{d.day}", "name": nm, "code": r["code"], "series": sk}   # B ④ 다음 발표
        return m
    return None

def ndoms(srcs):
    from urllib.parse import urlparse
    return len({urlparse(x.get("url", "")).netloc.removeprefix("www.") for x in srcs or []} - {""})
SIDEWORD = re.compile(r"호재|악재|쪽|▲|▼")
def check_types(e, allowed, errs):
    """명세 §3-10: T2 갈래 근거, 앞으로 한 줄, 크기 요인. 틀리면 그 칸만 빼고, T2 갈래 근거가 없으면 사건을 고르지 않음."""
    i = e.get("id")
    if e.get("etype") == "T2":
        t = e.get("t2") or {}
        if not t or any(ndoms((t.get(k) or {}).get("view_sources")) < 2 for k in ("a", "b")):
            errs.append(f"{i}: T2인데 갈래별 서로 다른 매체 2개 미만 → 사건 고르지 않음"); return False
        for k in ("a", "b"):
            if SIDEWORD.search(t[k].get("short", "") + t[k].get("view", "")) or re.search(r"^시장은", t[k].get("view", "")):
                errs.append(f"{i}: T2 갈래 {k} 이름·기사 견해에 쪽 말·'시장은' → 사건 고르지 않음"); return False
    o = e.get("outlook")
    if o:
        why = ("금리 결정 예상대로가 아님" if not (e.get("result") or {}).get("expect") == "예상대로" else "서로 다른 매체 2개 미만" if ndoms(o.get("sources")) < 2
               else "쪽 말·▲▼" if SIDEWORD.search(o.get("text", "")) else "출처 없는 숫자" if not nums_ok(o.get("text", ""), allowed) else "")
        if why: errs.append(f"{i}: 앞으로 한 줄 빠짐({why})"); e["outlook"] = None
    keep = []
    for z in e.get("size") or []:
        t = z.get("text", "")
        why = ("'다만/게다가'로 시작 안 함" if not re.match(r"^(다만|게다가) ", t) else "틀 밖(…수 있다고 봐요)" if not t.rstrip(". ").endswith("수 있다고 봐요")
               else "숫자 크기 금지" if NUM.search(ISO.sub("", t)) else "쪽 말·▲▼" if SIDEWORD.search(t) else "서로 다른 매체 2개 미만" if ndoms(z.get("sources")) < 2 else "")
        if why: errs.append(f"{i}: 크기 요인 빠짐({why}) — {t}")
        else: keep.append(dict(z, n=ndoms(z.get("sources"))))
    e["size"] = keep[:2]
    return True

def validate(today, facts):
    """today(생성본)를 검사해서 통과한 것만 남긴 사본과 오류 목록을 돌려준다."""
    errs = []
    allowed = {str(v).replace(",", "") for v in facts.get("allowed_numbers", [])}
    from urllib.parse import urlparse
    for n in today.get("extra_numbers") or []:          # 수집 안 되는 숫자: 서로 다른 매체 2개에 같은 숫자 (명세 §3-6 ⑤-2)
        doms = {urlparse(s.get("url", "")).netloc.removeprefix("www.") for s in n.get("sources") or []} - {""}
        if len(doms) >= 2: allowed.add(str(n["value"]).replace(",", "").lstrip("+-−").rstrip("%"))
        else: errs.append(f"숫자 {n.get('value')}: 서로 다른 매체 2개 미만이라 허용 안 함")
    out = dict(today)
    out["interests"] = check_interests(today.get("interests", []), errs, allowed)
    out["events"] = [e for e in today.get("events", []) if (e.get("watchChip") or check_sub(e, today.get("date"), errs)) and check_watch(e, errs) and check_event(e, allowed, today.get("date"), errs)][:3]
    out["events"] = [e for e in out["events"] if check_types(e, allowed, errs)]
    KT = json.loads((pathlib.Path(__file__).resolve().parent.parent / "config" / "sidetags.json").read_text(encoding="utf-8"))
    for e in out["events"]:                                   # §3-11: K 번호가 표 안인지만
        if e.get("ktype") and e["ktype"] not in KT: errs.append(f"{e.get('id')}: ktype {e['ktype']} 표에 없음 — 태그 없음"); e["ktype"] = None
    t2 = [e for e in out["events"] if e.get("etype") == "T2"]
    if len(t2) > 1: out["events"] = [e for e in out["events"] if e.get("etype") != "T2" or e is t2[0]]; errs.append("T2 사건은 하루 1개만 — 나머지 뺌")
    # 관심사 둘째 문장 지표 ⊂ 사건 watch·같이 볼 것·7일 안 발표 (02-UX)
    ok_keys = {e["watch"]["key"] for e in out["events"] if e.get("watch")} | set(today.get("judge_keys_all", [])) | set(today.get("upcoming_keys", []))
    keep = []
    for x in out["interests"]:
        if x.get("watch") and x.get("market_type") == "M2":
            bad = watch_terms(x["watch"]) - ok_keys
            if bad: errs.append(f"관심사 {x['key']}: 시장 칸(M2) 지표 {sorted(bad)}가 화면의 보는 지표·같이 볼 것에 없음"); x = dict(x, watch=None)
        else: x = dict(x, watch=None)                       # AI M1은 쓰지 않음 → 아래에서 코드가 채움
        code_m1.info = None; m1 = code_m1(x, today.get("date"), facts) if x.get("fact") else None
        x = dict(x, next_rel=code_m1.info)                    # B ④: 관심사의 다음 공식 발표
        if x.get("fact") and not x.get("watch"):              # M2가 없거나 빠지면 코드 M1 (명세 §3-6 ② PM 11/27)
            x = dict(x, watch=m1, market_type="M1" if m1 else None)
        x["sentence"] = " ".join(t for t in (x.get("fact"), x.get("watch")) if t)
        if x.get("fact"): keep.append(x)                       # 이유 문장(사실 칸)이 없으면 셀렉트에서 숨김 (명세 §3-3)
        else: errs.append(f"관심사 {x['key']}: 이유 문장 없음 → 숨김")
    for i, x in enumerate(keep): x["rank"] = i + 1   # 빠진 관심사가 있으면 순위 다시 매김
    out["interests"] = keep
    return out, errs

if __name__ == "__main__":
    import sys
    t = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    f = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")) if len(sys.argv) > 2 else {}
    o, e = validate(t, f)
    print(f"통과 사건 {len(o['events'])}/{len(t.get('events', []))}, 관심사 {len(o['interests'])}/{len(t.get('interests', []))}")
    print("\n".join(e) or "오류 없음")
