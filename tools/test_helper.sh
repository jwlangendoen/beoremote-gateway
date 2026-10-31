#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
helper_java="${BEOR_JAVA_HOME:-${JAVA_HOME:-$PWD/../android-spotify-client/.tools/jdk/Contents/Home}}"
mkdir -p .local/helper-tests
"$helper_java/bin/javac" --release 8 -d .local/helper-tests tv_helper/src/nl/beoremote/tvhelper/LaunchGate.java tv_helper/tests/LaunchGateTest.java
"$helper_java/bin/java" -cp .local/helper-tests nl.beoremote.tvhelper.LaunchGateTest

"$helper_java/bin/javac" --release 8 -d .local/helper-tests tv_helper/src/nl/beoremote/tvhelper/SourceOrderPlan.java tv_helper/src/nl/beoremote/tvhelper/SourceOrderTransaction.java tv_helper/tests/SourceOrderTest.java
"$helper_java/bin/java" -cp .local/helper-tests nl.beoremote.tvhelper.SourceOrderTest

# Real SupportService/provider recovery tests. Pinned test-only JSON implementation.
helper_json="$PWD/.local/test-deps/json-20240303.jar"
mkdir -p "$(dirname "$helper_json")"
if [[ ! -f "$helper_json" ]]; then
  curl --fail --silent --show-error --location --max-time 30 \
    https://repo.maven.apache.org/maven2/org/json/json/20240303/json-20240303.jar -o "$helper_json"
fi
python3 - "$helper_json" <<'CHECK_JSON'
import hashlib, pathlib, sys
assert hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest() == "3cf6cd6892e32e2b4c1c39e0f52f5248a2f5b37646fdfbb79a66b46b618414ed", "JSON test dependency checksum mismatch"
CHECK_JSON
mkdir -p .local/helper-recovery-tests
helper_stubs=()
while IFS= read -r file; do helper_stubs+=("$file"); done < <(find tv_helper/tests/android-stubs -name '*.java')
"$helper_java/bin/javac" --release 8 -classpath "$helper_json" -d .local/helper-recovery-tests "${helper_stubs[@]}" \
 tv_helper/src/nl/beoremote/tvhelper/{SupportService,SourceMaintenance,StartReceiver,ControlProvider,ShortcutCatalog,LaunchGate,SourceOrder,SourceOrderPlan,SourceOrderTransaction}.java \
 tv_helper/tests/SourceRecoveryTest.java
"$helper_java/bin/java" -cp ".local/helper-recovery-tests:$helper_json" nl.beoremote.tvhelper.SourceRecoveryTest
