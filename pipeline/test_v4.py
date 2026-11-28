"""v4 검사기 시험 — 키·네트워크 없이. python3 pipeline/test_v4.py
가짜 1년 값으로 '크게' 판단·연결표 방향·한국 영향·기록 전환·태그를 확인한다."""
import datetime as dt, json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import v4, v4_data
from v4_cells import find_link, load_links

T = dt.date(2026, 11, 28)
tmp = pathlib.Path(tempfile.mkdtemp()); v4.V4D, v4.V4W = tmp / "data", tmp / "web"; v4.V4D.mkdir(); v4.V4W.mkdir()

def series(jump_day, jump, base, calc):
    """잔잔한 300일 + jump_day에 큰 변화. 날짜는 평일만."""
    d, pts, v, i = dt.date(2025, 9, 1), [], base, 0
    while d <= T:
        if d.weekday() < 5:
            step = (0.01 if i % 2 else -0.01) * (1 if calc == "diff" else base / 100)
            v = v + step + (jump if d.isoformat() == jump_day else 0); pts.append((d.isoformat(), round(v, 4))); i += 1
        d += dt.timedelta(days=1)
    big, sd = v4_data.big_days(pts, calc)
    return {"points": pts, "sd": sd, "calc": calc, "big": big, "source": {"name": "test", "url": "https://x"}}

H = {"us_10y": series("2026-11-20", +0.3, 4.0, "diff"), "sp500": series("2026-11-23", -300, 7000, "log"),
     "usdkrw": series("2026-11-24", +40, 1400, "log"), "kospi": series("2026-11-10", 0, 4700, "log"), "vix": series("2026-11-10", 0, 20, "log")}
(v4.V4D / "history.json").write_text(json.dumps({"cells": H}), encoding="utf-8")

S2 = [{"name": "A", "url": "https://a.com/1"}, {"name": "B", "url": "https://b.com/1"}]
def draft(**kw):
    c = {"key": "k", "name": "미국 물가 급등", "kind": "macro", "date": "2026-11-19", "sources": S2, "gdelt_query": "q",
         "attention": {"pass": True, "z": 3.0, "base": "3개월"}}
    c.update(kw.pop("cand", {}))
    F = {"start_reason": {"text": "물가가 예상보다 크게 올랐어요", "sources": S2},
         "nodes": [{"id": "n1", "cell": "us_10y", "parents": ["start"], "reason": "금리 인하가 늦어질 거란 기사가 늘며 금리가 올랐어요", "reason_sources": S2},
                   {"id": "n2", "cell": "sp500", "parents": ["n1"], "reason": "돈 빌리는 비용이 늘 거란 걱정에 주식이 내렸어요", "reason_sources": S2},
                   {"id": "n3", "cell": "usdkrw", "parents": ["n1"], "reason": "달러가 강해지며 원/달러가 올랐어요", "reason_sources": S2}],
         "future": {"release_code": None, "header": "원화가 더 약해진다면?", "start": {"cell": "usdkrw", "dir": "up"},
                    "nodes": [{"id": "f1", "cell": "kospi", "parent": "fstart", "link": 11, "reason": "외국인이 팔기 쉬워서요"}]}}
    F.update(kw.pop("flow", {}))
    return {"date": T.isoformat(), "candidates": [c], "flows": {"k": F}}

def run(d):
    p = tmp / "d.json"; p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    log = v4.build(p, T); out = json.loads((v4.V4W / "cases.json").read_text(encoding="utf-8")); return log, out

fails = 0
def ok(name, cond):
    global fails
    print(("ok  " if cond else "FAIL"), name); fails += (not cond)

# 1. 정상: 사례 1개, 칸 3개(+시작), 앞으로 코스피 = 연결 11(약함) → 미지수
log, out = run(draft())
c = out["cases"][0] if out["cases"] else {}
ok("사례 생성", log["passed"] == ["2026-11-19-k"] and c.get("status") == "live")
ok("칸 3개 + 시작", [n["id"] for n in c.get("flow", [])] == ["start", "n1", "n2", "n3"])
ok("크게 움직인 날 = 11/20", c["flow"][1]["date"] == "2026-11-20")
ok("연결표로 이어진 칸(금리↑→주식↓ = 5번)", c["flow"][2]["link"] == 5)
ok("앞으로 코스피 = 미지수(연결 11 약함)", c["future"]["nodes"][0]["tag"] == "unknown")
ok("발표 없음 → 기본 타이틀", c["future"]["title"] == "앞으로 이렇게 바뀔 수 있어요")

# 2. 이유 없는 칸은 빠진다
_, out = run(draft(flow={"nodes": [{"id": "n1", "cell": "us_10y", "parents": ["start"], "reason": "", "reason_sources": S2},
                                   {"id": "n3", "cell": "usdkrw", "parents": ["start"], "reason": "달러가 강해지며 원/달러가 올랐어요", "reason_sources": S2}]}))
