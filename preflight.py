"""Preflight check to detect GKE version from within a pod."""

from collections.abc import Sequence
import logging
import os
import re
import subprocess
from absl import app
from absl import flags

FLAGS = flags.FLAGS

flags.DEFINE_string(
    "subprocess_ld_path",
    None,
    "If set, this value will be used as LD_LIBRARY_PATH for subprocesses.",
)

try:
  from kubernetes import client, config
  from kubernetes.client.rest import ApiException
  KUBERNETES_INSTALLED = True
except ImportError:
  KUBERNETES_INSTALLED = False


def run_command(command: str) -> str | None:
  """Runs a shell command and returns its stdout, or None on error."""
  try:
    result = subprocess.run(
        command,
        shell=True,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=10,
        env=os.environ,
    )
    return result.stdout.strip()
  except (
      subprocess.CalledProcessError,
      subprocess.TimeoutExpired,
      FileNotFoundError,
  ) as e:
    logging.error(f"Command '{command}' failed: {e}")
    if hasattr(e, "stdout") and e.stdout:
      logging.error(f"Output:\n{e.stdout}")
    return None


def get_nvidia_driver_version() -> str | None:
  """Detects NVIDIA driver version."""
  version = run_command(
      "nvidia-smi --query-gpu=driver_version --format=csv,noheader"
  )
  if version:
    return version
  version_text = run_command("cat /proc/driver/nvidia/version")
  if version_text:
    match = re.search(r"Kernel Module\s+([\d.]+)", version_text)
    if match:
      return match.group(1)
  return None


def get_cuda_version() -> str | None:
  """Detects CUDA toolkit version."""
  version_text = run_command("cat /usr/local/cuda/version.txt")
  if version_text:
    match = re.search(r"CUDA Version\s+([\d.]+)", version_text)
    if match:
      return match.group(1)
  version_text = run_command("nvcc --version")
  if version_text:
    match = re.search(r"release\s+([\d.]+)", version_text)
    if match:
      return match.group(1)
  return None


def get_nccl_version() -> str | None:
  """Detects NCCL version."""
  nccl_version = os.environ.get("NCCL_VERSION")
  if nccl_version:
    return nccl_version

  nccl_h_paths = [
      "/usr/include/nccl.h",
      "/usr/local/cuda/include/nccl.h",
      # Add other potential paths if needed
  ]
  for nccl_h_path in nccl_h_paths:
    if os.path.exists(nccl_h_path):
      major = run_command(
          f"grep '#define NCCL_MAJOR' {nccl_h_path} | awk '{{print $3}}'"
      )
      minor = run_command(
          f"grep '#define NCCL_MINOR' {nccl_h_path} | awk '{{print $3}}'"
      )
      patch = run_command(
          f"grep '#define NCCL_PATCH' {nccl_h_path} | awk '{{print $3}}'"
      )
      if major and minor and patch:
        return f"{major}.{minor}.{patch}"
      elif major and minor:
        return f"{major}.{minor}"
  return None


def detect_gpu_libraries():
  """Detects and prints versions of CUDA, NCCL, NIXL, and NVIDIA driver."""
  versions = {}
  versions["NVIDIA Driver"] = get_nvidia_driver_version() or "Not found"
  versions["CUDA"] = get_cuda_version() or "Not found"
  versions["NCCL"] = get_nccl_version() or "Not found"

  print("\nGPU Library Versions:")
  for lib, version in versions.items():
    print(f"- {lib}: {version}")


def get_gke_version() -> str | None:
  """
  Detects the GKE version by querying the Kubernetes API server.

  Returns:
      The git_version string (e.g., 'v1.28.3-gke.1200') if successful,
      None otherwise.
  """
  if not KUBERNETES_INSTALLED:
    logging.error(
        "Kubernetes client library not found. Please add "
        "'//third_party/py/kubernetes' to BUILD dependencies."
    )
    return None
  try:
    # This loads configuration from the pod's service account
    # and mounted token/cert at /var/run/secrets/kubernetes.io/serviceaccount/
    config.load_incluster_config()
    # The /version endpoint provides cluster version info
    api = client.VersionApi()
    version_info = api.get_code()
    return version_info.git_version
  except config.ConfigException:
    logging.error(
        "Could not configure Kubernetes client. "
        "This script must be run inside a Kubernetes cluster pod "
        "with access to the API server."
    )
    return None
  except ApiException as e:
    logging.error(
        f"An error occurred querying Kubernetes API version endpoint: {e}"
    )
    return None
  except Exception as e:
    logging.error(f"An unexpected error occurred: {e}")
    return None


def main(argv: Sequence[str]) -> None:
  if len(argv) > 1:
    raise app.UsageError("Too many command-line arguments.")

  print("--- Environment Variables ---")
  for key, value in os.environ.items():
    print(f"{key}={value}")
  print("---------------------------\n")

  # If flag is provided, set LD_LIBRARY_PATH in the current environment.
  # subprocess.run() will inherit this when env=None.
  if FLAGS.subprocess_ld_path:
    print(
        "Setting LD_LIBRARY_PATH="
        f"{FLAGS.subprocess_ld_path} for subprocesses."
    )
    os.environ["LD_LIBRARY_PATH"] = FLAGS.subprocess_ld_path

  version = get_gke_version()
  if version:
    print(f"Detected Kubernetes version: {version}")
  else:
    print("Failed to detect Kubernetes version.")
  detect_gpu_libraries()


if __name__ == "__main__":
  app.run(main)
