"""贴图/立绘导出"""
import argparse
import os
import time

import UnityPy

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join('D:' + os.sep, 'Steam', 'steamapps', 'common', 'In Falsus')
BDIR = os.path.join(GAME, 'infalsus_Data', 'StreamingAssets', 'aa', 'StandaloneWindows64')
OUT_IMAGES = os.path.join(HERE, 'output', 'images')
OUT_SPRITES = os.path.join(HERE, 'output', 'sprites')

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


def _asset_dir_name(container_path):
    parts = [p for p in str(container_path).replace(chr(92), '/').split('/') if _seg_ok(p)]
    if parts and parts[0] == 'Assets':
        parts = parts[1:]
    if len(parts) >= 3 and parts[0] == 'BuildSpecificAssets':
        parts = parts[2:]
    if not parts:
        return None
    stem = parts[:-1] if len(parts) > 1 else []
    name = os.path.splitext(parts[-1])[0]
    return '/'.join(stem + [name])


def export_bundles():
    bundles = sorted(f for f in os.listdir(BDIR) if f.endswith('.bundle'))
    print('[images] bundles:', len(bundles), flush=True)
    stats = {'Texture2D': 0, 'Sprite': 0, 'skipped': 0}
    t0 = time.time()
    used = set()

    def dedup(rel):
        if rel not in used:
            used.add(rel)
            return rel
        stem, ext = os.path.splitext(rel)
        i = 2
        while True:
            cand = stem + '~' + str(i) + ext
            if cand not in used:
                used.add(cand)
                return cand
            i += 1

    for bi, bname in enumerate(bundles, 1):
        try:
            env = UnityPy.load(os.path.join(BDIR, bname))
        except Exception:
            stats['skipped'] += 1
            continue
        cont = {}
        for cpath, cobj in env.container.items():
            cont[cobj.path_id] = str(cpath)
        for obj in env.objects:
            try:
                t = obj.type.name
                if t == 'Texture2D':
                    d = obj.read()
                    cp = cont.get(obj.path_id)
                    rel_dir = _asset_dir_name(cp) if cp and cp.startswith('Assets/') else None
                    nm = getattr(d, 'm_Name', '') or ('tex_' + str(obj.path_id))
                    if rel_dir and rel_dir != nm:
                        rel = 'textures/' + rel_dir + '.png'
                    else:
                        rel = 'textures/' + (nm if _seg_ok(nm) else 'tex_' + str(obj.path_id)) + '.png'
                    rel = dedup(rel)
                    p = safe_out(OUT_IMAGES, rel)
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    d.image.save(p)
                    stats['Texture2D'] += 1
                elif t == 'Sprite':
                    d = obj.read()
                    nm = getattr(d, 'm_Name', '') or ('sprite_' + str(obj.path_id))
                    cp = cont.get(obj.path_id)
                    rel_dir = _asset_dir_name(cp) if cp and cp.startswith('Assets/') else None
                    if rel_dir and rel_dir != nm:
                        rel = rel_dir + '.png'
                    else:
                        rel = (nm if _seg_ok(nm) else 'sprite_' + str(obj.path_id)) + '.png'
                    rel = dedup(rel)
                    p = safe_out(OUT_SPRITES, rel)
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    d.image.save(p)
                    stats['Sprite'] += 1
            except Exception:
                stats['skipped'] += 1
        if bi % 400 == 0 or bi == len(bundles):
            print('[images] %d/%d %s (%.0fs)' % (bi, len(bundles), stats, time.time() - t0), flush=True)
    print('[images] DONE', stats, flush=True)


def main():
    global GAME, BDIR, OUT_IMAGES, OUT_SPRITES
    ap = argparse.ArgumentParser(description='In Falsus 贴图/立绘导出')
    ap.add_argument('game_dir', nargs='?', default=GAME)
    ap.add_argument('out_dir', nargs='?', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output'))
    args = ap.parse_args()
    GAME = args.game_dir
    BDIR = os.path.join(GAME, 'infalsus_Data', 'StreamingAssets', 'aa', 'StandaloneWindows64')
    out_root = os.path.abspath(args.out_dir)
    OUT_IMAGES = os.path.join(out_root, 'images')
    OUT_SPRITES = os.path.join(out_root, 'sprites')
    os.makedirs(OUT_IMAGES, exist_ok=True)
    os.makedirs(OUT_SPRITES, exist_ok=True)
    print('游戏目录: ' + GAME)
    print('输出目录: ' + out_root)
    export_bundles()


if __name__ == '__main__':
    main()
