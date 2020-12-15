# Delete topics

docker run \
  --net=host \
  --rm \
  confluentinc/cp-kafka:latest \
  kafka-topics --delete --topic RequestMarketData --zookeeper localhost:22181

docker run \
  --net=host \
  --rm \
  confluentinc/cp-kafka:latest \
  kafka-topics --delete --topic ResultMarketData --zookeeper localhost:22181


# Create

docker run \
  --net=host \
  --rm \
  confluentinc/cp-kafka:latest \
  kafka-topics --create --topic RequestMarketData --partitions 100 --replication-factor 3 \
  --if-not-exists --zookeeper localhost:22181

docker run \
  --net=host \
  --rm \
  confluentinc/cp-kafka:latest \
  kafka-topics --create --topic ResultMarketData --partitions 100 --replication-factor 3 \
  --if-not-exists --zookeeper localhost:22181

# Describe

docker run \
    --net=host \
    --rm \
    confluentinc/cp-kafka:latest \
    kafka-topics --list --zookeeper localhost:22181


docker run \
    --net=host \
    --rm \
    confluentinc/cp-kafka:latest \
    kafka-topics --describe --topic RequestMarketData --zookeeper localhost:22181

docker run \
    --net=host \
    --rm \
    confluentinc/cp-kafka:latest \
    kafka-topics --describe --topic ResultMarketData --zookeeper localhost:22181

