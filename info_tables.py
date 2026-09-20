import os
import sys
import time
from pathlib import Path

import UnityPy

import json_compact

DEFAULT_GAME = os.path.join('D:' + os.sep, 'Steam', 'steamapps', 'common', 'In Falsus')
OUT = '.'
DIFFICULTY_NAMES = {0: 'Normal', 1: 'Hard', 2: 'Expert', 4: 'Extreme', 8: 'Special'}

SONGDATA_TABLE = 'SongData'
GAMEDATA_TABLE = 'GameData'
GAMESKILL_TABLE = 'GameSkillIconMapping'

EXTRA_TABLES = [
    ('DynamicStringMapping', 'dynamic_string_mapping.json'),
    ('PackData', 'pack_data.json'),
    ('RewardData', 'reward_data.json'),
    ('CardArtMapping', 'card_art_mapping.json'),
    ('CharacterUniversalIconMapping', 'character_icon_mapping.json'),
]

COMPACT_TABLES = {'game_data.json', 'pack_data.json', 'reward_data.json'}
COMPACT_LIMIT = 600

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


def scan_tables(bundle_dir, target_names):
    """一次遍历全部 bundle, 收集 m_Name 命中的 MonoBehaviour typetree"""
    targets = set(target_names)
    found = {name: [] for name in targets}
    bundles = sorted(f for f in os.listdir(bundle_dir) if f.endswith('.bundle'))
    t0 = time.time()
    for i, bname in enumerate(bundles, 1):
        try:
            env = UnityPy.load(os.path.join(bundle_dir, bname))
        except Exception:
            continue
        for obj in env.objects:
            if obj.type.name != 'MonoBehaviour':
                continue
            try:
                tt = obj.read_typetree()
            except Exception:
                continue
            nm = tt.get('m_Name')
            if nm in found:
                found[nm].append(tt)
        if i % 600 == 0:
            print('[tables] 扫描 %d/%d (%.0fs)' % (i, len(bundles), time.time() - t0),
                  flush=True)
    return found


def pick_table(tables, name):
    """取指定表的唯一实例; 缺失时报错退出而非静默产出残缺数据"""
    items = tables.get(name) or []
    if not items:
        raise SystemExit('[tables] 未找到 %s, 无法导出。游戏可能已更新。' % name)
    if len(items) > 1:
        print('[tables] 警告: %s 有 %d 个实例, 取第一个' % (name, len(items)))
    return items[0]


def write_json(root, rel, data):
    p = Path(safe_out(root, rel))
    limit = COMPACT_LIMIT if p.name in COMPACT_TABLES else 0
    p.write_text(json_compact.dumps(data, inline_limit=limit), encoding='utf-8')
    return str(p)


def export_songs(tables):
    tt = pick_table(tables, SONGDATA_TABLE)
    songs = []
    for s in tt['allSongInfo']:
        charts = []
        for c in s['ChartInfos']:
            charts.append({
                'chartId': c['Id'],
                'difficulty': DIFFICULTY_NAMES.get(c['Difficulty'], c['Difficulty']),
                'rating': c['Rating'],
                'levelIndicator': c['LevelSectionIndicator'],
                'chartDesigner': c['DisplayChartDesigner'],
                'jacketDesigner': c['DisplayJacketDesigner'],
                'available': bool(c['Available']),
            })
        songs.append({
            'songId': s['Id']['Value'],
            'baseName': s['BaseName'],
            'characterId': s['CharacterIdentifier'],
            'previewStartSec': s['PreviewStartSeconds'],
            'previewEndSec': s['PreviewEndSeconds'],
            'charts': charts,
        })
    write_json(OUT, 'songs.json', songs)
    table = []
    for s in songs:
        for c in s['charts']:
            table.append({
                'song': s['baseName'],
                'chartId': c['chartId'],
                'difficulty': c['difficulty'],
                'constant': c['rating'],
                'designer': c['chartDesigner'],
            })
    write_json(OUT, 'constant_table.json', table)
    return len(songs)


def export_game_data(tables):
    tt = pick_table(tables, GAMEDATA_TABLE)
    data = {k: v for k, v in tt.items() if not k.startswith('m_')}
    write_json(OUT, 'game_data.json', data)
    return len(data.get('baseCards', []))


def export_extra_tables(tables):
    for table_name, out_name in EXTRA_TABLES:
        tt = pick_table(tables, table_name)
        data = {k: v for k, v in tt.items() if not k.startswith('m_')}
        write_json(OUT, out_name, data)
        print('[tables] %s: OK' % out_name)


def export_game_skill_icons(tables):
    """合并所有 GameSkillIconMapping 实例"""
    items = tables.get(GAMESKILL_TABLE) or []
    if not items:
        raise SystemExit('[tables] 未找到 %s, 无法导出 skill_icon_mapping.json'
                         % GAMESKILL_TABLE)
    merged = {'gameSkillToIcon': [], 'fallbackIcon': None}
    seen = set()
    for tt in items:
        entries = tt.get('gameSkillToIcon', [])
        key = (tuple(e.get('m_PathID') for e in entries),
               (tt.get('fallbackIcon') or {}).get('m_PathID'))
        if key in seen:
            continue
        seen.add(key)
        merged['gameSkillToIcon'].extend(entries)
        if merged['fallbackIcon'] is None:
            merged['fallbackIcon'] = tt.get('fallbackIcon')
    print('[tables] %s: %d 个实例, 去重后 %d 份 / %d 条'
          % (GAMESKILL_TABLE, len(items), len(seen), len(merged['gameSkillToIcon'])))
    write_json(OUT, 'skill_icon_mapping.json', merged)


def main():
    global OUT
    game_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GAME
    out_root = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
    bundle_dir = os.path.join(game_dir, 'infalsus_Data', 'StreamingAssets', 'aa', 'StandaloneWindows64')
    if not os.path.isdir(bundle_dir):
        raise SystemExit('[tables] bundle 目录不存在: %s' % bundle_dir)
    OUT = os.path.join(out_root, 'info')
    os.makedirs(OUT, exist_ok=True)
    print('game dir: ' + game_dir)
    print('output:   ' + OUT)

    wanted = [SONGDATA_TABLE, GAMEDATA_TABLE, GAMESKILL_TABLE] + [t for t, _ in EXTRA_TABLES]
    tables = scan_tables(bundle_dir, wanted)

    print('[tables] songs.json: %d songs' % export_songs(tables))
    print('[tables] game_data.json: %d base cards' % export_game_data(tables))
    export_extra_tables(tables)
    export_game_skill_icons(tables)
    print('[tables] DONE')


if __name__ == '__main__':
    main()
