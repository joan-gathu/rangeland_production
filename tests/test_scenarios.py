import os
import unittest
import tempfile
import shutil
import json

from pygeoprocessing.testing import scm
DATA_DIR = os.path.join(os.path.abspath(__file__), '..', 'data', 'invest-data')
FW_DATA = os.path.join(DATA_DIR, 'Base_Data', 'Freshwater')


class ScenariosTest(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.workspace)

    def test_collect_simple_parameters(self):
        from natcap.invest import scenarios
        params = {
            'a': 1,
            'b': u'hello there',
            'c': 'plain bytestring'
        }

        archive_path = os.path.join(self.workspace, 'archive.invs.tar.gz')

        scenarios.collect_parameters(params, archive_path)
        out_directory = os.path.join(self.workspace, 'extracted_archive')
        scenarios.extract_archive(out_directory, archive_path)
        self.assertEqual(len(os.listdir(out_directory)), 1)

        self.assertEqual(
            json.load(open(os.path.join(out_directory, 'parameters.json'))),
            {'a': 1, 'b': u'hello there', 'c': u'plain bytestring'})

    @scm.skip_if_data_missing(FW_DATA)
    def test_collect_gdal_raster(self):
        pass

