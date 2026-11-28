"""v4 칸 목록과 연결표 — 01-정보설계.md v4 · 01-연결표.md · 02-화면.md (11/28).

칸은 고정 목록이 아니라 규칙이다(정보설계 v4 {흐름}.칸). 여기 있는 건 '수집값이 있는 칸'뿐이고,
그 밖의 칸(금·업종 지수 등)은 AI가 매체 2곳 같은 숫자로 가져온다(media 칸, '크게' 판단엔 안 씀 · 기획 11/28).
"""
import json, pathlib, re
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO_DOCS = ROOT.parent.parent          # my-service/ (로컬에서만 있음 — 연결표 원본)

# key: 이름, 출처(fred/ecos/facts/sec), 시리즈, 변화 계산(diff=%p · log=%), 나라, 묶음, 단위, 값 앞뒤 글자
CELLS = {
  "us_10y":  dict(name="미국 10년 국채 금리", src="fred", sid="DGS10",      calc="diff", kr=False, grp="rate_us", unit="%"),
  "us_2y":   dict(name="미국 2년 국채 금리",  src="fred", sid="DGS2",       calc="diff", kr=False, grp="rate_us", unit="%"),
  "us_be10": dict(name="미국 기대 물가(10년)", src="fred", sid="T10YIE",    calc="diff", kr=False, grp="cpi",     unit="%"),
  "vix":     dict(name="VIX(공포 지수)",      src="fred", sid="VIXCLS",     calc="log",  kr=False, grp="vix",     unit=""),
  "wti":     dict(name="유가(WTI)",           src="fred", sid="DCOILWTICO", calc="log",  kr=False, grp="oil",     unit="$", pre="배럴당 $"),
  "brent":   dict(name="유가(브렌트)",         src="fred", sid="DCOILBRENTEU", calc="log", kr=False, grp="oil",    unit="$", pre="배럴당 $"),
  "sp500":   dict(name="미국 주식(S&P 500)",  src="fred", sid="SP500",      calc="log",  kr=False, grp="stock_us", unit=""),
  "nasdaq":  dict(name="미국 주식(나스닥)",    src="fred", sid="NASDAQCOM",  calc="log",  kr=False, grp="stock_us", unit=""),
  "dxy":     dict(name="달러 가치(달러지수)",   src="fred", sid="DTWEXBGS",   calc="log",  kr=False, grp="dollar",  unit=""),
  "usdkrw":  dict(name="원/달러",             src="ecos", sid=("731Y001", "0000001"), calc="log", kr=True, grp="krw", unit="원", post="원"),
  "kospi":   dict(name="코스피",              src="ecos", sid=("802Y001", "0001000"), calc="log", kr=True, grp="stock_kr", unit=""),
  "ktb3y":   dict(name="한국 3년 국채 금리",   src="ecos", sid=("817Y002", "010200000"), calc="diff", kr=True, grp="rate_kr", unit="%"),
  # 매일 값이 아닌 칸: 값·방향만, '크게' 판단 안 함 (facts-날짜.json에서 읽음)
  "us_cpi":  dict(name="미국 물가",            src="facts", sid="us_cpi",  calc=None, kr=False, grp="cpi",     unit="%", yoy=True),
  "kr_cpi":  dict(name="한국 물가",            src="facts", sid="kr_cpi",  calc=None, kr=True,  grp="cpi_kr",  unit="%", yoy=True),
  "us_base": dict(name="미국 기준금리",         src="facts", sid="us_base", calc=None, kr=False, grp="rate_us", unit="%"),
  "kr_base": dict(name="한국 기준금리",         src="facts", sid="kr_base", calc=None, kr=True,  grp="rate_kr", unit="%"),
  "us_jobs": dict(name="미국 일자리",          src="facts", sid="us_jobs", calc=None, kr=False, grp="jobs",    unit="천 명"),
  # 엔비디아 재무 (SEC, 분기) — MVP 기업 1곳
  "nvda_rev":   dict(name="엔비디아 매출",      src="sec", sid="Revenues",              calc=None, kr=False, grp="nvda_fin", unit="$"),
  "nvda_opinc": dict(name="엔비디아 영업이익",   src="sec", sid="OperatingIncomeLoss",   calc=None, kr=False, grp="nvda_fin", unit="$"),
}
# 사례 ② 영향도에 쓰는 칸 (정보설계 v4: 거시 = 금리·유가·금·환율·주요 지수·VIX / 기업 = 업종·지수). 금·업종은 수집값이 없어 못 셈
IMPACT_MACRO = ["us_10y", "us_2y", "wti", "brent", "usdkrw", "dxy", "sp500", "nasdaq", "kospi", "vix"]
IMPACT_FIRM = ["nasdaq", "sp500", "kospi"]
ASSET_GRP = {"stock_us", "stock_kr", "gold", "sector"}   # 끝 칸 호재/악재를 다는 칸 (대상 = 그 칸 자신, 정보설계 v4)

