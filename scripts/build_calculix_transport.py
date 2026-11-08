"""Build a short-path adapter bound to the exact native CalculiX executable hash."""

import argparse
import os
import subprocess
from pathlib import Path

from rocketwright.agent.design_projects import sha, write_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("solver", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    template = Path(__file__).with_name("calculix_short_path.cs")
    generated = a.output / "adapter.cs"
    generated.write_text(
        template.read_text(encoding="utf-8").replace("__SOLVER_SHA256__", sha(a.solver)),
        encoding="utf-8",
    )
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    exe = a.output.resolve() / "solver.exe"
    subprocess.run([str(compiler), "/nologo", "/out:" + str(exe), str(generated)], check=True)
    write_json(
        a.output / "build.json",
        dict(
            adapter_sha256=sha(exe),
            native_solver_sha256=sha(a.solver),
            template_sha256=sha(template),
            compiler_sha256=sha(compiler),
            generated_source_sha256=sha(generated),
        ),
    )
    print(exe)


if __name__ == "__main__":
    main()
