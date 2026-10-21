# DSH sidecar 接入

咕嘎把长任务交给独立 `dsh` 进程，避免让两套 Agent 在同一个 Qt 进程里争抢会话、麦克风和工具状态。咕嘎外壳负责声音、权限、气泡、停止和汇报，DSH 负责长时多阶段执行。

## 前置条件

- 安装 `dsh`，确保 `dsh --version` 可运行。
- 通过 DSH 自己的配置或登录设置模型凭据。
- 用以下命令确认事件协议可用：

```powershell
@'
回答一个词：READY
'@ | dsh --profile headless --json -
```

正常输出至少包含 `session`、`status` 和 `final` NDJSON 事件。若出现 AUTH/401，需要先在 DSH 侧更换有效凭据。

## 从咕嘎调用

对咕嘎说：“这个任务很复杂，交给 DSH 长任务执行器，完成后告诉我。”模型会调用 `dsh_task(action=start, task=..., seconds=...)`。`start` 返回只代表子进程已受理，不代表任务完成；后续进度和结果通过节点事件流回到原会话、气泡和长语音。

支持：

- `start`：启动 headless sidecar，默认最多 900 秒。
- `status`：查看运行状态和最近事件。
- `stop`：终止 DSH 进程树。
- `session_id`：继续一个已有 DSH session。
- `cwd`：指定已存在的工作目录。

## 事件映射

- `session`：记录 DSH session ID。
- `status/turn_start/step_start`：节流后显示进度，避免每步都发语音。
- `dsh_completed`：仅按 DSH 最终事件和退出码确定成功/失败。
- stderr 只保存为错误摘要，不朗读密钥或完整响应体。

DSH 是独立进程，拥有自己的工具、权限和工作区；它不会自动获得咕嘎语音调用或战棋控制。需要共享能力时通过 MCP、CLI 或明确的文件/事件协议连接。
