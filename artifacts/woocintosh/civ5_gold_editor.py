#!/usr/bin/env python3
"""Civ5 세이브 골드 에디터 (Mac/Windows/Linux, 표준 라이브러리만 사용)

사용법:
    python3 civ5_gold_editor.py <세이브파일> --set <목표골드> --capital <수도이름> [--current <현재골드>]

예시 (파일명만 쓰면 세이브 폴더에서 자동으로 찾음, 확장자 생략 가능):
    python3 civ5_gold_editor.py A0 --set 500000 --capital Vienna
    python3 civ5_gold_editor.py 0011 --set 100000 --capital Madrid --current 168

--current는 선택사항. 주면 값 검증을 한 겹 더 하므로 더 안전하다.
실행 결과에 '감지된 현재 골드'가 출력되니 게임 표시값과 맞는지 확인할 것.

원리:
  - .Civ5Save 본문은 64KB 청크(4바이트 길이 프리픽스)로 나뉜 zlib 스트림.
  - 골드는 (골드 x 100) 정수로 저장되며, 화면에는 소수점이 잘려 표시됨.
    예: 화면에 168 -> 실제 저장값은 16800~16899 중 하나.
  - 같은 값이 두 벌(본값 + 동기화 사본) 가까운 거리에 저장되므로,
    범위 내에서 '가까운 거리의 동일 값 쌍'을 찾아 둘 다 패치한다.
  - 원본은 절대 덮어쓰지 않고 새 파일로 저장.
"""
import argparse
import os
import struct
import sys
import zlib

CHUNK = 65536

# 세이브 폴더: 파일명만 입력하면 여기서 순서대로 찾는다
SAVE_DIRS = [
    os.path.expanduser('~/Library/Containers/com.aspyr.civ5campaign/Data/Library/'
                       'Application Support/Civilization V Campaign Edition/Saves/single'),
    os.path.expanduser("~/Documents/Aspyr/Sid Meier's Civilization 5/Saves/single"),
]


def resolve_save_path(name: str) -> str:
    """파일명만 줘도 세이브 폴더에서 찾아준다. 확장자 생략도 허용."""
    candidates = [name]
    if not name.lower().endswith('.civ5save'):
        candidates.append(name + '.Civ5Save')
    for c in candidates:
        if os.path.exists(c):
            return c
        if not os.path.dirname(c):
            for d in SAVE_DIRS:
                p = os.path.join(d, c)
                if os.path.exists(p):
                    return p
    sys.exit(f'오류: 세이브 파일을 찾지 못했습니다: {name}\n'
             '찾아본 폴더:\n' + '\n'.join(f'  {d}' for d in SAVE_DIRS))


def find_body_start(raw: bytes) -> int:
    """청크 체인이 EOF까지 정확히 이어지는 시작점을 찾는다."""
    sig = struct.pack('<I', CHUNK) + b'\x78\x9c'
    idx = raw.find(sig)
    candidates = []
    if idx != -1:
        candidates.append(idx)
    # 작은 세이브(첫 청크 < 64KB) 대비: 78 9c 앞 4바이트를 길이로 가정해 본다
    j = raw.find(b'\x78\x9c')
    while j != -1:
        if j >= 4:
            candidates.append(j - 4)
        j = raw.find(b'\x78\x9c', j + 1)
        if j > 200000:
            break
    for start in candidates:
        pos = start
        while pos < len(raw):
            if pos + 4 > len(raw):
                break
            n = struct.unpack_from('<I', raw, pos)[0]
            if n == 0 or n > CHUNK:
                break
            pos += 4 + n
        if pos == len(raw):
            return start
    raise SystemExit('오류: 압축 청크 구조를 찾지 못했습니다. 일반 .Civ5Save 파일이 맞나요?')


def unpack_body(raw: bytes, start: int) -> bytes:
    payload = bytearray()
    pos = start
    while pos < len(raw):
        n = struct.unpack_from('<I', raw, pos)[0]
        payload += raw[pos + 4:pos + 4 + n]
        pos += 4 + n
    d = zlib.decompressobj()
    return d.decompress(bytes(payload))


def pack_body(header: bytes, body: bytes) -> bytes:
    co = zlib.compressobj(6)
    stream = co.compress(body) + co.flush(zlib.Z_SYNC_FLUSH)  # 게임과 동일: 종료 블록 없음
    out = bytearray(header)
    for i in range(0, len(stream), CHUNK):
        c = stream[i:i + CHUNK]
        out += struct.pack('<I', len(c)) + c
    return bytes(out)


