# OpenFOAM (ESI v2412) + LouiseMcMahon/Model-Rocket-CFD-Pipeline, used by
# rocketwright/aero/openfoam_pipeline.py as an EXTERNAL process.
#
# The pipeline repository has no license file, so RocketWright never copies or vendors its
# code: it is cloned here at image-build time, on the user's machine, and the image is not
# redistributed by this project. OpenFOAM is GPL-3.0 and also only called as a separate program.
#
# Build (from the repository root):
#   docker build -t rocketwright/openfoam-pipeline:2412 -f tools/aero/openfoam-pipeline.Dockerfile tools/aero
FROM opencfd/openfoam-default:2412

ARG PIPELINE_REPO=https://github.com/LouiseMcMahon/Model-Rocket-CFD-Pipeline.git
# Pinned commit (2026-10-27) so a rebuild gives the same pipeline.
ARG PIPELINE_COMMIT=b43605c90280fae8db47fd4b7822236df6b78516

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN git clone "$PIPELINE_REPO" /opt/rocketcfd-src \
 && git -C /opt/rocketcfd-src checkout "$PIPELINE_COMMIT" \
 && python3 -m venv /opt/rocketcfd \
 && /opt/rocketcfd/bin/pip install --no-cache-dir /opt/rocketcfd-src \
 && ln -s /opt/rocketcfd/bin/rocketcfd /usr/local/bin/rocketcfd

# mpirun refuses to run as root unless told otherwise; normally we run with --user uid:gid.
ENV OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 MPLBACKEND=Agg
LABEL org.opencontainers.image.description="OpenFOAM v2412 + rocketcfd pipeline (local build, not redistributed)"
