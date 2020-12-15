#!/bin/bash

MSYS_NO_PATHCONV=1 docker-compose exec -T etcd  \
  etcdctl "$@"
