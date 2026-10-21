#!/bin/bash
# Setup only: runs a command inside the rootfs WITH network, in a private mount namespace.
# G3C_ROOTFS: the rootfs; G3C_SRC (optional): bound read-write at /srv/src.
set -e
R=${G3C_ROOTFS:?}
exec unshare --mount --propagation private -- bash -c '
R='"$R"'; S='"${G3C_SRC:-}"'
mount -t proc proc $R/proc
mount --rbind /dev $R/dev
mount -t tmpfs tmpfs $R/tmp
if [ -n "$S" ]; then mkdir -p $R/srv/src; mount --bind $S $R/srv/src; fi
rm -f $R/etc/resolv.conf; cp /etc/resolv.conf $R/etc/resolv.conf
exec chroot $R /usr/bin/env -i HOME=/root PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 bash -c "$0"' "$1"
