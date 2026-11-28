"""v4 수집 — 1년 일별 값(표준편차 '크게' 판단용) · GDELT 기사 양(주목도) · SEC 엔비디아 재무.

  python3 pipeline/v4_data.py history        # FRED·ECOS 1년+ → data/v4/history.json  (Actions: FRED_API_KEY·ECOS_API_KEY)
  python3 pipeline/v4_data.py sec            # SEC companyfacts → data/v4/nvda.json    (Actions: SEC_USER_AGENT — 값은 Secrets에만)
  python3 pipeline/v4_data.py attention F    # F(draft)의 후보마다 GDELT 기사 양 → F에 attention 붙임 + data/v4/attention.json에 쌓음

'크게' = 하루 변화가 지난 1년(252거래일) 하루 변화 표준편차의 2배 이상 (정보설계 v4, 이벤트 스터디 방식).
주목도 = 미국·한국 매체 기사 양이 평소보다 표준편차 2배 이상 (GDELT). 1년치를 못 받으면 3개월 기준, 매일 쌓아 1년 되면 1년 기준 (기획 11/28).
"""
import csv, datetime as dt, io, json, math, os, pathlib, statistics as st, sys, time, urllib.parse, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from v4_cells import CELLS

ROOT = pathlib.Path(__file__).resolve().parent.parent
V4 = ROOT / "data" / "v4"
WIN, K = 252, 2.0          # 1년 거래일, 표준편차 배수 (사례가 너무 잦거나 드물면 K 조정 — 정보설계 v4)

def get(url, ua="market-brief-v4", raw=False, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read().decode("utf-8")
    return b if raw else json.loads(b)

# ── 1년 일별 값 ─────────────────────────────────────────────
def fred_hist(sid, key, start):
    if key:
        q = urllib.parse.urlencode({"series_id": sid, "api_key": key, "file_type": "json", "observation_start": start})
        return [(o["date"], float(o["value"])) for o in get(f"https://api.stlouisfed.org/fred/series/observations?{q}")["observations"] if o["value"] not in (".", "")]
    # 키 없을 때(로컬 시험): FRED 공개 CSV
    t = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}", ua="curl/8.7.1", raw=True)   # 이 CSV는 낯선 User-Agent면 응답이 없음
    return [(r[0], float(r[1])) for r in csv.reader(io.StringIO(t)) if r and r[0][:1] == "2" and r[1] not in ("", ".")]

def ecos_hist(table, item, key, start, end):
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/1000/{table}/D/{start.replace('-', '')}/{end.replace('-', '')}/{item}"
    rows = get(url).get("StatisticSearch", {}).get("row", [])
    return [(f"{r['TIME'][:4]}-{r['TIME'][4:6]}-{r['TIME'][6:]}", float(r["DATA_VALUE"])) for r in rows]

def changes(pts, calc):
    """[(날짜, 값)] → [(날짜, 하루 변화)]. diff = %p, log = %(로그 수익률×100)."""
    return [(pts[i][0], (pts[i][1] - pts[i - 1][1]) if calc == "diff" else math.log(pts[i][1] / pts[i - 1][1]) * 100) for i in range(1, len(pts))]

def big_days(pts, calc):
    """하루 변화가 그날 이전 252거래일 표준편차 × K 이상인 날. → [(날짜, 변화, σ, 방향)] 와 오늘 σ."""
    ch = changes(pts, calc); out = []
    for i in range(WIN, len(ch)):
        sd = st.pstdev([c for _, c in ch[i - WIN:i]])
        if sd and abs(ch[i][1]) >= K * sd: out.append({"date": ch[i][0], "chg": round(ch[i][1], 4), "sd": round(sd, 4), "dir": 1 if ch[i][1] > 0 else -1})
    sd_now = st.pstdev([c for _, c in ch[-WIN:]]) if len(ch) >= WIN else None
    return out, sd_now

