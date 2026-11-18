#!/usr/bin/env python3
"""경제용어사전 스레드 자동 게시.

흐름
  --build : 유튜브 영상 목록(seed videos.json + 채널 RSS)으로 중계 페이지(_site/go/ID.html)를 만든다.
            중계 페이지는 썸네일만 미리보기 카드로 보이게 하고, 열면 곧바로 유튜브로 넘긴다.
            새 페이지가 생겼으면 GITHUB_OUTPUT 에 changed=true 를 쓴다.
  --post  : 하루 3번(08:00 / 12:30 / 20:00 KST) 시각이 지났고 아직 못 올렸으면, 다음 공개 영상 1개를 올린다.
            본문 = 후킹 한 줄 + 비트코인 차트 상황, 첫 댓글 = 중계 페이지 링크 카드.
  --preview N : 게시하지 않고 다음 N개 글을 출력한다.

켜짐/꺼짐은 저장소 파일 enabled.txt 의 첫 글자열이 "on" 인지로 정한다(아니면 아무것도 게시하지 않음).
환경변수: SEOUL_TH_TOKEN(스레드 토큰), REPO(owner/name), SITE_BASE(선택, 중계 페이지 주소 머리)
"""
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from chart_facts import Chart, fetch_candles, fetch_ticker, fetch_fng

CHANNEL_ID = "UC-jeksSCZVCNxZdMIVcIh_Q"
KST = dt.timezone(dt.timedelta(hours=9))
SLOTS = [(8, 0), (12, 30), (20, 0)]
TH_API = "https://graph.threads.net/v1.0"
TH_TOKEN = os.environ.get("SEOUL_TH_TOKEN", "")
REPO = os.environ.get("REPO", "Kim-beomjun-0112/seoul-reels")
OWNER, NAME = REPO.split("/")
SITE_BASE = os.environ.get("SITE_BASE", f"https://{OWNER.lower()}.github.io/{NAME}")
HERE = os.path.dirname(os.path.abspath(__file__))


