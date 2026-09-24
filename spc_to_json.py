"""谱面 .spc (ICP1) 解密并转成可读 JSON"""
import os
import struct
import sys
from pathlib import Path

import json_compact

OUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
M64 = (1 << 64) - 1
M32 = (1 << 32) - 1

TYPE_FLICK = 4  # 标志 A 高字节 = 4 (1 tap / 2 hold / 5 field)
TYPE_FIELD = 5  # 标志 A 高字节 = 5
TRACK_AIR = 4  # 标志 A 低字节 = 4 (1 地面 / 2 左侧轨 / 3 右侧轨)
FLICK_CODE_SHIFT = 8  # 标志 B 的方向位: 1024 >> 8 = 4 右, 4096 >> 8 = 16 左
EASE_BITS_LEFT = 2  # 标志 B 位 2-4 = 左边界缓动 (one-hot), 0 Linear / 1 SineOut / 2 SineIn
EASE_BITS_RIGHT = 5  # 标志 B 位 5-7 = 右边界缓动


def rol(x, n):
    return ((x << n) | (x >> (64 - n))) & M64


def gen(state, idx, k):
    """GEN: 生成 (记录序号 idx, 字段号 k) 的密钥流"""
    s0, s1, s2, s3 = state[0], state[1], state[2], state[3]
    r9 = ((idx & M32) << 32) | (k & M32)
    v = k & 3
    if v == 3:
        return rol((s2 + s1 + r9) & M64, 37) ^ s3
    if v == 2:
        r9 ^= s0
        return ((rol(r9, 29) + s2) & M64) ^ s1
    if v == 1:
        return ((s1 - rol((s3 + r9) & M64, 17)) & M64) ^ s0
    r9 ^= s2
    return ((rol(r9, 11) + s0) & M64) ^ s3


def finalize(state, rdx, r8, r9):
    """状态推进一轮, 分支由计数器低 2 位选择"""
    s0, s1, s2, s3, cnt = state
    v = cnt & 3
    if v == 0:
        s0 = (s0 + (rol(s3, 7) + rdx)) & M64
        rax = rol((s0 + r8) & M64, 13)
        s1 ^= rax
        r9 ^= s1
        s2 = (s2 - r9) & M64
        s3 = rol((s2 + s3) & M64, 27) ^ s0
    elif v == 1:
        s1 = (s1 + (rol(s0, 9) + r9)) & M64
        rax = rol((s1 + rdx) & M64, 19)
        s2 ^= rax
        r8 ^= s2
        s3 = (s3 - r8) & M64
        s0 = rol((s3 + s0) & M64, 31) ^ s1
    elif v == 2:
        s2 = (s2 + (rol(s1, 15) + r8)) & M64
        rax = rol((s2 + r9) & M64, 23)
        s3 ^= rax
        rdx ^= s3
        s0 = (s0 - rdx) & M64
        s1 = rol((s1 + s0) & M64, 39) ^ s2
    else:
        keep = s2
        s3 = (s3 + (rol(s2, 21) + rdx)) & M64
        rax = rol((s3 + r8) & M64, 29)
        s0 ^= rax
        rax = s0 ^ r9
        s1 = (s1 - rax) & M64
        s2 = rol((keep + s1) & M64, 43) ^ s3
    return [s0, s1, s2, s3, (cnt + 1) & M32]


def derive_key(seed, count, u16):
    """deriveKey(种子, noteCount, 1)"""
    st = [(0xC4CEB9FE1A85EC53 + count) & M64,
          ((count & M32) << 32) ^ 0x9E3779B185EBCA87,
          (0xD1B54A32D192ED03 + (u16 & 0xFFFF)) & M64,
          (u16 & 0xFFFF) ^ 0x94D049BB133111EB, 0]
    for i, ch in enumerate(seed):
        rdx = ((i & M32) << 32) | (ord(ch) & M32)
        rdi = u16 ^ rdx
        r8 = (rdx + count) & M64
        s0, s1, s2, s3 = st[0], st[1], st[2], st[3]
        v = st[4] & 3
        if v == 0:
            s0 = (s0 + (rol(s3, 7) + rdx)) & M64
            rax = rol((s0 + r8) & M64, 13) ^ s1
            s1 = rax
            rdi ^= rax
            s2 = (s2 - rdi) & M64
            s3 = rol((s3 + s2) & M64, 27) ^ s0
        elif v == 1:
            s1 = (rol(s0, 9) + s1 + rdi) & M64
            rcx = rol((s1 + rdx) & M64, 19) ^ s2
            s2 = rcx
            r8 ^= rcx
            s3 = (s3 - r8) & M64
            s0 = rol((s0 + s3) & M64, 31) ^ s1
        elif v == 2:
            s2 = (rol(s1, 15) + r8 + s2) & M64
            rcx = rol((s2 + rdi) & M64, 23) ^ s3
            rdx ^= rcx
            s3 = rcx
            s0 = (s0 - rdx) & M64
            s1 = rol((s1 + s0) & M64, 39) ^ s2
        else:
            keep = s2
            s3 = (rol(s2, 21) + s3 + rdx) & M64
            rcx = rol((s3 + r8) & M64, 29)
            s0 ^= rcx
            rdi ^= s0
            s1 = (s1 - rdi) & M64
            s2 = rol((keep + s1) & M64, 43) ^ s3
        st = [s0, s1, s2, s3, (st[4] + 1) & M32]
    return finalize(st, count, u16, len(seed))


