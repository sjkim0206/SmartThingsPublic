# manwha-fetch — 신문 만평 다운로드/전송 스크립트

네이버 블로그의 "오늘의 신문 만평" 게시글에서 이미지를 내려받아 정리한 뒤,
Tasker를 통해 카카오톡 방으로 전송하는 자동화 스크립트입니다.

## 실행 환경

이 스크립트는 **안드로이드 Termux 환경 전용**으로 작성되어 있습니다.

- 저장 경로가 `/sdcard/Pictures/naver_manhwa` 로 하드코딩되어 있습니다.
- 파일 공유/전송에 `termux-share`, `termux-media-scan`, Tasker 태스크(`카톡만평전송`)를 사용합니다.
- 실제 다운로드에는 네이버 블로그로의 네트워크 접근이 필요합니다.

따라서 클라우드/데스크톱 Linux 에서는 코드 편집·구문 검사·순수 함수 단위 검증까지만 가능하며,
end-to-end 실행(다운로드→전송)은 안드로이드 단말에서 수행해야 합니다.

## 의존성 설치

```bash
pip3 install --user -r requirements.txt
```

설치되는 패키지:

- `requests` — HTTP 요청
- `beautifulsoup4` — HTML 파싱 (내장 `html.parser` 사용)
- `holidays` — 한국 공휴일 판별 (공휴일/일요일에는 실행하지 않음)
- `Pillow` — 이미지 분석(사진성 이미지 필터링)

## 실행

```bash
python3 fetch_manwha_fixed.py
```

일요일 또는 한국 공휴일에는 아무 작업도 하지 않고 종료합니다.
