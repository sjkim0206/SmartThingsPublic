#!/usr/bin/env python3
"""
골프존 네트워크플레이 스코어 자동 수집
uiautomator dump + input tap 방식 (ADB 불필요)

실행: python3 golfzon_auto.py
"""

import subprocess, time, sys, re, json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# ── 설정 ────────────────────────────────────────
GOLFZON_PKG  = "com.golfzon.android"
GOLFZON_ACT  = "com.golfzon.android.main.activity.MainActivity"
SCORES_DIR   = Path("/sdcard/Pictures/golf_scores")
OUTPUT_DIR   = Path.home() / "storage" / "downloads" / "sundayscreen"
TMP_DUMP     = str(SCORES_DIR / "tmp.xml")


# ══════════════════════════════════════════════
# Shell 래퍼 (ADB 없이 직접 실행)
# ══════════════════════════════════════════════

def sh(cmd, timeout=30):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()

def tap(x, y, wait=1.2):
    sh(f"input tap {x} {y}")
    time.sleep(wait)

def swipe_up(wait=0.8):
    sh("input swipe 540 1400 540 700 600")
    time.sleep(wait)

def swipe_to_top():
    for _ in range(3):
        sh("input swipe 540 700 540 1400 400")
        time.sleep(0.5)

def back(wait=1.2):
    sh("input keyevent 4")
    time.sleep(wait)


# ══════════════════════════════════════════════
# UI dump 파싱
# ══════════════════════════════════════════════

def dump(path=TMP_DUMP):
    sh(f"uiautomator dump \"{path}\"")
    time.sleep(0.5)
    try:
        return ET.parse(path).getroot()
    except Exception:
        return None

def center(node):
    nums = list(map(int, re.findall(r"\d+", node.get("bounds", "[0,0][1,1]"))))
    return (nums[0]+nums[2])//2, (nums[1]+nums[3])//2 if len(nums) >= 4 else (0, 0)

def find(root, text=None, has=None, res_id=None):
    """text: 완전일치 / has: 부분일치 / res_id: resource-id 포함"""
    if root is None:
        return None
    for node in root.iter("node"):
        if text    is not None and node.get("text","") == text:           return node
        if has     is not None and has in node.get("text",""):            return node
        if res_id  is not None and res_id in node.get("resource-id",""): return node
    return None

def find_all(root, text=None, has=None):
    out = []
    if root is None:
        return out
    for node in root.iter("node"):
        if text is not None and node.get("text","") == text:  out.append(node)
        elif has is not None and has in node.get("text",""):  out.append(node)
    return out

def row_texts(root, y_ref, tol=45):
    """y_ref 근처 같은 행의 텍스트를 x 순서대로 반환"""
    items = []
    for node in root.iter("node"):
        nums = list(map(int, re.findall(r"\d+", node.get("bounds",""))))
        if len(nums) >= 4:
            ny = (nums[1]+nums[3])//2
            if abs(ny-y_ref) < tol:
                t = node.get("text","").strip()
                if t:
                    items.append((nums[0], t))
    items.sort()
    return [t for _, t in items]

def tap_node(node, wait=1.2):
    x, y = center(node)
    tap(x, y, wait)

def tap_text(root, text=None, has=None, wait=1.2):
    node = find(root, text=text, has=has)
    if node:
        tap_node(node, wait)
        return True
    return False

def wait_for(text, timeout=20, has=False):
    """화면에 해당 텍스트가 나타날 때까지 대기"""
    for _ in range(timeout * 2):
        root = dump()
        node = find(root, has=text if has else None,
                         text=text if not has else None)
        if node:
            return root
        time.sleep(0.5)
    return None


# ══════════════════════════════════════════════
# 참가자 파싱 상수
# ══════════════════════════════════════════════

SCORE_RE = re.compile(r"^([+-]\d+|E|\+0|0)$")
RANK_RE  = re.compile(r"^\d{1,2}$")
SKIP     = {"스트로크","롱기","니어","다기록","신페리오","홀인원",
            "라운드","참여","완료","랭킹기준","스트로크플레이",
            "Par","Score","Hole","Putt","Sensor","T",""}

def extract_players(root, seen):
    """dump root에서 신규 참가자 추출"""
    new_players = []
    for node in root.iter("node"):
        s = node.get("text","").strip()
        if not (SCORE_RE.match(s) or s in ("+0","E","0")):
            continue
        y = center(node)[1]
        for txt in row_texts(root, y, tol=50):
            if (txt not in SKIP
                    and not SCORE_RE.match(txt)
                    and not RANK_RE.match(txt)
                    and not re.match(r"^\d+명", txt)
                    and txt not in seen
                    and len(txt) >= 2):
                val = 0
                try:
                    val = int(s.replace("+",""))
                except ValueError:
                    pass
                seen.add(txt)
                new_players.append({"name": txt, "total_relative": val})
                break
    return new_players


