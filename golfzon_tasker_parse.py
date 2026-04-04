#!/usr/bin/env python3
"""
골프존 Tasker 파서 v1
Tasker가 uiautomator dump로 저장한 XML 파일들을 파싱하여
전체 참가자 스코어카드 PDF를 생성합니다.

사용법:
  python3 golfzon_tasker_parse.py --list /sdcard/Pictures/golf_scores/ranking.xml
      → 참가자 목록 JSON 출력 (Tasker에서 호출)

  python3 golfzon_tasker_parse.py --generate /sdcard/Pictures/golf_scores/
      → 모든 dump 파일 파싱 후 PDF 생성
"""

import sys
import os
import re
import json
import glob
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

SCORES_DIR = Path("/sdcard/Pictures/golf_scores")
SUNDAYSCREEN_DIR = Path.home() / "storage" / "downloads" / "sundayscreen"
SCORECARD_SCRIPT = Path(__file__).parent / "golfzon_scorecard.py"

SCORE_RE = re.compile(r"^([+-]\d+|0)$")
RANK_RE  = re.compile(r"^\d{1,2}$")
SKIP     = {"스트로크", "롱기", "니어", "다기록", "신페리오", "홀인원",
            "라운드", "참여", "완료", "랭킹기준", "스트로크플레이",
            "Par", "Score", "Hole", "Putt", "Sensor", "T", ""}


# ══════════════════════════════════════════════
# UI dump 파싱 공통
# ══════════════════════════════════════════════

def load_dump(path):
    try:
        tree = ET.parse(path)
        return tree.getroot()
    except Exception as e:
        print(f"[ERR] dump 파싱 실패: {path} ({e})", file=sys.stderr)
        return None


def all_nodes(root):
    return list(root.iter("node")) if root is not None else []


def node_center(node):
    b = node.get("bounds", "[0,0][1,1]")
    nums = list(map(int, re.findall(r"\d+", b)))
    if len(nums) >= 4:
        return (nums[0] + nums[2]) // 2, (nums[1] + nums[3]) // 2
    return 0, 0


def same_row_texts(root, y_ref, tolerance=45):
    texts = []
    for node in all_nodes(root):
        b = node.get("bounds", "")
        nums = list(map(int, re.findall(r"\d+", b)))
        if len(nums) >= 4:
            ny = (nums[1] + nums[3]) // 2
            if abs(ny - y_ref) < tolerance:
                t = node.get("text", "").strip()
                if t:
                    texts.append((nums[0], t))
    texts.sort(key=lambda x: x[0])
    return [t for _, t in texts]


# ══════════════════════════════════════════════
# 랭킹 화면 파싱 → 참가자 목록
# ══════════════════════════════════════════════

def parse_ranking(dump_path):
    """
    랭킹 화면 dump에서 참가자 이름, 순위, 총점 추출.
    반환: [{"rank": 1, "name": "...", "total_relative": -7}, ...]
    """
    root = load_dump(dump_path)
    if root is None:
        return []

    players = []
    seen    = set()

    for node in all_nodes(root):
        score_text = node.get("text", "").strip()

        # 총점 패턴: +1, -3, 0, +0
        is_total = (SCORE_RE.match(score_text) or
                    score_text in ("+0", "E", "0", "-0"))
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
                    val = int(score_text.replace("+", ""))
                except ValueError:
                    pass

                seen.add(txt)
                players.append({
                    "rank":           len(players) + 1,
                    "name":           txt,
                    "total_relative": val,
                })
                break  # 한 행에서 이름은 하나

    # 총점 기준 재정렬
    players.sort(key=lambda x: x["total_relative"])
    for i, p in enumerate(players):
        p["rank"] = i + 1

    return players


# ══════════════════════════════════════════════
# 스코어카드 화면 파싱 → 18홀 점수
# ══════════════════════════════════════════════

def parse_scorecard(dump_path):
    """
    참가자 스코어카드 dump에서 18홀 상대 점수 추출.
    반환: [0, -1, 0, ...] (18개)
    """
    root = load_dump(dump_path)
    if root is None:
        return None

    scores = []

    for node in all_nodes(root):
        if node.get("text", "").strip() != "Score":
            continue

        y_ref = node_center(node)[1]
        row   = same_row_texts(root, y_ref, tolerance=30)

        row_scores = []
        for t in row:
            t = t.strip()
            if t == "Score":
                continue
            if re.match(r"^-?\d+$", t):
                row_scores.append(int(t))

        if len(row_scores) == 9:
            scores.extend(row_scores)
        elif len(row_scores) == 10:
            scores.extend(row_scores[:9])

        if len(scores) >= 18:
            return scores[:18]

    return scores[:18] if scores else None


