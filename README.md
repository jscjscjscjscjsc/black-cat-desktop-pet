# 咕嘎桌宠（Guga Penguin Pet）

一个 Windows 桌面企鹅宠物：从炉石酒馆战棋军师进化为 **Python/大模型助教帮手**，
能看屏幕、能出题、能连续对话问答，同时保留战棋胜率分析能力。

## 功能概览

### 1. 企鹅助教（Python / 大模型）

按 **数字键 1**（请教助教）打开输入条，提问 Python / 大模型相关问题：

- 咕嘎会**截屏看你的屏幕**（IDE / 文档 / 错误信息），结合你的问题作答
- 回答显示在置顶大对话面板（可拖动、可滚动、保留 30 条历史）
- AI 回答后**自动重新打开输入条**，可连续追问
- 8 秒屏幕分析超时保护：超时则直接用文字提问

按 **数字键 2**（助教出题）：

- 咕嘎出一道 Python/大模型中级工程师思考题
- 题目展示在对话面板，自动打开答题输入条
- 你写出答案后，咕嘎用助教人设点评

### 2. 酒馆战棋军师（保留）

右键菜单 → **分析对局（看屏幕）**：

- 优先读取 `power.log` 日志解析棋盘（零 API 调用，不触发限流）
- 日志不可用时回退 GLM-4.6V 视觉模型截屏分析
- 蒙特卡洛模拟胜率（n=600，避免主线程卡顿）
- 对手阵容流派分析 + 己方阵容方向展望

> 注意：自动分析已关闭，只在手动点击时触发。

**一键拔线**（数字键 4 / F1）：

- 战斗阶段跳战斗动画，需管理员权限
- 30 秒重连保护期，每局 9 次上限，15 秒冷却

### 3. 基础交互

- **数字键 3**：语音对话模式（按住说话）
- **数字键 5**：摇摆动画
- 透明悬浮置顶，可拖动
- 状态系统：饥饿/心情/精力，自动衰减
- 右键托盘菜单：显示/隐藏、退出
- Bongo 面板：按键时面板反馈

## 运行环境

- Windows 10/11
- Python 3.10+（推荐 3.12）
- PyQt5 + Qt 5.15（需 plugins/platforms 配置，见 `launcher.py`）

## 安装

```powershell
pip install -r requirements.txt
```

复制 `ai_config.example.json` 为 `ai_config.json`，填入你自己的 API Key：

```powershell
copy ai_config.example.json ai_config.json
# 然后用记事本编辑 ai_config.json 填入:
# - api_key: DeepSeek API Key
# - zhipu_api_key: 智谱 GLM-4.6V API Key（视觉分析用）
```

## 启动

双击 `启动企鹅.bat`，或：

```powershell
python launcher.py
```

> `run_as_admin` 默认为 `false`。仅在需要"一键拔线"功能时改为 `true`（会触发 UAC 提权）。

## 项目结构

```
guga-penguin-pet/
├── main.py                  # 应用入口
├── launcher.py              # 启动器（配置 Qt 路径、可选 UAC 提权）
├── ai_config.example.json   # 配置模板（脱敏）
├── ai_config.json           # 实际配置（gitignore，含 API Key）
├── requirements.txt
├── 启动企鹅.bat
│
├── core/                    # 核心逻辑
│   ├── ai_chat.py           # AI 对话引擎（DeepSeek + RAG 上下文）
│   ├── tutor.py             # 助教人设/出题/屏幕分析 prompt
│   ├── vision.py            # GLM-4.6V 视觉分析（截屏 + API）
│   ├── log_reader.py        # 炉石日志解析（带 _prune_ents 内存清理）
│   ├── battle_sim.py        # 蒙特卡洛胜率模拟
│   ├── card_db.py           # 随从卡牌库
│   ├── comp_analysis.py     # 对手阵容分析
│   ├── lineup_planner.py    # 阵容规划
│   ├── match_history.py     # 战绩记忆（最近 5 场）
│   ├── keyboard_hook.py     # 全局键盘钩子
│   ├── status_system.py     # 状态系统（饥饿/心情/精力）
│   ├── interaction.py       # 交互动作定义
│   ├── netcut.py            # 一键拔线
│   ├── bg_knowledge.py      # 酒馆战棋知识库
│   └── config_manager.py    # 配置管理
│
├── ui/                      # 界面
│   ├── pet_window.py        # 主窗口（透明悬浮、对话面板、事件过滤）
│   ├── sprite_animator.py   # 2D 精灵动画
│   ├── gl_penguin.py        # 3D 企鹅渲染（实验性，默认关闭）
│   ├── tts_engine.py        # TTS 语音（edge-tts 软萌音 + 豆包兜底）
│   ├── speech_system.py    # 台词库
│   ├── bongo_panel.py       # Bongo 按键面板
│   └── status_bar.py        # 状态栏
│
├── resources/               # 素材
│   ├── expressions/         # 表情 PNG
│   └── stickers/            # 动画贴图
│
├── knowledge/battlegrounds/  # 战棋知识库（JSON）
├── data/cards_zhcn.json      # 卡牌数据
└── tools/                    # 开发辅助脚本
```

