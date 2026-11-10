# seoul-reels
지금 서울에서는 — 인스타 릴스 자동 게시용 저장소.
- `reels/날짜/` : 영상·커버(공개 주소로 인스타가 가져감)
- `queue.json` : 게시 대기열(게시 시각 `publish_at`, 캡션, 영상 경로)
- `post_reel.py` + `.github/workflows/post.yml` : 시각이 된 영상을 인스타 API로 게시
