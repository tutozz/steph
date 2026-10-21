# Instrumentation de diagnostic R3-T1, build local seulement.
p = "ggml/src/ggml-vulkan/ggml-vulkan.cpp"
s = open(p).read()
anchor = "    const uint32_t split_k = ggml_vk_guess_split_k(ctx, ne01, ne11, ne10, disable_split_k, pipeline);\n"
assert s.count(anchor) >= 1
s = s.replace(anchor, anchor + '    if (getenv("R3T1_LOG")) fprintf(stderr, "R3T1 mm %s src0=%s m=%u n=%u k=%u quantize_y=%d y_non_contig=%d aligned=%d split_k=%u\\n", pipeline->name.c_str(), ggml_type_name(src0->type), (unsigned)ne01, (unsigned)ne11, (unsigned)ne10, (int)quantize_y, (int)y_non_contig, (int)aligned, split_k);\n', 1)
open(p, "w").write(s)
p = "common/debug.cpp"
s = open(p).read()
anchor = "        common_debug_print_tensor(data, t->type, t->ne, t->nb, 3, pimpl->abort_on_nan);\n"
s = s.replace(anchor, anchor + '''        if (t->type == GGML_TYPE_F32 && ggml_is_contiguous(t)) {
            const float * f = (const float *) data; int64_t n = ggml_nelements(t), im = 0; float mx = 0;
            for (int64_t i = 0; i < n; i++) { if (!(fabsf(f[i]) <= mx)) { mx = fabsf(f[i]); im = i; } }
            LOG("    maxabs = %f at col %lld row %lld (value %f)\\n", mx, (long long)(im % t->ne[0]), (long long)(im / t->ne[0]), f[im]);
        }
''', 1)
open(p, "w").write(s)
print("ok")
