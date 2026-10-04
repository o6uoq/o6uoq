# Use the Ubuntu browser runtime verified against Strava.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

# Set the working directory in the container to /app
WORKDIR /app

# Copy dependency files and install with uv
COPY pyproject.toml uv.lock ./
# The workflow mounts its checkout at /app, so keep dependencies outside that mount.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl xvfb libgtk-3-0 libdbus-glib-1-2 libasound2t64 libx11-xcb1 libxtst6 libnss3 libgbm1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install uv==0.12.22 && uv sync --python 3.14.8 --frozen --no-dev
# Download the exact browser without GitHub API discovery or its anonymous rate limit.
ARG TARGETARCH
RUN case "$TARGETARCH" in \
      amd64) browser_arch=x86_64; browser_sha=09effb44efec6f0617b6940b787054b4b8773f28d6573bcbabefe3163e75d0cc ;; \
      arm64) browser_arch=arm64; browser_sha=c30d865d1ef14e33231a92d256cdb78b31933acb38f1b090a374a2db6c68e0b1 ;; \
      *) exit 1 ;; \
    esac \
    && curl -fsSL "https://github.com/daijro/camoufox/releases/download/v156.0.1-beta.34/camoufox-156.0.1-beta.34-lin.${browser_arch}.zip" -o /tmp/camoufox.zip \
    && printf '%s  %s\n' "$browser_sha" /tmp/camoufox.zip | sha256sum -c - \
    && /opt/venv/bin/python -c "from zipfile import ZipFile; ZipFile('/tmp/camoufox.zip').extractall('/opt/camoufox')" \
    && chmod -R 755 /opt/camoufox \
    && rm /tmp/camoufox.zip
ENV CAMOUFOX_EXECUTABLE_PATH=/opt/camoufox/camoufox-bin
# Install fingerprint/addon assets now, outside the mounted checkout.
RUN /opt/venv/bin/python -c "from pathlib import Path; from camoufox.utils import launch_options; from camoufox.addons import get_addon_path; launch_options(headless=True, os='linux'); assert Path(get_addon_path('UBO'), 'manifest.json').is_file()"

# Runtime commands use the installed production dependencies without adding dev tools.
ENV UV_NO_SYNC=1

# Copy the current directory contents into the container at /app
COPY . /app

# Run Python via uv to use the virtual environment
CMD ["uv", "run", "python"]
