import fitz 
import cv2
import numpy as np
    
"""
pdf_to_images func for converting the pdf into hi res image of the answer sheet 

increased the dpi to 300 

"""

def pdf_to_images(pdf_path, dpi=300):
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    images = []
 
    with fitz.open(pdf_path) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
 
            # handle grayscale or RGBA pdfs
            if pix.n == 1:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            elif pix.n == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            else:
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
 
            images.append(img)
 
    return images


"""

clean_for_ocr func for taking the hi res image and then first converting it to grayscale(0 - 255)

increased sharpness

then adaptive threshold for ignoring disteactions like shadows and unwanted ink marks and then converting 
it to exclusive black and white only 0(black) or 255(white)

"""

def clean_for_ocr(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clean = cv2.adaptiveThreshold(sharpened, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    return clean

"""
getting cropped images of answer for every question 
clamps the crop box to the image boundary so out-of-range coordinates don't return a wrong-sized one

"""


def extract_snippet(image, x, y, w, h):
    img_h, img_w = image.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(x + w, img_w), min(y + h, img_h)
    return image[y0:y1, x0:x1]
