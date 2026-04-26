#!/usr/bin/env python3
"""
현재 화면의 모든 노드 출력 - 팝업 X버튼 좌표 확인용
팝업이 뜬 상태에서 실행: python3 dump_check.py
"""
import subprocess, re
import xml.etree.ElementTree as ET
from pathlib import Path

REMOTE = "/sdcard/dump_check.xml"
LOCAL  = str(Path.home() / "dump_check.xml")

subprocess.run(f"adb shell uiautomator dump {REMOTE}", shell=True)
subprocess.run(f"adb pull {REMOTE} {LOCAL}", shell=True, capture_output=True)

try:
    root = ET.parse(LOCAL).getroot()
except Exception as e:
    print(f"dump 실패: {e}")
    print("ADB 연결 확인: adb devices")
    exit(1)

print(f"\n{'─'*90}")
print(f"{'x':>5} {'y':>5}  {'bounds':<28} {'click':<6} {'text':<20} {'desc':<20} {'resource-id'}")
print(f"{'─'*90}")

for node in root.iter("node"):
    nums = list(map(int, re.findall(r"\d+", node.get("bounds",""))))
    if len(nums) < 4:
        continue
    x1, y1, x2, y2 = nums
    nx = (x1+x2)//2
    ny = (y1+y2)//2
    txt   = node.get("text","").strip()[:18]
    desc  = node.get("content-desc","").strip()[:18]
    resid = node.get("resource-id","").strip()
    click = node.get("clickable","")

    if txt or desc or click == "true":
        print(f"{nx:>5} {ny:>5}  [{x1},{y1},{x2},{y2}]  {click:<6} {txt:<20} {desc:<20} {resid}")

print(f"{'─'*90}\n")
