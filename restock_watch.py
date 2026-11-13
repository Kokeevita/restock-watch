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

재입고로 치는 것: 지난번 품절 → 이번 판매(상품 단위), 지난번 살 수 없던 옵션 → 이번 살 수 있음(옵션 단위)
치지 않는 것: 새 상품, 단종, 숨김→보임, 소량→넉넉. 다시 품절이 되면 결과에서 빠진다.
읽기만 한다(로그인·저장·장바구니 없음).
"""
import collections
import datetime
import html
import json
import os
import re
import sys
import time
import urllib.request

KST = datetime.timezone(datetime.timedelta(hours=9))
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
KEEP_DAYS, BADGE_DAYS = 30, 14
SPECIAL_CATES = [200]   # 특가 분류 번호(카페24에 만든 뒤 넣는다, 11/13). 특가 분류에만 넣고 전체상품(152)에 빠뜨린 상품도 품절·재입고를 감시한다
PAY = {4087, 4225, 4247, 4453, 4454, 4470}   # 개인결제창
MIN_RATIO = 0.9                               # 목록이 지난번의 90%보다 적게 읽히면 이번 실행은 버린다


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


def parse_feed(page):
    out = {}
    for m in CARD.finditer(page):
        no, c = int(m.group(1)), m.group(2)
        nm = re.search(r'class="nm"[^>]*>(.*?)</a>', c, re.S)
        name = html.unescape(re.sub(r'<[^>]+>', '', nm.group(1))).strip() if nm else ''
        sold = bool(re.search(r'class="soldsrc">\s*<img', c))
        # 목록 표시 항목 '배송비'(카페24 상품정보 표시설정에서 켬, 11/13). 숨은 칸(displaynone)은 보지 않는다
        fee = next((plain(v) for cls, k, v in ITEM.findall(c) if 'displaynone' not in cls and plain(k).rstrip(' :') == '배송비'), '')
        out[no] = {'n': name, 's': '품절' if sold else '판매', 'f': fee}
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


def main():
    root = arg('--dir', os.path.dirname(os.path.abspath(__file__)))
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

    # 1) 상품 단위 상태: 전체상품(152) + 단종(183)
    try:
        cur = crawl(base, 152, 5)
        for sc in SPECIAL_CATES:   # 전체상품에 이미 있으면 그대로(같은 상품을 두 번 세지 않는다)
            for no, e in crawl(base, sc).items():
                cur.setdefault(no, e)
        ended = crawl(base, 183)
    except Exception as e:
        log('목록을 못 읽어 이번 실행은 버림: %s' % e)
        return 1
    fees = {no: e.pop('f', '') for no, e in cur.items()}   # 배송비 글은 상태 파일에 넣지 않고 shipfee.json으로만 낸다
    for no, e in ended.items():
        cur[no] = {'n': e['n'], 's': '단종'}
    for no in list(cur):
        if no in PAY or '개인결제' in cur[no]['n']:
            del cur[no]
    pprods = {int(k): v for k, v in (prev or {}).get('products', {}).items()}
    live = lambda d: sum(1 for v in d.values() if v['s'] != '단종')
    if pprods and live(cur) < MIN_RATIO * live(pprods):
        log('목록이 지난번(%d)보다 너무 적게(%d) 읽혀 이번 실행은 버림' % (live(pprods), live(cur)))
        return 1

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
    s = sum(1 for v in cur.values() if v['s'] == '판매')
    q = sum(1 for v in cur.values() if v['s'] == '품절')
    d = sum(1 for v in cur.values() if v['s'] == '단종')
    log('%s상품 %d(판매 %d·품절 %d·단종 %d) · 상세 %d/%d%s%s · 새 재입고 %d · 결과 %d · 새 품절 %d(날짜 앎 %d·모름 %d) · 배송비 예외 %d · %.1f분' % (
        '' if prev else '기준점 · ', len(cur), s, q, d, len(fresh), len(targets), (' (못 읽음 %d)' % failed) if failed else '',
        (' (옵션 전체 %s시 칸)' % slot[-2:]) if full and slot else '', len(events), len(items),
        new_q, len(q_items), len(q_before), len(ship_items), (time.time() - t0) / 60))
    for e in events:
        print('  재입고', e['p'], e['n'][:30], ('옵션: ' + ', '.join(e['o'])) if e['o'] else '')
    return 0


if __name__ == '__main__':
    sys.exit(main())
