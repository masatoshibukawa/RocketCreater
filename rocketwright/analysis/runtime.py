"""Host runtime configuration and process-tree timeout enforcement."""

import os
import signal
import subprocess
from pathlib import Path

from pydantic import Field, model_validator

from rocketwright.analysis.schema import Strict


class Runtime(Strict):
    calculix: str | None = None
    cfd_enabled: bool = False
    cfd_cells_coarse: int = Field(default=12, ge=6, le=40)
    cfd_cells_fine: int = Field(default=16, ge=8, le=48)
    cfd_times: float = Field(default=40, ge=2, le=100)
    fem_level: int = Field(default=2, ge=2, le=4)

    @model_validator(mode="after")
    def increasing(self):
        if self.cfd_cells_fine <= self.cfd_cells_coarse:
            raise ValueError("Fine CFD resolution must exceed coarse resolution")
        return self

    @classmethod
    def installed(cls):
        return cls(
            calculix=os.getenv("ROCKETWRIGHT_CALCULIX"),
            cfd_enabled=os.getenv("ROCKETWRIGHT_CFD_ENABLED") == "1",
        )

    def capabilities(self):
        return (["fem"] if self.calculix and Path(self.calculix).is_file() else []) + (
            ["cfd"] if self.cfd_enabled else []
        )


def run(command, *, cwd, log, timeout):
    """Timeout cancels this worker and its solver descendants, never unrelated processes."""
    if timeout <= 0:
        raise RuntimeError("No execution time remains")
    with Path(log).open("w", encoding="utf-8") as out:
        p = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            code = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            if os.name == "nt":
                # PID belongs to the still-running Popen above; /T confines termination to its tree.
                subprocess.run(
                    ["taskkill", "/PID", str(p.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    check=False,
                )
            else:
                os.killpg(p.pid, signal.SIGKILL)
            p.wait(timeout=10)
            raise RuntimeError("Analysis time budget exceeded; worker tree terminated") from error
    if code:
        tail = Path(log).read_text(encoding="utf-8", errors="replace")[-1500:]
        raise RuntimeError(f"Analysis process exited with {code}: {tail}")
