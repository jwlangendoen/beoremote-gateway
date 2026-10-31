#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
helper_java="${BEOR_JAVA_HOME:-${JAVA_HOME:-$PWD/../android-spotify-client/.tools/jdk/Contents/Home}}"
mkdir -p .local/helper-tests
"$helper_java/bin/javac" --release 8 -d .local/helper-tests tv_helper/src/nl/beoremote/tvhelper/LaunchGate.java tv_helper/tests/LaunchGateTest.java
"$helper_java/bin/java" -cp .local/helper-tests nl.beoremote.tvhelper.LaunchGateTest
