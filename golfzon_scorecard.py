#!/usr/bin/env python3
"""
골프존 네트워크 플레이 스코어카드 통합 도구 v2
- 전체 참가자 (최대 16명+) 지원
- 검증 절차 내장
- PDF 저장: ~/storage/downloads/sundayscreen/
- 골프존 앱 디자인 동일하게 적용
"""

import json
import os
import sys
import argparse
import glob
from datetime import datetime
from pathlib import Path
import html as html_mod

# ── 출력 폴더 ──────────────────────────────────
SUNDAYSCREEN_DIR = Path.home() / "storage" / "downloads" / "sundayscreen"


# ══════════════════════════════════════════════
# 데이터 구조
# ══════════════════════════════════════════════

class HoleScore:
    def __init__(self, hole, par, strokes, relative):
        self.hole = hole
        self.par = par
        self.strokes = strokes
        self.relative = relative


class PlayerResult:
    def __init__(self, rank, name, total_relative, holes):
        self.rank = rank
        self.name = name
        self.total_relative = total_relative
        self.holes = holes
        self.front9 = sum(h.relative for h in holes[:9])
        self.back9  = sum(h.relative for h in holes[9:])


class NetworkGame:
    def __init__(self, data):
        self.game_id          = data.get("game_id", "")
        self.title            = data["title"]
        self.course           = data["course"]
        self.date             = data["date"]
        self.total_players    = data["total_players"]
        self.finished_players = data["finished_players"]
        self.par_list         = data["par_list"]   # 18개
        self.players          = []

        for p in data["players"]:
            scores = p["scores"]
            holes  = []
            for i, rel in enumerate(scores):
                par     = self.par_list[i]
                holes.append(HoleScore(i + 1, par, par + rel, rel))
            self.players.append(PlayerResult(
                rank           = p["rank"],
                name           = p["name"],
                total_relative = p["total_relative"],
                holes          = holes,
            ))


# ══════════════════════════════════════════════
# 검증
# ══════════════════════════════════════════════

def validate(game):
    print("\n" + "═" * 50)
    print("  검증 결과")
    print("═" * 50)

    ok = True

    # 1. 참가자 수
    actual = len(game.players)
    expected = game.total_players
    status = "✓" if actual == expected else "✗"
    print(f"  {status} 참가자 수: 데이터 {actual}명 / 선언 {expected}명")
    if actual != expected:
        print(f"    → JSON에 {expected - actual}명의 데이터가 더 필요합니다.")
        ok = False

    # 2. 각 선수 검증
    print(f"\n  {'순위':<4} {'이름':<14} {'홀수':>4} {'합계일치':>6} {'검증'}")
    print("  " + "-" * 44)
    for p in game.players:
        hole_cnt   = len(p.holes)
        calc_total = sum(h.relative for h in p.holes)
        match      = calc_total == p.total_relative
        sym        = "✓" if (hole_cnt == 18 and match) else "✗"
        total_str  = f"{p.total_relative:+d}" if p.total_relative != 0 else "E"
        calc_str   = f"{calc_total:+d}"  if calc_total != 0 else "E"
        note       = "" if match else f"← 선언:{total_str} 계산:{calc_str}"
        print(f"  {sym} {p.rank:<4} {p.name:<14} {hole_cnt:>4}홀   {total_str:>4}   {note}")
        if hole_cnt != 18 or not match:
            ok = False

    # 3. 이름 목록
    print(f"\n  등록된 선수 ({actual}명):")
    for p in sorted(game.players, key=lambda x: x.rank):
        print(f"    {p.rank:2}위  {p.name}")

    print("═" * 50)
    print(f"  최종: {'✓ 검증 통과' if ok else '✗ 오류 있음 — 위 내용 확인 필요'}")
    print("═" * 50 + "\n")
    return ok


# ══════════════════════════════════════════════
# HTML 생성
# ══════════════════════════════════════════════

def rel_str(val):
    if val > 0:  return f"+{val}"
    if val == 0: return "E"
    return str(val)


