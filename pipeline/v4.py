"""v4 사례 — 01-정보설계.md v4 · 02-화면.md (11/28 확정). 검사기('없을 때' 규칙) + 사례 고르기 + 흐름 조립 + 사례 저장.

  python3 pipeline/v4.py precheck data/v4/draft-오늘.json   # 후보마다 ①주목도·②영향도 통과 여부 (AI가 흐름을 쓸지 정함)
  python3 pipeline/v4.py build    data/v4/draft-오늘.json   # 검사 → web/v4/cases.json + data/v4/log-오늘.json
  python3 pipeline/v4.py mock                              # 화면 확인용 목업 → web/v4/mock.json

AI가 하는 일: 사건 후보(이름·날짜·매체 2곳·GDELT 검색어), 칸마다 '왜 움직였나'(과거형, 매체 2곳 또는 연결표 번호), 앞으로 조건 문장·이유.
코드가 하는 일: 값·방향·'크게' 날짜(수집값), 주목도·영향도·한국 영향 판단, 연결표 방향 검사, 다음 발표, 태그(호재/악재/미지수), 사례 상태·목록.
"""
import datetime as dt, json, pathlib, re, sys
from urllib.parse import urlparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from v4_cells import CELLS, IMPACT_MACRO, IMPACT_FIRM, ASSET_GRP, grp, load_links, find_link

ROOT = pathlib.Path(__file__).resolve().parent.parent
V4D, V4W = ROOT / "data" / "v4", ROOT / "web" / "v4"
BANNED = ["매수", "매도 권유", "사세요", "파세요", "유력", "확실", "반드시", "목표가", "목표 주가", "주가 전망", "오를 종목", "주목할 종목", "유망 종목", "추천주"]
PREDICT = re.compile(r"할 것|될 것|전망|예상된다|것으로 보|될 거예요|할 거예요")
SCHED_CELLS = {"US_CPI": {"us_cpi", "us_be10"}, "US_PPI": {"us_cpi"}, "US_JOBS": {"us_jobs"}, "FOMC": {"us_base", "us_10y", "us_2y"},
               "BOK": {"kr_base", "ktb3y"}, "KR_CPI": {"kr_cpi"}}

