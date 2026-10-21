import re,sys,os,collections,importlib.util
spec=importlib.util.spec_from_file_location("c","ec2/cmp.py")
def parse(f):
    out=collections.OrderedDict();cur=None;cnt=collections.Counter()
    for line in open(f,errors="replace"):
        m=re.search(r"common_debug_cb_eval:\s+(\S+) = \((\w+)\)\s+(\w+)\((.*)",line)
        if m:
            k=(m.group(1),m.group(3)); cnt[k]+=1; key=k+(cnt[k],)
            cur={"name":m.group(1),"op":m.group(3),"args":m.group(4)[:80]}; out[key]=cur; continue
        m=re.search(r"sum = (\S+)",line)
        if m and cur: cur["sum"]=float(m.group(1))
        m=re.search(r"maxabs = (\S+) at col (\d+) row (\d+)",line)
        if m and cur: cur["max"]=float(m.group(1)); cur["col"]=int(m.group(2)); cur["row"]=int(m.group(3))
    return out
m=sys.argv[1]; a=parse(f"ec2/{m}-cpu.txt")
big=sorted((x for x in a.values() if "max" in x), key=lambda x:-x["max"])[:6]
print("cpu largest:", [(x["name"],x["op"],round(x["max"])) for x in big])
for lab in sys.argv[2:]:
    b=parse(f"ec2/{m}-{lab}.txt"); shown=0; print("==",m,lab,"matched",len(set(a)&set(b)),"of",len(a))
    for k,x in a.items():
        y=b.get(k)
        if not y or "max" not in x or "max" not in y: continue
        r=abs(x["max"]-y["max"])/max(abs(x["max"]),1e-3)
        if r>float(os.environ.get("T","0.05")) or y["max"]!=y["max"]:
            print(f'{x["name"]:16s} {x["op"]:9s} cpu max {x["max"]:.6g} (c{x["col"]} r{x["row"]}) | {lab} max {y["max"]:.6g} (c{y["col"]} r{y["row"]}) | {x["args"]}')
            shown+=1
            if shown>=int(os.environ.get("N","6")): break
