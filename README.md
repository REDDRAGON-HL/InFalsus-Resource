# In Falsus 资源提取工具

用于提取《In Falsus》游戏内的资源（图片/音频/谱面/文本/数据表等）。支持 Windows x64 环境。

## 免责声明

本工具仅供个人学习研究使用，请勿用于商业用途或未经授权的传播。  
使用本工具提取的任何资源，其所有权和著作权均归属于游戏原始开发者/发行方，请遵守相关法律法规和用户协议。  
因使用本工具所引发的任何法律后果、数据丢失、或对游戏文件造成的损坏，作者概不负责。**使用前请确认您有权访问和备份相关游戏文件！**

## 功能

- **资源提取**
  - 音频（Ogg Vorbis）
  - 谱面（.spc 格式，可转为可读 JSON）
  - 游戏内所有图片（贴图、UI 立绘、卡牌、角色图标、歌曲封面等）
  - 视频（webm）、字体（ttf）
  - NovelEngine 文本脚本

- **数据表导出**
  - 定数表（按谱面/难度）
  - 歌曲列表（含难度、BPM、预览片段）
  - 卡牌数据（基础特性、掉落表）
  - 本地化字符串映射（多语言歌曲名、角色名、技能名等）
  - 关卡包数据、奖励表、角色图标映射等

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
   ├── audio/          # 音频文件（Ogg Vorbis）
   ├── charts/         # 原始谱面 .spc + .summary.json 概要
   ├── charts_json/    # 谱面解密后的 JSON（类型/轨道/起止毫秒/拍号/位置/宽度）
   ├── images/         # 贴图、UI立绘等（原始尺寸，不裁剪）
   ├── sprites/        # UI Sprite（UnityPy 输出尺寸）
   ├── videos/         # 视频文件
   ├── scripts/        # NovelEngine 文本脚本
   ├── info/           # 数据表（JSON 格式）
        ├── constant_table.json        # 定数表
        ├── songs.json                # 歌曲表
        ├── game_data.json            # 卡牌数据
        ├── pack_data.json            # 曲包数据
        ├── reward_data.json          # 奖励表
        ├── card_art_mapping.json     # 卡牌图映射
        ├── character_icon_mapping.json # 角色图标
        ├── skill_icon_mapping.json   # 技能图标
        └── dynamic_string_mapping.json # 本地化映射
   ```

## 自定义提取

如需只提取部分资源，修改 `main.py` 的配置区：

```python
EXTRACT_AUDIO   = True   # 音频
EXTRACT_CHARTS  = True   # 谱面
EXTRACT_SCRIPTS = True   # 文本
EXTRACT_IMAGES  = True   # 图片
EXTRACT_VIDEOS  = True   # 视频
EXTRACT_TABLES  = True   # 数据表
CHART_TO_JSON   = True   # 谱面转 JSON
```

设为 `False` 即可跳过对应类型提取。