import os
import mimetypes
import glob
import re

def get_next_sequence_number():
    """Find the next available sequence number for the output file."""
    script_dir = os.path.abspath(os.path.dirname(__file__))
    pattern = os.path.join(script_dir, "project_structure_*.txt")
    existing_files = glob.glob(pattern)
    
    if not existing_files:
        return 1
    
    # Extract sequence numbers from existing files
    sequence_numbers = []
    for file_path in existing_files:
        basename = os.path.basename(file_path)
        match = re.search(r'project_structure_(\d+)\.txt', basename)
        if match:
            sequence_numbers.append(int(match.group(1)))
    
    if not sequence_numbers:
        return 1
    
    # Return the next number in sequence
    return max(sequence_numbers) + 1

def generate_project_structure():
    """Generate a text file containing the project structure with file contents."""
    # Get the absolute path of the script's directory
    script_dir = os.path.abspath(os.path.dirname(__file__))
    # Change to that directory to ensure we're working only there
    os.chdir(script_dir)
    
    # Generate a unique filename with sequence number
    seq_num = get_next_sequence_number()
    output_file = os.path.join(script_dir, f"project_structure_{seq_num}.txt")
    
    with open(output_file, 'w', encoding='utf-8', errors='replace') as f:
        # Get items in the script directory only, excluding specified patterns
        items = get_directory_items(script_dir, output_file)
        
        # Process each item at root level
        for i, item in enumerate(items):
            is_last = i == len(items) - 1
            
            if os.path.isdir(os.path.join(script_dir, item)):
                # It's a directory
                if is_last:
                    f.write(f"└───{item}\n")
                    process_directory(os.path.join(script_dir, item), f, "    ", output_file, script_dir)
                else:
                    f.write(f"├───{item}\n")
                    process_directory(os.path.join(script_dir, item), f, "│   ", output_file, script_dir)
            else:
                # It's a file - at root level, format as in the example
                f.write(f"│   {item}\n")
                # Include file content
                content = read_file_content(os.path.join(script_dir, item))
                f.write(f"│   [\n")
                content_lines = content.split('\n')
                for line in content_lines:
                    f.write(f"│       {line}\n")
                f.write(f"│   ]\n")
    
    print(f"Project structure has been written to {output_file}")

def should_exclude(item_path):
    """Check if an item should be excluded based on patterns."""
    # Exclude __pycache__ directories
    if os.path.isdir(item_path) and "__pycache__" in item_path:
        return True
    
    # Exclude migrations directories
    if os.path.isdir(item_path) and "migrations" in item_path:
        return True
    
    # Exclude .pyc files
    if item_path.endswith('.pyc'):
        return True
    
    # Exclude all project_structure files
    if os.path.basename(item_path).startswith("project_structure_") and item_path.endswith(".txt"):
        return True
    
    return False

def get_directory_items(dir_path, output_file):
    """Get sorted list of items in a directory, excluding the output file and specified patterns."""
    # Get absolute path to output file to exclude it
    abs_output_path = os.path.abspath(output_file)
    
    try:
        # List directory contents
        items = sorted(os.listdir(dir_path))
        
        # Filter out the output file itself and items matching exclude patterns
        filtered_items = []
        for item in items:
            item_path = os.path.join(dir_path, item)
            
            # Skip the output file
            if os.path.abspath(item_path) == abs_output_path:
                continue
                
            # Skip symlinks that might point outside
            if os.path.islink(item_path):
                continue
                
            # Skip items matching exclude patterns
            if should_exclude(item_path):
                continue
                
            filtered_items.append(item)
        
        return filtered_items
    except Exception as e:
        print(f"Error listing directory {dir_path}: {e}")
        return []

def is_binary_file(file_path):
    """Determine if a file is binary or text."""
    # Initialize mimetypes
    if not mimetypes.inited:
        mimetypes.init()
    
    # Check by mime type first
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type and not mime_type.startswith(('text/', 'application/json', 'application/xml', 'application/javascript')):
        return True
        
    # Fallback: check for null bytes
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(4096)
            return b'\0' in chunk
    except Exception:
        return True  # If we can't read it, assume binary

def read_file_content(file_path, max_length=500000):
    """Read content from a file, handling binary files and errors."""
    try:
        # Check if binary
        if is_binary_file(file_path):
            return "[Binary file - content not shown]"
            
        # Read text file
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(max_length + 1)
            
        # Handle truncation
        if len(content) > max_length:
            content = content[:max_length] + "... [truncated]"
            
        # Return raw content without escaping special characters
        return content
    except Exception as e:
        return f"[Error reading file: {str(e)}]"

def process_directory(dir_path, file_obj, indent, output_file, script_dir):
    """Recursively process a directory and write its structure to the file."""
    # Safety check - ensure we're still within the script directory
    rel_path = os.path.relpath(dir_path, script_dir)
    if rel_path.startswith('..') or rel_path == '.':
        return  # Don't process if it's outside our script directory
    
    try:
        # List directory contents
        items = get_directory_items(dir_path, output_file)
        
        # Process each item
        for i, item in enumerate(items):
            item_path = os.path.join(dir_path, item)
            is_last = i == len(items) - 1
            
            # Safety check - don't follow symlinks or items outside our script directory
            if os.path.islink(item_path):
                continue
                
            rel_path = os.path.relpath(item_path, script_dir)
            if rel_path.startswith('..'):
                continue
            
            if os.path.isdir(item_path):
                # It's a directory
                if is_last:
                    file_obj.write(f"{indent}└───{item}\n")
                    process_directory(item_path, file_obj, indent + "    ", output_file, script_dir)
                else:
                    file_obj.write(f"{indent}├───{item}\n")
                    process_directory(item_path, file_obj, indent + "│   ", output_file, script_dir)
            else:
                # It's a file
                file_obj.write(f"{indent}{item}\n")
                # Include file content
                content = read_file_content(item_path)
                file_obj.write(f"{indent}[\n")
                content_lines = content.split('\n')
                for line in content_lines:
                    file_obj.write(f"{indent}    {line}\n")
                file_obj.write(f"{indent}]\n")
    except PermissionError:
        file_obj.write(f"{indent}[Permission denied]\n")
    except Exception as e:
        file_obj.write(f"{indent}[Error: {str(e)}]\n")

if __name__ == "__main__":
    generate_project_structure()