def doms(srcs): return {urlparse(x.get("url") or "").netloc.removeprefix("www.") for x in srcs or []} - {""}
def bad(t): return [w for w in BANNED if w in (t or "")]
def md(d): return f"{int(d[5:7])}/{int(d[8:10])}"
def josa(w, a="이", b="가"):
    c = (w or " ")[-1]
    return w + (a if "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 else b if "가" <= c <= "힣" else b)

def load(p, default=None):
    p = pathlib.Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

def fmt(v, cell):
    c = CELLS[cell]
    if c["unit"] == "%": s = f"{v:.2f}%"
    elif cell.startswith("nvda_"): s = f"${v / 1e9:,.1f}B"
    elif c["unit"] == "천 명": s = f"{v / 10:,.0f}만 명" if v >= 1000 else f"{v:,.0f}천 명"
    else: s = f"{v:,.2f}" if v < 1000 else f"{v:,.0f}"
    return c.get("pre", "") + s.replace("$", "") if c.get("pre") else s + (c.get("post", "") or "")

class Data:
    """수집값 묶음: 1년 일별(history) · 월간 등(facts) · SEC(nvda)."""
    def __init__(self, today, backfill=False):
        """backfill: 지난 사례 채우기 — history-backfill.json을 today(그날 공개 기준)까지만 자름. 월간·SEC 값은 그날 값이 없어 안 씀"""
        self.today = today
        if backfill:
            t = today.isoformat()
            H = (load(V4D / "history-backfill.json", {}) or {}).get("cells", {})
            self.hist = {k: dict(v, points=[p for p in v["points"] if p[0] < t], big=[b for b in v["big"] if b["date"] < t], notable=[b for b in v.get("notable", []) if b["date"] < t]) for k, v in H.items()}
            self.facts, self.nvda = {}, {}
            return
        self.hist = (load(V4D / "history.json", {}) or {}).get("cells", {})
        f = sorted((ROOT / "data").glob("facts-*.json"))
        self.facts = (load(f[-1], {}) or {}).get("series", {}) if f else {}
        self.nvda = (load(V4D / "nvda.json", {}) or {}).get("cells", {})
    def now(self, cell):
        """오늘 값 {value, text, date, source} — 없으면 None."""
        c = CELLS.get(cell)
        if not c: return None
        if cell in self.hist:
            d, v = self.hist[cell]["points"][-1]; return {"value": v, "text": fmt(v, cell), "date": d, "source": self.hist[cell]["source"]}
        s = (self.nvda if c["src"] == "sec" else self.facts).get(c["sid"])
        if not s: return None
        v = s["yoy"] if c.get("yoy") and s.get("yoy") is not None else s["value"]
        return {"value": v, "text": fmt(v, cell) if not c.get("yoy") else f"{v:.1f}%", "date": s.get("date") or s.get("end"), "source": s.get("source")}
    def move(self, cell, since, key="big"):
        """사건 날 이후: 방향(사건 전날 대비 +1/-1/0)과 처음 '크게' 움직인 날. 매일 값이 없는 칸은 마지막 발표가 사건 뒤인지로."""
        c = CELLS.get(cell)
        if cell in self.hist:
            h = self.hist[cell]; pts = h["points"]
            before = [v for d, v in pts if d < since]
            if not before: return None
            last, base = pts[-1][1], before[-1]
            big = next((b for b in h.get(key, []) if b["date"] >= since), None)
            if key == "notable" and big: big = max((b for b in h["notable"] if b["date"] >= since), key=lambda b: b["x"])  # 큰 순서용: 가장 많이 움직인 날
            tol = (h["sd"] or 0) * 0.25          # 옆걸음: 사건 전날과 차이가 하루 표준편차의 1/4 안 (값 단위 맞춤: log 칸은 %)
            diff = (last - base) if h["calc"] == "diff" else (last / base - 1) * 100
            return {"dir": 0 if abs(diff) <= tol else 1 if diff > 0 else -1, "big": big, "daily": True}
        s = (self.nvda if c and c["src"] == "sec" else self.facts).get(c["sid"]) if c else None
        if not s: return None
        d = s.get("date") or s.get("filed") or ""
        d = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 and "-" not in d else d if len(d) == 10 else None   # 월간(YYYYMM) 은 날짜 판단 불가
        a, b = (s.get("yoy"), s.get("yoy_prev")) if s.get("yoy") is not None else (s["value"], s["prev"])
        return {"dir": (a > b) - (a < b), "big": None, "daily": False, "released": bool(d and d >= since)}

# ── 사건 후보 검사 + ① 주목도 ② 영향도 ─────────────────────────────
def check_event(c, today, errs):
    nm = c.get("name") or ""
    if len(doms(c.get("sources"))) < 2: errs.append(f"[{nm}] 사건 출처 서로 다른 매체 2곳 미만 — 사례 아님"); return False
    if bad(nm) or PREDICT.search(nm): errs.append(f"[{nm}] 사건 이름에 해석·예측·금지어 — 사례 아님"); return False
    try: d = dt.date.fromisoformat(c["date"])
    except Exception: errs.append(f"[{nm}] 사건 날짜 없음"); return False
    if d > today: errs.append(f"[{nm}] 사건 날짜가 미래"); return False
    if c.get("kind") not in ("macro", "firm"): errs.append(f"[{nm}] kind는 macro/firm"); return False
    return True

def impact(c, D, recent=None):
    """② 영향도: 시장 칸 하나 이상이 '크게'(지난 1년 표준편차 2배) 움직였나. → [(칸, 날짜)]
    새 사례 = 사건 날 이후 아무 때나. 이어지는 사례(recent=날짜) = 그 날짜 이후에도 크게 움직였어야 '진행 중'(끝나는 때, 정보설계 v4)"""
    out = []
    for k in IMPACT_FIRM if c.get("kind") == "firm" else IMPACT_MACRO:
        h = D.hist.get(k)
        if not h: continue
        bigs = [b for b in h["big"] if b["date"] >= max(c["date"], recent or "")]
        if bigs: out.append((k, bigs[-1]["date"] if recent else bigs[0]["date"]))
    return out

def precheck(draft, today, backfill=False):
    D, errs, rows = Data(today, backfill), [], []
    for c in draft.get("candidates", []):
        ok = check_event(c, today, errs)
        a = c.get("attention") or {}
        im = impact(c, D) if ok else []
        rows.append({"key": c.get("key"), "name": c.get("name"), "event_ok": ok, "attention": a.get("pass"), "z": a.get("z"), "base": a.get("base"),
                     "impact": im, "write_flow": bool(ok and a.get("pass") and im)})
    if not any(r["write_flow"] for r in rows):   # 오늘의 이슈 후보 (1위가 흐름을 못 쓰면 2위도 쓴다)
        for r in sorted((r for r in rows if r["event_ok"] and r["z"] is not None), key=lambda r: -r["z"])[:2]: r["write_flow"] = "issue"
    return rows, errs

# ── 흐름 검사·조립 ─────────────────────────────────────────────
def node_value(n, D):
    if n.get("cell") in CELLS: return D.now(n["cell"])
    m = n.get("media") or {}
    if m.get("value") and len(doms(m.get("sources"))) >= 2: return {"value": None, "text": m["value"], "date": None, "source": m["sources"], "media": True}
    return None

def build_flow(c, F, D, links, errs, issue=False):
    """지금까지 흐름. 규칙: 칸마다 이유 필수(근거 = 매체 2곳만) · 연결 근거(연결표 방향 맞음 또는 매체 2곳) · 수집 칸은 사건 뒤 '크게' 움직인 날이 있어야 함."""
    nm, since = c["name"], c["date"]
    sr = F.get("start_reason") or {}
    if not ok_reason(sr.get("text"), past=True) or len(doms(sr.get("sources"))) < 2:
        errs.append(f"[{nm}] 시작 칸 이유 없음/매체 2곳 미만 — 흐름 없음"); return None
    start = {"id": "start", "kind": "start", "name": nm, "date": since, "reason": sr["text"], "sources": sr["sources"], "parents": [], "dir": 1, "grp": "event"}
    nodes, by = [start], {"start": start}
    for n in F.get("nodes", []):
        lab = n.get("cell") or (n.get("media") or {}).get("name") or n.get("id")
        par = [by[p] for p in n.get("parents", []) if p in by]
        if not par: errs.append(f"[{nm}] {lab}: 위 칸이 흐름에 없음 — 뺌"); continue
        val = node_value(n, D)
        if not val: errs.append(f"[{nm}] {lab}: 값 없음(수집값 또는 매체 2곳 같은 숫자) — 뺌"); continue
        if n.get("cell") in CELLS:
            m = D.move(n["cell"], since, "notable" if issue else "big")
            if not m: errs.append(f"[{nm}] {lab}: 사건 전 값 없음 — 뺌"); continue
            if m["daily"] and not m["big"]: errs.append(f"[{nm}] {lab}: 사건 뒤 {'평소보다 많이(1배)' if issue else '크게(2배)'} 움직인 날 없음 — 뺌"); continue
            if not m["daily"] and not m.get("released"): errs.append(f"[{nm}] {lab}: 사건 뒤 새 발표 없음 — 뺌"); continue
            d, date = m["dir"], (m["big"] or {}).get("date")
        else:
            d = {"up": 1, "down": -1, "flat": 0}.get((n.get("media") or {}).get("dir")); date = None
            if d is None: errs.append(f"[{nm}] {lab}: 매체 칸 방향 없음 — 뺌"); continue
        g = grp(n)
        # 연결 근거: 위 칸들 중 하나라도 연결표 방향이 맞거나, 이유에 매체 2곳
        L = None
        for p in par:
            L = find_link(p["grp"], p["dir"] or None, g, d or None, links)
            if L and (not n.get("link") or n["link"] == L["id"]): break
            L = None
        src2 = len(doms(n.get("reason_sources"))) >= 2
        if not (L or src2): errs.append(f"[{nm}] {lab}: 연결 근거 없음(연결표 방향 안 맞음 + 매체 2곳 미만) — 뺌"); continue
        # 이유 근거 = 서로 다른 매체 2곳만 (연결표는 '보통 이렇게 이어진다'일 뿐 — 연결에만 씀, 기획 11/28 · 정보설계 v4 .이유)
        if not ok_reason(n.get("reason"), past=True) or not src2:
            errs.append(f"[{nm}] {lab}: 왜 움직였나 없음/말투(과거형)/매체 2곳 미만 — 뺌"); continue
        x = {"id": n["id"], "kind": "past", "cell": n.get("cell"), "name": CELLS[n["cell"]]["name"] if n.get("cell") in CELLS else n["media"]["name"],
             "grp": g, "kr": CELLS[n["cell"]]["kr"] if n.get("cell") in CELLS else (n.get("media") or {}).get("country") == "kr",
             "value": val["text"], "dir": d, "date": date, "reason": n["reason"], "sources": n.get("reason_sources") or [],
             "link": L["id"] if L else None, "parents": [p["id"] for p in par], "value_source": val["source"], "media": bool(val.get("media")),
             "x": (m["big"] or {}).get("x") if n.get("cell") in CELLS else None}
        nodes.append(x); by[x["id"]] = x
    if issue:   # 오늘의 이슈: 큰 순서로 (위 칸보다 앞으로 오지 않게 — 깊이 먼저, 같은 깊이 안에서 배수 큰 순)
        depth = {"start": 0}
        for n in nodes[1:]: depth[n["id"]] = 1 + max(depth.get(p, 0) for p in n["parents"])
        nodes = [nodes[0]] + sorted(nodes[1:], key=lambda n: (depth[n["id"]], -(n.get("x") or 0)))
    return nodes

def ok_reason(t, past=False, end=None):
    t = (t or "").strip()
    if not t or bad(t) or not t.endswith("요"): return False
    if past and PREDICT.search(t): return False
    if end and not any(t.endswith(e) for e in end): return False
    return True

def next_release(codes, today):
    sch = []
    for p in (ROOT / "config").glob("schedule-*.json"): sch += load(p)["events"]
    rows = sorted([r for r in sch if r["code"] in codes and r.get("verified") and today <= dt.date.fromisoformat(r["date"]) <= today + dt.timedelta(days=30)], key=lambda r: r["date"])
    return rows[0] if rows else None

def build_future(c, F, flow, D, links, today, errs):
    """앞으로 = 하나의 흐름(02-화면.md): 조건(리스트 헤더) → 칸들(점선). 연결은 연결표만. 중간 칸 '…쉬워요', 끝 칸만 태그."""
    nm, fu = c["name"], F.get("future") or {}
    if not fu: return None
    flow_cells = {n.get("cell") for n in flow or []}
    rel = None
    if fu.get("release_code"):
        r = next_release({fu["release_code"]}, today)
        if r and (SCHED_CELLS.get(r["code"], set()) & (flow_cells | {fu.get("start", {}).get("cell")})): rel = r
        elif r: errs.append(f"[{nm}] 발표 {r['name']}가 흐름 칸과 안 이어짐 — 타이틀 기본 문구")
    st = fu.get("start") or {}
    sd = {"up": 1, "down": -1}.get(st.get("dir"))
    sg = grp(st.get("cell")) if st.get("cell") in CELLS else st.get("grp")
    head = (fu.get("header") or "").strip()
    if not (sd and sg and head.endswith("?") and "면" in head and not bad(head)):
        errs.append(f"[{nm}] 앞으로 조건(의문형 '…면?')·시작 칸 없음 — 앞으로 안 그림"); return None
    root = {"id": "fstart", "grp": sg, "dir": sd}
    by, out = {"fstart": root}, []
    kids = {}
    for n in fu.get("nodes", []): kids.setdefault(n.get("parent"), []).append(n.get("id"))
    for n in fu.get("nodes", []):
        lab = n.get("cell") or (n.get("media") or {}).get("name")
        p = by.get(n.get("parent"))
        if not p: errs.append(f"[{nm}] 앞으로 {lab}: 위 칸 없음 — 뺌"); continue
        g = grp(n)
        L = next((x for x in links.values() if x["id"] == n.get("link")), None)
        if not L or p["grp"] not in L.get("a", []) or g not in L.get("b", []) or (p["dir"] < 0 and not L.get("sym")):
            errs.append(f"[{nm}] 앞으로 {lab}: 연결표 {n.get('link')}번과 칸이 안 맞음 — 뺌"); continue
        d = p["dir"] * L["s"]
        end = not kids.get(n["id"])
        tag, reason = None, n.get("reason")
        if end and g in ASSET_GRP:
            if L.get("weak") or n.get("unknown_why"):
                tag, reason = "unknown", n.get("unknown_why") or "이어지는 연결의 근거가 아직 약해서 방향을 말하기 어려워요"
            else: tag = "good" if d > 0 else "bad"
        if not ok_reason(reason, end=None if end else ["쉬워요"]) :
            errs.append(f"[{nm}] 앞으로 {lab}: 이유 없음/말투(중간 칸은 '…쉬워요') — 뺌"); continue
        val = node_value(n, D)
        x = {"id": n["id"], "kind": "future", "cell": n.get("cell"), "name": CELLS[n["cell"]]["name"] if n.get("cell") in CELLS else (n.get("media") or {}).get("name"),
             "grp": g, "kr": CELLS[n["cell"]]["kr"] if n.get("cell") in CELLS else (n.get("media") or {}).get("country") == "kr",
             "dir": d, "now": val["text"] if val else None, "now_dir": (D.move(n["cell"], c["date"]) or {}).get("dir") if n.get("cell") in CELLS else None,
             "reason": reason, "tag": tag, "link": L["id"], "parent": p.get("id") if p is not root else None, "end": end}
        out.append(x); by[x["id"]] = x
    if not out: return None
    return {"release": {"code": rel["code"], "name": rel["name"], "date": rel["date"], "md": md(rel["date"]), "title": josa(rel["name"]) + " 중요해요", "source": rel.get("source")} if rel else None,
            "title": josa(rel["name"]) + " 중요해요" if rel else "앞으로 이렇게 바뀔 수 있어요", "header": head, "nodes": out}

# ── 사례 저장 ─────────────────────────────────────────────────
def build(draft_path, today=None, backfill=False, store_path=None):
    """backfill=True: today = 그 사례를 공개했을 날. 같은 규칙으로 검사하고, 사례는 '기록'으로 저장(다른 사례 상태는 안 건드림)."""
    today = today or dt.date.today()
    draft = load(draft_path)
    D, links, errs = Data(today, backfill), load_links(), []
    store_path = pathlib.Path(store_path or V4W / "cases.json")
    store = load(store_path, {"cases": []})
    cases = {x["id"]: x for x in store["cases"]}
    passed = []
    for c in draft.get("candidates", []):
        if not check_event(c, today, errs): continue
        a = c.get("attention") or {}
        if not a.get("pass"): errs.append(f"[{c['name']}] ① 주목도 못 넘음 (z={a.get('z')}, {a.get('base') or a.get('why')})"); continue
        cont = c.get("same_as") in cases and cases[c["same_as"]]["status"] == "live"
        im = impact(c, D, (today - dt.timedelta(days=4)).isoformat() if cont else None)
        if not im: errs.append(f"[{c['name']}] ② 영향도: {'최근 4일' if cont else '사건 뒤'} 크게 움직인 시장 칸 없음"); continue
        F = (draft.get("flows") or {}).get(c["key"])
        if not F: errs.append(f"[{c['name']}] 흐름 초안 없음"); continue
        flow = build_flow(c, F, D, links, errs)
        if not flow or len(flow) < 2: errs.append(f"[{c['name']}] 흐름 칸 0개 — 사례 아님"); continue
        fut = build_future(c, F, flow, D, links, today, errs)
        if not any(n.get("kr") for n in flow[1:] + ((fut or {}).get("nodes") or [])):
            errs.append(f"[{c['name']}] ③ 한국 영향: 흐름이 한국 칸까지 안 이어짐 — 사례 아님"); continue
        cid = c.get("same_as") if c.get("same_as") in cases else f"{c['date']}-{c['key']}"
        old = cases.get(cid)
        dates = (old or {}).get("event", {}).get("dates") or [{"date": c["date"], "label": "시작"}]
        if old and old.get("status") == "record": dates = dates + [{"date": today.isoformat(), "label": "다시 확대"}]
        cases[cid] = {"id": cid, "kind": c["kind"], "status": "record" if backfill else "live", "updated": today.isoformat(),
                      **({"backfill": True, "ended": today.isoformat(), "asof": today.isoformat()} if backfill else {}),
                      "event": {"name": c["name"], "date": c["date"], "dates": dates, "sources": c["sources"]},
                      "attention": a, "impact": [{"cell": k, "date": d} for k, d in im], "flow": flow, "future": fut}
        passed.append((a.get("z") or 0, cid))
    issue = None
    if not passed and not backfill:   # {오늘의 이슈}: 진행 중 사례가 없는 날, 범위 안 사건 중 기사 급증 배수 1위 (사례 아님 · 목록에 안 쌓음)
        ranked = sorted((c for c in draft.get("candidates", []) if (c.get("attention") or {}).get("z") is not None and check_event(c, today, [])),
                        key=lambda c: -c["attention"]["z"])
        for c in ranked:
            F = (draft.get("flows") or {}).get(c["key"])
            if not F: errs.append(f"[{c['name']}] 오늘의 이슈 후보지만 흐름 초안 없음 — 다음 후보"); continue
            ie = []
            flow = build_flow(c, F, D, links, ie, issue=True)
            if not flow: errs += ie; errs.append(f"[{c['name']}] 오늘의 이슈: 시작 칸 이유/매체 2곳 없음 — 다음 후보"); continue
            errs += [f"(오늘의 이슈) {e}" for e in ie]
            fut = build_future(c, F, flow, D, links, today, errs)
            issue = {"id": f"issue-{today.isoformat()}-{c['key']}", "kind": c["kind"], "status": "issue", "updated": today.isoformat(),
                     "event": {"name": c["name"], "date": c["date"], "dates": [{"date": c["date"]}], "sources": c["sources"]},
                     "attention": c["attention"], "flow": flow, "future": fut}
            break
    live_today = {cid for _, cid in passed}
    for cid, x in cases.items() if not backfill else []:                     # 끝나는 때: 오늘 기준을 못 넘은 진행 중 사례 → 기록(갱신 멈춤)
        if x["status"] == "live" and cid not in live_today: x["status"] = "record"; x["ended"] = today.isoformat()
    rep = (max(passed)[1] if passed else None) if not backfill else store.get("rep")
    order = sorted(cases.values(), key=lambda x: x["event"]["dates"][-1]["date"], reverse=True)
    first = rep or (order[0]["id"] if order else None)
    if issue: first = issue["id"]
    out = {"date": today.isoformat(), "asof": f"{today.isoformat()} 08:00", "rep": rep, "first": first, "issue": issue, "cases": order}
    if backfill:
        out.update(date=store.get("date", out["date"]), asof=store.get("asof", out["asof"]), issue=store.get("issue"))
        if store.get("issue") and not store.get("rep"): out["first"] = store["issue"]["id"]
    V4W.mkdir(parents=True, exist_ok=True); V4D.mkdir(parents=True, exist_ok=True)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    log = {"date": today.isoformat(), "passed": [cid for _, cid in passed], "rep": rep, "issue": issue and issue["id"], "errors": errs}
    (V4D / f"log-{'backfill-' if backfill else ''}{today.isoformat()}.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    return log

def backfill_sim(draft_path, start, end):
    """지난 사례 채우기: start~end 날마다 '그날 08:00 공개' 기준으로 같은 규칙(주목도·영향도·한국 영향·칸 검사)을 돌린다.
    주목도는 data/v4/attention.json에 쌓인 하루 기사 수로 계산(GDELT 다시 안 부름). 마지막 진행 중 모습을 '기록'으로 cases.json에 넣는다."""
    from v4_data import att_z
    draft = load(draft_path); att = load(V4D / "attention.json", {})
    tmp_store = V4D / "backfill-store.json"; tmp_store.unlink(missing_ok=True)
    tmp_draft = V4D / "backfill-draft.json"
    d, days = dt.date.fromisoformat(start), []
    while d <= dt.date.fromisoformat(end):
        live = {x["id"]: x for x in (load(tmp_store, {"cases": []})["cases"]) if x["status"] == "live"}
        for c in draft["candidates"]:
            c["attention"] = att_z(att[c["key"]], d) if c["key"] in att else {"z": None, "why": "기사 수 없음"}
            cid = f"{c['date']}-{c['key']}"
            if cid in live or any(x["id"] == cid for x in load(tmp_store, {"cases": []})["cases"]): c["same_as"] = cid
        tmp_draft.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        log = build(tmp_draft, d, backfill=True, store_path=tmp_store)
        # backfill 모드는 상태를 '기록'으로 저장하므로, 시뮬레이션 중엔 진행 중으로 되돌려 끝나는 때를 판단
        st_ = load(tmp_store)
        for x in st_["cases"]:
            if x["id"] in log["passed"]: x["status"] = "live"; x.pop("ended", None)
            elif x["status"] == "live" or (x.get("backfill") and not x.get("closed")): x["status"] = "record"; x["closed"] = True; x["ended"] = x.get("ended") or d.isoformat()
        tmp_store.write_text(json.dumps(st_, ensure_ascii=False), encoding="utf-8")
        days.append((d.isoformat(), log["passed"], [e for e in log["errors"] if "①" in e or "②" in e or "③" in e][:2]))
        d += dt.timedelta(days=1)
    real = load(V4W / "cases.json", {"cases": []}); have = {x["id"]: x for x in real["cases"]}
    for x in load(tmp_store, {"cases": []})["cases"]:
        x.update(status="record", backfill=True); x.pop("closed", None); have[x["id"]] = x
    real["cases"] = sorted(have.values(), key=lambda x: x["event"]["dates"][-1]["date"], reverse=True)
    if not real.get("first") and real["cases"]: real["first"] = real["cases"][0]["id"]
    (V4W / "cases.json").write_text(json.dumps(real, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp_store.unlink(missing_ok=True); tmp_draft.unlink(missing_ok=True)
    return days

if __name__ == "__main__":
    cmd, arg = (sys.argv + ["", ""])[1:3]
    if cmd == "precheck":
        rows, errs = precheck(load(arg), dt.date.today()); print(json.dumps(rows, ensure_ascii=False, indent=1)); print("\n".join(errs))
    elif cmd == "build": print(json.dumps(build(arg), ensure_ascii=False, indent=1))
    elif cmd == "backfill": print(json.dumps(build(arg, dt.date.fromisoformat(sys.argv[3]), backfill=True), ensure_ascii=False, indent=1))
    elif cmd == "backfill-sim":   # python3 pipeline/v4.py backfill-sim DRAFT 2026-03-01 2026-04-30
        for row in backfill_sim(arg, sys.argv[3], sys.argv[4]): print(row)
    elif cmd == "precheck-asof":
        rows, errs = precheck(load(arg), dt.date.fromisoformat(sys.argv[3]), backfill=True); print(json.dumps(rows, ensure_ascii=False, indent=1)); print("\n".join(errs))
    else: print(__doc__)
