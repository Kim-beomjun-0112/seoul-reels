"""업비트 비트코인(KRW-BTC) 일봉으로 '오늘 차트 상황' 문장을 만든다. 모두 사실(수치) 서술만 한다."""
import datetime as dt
import json
import urllib.request

KST = dt.timezone(dt.timedelta(hours=9))


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fetch_candles(total=400):
    """마감된 일봉만, 오래된 것부터."""
    rows, to = [], ""
    while len(rows) < total:
        url = "https://api.upbit.com/v1/candles/days?market=KRW-BTC&count=200" + (f"&to={to}" if to else "")
        part = _get(url)
        if not part:
            break
        rows += part
        to = part[-1]["candle_date_time_utc"] + "Z"
        if len(part) < 200:
            break
    rows.sort(key=lambda r: r["candle_date_time_utc"])
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for r in rows:
        start = dt.datetime.fromisoformat(r["candle_date_time_utc"]).replace(tzinfo=dt.timezone.utc)
        if start + dt.timedelta(days=1) <= now:  # 마감된 것만
            out.append(dict(d=start.astimezone(KST).strftime("%Y-%m-%d"), o=r["opening_price"], h=r["high_price"],
                            l=r["low_price"], c=r["trade_price"], v=r["candle_acc_trade_volume"]))
    return out


def fetch_ticker():
    try:
        t = _get("https://api.upbit.com/v1/ticker?markets=KRW-BTC")[0]
        return {"price": t["trade_price"], "chg24": t["signed_change_rate"] * 100}
    except Exception:
        return None


def fetch_fng():
    try:
        d = _get("https://api.alternative.me/fng/?limit=1")["data"][0]
        return {"v": int(d["value"]), "cls": d["value_classification"]}
    except Exception:
        return None


def man(x):
    return f"{x/1e4:,.0f}만"


def pct(a, b):
    return (a / b - 1) * 100


def sma(xs, n, end=None):
    end = len(xs) if end is None else end
    return sum(xs[end - n:end]) / n


