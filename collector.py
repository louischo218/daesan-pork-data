# -*- coding: utf-8 -*-
"""
대산에프앤비 경락 데이터 수집기 v1.1 (GitHub Actions용)
[v1.1] 조립 방식 교체: pigGrade 일별 호출(등외제외 파라미터 보장) 기반 시장별 두수가중.
       권역 API의 '전국' 오염 제거, 시장 코드 진단 출력, 대표가격·권역은 참고 수집 유지.
"""
import os, json, datetime, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

KEY = os.environ.get("EKAPE_KEY", "").strip()
BASE = "http://data.ekape.or.kr/openapi-data/service/user/grade/auct"
FETCH_DAYS = int(os.environ.get("FETCH_DAYS", "20"))
EXCLUDE_MARKET_WORDS = ["제주"]     # 시장명에 이 단어가 들면 전국(제주제외) 조립에서 제외
MARKET_NAMES = {}                    # 코드→시장명 (응답 태그만으로는 이름 불명 — 진단 로그로 축적)

def call(api, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    with urllib.request.urlopen(f"{BASE}/{api}?serviceKey={KEY}&{qs}", timeout=25) as r:
        return ET.fromstring(r.read())

def t(node, tag):
    el = node.find(f".//{tag}")
    return el.text.strip() if el is not None and el.text else ""

def num(s):
    try: return float(str(s).replace(",", ""))
    except Exception: return None

def biz_days(n):
    out, d = [], datetime.date.today()
    while len(out) < n:
        d -= datetime.timedelta(days=1)
        if d.weekday() < 5: out.append(d.strftime("%Y%m%d"))
    return list(reversed(out))

def main():
    if not KEY:
        raise SystemExit("EKAPE_KEY Secret이 설정되지 않았습니다.")
    p = Path("data.json")
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    for k in ("daily", "regional", "representative", "markets"): data.setdefault(k, {})
    data["basis"] = "축평원 pigGrade 일별 · 탕박 · 등외제외 · 전 등급/성별/도매시장(제주 제외) 두수가중"
    days = biz_days(FETCH_DAYS)
    diag = {}

    for ymd in days:                                    # ① 시장별(등외제외) — 일별 호출이 핵심
        try:
            root = call("pigGrade", startYmd=ymd, endYmd=ymd, skinYn="Y", egradeExceptYn="Y")
            mk = {}
            for it in root.iter("item"):
                for ch in it:
                    if ch.tag.startswith("c_") and ch.tag.endswith("Amt"):
                        code = ch.tag[2:-3]
                        amt, cnt = num(ch.text), num(t(it, f"c_{code}Cnt"))
                        if amt and cnt:
                            e = mk.setdefault(code, [0.0, 0.0])
                            e[0] += amt * cnt; e[1] += cnt
            if mk:
                data["markets"][ymd] = {c: {"amt": round(v[0]/v[1]), "cnt": v[1]} for c, v in mk.items()}
                for c, v in mk.items():
                    d0 = diag.setdefault(c, [0.0, 0.0]); d0[0] += v[0]; d0[1] += v[1]
        except Exception as e:
            print(f"시장별 {ymd} 실패: {e}")

    for ymd in days:                                    # ② 권역별 (참고용 — '전국' 행은 국가값으로 분리)
        try:
            root = call("pigApperence", baseYmd=ymd)
            regs = {}
            for it in root.iter("item"):
                if t(it, "skinNm") != "탕박": continue
                nm, amt, cnt = t(it, "localNm"), num(t(it, "auctAmt")), num(t(it, "auctCnt"))
                if nm and amt: regs[nm] = {"amt": amt, "cnt": cnt or 0}
            if regs: data["regional"][ymd] = regs
        except Exception as e:
            print(f"권역 {ymd} 실패: {e}")

    try:                                                # ③ 대표가격
        root = call("pigRepresentativePrice", startYmd=days[0], endYmd=days[-1], numOfRows=200, pageNo=1)
        for it in root.iter("item"):
            if "탕박" in t(it, "sableGubn") or "대표" in t(it, "sableGubn"):
                ymd, v = t(it, "sumYmd"), num(t(it, "costAmt"))
                if ymd and v: data["representative"][ymd] = v
    except Exception as e:
        print(f"대표가격 실패: {e}")

    # 전국(제주제외) 조립: 시장별 두수가중, 제외 코드 반영
    exc = set(os.environ.get("EXCLUDE_CODES", "").split(",")) - {""}
    for ymd, mk in data["markets"].items():
        s = c2 = 0.0
        for code, v in mk.items():
            if code in exc: continue
            s += v["amt"] * v["cnt"]; c2 += v["cnt"]
        if c2 > 0: data["daily"][ymd] = round(s / c2)

    data["updated"] = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    data["daily"] = dict(sorted(data["daily"].items()))
    p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print("\n── 시장 코드 진단 (기간 평균가·총두수 — 제주 코드 식별용) ──")
    for c, (sv, cv) in sorted(diag.items(), key=lambda x: -x[1][1]):
        print(f"  코드 {c}: 평균 {sv/cv:,.0f}원 · 두수 {cv:,.0f}")
    print("\n── 최근 조립가 (사내 리포트와 대조) ──")
    for k in sorted(data["daily"])[-5:]:
        print(f"  {k}: {data['daily'][k]:,}원")
    print(f"\n저장 완료: 일별 {len(data['daily'])} · 시장 {len(data['markets'])}일")

if __name__ == "__main__":
    main()
