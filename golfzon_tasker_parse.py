#!/usr/bin/env python3
"""
골프존 Tasker 파서 v2
Tasker가 uiautomator dump로 저장한 XML 파일들을 파싱하여
전체 참가자 스코어카드 PDF를 생성합니다.

사용법:
  --check   <ranking.xml>
      라운드 완료 여부 확인. 출력: "OK" 또는 "INCOMPLETE:X/Y"

  --list-page <ranking_N.xml> [기존이름1|이름2|...]
      단일 dump에서 신규 참가자 추출. JSON 출력.

  --generate <dump_folder/>
      모든 dump 파싱 후 스코어카드 PDF 생성.
"""

import sys, os, re, json, glob, subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

SCORES_DIR      = Path("/sdcard/Pictures/golf_scores")
SUNDAYSCREEN_DIR = Path.home() / "storage" / "downloads" / "sundayscreen"
SCORECARD_SCRIPT = Path(__file__).parent / "golfzon_scorecard.py"

SCORE_RE = re.compile(r"^([+-]\d+|0)$")
RANK_RE  = re.compile(r"^\d{1,2}$")
SKIP     = {"스트로크","롱기","니어","다기록","신페리오","홀인원",
            "라운드","참여","완료","랭킹기준","스트로크플레이",
            "Par","Score","Hole","Putt","Sensor","T",""}


# ══════════════════════════════════════════════
# UI dump 공통
# ══════════════════════════════════════════════

def load_dump(path):
    try:
        return ET.parse(path).getroot()
    except Exception as e:
        print(f"[ERR] dump 파싱 실패: {path} ({e})", file=sys.stderr)
        return None

def all_nodes(root):
    return list(root.iter("node")) if root is not None else []

