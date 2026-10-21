#!/usr/bin/env python3
"""T5 : puissance du banc de 36 cas (X1, tour 1).

Bootstrap apparié par cas (10 000 tirages) sur la qualité v2 et les inventions au juge, à partir
des sorties par cas déjà produites ; écart minimal détectable (alpha 0,05 bilatéral, puissance
80 %) et taille de banc nécessaire. Ne lance aucun modèle.

    python3 bench_power.py <dossier_des_bancs_p15_a1000> <sortie.json>
"""

import glob
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from rescore import load_facts, score_case  # noqa: E402
from score import HOLDOUT, clean  # noqa: E402

RES = HERE / "results" / "finetune"
SSB = HERE.parents[1] / "benchmark" / "results"
CASES = [f"fx{i:02d}" for i in range(31)] + ["df_proxmox", "ip_a_proxmox", "qa0", "qa1", "qa2"]
SEEDS = ("b7", "b42", "b123")
Z = 1.959964 + 0.841621
B = 10_000
RNG = np.random.default_rng(20260928)
FACTS = load_facts(HERE / "facts.v2.json")
# Cas contestés par docs/efficiency.md et docs/audit-bench.md : entrée de banc défectueuse,
# valeurs recopiées des exemples du prompt, ou verdict du juge révisé en faux positif.
CONTESTED_FACTS = {"fx00", "fx01", "fx08", "fx11", "fx16", "fx20", "fx27", "qa0"}
CONTESTED_INVENTIONS = {"fx04", "fx08", "fx22", "fx24"}


def seed_files(pattern):
    return [pattern.format(s=s) for s in SEEDS]


def v2_matrix(paths):
    """Scores par cas (lignes : graines, colonnes : CASES), NaN si absent."""
    m = np.full((len(paths), len(CASES)), np.nan)
    for i, p in enumerate(paths):
        for r in json.load(open(p))["rows"]:
            if r.get("out") is None:
                continue
            fx = r["fixture"]
            if fx in CASES:
                m[i, CASES.index(fx)] = score_case(FACTS, fx, r["kind"], clean(r["out"]))
    return m


def boot_mean_ci(d):
    d = d[~np.isnan(d)]
    idx = RNG.integers(0, len(d), size=(B, len(d)))
    bs = d[idx].mean(axis=1)
    return float(d.mean()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)), float(d.std(ddof=1)), len(d)


def sign_test_p(pos, neg):
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def fisher_p(a, n1, b, n2):
    """Test exact de Fisher bilatéral sur deux proportions a/n1 et b/n2."""
    tot, k = n1 + n2, a + b

    def pmf(x):
        return math.comb(n1, x) * math.comb(n2, k - x) / math.comb(tot, k)
    p0 = pmf(a)
    return min(1.0, sum(pmf(x) for x in range(max(0, k - n2), min(k, n1) + 1) if pmf(x) <= p0 * (1 + 1e-9)))


def mde(sd, n):
    return Z * sd / math.sqrt(n)


def n_needed(sd, delta):
    return math.ceil((Z * sd / delta) ** 2)