def s32(value):
    value &= M32
    return value - (1 << 32) if value >> 31 else value


def gcd(a, b):
    a, b = abs(a), abs(b)
    while b:
        a, b = b, a % b
    return a or 1


def decode_record(record, state, index):
    fields = {}
    for k, off, size in ([(0, 0x00, 8), (1, 0x08, 8)] +
                         [(j, 0x10 + (j - 2) * 4, 4) for j in range(2, 10)]):
        cipher = int.from_bytes(record[off:off + size], 'little')
        fields[k] = (cipher - gen(state, index, k)) & ((1 << (8 * size)) - 1)
    plain = [int.from_bytes(record[0x30 + j * 4:0x34 + j * 4], 'little')
             for j in range(8)]
    scales = []
    for num_i, den_i, k in ((0, 1, 6), (2, 3, 7), (4, 5, 8), (6, 7, 9)):
        g = gcd(s32(plain[num_i]), s32(plain[den_i]))
        scales.append((((s32(plain[num_i]) // g) * s32(fields[k])) & M32,
                       ((s32(plain[den_i]) // g) * s32(fields[k])) & M32))
    return fields, plain, scales


def advance(state, fields, scales):
    """记录解码后用 3 次 finalize 推进密钥流状态"""
    state = finalize(state, fields[0], fields[1],
                     ((fields[3] & M32) << 32) | (fields[2] & M32))
    state = finalize(state, fields[4], fields[5],
                     (scales[0][1] << 32) | scales[0][0])
    state = finalize(state, (scales[1][1] << 32) | scales[1][0],
                     (scales[2][1] << 32) | scales[2][0],
                     (scales[3][1] << 32) | scales[3][0])
    return state


def decode_event(raw):
    """解一条 32 字节尾部事件"""
    event_id = int.from_bytes(raw[0:8], 'little')
    time_ms = int.from_bytes(raw[8:12], 'little')
    event_type = int.from_bytes(raw[12:16], 'little')
    value1 = int.from_bytes(raw[16:24], 'little')
    value2 = int.from_bytes(raw[24:32], 'little')
    event = {'id': event_id, 'type': event_type, 'timeMs': time_ms}
    if event_type == 3:
        event['flags'] = value1
    else:
        number = struct.unpack('<d', struct.pack('<Q', value1))[0]
        # type 1 实测取值 65..2000, 是 BPM; 其余类型只是斜坡/滚动位置
        event['bpm' if event_type == 1 else 'value'] = round(number, 6)
    if value2:
        event['speed'] = round(struct.unpack('<f', struct.pack('<I', value2))[0], 6)
    return event


def bpm_timeline(events, bpm0):
    """BPM 时间轴: 头部 bpm 起始, type 1 事件在其时刻切换"""
    segments = [(0.0, bpm0)]
    for event in events:
        bpm = event.get('bpm')
        if bpm and 1.0 < bpm < 10000.0:
            segments.append((float(event['timeMs']), bpm))
    segments.sort()
    return segments


def beat_at(time_ms, segments):
    """分段积分求拍号"""
    total = 0.0
    prev_time, prev_bpm = segments[0]
    for seg_time, seg_bpm in segments[1:]:
        if seg_time >= time_ms:
            break
        total += (seg_time - prev_time) * prev_bpm / 60000.0
        prev_time, prev_bpm = seg_time, seg_bpm
    return total + (time_ms - prev_time) * prev_bpm / 60000.0


def onehot_index(value, base):
    """取位 base..base+2 中的 one-hot 位, 返回 0..2 或 None"""
    for i in range(3):
        if value & (1 << (base + i)):
            return i
    return None


def parse(data, seed):
    """解密一整份 ICP1 谱面, 返回可序列化的字典"""
    if data[:4] != b'ICP1':
        return None
    ver, hdr, rec_a, rec_b, note_count, tail_count = \
        struct.unpack_from('<HHHHII', data, 4)
    bpm, meter = struct.unpack_from('<ff', data, 0x14)
    if hdr + note_count * rec_a + tail_count * rec_b != len(data):
        raise ValueError('文件大小与头部不一致')

    state = derive_key(seed, note_count, 1)
    raw_notes = []
    for i in range(note_count):
        rec = data[hdr + i * rec_a:hdr + (i + 1) * rec_a]
        fields, plain, scales = decode_record(rec, state, i)
        raw_notes.append((fields, scales))
        state = advance(state, fields, scales)

    events = []
    tail_off = hdr + note_count * rec_a
    for t in range(tail_count):
        events.append(decode_event(
            data[tail_off + t * rec_b:tail_off + (t + 1) * rec_b]))

    segments = bpm_timeline(events, bpm)
    notes = []
    for index, (fields, scales) in enumerate(raw_notes):
        note_type = fields[4] >> 8
        track = fields[4] & 0xFF
        x_start = (scales[0][0] / scales[0][1]) if scales[0][1] else None
        x_end = (scales[1][0] / scales[1][1]) if scales[1][1] else None
        w_start = (scales[2][0] / scales[2][1]) if scales[2][1] else None
        w_end = (scales[3][0] / scales[3][1]) if scales[3][1] else None
        if track != TRACK_AIR and x_start is not None and w_start is not None:
            lane_first = round(x_start * 4)
            lane_last = round((x_start + w_start) * 4) - 1
        else:
            lane_first = lane_last = None
        note = {
            'index': fields[0],
            'line': fields[1],
            'type': note_type,
            'track': track,
            'lane': lane_first,
            'laneFirst': lane_first,
            'laneLast': lane_last,
            'timeMs': fields[2],
            'endMs': fields[3],
            'durationMs': fields[3] - fields[2],
            'beat': round(beat_at(fields[2], segments), 4),
            'endBeat': round(beat_at(fields[3], segments), 4),
            'x': round(x_start, 6) if x_start is not None else None,
            'endX': round(x_end, 6) if x_end is not None else None,
            'width': round(w_start, 6) if w_start is not None else None,
            'endWidth': round(w_end, 6) if w_end is not None else None,
            'fractions': [[num, den] for num, den in scales],
        }
        if note_type == TYPE_FLICK:
            note['flick'] = fields[5] >> FLICK_CODE_SHIFT
        elif note_type == TYPE_FIELD:
            note['leftEase'] = onehot_index(fields[5], EASE_BITS_LEFT)
            note['rightEase'] = onehot_index(fields[5], EASE_BITS_RIGHT)
        notes.append(note)

    for event in events:
        event['beat'] = round(beat_at(event['timeMs'], segments), 4)

    return {'format': 'ICP1', 'version': ver, 'bpm': bpm, 'meter': meter,
            'noteCount': note_count, 'eventCount': tail_count,
            'notes': notes, 'events': events}


def _flat_name(name):
    """只接受单层文件名, 拒绝任何目录成分或上级引用"""
    if name != os.path.basename(name) or '..' in name:
        raise SystemExit('非法文件名: %r' % name)
    if '/' in name or '\\' in name:
        raise SystemExit('非法文件名: %r' % name)
    return name


def read_chart(root, name):
    path = Path(root) / _flat_name(name)
    if not path.is_file():
        raise SystemExit('谱面不存在: %s' % path)
    return path.read_bytes()


def write_json(root, name, obj):
    path = Path(root) / _flat_name(name)
    # 只把 fractions 这类纯标量小数组内联, 音符与事件对象仍逐字段展开
    path.write_text(json_compact.dumps(obj, inline_limit=0, leaf_limit=240),
                    encoding='utf-8')


def main():
    out_root = sys.argv[2] if len(sys.argv) > 2 else OUT_ROOT
    charts_dir = os.path.join(out_root, 'charts')
    json_dir = os.path.join(out_root, 'charts_json')
    if not os.path.isdir(charts_dir):
        print('charts 目录不存在')
        return 1
    os.makedirs(json_dir, exist_ok=True)
    done = failed = 0
    for name in sorted(os.listdir(charts_dir)):
        if not name.endswith('.spc'):
            continue
        try:
            obj = parse(read_chart(charts_dir, name), name)
        except ValueError as exc:
            print('[spc->json] %s: %s' % (name, exc))
            failed += 1
            continue
        if obj is None:
            continue
        write_json(json_dir, name[:-4] + '.json', obj)
        done += 1
    print('[spc->json] %d 张谱面已解密 (%d 失败)' % (done, failed))
    return 0


if __name__ == '__main__':
    sys.exit(main())
