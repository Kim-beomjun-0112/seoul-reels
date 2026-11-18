"""내 스레드 글에 달린 댓글에 상황에 맞는 답글을 자동으로 단다.

- replies_enabled.txt 가 "on" 으로 시작할 때만 동작 (기본 off)
- 내 글(최근 10개)의 댓글만 대상. 남의 글에는 아무것도 하지 않는다.
- 규칙 기반 템플릿(질문/감사/매매 문의). 어디에도 해당하지 않으면 답하지 않는다.
- 한 댓글에 한 번만, 하루 상한, 한 번 실행에 상한, 새벽(00~07시)에는 쉰다.
- 권한 오류 등은 로그만 남기고 정상 종료 (게시 워크플로를 막지 않는다).
사용: python3 replies_bot.py [--run | --test]
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys

import threads_post as tp

KST = tp.KST
MIN_AGE_MIN = 10          # 댓글이 달리고 최소 10분 뒤에 답한다 (사람처럼)
MAX_AGE_H = 48            # 48시간 지난 댓글은 건너뛴다
PER_RUN = 2
PER_DAY = 12
STATE = "replies_state.json"

URL_RE = re.compile(r"https?://|www\.|\.com|\.kr|@\w+\.", re.I)
BUYSELL = re.compile(r"사야|살까|사도|팔아야|팔까|팔아도|매수|매도|지금\s*들어|물타|존버|전망|오를까|떨어질까|올라가|내려가|폭락|폭등|언제\s*(사|팔)")
THANKS = re.compile(r"감사|고마워|고맙|유익|도움|좋아요|좋은\s*정보|잘\s*봤|잘\s*보고|구독|응원|화이팅|파이팅")
ASK = re.compile(r"뜻|의미|설명|알려|궁금|\?|？|어떻게|뭐야|뭔가요|무슨")
SPAM = re.compile(r"수익\s*보장|리딩|텔레그램|카톡|오픈채팅|무료\s*상담|급등\s*종목|추천\s*코인|DM|디엠")

T = {
    "buysell": [
        "사고팔지 말지는 내가 답해줄 수 없어 🙏 대신 차트 숫자가 무슨 뜻인지는 같이 볼 수 있어! 영상 첫 댓글 링크 확인해줘 📊",
        "매수·매도 판단은 해줄 수 없어서 미안해 🙏 숫자가 어떤 뜻인지 배우는 곳이라고 생각해줘! 첫 댓글 영상에서 설명해뒀어 📊",
    ],
    "thanks": [
        "고마워! 앞으로도 쉽게 풀어서 올릴게 😊",
        "봐줘서 고마워 🙌 다음 글도 기대해줘!",
    ],
    "ask": [
        "좋은 질문이야! 첫 댓글 영상에서 쉽게 풀어뒀으니 먼저 봐줘 👀 더 궁금한 건 댓글로 또 남겨줘 ✍️",
        "궁금한 용어를 남겨줘서 고마워 ✍️ 영상에 설명해뒀고, 다음 주제 정할 때 참고할게!",
    ],
}


def now():
    return dt.datetime.now(KST)


def enabled():
    p = os.path.join(tp.HERE, "replies_enabled.txt")
    return os.path.exists(p) and open(p, encoding="utf-8").read().strip().lower().startswith("on")


def classify(text):
    t = (text or "").strip()
    if len(t) < 2 or URL_RE.search(t) or SPAM.search(t):
        return None
    if not re.search(r"[가-힣A-Za-z]", t):      # 이모지·숫자만 → 답하지 않음
        return None
    if BUYSELL.search(t):
        return "buysell"
    if THANKS.search(t):
        return "thanks"
    if ASK.search(t):
        return "ask"
    return None


def make_reply(cid, kind):
    lst = T[kind]
    return lst[int(hashlib.md5(cid.encode()).hexdigest(), 16) % len(lst)]


def parse_ts(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def run():
    if not enabled():
        print("답글 봇: replies_enabled.txt 가 off")
        return
    if not tp.TH_TOKEN:
        print("토큰 없음")
        return
    if now().hour < 7:
        print("새벽 시간대라 쉼")
        return
    st = tp.jload(STATE, {"replied": [], "day": "", "count": 0})
    today = now().strftime("%Y-%m-%d")
    if st.get("day") != today:
        st["day"], st["count"] = today, 0
    try:
        me = tp.th("GET", "me", fields="id,username")
        mine = tp.th("GET", f"{me['id']}/threads", fields="id,timestamp", limit=10).get("data", [])
    except RuntimeError as e:
        print("스레드 조회 실패:", e)
        return
    done = 0
    for post in mine:
        if done >= PER_RUN or st["count"] >= PER_DAY:
            break
        try:
            rep = tp.th("GET", f"{post['id']}/replies", fields="id,text,username,timestamp", reverse="false").get("data", [])
        except RuntimeError as e:
            print("댓글 조회 실패(권한 확인 필요):", str(e)[:200])
            break
        for c in rep:
            if done >= PER_RUN or st["count"] >= PER_DAY:
                break
            if c["id"] in st["replied"] or c.get("username") == me.get("username"):
                continue
            age = now() - parse_ts(c["timestamp"]).astimezone(KST)
            if age < dt.timedelta(minutes=MIN_AGE_MIN) or age > dt.timedelta(hours=MAX_AGE_H):
                continue
            kind = classify(c.get("text"))
            st["replied"].append(c["id"])        # 해당 없음도 기록해 다시 보지 않는다
            if not kind:
                continue
            text = make_reply(c["id"], kind)
            try:
                tp.th_publish(text, reply_to_id=c["id"])
            except RuntimeError as e:
                print("답글 실패:", str(e)[:200])
                continue
            st["count"] += 1
            done += 1
            print(f"답글 [{kind}] {c.get('username')}: {c.get('text','')[:30]!r}")
    st["replied"] = st["replied"][-500:]
    tp.jsave(STATE, st)
    print(f"답글 {done}개 (오늘 {st['count']}/{PER_DAY})")


def test():
    samples = ["지금 비트코인 사야 할까요?", "RSI가 뭔가요?", "유익한 정보 감사합니다", "ㅋㅋㅋ", "👍👍",
               "텔레그램 오세요 수익 보장", "볼린저밴드 설명 좀 해주세요", "https://spam.com 확인", "존버가 답이죠"]
    for s in samples:
        k = classify(s)
        print(f"{s!r:40} -> {k}", "|", make_reply('x' + s, k) if k else "(답하지 않음)")


if __name__ == "__main__":
    run() if "--run" in sys.argv else test()
