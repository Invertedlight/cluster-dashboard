FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

# System bits handy for Python web work + kubectl debugging from the workspace
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git make \
    && rm -rf /var/lib/apt/lists/*

# Scratch mount from cluster PVC (created empty if not present on other hosts)
RUN mkdir -p /scratch && chown vscode:vscode /scratch

WORKDIR /workspaces/cluster-dashboard
