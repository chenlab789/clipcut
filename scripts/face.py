#!/usr/bin/env python
"""หาตำแหน่งหน้าคนพูดในคลิป (OpenCV Haar) → {"x","y","size"} เป็นสัดส่วนของภาพ หรือ None
ใช้ซูมกรอบวงกลม/รูปมุมของ Motion Explainer ไปที่หน้า — คลิปอัดจอมีหน้าเล็กๆ ที่มุม ครอปกลางจอ = ได้แต่สไลด์

  python face.py <คลิป>
"""
import sys
import json
import subprocess
import numpy as np

FF = "ffmpeg"


def find_face(src, samples=24):
    import cv2
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", src], text=True).strip())
    W = 1280  # หน้าเล็กมุมจอ (webcam ในคลิปอัดจอ) ย่อ 640 แล้วหาไม่เจอ
    raw = subprocess.run([FF, "-v", "error", "-i", src, "-vf", f"fps={samples / max(dur, 1):.5f},scale={W}:-2,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    probe = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                     "stream=width,height", "-of", "csv=p=0", src], text=True).strip().split(",")
    sw, sh = int(probe[0]), int(probe[1])
    h = round(sh * W / sw / 2) * 2
    n = len(raw) // (W * h)
    det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    hits = []
    for i in range(n):
        img = np.frombuffer(raw[i * W * h:(i + 1) * W * h], np.uint8).reshape(h, W)
        fs = det.detectMultiScale(img, scaleFactor=1.1, minNeighbors=6, minSize=(20, 20))
        if len(fs):
            x, y, w, hh = max(fs, key=lambda f: f[2] * f[3])  # หน้าใหญ่สุดในเฟรม
            hits.append(((x + w / 2) / W, (y + hh / 2) / h, w / W))
    if len(hits) < max(3, n // 4):  # เจอหน้าน้อยเกิน = ไม่เชื่อ
        return None
    a = np.array(hits)
    return {"x": round(float(np.median(a[:, 0])), 4), "y": round(float(np.median(a[:, 1])), 4),
            "size": round(float(np.median(a[:, 2])), 4), "hits": len(hits), "frames": n}


if __name__ == "__main__":
    print(json.dumps(find_face(sys.argv[1])))