def history(today=None, since=None, name="history.json"):
    """since가 있으면 지난 사례 채우기용: since 이전 1년(표준편차)부터 전부 남김 → data/v4/history-backfill.json"""
    today = today or dt.date.today()
    start = ((dt.date.fromisoformat(since) if since else today) - dt.timedelta(days=560 if not since else 400)).isoformat()
    keep_from = since or (today - dt.timedelta(days=200)).isoformat()
    fk, ek = os.environ.get("FRED_API_KEY"), os.environ.get("ECOS_API_KEY")
    out, errs = {}, []
    for k, c in CELLS.items():
        if c["calc"] is None: continue
        try:
            pts = fred_hist(c["sid"], fk, start) if c["src"] == "fred" else ecos_hist(*c["sid"], ek, start, today.isoformat()) if ek else None
        except Exception as e:
            pts = None; errs.append(f"{k}: {type(e).__name__} {e}")
        if not pts or len(pts) < WIN + 2:
            errs.append(f"{k}: 값 {len(pts or [])}개 — 1년 표준편차 계산 불가" + ("" if pts or c["src"] != "ecos" or ek else " (ECOS_API_KEY 없음)")); continue
        big, sd = big_days(pts, c["calc"])
        out[k] = {"points": [p for p in pts if p[0] >= keep_from] if since else pts[-200:], "pre": [p for p in pts if p[0] < keep_from][-5:],
                  "sd": sd, "calc": c["calc"], "big": [b for b in big if b["date"] >= keep_from],
                  "source": {"name": f"FRED {c['sid']}" if c["src"] == "fred" else f"한국은행 ECOS {c['sid'][0]}",
                             "url": f"https://fred.stlouisfed.org/series/{c['sid']}" if c["src"] == "fred" else "https://ecos.bok.or.kr/"}}
    V4.mkdir(parents=True, exist_ok=True)
    doc = {"date": today.isoformat(), "window": WIN, "k": K, "cells": out, "errors": errs}
    (V4 / name).write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return doc

# ── GDELT 기사 양 ───────────────────────────────────────────
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
COUNTRIES = ["US", "KS"]           # GDELT 나라 코드(FIPS): 미국 US, 한국 KS

def gdelt_daily(query, country, span):
    """그 나라 매체의 하루 기사 수 [(날짜, 수)]. 요청 제한(5초에 1번)을 지킨다."""
    q = urllib.parse.urlencode({"query": f"{query} sourcecountry:{country}", "mode": "timelinevolraw", "format": "json", "timespan": span})
    for wait in (10, 40, 120):   # 공식 한도는 5초에 1번이지만 GitHub 공용 IP에선 더 막힘 (11/28 gdelt-check)
        time.sleep(wait)
        try: d = get(f"{GDELT}?{q}", timeout=60); break
        except urllib.error.HTTPError as e:
            if e.code != 429: raise
    else: raise RuntimeError("GDELT 429 (요청 제한) 3번")
    by = {}
    for p in (d.get("timeline") or [{}])[0].get("data", []):
        day = f"{p['date'][:4]}-{p['date'][4:6]}-{p['date'][6:8]}"; by[day] = by.get(day, 0) + int(p["value"])
    return sorted(by.items())

def attention_one(key, query, store, today):
    """후보 하나 → {z, base, today, mean, sd}. 받은 값은 store(data/v4/attention.json)에 날짜별로 쌓는다."""
    rec = store.setdefault(key, {"query": query, "days": {}})
    rec["query"] = query
    for c in COUNTRIES:
        pts = None
        for span in ("12m", "3m"):
            try:
                pts = gdelt_daily(query, c, span)
                if len(pts) >= 60: break
            except Exception as e:
                rec.setdefault("errors", []).append(f"{today} {c} {span}: {e}")
        for d, n in pts or []:
            rec["days"].setdefault(d, {})[c] = n
        print(f"  {key} {c}: {len(pts or [])}일, 마지막 {(pts or [[None]])[-1][0]}", flush=True)
    return att_z(rec, today)

def att_z(rec, today):
    """쌓인 하루 기사 수(rec["days"]) → today 공개 기준 주목도. 지난 사례 채우기도 이걸로 (GDELT 다시 안 부름)"""
    tot = {d: sum(v.get(c, 0) for c in COUNTRIES) for d, v in rec["days"].items() if all(c in v for c in COUNTRIES)}
    # 공개(08:00) 전 마지막으로 다 찬 하루 = 어제. GDELT가 하루 늦으면 그제까지 (그보다 오래되면 판단 안 함)
    y = next((d for d in ((today - dt.timedelta(days=i)).isoformat() for i in (1, 2)) if d in tot), None)
    if not y: return {"z": None, "why": "어제·그제 기사 수를 못 받음"}
    hist = [n for d, n in sorted(tot.items()) if d < y][-365:]
    base = "1년" if len(hist) >= 300 else "3개월" if len(hist) >= 60 else None
    if not base: return {"z": None, "why": f"평소 값이 {len(hist)}일뿐"}
    hist = hist if base == "1년" else hist[-90:]
    m, sd = st.mean(hist), st.pstdev(hist)
    z = (tot[y] - m) / sd if sd else None
    return {"z": round(z, 2) if z is not None else None, "base": base, "day": y, "count": tot[y], "mean": round(m, 1), "sd": round(sd, 1), "pass": bool(z is not None and z >= K)}

