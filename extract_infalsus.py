"""sam 解密部分
用法:
    python extract_infalsus.py [游戏目录] [输出目录]
    --skip-images : 只解密 sam
    --skip-sam    : 只提取 bundle (视频/字体)
"""
import argparse
import json
import os
import re
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join('D:' + os.sep, 'Steam', 'steamapps', 'common', 'In Falsus')
OUT = os.path.join(HERE, 'output')
SAM_XOR_KEY = bytes.fromhex('f016284b7d9ec3a5')
MASK64 = (1 << 64) - 1
C1 = 0x9e3779b97f4a7c15
C2 = 0xd6e8feb86659fd93
C3 = 0xa24baed4963ee407

SAFE_CHARS = set('._+() &!-') | {chr(39)}


def _seg_ok(seg):
    if seg in ('', '.', '..'):
        return False
    if len(seg) > 120:
        return False
    if not (seg[0].isalnum() or seg[0] == '_'):
        return False
    for ch in seg:
        if not (ch.isalnum() or ch in SAFE_CHARS):
            return False
    return True


def safe_out(root, rel):
    root_abs = os.path.abspath(root)
    out = root_abs
    for seg in str(rel).replace(chr(92), '/').split('/'):
        if not _seg_ok(seg):
            raise ValueError('unsafe segment')
        out = os.path.join(out, seg)
    out = os.path.normpath(out)
    if out != root_abs and not out.startswith(root_abs + os.sep):
        raise ValueError('escape')
    return out


