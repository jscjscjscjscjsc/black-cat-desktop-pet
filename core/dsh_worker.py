"""DSH headless sidecar: long tasks run outside Guga's Qt process."""
from collections import deque
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid

from PyQt5.QtCore import QObject, pyqtSignal

ROOT=Path(__file__).resolve().parents[1]


class DshManager(QObject):
    event=pyqtSignal(object)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.proc=None;self.thread=None;self.stop_event=threading.Event();self.lock=threading.Lock()
        self.recent=deque(maxlen=80);self.state=dict(running=False,session_id=None,last_phase=None)

    def status(self):
        with self.lock:return dict(self.state,recent=list(self.recent))

    def start(self,task,conversation_id=None,cwd=None,seconds=900,resume=None):
        task=str(task or '').strip()
        if not task or len(task)>16000:raise ValueError('DSH 任务需要 1—16000 字符')
        if type(seconds) is not int or not 30<=seconds<=1200:raise ValueError('DSH 时间预算需要 30—1200 秒')
        if self.thread and self.thread.is_alive():raise RuntimeError('DSH 子任务仍在运行；请查询状态或停止')
        cwd=Path(cwd or ROOT).expanduser().resolve()
        if not cwd.is_dir():raise ValueError('DSH 工作目录不存在')
        job_id=uuid.uuid4().hex
        self.stop_event=threading.Event()
        self.state=dict(running=True,job_id=job_id,conversation_id=conversation_id,started=time.time(),
                        session_id=resume,last_phase='starting',seconds=seconds,cwd=str(cwd))
        self.thread=threading.Thread(target=self._run,args=(job_id,task,cwd,seconds,resume),daemon=True)
        self.thread.start()
        return dict(accepted=True,job_id=job_id,message='DSH 长任务已受理；完成或失败以 sidecar 事件为准')

    def stop(self):
        self.stop_event.set();proc=self.proc
        if proc and proc.poll() is None:
            try:subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=5,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception:
                try:proc.kill()
                except Exception:pass
        return dict(requested=True,message='已请求停止 DSH 子任务')

    def _publish(self,value):
        with self.lock:self.recent.append(value)
        self.event.emit(value)

    def _run(self,job_id,task,cwd,seconds,resume):
        command='& dsh --profile headless --json '
        if resume:command+=f"--session-id '{str(resume).replace(chr(39),chr(39)*2)}' "
        command+='-'
        final_text='';error='';session_id=resume
        started=time.monotonic()
        try:
            self.proc=subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-Command',command],
                cwd=str(cwd),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                encoding='utf-8',errors='replace',bufsize=1,creationflags=subprocess.CREATE_NO_WINDOW)
            self.proc.stdin.write(task);self.proc.stdin.close()
            lines=queue.Queue()
            def reader(stream,label):
                for line in stream:lines.put((label,line))
                lines.put((label,None))
            threading.Thread(target=reader,args=(self.proc.stdout,'out'),daemon=True).start()
            threading.Thread(target=reader,args=(self.proc.stderr,'err'),daemon=True).start()
            ended=False
            while not self.stop_event.is_set() and time.monotonic()-started<seconds:
                try:label,line=lines.get(timeout=.2)
                except queue.Empty:
                    if self.proc.poll() is not None and lines.empty():break
                    continue
                if line is None:
                    if self.proc.poll() is not None:break
                    continue
                line=line.strip()
                if not line:continue
                if label=='err':error=(error+'\n'+line)[-4000:];continue
                try:event=json.loads(line)
                except ValueError:
                    error=(error+'\n'+line)[-4000:];continue
                if event.get('sessionId'):session_id=event['sessionId']
                kind=event.get('type')
                if kind=='final':final_text=str(event.get('text',''))
                if kind=='status' and event.get('phase')=='turn_end':
                    reason=event.get('reason') or {}
                    if reason.get('kind')=='error':error=str(reason.get('error') or reason)
                with self.lock:self.state.update(session_id=session_id,last_phase=event.get('phase') or kind)
                self._publish(dict(type='dsh_event',job_id=job_id,conversation_id=self.state.get('conversation_id'),event=event))
            else:
                if self.stop_event.is_set():error='用户停止'
                elif time.monotonic()-started>=seconds:error='DSH 达到本次时间预算'
                self.stop()
            self.proc.wait(timeout=5)
            ok=self.proc.returncode==0 and not error and bool(final_text.strip())
            self._publish(dict(type='dsh_completed',job_id=job_id,conversation_id=self.state.get('conversation_id'),
                ok=ok,text=final_text,session_id=session_id,error=error.strip(),returncode=self.proc.returncode))
        except FileNotFoundError:error='未找到 dsh 命令；请先安装并配置 DeepSeek Harness'
        except Exception as exc:error='DSH 子进程失败：'+type(exc).__name__
        finally:
            with self.lock:self.state['running']=False
            if error and self.proc is None:
                self._publish(dict(type='dsh_completed',job_id=job_id,conversation_id=self.state.get('conversation_id'),
                    ok=False,text='',session_id=session_id,error=error))
            self.proc=None