V2_GROUPS = {
    "p15_a1000": None,
    "soup_uniform_q4": str(RES / "soup-granite-uniform-Q4_K_M-{s}.json"),
    "soup_uniform_q8": str(RES / "soup-granite-uniform-Q8_0-{s}.json"),
    "soup_greedy_q4": str(RES / "soup-granite-greedy-Q4_K_M-{s}.json"),
    "soup_seed42_q4": str(RES / "soup-granite-seed42-Q4_K_M-{s}.json"),
    "judged_granite_s42_q4": str(RES / "judged-granite-350m-s42-Q4_K_M-{s}.json"),
    "judged_granite_s42_q8": str(RES / "judged-granite-350m-s42-Q8_0-{s}.json"),
    "judged_granite_s7_q4": str(RES / "judged-granite-350m-s7-Q4_K_M-{s}.json"),
    "compact_granite200": str(RES / "compact" / "granite-200tok-{s}.json"),
    "compact_granite300": str(RES / "compact" / "granite-300tok-{s}.json"),
}
V2_PAIRS = [
    ("soup_uniform_q4", "soup_greedy_q4", "deux soupes Granite, même harnais"),
    ("soup_uniform_q4", "soup_seed42_q4", "soupe contre graine seule"),
    ("soup_greedy_q4", "soup_seed42_q4", "soupe gloutonne contre graine seule"),
    ("soup_uniform_q4", "soup_uniform_q8", "même soupe, Q4 contre Q8"),
    ("judged_granite_s42_q4", "judged_granite_s7_q4", "deux graines d'entraînement"),
    ("judged_granite_s42_q4", "judged_granite_s42_q8", "même modèle, Q4 contre Q8"),
    ("compact_granite200", "compact_granite300", "même modèle, deux budgets d'entrée"),
]


def v2_section(p15_dir):
    groups = {}
    for name, pat in V2_GROUPS.items():
        paths = (sorted(glob.glob(str(Path(p15_dir) / "*-b*.json")), key=lambda p: SEEDS.index(p.rsplit("-", 1)[1][:-5]))
                 if pat is None else seed_files(pat))
        m = v2_matrix(paths)
        per_case_seed_sd = np.nanstd(m, axis=0, ddof=1)
        groups[name] = {
            "files": [Path(p).name for p in paths],
            "per_seed_v2": [round(100 * float(np.nanmean(r)), 1) for r in m],
            "v2": round(100 * float(np.nanmean(m)), 1),
            "holdout": round(100 * float(np.nanmean(m[:, [CASES.index(c) for c in CASES if c in HOLDOUT]])), 1),
            "v2_without_contested": round(100 * float(np.nanmean(m[:, [CASES.index(c) for c in CASES if c not in CONTESTED_FACTS]])), 1),
            "seed_only_se_pts": round(100 * float(np.sqrt(np.nanmean(per_case_seed_sd ** 2) / len(SEEDS) / len(CASES))), 2),
            "_m": m,
        }
        g = groups[name]
        g["case_boot_ci_pts"] = [round(100 * x, 1) for x in boot_mean_ci(np.nanmean(m, axis=0))[1:3]]
    pairs, sds, sds_hold = [], [], []
    hold_idx = [CASES.index(c) for c in CASES if c in HOLDOUT]
    for a, b, why in V2_PAIRS:
        d = np.nanmean(groups[a]["_m"], axis=0) - np.nanmean(groups[b]["_m"], axis=0)
        mean, lo, hi, sd, n = boot_mean_ci(d)
        _, hlo, hhi, hsd, hn = boot_mean_ci(d[hold_idx])
        sds.append(sd)
        sds_hold.append(hsd)
        pairs.append({"a": a, "b": b, "why": why, "diff_pts": round(100 * mean, 1),
                      "ci95_pts": [round(100 * lo, 1), round(100 * hi, 1)],
                      "holdout_ci95_pts": [round(100 * hlo, 1), round(100 * hhi, 1)],
                      "sd_case_diff_pts": round(100 * sd, 1), "n": n,
                      "discordant_cases": int(np.sum(np.abs(d) > 1e-9))})
    sd_pool = float(np.sqrt(np.mean(np.square(sds))))
    sd_hold = float(np.sqrt(np.mean(np.square(sds_hold))))
    for g in groups.values():
        del g["_m"]
    return groups, pairs, sd_pool, sd_hold


def ids(lst):
    return {i.split("@")[0] for i in lst}


def inv_vector(id_sets):
    return np.array([[1.0 if c in s else 0.0 for c in CASES] for s in id_sets]).mean(axis=0)


