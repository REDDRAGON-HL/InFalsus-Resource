"""
紧凑 JSON 序列化：短容器写在一行，长容器按层缩进
把 `inline_limit` 调小（如 0）则逐字段展开的常规缩进输出
"""

import json


def dumps(obj, indent=1, inline_limit=600, leaf_limit=0, leaf_object_limit=0,
          default=str):
    """序列化为字符串。`indent` 为每层缩进宽度"""
    return _dump(obj, 0, indent, inline_limit, leaf_limit, leaf_object_limit, default)


def _is_scalar(value):
    return value is None or isinstance(value, (int, float, str, bool))


def _leaf_array(obj, limit):
    if not obj or not isinstance(obj, list):
        return False
    if all(_is_scalar(x) for x in obj):
        return True
    if not all(isinstance(x, list) and x and all(_is_scalar(y) for y in x)
               for x in obj):
        return False
    return limit <= 0 or len(json.dumps(obj, ensure_ascii=False)) <= limit


def _leaf_object_array(obj, limit):
    if not obj or not isinstance(obj, list) or limit <= 0:
        return False
    if not all(isinstance(x, dict) and x and all(_is_scalar(v) for v in x.values())
               for x in obj):
        return False
    return len(json.dumps(obj, ensure_ascii=False)) <= limit


def _dump(obj, depth, step, limit, leaf_limit, leaf_object_limit, default):
    pad = ' ' * (depth * step)
    inner = ' ' * ((depth + 1) * step)
    compact = json.dumps(obj, ensure_ascii=False, default=default)
    if not isinstance(obj, (dict, list)) or not obj or len(compact) <= limit:
        return compact
    if leaf_limit > 0 and _leaf_array(obj, leaf_limit):
        return compact
    if _leaf_object_array(obj, leaf_object_limit):
        return compact
    if isinstance(obj, dict):
        items = ['%s%s: %s' % (inner, json.dumps(k, ensure_ascii=False),
                               _dump(v, depth + 1, step, limit, leaf_limit,
                                     leaf_object_limit, default))
                 for k, v in obj.items()]
        return '{\n' + ',\n'.join(items) + '\n' + pad + '}'
    items = ['%s%s' % (inner, _dump(v, depth + 1, step, limit, leaf_limit,
                                    leaf_object_limit, default))
             for v in obj]
    return '[\n' + ',\n'.join(items) + '\n' + pad + ']'
