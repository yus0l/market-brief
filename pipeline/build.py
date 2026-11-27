"""매일 07:30 KST 실행: 수집 → AI 생성 → 조립 → 검사 → web/today.json 공개(08:00).
  python3 pipeline/build.py            # 실제 실행 (키 필요)
  python3 pipeline/build.py --draft X  # AI 단계 건너뛰고 저장된 draft로 조립만 (테스트)"""
import json, re, sys, pathlib, datetime as dt
HERE = pathlib.Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from collect import collect, KST, FRED, ECOS
NAMES = {k: v[1] for k, v in {**FRED, **ECOS}.items()}
from validate import validate, sub_for
CFG = json.loads((ROOT / "config" / "graph.json").read_text(encoding="utf-8"))
KT = {k: v for k, v in json.loads((ROOT / "config" / "sidetags.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}
SECT = json.loads((ROOT / "config" / "sectors.json").read_text(encoding="utf-8"))
ARCH = ROOT / "data" / "archive"; WEB = ROOT / "web"
EVENT_SERIES = {"BOK": "kr_base", "US_JOBS": "us_jobs"}            # 결과 숫자를 수집값으로 채울 수 있는 발표

def load_schedule():
    ev = []
    for p in (ROOT / "config").glob("schedule-*.json"):
        ev += json.loads(p.read_text(encoding="utf-8"))["events"]
    return ev

def upcoming(schedule, today, days=7):
    """7일 안, 공식 확인된 일정만 (기획 v4.2: '확인 필요'는 D-day로 안 보여줌)."""
    out = []
    for e in schedule:
        d = dt.date.fromisoformat((e.get("kst") or e["date"])[:10]); n = (d - today).days   # D-day는 한국 날짜 기준
        if e["verified"] and 0 <= n <= days: out.append(dict(e, dday=n))
    return sorted(out, key=lambda e: e["dday"])

def rank_interests(draft_ints, upc):
    """기획 v4.3: 최근 3일 언급량 순 → 관련 주요 발표가 7일 안이면 한 단계 올림 → 같으면 가까운 발표 우선."""
    score = {"많음": 3, "보통": 2, "적음": 1}
    items = []
    for x in draft_ints:
        c = CFG["interests"][x["key"]]
        ev = next((u for u in upc if u["code"] in c["events"]), None) if len(x.get("sources") or []) >= 3 else None   # 발표 가산은 언급 인정(URL 3개+) 관심사만 (명세 §3-3)
        items.append(dict(x, s=score[x["mention"]], ev=ev))
    items = [x for x in items if len(x.get("sources") or []) >= 3 and (x["mention"] != "적음" or x["ev"])]   # 언급 인정 안 되면 숨김
    items.sort(key=lambda x: (-x["s"], x["ev"]["dday"] if x["ev"] else 99))
    for i in range(1, len(items)):                                             # 발표 가산: 한 단계 올림
        if items[i]["ev"] and not items[i - 1]["ev"]: items[i - 1], items[i] = items[i], items[i - 1]
    out = []
    for i, x in enumerate(items):
        c = CFG["interests"][x["key"]]; boosted = x["ev"] and (i == 0 or items[i - 1]["s"] >= x["s"]) and x["s"] < max(y["s"] for y in items)
        # 칩 아랫줄 계기 (02-UX "오늘의 이슈 순위"): 앞둔 발표면 코드가 "미국 CPI D-3", 아니면 AI 계기(출처 2개↑, 검사기가 확인)
        if boosted:
            n = x["ev"]["dday"]
            reason = {"type": "event", "label": f"{x['ev']['name']} {md(x['ev'].get('kst') or x['ev']['date'])}"}   # "미국 CPI 12/10"
            fact, fsrc = x.get("fact"), x.get("fact_sources") or []   # B3 첫 문장 = 왜 지금 보는지(S1·S3). S2 발표 예정 문장은 금지 (명세 §3-6 ③)
        else:
            reason = {"type": "mention", "label": x.get("trigger")}
            fact, fsrc = x.get("fact"), x.get("fact_sources") or []
        out.append({"key": x["key"], "node": c["node"], "name": c["name"], "rank": i + 1, "reason": reason, "upSide": c["upSide"],
                    "fact": fact, "watch": x.get("watch"), "market_type": x.get("market_type"), "market_sources": x.get("market_sources") or [], "moves": x.get("moves") or [], "sentence": " ".join(t for t in (fact, x.get("watch")) if t),
                    "fact_sources": fsrc, "trigger_sources": x.get("trigger_sources") or [],
                    "explain": c["explain"], "sources": x["sources"]})
    return out

def st_dict(arr):
    d = {}
    for s in arr:
        v = {k: s[k] for k in ("dir", "us", "kr") if s.get(k)}
        if v: d[s["node"]] = v
    return d

def mdd(d):   # FRED "2026-11-24" · ECOS "20261126" / "202610" → "11/24" · "10월"
    d = str(d).replace("-", "")
    return f"{int(d[4:6])}/{int(d[6:8])}" if len(d) >= 8 else f"{int(d[4:6])}월"

UP_SIDE = {"stock": "good", "job": "good", "rate": "bad", "cpi": "bad", "fx": "bad", "vix": "bad", "oil": "bad"}
def default_judge(facts, e):
    """AI가 판단 재료 지표를 안 골랐을 때: 사건이 닿는 칸의 수집 지표에서 최대 3개 (한국 사건이면 한국 지표 먼저)."""
    nodes = [r["node"] for r in e["real"]] + list(e.get("next") or [])
    kr = any(r.get("kr") for r in e["real"])
    keys = sorted((k for k, v in facts["series"].items() if v["node"] in nodes), key=lambda k: (kr != k.startswith(("kr_", "usdkrw", "ktb", "kospi")), nodes.index(facts["series"][k]["node"])))
    return [{"key": k, "side_if_up": UP_SIDE.get(facts["series"][k]["node"], "bad")} for k in keys[:3]]

DAILY = {"us_10y", "vix", "wti", "sp500", "usdkrw", "ktb3y", "kospi"}   # 나머지(금리 결정·월간 지표)는 "직전보다"
def judge_row(f, key, side_if_up):
    s = f["series"].get(key)
    if not s: return [NAMES.get(key, key), None, None, None]
    ch = s["value"] - s["prev"]; d = "up" if ch > 0 else "down" if ch < 0 else None
    side = side_if_up if d == "up" else ({"good": "bad", "bad": "good"}.get(side_if_up) if d == "down" else None)
    unit = s["unit"] if s["unit"] in ("%", "원") else ""
    chs = f"{ch:+.2f}%p" if unit == "%" else f"{(s['value'] / s['prev'] - 1) * 100:+.2f}%"
    return [s["name"], d, f"{s['value']:,.2f}{unit} · {'전일보다' if key in DAILY else '직전보다'} {chs} ({mdd(s['date'])} 기준)", side]

WS = CFG.get("watch_series", {})

def sdate(s):   # "20261126"·"2026-11-24" → date (월간 "202610"은 None)
    d = s["date"]
    if len(d) == 8: return dt.date(int(d[:4]), int(d[4:6]), int(d[6:]))
    if len(d) == 10: return dt.date.fromisoformat(d)
    return None
def next_wd(d):
    d += dt.timedelta(days=1)
    while d.weekday() >= 5: d += dt.timedelta(days=1)
    return d
# 명세 §3-8 ② v2: 사건 뒤 "가격"만 센다. (key, 묶음, 오르면 쪽, 가중치)
PRICE = {"kr": [("ktb3y", "rate", "bad", 1), ("kospi", "stock", "good", 1), ("usdkrw", "fx", "bad", .5)],
         "us": [("us_10y", "rate", "bad", 1), ("sp500", "stock", "good", 1), ("vix", "stock", "bad", 1)]}
def price_reaction(country, edate, facts, status, upcoming_ev):
    """E10 행 + E12 막대. 기간 = 사건 당일 + 다음 1거래일. 변화 0·기간 밖·휴장은 안 셈."""
    rows, g = [], {}
    win = (edate, next_wd(edate))
    closed = (status.get("closed") or {}).get(country)
    for key, grp, up, wt in PRICE[country]:
        s = facts["series"].get(key)
        if not s: continue
        r = judge_row(facts, key, up); d = sdate(s)
        row = {"name": r[0], "dir": r[1], "value": r[2], "side": r[3], "weak": wt < 1, "counted": False, "note": None}
        if upcoming_ev: row["note"] = None
        elif closed: row["note"] = "휴장"
        elif not d or not (win[0] <= d <= win[1]): row["note"] = "셈 안 함"
        elif not r[1]: row["note"] = "셈 안 함"
        elif grp == "stock" and key == "vix" and g.get("stock"): row["note"] = "셈 안 함"      # 주식+공포 합쳐서 1표, 주식이 0이면 VIX
        else: row["counted"] = True; g[grp] = (r[3], wt)
        rows.append(row)
    if upcoming_ev: return rows, {"pos": None, "text": "발표 뒤 시장 움직임을 세서 보여드려요"}
    if len(g) < 2: return rows, {"pos": None, "text": "아직 시장 반응이 충분하지 않아요"}
    bad = sum(w for s_, w in g.values() if s_ == "bad"); good = sum(w for s_, w in g.values() if s_ == "good"); tot = bad + good
    sc = (bad - good) / tot
    side = "bad" if sc >= .34 else "good" if sc <= -.34 else None
    weak = any(r["weak"] and r["counted"] for r in rows)
    return rows, {"pos": round(50 + sc * 50), "side": side,
                  "text": f"사건 뒤 시장 움직임은 {'악재 쪽' if side == 'bad' else '호재 쪽'}에 더 가까워요" if side else "사건 뒤 시장 반응이 엇갈려요",
                  "basis": f"위 시장 움직임 {sum(1 for r in rows if r['counted'])}개를 셌어요" + (" · 약하게는 반만" if weak else "")}

def doms(srcs):
    from urllib.parse import urlparse
    return {urlparse(x.get("url", "")).netloc.removeprefix("www.") for x in srcs or []} - {""}
def t2_tally(t2):
    """명세 §3-10 ② T2 E12: 갈래를 만든 기사는 빼고, 서로 다른 매체 3개+. 매체당 1개."""
    made = {x.get("url") for k in ("a", "b") for x in (t2.get(k) or {}).get("view_sources", [])}
    seen, items = set(), []
    for x in t2.get("tally") or []:
        dm = next(iter(doms([x])), None)
        if not dm or x["url"] in made or dm in seen: continue
        seen.add(dm); items.append(x)
    if len(items) < 3: return {"items": [], "text": "아직 기사가 충분하지 않아요", "pos": None}
    na = sum(1 for x in items if x["branch"] == "a"); n = len(items); nb = n - na
    big = "a" if na > nb else "b" if nb > na else None
    nm = lambda k: f"{k.upper()} 갈래"
    text = f"기사들은 {nm(big)}를 더 많이 말해요 ({n}개 중 {max(na, nb)}개)" if big else f"기사들은 두 갈래를 비슷하게 말해요 ({n}개 중 {na}개씩)"
    return {"items": items, "text": text, "pos": round(nb / n * 100), "basis": f"기사 {n}개 중 A {na}개 · 업종 가격은 아직 안 셈"}

def watch_card(key, hi, lo, facts, today):
    """보는 지표 카드 (02-UX "지난 사건 → 다음에 볼 지표"): 값·방향·출처·다음 발표는 코드(수집값·일정표)만. 없으면 None → 화면 "값 확인 전"/"일정 확인 전"."""
    c = WS.get(key)
    if not c: return None
    s = facts["series"].get(key); val = dirn = asof = src = None
    if s:
        if "yoy" in s:
            val = f"{mdd(s['date'])} 전년 대비 {s['yoy']:.1f}%"; ch = s["yoy"] - s["yoy_prev"]
        else:
            unit = s["unit"] if s["unit"] in ("%", "원") else ""
            val = f"{s['value']:,.2f}{unit} ({mdd(s['date'])} 기준)"; ch = s["value"] - s["prev"]
        dirn = "up" if ch > 0 else "down" if ch < 0 else None
        src = {"name": "한국은행 ECOS" if "ecos" in s["source"]["url"] else "FRED", "url": s["source"]["url"]}   # 통계표 번호가 숫자 검사에 걸리지 않게
    nx = next((r for r in sorted(load_schedule(), key=lambda r: r["date"]) if r["code"] == c["sched"] and r.get("verified")
               and (r.get("kst") or r["date"])[:10] >= today.isoformat()), None) if c.get("sched") else None
    nd = (nx.get("kst") or nx["date"])[:10] if nx else None
    return {"key": key, "short": c["short"], "name": c["full"], "value": val, "dir": dirn, "source": src,
            "next": md(nd) if nd else None, "next_date": nd, "high": hi, "low": lo, "hit": None}

def asof_of(facts, today):
    """기준 시각 = 실제 수집 시각 (검수 11/27: 08:00 고정 표기는 재실행 때 틀림)."""
    try: c = dt.datetime.fromisoformat(facts["collected_at"]); return f"{c.month}/{c.day} {c.hour:02d}:{c.minute:02d}"
    except (KeyError, ValueError): return f"{today.month}/{today.day}"

def assemble(today, facts, draft, upc, yesterday):
    events = []
    for e in draft["events"]:
        if not e.get("schedule_code") and e["type"] == "E1" and any(r["node"] == "rate" and r.get("kr") for r in e["real"]):
            e["schedule_code"] = "BOK"                          # AI가 비워도 한국 금리 결정이면 금통위로 연결 (결과 줄 값 채우기)
        sched = next((u for u in upc if u["code"] == e.get("schedule_code")), None)
        ev = {"id": e["id"], "type": e["type"], "chip": e["chip"], "head": e["head"], "kind": e["kind"],
              "date": edate(e, sched, today), "dday": e["kind"] != "done",
              "real": st_dict(e["real"]), "realPath": e["realPath"], "next": e["next"], "actual": None,
              "opts": {k: {"label": o["label"], "path": o["path"], "state": st_dict(o["state"]),
                           "cond": [[c["text"], c["dir"], 1 if c["done"] else 0] for c in o["cond"]], "out": o["out"]} for k, o in e["opts"].items()},
              "judgeKeys": [j["key"] for j in (e["judge_keys"] or default_judge(facts, e))],
              "judge": {"interest": {}, "items": [judge_row(facts, j["key"], j["side_if_up"]) for j in (e["judge_keys"] or default_judge(facts, e))]},
              "lean": None, "confirm": [dict(c, done=False, when=md(c.get("when")), date=iso(c.get("when"), today)) for c in e["confirm"]], "sources": e["sources"],
              "sectorTab": "kr" if e["type"] in ("E4",) else "us", "sectors": SECT.get(e["type"])}
        # 보는 지표 + 열린 질문 + 시나리오·결과 확인 첫 단계를 그 지표와 1:1
        w = e.get("watch") or {}
        ev["watch"] = watch_card(w.get("key"), w.get("high"), w.get("low"), facts, today) if w else None
        ev["question"] = e.get("question")
        if ev["watch"] and w.get("expect") and len(doms(w.get("expect_sources"))) >= 2:
            ev["watch"]["expect"] = {"value": w["expect"], "source": (w["expect_sources"] or [None])[0]}
        # 유형(명세 §3-10 ①): 일정표 정기 발표·금리 결정은 무조건 T1
        ev["ktype"] = e.get("ktype") if e.get("ktype") in KT and e.get("etype") != "T2" else None   # §3-11
        ev["etype"] = "T1" if e.get("schedule_code") or e.get("etype") != "T2" else "T2"
        ev["t2"] = None
        if ev["etype"] == "T2" and e.get("t2"):
            t = e["t2"]; ev["t2"] = {"verify": dict(t["verify"], when=md(t["verify"].get("when")) if t["verify"].get("when") else None),
                                     "a": t["a"], "b": t["b"], "actual": t.get("actual"), "tally": t2_tally(t)}
            if t.get("actual") in ("a", "b"): ev["actual"] = t["actual"]
        ev["outlook"] = e.get("outlook"); ev["size"] = (e.get("size") or [])[:2]
        if ev["watch"]:
            W = ev["watch"]
            jo = lambda w: w + ("이" if (ord(w[-1]) - 0xAC00) % 28 and 0xAC00 <= ord(w[-1]) <= 0xD7A3 else "가")
            for k, d in (("a", "up"), ("b", "down")):
                if k in ev["opts"]:
                    ev["opts"][k]["label"] = f"{jo(W['short'])} 예상보다 {'높으면' if d == 'up' else '낮으면'}"   # E5 (명세 §3-6)
                    rest = [c for c in ev["opts"][k]["cond"] if W["short"] not in c[0] and W["name"] not in c[0]]
                    ev["opts"][k]["cond"] = [[W["name"], d, 0]] + rest[:2]
            first = {"label": "먼저", "what": f"{W['name']} 발표", "when": W["next"] or "일정 확인 전", "date": W["next_date"], "done": False}
            # 최종 단계 = 이 사건을 낸 기관의 다음 결정 (한국 금리 사건 → 다음 금통위). 일정표에 공식 날짜가 있을 때만
            DEC = {"BOK": "금통위 금리 결정", "FOMC": "FOMC 금리 결정"}
            code = e.get("schedule_code")
            nd = next((r for r in sorted(load_schedule(), key=lambda r: r["date"]) if r["code"] == code and r.get("verified") and r["date"] > ev["date"]), None) if code in DEC else None
            later = [{"label": "최종", "what": DEC[code], "when": md(nd["date"]), "date": nd["date"], "done": False}] if nd else []
            ev["confirm"] = [first] + later
        if e["kind"] == "upcoming": ev["top"] = f"예상치 확인 전" if not e["expect_src"] else "예상치 출처 있음"
        if e["kind"] == "done":
            s = facts["series"].get(EVENT_SERIES.get(e.get("schedule_code") or "", ""), None)
            nums = f"{s['prev']:.2f}{s['unit']} → {s['value']:.2f}{s['unit']}" if s else ""
            exp = e["expect"] + (" · 전망이 갈렸어요" if e["spread"] else "") if e["expect"] else ""
            d = next(iter(ev["real"].values()), {}); d = d.get("dir") or d.get("kr") or d.get("us")
            ev["result"] = {"dir": d, "text": " · ".join(x for x in (nums, exp) if x) or None, "expect": e["expect"],
                            "actual_src": e["actual_src"], "expect_src": e["expect_src"]}
        ev["sub"] = sub_for(ev["date"], today.isoformat())
        ev["country"] = "kr" if e.get("schedule_code") in ("BOK", "KR_CPI") or any(r.get("kr") and not r.get("us") for r in e["real"]) else "us"
        if e["kind"] == "done" and ev.get("result", {}).get("text"):
            sname = NAMES.get(EVENT_SERIES.get(e.get("schedule_code") or "", ""), "")
            ev["trigger"] = f"{md(ev['date'])} {sname} {ev['result']['text']}".replace("  ", " ")   # 계기 한 줄 "11/26 기준금리 3.00% → 3.25%"
        events.append(ev)
    # 지난 사건 중 결과 확인(먼저/최종)이 아직 남은 것은 계속 보여줌 (02-UX 칩 규칙)
    have = {x["id"] for x in events}
    for y in (yesterday or {}).get("events", []):
        if y["id"] in have or y["kind"] != "done" or not y.get("date"): continue
        if any((c.get("date") or "") >= today.isoformat() for c in y.get("confirm", [])):
            y = dict(y, sub=sub_for(y["date"], today.isoformat()))
            if y.get("watch"): y["watch"] = dict(watch_card(y["watch"]["key"], y["watch"]["high"], y["watch"]["low"], facts, today) or y["watch"], expect=y["watch"].get("expect"))
            y["_y"] = True
            events.append(y)
    # 결과 확인이 남은 지난 사건: 칩 = 다음에 볼 지표 + 발표 날짜, 같은 지표가 두 칩이면 하나로
    seen = set(); merged = []
    for x in events:
        if x["kind"] == "done" and x["date"] < today.isoformat() and x.get("watch"):
            if x["watch"]["key"] in seen: continue
            seen.add(x["watch"]["key"]); x["chip"] = x["watch"]["short"]; x["sub"] = x["watch"]["next"] or "일정 확인 전"; x["watchChip"] = True
        merged.append(x)
    events = merged
    t0 = today.isoformat()
    events.sort(key=lambda x: (0, "") if x["kind"] == "done" and x["date"] == t0 else (1, "".join(chr(0x10FFFF - ord(ch)) for ch in x["date"])) if x["kind"] == "done" else (2, x["date"]))
    ints = rank_interests(draft["interests"], upc)
    for x in events: x.pop("_y", None)
    status = {"delayed": None, "quiet": not any(e["kind"] == "done" for e in events), "split": None,
              "closed": {"us": False, "kr": False}, "rankChange": None}
    sp, ks = facts["series"].get("sp500"), facts["series"].get("kospi")
    def gap(a, b):   # 두 날짜 사이에 낀 평일 수 (같은 날 방향 비교인지 확인, 명세 §3-1)
        a, b = sorted(dt.date.fromisoformat(x[:4] + "-" + x[4:6] + "-" + x[6:8]) if "-" not in x else dt.date.fromisoformat(x) for x in (a, b))
        return sum(1 for i in range(1, (b - a).days) if (a + dt.timedelta(days=i)).weekday() < 5)
    if sp and ks and gap(sp["date"], ks["date"]) == 0 and (sp["value"] - sp["prev"]) * (ks["value"] - ks["prev"]) < 0:
        status["split"] = {"us": "up" if sp["value"] > sp["prev"] else "down", "kr": "up" if ks["value"] > ks["prev"] else "down"}
    daily = [s["date"] for k, s in facts["series"].items() if len(s["date"]) == 10]
    if not daily or max(daily) < (today - dt.timedelta(days=4)).isoformat(): status["delayed"] = max(daily) if daily else "어제"
    if yesterday and yesterday.get("interests") and ints and yesterday["interests"][0]["key"] != ints[0]["key"]:
        status["rankChange"] = {"from": yesterday["interests"][0]["name"], "to": ints[0]["name"]}
    # E10 근거 행 + E12 가격 반응 (명세 §3-8). 이어 온 지난 사건은 기간이 지나면 어제 집계를 그대로 둠
    ylean = {y["id"]: y for y in (yesterday or {}).get("events", [])}
    for x in events:
        if x.get("etype") == "T2": x["lean"] = None; x["prices"] = []; continue
        up = x["kind"] != "done" or x["date"] > t0
        rows, lean = price_reaction(x.get("country", "us"), dt.date.fromisoformat(x["date"]), facts, status, up)
        yv = ylean.get(x["id"])
        if lean["pos"] is None and not up and yv and (yv.get("lean") or {}).get("pos") is not None: rows, lean = yv["prices"], yv["lean"]
        x["prices"], x["lean"] = rows, lean
        # 흐름도: 실제 경로 도착 칸이 가격 칸이면 센 방향을 실제 상태로 (보통과 반대 표시용, 명세 §3-9)
        if not up:
            node_of = {"ktb3y": "rate", "kospi": "stock", "usdkrw": "fx", "us_10y": "rate", "sp500": "stock"}
            for key, grp, _, _ in PRICE[x.get("country", "us")]:
                r = next((r for r in rows if r["name"] == NAMES.get(key, key) and r["counted"]), None)
                n = node_of.get(key)
                if not r or not n or n in x["real"] or not any(b == n for a, b in x["realPath"]): continue
                m = x.get("country", "us"); x["real"][n] = {m: r["dir"]}
    # B 풀이 순서(?b=1): 칸마다 지금 실제 방향(나라별) — 수집값만
    def sdir(k):
        x = facts["series"].get(k)
        if not x: return None
        ch = (x["yoy"] - x["yoy_prev"]) if x.get("yoy") is not None and x.get("yoy_prev") is not None else x["value"] - x["prev"]
        return "up" if ch > 0 else "down" if ch < 0 else None
    NOW = {"kr": {"cpi": "kr_cpi", "rate": "ktb3y", "fx": "usdkrw", "stock": "kospi", "oil": "wti", "vix": "vix"},
           "us": {"cpi": "us_cpi", "rate": "us_10y", "job": "us_jobs", "fx": "usdkrw", "stock": "sp500", "oil": "wti", "vix": "vix", "kospi": "kospi"}}
    now = {c: {n: sdir(k) for n, k in m.items() if sdir(k)} for c, m in NOW.items()}
    # "최신 값 확인 전" (검수 11/28): 일간 = 데이터 나라 휴장일 뺀 2영업일+, 월간 = 그 값 다음 발표일이 지났는데 그대로, 기준금리 = 다음 결정일이 지났는데 그대로
    HOL = {k: set(v) for k, v in json.loads((ROOT / "config" / "holidays.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}
    DAYKEY = {"us_10y": "us_bond", "us_base": "us_bond", "sp500": "us_stock", "vix": "us_stock", "wti": "us_stock", "usdkrw": "kr", "ktb3y": "kr", "kospi": "kr", "kr_base": "kr"}
    MON = {"us_cpi": "US_CPI", "us_ppi": "US_PPI", "us_jobs": "US_JOBS", "kr_cpi": "KR_CPI"}, 
    BSCH = {"us_base": "FOMC", "kr_base": "BOK"}
    SCH = load_schedule(); td = today if isinstance(today, dt.date) else dt.date.fromisoformat(str(today)[:10])
    def is_stale(k, d, x):
        if k in MON[0]:   # 값의 달 M → M 다음다음 달 이후 발표가 오늘 전에 있었으면 새 값이 나왔어야 함
            y, m = int(d[:4]), int(d[5:7] if "-" in d else d[4:6]); m2 = (y * 12 + m - 1 + 2); after = dt.date(m2 // 12, m2 % 12 + 1, 1)
            return any(r["code"] == MON[0][k] and after <= dt.date.fromisoformat(r["date"]) < td for r in SCH)
        if len(d) not in (8, 10): return False
        vd = dt.date(int(d[:4]), int(d[-4:-2]), int(d[-2:])) if len(d) == 8 else dt.date.fromisoformat(d)
        if k in BSCH:
            return any(r["code"] == BSCH[k] and vd < dt.date.fromisoformat(r["date"]) < td for r in SCH)
        hk = DAYKEY.get(k, "us_stock"); end = td - dt.timedelta(days=1) if hk.startswith("us") else td   # 미국 데이터 = 미국 날짜(한국 −1일)까지 (FRED는 다음 날 게시)
        hol, n, c = HOL.get(hk, set()), 0, vd + dt.timedelta(days=1)
        while c <= end:
            if c.weekday() < 5 and c.isoformat() not in hol: n += 1
            c += dt.timedelta(days=1)
        return n >= 2
    def sval(k):   # B v3 타임라인 제목 값 (수집값만)
        x = facts["series"].get(k)
        if not x: return None
        d, u, v = x["date"], x.get("unit", ""), x["value"]
        md = f"{int(d[4:6])}/{int(d[6:])}" if len(d) == 8 else f"{int(d[5:7])}/{int(d[8:])}" if len(d) == 10 and not d.endswith("-01") else f"{int(d[5:7] if '-' in d else d[4:6])}월"
        if x.get("yoy") is not None: t = f"전년 대비 {x['yoy']:.1f}%"
        elif u == "천 명": t = f"{(v - x['prev']) / 10:+,.1f}만 명"
        elif u == "%": t = f"{v:.2f}%"
        elif u == "원": t = f"{v:,.0f}원"
        else: t = f"{v:,.2f}"
        r = {"val": t, "date": md, "dir": sdir(k), "iso": f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else d if len(d) == 10 else None}
        r["stale"] = is_stale(k, d, x)
        ch = x.get("changed") or ({"date": d, "from": x["prev"]} if k in ("kr_base", "us_base") and x.get("prev") is not None and x["prev"] != v else None)
        if ch:   # 기준금리: 마지막 결정 (§3-10-2)
            cd = ch["date"].replace("-", "")
            r.update(dir="up" if v > ch["from"] else "down", chg={"from": f"{ch['from']:.2f}%", "md": f"{int(cd[4:6])}/{int(cd[6:8])}", "iso": f"{cd[:4]}-{cd[4:6]}-{cd[6:8]}"})
        elif k in ("kr_base", "us_base"): r["dir"] = None
        return r
    nowv = {c: {n: sval(k) for n, k in m.items() if sval(k)} for c, m in NOW.items()}
    sv = {k: sval(k) for k in facts["series"] if sval(k)}   # B v4: 지표 열쇠별 화면 값
    for c, k in (("kr", "kr_base"), ("us", "us_base")):   # 금리 칸 두 줄: 기준금리 + 시장 금리
        if sval(k): nowv[c]["rate_base"] = sval(k)
    up_codes = {u["code"] for u in upc}
    return {"judge_keys_all": sorted({k for e in events for k in e.get("judgeKeys", [])}),
            "upcoming_keys": sorted(k for k, c in WS.items() if c.get("sched") in up_codes),
            "date": today.isoformat(), "asof": asof_of(facts, today), "mock": False,
            "status": status, "interests": ints, "events": events, "now": now, "nowv": nowv, "sv": sv, "ktags": KT, "holidays": {k: v for k, v in json.loads((ROOT / "config" / "holidays.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}, "why": {k: v for k, v in CFG.get("why", {}).items() if not k.startswith("_")}}

def iso(w, today=None):
    """"2026-12-04" 또는 "12/4"(연도 없음 → 오늘 기준 가까운 해) → "2026-12-04". 못 읽으면 None."""
    try: return dt.date.fromisoformat(str(w)[:10]).isoformat()
    except (ValueError, TypeError): pass
    m = re.match(r"(\d{1,2})/(\d{1,2})", str(w or ""))
    if not (m and today): return None
    d = dt.date(today.year, int(m[1]), int(m[2]))
    if (d - today).days < -180: d = d.replace(year=today.year + 1)
    return d.isoformat()

def edate(e, sched, today):
    """사건 날짜(한국 날짜): AI가 준 date → 일정표 → id 앞 날짜 → 오늘 순."""
    for c in (e.get("date"), sched and (sched.get("kst") or sched.get("date")), str(e.get("id", ""))[:10]):
        if iso(c): return iso(c)
    return today.isoformat()

def md(w):   # "2026-12-04" → "12/4" (화면 표기). 그 외 문구는 그대로
    try: d = dt.date.fromisoformat(str(w)[:10]); return f"{d.month}/{d.day}"
    except (ValueError, TypeError): return w

def main():
    today = dt.datetime.now(KST).date()
    fp = ROOT / "data" / f"facts-{today}.json"                # 07:10 GitHub Actions가 키로 미리 수집해 둔 파일 (예약 실행엔 키 없음)
    facts = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else collect(today)
    upc = upcoming(load_schedule(), today)
    if "--draft" in sys.argv: draft = json.loads(pathlib.Path(sys.argv[sys.argv.index("--draft") + 1]).read_text(encoding="utf-8"))
    else:
        from generate import generate
        draft = generate(today.isoformat(), facts, upc)
    ARCH.mkdir(parents=True, exist_ok=True)
    (ARCH / f"draft-{today}.json").write_text(json.dumps(draft, ensure_ascii=False, indent=1), encoding="utf-8")
    yp = ARCH / f"today-{today - dt.timedelta(days=1)}.json"
    tp = ARCH / f"today-{today}.json"
    prev = json.loads(tp.read_text(encoding="utf-8")) if tp.exists() else None
    out = assemble(today, facts, draft, upc, json.loads(yp.read_text(encoding="utf-8")) if yp.exists() else None)
    if not draft.get("events") and prev and prev.get("events"):   # 같은 날 다시 생성에서 사건이 0개면 앞 실행의 통과 사건 유지
        out["events"] = prev["events"]; out["status"]["quiet"] = not any(e["kind"] == "done" for e in out["events"])
    final, errs = validate(out, facts)
    done = [e for e in out["events"] if e["kind"] == "done"]
    stats = {"date": today.isoformat(), "events": len(out["events"]), "passed": len(final["events"]), "errors": errs,
             "expect_found": sum(1 for e in done if e["result"].get("expect")), "expect_total": len(done), "collect_errors": facts["errors"]}
    (ARCH / f"today-{today}.json").write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
    (ARCH / f"log-{today}.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    if final["interests"]:                                   # 관심사가 하나도 없으면 공개하지 않음 → 어제 파일 유지 + 화면은 지연 표시
        (WEB / "today.json").write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k != "errors"}, ensure_ascii=False), "\n" + "\n".join(errs))

if __name__ == "__main__": main()
