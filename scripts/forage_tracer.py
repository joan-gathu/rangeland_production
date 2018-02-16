"""Tracer code for Forage model development."""
import os

import natcap.invest.forage
import logging

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger('forage_tracer')

POSSIBLE_DROPBOX_LOCATIONS = [
    r'D:\Dropbox',
    r'C:\Users\Rich\Dropbox',
    r'C:\Users\rpsharp\Dropbox',
    r'E:\Dropbox']

LOGGER.info("checking dropbox locations")
for dropbox_path in POSSIBLE_DROPBOX_LOCATIONS:
    print dropbox_path
    if os.path.exists(dropbox_path):
        BASE_DROPBOX_DIR = dropbox_path
        break
LOGGER.info("found %s", BASE_DROPBOX_DIR)


def main():
    """Entry point."""
    args = {
        'workspace_dir': 'forage_tracer_workspace',
        'starting_year': '2016',
        'starting_month': '5',
        'n_months': '24',
        'aoi_path': None,
    }
    LOGGER.info('launching forage model')
    natcap.invest.forage.execute(args)

if __name__ == '__main__':
    main()
