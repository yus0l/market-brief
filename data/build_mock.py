"""샘플 today.json + 상태별 샘플 만들기 (실제 파이프라인이 붙기 전 화면 확인용).
원칙: 출처 있는 값만 숫자로 넣고, 모르면 null(화면: "값 확인 전")."""
import json, copy, pathlib
OUT = pathlib.Path(__file__).resolve().parent.parent / "web"

SRC_BOK = [
  {"name": "이투데이 · 한은 기준금리 3.25% 인상", "url": "https://www.etoday.co.kr/news/view/2652786"},
  {"name": "서울신문 · 금통위 11월", "url": "https://www.seoul.co.kr/news/economy/finance/2026/11/26/20261126500036"},
  {"name": "머니투데이 · 전문가 전망(전원 인상)", "url": "https://www.mt.co.kr/economy/2026/11/22/2026112009065366740"},
  {"name": "이투데이 · 채권시장 설문", "url": "https://www.etoday.co.kr/news/view/2652153"},
  {"name": "코스피 11/26 종가", "url": "https://supple.kr/news/cmwx70io5p880kwp8a27djm85"},
]
# 업종 표: 01-기획-표/업종-민감도.md (E1 금리 ▲ 등). 막대·퍼센트 없이 더 크게 / 덜 / 반대로
SEC = {
  "E1": {"us": [["더 크게", ["인터넷·성장주", "유틸리티·리츠"]], ["덜", ["은행·금융"]]],
         "kr": [["더 크게", ["2차전지", "인터넷·게임", "건설"]], ["덜", ["은행·보험"]]]},
  "E8": {"us": [["더 크게", ["반도체·AI"]]], "kr": [["더 크게", ["반도체"]]]},
}
PATH_US = [["cpi","rate"],["rate","stock"],["rate","fx"],["fx","stock"]]

