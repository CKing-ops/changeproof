#!/usr/bin/env bash
# Builds both candidate parsers from pinned sources into spike/_build.
# Needs git, a C compiler and Java (ANTLR code generation only). Setup-time network use.
set -euo pipefail

TS_COBOL_REPO=https://github.com/yutaro-sakamoto/tree-sitter-cobol.git
TS_COBOL_COMMIT=550020ddf42ef9b718ad897868a9308d2afcda35
GRAMMARS_REPO=https://github.com/antlr/grammars-v4.git
GRAMMARS_COMMIT=e199816b3f1a7a49ea1ad84fb6b87c382ea36a33
ANTLR_JAR_URL=https://repo1.maven.org/maven2/org/antlr/antlr4/4.13.2/antlr4-4.13.2-complete.jar
ANTLR_JAR_SHA256=eae2dfa119a64327444672aff63e9ec35a20180dc5b8090b7a6ab85125df4d76

cd "$(dirname "$0")"
mkdir -p _build && cd _build

if [ ! -f tree-sitter-cobol.so ]; then
  rm -rf ts-cobol && git init -q ts-cobol
  git -C ts-cobol fetch -q --depth 1 "$TS_COBOL_REPO" "$TS_COBOL_COMMIT"
  git -C ts-cobol checkout -q FETCH_HEAD
  cc -O2 -fPIC -shared -Its-cobol/src ts-cobol/src/parser.c ts-cobol/src/scanner.c -o tree-sitter-cobol.so
fi

if [ ! -f antlr/Cobol85Parser.py ]; then
  curl -sSL -o antlr.jar "$ANTLR_JAR_URL"
  echo "$ANTLR_JAR_SHA256  antlr.jar" | sha256sum -c -
  rm -rf gv4 && git init -q gv4
  git -C gv4 fetch -q --depth 1 --filter=blob:none "$GRAMMARS_REPO" "$GRAMMARS_COMMIT"
  git -C gv4 sparse-checkout set cobol85 && git -C gv4 checkout -q FETCH_HEAD
  (cd gv4/cobol85 && java -jar ../../antlr.jar -Dlanguage=Python3 -o ../../antlr Cobol85.g4)
fi
echo "built: $(pwd)"
