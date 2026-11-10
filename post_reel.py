#!/usr/bin/env python3
"""queue.json 에서 게시 시각이 지난 릴스를 인스타 API(Instagram Login)로 게시한다.
환경변수: SEOUL_IG_TOKEN, SEOUL_IG_USER_ID, REPO (owner/name), DRY(1이면 게시 안 함)
queue.json 항목: {id, video, caption, publish_at(ISO, +09:00), cover(선택), posted(false), media_id}
"""
import json, os, subprocess, sys, time, urllib.parse, urllib.request, datetime as dt

API = "https://graph.instagram.com/v21.0"
TOKEN = os.environ.get("SEOUL_IG_TOKEN", "")
UID = os.environ.get("SEOUL_IG_USER_ID", "")
REPO = os.environ.get("REPO", "")
BRANCH = os.environ.get("BRANCH", "main")
DRY = os.environ.get("DRY") == "1"
MAX_PER_RUN = 1  # 한 번 실행에 1개만(시각 간격 보장)


def call(method, path, **params):
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    req = urllib.request.Request(url if method == "POST" else url + "?" + data.decode(),
                                 data=data if method == "POST" else None, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} -> {e.code} {e.read().decode()[:400]}")


def raw(path):
    return f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{urllib.parse.quote(path)}"


def ratio_ok(path, label):
    """영상·커버가 9:16(세로, 정사각 픽셀)인지 확인. ffprobe 가 없으면 건너뛴다."""
    if not os.path.exists(path):
        print(f"{label} 파일 없음:", path); return False
    try:
        out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,sample_aspect_ratio", "-of", "json", path])
    except Exception as e:
        print("ffprobe 없음/실패 → 비율 검사 건너뜀:", e); return True
    s = json.loads(out)["streams"][0]
    w, h = int(s["width"]), int(s["height"])
    sar = s.get("sample_aspect_ratio", "1:1")
    ok = abs(w / h - 9 / 16) < 0.01 and sar in ("1:1", "0:1", "N/A")
    print(f"{label} 비율 {w}x{h} SAR {sar} →", "OK" if ok else "9:16 아님")
    return ok


def check():
    me = call("GET", "me", fields="user_id,username,account_type")
    print("토큰 확인:", me.get("username"), me.get("account_type"), "id 일치:", str(me.get("user_id")) == UID or str(me.get("id")) == UID)


def main():
    if DRY and TOKEN:
        check()
    q = json.load(open("queue.json", encoding="utf-8"))
    now = dt.datetime.now(dt.timezone.utc)
    due = [x for x in q if not x.get("posted") and not x.get("skipped")
           and dt.datetime.fromisoformat(x["publish_at"]) <= now]
    due.sort(key=lambda x: x["publish_at"])
    # 너무 오래 지난 건(6시간 초과) 건너뛴다 — 시간대가 지난 소식 방지
    fresh = [x for x in due if (now - dt.datetime.fromisoformat(x["publish_at"])).total_seconds() < 6 * 3600]
    for x in due:
        if x not in fresh and not x.get("skipped"):
            x["skipped"] = "late"
            print("늦어서 건너뜀:", x["id"])
    done = 0
    for x in fresh[:MAX_PER_RUN]:
        print("게시 대상:", x["id"], x["publish_at"])
        bad = not ratio_ok(x["video"], "영상") or (x.get("cover") and not ratio_ok(x["cover"], "커버"))
        if not x.get("cover"):
            print("커버 없음 → 게시 보류"); bad = True
        if bad:
            x["skipped"] = "bad_media"
            print("영상/커버 문제로 게시 보류:", x["id"]); continue
        if DRY or not TOKEN or not UID:
            print("DRY/토큰 없음 → 게시하지 않음")
            continue
        params = dict(media_type="REELS", video_url=raw(x["video"]),
                      caption=x["caption"], share_to_feed="true")
        if x.get("cover"):
            params["cover_url"] = raw(x["cover"])
        c = call("POST", f"{UID}/media", **params)
        cid = c["id"]
        for _ in range(40):  # 최대 ~6분 대기
            st = call("GET", cid, fields="status_code,status")
            print("상태:", st.get("status_code"))
            if st.get("status_code") == "FINISHED":
                break
            if st.get("status_code") in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"컨테이너 실패: {st}")
            time.sleep(10)
        else:
            raise RuntimeError("처리 시간 초과")
        p = call("POST", f"{UID}/media_publish", creation_id=cid)
        x["posted"] = True
        x["media_id"] = p["id"]
        x["posted_at"] = now.isoformat()
        print("게시 완료:", p["id"])
        done += 1
    json.dump(q, open("queue.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return done


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("실패:", e)
        sys.exit(1)
