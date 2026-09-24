"""剧情脚本转可读剧本

用法
    python story_readable.py                    # 默认简体中文 + 解锁顺序
    python story_readable.py --lang ChineseTC   # 繁体 / Japanese / English / Korean
    python story_readable.py --order list       # 游戏剧情列表原始顺序（纯时间序）
    python story_readable.py --check            # 只体检不写文件
    python story_readable.py --no-markers       # 不输出 【CG】【影片】 等提示行
"""

import argparse
import json
import re
from pathlib import Path

import json_compact

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / 'output'
SCRIPTS_DIR = OUT_DIR / 'scripts'
INFO_DIR = OUT_DIR / 'info'

# .sps 的语言字段
LANG_CHOICES = ('ChineseSC', 'ChineseTC', 'Japanese', 'English', 'Korean')
# dynamic_string_mapping 
LOC_FIELD = {
    'English': 'English',
    'Japanese': 'Japanese',
    'Korean': 'Korean',
    'ChineseTC': 'TraditionalChinese',
    'ChineseSC': 'SimplifiedChinese',
}

# --- 正则

ID_RE = re.compile(r'^id\s+(\d{3}-\d{3})\s*$')
SAY_RE = re.compile(r'^s\s+(?:\$(\w+)\s+)?`(.*)$')
LOG_RE = re.compile(r'^log\s+`(.*)$')
PHONE_MSG_RE = re.compile(r'^phone\s+message\s+(?:left|right)\s+\$(\w+)\s+`(.*)$')
BG_INIT_RE = re.compile(r'^\s*bg_init\s+(\S+)')
VIDEO_RE = re.compile(r'^\s*video\s+"([^"]+)"')
SHOW_RE = re.compile(r'^\s*show\s+"([^"]+)"')
SHOW_ALIAS_RE = re.compile(r'^\s*show\s+\$(\w+)')
CG_NAME_RE = re.compile(r'_CG[A-Za-z0-9_]*$')
PHONE_SETUP_RE = re.compile(r'^\s*phone\s+setup\b')
CHOICE_RE = re.compile(r'^choice\s+"[^"]*"\s+"([^"]+)"')
ALIAS_RE = re.compile(r'^alias\s+\$(\w+)\s+"([^"]*)"', re.M)
ALIAS_PATH_RE = re.compile(r'^alias\s+\$(\w+)\s+"[^"]*"(?:\s+"([^"]*)")?', re.M)
STEM_RE = re.compile(r'^Y(\d+)-(\d+)-(\d+)([A-Z])-(\d+)')
STEM_FULL_RE = re.compile(r'^Y(\d+)-(\d+)-(\d+)([A-Z])-(\d+)(-O)?_([A-Za-z]+)$')
RUBY_RE = re.compile(r'<rt>.*?</rt>', re.S)

# --- StoryIdentifier
SEG_CODES = {c: i for i, c in enumerate('ABCDEFGHI')}
POV_CODES = {'Ni': 0, 'Me': 1, 'Ay': 2, 'Ir': 3, 'St': 4, 'Xt': 14}

LINE_TAGS = ('Ni', 'Me', 'Ay', 'Ir', 'St')
LINE_TAG_OTHER = 'Xt'

MD_LEAD = '#>-*|'


def clean_text(text):
    """清掉ruby注音标记和字面量"""
    text = RUBY_RE.sub('', text)
    text = text.replace('<ruby>', '').replace('</ruby>', '')
    text = text.replace('\\n', '\n')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text.strip('\n')


def esc_md(text):
    """转义掉markdown语法字符"""
    if text and text[0] in MD_LEAD:
        return '\\' + text
    return text


# --- 载入辅助表

def alias_files():
    files = []
    for sub, ext in (('scripts', '*.spp'), ('anim', '*.spi')):
        base = SCRIPTS_DIR / 'assets' / sub
        files += sorted(base.glob(ext))
    return files


