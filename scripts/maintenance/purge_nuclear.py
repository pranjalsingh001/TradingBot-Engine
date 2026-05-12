import os
import re

def purge_all_non_ascii(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                try:
                    with open(path, "rb") as f:
                        data = f.read()
                    
                    new_data = re.sub(rb'[^\x00-\x7f]+', b'->', data)
                    
                    if new_data != data:
                        print(f"Purged non-ascii in {path}")
                        with open(path, "wb") as f:
                            f.write(new_data)
                except Exception as e:
                    print(f"Error processing {path}: {e}")

purge_all_non_ascii("services")
