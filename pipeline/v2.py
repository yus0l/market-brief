"""v2 데이터 — 01-정보설계.md v3 (변수 기준, 11/28 확정).
화면의 모든 정보는 {관심사}가 정한다. 이 파일 하나에 스키마(AI가 채울 틀)·검사기('없을 때' 규칙)·조립(today.json "topics")을 둔다.
아직 매일 실행(routine)에 연결하지 않음 — UX 배치가 오면 routine-prompt를 v2로 바꾸고 화면을 붙인다.

AI가 하는 일: 관심사 키워드 찾기·요소 분류·근거 기사·경로 칸 목록·칸마다 이번에 왜·K 번호.
코드가 하는 일: 값(수집값)·방향·비교 결과·다음 발표·가정 경로·기본 관계 why·순위·코스피 끝 칸.
"""
import datetime as dt, json, pathlib, re
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config" / "graph.json").read_text(encoding="utf-8"))
KT = {k: v for k, v in json.loads((ROOT / "config" / "sidetags.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}

# §3 요소 목록 (MVP만). base = {기준 지표}를 어디서 얻나, path = {경로} 그리는 법, sched = 발표 올림
ELEMENTS = {
    "econ":    {"name": "경제 지표", "base": "series", "path": "basic", "sched": True},
    "cb":      {"name": "중앙은행", "base": "rate_base", "path": "basic", "sched": True},
    "company": {"name": "기업 소식", "base": "number", "path": "article", "sched": False},
    "policy":  {"name": "정책·정치", "base": None, "path": "article", "sched": False},
    "geo":     {"name": "지정학", "base": None, "path": "article", "sched": False},
    "fear":    {"name": "공포·심리", "base": "vix", "path": "basic", "sched": False},
}
SERIES_NODE = {"us_cpi": "cpi", "kr_cpi": "cpi", "us_ppi": "cpi", "us_jobs": "job", "us_10y": "rate", "ktb3y": "rate", "us_base": "rate", "kr_base": "rate",
               "usdkrw": "fx", "wti": "oil", "vix": "vix", "sp500": "stock", "kospi": "stock"}
SERIES_SCHED = {"us_cpi": "US_CPI", "kr_cpi": "KR_CPI", "us_ppi": "US_PPI", "us_jobs": "US_JOBS", "us_base": "FOMC", "kr_base": "BOK", "us_10y": "FOMC", "ktb3y": "BOK"}
# 칸 이름: 나라 + 종류 전체 (§2 {칸}.이름)
NODE_NAME = {"us": {"cpi": "미국 물가", "job": "미국 고용", "rate": "미국 10년 국채 금리", "fx": "원/달러", "stock": "S&P500", "oil": "WTI 유가", "vix": "미국 VIX", "gold": "국제 금값", "kospi": "코스피"},
             "kr": {"cpi": "한국 물가", "job": "한국 고용", "rate": "한국 3년 국채 금리", "fx": "원/달러", "stock": "코스피", "oil": "WTI 유가", "vix": "미국 VIX", "gold": "국제 금값", "kospi": "코스피"}}
NODE_SERIES = {"us": {"cpi": "us_cpi", "job": "us_jobs", "rate": "us_10y", "fx": "usdkrw", "stock": "sp500", "oil": "wti", "vix": "vix", "kospi": "kospi"},
               "kr": {"cpi": "kr_cpi", "rate": "ktb3y", "fx": "usdkrw", "stock": "kospi", "oil": "wti", "vix": "vix", "kospi": "kospi"}}
MARKET_END = re.compile(r"^(stock|kospi|rate|fx|sector:.+|idx:.+)$")   # 시장 칸(주식·업종·금리·환율)
EDGES = {(a, b) for a, b, *_ in CFG["edges"]} | {("stock", "kospi")}
WHY = CFG.get("why", {})
PREDICT = re.compile(r"할 것|될 것|할 수 있|될 수 있|전망|예상된다|것으로 보|될 거예요")
BANNED = ["매수", "매도", "사세요", "파세요", "유력", "확실", "반드시", "판정", "목표가", "목표 주가", "주가 전망", "오를 종목", "주목할 종목", "유망 종목", "추천주"]
EMPTYCAUSE = re.compile(r"^(투자\s*심리|시장\s*심리|불확실성|경계감|관망세|심리)\s*(이|가|의|에)?$")
NUM = re.compile(r"[+-]?\d[\d,]*\.?\d*")

# ── 스키마 (AI가 채움) ─────────────────────────────────────────
SRC = {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "url": {"type": "string"}}, "required": ["name", "url"], "additionalProperties": False}}
NUMV = {"type": ["object", "null"], "additionalProperties": False, "required": ["value", "sources"],
        "properties": {"value": {"type": "string", "description": "기사에 나온 숫자 그대로(단위 포함). 서로 다른 매체 2개가 같은 숫자일 때만"}, "sources": SRC}}
CELL = {"type": "object", "additionalProperties": False, "required": ["key", "name", "num", "link_sources", "why", "why_sources", "link_prev"], "properties": {
    "key": {"type": "string", "description": "칸 열쇠. 기본 칸이면 " + "/".join(CFG["nodes"]) + ". 그 밖은 'co:회사', 'sector:업종', 'idx:지수', 'px:가격'(예: 'co:엔비디아', 'sector:반도체', 'idx:나스닥', 'px:구리')"},
    "name": {"type": "string", "description": "나라+종류 전체 이름(예: '미국 10년 국채 금리', '엔비디아 주가'). 기본 칸은 코드가 덮어씀"},
    "num": dict(NUMV, description="수집값이 없는 칸(co:·sector:·idx:·px:)의 값. 기본 칸은 null(코드가 수집값으로 채움)"),
    "link_sources": dict(SRC, description="위 칸 → 이 칸 연결 근거. 기본 관계 14개에 있는 연결이면 빈 배열. 없는 연결이면 서로 다른 매체 2개 기사"),
    "why": {"type": ["string", "null"], "description": "이번에 왜 움직였나: '[원인] 때문이라고 봐요'. 원인 = 사건·지표·발표 이름. 과거형, 예측 금지, 숫자 금지. 근거 없으면 null"},
    "why_sources": SRC,
    "link_prev": {"type": "string", "enum": ["yes", "no", "unknown"], "description": "yes = 기사들이 위 칸 움직임 때문이라고 말함 / no = 다른 원인 / unknown = 근거 없음"}}}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["date", "topics"], "properties": {
    "date": {"type": "string"},
    "topics": {"type": "array", "maxItems": 5, "description": "후보 관심사(코드가 순위 매겨 3개). 최근 3일 뉴스에서 주목받는 키워드", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["name", "element", "country", "mention_sources", "reason", "reason_sources", "base_key", "base_num", "expect", "expect_sources",
                     "recent", "recent_sources", "path", "ktype", "read_articles"],
        "properties": {
            "name": {"type": "string", "description": "키워드. 나라가 있으면 붙임(예: '미국 물가', '데이터센터 규제', '엔비디아 실적')"},
            "element": {"type": "string", "enum": list(ELEMENTS), "description": "; ".join(f"{k}={v['name']}" for k, v in ELEMENTS.items())},
            "country": {"type": ["string", "null"], "enum": ["us", "kr", None]},
            "mention_sources": dict(SRC, description="최근 3일 이 키워드를 다룬 기사 URL(3개 이상이어야 인정)"),
            "reason": {"type": ["string", "null"], "description": "주목 이유 = 가장 많이 다뤄진 사건 이름(10자 안팎). 발표 때문이면 null(코드가 '발표 이름 날짜'로 채움)"},
            "reason_sources": SRC,
            "base_key": {"type": ["string", "null"], "enum": list(SERIES_NODE) + [None], "description": "기준 지표 수집값 열쇠. econ=그 지표, cb=us_base/kr_base, fear=vix. 기업·정책·지정학은 null"},
            "base_num": dict(NUMV, description="기업 소식일 때 그 회사 주가(매체 2개 같은 숫자). 그 밖엔 null"),
            "expect": {"type": ["string", "null"], "description": "기준 지표 예상치(숫자, 서로 다른 매체 2개). 없으면 null"},
            "expect_sources": SRC,
            "recent": {"type": ["string", "null"], "description": "기준 지표가 없는 요소(정책·정치·지정학)만: 최근 3일 일어난 일 한 줄, 과거형 사실, 예측 금지"},
            "recent_sources": SRC,
            "path": {"type": "array", "maxItems": 6, "items": CELL, "description": "관심사 칸에서 시작해 시장 칸(주식·업종·금리·환율·지수)에서 끝나는 칸 목록. 미국 경로의 '다음 날 코스피'는 코드가 붙임"},
            "ktype": {"type": ["string", "null"], "enum": list(KT) + [None], "description": "명세 §3-11 K표 번호. 맞는 게 없으면 null"},
            "read_articles": {"type": "array", "maxItems": 2, "description": "K표에 없을 때만: 기사들이 보는 쪽. 갈리면 갈래별 2개", "items": {
                "type": "object", "additionalProperties": False, "required": ["cond", "side", "sources"],
                "properties": {"cond": {"type": ["string", "null"], "description": "갈릴 때 조건('[다른 소식]이랑 같이 나오면'). 하나면 null"},
                               "side": {"type": "string", "enum": ["good", "bad"]}, "sources": SRC}}}}}}}}
