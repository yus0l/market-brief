"""① 수집: FRED(미국) · 한국은행 ECOS(한국) 공식 API → data/facts-YYYY-MM-DD.json
값마다 {value, prev, date, source}. 출처 없는 값은 저장하지 않는다 (기획 v4 기본 원칙).
환경변수: FRED_API_KEY, ECOS_API_KEY (둘 다 무료 발급)."""
import os, json, pathlib, datetime as dt, urllib.request, urllib.parse
HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE.parent / "data"
KST = dt.timezone(dt.timedelta(hours=9))

# key: (칸, 이름, FRED 시리즈, 단위)
FRED = {
  "us_cpi":   ("cpi",   "미국 CPI",        "CPIAUCSL",   "지수"),
  "us_ppi":   ("cpi",   "미국 PPI",        "PPIACO",     "지수"),
  "us_jobs":  ("job",   "비농업 고용",      "PAYEMS",     "천 명"),
  "us_10y":   ("rate",  "미국채 10년물",    "DGS10",      "%"),
  "vix":      ("vix",   "VIX",             "VIXCLS",     ""),
  "wti":      ("oil",   "WTI 유가",        "DCOILWTICO", "달러"),
  "sp500":    ("stock", "S&P 500",         "SP500",      ""),
}
# key: (칸, 이름, 통계표, 주기, 항목코드, 단위) — 코드는 첫 실행 때 ECOS 화면과 한 번 대조할 것 (README)
ECOS = {
  "kr_base":  ("rate",  "기준금리",         "722Y001", "D", "0101000",   "%"),
  "usdkrw":   ("fx",    "원/달러 환율",      "731Y001", "D", "0000001",   "원"),
  "ktb3y":    ("rate",  "국고채 3년",        "817Y002", "D", "010200000", "%"),
  "kospi":    ("stock", "코스피",            "802Y001", "D", "0001000",   ""),
  "kr_cpi":   ("cpi",   "한국 소비자물가",    "901Y009", "M", "0",         "지수"),
}

MONTHLY = {"us_cpi", "us_ppi"}   # 전년 대비를 계산하는 월간 지수

def get(url):
    with urllib.request.urlopen(url, timeout=30) as r: return json.loads(r.read().decode("utf-8"))

def fred(series, key):
    q = urllib.parse.urlencode({"series_id": series, "api_key": key, "file_type": "json", "sort_order": "desc", "limit": 15})
    obs = [o for o in get(f"https://api.stlouisfed.org/fred/series/observations?{q}")["observations"] if o["value"] not in (".", "")]
    if len(obs) < 2: return None
    out = {"value": float(obs[0]["value"]), "prev": float(obs[1]["value"]), "date": obs[0]["date"],
           "source": {"name": f"FRED {series}", "url": f"https://fred.stlouisfed.org/series/{series}"}}
    return dict(out, **yoy([float(o["value"]) for o in obs]))   # obs는 최신이 앞

def ecos(table, cyc, item, key, today):
    start = (today - dt.timedelta(days=40 if cyc == "D" else 460)).strftime("%Y%m%d" if cyc == "D" else "%Y%m")
    end = today.strftime("%Y%m%d" if cyc == "D" else "%Y%m")
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100/{table}/{cyc}/{start}/{end}/{item}"
    rows = get(url).get("StatisticSearch", {}).get("row", [])
    if len(rows) < 2: return None
    a, b = rows[-1], rows[-2]
    out = {"value": float(a["DATA_VALUE"]), "prev": float(b["DATA_VALUE"]), "date": a["TIME"],
           "source": {"name": f"한국은행 ECOS {table}", "url": "https://ecos.bok.or.kr/"}}
    return dict(out, **(yoy([float(r["DATA_VALUE"]) for r in reversed(rows)]) if cyc == "M" else {}))

def yoy(vals):
    """월간 지수(최신이 앞) → 전년 대비 %와 한 달 전의 전년 대비 %. 13·14개월치가 없으면 빈 값."""
    if len(vals) < 14: return {}
    return {"yoy": round((vals[0] / vals[12] - 1) * 100, 1), "yoy_prev": round((vals[1] / vals[13] - 1) * 100, 1)}

def fmt_variants(x):
    """검사기가 문장 속 숫자를 대조할 수 있게, 화면에 쓸 법한 표기를 모두 허용 목록에 넣는다."""
    out = {f"{x:.2f}", f"{x:.1f}", f"{x:,.2f}", f"{x:,.1f}", f"{x:,.0f}", f"{x:g}"}
    return {s.replace(",", "") for s in out}

def collect(today=None):
    today = today or dt.datetime.now(KST).date()
    series, errors = {}, []
    fk, ek = os.environ.get("FRED_API_KEY"), os.environ.get("ECOS_API_KEY")
    for k, (node, name, sid, unit) in FRED.items():
        try:
            v = fred(sid, fk) if fk else None
            if v and k not in MONTHLY: v.pop("yoy", None); v.pop("yoy_prev", None)
            if v: series[k] = dict(v, node=node, name=name, unit=unit)
            else: errors.append(f"{k}: 값 없음" + ("" if fk else " (FRED_API_KEY 없음)"))
        except Exception as e: errors.append(f"{k}: {e}")
    for k, (node, name, tb, cyc, item, unit) in ECOS.items():
        try:
            v = ecos(tb, cyc, item, ek, today) if ek else None
            if v: series[k] = dict(v, node=node, name=name, unit=unit)
            else: errors.append(f"{k}: 값 없음" + ("" if ek else " (ECOS_API_KEY 없음)"))
        except Exception as e: errors.append(f"{k}: {e}")
    allowed = set()
    for v in series.values():
        allowed |= fmt_variants(v["value"]) | fmt_variants(v["prev"]) | fmt_variants(v["value"] - v["prev"])
        if v["prev"]: allowed |= fmt_variants((v["value"] / v["prev"] - 1) * 100)
        for y in ("yoy", "yoy_prev"):
            if y in v: allowed |= fmt_variants(v[y])
    facts = {"date": today.isoformat(), "collected_at": dt.datetime.now(KST).isoformat(timespec="minutes"),
             "series": series, "errors": errors, "allowed_numbers": sorted(allowed)}
    DATA.mkdir(exist_ok=True)
    (DATA / f"facts-{today.isoformat()}.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")
    return facts

if __name__ == "__main__":
    f = collect(); print(len(f["series"]), "series;", "\n".join(f["errors"]))
