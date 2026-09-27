#!/usr/bin/env bash
# Regenerates src/changeproof/adapters/cobol/_generated from the pinned Cobol85 grammar.
# Needs git, curl and Java. Build-time only: the engine never runs Java.
set -euo pipefail

GRAMMARS_REPO=https://github.com/antlr/grammars-v4.git
GRAMMARS_COMMIT=e199816b3f1a7a49ea1ad84fb6b87c382ea36a33
ANTLR_JAR_URL=https://repo1.maven.org/maven2/org/antlr/antlr4/4.13.2/antlr4-4.13.2-complete.jar
ANTLR_JAR_SHA256=eae2dfa119a64327444672aff63e9ec35a20180dc5b8090b7a6ab85125df4d76

root="$(cd "$(dirname "$0")/.." && pwd)"
out="$root/src/changeproof/adapters/cobol/_generated"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

curl -sSL -o "$work/antlr.jar" "$ANTLR_JAR_URL"
echo "$ANTLR_JAR_SHA256  $work/antlr.jar" | sha256sum -c -
git init -q "$work/gv4"
git -C "$work/gv4" fetch -q --depth 1 --filter=blob:none "$GRAMMARS_REPO" "$GRAMMARS_COMMIT"
git -C "$work/gv4" sparse-checkout set cobol85
git -C "$work/gv4" checkout -q FETCH_HEAD
(cd "$work/gv4/cobol85" && java -jar "$work/antlr.jar" -Dlanguage=Python3 -no-listener -o "$work/gen" Cobol85.g4)
cp "$work/gen/Cobol85Lexer.py" "$work/gen/Cobol85Parser.py" "$out/"
echo "regenerated $out"
