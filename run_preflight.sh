#!/bin/bash
# This script creates a Python virtual environment, installs dependencies,
# and runs the preflight.py check.

set -e

# Define paths relative to script location
CURRENT_DIR=$(dirname "$0")
SCRIPT_DIR="/tmp/preflight"
mkdir -p ${SCRIPT_DIR}
echo "Downloading requirements.txt from GitHub..."
if ! curl -sSfo "${SCRIPT_DIR}/requirements.txt" "https://raw.githubusercontent.com/xzhaosg/gke-tools/refs/heads/main/requirements.txt"; then
  echo "Failed to download requirements.txt. Please check network or URL."
  exit 1
fi
echo "Downloading preflight.py from GitHub..."
if ! curl -sSfo "${SCRIPT_DIR}/preflight.py" "https://raw.githubusercontent.com/xzhaosg/gke-tools/refs/heads/main/preflight.py"; then
  echo "Failed to download preflight.py. Please check network or URL."
  exit 1
fi

VENV_DIR="${SCRIPT_DIR}/venv"
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements.txt"
PREFLIGHT_SCRIPT="${SCRIPT_DIR}/preflight.py"

# Check if python3 is available
if ! command -v python3 &> /dev/null
then
    echo "python3 could not be found, please install it."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "${VENV_DIR}" ]; then
  echo "Creating Python virtual environment in ${VENV_DIR}..."
  python3 -m venv "${VENV_DIR}"
else
  echo "Virtual environment ${VENV_DIR} already exists."
fi

# Activate virtual environment
source "${VENV_DIR}/bin/activate"

# Install dependencies if requirements.txt exists
if [ -f "${REQUIREMENTS_FILE}" ]; then
  echo "Installing dependencies from ${REQUIREMENTS_FILE}..."
  pip install -r "${REQUIREMENTS_FILE}"
else
  echo "Warning: ${REQUIREMENTS_FILE} not found. Skipping dependency installation."
fi

# Check if nvidia-smi is in PATH, if not, find it and add its directory to PATH
if ! command -v nvidia-smi &> /dev/null; then
  echo "nvidia-smi not found in PATH. Searching for it..."
  NVIDIA_SMI_PATH=$(find / -name nvidia-smi -type f -executable 2>/dev/null | head -n 1)

  if [ -n "$NVIDIA_SMI_PATH" ]; then
    NVIDIA_DIR=$(dirname "$NVIDIA_SMI_PATH")
    echo "Found nvidia-smi in ${NVIDIA_DIR}. Adding this directory to PATH."
    export PATH="${NVIDIA_DIR}:${PATH}"
  else
    echo "Warning: nvidia-smi executable not found on the system."
  fi
else
  echo "nvidia-smi is already in PATH."
fi

# Check if libnvidia-ml.so is in LD_LIBRARY_PATH
lib_found=false
if [ -n "$LD_LIBRARY_PATH" ]; then
  IFS=':' read -ra paths <<< "$LD_LIBRARY_PATH"
  for path in "${paths[@]}"; do
    if [ -d "$path" ] && find "$path" -maxdepth 1 -name 'libnvidia-ml.so*' 2>/dev/null | grep -q .; then
      lib_found=true
      break
    fi
  done
fi

if [ "$lib_found" = true ]; then
  echo "libnvidia-ml.so found in LD_LIBRARY_PATH."
else
  echo "libnvidia-ml.so not found in LD_LIBRARY_PATH. Searching for it..."
  LIBNVIDIA_ML_SO_PATH=$(find / -name "libnvidia-ml.so*" 2>/dev/null | head -n 1)

  if [ -n "$LIBNVIDIA_ML_SO_PATH" ]; then
    LIBNVIDIA_ML_DIR=$(dirname "$LIBNVIDIA_ML_SO_PATH")
    echo "Found libnvidia-ml.so in ${LIBNVIDIA_ML_DIR}. Adding to LD_LIBRARY_PATH."
    export LD_LIBRARY_PATH="${LIBNVIDIA_ML_DIR}:${LD_LIBRARY_PATH}"
  else
    echo "Warning: libnvidia-ml.so not found on the system."
  fi
fi

# Run the preflight script
echo ""
echo "Running preflight check..."
python3 "${PREFLIGHT_SCRIPT}"

# Deactivate venv
deactivate

echo ""
echo "Checking nixl version..."
NIXL_VERSION=$(pip show nixl 2>/dev/null | grep '^Version:' | awk '{print $2}')
if [ -n "$NIXL_VERSION" ]; then
  echo "NIXL version (from nixl package): $NIXL_VERSION"
else
  echo "nixl package not found, cannot determine NIXL version via pip."
fi

echo ""
cd "${CURRENT_DIR}"
echo "Preflight check finished."
