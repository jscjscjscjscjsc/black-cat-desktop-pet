"""Deterministic completion checks for tool side effects and verification receipts."""

INPUT_ACTIONS={"click","double_click","drag","scroll","hotkey","type","editor_select_tail","uia"}
VERIFY_ACTIONS={"observe","accessibility"}
ACTION_WORDS=("打开","启动","关闭","读取","修改","写入","保存","运行","安装","下载",
              "删除","移动","复制","重命名","上传","提交","点击","输入","执行","修复",
              "测试","检查窗口","截屏","看屏幕","整理文件","创建文件")
QUESTION_WORDS=("如何","怎么","为什么","解释一下","有什么区别","是什么","教我","步骤是")


def requires_execution(prompt):
    text=str(prompt or "").lower()
    return any(word in text for word in ACTION_WORDS) and not any(word in text for word in QUESTION_WORDS)


class ExecutionLedger:
    """Track only externally consequential work. Read-only failures stay recoverable."""
    def __init__(self):
        self.pending=[]
        self.failures={}
        self.completed=[]
        self.evidence_count=0

    @staticmethod
    def _ok(value):
        return bool(isinstance(value,dict) and value.get("ok") is True)

    def record(self,name,args,value):
        args=args if isinstance(args,dict) else {}
        value=value if isinstance(value,dict) else {}
        action=str(args.get("action",""))
        result=value.get("result") if isinstance(value.get("result"),dict) else {}
        ok=self._ok(value)
        if name not in ("task_plan","self_ask") and ok:
            self.evidence_count+=1
        if name=="computer":
            if action in INPUT_ACTIONS and ok:
                item=dict(category="computer_input",action=action,hwnd=args.get("hwnd"),
                          description=f"computer.{action} 已发送，尚未复查")
                self.pending.append(item)
                self.failures.pop("computer",None)
            elif action in VERIFY_ACTIONS and ok:
                self.pending=[x for x in self.pending if x.get("category")!="computer_input"]
                self.failures.pop("computer",None)
                self.completed.append(dict(category="computer_verified",action=action))
            elif action in INPUT_ACTIONS and not ok:
                self.failures["computer"]=f"computer.{action} 未成功"
            return
        if name=="local_computer":
            if action in ("write","run"):
                category="local_write" if action=="write" else "local_run"
                if ok and (action=="write" and result.get("written") or
                           action=="run" and result.get("exit_code")==0 and not result.get("stopped")):
                    self.failures.pop(category,None)
                    self.completed.append(dict(category=category,action=action,path=args.get("path")))
                else:
                    self.failures[category]=f"local_computer.{action} 没有成功回执"
            return
        if name=="ecosystem":
            if action=="call":
                self.failures.pop("ecosystem",None) if ok else self.failures.update(ecosystem="外部软件工具调用失败")
            return
        if name=="battleground":
            if action=="netcut" and not ok:
                self.failures["battleground_netcut"]="拔线请求失败或未获确认"
            elif action=="netcut" and ok:
                self.failures.pop("battleground_netcut",None)
                self.completed.append(dict(category="battleground_netcut",action=action))

    def blockers(self):
        reasons=[item["description"] for item in self.pending]
        reasons.extend(self.failures.values())
        return reasons

    def summary(self):
        return dict(pending=list(self.pending),failures=dict(self.failures),evidence_count=self.evidence_count,
                    completed=list(self.completed[-30:]))
