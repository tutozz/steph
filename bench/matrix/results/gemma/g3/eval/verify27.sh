#!/bin/bash
M=/dev/shm/g3-style-Qwen3.5-27B-Q4_K_M.gguf
until [ "$(stat -c %s $M 2>/dev/null)" = 16740812704 ] && [ "$(sha256sum $M | cut -d" " -f1)" = 84b5f7f112156d63836a01a69dc3f11a6ba63b10a23b8ca7a7efaf52d5a2d806 ]; do sleep 60; done
touch $M.ok; echo "$(date +%T) 27B sha256 ok" >> /root/steph-ft/g3/eval/style.done
