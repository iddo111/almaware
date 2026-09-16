import sys, glob, torch, numpy as np, judge as J
from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq
M="ivrit-ai/whisper-large-v3-turbo"
p=AutoProcessor.from_pretrained(M); m=AutoModelForSpeechSeq2Seq.from_pretrained(M, dtype=torch.float16).to("cuda").eval()
fs=[]
for a in sys.argv[1:]: fs+=sorted(glob.glob(a))
for i in range(0,len(fs),8):
    ch=fs[i:i+8]; ws=[J.read_wav(f) for f in ch]
    inp=p(ws, sampling_rate=16000, return_tensors="pt").to("cuda")
    with torch.no_grad():
        ids=m.generate(inp.input_features.half(), language="he", task="transcribe", max_new_tokens=12)
    for f,t in zip(ch,p.batch_decode(ids, skip_special_tokens=True)): print("%-34s %s"%(f.split("/")[-1],t.strip()), flush=True)
