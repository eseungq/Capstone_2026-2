"""Display-only CAM encoding. Never changes model input, raw CAM or geometry."""
import io
from PIL import Image


def encode_overlay(png,expected_size,cam_format='png',jpeg_quality=90):
    if cam_format not in ('png','jpeg'):raise ValueError('Unsupported CAM encoding')
    if not isinstance(jpeg_quality,int) or isinstance(jpeg_quality,bool) or not 1<=jpeg_quality<=95:raise ValueError('JPEG quality must be an integer from 1 to 95')
    with Image.open(io.BytesIO(png)) as source:
        if source.format!='PNG' or source.size!=tuple(expected_size):raise ValueError('Invalid source CAM PNG geometry')
        source.verify()
    if cam_format=='png':return png,'image/png'
    with Image.open(io.BytesIO(png)) as source:
        if source.mode!='RGB':raise ValueError('Expected the original RGB overlay')
        source.load();encoded=io.BytesIO()
        # Explicit parameters for reproducibility. No EXIF orientation is copied:
        # the overlay already has EXIF-corrected display geometry.
        source.save(encoded,format='JPEG',quality=jpeg_quality,subsampling=2,optimize=False,progressive=False)
    result=encoded.getvalue()
    with Image.open(io.BytesIO(result)) as decoded:
        if decoded.format!='JPEG' or decoded.size!=tuple(expected_size):raise ValueError('Invalid encoded CAM geometry')
        decoded.verify()
    return result,'image/jpeg'
