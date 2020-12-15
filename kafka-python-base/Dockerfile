ARG ALPINE_VERSION=3.8
FROM alpine:${ALPINE_VERSION}
LABEL maintainer="Wjatscheslaw Kewlin <slawa@kewlin.com>"

ARG ALPINE_VERSION=3.8
ENV ALPINE_VERSION ${ALPINE_VERSION}

ARG LIBRDKAFKA_NAME="librdkafka"
ARG LIBRDKAFKA_VER="0.11.6"
ARG CONFLUENT_KAFKA_VER="0.11.6"


# These are always installed. Notes:
#   * dumb-init: a proper init system for containers, to reap zombie children
#   * bash: For entrypoint, and debugging
#   * ca-certificates: for SSL verification during Pip and easy_install
#   * python: the binaries themselves
#   * py-setuptools: required only in major version 2, installs easy_install so we can install Pip.
ENV PACKAGES="\
  dumb-init \
  bash \
  ca-certificates \
  python3 \
  libstdc++ \
"

RUN echo \
  # replacing default repositories with edge ones
  && echo "http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/testing" > /etc/apk/repositories \
  && echo "http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/community" >> /etc/apk/repositories \
  && echo "http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/main" >> /etc/apk/repositories \
  # Add the packages, with a CDN-breakage fallback if needed
  && apk add --no-cache $PACKAGES || \
    (sed -i -e 's/dl-cdn/dl-4/g' /etc/apk/repositories && apk add --no-cache $PACKAGES) \
  # turn back the clock -- so hacky!
  && echo "http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/main/" > /etc/apk/repositories \
  # && echo "@community http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/community" >> /etc/apk/repositories \
  # && echo "@testing http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/testing" >> /etc/apk/repositories \
  # && echo "@edge-main http://dl-cdn.alpinelinux.org/alpine/edge/main" >> /etc/apk/repositories \
  # make some useful symlinks that are expected to exist
  && if [[ ! -e /usr/bin/python ]];        then ln -sf /usr/bin/python3 /usr/bin/python; fi \
  && if [[ ! -e /usr/bin/python-config ]]; then ln -sf /usr/bin/python3-config /usr/bin/python-config; fi \
  # Install and upgrade Pip
  && pip3 install --upgrade pip setuptools \
  && if [[ ! -e /usr/bin/pip ]]; then ln -sf /usr/bin/pip3 /usr/bin/pip; fi \
  && echo

ENV BUILD_PACKAGES_KAFKA="\
  libressl \
  curl \
  tar \
  bash \
  g++ \
  libressl-dev \
  make \
  musl-dev \
  zlib-dev \
"

# Install librdkafka
RUN echo \
  # replacing default repositories with edge ones
  #&& echo "http://dl-cdn.alpinelinux.org/alpine/edge/testing" > /etc/apk/repositories \
  #&& echo "http://dl-cdn.alpinelinux.org/alpine/edge/community" >> /etc/apk/repositories \
  #&& echo "http://dl-cdn.alpinelinux.org/alpine/edge/main" >> /etc/apk/repositories \
  && echo "http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/testing" > /etc/apk/repositories \
  && echo "http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/community" >> /etc/apk/repositories \
  && echo "http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/main" >> /etc/apk/repositories \  
  # Update apk-tools to edge
  && apk add --no-cache --upgrade apk-tools || \
    (sed -i -e 's/dl-cdn/dl-4/g' /etc/apk/repositories && apk add --no-cache --upgrade apk-tools) \
  # Add the packages, with a CDN-breakage fallback if needed
  && apk add --no-cache --virtual .build-deps  $BUILD_PACKAGES_KAFKA || \
    (sed -i -e 's/dl-cdn/dl-4/g' /etc/apk/repositories && apk add --no-cache --virtual .build-deps  $BUILD_PACKAGES_KAFKA) \
  # turn back the clock -- so hacky!
  && echo "http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/main/" > /etc/apk/repositories \
  # && echo "@community http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/community" >> /etc/apk/repositories \
  # && echo "@testing http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/testing" >> /etc/apk/repositories \
  # && echo "@edge-main http://dl-cdn.alpinelinux.org/alpine/edge/main" >> /etc/apk/repositories \
  && echo && \