## 稳定性设计

- **TTS 跨线程安全**：QMediaPlayer 仅主线程操作，后台线程只合成 mp3，通过 pyqtSignal 回主线程播放
- **临时文件清理**：TTS mp3 用完即删，启动时清理残留，列表限长 4 个
- **内存防泄漏**：log_reader `_prune_ents()` 自动清理非 PLAY 区实体，总量限 3000
- **主线程防阻塞**：蒙特卡洛模拟用 n=600（非 2000），背景采样失败退避
- **跨线程 UI**：后台视觉分析通过类级 pyqtSignal 投递到主线程
- **超时保护**：屏幕分析 8 秒超时，edge-tts 合成 20 秒超时

## 技术栈

- Python 3.12
- PyQt5（QMediaPlayer/QTimer/pyqtSignal/eventFilter）
- 兼容 Chat Completions 的对话 API（实际平台与模型由本地 `ai_config.json` 的 `base_url` / `model` 决定）
- 智谱 GLM-4.6V（视觉）
- edge-tts >= 7.3.0（软萌语音；修复旧版请求被微软服务以 403 拒绝的问题）
- 豆包语音 V3（TTS 兜底）

## License

MIT

## 持续语音对话（2026-10-13 升级）

右键企鹅或托盘 → **实时语音配置** → **持续语音对话**。
默认接入 `qwen-audio-3.1-realtime-plus`（千问 AI 平台，无需业务空间 ID），支持持续收音、流式播放、静音、耳机语音打断和断线续接。
仅使用赠送额度：先在千问 AI 平台权益页面为同名模型确认“免费额度用尽即停”保护；未确认时程序阻止联网，额度耗尽后停止。
详细设置、当前限制与回滚方法见 [持续语音使用说明](docs/realtime-voice.md)。

## 普通 Edge 语音排查

普通聊天的朗读仍使用 `zh-CN-XiaoyiNeural`，语速 `+15%`、音调 `+14Hz`；助教模式语速为 `+5%`。千问实时音频仅在主动开启持续语音通话时使用。

2026-10-16 已复现旧版 `edge-tts 7.2.8` 合成时返回 HTTP 403；升级到 `7.3.0` 后合成与 Qt 播放通过。上游修复记录见 [edge-tts #490](https://github.com/rany2/edge-tts/issues/490)。升级依赖后需退出并重新启动桌宠，运行中的 Python 进程会保留已导入的旧版本。

使用桌宠的 Python 运行 `python tools/diag_tts.py` 可验证 Edge 合成及 Qt 播放。该诊断会朗读一句通用测试语，最多运行 30 秒，不使用豆包兜底或麦克风；成功返回 `ok: true`。播放状态通过后，最终听感仍取决于 Windows 输出设备及音量。

## OpenCode Go 普通聊天

本地配置可将 `base_url` 设为 `https://opencode.ai/inference/go/openai/v1`，`model` 设为 `deepseek-v4.1-flash`，API Key 仅保存在 Git 忽略的 `ai_config.json` 中。此调用消耗 Go 套餐额度；普通 Edge 朗读、视觉分析和千问持续通话仍使用各自配置。

聊天引擎为 Go 请求附带自身客户端标识和会话 ID，多轮对话复用 ID，清空历史时更新；不需要本地 CLI 转发或代理。配置更新后需重启桌宠。`python tools/test_ai_go.py` 提供不联网的会话路由检查。
