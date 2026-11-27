"""01-기획-표/업종-민감도.md → config/sectors.json (사건 유형 E1~E8 × 미국/한국 업종 묶음)."""
import re, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = pathlib.Path(__file__).resolve().parent.parent / "config" / "sectors.json"
res = {}
for line in (ROOT / "01-기획-표" / "업종-민감도.md").read_text(encoding="utf-8").splitlines():
    m = re.match(r"\|\s*\*\*(E\d)[^|]*\*\*[^|]*\|([^|]*)\|([^|]*)\|", line)
    if not m: continue
    def groups(cell):
        out = []
        for part in cell.split(" / "):
            if ":" not in part: continue
            g, items = part.split(":", 1)
            out.append([g.strip(), [x.strip() for x in items.split(",") if x.strip()]])
        return out
    res[m[1]] = {"us": groups(m[2]), "kr": groups(m[3])}
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(sorted(res))
