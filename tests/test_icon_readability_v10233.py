import unittest
from pathlib import Path
from PIL import Image
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
            points = [(x, y) for y in range(size) for x in range(size)
                      if max(frame.getpixel((x, y))) < 170]
            self.assertTrue(points, 'CT mark must have dark pixels')
            xs = [x for x, _ in points]
            ys = [y for _, y in points]
            self.assertGreaterEqual(max(ys)-min(ys)+1,int(size*.62))
            self.assertGreaterEqual(max(xs)-min(xs)+1,int(size*.73))