SEARCH_BUDGET = """웹 검색 18회 배분 (v2 제안):
- 관심사 찾기·언급 세기·주목 이유: 4회 (요소별 넓게: 경제/중앙은행, 기업, 정책·지정학, 한국)
- 기준 지표 예상치: 2회 (7일 안 발표만)
- 칸마다 이번에 왜: 6회 (관심사 3개 × 2)
- 기사 연결 경로(하루 1개 관심사만): 4회 (연결 근거 + 회사·업종 숫자)
- 읽는 법 기사 근거(K표에 없을 때): 2회"""

# ── 검사기 ('없을 때' 규칙) ─────────────────────────────────────
def doms(srcs): return {urlparse(x.get("url", "")).netloc.removeprefix("www.") for x in srcs or []} - {""}
def bad(t): return [w for w in BANNED if w in (t or "")]
def moved(s): return s and (s.get("value") != s.get("prev") or s.get("yoy") != s.get("yoy_prev"))
def edge_ok(a, b): return (a, b) in EDGES

def check(draft, facts, errs):
    """AI 초안 → 통과한 관심사만. 각 변수의 '없을 때'는 정보설계 §2 그대로."""
    S, out, article_used = facts.get("series", {}), [], False
    for t in draft.get("topics", []):
        nm = t.get("name") or "?"
        el = ELEMENTS.get(t.get("element"))
        if not el: errs.append(f"[{nm}] 요소가 목록 밖 → 뺌"); continue
        if len(doms(t.get("mention_sources"))) < 3: errs.append(f"[{nm}] 언급 기사 매체 3개 미만 → 뺌"); continue
        t = dict(t)
        # 주목 이유: 사건 이름이면 매체 2개 (발표 이유는 조립 때 코드가 채움)
        if t.get("reason") and (len(doms(t.get("reason_sources"))) < 2 or bad(t["reason"]) or len(t["reason"]) > 14): errs.append(f"[{nm}] 주목 이유 빠짐"); t["reason"] = None
        # 기준 지표
        if el["base"] in ("series", "rate_base", "vix"):
            if t.get("base_key") not in S: errs.append(f"[{nm}] 기준 지표 수집값 없음 → 값 확인 전"); t["base_key"] = t.get("base_key") if t.get("base_key") in SERIES_NODE else None
        else: t["base_key"] = None
        if el["base"] == "number":
            n = t.get("base_num")
            if not n or len(doms(n.get("sources"))) < 2: errs.append(f"[{nm}] 회사 주가 매체 2개 미만 → 값 확인 전"); t["base_num"] = None
        else: t["base_num"] = None
        if t.get("expect") and len(doms(t.get("expect_sources"))) < 2: errs.append(f"[{nm}] 예상치 매체 2개 미만 → 지난번과 비교"); t["expect"] = None
        # 최근 사건 (기준 지표 없는 요소만)
        if el["base"] is None:
            r = t.get("recent") or ""
            why = "매체 2개 미만" if len(doms(t.get("recent_sources"))) < 2 else "예측 표현" if PREDICT.search(r) else "금지어" if bad(r) else "" if r else "없음"
            if why: errs.append(f"[{nm}] 최근 사건 빠짐({why}) → 관심사 뺌"); continue
        else: t["recent"] = None
        # 경로: 칸 규칙 ① 값이 있다 ② 연결 근거가 있다. 어긋나는 칸에서 자름. 기사 연결은 하루 1개 관심사만
        cells, prev, uses_article = [], None, False
        for c in (t.get("path") or [])[:6]:
            c = dict(c); k = c.get("key", "")
            basic_node = k in CFG["nodes"]
            if basic_node: c["num"] = None
            elif not (c.get("num") and len(doms(c["num"].get("sources"))) >= 2): errs.append(f"[{nm}] 칸 {k}: 값 없음(수집값·매체 2개 숫자) → 여기서 자름"); break
            if prev is not None:
                if edge_ok(prev, k): c["link_sources"] = []
                elif len(doms(c.get("link_sources"))) >= 2:
                    if el["path"] != "article" or article_used: errs.append(f"[{nm}] 칸 {k}: 기사 연결은 하루 1개 관심사만 → 여기서 자름"); break
                    uses_article = True
                else: errs.append(f"[{nm}] 칸 {prev}→{k}: 연결 근거 없음(기본 관계 밖, 매체 2개 미만) → 여기서 자름"); break
            # 이번에 왜 (§3-10-3)
            w = (c.get("why") or "").strip()
            if w:
                cause = re.sub(r"^같은 날\s*", "", w.rstrip(". ").removesuffix("때문이라고 봐요").strip())
                why = ("매체 2개 미만" if len(doms(c.get("why_sources"))) < 2 else "틀 아님" if not w.rstrip(". ").endswith("때문이라고 봐요")
                       else "원인 이름 없음" if len(cause) < 3 or EMPTYCAUSE.match(cause) else "예측 표현" if PREDICT.search(w)
                       else "금지어" if bad(w) else "숫자" if NUM.search(w) else "")
                if why: errs.append(f"[{nm}] 칸 {k} 이번에 왜 빠짐({why})"); w = ""
            c["why"] = w or None
            if c.get("link_prev") not in ("yes", "no", "unknown"): c["link_prev"] = "unknown"
            if c["link_prev"] == "yes" and prev in CFG["nodes"] and not moved(S.get(NODE_SERIES.get(t.get("country") or "us", {}).get(prev, ""))):
                errs.append(f"[{nm}] 칸 {k}: link_prev yes인데 위 칸이 실제로 안 움직임 → unknown"); c["link_prev"] = "unknown"
            if c["link_prev"] == "no" and not c["why"]: c["link_prev"] = "unknown"
            cells.append(c); prev = k
        while cells and not MARKET_END.match(cells[-1]["key"]): cells.pop()   # 끝은 시장 칸
        if (t.get("path") or []) and not cells: errs.append(f"[{nm}] 경로가 시장 칸까지 못 감 → ② 안 그림")
        if uses_article and cells: article_used = True
        t["path"] = cells
        # 읽는 법: K표 → 없으면 기사 근거(매체 2개, 갈래별)
        if t.get("ktype") and t["ktype"] not in KT: errs.append(f"[{nm}] ktype 표 밖 → 기사 근거로"); t["ktype"] = None
        ra = [a for a in (t.get("read_articles") or []) if len(doms(a.get("sources"))) >= 2 and not bad(a.get("cond"))]
        if len(ra) < len(t.get("read_articles") or []): errs.append(f"[{nm}] 읽는 법 기사 근거 일부 빠짐(매체 2개 미만)")
        t["read_articles"] = [] if t.get("ktype") else ra
        out.append(t)
    return out