def jload(name, default):
    p = os.path.join(HERE, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def jsave(name, data):
    json.dump(data, open(os.path.join(HERE, name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def http(url, timeout=30, method="GET", data=None):
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


# ---------------------------------------------------------------- 영상 목록
def rss_videos():
    try:
        _, b = http(f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}")
    except Exception as e:
        print("RSS 실패:", e)
        return []
    ns = {"a": "http://www.w3.org/2005/Atom", "y": "http://www.youtube.com/xml/schemas/2015"}
    out = []
    for e in ET.fromstring(b).findall("a:entry", ns):
        out.append({"id": e.find("y:videoId", ns).text,
                    "title": e.find("a:title", ns).text,
                    "published": e.find("a:published", ns).text})
    return out


def all_videos():
    """seed + RSS 합치기(공개 시각 오름차순). 시작 이전 영상(2025년 이전 옛 영상)은 seed 에 없으니 RSS 에서도 제외."""
    seed = jload("videos.json", [])
    have = {v["id"] for v in seed}
    cutoff = seed[0]["published"] if seed else "2026-11-01"
    for v in rss_videos():
        if v["id"] not in have and v["published"] >= cutoff:
            seed.append(v)
    seed.sort(key=lambda v: v["published"])
    return seed


def is_public(vid):
    try:
        s, _ = http(f"https://www.youtube.com/oembed?url=https://www.youtube.com/shorts/{vid}&format=json", 20)
        return s == 200
    except Exception:
        return False


def video_title(vid, fallback=""):
    try:
        _, b = http(f"https://www.youtube.com/oembed?url=https://www.youtube.com/shorts/{vid}&format=json", 20)
        return json.loads(b)["title"]
    except Exception:
        return fallback


# ---------------------------------------------------------------- 중계 페이지
PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>{title}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta property="og:type" content="video.other">
<meta property="og:site_name" content="경제용어사전">
<meta property="og:title" content="{title}">
<meta property="og:description" content="경제용어사전 · 비트코인 차트로 배우는 경제용어">
<meta property="og:image" content="https://i.ytimg.com/vi/{vid}/maxresdefault.jpg">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary_large_image">
<meta http-equiv="refresh" content="0;url={yt}">
</head><body><script>location.replace("{yt}");</script>
<p><a href="{yt}">유튜브에서 보기</a></p></body></html>
"""


def clean_title(t):
    return re.sub(r"\s*\|?\s*경제용어사전.*$", "", t.replace("#shorts", "")).strip(" |")


def page_url(vid):
    return f"{SITE_BASE}/go/{vid}.html"


def build():
    vids = all_videos()
    os.makedirs(os.path.join(HERE, "_site", "go"), exist_ok=True)
    state = jload("state.json", {"posted": {}, "pages": []})
    known = set(state.get("pages", []))
    for v in vids:
        yt = f"https://www.youtube.com/shorts/{v['id']}"
        t = clean_title(v.get("title") or "경제용어사전")
        open(os.path.join(HERE, "_site", "go", f"{v['id']}.html"), "w", encoding="utf-8").write(
            PAGE.format(title=html.escape(t), vid=v["id"], url=page_url(v["id"]), yt=yt))
    open(os.path.join(HERE, "_site", "index.html"), "w", encoding="utf-8").write(
        "<!doctype html><meta charset=utf-8><title>경제용어사전</title><a href='https://www.youtube.com/@economy_dictionary112'>경제용어사전</a>")
    ids = sorted(v["id"] for v in vids)
    changed = set(ids) != known
    json.dump(ids, open(os.path.join(HERE, "_site", "ids.json"), "w"))
    print("중계 페이지", len(ids), "개 / 변경:", changed)
    if os.environ.get("GITHUB_OUTPUT"):
        open(os.environ["GITHUB_OUTPUT"], "a").write(
            f"changed={'true' if changed and enabled() else 'false'}\n")


def mark_pages():
    """중계 페이지 배포가 성공한 뒤에만 '배포된 목록'을 기록한다."""
    state = jload("state.json", {"posted": {}, "pages": []})
    state["pages"] = json.load(open(os.path.join(HERE, "_site", "ids.json")))
    jsave("state.json", state)


# ---------------------------------------------------------------- 글 만들기
# (키워드 패턴, 지표 키, 용어 이름) — 위에서부터 먼저 맞는 것을 쓴다
RULES = [
    (r"RSI", "rsi", "RSI"),
    (r"골든크로스", "gc", "골든크로스"),
    (r"데드크로스", "gc", "데드크로스"),
    (r"볼린저", "bb", "볼린저밴드"),
    (r"20일선", "ma", "20일선"),
    (r"MACD", "macd", "MACD"),
    (r"스토캐스틱", "stoch", "스토캐스틱"),
    (r"거래량", "vol", "거래량"),
    (r"이동평균선", "ma", "이동평균선"),
    (r"추세선", "trend", "추세선"),
    (r"눌림목", "trend", "눌림목"),
    (r"박스권", "box", "박스권"),
    (r"지지선|저항선", "sr", "지지선·저항선"),
    (r"변동성", "volat", "변동성"),
    (r"캔들", "candle", "캔들"),
    (r"갭", "gap", "갭"),
    (r"공포탐욕", "fear", "공포탐욕지수"),
    (r"52주", "high52", "52주 신고가"),
    (r"시가총액", "cap", "시가총액"),
    (r"분할매수", "dca", "분할매수"),
    (r"손절", "stop", "손절"),
]
CORP = r"PER|PBR|ROE|EPS|부채비율|영업이익률|배당수익률|유상증자|공매도|ETF|기준금리"

HOOKS = {
    "gc": ["{t}, 비트코인은 지금 어떨까? 🤔", "{t} 뜬 날의 승률이 궁금하다면 👀", "{t} 상황, 지금 바로 체크해봐요"],
    "rsi": ["RSI 70 넘으면 정말 팔아야 할까? 🤔", "RSI 숫자, 지금은 몇일까요?"],
    "bb": ["{t} 윗선을 뚫으면 과열일까? 👀", "{t}, 비트코인 위치는?"],
    "ma": ["{t}, 비트코인은 위일까 아래일까? 🤔", "{t} 하나로 추세 체크하는 법 📊"],
    "macd": ["{t} 신호, 지금은 어떨까? 📈", "{t} 읽는 법, 실제 차트로 확인!"],
    "stoch": ["{t}, 지금 과열일까 침체일까? 🌡️", "{t} 수치, 지금은 몇일까요?"],
    "vol": ["{t}이 터지면 진짜 오를까? 👀", "{t}, 어제는 평소의 몇 배였을까요?"],
    "trend": ["{t}, 지금 비트코인은 어디쯤일까? 🤔", "{t}으로 보는 비트코인 차트 📊"],
    "box": ["{t}에 갇혔을까, 뚫었을까? 👀", "{t}, 지금 비트코인 위치는?"],
    "sr": ["{t}, 가격은 어디쯤일까? 🤔", "{t} 근처인지 체크해봐요 📍"],
    "volat": ["{t}, 요즘 비트코인은 얼마나 출렁일까? 🎢", "{t} 숫자로 보는 비트코인 차트"],
    "candle": ["{t} 하나만 읽어도 보이는 것들 🕯️", "어제 비트코인 {t}은 어땠을까?"],
    "gap": ["{t}, 코인에도 있을까? 🤔", "{t} 개념, 비트코인에 대면?"],
    "fear": ["{t}, 시장 분위기는? 🌡️", "{t} 수치로 보는 지금 분위기"],
    "high52": ["{t} 근처에 있을까? 🏔️", "{t} 대비 비트코인은?"],
    "cap": ["{t}, 비트코인 크기는 어느 정도일까? 🤔", "{t}으로 보는 비트코인"],
    "dca": ["{t}, 지난 8주 했다면 어땠을까? 🧮", "{t}의 결과를 숫자로 확인해요"],
    "stop": ["{t}, 지금 고점에서 얼마나 내려왔을까? 🤔", "{t} 기준을 정할 때 보는 숫자 📉"],
    "snap": ["경제용어 한 입: {t} 📚", "{t}, 알아두면 투자 공부에 도움돼요 📚"],
}


def classify(title):
    t = clean_title(title)
    for pat, key, name in RULES:
        if re.search(pat, t):
            return key, name, t
    m = re.search(CORP, t)
    return "snap", (m.group(0) if m else re.sub(r"\s*뜻.*$", "", t)), t


def is_quiz(t):
    return ("해보니" in t) or ("?" in t) or ("%" in t)


def pick(lst, vid):
    return lst[int(hashlib.md5(vid.encode()).hexdigest(), 16) % len(lst)]


def make_post(v, ch, tick, fng):
    title = v.get("title") or video_title(v["id"])
    key, name, t = classify(title)
    if is_quiz(t) and key != "snap":
        if "?" in t:
            hook = t[: t.index("?") + 1] + " 🤔"
        else:
            hook = re.sub(r"\s*비트코인.*$", "", t).strip()
            hook = hook if len(hook) > 6 else t
    else:
        hook = pick(HOOKS[key], v["id"]).format(t=name)
    lines = ch.facts(key, fng)
    price = f"{tick['price']/1e4:,.0f}만" if tick else f"{ch.price/1e4:,.0f}만"
    chg = f" ({tick['chg24']:+.1f}%)" if tick else ""
    head = f"📊 비트코인 차트 상황 ({_kst_now().month}/{_kst_now().day} 기준)\n• 현재가 {price}원{chg}"
    body = "\n".join("• " + x for x in lines)
    text = f"{hook}\n\n{head}\n{body}\n\n※ 일봉 마감 기준 · 학습용 정보이며 투자 권유가 아닙니다.\n👇 영상은 첫 댓글에"
    return text[:490], t


def _kst_now():
    import datetime as _d
    return _d.datetime.now(_d.timezone(_d.timedelta(hours=9)))


# ---------------------------------------------------------------- 스레드 API
def th(method, path, **params):
    params["access_token"] = TH_TOKEN
    data = urllib.parse.urlencode(params).encode()
    url = f"{TH_API}/{path}"
    req = urllib.request.Request(url if method == "POST" else url + "?" + data.decode(),
                                 data=data if method == "POST" else None, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"threads {method} {path} -> {e.code} {e.read().decode()[:400]}")


def th_publish(text, **extra):
    me = th("GET", "me", fields="id")["id"]
    c = th("POST", f"{me}/threads", media_type="TEXT", text=text, **extra)
    for _ in range(12):
        st = th("GET", c["id"], fields="status")
        if st.get("status") in ("FINISHED", None):
            break
        if st.get("status") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"컨테이너 실패: {st}")
        time.sleep(5)
    return th("POST", f"{me}/threads_publish", creation_id=c["id"])["id"]


def page_live(vid):
    try:
        s, _ = http(page_url(vid), 20)
        return s == 200
    except Exception:
        return False


def enabled():
    p = os.path.join(HERE, "enabled.txt")
    return os.path.exists(p) and open(p).read().strip().lower().startswith("on")


def now_kst():
    return dt.datetime.now(KST)


def slots_passed(n):
    return sum(1 for h, m in SLOTS if (n.hour, n.minute) >= (h, m))


def next_candidates(state, limit=1, need_live=True):
    out = []
    for v in all_videos():
        if v["id"] in state["posted"] or state.get("fail", {}).get(v["id"], 0) >= 3:
            continue
        if not is_public(v["id"]):
            continue
        if need_live and not page_live(v["id"]):
            continue
        out.append(v)
        if len(out) >= limit:
            break
    return out


def post():
    state = jload("state.json", {"posted": {}, "pages": []})
    if not enabled():
        print("enabled.txt 가 on 이 아님 → 게시 안 함")
        return
    n = now_kst()
    today = n.strftime("%Y-%m-%d")
    done_today = sum(1 for p in state["posted"].values() if p.get("at", "").startswith(today))
    # 이전에 본문만 올라가고 댓글이 실패한 건 먼저 마무리
    for vid, p in state["posted"].items():
        if p.get("thread_id") and not p.get("done"):
            try:
                finish_comment(vid, p)
            except Exception as e:
                p["error"] = str(e)[:200]
                print("댓글 재시도 실패:", e)
            jsave("state.json", state)
            return
    if slots_passed(n) <= done_today:
        print(f"아직 시각 아님 (오늘 {done_today}개 / 지난 슬롯 {slots_passed(n)})")
        return
    cand = next_candidates(state, 1)
    if not cand:
        print("올릴 공개 영상 없음(또는 중계 페이지 준비 중)")
        return
    v = cand[0]
    ch, tick, fng = load_market()
    text, t = make_post(v, ch, tick, fng)
    print("게시:", v["id"], "\n" + text)
    try:
        tid = th_publish(text)
    except Exception as e:
        state.setdefault("fail", {})[v["id"]] = state.get("fail", {}).get(v["id"], 0) + 1
        jsave("state.json", state)
        print("본문 실패:", e)
        sys.exit(1)
    p = {"at": n.isoformat(), "thread_id": tid, "title": t, "done": False}
    state["posted"][v["id"]] = p
    jsave("state.json", state)
    try:
        finish_comment(v["id"], p)
    except Exception as e:
        p["error"] = str(e)[:200]
        print("첫 댓글 실패(다음 실행에서 재시도):", e)
    jsave("state.json", state)


def finish_comment(vid, p):
    link = page_url(vid)
    text = f"영상으로 보기 👉 {link}"
    try:
        th_publish(text, reply_to_id=p["thread_id"], link_attachment=link)
        p["card"] = True
    except Exception as e:
        print("링크 카드 첨부 실패 → 글자 링크로:", str(e)[:150])
        th_publish(text, reply_to_id=p["thread_id"])
        p["card"] = False
    p["done"] = True
    p.pop("error", None)


def load_market():
    candles = fetch_candles()
    return Chart(candles), fetch_ticker(), fetch_fng()


def preview(n):
    state = jload("state.json", {"posted": {}, "pages": []})
    ch, tick, fng = load_market()
    cands = next_candidates(state, n, need_live=False)
    for v in cands:
        text, t = make_post(v, ch, tick, fng)
        print("=" * 50, v["id"], v.get("published", "")[:10])
        print(text)
        print("-- 첫 댓글: 영상으로 보기 👉", page_url(v["id"]), "(링크카드: 썸네일)")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--build"]:
        build()
    elif a[:1] == ["--mark"]:
        mark_pages()
    elif a[:1] == ["--post"]:
        post()
    elif a[:1] == ["--preview"]:
        preview(int(a[1]) if len(a) > 1 else 3)
    else:
        print(__doc__)
