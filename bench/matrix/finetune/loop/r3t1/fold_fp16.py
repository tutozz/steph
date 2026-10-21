"""Réduit les activations massives du Granite dense sans changer la fonction du modèle.

Les couches 2 et 3 du Granite 4.0 350M dense produisent sur le premier jeton une sortie
SwiGLU de 65 000 à 67 000, au-dessus du maximum fp16 (65 504). Le chemin coopmat de Vulkan
convertit cette entrée de ffn_down en fp16 : elle devient infinie et tout le cache KV
suit. Le correctif déplace des puissances de 2 entre tenseurs des couches choisies, sur
les échelles fp16 des blocs quantifiés, sans requantifier :

    ffn_up      x 2^-up_shift        (SwiGLU est linéaire en up)
    ffn_down    x 2^(up_shift - res_shift)
    attn_output x 2^-res_shift       (toutes les couches, si res_shift)
    granite.residual_scale x 2^res_shift

Une multiplication par 2^k d'un fp16 normal est exacte. Les échelles de ce modèle sont
petites : une division peut rendre une échelle sous-normale et lui faire perdre des bits.
Le script compte ces échelles inexactes et refuse de les écrire sans --allow-inexact.
Avec --f32-up, ffn_up des couches choisies est déquantifié en F32 puis divisé par 2^k,
ce qui est exact ; seul ffn_down, multiplié, garde ses blocs quantifiés.
"""
import argparse
import shutil
import sys

import numpy as np

# Octet de début des échelles fp16 dans chaque bloc.
SCALE_OFFSETS = {"Q4_K": (144, (0, 2)), "Q6_K": (210, (208,)), "Q8_0": (34, (0,))}
FP16_MIN_NORMAL = 6.103515625e-05
ALLOW_INEXACT = False


def scale_blocks(tensor, shift):
    kind = tensor.tensor_type.name
    if kind == "F32":
        tensor.data[...] = tensor.data * np.float32(2.0 ** shift)
        return 0
    if kind not in SCALE_OFFSETS:
        raise SystemExit(f"{tensor.name}: type {kind} non géré")
    size, offsets = SCALE_OFFSETS[kind]
    raw = tensor.data.reshape(-1)
    blocks = raw.reshape(-1, size)
    lost = 0
    for off in offsets:
        view = blocks[:, off:off + 2].copy().view(np.float16).reshape(-1)
        new = (view.astype(np.float32) * np.float32(2.0 ** shift)).astype(np.float16)
        nz = view != 0
        if np.any(~np.isfinite(new)):
            raise SystemExit(f"{tensor.name}: dépassement fp16")
        sub = nz & (np.abs(new.astype(np.float32)) < FP16_MIN_NORMAL)
        exact = new.astype(np.float32) == view.astype(np.float32) * np.float32(2.0 ** shift)
        lost += int(np.sum(nz & ~exact))
        if np.any(sub & ~exact) and not ALLOW_INEXACT:
            raise SystemExit(f"{tensor.name}: échelle sous-normale inexacte")
        blocks[:, off:off + 2] = new.view(np.uint8).reshape(-1, 2)
    return lost


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--gguf-py", required=True)
    ap.add_argument("--up-shift", type=int, default=2)
    ap.add_argument("--res-shift", type=int, default=0)
    ap.add_argument("--layers", default="2,3", help="couches dont ffn_up et ffn_down changent")
    ap.add_argument("--allow-inexact", action="store_true")
    ap.add_argument("--f32-up", action="store_true")
    a = ap.parse_args()
    global ALLOW_INEXACT
    ALLOW_INEXACT = a.allow_inexact
    layers = {int(x) for x in a.layers.split(",")}
    sys.path.insert(0, a.gguf_py)
    from gguf import GGUFReader
    if a.f32_up:
        return write_f32_up(a, layers)

    shutil.copyfile(a.src, a.dst)
    r = GGUFReader(a.dst, "r+")
    field = r.fields["granite.residual_scale"]
    old = float(field.parts[field.data[0]][0])
    if a.res_shift:
        field.parts[field.data[0]][0] = np.float32(old) * np.float32(2.0 ** a.res_shift)
    shifts = {
        "ffn_up.weight": -a.up_shift,
        "ffn_down.weight": a.up_shift - a.res_shift,
        "attn_output.weight": -a.res_shift,
    }
    done, lost = 0, 0
    for t in r.tensors:
        if not t.name.startswith("blk."):
            continue
        _, layer, suffix = t.name.split(".", 2)
        shift = shifts.get(suffix, 0)
        if int(layer) not in layers:
            shift = {"ffn_up.weight": 0, "ffn_down.weight": -a.res_shift}.get(suffix, shift)
        if shift:
            lost += scale_blocks(t, shift)
            done += 1
    r.data.flush()
    print(f"residual_scale {old} -> {float(field.parts[field.data[0]][0])}; "
          f"{done} tenseurs modifiés ; échelles inexactes {lost}")


def write_f32_up(a, layers):
    import gguf

    tmp = a.dst + ".tmp"
    shutil.copyfile(a.src, tmp)
    r = gguf.GGUFReader(tmp, "r+")
    for t in r.tensors:
        if t.name in {f"blk.{i}.ffn_down.weight" for i in layers}:
            scale_blocks(t, a.up_shift)
    r.data.flush()
    r = gguf.GGUFReader(tmp)
    arch = r.fields[gguf.Keys.General.ARCHITECTURE].contents()
    w = gguf.GGUFWriter(a.dst, arch=arch, endianess=r.endianess)
    for f in r.fields.values():
        if f.name == gguf.Keys.General.ARCHITECTURE or f.name.startswith("GGUF."):
            continue
        vt = f.types[0]
        sub = f.types[-1] if vt == gguf.GGUFValueType.ARRAY else None
        w.add_key_value(f.name, f.contents(), vt, sub_type=sub)
    ups = {f"blk.{i}.ffn_up.weight" for i in layers}
    data = {}
    for t in r.tensors:
        if t.name in ups:
            x = gguf.quants.dequantize(t.data, t.tensor_type) * np.float32(2.0 ** -a.up_shift)
            data[t.name] = x.astype(np.float32)
            w.add_tensor_info(t.name, x.shape, np.float32, x.nbytes, gguf.GGMLQuantizationType.F32)
        else:
            data[t.name] = t.data
            w.add_tensor_info(t.name, t.data.shape, t.data.dtype, t.data.nbytes, t.tensor_type)
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_ti_data_to_file()
    for t in r.tensors:
        w.write_tensor_data(data[t.name], tensor_endianess=r.endianess)
    w.close()
    import os
    os.remove(tmp)
    print(f"ffn_up F32 x 2^-{a.up_shift} et ffn_down x 2^{a.up_shift}, couches {sorted(layers)}")


if __name__ == "__main__":
    main()
