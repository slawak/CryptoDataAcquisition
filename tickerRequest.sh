#!/bin/sh
MSYS_NO_PATHCONV=1 docker run -it --rm \
    -v `pwd`/src:/usr/local/bin \
    -v `pwd`:/var/local \
    -w /var/local \
    -e "BOOTSTRAP_SERVERS=kafka-1:9092" \
    -e "MONGO_USER=connect" \
    -e "MONGO_PASSWORD=cryptoanalyzer!" \
    --network="kafka-net" \
    --entrypoint "" \
    kewlin/kafka-python-base \
    tickerRequest.py "$@"