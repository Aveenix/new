import os
import shutil

def clean_pycache(root_dir='.'):
    """
    Recursively deletes __pycache__ directories and .pyc files.
    """
    for root, dirs, files in os.walk(root_dir):
        # Delete __pycache__ directories
        for dir_name in dirs:
            if dir_name == '__pycache__':
                dir_path = os.path.join(root, dir_name)
                print(f"Deleting directory: {dir_path}")
                try:
                    shutil.rmtree(dir_path)
                except Exception as e:
                    print(f"Error deleting {dir_path}: {e}")

        # Delete .pyc, .pyo, and .pyd files
        for file_name in files:
            if file_name.endswith(('.pyc', '.pyo', '.pyd')):
                file_path = os.path.join(root, file_name)
                print(f"Deleting file: {file_path}")
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")

if __name__ == "__main__":
    current_dir = os.getcwd()
    print(f"Starting cleanup in: {current_dir}")
    clean_pycache(current_dir)
    print("Cleanup completed.")
