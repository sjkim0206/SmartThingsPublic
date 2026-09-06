# 내 개인 스크립트 저장소

## 프로젝트
- golf-scorecard/  : 골프존 네트워크 플레이 스코어카드
- manwha-fetch/    : 만화 다운로드 스크립트

## 개발 환경

Python 3 기반 스크립트 모음입니다. (Python 3.12 에서 검증)

### 의존성 설치

```bash
# manwha-fetch 실행에 필요한 패키지 설치
pip3 install --user -r manwha-fetch/requirements.txt
```

`golf-scorecard` 의 스코어카드 생성 도구(`golfzon_scorecard.py`)는 표준 라이브러리만
사용하므로 별도 설치가 필요 없습니다.

Cloud Agent 환경은 `.cursor/environment.json` 의 `install` 단계에서 위 의존성을
자동으로 설치합니다.

### 빠른 실행 예시

```bash
# 골프 스코어카드 HTML 생성 (샘플 데이터 사용)
cd golf-scorecard && python3 golfzon_scorecard.py --no-pdf
```

> 참고: `manwha-fetch` 는 안드로이드 Termux 전용 스크립트로, `/sdcard` 경로와
> Tasker/카카오톡 연동에 의존합니다. 자세한 내용은 `manwha-fetch/README.md` 참고.