# ══════════════════════════════════════════════
# 스코어카드 파싱
# ══════════════════════════════════════════════

def parse_scores(root):
    scores = []
    for node in root.iter("node"):
        if node.get("text","").strip() != "Score":
            continue
        y = center(node)[1]
        nums = [int(t) for t in row_texts(root, y, tol=30)
                if t != "Score" and re.match(r"^-?\d+$", t)]
        if len(nums) == 9:   scores.extend(nums)
        elif len(nums) == 10: scores.extend(nums[:9])
        if len(scores) >= 18: return scores[:18]
    return scores[:18] if scores else None

def parse_par(root):
    pars = []
    for node in root.iter("node"):
        if node.get("text","").strip() != "Par":
            continue
        y = center(node)[1]
        nums = [int(t) for t in row_texts(root, y, tol=30)
                if re.match(r"^[345]$", t.strip())]
        if len(nums) == 9:   pars.extend(nums)
        elif len(nums) == 10: pars.extend(nums[:9])
        if len(pars) >= 18: return pars[:18]
    return [4,3,4,4,5,3,4,5,4, 4,5,4,3,4,4,4,3,5]

def parse_meta(root):
    course, date, n_total = "코스 미확인", "", 0
    for node in root.iter("node"):
        t = node.get("text","").strip()
        if ("CC" in t or "GC" in t) and len(t) < 40:
            course = t
        m = re.search(r"(\d{4}\.\d{2}\.\d{2})", t)
        if m:
            date = m.group(1)
        m2 = re.search(r"참여\s*(\d+)명", t)
        if m2:
            n_total = int(m2.group(1))
    return course, date, n_total

def fallback_scores(total):
    scores = [0]*18
    rem = total
    i = 0
    while rem != 0 and i < 100:
        d = 1 if rem > 0 else -1
        scores[i%18] += d
        rem -= d
        i += 1
    return scores


# ══════════════════════════════════════════════
# HTML / PDF 생성
# ══════════════════════════════════════════════

def score_badge(s):
    txt = str(s) if s != 0 else "0"
    if s <= -2: return f'<span class="badge eagle">{txt}</span>'
    if s == -1: return f'<span class="badge birdie">{txt}</span>'
    if s ==  0: return f'<span class="badge par">{txt}</span>'
    if s ==  1: return f'<span class="badge bogey">{txt}</span>'
    return f'<span class="badge double-bogey">{txt}</span>'

def scorecard_table(name, rank, par_list, scores, front=True):
    if front:
        holes, pars, sc = list(range(1,10)), par_list[:9], scores[:9]
    else:
        holes, pars, sc = list(range(10,19)), par_list[9:], scores[9:]
    par_t   = sum(pars)
    score_t = sum(sc)
    total   = sum(scores)

    hole_td  = "".join(f"<td>{h}</td>" for h in holes)
    par_td   = "".join(f"<td>{p}</td>" for p in pars)
    score_td = "".join(f"<td>{score_badge(s)}</td>" for s in sc)
    s_str    = f"+{score_t}" if score_t > 0 else str(score_t)
    t_str    = f"+{total}"  if total   > 0 else str(total)
    medal    = {1:"🥇",2:"🥈",3:"🥉"}.get(rank, str(rank))

    return f"""
<div class="player-section">
  <div class="player-header">
    <span class="rank">{medal}</span>
    <span class="pname">{name}</span>
    <span class="total">{t_str}</span>
  </div>
  <table>
    <tr class="hole-row"><td class="label">Hole</td>{hole_td}<td class="label-t">T</td></tr>
    <tr class="par-row"> <td class="label">Par</td>{par_td}<td class="par-t">{par_t}</td></tr>
    <tr class="score-row"><td class="label">Score</td>{score_td}<td class="score-t">{s_str}</td></tr>
  </table>
</div>"""