def attention(draft_path, today=None):
    today = today or dt.date.today()
    p = pathlib.Path(draft_path); draft = json.loads(p.read_text(encoding="utf-8"))
    sp = V4 / "attention.json"; store = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    for c in draft.get("candidates", []):
        if c.get("gdelt_query"): c["attention"] = attention_one(c["key"], c["gdelt_query"], store, today)
    V4.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(store, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    p.write_text(json.dumps(draft, ensure_ascii=False, indent=1), encoding="utf-8")
    return [(c["key"], c.get("attention")) for c in draft.get("candidates", [])]

# ── SEC 엔비디아 재무 ───────────────────────────────────────
NVDA_CIK = "0001045810"
def sec():
    ua = " ".join((os.environ.get("SEC_USER_AGENT") or "").split())   # Secrets 값에 줄바꿈이 섞이면 헤더 오류 → 공백 하나로
    if not ua: print("SEC_USER_AGENT 없음 — 건너뜀"); return None
    d = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{NVDA_CIK}.json", ua=ua)
    gaap, out = d["facts"]["us-gaap"], {}
    for k, c in CELLS.items():
        if c["src"] != "sec": continue
        for tag in (c["sid"], "RevenueFromContractWithCustomerExcludingAssessedTax") if c["sid"] == "Revenues" else (c["sid"],):
            rows = [r for r in gaap.get(tag, {}).get("units", {}).get("USD", []) if r.get("fp", "").startswith("Q") or r.get("form") == "10-K"]
            q = sorted([r for r in rows if r.get("start") and (dt.date.fromisoformat(r["end"]) - dt.date.fromisoformat(r["start"])).days < 100], key=lambda r: (r["end"], r["filed"]))
            if len(q) >= 2:
                last = {r["end"]: r for r in q}                # 같은 분기 여러 번 공시 → 가장 늦게 낸 값
                ends = sorted(last)
                a, b = last[ends[-1]], last[ends[-2]]
                out[k] = {"value": a["val"], "prev": b["val"], "end": a["end"], "filed": a["filed"], "form": a["form"], "tag": tag,
                          "source": {"name": f"SEC EDGAR {a['form']} ({a['filed']})", "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={NVDA_CIK}&type=10-Q"}}
                break
    V4.mkdir(parents=True, exist_ok=True)
    (V4 / "nvda.json").write_text(json.dumps({"date": dt.date.today().isoformat(), "cells": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    return out

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "history":
        d = history(); print(len(d["cells"]), "cells;", "\n".join(d["errors"]))
    elif cmd == "history-backfill":   # python3 pipeline/v4_data.py history-backfill 2026-02-01
        d = history(since=sys.argv[2], name="history-backfill.json"); print(len(d["cells"]), "cells;", "\n".join(d["errors"]))
    elif cmd == "attention-asof":     # python3 pipeline/v4_data.py attention-asof DRAFT 2026-03-02  (지난 사례: 그날 공개 기준)
        print(attention(sys.argv[2], dt.date.fromisoformat(sys.argv[3])))
    elif cmd == "sec": print(json.dumps(sec(), ensure_ascii=False)[:400])
    elif cmd == "attention": print(attention(sys.argv[2]))
    elif cmd == "gdelt-check":   # 1년치(12m)가 실제로 받아지는지 — 기획 결정 "안 되면 3개월 기준" 판단용
        out = {}
        for c in COUNTRIES:
            for span in ("12m", "3m"):
                try: pts = gdelt_daily("inflation", c, span); out[f"{c}-{span}"] = {"days": len(pts), "first": pts[0][0] if pts else None}
                except Exception as e: out[f"{c}-{span}"] = {"error": str(e)}
        V4.mkdir(parents=True, exist_ok=True)
        (V4 / "gdelt-check.json").write_text(json.dumps({"date": dt.date.today().isoformat(), **out}, ensure_ascii=False, indent=1), encoding="utf-8"); print(out)
    else: print(__doc__)
