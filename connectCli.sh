#!/bin/bash

MSYS_NO_PATHCONV=1 docker-compose exec -T kafka-connect-mongodb  \
  /etc/landoop/bin/connect-cli "$@"
