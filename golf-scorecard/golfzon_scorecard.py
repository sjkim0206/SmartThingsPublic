#!/usr/bin/env python3
"""
골프존 네트워크 플레이 스코어카드 통합 도구
Golfzon Network Play Scorecard Aggregator

골프존 앱에서 네트워크 플레이 결과를 읽어와 모든 참가자의
홀별 점수를 하나의 표로 만들어줍니다.
"""

import json
import argparse
import sys
from dataclasses import dataclass, field
from typing import Optional
import html


# ──────────────────────────────────────────────
# 데이터 구조
# ──────────────────────────────────────────────

@dataclass
class HoleScore:
    hole: int
    par: int
    strokes: int          # 실제 타수
    relative: int         # 파 기준 상대 점수 (−2=이글, −1=버디, 0=파, +1=보기 …)

    @property
    def label(self) -> str:
        """점수 라벨 반환 (이글, 버디, 파, 보기, 더블보기 등)"""
        mapping = {-3: "알바트로스", -2: "이글", -1: "버디", 0: "파", 1: "보기",
                   2: "더블보기", 3: "트리플보기"}
        return mapping.get(self.relative, f"+{self.relative}" if self.relative > 0 else str(self.relative))


@dataclass
class PlayerResult:
    rank: int
    name: str
    total_relative: int   # 전체 상대 점수
    front9: int           # 전반 9홀 합계
    back9: int            # 후반 9홀 합계
    holes: list[HoleScore] = field(default_factory=list)  # 홀별 점수 (18개)


@dataclass
class NetworkGame:
    game_id: str
    title: str            # 게임명 (예: ㅂㅂ11)
    course: str           # 코스명 (예: 백제 CC - 웅진/사비)
    date: str             # 날짜 (예: 2026.03.29)
    total_players: int
    finished_players: int
    par_list: list[int]   # 18홀 파 정보
    players: list[PlayerResult] = field(default_factory=list)


# ──────────────────────────────────────────────
# 데이터 파싱 (샘플 / 직접 입력 모드)
# ──────────────────────────────────────────────

def parse_from_json(data: dict) -> NetworkGame:
    """
    JSON 형식 데이터를 NetworkGame 객체로 변환합니다.

    JSON 형식 예시:
    {
      "game_id": "2026032900001",
      "title": "ㅂㅂ11",
      "course": "백제 CC - 웅진/사비",
      "date": "2026.03.29",
      "total_players": 16,
      "finished_players": 16,
      "par_list": [4,3,4,4,5,3,4,5,4, 4,5,4,3,4,4,4,3,5],
      "players": [
        {
          "rank": 1,
          "name": "[늘푸른]",
          "total_relative": -7,
          "front9": -3,
          "back9": -4,
          "scores": [0,0,-1,0,-1,0,-1,0,0, -1,-1,0,0,-1,-1,0,1,-1]
        },
        ...
      ]
    }
    """
    par_list = data["par_list"]
    players = []
    for p in data["players"]:
        scores_rel = p["scores"]  # 상대 점수 18개
        holes = []
        for i, rel in enumerate(scores_rel):
            hole_num = i + 1
            par = par_list[i]
            strokes = par + rel
            holes.append(HoleScore(hole=hole_num, par=par, strokes=strokes, relative=rel))

        front9 = sum(scores_rel[:9])
        back9 = sum(scores_rel[9:])

        players.append(PlayerResult(
            rank=p["rank"],
            name=p["name"],
            total_relative=p["total_relative"],
            front9=front9,
            back9=back9,
            holes=holes,
        ))

    return NetworkGame(
        game_id=data["game_id"],
        title=data["title"],
        course=data["course"],
        date=data["date"],
        total_players=data["total_players"],
        finished_players=data["finished_players"],
        par_list=par_list,
        players=players,
    )


# ──────────────────────────────────────────────
# 샘플 데이터 (스크린샷 기반)
# ──────────────────────────────────────────────

