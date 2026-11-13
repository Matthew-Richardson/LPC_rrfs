import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec = importlib.util.spec_from_file_location('rrfs', Path(__file__).resolve().parents[1]/'scripts/update_rrfs.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class ProcessingTests(unittest.TestCase):
    def test_cumulative_message_not_last_hour(self):
        rows = r.parse_index('1:0:d=2026111218:APCP:surface:23-24 hour acc fcst:\n2:100:d=2026111218:APCP:surface:0-1 day acc fcst:\n3:250:d=2026111218:TMP:2 m above ground:24 hour fcst:\n')
        self.assertEqual(r.select_record(rows,'APCP','surface',True)['offset'],100)
        self.assertEqual(r.select_record(rows,'APCP','surface',True)['end'],249)

    def test_ambiguous_accumulation_rejected(self):
        rows=r.parse_index('1:0:d=x:APCP:surface:0-24 hour acc fcst:\n2:100:d=x:APCP:surface:0-1 day acc fcst:\n')
        with self.assertRaises(ValueError):r.select_record(rows,'APCP','surface',True)

    def test_dry_cells_transparent_temperature_opaque(self):
        self.assertEqual(int(r.colorize(np.array([[0,.009,.01]]),'qpf')[0,0,3]),0)
        self.assertEqual(int(r.colorize(np.array([[0,.009,.01]]),'qpf')[0,1,3]),0)
        self.assertGreater(int(r.colorize(np.array([[0,.009,.01]]),'qpf')[0,2,3]),0)
        self.assertGreater(int(r.colorize(np.array([[-40]]),'temp')[0,0,3]),0)

    def test_mercator_orientation(self):
        west,south,east,north=r.BOUNDS
        x0,y0=r.mercator(west,south);x1,y1=r.mercator(east,north)
        self.assertLess(x0,x1);self.assertLess(y0,y1)


if __name__=='__main__':unittest.main()
