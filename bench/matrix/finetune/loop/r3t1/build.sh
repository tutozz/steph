#!/bin/bash
# Compile llama.cpp b11232 (Vulkan + CPU, outils de diagnostic) sans rien installer dans le système.
set -eu
D=/root/steph-ft/loop/r3t1; cd $D
[ -d sdk ] || { mkdir -p sdk && tar xJf vksdk.tar.xz -C sdk; }
SDKV=$(ls sdk); export VULKAN_SDK=$D/sdk/$SDKV/x86_64
mkdir -p tools; cd tools
[ -x cmake/bin/cmake ] || { wget -q https://github.com/Kitware/CMake/releases/download/v3.31.8/cmake-3.31.8-linux-x86_64.tar.gz && tar xzf cmake-3.31.8-linux-x86_64.tar.gz && mv cmake-3.31.8-linux-x86_64 cmake; }
[ -x ninja ] || { wget -q https://github.com/ninja-build/ninja/releases/download/v1.12.1/ninja-linux.zip && unzip -o -q ninja-linux.zip; }
cd $D
export PATH=$D/tools/cmake/bin:$D/tools:$VULKAN_SDK/bin:$PATH
export LD_LIBRARY_PATH=$VULKAN_SDK/lib; export CMAKE_PREFIX_PATH=$VULKAN_SDK
[ -d src ] || { tar xzf bin/src-b11232.tar.gz && mv llama.cpp-b11232 src; }
cd src
cmake -B build -G Ninja -DGGML_VULKAN=ON -DLLAMA_BUILD_TESTS=ON -DLLAMA_BUILD_EXAMPLES=ON -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DVulkan_LIBRARY=/lib/x86_64-linux-gnu/libvulkan.so.1
cmake --build build -j 8 --target llama-eval-callback test-backend-ops llama-completion llama-perplexity
echo BUILD-OK
