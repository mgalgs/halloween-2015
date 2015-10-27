#!/bin/zsh

PROGGIE=$0

REMOTEUSER=${REMOTEUSER:-root}
IPADDR=${IPADDR:-10.0.5.150}
VENV=${VENV:-"~/venv/default/bin/python"}

ssh -t $REMOTEUSER@$IPADDR "$VENV" < $(dirname $PROGGIE)/main.py
