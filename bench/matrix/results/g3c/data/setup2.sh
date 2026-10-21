set -x
apt-get install -y -q --no-install-recommends gcc-14-locales cpp-14-locales || echo WARN locales-gcc
apt-get install -y -q --no-install-recommends rust-clippy rustfmt || echo WARN clippy
apt-get install -y -q --no-install-recommends golang-golang-x-tools || echo WARN gotools
pip install -q --break-system-packages ruff simplejson freezegun || echo WARN pip
npm install -g --no-audit --no-fund eslint@9 typescript@5 prettier@3 || echo WARN npm
getent group user || groupadd -g 1000 user
getent passwd user || useradd -u 1000 -g 1000 -d /home/user -M -s /bin/bash -c Utilisateur user
getent group docker || groupadd -g 999 docker
mkdir -p /home/user
echo machine-demo > /etc/hostname
printf '127.0.0.1\tlocalhost\n127.0.1.1\tmachine-demo\n::1\tlocalhost ip6-localhost\n' > /etc/hosts
echo 00000000000000000000000000000001 > /etc/machine-id
git config --system init.defaultBranch main
git config --system advice.detachedHead true
# public sources that need their dependencies before the network goes away
cd /srv/src
for r in js/*; do (cd $r && npm install --no-audit --no-fund --loglevel=error > /tmp/npm-$(basename $r).log 2>&1 && echo "npm ok $r" || { echo "npm FAIL $r"; tail -5 /tmp/npm-$(basename $r).log; }); done
export CARGO_HOME=/srv/src/cargo-home
for r in rust/*; do (cd $r && cargo fetch -q && echo "cargo ok $r" || echo "cargo FAIL $r"); done
export GOCACHE=/srv/src/gocache GOPATH=/srv/src/gopath GOFLAGS=-mod=mod
for r in go/*; do (cd $r && go mod download && go test ./... > /dev/null 2>&1; echo "go $r $?"); done
chmod -R a+rX /srv/src/gocache /srv/src/gopath /srv/src/cargo-home 2>/dev/null
mkdir -p /srv/src/ready
rm -rf /srv/src/ready/*; cp -a /srv/src/c/libyaml /srv/src/c/jansson /srv/src/c/libuv /srv/src/ready/; cp -a /srv/src/c/libexpat/expat /srv/src/ready/expat
(cd /srv/src/ready/libyaml && ./bootstrap > /dev/null 2>&1 && echo "bootstrap libyaml ok")
(cd /srv/src/ready/jansson && autoreconf -fi > /dev/null 2>&1 && echo "autoreconf jansson ok")
(cd /srv/src/ready/libuv && sh autogen.sh > /dev/null 2>&1 && echo "autogen libuv ok")
(cd /srv/src/ready/expat && ./buildconf.sh > /dev/null 2>&1 && echo "buildconf expat ok")
echo 'nameserver 127.0.0.53' > /etc/resolv.conf.g3c
echo SETUP2_DONE
