import os
from abc import ABC, abstractmethod
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

TRACE_RE = re.compile(r"^Program-Id:\s+(\S+)\s.*\bLine:\s+(\d+)\s*$")
RUN_TIMEOUT = 10  # RENAME: SECONDS ONE RUN MAY TAKE BEFORE IT COUNTS AS HUNG (EXIT 124)
# One script for every runner, so a local run and a container run build and execute the same way.
RUN_SCRIPT = """set -eu
cd "$1"
COBC="${COBC:-cobc}"
INCLUDES=""
for d in copy/*/; do [ -d "$d" ] && INCLUDES="$INCLUDES -I $d"; done
"$COBC" -c -ftraceall $INCLUDES -o prog.o "$(cat program)" > build.log 2>&1
"$COBC" -x -free -o drv drv.cbl prog.o >> build.log 2>&1
set +e
for f in in/*.txt; do
  i=$(basename "$f" .txt)
  COB_SET_TRACE=Y COB_TRACE_FILE="$PWD/out/$i.trace" timeout %d ./drv < "$f" > "out/$i.out" 2> "out/$i.err"
  echo $? > "out/$i.rc"
done
""" % RUN_TIMEOUT


@dataclass
class Run:
    output: dict[str, str]
    lines: Counter
    rc: int


# PURPOSE: LINE COUNTS FROM A GNUCOBOL -FTRACEALL TRACE FOR ONE PROGRAM
def read_trace(text: str, program: str) -> Counter:
    found = Counter()  # RENAME: SOURCE LINE TO TIMES IT RAN
    for line in text.splitlines():
        if (m := TRACE_RE.match(line)) and m[1].upper() == program.upper():
            found[int(m[2])] += 1
    return found


# PURPOSE: FIELD=VALUE LINES THE DRIVER DISPLAYED, TRAILING SPACES KEPT
def read_output(text: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


# PURPOSE: WORK FOLDER WITH THE PROGRAM, ITS DRIVER, COPYBOOKS AND ONE INPUT FILE PER RUN
def stage(work: Path, source: Path, driver: str, copybook_dirs: list[Path], inputs: list[list[str]]) -> None:
    shutil.copy(source, work / source.name)
    (work / "program").write_text(source.name)
    (work / "drv.cbl").write_text(driver)
    (work / "run.sh").write_text(RUN_SCRIPT)
    for i, folder in enumerate(copybook_dirs):
        shutil.copytree(folder, work / "copy" / str(i))
    (work / "in").mkdir()
    (work / "out").mkdir()
    for i, values in enumerate(inputs):
        (work / "in" / f"{i:05d}.txt").write_text("".join(f"{v}\n" for v in values))


# PURPOSE: READS EACH RUN'S OUTPUT, TRACE AND EXIT CODE BACK FROM THE WORK FOLDER
def collect(work: Path, program: str, count: int) -> list[Run]:
    runs = []
    for i in range(count):
        out = work / "out" / f"{i:05d}"
        trace = out.with_suffix(".trace")
        runs.append(Run(read_output(out.with_suffix(".out").read_text()),
                        read_trace(trace.read_text() if trace.exists() else "", program),
                        int(out.with_suffix(".rc").read_text())))
    return runs


class Runner(ABC):
    # PURPOSE: COMMAND THAT RUNS THE STAGED SCRIPT IN THIS RUNNER
    @abstractmethod
    def command(self, work: Path) -> list[str]: ...

    # PURPOSE: WHAT RAN THE TESTS, RECORDED IN THE SUITE
    @abstractmethod
    def describe(self) -> dict: ...

    # PURPOSE: BUILDS THE PROGRAM WITH ITS DRIVER ONCE AND RUNS IT ON EVERY INPUT
    def run(self, source: Path, program: str, driver: str, copybook_dirs: list[Path],
            inputs: list[list[str]]) -> list[Run]:
        with tempfile.TemporaryDirectory(prefix="changeproof-characterize-") as tmp:
            work = Path(tmp)
            stage(work, source, driver, copybook_dirs, inputs)
            proc = subprocess.run(self.command(work), capture_output=True, text=True)
            if proc.returncode:
                log = work / "build.log"
                raise RuntimeError(f"{source.name} did not build: {(log.read_text() if log.exists() else proc.stderr).strip()}")
            return collect(work, program, len(inputs))


class LocalRunner(Runner):
    # PURPOSE: USES CHANGEPROOF_COBC OR COBC ON THE PATH
    def __init__(self) -> None:
        self.cobc = os.environ.get("CHANGEPROOF_COBC") or shutil.which("cobc")
        if not self.cobc or not Path(self.cobc).is_file():
            raise RuntimeError(f"GnuCOBOL's cobc was not found ({self.cobc or 'not on PATH'}); "
                               "install it or set CHANGEPROOF_COBC")

    # PURPOSE: RUNS THE SCRIPT WITH THE LOCAL COBC
    def command(self, work: Path) -> list[str]:
        return ["env", f"COBC={self.cobc}", "sh", str(work / "run.sh"), str(work)]

    # PURPOSE: LOCAL RUNNER AND COBC VERSION
    def describe(self) -> dict:
        version = subprocess.run([self.cobc, "--version"], capture_output=True, text=True, check=True)
        return {"kind": "local", "cobc": version.stdout.splitlines()[0]}


class DockerRunner(Runner):
    # PURPOSE: NAMES THE IMAGE BUILT FROM DOCKER/GNUCOBOL/DOCKERFILE
    def __init__(self, image: str) -> None:
        self.image = image

    # PURPOSE: RUNS THE SCRIPT IN A THROWAWAY CONTAINER WITH NO NETWORK
    def command(self, work: Path) -> list[str]:
        return ["docker", "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
                "-v", f"{work}:/work", self.image, "sh", "/work/run.sh", "/work"]

    # PURPOSE: IMAGE ID AND THE COBC VERSION INSIDE IT
    def describe(self) -> dict:
        image_id = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", self.image],
                                  capture_output=True, text=True, check=True).stdout.strip()
        version = subprocess.run(["docker", "run", "--rm", "--network", "none", self.image, "cobc", "--version"],
                                 capture_output=True, text=True, check=True)
        return {"kind": "docker", "image": self.image, "image_id": image_id, "cobc": version.stdout.splitlines()[0]}
