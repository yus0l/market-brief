"""01-기획-표/발표일정-2027.md → config/schedule-2027.json (ET → KST 변환 포함).
"확인 필요" 행은 verified=false로 넣고, 화면·순위 가산에서 쓰지 않는다 (기획 v4.2·v4.3)."""
import re, json, pathlib, datetime as dt
ROOT = pathlib.Path(__file__).resolve().parents[3]
MD = ROOT / "01-기획-표" / "발표일정-2027.md"
OUT = pathlib.Path(__file__).resolve().parent.parent / "config" / "schedule-2027.json"   # 2026년 12월분 포함
DST = {2026: (dt.date(2026, 3, 8), dt.date(2026, 11, 1)), 2027: (dt.date(2027, 3, 14), dt.date(2027, 11, 7))}   # 미국 서머타임

def et_to_kst(d, hh, mm):
    off = 13 if DST[d.year][0] <= d < DST[d.year][1] else 14                     # EDT(UTC-4) → +13h, EST(UTC-5) → +14h
    t = dt.datetime(d.year, d.month, d.day, hh, mm) + dt.timedelta(hours=off)
    return t.strftime("%Y-%m-%dT%H:%M+09:00")

SECTIONS = {"## 1.": ("US_CPI", "미국 CPI", (8, 30)), "## 2.": ("US_JOBS", "미국 고용", (8, 30)),
            "## 3.": ("US_PPI", "미국 PPI", (8, 30)), "## 4.": ("FOMC", "FOMC 금리 결정", (14, 0)), "## 5.": ("BOK", "금통위 금리 결정", None)}
rows, cur, src = [], None, ""
for line in MD.read_text(encoding="utf-8").splitlines():
    if line.startswith("## 0."): cur = ("DEC2026", None, None); continue
    if line.startswith("## "):
        cur = next((v for k, v in SECTIONS.items() if line.startswith(k)), None); src = ""; continue
    if cur and line.startswith("출처:"): src = line.split("출처:")[1].split("·")[0].strip().split(" , ")[0]
    if not cur or not line.startswith("|") or "---" in line: continue
    cells = [c.strip() for c in line.strip("|").split("|")]
    code, name, et = cur
    if code == "DEC2026":                                       # 2026년 12월 표: | 발표 | 대상 | 날짜 (ET) | 비고 |
        M = {"미국 고용": ("US_JOBS", "미국 고용"), "FOMC": ("FOMC", "FOMC 금리 결정"), "미국 CPI": ("US_CPI", "미국 CPI"),
             "미국 PPI": ("US_PPI", "미국 PPI"), "ISM 제조업": ("US_ISM", "ISM 제조업")}
        if cells[0] == "한국 소비자물가":                          # 한국 날짜 그대로, 시각은 원문에 없음 → 08:00 KST 관행
            m = re.search(r"(\d+)/(\d+)", cells[2])
            if m:
                d = dt.date(2026, int(m[1]), int(m[2]))
                rows.append({"code": "KR_CPI", "name": "한국 소비자물가", "target": cells[1], "date": d.isoformat(), "kst": f"{d.isoformat()}T08:00+09:00",
                             "time_note": "관행", "verified": "공식" in cells[3] and "미확인" not in cells[3], "source": "https://mods.go.kr/lcofNewsPln.es?mid=a60303000000"})
            continue
        if cells[0] not in M: continue
        m = re.search(r"(?:결정 )?(\d+)/(\d+) \([^)]*\) (\d+):(\d+)", cells[2])
        if not m: continue
        d = dt.date(2026, int(m[1]), int(m[2]))
        rows.append({"code": M[cells[0]][0], "name": M[cells[0]][1], "target": cells[1], "date": d.isoformat(),
                     "kst": et_to_kst(d, int(m[3]), int(m[4])), "verified": "미확인" not in cells[3],
                     "source": {"FOMC": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", "ISM 제조업": "https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/"}.get(cells[0], "https://www.bls.gov/schedule/")})
        continue
    if code == "BOK":
        m = re.match(r"(\d+)/(\d+)", cells[0]);
        if not m: continue
        d = dt.date(2027, int(m[1]), int(m[2])); ok = "확인 필요" not in cells[1]
        rows.append({"code": code, "name": name, "date": d.isoformat(), "kst": None, "verified": ok,
                     "source": "https://www.bok.or.kr/portal/singl/crncyPolicyDrcMtg/listYear.do?mtgSe=A&menuNo=200755&pYear=2027"}); continue
    m = re.search(r"(\d+)/(\d+)", cells[1] if code == "FOMC" else cells[1])
    if not m or "발표일" in cells[1]: continue
    y = 2027
    d = dt.date(y, int(m[1]), int(m[2]))
    rows.append({"code": code, "name": name, "target": cells[0], "date": d.isoformat(), "kst": et_to_kst(d, *et), "verified": True, "source": src})
OUT.write_text(json.dumps({"_doc": "자동 생성 — 원본은 01-기획-표/발표일정-2027.md", "events": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(rows), "rows;", sum(not r["verified"] for r in rows), "unverified")
