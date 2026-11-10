"""
Packaging Script for Coursera Project Submission
Creates a clean, self-contained ZIP archive of all project source code,
configurations, tests, reports, and runbooks while excluding virtual
environments and cached byte-code.
"""

import os
import zipfile

OUTPUT_ZIP = "coursera_project_submission.zip"
EXCLUDE_DIRS = {"deployment_env", ".venv", "venv", ".git", "__pycache__"}
EXCLUDE_EXTS = {".pyc", ".pyo", ".pyd"}

def package_project():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    zip_path = os.path.join(root_dir, OUTPUT_ZIP)

    print(f"📦 Packaging project files into {OUTPUT_ZIP}...")
    file_count = 0

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(root_dir):
            # Modify dirs in-place to skip excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

            for file in files:
                if file == OUTPUT_ZIP:
                    continue
                ext = os.path.splitext(file)[1]
                if ext in EXCLUDE_EXTS:
                    continue

                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, root_dir)
                zipf.write(full_path, rel_path)
                file_count += 1

    zip_size_kb = os.path.getsize(zip_path) / 1024.0
    print(f"✅ Submission archive created successfully!")
    print(f"   • Path: {zip_path}")
    print(f"   • Total Files Archived: {file_count}")
    print(f"   • Archive Size: {zip_size_kb:.2f} KB\n")

if __name__ == "__main__":
    package_project()

