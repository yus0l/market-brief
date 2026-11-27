"""키 없이 조립·검사 경로를 확인하는 테스트 (11/26 한국은행 사건, 출처 있는 값만)."""
import json, sys, pathlib, datetime as dt
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build import assemble, upcoming, load_schedule
from collect import fmt_variants
from validate import validate
today = dt.date(2026, 11, 26)
S = lambda n, node, v, p, d, u: {"name": n, "node": node, "value": v, "prev": p, "date": d, "unit": u, "source": {"name": "test", "url": "https://example.org"}}
facts = {"series": {"kr_base": S("기준금리", "rate", 3.25, 3.00, "2026-11-26", "%"), "kospi": S("코스피", "stock", 4711.21, 4697.6, "2026-11-26", "")}, "errors": []}
facts["allowed_numbers"] = sorted({x for s in facts["series"].values() for x in fmt_variants(s["value"]) | fmt_variants(s["prev"]) | fmt_variants(s["value"] - s["prev"]) | fmt_variants((s["value"] / s["prev"] - 1) * 100)})
U = [{"name": "a", "url": f"https://news.example/{i}"} for i in range(3)]
st = lambda node, dir=None, us=None, kr=None: {"node": node, "dir": dir, "us": us, "kr": kr}
draft = {"interests": [{"key": "cpi", "mention": "많음", "dir": "up", "sources": U}, {"key": "rate", "mention": "보통", "dir": "up", "sources": U},
                       {"key": "job", "mention": "적음", "dir": "down", "sources": U[:1]}],
  "events": [
   {"id": "bok", "type": "E1", "chip": "한국은행 금리", "head": "한국은행 기준금리 인상", "kind": "done", "schedule_code": "BOK", "expect": "예상대로",
    "actual_src": "https://www.etoday.co.kr/news/view/2652786", "expect_src": "https://www.mt.co.kr/economy/2026/11/22/2026112009065366740", "spread": True,
    "real": [st("rate", kr="up")], "realPath": [], "next": ["fx", "cpi"],
    "opts": {"a": {"label": "물가가 잡히면", "path": [["rate", "fx"], ["fx", "cpi"], ["rate", "cpi"]], "state": [st("fx", "down"), st("cpi", "down")], "cond": [{"text": "금리", "dir": "up", "done": True}, {"text": "원화 강세", "dir": None, "done": False}], "out": ""},
             "b": {"label": "물가가 안 잡히면", "path": [["cpi", "rate"], ["rate", "stock"]], "state": [st("cpi", "up"), st("stock", kr="down")], "cond": [{"text": "물가", "dir": "up", "done": False}, {"text": "추가 인상", "dir": None, "done": False}], "out": ""}},
    "judge_keys": [{"key": "kospi", "side_if_up": "good"}, {"key": "usdkrw", "side_if_up": "bad"}],
    "confirm": [{"label": "먼저", "what": "원/달러 환율", "when": "며칠~몇 주"}, {"label": "최종", "what": "1월 금통위", "when": "1/14"}],
    "sources": [{"name": "이투데이", "url": "https://www.etoday.co.kr/news/view/2652786"}, {"name": "서울신문", "url": "https://www.seoul.co.kr/news/economy/finance/2026/11/26/20261126500036"}]},
   {"id": "bad", "type": "E8", "chip": "나쁜 예", "head": "삼성전자 매수 유력", "kind": "done", "schedule_code": None, "expect": None, "actual_src": None, "expect_src": None, "spread": False,
    "real": [st("stock", us="up")], "realPath": [["oil", "stock"]], "next": [], "opts": {"a": {"label": "x", "path": [], "state": [], "cond": [{"text": "x", "dir": None, "done": False}], "out": "12.5% 오를 것"},
    "b": {"label": "y", "path": [], "state": [], "cond": [{"text": "y", "dir": None, "done": False}], "out": ""}}, "judge_keys": [], "confirm": [], "sources": [{"name": "a", "url": "u"}]}]}
out = assemble(today, facts, draft, upcoming(load_schedule(), today), None)
final, errs = validate(out, facts)
print("사건", [e["id"] for e in final["events"]], "| 관심사", [(x["rank"], x["name"], x["reason"]["label"]) for x in final["interests"]])
e0 = out["events"][0]; print("결과 줄:", e0["result"]["text"]); print("판단 재료:", e0["judge"]["items"])
print("\n".join(errs))
pathlib.Path(__file__).resolve().parent.parent.joinpath("web/mock/pipeline-test.json").write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
