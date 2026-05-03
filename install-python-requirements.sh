#!/bin/bash

echo "=== VirtualDJ Chords Injection - Python Setup ==="
echo ""

VENV_PATH="$HOME/.venvs/audio312"
PYTHON_BIN="$VENV_PATH/bin/python"

# ----------------------------
# 1. Check Homebrew
# ----------------------------
if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew not found. Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true
else
    echo "Homebrew already installed ✔"
fi

# ----------------------------
# 2. Check Python
# ----------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python3 not found. Installing with Homebrew..."
    brew install python
else
    echo "Python3 already installed ✔"
fi

echo ""
python3 --version

# ----------------------------
# 3. Check virtual environment
# ----------------------------
if [ -f "$PYTHON_BIN" ]; then
    echo "Virtual environment detected ✔"
else
    echo "Creating virtual environment..."
    mkdir -p "$HOME/.venvs"
    python3 -m venv "$VENV_PATH"
fi

# ----------------------------
# 4. Check dependencies
# ----------------------------
echo ""
echo "Checking Python packages..."

if "$PYTHON_BIN" -c "import numpy, scipy, librosa, soundfile" >/dev/null 2>&1; then
    echo "All required packages already installed ✔"
else
    echo "Installing missing packages..."

    source "$VENV_PATH/bin/activate"

    pip install --upgrade pip
    pip install numpy scipy librosa soundfile
fi

# ----------------------------
# 5. Verify installation
# ----------------------------
echo ""
echo "Verifying environment..."

"$PYTHON_BIN" -c "import numpy, scipy, librosa, soundfile; print('Python environment OK ✔')" || {
    echo "ERROR: Environment verification failed"
    exit 1
}

# ----------------------------
# DONE
# ----------------------------
echo ""
echo "=== Installation complete ==="
echo "Python path for AppleScript:"
echo "$PYTHON_BIN"
echo ""
echo "You can now run the AppleScript."