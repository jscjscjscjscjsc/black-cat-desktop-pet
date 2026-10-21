import os
import subprocess
import time
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.fast_commands import match,execute
from core.speaker_gate import SpeakerGate,SAMPLE_RATE


class FastCommandTests(unittest.TestCase):
    def test_stop_and_url_are_parsed_without_llm(self):
        self.assertEqual(match('停止对话')['action'],'stop_call')
        self.assertEqual(match('打开 github')['target'],'https://github.com')
        self.assertEqual(match('访问 example.com')['target'],'https://example.com')
        self.assertEqual(match('搜索 Python 教程')['action'],'web_search')

    def test_execution_uses_browser_or_app_without_model(self):
        with patch('webbrowser.open') as browser:
            result=execute(dict(matched=True,action='open_url',kind='url',target='https://example.com'))
            browser.assert_called_once_with('https://example.com',new=2)
        self.assertTrue(result['ok'])
        with patch('os.startfile') as start:
            result=execute(dict(matched=True,action='open_app',kind='app',target='记事本'))
            start.assert_called_once_with('notepad.exe')
        self.assertTrue(result['ok'])


class SpeakerGateTests(unittest.TestCase):
    def test_owner_audio_unlocks_and_foreign_audio_is_gated(self):
        owner=np.sin(np.arange(SAMPLE_RATE*2)*.06).astype(np.float32)*.08
        raw=(np.clip(owner,-1,1)*32767).astype(np.int16).tobytes()
        with tempfile.TemporaryDirectory() as folder:
            profile=Path(folder)/'owner.npy'
            code=("import numpy as np;from core.speaker_gate import _embedding;"
                  "a=np.sin(np.arange(32000)*.06).astype(np.float32)*.08;v=_embedding(a);v/=np.linalg.norm(v);"
                  f"np.save(r'{profile}',v)")
            subprocess.run([sys.executable,'-X','utf8','-c',code],cwd=str(ROOT),check=True)
            outputs=[];gate=SpeakerGate(profile_path=profile,threshold=.5,emit=outputs.append)
            try:
                for i in range(8):
                    gate.submit(raw[i*4000:(i+1)*4000]);time.sleep(.06)
                deadline=time.monotonic()+3
                while gate.state!='owner' and time.monotonic()<deadline:time.sleep(.05)
                self.assertEqual(gate.state,'owner');self.assertTrue(any(outputs))
            finally:gate.close()
            foreign=(np.random.default_rng(3).normal(0,.08,SAMPLE_RATE).clip(-1,1)*32767).astype(np.int16).tobytes()
            outputs=[];gate=SpeakerGate(profile_path=profile,threshold=.85,emit=outputs.append)
            try:
                states=[]
                for i in range(12):
                    gate.submit(foreign[(i%8)*4000:((i%8)+1)*4000]);time.sleep(.1);states.append(gate.state)
                deadline=time.monotonic()+.5
                while time.monotonic()<deadline:states.append(gate.state);time.sleep(.05)
                self.assertIn('rejected',states)
            finally:gate.close()


if __name__=='__main__':unittest.main()
