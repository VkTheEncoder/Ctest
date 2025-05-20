import cv2
import pytesseract
import numpy as np


def perform_ocr_with_preprocessing(regions):
    results = []
    for img, ts, coords in regions:
        if img.shape[0]<10 or img.shape[1]<20: continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        filt = cv2.bilateralFilter(gray, 11, 17, 17)
        thresh = cv2.adaptiveThreshold(
            filt, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        if np.mean(thresh)>127:
            thresh = cv2.bitwise_not(thresh)
        dil = cv2.dilate(thresh, np.ones((2,2),np.uint8), iterations=1)
        cfg = r'--oem 3 --psm 6 -l eng+chi_sim+jpn'
        text = pytesseract.image_to_string(dil, config=cfg).strip()
        if text:
            results.append((text, ts, coords))
    return results