# ── 조립 (코드가 채우는 값) ─────────────────────────────────────
def load_schedule():
    ev = []
    for p in (ROOT / "config").glob("schedule-*.json"): ev += json.loads(p.read_text(encoding="utf-8"))["events"]
    return ev
def md(d): return f"{int(d[5:7])}/{int(d[8:10])}"

def assemble(topics, facts, today, nowv=None):
    """검사 통과 관심사 → 순위·값·비교·다음 발표·가정 경로를 붙인 today.json "topics"."""
    S, SCH = facts.get("series", {}), sorted(load_schedule(), key=lambda r: r["date"])
    td = today if isinstance(today, dt.date) else dt.date.fromisoformat(str(today)[:10])
    def next_rel(t):   # {다음 발표}: 일정표 verified, 30일 안, 가장 가까운 것
        codes = {SERIES_SCHED.get(t.get("base_key"))} - {None}
        if t["element"] == "cb": codes |= {"FOMC" if t.get("country") == "us" else "BOK"}
        r = next((r for r in SCH if r["code"] in codes and r.get("verified") and td <= dt.date.fromisoformat(r["date"]) <= td + dt.timedelta(days=30)), None)
        return {"code": r["code"], "name": r["name"], "date": r["date"], "md": md(r["date"]), "source": r.get("source")} if r else None
    def val(k):
        x = S.get(k)
        if not x: return None
        ch = (x["yoy"] - x["yoy_prev"]) if x.get("yoy") is not None and x.get("yoy_prev") is not None else x["value"] - x["prev"]
        return {"key": k, "value": x["value"], "prev": x["prev"], "yoy": x.get("yoy"), "dir": "up" if ch > 0 else "down" if ch < 0 else None,
                "date": x["date"], "source": x.get("source"), **({"view": nowv.get(k)} if nowv and nowv.get(k) else {})}
    rows = []
    for t in topics:
        c = t.get("country") or "us"
        nr = next_rel(t) if ELEMENTS[t["element"]]["sched"] else None
        boost = bool(nr and (dt.date.fromisoformat(nr["date"]) - td).days <= 7)
        reason = f"{nr['name']} {nr['md']}" if boost else t.get("reason")
        if not reason: continue   # 주목 이유를 못 만들면 제외
        base = val(t["base_key"]) if t.get("base_key") else None
        cmp_ = None
        if base:
            if t.get("expect"): cmp_ = {"type": "expect", "expect": t["expect"], "sources": t["expect_sources"]}   # 높음/낮음 판단은 실제 발표값과 단위 맞춰 코드에서 (값 확정 후)
            elif base["dir"]: cmp_ = {"type": "prev", "text": "지난번보다 높음" if base["dir"] == "up" else "지난번보다 낮음"}
        path = []
        for i, cl in enumerate(t["path"]):
            k = cl["key"]; sk = NODE_SERIES[c].get(k) if k in CFG["nodes"] else None
            p = {"key": k, "name": NODE_NAME[c].get(k, cl["name"]), "value": val(sk) if sk else None, "num": cl.get("num"),
                 "link": "basic" if i and not cl.get("link_sources") else ("article" if i else None), "link_sources": cl.get("link_sources") or [],
                 "why_rule": WHY.get(f"{path[-1]['key']}>{k}") if i and not cl.get("link_sources") else None,
                 "why": cl.get("why"), "why_sources": cl.get("why_sources") or [], "link_prev": cl.get("link_prev", "unknown")}
            if isinstance(p["why_rule"], dict): p["why_rule"] = p["why_rule"].get(c)
            path.append(p)
        if path and c == "us" and path[-1]["key"] != "kospi":   # 미국 경로 끝 = 다음 날 코스피 (기본 관계 14번)
            path.append({"key": "kospi", "name": "코스피", "value": val("kospi"), "num": None, "link": "basic", "link_sources": [], "why_rule": WHY.get("stock>kospi"),
                         "why": None, "why_sources": [], "link_prev": "unknown", "next_day": True})
        # 읽는 법
        K = KT.get(t.get("ktype")) if t.get("ktype") else None
        read = ({"type": "k", "k": t["ktype"], "sure": K.get("sure"), "conds": K.get("conds"), "none": K.get("none")} if K
                else {"type": "articles", "items": t["read_articles"]} if t.get("read_articles") else None)
        # 실제로는: 읽는 법이 한 쪽이고 마지막 시장 칸이 반대로 움직였으면
        side = (read or {}).get("sure") or (read["items"][0]["side"] if read and read["type"] == "articles" and len(read["items"]) == 1 else None)
        end = next((p for p in reversed(path) if p["value"] and p["key"] in ("stock", "kospi")), None)
        actual = None
        if side and end and end["value"]["dir"] and end["value"]["dir"] != ("up" if side == "good" else "down"):
            actual = {"name": end["name"], "dir": end["value"]["dir"]}
        rows.append({"name": t["name"], "element": t["element"], "country": t.get("country"), "reason": reason, "reason_sources": [] if boost else t.get("reason_sources") or [],
                     "mentions": len(doms(t["mention_sources"])), "boost": boost, "base": base, "base_num": t.get("base_num"), "compare": cmp_,
                     "recent": t.get("recent"), "recent_sources": t.get("recent_sources") or [], "path": path, "read": read, "actual": actual, "next": nr,
                     "sources": t["mention_sources"]})
    # 순위: 언급 매체 수 → 7일 안 발표면 한 칸 올림 → 같으면 가까운 발표
    rows.sort(key=lambda r: (-r["mentions"], r["next"]["date"] if r["next"] else "9999"))
    for i in range(1, len(rows)):
        if rows[i]["boost"] and not rows[i - 1]["boost"]: rows[i - 1], rows[i] = rows[i], rows[i - 1]
    for i, r in enumerate(rows[:3]): r["rank"] = i + 1
    return rows[:3]

def export():
    (ROOT / "config" / "draft-schema-v2.json").write_text(json.dumps(SCHEMA, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    export(); print(SEARCH_BUDGET)