def score_cell(rel, strokes):
    """골프존 앱과 동일한 스타일의 점수 셀"""
    if rel <= -2:
        bg, color, shape = "#FFD700", "#000", "eagle-cell"
    elif rel == -1:
        bg, color, shape = "#FF4500", "#fff", "birdie-cell"
    elif rel == 0:
        bg, color, shape = "transparent", "#222", "par-cell"
    elif rel == 1:
        bg, color, shape = "#3A7FD5", "#fff", "bogey-cell"
    else:
        bg, color, shape = "#1A1A6E", "#fff", "double-cell"

    rel_label = f"{rel:+d}" if rel != 0 else "0"
    return (
        f'<td class="sc {shape}" style="background:{bg};color:{color}">'
        f'<span class="st">{strokes}</span>'
        f'<span class="rl">{rel_label}</span>'
        f'</td>'
    )


def build_html(game):
    par_f = sum(game.par_list[:9])
    par_b = sum(game.par_list[9:])
    par_t = par_f + par_b
    now   = datetime.now().strftime("%Y.%m.%d %H:%M")

    # 파 셀
    par_front_cells = "".join(f'<td class="par-num">{p}</td>' for p in game.par_list[:9])
    par_back_cells  = "".join(f'<td class="par-num">{p}</td>' for p in game.par_list[9:])

    # 선수 행
    rows_f = ""
    rows_b = ""
    for p in game.players:
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(p.rank, f"{p.rank}")
        name  = html_mod.escape(p.name)

        fc = "".join(score_cell(h.relative, h.strokes) for h in p.holes[:9])
        bc = "".join(score_cell(h.relative, h.strokes) for h in p.holes[9:])

        # 전반 섹션 행
        rows_f += f"""
<tr class="prow">
  <td class="rank" rowspan="2">{medal}</td>
  <td class="pname" rowspan="2">{name}</td>
  <td class="half">전반</td>
  {fc}
  <td class="sub">{rel_str(p.front9)}</td>
  <td class="tot" rowspan="2">{rel_str(p.total_relative)}</td>
</tr>
<tr class="prow2">
  <td class="half">-</td>
  {"".join(f'<td class="sc par-cell" style="background:transparent;color:#222"><span class="st">-</span><span class="rl">-</span></td>' for _ in range(9))}
  <td class="sub">-</td>
</tr>"""

        # 후반 섹션 행
        rows_b += f"""
<tr class="prow">
  <td class="rank" rowspan="2">{medal}</td>
  <td class="pname" rowspan="2">{name}</td>
  <td class="half">후반</td>
  {bc}
  <td class="sub">{rel_str(p.back9)}</td>
  <td class="tot" rowspan="2">{rel_str(p.total_relative)}</td>
</tr>
<tr class="prow2">
  <td class="half">-</td>
  {"".join(f'<td class="sc par-cell" style="background:transparent;color:#222"><span class="st">-</span><span class="rl">-</span></td>' for _ in range(9))}
  <td class="sub">-</td>
</tr>"""

    hole_headers_f = "".join(f"<th>{h}</th>" for h in range(1, 10))
    hole_headers_b = "".join(f"<th>{h}</th>" for h in range(10, 19))

    css = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
       background: #eef0f4; padding: 16px; }
.card { background: #fff; border-radius: 14px;
        box-shadow: 0 4px 18px rgba(0,0,0,.13);
        overflow: hidden; max-width: 1300px; margin: 0 auto 24px; }