def node_center(node):
    b = node.get("bounds","[0,0][1,1]")
    nums = list(map(int, re.findall(r"\d+", b)))
    return ((nums[0]+nums[2])//2, (nums[1]+nums[3])//2) if len(nums)>=4 else (0,0)

def same_row_texts(root, y_ref, tolerance=45):
    texts = []
    for node in all_nodes(root):
        nums = list(map(int, re.findall(r"\d+", node.get("bounds",""))))
        if len(nums) >= 4:
            ny = (nums[1]+nums[3])//2
            if abs(ny-y_ref) < tolerance:
                t = node.get("text","").strip()
                if t:
                    texts.append((nums[0], t))
    texts.sort(key=lambda x: x[0])
    return [t for _,t in texts]


# ══════════════════════════════════════════════
# --check: 라운드 완료 여부
# ══════════════════════════════════════════════

def cmd_check(dump_path):
    root = load_dump(dump_path)
    if root is None:
        print("UNKNOWN"); return

    for node in all_nodes(root):
        t = node.get("text","")
        # "라운드 완료 16명 / 참여 16명" 형식
        m = re.search(r"라운드 완료\s*(\d+)명.*참여\s*(\d+)명", t)
        if m:
            done  = int(m.group(1))
            total = int(m.group(2))
            if done == total:
                print("OK")
            else:
                print(f"INCOMPLETE:{done}/{total}")
            return

    print("UNKNOWN")


# ══════════════════════════════════════════════
# 랭킹 화면 파싱 (단일 dump)
# ══════════════════════════════════════════════

def parse_ranking_page(root):
    """dump root에서 참가자 이름+총점 추출"""
    players = []
    seen    = set()

    for node in all_nodes(root):
        score_text = node.get("text","").strip()
        is_total   = (SCORE_RE.match(score_text) or
                      score_text in ("+0","E","0","-0"))
        if not is_total:
            continue

        y_ref = node_center(node)[1]
        row   = same_row_texts(root, y_ref, tolerance=50)

        for txt in row:
            if (txt not in SKIP and
                    not SCORE_RE.match(txt) and
                    not RANK_RE.match(txt) and
                    not re.match(r"^\d+명", txt) and
                    txt not in seen and
                    len(txt) >= 2):
                val = 0
                try:
                    val = int(score_text.replace("+",""))
                except ValueError:
                    pass
                seen.add(txt)
                players.append({"name": txt, "total_relative": val})
                break

    return players


# ══════════════════════════════════════════════
# --list-page: 신규 참가자 추출
# ══════════════════════════════════════════════

def cmd_list_page(dump_path, existing_raw=""):
    root = load_dump(dump_path)
    if root is None:
        print(json.dumps({"count":0,"names":[],"data":[]}, ensure_ascii=False))
        return

    existing = set(existing_raw.split("|")) if existing_raw else set()
    all_p    = parse_ranking_page(root)
    new_p    = [p for p in all_p if p["name"] not in existing]

    # 전체 참가자 수 확인
    total = 0
    for node in all_nodes(root):
        m = re.search(r"참여\s*(\d+)명", node.get("text",""))
        if m:
            total = int(m.group(1)); break

    print(json.dumps({
        "count":       len(new_p),
        "names":       [p["name"] for p in new_p],
        "data":        new_p,
        "total_players": total,
    }, ensure_ascii=False))


# ══════════════════════════════════════════════
# 스코어카드 파싱
# ══════════════════════════════════════════════

def parse_scorecard(dump_path):
    root = load_dump(dump_path)
    if root is None: return None
    scores = []
    for node in all_nodes(root):
        if node.get("text","").strip() != "Score": continue
        y_ref = node_center(node)[1]
        row   = same_row_texts(root, y_ref, tolerance=30)
        row_s = [int(t) for t in row if t!="Score" and re.match(r"^-?\d+$",t)]
        if len(row_s) == 9:   scores.extend(row_s)
        elif len(row_s) == 10: scores.extend(row_s[:9])
        if len(scores) >= 18: return scores[:18]
    return scores[:18] if scores else None

def parse_par_list(dump_path):
    root = load_dump(dump_path)
    if root is None: return [4,3,4,4,5,3,4,5,4, 4,5,4,3,4,4,4,3,5]
    par_list = []
    for node in all_nodes(root):
        if node.get("text","").strip() != "Par": continue
        y_ref = node_center(node)[1]
        row   = same_row_texts(root, y_ref, tolerance=30)
        nums  = [int(t) for t in row if re.match(r"^[345]$", t.strip())]
        if len(nums) == 9:   par_list.extend(nums)
        elif len(nums) == 10: par_list.extend(nums[:9])
        if len(par_list) >= 18: return par_list[:18]
    return [4,3,4,4,5,3,4,5,4, 4,5,4,3,4,4,4,3,5]

def parse_game_meta(dump_path):
    root = load_dump(dump_path)
    if root is None: return "코스 미확인","네트워크플레이","",16
    course,title,date,n_total = "코스 미확인","네트워크플레이","",16
    for node in all_nodes(root):
        t = node.get("text","").strip()
        if ("CC" in t or "GC" in t) and len(t)<40: course = t
        m = re.search(r"(\d{4}\.\d{2}\.\d{2})", t)
        if m: date = m.group(1)
        m2 = re.search(r"참여\s*(\d+)명", t)
        if m2: n_total = int(m2.group(1))
    return course, title, date, n_total

def fallback_scores(total):
    scores=[0]*18; remaining=total; i=0
    while remaining!=0 and i<100:
        delta=1 if remaining>0 else -1
        scores[i%18]+=delta; remaining-=delta; i+=1
    return scores


# ══════════════════════════════════════════════
# HTML 스코어카드 생성 (골프존 앱 디자인)
# ══════════════════════════════════════════════

def score_badge(score):
    """골프존 앱과 동일한 스코어 뱃지 HTML"""
    s = str(score) if score != 0 else "0"
    if score <= -2:
        # 이글: 빨간 두 겹 원
        return f'<span class="badge eagle">{s}</span>'
    elif score == -1:
        # 버디: 빨간 원
        return f'<span class="badge birdie">{s}</span>'
    elif score == 0:
        # 파: 테두리 없음
        return f'<span class="badge par">{s}</span>'
    elif score == 1:
        # 보기: 파란 사각형
        return f'<span class="badge bogey">{s}</span>'
    else:
        # 더블보기+: 파란 두 겹 사각형
        return f'<span class="badge double-bogey">{s}</span>'

def build_scorecard_table(name, rank, par_list, scores, front=True):
    """9홀 스코어카드 테이블 생성"""
    if front:
        holes   = list(range(1, 10))
        pars    = par_list[:9]
        sc      = scores[:9]
        par_t   = sum(pars)
        score_t = sum(sc)
    else:
        holes   = list(range(10, 19))
        pars    = par_list[9:]
        sc      = scores[9:]
        par_t   = sum(pars)
        score_t = sum(sc)

    hole_cells  = "".join(f'<td>{h}</td>' for h in holes)
    par_cells   = "".join(f'<td>{p}</td>' for p in pars)
    score_cells = "".join(f'<td>{score_badge(s)}</td>' for s in sc)

    score_t_str = f"+{score_t}" if score_t > 0 else str(score_t)
    total_all   = sum(scores)
    total_str   = f"+{total_all}" if total_all > 0 else str(total_all)

    medal = {1:"🥇",2:"🥈",3:"🥉"}.get(rank, str(rank))

    return f"""
<div class="player-section">
  <div class="player-header">
    <span class="rank">{medal}</span>
    <span class="pname">{name}</span>
    <span class="total">{total_str}</span>
  </div>
  <table>
    <tr class="hole-row">
      <td class="label">Hole</td>{hole_cells}<td class="label-t">T</td>
    </tr>
    <tr class="par-row">
      <td class="label">Par</td>{par_cells}<td class="par-t">{par_t}</td>
    </tr>
    <tr class="score-row">
      <td class="label">Score</td>{score_cells}<td class="score-t">{score_t_str}</td>
    </tr>
  </table>
</div>"""

def build_full_html(game_data):
    players  = game_data["players"]
    par_list = game_data["par_list"]
    title    = game_data.get("title","네트워크플레이")
    course   = game_data.get("course","")
    date     = game_data.get("date","")
    n_total  = game_data.get("total_players", len(players))
    now      = datetime.now().strftime("%Y.%m.%d %H:%M")

    cards = ""
    for p in players:
        scores = p.get("scores",[0]*18)
        cards += build_scorecard_table(p["name"], p["rank"], par_list, scores, front=True)
        cards += build_scorecard_table(p["name"], p["rank"], par_list, scores, front=False)
        cards += '<hr class="player-divider">'

    css = """
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
       background:#f4f4f4; padding:16px; color:#222; }

/* 헤더 */
.header { background:linear-gradient(135deg,#1a4fd6,#0a2fa0);
          color:#fff; padding:20px 24px; border-radius:12px 12px 0 0; }
.header h1 { font-size:1.5rem; margin-bottom:4px; }
.header .meta { font-size:.85rem; opacity:.85; }
.header .stat { margin-top:8px; font-size:.82rem; opacity:.9; }

/* 참가자 섹션 */
.player-section { background:#fff; margin-bottom:0;
                  padding:14px 16px 8px; }
.player-header { display:flex; align-items:center;
                 gap:8px; margin-bottom:8px; }
.rank  { font-size:1.1rem; min-width:28px; }
.pname { font-weight:700; font-size:1rem; flex:1; }
.total { font-weight:800; font-size:1.1rem; color:#1a4fd6; }

/* 테이블 */
table { width:100%; border-collapse:collapse;
        font-size:.82rem; margin-bottom:6px; }
td { text-align:center; padding:5px 2px; }

.hole-row td { background:#5a6472; color:#fff;
               font-weight:600; padding:6px 2px; }
.par-row  td { background:#ececec; color:#666; }
.score-row td { background:#fff; }
.label   { text-align:left; padding-left:6px;
           font-weight:600; min-width:46px; }
.label-t,.par-t,.score-t { font-weight:700; }

/* 뱃지 */
.badge { display:inline-flex; align-items:center;
         justify-content:center;
         width:30px; height:30px; font-weight:600;
         font-size:.85rem; }

/* 버디: 빨간 원 */
.birdie { border:2px solid #e74c3c; border-radius:50%; color:#e74c3c; }

/* 이글: 빨간 이중 원 */
.eagle  { border:2px solid #e74c3c; border-radius:50%;
          outline:2px solid #e74c3c; outline-offset:2px; color:#e74c3c; }

/* 파: 테두리 없음 */
.par    { color:#222; }

/* 보기: 파란 사각형 */
.bogey  { border:2px solid #3a7fd5; border-radius:3px; color:#3a7fd5; }

/* 더블보기+: 파란 이중 사각형 */
.double-bogey { border:2px solid #3a7fd5; border-radius:3px;
                outline:2px solid #3a7fd5; outline-offset:2px; color:#3a7fd5; }

.player-divider { border:none; border-top:6px solid #f4f4f4; margin:0; }

footer { text-align:center; padding:12px; font-size:.72rem;
         color:#aaa; background:#fff; border-radius:0 0 12px 12px; }

@media print {
  body { background:white; padding:0; }
  .player-divider { border-top:4px solid #eee; }
}
"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} - {date}</title>
<style>{css}</style>
</head>
<body>
<div class="header">
  <h1>{title}</h1>
  <div class="meta">{course} &nbsp;|&nbsp; {date}</div>
  <div class="stat">라운드 완료 {len(players)}명 / 참여 {n_total}명</div>
</div>
{cards}
<footer>골프존 네트워크플레이 스코어카드 &nbsp;|&nbsp; 생성: {now}</footer>
</body>
</html>"""


# ══════════════════════════════════════════════
# --generate: 전체 스코어카드 PDF 생성
# ══════════════════════════════════════════════

def cmd_generate(folder):
    folder    = Path(folder)
    rank_dump = folder / "ranking_0.xml"
    if not rank_dump.exists():
        rank_dump = folder / "ranking.xml"
    if not rank_dump.exists():
        print(f"[ERR] ranking dump 없음", file=sys.stderr); sys.exit(1)

    # 게임 메타
    course, title, date, n_total = parse_game_meta(str(rank_dump))
    par_list = parse_par_list(str(rank_dump))
    if not date:
        date = datetime.now().strftime("%Y.%m.%d")

    # 전체 참가자 목록 (여러 ranking_N.xml 병합)
    all_players = {}
    for rf in sorted(folder.glob("ranking_*.xml")):
        root = load_dump(str(rf))
        if root is None: continue
        for p in parse_ranking_page(root):
            if p["name"] not in all_players:
                all_players[p["name"]] = p

    players = list(all_players.values())
    players.sort(key=lambda x: x["total_relative"])
    for i,p in enumerate(players): p["rank"] = i+1

    print(f"[INFO] {course} | {date} | {len(players)}명")

    # 각 참가자 스코어 수집
    for p in players:
        name = p["name"]
        dump_file = folder / f"score_{name}.xml"
        if dump_file.exists():
            scores = parse_scorecard(str(dump_file))
            if scores and len(scores) == 18:
                p["scores"] = scores
                print(f"  ✓ {name}: {scores}")
                continue
        print(f"  ⚠ {name}: dump 없음 → 총점 대체")
        p["scores"] = fallback_scores(p["total_relative"])

    game_data = {
        "game_id":          date.replace(".",""),
        "title":            title,
        "course":           course,
        "date":             date,
        "total_players":    n_total,
        "finished_players": len(players),
        "par_list":         par_list,
        "players":          players,
    }

    SUNDAYSCREEN_DIR.mkdir(parents=True, exist_ok=True)
    tag       = date.replace(".","")
    html_path = SUNDAYSCREEN_DIR / f"scorecard_{tag}.html"
    pdf_path  = SUNDAYSCREEN_DIR / f"scorecard_{tag}.pdf"

    # HTML 저장
    with open(html_path,"w",encoding="utf-8") as f:
        f.write(build_full_html(game_data))
    print(f"[✓] HTML: {html_path}")

    # PDF 변환
    for cmd in [
        ["weasyprint", str(html_path), str(pdf_path)],
        ["wkhtmltopdf", str(html_path), str(pdf_path)],
    ]:
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            print(f"[✓] PDF: {pdf_path}"); return
        except Exception:
            continue

    print(f"[!] PDF 변환 실패 → HTML만 저장됨: {html_path}")
    print(f"    termux-open \"{html_path}\"  →  브라우저 → 공유 → 인쇄 → PDF")


# ══════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)

    mode = sys.argv[1]

    if mode == "--check" and len(sys.argv) >= 3:
        cmd_check(sys.argv[2])

    elif mode == "--list-page" and len(sys.argv) >= 3:
        existing = sys.argv[3] if len(sys.argv) >= 4 else ""
        cmd_list_page(sys.argv[2], existing)

    elif mode == "--generate" and len(sys.argv) >= 3:
        cmd_generate(sys.argv[2])

    else:
        print(__doc__); sys.exit(1)