def parse_par_list(dump_path):
    """Par 행에서 18홀 파 추출"""
    root = load_dump(dump_path)
    if root is None:
        return [4,3,4,4,5,3,4,5,4, 4,5,4,3,4,4,4,3,5]

    par_list = []
    for node in all_nodes(root):
        if node.get("text", "").strip() != "Par":
            continue
        y_ref = node_center(node)[1]
        row   = same_row_texts(root, y_ref, tolerance=30)
        nums  = [int(t) for t in row if re.match(r"^[345]$", t.strip())]
        if len(nums) == 9:
            par_list.extend(nums)
        elif len(nums) == 10:
            par_list.extend(nums[:9])
        if len(par_list) >= 18:
            return par_list[:18]

    return [4,3,4,4,5,3,4,5,4, 4,5,4,3,4,4,4,3,5]


def parse_game_meta(dump_path):
    """코스명, 게임 타이틀, 날짜, 참가자 수 추출"""
    root = load_dump(dump_path)
    if root is None:
        return "코스 미확인", "네트워크플레이", "", 16

    course  = "코스 미확인"
    title   = "네트워크플레이"
    date    = ""
    n_total = 16

    for node in all_nodes(root):
        t = node.get("text", "").strip()
        if ("CC" in t or "GC" in t or "골프장" in t) and len(t) < 40:
            course = t
        m = re.search(r"(\d{4}\.\d{2}\.\d{2})", t)
        if m:
            date = m.group(1)
        m2 = re.search(r"참여\s*(\d+)명", t)
        if m2:
            n_total = int(m2.group(1))

    return course, title, date, n_total


# ══════════════════════════════════════════════
# 점수 보정 (총점과 홀별 합계가 다를 때)
# ══════════════════════════════════════════════

def fallback_scores(total):
    """총점으로 18홀 균등 분배"""
    scores    = [0] * 18
    remaining = total
    i         = 0
    while remaining != 0 and i < 100:
        delta = 1 if remaining > 0 else -1
        scores[i % 18] += delta
        remaining -= delta
        i += 1
    return scores


# ══════════════════════════════════════════════
# --list 모드: 참가자 목록 JSON 출력
# ══════════════════════════════════════════════

def cmd_list(dump_path):
    players = parse_ranking(dump_path)
    result  = {
        "count": len(players),
        "names": [p["name"] for p in players],
        "data":  players,
    }
    print(json.dumps(result, ensure_ascii=False))


# ══════════════════════════════════════════════
# --generate 모드: 모든 dump 파싱 + PDF 생성
# ══════════════════════════════════════════════

def cmd_generate(folder):
    folder    = Path(folder)
    rank_dump = folder / "ranking.xml"

    if not rank_dump.exists():
        print(f"[ERR] ranking.xml 없음: {rank_dump}", file=sys.stderr)
        sys.exit(1)

    # 1. 참가자 목록
    players  = parse_ranking(rank_dump)
    par_list = parse_par_list(rank_dump)

    # 2. 게임 메타
    course, title, date, n_total = parse_game_meta(rank_dump)

    if not date:
        import datetime
        date = datetime.date.today().strftime("%Y.%m.%d")

    print(f"[INFO] 코스: {course}  날짜: {date}  참가자: {len(players)}명")

    # 3. 각 참가자 스코어 수집
    for p in players:
        name      = p["name"]
        dump_file = folder / f"score_{name}.xml"

        if dump_file.exists():
            scores = parse_scorecard(str(dump_file))
            if scores and len(scores) == 18:
                p["scores"] = scores
                print(f"  ✓ {name}: {scores}")
                continue

        # dump 파일 없거나 파싱 실패 → 총점으로 대체
        print(f"  ⚠ {name}: dump 없음 → 총점 대체")
        p["scores"] = fallback_scores(p["total_relative"])

    # 4. JSON 생성
    game_data = {
        "game_id":          date.replace(".", ""),
        "title":            title,
        "course":           course,
        "date":             date,
        "total_players":    n_total,
        "finished_players": len(players),
        "par_list":         par_list,
        "players":          players,
    }

    SUNDAYSCREEN_DIR.mkdir(parents=True, exist_ok=True)
    json_path = SUNDAYSCREEN_DIR / f"game_{date.replace('.','')}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(game_data, f, ensure_ascii=False, indent=2)
    print(f"[✓] JSON 저장: {json_path}")

    # 5. golfzon_scorecard.py로 PDF 생성
    if SCORECARD_SCRIPT.exists():
        result = subprocess.run(
            ["python3", str(SCORECARD_SCRIPT), "--input", str(json_path)],
            capture_output=True, text=True
        )
        print(result.stdout.strip())
        if result.returncode != 0:
            print(result.stderr.strip(), file=sys.stderr)
    else:
        print(f"[WARN] golfzon_scorecard.py 없음: {SCORECARD_SCRIPT}", file=sys.stderr)


# ══════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "--list" and len(sys.argv) >= 3:
        cmd_list(sys.argv[2])

    elif mode == "--generate" and len(sys.argv) >= 3:
        cmd_generate(sys.argv[2])

    else:
        print(__doc__)
        sys.exit(1)
