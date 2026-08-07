# -*- coding: utf-8 -*-
"""
대산에프앤비 경락 데이터 수집기 v2.0 (GitHub Actions용)
[v2.0] 사내 검증 레시피 채택: pigGrade 응답의 '등외제외' 집계행 c_1101eTotAmt
       = 축평원 공식 전국(탕박·등외제외) — 사내 경락 리포트와 동일 값 보장.
       + 시장별(이름 매핑)·권역별·대표가격 수집, 최근 7일 재수집, 공휴일 API.
"""
import os, json, datetime, urllib.request, xml.etree.ElementTree as ET
from datetime import timedelta
from pathlib import Path

KEY = os.environ.get("EKAPE_KEY", "").strip()
BASE = "http://data.ekape.or.kr/openapi-data/service/user/grade/auct"
FETCH_DAYS = int(os.environ.get("FETCH_DAYS", "20"))   # 신규 수집 범위(영업일)
RECHECK_DAYS = 7                                        # 확정치 소급 반영 재수집
MARKETS = {  # 사내 검증 매핑
    "0320": ("도드람", "수도권"), "0302": ("협신식품", "수도권"), "1301": ("삼성식품", "수도권"),
    "0323": ("농협부천", "수도권"), "1005": ("김해축공", "영남권"), "0202": ("부경축공", "영남권"),
    "1201": ("신흥산업", "영남권"), "0905": ("농협고령", "영남권"), "0809": ("농협나주", "호남권"),
    "1401": ("삼호축산", "호남권"),
}
HOLIDAYS_FALLBACK = {
    "20260101","20260216","20260217","20260218","20260301","20260505","20260525",
    "20260603","20260606","20260815","20261009","20261225",
}

def call(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8")

def api(name, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return ET.fromstring(call(f"{BASE}/{name}?serviceKey={KEY}&{qs}"))

def t(node, tag):
    el = node.find(f".//{tag}")
    return el.text.strip() if el is not None and el.text else ""

def num(s):
    try: return float(str(s).replace(",", ""))
    except Exception: return None

def load_holidays():
    hol = set(HOLIDAYS_FALLBACK)
    y = datetime.date.today().year
    for yr in (y, y + 1):
        try:
            raw = call(f"http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
                       f"?serviceKey={KEY}&solYear={yr}&numOfRows=60&_type=json")
            items = json.loads(raw)["response"]["body"]["items"]["item"]
            if isinstance(items, dict): items = [items]
            for it in items: hol.add(str(it["locdate"]))
        except Exception:
            pass
    return hol

def workdays_back(n, hol):
    out, d = [], datetime.date.today()
    while len(out) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5 and d.strftime("%Y%m%d") not in hol:
            out.append(d.strftime("%Y%m%d"))
    return list(reversed(out))

def fetch_day(ymd):
    """(전국_등외제외, 시장별dict) — 사내 검증 레시피"""
    try:
        root = api("pigGrade", startYmd=ymd, endYmd=ymd, skinYn="Y", numOfRows=100, pageNo=1)
    except Exception as e:
        print(f"  {ymd} 호출 실패: {e}")
        return 0, {}
    national, mk = 0, {}
    for it in root.findall(".//item"):
        if (it.findtext("gradeNm") or "") == "등외제외":
            v = it.findtext("c_1101eTotAmt")
            national = int(v) if v and v.strip() else 0
            for code, (nm, reg) in MARKETS.items():
                amt, cnt = num(it.findtext(f"c_{code}Amt")), num(it.findtext(f"c_{code}Cnt"))
                if amt and cnt:
                    mk[code] = {"nm": nm, "reg": reg, "amt": round(amt), "cnt": cnt}
    return national, mk

def main():
    if not KEY:
        raise SystemExit("EKAPE_KEY Secret이 설정되지 않았습니다.")
    p = Path("data.json")
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    for k in ("daily", "markets", "regional", "representative"): data.setdefault(k, {})
    data["basis"] = "축평원 pigGrade '등외제외' 공식 집계 (탕박·등외제외 전국) — 사내 리포트와 동일 원천"
    hol = load_holidays()
    days = workdays_back(FETCH_DAYS, hol)
    recheck = set(workdays_back(RECHECK_DAYS, hol))
    todo = [d for d in days if d not in data["daily"] or d in recheck]
    print(f"수집: {len(todo)}건 (신규+최근{RECHECK_DAYS}일 재확인)")

    for ymd in todo:
        nat, mk = fetch_day(ymd)
        if nat > 0:
            data["daily"][ymd] = nat
            if mk: data["markets"][ymd] = mk

    for ymd in todo:                                   # 권역별 (참고)
        try:
            root = api("pigApperence", baseYmd=ymd)
            regs = {}
            for it in root.iter("item"):
                if t(it, "skinNm") != "탕박": continue
                nm, amt, cnt = t(it, "localNm"), num(t(it, "auctAmt")), num(t(it, "auctCnt"))
                if nm and amt: regs[nm] = {"amt": amt, "cnt": cnt or 0}
            if regs: data["regional"][ymd] = regs
        except Exception:
            pass

    try:                                               # 대표가격
        root = api("pigRepresentativePrice", startYmd=days[0], endYmd=days[-1], numOfRows=200, pageNo=1)
        for it in root.iter("item"):
            if "탕박" in t(it, "sableGubn") or "대표" in t(it, "sableGubn"):
                ymd, v = t(it, "sumYmd"), num(t(it, "costAmt"))
                if ymd and v: data["representative"][ymd] = v
    except Exception as e:
        print(f"대표가격 실패: {e}")

    data["updated"] = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    data["daily"] = dict(sorted(data["daily"].items()))
    p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("\n── 최근 전국(탕박·등외제외) — 사내 리포트와 동일해야 정상 ──")
    for k in sorted(data["daily"])[-5:]:
        print(f"  {k}: {data['daily'][k]:,}원")
    print(f"\n저장: 일별 {len(data['daily'])} · 시장 {len(data['markets'])} · 권역 {len(data['regional'])} · 대표 {len(data['representative'])}")

if __name__ == "__main__":
    main()