CSS = """
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
       background:#f4f4f4; padding:16px; color:#222; }
.header { background:linear-gradient(135deg,#1a4fd6,#0a2fa0);
          color:#fff; padding:20px 24px; border-radius:12px 12px 0 0; }
.header h1 { font-size:1.5rem; margin-bottom:4px; }
.header .meta { font-size:.85rem; opacity:.85; }
.header .stat { margin-top:8px; font-size:.82rem; opacity:.9; }
.player-section { background:#fff; padding:14px 16px 8px; }
.player-header { display:flex; align-items:center; gap:8px; margin-bottom:8px; }
.rank  { font-size:1.1rem; min-width:28px; }
.pname { font-weight:700; font-size:1rem; flex:1; }
.total { font-weight:800; font-size:1.1rem; color:#1a4fd6; }
table  { width:100%; border-collapse:collapse; font-size:.82rem; margin-bottom:6px; }
td     { text-align:center; padding:5px 2px; }
.hole-row td  { background:#5a6472; color:#fff; font-weight:600; padding:6px 2px; }
.par-row  td  { background:#ececec; color:#666; }
.score-row td { background:#fff; }
.label   { text-align:left; padding-left:6px; font-weight:600; min-width:46px; }
.label-t,.par-t,.score-t { font-weight:700; }
.badge { display:inline-flex; align-items:center; justify-content:center;
         width:30px; height:30px; font-weight:600; font-size:.85rem; }
.birdie      { border:2px solid #e74c3c; border-radius:50%; color:#e74c3c; }
.eagle       { border:2px solid #e74c3c; border-radius:50%;
               outline:2px solid #e74c3c; outline-offset:2px; color:#e74c3c; }
.par         { color:#222; }
.bogey       { border:2px solid #3a7fd5; border-radius:3px; color:#3a7fd5; }
.double-bogey{ border:2px solid #3a7fd5; border-radius:3px;
               outline:2px solid #3a7fd5; outline-offset:2px; color:#3a7fd5; }
.player-divider { border:none; border-top:6px solid #f4f4f4; margin:0; }
footer { text-align:center; padding:12px; font-size:.72rem;
         color:#aaa; background:#fff; border-radius:0 0 12px 12px; }
"""

def build_html(game_data):
    players  = game_data["players"]
    par_list = game_data["par_list"]
    course   = game_data.get("course","")
    date     = game_data.get("date","")
    n_total  = game_data.get("total_players", len(players))
    now      = datetime.now().strftime("%Y.%m.%d %H:%M")

    cards = ""
    for p in players:
        sc = p.get("scores", [0]*18)
        cards += scorecard_table(p["name"], p["rank"], par_list, sc, front=True)
        cards += scorecard_table(p["name"], p["rank"], par_list, sc, front=False)
        cards += '<hr class="player-divider">'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>네트워크플레이 - {date}</title>
<style>{CSS}</style>
</head>
<body>
<div class="header">
  <h1>네트워크플레이</h1>
  <div class="meta">{course} &nbsp;|&nbsp; {date}</div>
  <div class="stat">라운드 완료 {len(players)}명 / 참여 {n_total}명</div>
