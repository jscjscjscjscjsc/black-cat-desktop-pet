"""Short, factual feedback independent of whether the reasoning model finishes."""
import re
from pathlib import Path

def acknowledgement(request):
    match=re.search(r'([\w\u4e00-\u9fff .-]+\.py)',request)
    if '冒泡' in request and match:
        name=match.group(1).strip().split('下的')[-1].strip('“”「」 ')
        # Spoken ASR sometimes spells the extension out instead of writing .py.
        name='文件读写.py' if '文件读写' in request else name[-28:]
        return f'你的意思是让我在{name}里写冒泡排序。我先核对当前编辑器，然后开始。'
    summary=re.sub(r'^(用户(?:希望|要求)(?:我)?|请帮我|请)','',request).strip()
    summary=summary.split('。')[0].rstrip('，, ')
    if len(summary)>44:summary=summary[:44]+'…'
    return '收到，你想让我'+summary+'。我现在开始处理。'

def tool_feedback(name,args,result=None):
    if not isinstance(args,dict):args={}
    action=args.get('action','')
    subject=Path(args.get('path','')).name
    labels={('computer','windows'):'正在确认已打开的软件窗口',('computer','editor_context'):'正在定位编辑器的实际工作目录',
        ('computer','focus'):'正在切换到目标窗口',('computer','observe'):'正在查看目标窗口和当前内容',
        ('computer','type'):'正在向编辑器输入代码',('computer','hotkey'):'正在操作编辑器快捷键',
        ('computer','click'):'正在定位编辑区域',('computer','accessibility'):'正在读取窗口控件',
        ('computer','uia'):'正在通过结构化控件执行操作',
        ('computer','editor_select_tail'):'正在选中待修改的函数，保留此前代码',
        ('local_computer','read'):'正在读取'+(subject or '目标文件'),('local_computer','write'):'正在备份并写入'+(subject or '目标文件'),
        ('local_computer','run'):'正在执行命令并等待验证结果',('applications','open'):'正在打开目标软件'}
    summary=labels.get((name,action),'正在执行下一步操作')
    if result is not None:
        if result.get('ok') and name=='computer' and action in ('click','double_click','drag','scroll','hotkey','type','editor_select_tail','uia'):
            summary=summary.replace('正在','已发送，等待复查：',1)
        elif result.get('ok'):summary=summary.replace('正在','已完成：',1)
        else:summary='这一步没有完成，我会根据错误检查后调整。'
    return summary