SAMPLE_DATA = {
    "game_id": "2026032900001",
    "title": "ㅂㅂ11",
    "course": "백제 CC - 웅진/사비",
    "date": "2026.03.29",
    "total_players": 16,
    "finished_players": 16,
    "par_list": [4, 3, 4, 4, 5, 3, 4, 5, 4,
                 4, 5, 4, 3, 4, 4, 4, 3, 5],
    "players": [
        {
            "rank": 1, "name": "[늘푸른]", "total_relative": -7,
            "scores": [0, 0, -1, 0, -1, 0, -1, 0, 0,
                       -1, -1, 0, 0, -1, -1, 0, 1, -1]
        },
        {
            "rank": 2, "name": "bonteng", "total_relative": -4,
            "scores": [0, 0, 0, -1, -1, 0, 0, -1, 0,
                       -1, 0, 0, 0, 0, -1, 0, 0, 0]
        },
        {
            "rank": 3, "name": "써클에너지", "total_relative": -3,
            "scores": [0, -1, 0, 0, -1, 0, 0, 0, -1,
                       0, -1, 0, 0, 0, 0, 0, 0, 0]
        },
        {
            "rank": 4, "name": "마차이새쯔", "total_relative": 0,
            "scores": [0, 0, 0, 0, 0, 1, 0, -1, 0,
                       0, 0, 1, 0, 0, 0, 0, -1, 0]
        },
        {
            "rank": 5, "name": "나 (사용자)", "total_relative": 1,
            "scores": [0, 1, 0, 0, 0, 0, 1, 0, -1,
                       0, 0, 1, 0, 0, 0, 0, 0, -1]
        },
    ]
}


# ──────────────────────────────────────────────
# HTML 출력 생성
# ──────────────────────────────────────────────

SCORE_STYLE = {
    -3: ("albatross", "#8B0000", "white"),   # 알바트로스
    -2: ("eagle",     "#FFD700", "black"),   # 이글
    -1: ("birdie",    "#FF4500", "white"),   # 버디
     0: ("par",       "transparent", "inherit"),
     1: ("bogey",     "#3A7FD5", "white"),   # 보기
     2: ("double",    "#1A1A6E", "white"),   # 더블보기
     3: ("triple",    "#000000", "white"),   # 트리플보기
}


def score_cell_html(rel: int, strokes: int) -> str:
    """홀 점수 셀 HTML 생성"""
    label_class, bg, color = SCORE_STYLE.get(rel, ("over", "#333", "white"))

    shape_class = ""
    if rel <= -2:
        shape_class = "double-circle"
    elif rel == -1:
        shape_class = "circle"
    elif rel == 1:
        shape_class = "square"
    elif rel >= 2:
        shape_class = "double-square"

    rel_str = f"+{rel}" if rel > 0 else str(rel)
    display = f"{strokes}<br><span class='rel-label'>{rel_str}</span>"

    style = f"background:{bg};color:{color};"
    return f'<td class="score-cell {label_class} {shape_class}" style="{style}">{display}</td>'


def relative_str(val: int) -> str:
    if val > 0:
        return f"+{val}"
    return str(val)