def load_aliases():
    aliases = {}
    for path in alias_files():
        text = path.read_text(encoding='utf-8', errors='replace')
        for match in ALIAS_RE.finditer(text):
            aliases.setdefault(match.group(1), match.group(2))
    return aliases


def load_alias_paths():
    paths = {}
    for path in alias_files():
        text = path.read_text(encoding='utf-8', errors='replace')
        for match in ALIAS_PATH_RE.finditer(text):
            paths.setdefault(match.group(1), match.group(2) or '')
    return paths


def load_translations():
    path = INFO_DIR / 'story_translations.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    return {entry['Id']: entry for entry in data['Translations']}


def load_name_loc():
    path = INFO_DIR / 'dynamic_string_mapping.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    mapping = data.get('rawStoryNameTypeMapping', {})
    names = mapping.get('IdStr', [])
    values = mapping.get('IdValues', [])
    table = {}
    for english, loc in zip(names, values):
        key = english.lstrip('*').strip()
        if key and key not in table:
            table[key] = loc
    return table


# --- .sps 解析

def read_backtick(lines, index, rest):
    """跨行引号"""
    buf = rest
    while '`' not in buf and index + 1 < len(lines):
        index += 1
        buf += '\n' + lines[index]
    text, _, _ = buf.partition('`')
    return text, index


def parse_sps(path, aliases=None, alias_paths=None):
    """返回 (items, scene_token)
    items 里每项是 (kind, id, speaker, text)"""
    lines = path.read_text(encoding='utf-8', errors='replace').split('\n')
    items = []
    scene = None
    current_bg = None
    pending_id = None
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()

        match = ID_RE.match(stripped)
        if match:
            pending_id = match.group(1)
            index += 1
            continue

        match = BG_INIT_RE.match(lines[index])
        if match:
            if scene is None:
                scene = match.group(1)
                current_bg = resolve_asset(scene, aliases)
            index += 1
            continue

        match = SAY_RE.match(stripped)
        if match:
            speaker, rest = match.group(1), match.group(2)
            text, index = read_backtick(lines, index, rest)
            text = clean_text(text)
            if text.strip():
                items.append(('line' if speaker else 'say', pending_id, speaker, text))
            pending_id = None
            index += 1
            continue

        match = LOG_RE.match(stripped)
        if match:
            text, index = read_backtick(lines, index, match.group(1))
            text = clean_text(text)
            if text.strip():
                items.append(('say', pending_id, None, text))
            pending_id = None
            index += 1
            continue

        match = PHONE_MSG_RE.match(stripped)
        if match:
            speaker, rest = match.group(1), match.group(2)
            text, index = read_backtick(lines, index, rest)
            text = clean_text(text)
            if text.strip():
                items.append(('line', pending_id, speaker, text))
            pending_id = None
            index += 1
            continue

        match = VIDEO_RE.match(lines[index])
        if match:
            items.append(('marker', None, None, '【影片】' + match.group(1)))
            index += 1
            continue

        match = SHOW_RE.match(lines[index])
        if match:
            name = match.group(1)
            tag = '【CG】' if CG_NAME_RE.search(name) else '【画面】'
            items.append(('marker', None, None, tag + name))
            index += 1
            continue

        match = SHOW_ALIAS_RE.match(lines[index])
        if match:
            var = match.group(1)
            asset = (alias_paths or {}).get(var, '')
            if asset.startswith('bg/'):
                name = (aliases or {}).get(var, var)
                if name != current_bg:
                    current_bg = name
                    items.append(('marker', None, None, '场景：' + name))
            index += 1
            continue

        match = PHONE_SETUP_RE.match(lines[index])
        if match:
            items.append(('marker', None, None, '【手机】'))
            index += 1
            continue

        match = CHOICE_RE.match(stripped)
        if match:
            items.append(('marker', None, None, '【选择支 ' + match.group(1) + '】'))
            index += 1
            continue

        index += 1

    return items, scene


