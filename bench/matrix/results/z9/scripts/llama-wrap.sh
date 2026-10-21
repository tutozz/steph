#!/bin/sh
# binaire llama.cpp (glibc 2.38 requise) lancé avec une libc Debian 13 extraite dans le HOME isolé
R=/root/steph-z9/glibc/root/usr/lib/x86_64-linux-gnu
L=$(ls -d /root/steph-z9/home/.local/share/steph/src/vendor/llama/llama-*)
exec $R/ld-linux-x86-64.so.2 --library-path $R:$L:/root/steph-z9/nvlibs $L/$(basename "$0") "$@"
