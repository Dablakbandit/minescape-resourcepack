import os

def list_files(folder):
    files = os.listdir(folder)

    for file in files:
        
        file_path = os.path.join(folder, file)
        
        if os.path.isdir(file_path):
            # Recursively call the function for subdirectories
            list_files(file_path)
        else:
            filep = "models/blocks/geyser_custom/ms" + file_path.replace(os.getcwd(), "").replace("\\", "/")
            filea = "attachables/ms/item" + file_path.replace(os.getcwd(), "").replace("\\", "/")

            if len(filep) >= 80:
                print(filep + ": " + str(len(filep)))
                
            if len(filea) >= 80:
                print("A " + filea + ": " + str(len(filea)))

folder = os.getcwd()
print(folder)
list_files(folder)

input("Press Enter to exit...")