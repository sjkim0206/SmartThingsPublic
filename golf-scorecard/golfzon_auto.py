#!/usr/bin/env python3
"""
골프존 네트워크플레이 스코어 자동 수집
Python (Termux) + Auto.js 하이브리드 방식

역할 분리:
  golfzon_autojs.js  →  Auto.js 앱에서 실행 (UI 탭/스와이프)
  golfzon_auto.py    →  Termux에서 실행   (데이터 파싱 + 스코어카드 생성)

통신 방식 (파일 IPC, ADB 불필요):
  /sdcard/golfzon/ready.json  Auto.js 시작 신호
  /sdcard/golfzon/cmd.json    Python → Auto.js 명령
  /sdcard/golfzon/done.json   Auto.js → Python 완료 신호
  /sdcard/golfzon/dump.json   Auto.js → Python 화면 노드 JSON



사전 준비:
  1. AutoJs6 설치 → 설정 → 접근성 → AutoJs6 활성화
  2. Auto.js에서 golfzon_autojs.js 실행 (서비스 대기 유지)
  3. termux-setup-storage  (최초 1회)
  4. python3 golfzon_auto.py
"""

import json, time, sys, re, subprocess
from datetime import datetime
from pathlib import Path

# ── 경로 설정 ──────────────────────────────────────────
GOLFZON_PKG = "com.golfzon.android"
BASE_DIR    = Path("/sdcard/golfzon")
CMD_FILE    = BASE_DIR / "cmd.json"
DONE_FILE   = BASE_DIR / "done.json"
DUMP_FILE   = BASE_DIR / "dump.json"
READY_FILE  = BASE_DIR / "ready.json"
OUTPUT_DIR  = Path("/sdcard/sundayscreen")

BASE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════
# Auto.js IPC 통신 레이어
# ══════════════════════════════════════════════════════

_seq      = 0
_screen_w = 1080
_screen_h = 2316


def wait_for_autojs(timeout=120):
    """Auto.js 서비스가 ready.json을 쓸 때까지 대기"""
    print("[~] Auto.js 서비스 대기 중...")
    print("    → Auto.js 앱에서 golfzon_autojs.js 를 실행하세요")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if READY_FILE.exists():
            try:
                info = json.loads(READY_FILE.read_text())
                global _screen_w, _screen_h
                _screen_w = info.get("screen_w", 1080)
                _screen_h = info.get("screen_h", 2316)
                print(f"[✓] Auto.js 연결됨 (v{info.get('version','?')}, "
                      f"화면 {_screen_w}x{_screen_h})")
                return True
            except Exception:
                pass
        time.sleep(1)
    return False


def send(action, timeout=30, **kwargs):
    """명령 전송 → done.json 응답 대기 → 결과 반환"""
    global _seq
    _seq += 1
    cmd = {"seq": _seq, "action": action}
    cmd.update(kwargs)

    if DONE_FILE.exists():
        DONE_FILE.unlink()

    CMD_FILE.write_text(json.dumps(cmd, ensure_ascii=False))

    deadline = time.time() + timeout
    while time.time() < deadline:
        if DONE_FILE.exists():
            try:
                return json.loads(DONE_FILE.read_text())
            except Exception:
                pass
        time.sleep(0.3)

    raise TimeoutError(f"Auto.js 응답 없음 (action={action}, {timeout}s 초과)")


# ── 고수준 UI 액션 ─────────────────────────────────────

def tap_text(text, wait=1.2, timeout=10):
    r = send("tap_text", text=text, wait=int(wait * 1000), timeout=timeout + 5)
    return r.get("found", False)


def tap_contains(text, wait=1.2, timeout=10):
    r = send("tap_contains", text=text, wait=int(wait * 1000), timeout=timeout + 5)
    return r.get("found", False)


def tap(x, y, wait=1.2):
    send("tap_xy", x=x, y=y, wait=int(wait * 1000), timeout=10)


def swipe_up(wait=0.8):
    send("swipe_up", wait=int(wait * 1000), timeout=10)


def swipe_to_top():
    for _ in range(3):
        send("swipe_down", wait=500, timeout=10)


def back(wait=1.2):
    send("back", wait=int(wait * 1000), timeout=10)


def dump():
    """화면 덤프 요청 → JSON 노드 리스트 반환"""
    send("dump", timeout=15)
    if not DUMP_FILE.exists():
        return None
    try:
        return json.loads(DUMP_FILE.read_text())
    except Exception:
        return None


def launch_app():
    send("launch", pkg=GOLFZON_PKG, wait=4000, timeout=15)


# ══════════════════════════════════════════════════════
# 노드 파싱 유틸  (JSON 기반 — ADB XML 대신)
# ══════════════════════════════════════════════════════
# 노드 형식: {"text":"...", "desc":"...", "id":"...",
#             "bounds":[left,top,right,bottom], "clickable":bool}

