# seoul-reels
지금 서울에서는 — 인스타 릴스 자동 게시용 저장소.
- `reels/날짜/` : 영상·커버(공개 주소로 인스타가 가져감)
- `queue.json` : 게시 대기열(게시 시각 `publish_at`, 캡션, 영상 경로)
- `post_reel.py` + `.github/workflows/post.yml` : 시각이 된 영상을 인스타 API로 게시

## 규칙
- 영상·커버 모두 1080x1920(9:16), 정사각 픽셀. 아니면 게시를 보류하고 `queue.json`에 `skipped`로 남긴다.
- 커버는 영상마다 따로: 글씨는 크고 잘 보이게, 사진은 내용에 맞게. 피드 격자는 가운데 3:4로 잘리니 글씨는 위·아래 끝에 두지 않는다.
- `queue.json` 항목: `{id, video, cover, caption, publish_at(+09:00), posted:false}`

## 스레드
- 릴스가 게시되면 같은 실행에서 스레드 본문(`threads`)을 올리고, 첫 댓글에 인스타 릴스 링크를 단다.
- `queue.json` 항목에 `threads`(후킹 본문, 490자 이내, 링크 없음)를 넣는다. 시크릿 `SEOUL_TH_TOKEN` 이 없으면 스레드는 건너뛴다.
- 스레드가 실패해도 릴스는 유지되고, 게시 후 6시간 안에는 다음 실행에서 다시 시도한다(`threads_error` 기록).
