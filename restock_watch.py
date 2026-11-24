#!/usr/bin/env python3
"""재입고 감시 — 손님 화면(공개 페이지)만 읽어 '품절 → 살 수 있음'으로 바뀐 상품·옵션을 기록한다.

쓰는 법
  python3 -I restock_watch.py [--dir 폴더] [--base https://campingmoon.co.kr] [--opts auto|yes|no] [--opt-hours 9,12,15,18]

  --dir        state/·docs/가 있는 폴더(기본: 이 파일이 있는 폴더)
  --opts       옵션 상태(상세 화면) 읽기. auto = --opt-hours 칸(9~11·12~14·15~17·18~20시)마다 그 칸에서 처음 도는 실행이
               판매 중 옵션 상품을 다 읽고, 그 밖에는 상품 단위 재입고가 생긴 상품만 / yes = 판매 중 옵션 상품 전부 / no = 안 읽음
               (GitHub 정시 실행은 수십 분 늦게 돌 때가 많다 — 11/10 밤 7·48·51분. 정해진 '시각'으로 하면 그 시각을 건너뛸 수 있어 '칸'으로 한다)
  --only       시험용. 상세를 읽을 상품을 이 번호들로 좁힌다(예: --only 949,4305)
  --now        시험용. 지금 시각을 바꾼다(예: --now 2026-11-11T10:13+09:00)

남기는 것
  state/snapshot.json  지난번 상태(상품: 판매·품절·단종, 옵션 상품: 옵션마다 살 수 있음 여부)
  state/history.json   재입고 기록(30일)
  state/log.txt        실행 한 줄 기록
  docs/restock.json    스킨이 읽는 결과 — 지금 살 수 있는 재입고만, 최신순
  state/soldout.json   품절 시각 — 상품마다 '판매 → 품절'로 바뀐 때(감시 전부터 품절이던 상품은 before = 날짜 모름)
  docs/soldout.json    스킨이 읽는 품절 날짜 — 지금 품절인 상품만. items(날짜 아는 것, 최신순) + before(날짜 모름)
  docs/shipfee.json    스킨이 읽는 배송비 예외 — 목록 카드 '배송비' 글이 가장 흔한 값(common, 몰 기본)과 다른 상품만 {상품번호: 글}.
                       휴대폰 카드는 배송비 칸이 없어 무료배송 표시를 이것으로 판단한다(11/13). 상태 파일에는 넣지 않는다
  state/skip.json      목록을 못 읽어 버린 실행이 몇 번 이어졌는지(정상 실행에서 지운다). 한두 번은 정상으로 끝내 기록만 남기고,
                       3번째(FAIL_ALERT)부터 실패로 끝내 GitHub 실패 메일이 가게 한다(11/14 사용자: 한 번 실패는 치명적이지 않다)
  state/specials.json  특가 검사(11/24): 품목마다 지난번 판매가 · 최종가(base)와 이어지는 경보(alerts). 아래 '특가 검사'

특가 검사(11/24 — 출시 전 점검 다1 · 다3, 코덱스 · Claude 계획 검토)
  특가 분류(200)의 판매 중 상품 · 품목을 비회원으로 카페24 할인 계산(CalculatorProduct) 수량 1 · 2 해 본다. 목록의 판매가 · 할인판매가도 본다.
  계속 경보 — 문제가 남아 있는 동안 SPECIAL_MAIL_HOURS(6시간)마다 다시 메일, 풀리면 기록에 '해소':
    할인 없음(특가 분류인데 할인 0) · 0원 이하 · 수량(2개 ≠ 1개 × 2 — 혜택 '구매수량에 관계없이') · 계산 거절(판매 중인데)
    · 분류 밖 할인(특가 분류가 아닌데 목록 할인판매가 < 판매가) · 목록에 할인판매가가 안 보임(표시 설정)
  한 번 경보 — 바뀐 것을 한 번 알리고 새 값을 기준으로 삼는다: 판매가 바뀜(특가 금액을 판매가에 넣으면 할인이 한 번 더 빠짐) · 최종가 30% 넘게 떨어짐
  기록만: 새 특가 품목 · 특가에서 빠짐 · 최종가 오름 · 2개 계산 안 됨(재고 1개 등)
  새 경보는 SPECIAL_RECHECK(6분) 뒤 다시 계산해 같을 때만 낸다 — 카페24 설정을 바꾼 직후 3~5분은 계산이 옛 값과 섞인다(점검 다5).
  메일 = GitHub 실행 실패. 실패하면 watch.yml '결과 저장'이 건너뛰어지므로 이 프로그램이 기록을 먼저 올린(commit · push) 뒤 실패로 끝낸다.
  회원 등급 쪽(등급 '상품별 할인과 중복시 설정')은 비회원 계산으로 못 본다 — 등급 7개 모두 '상품별 가격할인만'이라 특가는 누구에게나 같은 값(11/24)

GitHub에서 돌 때는 시작하면서 저장소의 최신 커밋으로 옮긴다(이 실행이 시작한 커밋 뒤에 다른 실행이 기록을 올렸을 때).
옛 기록으로 계산하면 '결과 저장'(git pull --rebase)에서 부딪혀 실패하기 때문이다(11/13 프로그램을 올린 실행).

재입고로 치는 것: 지난번 품절 → 이번 판매(상품 단위), 지난번 살 수 없던 옵션 → 이번 살 수 있음(옵션 단위)
치지 않는 것: 새 상품, 단종, 숨김→보임, 소량→넉넉. 다시 품절이 되면 결과에서 빠진다.
읽기만 한다(로그인·저장·장바구니 없음).
"""
import collections
import datetime
import html
import http.cookiejar
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

