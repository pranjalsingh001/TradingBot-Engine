import os

def find_non_ascii(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                with open(path, "rb") as f:
                    data = f.read()
                
                for i, byte in enumerate(data):
                    if byte > 127:
                        print(f"Found non-ascii at {path}:{i} - Byte: {hex(byte)}")

find_non_ascii("services")
