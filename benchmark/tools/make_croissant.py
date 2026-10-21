#!/usr/bin/env python3
"""Write data/croissant.json: MLCommons Croissant 1.0 metadata with Responsible AI fields.

    python3 benchmark/tools/make_croissant.py

Rerun after every change to data/v1 (checksums).

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1]
DATA = BENCH / "data"

CONTEXT = {
    "@language": "en", "@vocab": "https://schema.org/", "sc": "https://schema.org/",
    "cr": "http://mlcommons.org/croissant/", "rai": "http://mlcommons.org/croissant/RAI/",
    "dct": "http://purl.org/dc/terms/", "citeAs": "cr:citeAs", "column": "cr:column",
    "conformsTo": "dct:conformsTo", "data": {"@id": "cr:data", "@type": "@json"},
    "dataType": {"@id": "cr:dataType", "@type": "@vocab"}, "examples": {"@id": "cr:examples", "@type": "@json"},
    "extract": "cr:extract", "field": "cr:field", "fileProperty": "cr:fileProperty", "fileObject": "cr:fileObject",
    "fileSet": "cr:fileSet", "format": "cr:format", "includes": "cr:includes", "isLiveDataset": "cr:isLiveDataset",
    "jsonPath": "cr:jsonPath", "key": "cr:key", "md5": "cr:md5", "parentField": "cr:parentField", "path": "cr:path",
    "recordSet": "cr:recordSet", "references": "cr:references", "regex": "cr:regex", "repeated": "cr:repeated",
    "replace": "cr:replace", "separator": "cr:separator", "source": "cr:source", "subField": "cr:subField",
    "transform": "cr:transform",
}

FIELDS = [
    ("id", "sc:Text", "Stable case identifier, identical across languages."),
    ("lang", "sc:Text", "en, fr, de, es, pt or ru."),
    ("split", "sc:Text", "dev or test."),
    ("category", "sc:Text", "One of 13 categories."),
    ("origin", "sc:Text", "real-anonymized or synthetic."),
    ("task", "sc:Text", "summary (one output) or qa (history plus question)."),
    ("cmd", "sc:Text", "Command line (summary)."),
    ("exit", "sc:Integer", "Exit code (summary)."),
    ("output", "sc:Text", "Raw terminal output, 5 to 400 lines (summary)."),
    ("question", "sc:Text", "Question about the session history (qa)."),
    ("expected", "sc:Text", "Regexes the spoken answer must match (repeated)."),
    ("forbidden", "sc:Text", "Regexes the spoken answer must not match (repeated)."),
    ("reference", "sc:Text", "Reference spoken answer."),
    ("max_words", "sc:Integer", "Word budget before the length penalty."),
]


def citation() -> dict:
    """Author, version and date come from CITATION.cff, the single source for them."""
    text = (BENCH / "CITATION.cff").read_text(encoding="utf-8")
    field = lambda key: re.search(rf"^\s*-?\s*{key}:\s*\"?([^\"\n]+)\"?$", text, re.M).group(1).strip()
    return {"family": field("family-names"), "given": field("given-names"), "version": field("version"),
            "date": field("date-released"), "url": field("url"), "repo": field("repository-code")}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    cite = citation()
    URL = cite["url"]
    RAW = cite["repo"].replace("github.com", "raw.githubusercontent.com") + "/master/benchmark/data/"
    files = sorted((DATA / "v1").glob("*/*.jsonl"))
    distribution = [{
        "@type": "cr:FileObject", "@id": f"v1/{p.parent.name}/{p.name}", "name": f"{p.parent.name}-{p.stem}",
        "contentUrl": f"{RAW}v1/{p.parent.name}/{p.name}", "encodingFormat": "application/jsonlines",
        "sha256": sha256(p)} for p in files]
    distribution.append({"@type": "cr:FileSet", "@id": "cases", "name": "cases",
                         "encodingFormat": "application/jsonlines", "includes": "v1/*/*.jsonl",
                         "containedIn": [{"@id": d["@id"]} for d in distribution]})
    fields = [{
        "@type": "cr:Field", "@id": f"cases/{name}", "name": name, "description": desc, "dataType": dtype,
        **({"repeated": True} if name in ("expected", "forbidden") else {}),
        "source": {"fileSet": {"@id": "cases"}, "extract": {"column": name}}} for name, dtype, desc in FIELDS]
    author = f"{cite['given']} {cite['family']}"
    meta = {
        "@context": CONTEXT,
        "@type": "sc:Dataset",
        "conformsTo": ["http://mlcommons.org/croissant/1.0", "http://mlcommons.org/croissant/RAI/1.0"],
        "name": "Steph Speak Bench",
        "description": ("Multilingual (English, French, German, Spanish, Portuguese, Russian) benchmark of "
                        "spoken summaries of terminal command outputs by local LLMs, for blind and visually "
                        "impaired users: short answer, exact facts, nothing invented, time to first token."),
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "url": URL,
        "version": cite["version"],
        "datePublished": cite["date"],
        "creator": {"@type": "sc:Person", "name": author},
        "inLanguage": ["en", "fr", "de", "es", "pt", "ru"],
        "keywords": ["benchmark", "accessibility", "screen reader", "terminal", "summarization", "hallucination",
                     "small language models", "latency"],
        "citeAs": f"{cite['family']}, {cite['given'][0]}. ({cite['date'][:4]}). Steph Speak Bench: spoken summaries of "
                  f"terminal output by local LLMs (v{cite['version']}). {URL}",
        "isLiveDataset": False,
        "distribution": distribution,
        "recordSet": [{"@type": "cr:RecordSet", "@id": "cases", "name": "cases", "key": {"@id": "cases/id"},
                       "field": fields}],
        "rai:dataCollection": ("Real cases: outputs captured on the author's own Linux and macOS machines while "
                               "developing a talking terminal, then anonymized by hand. Synthetic cases: written "
                               "for the benchmark to look like the real tools, generated deterministically."),
        "rai:dataCollectionType": ["Manual Human Curation", "Software Collection", "Synthetic Data"],
        "rai:dataCollectionTimeframe": ["2026-09-01", "2026-09-27"],
        "rai:dataCollectionRawData": "Terminal outputs of standard command-line tools (compilers, git, package "
                                     "managers, network and disk tools, container tools, test runners).",
        "rai:dataPreprocessingProtocol": ("Anonymization: user, host and project names replaced; LAN, VPN and public "
                                          "addresses remapped to private or documentation ranges; MAC addresses, "
                                          "UUIDs, serial numbers and IPv6 interface identifiers removed. Every case "
                                          "passes an automated PII scanner with zero findings."),
        "rai:dataAnnotationProtocol": ("Each case carries expected facts (regular expressions), forbidden content "
                                       "and a reference answer, written by the author and checked automatically: "
                                       "the reference scores 100 %, every number it states appears in the model "
                                       "input, patterns are accent-free."),
        "rai:dataAnnotationPlatform": "Plain text editor and the benchmark's own build checks.",
        "rai:annotationsPerItem": "1",
        "rai:dataUseCases": ["Evaluation of LLMs and prompts for spoken terminal assistance. The test split is "
                             "for evaluation only; the dev split may be used for tuning."],
        "rai:dataLimitations": ("105 cases per language; regex scoring rewards stated facts and can miss a "
                                "correct paraphrase or a subtle hallucination; outputs cover common Linux and macOS "
                                "tools, not Windows; references reflect one author's notion of a useful summary."),
        "rai:dataBiases": ("Tool mix follows a developer and home-server workflow; six languages (en, fr, de, "
                           "es, pt, ru), most other languages absent; synthetic outputs may be cleaner than "
                           "real ones; for de/es/pt/ru most tool outputs stay English/French (untranslated by "
                           "the tool itself, see docs/research-terminal-languages.md), only the expected facts "
                           "and reference answer are translated, plus a handful of genuine new-language tool "
                           "captures (apt, git, df, du, ls)."),
        "rai:personalSensitiveInformation": "None. Real outputs were anonymized and scanned.",
        "rai:dataSocialImpact": ("Aims to improve accessibility of command-line work for blind and visually "
                                 "impaired people by making local, private assistants measurable."),
        "rai:dataReleaseMaintenancePlan": ("Versioned directories (data/v1, v2...). A released version is never "
                                           "edited in place; fixes ship as a new version with a changelog."),
    }
    out = DATA / "croissant.json"
    out.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"written {out} ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