KST = datetime.timezone(datetime.timedelta(hours=9))
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
KEEP_DAYS, BADGE_DAYS = 30, 14
SPECIAL_CATES = [200]   # 특가 분류 번호(카페24에 만든 뒤 넣는다, 11/13). 특가 분류에만 넣고 전체상품(152)에 빠뜨린 상품도 품절·재입고를 감시한다
PAY = {4087, 4225, 4247, 4453, 4454, 4470}   # 개인결제창
MIN_RATIO = 0.9                               # 목록이 지난번의 90%보다 적게 읽히면 이번 실행은 버린다
FAIL_ALERT = 3                                # 버린 실행이 이만큼 이어질 때만 실패로 끝낸다(GitHub 실패 메일, 11/14)
SPECIAL_MAIL_HOURS = 6                        # 같은 특가 경보가 이어지면 이만큼마다 다시 메일(11/24)
SPECIAL_RECHECK = int(os.environ.get('SPECIAL_RECHECK_SEC', '360'))   # 새 특가 경보는 6분 뒤 다시 계산해 같을 때만(시험 때만 줄인다)
SPECIAL_DROP = 0.3                            # 최종가가 지난번보다 30% 넘게 떨어지면 한 번 경보


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1]
    return default


def get(url, tries=3):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'ko-KR,ko;q=0.9'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as e:  # 잠깐 끊긴 것은 다시 해 본다
            last = e
            time.sleep(2 + 3 * k)
    raise last


CARD = re.compile(r'<li data-no="(\d+)"[^>]*class="v3-card[^"]*">(.*?)</li>\s*(?=<li data-no|</ul>)', re.S)
ITEM = re.compile(r'<li class="([^"]*)">\s*<span class="k">(.*?)</span>\s*<span class="v">(.*?)</span>', re.S)


