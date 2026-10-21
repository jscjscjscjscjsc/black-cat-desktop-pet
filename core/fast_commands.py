"""Zero-LLM command router for latency-sensitive, low-ambiguity voice actions."""
import os
import re
import urllib.parse
import webbrowser


SITE_ALIASES={
    '百度':'https://www.baidu.com','必应':'https://www.bing.com','谷歌':'https://www.google.com',
    'google':'https://www.google.com','b站':'https://www.bilibili.com','哔哩哔哩':'https://www.bilibili.com',
    'bilibili':'https://www.bilibili.com','github':'https://github.com','知乎':'https://www.zhihu.com',
    'youtube':'https://www.youtube.com','微博':'https://weibo.com',
}
APP_ALIASES={
    '记事本':'notepad.exe','计算器':'calc.exe','画图':'mspaint.exe','资源管理器':'explorer.exe',
    '设置':'ms-settings:','终端':'wt.exe','命令提示符':'cmd.exe','任务管理器':'taskmgr.exe',
}
STOP_PHRASES=('停止对话','结束对话','停止通话','结束通话','停止语音','结束语音','别说了','不用聊了')


def normalize(text):
    text=str(text or '').strip().strip('。！？!?，, ')
    return re.sub(r'\s+',' ',text)


def _open_target(target):
    target=target.strip().strip('“”"\' ')
    if target in SITE_ALIASES:
        url=SITE_ALIASES[target]
    elif re.fullmatch(r'[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/.*)?',target):
        url='https://'+target
    elif target.startswith(('http://','https://')):
        url=target
    else:
        return None
    webbrowser.open(url,new=2)
    return dict(kind='url',target=url,message='已请求浏览器打开')


def _open_app(target):
    target=target.strip().strip('“”"\' ')
    alias=APP_ALIASES.get(target)
    if alias:
        os.startfile(alias)
        return dict(kind='app',target=target,message='Windows 已接受启动请求')
    from core.authorized_apps import AuthorizedApps
    result=AuthorizedApps().open(target)
    return dict(kind='app',target=target,message=result.get('message','Windows 已接受启动请求'))


def match(text):
    """Parse a high-confidence local action without performing it."""
    value=normalize(text)
    prefix=dict(source_text=value)
    if value in STOP_PHRASES:
        return dict(prefix,matched=True,action='stop_call',silent=True,priority='critical',
                    message='结束实时语音通话')
    match=re.fullmatch(r'(?:请在浏览器)?(?:打开|访问|前往)(?:一下)?(?:网页|网站|页面)?\s*(.+)',value)
    if match:
        target=match.group(1).strip().strip('“”"\' ')
        if target in SITE_ALIASES:
            url=SITE_ALIASES[target]
        elif re.fullmatch(r'[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/.*)?',target):
            url='https://'+target
        elif target.startswith(('http://','https://')):
            url=target
        else:
            url=None
        if url:
            return dict(prefix,matched=True,action='open_url',silent=True,priority='fast',kind='url',target=url)
    match=re.fullmatch(r'(?:帮我|请)?(?:搜索|搜一下|查一下|查查)\s*(.+)',value)
    if match:
        query=match.group(1).strip()
        if query and len(query)<=300:
            url='https://www.baidu.com/s?wd='+urllib.parse.quote(query)
            return dict(prefix,matched=True,action='web_search',silent=True,priority='fast',kind='url',target=url)
    match=re.fullmatch(r'(?:帮我|请)?打开\s*(.+)',value)
    if match:
        target=match.group(1).strip()
        if target in ('浏览器','默认浏览器'):
            return dict(prefix,matched=True,action='open_app',silent=True,priority='fast',kind='app',target='浏览器')
        if target and len(target)<=80:
            return dict(prefix,matched=True,action='open_app',silent=True,priority='fast',kind='app',target=target)
    return dict(matched=False,action='none',silent=False)


def execute(result):
    values=dict(result or {})
    if not values.get('matched'):return dict(ok=False,error='没有匹配的快速命令')
    if values.get('action')=='stop_call':return dict(ok=True,message='结束实时语音通话')
    if values.get('kind')=='url':
        webbrowser.open(values['target'],new=2)
        return dict(ok=True,message='已请求浏览器打开')
    if values.get('kind')=='app':
        return dict(ok=True,**_open_app(values['target']))
    return dict(ok=False,error='未知快速动作')


def route(text):
    """Compatibility helper for scripts and tests."""
    parsed=match(text)
    return dict(parsed,execution=execute(parsed)) if parsed.get('matched') else parsed
