#!/bin/bash
# G3c sandbox: runs the script read on stdin as uid 1000 inside the read-only rootfs, with no network
# (fresh net namespace, loopback only), its own pid, uts, ipc and mount namespaces, the workspace WS
# bound at /home/user, public sources ($G3C_SRC) and the template ($G3C_TPL) read-only at /srv/src
# and /srv/tpl, and tmpfs on /tmp, /var/tmp, /run, /dev/shm.
#   sbx.sh ROOTFS WS LOCALE DOCKER_MODE(absent|denied) < script
exec unshare --mount --uts --ipc --net --pid --fork --kill-child --propagation private -- /bin/bash -c '
set -e
R=$1; WS=$2; L=$3; MODE=$4
mount --bind "$R" "$R"; mount -o remount,bind,ro "$R"
mount --bind "$G3C_SRC" "$R/srv/src"; mount -o remount,bind,ro "$R/srv/src"
mount --bind "$G3C_TPL" "$R/srv/tpl"; mount -o remount,bind,ro "$R/srv/tpl"
mount -t proc proc "$R/proc"
mount -t tmpfs -o mode=755,size=1m tmpfs "$R/dev"
for d in null zero full random urandom tty; do touch "$R/dev/$d"; mount --bind "/dev/$d" "$R/dev/$d"; done
ln -s /proc/self/fd "$R/dev/fd"; ln -s /proc/self/fd/0 "$R/dev/stdin"; ln -s /proc/self/fd/1 "$R/dev/stdout"; ln -s /proc/self/fd/2 "$R/dev/stderr"
mkdir "$R/dev/shm" "$R/dev/pts"; mount -t tmpfs -o mode=1777,size=256m tmpfs "$R/dev/shm"
mount -t tmpfs -o mode=1777,size=1g tmpfs "$R/tmp"
mount -t tmpfs -o mode=1777,size=256m tmpfs "$R/var/tmp"
mount -t tmpfs -o mode=755,size=64m tmpfs "$R/run"; mkdir -m 1777 "$R/run/lock" "$R/run/user"
mkdir -m 775 "$R/run/postgresql"; chown 1000:1000 "$R/run/postgresql"
if [ "$MODE" = denied ]; then touch "$R/run/docker.sock"; mount --bind "$(dirname "$0")/docker.sock" "$R/run/docker.sock"; fi
mount --bind "$WS" "$R/home/user"
hostname machine-demo
ip link set lo up
LANGUAGE=en; case "$L" in fr*) LANGUAGE=fr;; esac
exec chroot "$R" /usr/bin/setpriv --reuid=1000 --regid=1000 --clear-groups --inh-caps=-all --bounding-set=-all \
  /usr/bin/env -i HOME=/home/user USER=user LOGNAME=user TERM=dumb COLUMNS=100 SHELL=/bin/bash \
  PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/usr/lib/postgresql/17/bin LANG="$L" LC_ALL="$L" LANGUAGE="$LANGUAGE" NO_COLOR=1 \
  PIP_NO_INPUT=1 PIP_DISABLE_PIP_VERSION_CHECK=1 npm_config_update_notifier=false npm_config_fund=false \
  /bin/bash
' "$(readlink -f "$0")" "$1" "$2" "$3" "$4"
