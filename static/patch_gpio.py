#!/usr/bin/env python3
# This is a patch script to modify the Jetson GPIO library to work with Orin Nano

import os
import sys
import shutil
import re

# Path to the Jetson.GPIO library
gpio_module_path = "/usr/lib/python3/dist-packages/Jetson/GPIO"
gpio_pin_data_path = os.path.join(gpio_module_path, "gpio_pin_data.py")

# Backup original file
backup_path = gpio_pin_data_path + ".backup"
if not os.path.exists(backup_path):
    print(f"Creating backup of {gpio_pin_data_path} to {backup_path}")
    shutil.copy2(gpio_pin_data_path, backup_path)
else:
    print(f"Backup already exists at {backup_path}")

# Read the original file
with open(gpio_pin_data_path, 'r') as f:
    content = f.read()

# Modify the get_model function to detect Orin Nano
pattern = r"def get_model\(\):(.*?)raise Exception\('Could not determine Jetson model'\)"
replacement = """def get_model():
    # Force return Orin Nano model regardless of detection
    return 'JETSON_ORIN_NANO'
"""

modified_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

# Add Orin Nano pin data if not already present
if "JETSON_ORIN_NANO" not in content:
    # Using the same pin data as AGX Orin or Xavier NX, which is typically compatible
    orin_data = """
# Orin Nano specific pin data
JETSON_ORIN_NANO = (
    'JETSON_ORIN_NANO',
    {
        'P1_REVISION': 3,
        'RAM': '8GB',
        'REVISION': '1.0',
        'TYPE': 'Orin Nano',
        'MANUFACTURER': 'NVIDIA',
        'PROCESSOR': 'A78AE'
    }
)

"""
    # Find the last JETSON_* model defined in the file
    last_model_pos = content.rfind("JETSON_")
    last_model_def_end = content.find(")", last_model_pos)
    
    # Insert the Orin data after the last model definition
    modified_content = modified_content[:last_model_def_end+1] + orin_data + modified_content[last_model_def_end+1:]

# Add the Orin Nano to the list of models (if needed)
if "_orin_nano_models = []" in modified_content:
    modified_content = modified_content.replace("_orin_nano_models = []", "_orin_nano_models = ['JETSON_ORIN_NANO']")
else:
    # Find where the models are defined and add Orin Nano
    models_pos = modified_content.find("_jetson_models = ")
    if models_pos != -1:
        models_end_pos = modified_content.find("]", models_pos)
        if models_end_pos != -1:
            modified_content = modified_content[:models_end_pos] + ", 'JETSON_ORIN_NANO'" + modified_content[models_end_pos:]

# Write the modified content back to the file
with open(gpio_pin_data_path, 'w') as f:
    f.write(modified_content)
    
print(f"Successfully patched {gpio_pin_data_path}")
print("The Jetson GPIO library should now work with your Orin Nano.")
print("You can revert to the original file with:")
print(f"sudo cp {backup_path} {gpio_pin_data_path}")