def find_gold_offsets_v2(body: bytes, gold=None, capital: str = None):
    """국고 서명 [int32: 0, 1, 골드x100] 으로 정확히 탐지.

    검증된 사실 (BNW 세이브와 Campaign Edition 세이브 차분 분석으로 확인):
      - 국고는 단 한 곳에 (골드 x 100) int32로 저장된다.
      - 바로 앞에 항상 int32 [0, 1]이 온다.
      - 플레이어 국고는 수도 이름 문자열(도시 오브젝트) 뒤 500KB 안에 있고,
        그 윈도우에서 '1골드(=100) 이상인 첫 서명'이 국고다 (3개 세이브에서 검증).

    gold(현재 골드)가 주어지면 값 범위까지 검증해 더 안전하다.
    """
    pre = struct.pack('<ii', 0, 1)

    win_start, win_end = 0, len(body)
    if capital:
        needle = capital.encode('utf-8')
        a = body.find(needle, 1_000_000)
        if a == -1:
            a = body.find(needle)
        if a == -1:
            sys.exit(f'오류: 본문에서 수도 이름 "{capital}"을 찾지 못했습니다. 철자를 확인하세요.')
        win_start, win_end = a, a + 500_000
        print(f'수도 "{capital}" @{a}')

    if gold is not None:
        lo, hi = gold * 100, gold * 100 + 99
    else:
        lo, hi = 100, 2_000_000_000   # 1골드 이상이면 국고로 본다

    cands = []
    i = body.find(pre, win_start)
    while i != -1 and i < win_end:
        v = struct.unpack_from('<i', body, i + 8)[0]
        if lo <= v <= hi:
            cands.append((i + 8, v))
            if gold is None:
                break  # 윈도우 내 첫 서명 = 국고
        i = body.find(pre, i + 1)
    return cands


