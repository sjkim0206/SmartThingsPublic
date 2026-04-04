#!/usr/bin/env python3
"""
골프존 앱 자동 스크래핑 도구 v3
ADB UI 자동화로 골프존 앱을 직접 조작하여 스코어 데이터를 추출합니다.

사전 준비:
  1. Termux에서 ADB 설치: pkg install android-tools
  2. 폰 설정 → 개발자 옵션 → 무선 디버깅 → 활성화
  3. 무선 디버깅 화면에서 IP:PORT 확인 후:
     adb connect <IP>:<PORT>
  4. 이 스크립트 실행: python golfzon_auto.py
"""

import subprocess, time, json, re, sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# ── 설정 ───────────────────────────────────────
GOLFZON_PACKAGE = "com.golfzon.android"
SUNDAYSCREEN_DIR = Path.home() / "storage" / "downloads" / "sundayscreen"
UI_DUMP_PATH    = "/sdcard/ui_gz.xml"
SWIPE_SPEED     = 600   # ms


# ══════════════════════════════════════════════
# ADB 래퍼
# ══════════════════════════════════════════════
class ADB:
    def shell(self, *args, timeout=20):
        try:
            r = subprocess.run(["adb", "shell", *args],
                               capture_output=True, text=True, timeout=timeout)
            return r.stdout.strip()
        except subprocess.TimeoutExpired:
            return ""

    def run(self, *args, timeout=10):
        try:
            r = subprocess.run(["adb", *args],
                               capture_output=True, text=True, timeout=timeout)
            return r.stdout.strip()
        except subprocess.TimeoutExpired:
            return ""

    def tap(self, x, y, wait=1.0):
        self.shell("input", "tap", str(int(x)), str(int(y)))
        time.sleep(wait)

    def swipe_up(self, distance=700, speed=None):
        sp = speed or SWIPE_SPEED
        h = self._screen_height()
        mid_x = self._screen_width() // 2
        y1 = int(h * 0.75)
        y2 = max(int(h * 0.75) - distance, 100)
        self.shell("input", "swipe", str(mid_x), str(y1), str(mid_x), str(y2), str(sp))
        time.sleep(0.8)

    def swipe_down(self, distance=400):
        h = self._screen_height()
        mid_x = self._screen_width() // 2
        y1 = int(h * 0.3)
        y2 = int(h * 0.3) + distance
        self.shell("input", "swipe", str(mid_x), str(y1), str(mid_x), str(y2), str(SWIPE_SPEED))
        time.sleep(0.8)

    def back(self):
        self.shell("input", "keyevent", "4")
        time.sleep(1.0)

    def dump_ui(self):
        self.shell("uiautomator", "dump", "--compressed", UI_DUMP_PATH)
        xml_str = self.shell("cat", UI_DUMP_PATH)
        if not xml_str or "<hierarchy" not in xml_str:
            return None
        try:
            return ET.fromstring(xml_str)
        except ET.ParseError:
            return None

    def _screen_size(self):
        out = self.shell("wm", "size")
        m = re.search(r'(\d+)x(\d+)', out)
        if m:
            return int(m.group(1)), int(m.group(2))
        return 1080, 2340

    def _screen_width(self):
        return self._screen_size()[0]

    def _screen_height(self):
        return self._screen_size()[1]

    def launch(self, package):
        self.shell("monkey", "-p", package, "-c",
                   "android.intent.category.LAUNCHER", "1")
        time.sleep(3.5)

    def is_connected(self):
        out = self.run("devices")
        lines = [l for l in out.splitlines()[1:] if "\tdevice" in l]
        return len(lines) > 0


