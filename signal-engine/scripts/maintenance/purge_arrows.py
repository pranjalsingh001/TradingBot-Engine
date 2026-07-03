import os

def purge_arrow(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                if "→" in content:
                    print(f"Purging in {path}")
                    new_content = content.replace("→", "->")
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(new_content)

purge_arrow("services")
