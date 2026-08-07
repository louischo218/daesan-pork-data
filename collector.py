# -*- coding: utf-8 -*-
"""
대산에프앤비 경락 데이터 수집기 (GitHub Actions용)
축평원 OpenAPI → data.json 자동 발행. 판가 운영프로그램 전용 데이터 파이프라인.
- 인증키는 저장소 Secret(EKAPE_KEY)에서 읽음 (코드에 키 없음)
- 실행할 때마다 최근 20영업일을 수집해 기존 data.json에 병합 (이력 누적)
"""
import os, json, datetime, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

KEY = os.environ.get("EKAPE_KEY", "").strip()
BASE = "http://data.ekape.or.kr/openapi-data/service/user/grade/auct"
EXCLUDE = ["제주"]        # 전국(제주제외) 조립 시 제외할 권역 키워드
FETCH_DAYS = int(os.environ.get("FETCH_DAYS", "20"))

def call(api, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}/{api}?serviceKey={KEY}&{qs}"
    with urllib.request.urlopen(url, timeout=25) as r:
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
    data.setdefault("daily", {}); data.setdefault("regional", {})
    data.setdefault("representative", {}); data.setdefault("markets", {})
    data["basis"] = "축평원 OpenAPI · 탕박 · 등외제외 · 전국(제주제외) 두수가중 조립"
    days = biz_days(FETCH_DAYS)

    for ymd in days:                                   # ① 권역별
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

    try:                                               # ② 시장별 (등외제외·탕박)
        root = call("pigGrade", startYmd=days[0], endYmd=days[-1], skinYn="Y", egradeExceptYn="Y")
        for it in root.iter("item"):
            ymd = t(it, "startYmd").replace(".", "").replace("-", "")[:8]
            if not ymd: continue
            mk = data["markets"].setdefault(ymd, {})
            for ch in it:
                if ch.tag.startswith("c_") and ch.tag.endswith("Amt"):
                    code = ch.tag[2:-3]; amt = num(ch.text)
                    if amt: mk[code] = {"amt": amt, "cnt": num(t(it, f"c_{code}Cnt")) or 0}
    except Exception as e:
        print(f"시장별 실패: {e}")

    try:                                               # ③ 대표가격
        root = call("pigRepresentativePrice", startYmd=days[0], endYmd=days[-1], numOfRows=200, pageNo=1)
        for it in root.iter("item"):
            if "탕박" in t(it, "sableGubn") or "대표" in t(it, "sableGubn"):
                ymd, v = t(it, "sumYmd"), num(t(it, "costAmt"))
                if ymd and v: data["representative"][ymd] = v
    except Exception as e:
        print(f"대표가격 실패: {e}")

    for ymd, regs in data["regional"].items():         # 전국(제주제외) 조립
        use = {k: v for k, v in regs.items() if not any(x in k for x in EXCLUDE)}
        tot = sum(v["cnt"] for v in use.values())
        if tot > 0:
            data["daily"][ymd] = round(sum(v["amt"] * v["cnt"] for v in use.values()) / tot)

    data["updated"] = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    data["daily"] = dict(sorted(data["daily"].items()))
    p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    last = sorted(data["daily"])[-3:]
    print("최근 조립가:", {k: data["daily"][k] for k in last})
    print(f"저장 완료: 일별 {len(data['daily'])}건")

if __name__ == "__main__":
    main()
