#!/usr/bin/env python3
"""잡문이(내가알려고만든잡다한상식들) 스레드(+인스타 릴스, 지금은 꺼둠) 자동 게시.

queue.json 의 항목을 publish_at(KST) 이 지나고, 유튜브 영상이 공개된 뒤에 올린다.
  - 스레드: 정답은 숨긴 호기심 후킹 글, 첫 댓글 = 유튜브 쇼츠 링크
  - 인스타: 예고편 릴스 (항목의 "ig": true 일 때만, 지금은 전부 false)
한 번 실행에 한 항목만 처리한다. 게시 기록은 state.json.

켜짐/꺼짐: jabmuni/enabled.txt 첫 줄이 "on" 일 때만 게시.
환경변수: JABMUNI_IG_TOKEN, JABMUNI_TH_TOKEN (없으면 그 플랫폼은 건너뜀), REPO
사용: python3 jabmuni/post.py --run | --preview
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
KST = dt.timezone(dt.timedelta(hours=9))
REPO = os.environ.get("REPO", "Kim-beomjun-0112/seoul-reels")
IG_TOKEN = os.environ.get("JABMUNI_IG_TOKEN", "").strip()
TH_TOKEN = os.environ.get("JABMUNI_TH_TOKEN", "").strip()
IG_API = "https://graph.instagram.com/v21.0"
TH_API = "https://graph.threads.net/v1.0"
CHANNEL = "https://www.youtube.com/@잡문이상식"


def jload(name, default):
    p = os.path.join(HERE, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def jsave(name, data):
    with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def call(base, method, path, token, **params):
    params["access_token"] = token
    data = urllib.parse.urlencode(params).encode()
    url = f"{base}/{path}"
    if method == "GET":
        url += "?" + data.decode()
        data = None
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        raise RuntimeError(f"{method} {path} → {e.code}: {body}")


def media_urls(path):
    ref = os.environ.get("GITHUB_SHA", "main")  # 커밋 고정 → jsDelivr 캐시 문제 없음
    return [f"https://cdn.jsdelivr.net/gh/{REPO}@{ref}/jabmuni/{path}",
            f"https://raw.githubusercontent.com/{REPO}/main/jabmuni/{path}"]


def yt_public(vid):
    u = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}")
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
            return r.status == 200
    except Exception:
        return False


def wait_ready(base, cid, token, field, ok, bad, limit=600):
    t0 = time.time()
    while time.time() - t0 < limit:
        st = call(base, "GET", cid, token, fields=field).get(field, "")
        if st in ok:
            return
        if st in bad:
            raise RuntimeError(f"컨테이너 처리 실패: {st}")
        time.sleep(10)
    raise RuntimeError("컨테이너 처리 시간 초과")


# ------------------------------------------------------------------ 인스타
def post_ig(item):
    last = None
    for vurl, curl in zip(media_urls(item["video"]), media_urls(item["cover"])):
        try:
            c = call(IG_API, "POST", "me/media", IG_TOKEN, media_type="REELS", video_url=vurl,
                     cover_url=curl, caption=item["ig_caption"], share_to_feed="true")
            wait_ready(IG_API, c["id"], IG_TOKEN, "status_code", {"FINISHED"}, {"ERROR", "EXPIRED"})
            p = call(IG_API, "POST", "me/media_publish", IG_TOKEN, creation_id=c["id"])
            return p["id"]
        except Exception as e:
            last = e
            print("인스타 시도 실패:", e)
    raise last


# ------------------------------------------------------------------ 스레드
def post_th(item):
    """본문 = 결말 없는 반말 후킹 글(텍스트), 첫 댓글 = 유튜브 링크."""
    link = f"https://youtube.com/shorts/{item['yt_id']}"
    c = call(TH_API, "POST", "me/threads", TH_TOKEN, media_type="TEXT", text=item["th_text"])
    time.sleep(5)
    pid = call(TH_API, "POST", "me/threads_publish", TH_TOKEN, creation_id=c["id"])["id"]
    # 첫 댓글: 유튜브 풀버전 링크 (링크 카드 → 실패 시 일반 글)
    reply = f"궁금하면 잡문이가 30초 만에 알려줄게 👉 {link}\n잡문이 채널: {CHANNEL}"
    if item.get("th_reply"):  # 소개글 등: 첫 댓글 직접 지정
        reply, link = item["th_reply"], item.get("th_link", CHANNEL)
    time.sleep(5)
    for extra in ({"link_attachment": link}, {}):
        try:
            r = call(TH_API, "POST", "me/threads", TH_TOKEN, media_type="TEXT", text=reply,
                     reply_to_id=pid, **extra)
            time.sleep(3)
            call(TH_API, "POST", "me/threads_publish", TH_TOKEN, creation_id=r["id"])
            break
        except Exception as e:
            print("댓글 실패:", e)
    return pid


# ------------------------------------------------------------------ 실행
def due_items(queue, state, now):
    for it in sorted(queue, key=lambda x: x["publish_at"]):
        s = state.get(it["ep"], {})
        need_ig = it.get("ig") is True and not s.get("ig")
        need_th = it.get("threads") is True and not s.get("th")
        if (need_ig or need_th) and dt.datetime.fromisoformat(it["publish_at"]) <= now:
            yield it, need_ig, need_th


def run(preview=False):
    queue = jload("queue.json", [])
    state = jload("state.json", {})
    now = dt.datetime.now(KST)
    if preview:
        for it in queue:
            print(f"── {it['ep']}  {it['publish_at']}  yt={it['yt_id']}  ig={it.get('ig')} th={it.get('threads')}  기록={state.get(it['ep'], {})}")
            print("[인스타]\n" + it["ig_caption"] + "\n[스레드]\n" + it["th_text"] + "\n")
        return
    if open(os.path.join(HERE, "enabled.txt")).read().strip().splitlines()[0].strip() != "on":
        print("꺼져 있음")
        return
    for name, base, tok in (("인스타", IG_API, IG_TOKEN), ("스레드", TH_API, TH_TOKEN)):
        if tok:
            try:
                print(name, "토큰 OK:", call(base, "GET", "me", tok, fields="username").get("username"))
            except Exception as e:
                print(name, "토큰 오류:", e)
    for it, need_ig, need_th in due_items(queue, state, now):
        if it.get("kind") != "intro" and not yt_public(it["yt_id"]):
            print(f"{it['ep']}: 유튜브 아직 비공개 → 대기")
            continue
        s = state.setdefault(it["ep"], {})
        if need_ig and IG_TOKEN:
            try:
                s["ig"] = post_ig(it)
                s["ig_at"] = now.isoformat(timespec="minutes")
                print(f"{it['ep']}: 인스타 게시 {s['ig']}")
            except Exception as e:
                print(f"{it['ep']}: 인스타 실패 {e}")
            jsave("state.json", state)
        if need_th and TH_TOKEN:
            try:
                s["th"] = post_th(it)
                s["th_at"] = now.isoformat(timespec="minutes")
                print(f"{it['ep']}: 스레드 게시 {s['th']}")
            except Exception as e:
                print(f"{it['ep']}: 스레드 실패 {e}")
            jsave("state.json", state)
        return True  # 한 번에 한 편만
    print("올릴 차례인 항목 없음")
    return False


def commit_state():
    import subprocess
    sh = lambda *c: subprocess.run(c, cwd=os.path.dirname(HERE), check=False)
    sh("git", "add", "jabmuni/state.json")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=os.path.dirname(HERE)).returncode:
        sh("git", "commit", "-q", "-m", "잡문이 게시 기록")
        sh("git", "pull", "--rebase", "-q")
        sh("git", "push", "-q")


def loop(minutes, gap=50, tick=10):
    """GitHub 예약 실행이 드문드문이라, 한 번 깨어나면 몇 시간 동안 10분마다 확인하며 올린다(게시 간격 최소 gap분)."""
    t0 = time.time(); last = 0
    while time.time() - t0 < minutes * 60:
        if time.time() - last >= gap * 60:
            try:
                if run():
                    last = time.time(); commit_state()
            except Exception as e:
                print("오류:", e)
        time.sleep(tick * 60)


if __name__ == "__main__":
    if "--loop" in sys.argv:
        loop(int(os.environ.get("LOOP_MIN", "320")))
    else:
        run(preview="--preview" in sys.argv)