# --- 命名

def chapter_of(folder_name):
    """scenario_Y1-2_5 -> 1-2.5"""
    label = folder_name.replace('scenario_Y', '', 1)
    return label.replace('_', '.')


def time_of(stem):
    """Y1-8-27C-1_Ir -> 第1年8月27日 C-1"""
    match = STEM_RE.match(stem)
    if not match:
        return stem
    year, month, day, seg, part = match.groups()
    return '第%s年%s月%s日 %s-%s' % (year, month, day, seg, part)


def time_key(stem):
    match = STEM_RE.match(stem)
    if not match:
        return (9999, 99, 99, 'Z', 99)
    year, month, day, seg, part = match.groups()
    return (int(year), int(month), int(day), seg, int(part))


def story_identifier(stem):
    """算StoryIdentifier"""
    match = STEM_FULL_RE.match(stem)
    if not match:
        return None
    year, month, day, seg, part, suffix, pov = match.groups()
    if seg not in SEG_CODES or pov not in POV_CODES:
        return None
    return ((int(year) << 28) | (int(month) << 24) | (int(day) << 19)
            | (SEG_CODES[seg] << 15) | (int(part) << 11)
            | (POV_CODES[pov] << 3) | ((1 if suffix else 0) << 2))


def load_story_order():
    """顺序 + 解锁依赖"""
    path = INFO_DIR / 'story_details.json'
    if not path.is_file():
        return None, {}, {}
    data = json.loads(path.read_text(encoding='utf-8'))
    entries = data.get('orderedStoryEntries') or []
    order = {}
    for index, entry in enumerate(entries):
        value = entry.get('StoryIdentifier', {}).get('underlyingValue')
        if value is not None:
            order[value] = index
    requires = {}
    for item in data.get('orderedStoryEntryUnlockRequirements') or []:
        target = item.get('TargetStory', {}).get('underlyingValue')
        need = item.get('RequiredRead', {}).get('underlyingValue')
        if target is not None and need is not None:
            requires.setdefault(target, []).append(need)
    return order, requires, {v: v for v in order}


def topo_order(order, requires):
    nodes = list(order)
    pending = {n: set(r for r in requires.get(n, []) if r in order) for n in nodes}
    done = set()
    result = []
    while len(result) < len(nodes):
        ready = [n for n in nodes if n not in done and not (pending[n] - done)]
        if not ready:  # 有环，剩下的按列表顺序收尾
            ready = [n for n in nodes if n not in done]
        ready.sort(key=lambda n: order[n])
        pick = ready[0]
        done.add(pick)
        result.append(pick)
    return {v: i for i, v in enumerate(result)}


def pov_of(stem, aliases, name_loc, lang):
    suffix = stem.rsplit('_', 1)[-1]
    if not suffix or not suffix[0].isupper():
        return None, None
    if suffix == LINE_TAG_OTHER:
        return suffix, None
    return suffix, localize(aliases.get(suffix), name_loc, lang)


def localize(english_name, name_loc, lang):
    if not english_name:
        return None
    key = english_name.lstrip('*').strip()
    entry = name_loc.get(key)
    if not entry:
        return key
    return (entry.get(LOC_FIELD[lang]) or '').strip() or key


def resolve_asset(token, aliases):
    token = token.strip()
    if token.startswith('$'):
        return aliases.get(token[1:], token[1:])
    return token.strip('"')


# --- 渲染

def render(title, scene, items, translations, aliases, name_loc, lang, markers):
    scene = resolve_asset(scene, aliases) if scene else None
    out = ['# ' + title, '场景：' + (scene or '（未知）'), '']
    for kind, item_id, speaker, text in items:
        if not text:
            continue
        if kind == 'marker':
            if markers:
                out.append(text)
                out.append('')
            continue
        entry = translations.get(item_id) if item_id else None
        if entry:
            translated = (entry.get(lang) or '').strip()
            if translated:
                text = clean_text(translated)
        if kind == 'line':
            name = localize(aliases.get(speaker), name_loc, lang) if speaker else None
            name = name or (speaker or '???')
            out.append('%s：%s' % (name, text.strip()))
        else:
            out.append(esc_md(text))
        out.append('')
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out) + '\n'


