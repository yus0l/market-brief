"""v2 검사기·조립 확인 (01-정보설계 v3 '없을 때' 규칙)."""
import json, sys, pathlib, datetime as dt
sys.path.insert(0, str(pathlib.Path(__file__).parent)); import v2
F = json.loads((v2.ROOT / "data" / "facts-2026-11-27.json").read_text(encoding="utf-8"))
U = lambda *d: [{"name": x, "url": f"https://{x}.com/a"} for x in d]
C = lambda key, name, **k: dict({"key": key, "name": name, "num": None, "link_sources": [], "why": None, "why_sources": [], "link_prev": "unknown"}, **k)
draft = {"date": "2026-11-27", "topics": [
  {"name": "미국 물가", "element": "econ", "country": "us", "mention_sources": U("a", "b", "c"), "reason": None, "reason_sources": [], "base_key": "us_cpi", "base_num": None,
   "expect": None, "expect_sources": [], "recent": None, "recent_sources": [], "ktype": "K1", "read_articles": [],
   "path": [C("cpi", "미국 물가"), C("rate", "x", why="미국 CPI 상승 때문이라고 봐요", why_sources=U("a", "b"), link_prev="yes"), C("stock", "x")]},
  {"name": "엔비디아 실적", "element": "company", "country": "us", "mention_sources": U("a", "b", "c", "d"), "reason": "엔비디아 실적 발표", "reason_sources": U("a", "b"), "base_key": None,
   "base_num": {"value": "181.2달러", "sources": U("a", "b")}, "expect": None, "expect_sources": [], "recent": None, "recent_sources": [], "ktype": "K11", "read_articles": [],
   "path": [C("co:엔비디아", "엔비디아 주가", num={"value": "181.2달러", "sources": U("a", "b")}),
            C("sector:반도체", "미국 반도체 업종", num={"value": "5,120", "sources": U("c", "d")}, link_sources=U("a", "c"), why="엔비디아 실적 발표 때문이라고 봐요", why_sources=U("a", "c"), link_prev="yes"),
            C("idx:나스닥", "나스닥", num={"value": "18,420", "sources": U("b", "d")}, link_sources=U("b", "d"), link_prev="unknown")]},
  {"name": "데이터센터 규제", "element": "policy", "country": "us", "mention_sources": U("a", "b", "c"), "reason": "규제 초안 공개", "reason_sources": U("a", "b"), "base_key": None, "base_num": None,
   "expect": None, "expect_sources": [], "recent": "미국 상무부가 데이터센터 전력 규제 초안을 냈어요", "recent_sources": U("a"), "ktype": None, "read_articles": [], "path": []},
  {"name": "관세", "element": "policy", "country": "us", "mention_sources": U("a", "b", "c"), "reason": "관세 발표", "reason_sources": U("a", "b"), "base_key": None, "base_num": None,
   "expect": None, "expect_sources": [], "recent": "미국이 관세 인상안을 발표했어요", "recent_sources": U("a", "b"), "ktype": None,
   "read_articles": [{"cond": None, "side": "bad", "sources": U("a", "b")}],
   "path": [C("px:구리", "구리 가격", num={"value": "4.1달러", "sources": U("a", "b")}), C("idx:나스닥", "나스닥", num={"value": "18,420", "sources": U("a", "b")}, link_sources=U("a", "b"))]}]}
errs = []
ok = v2.check(draft, F, errs)
print("\n".join(errs))
out = v2.assemble(ok, F, dt.date(2026, 11, 27))
for t in out: print(t["rank"], t["name"], t["reason"], [p["key"] for p in t["path"]], t["read"] and t["read"]["type"], t["next"] and t["next"]["md"])
assert [t["name"] for t in ok] == ["미국 물가", "엔비디아 실적", "관세"], "정책(최근 사건 매체 1개)은 빠져야"
assert ok[2]["path"] == [], "기사 연결은 하루 1개 관심사만 → 관세 경로 잘림"
(v2.ROOT / "web" / "mock" / "v2-topics.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("ok")
