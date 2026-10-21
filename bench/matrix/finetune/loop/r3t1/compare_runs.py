import json,glob,difflib,sys
def load(l):
    d=json.load(open(f"runs/{l}.json")); return {r["id"]:r["out"] or "" for r in d["rows"]}
def rep(o): return sum(len(o[k].split())>8 and len(set(o[k].split()))<len(o[k].split())/4 or "ineTransform" in o[k] for k in o)
refs={"dense-cpu":load("dense-cpu"),"r1-cpu":load("r1-cpu")}
for l,ref in [(x.split(":")[0],x.split(":")[1]) for x in sys.argv[1:]]:
    o=load(l); R=refs.get(ref) or load(ref)
    same=sum(o[k]==R[k] for k in o); sim=sum(difflib.SequenceMatcher(None,o[k],R[k]).ratio() for k in o)/len(o)
    print(f"{l:20s} vs {ref:12s} identical {same}/50 meansim {sim:.3f} degenerate {rep(o)}")
