#!/bin/zsh

PROGGIE=$0

REMOTEUSER=${REMOTEUSER:-root}
IPADDR=${IPADDR:-10.0.5.150}

rsync -ai $(dirname $PROGGIE)/main.py $REMOTEUSER@$IPADDR:/root/main.py
