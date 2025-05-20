import cv2
import numpy as np


def extract_subtitle_regions(frames):
    regions = []
    for frame, ts in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2
        )
        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        h, w = frame.shape[:2]
        text_contours = []
        for c in contours:
            x,y,ww,hh = cv2.boundingRect(c)
            if 20<ww<w*0.9 and 8<hh<h*0.2 and y>h*0.6:
                text_contours.append((x,y,ww,hh))
        if text_contours:
            lines = group_text_contours(text_contours)
            for x,y,ww,hh in lines:
                pad=10
                xs, ys = max(0,x-pad), max(0,y-pad)
                xe, ye = min(w,x+ww+pad), min(h,y+hh+pad)
                regions.append((frame[ys:ye,xs:xe], ts, (xs,ys,xe,ye)))
        else:
            y0=int(h*0.8)
            regions.append((frame[y0:h,0:w], ts, (0,y0,w,h)))
    return regions


def group_text_contours(contours, max_y=10):
    if not contours: return []
    contours = sorted(contours, key=lambda c: c[1])
    lines = []
    cur = list(contours[0])
    for x,y,ww,hh in contours[1:]:
        if abs(y-cur[1])<=max_y:
            x1,y1 = min(cur[0],x), min(cur[1],y)
            x2 = max(cur[0]+cur[2], x+ww)
            y2 = max(cur[1]+cur[3], y+hh)
            cur = [x1, y1, x2-x1, y2-y1]
        else:
            lines.append(tuple(cur)); cur=[x,y,ww,hh]
    lines.append(tuple(cur))
    return lines