def plain(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', s))).strip()


def won(s):
    """'25,000원' → 25000, 금액이 없으면 0"""
    m = re.search(r'([\d,]+)\s*원', s or '')
    return int(m.group(1).replace(',', '')) if m else 0


def parse_feed(page):
    out = {}
    for m in CARD.finditer(page):
        no, c = int(m.group(1)), m.group(2)
        nm = re.search(r'class="nm"[^>]*>(.*?)</a>', c, re.S)
        name = html.unescape(re.sub(r'<[^>]+>', '', nm.group(1))).strip() if nm else ''
        sold = bool(re.search(r'class="soldsrc">\s*<img', c))
        # 목록 표시 항목 '배송비'(카페24 상품정보 표시설정에서 켬, 11/13). 숨은 칸(displaynone)은 보지 않는다
        shown = {plain(k).rstrip(' :'): plain(v) for cls, k, v in ITEM.findall(c) if 'displaynone' not in cls}
        fee = shown.get('배송비', '')
        # 판매가 · 할인판매가(비회원 목록 — 할인판매가는 상품 할인(특가 혜택)이 있을 때만 나온다, 11/23 표시 켬): 특가 검사만 쓰고 상태 파일에는 넣지 않는다
        out[no] = {'n': name, 's': '품절' if sold else '판매', 'f': fee, 'pr': won(shown.get('판매가')), 'dc': won(shown.get('할인판매가'))}
    return out


def crawl(base, cate, sort=None):
    items, page = {}, 1
    while page <= 30:
        url = '%s/product/v3_feed.html?cate_no=%d%s%s' % (base, cate, '&sort_method=%d' % sort if sort else '', '&page=%d' % page if page > 1 else '')
        got = parse_feed(get(url))
        items.update(got)
        if len(got) < 200:
            break
        page += 1
        time.sleep(0.5)
    return items


OSD = re.compile(r"var option_stock_data = '(.*?)';", re.S)
HAS = re.compile(r"var has_option = '([TF])'")


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 1.0


def options_of(base, no):
    """옵션 상품이면 {품목코드: [살 수 있음 1/0, 옵션 이름]}, 옵션 없는 상품이면 {}, 못 읽으면 None"""
    try:
        h = get('%s/product/detail.html?product_no=%d' % (base, no))
    except Exception:
        return None
    has = HAS.search(h)
    if has and has.group(1) == 'F':
        return {}
    m = OSD.search(h)
    if not m:
        return None
    try:
        data = json.loads(re.sub(r'\\(["\\/])', r'\1', m.group(1)))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return {}
    out = {}
    for code, v in data.items():
        if not isinstance(v, dict) or v.get('is_display') != 'T':
            continue   # 손님에게 안 보이는 옵션은 보지 않는다
        sold = v.get('use_stock') in (True, 'T') and v.get('use_soldout') == 'T' and 'stock_number' in v and num(v['stock_number']) <= 0
        out[code] = [1 if (v.get('is_selling') == 'T' and not sold) else 0, (v.get('option_value') or '').strip()]
    return out


def opt_slot(t, hours):
    """옵션 전체 읽기 칸. 각 시각부터 다음 시각 전까지(마지막 시각은 3시간), 칸 밖이면 None. 예: 9·12·15·18 → 10:13은 '날짜 09'"""
    hs = sorted(hours)
    if not hs or t.hour < hs[0] or t.hour >= hs[-1] + 3:
        return None
    return '%s %02d' % (t.date().isoformat(), max(h for h in hs if h <= t.hour))


def load(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(tmp, path)



def sync_latest(root):
    """GitHub에서 돌 때만: 이 실행이 시작한 커밋 뒤에 다른 실행이 기록을 더 올렸으면 그 최신 커밋으로 옮긴다.
    옮기지 못하면(받기 실패 · 이어지지 않는 커밋 · 고친 파일 있음) 그대로 한다 — 예전과 같다. 옮긴 커밋 앞 7자리 또는 ''를 돌려준다"""
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        return ''

    def git(*a):
        return subprocess.run(['git', '-C', root] + list(a), capture_output=True, text=True, timeout=120)
    try:
        if git('fetch', '-q', '--depth=50', 'origin', 'main').returncode:
            return ''
        head = git('rev-parse', 'HEAD').stdout.strip()
        latest = git('rev-parse', 'FETCH_HEAD').stdout.strip()
        if not latest or head == latest or git('merge-base', '--is-ancestor', 'HEAD', 'FETCH_HEAD').returncode:
            return ''
        if git('status', '--porcelain', '--untracked-files=no').stdout.strip():
            return ''
        return latest[:7] if git('reset', '-q', '--hard', 'FETCH_HEAD').returncode == 0 else ''
    except Exception:
        return ''


# ── 특가 검사(11/24) ──

def code_of(no):
    """카페24 상품코드(스킨 codeOf와 같은 규칙 — 2441~3048은 번호 − 1). 옵션 없는 상품의 품목코드는 여기에 000A"""
    n = no - 1 if 2441 <= no <= 3048 else no
    s = ''
    while n > 0:
        s = chr(65 + n % 26) + s
        n //= 26
    return 'P0000' + ('000' + s)[-3:]


def intval(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


class Guest:
    """비회원 손님 연결(쿠키를 지님) — 카페24 할인 계산(CalculatorProduct)은 상세 화면을 연 뒤의 쿠키로만 된다(11/24 실측)"""

    def __init__(self, base):
        self.base = base
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def get(self, path, xhr=False, tries=3):
        last = None
        for k in range(tries):
            try:
                h = {'User-Agent': UA, 'Accept-Language': 'ko-KR,ko;q=0.9'}
                if xhr:
                    h['X-Requested-With'] = 'XMLHttpRequest'
                with self.op.open(urllib.request.Request(self.base + path, headers=h), timeout=30) as r:
                    return r.read().decode('utf-8', 'replace')
            except Exception as e:  # 잠깐 끊긴 것은 다시 해 본다
                last = e
                time.sleep(2 + 3 * k)
        raise last

    def items(self, no):
        """판매 중 품목 [(품목코드, 옵션 이름)] — 손님에게 보이고 팔고 있고 품절이 아닌 것만(options_of와 같은 기준). 못 읽으면 None"""
        h = self.get('/product/detail.html?product_no=%d' % no)
        has = HAS.search(h)
        if has and has.group(1) == 'F':
            return [(code_of(no) + '000A', '')]
        m = OSD.search(h)
        if not m:
            return None
        try:
            data = json.loads(re.sub(r'\\(["\\/])', r'\1', m.group(1)))
        except ValueError:
            return None
        out = []
        for code, v in sorted((data or {}).items()):
            if not isinstance(v, dict) or v.get('is_display') != 'T' or v.get('is_selling') != 'T':
                continue
            sold = v.get('use_stock') in (True, 'T') and v.get('use_soldout') == 'T' and 'stock_number' in v and num(v['stock_number']) <= 0
            if not sold:
                out.append((code, (v.get('option_value') or '').strip()))
        return out

    def calc(self, no, code, qty):
        """비회원 할인 계산 → {'p': 품목 단가(옵션 추가금액 포함), 'd': 할인 합, 'o': 최종 합}. 카페24가 거절하면(품절 · 재고 모자람 등) None"""
        q = urllib.parse.urlencode({'product_no': no, 'ch_ref': '', 'is_subscription': 'F', 'product[%s]' % code: qty})
        j = json.loads(self.get('/exec/front/shop/CalculatorProduct?' + q, xhr=True))
        x = j.get(code) if isinstance(j, dict) else None
        if not isinstance(x, dict) or j.get('Result') is False:
            return None
        p, d, o = intval(x.get('item_price')), intval(j.get('iTotalAddSalePrice')), intval(j.get('iTotalOrderPrice'))
        return None if None in (p, d, o) else {'p': p, 'd': d, 'o': o}


def special_lists(base):
    """특가 검사에 쓰는 목록: {상품번호: {'n', 's', 'pr' 판매가, 'dc' 할인판매가}}와 특가 분류 상품번호(개인결제창 뺌)"""
    lst, sp = crawl(base, 152, 5), set()
    for sc in SPECIAL_CATES:
        got = crawl(base, sc)
        sp |= set(got)
        for no, e in got.items():
            lst.setdefault(no, e)
    for no in list(lst):
        if no in PAY or '개인결제' in lst[no]['n']:
            del lst[no]
    return lst, sp - PAY


def special_observe(g, lst, sp):
    """특가 분류의 판매 중 상품 · 품목을 수량 1 · 2로 계산한다. 연결이 끊겨 못 본 상품 · 품목은 'errs'에(경보를 풀지도 내지도 않는다)"""
    items, errs = {}, set()
    for no in sorted(sp):
        e = lst.get(no) or {}
        if e.get('s') != '판매':
            continue   # 품절 · 단종 특가는 계산하지 않는다(카페24가 거절)
        try:
            its = g.items(no)
        except Exception:
            its = None
        if its is None:
            errs.add(no)
            continue
        for code, oname in its:
            key = '%d:%s' % (no, code)
            r = {'n': (e.get('n') or '')[:40] + (' · ' + oname if oname else '')}
            try:
                r['c1'] = g.calc(no, code, 1)
                r['c2'] = g.calc(no, code, 2) if r['c1'] else None
            except Exception:
                errs.add(no)
                continue
            items[key] = r
            time.sleep(0.3)
    return {'items': items, 'errs': sorted(errs), 'sp': sorted(sp),
            'list': {no: (e.get('pr') or 0, e.get('dc') or 0, e.get('s')) for no, e in lst.items()}}


def special_findings(obs, base, stamp):
    """관찰 → (계속 경보 {열쇠: 글}, 한 번 경보 {열쇠: 글}, 기록 [글], 새 기준 {품목: 값})"""
    keep, once, info, nb = {}, {}, [], {}
    fmt = lambda v: '{:,}'.format(v)
    for key, r in sorted(obs['items'].items()):
        c1, c2, nm = r.get('c1'), r.get('c2'), r['n']
        if c1 is None:
            keep['calc:' + key] = '%s(%s) — 판매 중인데 1개 계산을 카페24가 거절' % (nm, key)
            continue
        p, d1, o1 = c1['p'], c1['d'], c1['o']
        if d1 <= 0:
            keep['nodc:' + key] = '%s(%s) — 특가 분류인데 할인이 붙지 않음(판매가 %s원 그대로)' % (nm, key, fmt(p))
        if o1 <= 0:
            keep['zero:' + key] = '%s(%s) — 할인 뒤 %s원(0원 이하)' % (nm, key, fmt(o1))
        if c2 is None:
            info.append('2개 계산 안 됨(재고 등) %s' % key)
        elif c2['o'] != 2 * o1:
            keep['qty:' + key] = '%s(%s) — 2개 %s원 ≠ 1개 %s원 × 2: 할인이 수량대로 붙지 않음(혜택 \'구매수량에 따라\' 확인)' % (nm, key, fmt(c2['o']), fmt(o1))
        b = base.get(key)
        if b:
            if b.get('p') != p:
                once['price:%s:%d' % (key, p)] = '%s(%s) — 판매가 %s → %s원: %s' % (nm, key, fmt(b.get('p') or 0), fmt(p), (
                    '특가 금액을 판매가에 넣은 것이면 할인이 한 번 더 빠집니다(판매가는 평소 가격 그대로 두기)' if p < (b.get('p') or 0) else '평소 가격을 바꾼 것이면 그대로 두세요'))
            if o1 < (b.get('o1') or 0) * (1 - SPECIAL_DROP):
                once['drop:%s:%d' % (key, o1)] = '%s(%s) — 최종가 %s → %s원(%d%% 떨어짐)' % (nm, key, fmt(b['o1']), fmt(o1), round(100 * (1 - o1 / b['o1'])))
            elif o1 != b.get('o1'):
                info.append('최종가 바뀜 %s %s → %s' % (key, fmt(b.get('o1') or 0), fmt(o1)))
        else:
            info.append('새 특가 품목 %s %s원 → %s원' % (key, fmt(p), fmt(o1)))
        nb[key] = {'n': nm, 'p': p, 'o1': o1, 't': stamp}
    sp, errs = set(obs['sp']), set(obs['errs'])
    for key, b in base.items():
        no = int(key.split(':')[0])
        if key in nb:
            continue
        if no in sp:
            nb[key] = b   # 품절 · 못 읽음 · 잠시 안 파는 품목: 기준은 그대로 둔다
        else:
            info.append('특가에서 빠짐 %s' % key)
    # 목록: 특가 분류 밖의 할인 · 특가 분류인데 목록에 할인판매가가 안 보임
    hidden = []
    for no, (pr, dc, st) in sorted(obs['list'].items()):
        if no not in sp:
            if st == '판매' and pr and dc and dc < pr:
                keep['outside:%d' % no] = '상품 %d — 특가 분류(200) 밖인데 목록에 할인 %s → %s원: 특가면 분류에 넣고, 아니면 할인혜택 확인' % (no, fmt(pr), fmt(dc))
        elif st == '판매' and no not in errs and not (pr and dc and dc < pr):
            hidden.append(no)
    if hidden:
        keep['listdc'] = '특가 분류 판매 상품 %s의 목록에 할인판매가가 안 보임 — 상품정보 표시설정의 할인판매가 · 할인혜택 기간 확인' % ', '.join(map(str, hidden))
    return keep, once, info, nb


def special_alerts(keep, once, state, errs, stamp, now):
    """메일을 보낼지와 이어지는 경보 정리 → (메일 여부, 줄 [(종류, 열쇠, 글)])
    새 계속 경보 · SPECIAL_MAIL_HOURS 지난 계속 경보 · 한 번 경보 → 메일. 없어진 계속 경보 → '해소'(못 읽은 상품의 경보는 그대로 둔다)"""
    alerts, lines, mail = state.setdefault('alerts', {}), [], False
    for k, m in sorted(keep.items()):
        a = alerts.get(k)
        if not a:
            alerts[k] = {'m': m, 'first': stamp, 'mail': stamp}
            lines.append(('새 경보', k, m))
            mail = True
            continue
        a['m'] = m
        try:
            gap = (now - datetime.datetime.fromisoformat(a['mail'])).total_seconds() / 3600
        except (KeyError, TypeError, ValueError):
            gap = SPECIAL_MAIL_HOURS
        if gap >= SPECIAL_MAIL_HOURS - 0.05:
            a['mail'] = stamp
            lines.append(('계속', k, m))
            mail = True
    for k in sorted(alerts):
        if k in keep:
            continue
        parts = k.split(':')
        if len(parts) > 1 and parts[1].isdigit() and int(parts[1]) in errs:
            continue   # 이번에 못 읽은 상품: 풀렸는지 모른다
        lines.append(('해소', k, alerts.pop(k)['m']))
    for k, m in sorted(once.items()):
        lines.append(('바뀜', k, m))
        mail = True
    return mail, lines


def push_now(root, msg):
    """메일(실패)로 끝내기 전에 기록을 먼저 올린다 — 실패하면 watch.yml의 '결과 저장'이 건너뛰어지므로(11/24). GitHub에서만"""
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        return '올리지 않음(GitHub 밖)'

    def git(*a):
        return subprocess.run(['git', '-C', root] + list(a), capture_output=True, text=True, timeout=120)
    git('config', 'user.name', 'restock-watch')
    git('config', 'user.email', 'restock-watch@users.noreply.github.com')
    git('add', 'state', 'docs')
    if git('commit', '-q', '-m', msg).returncode:
        return '올릴 것 없음'
    git('pull', '--rebase', '-q', 'origin', 'main')
    return '올림' if git('push', '-q').returncode == 0 else '올리기 실패'


def special_run(root, base, stamp, now, lst, sp, log):
    """특가 검사 한 번. 메일을 보내야 하면 1"""
    path = os.path.join(root, 'state', 'specials.json')
    state = load(path, None) or {}
    basep = state.get('base') or {}
    g = Guest(base)
    obs = special_observe(g, lst, sp)
    if obs['errs'] and not obs['items']:
        raise RuntimeError('판매 중 특가를 하나도 못 읽음(%s)' % ','.join(map(str, obs['errs'])))
    keep, once, info, nb = special_findings(obs, basep, stamp)
    fresh = [k for k in keep if k not in (state.get('alerts') or {})]
    rechecked = ''
    if (fresh or once) and SPECIAL_RECHECK >= 0:
        time.sleep(SPECIAL_RECHECK)   # 카페24 설정을 바꾼 직후 3~5분은 계산이 옛 값과 섞인다 — 같은 결과일 때만 경보
        lst2, sp2 = special_lists(base)
        obs = special_observe(Guest(base), lst2, sp2)
        keep2, once2, info, nb = special_findings(obs, basep, stamp)
        dropped = [k for k in list(keep) + list(once) if k not in keep2 and k not in once2]
        keep = {k: m for k, m in keep2.items() if k in keep or k in (state.get('alerts') or {})}
        once = {k: m for k, m in once2.items() if k in once}
        rechecked = ' · %d분 뒤 다시 계산%s' % (max(1, round(SPECIAL_RECHECK / 60)), (' — 사라짐 %d' % len(dropped)) if dropped else '')
    mail, lines = special_alerts(keep, once, state, set(obs['errs']), stamp, now)
    state['base'] = nb
    state['checked'] = stamp
    state.pop('fail', None)   # 검사를 해냈으면 '못 함' 이어짐을 지운다
    save(path, state)
    log('특가 %d개 · 품목 %d · 경보 %d(새 %d · 계속 %d · 바뀜 %d · 해소 %d)%s%s%s' % (
        len(obs['sp']), len(obs['items']), len(state.get('alerts') or {}),
        sum(1 for x in lines if x[0] == '새 경보'), sum(1 for x in lines if x[0] == '계속'), sum(1 for x in lines if x[0] == '바뀜'),
        sum(1 for x in lines if x[0] == '해소'), rechecked, (' · 못 읽음 %s' % ','.join(map(str, obs['errs']))) if obs['errs'] else '',
        ' → 메일' if mail else ''))
    for kind, k, m in lines:
        log('  특가 %s %s' % (kind, m))
        if mail and kind != '해소':
            print('::error title=특가 %s::%s' % (kind, m))
    for x in info:
        log('  특가 기록 %s' % x)
    summ = os.environ.get('GITHUB_STEP_SUMMARY')
    if summ and lines:
        with open(summ, 'a', encoding='utf-8') as f:
            f.write('### 특가 검사 %s\n\n' % stamp + ''.join('- **%s** %s\n' % (kind, m) for kind, k, m in lines))
    return 1 if mail else 0


def main():
    root = arg('--dir', os.path.dirname(os.path.abspath(__file__)))
    synced = sync_latest(root)   # 기록을 읽기 전에
    base = arg('--base', 'https://campingmoon.co.kr').rstrip('/')
    mode = arg('--opts', 'auto')
    opt_hours = {int(x) for x in arg('--opt-hours', '9,12,15,18').split(',') if x.strip()}
    sp, hp, op, lp = (os.path.join(root, 'state', 'snapshot.json'), os.path.join(root, 'state', 'history.json'),
                      os.path.join(root, 'docs', 'restock.json'), os.path.join(root, 'state', 'log.txt'))
    qp, qo = os.path.join(root, 'state', 'soldout.json'), os.path.join(root, 'docs', 'soldout.json')
    fo = os.path.join(root, 'docs', 'shipfee.json')
    t0 = time.time()
    now = datetime.datetime.fromisoformat(arg('--now')) if arg('--now') else datetime.datetime.now(KST)   # --now: 시험용
    now = (now if now.tzinfo else now.replace(tzinfo=KST)).astimezone(KST)
    stamp = now.isoformat(timespec='minutes')
    prev = load(sp, None)
    hist = load(hp, {})

    def log(msg):
        os.makedirs(os.path.dirname(lp), exist_ok=True)
        with open(lp, 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (stamp, msg))
        print(msg)

    kp = os.path.join(root, 'state', 'skip.json')

    def skip(msg):
        """이번 실행을 버린다(결과 · 상태는 그대로). FAIL_ALERT번째로 이어질 때부터만 실패로 끝낸다"""
        k = load(kp, None) or {}
        n = int(k.get('n', 0)) + 1
        save(kp, {'n': n, 'first': k.get('first') or stamp, 'last': stamp, 'why': msg[:200]})
        alert = n >= FAIL_ALERT
        log('%s — 버림 %d번째 연속%s' % (msg, n, ' → 실패로 끝냄(GitHub 메일)' if alert else ''))
        return 1 if alert else 0

    # 1) 상품 단위 상태: 전체상품(152) + 단종(183)
    try:
        cur, sp_ids = crawl(base, 152, 5), set()
        for sc in SPECIAL_CATES:   # 전체상품에 이미 있으면 그대로(같은 상품을 두 번 세지 않는다)
            got = crawl(base, sc)
            sp_ids |= set(got)   # 특가 검사(11/24)가 쓴다
            for no, e in got.items():
                cur.setdefault(no, e)
        ended = crawl(base, 183)
    except Exception as e:
        return skip('목록을 못 읽어 이번 실행은 버림: %s' % e)
    fees = {no: e.pop('f', '') for no, e in cur.items()}   # 배송비 글은 상태 파일에 넣지 않고 shipfee.json으로만 낸다
    prices = {no: (e.pop('pr', 0), e.pop('dc', 0)) for no, e in cur.items()}   # 판매가 · 할인판매가도 상태 파일에 넣지 않고 특가 검사만 쓴다
    for no, e in ended.items():
        cur[no] = {'n': e['n'], 's': '단종'}
    for no in list(cur):
        if no in PAY or '개인결제' in cur[no]['n']:
            del cur[no]
    pprods = {int(k): v for k, v in (prev or {}).get('products', {}).items()}
    live = lambda d: sum(1 for v in d.values() if v['s'] != '단종')
    if pprods and live(cur) < MIN_RATIO * live(pprods):
        return skip('목록이 지난번(%d)보다 너무 적게(%d) 읽혀 이번 실행은 버림' % (live(pprods), live(cur)))

    # 2) 옵션 상태: 지난번 것을 이어받고, 필요한 상품만 상세를 다시 읽는다
    for no, c in cur.items():
        p = pprods.get(no)
        if p and 'o' in p:
            c['o'] = p['o']
    back_whole = [no for no, c in cur.items() if c['s'] == '판매' and pprods.get(no, {}).get('s') == '품절']
    slot = opt_slot(now, opt_hours)
    done_slot = (prev or {}).get('opt_slot')   # 옵션 전체 읽기를 마친 마지막 칸
    full = mode == 'yes' or (mode == 'auto' and slot is not None and slot != done_slot)
    if full:
        targets = [no for no, c in cur.items() if c['s'] == '판매' and (c.get('o') is None or len(c['o']) > 0)]
    elif mode == 'auto':
        targets = list(back_whole)
    else:
        targets = []
    only = arg('--only')   # 시험용: 상세를 읽을 상품을 이 번호들로 좁힌다(예: --only 949,4305)
    if only:
        keep = {int(x) for x in only.split(',') if x.strip()}
        targets = [no for no in targets if no in keep]
    fresh, failed = set(), 0
    for no in targets:
        o = options_of(base, no)
        if o is None:
            failed += 1
        else:
            cur[no]['o'] = o
            fresh.add(no)
        time.sleep(0.3)
    if full and slot and not only and failed <= len(targets) // 10:
        done_slot = slot   # 이 칸은 끝 — 같은 칸의 다음 실행은 다시 다 읽지 않는다(많이 못 읽었으면 다음 실행이 다시 한다)

    # 3) 비교
    events = []
    if prev:
        for no, c in cur.items():
            p = pprods.get(no)
            if not p or c['s'] != '판매':
                continue
            if p['s'] == '품절':
                opts = c.get('o') or {}
                avail = [v[1] for v in opts.values() if v[0]]
                part = avail if 0 < len(avail) < len(opts) else []   # 옵션 일부만 들어왔으면 그 이름을 적는다
                events.append({'p': no, 't': stamp, 'k': 'p', 'o': part, 'n': c['n']})
            elif p['s'] == '판매' and no in fresh and p.get('o') and c.get('o'):
                po, co = p['o'], c['o']
                back = [co[k][1] for k in co if co[k][0] and k in po and not po[k][0]]
                if back:
                    events.append({'p': no, 't': stamp, 'k': 'o', 'o': back, 'n': c['n']})
    for e in events:
        hist[str(e['p'])] = e
    cut = (now - datetime.timedelta(days=KEEP_DAYS)).isoformat(timespec='minutes')
    hist = {k: v for k, v in hist.items() if v['t'] >= cut}

    # 4) 결과: 지금 살 수 있는 재입고만. 옵션 재입고는 그 옵션이 아직 살 수 있을 때만
    items = []
    for k, e in hist.items():
        c = cur.get(int(k))
        if not c or c['s'] != '판매':
            continue
        o = list(e.get('o') or [])
        if c.get('o'):
            still = {v[1] for v in c['o'].values() if v[0]}
            o = [x for x in o if x in still]
            if e['k'] == 'o' and not o:
                continue
        items.append({'p': e['p'], 't': e['t'], 'k': e['k'], 'o': o, 'n': c['n']})
    items.sort(key=lambda x: (x['t'], x['p']), reverse=True)

    # 5) 품절 시각(11/12 사업자 요청 "최근 품절이 먼저 보이게"): 상품 단위로 '판매 → 품절'이 된 때를 적는다
    #    감시 전부터 품절이던 상품은 'before'(날짜 모름). 다시 판매·단종이 되면 지운다. 목록에서 잠깐 빠진 상품의 기록은 그대로 둔다
    sq = load(qp, None)
    if not isinstance(sq, dict) or not isinstance(sq.get('since'), dict):
        sq = {'start': (prev or {}).get('taken') or stamp, 'since': {}}
    since, new_q = sq['since'], 0
    for no, c in cur.items():
        k = str(no)
        if c['s'] != '품절':
            since.pop(k, None)
        elif k not in since:
            p = pprods.get(no)
            if not prev or (p and p['s'] == '품절'):
                since[k] = 'before'   # 첫 실행이거나, 지난번에도 품절인데 기록이 없으면 날짜를 모르는 것으로
            else:
                since[k] = stamp      # 지난번 판매(또는 새로 보인 상품·단종에서 돌아옴) → 이번에 품절
                new_q += 1
    sold_now = [no for no, c in cur.items() if c['s'] == '품절']
    q_items = sorted(({'p': no, 't': since[str(no)]} for no in sold_now if since[str(no)] != 'before'), key=lambda x: (x['t'], x['p']), reverse=True)
    q_before = sorted((no for no in sold_now if since[str(no)] == 'before'), reverse=True)

    save(sp, {'taken': stamp, 'base': base, 'opt_slot': done_slot, 'products': {str(k): v for k, v in sorted(cur.items())}})
    save(hp, hist)
    save(op, {'updated': stamp, 'badge_days': BADGE_DAYS, 'keep_days': KEEP_DAYS, 'items': items})
    save(qp, sq)
    save(qo, {'updated': stamp, 'start': sq['start'], 'items': q_items, 'before': q_before})
    # 6) 배송비 예외(11/13): 가장 흔한 글(몰 기본)과 다른 상품만. 단종 · 개인결제창은 뺀다. 글이 하나도 없으면(항목을 끄면) 빈 목록
    sell = [no for no, c in cur.items() if c['s'] != '단종' and fees.get(no)]
    common = collections.Counter(fees[no] for no in sell).most_common(1)[0][0] if sell else ''
    ship_items = {str(no): fees[no] for no in sorted(sell) if fees[no] != common}
    save(fo, {'updated': stamp, 'common': common, 'items': ship_items})
    skipped = load(kp, None)   # 앞서 버린 실행이 있었으면 지우고 줄에 남긴다
    if skipped is not None:
        os.remove(kp)
    s = sum(1 for v in cur.values() if v['s'] == '판매')
    q = sum(1 for v in cur.values() if v['s'] == '품절')
    d = sum(1 for v in cur.values() if v['s'] == '단종')
    log('%s상품 %d(판매 %d·품절 %d·단종 %d) · 상세 %d/%d%s%s · 새 재입고 %d · 결과 %d · 새 품절 %d(날짜 앎 %d·모름 %d) · 배송비 예외 %d · %.1f분%s%s' % (
        '' if prev else '기준점 · ', len(cur), s, q, d, len(fresh), len(targets), (' (못 읽음 %d)' % failed) if failed else '',
        (' (옵션 전체 %s시 칸)' % slot[-2:]) if full and slot else '', len(events), len(items),
        new_q, len(q_items), len(q_before), len(ship_items), (time.time() - t0) / 60,
        (' · 앞서 버림 %d번 뒤 정상' % int(skipped.get('n', 0))) if skipped else '', (' · 최신 기록 %s에서 시작' % synced) if synced else ''))
    for e in events:
        print('  재입고', e['p'], e['n'][:30], ('옵션: ' + ', '.join(e['o'])) if e['o'] else '')

    # 7) 특가 검사(11/24): 재입고 결과는 위에서 이미 저장했다. 경보가 나면 기록을 먼저 올리고 실패로 끝내 GitHub 메일이 가게 한다
    rc = 0
    slist = {no: {'n': c['n'], 's': c['s'], 'pr': prices.get(no, (0, 0))[0], 'dc': prices.get(no, (0, 0))[1]} for no, c in cur.items()}
    try:
        rc = special_run(root, base, stamp, now, slist, sp_ids - PAY, log)
    except Exception as e:   # 검사 자체를 못 하면 기록만 — FAIL_ALERT번째로 이어질 때부터 메일(조용히 멈추지 않게)
        spp = os.path.join(root, 'state', 'specials.json')
        sst = load(spp, None) or {}
        n = int((sst.get('fail') or {}).get('n', 0)) + 1
        sst['fail'] = {'n': n, 'last': stamp, 'why': str(e)[:200]}
        save(spp, sst)
        rc = 1 if n >= FAIL_ALERT else 0
        log('특가 검사 못 함 %d번째 연속%s: %s' % (n, ' → 메일' if rc else '', str(e)[:200]))
        if rc:
            print('::error title=특가 검사 못 함::%d번 연속 — %s' % (n, str(e)[:200]))
    if rc:
        log('특가 경보로 실패로 끝냄(GitHub 메일)')
        print('기록:', push_now(root, '감시 %s · 특가 경보' % now.strftime('%Y-%m-%d_%H%M')))
    return rc


if __name__ == '__main__':
    sys.exit(main())
