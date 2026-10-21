# Points the untouched A7 judge_lib at this session's server, then runs the given tool.
import os, runpy, sys
import judge_lib
judge_lib.URL = f"http://127.0.0.1:{os.environ['JUDGE_PORT']}/v1/chat/completions"
tool = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(tool, run_name="__main__")
