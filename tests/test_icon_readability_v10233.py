import unittest
from pathlib import Path
from PIL import Image
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
class IconReadabilityTests(unittest.TestCase):
    def test_complete_windows_icon_sizes(self):
        im=Image.open(ROOT/'CT.ico')
        self.assertEqual(im.format,'ICO')
        for s in [16,24,32,40,48,64,96,128,256]:
            self.assertIn((s,s),im.info['sizes'])
    def test_small_icon_contrast_and_height(self):
        im=Image.open(ROOT/'CT.ico')
        for size in [16,24,32]:
            frame=im.ico.getimage((size,size)).convert('RGB')
            self.assertEqual(frame.getpixel((0,0)),(255,255,255))
            pixels=np.asarray(frame)
            mask=np.max(pixels,axis=2)<170
            ys,xs=np.where(mask)
            self.assertGreaterEqual(ys.max()-ys.min()+1,int(size*.62))
            self.assertGreaterEqual(xs.max()-xs.min()+1,int(size*.73))
