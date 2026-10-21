"""NDJSON speaker gate worker; keeps ONNX Runtime isolated from Qt/pythonnet."""
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.speaker_gate import LocalSpeakerGate


def main():
    gate=None
    for line in sys.stdin:
        try:request=json.loads(line)
        except ValueError:continue
        command=request.get('cmd')
        try:
            if command=='init':
                gate=LocalSpeakerGate(request['profile'],request['model'],request.get('threshold'))
                answer=dict(ok=True)
            elif command=='audio' and gate:
                out=gate.process_pcm(base64.b64decode(request.get('pcm','')))
                answer=dict(ok=True,out=base64.b64encode(out).decode('ascii'),state=gate.state,score=gate.last_score)
            elif command=='close':
                answer=dict(ok=True);print(json.dumps(answer),flush=True);return
            else:answer=dict(ok=False,error='声纹进程未初始化或命令无效')
        except Exception as exc:answer=dict(ok=False,error=str(exc))
        print(json.dumps(answer,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