def build_html(game: NetworkGame) -> str:
    par_front = sum(game.par_list[:9])
    par_back  = sum(game.par_list[9:])
    par_total = par_front + par_back

    # ── 헤더 행 ──
    holes_front = "".join(f"<th>{h}</th>" for h in range(1, 10))
    holes_back  = "".join(f"<th>{h}</th>" for h in range(10, 19))
    par_front_cells = "".join(f"<td class='par-cell'>{p}</td>" for p in game.par_list[:9])
    par_back_cells  = "".join(f"<td class='par-cell'>{p}</td>" for p in game.par_list[9:])

    # ── 플레이어 행 ──
    player_rows = ""
    for player in game.players:
        rank_medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(player.rank, str(player.rank))
        front_cells = "".join(score_cell_html(h.relative, h.strokes) for h in player.holes[:9])
        back_cells  = "".join(score_cell_html(h.relative, h.strokes) for h in player.holes[9:])

        front_rel = relative_str(player.front9)
        back_rel  = relative_str(player.back9)
        total_rel = relative_str(player.total_relative)

        # 전반 행
        player_rows += f"""
        <tr class="player-front">
          <td class="rank-cell" rowspan="2">{rank_medal}</td>
          <td class="name-cell" rowspan="2">{html.escape(player.name)}</td>
          <td class="half-label">전반</td>
          {front_cells}
          <td class="subtotal-cell">{front_rel}</td>
          <td class="total-cell" rowspan="2"><strong>{total_rel}</strong></td>
        </tr>"""
        # 후반 행
        player_rows += f"""
        <tr class="player-back">
          <td class="half-label">후반</td>
          {back_cells}
          <td class="subtotal-cell">{back_rel}</td>
        </tr>"""

    legend_items = [
        ("double-circle", "이글 이상"),
        ("circle",        "버디"),
        ("par-cell",      "파"),
        ("square",        "보기"),
        ("double-square", "더블보기 이상"),
    ]
    legend_html = "".join(
        f'<span class="legend-item {cls}">{label}</span>' for cls, label in legend_items
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>골프존 네트워크 플레이 스코어카드 - {html.escape(game.title)}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
      background: #f0f2f5;
      padding: 20px;
      color: #222;
    }}
    .card {{
      background: white;
      border-radius: 16px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.12);
      overflow: hidden;
      max-width: 1400px;
      margin: 0 auto;
    }}
    .header {{
      background: linear-gradient(135deg, #1a4fd6 0%, #0a2fa0 100%);
      color: white;
      padding: 24px 28px;
    }}
    .header h1 {{ font-size: 1.8rem; margin-bottom: 6px; }}
    .header .meta {{ font-size: 0.95rem; opacity: 0.85; }}
    .header .stats {{
      margin-top: 12px;
      font-size: 0.9rem;
      opacity: 0.9;
    }}

    .legend {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      padding: 14px 20px;
      background: #f8f9fa;
      border-bottom: 1px solid #e0e0e0;
      font-size: 0.82rem;
    }}
    .legend-item {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 3px 10px;
      border-radius: 4px;
    }}
    .legend-item::before {{ content: "■"; font-size: 10px; }}
    .legend-item.double-circle {{ background: #FFD700; color: black; }}
    .legend-item.circle        {{ background: #FF4500; color: white; }}
    .legend-item.par-cell      {{ background: #eee; color: #333; }}
    .legend-item.square        {{ background: #3A7FD5; color: white; }}
    .legend-item.double-square {{ background: #1A1A6E; color: white; }}

    .table-wrap {{ overflow-x: auto; padding: 0; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
    }}

    /* 섹션 헤더 */
    .section-header th {{
      background: #2c3e50;
      color: white;
      text-align: center;
      padding: 8px 6px;
      font-weight: 600;
      font-size: 0.8rem;
    }}

    /* 파 행 */
    .par-row td {{
      background: #4a5568;
      color: #cfd8dc;
      text-align: center;
      padding: 6px 4px;
      font-size: 0.78rem;
    }}
    .par-cell {{ font-weight: bold; }}

    /* 플레이어 행 */
    .rank-cell {{
      text-align: center;
      font-size: 1.1rem;
      white-space: nowrap;
      padding: 6px 8px;
      vertical-align: middle;
      border-left: 3px solid #e0e0e0;
    }}
    .name-cell {{
      font-weight: 600;
      white-space: nowrap;
      padding: 6px 12px;
      vertical-align: middle;
      min-width: 100px;
    }}
    .half-label {{
      text-align: center;
      font-size: 0.75rem;
      color: #666;
      padding: 4px 6px;
      white-space: nowrap;
    }}
    .score-cell {{
      text-align: center;
      padding: 4px 3px;
      min-width: 36px;
      font-size: 0.82rem;
      font-weight: 600;
      vertical-align: middle;
    }}
    .score-cell .rel-label {{
      font-size: 0.68rem;
      font-weight: 400;
      opacity: 0.85;
    }}
    .subtotal-cell, .total-cell {{
      text-align: center;
      padding: 6px 8px;
      font-size: 0.88rem;
      min-width: 44px;
      vertical-align: middle;
    }}
    .total-cell {{ background: #f0f4ff; font-size: 1rem; }}

    /* 점수 모양 */
    .circle  {{ border-radius: 50%; }}
    .double-circle {{ border-radius: 50%; outline: 2px solid currentColor; }}
    .square  {{ border-radius: 2px; }}
    .double-square {{ border-radius: 2px; outline: 2px solid currentColor; }}

    /* 행 구분 */
    tr.player-front td {{ border-top: 1px solid #e0e0e0; }}
    tr.player-back  td {{ border-bottom: 2px solid #c8c8c8; }}

    /* 섹션 구분자 */
    .divider th {{
      background: #eceff1;
      padding: 4px;
      text-align: center;
      font-size: 0.78rem;
      color: #888;
      font-weight: 600;
      border-top: 2px solid #cfd8dc;
    }}

    /* 파 합계 행 */
    .par-total-row td {{
      background: #37474f;
      color: white;
      text-align: center;
      font-weight: bold;
      padding: 6px 4px;
    }}

    footer {{
      text-align: center;
      padding: 14px;
      font-size: 0.78rem;
      color: #aaa;
      background: #f8f9fa;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1>{html.escape(game.title)}</h1>
      <div class="meta">{html.escape(game.course)} &nbsp;|&nbsp; {html.escape(game.date)}</div>
      <div class="stats">
        라운드 완료 {game.finished_players}명 / 참여 {game.total_players}명 &nbsp;|&nbsp;
        Par {par_total} (전반 {par_front} / 후반 {par_back})
      </div>
    </div>

    <div class="legend">{legend_html}</div>

    <div class="table-wrap">
      <table>
        <!-- ── 전반 9홀 ── -->
        <thead>
          <tr class="section-header">
            <th colspan="2">순위 / 선수</th>
            <th>구분</th>
            {holes_front}
            <th>소계</th>
            <th>합계</th>
          </tr>
          <tr class="par-row">
            <td colspan="2">Par</td>
            <td></td>
            {par_front_cells}
            <td class="par-cell">{par_front}</td>
            <td class="par-cell">{par_total}</td>
          </tr>
        </thead>
        <tbody>
          {player_rows}
        </tbody>

        <!-- ── 후반 9홀 헤더 ── -->
        <thead>
          <tr class="divider">
            <th colspan="13">▼ 후반 9홀 (Hole 10–18)</th>
          </tr>
          <tr class="section-header">
            <th colspan="2">순위 / 선수</th>
            <th>구분</th>
            {holes_back}
            <th>소계</th>
            <th>합계</th>
          </tr>
          <tr class="par-row">
            <td colspan="2">Par</td>
            <td></td>
            {par_back_cells}
            <td class="par-cell">{par_back}</td>
            <td class="par-cell">{par_total}</td>
          </tr>
        </thead>
      </table>
    </div>

    <footer>골프존 네트워크 플레이 스코어카드 &nbsp;|&nbsp; 생성일: {html.escape(game.date)}</footer>
  </div>
</body>
</html>"""


# ──────────────────────────────────────────────
# CLI 진입점
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="골프존 네트워크 플레이 스코어카드 통합 도구"
    )
    parser.add_argument(
        "--input", "-i",
        help="게임 데이터 JSON 파일 경로 (미지정 시 샘플 데이터 사용)",
        default=None,
    )
    parser.add_argument(
        "--output", "-o",
        help="출력 HTML 파일 경로 (기본: scorecard.html)",
        default="scorecard.html",
    )
    args = parser.parse_args()

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            raw = json.load(f)
        game = parse_from_json(raw)
        print(f"[✓] JSON 파일 로드: {args.input}")
    else:
        game = parse_from_json(SAMPLE_DATA)
        print("[✓] 샘플 데이터 사용 (스크린샷 기반)")

    html_content = build_html(game)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[✓] 스코어카드 생성 완료: {args.output}")
    print(f"    게임: {game.title} | 코스: {game.course} | 날짜: {game.date}")
    print(f"    참가자: {game.total_players}명 | 완료: {game.finished_players}명")


if __name__ == "__main__":
    main()