def inventions_section():
    p17 = json.load(open(RES / "p17" / "p17-summary.json"))
    runs = {
        "p15_uniform_3080": [ids(p17["p15_uniform_3080"]["judge"][s]["invention_ids"]) for s in SEEDS],
        "p17_ep3": [ids(p17["p17_lr2e5_ep3"]["judge"][s]["invention_ids"]) for s in SEEDS],
        "p17_ep12": [ids(p17["p17_lr2e5_ep12"]["judge"][s]["invention_ids"]) for s in SEEDS],
    }
    for jf in ("judge-soup.json", "judge-judged.json"):
        for k, v in json.load(open(RES / jf))["par_modele"].items():
            if "granite" in k and "cas_inventions" in v:
                runs[k.replace(".json", "")] = [ids(c["id"] for c in v["cas_inventions"] if not c.get("discutable"))]
    pairs_spec = [
        ("p15_uniform_3080", "p17_ep12", "P15 -> P17 (décision P17)"),
        ("p17_ep3", "p17_ep12", "P17 3 contre 12 époques"),
        ("p15_uniform_3080", "p17_ep3", "P15 -> P17 3 époques"),
        ("soup-granite-uniform-Q4_K_M-b42", "soup-granite-greedy-Q4_K_M-b42", "deux soupes, une graine de banc"),
        ("soup-granite-uniform-Q4_K_M-b42", "soup-granite-uniform-Q8_0-b42", "même soupe Q4 contre Q8"),
        ("soup-granite-uniform-Q4_K_M-b42", "soup-granite-seed42-Q4_K_M-b42", "soupe contre graine seule"),
        ("judged-granite-350m-s42-Q4_K_M-b42", "judged-granite-350m-s42-Q8_0-b42", "même modèle Q4 contre Q8"),
    ]
    out, sds = [], []
    for a, b, why in pairs_spec:
        va, vb = inv_vector(runs[a]), inv_vector(runs[b])
        d = va - vb
        mean, lo, hi, sd, n = boot_mean_ci(d)
        sds.append(sd)
        robust = [round(sum(len(x - CONTESTED_INVENTIONS) for x in runs[k]) / len(runs[k]), 2) for k in (a, b)]
        out.append({"a": a, "b": b, "why": why, "seeds": [len(runs[a]), len(runs[b])],
                    "inv_per36_without_contested": robust,
                    "inv_per36_a": round(36 * float(va.mean()), 2), "inv_per36_b": round(36 * float(vb.mean()), 2),
                    "diff_per36": round(36 * mean, 2), "ci95_per36": [round(36 * lo, 2), round(36 * hi, 2)],
                    "discordant_cases": int(np.sum(np.abs(d) > 1e-9)),
                    "sign_test_p": round(sign_test_p(int(np.sum(d > 1e-9)), int(np.sum(d < -1e-9))), 3),
                    "sd_case_diff": round(sd, 3)})
    three_seed_sds = [p["sd_case_diff"] for p in out if p["seeds"] == [3, 3]]
    one_seed_sds = [p["sd_case_diff"] for p in out if p["seeds"] == [1, 1]]
    retest = {"model": "P17 ep12, même GGUF, même harnais 3080, deux sessions de juge",
              "p17_session": [len(s) for s in runs["p17_ep12"]],
              "k3_session": json.load(open(RES / "k3" / "k3-summary.json"))["models"]["p17"]["inv"]}
    return out, runs, float(np.sqrt(np.mean(np.square(three_seed_sds)))), float(np.sqrt(np.mean(np.square(one_seed_sds)))), retest


