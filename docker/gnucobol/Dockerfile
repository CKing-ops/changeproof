# GnuCOBOL runner for `changeproof characterize --docker`. The build needs the network; runs use --network none.
# GnuCOBOL is GPL-3.0 (compiler) and LGPL-3.0 (libcob). It is used as a tool here; nothing of it ships with changeproof.
FROM ubuntu:24.04
RUN apt-get update \
 && apt-get install -y --no-install-recommends gnucobol3=3.1.2-5.1ubuntu1 \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /work