# --- 主流程

def collect_scenes(story_order, requires, mode='game'):
    """扫描所有.sps，按章节归组并按顺序定序，返回 (chapters, problems)"""
    problems = []
    scenes = []
    for path in sorted(SCRIPTS_DIR.glob('scenario_wip/*/*.sps')):
        text = path.read_text(encoding='utf-8', errors='replace')
        groups = re.findall(r'^id (\d{3})-\d{3}$', text, re.M)
        ident = story_identifier(path.stem)
        scenes.append({
            'path': path,
            'folder': path.parent.name,
            'chapter': chapter_of(path.parent.name),
            'stem': path.stem,
            'group': int(groups[0]) if groups else None,
            'n_lines': len(groups),
            'ident': ident,
            'needs': [],
        })

    present = {s['group'] for s in scenes if s['group'] is not None}
    holes = sorted(set(range(1, max(present) + 1)) - present)
    blank = [s for s in scenes if s['group'] is None]
    if blank:
        if len(holes) == len(blank):
            for scene, hole in zip(blank, holes):
                scene['group'] = hole
                scene['guessed'] = True
        else:
            problems.append('有 %d 幕没有 id 行，但空缺组号有 %d 个，无法一一对应'
                            % (len(blank), len(holes)))
            for scene in blank:
                scene['group'] = 900 + blank.index(scene)
                scene['guessed'] = True

    if story_order:
        unknown = [s for s in scenes if s['ident'] not in story_order]
        for scene in unknown:
            problems.append('%s 算出的 StoryIdentifier 不在游戏剧情表里，按时间序兜底'
                            % scene['stem'])
        if mode == 'unlock':
            story_order = topo_order(story_order, requires)
        for scene in scenes:
            scene['order'] = story_order.get(scene['ident'])
        scenes.sort(key=lambda s: (s['order'] is None, s['order'] if s['order'] is not None
        else 0, time_key(s['stem']), s['stem']))
        for scene in scenes:
            scene['needs'] = [r for r in requires.get(scene['ident'], []) if r in story_order]
    else:
        problems.append('没有 output/info/story_details.json，退回按剧情时间排序')
        for scene in scenes:
            scene['order'] = None
        scenes.sort(key=lambda s: (time_key(s['stem']), s['group'], s['stem']))

    chapters = {}
    for scene in scenes:
        chapters.setdefault(scene['chapter'], []).append(scene)
    for chapter_scenes in chapters.values():
        for position, scene in enumerate(chapter_scenes, 1):
            scene['index'] = position
            scene['number'] = '%s-%02d' % (scene['chapter'], position)

    ordered = sorted(chapters.items(), key=lambda kv: kv[1][0]['order']
    if kv[1][0]['order'] is not None else 10 ** 6)
    return ordered, problems