ok("이유 없는 칸 제외", [n["id"] for n in out["cases"][0]["flow"]] == ["start", "n3"])

# 2-2. 연결표만 있고 이유 매체 2곳이 없으면 빠진다 (기획 11/28: 이유 근거 = 매체 2곳만)
_, out = run(draft(flow={"nodes": [{"id": "n1", "cell": "us_10y", "parents": ["start"], "reason": "금리 인하가 늦어질 거란 기사가 늘며 금리가 올랐어요", "reason_sources": S2},
                                   {"id": "n2", "cell": "sp500", "parents": ["n1"], "reason": "돈 빌리는 비용이 늘 거란 걱정에 주식이 내렸어요"},
                                   {"id": "n3", "cell": "usdkrw", "parents": ["n1"], "reason": "달러가 강해지며 원/달러가 올랐어요", "reason_sources": S2}]}))
ok("연결표만 있는 이유 → 칸 제외", [n["id"] for n in out["cases"][0]["flow"]] == ["start", "n1", "n3"])

# 3. 연결표 방향이 안 맞고 매체 2곳도 없으면 빠진다 (금리↑ → 주식↑ 이라고 우김)
L = find_link("rate_us", 1, "stock_us", 1, load_links())
ok("연결표: 금리↑→주식↑ 없음", L is None)

# 4. 크게 움직인 날이 없는 칸은 빠진다 (vix는 잔잔)
_, out = run(draft(flow={"nodes": [{"id": "n1", "cell": "vix", "parents": ["start"], "reason": "불안이 커져 올랐어요", "reason_sources": S2},
                                   {"id": "n3", "cell": "usdkrw", "parents": ["start"], "reason": "달러가 강해지며 원/달러가 올랐어요", "reason_sources": S2}]}))
ok("크게 안 움직인 칸 제외", "n1" not in [n["id"] for n in out["cases"][0]["flow"]])

# 5. 한국 칸까지 안 이어지면 사례 아님
log, out = run(draft(flow={"nodes": [{"id": "n1", "cell": "us_10y", "parents": ["start"], "reason": "금리 인하가 늦어질 거란 기사가 늘며 금리가 올랐어요", "reason_sources": S2}], "future": None}))
ok("한국 영향 없음 → 사례 아님 + 앞 사례는 기록으로", not log["passed"] and out["cases"][0]["status"] == "record")

# 6. 주목도 못 넘으면 사례 아님
log, _ = run(draft(cand={"key": "k2", "attention": {"pass": False, "z": 1.2, "base": "3개월"}}))
ok("주목도 미달 → 사례 아님", not log["passed"])

# 7. 다시 넘으면 기존 사례에 날짜 이어 붙임
log, out = run(draft(cand={"same_as": "2026-11-19-k"}))
c = next(x for x in out["cases"] if x["id"] == "2026-11-19-k")
ok("다시 확대 → 날짜 추가", c["status"] == "live" and len(c["event"]["dates"]) == 2 and c["event"]["dates"][1]["label"] == "다시 확대")

# 8. 사건 출처 1곳·해석 이름은 사례 아님
log, _ = run(draft(cand={"key": "k3", "sources": S2[:1]})); ok("사건 출처 1곳 → 아님", not log["passed"])

# 9. 조사
ok("조사 가/이", v4.josa("미국 CPI") == "미국 CPI가" and v4.josa("미국 물가 발표") == "미국 물가 발표가" and v4.josa("금통위 결정") == "금통위 결정이")

# 10. 오늘의 이슈: 사례가 없는 날 z 1위 · 1배 칸 · 목록에 안 쌓임
for k in H: H[k]["notable"] = v4_data.big_days(H[k]["points"], H[k]["calc"], 1)[0]
(v4.V4D / "history.json").write_text(json.dumps({"cells": H}), encoding="utf-8")
(v4.V4W / "cases.json").unlink()
d = draft(cand={"attention": {"pass": False, "z": 1.2, "base": "3개월"}})
d["candidates"].append(dict(d["candidates"][0], key="k9", name="미국 고용 발표", attention={"pass": False, "z": 0.4}))
d["flows"]["k9"] = d["flows"]["k"]
log, out = run(d)
I = out.get("issue") or {}
ok("오늘의 이슈 = z 1위", not log["passed"] and I.get("event", {}).get("name") == "미국 물가 급등" and out["first"] == I.get("id"))
ok("오늘의 이슈는 목록에 안 쌓임", out["cases"] == [])
ok("오늘의 이슈 칸 = 1배 이상", [n["id"] for n in I.get("flow", [])][:2] == ["start", "n1"])
rows, _ = v4.precheck(d, T); ok("precheck: 사례 없으면 이슈 후보 흐름 쓰기", [r["write_flow"] for r in rows] == ["issue", "issue"])

print("\n실패", fails); sys.exit(1 if fails else 0)