def ssb_section():
    def rows(pattern):
        f = sorted(glob.glob(str(SSB / "steph-protocol" / pattern)))[0]
        return {r["id"]: r["score"] for r in json.load(open(f))["rows"]}
    out = {}
    for lang in ("fr", "en"):
        a = rows(f"multilingual/*p17*steph-protocol_{lang}_test.json")
        b = rows(f"*soup-uniform*steph-protocol_{lang}_test.json")
        common = sorted(set(a) & set(b))
        d = np.array([a[i] - b[i] for i in common])
        mean, lo, hi, sd, n = boot_mean_ci(d)
        sa = np.array([a[i] for i in common])
        out[lang] = {"pair": "P17 contre soupe P-antérieure, protocole steph, test", "n": n,
                     "diff_pts": round(100 * mean, 1), "ci95_pts": [round(100 * lo, 1), round(100 * hi, 1)],
                     "sd_case_diff_pts": round(100 * sd, 1),
                     "sd_case_score_pts": round(100 * float(sa.std(ddof=1)), 1),
                     "mde_pts_n14": round(100 * mde(sd, 14), 1), "mde_pts_n62": round(100 * mde(sd, 62), 1),
                     "single_model_ci_halfwidth_n14_pts": round(100 * 1.96 * float(sa.std(ddof=1)) / math.sqrt(14), 1)}
    return out


def main():
    p15_dir, out_path = sys.argv[1], sys.argv[2]
    groups, v2_pairs, sd_v2, sd_hold = v2_section(p15_dir)
    inv_pairs, runs, sd_inv3, sd_inv1, retest = inventions_section()
    sizes = (36, 69, 120, 150, 200, 300)
    report = {
        "method": "bootstrap apparié par cas, 10 000 tirages, graine 20260928 ; MDE = (z0,975 + z0,80) x sd(diff par cas) / racine(n) ; v2 = facts.v2.json via rescore.score_case, moyenne des graines de banc b7/b42/b123 par cas",
        "v2": {"groups": groups, "pairs": v2_pairs,
               "sd_case_diff_pooled_pts": round(100 * sd_v2, 1),
               "sd_case_diff_holdout_pooled_pts": round(100 * sd_hold, 1),
               "mde_pts": {n: round(100 * mde(sd_v2, n), 1) for n in sizes},
               "mde_holdout_pts_n15": round(100 * mde(sd_hold, 15), 1),
               "n_for_mde": {f"{d} pts": n_needed(sd_v2, d / 100) for d in (2, 3, 4, 5)}},
        "inventions": {"pairs": inv_pairs,
                       "sd_case_diff_pooled_3seeds": round(sd_inv3, 3),
                       "sd_case_diff_pooled_1seed": round(sd_inv1, 3),
                       "mde_per36_3seeds": {n: round(36 * mde(sd_inv3, n), 2) for n in sizes},
                       "mde_per36_1seed": {n: round(36 * mde(sd_inv1, n), 2) for n in sizes},
                       "n_for_mde_3seeds": {f"{k}/36": n_needed(sd_inv3, k / 36) for k in (1, 2, 3)},
                       "retest_same_model": retest,
                       "min_sign_test_p_for_net_diff": {k: round(sign_test_p(k, 0), 4) for k in (1, 2, 3, 4, 5, 6, 7)}},
        "speak_bench": ssb_section(),
        "unpaired_checks": {
            "p14_speak_dev_unresolved_inv_10of28_vs_6of28_fisher_p": round(fisher_p(10, 28, 6, 28), 3),
            "k3_lang_fr_80_6_vs_66_1_on_62_fisher_p": round(fisher_p(50, 62, 41, 62), 3),
            "k3_qa0_1of3_vs_3of3_fisher_p": round(fisher_p(1, 3, 3, 3), 3),
            "k3_speak_dev_en_inv_4of14_vs_1of14_fisher_p": round(fisher_p(4, 14, 1, 14), 3),
            "seed_only_mde_v2_pts_3seeds_fixed_bench": round(Z * math.sqrt(2) * float(np.mean(
                [g["seed_only_se_pts"] for g in groups.values()])), 1),
        },
        "invention_ids": {k: [sorted(s) for s in v] for k, v in runs.items()},
    }
    Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "invention_ids"}, ensure_ascii=False, indent=1)[:12000])


if __name__ == "__main__":
    main()