/* 헤더 */
.hdr { background: linear-gradient(135deg,#1a4fd6,#0a2fa0);
       color:#fff; padding:20px 22px; }
.hdr h1 { font-size:1.6rem; margin-bottom:4px; }
.hdr .meta { font-size:.88rem; opacity:.85; }
.hdr .stat { margin-top:8px; font-size:.84rem; opacity:.9; }

/* 범례 */
.legend { display:flex; gap:10px; flex-wrap:wrap;
          padding:10px 16px; background:#f5f6f8;
          border-bottom:1px solid #ddd; font-size:.78rem; }
.leg { display:inline-flex; align-items:center; gap:5px;
       padding:3px 10px; border-radius:20px; font-weight:600; }
.leg-eagle  { background:#FFD700; color:#000; border:2px solid #FFD700; border-radius:50px; }
.leg-birdie { background:#FF4500; color:#fff; border-radius:50px; }
.leg-par    { background:#e8e8e8; color:#333; border-radius:4px; }
.leg-bogey  { background:#3A7FD5; color:#fff; border-radius:4px; }
.leg-double { background:#1A1A6E; color:#fff; border-radius:4px; }

/* 섹션 타이틀 */
.section-title { background:#1e2d40; color:#fff; text-align:center;
                 padding:7px; font-size:.82rem; font-weight:700;
                 letter-spacing:.5px; }

/* 테이블 */
.tbl-wrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:.82rem; }
thead th { background:#2c3e50; color:#fff; text-align:center;
           padding:7px 4px; font-weight:600; white-space:nowrap; }
.par-row td { background:#4a5568; color:#cfd8dc; text-align:center;
              padding:5px 3px; font-size:.78rem; }
.par-num { font-weight:700; }

/* 선수 행 */
.rank { text-align:center; font-size:1rem; padding:4px 6px;
        vertical-align:middle; border-left:3px solid #ddd; white-space:nowrap; }
.pname { font-weight:700; padding:4px 10px; vertical-align:middle;
         white-space:nowrap; min-width:90px; }
.half { text-align:center; font-size:.72rem; color:#777;
        padding:3px 5px; white-space:nowrap; }
.sub { text-align:center; padding:4px 6px; font-weight:600;
       min-width:38px; font-size:.84rem; }
.tot { text-align:center; padding:4px 8px; font-weight:800;
       background:#eef2ff; font-size:.95rem; min-width:42px; vertical-align:middle; }

/* 점수 셀 */
.sc { text-align:center; padding:3px 2px; min-width:34px;
      vertical-align:middle; }
.sc .st { display:block; font-size:.84rem; font-weight:700; line-height:1.2; }
.sc .rl { display:block; font-size:.65rem; font-weight:400; opacity:.9; line-height:1; }

/* 모양 */
.birdie-cell { border-radius:50%; }
.eagle-cell  { border-radius:50%; outline:2px solid #e6b800; }
.bogey-cell  { border-radius:3px; }
.double-cell { border-radius:3px; outline:2px solid #3A7FD5; }

/* 행 구분 */
tr.prow  td { border-top:1px solid #e4e4e4; }
tr.prow2 td { border-bottom:2px solid #c0c0c0; }

footer { text-align:center; padding:10px; font-size:.72rem;
         color:#aaa; background:#f5f6f8; }

@media print {
  body { background:white; padding:0; }
  .card { box-shadow:none; border-radius:0; }
}
"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>골프존 네트워크플레이 - {html_mod.escape(game.title)}</title>
<style>{css}</style>
</head>
<body>
<div class="card">

  <div class="hdr">
    <h1>{html_mod.escape(game.title)}</h1>
    <div class="meta">{html_mod.escape(game.course)} &nbsp;|&nbsp; {html_mod.escape(game.date)}</div>
    <div class="stat">
      라운드 완료 {game.finished_players}명 / 참여 {game.total_players}명
      &nbsp;|&nbsp; Par {par_t} (전반 {par_f} / 후반 {par_b})
    </div>
  </div>

  <div class="legend">
    <span class="leg leg-eagle">■ 이글 이상</span>
    <span class="leg leg-birdie">■ 버디</span>
    <span class="leg leg-par">■ 파</span>
    <span class="leg leg-bogey">■ 보기</span>
    <span class="leg leg-double">■ 더블보기 이상</span>
  </div>

  <div class="section-title">▶ 전반 (Hole 1 – 9) &nbsp;|&nbsp; Par {par_f}</div>
  <div class="tbl-wrap">
    <table>
      <thead>
        <tr>
          <th colspan="2">순위 / 선수</th>
          <th>구분</th>
          {hole_headers_f}
          <th>소계</th>
          <th>합계</th>
        </tr>
        <tr class="par-row">
          <td colspan="2">Par</td><td></td>
          {par_front_cells}
          <td class="par-num">{par_f}</td>
          <td class="par-num">{par_t}</td>
        </tr>
      </thead>
      <tbody>{rows_f}</tbody>
    </table>
  </div>

  <div class="section-title" style="margin-top:18px">▶ 후반 (Hole 10 – 18) &nbsp;|&nbsp; Par {par_b}</div>
  <div class="tbl-wrap">
    <table>
      <thead>
        <tr>
          <th colspan="2">순위 / 선수</th>
          <th>구분</th>
          {hole_headers_b}
          <th>소계</th>
          <th>합계</th>
        </tr>
        <tr class="par-row">
          <td colspan="2">Par</td><td></td>
          {par_back_cells}
          <td class="par-num">{par_b}</td>
          <td class="par-num">{par_t}</td>
        </tr>
      </thead>
      <tbody>{rows_b}</tbody>
    </table>
  </div>

  <footer>골프존 네트워크플레이 스코어카드 &nbsp;|&nbsp; 생성: {now}</footer>
</div>
</body>
</html>"""


# ══════════════════════════════════════════════
# PDF 변환
# ══════════════════════════════════════════════

def save_pdf(html_path, pdf_path):
    """HTML을 PDF로 변환. 실패 시 HTML만 저장하고 안내 출력."""
    # 방법 1: weasyprint
    try:
        from weasyprint import HTML
        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        print(f"[✓] PDF 저장: {pdf_path}")
        return True
    except Exception:
        pass

    # 방법 2: pdfkit (wkhtmltopdf 필요)
    try:
        import pdfkit
        pdfkit.from_file(str(html_path), str(pdf_path))
        print(f"[✓] PDF 저장: {pdf_path}")
        return True
    except Exception:
        pass

    # 방법 3: HTML만 저장하고 안내
    print(f"[✓] HTML 저장 완료: {html_path}")
    print("    ※ PDF 변환은 브라우저에서 직접 하세요:")
    print(f"       termux-open \"{html_path}\"")
    print("       브라우저 메뉴 → 공유 → 인쇄 → PDF로 저장")
    return False


# ══════════════════════════════════════════════
# JSON 자동 탐색
# ══════════════════════════════════════════════

def find_latest_json(search_dirs):
    """지정 폴더에서 가장 최근 수정된 .json 파일 반환"""
    candidates = []
    for d in search_dirs:
        candidates.extend(glob.glob(str(Path(d) / "*.json")))
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


# ══════════════════════════════════════════════
# 샘플 데이터 (16명)
# ══════════════════════════════════════════════

SAMPLE_DATA = {
    "game_id": "2026032900001",
    "title": "ㅂㅂ11",
    "course": "백제 CC - 웅진/사비",
    "date": "2026.03.29",
    "total_players": 16,
    "finished_players": 16,
    "par_list": [4,3,4,4,5,3,4,5,4, 4,5,4,3,4,4,4,3,5],
    "players": [
        {"rank":1,"name":"[늘푸른]",    "total_relative":-7,
         "scores":[0,0,-1,0,-1,0,-1,0,0, -1,-1,0,0,-1,-1,0,1,-1]},
        {"rank":2,"name":"bonteng",      "total_relative":-4,
         "scores":[0,0,0,-1,-1,0,0,-1,0, -1,0,0,0,0,-1,0,0,0]},
        {"rank":3,"name":"써클에너지",   "total_relative":-3,
         "scores":[0,-1,0,0,-1,0,0,0,-1, 0,-1,0,0,0,0,0,0,0]},
        {"rank":4,"name":"마차이새쯔",   "total_relative":0,
         "scores":[0,0,0,0,0,1,0,-1,0, 0,0,1,0,0,0,0,-1,0]},
        {"rank":5,"name":"나 (사용자)", "total_relative":1,
         "scores":[0,1,0,0,0,0,1,0,-1, 0,0,1,0,0,0,0,0,-1]},
        {"rank":6,"name":"선수6",        "total_relative":2,
         "scores":[1,0,0,0,1,0,0,0,1, 0,-1,0,1,0,0,0,0,0]},
        {"rank":7,"name":"선수7",        "total_relative":3,
         "scores":[0,1,1,0,0,0,0,1,0, 1,0,0,0,0,0,0,-1,0]},
        {"rank":8,"name":"선수8",        "total_relative":4,
         "scores":[1,0,1,0,0,1,0,0,0, 0,1,0,0,0,0,0,1,-1]},
        {"rank":9,"name":"선수9",        "total_relative":5,
         "scores":[0,1,0,1,0,1,0,1,0, 1,0,1,0,0,0,0,-1,0]},
        {"rank":10,"name":"선수10",      "total_relative":6,
         "scores":[1,0,1,0,1,0,1,0,1, 0,1,0,1,0,0,0,0,0]},
        {"rank":11,"name":"선수11",      "total_relative":7,
         "scores":[1,1,0,1,0,1,0,0,1, 1,0,1,0,0,0,1,0,0]},
        {"rank":12,"name":"선수12",      "total_relative":8,
         "scores":[1,0,1,1,0,1,0,1,0, 1,0,1,0,0,1,0,0,0]},
        {"rank":13,"name":"선수13",      "total_relative":9,
         "scores":[1,1,1,0,1,0,1,0,1, 0,1,0,1,0,0,1,0,0]},
        {"rank":14,"name":"선수14",      "total_relative":10,
         "scores":[1,1,0,1,1,0,1,1,0, 1,0,1,0,1,0,0,1,0]},
        {"rank":15,"name":"선수15",      "total_relative":11,
         "scores":[1,1,1,0,1,1,0,1,1, 1,0,1,0,1,0,1,0,0]},
        {"rank":16,"name":"선수16",      "total_relative":12,
         "scores":[1,1,1,1,0,1,1,1,1, 1,0,1,0,1,0,1,1,0]},
    ]
}


# ══════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="골프존 네트워크 플레이 스코어카드")
    parser.add_argument("--input",  "-i", default=None,
                        help="게임 데이터 JSON 파일 (생략 시 자동탐색 → 샘플)")
    parser.add_argument("--no-pdf", action="store_true",
                        help="PDF 변환 건너뜀 (HTML만 저장)")
    args = parser.parse_args()

    # ── 1. 데이터 로드 ──────────────────────────
    if args.input:
        src = args.input
    else:
        # 자동 탐색: 스크립트 폴더 + 현재 폴더
        search = [Path(__file__).parent, Path.cwd()]
        src = find_latest_json(search)

    if src and Path(src).exists():
        with open(src, encoding="utf-8") as f:
            raw = json.load(f)
        print(f"[✓] JSON 로드: {src}")
    else:
        raw = SAMPLE_DATA
        print("[✓] 샘플 데이터 사용 (sample_game.json 없음)")

    game = NetworkGame(raw)

    # ── 2. 검증 ────────────────────────────────
    ok = validate(game)
    if not ok:
        print("[!] 검증 실패 — 계속 진행합니다. JSON 데이터를 확인하세요.\n")

    # ── 3. 출력 폴더 준비 ──────────────────────
    SUNDAYSCREEN_DIR.mkdir(parents=True, exist_ok=True)
    date_tag = game.date.replace(".", "")
    base_name = f"scorecard_{date_tag}_{game.title}"

    html_path = SUNDAYSCREEN_DIR / f"{base_name}.html"
    pdf_path  = SUNDAYSCREEN_DIR / f"{base_name}.pdf"

    # ── 4. HTML 저장 ───────────────────────────
    content = build_html(game)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[✓] HTML 저장: {html_path}")

    # ── 5. PDF 변환 ───────────────────────────
    if not args.no_pdf:
        save_pdf(html_path, pdf_path)

    # ── 6. 요약 ───────────────────────────────
    print(f"\n  게임  : {game.title}")
    print(f"  코스  : {game.course}  ({game.date})")
    print(f"  참가자: {len(game.players)}명 / {game.total_players}명")
    print(f"  폴더  : {SUNDAYSCREEN_DIR}\n")


if __name__ == "__main__":
    main()
