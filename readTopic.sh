#!/bin/bash

docker-compose exec kafka-1  \
  kafka-console-consumer --bootstrap-server kafka-1:9092 --topic $1 \
  --from-beginning --property print.key=true --property key.separator=" " 
#  --key-deserializer 	org.apache.kafka.common.serialization.ByteArrayDeserializer