# ══════════════════════════════════════════════
# UI 헬퍼
# ══════════════════════════════════════════════
class UI:
    def __init__(self, adb: ADB):
        self.adb = adb

    def refresh(self):
        return self.adb.dump_ui()

    # ── 노드 탐색 ──────────────────────────────
    def find(self, root, text=None, contains=None, res_id=None):
        if root is None:
            return None
        for node in root.iter("node"):
            if text is not None and node.get("text", "") == text:
                return node
            if contains is not None and contains in node.get("text", ""):
                return node
            if res_id is not None and res_id in node.get("resource-id", ""):
                return node
        return None

    def find_all(self, root, text=None, contains=None):
        results = []
        if root is None:
            return results
        for node in root.iter("node"):
            if text is not None and node.get("text", "") == text:
                results.append(node)
            elif contains is not None and contains in node.get("text", ""):
                results.append(node)
        return results

    def center(self, node):
        b = node.get("bounds", "[0,0][1,1]")
        nums = list(map(int, re.findall(r"\d+", b)))
        return (nums[0] + nums[2]) // 2, (nums[1] + nums[3]) // 2

    def y_center(self, node):
        return self.center(node)[1]

    # ── 탭 (텍스트로) ──────────────────────────
    def tap_text(self, text, exact=True, wait=1.2):
        root = self.refresh()
        node = self.find(root, text=text if exact else None,
                         contains=text if not exact else None)
        if node:
            x, y = self.center(node)
            self.adb.tap(x, y, wait)
            return True
        return False

    # ── 대기 ──────────────────────────────────
    def wait(self, text, timeout=20, contains=False):
        for _ in range(timeout * 2):
            root = self.refresh()
            node = self.find(root, text=text if not contains else None,
                             contains=text if contains else None)
            if node:
                return root
            time.sleep(0.5)
        return None

    # ── 텍스트 전체 목록 ──────────────────────
    def all_texts(self, root):
        return [n.get("text", "").strip()
                for n in root.iter("node") if n.get("text", "").strip()]

    # ── 같은 행(y좌표 인접)의 텍스트 ─────────
    def same_row_texts(self, root, y_ref, tolerance=45):
        texts = []
        for node in root.iter("node"):
            b = node.get("bounds", "")
            nums = list(map(int, re.findall(r"\d+", b)))
            if nums:
                ny = (nums[1] + nums[3]) // 2
                if abs(ny - y_ref) < tolerance:
                    t = node.get("text", "").strip()
                    if t:
                        texts.append((nums[0], t))  # (x좌표, 텍스트)
        texts.sort(key=lambda x: x[0])
        return [t for _, t in texts]