\
  BUILD_DIR="$(mktemp -d)" && \
\
    curl -sLo "$BUILD_DIR/$LIBRDKAFKA_NAME.tar.gz" "https://github.com/edenhill/librdkafka/archive/v$LIBRDKAFKA_VER.tar.gz" && \
    mkdir -p $BUILD_DIR/$LIBRDKAFKA_NAME-$LIBRDKAFKA_VER && \
    tar \
      --extract \
      --file "$BUILD_DIR/$LIBRDKAFKA_NAME.tar.gz" \
      --directory "$BUILD_DIR/$LIBRDKAFKA_NAME-$LIBRDKAFKA_VER" \
      --strip-components 1 && \
\
    cd "$BUILD_DIR/$LIBRDKAFKA_NAME-$LIBRDKAFKA_VER" && \
    ./configure \
      --prefix=/usr && \
    make -j "$(getconf _NPROCESSORS_ONLN)" && \
    make install && \
\
    runDeps="$( \
      scanelf --needed --nobanner --recursive /usr/local \
        | awk '{ gsub(/,/, "\nso:", $2); print "so:" $2 }' \
        | sort -u \
        | xargs -r apk info --installed \
        | sort -u \
      )" && \
    apk add --no-cache --virtual .librdkafka-rundeps \
      $runDeps && \
\
    cd / \
    && apk del --no-cache --purge .build-deps &&\
    rm -rf /var/cache/apk/* && \
\
    rm -rf $BUILD_DIR

ENV PACKAGES_EDGE="\
  snappy \
  krb5-libs \
"

ENV BUILD_PACKAGES_EDGE="\
  build-base \
  alpine-sdk \
  git \
  python3-dev \
  py3-cffi \
  krb5 \
  curl \
  musl-dev \
  krb5-dev \
  snappy-dev \
"

ENV PIP_PACKAGES="\
  confluent-kafka==$CONFLUENT_KAFKA_VER \
  ccxt \
  click \
  etcd3 \
  python-dateutil \
  pymongo[snappy,gssapi,srv,tls] \
"

RUN echo \
  # replacing default repositories with edge ones
  #&& echo "http://dl-cdn.alpinelinux.org/alpine/edge/testing" > /etc/apk/repositories \
  #&& echo "http://dl-cdn.alpinelinux.org/alpine/edge/community" >> /etc/apk/repositories \
  #&& echo "http://dl-cdn.alpinelinux.org/alpine/edge/main" >> /etc/apk/repositories \
  && echo "http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/testing" > /etc/apk/repositories \
  && echo "http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/community" >> /etc/apk/repositories \
  && echo "http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/main" >> /etc/apk/repositories \  
  # Update apk-tools to edge
  && apk add --no-cache --upgrade apk-tools || \
    (sed -i -e 's/dl-cdn/dl-4/g' /etc/apk/repositories && apk add --no-cache --upgrade apk-tools) \
  # Add the packages, with a CDN-breakage fallback if needed
  && apk add --no-cache $PACKAGES_EDGE || \
    (sed -i -e 's/dl-cdn/dl-4/g' /etc/apk/repositories && apk add --no-cache $PACKAGES_EDGE) \
  && apk add --no-cache --virtual .build-deps  $BUILD_PACKAGES_EDGE || \
    (sed -i -e 's/dl-cdn/dl-4/g' /etc/apk/repositories && apk add --no-cache --virtual .build-deps  $BUILD_PACKAGES_EDGE) \
  # turn back the clock -- so hacky!
  && echo "http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/main/" > /etc/apk/repositories \
  # && echo "@community http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/community" >> /etc/apk/repositories \
  # && echo "@testing http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VERSION}/testing" >> /etc/apk/repositories \
  # && echo "@edge-main http://dl-cdn.alpinelinux.org/alpine/edge/main" >> /etc/apk/repositories \
  && echo \
  # get kafka
  && pip3 install $PIP_PACKAGES \
  # remove build libs
  && apk del --no-cache --purge .build-deps &&\
    rm -rf /var/cache/apk/*

ENTRYPOINT [ "/usr/bin/python" ]