import os

import pytest

from rocketwright.aero.openfoam_pipeline import docker_command, docker_user


def test_docker_desktop_without_posix_uid_keeps_nonroot_and_offline(monkeypatch, tmp_path):
    monkeypatch.delenv("ROCKETWRIGHT_OPENFOAM_USER", raising=False)
    monkeypatch.delattr(os, "getuid", raising=False)
    monkeypatch.delattr(os, "getgid", raising=False)
    cmd = docker_command("local:fixed", tmp_path, "test-container", 2)
    assert "--user=1000:1000" in cmd and "--network=none" in cmd and "--cpus=2" in cmd


@pytest.mark.parametrize("value", ["0:0", "root", "1000:0", "1:2 --privileged", "-1:2"])
def test_invalid_override_is_rejected(monkeypatch, value):
    monkeypatch.setenv("ROCKETWRIGHT_OPENFOAM_USER", value)
    with pytest.raises(ValueError, match="UID:GID"):
        docker_user()


def test_explicit_numeric_mount_user(monkeypatch):
    monkeypatch.setenv("ROCKETWRIGHT_OPENFOAM_USER", "1001:1002")
    assert docker_user() == "1001:1002"
