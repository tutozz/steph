#!/bin/bash
# Génère des sorties réelles des outils GNU, en anglais et en français, dans un dossier jetable.
# Usage : bash gen.sh <C|fr_FR.UTF-8>
set -u
L=$1
W=$(mktemp -d /dev/shm/d6b.XXXX)
cd "$W" || exit 1
export LANG=$L LC_ALL=$L
run() { echo "=== \$ $*"; eval "$@" 2>&1; echo "=== exit $?"; }
mkdir -p src/sub && printf 'a TODO x\nb\nTODO y\n' > src/a.py && printf 'TODO z\n' > src/sub/b.py && printf 'none\n' > src/c.py
run "mkdir -pv out/2024/janvier out/2024/fevrier"
run "mkdir -v out/2024/janvier"
touch f1 f2 f3; mkdir -p d1
run "rm -v f1 f2"
run "rm -rv d1"
seq 1 100 > lines.txt
run "split -n 3 -d --verbose lines.txt part_"
run "chmod -v 640 part_00 part_01"
run "chmod -c 640 part_00 part_02"
run "chmod -Rv 750 out"
run "chown -v nobody:nogroup part_00 part_01"
run "chown -c nobody:nogroup part_00 part_02"
run "chgrp -v nogroup part_02"
printf 'x\n' > s1; printf 'y\n' > s2
run "shred -v -n 2 s1"
run "shred -vzu -n 1 s2"
printf 'k\n' > c1; printf 'l\n' > c2; printf 'm\n' > c3
sha256sum c1 c2 c3 > sums; printf 'changed\n' > c2; rm c3
run "sha256sum -c sums"
sha256sum c1 > ok.sums
run "sha256sum -c ok.sums"
run "md5sum -c sums"
mkdir -p r1/src r2/src r2/new; printf '1\n' > r1/x; printf '2\n' > r2/x; printf 'o\n' > r1/only; printf 's\n' > r1/src/s; printf 't\n' > r2/src/s
run "diff -rq r1 r2"
run "diff -q r1/x r2/x"
run "wc -l lines.txt src/a.py src/c.py"
run "wc -w lines.txt src/a.py"
run "grep -rn TODO src"
run "grep -r TODO src"
run "grep -rc TODO src"
run "grep -rl TODO src"
run "grep -n TODO src/a.py"
run "tar -czvf ../d6b-t.tgz src"
run "tar -xzvf ../d6b-t.tgz -C out"
head -c 3000 ../d6b-t.tgz > trunc.tgz
run "tar -xzvf trunc.tgz -C out"
run "tar -xvf missing.tar"
run "cp -v part_00 part_01 out/"
run "cp -rv src out/copie"
run "ln -sv ../part_00 ../part_01 out/"
run "mv -v part_02 out/"
run "cp missing.csv out/"
run "sort missing.txt"
run "mkdir out"
printf '#!/bin/bash\nset -u\necho start\necho "$UNDEF_VAR"\n' > unbound.sh
run "bash unbound.sh"
printf '#!/bin/bash\necho start\ncd /nonexistent/dir\ncp nope.csv /tmp/x\nexit 3\n' > errs.sh
run "bash errs.sh"
printf '#!/bin/bash\nx=$((1 / 0))\n' > div.sh
run "bash div.sh"
printf '#!/bin/bash\n[ 3 -eq ]\nexit 2\n' > unary.sh
run "bash unary.sh"
printf '#!/bin/bash\nif true; then\n  echo x\n' > syn.sh
run "bash syn.sh"
mkdir -p mirror
run "rsync -av src/ mirror/"
run "rsync -a --stats src/ mirror2/"
cd / && rm -rf "$W" /dev/shm/d6b-t.tgz