def _legacy_find_gold_offsets(body: bytes, gold: int, capital: str = None):
    """표시 골드(소수점 버림) -> 저장값 후보(x100, +0~99센트)의 '근접 동일값 쌍'을 점수로 랭킹.

    실제 국고는 (본값 + 동기화 사본) 두 벌이 일정 간격(저장 버전마다 다름, 예: 336/448)으로
    저장된다. 같은 세이브 안에서 다른 문명들의 국고 쌍도 같은 간격을 가지므로,
    파일 전체에서 가장 흔한 쌍 간격(모달 간격)이 진짜 국고의 간격이다.

    --capital(수도 이름)이 주어지면 수도 문자열이 있는 플레이어 블록 뒤 500KB로
    탐색을 좁혀, AI 문명의 국고를 잘못 짚는 것을 방지한다.
    """
    lo, hi = gold * 100, gold * 100 + 99
    hits = {}  # value -> [offsets]
    for shift in range(4):
        end = shift + ((len(body) - shift) // 4) * 4
        mv = memoryview(body)[shift:end]
        for i, v in enumerate(struct.iter_unpack('<i', mv)):
            if lo <= v[0] <= hi:
                hits.setdefault(v[0], []).append(shift + i * 4)

    # 모든 근접 동일값 쌍 수집 (파일 전체)
    all_pairs = []
    for val, offs in hits.items():
        offs.sort()
        for a, b in zip(offs, offs[1:]):
            if 16 <= b - a <= 4096:
                all_pairs.append((val, a, b))

    # 모달 간격: 다른 문명들의 국고 쌍이 투표해 준다.
    # 단, 투표권은 희소값(전체 2~4회 등장)에만 — 진짜 국고 값은 희소하고,
    # 수백 번 반복되는 노이즈 상수(예: 16896)가 투표를 오염시키면 안 된다.
    from collections import Counter
    gap_votes = Counter(b - a for val, a, b in all_pairs if len(hits[val]) <= 4)
    modal_gap, modal_n = (gap_votes.most_common(1)[0] if gap_votes else (None, 0))

    # 수도 앵커: 본문 1MB 이후 첫 등장 위치(도시 오브젝트) 뒤 500KB 윈도우
    window = None
    if capital:
        needle = capital.encode('utf-8')
        i = body.find(needle, 1_000_000)
        if i == -1:
            i = body.find(needle)
        if i == -1:
            sys.exit(f'오류: 본문에서 수도 이름 "{capital}"을 찾지 못했습니다. 철자를 확인하세요.')
        window = (i, i + 500_000)
        print(f'수도 "{capital}" 위치: {i} -> 탐색 윈도우 {window}')

    def neighbors_small(off):
        s = 0
        for d in (-4, 4):
            v = struct.unpack_from('<i', body, off + d)[0]
            if abs(v) < 1_000_000:
                s += 1
        return s

    scored = []
    for val, a, b in all_pairs:
        if window and not (window[0] <= a <= window[1]):
            continue
        if not window and len(hits[val]) > 4:
            continue  # 윈도우 없이는 흔한 값 = 노이즈 상수로 간주
        gap = b - a
        score = neighbors_small(a) + neighbors_small(b)   # 0~4
        score += 1 if 128 <= gap <= 1024 else 0           # 전형적 간격 가산점
        if modal_n >= 3 and gap == modal_gap:
            score += 10                                   # 다른 문명 국고들과 같은 간격
        if len(hits[val]) > 50:
            score -= 5                                    # 초고빈도 노이즈 상수 감점
        scored.append((score, val, a, b))
    scored.sort(key=lambda t: -t[0])
    return scored


def main():
    ap = argparse.ArgumentParser(description='Civ5 세이브 골드 에디터')
    ap.add_argument('savefile')
    ap.add_argument('--current', type=int, help='(선택) 현재 골드 — 주면 값 검증까지 해서 더 안전')
    ap.add_argument('--set', dest='target', type=int, required=True, help='바꿀 골드 (최대 2000만)')
    ap.add_argument('--capital', required=True, help='내 수도(첫 도시) 이름 (예: Vienna)')
    ap.add_argument('-o', '--output', help='출력 파일명 (기본: 원본명_gold<목표>.Civ5Save)')
    args = ap.parse_args()

    if not (0 <= args.target <= 20_000_000):
        sys.exit('오류: 목표 골드는 0~20,000,000 사이여야 합니다 (x100 저장이라 int32 한계).')

    args.savefile = resolve_save_path(args.savefile)
    print(f'세이브 파일: {args.savefile}')
    raw = open(args.savefile, 'rb').read()
    if raw[:4] != b'CIV5':
        sys.exit('오류: CIV5 세이브 파일이 아닙니다.')

    start = find_body_start(raw)
    header, body = raw[:start], bytearray(unpack_body(raw, start))
    print(f'본문 해제: {len(body):,} bytes (청크 시작 오프셋 {start})')

    # 자가 검증: 무수정 재압축이 원본과 동일해야 같은 게임 버전
    if pack_body(header, bytes(body)) != raw:
        print('경고: 재압축 결과가 원본과 다릅니다. 게임 버전에 따라 실패할 수 있으니')
        print('      반드시 원본을 백업해 두고 결과물을 테스트하세요.')

    cands = find_gold_offsets_v2(bytes(body), args.current, args.capital)
    if not cands:
        sys.exit('오류: 국고 서명을 찾지 못했습니다. --capital 철자(게임 내 표기 그대로)와 '
                 '--current 값(세이브 당시 골드)을 확인하세요.')
    if len(cands) > 1:
        print(f'주의: 후보 {len(cands)}개 (같은 골드의 AI 문명일 수 있음). 수도에서 가장 가까운 첫 번째 사용:')
        for o, v in cands:
            print(f'  @ {o}: {v} ({v/100:.2f}골드)')

    a, val = cands[0]
    if args.current is None:
        print(f'감지된 현재 골드: {val/100:.2f} — 게임에 표시되던 골드와 다르면 중단하고 '
              f'--current <골드>를 붙여 다시 실행하세요.')
    new_val = args.target * 100
    struct.pack_into('<i', body, a, new_val)
    print(f'패치: {val} ({val/100:.2f}골드) -> {new_val} ({args.target}골드)  @ 오프셋 {a}')

    out_name = args.output or args.savefile.rsplit('.', 1)[0] + f'_gold{args.target}.Civ5Save'
    out = pack_body(header, bytes(body))

    # 최종 검증: 결과물을 다시 풀어 패치 외 동일성 확인
    body2 = unpack_body(out, start)
    assert struct.unpack_from('<i', body2, a)[0] == new_val
    orig_body = unpack_body(raw, start)
    diff = [i for i in range(len(orig_body)) if orig_body[i] != body2[i]]
    if not all(a <= i < a + 4 for i in diff):
        sys.exit('오류: 의도하지 않은 바이트 변경이 감지되어 저장을 중단했습니다.')

    open(out_name, 'wb').write(out)
    print(f'완료: {out_name} (패치 외 모든 데이터 원본과 동일함을 검증)')


if __name__ == '__main__':
    main()
