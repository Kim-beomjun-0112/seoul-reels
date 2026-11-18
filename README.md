# 경제용어사전 스레드 자동 게시
유튜브 채널 경제용어사전(@economy_dictionary112) 영상을 스레드에 홍보하는 자동화.

- 하루 3번(08:00 / 12:30 / 20:00 KST) 공개된 영상 1개씩, 오래된 영상부터 순서대로.
- 본문: 후킹 한 줄 + 그날 업비트 BTC/KRW 일봉 마감 기준 차트 상황(수치 서술만). 첫 댓글: 중계 페이지 링크 카드(썸네일만 보이고 누르면 유튜브로 이동).
- 영상 목록: `videos.json`(시작 시점 목록) + 채널 RSS(새 영상 자동 추가).
- 켜기/끄기: `enabled.txt` 에 `on` / `off`.
- 중계 페이지: GitHub Pages(소스: GitHub Actions)로 `go/영상ID.html` 배포.
- 시크릿: `SEOUL_TH_TOKEN`(스레드), 토큰 연장용 `GH_PAT`.
- 확인용: `python3 threads_post.py --preview 5`
