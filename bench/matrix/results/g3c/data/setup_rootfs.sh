set -e
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d; chmod +x /usr/sbin/policy-rc.d
apt-get update -q
apt-get install -y -q --no-install-recommends locales ca-certificates
sed -i 's/^# *fr_FR.UTF-8/fr_FR.UTF-8/; s/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen
locale-gen
apt-get install -y -q --no-install-recommends \
  build-essential cmake autoconf automake libtool pkg-config gettext \
  python3 python3-pip python3-venv python3-pytest python3-dev flake8 pylint mypy black python3-hypothesis \
  shellcheck bats golang-go cargo rustc nodejs npm \
  sqlite3 postgresql postgresql-client valkey-server valkey-tools nginx-light openssh-server openssh-client \
  curl wget netcat-openbsd iproute2 iputils-ping dnsutils net-tools openssl git jq rsync zip unzip xz-utils bzip2 zstd \
  file procps psmisc lsof tree less man-db cron docker-cli docker-compose tar diffutils patch bc time
apt-get clean
echo SETUP_OK
