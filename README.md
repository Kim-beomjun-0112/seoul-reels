# seoul-reels
지금 서울에서는 — 인스타 릴스 자동 게시용 저장소.
- `reels/날짜/` : 영상·커버(공개 주소로 인스타가 가져감)
- `queue.json` : 게시 대기열(게시 시각 `publish_at`, 캡션, 영상 경로)
- `post_reel.py` + `.github/workflows/post.yml` : 시각이 된 영상을 인스타 API로 게시

## 규칙
- 영상·커버 모두 1080x1920(9:16), 정사각 픽셀. 아니면 게시를 보류하고 `queue.json`에 `skipped`로 남긴다.
- 커버는 영상마다 따로: 글씨는 크고 잘 보이게, 사진은 내용에 맞게. 피드 격자는 가운데 3:4로 잘리니 글씨는 위·아래 끝에 두지 않는다.
- `queue.json` 항목: `{id, video, cover, caption, publish_at(+09:00), posted:false}`
