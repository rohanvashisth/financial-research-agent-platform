import subprocess
import time
import sys
import os

def run_cmd(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=True)
        return 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout.strip(), e.stderr.strip()

def main():
    print("Auto-commit & push service initialized. Watching workspace for changes...", flush=True)
    
    # Verify we are in a git repository
    code, stdout, stderr = run_cmd(["git", "rev-parse", "--is-inside-work-tree"])
    if code != 0 or stdout != "true":
        print(f"Error: Not in a git repository: {stderr}", file=sys.stderr, flush=True)
        sys.exit(1)
        
    while True:
        try:
            # Check git status for changes
            code, stdout, stderr = run_cmd(["git", "status", "--porcelain"])
            if code == 0 and stdout:
                # Changes exist!
                print(f"Changes detected:\n{stdout}", flush=True)
                
                # Stage all changes (adhering to .gitignore)
                add_code, add_out, add_err = run_cmd(["git", "add", "-A"])
                if add_code != 0:
                    print(f"Failed to stage changes: {add_err}", file=sys.stderr, flush=True)
                    time.sleep(10)
                    continue
                    
                # Commit with timestamp
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                commit_msg = f"Auto-commit: changes detected at {timestamp}"
                commit_code, commit_out, commit_err = run_cmd(["git", "commit", "-m", commit_msg])
                
                if commit_code == 0:
                    print(f"Successfully committed changes: '{commit_msg}'", flush=True)
                    
                    # Push to remote GitHub repository
                    print("Pushing committed changes to GitHub remote...", flush=True)
                    push_code, push_out, push_err = run_cmd(["git", "push", "origin", "main"])
                    if push_code == 0:
                        print("Successfully pushed changes to remote origin/main.", flush=True)
                    else:
                        print(f"Push to remote failed: {push_err}", file=sys.stderr, flush=True)
                else:
                    print(f"Commit failed: {commit_err}", file=sys.stderr, flush=True)
            elif code != 0:
                print(f"Error checking git status: {stderr}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"Unexpected error in auto-commit loop: {e}", file=sys.stderr, flush=True)
            
        time.sleep(10) # check every 10 seconds

if __name__ == "__main__":
    main()