def export_unlock_table(index_rows, raw_order, requires):
    """导出 `story_unlock_requirements.json`"""
    if not raw_order:
        return None
    INFO_DIR.mkdir(parents=True, exist_ok=True)
    by_ident = {scene['ident']: scene for _, scene in index_rows}
    stories = []
    for _, scene in index_rows:
        stories.append({
            'ListOrder': raw_order.get(scene['ident']) + 1 if scene['ident'] in raw_order else None,
            'Number': scene['number'],
            'Chapter': scene['chapter'],
            'File': scene['stem'] + '.sps',
            'Time': time_of(scene['stem']),
            'Line': scene.get('line'),
            'LineTag': scene.get('line_tag'),
            'StoryIdentifier': scene['ident'],
            'RequiresRead': sorted(by_ident[n]['number'] for n in scene['needs'] if n in by_ident),
        })
    stories.sort(key=lambda s: (s['ListOrder'] is None, s['ListOrder'] or 0))

    requirements = []
    for target, needs in requires.items():
        for need in needs:
            target_scene = by_ident.get(target)
            need_scene = by_ident.get(need)
            requirements.append({
                'TargetStory': target,
                'Target': target_scene['number'] if target_scene else None,
                'RequiredRead': need,
                'Required': need_scene['number'] if need_scene else None,
                'BackEdge': (target in raw_order and need in raw_order
                             and raw_order[need] > raw_order[target]),
            })
    requirements.sort(key=lambda r: (raw_order.get(r['TargetStory'], 10 ** 6),
                                     raw_order.get(r['RequiredRead'], 10 ** 6)))

    doc = {
        'Note': '剧情解锁前置表',
        'StoryCount': len(stories),
        'RequirementCount': len(requirements),
        'BackEdgeCount': sum(1 for r in requirements if r['BackEdge']),
        'OrderedStories': stories,
        'Requirements': requirements,
    }
    path = INFO_DIR / 'story_unlock_requirements.json'
    path.write_text(json_compact.dumps(doc, inline_limit=600), encoding='utf-8')
    return path


