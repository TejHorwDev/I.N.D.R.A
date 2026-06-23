from PIL import Image, ImageFilter, ImageOps
from pathlib import Path
import os

def image_editor(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Edits an image on the filesystem (resize, crop, blur, black-and-white, convert).
    """
    action = parameters.get("action", "").lower()
    source_path = parameters.get("source_path", "")
    
    if not action or not source_path:
        return "Must specify both an 'action' and a 'source_path'."
        
    if not os.path.exists(source_path):
        return f"File not found: {source_path}"
        
    try:
        img = Image.open(source_path)
        
        save_path = parameters.get("save_path", "")
        if not save_path:
            # Default save behavior: overwrite or append _edited
            p = Path(source_path)
            save_path = str(p.parent / f"{p.stem}_edited{p.suffix}")
            
        if action == "resize":
            width = parameters.get("width")
            height = parameters.get("height")
            if not width or not height:
                return "Resize requires 'width' and 'height'."
            img = img.resize((int(width), int(height)))
            img.save(save_path)
            return f"Image resized and saved to: {save_path}"
            
        elif action == "blur":
            radius = parameters.get("radius", 5)
            img = img.filter(ImageFilter.GaussianBlur(int(radius)))
            img.save(save_path)
            return f"Image blurred and saved to: {save_path}"
            
        elif action == "bw" or action == "grayscale":
            img = ImageOps.grayscale(img)
            img.save(save_path)
            return f"Image converted to black-and-white and saved to: {save_path}"
            
        elif action == "convert":
            format_ext = parameters.get("format", "jpg").lower().replace(".", "")
            if format_ext == "jpg":
                format_ext = "jpeg"
            
            p = Path(source_path)
            save_path = str(p.parent / f"{p.stem}.{format_ext}")
            
            # Convert RGBA to RGB for JPEG
            if format_ext == "jpeg" and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
                
            img.save(save_path, format=format_ext.upper())
            return f"Image converted to {format_ext.upper()} and saved to: {save_path}"
            
        else:
            return f"Unknown image editing action: {action}"
            
    except Exception as e:
        return f"Failed to edit image: {e}"
