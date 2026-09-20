import os
import subprocess
import sys

# ============ 配置区 (按需修改) ============
# 游戏安装目录
GAME_DIR = r'D:\Steam\steamapps\common\In Falsus'
# 输出目录
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
# 要提取哪些资源 (True/False)
EXTRACT_AUDIO = True  # sam 解密: 音频 (Ogg Vorbis)
EXTRACT_CHARTS = True  # sam 解密: 谱面 .spc + 谱面概要
EXTRACT_SCRIPTS = True  # sam 解密: NovelEngine 文本脚本
EXTRACT_IMAGES = True  # bundle: 贴图/立绘 (原始尺寸) + Sprite
EXTRACT_VIDEOS = True  # bundle: 视频 (webm) 与字体
EXTRACT_TABLES = True  # 信息表: 定数表 / 歌曲表 / 卡牌数据 -> info/
CHART_TO_JSON = True  # 谱面 .spc 转可读 JSON (输出到 charts_json/)

# ============ 以下无需修改 ============

HERE = os.path.dirname(os.path.abspath(__file__))

ALLOWED_SCRIPTS = {
    'extract_infalsus.py',
    'export_images.py',
    'info_tables.py',
    'spc_to_json.py',
}


def run(script, args=None):
    if script not in ALLOWED_SCRIPTS:
        raise ValueError('script not allowed: %r' % script)
    cmd = [sys.executable, os.path.join(HERE, script)] + (args or [])
    print()
    print("====== " + script + " ======")
    subprocess.run(cmd, check=True, shell=False)


def safe_rmtree(out_root, sub):
    target = os.path.realpath(os.path.join(os.path.abspath(out_root), sub))
    root = os.path.realpath(os.path.abspath(out_root))
    if target == root or not target.startswith(root + os.sep):
        raise ValueError('refuse to delete outside output dir: %r' % sub)
    import shutil
    shutil.rmtree(target, ignore_errors=True)


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else GAME_DIR
    out = sys.argv[2] if len(sys.argv) > 2 else OUT_DIR
    os.makedirs(out, exist_ok=True)
    print('game dir: ' + game)
    print('out dir:   ' + out)

    if EXTRACT_AUDIO or EXTRACT_CHARTS or EXTRACT_SCRIPTS:
        run('extract_infalsus.py', [game, out])
        if not EXTRACT_AUDIO:
            safe_rmtree(out, 'audio')
        if not EXTRACT_CHARTS:
            safe_rmtree(out, 'charts')
        if not EXTRACT_SCRIPTS:
            safe_rmtree(out, 'scripts')

    if EXTRACT_IMAGES:
        run('export_images.py', [game, out])

    if EXTRACT_VIDEOS:
        run('extract_infalsus.py', [game, out, '--skip-sam'])

    if EXTRACT_TABLES:
        run('info_tables.py', [game, out])

    if CHART_TO_JSON and EXTRACT_CHARTS:
        run('spc_to_json.py', [game, out])

    print()
    print('全部完成')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit('\n[错误] 子步骤失败 (退出码 %d), 提取已中断。' % exc.returncode)
