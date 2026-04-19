import subprocess
import sys
import os

token = os.environ.get("GITHUB_TOKEN")
if not token:
    print("No GITHUB_TOKEN available")
    sys.exit(1)

repo_url = "https://x-access-token:" + token + "@github.com/shoaibrza9999-png/WhatsApp_automation.git"
branch = sys.argv[1]

try:
    subprocess.run(["git", "push", "--force", repo_url, branch], check=True)
    print("Push successful")
except subprocess.CalledProcessError as e:
    print(f"Push failed: {e}")
    sys.exit(1)
