"""RouteDEM for exposing the natcap.invest's routing package to UI."""
from __future__ import absolute_import

import os
import logging

from osgeo import gdal
from osgeo import ogr
import pygeoprocessing
import pygeoprocessing.routing
import natcap.invest.pygeoprocessing_0_3_3.routing
import natcap.invest.pygeoprocessing_0_3_3.routing.routing_core
import taskgraph
import numpy

from . import utils
from . import validation

LOGGER = logging.getLogger('natcap.invest.routing.routedem')

# replace %s with file suffix
_TARGET_FILLED_PITS_FILED_PATTERN = 'filled%s.tif'
_TARGET_SLOPE_FILE_PATTERN = 'slope%s.tif'
_TARGET_FLOW_DIRECTION_FILE_PATTERN = 'flow_direction%s.tif'
_FLOW_ACCUMULATION_FILE_PATTERN = 'flow_accumulation%s.tif'
_STREAM_MASK_FILE_PATTERN = 'stream_mask%s.tif'
_DOWNSTREAM_DISTANCE_FILE_PATTERN = 'downstream_distance%s.tif'

_ROUTING_FUNCS = {
    'D8': {
        'flow_accumulation': pygeoprocessing.routing.flow_accumulation_d8,
        'flow_direction': pygeoprocessing.routing.flow_dir_d8,
        'threshold_flow': None,  # Defined in source code here
        'distance_to_channel': pygeoprocessing.routing.distance_to_channel_d8,
    },
    'MFD': {
        'flow_accumulation': pygeoprocessing.routing.flow_accumulation_mfd,
        'flow_direction': pygeoprocessing.routing.flow_dir_mfd,
        'threshold_flow': pygeoprocessing.routing.extract_streams_mfd,
        'distance_to_channel': pygeoprocessing.routing.distance_to_channel_mfd,
    }
}


def _threshold_flow(flow_accum_pixels, threshold, in_nodata, out_nodata):
    out_matrix = numpy.empty(flow_accum_pixels.shape, dtype=numpy.uint8)
    out_matrix[:] = out_nodata
    valid_pixels = ~numpy.isclose(flow_accum_pixels, in_nodata)
    stream_mask = (flow_accum_pixels > threshold)
    out_matrix[valid_pixels & stream_mask] = 1
    out_matrix[valid_pixels & ~stream_mask] = 0
    return out_matrix


def _log_callable(message, func):
    def _call(*args, **kwargs):
        LOGGER.info(message)
        return func(*args, **kwargs)
    return _call


