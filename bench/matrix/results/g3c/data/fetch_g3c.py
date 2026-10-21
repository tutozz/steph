#!/usr/bin/env python3
"""G3c data: fetch public sources at the default-branch HEAD, record the pinned commit, keep only
permissive licenses (MIT, Apache-2.0, BSD, ISC, Zlib, PostgreSQL, CC0-1.0). Network is used here only.

    python3 fetch_g3c.py DEST_DIR sources.json
"""
import hashlib, io, json, os, sys, tarfile, urllib.request

REPOS = {
    "python": ["python-attrs/attrs", "pytoolz/toolz", "astanin/python-tabulate", "kjd/idna", "tkem/cachetools",
               "pyparsing/pyparsing", "grantjenks/python-sortedcontainers", "jquast/wcwidth", "pytest-dev/iniconfig",
               "marshmallow-code/marshmallow"],
    "js": ["visionmedia/bytes.js", "jshttp/content-type", "jshttp/statuses", "jshttp/http-errors", "jshttp/negotiator",
           "jshttp/vary"],
    "go": ["gorilla/mux", "julienschmidt/httprouter", "BurntSushi/toml", "pkg/errors", "google/btree"],
    "rust": ["BurntSushi/walkdir", "rust-lang/glob", "rayon-rs/either", "servo/rust-fnv"],
    "c": ["yaml/libyaml", "akheron/jansson", "libexpat/libexpat", "madler/zlib", "libuv/libuv"],
    "shell": ["alexanderepstein/Bash-Snippets", "nvie/gitflow", "dylanaraps/pure-bash-bible", "junegunn/fzf"],
    "db": ["lerocha/chinook-database", "devrimgunduz/pagila"],
    "compose": ["docker/awesome-compose"],
}
ALLOWED = {"Unlicense", "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Zlib", "PostgreSQL", "CC0-1.0"}
LICENSE_NAMES = ("LICENSE", "LICENSE.txt", "LICENSE.md", "LICENSE.rst", "license", "License", "COPYING", "COPYING.md",
                 "LICENSE-MIT", "LICENSE.MIT", "LICENCE", "LICENSE-APACHE", "LICENSE.mit", "UNLICENSE", "license.md")


def spdx_of(text):
    t = " ".join(text.split())
    if "Permission is hereby granted, free of charge" in t and "WITHOUT WARRANTY OF ANY KIND" in t:
        return "MIT"
    if "Apache License" in t and "Version 2.0" in t:
        return "Apache-2.0"
    if "Redistribution and use in source and binary forms" in t:
        return "BSD-3-Clause" if ("Neither the name" in t or "names of its contributors" in t
                                  or "name of the copyright holder" in t or "name of the author" in t) else "BSD-2-Clause"
    if "Permission to use, copy, modify, and/or distribute this software for any purpose" in t:
        return "ISC"
    if "provided 'as-is', without any express or implied" in t and "altered source versions" in t.lower():
        return "Zlib"
    if "Permission to use, copy, modify, and distribute this software and its documentation for any purpose, without fee" in t:
        return "PostgreSQL"
    if "CC0 1.0 Universal" in t or "Creative Commons Legal Code CC0" in t.replace("\n", " "):
        return "CC0-1.0"
    if "free and unencumbered software released into the public domain" in t:
        return "Unlicense"
    if len(t) < 600 and "dual-licensed" in t.lower():
        return "pointer"
    return "unknown"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "g3c-data"})
    return urllib.request.urlopen(req, timeout=600).read()


def fetch_repo(dest, kind, full):
    raw = get(f"https://codeload.github.com/{full}/tar.gz/HEAD")
    with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
        commit = tf.pax_headers.get("comment", "")
        top = tf.getnames()[0].split("/")[0]
        files = {m.name.split("/", 1)[1]: m for m in tf.getmembers() if m.name.count("/") == 1 and m.isfile()}
        found = [n for n in LICENSE_NAMES if n in files]
        spdx = [x for x in (spdx_of(tf.extractfile(files[n]).read().decode("utf-8", "replace")) for n in found) if x != "pointer"]
        ok = bool(spdx) and all(x in ALLOWED for x in spdx)
        rec = {"source": full, "kind": kind, "commit": commit, "spdx": " AND ".join(sorted(set(spdx))) or "none",
               "license_files": found, "kept": ok, "tar_sha256": hashlib.sha256(raw).hexdigest()}
        if ok:
            name = full.split("/")[1]
            os.makedirs(os.path.join(dest, kind), exist_ok=True)
            members = [m for m in tf.getmembers() if not m.name.startswith("/") and ".." not in m.name.split("/")
                       and not m.isdev() and not (m.issym() and (m.linkname.startswith("/") or ".." in m.linkname.split("/")[:-1]))]
            tf.extractall(os.path.join(dest, kind), members=members)
            os.rename(os.path.join(dest, kind, top), os.path.join(dest, kind, name))
            rec["dir"] = f"{kind}/{name}"
    return rec


def main(dest, out):
    os.makedirs(dest, exist_ok=True)
    meta = []
    for kind, specs in REPOS.items():
        for spec in specs:
            try:
                rec = fetch_repo(dest, kind, spec)
            except Exception as e:
                rec = {"source": spec, "kind": kind, "kept": False, "error": repr(e)[:200]}
            print(json.dumps(rec), flush=True)
            meta.append(rec)
    json.dump(meta, open(out, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