# 연결표 번호 → 어느 칸 묶음에서 어느 칸 묶음으로, 방향(+ 같은 쪽 / - 반대 쪽). sym = 반대로도 성립(금리↓→금↑)
# 문장·출처·깨지는 때·상태는 01-연결표.md에서 읽어 config/links-v4.json으로 내보낸다
LINK_MAP = {
  1:  dict(a=["vix", "event"], b=["gold"], s=+1, sym=True),
  2:  dict(a=["rate_us"], b=["gold"], s=-1, sym=True),
  3:  dict(a=["oil"], b=["cpi", "cpi_kr"], s=+1, sym=True),
  4:  dict(a=["cpi"], b=["rate_us"], s=+1, sym=True),
  5:  dict(a=["rate_us", "rate_kr"], b=["stock_us", "stock_kr", "sector"], s=-1, sym=True),
  6:  dict(a=["jobs"], b=["cpi"], s=+1, sym=True),
  7:  dict(a=["krw"], b=["cpi_kr"], s=+1, sym=True),
  8:  dict(a=["jobs"], b=["rate_us"], s=+1, sym=True),
  9:  dict(a=["rate_us"], b=["cpi"], s=-1, sym=False, slow=True),
  10: dict(a=["rate_us"], b=["dollar", "krw"], s=+1, sym=True),
  11: dict(a=["krw"], b=["stock_kr"], s=-1, sym=True),
  12: dict(a=["vix"], b=["stock_us", "stock_kr"], s=-1, sym=True),
  13: dict(a=["growth"], b=["stock_us", "stock_kr"], s=+1, sym=True),
  14: dict(a=["dollar"], b=["gold"], s=-1, sym=True),
  15: dict(a=["stock_us"], b=["stock_kr"], s=+1, sym=True),
  16: dict(a=["nvda_fin"], b=["company"], s=+1, sym=True),
  17: dict(a=["nvda_fin", "event"], b=["sector"], s=+1, sym=True),
}

def grp(cell):
    """칸(dict 또는 key) → 묶음. media 칸은 AI가 grp를 붙인다(gold·sector·…)."""
    if isinstance(cell, str): return CELLS[cell]["grp"] if cell in CELLS else None
    if cell.get("cell") in CELLS: return CELLS[cell["cell"]]["grp"]
    return (cell.get("media") or {}).get("grp") or cell.get("grp")

def links_from_md(path=None):
    """01-연결표.md 표 → config/links-v4.json. 연결표가 바뀌면 다시 돌린다."""
    p = pathlib.Path(path or REPO_DOCS / "01-연결표.md")
    rows = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) < 7 or not c[0].isdigit(): continue
        n = int(c[0])
        srcs = [{"name": m[0], "url": m[1]} for m in re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", c[5])]
        rows[n] = {"id": n, "link": c[1], "line": c[2], "why": c[3], "breaks": c[4], "sources": srcs, "status": c[6],
                   "weak": "⚠" in c[6] or len({urlparse(x["url"]).netloc.removeprefix("www.") for x in srcs}) < 2, **LINK_MAP.get(n, {})}
    out = {"_doc": "01-연결표.md에서 자동 생성 (pipeline/v4_cells.py links). 직접 고치지 말 것. weak = ⚠ 또는 서로 다른 출처(도메인) 2곳 미만 → 앞으로 칸이면 미지수",
           "links": [rows[k] for k in sorted(rows)]}
    (ROOT / "config" / "links-v4.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out

def load_links():
    return {x["id"]: x for x in json.loads((ROOT / "config" / "links-v4.json").read_text(encoding="utf-8"))["links"]}

def find_link(ga, da, gb, db, links=None):
    """a 칸(묶음 ga, 방향 da ±1)과 b 칸(gb, db)이 연결표의 어느 줄로 이어지나. 방향까지 맞아야 한다. 없으면 None."""
    for L in (links or load_links()).values():
        if ga in L.get("a", []) and gb in L.get("b", []):
            if da and db and da * L["s"] == db and (L.get("sym") or da > 0): return L
    return None

if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["links"]: print(len(links_from_md()["links"]), "links → config/links-v4.json")