def execute(args):
    """RouteDEM: Hydrological routing.

    This model exposes the pygeoprocessing D8 and Multiple Flow Direction
    routing functionality as an InVEST model.

    Parameters:
        args['workspace_dir'] (string): output directory for intermediate,
            temporary, and final files
        args['results_suffix'] (string): (optional) string to append to any
            output file names
        args['dem_path'] (string): path to a digital elevation raster
        args['algorithm'] (string): The routing algorithm to use.  Must be
            one of 'D8' or 'MFD' (case-insensitive).
        args['calculate_flow_accumulation'] (bool): If True, model will
            calculate a flow accumulation raster.
        args['calculate_stream_threshold'] (bool): if True, model will
            calculate a stream classification layer by thresholding flow
            accumulation to the provided value in
            ``args['threshold_flow_accumulation']``.
        args['threshold_flow_accumulation'] (int): The number of upstream
            cells that must flow into a cell before it's classified as a
            stream.
        args['calculate_downstream_distance'] (bool): If True, and a stream
            threshold is calculated, model will calculate a downstream
            distance raster in units of pixels.
        args['calculate_slope'] (bool):  If True, model will calculate a
            slope raster from the DEM.

    Returns:
        ``None``
    """
    file_suffix = utils.make_suffix_string(args, 'results_suffix')
    task_cache_dir = os.path.join(args['workspace_dir'], '_tmp_work_tokens')
    utils.make_directories([args['workspace_dir'], task_cache_dir])
    dem_info = pygeoprocessing.get_raster_info(args['dem_path'])
    if dem_info['n_bands'] > 1:
        LOGGER.warn(
            "There are more than 1 bands in %s.  RouteDEM will only operate "
            "on band 1.", args['dem_path'])

    # Check the algorithm early so we can fail quickly.
    algorithm = args['algorithm'].upper()
    try:
        routing_funcs = _ROUTING_FUNCS[algorithm]
    except KeyError:
        raise RuntimeError(
            'Invalid algorithm specified (%s). Must be one of %s' % (
                args['algorithm'], ', '.join(sorted(_ROUTING_FUNCS.keys()))))

    dem_raster_path_band = (args['dem_path'], 1)

    graph = taskgraph.TaskGraph(task_cache_dir, n_workers=-1)

    # Calculate slope
    if 'calculate_slope' in args and bool(args['calculate_slope']):
        target_slope_path = os.path.join(
            args['workspace_dir'], _TARGET_SLOPE_FILE_PATTERN % file_suffix)
        graph.add_task(
            _log_callable('Calculating slope',
                          pygeoprocessing.calculate_slope),
            args=(dem_raster_path_band,
                  target_slope_path),
            task_name='calculate_slope',
            target_path_list=[target_slope_path])

    dem_filled_pits_path = _TARGET_FILLED_PITS_FILED_PATTERN % file_suffix
    filled_pits_task = graph.add_task(
        _log_callable('Filling hydrological sinks',
                      pygeoprocessing.routing.fill_pits),
        args=((args['dem_path'], 1),
              dem_filled_pits_path,
              args['workspace_dir']),
        task_name='fill_pits',
        target_path_list=[dem_filled_pits_path])

    # Calculate flow accumulation
    LOGGER.info("calculating flow direction")
    flow_dir_path = os.path.join(
        args['workspace_dir'],
        _TARGET_FLOW_DIRECTION_FILE_PATTERN % file_suffix)
    flow_direction_task = graph.add_task(
        _log_callable('Calculating flow direction',
                      routing_funcs['flow_direction']),
        args=((args['dem_path'], 1),
              flow_dir_path,
              args['workspace_dir']),
        target_path_list=[flow_dir_path],
        task_name='flow_dir_%s' % algorithm)

    if ('calculate_flow_accumulation' in args and
            bool(args['calculate_flow_accumulation'])):
        LOGGER.info("calculating flow accumulation")
        flow_accumulation_path = os.path.join(
            args['workspace_dir'],
            _FLOW_ACCUMULATION_FILE_PATTERN % file_suffix)
        flow_accum_task = graph.add_task(
            _log_callable('Calculating flow accumulation',
                          routing_funcs['flow_accumulation']),
            args=((flow_dir_path, 1),
                  flow_accumulation_path
            ),  # TODO allow weight raster to be provided.
            target_path_list=[flow_accumulation_path],
            task_name='flow_accumulation_%s' % algorithm,
            dependent_task_list=[flow_direction_task])

        if ('calculate_stream_threshold' in args and
                bool(args['calculate_stream_threshold'])):
            stream_mask_path = _STREAM_MASK_FILE_PATTERN % file_suffix
            if algorithm == 'D8':
                flow_accum_task.join()
                flow_accum_info = pygeoprocessing.get_raster_info(
                    flow_accumulation_path)
                stream_threshold_task = graph.add_task(
                    _log_callable('Classifying streams from flow '
                                  'accumulation raster',
                                  pygeoprocessing.raster_calculator),
                    args=(((flow_accumulation_path, 1),
                           (float(args['threshold_flow_accumulation']), 'raw'),
                           (flow_accum_info['nodata'][0], 'raw'),
                           (255, 'raw')),
                          _threshold_flow,
                          stream_mask_path,
                          gdal.GDT_Byte,
                          255),
                    target_path_list=[stream_mask_path],
                    task_name='stream_thresholding_D8',
                    dependent_task_list=[flow_accum_task])
            else:  # MFD
                stream_threshold_task = graph.add_task(
                    _log_callable('Classifying streams from MFD flow '
                                  'accumulation',
                                  routing_funcs['threshold_flow']),
                    # TODO: support trace threshold proportion
                    args=((flow_accumulation_path, 1),
                          (flow_dir_path, 1),
                          float(args['stream_threshold']),
                          stream_mask_path),
                    target_path_list=[stream_mask_path],
                    task_name=['stream_extraction_MFD'],
                    dependent_path_list=[flow_accum_task])

            if ('calculate_downstream_distance' in args and
                    bool(args['calculate_downstream_distance'])):
                distance_path = os.path.join(
                    args['workspace_dir'],
                    _DOWNSTREAM_DISTANCE_FILE_PATTERN % file_suffix)
                graph.add_task(
                    _log_callable('Calculating distance to stream',
                                  routing_funcs['distance_to_channel']),
                    # TODO: support the weight raster
                    args=((flow_dir_path, 1),
                          (stream_mask_path, 1),
                          distance_path),
                    target_path_list=[distance_path],
                    task_name='downstream_distance_%s' % algorithm,
                    dependent_task_list=[stream_threshold_task])
    graph.join()
    # TODO: test routedem execute for MFD
    # TODO: test routedem execute for D8
    # TODO: test routedem validate function
    # TODO: add needed functionality to the UI
    # TODO: add n_workers to the UI if it makes sense.


