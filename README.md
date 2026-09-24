# In Falsus 资源提取工具

把《In Falsus》（lowiro，Unity 6 / IL2CPP 打包）游戏内的资源整包提取出来：
解密 `.sam`、扫 AssetBundle、导出图片 / 音频 / 谱面 / 视频 / 字体 / 文本脚本 / 数据表，
并额外把**剧情脚本合成可读剧本**、把**谱面解成可读 JSON**。

> **免责声明**
>
> 本工具仅供个人学习研究使用，请勿用于商业用途或未经授权的传播。
> 
> 使用本工具提取的任何资源，其所有权和著作权均归属于游戏原始开发者/发行方，请遵守相关法律法规和用户协议。
>  
> 因使用本工具所引发的任何法律后果、数据丢失、或对游戏文件造成的损坏，作者概不负责。
> 使用前请确认您有权访问和备份相关游戏文件！

## 功能

**资源提取**

- 音频（Ogg Vorbis）
- 谱面（.spc 格式，可转为可读 JSON）
- 游戏内所有图片（贴图、UI 立绘、卡牌、角色图标、歌曲封面等）
- 视频（webm）、字体（ttf/otf，共 27 个，含日中韩繁简）
- NovelEngine 文本脚本
- 转写剧情脚本
- 数据表

## 使用方法

### 环境要求

- Python 3.9+
- 依赖库（UnityPy、Pillow）

### 步骤

1. **确认游戏路径**  
   默认路径：`D:\Steam\steamapps\common\In Falsus`  
   若游戏安装在其他位置，请修改 `main.py` 的 `GAME_DIR` 变量。

2. **运行主脚本**  
   在项目目录下，直接运行：

   ```bash
   python main.py
   ```

3. **输出资源**  
   所有资源将输出到当前目录下的 `output/` 文件夹，结构如下：

```
output/
├── audio/            # 音频文件
├── charts/            # 原始谱面 .spc + .summary.json 概要
├── charts_json/       # 谱面解密后的 JSON
├── images/           # 贴图、UI立绘等
├── sprites/           # UI Sprite
├── videos/             # 视频文件   webm
├── fonts/              # 字体
├── scripts/           # NovelEngine 文本脚本
│   ├── scenario_wip/scenario_Y1-1..Y1-4/*.sps    # 剧情脚本
│   └── assets/scripts/names.spp, common.spp      # 人名 / 场景名等别名表
│   └── assets/anim/*.spi                          # 演出 / 动画定义
├── story_readable/    # 可读剧本 md
└── info/               # 数据表 JSON（见下）
```

## 自定义提取

如需只提取部分资源，修改 `main.py` 的配置区：

```python
GAME_DIR = r'D:\Steam\steamapps\common\In Falsus'   # 游戏安装目录
OUT_DIR  = ./output                                # 输出目录

EXTRACT_AUDIO   = True   # 音频
EXTRACT_CHARTS  = True   # 谱面
EXTRACT_SCRIPTS = True   # 文本
EXTRACT_IMAGES  = True   # 图片
EXTRACT_VIDEOS  = True   # 视频
EXTRACT_TABLES  = True   # 数据表
CHART_TO_JSON   = True   # 谱面转 JSON
STORY_READABLE  = True   # 剧情脚本+译文转可读剧本
```

设为 `False` 即可跳过对应类型提取

## 数据表说明

`output/info/` 下 14 张表：

| 文件                             | 内容                                                       |
| -------------------------------- | ---------------------------------------------------------- |
| `constant_table.json`            | 定数表：`{song, chartId, difficulty, constant, designer}`  |
| `songs.json`                     | 歌曲表 ，含难度 / 定数 / BPM / 预览片段起止秒 / 曲绘与艺人 |
| `game_data.json`                 | 卡牌数据                                                   |
| `pack_data.json`                 | 曲包：`{Id, Slug, SongIds}`                                |
| `reward_data.json`               | 剧情 / 歌曲 / 配方 / 战斗的奖励发放                        |
| `recipe_specifications.json`     | iota + 配方                                                |
| `encounter_details.json`         | 战斗配置）                                                 |
| `dynamic_string_mapping.json`    | 本地化映射                                                 |
| `story_translations.json`        | 剧情对白多语言表                                           |
| `story_details.json`             | 剧情目录                                                   |
| `story_unlock_requirements.json` | 剧情顺序 + 解锁前置                                        |
| `card_art_mapping.json`          | 卡牌图映射                                                 |
| `character_icon_mapping.json`    | 角色图标映射                                               |
| `skill_icon_mapping.json`        | 技能图标映射                                               |