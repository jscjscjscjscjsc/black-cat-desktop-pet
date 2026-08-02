# 黑猫桌宠

一个 Windows 桌面宠物：带有状态动画、键盘互动、对话面板与语音功能。

## 复刻说明

这是一个可直接运行的 Windows 桌宠源码项目。其他 AI 智能体可根据仓库中的 Python 源码、表情素材、依赖清单和中文使用说明复刻完整功能，不需要额外构建产物。

运行环境：Windows 10/11、Python 3.10+。

## 运行

```powershell
pip install -r requirements.txt
python main.py
```

也可使用 `启动黑猫.bat`。

## 复刻入口

1. 阅读 `使用说明.txt` 与 `requirements.txt`。
2. 从 `main.py` 启动应用。
3. 核心行为位于 `core/`，界面与动画位于 `ui/`，素材位于 `resources/expressions/`。

## 结构

- `core/`：状态、键盘钩子与交互逻辑
- `ui/`：窗口、动画、状态栏与语音 UI
- `resources/expressions/`：桌宠表情素材