class Chart:
    def __init__(self, candles):
        self.k = candles
        self.c = [x["c"] for x in candles]
        self.price = self.c[-1]
        self.date = candles[-1]["d"]

    # --- 지표 계산
    def rsi(self, n=14):
        c = self.c
        gains = [max(c[i] - c[i - 1], 0) for i in range(1, len(c))]
        losses = [max(c[i - 1] - c[i], 0) for i in range(1, len(c))]
        ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
        for i in range(n, len(gains)):
            ag = (ag * (n - 1) + gains[i]) / n
            al = (al * (n - 1) + losses[i]) / n
        return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)

    def ema(self, xs, n):
        a = 2 / (n + 1)
        e = xs[0]
        out = [e]
        for x in xs[1:]:
            e = a * x + (1 - a) * e
            out.append(e)
        return out

    def macd(self):
        e12, e26 = self.ema(self.c, 12), self.ema(self.c, 26)
        m = [a - b for a, b in zip(e12, e26)]
        s = self.ema(m, 9)
        return m[-1], s[-1], m[-1] - s[-1], m[-2] - s[-2]

    def facts(self, key, fng=None):
        f = getattr(self, "f_" + key, self.f_snap)
        try:
            return f(fng)
        except Exception:
            return self.f_snap(fng)

    # --- 지표별 문장
    def f_snap(self, fng=None):
        c = self.c
        ma20 = sma(c, 20)
        return [f"최근 7일 {pct(c[-1], c[-8]):+.1f}% · 30일 {pct(c[-1], c[-31]):+.1f}%",
                f"20일선 {man(ma20)} — 현재가는 {'위' if c[-1] > ma20 else '아래'} ({pct(c[-1], ma20):+.1f}%)",
                f"RSI(14) {self.rsi():.0f}"]

    def f_gc(self, fng=None):
        c = self.c
        a, b = sma(c, 20), sma(c, 60)
        # 최근 교차
        last = None
        prev = None
        for i in range(60, len(c) + 1):
            d = sma(c, 20, i) - sma(c, 60, i)
            if prev is not None and ((prev <= 0 < d) or (prev >= 0 > d)):
                last = ("골든크로스" if d > 0 else "데드크로스", len(c) - i)
            prev = d
        out = [f"20일선 {man(a)} / 60일선 {man(b)}",
               f"20일선이 60일선 {'위' if a > b else '아래'} (격차 {pct(a, b):+.1f}%)"]
        if last:
            out.append(f"가장 최근 교차: {last[0]} {last[1]}일 전" if last[1] else f"가장 최근 교차: {last[0]} (어제 마감)")
        return out

    def f_rsi(self, fng=None):
        r = self.rsi()
        z = "70 이상 구간" if r >= 70 else "30 이하 구간" if r <= 30 else "30~70 사이"
        c = self.c
        return [f"RSI(14) {r:.0f} — {z}", f"최근 7일 {pct(c[-1], c[-8]):+.1f}% · 30일 {pct(c[-1], c[-31]):+.1f}%"]

    def f_bb(self, fng=None):
        c = self.c[-20:]
        m = sum(c) / 20
        sd = (sum((x - m) ** 2 for x in c) / 20) ** 0.5
        up, lo = m + 2 * sd, m - 2 * sd
        pb = (self.c[-1] - lo) / (up - lo) * 100
        pos = "윗선 위" if pb > 100 else "아랫선 아래" if pb < 0 else "밴드 안"
        return [f"밴드 {man(lo)} ~ {man(up)} (중심 {man(m)})", f"종가는 {pos} — 밴드 내 위치 {pb:.0f}%",
                f"밴드 폭 {((up - lo) / m * 100):.1f}%"]

    def f_ma(self, fng=None):
        c = self.c
        a, b = sma(c, 20), sma(c, 60)
        a5 = sma(c, 20, len(c) - 5)
        return [f"현재가는 20일선 {'위' if c[-1] > a else '아래'} ({pct(c[-1], a):+.1f}%) · 60일선 {'위' if c[-1] > b else '아래'} ({pct(c[-1], b):+.1f}%)",
                f"20일선 {man(a)} — 5일 전보다 {'높음' if a > a5 else '낮음'} ({pct(a, a5):+.1f}%)"]

    def f_macd(self, fng=None):
        m, s, h, hp = self.macd()
        return [f"MACD {'시그널 위' if m > s else '시그널 아래'} (히스토그램 {'+' if h > 0 else ''}{h / 1e4:,.0f}만)",
                f"전일 대비 히스토그램 {'커짐' if abs(h) > abs(hp) else '작아짐'} · MACD {'0선 위' if m > 0 else '0선 아래'}"]

    def f_stoch(self, fng=None):
        k = self.k
        ks = []
        for i in range(len(k) - 5, len(k)):
            w = k[i - 13:i + 1]
            hi, lo = max(x["h"] for x in w), min(x["l"] for x in w)
            ks.append((k[i]["c"] - lo) / (hi - lo) * 100)
        k3 = sum(ks[-3:]) / 3
        d3 = sum([sum(ks[j - 2:j + 1]) / 3 for j in range(2, 5)]) / 3
        z = "80 이상 구간" if k3 >= 80 else "20 이하 구간" if k3 <= 20 else "20~80 사이"
        return [f"스토캐스틱 %K {k3:.0f} / %D {d3:.0f} — {z}"]

    def f_vol(self, fng=None):
        v = [x["v"] for x in self.k]
        avg = sum(v[-21:-1]) / 20
        return [f"어제 거래량은 20일 평균의 {v[-1] / avg:.1f}배", f"최근 7일 평균은 20일 평균의 {sum(v[-7:]) / 7 / avg:.1f}배"]

    def f_trend(self, fng=None):
        c = self.c
        hi30 = max(x["h"] for x in self.k[-30:])
        a = sma(c, 20)
        return [f"최근 30일 고점 {man(hi30)} 대비 {pct(c[-1], hi30):+.1f}%",
                f"20일선까지 거리 {pct(c[-1], a):+.1f}% ({'위' if c[-1] > a else '아래'})"]

    def f_box(self, fng=None):
        w = self.k[-30:]
        hi, lo = max(x["h"] for x in w), min(x["l"] for x in w)
        pos = (self.c[-1] - lo) / (hi - lo) * 100
        return [f"최근 30일 범위 {man(lo)} ~ {man(hi)} (폭 {pct(hi, lo):.1f}%)", f"현재 위치: 범위의 {pos:.0f}% 지점"]

    def f_sr(self, fng=None):
        w = self.k[-60:]
        hi, lo = max(x["h"] for x in w), min(x["l"] for x in w)
        return [f"최근 60일 고점 {man(hi)} ({pct(self.c[-1], hi):+.1f}%)", f"최근 60일 저점 {man(lo)} ({pct(self.c[-1], lo):+.1f}%)"]

    def f_volat(self, fng=None):
        k = self.k
        rng = [(x["h"] - x["l"]) / x["o"] * 100 for x in k]
        r7, r30 = sum(rng[-7:]) / 7, sum(rng[-30:]) / 30
        return [f"일간 고저 폭 평균: 7일 {r7:.1f}% / 30일 {r30:.1f}%", f"최근 일주일은 한 달 평균보다 {'크게' if r7 > r30 else '작게'} 움직임"]

    def f_candle(self, fng=None):
        x = self.k[-1]
        rng = x["h"] - x["l"]
        body = abs(x["c"] - x["o"]) / rng * 100
        up = (x["h"] - max(x["o"], x["c"])) / rng * 100
        dn = (min(x["o"], x["c"]) - x["l"]) / rng * 100
        return [f"어제 {'양봉' if x['c'] >= x['o'] else '음봉'} ({pct(x['c'], x['o']):+.1f}%)",
                f"몸통 {body:.0f}% · 윗꼬리 {up:.0f}% · 아랫꼬리 {dn:.0f}%"]

    def f_gap(self, fng=None):
        g = pct(self.k[-1]["o"], self.k[-2]["c"])
        return [f"코인은 24시간 거래라 갭이 거의 없어요", f"어제 시가와 전날 종가 차이 {g:+.2f}%"]

    def f_fear(self, fng=None):
        if not fng:
            return self.f_rsi()
        return [f"공포·탐욕 지수 {fng['v']} ({fng['cls']})", f"RSI(14) {self.rsi():.0f}"]

    def f_high52(self, fng=None):
        w = self.k[-365:]
        hi = max(x["h"] for x in w)
        lo = min(x["l"] for x in w)
        return [f"52주 고점 {man(hi)} 대비 {pct(self.c[-1], hi):+.1f}%", f"52주 저점 {man(lo)} 대비 {pct(self.c[-1], lo):+.1f}%"]

    def f_cap(self, fng=None):
        c = self.c
        return [f"종가 {man(c[-1])}원", f"최근 7일 {pct(c[-1], c[-8]):+.1f}% · 30일 {pct(c[-1], c[-31]):+.1f}%",
                f"90일 {pct(c[-1], c[-91]):+.1f}%"]

    def f_dca(self, fng=None):
        c = self.c
        buys = [c[-1 - 7 * i] for i in range(8)]  # 8주 전부터 매주 같은 금액
        avg = len(buys) / sum(1 / p for p in buys)  # 같은 금액 매수의 평균 단가
        lump = buys[-1]
        return [f"8주 전부터 매주 같은 금액씩 샀다면 평균 단가 {man(avg)}",
                f"종가 {man(c[-1])} 기준 {pct(c[-1], avg):+.1f}% (8주 전 한 번에 샀다면 {pct(c[-1], lump):+.1f}%)"]

    def f_stop(self, fng=None):
        c = self.c
        hi30 = max(x["h"] for x in self.k[-30:])
        peak = c[-30]
        worst = 0
        for x in c[-30:]:
            peak = max(peak, x)
            worst = min(worst, pct(x, peak))
        return [f"최근 30일 고점 {man(hi30)} 대비 {pct(c[-1], hi30):+.1f}%", f"최근 30일 중 가장 깊었던 낙폭 {worst:.1f}%"]