</div>
{cards}
<footer>골프존 네트워크플레이 스코어카드 &nbsp;|&nbsp; 생성: {now}</footer>
</body>
</html>"""

def save_output(game_data):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tag       = game_data["date"].replace(".","")
    html_path = OUTPUT_DIR / f"scorecard_{tag}.html"
    pdf_path  = OUTPUT_DIR / f"scorecard_{tag}.pdf"

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(game_data))
    print(f"  [✓] HTML: {html_path}")

    for cmd in [
        f"weasyprint \"{html_path}\" \"{pdf_path}\"",
        f"wkhtmltopdf \"{html_path}\" \"{pdf_path}\"",
    ]:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, timeout=120)
            if r.returncode == 0:
                print(f"  [✓] PDF:  {pdf_path}")
                return str(pdf_path)
        except Exception:
            continue

    print(f"  [!] PDF 변환기 없음 → HTML만 저장")
    print(f"      termux-open \"{html_path}\"  →  공유 → 인쇄 → PDF")
    return str(html_path)


# ══════════════════════════════════════════════
# 메인 흐름
# ══════════════════════════════════════════════

def main():
    print("\n" + "═"*50)
    print("  골프존 네트워크플레이 스코어 자동 수집")
    print("═"*50 + "\n")

    # 날짜 설정 (기본값: 오늘)
    today = datetime.now().strftime("%Y.%m.%d")
    user_date = input(f"경기 날짜 입력 [{today}]: ").strip()
    target_date = user_date if user_date else today
    print(f"  대상 날짜: {target_date}\n")

    # ── 1. 앱 실행 및 폴더 초기화 ──────────────
    print("[1/6] 골프존 앱 실행...")
    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    sh(f"rm -f {SCORES_DIR}/*.xml")
    sh(f"am start -n {GOLFZON_PKG}/{GOLFZON_ACT}")
    time.sleep(4)

    # ── 2. 전체메뉴 클릭 ────────────────────────
    print("[2/6] 전체메뉴 → 네트워크플레이 이동...")
    for attempt in range(5):
        root = dump()
        if tap_text(root, text="전체메뉴", wait=2.0):
            break
        time.sleep(1)
    else:
        sys.exit("[오류] '전체메뉴'를 찾지 못했습니다.")

    # ── 3. 네트워크플레이 클릭 ──────────────────
    for attempt in range(5):
        root = dump()
        if tap_text(root, text="네트워크플레이", wait=2.0):
            break
        time.sleep(1)
    else:
        sys.exit("[오류] '네트워크플레이'를 찾지 못했습니다.")

    # ── 4. 날짜 경기 선택 ───────────────────────
    print(f"[3/6] {target_date} 경기 탐색...")
    found_game = False
    for _ in range(10):
        root = dump()
        if root is None:
            time.sleep(1)
            continue
        node = find(root, has=target_date)
        if node:
            tap_node(node, wait=3.0)
            found_game = True
            break
        swipe_up()

    if not found_game:
        sys.exit(f"[오류] '{target_date}' 날짜 경기를 찾지 못했습니다.")

    # ── 5. 라운드 완료 확인 ─────────────────────
    print("[4/6] 라운드 완료 여부 확인...")
    ranking_0 = str(SCORES_DIR / "ranking_0.xml")
    sh(f"uiautomator dump \"{ranking_0}\"")
    time.sleep(0.5)

    n_total = 0
    course  = "코스 미확인"
    date    = target_date
    par_list = [4,3,4,4,5,3,4,5,4, 4,5,4,3,4,4,4,3,5]

    try:
        r0 = ET.parse(ranking_0).getroot()
        course, meta_date, n_total = parse_meta(r0)
        par_list = parse_par(r0)
        if meta_date:
            date = meta_date

        for node in r0.iter("node"):
            t = node.get("text","")
            m = re.search(r"라운드 완료\s*(\d+)명.*참여\s*(\d+)명", t)
            if m:
                done, total = int(m.group(1)), int(m.group(2))
                n_total = total
                print(f"  라운드 완료 {done}명 / 참여 {total}명")
                if done < total:
                    ans = input(f"  아직 {total-done}명 라운드 중. 계속하시겠습니까? (y/N): ").strip().lower()
                    if ans != 'y':
                        sys.exit("중단.")
                break
    except Exception as e:
        print(f"  확인 실패: {e} - 계속 진행")

    # ── 6. 참가자 목록 수집 ─────────────────────
    print("[5/6] 참가자 목록 수집 중...")
    swipe_to_top()
    time.sleep(1)

    players = []
    seen    = set()
    no_new  = 0

    for i in range(20):
        rpath = str(SCORES_DIR / f"ranking_{i}.xml")
        sh(f"uiautomator dump \"{rpath}\"")
        time.sleep(0.5)

        try:
            root = ET.parse(rpath).getroot()
        except Exception:
            continue

        new_p = extract_players(root, seen)
        if new_p:
            players.extend(new_p)
            no_new = 0
            print(f"  스크롤 {i}: {len(new_p)}명 추가 (누적 {len(players)}명)")
        else:
            no_new += 1
            if no_new >= 3:
                break

        if n_total > 0 and len(players) >= n_total:
            break

        swipe_up()

    players.sort(key=lambda x: x["total_relative"])
    for i, p in enumerate(players):
        p["rank"] = i + 1
    print(f"  → 총 {len(players)}명 수집 완료")

    # ── 7. 스코어카드 수집 ──────────────────────
    print("[6/6] 스코어카드 수집 중...")
    swipe_to_top()
    time.sleep(1)

    for i, p in enumerate(players):
        name = p["name"]
        print(f"  [{i+1}/{len(players)}] {name}...")

        found = False
        for _ in range(10):
            root = dump()
            node = find(root, text=name)
            if node:
                tap_node(node, wait=2.0)
                found = True
                break
            swipe_up()

        if not found:
            print(f"    ⚠ 화면에서 찾지 못함 - 건너뜀")
            p["scores"] = fallback_scores(p["total_relative"])
            continue

        # 스코어카드 dump
        score_path = str(SCORES_DIR / f"score_{name}.xml")
        sh(f"uiautomator dump \"{score_path}\"")
        time.sleep(0.5)

        try:
            sc_root  = ET.parse(score_path).getroot()
            scores   = parse_scores(sc_root)
            if scores and len(scores) == 18:
                p["scores"]   = scores
                p_list        = parse_par(sc_root)
                if len(p_list) == 18:
                    par_list  = p_list
                print(f"    ✓ {scores}")
            else:
                p["scores"] = fallback_scores(p["total_relative"])
                print(f"    ⚠ 홀 데이터 부족 → 총점 대체")
        except Exception:
            p["scores"] = fallback_scores(p["total_relative"])

        back()

    # ── 8. 스코어카드 생성 ──────────────────────
    print("\n스코어카드 생성 중...")

    game_data = {
        "date":             date,
        "course":           course,
        "total_players":    n_total or len(players),
        "par_list":         par_list,
        "players":          players,
    }

    out = save_output(game_data)

    print(f"\n{'═'*50}")
    print(f"  완료! → {out}")
    print(f"{'═'*50}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[중단] 사용자가 종료했습니다.")
    except SystemExit as e:
        print(e)
    except Exception as e:
        import traceback
        print(f"\n[오류] {e}")
        traceback.print_exc()
        sys.exit(1)
