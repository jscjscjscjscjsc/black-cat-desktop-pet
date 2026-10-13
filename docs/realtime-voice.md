# 咕嘎持续语音升级

当前默认模型：`qwen-audio-3.1-realtime-plus`，北京地域，音色 `longanqian_v3.1`。
采用官方 WebSocket PCM 协议：输入 16kHz / 输出 24kHz / 16bit / 单声道；语义轮次 `smart_turn`。

## 使用

1. 在百炼免费额度页面查找**完全相同的模型ID**，确认有未过期额度，开启“免费额度用完即停”，等待设置生效。
2. 右键企鹅或托盘 → “阿里语音配置”，填写该地域、该业务空间的 API Key 和业务空间 ID。
3. 已完成第1步后勾选服务端开关确认项，保存。程序的确认项不能代替百炼服务端开关。
4. “持续语音对话（阿里）”开始通话。程序不在启动时自动开启麦克风。
5. 可静音、打断、结束；关闭通话窗口也会停止收音并释放设备。

外放模式在AI生成/播放期间暂停输入，避免回录。耳机模式允许双向收音、语音打断；当前没有软件声学回声消除。
默认通话总时限4小时，10分钟无语音自动结束，配置可调整。断网最多连续尝试5次，然后停止。
会话连接满110分钟后在回复结束处续接，携带最多80条近期文字记录；记录只在内存中，结束后不保存。
Qwen-Audio模型原生音频历史容量与会话持续时长不同，不能保证长聊时记住所有细节。

## 免费额度保护

- 只允许北京地域；未确认当前模型已开启服务端保护时，程序拒绝联网。
- 服务端返回 `AllocationQuota.FreeTierOnly` 或 HTTP 403 后结束，不重试，不转其他模型。
- 本地不能通过语音响应准确获知账号剩余额度，因此必须依靠阿里服务端开关，不能靠估算Token防扣费。
- Key保存在Git忽略的 `ai_config.json`；不写日志，不提交Git。

## 回滚

升级前提交：`9140bbf`；标签：`backup/guga-before-realtime-20261013`。
升级分支：`codex/guga-realtime-voice`。
退出桌宠后，使用 `git switch main` 返回升级前代码；升级版本仍在独立分支。
`ai_config.json` 不随Git切换，保留本地Key配置；旧版会忽略新增语音配置。
历史版本含旧的硬编码凭据，回滚备份仅本地保存，不能直接公开或推送。

## 验证

`python tools/test_realtime_voice.py`：离线验证停止释放设备、队列上限、外放收音抑制、取消旧音频、上下文限制、配置保存和免费额度保护。
`python tools/smoke_voice_ui.py`：有限时间的离线桌宠与语音面板集成检查。
真实麦克风、音质、延迟、网络重连和长时间持续通话仍需接入后实测。

官方依据：
- https://help.aliyun.com/zh/model-studio/qwen-audio-realtime-user-guides
- https://help.aliyun.cn/zh/model-studio/new-free-quota