base = {
  "date": "2026-11-26", "asof": "11/26 08:00", "mock": True,
  "status": {"delayed": None, "quiet": False, "split": None, "closed": {"us": False, "kr": False}, "rankChange": None},
  # 관심사 후보(고정 3개) 순위 — 샘플 순위. 실제는 AI가 매일 근거·출처와 함께 정함
  "interests": [
    {"key": "cpi", "node": "cpi", "name": "물가", "rank": 1, "reason": {"type": "mention", "label": "가장 많이 언급"}, "upSide": "bad",
     "sentence": "지금 시장은 물가가 올라 주식에 악재가 될까 봐 걱정하고 있어요",
     "explain": [["cpi","rate"],["rate","stock"]], "sources": []},
    {"key": "rate", "node": "rate", "name": "금리", "rank": 2, "reason": {"type": "mention", "label": "언급 늘어나는 중"}, "upSide": "bad",
     "sentence": "지금 시장은 금리가 더 올라 주식에 악재가 될까 봐 걱정하고 있어요",
     "explain": [["rate","stock"]], "sources": []},
    {"key": "job", "node": "job", "name": "경기", "rank": 3, "reason": {"type": "mention", "label": "가끔 언급"}, "upSide": "good",
     "sentence": "지금 시장은 경기가 식어 주식에 악재가 될까 봐 걱정하고 있어요",
     "explain": [["job","stock"]], "sources": []},
  ],
  "events": [
    {"id": "bok-2026-11-26", "type": "E1", "chip": "한국은행 금리", "sub": "오늘", "kind": "done",
     "head": "한국은행 기준금리 인상", "result": {"dir": "up", "text": "3.00% → 3.25% · 예상대로 인상"},
     "confirm": [{"label": "먼저", "what": "원/달러 환율", "when": "며칠~몇 주", "done": False},
                 {"label": "최종", "what": "1월 금통위", "when": "1/14", "done": False}],
     "real": {"rate": {"kr": "up"}}, "realPath": [], "next": ["fx", "cpi"], "actual": None,
     "opts": {
       "a": {"label": "물가가 잡히면", "path": [["rate","fx"],["fx","cpi"],["rate","cpi"]], "state": {"fx": {"dir": "down"}, "cpi": {"dir": "down"}},
             "cond": [["금리","up",1],["원화 강세",None]], "mid": ["물가 오름세 둔화","down"], "out": ""},
       "b": {"label": "물가가 안 잡히면", "path": [["cpi","rate"],["rate","stock"]], "state": {"cpi": {"dir": "up"}, "rate": {"kr": "up"}, "stock": {"kr": "down"}},
             "cond": [["물가","up",0,"유지"],["추가 인상",None]], "seq": True, "out": ""}},
     "judge": {"interest": {"cpi": ["down", "금리 인상이 오름세를 늦추는 쪽", "good", True],
                            "rate": ["up", "3.00% → 3.25%", "bad"]},
               "items": [["원/달러 환율", None, None, None], ["국고채 3년", None, None, None],
                         ["코스피", "up", "4,711.21 · +0.29% (장중 +2% 넘었다가 인상 후 대부분 반납)", None]]},
     "lean": None, "sectorTab": "kr", "sectors": SEC["E1"], "sources": SRC_BOK},
    {"id": "us-cpi-next", "type": "E1", "chip": "미국 CPI", "sub": "곧 발표", "kind": "upcoming",
     "head": "미국 CPI 발표", "top": "발표일·예상치 확인 전",
     "real": {}, "realPath": [], "next": ["cpi", "rate"], "actual": None,
     "opts": {
       "a": {"label": "예상보다 낮으면", "path": PATH_US, "state": {"cpi": {"dir": "down"}, "rate": {"us": "down"}, "fx": {"dir": "down"}, "stock": {"us": "up", "kr": "up"}},
             "cond": [["물가","down"],["금리","down"]], "out": "금리 인하 기대로 성장주에 좋은 흐름"},
       "b": {"label": "예상보다 높으면", "path": PATH_US, "state": {"cpi": {"dir": "up"}, "rate": {"us": "up"}, "fx": {"dir": "up"}, "stock": {"us": "down", "kr": "down"}},
             "cond": [["물가","up"],["금리","up"]], "out": "금리 인하가 멀어져 성장주에 부담"}},
     "judge": {"interest": {}, "items": [["미국채 10년물", None, None, None], ["VIX", None, None, None], ["달러 인덱스", None, None, None]]},
     "lean": None, "sectorTab": "us", "sectors": SEC["E1"], "sources": []},
    {"id": "nvda-earnings", "type": "E8", "chip": "엔비디아 실적", "sub": "일정 확인 전", "kind": "upcoming",
     "head": "엔비디아 실적", "top": "예상치 확인 전",
     "real": {}, "realPath": [], "next": ["stock"], "actual": None,
     "opts": {
       "a": {"label": "예상보다 낮으면", "path": [["vix","stock"]], "state": {"stock": {"us": "down", "kr": "down"}, "vix": {"dir": "up"}}, "cond": [["매출","down"],["공포","up"]], "out": "반도체 업종에 부담"},
       "b": {"label": "예상보다 높으면", "path": [], "state": {"stock": {"us": "up", "kr": "up"}}, "cond": [["매출","up"]], "out": "반도체 업종에 좋은 흐름"}},
     "judge": {"interest": {}, "items": [["미국 반도체 지수", None, None, None], ["나스닥", None, None, None]]},
     "lean": None, "sectorTab": "us", "highlight": "반도체·AI", "sectors": SEC["E8"], "sources": []},
  ],
}

def write(name, d):
    p = OUT / name; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")

write("today.json", base)
q = copy.deepcopy(base); q["status"]["quiet"] = True; q["events"] = q["events"][1:]; write("mock/quiet.json", q)
r = copy.deepcopy(base); c = r["events"][1]
c.update({"sub": "오늘 발표", "kind": "done", "actual": "b", "result": {"dir": "up", "text": "예상보다 높음 (샘플)"},
          "top": None, "reason": "예상보다 높게 나와 금리 인하가 멀어졌어요"}); r["events"] = [c] + [r["events"][0]]; write("mock/release.json", r)
s = copy.deepcopy(base); s["status"]["split"] = {"us": "down", "kr": "up"}; write("mock/split.json", s)
d = copy.deepcopy(base); d["status"]["delayed"] = "11/25 08:00"; write("mock/delayed.json", d)
k = copy.deepcopy(base); k["status"]["closed"] = {"us": False, "kr": True}; write("mock/closed.json", k)
i = copy.deepcopy(base); i["status"]["rankChange"] = {"from": "금리", "to": "물가"}; write("mock/interest-change.json", i)
o = copy.deepcopy(base); o["interests"] = o["interests"][:1]; write("mock/one-interest.json", o)
print("ok")