@validation.invest_validator
def validate(args, limit_to=None):
    """Validate args to ensure they conform to `execute`'s contract.

    Parameters:
        args (dict): dictionary of key(str)/value pairs where keys and
            values are specified in `execute` docstring.
        limit_to (str): (optional) if not None indicates that validation
            should only occur on the args[limit_to] value. The intent that
            individual key validation could be significantly less expensive
            than validating the entire `args` dictionary.

    Returns:
        list of ([invalid key_a, invalid_keyb, ...], 'warning/error message')
            tuples. Where an entry indicates that the invalid keys caused
            the error message in the second part of the tuple. This should
            be an empty list if validation succeeds.
    """
    missing_key_list = []
    no_value_list = []
    validation_error_list = []

    required_keys = [
        'workspace_dir',
        'dem_path']

    if ('calculate_stream_threshold' in args and
            args['calculate_stream_threshold']):
        required_keys.append('threshold_flow_accumulation')

    for key in required_keys:
        if limit_to is None or limit_to == key:
            if key not in args:
                missing_key_list.append(key)
            elif args[key] in ['', None]:
                no_value_list.append(key)

    if len(missing_key_list) > 0:
        # if there are missing keys, we have raise KeyError to stop hard
        raise KeyError(
            "The following keys were expected in `args` but were missing " +
            ', '.join(missing_key_list))

    if len(no_value_list) > 0:
        validation_error_list.append(
            (no_value_list, 'parameter has no value'))

    file_type_list = [('dem_path', 'raster')]

    # check that existing/optional files are the correct types
    with utils.capture_gdal_logging():
        for key, key_type in file_type_list:
            if (limit_to in [None, key]) and key in required_keys:
                if not os.path.exists(args[key]):
                    validation_error_list.append(
                        ([key], 'not found on disk'))
                    continue
                if key_type == 'raster':
                    raster = gdal.OpenEx(args[key])
                    if raster is None:
                        validation_error_list.append(
                            ([key], 'not a raster'))
                    del raster
                elif key_type == 'vector':
                    vector = gdal.OpenEx(args[key])
                    if vector is None:
                        validation_error_list.append(
                            ([key], 'not a vector'))
                    del vector

    return validation_error_list
