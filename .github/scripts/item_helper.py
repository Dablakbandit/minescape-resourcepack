import json
import os
from tkinter import Tk, filedialog
import requests
from PIL import Image
from io import BytesIO
import win32clipboard
from tkinter import Toplevel, Label, Button
from PIL import ImageTk

with open('assets/minecraft/models/item/flint.json') as f:
    flint = json.load(f)

def can_resize_image(image_path, target_size):
    image = Image.open(image_path)
    original_size = image.size
    return original_size[0] <= target_size[0] and original_size[1] <= target_size[1]

def resize_image_with_padding(image_path, output_path, target_size):
    image = Image.open(image_path)
    original_size = image.size

    # Create a new image with transparent background
    new_image = Image.new("RGBA", target_size, (0, 0, 0, 0))

    # Calculate the position to paste the original image
    x = (target_size[0] - original_size[0]) // 2
    y = (target_size[1] - original_size[1]) // 2

    # Paste the original image onto the new image
    new_image.paste(image, (x, y))

    # Save the new image
    new_image.save(output_path)

target_size = (32, 32)

clipboard_format = win32clipboard.RegisterClipboardFormat('PNG')

# Prompt user to confirm the image
def on_yes():
    global user_response
    user_response = 'yes'
    confirm_window.destroy()

def on_no():
    global user_response
    user_response = 'no'
    confirm_window.destroy()

fix = True
for item in flint['overrides']:
    modelFile = item['model']
    if modelFile == 'item/empty' or not modelFile.startswith('ms:'):
        continue
    #remove ms: prefix
    modelFile = modelFile[3:]

    if not os.path.exists(f'assets/ms/models/{modelFile}.json'):
        image_path = f'assets/minecraft/textures/item/ms/{modelFile}.png'
        print(f"Path {modelFile} does not exist.")

        if not fix:
            continue

        url = input("Enter the URL of the image file: ")
        if url:
            print(f"Entered URL: {url}")
            # Download the file
            response = requests.get(url)
            if response.status_code == 200:
                os.makedirs(os.path.dirname(image_path), exist_ok=True)
                with open(image_path, 'wb') as image_file:
                    image_file.write(response.content)
                print(f"Downloaded and saved {modelFile}.png")
                if can_resize_image(image_path, target_size):
                    resize_image_with_padding(image_path, image_path, target_size)
                    print(f"Resized {modelFile}.png")
                else: 
                    print(f"Image is too large. Maximum size is {target_size[0]}x{target_size[1]}")
            else:
                print(f"Failed to download the file. Status code: {response.status_code}")
                continue
        else:
            win32clipboard.OpenClipboard()
            try:
                clipboard_content = win32clipboard.GetClipboardData(clipboard_format)
            except TypeError:
                print("Specified clipboard format is not available.")
                clipboard_content = None
            finally:
                win32clipboard.CloseClipboard()
            
            print(f"Clipboard content: {clipboard_content}")

            if clipboard_content:
                image_bytes = BytesIO(clipboard_content)
                image = Image.open(image_bytes)

                confirm_window = Toplevel()
                confirm_window.title("Confirm Image")

                img = ImageTk.PhotoImage(image)
                img_label = Label(confirm_window, image=img)
                img_label.pack()

                yes_button = Button(confirm_window, text="Yes", command=on_yes)
                yes_button.pack(side="left")

                no_button = Button(confirm_window, text="No", command=on_no)
                no_button.pack(side="right")

                # Move the window to the center of the screen
                confirm_window.update_idletasks()
                confirm_window.geometry(f"+{confirm_window.winfo_screenwidth() // 2 - confirm_window.winfo_width() // 2}+{confirm_window.winfo_screenheight() // 2 - confirm_window.winfo_height() // 2}")

                #Open above current window
                confirm_window.attributes("-topmost", True)

                confirm_window.wait_window()

                if user_response != 'yes':
                    print("Image not confirmed by user.")
                    continue

                if can_resize_image(image_bytes, target_size):
                    os.makedirs(os.path.dirname(image_path), exist_ok=True)
                    resize_image_with_padding(image_bytes, image_path, target_size)
                    print(f"Resized and saved {modelFile}.png")
                else:
                    print(f"Image is too large. Maximum size is {target_size[0]}x{target_size[1]}")
                # clear the clipboard
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.CloseClipboard()
            else:
                print("No valid image found in clipboard.")
                root = Tk()
                root.withdraw()  # Hide the root window
                file_path = filedialog.askopenfilename(title="Select the image file", filetypes=[("Image files", "*.png")])
                if file_path:
                    print(f"Selected file: {file_path}")
                    if can_resize_image(file_path, target_size):
                        os.makedirs(os.path.dirname(image_path), exist_ok=True)
                        resize_image_with_padding(file_path, image_path, target_size)
                        print(f"Resized and saved {modelFile}.png")
                    else:
                        print(f"Image is too large. Maximum size is {target_size[0]}x{target_size[1]}")
                        continue
                else:
                    print("No file selected.")
                    continue

        # Create the model file
        os.makedirs(os.path.dirname(f'assets/ms/models/{modelFile}.json'), exist_ok=True)
        with open(f'assets/ms/models/{modelFile}.json', 'w') as f:
            json.dump({
                "parent": "item/handheld",
                "textures": {
                    "layer0": f"item/ms/{modelFile}"
                }
            }, f, indent=4)