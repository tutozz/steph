import json,sys
sys.path.insert(0,"/root/steph-ft/loop/r3t1/src/gguf-py")
from gguf import GGUFReader
import jinja2
r=GGUFReader("dense.gguf")
tpl=r.fields["tokenizer.chat_template"].contents()
cases=json.load(open("dev50.json"))
env=jinja2.Environment(); env.globals["raise_exception"]=lambda m: (_ for _ in ()).throw(Exception(m))
import datetime; env.globals["strftime_now"]=lambda f: datetime.datetime(2026,9,28).strftime(f)
for i in [int(x) for x in sys.argv[1:]]:
    c=cases[i]
    s=env.from_string(tpl).render(messages=c["messages"],add_generation_prompt=True,bos_token="",eos_token="<|end_of_text|>")
    open(f"ec2/prompt{i}.txt","w").write(s); print(i,c["id"],len(s))