def write_out(root, rel, data):
    p = safe_out(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as f:
        f.write(data)
    return p


def sam_xor(data):
    n = len(data)
    rep = (SAM_XOR_KEY * ((n + 7) // 8))[:n]
    return (int.from_bytes(data, 'little') ^ int.from_bytes(rep, 'little')).to_bytes(n, 'little')


def ror(v, n):
    n &= 63
    return ((v >> n) | (v << (64 - n))) & MASK64 if n else v


def mix(x):
    t = (ror(x, 0x2F) ^ x) * C3 & MASK64
    return ror(t, 0x17) ^ t


def inv_xor_ror(y, shift):
    sols = []
    for init in (0, 1):
        bits = [None] * 64
        bits[0] = init
        ch = True
        while ch:
            ch = False
            for i in range(64):
                j = (i + shift) % 64
                if bits[i] is not None and bits[j] is None:
                    bits[j] = bits[i] ^ ((y >> i) & 1)
                    ch = True
                elif bits[j] is not None and bits[i] is None:
                    bits[i] = bits[j] ^ ((y >> i) & 1)
                    ch = True
        if None in bits:
            continue
        out = sum(b << i for i, b in enumerate(bits) if b)
        if out ^ ror(out, shift) == y and out not in sols:
            sols.append(out)
    return sols


def inv_mix(y):
    outs = []
    ci = pow(C3, -1, 1 << 64)
    for t in inv_xor_ror(y, 23):
        u = (t * ci) & MASK64
        for x in inv_xor_ror(u, 47):
            if mix(x) == y and x not in outs:
                outs.append(x)
    return outs


def fmod_transform(buf, base, rbp):
    n = len(buf)
    view = memoryview(buf)
    pos = 0
    while pos < n:
        ecx = (base + pos) & 0xFFFFFFFF
        block = ((ecx & MASK64) >> 3) * C2 & MASK64
        edi = ecx & 7
        ks = mix((block + rbp) & MASK64)
        run = min(8 - edi, n - pos)
        if edi == 0 and run == 8:
            off = pos
            grp = int.from_bytes(view[off:off + 8], 'little')
            grp ^= ks
            view[off:off + 8] = grp.to_bytes(8, 'little')
        else:
            for j in range(run):
                buf[pos + j] ^= (ks >> (((j + edi) * 8) & 63)) & 0xFF
        pos += run


def recover_rbp(after):
    pt0 = bytes.fromhex('4f67675300020000')
    ks0 = bytes(a ^ b for a, b in zip(after[:8], pt0))
    good = []
    for rbp in inv_mix(int.from_bytes(ks0, 'little')):
        ks1 = mix((C2 + rbp) & MASK64)
        if all((after[8 + k] ^ ((ks1 >> (8 * k)) & 0xFF)) == 0 for k in range(6)):
            good.append(rbp)
    return good


def parse_spc(d):
    if d[:4] != b'ICP1':
        return None
    ver, hdr, ra, rb, note, u2 = struct.unpack_from('<HHHHII', d, 4)
    bpm, meter = struct.unpack_from('<ff', d, 20)
    return {'format': 'ICP1', 'version': ver, 'headerSize': hdr,
            'recordSizeA': ra, 'recordSizeB': rb, 'noteCount': note,
            'u2': u2, 'bpm': bpm, 'meter': meter}


MP3_SYG = (bytes([0xff, 0xfb]), bytes([0xff, 0xf3]), bytes([0xff, 0xf2]), bytes([0xff, 0xe3]))
GZ_SIG = bytes([0x1f, 0x8b])


def classify(after):
    if after[:4] == b'ICP1':
        return 'chart'
    if after[:4] == b'OggS':
        return 'audio-plain'
    w = after[:256]
    tx = sum(1 for b in w if 32 <= b < 127 or b in (9, 10, 13))
    if len(after) >= 256 and tx >= 250 or (0 < len(after) < 256 and tx >= len(after) - 4):
        return 'script'
    return 'maybe-audio'


def process_sam(job):
    guid, sam_path, rel, out_root = job
    with open(sam_path, 'rb') as f:
        raw = f.read()
    after = sam_xor(raw)
    kind = classify(after)
    base = os.path.splitext(rel)[0].replace(chr(92), '/')
    if kind == 'chart':
        write_out(out_root, 'charts/' + base + '.spc', after)
        info = parse_spc(after)
        p = safe_out(out_root, 'charts/' + base + '.summary.json')
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False, indent=1)
        return (guid, rel, 'chart', 'charts/' + base + '.spc')
    if kind == 'script':
        write_out(out_root, 'scripts/' + rel, after)
        return (guid, rel, 'script', 'scripts/' + rel)
    if kind == 'audio-plain':
        write_out(out_root, 'audio/' + base + '.ogg', after)
        return (guid, rel, 'audio', 'audio/' + base + '.ogg')
    rbps = recover_rbp(after)
    if rbps:
        buf = bytearray(after)
        fmod_transform(buf, 0, rbps[0])
        write_out(out_root, 'audio/' + base + '.ogg', buf)
        return (guid, rel, 'audio', 'audio/' + base + '.ogg')
    if after[:3] == b'ID3' or after[:2] in MP3_SYG:
        write_out(out_root, 'audio/' + base + '.mp3', after)
        return (guid, rel, 'audio-mp3', 'audio/' + base + '.mp3')
    if after[:2] == GZ_SIG:
        import gzip
        try:
            inner = gzip.decompress(after)
        except OSError:
            inner = None
        if inner is not None:
            ext = '.json' if inner[:1] in (b'{', b'[') else '.bin'
            write_out(out_root, 'misc/' + base + ext, inner)
            return (guid, rel, 'gzip', 'misc/' + base + ext)
    write_out(out_root, 'misc/' + rel + '.dec', after)
    return (guid, rel, 'unknown', 'misc/' + rel + '.dec')


def _seg_filter(name, fallback):
    segs = [s for s in str(name).replace(chr(92), '/').split('/') if _seg_ok(s)]
    return '/'.join(segs) if segs else fallback


def _font_bytes(data):
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, list):
        try:
            return bytes(data)
        except ValueError:
            return b''
    return b''


def _font_ext(data):
    if data[:4] == b'OTTO':
        return '.otf'
    if data[:4] in (b'\x00\x01\x00\x00', b'true', b'ttcf'):
        return '.ttf'
    return '.bin'


def write_font(out_root, path_id, name, data, ext=None):
    if not data:
        return False
    raw_name = name or ('font_' + str(path_id))
    safe_name = raw_name if _seg_ok(raw_name) else ('font_' + str(path_id))
    write_out(out_root, 'fonts/' + safe_name + (ext or _font_ext(data)), data)
    return True


def extract_assets_fonts(ddir, out_root, bstats):
    """从游戏 Data 目录的 *.assets 里导出 Font 资源"""
    import UnityPy
    if not os.path.isdir(ddir):
        return
    for fn in sorted(os.listdir(ddir)):
        if not fn.endswith('.assets'):
            continue
        try:
            aenv = UnityPy.load(os.path.join(ddir, fn))
        except Exception:
            bstats['errors'] += 1
            continue
        for obj in aenv.objects:
            if obj.type.name != 'Font':
                continue
            try:
                d = obj.read()
                if write_font(out_root, obj.path_id, getattr(d, 'm_Name', ''),
                              _font_bytes(getattr(d, 'm_FontData', None))):
                    bstats['Font'] += 1
            except Exception:
                bstats['errors'] += 1


def extract_bundle_fonts(benv, out_root, bstats, seen, min_size=8000):
    """导出 bundle 内的字体"""
    for obj in benv.objects:
        if obj.type.name != 'MonoBehaviour':
            continue
        if getattr(obj, 'byte_size', 0) < min_size:
            continue
        try:
            tt = obj.read_typetree()
        except Exception:
            continue
        raw = tt.get('RawBytes')
        if not raw:
            continue
        ident = str(tt.get('Identifier') or tt.get('m_Name') or ('font_' + str(obj.path_id)))
        if ident in seen:
            continue
        seen.add(ident)
        if write_font(out_root, obj.path_id, ident, _font_bytes(raw)):
            bstats['Font'] += 1


def extract_bundles(BDIR, OUT, DDIR=None):
    import UnityPy
    bundles = sorted(f for f in os.listdir(BDIR) if f.endswith('.bundle'))
    print('[bundles] %d bundles' % len(bundles), flush=True)
    bstats = {'VideoClip': 0, 'Font': 0, 'errors': 0}
    extract_assets_fonts(DDIR, OUT, bstats)
    seen_fonts = set()
    t0 = time.time()
    for bi, bname in enumerate(bundles, 1):
        try:
            benv = UnityPy.load(os.path.join(BDIR, bname))
        except Exception:
            bstats['errors'] += 1
            continue
        cont = {}
        for cpath, cobj in getattr(benv, 'container', {}).items():
            cont[cobj.path_id] = cpath
        res_data = {}
        try:
            bfile = list(benv.files.values())[0]
            for fn, fnode in getattr(bfile, 'files', {}).items():
                if fn.endswith('.resource'):
                    fnode.Position = 0
                    res_data[fn] = fnode.read_bytes(fnode.Length)
        except Exception:
            pass
        extract_bundle_fonts(benv, OUT, bstats, seen_fonts)
        for obj in benv.objects:
            try:
                t = obj.type.name
                if t == 'VideoClip':
                    d = obj.read()
                    raw_name = getattr(d, 'm_Name', '') or ('video_' + str(obj.path_id))
                    safe_name = raw_name if _seg_ok(raw_name) else ('video_' + str(obj.path_id))
                    er = d.m_ExternalResources
                    src = str(er.m_Source)
                    m = re.search(r'([^/]+)[.]resource$', src)
                    blob = None
                    rkey = (m.group(1) + '.resource') if m else None
                    if rkey and rkey in res_data:
                        blob = res_data[rkey][er.m_Offset:er.m_Offset + er.m_Size]
                    elif res_data:
                        for v in res_data.values():
                            if len(v) >= er.m_Size:
                                blob = v[er.m_Offset:er.m_Offset + er.m_Size]
                                break
                    ext = '.webm' if str(getattr(d, 'm_OriginalPath', '')).lower().endswith('.webm') else '.mp4'
                    if blob:
                        write_out(OUT, 'videos/' + safe_name + ext, blob)
                        bstats['VideoClip'] += 1
                    else:
                        bstats['errors'] += 1
                elif t == 'Font':
                    d = obj.read()
                    if write_font(OUT, obj.path_id,
                                  cont.get(obj.path_id) or getattr(d, 'm_Name', ''),
                                  _font_bytes(getattr(d, 'm_FontData', None))):
                        bstats['Font'] += 1
            except Exception:
                bstats['errors'] += 1
        if bi % 200 == 0 or bi == len(bundles):
            print('[bundles] %d/%d %s (%.0fs)' % (bi, len(bundles), bstats, time.time() - t0), flush=True)
    return bstats


def load_streaming_mapping(BDIR, pid_hint=None):
    """定位 StreamingAssetsMapping 并返回其 Entries"""
    import UnityPy
    bundles = sorted(f for f in os.listdir(BDIR) if f.endswith('.bundle'))
    if pid_hint is not None:
        for bname in bundles:
            try:
                env = UnityPy.load(os.path.join(BDIR, bname))
            except Exception:
                continue
            for obj in env.objects:
                if obj.type.name != 'MonoBehaviour' or obj.path_id != pid_hint:
                    continue
                try:
                    tt = obj.read_typetree()
                except Exception:
                    continue
                if 'Entries' in tt:
                    print('[mapping] %s (path_id=%d)' % (bname, obj.path_id), flush=True)
                    return tt['Entries']
    for bname in bundles:
        try:
            env = UnityPy.load(os.path.join(BDIR, bname))
        except Exception:
            continue
        for obj in env.objects:
            if obj.type.name != 'MonoBehaviour':
                continue
            try:
                tt = obj.read_typetree()
            except Exception:
                continue
            if tt.get('m_Name') == 'StreamingAssetsMapping' and 'Entries' in tt:
                print('[mapping] %s (按名称匹配, path_id=%d)' % (bname, obj.path_id), flush=True)
                return tt['Entries']
    return None


def main():
    global GAME, OUT
    ap = argparse.ArgumentParser(description='sam 解密 + 视频/字体')
    ap.add_argument('game_dir', nargs='?', default=GAME)
    ap.add_argument('out_dir', nargs='?', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output'))
    ap.add_argument('--skip-images', action='store_true', help='只解密 sam, 跳过 bundle')
    ap.add_argument('--skip-sam', action='store_true', help='只提取 bundle, 跳过 sam')
    args = ap.parse_args()
    GAME = args.game_dir
    OUT = args.out_dir
    os.makedirs(OUT, exist_ok=True)
    print('游戏目录: ' + GAME)
    print('输出目录: ' + OUT)
    t0 = time.time()
    MAPPING_PID = -1885377428196858104
    BDIR = os.path.join(GAME, 'infalsus_Data', 'StreamingAssets', 'aa', 'StandaloneWindows64')
    DDIR = os.path.join(GAME, 'infalsus_Data')
    if not os.path.isdir(BDIR):
        raise SystemExit('[bundle] 目录不存在: %s\n  请用第 1 个参数指定正确的游戏目录。' % BDIR)

    if args.skip_sam:
        print('[sam] --skip-sam, 跳过 sam 解密', flush=True)
    else:
        mapping = load_streaming_mapping(BDIR, MAPPING_PID)
        if not mapping:
            raise SystemExit('[mapping] 未找到 StreamingAssetsMapping, 无法定位 sam 文件。'
                             ' 游戏可能已更新, 请检查 %s' % BDIR)
        print('[mapping]', len(mapping), 'entries  %.1fs' % (time.time() - t0), flush=True)

        sam_dir = os.path.join(GAME, 'infalsus_Data', 'StreamingAssets', 'sam')
        jobs = [(e['Guid'], os.path.join(sam_dir, e['Guid']), e['FullLookupPath'], OUT)
                for e in mapping if os.path.isfile(os.path.join(sam_dir, e['Guid']))]
        print('[sam]', len(jobs), 'files', flush=True)
        stats = {}
        lock = threading.Lock()
        counter = [0]

        def run_job(job):
            res = process_sam(job)
            with lock:
                counter[0] += 1
                stats[res[2]] = stats.get(res[2], 0) + 1
                c = counter[0]
                if c % 1000 == 0 or c == len(jobs):
                    print('[sam] %d/%d %s (%.0fs)' % (c, len(jobs), dict(stats), time.time() - t0), flush=True)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(run_job, jobs))
        print('[sam] DONE', dict(stats), flush=True)

    if args.skip_images:
        print('[bundles] --skip-images, 跳过 bundle 提取', flush=True)
    else:
        bstats = extract_bundles(BDIR, OUT, DDIR)
        print('[bundles] DONE', bstats, flush=True)

    print('')
    print('=== 提取完成 (%.0fs) ===' % (time.time() - t0))
    for sub in ('audio', 'charts', 'scripts', 'videos', 'misc', 'fonts'):
        d = os.path.join(OUT, sub)
        if os.path.isdir(d):
            n = sum(len(fs) for _, _, fs in os.walk(d))
            print('  %s: %d files' % (sub, n))


if __name__ == '__main__':
    main()
