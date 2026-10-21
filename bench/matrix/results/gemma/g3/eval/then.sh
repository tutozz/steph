#!/bin/bash
# Enchaîne une seconde passe du juge quand la première (PID $1) a rendu la carte.
pid=$1; shift
while kill -0 $pid 2>/dev/null; do sleep 60; done
exec ./judge-test.sh "$@"
