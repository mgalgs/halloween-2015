#!/bin/zsh

cd $(dirname $0)
./remote-sync.sh

REMOTEUSER=${REMOTEUSER:-root}
IPADDR=${IPADDR:-10.0.5.150}
VENV=${VENV:-"/root/venv/default/bin/python"}

ssh -t $REMOTEUSER@$IPADDR "$VENV" /root/main.py $*
