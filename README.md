# 골프존 네트워크 플레이 스코어카드 통합 도구

골프존 앱에서 네트워크 플레이가 끝난 후 **모든 참가자의 홀별 점수**를 하나의 표(HTML)로 시각화합니다.

## 실행 방법

### 1. 의존성 설치

```bash
pip install requests beautifulsoup4
```

### 2. 샘플 데이터로 실행 (빠른 테스트)

```bash
python golfzon_scorecard.py
# → scorecard.html 생성됨
```

브라우저에서 `scorecard.html`을 열면 전체 스코어카드를 확인할 수 있습니다.

### 3. 내 게임 데이터로 실행

```bash
python golfzon_scorecard.py --input my_game.json --output my_scorecard.html
```

## JSON 데이터 형식

골프존 앱에서 게임이 끝나면 아래 형식에 맞춰 데이터를 입력하세요.

```json
{
  "game_id": "2026032900001",
  "title": "게임명 (예: ㅂㅂ11)",
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
      "scores": [0,0,-1,0,-1,0,-1,0,0, -1,-1,0,0,-1,-1,0,1,-1]
    }
  ]
}
```

### scores 값 의미

| 값   | 의미         | 골프존 표시 |
|------|------------|-----------|
| -3   | 알바트로스    | 이중 원 (빨강) |
| -2   | 이글         | 이중 원 |
| -1   | 버디         | 원 (빨강) |
|  0   | 파           | 숫자만 |
| +1   | 보기         | 사각 (파랑) |
| +2   | 더블보기     | 이중 사각 |
| +3   | 트리플보기   | 이중 사각 |

## 출력 예시

생성된 `scorecard.html`을 브라우저로 열면:

- 전반(1~9홀) / 후반(10~18홀) 구분 표
- 모든 참가자 홀별 타수 및 파 대비 상대 점수
- 버디(원), 보기(사각형) 등 골프존 스타일 색상 표시
- 전반/후반 소계 및 총합

## 파일 구조

```
golf-scorecard/
├── golfzon_scorecard.py   # 메인 스크립트
├── sample_game.json       # 샘플 데이터 (스크린샷 기반)
└── README.md
```
