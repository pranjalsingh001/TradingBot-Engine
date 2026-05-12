import os

def purge_arrow_binary(directory):
    # UTF-8 bytes for →
    target = b"\xe2\x86\x92"
    replacement = b"->"
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                with open(path, "rb") as f:
                    data = f.read()
                
                if target in data:
                    print(f"Purging binary matches in {path}")
                    new_data = data.replace(target, replacement)
                    with open(path, "wb") as f:
                        f.write(new_data)

purge_arrow_binary("services")
