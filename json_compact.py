"""
紧凑 JSON 序列化：短容器写在一行，长容器按层缩进
把 `inline_limit` 调小（如 0）则逐字段展开的常规缩进输出
"""

import json


def dumps(obj, indent=1, inline_limit=600, inline_leaf_arrays=False, default=str):
    """序列化为字符串。`indent` 为每层缩进宽度"""
    return _dump(obj, 0, indent, inline_limit, inline_leaf_arrays, default)


def _is_scalar(value):
    return value is None or isinstance(value, (int, float, str, bool))


def _leaf_array(obj):
    if not obj or not isinstance(obj, list):
        return False
    if all(_is_scalar(x) for x in obj):
        return True
    return all(isinstance(x, list) and x and all(_is_scalar(y) for y in x)
               for x in obj)


def _dump(obj, depth, step, limit, leaf_arrays, default):
    pad = ' ' * (depth * step)
    inner = ' ' * ((depth + 1) * step)
    compact = json.dumps(obj, ensure_ascii=False, default=default)
    if not isinstance(obj, (dict, list)) or not obj or len(compact) <= limit:
        return compact
    if leaf_arrays and _leaf_array(obj):
        return compact
    if isinstance(obj, dict):
        items = ['%s%s: %s' % (inner, json.dumps(k, ensure_ascii=False),
                               _dump(v, depth + 1, step, limit, leaf_arrays, default))
                 for k, v in obj.items()]
        return '{\n' + ',\n'.join(items) + '\n' + pad + '}'
    items = ['%s%s' % (inner, _dump(v, depth + 1, step, limit, leaf_arrays, default))
             for v in obj]
    return '[\n' + ',\n'.join(items) + '\n' + pad + ']'
