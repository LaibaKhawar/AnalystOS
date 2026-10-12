# AnalystOS Python sandbox image. Runs untrusted, model-generated analysis code.
# The container is started with: no network, read-only rootfs, non-root user, all capabilities
# dropped, no-new-privileges, CPU/memory/PID limits and a wall-clock timeout (see app/services/sandbox).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/mpl \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1

RUN pip install --no-cache-dir \
      "pandas==2.2.3" "numpy==2.1.3" "scipy==1.14.1" "scikit-learn==1.5.2" \
      "matplotlib==3.9.2" "pyarrow==18.0.0" "statsmodels==0.14.4" \
 && rm -rf /root/.cache \
 && python -c "import matplotlib.pyplot"  # warm the font cache at build time

# Built from the repository root: docker build -f sandbox/Dockerfile .
# The runner is shared with the Modal sandbox backend, so it lives in the backend package.
COPY backend/app/services/sandbox/runner.py /opt/runner/runner.py
RUN chmod 0555 /opt/runner/runner.py && mkdir -p /work && chmod 0755 /work

USER 65534:65534
WORKDIR /work
ENTRYPOINT ["python", "-I", "/opt/runner/runner.py"]