# ══════════════════════════════════════════════
# 골프존 스크래퍼
# ══════════════════════════════════════════════
class GolfzonScraper:
    SCORE_RE = re.compile(r"^([+-]\d+|E|\+0)$")
    RANK_RE  = re.compile(r"^\d{1,2}$")
    HOLE_RE  = re.compile(r"^\d{1,2}$")

    def __init__(self):
        self.adb  = ADB()
        self.ui   = UI(self.adb)
        self.today      = datetime.now().strftime("%y.%m.%d")   # 26.03.29
        self.today_full = datetime.now().strftime("%Y.%m.%d")   # 2026.03.29

    # ── 0. ADB 연결 확인 ──────────────────────
    def check_adb(self):
        if not self.adb.is_connected():
            print("\n[오류] ADB 기기가 연결되지 않았습니다.")
            print("  Termux에서 아래 명령을 실행하세요:\n")
            print("  1) pkg install android-tools")
            print("  2) 폰 설정 → 개발자 옵션 → 무선 디버깅 → ON")
            print("  3) 무선 디버깅 탭 → IP주소 및 포트 확인")
            print("  4) adb connect <IP>:<PORT>")
            print("  5) 다시 이 스크립트 실행\n")
            sys.exit(1)
        print("[✓] ADB 연결 확인")

    # ── 1. 골프존 앱 실행 ─────────────────────
    def launch(self):
        print("[1/6] 골프존 앱 실행 중...")
        self.adb.launch(GOLFZON_PACKAGE)
        root = self.ui.wait("스크린", timeout=25)
        if not root:
            raise RuntimeError("골프존 홈 화면 로딩 실패")
        print("      ✓ 완료")

    # ── 2. 스크린 탭 → 스코어카드 ────────────
    def go_scorecard(self):
        print("[2/6] 스코어카드로 이동...")

        # 스크린 탭 클릭
        if not self.ui.tap_text("스크린"):
            raise RuntimeError("'스크린' 탭을 찾을 수 없음")
        time.sleep(1.5)

        # 스코어카드 아이콘 클릭
        if not self.ui.tap_text("스코어카드"):
            raise RuntimeError("'스코어카드' 버튼을 찾을 수 없음")
        time.sleep(2.0)
        print("      ✓ 완료")

    # ── 3. 오늘 날짜 네트워크플레이 게임 선택 ─
    def select_today_game(self):
        print(f"[3/6] 오늘 게임 탐색 ({self.today_full} 네트워크플레이)...")

        for scroll in range(8):
            root = self.ui.refresh()
            if root is None:
                time.sleep(1)
                continue

            # 날짜 텍스트를 포함하는 노드 찾기
            date_nodes = self.ui.find_all(root, contains=self.today)
            for dnode in date_nodes:
                dy = self.ui.y_center(dnode)
                row_texts = self.ui.same_row_texts(root, dy, tolerance=60)
                if "네트워크플레이" in row_texts:
                    x, y = self.ui.center(dnode)
                    # 행 전체 탭 (코스명이 탭 대상)
                    self.adb.tap(x, y, wait=2.0)
                    print("      ✓ 오늘 게임 선택")
                    return

            self.adb.swipe_up()

        raise RuntimeError(f"오늘({self.today_full}) 네트워크플레이 게임을 찾을 수 없음")

    # ── 4. 네트워크플레이 결과 화면으로 이동 ──
    def go_network_result(self):
        print("[4/6] 네트워크플레이 결과 화면으로 이동...")
        # 스코어카드 상세 → 하단에 "네트워크플레이 >" 링크 있음
        for _ in range(6):
            if self.ui.tap_text("네트워크플레이 >", wait=2.0):
                print("      ✓ 완료")
                return
            if self.ui.tap_text("네트워크플레이", exact=False, wait=2.0):
                print("      ✓ 완료")
                return
            self.adb.swipe_up(distance=500)
        raise RuntimeError("'네트워크플레이' 링크를 찾을 수 없음")

    # ── 5. 참가자 목록 + 홀별 점수 수집 ───────
    def collect_all_scores(self):
        print("[5/6] 참가자 목록 및 홀별 점수 수집 중...")

        # 5-a. 플레이어 목록 수집 (스크롤하면서 전원)
        players_basic = self._collect_player_list()
        print(f"      → {len(players_basic)}명 확인")

        # 5-b. 각 플레이어 홀별 점수 수집
        players_full = []
        for i, p in enumerate(players_basic):
            print(f"      → [{i+1}/{len(players_basic)}] {p['name']} 홀별 점수 수집...")
            scores = self._collect_hole_scores(p['name'], p['total_relative'])
            p['scores'] = scores
            players_full.append(p)

        return players_full

    # ── 5-a. 플레이어 목록 수집 ───────────────
    def _collect_player_list(self):
        """랭킹 화면 스크롤하며 선수명+총점 수집"""
        players = []
        seen    = set()
        SKIP    = {"스트로크", "롱기", "니어", "다기록", "신페리오", "홀인원",
                   "라운드", "참여", "완료", "랭킹기준", "스트로크플레이",
                   "Par", "Score", "Hole", "Putt", "Sensor", ""}

        # 화면 위로 초기화
        self.adb.swipe_down()
        time.sleep(0.5)

        no_new_count = 0
        for scroll in range(20):
            root = self.ui.refresh()
            if root is None:
                continue

            # 점수 노드 찾기 (−7, +1, +0, E 등)
            new_found = False
            for node in root.iter("node"):
                score_text = node.get("text", "").strip()
                if not self.SCORE_RE.match(score_text) and score_text not in ("+0", "E", "0"):
                    continue

                y_ref = self.ui.y_center(node)
                row   = self.ui.same_row_texts(root, y_ref, tolerance=50)

                for txt in row:
                    if (txt not in SKIP and
                        not self.SCORE_RE.match(txt) and
                        not self.RANK_RE.match(txt) and
                        not re.match(r"^\d+명", txt) and
                        txt not in seen and
                        len(txt) >= 2):

                        val = 0
                        if score_text not in ("E", "+0", "0"):
                            try:
                                val = int(score_text)
                            except ValueError:
                                pass

                        seen.add(txt)
                        players.append({
                            "rank": len(players) + 1,
                            "name": txt,
                            "total_relative": val
                        })
                        new_found = True

            if new_found:
                no_new_count = 0
            else:
                no_new_count += 1
                if no_new_count >= 3:
                    break

            self.adb.swipe_up(distance=600)

        # 총점 기준 재정렬
        players.sort(key=lambda x: x["total_relative"])
        for i, p in enumerate(players):
            p["rank"] = i + 1

        return players

    # ── 5-b. 선수 클릭 → 홀별 점수 수집 ──────
    def _collect_hole_scores(self, name, total_relative):
        """선수 이름 탭 → 펼쳐진 스코어카드에서 18홀 점수 추출"""
        # 선수 이름 찾아서 탭
        for scroll in range(8):
            root = self.ui.refresh()
            node = self.ui.find(root, text=name)
            if node:
                x, y = self.ui.center(node)
                self.adb.tap(x, y, wait=1.5)
                break
            self.adb.swipe_up(distance=400)
        else:
            print(f"        ⚠ {name} 을 화면에서 찾지 못함 — 0점으로 처리")
            return [0] * 18

        # 스코어카드 행 파싱
        scores = self._parse_scorecard_rows()
        if len(scores) == 18:
            return scores

        # 못 찾으면 총점으로 균등 분배
        print(f"        ⚠ 홀 데이터 부족({len(scores)}개) — 총점으로 대체")
        return self._fallback_scores(total_relative)

    # ── 스코어카드 행 파싱 ────────────────────
    def _parse_scorecard_rows(self):
        """
        펼쳐진 스코어카드에서 Score 행의 18개 값 추출
        골프존 앱 형식: Score | 0 | 0 | -1 | 0 | ... (9홀) / (9홀)
        """
        scores = []

        for scroll in range(4):
            root = self.ui.refresh()
            if root is None:
                time.sleep(0.5)
                continue

            # "Score" 텍스트 노드 찾기
            score_label_nodes = self.ui.find_all(root, text="Score")

            for slabel in score_label_nodes:
                sy = self.ui.y_center(slabel)
                row_pairs = self.ui.same_row_texts(root, sy, tolerance=30)

                # Score 행에서 숫자/상대점수 추출
                row_scores = []
                for t in row_pairs:
                    t = t.strip()
                    if t == "Score":
                        continue
                    # 상대점수 또는 T(합계) 제외
                    if re.match(r"^-?\d+$", t):
                        row_scores.append(int(t))

                # 9홀 분량이면 추가
                if len(row_scores) == 9:
                    scores.extend(row_scores)
                elif len(row_scores) == 10:
                    # 마지막은 합계(T)이므로 제외
                    scores.extend(row_scores[:9])

            if len(scores) >= 18:
                return scores[:18]

            # 더 보기 위해 아래로 스크롤
            self.adb.swipe_up(distance=400)

        return scores[:18] if len(scores) >= 18 else scores

    def _fallback_scores(self, total):
        """총점으로 18홀 균등 분배 (정확한 홀 데이터 없을 때)"""
        scores = [0] * 18
        remaining = total
        i = 0
        while remaining != 0 and i < 18:
            delta = 1 if remaining > 0 else -1
            scores[i] += delta
            remaining -= delta
            i = (i + 1) % 18
        return scores

    # ── 6. 코스 파(Par) 추출 ──────────────────
    def _collect_par_list(self, root):
        """Par 행에서 18홀 파 정보 추출"""
        par_nodes = self.ui.find_all(root, text="Par")
        par_list  = []
        for pnode in par_nodes:
            py  = self.ui.y_center(pnode)
            row = self.ui.same_row_texts(root, py, tolerance=30)
            nums = []
            for t in row:
                if re.match(r"^[345]$", t.strip()):
                    nums.append(int(t.strip()))
            if len(nums) == 9:
                par_list.extend(nums)
            elif len(nums) == 10:
                par_list.extend(nums[:9])
            if len(par_list) >= 18:
                return par_list[:18]

        # 기본값 (찾지 못한 경우)
        return [4,3,4,4,5,3,4,5,4, 4,5,4,3,4,4,4,3,5]

    # ── 6. 게임 메타 정보 수집 ────────────────
    def collect_game_meta(self):
        root = self.ui.refresh()
        # 코스명, 날짜, 총인원 추출
        texts = self.ui.all_texts(root)

        course  = "코스 미확인"
        title   = "네트워크플레이"
        n_total = 16
        par_list = [4,3,4,4,5,3,4,5,4, 4,5,4,3,4,4,4,3,5]

        for t in texts:
            if "CC" in t or "GC" in t or "골프" in t:
                course = t
                break
        for t in texts:
            m = re.search(r"(\d+)명", t)
            if m:
                n_total = int(m.group(1))
                break

        par_list = self._collect_par_list(root)
        return course, title, n_total, par_list

    # ── 메인 실행 ──────────────────────────────
    def run(self):
        print("\n" + "═"*52)
        print("  골프존 네트워크플레이 자동 스크래핑")
        print("═"*52 + "\n")

        self.check_adb()
        self.launch()
        self.go_scorecard()
        self.select_today_game()

        # 게임 메타 (코스명, 파 등)
        course, title, n_total, par_list = self.collect_game_meta()

        self.go_network_result()

        # 선수 데이터 수집
        players = self.collect_all_scores()

        print(f"\n[6/6] 스코어카드 생성 중...")

        # JSON 구성
        game_data = {
            "game_id":          self.today_full.replace(".", ""),
            "title":            title,
            "course":           course,
            "date":             self.today_full,
            "total_players":    n_total,
            "finished_players": len(players),
            "par_list":         par_list,
            "players":          players,
        }

        # JSON 저장
        SUNDAYSCREEN_DIR.mkdir(parents=True, exist_ok=True)
        json_path = SUNDAYSCREEN_DIR / f"game_{self.today_full.replace('.','')}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(game_data, f, ensure_ascii=False, indent=2)
        print(f"      ✓ JSON 저장: {json_path}")

        # 스코어카드 HTML 생성
        scorecard_script = Path(__file__).parent / "golfzon_scorecard.py"
        if scorecard_script.exists():
            import subprocess
            result = subprocess.run(
                ["python3", str(scorecard_script),
                 "--input", str(json_path), "--no-pdf"],
                capture_output=True, text=True
            )
            print(result.stdout.strip())
            if result.returncode != 0:
                print(result.stderr.strip())
        else:
            print("      ⚠ golfzon_scorecard.py 를 찾을 수 없어 HTML 생성 건너뜀")

        print(f"\n  완료! 결과 폴더: {SUNDAYSCREEN_DIR}\n")
        return game_data


# ══════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════
if __name__ == "__main__":
    scraper = GolfzonScraper()
    try:
        scraper.run()
    except KeyboardInterrupt:
        print("\n[중단] 사용자가 종료했습니다.")
    except Exception as e:
        print(f"\n[오류] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