def center(node):
    b = node["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def find(nodes, text=None, has=None, res_id=None):
    if nodes is None:
        return None
    for n in nodes:
        if text   is not None and n.get("text", "") == text:     return n
        if has    is not None and has in n.get("text", ""):       return n
        if res_id is not None and res_id in n.get("id", ""):      return n
    return None


def find_all(nodes, text=None, has=None):
    out = []
    if nodes is None:
        return out
    for n in nodes:
        if text is not None and n.get("text", "") == text:   out.append(n)
        elif has is not None and has in n.get("text", ""):   out.append(n)
    return out


def row_texts(nodes, y_ref, tol=45):
    """y_ref 근처 같은 행의 텍스트를 x 순서대로 반환"""
    items = []
    for n in (nodes or []):
        b  = n.get("bounds", [0, 0, 1, 1])
        ny = (b[1] + b[3]) // 2
        if abs(ny - y_ref) < tol:
            t = n.get("text", "").strip()
            if t:
                items.append((b[0], t))
    items.sort()
    return [t for _, t in items]


def tap_node(node, wait=1.2):
    x, y = center(node)
    tap(x, y, wait)


def tap_text_node(nodes, text=None, has=None, wait=1.2):
    node = find(nodes, text=text, has=has)
    if node:
        tap_node(node, wait)
        return True
    return False


# ══════════════════════════════════════════════════════
# 팝업 닫기
# ══════════════════════════════════════════════════════

def close_popup():
    """앱 실행 후 공지사항/광고 팝업 닫기"""
    nodes = dump()
    if nodes is None:
        return

    banner = find(nodes, has="오늘 하루 보지 않기")
    if not banner:
        if tap_text("닫기", wait=1.0):
            print("  [공지] 닫기 버튼 클릭")
        return

    y_ref = center(banner)[1]
    tap_text("오늘 하루 보지 않기", wait=0.5)

    candidates = []
    for n in nodes:
        b  = n.get("bounds", [0, 0, 1, 1])
        ny = (b[1] + b[3]) // 2
        nx = (b[0] + b[2]) // 2
        if abs(ny - y_ref) > 80:
            continue

        txt      = n.get("text", "").strip()
        desc_txt = n.get("desc", "").strip()
        clickable = n.get("clickable", False)
        w_node   = b[2] - b[0]

        score = 0
        if nx > _screen_w // 2:          score += 2
        if w_node <= 200:                score += 2
        if clickable:                    score += 3
        if "닫기" in desc_txt:           score += 5
        if "close" in desc_txt.lower(): score += 5
        if txt in ("X", "×", "✕"):      score += 5
        if b[2] > _screen_w * 0.8:      score += 2

        candidates.append((score, b[2], n, nx, ny))

    if not candidates:
        tap(_screen_w - 80, y_ref, wait=1.0)
        return

    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
    best = candidates[0]
    print(f"  [공지] X버튼 탭: ({best[3]},{best[4]}) score={best[0]}")
    tap(best[3], best[4], wait=1.0)
    print("  [공지] 팝업 닫기 완료")


def wait_for(text_str, timeout=20, has=False):
    """화면에 해당 텍스트가 나타날 때까지 dump 반복"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        nodes = dump()
        node  = find(nodes,
                     has=text_str if has else None,
                     text=text_str if not has else None)
        if node:
            return nodes
        time.sleep(1)
    return None


# ══════════════════════════════════════════════════════
# 참가자 / 스코어 파싱
# ══════════════════════════════════════════════════════

SCORE_RE = re.compile(r"^([+-]\d+|E|\+0|0)$")
RANK_RE  = re.compile(r"^\d{1,2}$")
SKIP     = {"스트로크", "롱기", "니어", "다기록", "신페리오", "홀인원",
            "라운드", "참여", "완료", "랭킹기준", "스트로크플레이",
            "Par", "Score", "Hole", "Putt", "Sensor", "T", ""}


def extract_players(nodes, seen):
    """dump 노드에서 신규 참가자 추출"""
    new_players = []
    for n in (nodes or []):
        s = n.get("text", "").strip()
        if not (SCORE_RE.match(s) or s in ("+0", "E", "0")):
            continue
        y = center(n)[1]
        for txt in row_texts(nodes, y, tol=50):
            if (txt not in SKIP
                    and not SCORE_RE.match(txt)
                    and not RANK_RE.match(txt)
                    and not re.match(r"^\d+명", txt)
                    and txt not in seen
                    and len(txt) >= 2):
                val = 0
                try:
                    val = int(s.replace("+", ""))
                except ValueError:
                    pass
                seen.add(txt)
                new_players.append({"name": txt, "total_relative": val})
                break
    return new_players


def parse_scores(nodes):
    """스코어카드 화면에서 홀별 타수 추출"""
    scores = []
    for n in (nodes or []):
        if n.get("text", "").strip() != "Score":
            continue
        y    = center(n)[1]
        nums = [int(t) for t in row_texts(nodes, y, tol=30)
                if t != "Score" and re.match(r"^-?\d+$", t)]
        if len(nums) == 9:    scores.extend(nums)
        elif len(nums) == 10: scores.extend(nums[:9])
        if len(scores) >= 18: return scores[:18]
    return scores[:18] if scores else None


def parse_par(nodes):
    """파 데이터 추출"""
    pars = []
    for n in (nodes or []):
        if n.get("text", "").strip() != "Par":
            continue
        y    = center(n)[1]
        nums = [int(t) for t in row_texts(nodes, y, tol=30)
                if re.match(r"^[345]$", t.strip())]
        if len(nums) == 9:    pars.extend(nums)
        elif len(nums) == 10: pars.extend(nums[:9])
        if len(pars) >= 18:   return pars[:18]
    return [4, 3, 4, 4, 5, 3, 4, 5, 4,  4, 5, 4, 3, 4, 4, 4, 3, 5]


def parse_meta(nodes):
    """코스명 / 날짜 / 참가자 수 추출"""
    course, date, n_total = "코스 미확인", "", 0
    for n in (nodes or []):
        t = n.get("text", "").strip()
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
    """총점만 알 때 홀별 배분"""
    scores = [0] * 18
    rem = total
    i   = 0
    while rem != 0 and i < 100:
        d = 1 if rem > 0 else -1
        scores[i % 18] += d
        rem -= d
        i   += 1
    return scores


# ══════════════════════════════════════════════════════
# HTML / 스코어카드 생성
# ══════════════════════════════════════════════════════

def score_badge(s):
    txt = f"+{s}" if s > 0 else str(s)
    if s <= -2: return f'<span class="badge eagle">{txt}</span>'
    if s == -1: return f'<span class="badge birdie">{txt}</span>'
    if s ==  0: return f'<span class="badge par">0</span>'
    if s ==  1: return f'<span class="badge bogey">{txt}</span>'
    return             f'<span class="badge double-bogey">{txt}</span>'


def scorecard_table(name, rank, par_list, scores, front=True):
    if front:
        holes, pars, sc = list(range(1, 10)),  par_list[:9],  scores[:9]
    else:
        holes, pars, sc = list(range(10, 19)), par_list[9:], scores[9:]
    par_t   = sum(pars)
    score_t = sum(sc)
    total   = sum(scores)
    hole_td  = "".join(f"<td>{h}</td>" for h in holes)
    par_td   = "".join(f"<td>{p}</td>" for p in pars)
    score_td = "".join(f"<td>{score_badge(s)}</td>" for s in sc)
    s_str    = f"+{score_t}" if score_t > 0 else str(score_t)
    t_str    = f"+{total}"  if total   > 0 else str(total)
    medal    = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, str(rank))
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
    course   = game_data.get("course", "")
    date     = game_data.get("date", "")
    n_total  = game_data.get("total_players", len(players))
    now      = datetime.now().strftime("%Y.%m.%d %H:%M")

    cards = ""
    for p in players:
        sc     = p.get("scores", [0] * 18)
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
    tag       = game_data["date"].replace(".", "")
    html_path = OUTPUT_DIR / f"scorecard_{tag}.html"
    pdf_path  = OUTPUT_DIR / f"scorecard_{tag}.pdf"

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(game_data))
    print(f"  [✓] HTML: {html_path}")

    for cmd in [
        f'weasyprint "{html_path}" "{pdf_path}"',
        f'wkhtmltopdf "{html_path}" "{pdf_path}"',
    ]:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, timeout=120)
            if r.returncode == 0:
                print(f"  [✓] PDF:  {pdf_path}")
                return str(pdf_path)
        except Exception:
            continue

    print(f"  [!] PDF 변환기 없음 → HTML만 저장")
    print(f"      브라우저에서 열기: termux-open \"{html_path}\"")
    print(f"      → 공유 → 인쇄 → PDF로 저장")
    return str(html_path)


# ══════════════════════════════════════════════════════
# 메인 흐름
# ══════════════════════════════════════════════════════

def main():
    print("\n" + "═" * 52)
    print("  골프존 네트워크플레이 스코어 자동 수집")
    print("  (Python + Auto.js 하이브리드)")
    print("═" * 52 + "\n")

    # ── 0. Auto.js 연결 대기 ────────────────────────────
    if not wait_for_autojs(timeout=120):
        sys.exit("[오류] Auto.js 서비스가 응답하지 않습니다.\n"
                 "  → Auto.js 앱에서 golfzon_autojs.js 를 실행하세요.")

    # ── 날짜 입력 ───────────────────────────────────────
    today        = datetime.now().strftime("%Y.%m.%d")
    user_date    = input(f"경기 날짜 입력 [{today}]: ").strip()
    target_date  = user_date if user_date else today
    print(f"  대상 날짜: {target_date}\n")

    # ── 1. 앱 실행 ──────────────────────────────────────
    print("[1/6] 골프존 앱 실행...")
    launch_app()

    # ── 1-b. 공지 팝업 닫기 ─────────────────────────────
    close_popup()

    # ── 2. 전체메뉴 ─────────────────────────────────────
    print("[2/6] 전체메뉴 → 네트워크플레이 이동...")
    for attempt in range(5):
        if tap_text("전체메뉴", wait=2.0):
            break
        time.sleep(1)
    else:
        sys.exit("[오류] '전체메뉴'를 찾지 못했습니다.")

    # ── 3. 네트워크플레이 ───────────────────────────────
    for attempt in range(5):
        if tap_text("네트워크플레이", wait=2.0):
            break
        time.sleep(1)
    else:
        sys.exit("[오류] '네트워크플레이'를 찾지 못했습니다.")

    # ── 4. 날짜 경기 선택 ───────────────────────────────
    print(f"[3/6] {target_date} 경기 탐색...")
    found_game = False
    for _ in range(10):
        nodes = dump()
        node  = find(nodes, has=target_date)
        if node:
            tap_node(node, wait=3.0)
            found_game = True
            break
        swipe_up()

    if not found_game:
        sys.exit(f"[오류] '{target_date}' 날짜 경기를 찾지 못했습니다.")

    # ── 5. 메타 정보 / 라운드 완료 확인 ────────────────
    print("[4/6] 라운드 정보 확인...")
    course   = "코스 미확인"
    date     = target_date
    n_total  = 0
    par_list = [4, 3, 4, 4, 5, 3, 4, 5, 4,  4, 5, 4, 3, 4, 4, 4, 3, 5]

    try:
        nodes = dump()
        course, meta_date, n_total = parse_meta(nodes)
        par_list = parse_par(nodes)
        if meta_date:
            date = meta_date

        for n in (nodes or []):
            t  = n.get("text", "")
            m  = re.search(r"라운드 완료\s*(\d+)명.*참여\s*(\d+)명", t)
            if m:
                done, total = int(m.group(1)), int(m.group(2))
                n_total = total
                print(f"  라운드 완료 {done}명 / 참여 {total}명")
                if done < total:
                    ans = input(f"  아직 {total-done}명 라운드 중. 계속하시겠습니까? (y/N): ").strip().lower()
                    if ans != "y":
                        sys.exit("중단.")
                break
    except Exception as e:
        print(f"  확인 실패: {e} - 계속 진행")

    # ── 6. 참가자 목록 수집 ─────────────────────────────
    print("[5/6] 참가자 목록 수집 중...")
    swipe_to_top()
    time.sleep(1)

    players = []
    seen    = set()
    no_new  = 0

    for i in range(20):
        nodes = dump()
        if nodes is None:
            continue

        new_p = extract_players(nodes, seen)
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

    # ── 7. 스코어카드 수집 ──────────────────────────────
    print("[6/6] 스코어카드 수집 중...")
    swipe_to_top()
    time.sleep(1)

    for i, p in enumerate(players):
        name = p["name"]
        print(f"  [{i+1}/{len(players)}] {name}...")

        found = False
        for _ in range(10):
            nodes = dump()
            node  = find(nodes, text=name)
            if node:
                tap_node(node, wait=2.0)
                found = True
                break
            swipe_up()

        if not found:
            print(f"    ⚠ 화면에서 찾지 못함 - 건너뜀")
            p["scores"] = fallback_scores(p["total_relative"])
            continue

        try:
            sc_nodes = dump()
            scores   = parse_scores(sc_nodes)
            if scores and len(scores) == 18:
                p["scores"] = scores
                p_list      = parse_par(sc_nodes)
                if len(p_list) == 18:
                    par_list = p_list
                print(f"    ✓ {scores}")
            else:
                p["scores"] = fallback_scores(p["total_relative"])
                print(f"    ⚠ 홀 데이터 부족 → 총점 대체")
        except Exception:
            p["scores"] = fallback_scores(p["total_relative"])

        back()

    # ── 8. HTML/PDF 생성 ────────────────────────────────
    print("\n스코어카드 생성 중...")
    game_data = {
        "date":          date,
        "course":        course,
        "total_players": n_total or len(players),
        "par_list":      par_list,
        "players":       players,
    }
    out = save_output(game_data)

    # Auto.js 종료
    try:
        send("quit", timeout=5)
    except Exception:
        pass

    print(f"\n{'═'*52}")
    print(f"  완료! → {out}")
    print(f"{'═'*52}\n")


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
