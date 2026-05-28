"""
Environment Setup Script
Install dependencies and download models.
"""
import subprocess
import sys
import os


def run_command(cmd, desc=""):
    """Run a shell command."""
    print(f"\n{'=' * 50}")
    if desc:
        print(f"{desc}")
    print(f"Running: {cmd}")
    print("=" * 50)
    result = subprocess.run(cmd, shell=True)
    return result.returncode == 0


def main():
    print("=" * 50)
    print("My RAG Framework - Environment Setup")
    print("=" * 50)

    print("\n1. Installing Python dependencies...")
    if not run_command("pip install -r requirements.txt", "Installing requirements.txt"):
        print("Failed to install requirements. Please check your environment.")
        sys.exit(1)

    print("\n2. Downloading AI models...")
    if not run_command("python scripts/download_models.py", "Downloading models"):
        print("Some models failed to download. The system will use mock mode.")

    print("\n3. Checking environment...")
    try:
        from backend.config import settings
        print(f"  Project: {settings.PROJECT_NAME}")
        print(f"  Version: {settings.VERSION}")
        print("  Configuration OK")
    except Exception as e:
        print(f"  Config error: {e}")

    print("\n" + "=" * 50)
    print("Setup complete!")
    print("=" * 50)
    print("\nTo start the backend:")
    print("  uvicorn backend.main:app --reload --port 8000")
    print("\nTo start the frontend:")
    print("  cd frontend && npm install && npm run dev")
    print("=" * 50)


if __name__ == "__main__":
    main()