def main():
    parser = argparse.ArgumentParser(description='把解出的剧情脚本合成可读剧本')
    parser.add_argument('--lang', default='ChineseSC', choices=LANG_CHOICES,
                        help='正文语言 (默认 ChineseSC')
    parser.add_argument('--out', default=None, help='输出目录 (默认 output/story_readable)')
    parser.add_argument('--check', action='store_true', help='只体检，不写文件')
    parser.add_argument('--no-markers', action='store_true',
                        help='不输出 【CG】【影片】【手机】【选择支】 提示行')
    parser.add_argument('--order', default='unlock', choices=('unlock', 'list'),
                        help='unlock=解锁顺序（默认，按依赖图拓扑排序）；'
                             'list=游戏剧情列表原始顺序（纯时间序）')
    args = parser.parse_args()

    if not SCRIPTS_DIR.is_dir():
        raise SystemExit('找不到 %s，先跑 main.py 解包' % SCRIPTS_DIR)

    dest = Path(args.out) if args.out else OUT_DIR / 'story_readable'
    translations = load_translations()
    name_loc = load_name_loc()
    aliases = load_aliases()
    alias_paths = load_alias_paths()
    story_order, requires, _ = load_story_order()
    raw_order = story_order

    chapters, problems = collect_scenes(story_order, requires, args.order)

    back_edges = sum(1 for target, needs in requires.items() if target in story_order
                     for need in needs
                     if need in story_order and story_order[need] > story_order[target])

    stats = {'scenes': 0, 'lines': 0, 'missing_id': 0, 'missing_tr': 0,
             'unresolved': 0, 'no_scene': 0, 'guessed': 0, 'empty': 0,
             'back_edges': back_edges}
    index_rows = []

    for chapter, chapter_scenes in chapters:
        for scene in chapter_scenes:
            items, scene_token = parse_sps(scene['path'], aliases, alias_paths)
            stats['scenes'] += 1
            stats['lines'] += len(items)
            if scene_token is None:
                stats['no_scene'] += 1
                problems.append('%s 没有 bg_init，场景未知' % scene['path'].name)
            if scene.get('guessed'):
                stats['guessed'] += 1
                problems.append('%s 无 id 行，按空缺组号补为 %03d'
                                % (scene['path'].name, scene['group']))

            tag, line = pov_of(scene['stem'], aliases, name_loc, args.lang)
            scene['line_tag'] = tag
            scene['line'] = line
            if tag is None:
                stats['unresolved'] += 1
                problems.append('%s 取不到人物线标记' % scene['path'].name)

            if not items:
                stats['empty'] += 1
                items = [('say', None, None, '本幕无台词')]

            for kind, item_id, speaker, text in items:
                if kind == 'marker' or not text:
                    continue
                if item_id is None:
                    stats['missing_id'] += 1
                else:
                    entry = translations.get(item_id)
                    if not entry or not (entry.get(args.lang) or '').strip():
                        stats['missing_tr'] += 1
                        problems.append('%s 的 %s 没有 %s 译文，回落到英文原文'
                                        % (scene['path'].name, item_id, args.lang))
                if kind == 'line' and speaker and speaker not in aliases:
                    stats['unresolved'] += 1
                    problems.append('%s 的说话人 $%s 不在别名表里' % (scene['path'].name, speaker))

            title = ' - '.join([scene['number'], time_of(scene['stem'])]
                               + ([line] if line else []))
            body = render(title, scene_token, items, translations, aliases,
                          name_loc, args.lang, not args.no_markers)
            scene['title'] = title
            scene['scene'] = resolve_asset(scene_token, aliases) if scene_token else None
            scene['body'] = body
            scene['n_items'] = len(items)
            index_rows.append((chapter, scene))

    # 写文件
    if not args.check:
        dest.mkdir(parents=True, exist_ok=True)
        # 清掉上一次的产物
        for stale in dest.rglob('*.md'):
            stale.unlink()
        for chapter, scene in index_rows:
            chapter_dir = dest / chapter
            chapter_dir.mkdir(parents=True, exist_ok=True)
            target = chapter_dir / ('%s_%s.md' % (scene['number'], scene['stem']))
            target.write_text(scene['body'], encoding='utf-8')

        order_note = ('按**解锁顺序**（游戏剧情列表顺序 + 解锁依赖拓扑排序）'
                      if args.order == 'unlock' else
                      '按**游戏剧情列表原始顺序**（= 时间序，同槽内按视角码）')
        lines = ['# 剧情目录', '',
                 '共 %d 章 %d 幕（%s），%s' % (len(chapters), stats['scenes'], args.lang, order_note),
                 '',
                 '| 编号 | 剧情时间 | 人物线 | 场景 | 正文行 | 解锁前置 | 文件 |',
                 '| --- | --- | --- | --- | --- | --- | --- |']
        number_of = {scene['ident']: scene['number'] for _, scene in index_rows}
        for chapter, scene in index_rows:
            rel = '%s/%s_%s.md' % (chapter, scene['number'], scene['stem'])
            needs = sorted(number_of[n] for n in scene['needs'] if n in number_of)
            lines.append('| %s | %s | %s | %s | %d | %s | [%s](%s) |' % (
                scene['number'], time_of(scene['stem']), scene['line'] or '-',
                scene['scene'] or '?', scene['n_items'],
                ', '.join(needs) or '-', scene['stem'], rel))
        (dest / 'INDEX.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        table = export_unlock_table(index_rows, raw_order, requires)
        if table:
            print('前置表已导出: %s' % table)

    print('章节数: %d' % len(chapters))
    for chapter, chapter_scenes in chapters:
        print('  %-6s %2d 幕  %s .. %s'
              % (chapter, len(chapter_scenes),
                 chapter_scenes[0]['number'], chapter_scenes[-1]['number']))
    print('幕数: %d | 正文行: %d | 空幕: %d'
          % (stats['scenes'], stats['lines'], stats['empty']))
    print('无 id 的行: %d | 缺译文: %d | 说话人/人物线未解析: %d'
          % (stats['missing_id'], stats['missing_tr'], stats['unresolved']))
    if problems:
        print('\n提示 %d 条（最多列 20 条）:' % len(problems))
        for line in problems[:20]:
            print('  - ' + line)
    print('\n输出: %s' % (dest if not args.check else '(check 模式，未写文件)'))


if __name__ == '__main__':
    main()
