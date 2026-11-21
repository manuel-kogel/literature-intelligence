import unittest
from unittest.mock import patch
import app_core

class TestCore(unittest.TestCase):
    def test_abstract(self):
        self.assertEqual(app_core.abstract_from_index({'world':[1], 'Hello':[0]}), 'Hello world')
    def test_doi(self):
        self.assertEqual(app_core.clean_doi('https://doi.org/10.123/ABC'), '10.123/abc')
    def test_deduplicate(self):
        work = {'display_name':'Example', 'doi':'https://doi.org/10.1/A', 'authorships':[]}
        self.assertEqual(len(app_core.merge_results({'a':[work], 'b':[work]})), 1)
    def test_scoring(self):
        s, dim = app_core.score_work({'title':'Affective polarization following terrorist attacks', 'abstract':''})
        self.assertGreater(s, 0)
        self.assertIn('Affektive Polarisierung', dim)
if __name__ == '__main__': unittest.main()
