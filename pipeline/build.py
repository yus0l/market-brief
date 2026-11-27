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
        ev = next((u for u in upc if u["code"] in c["events"]), None)
        items.append(dict(x, s=score[x["mention"]], ev=ev))
    items = [x for x in items if x["mention"] != "적음" or x["ev"]]            # 언급이 거의 없으면 숨김
    items.sort(key=lambda x: (-x["s"], x["ev"]["dday"] if x["ev"] else 99))
    for i in range(1, len(items)):                                             # 발표 가산: 한 단계 올림
        if items[i]["ev"] and not items[i - 1]["ev"]: items[i - 1], items[i] = items[i], items[i - 1]
    out = []
    for i, x in enumerate(items):
        c = CFG["interests"][x["key"]]; boosted = x["ev"] and (i == 0 or items[i - 1]["s"] >= x["s"]) and x["s"] < max(y["s"] for y in items)
        reason = ({"type": "event", "label": f"{x['ev']['name']} D-{x['ev']['dday']}"} if boosted
                  else {"type": "mention", "label": "가장 많이 언급" if i == 0 else f"언급 {x['mention']}"})
        out.append({"key": x["key"], "node": c["node"], "name": c["name"], "rank": i + 1, "reason": reason, "upSide": c["upSide"],
                    "sentence": c["sentence"][x["dir"]], "explain": c["explain"], "sources": x["sources"]})
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
              "judge": {"interest": {}, "items": [judge_row(facts, j["key"], j["side_if_up"]) for j in (e["judge_keys"] or default_judge(facts, e))]},
              "lean": None, "confirm": [dict(c, done=False, when=md(c.get("when")), date=iso(c.get("when"), today)) for c in e["confirm"]], "sources": e["sources"],
              "sectorTab": "kr" if e["type"] in ("E4",) else "us", "sectors": SECT.get(e["type"])}
        if e["kind"] == "upcoming": ev["top"] = f"예상치 확인 전" if not e["expect_src"] else "예상치 출처 있음"
        if e["kind"] == "done":
            s = facts["series"].get(EVENT_SERIES.get(e.get("schedule_code") or "", ""), None)
            nums = f"{s['prev']:.2f}{s['unit']} → {s['value']:.2f}{s['unit']}" if s else ""
            exp = e["expect"] + (" · 전망이 갈렸어요" if e["spread"] else "") if e["expect"] else ""
            d = next(iter(ev["real"].values()), {}); d = d.get("dir") or d.get("kr") or d.get("us")
            ev["result"] = {"dir": d, "text": " · ".join(x for x in (nums, exp) if x) or None, "expect": e["expect"],
                            "actual_src": e["actual_src"], "expect_src": e["expect_src"]}
        ev["sub"] = sub_for(ev["date"], today.isoformat())
        events.append(ev)
    # 지난 사건 중 결과 확인(먼저/최종)이 아직 남은 것은 계속 보여줌 (02-UX 칩 규칙)
    have = {x["id"] for x in events}
    for y in (yesterday or {}).get("events", []):
        if y["id"] in have or y["kind"] != "done" or not y.get("date"): continue
        if any((c.get("date") or "") >= today.isoformat() for c in y.get("confirm", [])):
            events.append(dict(y, sub=sub_for(y["date"], today.isoformat())))
    t0 = today.isoformat()
    events.sort(key=lambda x: (0, "") if x["kind"] == "done" and x["date"] == t0 else (1, "".join(chr(0x10FFFF - ord(ch)) for ch in x["date"])) if x["kind"] == "done" else (2, x["date"]))
    ints = rank_interests(draft["interests"], upc)
    status = {"delayed": None, "quiet": not any(e["kind"] == "done" for e in events), "split": None,
              "closed": {"us": False, "kr": False}, "rankChange": None}
    sp, ks = facts["series"].get("sp500"), facts["series"].get("kospi")
    if sp and ks and (sp["value"] - sp["prev"]) * (ks["value"] - ks["prev"]) < 0:
        status["split"] = {"us": "up" if sp["value"] > sp["prev"] else "down", "kr": "up" if ks["value"] > ks["prev"] else "down"}
    daily = [s["date"] for k, s in facts["series"].items() if len(s["date"]) == 10]
    if not daily or max(daily) < (today - dt.timedelta(days=4)).isoformat(): status["delayed"] = max(daily) if daily else "어제"
    if yesterday and yesterday.get("interests") and ints and yesterday["interests"][0]["key"] != ints[0]["key"]:
        status["rankChange"] = {"from": yesterday["interests"][0]["name"], "to": ints[0]["name"]}
    return {"date": today.isoformat(), "asof": f"{today.month}/{today.day} 08:00", "mock": False,
            "status": status, "interests": ints, "events": events}

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
    out = assemble(today, facts, draft, upc, json.loads(yp.read_text(encoding="utf-8")) if yp.exists() else None)
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
